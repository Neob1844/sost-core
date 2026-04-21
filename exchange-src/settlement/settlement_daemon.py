"""
SOST Gold Exchange — Settlement Daemon

Coordinates deal lifecycle:
  1. Monitors watchers for lock events
  2. Correlates events with deals
  3. Drives state transitions
  4. Triggers settlement or refund
"""

import time
import logging
import threading
from typing import Optional

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.watchers.ethereum_watcher import EthereumWatcher, EthEvent
from src.watchers.sost_watcher import SostWatcher, SostEvent
from src.settlement.refund_engine import RefundEngine
from src.operator.audit_log import AuditLog

log = logging.getLogger("settlement")

TICK_INTERVAL = 5  # seconds


class SettlementDaemon:
    def __init__(self, deal_store: DealStore, eth_watcher: EthereumWatcher,
                 sost_watcher: SostWatcher, refund_engine: RefundEngine,
                 audit: AuditLog):
        self.deals = deal_store
        self.eth = eth_watcher
        self.sost = sost_watcher
        self.refund = refund_engine
        self.audit = audit
        self.running = False
        self._deal_eth_map: dict[int, str] = {}  # deposit_id → deal_id
        self._deal_sost_map: dict[str, str] = {}  # sost_addr → deal_id

    def register_deal(self, deal: Deal):
        self.audit.log_event(deal.deal_id, "registered", deal.state.value)
        if deal.taker_eth_addr:
            pass  # will be mapped when deposit_id is known
        if deal.taker_sost_addr:
            self.sost.add_watch_address(deal.taker_sost_addr)
            self._deal_sost_map[deal.taker_sost_addr] = deal.deal_id
        if deal.maker_sost_addr:
            self.sost.add_watch_address(deal.maker_sost_addr)
            self._deal_sost_map[deal.maker_sost_addr] = deal.deal_id

    def on_eth_event(self, event: EthEvent):
        deal_id = self._deal_eth_map.get(event.deposit_id)
        if not deal_id:
            log.info("Unmatched ETH deposit: id=%d tx=%s", event.deposit_id, event.tx_hash)
            self.audit.log_event("unknown", "unmatched_eth_deposit",
                                f"deposit_id={event.deposit_id} tx={event.tx_hash}")
            return

        deal = self.deals.get(deal_id)
        if not deal:
            return

        if deal.mark_eth_locked(event.tx_hash, event.deposit_id):
            self.audit.log_event(deal_id, "eth_locked",
                                f"tx={event.tx_hash} deposit_id={event.deposit_id}")
            log.info("Deal %s: ETH side locked", deal_id)
            self._check_both_locked(deal)

    def on_sost_event(self, event: SostEvent):
        deal_id = self._deal_sost_map.get(event.address)
        if not deal_id:
            return

        deal = self.deals.get(deal_id)
        if not deal:
            return

        if deal.mark_sost_locked(event.txid or f"balance@{event.block_height}"):
            self.audit.log_event(deal_id, "sost_locked",
                                f"addr={event.address} amount={event.amount}")
            log.info("Deal %s: SOST side locked", deal_id)
            self._check_both_locked(deal)

    def _check_both_locked(self, deal: Deal):
        if deal.state == DealState.BOTH_LOCKED:
            self.audit.log_event(deal.deal_id, "both_locked", "ready for settlement")
            log.info("Deal %s: BOTH SIDES LOCKED — ready to settle", deal.deal_id)

    def execute_settlement(self, deal_id: str) -> bool:
        deal = self.deals.get(deal_id)
        if not deal or deal.state != DealState.BOTH_LOCKED:
            return False

        self.audit.log_event(deal_id, "settlement_initiated", "")
        # In production: trigger contract release + SOST transfer
        # For alpha: mark as settled with operator confirmation
        settlement_ref = f"manual_settlement_{int(time.time())}"
        if deal.settle(settlement_ref):
            self.audit.log_event(deal_id, "settled", settlement_ref)
            log.info("Deal %s: SETTLED", deal_id)
            return True
        return False

    def tick(self):
        expired = self.deals.check_all_expiry()
        for deal_id in expired:
            deal = self.deals.get(deal_id)
            if deal:
                self.audit.log_event(deal_id, "expired", deal.state.value)
                if deal.eth_tx_hash or deal.sost_lock_txid:
                    self.refund.request_refund(deal)

        for deal in self.deals.active_deals():
            if deal.state == DealState.BOTH_LOCKED:
                log.debug("Deal %s awaiting operator settlement", deal.deal_id)

    def run(self):
        self.running = True
        self.eth.on_event = self.on_eth_event
        self.sost.on_event = self.on_sost_event

        eth_thread = threading.Thread(target=self.eth.run, daemon=True)
        sost_thread = threading.Thread(target=self.sost.run, daemon=True)
        eth_thread.start()
        sost_thread.start()

        log.info("Settlement daemon started")
        while self.running:
            try:
                self.tick()
            except Exception as e:
                log.error("Tick error: %s", e)
            time.sleep(TICK_INTERVAL)

    def stop(self):
        self.running = False
        self.eth.stop()
        self.sost.stop()

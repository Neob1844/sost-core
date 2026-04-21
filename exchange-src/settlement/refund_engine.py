"""
SOST Gold Exchange — Refund Engine

Handles refund logic when deals fail, expire, or are disputed.
Both ETH-side (SOSTEscrow withdraw) and SOST-side (unlock/return).
"""

import time
import logging
from typing import Optional

from src.settlement.deal_state_machine import Deal, DealState

log = logging.getLogger("refund")


class RefundAction:
    def __init__(self, deal_id: str, side: str, reason: str,
                 tx_ref: Optional[str] = None):
        self.deal_id = deal_id
        self.side = side  # "eth" or "sost" or "both"
        self.reason = reason
        self.tx_ref = tx_ref
        self.created_at = time.time()
        self.executed = False
        self.executed_at: Optional[float] = None
        self.result: Optional[str] = None


class RefundEngine:
    def __init__(self):
        self._pending: list[RefundAction] = []
        self._completed: list[RefundAction] = []

    def request_refund(self, deal: Deal) -> Optional[RefundAction]:
        if deal.is_terminal():
            log.warning("Cannot refund terminal deal %s", deal.deal_id)
            return None

        side = "both"
        if deal.eth_tx_hash and not deal.sost_lock_txid:
            side = "eth"
        elif deal.sost_lock_txid and not deal.eth_tx_hash:
            side = "sost"

        reason = deal.refund_reason or "deal failed"
        if not deal.request_refund(reason):
            log.error("State transition to REFUND_PENDING failed for %s", deal.deal_id)
            return None

        action = RefundAction(
            deal_id=deal.deal_id,
            side=side,
            reason=reason,
        )
        self._pending.append(action)
        log.info("Refund requested: deal=%s side=%s reason=%s", deal.deal_id, side, reason)
        return action

    def execute_eth_refund(self, action: RefundAction) -> bool:
        # In production: call SOSTEscrow.withdraw() or wait for timelock expiry
        # For alpha: operator-triggered
        log.info("ETH refund for deal %s — operator must call withdraw()", action.deal_id)
        action.result = "eth_refund_pending_operator"
        return True

    def execute_sost_refund(self, action: RefundAction) -> bool:
        # In production: unlock SOST outputs
        # For alpha: operator-triggered
        log.info("SOST refund for deal %s — operator must release lock", action.deal_id)
        action.result = "sost_refund_pending_operator"
        return True

    def execute(self, action: RefundAction, deal: Deal) -> bool:
        success = True
        if action.side in ("eth", "both"):
            success = self.execute_eth_refund(action) and success
        if action.side in ("sost", "both"):
            success = self.execute_sost_refund(action) and success

        if success:
            action.executed = True
            action.executed_at = time.time()
            deal.confirm_refund()
            self._pending.remove(action)
            self._completed.append(action)
            log.info("Refund executed: deal=%s", action.deal_id)
        return success

    def pending(self) -> list[RefundAction]:
        return list(self._pending)

    def completed(self) -> list[RefundAction]:
        return list(self._completed)

"""
SOST Gold Exchange — Ethereum Watcher

Watches SOSTEscrow contract on Ethereum (or Sepolia) for deposit/withdraw events.
Correlates events with deal_ids and notifies the settlement daemon.
"""

import time
import json
import logging
from dataclasses import dataclass
from typing import Optional, Callable

log = logging.getLogger("eth-watcher")

ESCROW_ABI_EVENTS = {
    "GoldDeposited": "0x" + "a1b2c3d4",  # placeholder — replace with real selector
    "GoldWithdrawn": "0x" + "e5f6a7b8",
}

POLL_INTERVAL = 15  # seconds
CONFIRMATIONS_REQUIRED = 6


@dataclass
class EthEvent:
    event_type: str  # "deposit" or "withdraw"
    tx_hash: str
    block_number: int
    deposit_id: int
    depositor: str
    token: str  # XAUT or PAXG contract address
    amount: int  # wei
    unlock_time: int
    timestamp: float


class EthereumWatcher:
    def __init__(self, rpc_url: str, escrow_address: str, on_event: Optional[Callable] = None):
        self.rpc_url = rpc_url
        self.escrow_address = escrow_address
        self.on_event = on_event
        self.last_block = 0
        self.running = False
        self._events: list[EthEvent] = []

    def _rpc_call(self, method: str, params: list) -> dict:
        import urllib.request
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }).encode()
        req = urllib.request.Request(
            self.rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    def get_block_number(self) -> int:
        result = self._rpc_call("eth_blockNumber", [])
        return int(result["result"], 16)

    def get_logs(self, from_block: int, to_block: int) -> list[dict]:
        result = self._rpc_call("eth_getLogs", [{
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": self.escrow_address,
        }])
        return result.get("result", [])

    def parse_deposit_event(self, raw_log: dict) -> Optional[EthEvent]:
        try:
            topics = raw_log.get("topics", [])
            if len(topics) < 3:
                return None
            deposit_id = int(topics[1], 16)
            depositor = "0x" + topics[2][-40:]
            data = raw_log.get("data", "0x")
            return EthEvent(
                event_type="deposit",
                tx_hash=raw_log["transactionHash"],
                block_number=int(raw_log["blockNumber"], 16),
                deposit_id=deposit_id,
                depositor=depositor,
                token="",  # decoded from data
                amount=int(data[2:66], 16) if len(data) >= 66 else 0,
                unlock_time=0,
                timestamp=time.time(),
            )
        except (KeyError, ValueError, IndexError) as e:
            log.warning("Failed to parse deposit event: %s", e)
            return None

    def poll_once(self) -> list[EthEvent]:
        current = self.get_block_number()
        safe_block = current - CONFIRMATIONS_REQUIRED
        if safe_block <= self.last_block:
            return []

        from_block = self.last_block + 1
        to_block = min(safe_block, from_block + 1000)  # max 1000 blocks per query

        logs = self.get_logs(from_block, to_block)
        events = []
        for raw in logs:
            ev = self.parse_deposit_event(raw)
            if ev:
                events.append(ev)
                self._events.append(ev)
                log.info("Deposit detected: id=%d amount=%d tx=%s", ev.deposit_id, ev.amount, ev.tx_hash)
                if self.on_event:
                    self.on_event(ev)

        self.last_block = to_block
        return events

    def run(self):
        self.running = True
        log.info("Ethereum watcher started — escrow=%s rpc=%s", self.escrow_address, self.rpc_url)
        while self.running:
            try:
                self.poll_once()
            except Exception as e:
                log.error("Poll error: %s", e)
            time.sleep(POLL_INTERVAL)

    def stop(self):
        self.running = False

    def get_events(self) -> list[EthEvent]:
        return list(self._events)

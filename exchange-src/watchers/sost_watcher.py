"""
SOST Gold Exchange — SOST Chain Watcher

Watches SOST chain via RPC for lock outputs / balance commitments
related to active deals. Correlates with deal_ids.
"""

import time
import json
import logging
from dataclasses import dataclass
from typing import Optional, Callable

log = logging.getLogger("sost-watcher")

POLL_INTERVAL = 10  # seconds — SOST blocks ~600s but we check frequently


@dataclass
class SostEvent:
    event_type: str  # "lock_detected", "balance_confirmed", "block_new"
    txid: str
    block_height: int
    address: str
    amount: int  # satoshis
    deal_ref: str  # extracted from tx metadata if present
    timestamp: float


class SostWatcher:
    def __init__(self, rpc_url: str, rpc_user: str, rpc_pass: str,
                 watch_addresses: Optional[list[str]] = None,
                 on_event: Optional[Callable] = None):
        self.rpc_url = rpc_url
        self.rpc_user = rpc_user
        self.rpc_pass = rpc_pass
        self.watch_addresses = watch_addresses or []
        self.on_event = on_event
        self.last_height = 0
        self.running = False
        self._events: list[SostEvent] = []

    def _rpc(self, method: str, params: Optional[list] = None) -> dict:
        import urllib.request
        import base64
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or [],
        }).encode()
        auth = base64.b64encode(f"{self.rpc_user}:{self.rpc_pass}".encode()).decode()
        req = urllib.request.Request(
            self.rpc_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth}",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    def get_info(self) -> dict:
        result = self._rpc("getinfo")
        return result.get("result", {})

    def get_block_height(self) -> int:
        info = self.get_info()
        return info.get("blocks", 0)

    def get_address_utxos(self, address: str) -> list[dict]:
        result = self._rpc("getaddressutxos", [address])
        return result.get("result", [])

    def check_address_balance(self, address: str) -> int:
        utxos = self.get_address_utxos(address)
        return sum(u.get("amount", 0) for u in utxos)

    def poll_once(self) -> list[SostEvent]:
        current = self.get_block_height()
        if current <= self.last_height:
            return []

        events = []
        for addr in self.watch_addresses:
            try:
                balance = self.check_address_balance(addr)
                if balance > 0:
                    ev = SostEvent(
                        event_type="balance_confirmed",
                        txid="",
                        block_height=current,
                        address=addr,
                        amount=balance,
                        deal_ref="",
                        timestamp=time.time(),
                    )
                    events.append(ev)
                    self._events.append(ev)
                    log.info("SOST balance detected: addr=%s amount=%d height=%d", addr, balance, current)
                    if self.on_event:
                        self.on_event(ev)
            except Exception as e:
                log.warning("Failed to check address %s: %s", addr, e)

        self.last_height = current
        return events

    def add_watch_address(self, address: str):
        if address not in self.watch_addresses:
            self.watch_addresses.append(address)

    def remove_watch_address(self, address: str):
        if address in self.watch_addresses:
            self.watch_addresses.remove(address)

    def run(self):
        self.running = True
        log.info("SOST watcher started — rpc=%s watching=%d addresses", self.rpc_url, len(self.watch_addresses))
        while self.running:
            try:
                self.poll_once()
            except Exception as e:
                log.error("Poll error: %s", e)
            time.sleep(POLL_INTERVAL)

    def stop(self):
        self.running = False

    def get_events(self) -> list[SostEvent]:
        return list(self._events)

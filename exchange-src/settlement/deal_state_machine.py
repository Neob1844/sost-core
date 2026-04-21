"""
SOST Gold Exchange — Deal State Machine

States:
  CREATED → NEGOTIATED → AWAITING_ETH_LOCK → AWAITING_SOST_LOCK →
  BOTH_LOCKED → SETTLING → SETTLED
  Any state → REFUND_PENDING → REFUNDED
  Any state → EXPIRED
  Any state → DISPUTED
"""

import time
import hashlib
import json
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional


class DealState(Enum):
    CREATED = "CREATED"
    NEGOTIATED = "NEGOTIATED"
    AWAITING_ETH_LOCK = "AWAITING_ETH_LOCK"
    AWAITING_SOST_LOCK = "AWAITING_SOST_LOCK"
    BOTH_LOCKED = "BOTH_LOCKED"
    SETTLING = "SETTLING"
    SETTLED = "SETTLED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"
    EXPIRED = "EXPIRED"
    DISPUTED = "DISPUTED"


VALID_TRANSITIONS = {
    DealState.CREATED: {DealState.NEGOTIATED, DealState.EXPIRED},
    DealState.NEGOTIATED: {DealState.AWAITING_ETH_LOCK, DealState.EXPIRED},
    DealState.AWAITING_ETH_LOCK: {DealState.AWAITING_SOST_LOCK, DealState.BOTH_LOCKED, DealState.REFUND_PENDING, DealState.EXPIRED},
    DealState.AWAITING_SOST_LOCK: {DealState.BOTH_LOCKED, DealState.REFUND_PENDING, DealState.EXPIRED},
    DealState.BOTH_LOCKED: {DealState.SETTLING, DealState.REFUND_PENDING, DealState.DISPUTED},
    DealState.SETTLING: {DealState.SETTLED, DealState.REFUND_PENDING, DealState.DISPUTED},
    DealState.SETTLED: set(),
    DealState.REFUND_PENDING: {DealState.REFUNDED},
    DealState.REFUNDED: set(),
    DealState.EXPIRED: set(),
    DealState.DISPUTED: {DealState.SETTLED, DealState.REFUND_PENDING},
}


@dataclass
class Deal:
    deal_id: str
    pair: str  # "SOST/XAUT" or "SOST/PAXG"
    side: str  # "buy" or "sell" (from maker perspective)
    amount_sost: int  # in satoshis (1e8)
    amount_gold: int  # in wei (1e18)
    maker_sost_addr: str
    taker_sost_addr: str
    maker_eth_addr: str
    taker_eth_addr: str
    state: DealState = DealState.CREATED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    eth_tx_hash: Optional[str] = None
    eth_deposit_id: Optional[int] = None
    sost_lock_txid: Optional[str] = None
    settlement_tx_hash: Optional[str] = None
    refund_reason: Optional[str] = None
    history: list = field(default_factory=list)

    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + 3600  # 1 hour default

    @staticmethod
    def generate_id(maker_addr: str, taker_addr: str, timestamp: float) -> str:
        raw = f"{maker_addr}:{taker_addr}:{timestamp}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def transition(self, new_state: DealState, reason: str = "") -> bool:
        if new_state not in VALID_TRANSITIONS.get(self.state, set()):
            return False
        old = self.state
        self.state = new_state
        self.updated_at = time.time()
        self.history.append({
            "from": old.value,
            "to": new_state.value,
            "reason": reason,
            "timestamp": self.updated_at,
        })
        return True

    def is_terminal(self) -> bool:
        return self.state in {DealState.SETTLED, DealState.REFUNDED, DealState.EXPIRED}

    def is_expired(self) -> bool:
        return time.time() > self.expires_at and not self.is_terminal()

    def check_expiry(self) -> bool:
        if self.is_expired() and self.state not in {DealState.BOTH_LOCKED, DealState.SETTLING}:
            return self.transition(DealState.EXPIRED, "timeout")
        return False

    def mark_eth_locked(self, tx_hash: str, deposit_id: int) -> bool:
        self.eth_tx_hash = tx_hash
        self.eth_deposit_id = deposit_id
        if self.sost_lock_txid:
            return self.transition(DealState.BOTH_LOCKED, "both sides locked")
        if self.state == DealState.NEGOTIATED:
            return self.transition(DealState.AWAITING_ETH_LOCK, "eth lock detected")
        if self.state == DealState.AWAITING_ETH_LOCK:
            return self.transition(DealState.AWAITING_SOST_LOCK, "eth lock confirmed")
        return False

    def mark_sost_locked(self, txid: str) -> bool:
        self.sost_lock_txid = txid
        if self.eth_tx_hash:
            return self.transition(DealState.BOTH_LOCKED, "both sides locked")
        if self.state in {DealState.AWAITING_ETH_LOCK, DealState.AWAITING_SOST_LOCK}:
            return self.transition(DealState.AWAITING_SOST_LOCK, "sost lock detected")
        return False

    def settle(self, settlement_tx: str) -> bool:
        self.settlement_tx_hash = settlement_tx
        if self.state == DealState.BOTH_LOCKED:
            self.transition(DealState.SETTLING, "settlement initiated")
        return self.transition(DealState.SETTLED, "settlement complete")

    def request_refund(self, reason: str) -> bool:
        self.refund_reason = reason
        return self.transition(DealState.REFUND_PENDING, reason)

    def confirm_refund(self) -> bool:
        return self.transition(DealState.REFUNDED, "refund confirmed")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class DealStore:
    def __init__(self):
        self._deals: dict[str, Deal] = {}

    def create(self, **kwargs) -> Deal:
        ts = time.time()
        deal_id = Deal.generate_id(
            kwargs.get("maker_sost_addr", ""),
            kwargs.get("taker_sost_addr", ""),
            ts,
        )
        deal = Deal(deal_id=deal_id, created_at=ts, **kwargs)
        self._deals[deal_id] = deal
        return deal

    def get(self, deal_id: str) -> Optional[Deal]:
        return self._deals.get(deal_id)

    def active_deals(self) -> list[Deal]:
        return [d for d in self._deals.values() if not d.is_terminal()]

    def check_all_expiry(self) -> list[str]:
        expired = []
        for d in self.active_deals():
            if d.check_expiry():
                expired.append(d.deal_id)
        return expired

    def save(self, path: str):
        data = {did: d.to_dict() for did, d in self._deals.items()}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        with open(path, "r") as f:
            data = json.load(f)
        for did, d in data.items():
            d["state"] = DealState(d["state"])
            self._deals[did] = Deal(**d)

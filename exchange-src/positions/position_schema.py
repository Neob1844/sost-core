"""
SOST Gold Exchange — Position Schema

A position is a SOST-native representation of a gold-backed contract.
ETH is only the onboarding/exit rail — positions live and trade inside SOST.

Types:
  MODEL_B_ESCROW:  gold locked in SOSTEscrow on Ethereum
  MODEL_A_CUSTODY: gold held by user, proven via PoPC
  REWARD_RIGHT:    separated right to future SOST rewards only
  PRINCIPAL_CLAIM: separated right to principal at maturity
"""

import time
import hashlib
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional


class ContractType(Enum):
    MODEL_B_ESCROW = "MODEL_B_ESCROW"
    MODEL_A_CUSTODY = "MODEL_A_CUSTODY"


class BackingType(Enum):
    ETH_TOKENIZED_GOLD = "ETH_TOKENIZED_GOLD"
    AUTOCUSTODY_GOLD = "AUTOCUSTODY_GOLD"
    PHYSICAL_CUSTODY_CERT = "PHYSICAL_CUSTODY_CERT"


class PositionStatus(Enum):
    ACTIVE = "ACTIVE"
    MATURED = "MATURED"
    REDEEMED = "REDEEMED"
    SLASHED = "SLASHED"
    TRANSFERRED = "TRANSFERRED"
    EXPIRED = "EXPIRED"


class RightType(Enum):
    FULL_POSITION = "FULL_POSITION"
    REWARD_RIGHT = "REWARD_RIGHT"
    PRINCIPAL_CLAIM = "PRINCIPAL_CLAIM"


@dataclass
class Position:
    position_id: str
    owner: str                       # current SOST address
    contract_type: ContractType
    backing_type: BackingType
    token_symbol: str                # "XAUT" or "PAXG" or "PHYSICAL"
    reference_amount: int            # underlying gold amount (wei for tokenized, mg for physical)
    bond_amount_sost: int            # SOST bond in satoshis
    start_time: float
    expiry_time: float
    reward_schedule: str             # e.g. "linear_12m" or "epoch_quarterly"
    reward_total_sost: int           # total SOST rewards over lifetime
    reward_claimed_sost: int = 0
    status: PositionStatus = PositionStatus.ACTIVE
    transferable: bool = True
    right_type: RightType = RightType.FULL_POSITION
    parent_position_id: Optional[str] = None  # if split from another position
    eth_escrow_deposit_id: Optional[int] = None
    eth_escrow_tx: Optional[str] = None
    backing_proof_hash: Optional[str] = None  # hash of latest PoPC proof
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    history: list = field(default_factory=list)

    @staticmethod
    def generate_id(owner: str, timestamp: float) -> str:
        raw = f"pos:{owner}:{timestamp}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def is_active(self) -> bool:
        return self.status == PositionStatus.ACTIVE

    def is_matured(self) -> bool:
        return time.time() >= self.expiry_time and self.status == PositionStatus.ACTIVE

    def reward_remaining(self) -> int:
        return max(0, self.reward_total_sost - self.reward_claimed_sost)

    def time_remaining(self) -> float:
        return max(0.0, self.expiry_time - time.time())

    def pct_complete(self) -> float:
        total = self.expiry_time - self.start_time
        if total <= 0:
            return 100.0
        elapsed = time.time() - self.start_time
        return min(100.0, max(0.0, elapsed / total * 100.0))

    def record_event(self, event: str, detail: str = ""):
        self.history.append({
            "event": event,
            "detail": detail,
            "timestamp": time.time(),
        })
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["contract_type"] = self.contract_type.value
        d["backing_type"] = self.backing_type.value
        d["status"] = self.status.value
        d["right_type"] = self.right_type.value
        return d

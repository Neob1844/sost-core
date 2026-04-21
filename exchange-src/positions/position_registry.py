"""
SOST Gold Exchange — Position Registry

Creates, stores, updates and queries SOST-native gold positions.
This is the central authority for position lifecycle within SOST.
"""

import json
import time
import logging
from typing import Optional

from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, RightType,
)

log = logging.getLogger("position-registry")


class PositionRegistry:
    def __init__(self):
        self._positions: dict[str, Position] = {}

    def create_model_b(self, owner: str, token: str, amount: int,
                       bond_sost: int, duration_seconds: int,
                       reward_total: int, eth_deposit_id: int,
                       eth_tx: str) -> Position:
        now = time.time()
        pos = Position(
            position_id=Position.generate_id(owner, now),
            owner=owner,
            contract_type=ContractType.MODEL_B_ESCROW,
            backing_type=BackingType.ETH_TOKENIZED_GOLD,
            token_symbol=token,
            reference_amount=amount,
            bond_amount_sost=bond_sost,
            start_time=now,
            expiry_time=now + duration_seconds,
            reward_schedule=f"linear_{duration_seconds // 86400}d",
            reward_total_sost=reward_total,
            eth_escrow_deposit_id=eth_deposit_id,
            eth_escrow_tx=eth_tx,
            transferable=True,
        )
        pos.record_event("created", f"model_b token={token} amount={amount}")
        self._positions[pos.position_id] = pos
        log.info("Position created: %s owner=%s type=MODEL_B", pos.position_id, owner)
        return pos

    def create_model_a(self, owner: str, token: str, amount: int,
                       bond_sost: int, duration_seconds: int,
                       reward_total: int, proof_hash: str) -> Position:
        now = time.time()
        pos = Position(
            position_id=Position.generate_id(owner, now),
            owner=owner,
            contract_type=ContractType.MODEL_A_CUSTODY,
            backing_type=BackingType.AUTOCUSTODY_GOLD,
            token_symbol=token,
            reference_amount=amount,
            bond_amount_sost=bond_sost,
            start_time=now,
            expiry_time=now + duration_seconds,
            reward_schedule=f"linear_{duration_seconds // 86400}d",
            reward_total_sost=reward_total,
            backing_proof_hash=proof_hash,
            transferable=False,  # Model A: only reward rights are transferable
        )
        pos.record_event("created", f"model_a proof={proof_hash[:16]}...")
        self._positions[pos.position_id] = pos
        log.info("Position created: %s owner=%s type=MODEL_A", pos.position_id, owner)
        return pos

    def get(self, position_id: str) -> Optional[Position]:
        return self._positions.get(position_id)

    def by_owner(self, owner: str) -> list[Position]:
        return [p for p in self._positions.values() if p.owner == owner]

    def active(self) -> list[Position]:
        return [p for p in self._positions.values() if p.is_active()]

    def matured(self) -> list[Position]:
        return [p for p in self._positions.values() if p.is_matured()]

    def check_maturities(self) -> list[str]:
        matured_ids = []
        for p in self.active():
            if p.is_matured():
                p.status = PositionStatus.MATURED
                p.record_event("matured", "")
                matured_ids.append(p.position_id)
                log.info("Position matured: %s", p.position_id)
        return matured_ids

    def claim_reward(self, position_id: str, amount: int) -> bool:
        pos = self.get(position_id)
        if not pos or not pos.is_active():
            return False
        if amount > pos.reward_remaining():
            return False
        pos.reward_claimed_sost += amount
        pos.record_event("reward_claimed", f"amount={amount}")
        return True

    def slash(self, position_id: str, reason: str) -> bool:
        pos = self.get(position_id)
        if not pos or not pos.is_active():
            return False
        pos.status = PositionStatus.SLASHED
        pos.record_event("slashed", reason)
        log.warning("Position slashed: %s reason=%s", position_id, reason)
        return True

    def redeem(self, position_id: str) -> bool:
        pos = self.get(position_id)
        if not pos or pos.status not in {PositionStatus.MATURED, PositionStatus.ACTIVE}:
            return False
        pos.status = PositionStatus.REDEEMED
        pos.record_event("redeemed", "")
        log.info("Position redeemed: %s", position_id)
        return True

    def save(self, path: str):
        data = {pid: p.to_dict() for pid, p in self._positions.items()}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        with open(path, "r") as f:
            data = json.load(f)
        for pid, d in data.items():
            d["contract_type"] = ContractType(d["contract_type"])
            d["backing_type"] = BackingType(d["backing_type"])
            d["status"] = PositionStatus(d["status"])
            d["right_type"] = RightType(d["right_type"])
            self._positions[pid] = Position(**d)

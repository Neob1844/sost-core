"""
SOST Gold Exchange — Position Transfer

Handles ownership transfer of positions within SOST.
Model B: full position transferable.
Model A: only reward rights transferable, not the custody position itself.
"""

import time
import logging
from typing import Optional

from src.positions.position_schema import (
    Position, ContractType, PositionStatus, RightType,
)
from src.positions.position_registry import PositionRegistry

log = logging.getLogger("position-transfer")


class TransferResult:
    def __init__(self, success: bool, position_id: str, message: str):
        self.success = success
        self.position_id = position_id
        self.message = message


class PositionTransferEngine:
    def __init__(self, registry: PositionRegistry):
        self.registry = registry

    def can_transfer(self, position: Position, new_owner: str) -> tuple[bool, str]:
        if not position.is_active():
            return False, "position not active"
        if position.owner == new_owner:
            return False, "same owner"
        if not position.transferable:
            if position.contract_type == ContractType.MODEL_A_CUSTODY:
                return False, "model_a full position not transferable — use split_reward_right()"
            return False, "position not transferable"
        return True, "ok"

    def transfer(self, position_id: str, new_owner: str,
                 deal_id: Optional[str] = None) -> TransferResult:
        pos = self.registry.get(position_id)
        if not pos:
            return TransferResult(False, position_id, "position not found")

        ok, reason = self.can_transfer(pos, new_owner)
        if not ok:
            return TransferResult(False, position_id, reason)

        old_owner = pos.owner
        pos.owner = new_owner
        pos.updated_at = time.time()
        pos.record_event("transferred", f"from={old_owner} to={new_owner} deal={deal_id or 'direct'}")
        log.info("Position %s transferred: %s → %s", position_id, old_owner, new_owner)
        return TransferResult(True, position_id, "transferred")

    def split_reward_right(self, position_id: str, buyer: str,
                           deal_id: Optional[str] = None) -> TransferResult:
        """Split reward rights from a position into a new REWARD_RIGHT position."""
        parent = self.registry.get(position_id)
        if not parent:
            return TransferResult(False, position_id, "position not found")
        if not parent.is_active():
            return TransferResult(False, position_id, "not active")
        if parent.reward_remaining() <= 0:
            return TransferResult(False, position_id, "no rewards remaining")

        now = time.time()
        child = Position(
            position_id=Position.generate_id(buyer, now),
            owner=buyer,
            contract_type=parent.contract_type,
            backing_type=parent.backing_type,
            token_symbol=parent.token_symbol,
            reference_amount=0,  # no principal in reward-only right
            bond_amount_sost=0,
            start_time=now,
            expiry_time=parent.expiry_time,
            reward_schedule=parent.reward_schedule,
            reward_total_sost=parent.reward_remaining(),
            transferable=True,
            right_type=RightType.REWARD_RIGHT,
            parent_position_id=position_id,
        )
        child.record_event("created_from_split", f"parent={position_id} deal={deal_id or 'direct'}")

        # Zero out parent rewards (transferred to child)
        parent.reward_total_sost = parent.reward_claimed_sost
        parent.record_event("reward_right_split", f"child={child.position_id} buyer={buyer}")

        self.registry._positions[child.position_id] = child
        log.info("Reward right split: parent=%s child=%s buyer=%s", position_id, child.position_id, buyer)
        return TransferResult(True, child.position_id, "reward_right_created")

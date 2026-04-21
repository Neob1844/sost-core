"""
SOST Gold Exchange — Position Settlement

Settles trades of positions within SOST.
When a position changes hands via the DEX, this module:
  1. Validates the trade
  2. Updates ownership in the registry
  3. Records the settlement
  4. Handles bond reassignment if needed
"""

import time
import logging
from typing import Optional

from src.positions.position_schema import Position, PositionStatus, RightType
from src.positions.position_registry import PositionRegistry
from src.positions.position_transfer import PositionTransferEngine, TransferResult
from src.settlement.deal_state_machine import Deal, DealState
from src.operator.audit_log import AuditLog

log = logging.getLogger("position-settlement")


class PositionSettlement:
    def __init__(self, registry: PositionRegistry,
                 transfer: PositionTransferEngine,
                 audit: AuditLog):
        self.registry = registry
        self.transfer = transfer
        self.audit = audit

    def settle_position_trade(self, deal: Deal, position_id: str) -> bool:
        """
        Settle a DEX trade where SOST is exchanged for a position.
        The deal must be in BOTH_LOCKED state (SOST payment confirmed).
        """
        if deal.state != DealState.BOTH_LOCKED:
            log.error("Cannot settle: deal %s not in BOTH_LOCKED state", deal.deal_id)
            return False

        pos = self.registry.get(position_id)
        if not pos:
            log.error("Position %s not found", position_id)
            return False

        buyer = deal.taker_sost_addr

        # Determine transfer type
        if pos.right_type == RightType.FULL_POSITION:
            result = self.transfer.transfer(position_id, buyer, deal.deal_id)
        elif pos.right_type == RightType.REWARD_RIGHT:
            result = self.transfer.transfer(position_id, buyer, deal.deal_id)
        else:
            result = TransferResult(False, position_id, "unsupported right type")

        if not result.success:
            log.error("Transfer failed: %s — %s", position_id, result.message)
            self.audit.log_event(deal.deal_id, "position_transfer_failed",
                                f"pos={position_id} reason={result.message}")
            return False

        # Mark deal as settled
        deal.settle(f"position_transfer:{position_id}")
        self.audit.log_event(deal.deal_id, "position_settled",
                            f"pos={position_id} buyer={buyer}")
        log.info("Position trade settled: deal=%s pos=%s buyer=%s",
                 deal.deal_id, position_id, buyer)
        return True

    def settle_reward_split(self, deal: Deal, parent_position_id: str) -> bool:
        """
        Settle a trade where buyer purchases reward rights from a Model A position.
        """
        if deal.state != DealState.BOTH_LOCKED:
            return False

        buyer = deal.taker_sost_addr
        result = self.transfer.split_reward_right(parent_position_id, buyer, deal.deal_id)

        if not result.success:
            self.audit.log_event(deal.deal_id, "reward_split_failed",
                                f"parent={parent_position_id} reason={result.message}")
            return False

        deal.settle(f"reward_split:{result.position_id}")
        self.audit.log_event(deal.deal_id, "reward_split_settled",
                            f"parent={parent_position_id} child={result.position_id} buyer={buyer}")
        log.info("Reward split settled: deal=%s child=%s", deal.deal_id, result.position_id)
        return True

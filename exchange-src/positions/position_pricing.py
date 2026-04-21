"""
SOST Gold Exchange — Position Pricing

Values a position based on:
  - underlying gold value
  - time remaining to maturity
  - reward remaining (discounted)
  - risk (slashing probability, backing type)
  - illiquidity discount
"""

import time
import logging
from typing import Optional

from src.positions.position_schema import (
    Position, ContractType, BackingType, RightType,
)

log = logging.getLogger("position-pricing")

# Discount rates (annual, simple)
DISCOUNT_RATE_MODEL_B = 0.05   # 5% — lower risk (escrow)
DISCOUNT_RATE_MODEL_A = 0.12   # 12% — higher risk (autocustody)
ILLIQUIDITY_DISCOUNT = 0.03    # 3% flat


class PositionValuation:
    def __init__(self, position_id: str, gold_value_sost: int,
                 reward_value_sost: int, discount_sost: int,
                 net_value_sost: int, detail: str):
        self.position_id = position_id
        self.gold_value_sost = gold_value_sost
        self.reward_value_sost = reward_value_sost
        self.discount_sost = discount_sost
        self.net_value_sost = net_value_sost
        self.detail = detail


def value_position(position: Position,
                   gold_price_sost_per_unit: float) -> PositionValuation:
    """
    Value a position in SOST terms.
    gold_price_sost_per_unit: how many SOST satoshis per 1 unit of gold reference.
    """
    # Principal value
    if position.right_type == RightType.REWARD_RIGHT:
        gold_value = 0
    else:
        gold_value = int(position.reference_amount * gold_price_sost_per_unit)

    # Reward value (time-discounted)
    remaining_reward = position.reward_remaining()
    years_left = position.time_remaining() / (365.25 * 86400)

    if position.contract_type == ContractType.MODEL_B_ESCROW:
        rate = DISCOUNT_RATE_MODEL_B
    else:
        rate = DISCOUNT_RATE_MODEL_A

    discount_factor = 1.0 / (1.0 + rate * max(years_left, 0))
    reward_value = int(remaining_reward * discount_factor)

    # Illiquidity
    gross = gold_value + reward_value
    illiquidity = int(gross * ILLIQUIDITY_DISCOUNT)

    net = max(0, gross - illiquidity)

    detail = (f"gold={gold_value} reward={reward_value}(disc={1-discount_factor:.2%}) "
              f"illiq=-{illiquidity} net={net}")

    return PositionValuation(
        position_id=position.position_id,
        gold_value_sost=gold_value,
        reward_value_sost=reward_value,
        discount_sost=illiquidity,
        net_value_sost=net,
        detail=detail,
    )

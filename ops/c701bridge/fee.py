"""Gold Access Key — byte-for-byte the same integer math as contracts/bridge/src/GoldAccessKey.sol.

feeEUR  = min(50, max(0.50, bridgeValueEUR * 0.001))
feeXAUT = ceil(feeEUR / XAUT_EUR, 6 decimals)
Operations below 100 EUR are rejected. EUR amounts are integers scaled 1e8 (EUR8).
"""
from __future__ import annotations

from decimal import Decimal

EUR8 = 10**8
STOCKS_PER_SOST = 10**8
XAUT_UNIT = 10**6
FEE_MIN_EUR8 = 50_000_000
FEE_MAX_EUR8 = 5_000_000_000
MIN_OPERATION_EUR8 = 10_000_000_000
RATE_DEN = 1000


class BelowMinimumOperation(ValueError):
    pass


def meets_minimum(v_num: int, v_den: int) -> bool:
    if v_den <= 0:
        raise ValueError("bad denominator")
    return v_num >= MIN_OPERATION_EUR8 * v_den


def fee_xaut(v_num: int, v_den: int, xaut_eur8: int) -> int:
    for v in (v_num, v_den, xaut_eur8):
        if not isinstance(v, int) or isinstance(v, bool):
            raise TypeError("integers only (no floats in money math)")
    if xaut_eur8 <= 0:
        raise ValueError("zero XAUT price")
    if not meets_minimum(v_num, v_den):
        raise BelowMinimumOperation("bridge value below 100 EUR")
    if v_num < FEE_MIN_EUR8 * RATE_DEN * v_den:
        num, den = FEE_MIN_EUR8, 1
    elif v_num > FEE_MAX_EUR8 * RATE_DEN * v_den:
        num, den = FEE_MAX_EUR8, 1
    else:
        num, den = v_num, v_den * RATE_DEN
    n = num * XAUT_UNIT
    d = den * xaut_eur8
    return (n + d - 1) // d


def fee_xaut_for_amount(amount_stocks: int, sost_eur8: int, xaut_eur8: int) -> int:
    return fee_xaut(amount_stocks * sost_eur8, STOCKS_PER_SOST, xaut_eur8)


def eur8(value: str) -> int:
    """'3713.13' -> 371313000000. Strings only; floats refused."""
    if not isinstance(value, str):
        raise TypeError("pass prices as decimal strings")
    q = Decimal(value) * EUR8
    if q != q.to_integral_value():
        raise ValueError("more than 8 decimals")
    return int(q)


def fmt_xaut(units: int) -> str:
    return f"{units // XAUT_UNIT}.{units % XAUT_UNIT:06d}"


EXAMPLE_VALUES_EUR = [0, 10, 50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000, 7500, 10000,
                      15000, 25000, 50000, 100000, 500000, 1000000]


def example_table(xaut_eur8: int = 371_313_000_000):
    rows = []
    for v in EXAMPLE_VALUES_EUR:
        v8 = v * EUR8
        if not meets_minimum(v8, 1):
            rows.append({"value_eur": v, "fee_eur": None, "fee_xaut_units": None, "status": "REJECTED_BELOW_MINIMUM"})
            continue
        fe = FEE_MIN_EUR8 if v8 < FEE_MIN_EUR8 * RATE_DEN else FEE_MAX_EUR8 if v8 > FEE_MAX_EUR8 * RATE_DEN else v8 // RATE_DEN
        rows.append({"value_eur": v, "fee_eur8": fe, "fee_xaut_units": fee_xaut(v8, 1, xaut_eur8), "status": "OK"})
    return rows

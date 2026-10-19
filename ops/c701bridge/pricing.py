"""Price inputs for the Gold Access Key.

XAUT/EUR: aggregated from >= `min_sources` independent observations; each must be fresh; the
          spread between them is bounded; the median is used; then signed by the PRICE SIGNER key
          (a role separate from the mint authorizer).
SOST/EUR: there is NO approved valuation methodology today. `SostValuation(methodology=None)` raises
          ValuationNotApproved for every request, which blocks every real operation (the on-chain
          contract enforces the same gate with params.approvedMethodology == 0). The informational
          SOST reference weight (mg of gold per SOST) is NOT a price and is never used here.
"""
from __future__ import annotations

import os
import statistics
from dataclasses import dataclass
from typing import List, Optional

from .eip712 import price_struct_hash, sign_price


class PriceUnavailable(Exception):
    pass


class ValuationNotApproved(Exception):
    pass


@dataclass(frozen=True)
class Observation:
    source: str
    xaut_eur8: int
    observed_at: int


class XautEurOracle:
    def __init__(self, min_sources=2, max_age=600, max_spread_bps=100, floor_eur8=1_000 * 10**8, ceil_eur8=10_000 * 10**8):
        self.min_sources, self.max_age, self.max_spread_bps = min_sources, max_age, max_spread_bps
        self.floor, self.ceil = floor_eur8, ceil_eur8

    def aggregate(self, obs: List[Observation], now: int) -> Observation:
        fresh = [o for o in obs if 0 <= now - o.observed_at <= self.max_age]
        sources = {o.source for o in fresh}
        if len(sources) < self.min_sources:
            raise PriceUnavailable(f"need {self.min_sources} fresh independent sources, have {len(sources)}")
        vals = sorted(o.xaut_eur8 for o in fresh)
        lo, hi = vals[0], vals[-1]
        if (hi - lo) * 10_000 > lo * self.max_spread_bps:
            raise PriceUnavailable("sources disagree beyond the allowed spread")
        med = int(statistics.median_low(vals))
        if not (self.floor <= med <= self.ceil):
            raise PriceUnavailable("price outside sanity bounds")
        return Observation("median", med, min(o.observed_at for o in fresh))


class SostValuation:
    def __init__(self, methodology: Optional[bytes] = None, price_eur8: Optional[int] = None):
        self.methodology, self.price_eur8 = methodology, price_eur8

    def current(self):
        if self.methodology is None or self.price_eur8 is None:
            raise ValuationNotApproved("no approved SOST/EUR valuation methodology: real operations are blocked")
        return self.methodology, self.price_eur8


class PriceSigner:
    """Signs PriceQuote messages. In production this is a separate service and key; here a test key."""

    def __init__(self, key, chain_id: int, contract: str):
        self.key, self.chain_id, self.contract = key, chain_id, contract

    def quote(self, xaut: Observation, valuation: SostValuation):
        methodology, sost_eur8 = valuation.current()
        q = {"xautEur8": xaut.xaut_eur8, "sostEur8": sost_eur8, "methodology": methodology,
             "observedAt": xaut.observed_at, "quoteId": os.urandom(32)}
        return q, sign_price(q, self.chain_id, self.contract, self.key), price_struct_hash(q)

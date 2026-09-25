#!/usr/bin/env python3
"""Phase B — monetary/arithmetic invariants over the SOST emission schedule,
checked on the independent reference model (validated == C++ and == live chain)
AND cross-checked against the real C++ dumper output when provided.

Invariants (fail => non-zero exit):
  I1 subsidy(h) >= 0 for all h
  I2 subsidy non-increasing across epochs (monotone decay)
  I3 cumulative_emission monotone non-decreasing
  I4 cumulative_emission(h) <= SUPPLY_CAP  (no over-issuance)
  I5 identity: cumulative(h) - cumulative(h-1) == subsidy(h)  (the two funcs agree)
  I6 no int64 overflow (all values fit signed 64-bit and are >= 0)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "reference_model"))
import subsidy_model as M

I64_MAX = (1 << 63) - 1
fails = []
def check(cond, msg):
    if not cond: fails.append(msg)

# Range: dense live era + epoch boundaries + supply-cap approach
heights = list(range(0, 30001))
E = M.BLOCKS_PER_EPOCH
for k in range(0, 80):
    for d in (-1, 0, 1):
        h = k*E + d
        if h >= 0: heights.append(h)
heights += [10**6, 5*10**6, 7_900_000, 7_900_001, 10**7, 5*10**7, 10**8]
heights = sorted(set(heights))

prev_cum = 0
prev_epoch_sub = None
for h in heights:
    s = M.subsidy(h); c = M.cumulative_emission(h)
    check(s >= 0, f"I1 subsidy<0 at {h}")
    check(0 <= c <= I64_MAX, f"I6 cumulative out of int64 at {h}: {c}")
    check(0 <= s <= I64_MAX, f"I6 subsidy out of int64 at {h}: {s}")
    check(c <= M.SUPPLY_CAP, f"I4 cumulative>{M.SUPPLY_CAP} at {h}: {c}")
    # I5 identity (skip h where a jump in heights breaks adjacency)
    cm1 = M.cumulative_emission(h-1)
    check(c - cm1 == s, f"I5 cumulative-diff != subsidy at {h}: {c-cm1} vs {s}")
    # monotone decay per epoch boundary (compare first block of each epoch)
    if h % E == 0:
        if prev_epoch_sub is not None:
            check(s <= prev_epoch_sub, f"I2 subsidy increased at epoch start {h}")
        prev_epoch_sub = s

# I3 monotone non-decreasing cumulative over the dense range
for h in range(1, 30001):
    check(M.cumulative_emission(h) >= M.cumulative_emission(h-1), f"I3 cumulative decreased at {h}")

# Cross-check against real C++ dumper output if provided (h subsidy cumulative)
if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
    for line in open(sys.argv[1]):
        h, cs, cc = map(int, line.split())
        check(M.subsidy(h) == cs, f"XCHK subsidy mismatch vs C++ at {h}")
        check(M.cumulative_emission(h) == cc, f"XCHK cumulative mismatch vs C++ at {h}")

if fails:
    print(f"FAIL: {len(fails)} invariant violation(s)")
    for m in fails[:20]: print("  "+m)
    sys.exit(1)
print(f"PASS: monetary invariants I1-I6 hold over {len(heights)} heights (+ dense monotone 0..30000)")

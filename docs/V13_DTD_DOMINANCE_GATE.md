# V13 — DTD Anti-Dominance Eligibility Gate

**Activation height:** `DTD_DOMINANCE_GATE_HEIGHT = 12100`
**Window:** `DTD_DOMINANCE_WINDOW = 288` blocks (≈ 48 h at 10 min/block)
**Threshold:** `DTD_DOMINANCE_MAX_BPS = 500` (5.00 %)
**Status:** SHIPPED in this build. Activates automatically at the gate height.

This document describes the V13 anti-dominance filter that further
restricts DTD lottery eligibility starting at block 12,100. The
filter is independent from the existing recent-winner cooldown and
from the (preparatory) V14 PoPC gate — all three apply, and a pkh
excluded by any one is excluded from the eligibility set.

---

## 1. Rule (operational)

From height `h >= DTD_DOMINANCE_GATE_HEIGHT`:

> A miner_pkh is excluded from the DTD lottery eligibility set at
> height `h` iff the pkh's share of the previous
> `DTD_DOMINANCE_WINDOW` blocks is greater than or equal to 5 %.

The window is `[h - 288, h - 1]` inclusive on both ends. The current
block itself is NOT in the window. The threshold check is in
integer math at basis-point precision (no floats).

A dominant miner is NOT prevented from producing normal blocks. The
gate only removes them from the DTD lottery eligibility set. They
continue to receive the standard 50 % miner share on every block they
produce; they only miss the redistributed 25 % + 25 % protocol-side
share that the DTD lottery would otherwise pay them when triggered.

The exclusion is **dynamic**. As soon as the rolling 288-block window
no longer contains ≥ 5 % of that pkh's blocks, eligibility is
restored automatically. No operator action, no retroactive penalty,
no permanent ban.

> **Note on the 5 % calibration.** At 5 % the gate is deliberately
> aggressive — it favours small miners by excluding from the DTD
> lottery any pkh producing 15 or more of the last 288 blocks
> (15/288 = 5.21 %). On a chain with few active miners this can shrink
> the eligibility set substantially; if every recent producer is above
> 5 %, the set is empty and the DTD pool simply accumulates (UPDATE,
> not PAYOUT) until a sub-5 % producer appears. Block production and
> the 50 % miner share are never affected.

---

## 2. Threshold mathematics

Implemented in `include/sost/params.h::is_dtd_dominant`:

```c++
inline constexpr bool is_dtd_dominant(
    int32_t mined_count_in_window,
    int32_t observed_window_blocks,
    int64_t height)
{
    if (height < DTD_DOMINANCE_GATE_HEIGHT) return false;
    if (observed_window_blocks <= 0) return false;
    return (int64_t)mined_count_in_window * 10000 >=
           (int64_t)DTD_DOMINANCE_MAX_BPS * (int64_t)observed_window_blocks;
}
```

Equivalent to `mined / observed >= 5 %` evaluated at basis-point
precision. Examples for `observed_window_blocks = 288`:

| `mined` | ratio | excluded? |
|---|---|---|
| 14 | 4.86 % | NO (eligible) |
| 15 | 5.21 % | YES |
| 100 | 34.72 % | YES |

The `observed_window_blocks` argument is the count of blocks the
caller actually saw in the window — typically 288 in steady state,
but possibly less very near the gate activation height. The helper
uses `observed`, not the static constant, so the 5 % rule still
applies at partial windows.

---

## 3. Integration with existing filters

In `compute_lottery_eligibility_set` (`src/lottery.cpp`), three
filters are applied in this order for each pkh that ever mined a block:

1. **Recent-winner cooldown.** Excluded iff the pkh won a block in
   the last `lottery_exclusion_window_at(h)` heights (5 pre-V13,
   6 from V13_HEIGHT = 12000).
2. **V13 anti-dominance gate.** Excluded iff `is_dtd_dominant(...)`
   returns true (active from `DTD_DOMINANCE_GATE_HEIGHT = 12100`).
3. **V14 PoPC gate.** Wired but consensus-deferred. See
   `docs/V14_DTD_POPC_ELIGIBILITY.md`.

A pkh excluded by any filter is not in the eligibility set. There is
no "saving throw" or override: each filter applies independently.

Pre-V13.5 behaviour is preserved bit-for-bit. The dominance check
short-circuits to false for `height < DTD_DOMINANCE_GATE_HEIGHT`, so
any replay of historical blocks below 12100 produces identical
eligibility sets to the prior implementation.

---

## 4. Worked example — 2026-05-30 snapshot

Live mining distribution from the explorer at block ~10,940 (window
of the last 288 blocks):

| Wallet | Blocks | Share | Eligible under 5 % gate (block ≥ 12100) |
|---|---|---|---|
| `sost10fa49a0…c624a8` | 110 | 38.2 % | **NO** — ≥ 5 % |
| `sost1993a8eb…d13d8f` | 97 | 33.7 % | **NO** — ≥ 5 % |
| `sost1ad42b84…9bed53` | 31 | 10.8 % | **NO** — ≥ 5 % |
| `sost1146b626…525f99` | 24 | 8.3 % | **NO** — ≥ 5 % |
| `sost1269ecd7…407159` | 23 | 8.0 % | **NO** — ≥ 5 % |
| `sost1c1c6d7e…5d66da` | 3 | 1.0 % | YES |

Under the 5 % calibration, every wallet at or above 15/288 (5.21 %)
falls out of the DTD eligibility set until its rolling 288-block share
drops below 5 %. In this snapshot only the 1.0 % wallet remains
eligible, so the entire redistributed 25 % + 25 % DTD share on a
triggered block flows to small miners. All six wallets continue to
receive the standard 50 % miner share on every block they produce.

The rebalancing is purely economic: a miner above 5 % can either
reduce its hashrate to regain DTD eligibility, or accept the loss of
the lottery share while keeping its 50 % miner share. The protocol
exercises no admin authority — the rule simply applies. (Note that at
this aggressive threshold, if *no* recent producer is under 5 %, the
eligibility set is empty and the DTD pool accumulates rather than
paying out — see the calibration note in §1.)

---

## 5. Tests

New cases in `tests/test_lottery_eligibility.cpp`:

- `test_v13_dominance_gate_inactive_below_12100` — at height 12099,
  a pkh with 100/288 (34.7 %) is still eligible.
- `test_v13_dominance_gate_active_at_12100` — same pkh at height
  12100 is excluded.
- `test_v13_dominance_boundary_14_eligible` — 14/288 = 4.86 % is
  eligible.
- `test_v13_dominance_boundary_15_excluded` — 15/288 = 5.21 % is
  excluded.
- `test_v13_dominance_dynamic_recovery` — pkh excluded at 20/288
  becomes eligible again at 10/288 (rolling recovery).
- `test_v13_dominance_combines_with_recent_winner_cooldown` —
  recent-winner cooldown and anti-dominance gate apply
  independently.
- `test_v13_dominance_partial_window_near_activation` — a pkh with
  20/200 (10 %) on a partial window is excluded.

Helper-level checks live in the same suite via `is_dtd_dominant`
directly through `compute_lottery_eligibility_set`.

---

## 6. What this gate does NOT do

- It does NOT prevent dominant miners from producing blocks. The
  block production path is unaffected.
- It does NOT slash, fine, blacklist or banish any address. The
  exclusion is automatic and reversible.
- It does NOT change the DTD frequency. The 2-of-3 → 1-of-3 flip at
  height 12,100 is a separate behaviour governed by
  `is_lottery_block` in `include/sost/lottery.h`.
- It does NOT depend on `popc_registry.json` or any per-node local
  file. The window count is derived from chain state only.

---

## 7. Rollback

A single-line revert restores the prior behaviour:

```c++
// In include/sost/params.h::is_dtd_dominant, replace the body with:
return false;
```

That short-circuits the gate at every height. Recompile, deploy,
done. The `DTD_DOMINANCE_GATE_HEIGHT` constant can stay in place for
forensics.

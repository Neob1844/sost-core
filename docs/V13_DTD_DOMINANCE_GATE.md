# V13 — DTD Anti-Dominance Eligibility Gate

**Activation height:** `DTD_DOMINANCE_GATE_HEIGHT = 12100`
**Window:** `DTD_DOMINANCE_WINDOW = 288` blocks (≈ 48 h at 10 min/block)
**Threshold:** `DTD_DOMINANCE_MAX_BPS = 1000` (10.00 %)
**Companion gate:** SbPoW-activity (`is_sbpow_eligible`) — same activation height.
**Status:** SHIPPED in this build. Activates automatically at the gate height.

This document describes two V13.5 DTD-eligibility filters that activate at
block 12,100: the **anti-dominance gate** (caps any single miner's share of
the DTD lottery) and the **SbPoW-activity gate** (admits only miners that
have produced at least one SbPoW-signed block — a real signed identity).
Both are independent from the existing recent-winner cooldown and from the
(preparatory) V14 PoPC gate — all apply, and a pkh excluded by any one is
excluded from the eligibility set.

---

## 1. Rule (operational)

From height `h >= DTD_DOMINANCE_GATE_HEIGHT`:

> A miner_pkh is excluded from the DTD lottery eligibility set at
> height `h` iff the pkh's share of the previous
> `DTD_DOMINANCE_WINDOW` blocks is greater than or equal to 10 %.

The window is `[h - 288, h - 1]` inclusive on both ends. The current
block itself is NOT in the window. The threshold check is in
integer math at basis-point precision (no floats).

A dominant miner is NOT prevented from producing normal blocks. The
gate only removes them from the DTD lottery eligibility set. They
continue to receive the standard 50 % miner share on every block they
produce; they only miss the redistributed 25 % + 25 % protocol-side
share that the DTD lottery would otherwise pay them when triggered.

The exclusion is **dynamic**. As soon as the rolling 288-block window
no longer contains ≥ 10 % of that pkh's blocks, eligibility is
restored automatically. No operator action, no retroactive penalty,
no permanent ban.

> **Note on the 10 % calibration.** At 10 % the gate excludes from the DTD
> lottery any pkh producing 29 or more of the last 288 blocks
> (29/288 = 10.07 %). It favours broad distribution without being as
> aggressive as a lower bound. On a chain with very few active miners it can
> still shrink the eligibility set; if every recent producer is at or above
> 10 %, the set is empty and the DTD pool simply accumulates (UPDATE, not
> PAYOUT) until a sub-10 % producer appears. Block production and the 50 %
> miner share are never affected.

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

Equivalent to `mined / observed >= 10 %` evaluated at basis-point
precision. Examples for `observed_window_blocks = 288`:

| `mined` | ratio | excluded? |
|---|---|---|
| 28 | 9.72 % | NO (eligible) |
| 29 | 10.07 % | YES |
| 100 | 34.72 % | YES |

The `observed_window_blocks` argument is the count of blocks the
caller actually saw in the window — typically 288 in steady state,
but possibly less very near the gate activation height. The helper
uses `observed`, not the static constant, so the 10 % rule still
applies at partial windows.

---

## 3. Integration with existing filters

In `compute_lottery_eligibility_set` (`src/lottery.cpp`), four
filters are applied in this order for each pkh that ever mined a block:

1. **Recent-winner cooldown.** Excluded iff the pkh won a block in
   the last `lottery_exclusion_window_at(h)` heights (5 pre-V13,
   6 from V13_HEIGHT = 12000).
2. **V13.5 SbPoW-activity gate.** Excluded iff `is_sbpow_eligible(...)`
   returns false — i.e. the pkh's most recent block is below
   `V11_PHASE2_HEIGHT = 7100`, so it never produced an SbPoW-signed
   block. Active from `DTD_DOMINANCE_GATE_HEIGHT = 12100`.
3. **V13 anti-dominance gate.** Excluded iff `is_dtd_dominant(...)`
   returns true (active from `DTD_DOMINANCE_GATE_HEIGHT = 12100`).
4. **V14 PoPC gate.** Wired but consensus-deferred. See
   `docs/V14_DTD_POPC_ELIGIBILITY.md`.

A pkh excluded by any filter is not in the eligibility set. There is
no "saving throw" or override: each filter applies independently.

### 3.1 SbPoW-activity gate (`is_sbpow_eligible`)

From block 12,100, a candidate must have produced **at least one
SbPoW-signed block** to enter the DTD lottery. SbPoW (a mandatory
`miner_pubkey` + Schnorr signature) is enforced for every block at
height ≥ `V11_PHASE2_HEIGHT = 7100`. Because `last_mined_height` is the
maximum height a pkh ever mined, the check is exactly:

```c++
// eligible only if the pkh has an SbPoW block
last_mined_height >= V11_PHASE2_HEIGHT   // 7100
```

This removes only addresses that mined **exclusively before SbPoW
activation** and then went dormant — they carry no signed identity
("label") proving an active key. It deliberately uses the SbPoW
threshold (7100), **not** V13_HEIGHT (12000): the goal is proven SbPoW
activity, not forced post-V13 participation. Block production and the
50 % miner share are unaffected; only DTD lottery eligibility is filtered.
Below 12,100 the gate is OFF, so historical replay is bit-identical.

Pre-V13.5 behaviour is preserved bit-for-bit. The dominance check
short-circuits to false for `height < DTD_DOMINANCE_GATE_HEIGHT`, so
any replay of historical blocks below 12100 produces identical
eligibility sets to the prior implementation.

---

## 4. Worked example — 2026-05-30 snapshot

Live mining distribution from the explorer at block ~10,940 (window
of the last 288 blocks):

| Wallet | Blocks | Share | Eligible under 10 % gate (block ≥ 12100) |
|---|---|---|---|
| `sost10fa49a0…c624a8` | 110 | 38.2 % | **NO** — ≥ 10 % |
| `sost1993a8eb…d13d8f` | 97 | 33.7 % | **NO** — ≥ 10 % |
| `sost1ad42b84…9bed53` | 31 | 10.8 % | **NO** — ≥ 10 % |
| `sost1146b626…525f99` | 24 | 8.3 % | YES |
| `sost1269ecd7…407159` | 23 | 8.0 % | YES |
| `sost1c1c6d7e…5d66da` | 3 | 1.0 % | YES |

Under the 10 % calibration, every wallet at or above 29/288 (10.07 %)
falls out of the DTD eligibility set until its rolling 288-block share
drops below 10 %. In this snapshot the top three wallets are excluded and
the three smaller wallets (≤ 8.3 %) keep receiving the redistributed
25 % + 25 % DTD share on a triggered block. All six wallets continue to
receive the standard 50 % miner share on every block they produce.

The rebalancing is purely economic: a miner above 10 % can either reduce
its hashrate to regain DTD eligibility, or accept the loss of the lottery
share while keeping its 50 % miner share. The protocol exercises no admin
authority — the rule simply applies. (If *no* recent producer is under 10 %,
the eligibility set is empty and the DTD pool accumulates rather than paying
out — see the calibration note in §1.)

---

## 5. Tests

New cases in `tests/test_lottery_eligibility.cpp`:

- `test_v13_dominance_gate_inactive_below_12100` — at height 12099,
  a pkh with 100/288 (34.7 %) is still eligible.
- `test_v13_dominance_gate_active_at_12100` — same pkh at height
  12100 is excluded.
- `test_v13_dominance_boundary_28_eligible` — 28/288 = 9.72 % is
  eligible.
- `test_v13_dominance_boundary_29_excluded` — 29/288 = 10.07 % is
  excluded.
- `test_v13_dominance_dynamic_recovery` — pkh excluded at 40/288
  becomes eligible again at 20/288 (rolling recovery).
- `test_v13_dominance_combines_with_recent_winner_cooldown` —
  recent-winner cooldown and anti-dominance gate apply
  independently.
- `test_v13_dominance_partial_window_near_activation` — a pkh with
  20/200 (== 10 %) on a partial window is excluded.
- `test_v135_sbpow_gate_excludes_presbpow_miner` — a miner whose most
  recent block is below 7100 (pre-SbPoW) is excluded at height ≥ 12100.
- `test_v135_sbpow_gate_off_below_gate_height` — the same miner is
  eligible at height 12099 (gate off; bit-identical replay).

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

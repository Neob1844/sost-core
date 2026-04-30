# Granular relief cascade fork — block 6700 (V10)

_Status: scheduled for activation at block 6700._
_Author: NeoB._
_Type: coordinated experimental fork. Mandatory update._

## TL;DR

Replaces the V9 staged-relief cascade (drop 3 profile levels every
60 s, starting at 540 s elapsed) with a finer **drop 1 every 60 s,
starting at 600 s**. Floor stays at E7. Lag-advance disabled at
this height. Future-drift cap unchanged.

No supply change. No reward change. No wallet action. No GPU ban.
No pool ban. Hashrate-proportional competition preserved.

## Why

Live data on the V9 fork (blocks 6553–6595, 40 samples) showed:

| metric                       | pre-V8 (6533–6542) | V9 (6553–6592)        |
|------------------------------|--------------------|------------------------|
| blocks                       | 10                 | 40                     |
| mean interval                | 603 s              | 624 s                  |
| deviation vs 600 s target    | +0.5 %             | +4 %                   |
| base profile avg             | H11                | H9–H10                 |
| blocks with relief           | 7/10 (70 %)        | 32/40 (80 %)           |
| effective profile distribution | bimodal H10/H11 ↔ E7 | smooth, all profiles |

V9 already eliminated the H10/H11→E7 cliff that made relief blocks
a reaction-speed race. The remaining sharpness is the **grain of
the cascade**:

- With drop = 3, every relief step over-relaxes by two profile
  levels relative to what the chain actually needs at that
  moment.
- The bitsQ controller then re-tightens on the next block, producing
  the small visible oscillation — `H9 → E5 → H8 → H8 → H9 → H7 → E3
  → E7` over a few blocks.
- Reducing the step from 3 to 1 lets each relief decision match the
  actual lag, and the bitsQ continues to converge to the 10-minute
  target without external intervention.

A second observation prompted the lag-advance change. The V6
calibration (block 5050+) promotes `lag_time = now_time` inside
`casert_compute`, which makes `lag` shrink by one unit per
TARGET_SPACING of wall-clock elapsed. Under V9 this caused the
"off-by-one" extra drop visible in live data — block 6579 was
declared E1 instead of B0 (staged-only would have given B0; the
extra notch came from the lag-advance). With drop = 1 the cascade
is fine-grained enough on its own; disabling lag-advance at V10
makes validation deterministic with respect to `block.timestamp`.

## What changes

### Constants (`include/sost/params.h`)

```cpp
inline constexpr int64_t  CASERT_GRANULAR_RELIEF_HEIGHT    = 6700;
inline constexpr int64_t  CASERT_GRANULAR_RELIEF_START     = 600;  // was 540
inline constexpr int64_t  CASERT_GRANULAR_STEP_SECONDS     = 60;   // unchanged
inline constexpr int32_t  CASERT_GRANULAR_DROP_PER_STEP    = 1;    // was 3
```

### Logic (`src/pow/casert.cpp`)

Two gates added:

1. **Lag-advance** (line ~298) now requires `next_height < CASERT_GRANULAR_RELIEF_HEIGHT`.
   Pre-V10 blocks keep the V6-calibration behaviour. V10+ blocks
   compute `lag` strictly from `chain.back().time`.
2. **Staged relief** (line ~448) picks V9 or V10 constants
   depending on `next_height`. Both schedules continue to apply
   `if (staged < H) H = staged` so they only ever ease the profile.

Anti-stall, lag-clamp, V8 single-step relief, BURST cap, ceiling
table and bitsQ are all unchanged.

### Future-drift cap

`MAX_FUTURE_DRIFT_STAGED = 60` is **kept at 60 s** for V10. Justification:

- Already activated at the V9 fork (block 6550); operationally
  proven on the live chain.
- Under V10 the cap is effectively safer than under V9: a
  future-timestamp attack can at best steal one cascade step,
  which is now worth **1 profile level instead of 3**. The attack
  surface is half what it was.
- Tightening to +30 s would not improve safety further (the cap
  is already aligned with the cascade STEP) while introducing
  real risk of valid blocks being rejected on hosts with NTP drift
  in the 5–15 s range.

The legacy `MAX_FUTURE_DRIFT = 600` continues to apply for blocks
below `CASERT_STAGED_RELIEF_HEIGHT` — historical compatibility.

### Schedule

The cascade formula is **base-agnostic**:

```
eff(elapsed, base) = max(base − floor((elapsed − 600) / 60) − 1, E7)
                                                     for elapsed ≥ 600 s
```

`base` here is the **`raw_base_H`** captured by `casert_compute` BEFORE
any clamps (V8 single-step relief, lag-clamp, anti-stall, V9 staged).
That value is bounded:

```
raw_base_H ∈ [B0, H13]    (i.e. [0, +13])
```

It is **never negative** because `target_profile` is clamped to B0
when `lag ≤ 0` (chain ahead of schedule — see `casert.cpp:326`). The
upper bound is the active height-tier ceiling
(`CASERT_HARD_PROFILE_CEILING_H13` for height ≥ 5750).

The cascade then maps `raw_base_H` into `[E7, H13]` for the declared
profile.

#### Effective profile per base — full table

| elapsed (s) | drop | base = B0 | H1  | H5  | H9  | **H10** | H11 | H12 | H13 |
|------------:|-----:|----------:|----:|----:|----:|--------:|----:|----:|----:|
| < 600       |   0  | B0        | H1  | H5  | H9  | **H10** | H11 | H12 | H13 |
| 600         |   1  | E1        | B0  | H4  | H8  | **H9**  | H10 | H11 | H12 |
| 660         |   2  | E2        | E1  | H3  | H7  | **H8**  | H9  | H10 | H11 |
| 720         |   3  | E3        | E2  | H2  | H6  | **H7**  | H8  | H9  | H10 |
| 780         |   4  | E4        | E3  | H1  | H5  | **H6**  | H7  | H8  | H9  |
| 840         |   5  | E5        | E4  | B0  | H4  | **H5**  | H6  | H7  | H8  |
| 900         |   6  | E6        | E5  | E1  | H3  | **H4**  | H5  | H6  | H7  |
| 960         |   7  | E7 ▣      | E6  | E2  | H2  | **H3**  | H4  | H5  | H6  |
| 1020        |   8  | E7 ▣      | E7 ▣| E3  | H1  | **H2**  | H3  | H4  | H5  |
| 1080        |   9  | E7 ▣      | E7 ▣| E4  | B0  | **H1**  | H2  | H3  | H4  |
| 1140        |  10  | E7 ▣      | E7 ▣| E5  | E1  | **B0**  | H1  | H2  | H3  |
| 1200        |  11  | E7 ▣      | E7 ▣| E6  | E2  | **E1**  | B0  | H1  | H2  |
| 1260        |  12  | E7 ▣      | E7 ▣| E7 ▣| E3  | **E2**  | E1  | B0  | H1  |
| 1320        |  13  | E7 ▣      | E7 ▣| E7 ▣| E4  | **E3**  | E2  | E1  | B0  |
| 1380        |  14  | E7 ▣      | E7 ▣| E7 ▣| E5  | **E4**  | E3  | E2  | E1  |
| 1440        |  15  | E7 ▣      | E7 ▣| E7 ▣| E6  | **E5**  | E4  | E3  | E2  |
| 1500        |  16  | E7 ▣      | E7 ▣| E7 ▣| E7 ▣| **E6**  | E5  | E4  | E3  |
| 1560        |  17  | E7 ▣      | E7 ▣| E7 ▣| E7 ▣| **E7 ▣**| E6  | E5  | E4  |
| 1620        |  18  | E7 ▣      | E7 ▣| E7 ▣| E7 ▣| **E7 ▣**| E7 ▣| E6  | E5  |
| 1680        |  19  | E7 ▣      | E7 ▣| E7 ▣| E7 ▣| **E7 ▣**| E7 ▣| E7 ▣| E6  |
| 1740+       |  20+ | E7 ▣      | E7 ▣| E7 ▣| E7 ▣| **E7 ▣**| E7 ▣| E7 ▣| E7 ▣|

▣ = at the E7 floor (`CASERT_H_MIN`). H10 is highlighted because it
is the most common base on the live chain (recent data showed
raw_base_H ≈ H9–H10 across 40 post-V9 blocks).

**Time-to-E7 by base** (the worst case the chain has to absorb at a
single block before anti-stall kicks in at 3600 s = 60 min):

| base   | elapsed at E7 | minutes |
|-------:|--------------:|--------:|
| B0     | 1020 s        | 17.0 m  |
| H1     | 1080 s        | 18.0 m  |
| H5     | 1500 s        | 25.0 m  |
| H9     | 1500 s        | 25.0 m  |
| **H10**| **1560 s**    | **26.0 m** |
| H11    | 1620 s        | 27.0 m  |
| H12    | 1680 s        | 28.0 m  |
| H13    | 1740 s        | 29.0 m  |

All well below the 60 min anti-stall threshold.

For comparison, the V9 schedule (drop 3 from 540 s) reaches E7 at
840 s for H10 (14 min); V10 reaches it at 1560 s (26 min). The relief
is gentler and combines with bitsQ instead of overshooting it.

## Monte Carlo fairness comparison

`scripts/relief_valve_simulator.py` (in this repo) compares the three schemes against
the live miner profile (1 miner_A @ 195 attempts/s, 1 medium
@ 90, 1 remote @ 36, 2 small @ 22 / 12).

5000 blocks per scheme, seed = 42:

| scheme   | avg blk | stdev | n_E7-or-easier | miner_A (all) | miner_B | miner_C | miner_D | miner_E |
|----------|---------|-------|----------------|---------------|-----------|------|----------|----------|
| V8 cliff | 399.4 s | 244.6 | 1813           | 55.7 %        | 25.2 %    | 9.6 %| 6.4 %    | 3.1 %    |
| V9 staged| 418.7 s | 259.0 | 1924           | 55.2 %        | 25.0 %    | 9.3 %| 6.9 %    | 3.6 %    |
| V10 granular | 491.6 s | 365.2 | 1404       | **55.3 %**    | **25.3 %**| **9.8 %** | **6.0 %** | **3.7 %** |
| _hashrate share (fair baseline)_ | — | — | — | 54.9 %    | 25.4 %    | 10.1 %| 6.2 %  | 3.4 %    |

Reading the V10 row: every miner is within **0.4 %** of its
hashrate share. V8 and V9 both peak at 0.8 % deviation. V10 is
the closest to fair.

Note: the simulator uses a fixed H10 baseline difficulty, so the
absolute avg block time differs from the live chain. The relevant
comparison is the **share distribution** and the **standard
deviation pattern**, not the avg in seconds. On the live chain,
bitsQ continues to absorb any drift to the 10-minute target.

The full simulator output is reproducible with:

```bash
python3 scripts/relief_valve_simulator.py \
    --schemes current,staged,granular --n-blocks 5000 --seed 42
```

## Tests

- `tests/test_casert.cpp` adds section 21 (V10 granular relief)
  with 19 new cases covering activation height, no-drop-before-600s,
  full schedule from H13 base, the E7 floor, and the disabled
  lag-advance.
- All 210 prior cases (210 → 229) continue to pass.

## Operator update

```bash
cd ~/SOST/sostcore/sost-core
git pull --ff-only origin main
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --target sost-node sost-miner -j$(nproc)
# then restart sost-node and sost-miner
```

`git rev-parse --short HEAD` should print the calibration commit
or later. NTP must be active (the +60 s drift cap is unchanged).

## What does NOT change

- Block reward, halving schedule, supply curve.
- Wallet behaviour, address format, signature scheme.
- Mempool / RBF / fee policy.
- ConvergenceX PoW (4 GB dataset + 4 GB scratchpad).
- AI engine / GeaSpirit / Materials engine.
- Useful Compute remains paused for design (no rewards, no queue).
- BurstCap, anti-stall floor (60 min), profile ceiling table.

## Coordinated revert

If post-fork live data deviates materially from the simulator
expectations, a coordinated revert window will be announced and
the chain will return to V9 calibration until the next milestone.
With the bitsQ controller intact this is considered very unlikely;
the granular cascade only refines the descent, it does not change
the equilibrium.

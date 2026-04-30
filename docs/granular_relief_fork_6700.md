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

Effective profile vs elapsed for a base of H10:

```
elapsed (s)   eff profile
 < 600        H10 (no relief)
   600        H9   (drop 1)
   660        H8   (drop 2)
   720        H7   (drop 3)
   780        H6   (drop 4)
   840        H5   (drop 5)
   900        H4   (drop 6)
   960        H3   (drop 7)
  1020        H2   (drop 8)
  1080        H1   (drop 9)
  1140        B0   (drop 10)
  1200        E1   (drop 11)
  1260        E2   (drop 12)
  1320        E3   (drop 13)
  1380        E4   (drop 14)
  1440        E5   (drop 15)
  1500        E6   (drop 16)
  1560+       E7   (floor)
```

For comparison, the V9 schedule (drop 3 from 540 s) reaches E7 at
840 s; V10 reaches it at 1560 s. The relief is gentler and
combines with bitsQ instead of overshooting it.

## Monte Carlo fairness comparison

`scripts/relief_valve_simulator.py` (in
`materials-engine-private`) compares the three schemes against
the live miner profile (1 dominant @ 195 attempts/s, 1 medium
@ 90, 1 remote @ 36, 2 small @ 22 / 12).

5000 blocks per scheme, seed = 42:

| scheme   | avg blk | stdev | n_E7-or-easier | dominant (all) | vostokzyf | neob | small_8c | small_4c |
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

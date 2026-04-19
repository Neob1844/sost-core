# cASERT Dual Subsystem Audit: bitsQ + Equalizer Interaction Analysis

**Date:** 2026-04-15
**Purpose:** V6 fork decision — determine whether both CASERT subsystems work coherently and whether slew-only changes are sufficient.
**Source:** `include/sost/params.h`, `src/pow/casert.cpp`

---

## Section 1: bitsQ CASERT Parameters (current code)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `GENESIS_BITSQ` | 765730 (11.6841 Q16.16) | Calibrated starting difficulty |
| `BITSQ_HALF_LIFE` (V1) | 172800s (48h / 288 blocks) | Exponential decay half-life, blocks < 1450 |
| `BITSQ_HALF_LIFE_V2` | 86400s (24h / 144 blocks) | Exponential decay half-life, blocks >= 1450 |
| `BITSQ_MAX_DELTA_DEN` (V1) | 16 (6.25% cap) | Per-block relative delta cap, blocks < 1450 |
| `BITSQ_MAX_DELTA_DEN_V2` | 8 (12.5% cap) | Per-block relative delta cap, blocks >= 1450 |
| `MIN_BITSQ` | 65536 (1.0 Q16.16) | Global minimum bitsQ |
| `MAX_BITSQ` | 16711680 (255.0 Q16.16) | Global maximum bitsQ |
| `CASERT_AHEAD_ENTER` | 16 blocks | Enter Ahead Guard when >= 16 blocks ahead |
| `CASERT_AHEAD_EXIT` | 8 blocks | V4-only hysteresis exit threshold |
| `CASERT_AHEAD_DELTA_DEN` | 64 (1.56%) | Max downward bitsQ change per block in Ahead Guard |
| `CASERT_AHEAD_PROFILE_THRESH` | 8 | H8+ triggers stronger clamp (defined but unused in current code) |
| `BLOCKS_PER_EPOCH` | 131553 | Epoch length for anchor computation |

**bitsQ delta cap is symmetric** for normal operation: `max_delta = prev_bitsq / 8`, applied equally to up and down adjustments. The Ahead Guard makes it **asymmetric when chain is ahead**: downward delta is further clamped to `prev_bitsq / 64` (1.56% vs 12.5%).

**Epoch anchoring:** bitsQ is computed as `anchor_bitsq * 2^(-td / halflife)` where `anchor_bitsq` is the bitsQ at the first block of the current epoch, and `td` is the timing deviation since the anchor. The per-block delta cap then limits how far the raw result can deviate from the previous block's bitsQ.

---

## Section 2: Equalizer CASERT Parameters (current code)

### PID Gains (Q16.16 fixed-point)

| Parameter | Value (Q16.16) | Value (float) | Weight (% of total) | Description |
|-----------|----------------|---------------|---------------------|-------------|
| `K_R` | 3277 | 0.05 | 7.5% | Instantaneous log-ratio (r_n) |
| `K_L` | 26214 | 0.40 | 59.7% | Schedule lag (dominant term) |
| `K_I` | 9830 | 0.15 | 22.4% | Integrator (accumulated lag) |
| `K_B` | 3277 | 0.05 | 7.5% | Burst score (S - M) |
| `K_V` | 1311 | 0.02 | 3.0% | Volatility |

**Total gain: 0.67.** Lag (K_L) dominates at 60% of total weight.

### EWMA Smoothing

| Parameter | Value | Window (blocks) |
|-----------|-------|----------------|
| `EWMA_SHORT_ALPHA` | 32/256 | ~8-block |
| `EWMA_LONG_ALPHA` | 3/256 | ~96-block |
| `EWMA_VOL_ALPHA` | 16/256 | ~16-block |
| `INTEG_RHO` | 253/256 (~0.988) | Integrator leak |
| `INTEG_MAX` | 6553600 (100.0 Q16.16) | Integrator clamp |

### Slew Rate and Policy

| Parameter | Value | Description |
|-----------|-------|-------------|
| `CASERT_V3_SLEW_RATE` | **1** (was 3 pre-V6) | Max profile levels per block |
| `CASERT_V3_LAG_FLOOR_DIV` | 8 | lag_floor = lag / 8 when lag > 10 |
| `CASERT_V5_EXTREME_MIN` | 10 | H10+ requires +1/block climb |
| `CASERT_EBR_ENTER` | -10 (100min behind) | Force H <= B0 |
| `CASERT_EBR_LEVEL_E2` | -15 (150min behind) | Force H <= E2 |
| `CASERT_EBR_LEVEL_E3` | -20 (200min behind) | Force H <= E3 |
| `CASERT_EBR_LEVEL_E4` | -25 (250min behind) | Force H <= E4 (minimum) |
| `CASERT_ANTISTALL_FLOOR_V5` | 3600s (60min) | Anti-stall activation threshold |
| `CASERT_ANTISTALL_EASING_EXTRA` | 21600s (6h) | Time at B0 before easing profiles |

### Profile Table (40 profiles: E4 through H35)

| Profile | Index | Scale | Steps | K | Margin | Stability % | Rel. Difficulty |
|---------|-------|-------|-------|---|--------|-------------|----------------|
| E4 | -4 | 1 | 2 | 3 | 280 | 100% | 0.35x |
| E3 | -3 | 1 | 3 | 3 | 240 | 100% | 0.50x |
| E2 | -2 | 1 | 4 | 3 | 225 | 100% | 0.65x |
| E1 | -1 | 1 | 4 | 4 | 205 | 100% | 0.80x |
| B0 | 0 | 1 | 4 | 4 | 185 | 100% | 1.00x |
| H1 | 1 | 1 | 5 | 4 | 170 | 97% | 1.25x |
| H2 | 2 | 1 | 5 | 5 | 160 | 92% | 1.55x |
| H3 | 3 | 1 | 6 | 5 | 150 | 85% | 2.00x |
| H4 | 4 | 1 | 6 | 6 | 145 | 78% | 2.50x |
| H5 | 5 | 2 | 5 | 5 | 140 | 65% | 3.20x |
| H6 | 6 | 2 | 6 | 5 | 135 | 50% | 4.20x |
| H7 | 7 | 2 | 6 | 6 | 130 | 45% | 5.50x |
| H8 | 8 | 2 | 7 | 6 | 125 | 35% | 7.50x |
| H9 | 9 | 2 | 7 | 7 | 120 | 25% | 10.0x |
| H10 | 10 | 2 | 7 | 7 | 115 | 15% | 14.0x |
| H11 | 11 | 2 | 8 | 7 | 110 | 8% | 20.0x |
| H12 | 12 | 2 | 8 | 8 | 105 | 3% | 30.0x |
| H13-H35 | 13-35 | 2 | 8-20 | 8-20 | 105-100 | <3% | 30x+ |

---

## Section 3: Computation Flow

### Step-by-step pseudocode for computing a new block's difficulty:

```
casert_compute(chain, next_height, now_time):

  ┌─── STEP 1: Compute bitsQ (numerical difficulty) ───────────────┐
  │  anchor = first block of current epoch                          │
  │  td = parent_time - expected_time_at_parent                     │
  │  raw_bitsq = anchor_bitsq * 2^(-td / halflife_v2)              │
  │  delta = raw_bitsq - prev_bitsq                                │
  │  delta = clamp(delta, -prev_bitsq/8, +prev_bitsq/8)  [12.5%]  │
  │  if (ahead >= 16 blocks AND delta < 0):                        │
  │      delta = max(delta, -prev_bitsq/64)  [1.56% cap]           │
  │  bitsq = clamp(prev_bitsq + delta, MIN_BITSQ, MAX_BITSQ)      │
  └─────────────────────────────────────────────────────────────────┘

  ┌─── STEP 2: Compute equalizer signals ──────────────────────────┐
  │  dt = last_block_time - second_to_last_time                     │
  │  r_n = log2(600 / dt)  [instantaneous rate signal]              │
  │  lag = (height - 1) - floor(elapsed / 600)  [schedule lag]      │
  │  S, M, V, I = EWMA over last 128 blocks                        │
  │  burst_score = S - M                                            │
  └─────────────────────────────────────────────────────────────────┘

  ┌─── STEP 3: Compute PID control signal ─────────────────────────┐
  │  U = K_R*r_n + K_L*lag + K_I*I + K_B*burst + K_V*V             │
  │  H_raw = U >> 16                                                │
  │  H = clamp(H_raw, H_MIN=-4, H_MAX=35)                          │
  └─────────────────────────────────────────────────────────────────┘

  ┌─── STEP 4: Apply safety rules (pre-slew) ──────────────────────┐
  │  if (lag <= 0): H = min(H, 0)  [never harden when behind]      │
  │  if (chain_len < 10): H = min(H, 0)                            │
  └─────────────────────────────────────────────────────────────────┘

  ┌─── STEP 5: Apply slew rate ────────────────────────────────────┐
  │  prev_H = stored profile_index from last block                  │
  │  H = clamp(H, prev_H - slew_rate, prev_H + slew_rate)          │
  │  (V6: slew_rate = 1; V3-V5: slew_rate = 3)                     │
  └─────────────────────────────────────────────────────────────────┘

  ┌─── STEP 6: Apply lag floor ────────────────────────────────────┐
  │  if (lag > 10): H = max(H, lag / 8)                             │
  └─────────────────────────────────────────────────────────────────┘

  ┌─── STEP 7: V5 post-slew safety + EBR + extreme cap ───────────┐
  │  if (lag <= 0): H = min(H, 0)  [re-applied after slew]         │
  │  if (lag <= -10): H = min(H, EBR_cliff)                         │
  │  if (H >= 10 and H > prev_H + 1): H = prev_H + 1  [slow entry]│
  └─────────────────────────────────────────────────────────────────┘

  ┌─── STEP 8: Anti-stall (mining-time only) ──────────────────────┐
  │  if (stall >= 60min and H > 0): zone-based decay toward B0     │
  │  if (at B0 for 6+h extra): activate easing profiles (E1-E4)    │
  └─────────────────────────────────────────────────────────────────┘

  return { bitsq, profile_index = H }
```

### Key ordering facts:

1. **bitsQ is computed FIRST** (line 169: `dec.bitsq = casert_next_bitsq(chain, next_height)`)
2. **The profile/equalizer is computed SECOND** (lines 170-458)
3. **bitsQ does NOT read or use the profile index** — it only looks at timestamps and the anchor
4. **The profile does NOT read or use bitsQ** — it only looks at timestamps and schedule lag
5. **They share the same timing inputs** (block timestamps, schedule lag) but compute independently
6. **There is NO feedback loop between them in the computation for a single block**

---

## Section 4: Cap Behavior Analysis

### bitsQ per-block cap

The current (V2+) cap is **12.5%** of the previous bitsQ per block (`prev_bitsq / 8`).

At bitsQ = 765730 (genesis), max_delta = 95716, meaning bitsQ can move by ~1.46 bits per block.

Over 10 blocks, bitsQ can compound: approximately `0.875^10` to `1.125^10` = 0.263x to 3.247x, which is a wide range but still far slower than the profile can move.

### Profile's effect on effective difficulty

The profile changes effective difficulty by a **multiplicative factor** that is independent of bitsQ. Moving from B0 to H9 multiplies difficulty by 10x. Moving from B0 to H35 multiplies by 30x+.

With slew=3 (V3-V5): the profile can move from B0 to H9 in 3 blocks (B0 -> H3 -> H6 -> H9). This is a 10x difficulty change in 3 blocks.

With slew=1 (V6): the profile can move from B0 to H9 in 9 blocks. This is a 10x difficulty change in 9 blocks.

### Could bitsQ cap LIMIT the profile's ability?

**No.** bitsQ and profile operate on independent axes:
- bitsQ sets the **numerical threshold** (commit < target)
- Profile sets the **stability test parameters** (how many attempts pass)

They combine multiplicatively in effective mining time. The bitsQ cap does not constrain the profile at all.

However, when the chain is ahead and the profile is hardening, the **Ahead Guard clamps bitsQ downward movement to 1.56%/block**. This means bitsQ stays high while the profile is also high, compounding the difficulty increase. This is by design — it prevents bitsQ from "undoing" the equalizer's braking.

### Could bitsQ cap AMPLIFY oscillation?

**Yes, indirectly.** The mechanism:

1. Chain gets ahead. Equalizer pushes profile to H9+. bitsQ also wants to drop (ease difficulty since blocks are fast) but Ahead Guard limits it to 1.56%/block.
2. The combined effect (high profile + still-high bitsQ) overshoots: blocks become very slow.
3. Chain falls behind. Profile drops to B0 (safety rule: never harden when behind). bitsQ now wants to rise but is capped at 12.5%/block.
4. bitsQ is slow to recover upward, so effective difficulty drops below target (profile at B0 + low bitsQ).
5. Blocks come fast again, chain gets ahead, cycle repeats.

The **asymmetry** is key: bitsQ drops slowly when ahead (1.56%) but recovers upward at 12.5%. Combined with the profile's rapid descent (safety rule forces B0 instantly when behind), this creates a ratchet that can amplify oscillation.

With slew=1, the profile moves slowly enough that bitsQ can track it, reducing this effect.

---

## Section 5: Interaction Map

### Scenario 1: Chain is 10 blocks ahead of schedule

| Subsystem | Response |
|-----------|----------|
| **bitsQ** | Exponential formula produces lower bitsQ (wants to ease). Delta cap limits to -12.5%/block. Ahead Guard NOT active (threshold is 16). Normal operation. |
| **Equalizer** | lag=10 is the threshold boundary. PID signal is positive (K_L*10 dominates). H_raw likely ~4 (0.40 * 10 = 4.0 from lag alone). Slew limits movement from prev_H. lag_floor NOT active (requires lag > 10). |
| **Interaction** | Both push same direction: bitsQ drops (easier numbers), profile hardens (harder stability). They partially cancel: bitsQ makes blocks easier numerically while profile makes them harder structurally. Net effect depends on profile level reached. |

### Scenario 2: Chain is 10 blocks behind schedule

| Subsystem | Response |
|-----------|----------|
| **bitsQ** | Exponential formula produces higher bitsQ (harder). Delta cap limits to +12.5%/block. |
| **Equalizer** | lag=-10 is exactly EBR_ENTER. Safety rule forces H <= 0. EBR forces H <= B0. Profile is at B0 or below. |
| **Interaction** | **OPPOSING**: bitsQ hardens (makes blocks slower) while profile eases to B0 (makes stability easier). The profile easing dominates for liveness — stability goes to 100% at B0, removing the structural brake. bitsQ hardening is slow (12.5%/block) and modest in magnitude. |

### Scenario 3: A 60-minute gap just occurred

| Subsystem | Response |
|-----------|----------|
| **bitsQ** | The gap shifts td significantly positive (chain is behind expected time). Raw bitsQ jumps up (harder), capped at +12.5%. |
| **Equalizer** | r_n = log2(600/3600) = -2.58 (very negative: block was slow). lag drops significantly. Safety rule forces H <= 0 if behind. Anti-stall fires if stall >= 60min (V5 threshold). At B0, no further easing unless 6h+ at B0. |
| **Interaction** | **OPPOSING**: bitsQ pushes harder (wrong direction for recovery), but only at 12.5%/block. Profile drops to B0 and anti-stall may fire. The profile response is immediate and dominant; bitsQ drift is a minor headwind. |

### Scenario 4: 5 blocks came in under 30 seconds each

| Subsystem | Response |
|-----------|----------|
| **bitsQ** | Chain runs ahead of schedule. td becomes negative. Raw bitsQ drops. Capped at -12.5%/block. If ahead >= 16, Ahead Guard limits to -1.56%/block. |
| **Equalizer** | r_n = log2(600/30) = 4.32 (very positive: blocks are fast). EWMA_short spikes. Burst score (S-M) increases. Lag jumps positive. PID outputs high H_raw. Slew limits transition rate. lag_floor may kick in if lag > 10. |
| **Interaction** | **COHERENT for braking**: bitsQ stays high (Ahead Guard prevents relaxation), profile climbs toward hardening. Both work together to slow the chain. This is the intended design. |

### Scenario 5: Anti-stall just activated

| Subsystem | Response |
|-----------|----------|
| **bitsQ** | Not directly affected by anti-stall. bitsQ continues exponential tracking based on timestamps. Since the chain is stuck, td grows large, pushing bitsQ up (harder) — **wrong direction**. But this only matters at ~12.5%/block if blocks were being mined. Since no blocks are being mined, bitsQ is frozen at its last value. |
| **Equalizer** | Anti-stall is a mining-time-only override: it decays H toward B0 at zone-based rates (10-20 min per level). After 6h at B0, easing profiles (E1-E4) activate. This directly overrides the PID output. |
| **Interaction** | Anti-stall is purely an equalizer mechanism. bitsQ is inert (no new blocks to trigger recalculation). When a block is finally mined, bitsQ will see the large gap and adjust, while the profile will reflect the anti-stall state at mining time. |

---

## Section 6: Answers to Key Questions

### 1. What does the code say TODAY about the bitsQ cap?

The bitsQ per-block cap is `prev_bitsq / 8` = **12.5%** symmetric for normal blocks (V2+). The Ahead Guard reduces downward cap to `prev_bitsq / 64` = **1.56%** when the chain is 16+ blocks ahead. The cap is applied as `delta = clamp(delta, -max_delta, +max_delta)` after the exponential computation but before the global min/max bounds. The value `CASERT_V3_SLEW_RATE = 1` in the current code confirms the slew rate has already been changed from 3 to 1 for V6.

### 2. Is the cap actively shaping dynamics or just a safety net?

**Actively shaping dynamics.** The 12.5% cap limits bitsQ movement to ~1.46 bits/block at genesis difficulty. Since the half-life is 144 blocks (24h), the exponential would want to move much faster during sharp timing deviations. The cap prevents bitsQ from overshooting but also slows its recovery. The Ahead Guard further constrains downward bitsQ when ahead, which is an active design choice to prevent bitsQ from counteracting the equalizer's braking.

### 3. Do bitsQ and equalizer work coherently together?

**Mostly yes, with one important exception.** They are coherent when:
- Chain is ahead: both make blocks harder (bitsQ stays high via Ahead Guard, profile hardens)
- Chain is on schedule: bitsQ is stable, profile is at B0

They are **partially incoherent** when:
- Chain is behind: bitsQ wants to harden (exponential pushes up because time is behind), while the profile eases to B0. This is a design tension: bitsQ responds to the time-domain signal (blocks were slow, so bitsQ should drop to make them easier), but the exponential formula compares parent time to expected time, and when behind schedule the formula actually pushes bitsQ UP (since `td` is positive when behind, the exponent is negative, and `2^(-positive)` < 1... wait, let me re-read).

Actually: `td = parent_time - expected_parent_time`. When blocks are slow, parent_time > expected_parent_time, so td > 0. The exponent is `(-td) / halflife` which is negative, so `2^(negative)` < 1, meaning raw_bitsq < anchor_bitsq. **bitsQ drops when behind schedule** (makes blocks easier). This is **coherent** with the profile also easing. Both subsystems ease together when behind.

When ahead: td < 0, exponent is positive, raw_bitsq > anchor_bitsq. **bitsQ rises when ahead** (makes blocks harder). Coherent with profile hardening.

**Conclusion: they are coherent in direction in all normal scenarios.** The potential issue is **magnitude and timing**: the profile can jump multiple levels per block while bitsQ is capped, creating temporary imbalances.

### 4. Do they interfere in any range?

The critical interference range is **the transition from "ahead" to "behind"**:
- Profile can snap from H9 to B0 in one block (via safety rule post-slew: lag <= 0 forces H <= 0)
- bitsQ cannot snap — it is capped at 12.5%/block
- Result: for several blocks after the transition, bitsQ is still low (from the ahead period where it was being eased) while the profile is at B0. Effective difficulty drops below target, causing fast blocks and re-triggering the ahead condition.

With slew=1, the profile cannot reach H9 as fast, so the snap-back is less severe.

### 5. Does the sawtooth come from the equalizer, bitsQ, or their interaction?

**Primarily from the equalizer.** The sawtooth pattern is:
1. Profile climbs to H9+ (high difficulty, blocks slow down)
2. Chain falls behind → safety rule snaps profile to B0 (sudden ease)
3. Blocks speed up → chain gets ahead → profile climbs again
4. Repeat

bitsQ **amplifies** the sawtooth slightly through the ratchet effect described in Section 4, but the primary oscillation driver is the equalizer's ability to create large one-block discontinuities when the safety rule fires.

With slew=1, the equalizer cannot climb fast enough to reach H9+ before the chain self-corrects, so the sawtooth is largely eliminated.

### 6. Would changing slew without reviewing bitsQ cap be incomplete?

**Slew=1 is sufficient for eliminating the sawtooth.** However, the bitsQ cap deserves review for a separate reason: at 12.5%/block, it may be overly generous for a chain that now has gentler profile transitions. A tighter bitsQ cap (e.g., 16 = 6.25%) would further smooth difficulty transitions. But this is a refinement, not a prerequisite.

The Ahead Guard (1.56% cap when ahead) is the more important bitsQ parameter. With slew=1, the chain rarely gets 16+ blocks ahead because the profile responds early, so the Ahead Guard fires less often. This is fine — it becomes a true safety net rather than an active controller.

### 7. Which is the true "dominant" controller today?

**The equalizer is the dominant controller.** It can change effective mining time by 30x+ (E4 to H35), while bitsQ can change by at most 12.5% per block. The profile table's nonlinear difficulty curve means that profile changes dominate the block time distribution.

bitsQ serves as a **slow-moving baseline adjustment** that tracks the fundamental hashrate level. The equalizer provides **fast structural correction** for schedule deviations.

---

## Section 7: Recommendation for V6

### Can V6 be decided by looking at slew only?

**Yes, for the primary decision.** The slew rate change from 3 to 1 is the single most impactful parameter for eliminating the sawtooth oscillation. The evidence is strong:
- The sawtooth is caused by the equalizer's rapid climb to extreme profiles followed by safety-rule snap-back
- Slew=1 prevents rapid climb, keeping the profile in moderate ranges where self-correction occurs naturally
- bitsQ is not the oscillation driver and does not need to change for the sawtooth fix

### Must bitsQ cap/halflife also be reviewed first?

**Not for the V6 fork itself, but recommended for V7 planning.** Specific considerations:

1. **Half-life (24h):** With slew=1, the profile moves slowly enough that bitsQ has time to track. The 24h half-life is well-matched. No change needed.

2. **Delta cap (12.5%):** This is generous relative to slew=1's maximum effective difficulty change of ~25% per block (one profile level). A tighter cap (6.25%) would create better symmetry between the two subsystems. This is a V7 candidate.

3. **Ahead Guard (1.56% at 16+ ahead):** With slew=1, the chain rarely reaches 16+ ahead. The Ahead Guard becomes dormant. This is fine — it remains as a safety net. No change needed.

**Verdict: V6 can proceed with slew=1 alone. The bitsQ subsystem is coherent, non-interfering at the current operating point, and does not block the fork.**

# SOST cASERT Simulator Parity Report

Generated: 2026-04-16 17:26:56 UTC

C++ source: `src/pow/casert.cpp` + `include/sost/params.h`
Python simulator: `scripts/v5_simulator.py`

## 1. CONSTANTS COMPARISON

| Constant | C++ Value | Python Value | Status |
|----------|-----------|--------------|--------|
| GENESIS_TIME | 1773597600 | 1773597600 | PASS |
| TARGET_SPACING | 600 | 600 | PASS |
| GENESIS_BITSQ | 765730 | 765730 | PASS |
| H_MIN | -4 | -4 | PASS |
| H_MAX | 12 | 12 | PASS |
| V3_SLEW_RATE | 3 | 3 | PASS |
| V3_LAG_FLOOR_DIV | 8 | 8 | PASS |
| V4_FORK_HEIGHT | 4170 | 4170 | PASS |
| AHEAD_ENTER | 16 | 16 | PASS |
| V5_FORK_HEIGHT | 4300 | 4300 | PASS |
| ANTISTALL_FLOOR_V5 | 3600 | 3600 | PASS |
| ANTISTALL_FLOOR | 7200 | 7200 | PASS |
| ANTISTALL_EASING_EXTRA | 21600 | 21600 | PASS |
| EBR_ENTER | -10 | -10 | PASS |
| EBR_LEVEL_E2 | -15 | -15 | PASS |
| EBR_LEVEL_E3 | -20 | -20 | PASS |
| EBR_LEVEL_E4 | -25 | -25 | PASS |
| V5_EXTREME_MIN | 10 | 10 | PASS |

### Anti-stall Decay Zone Costs

| Zone | C++ Cost (s) | Python Cost (s) | Status |
|------|-------------|-----------------|--------|
| H>=7 | 600 | 600 | PASS |
| H>=4 | 900 | 900 | PASS |
| else (H1-H3) | 1200 | 1200 | PASS |

### Easing Per-Level Cost

| Parameter | C++ | Python | Status |
|-----------|-----|--------|--------|
| Easing seconds per level | 1800 | N/A (not implemented) | WARN |

### Profile Table (CASERT_PROFILES)

Profile table present in C++ with 17 entries: **MATCH**

Note: The Python simulator does not use the profile table directly. It uses STAB_PCT and PROFILE_DIFFICULTY lookup tables as behavioral approximations of the scale/steps/k/margin parameters.

### Constants Present in C++ Only (Not in Simulator)

These are intentionally omitted because the simulator uses a simplified model:

- `CASERT_EWMA_SHORT_ALPHA` = 32
- `CASERT_EWMA_LONG_ALPHA` = 3
- `CASERT_EWMA_VOL_ALPHA` = 16
- `CASERT_EWMA_DENOM` = 256
- `CASERT_INTEG_RHO` = 253
- `CASERT_INTEG_ALPHA` = 1
- `CASERT_INTEG_MAX` = 6553600
- `CASERT_K_R` = 3277
- `CASERT_K_L` = 26214
- `CASERT_K_I` = 9830
- `CASERT_K_B` = 3277
- `CASERT_K_V` = 1311
- `CASERT_HYSTERESIS` = 0
- `CASERT_DT_MIN` = 1
- `CASERT_DT_MAX` = 86400
- `BITSQ_HALF_LIFE` = 172800
- `BITSQ_HALF_LIFE_V2` = 86400
- `BITSQ_MAX_DELTA_DEN` = 16
- `BITSQ_MAX_DELTA_DEN_V2` = 8
- `CASERT_V2_FORK_HEIGHT` = 1450
- `CASERT_V3_FORK_HEIGHT` = 4100
- `CASERT_V3_1_FORK_HEIGHT` = 4110
- `CASERT_AHEAD_EXIT` = 8
- `CASERT_AHEAD_DELTA_DEN` = 64
- `CASERT_AHEAD_PROFILE_THRESH` = 8
- `CASERT_ANTISTALL_INTEG_DECAY` = 240

## 2. LOGIC COMPARISON

### LOGIC-001: PID controller is simplified in simulator

**Severity:** HIGH

C++ uses a full 5-term PID controller (K_R*r + K_L*lag + K_I*I + K_B*burst + K_V*vol) with EWMA smoothing. Python uses a simplified approximation: H_raw = int(round(lag * 0.25 + burst_signal * 0.5)). The gains are NOT the same as the C++ K_L=0.40, K_R=0.05, etc.

**Impact:** Profile selection will differ between C++ and Python for the same chain state. The simulator is a behavioral model, not a bit-exact replica. This is documented in the simulator header.

- C++ location: `casert.cpp:234-238`
- Python location: `v5_simulator.py:124`

### LOGIC-002: bitsQ primary controller absent from simulator

**Severity:** MEDIUM

C++ computes bitsQ (Q16.16 difficulty) using exponential adjustment with epoch anchoring, half-life, delta caps, and Ahead Guard. Python simulator does not model bitsQ at all; it uses a separate block-time sampling model (exponential distribution based on PROFILE_DIFFICULTY and STAB_PCT).

**Impact:** Simulator cannot verify bitsQ-related behavior (delta caps, Ahead Guard on bitsQ). Equalizer policy is tested, bitsQ is not.

- C++ location: `casert.cpp:67-158`
- Python location: `v5_simulator.py:188-208 (sample_block_dt)`

### LOGIC-003: EWMA signal computation absent from simulator

**Severity:** MEDIUM

C++ computes S (short EWMA), M (long EWMA), V (volatility), and I (integrator) iteratively over the last 128 blocks. Python simulator approximates the control signal directly from lag and a single burst_signal term.

**Impact:** Volatility-driven and integrator-driven profile adjustments are not captured. The simulator may under- or over-respond to sustained deviations.

- C++ location: `casert.cpp:192-224`
- Python location: `v5_simulator.py:121-124`

### LOGIC-004: Safety rule 1 post-slew: MATCHES C++ V5 logic

**Severity:** OK

Both C++ and Python apply safety rule 1 (if lag <= 0: H = min(H, 0)) AFTER the slew rate when V5 is active. This is the key V5 fix.

**Impact:** Correct behavior.

- C++ location: `casert.cpp:371-373`
- Python location: `v5_simulator.py:143-144`

### LOGIC-005: V2 slew rate heuristic not modeled in simulator

**Severity:** LOW

C++ has a V2 code path (blocks < 4100) with +/-1 slew and heuristic prev_H estimation. The simulator only models V3+ behavior (starts at height 4300 by default).

**Impact:** Not relevant for V5 analysis since the simulator focuses on heights >= 4300.

- C++ location: `casert.cpp:404-416`
- Python location: `N/A`

### LOGIC-006: V3/V3.1 prev_H recomputation not modeled

**Severity:** LOW

C++ has separate code paths for V3 (PID recompute) and V3.1 (stored profile_index with fallback). The simulator uses chain[-1]['profile_index'] directly (V4+ behavior).

**Impact:** Not relevant for V5 analysis. V3/V3.1 heights are in the past.

- C++ location: `casert.cpp:292-339`
- Python location: `v5_simulator.py:111`

### LOGIC-008: PID lag gain mismatch: C++ K_L=0.4000 vs Python lag*0.25

**Severity:** HIGH

C++ K_L = 26214/65536 = 0.4000. Python uses lag * 0.25. The Python weight is applied to raw lag (integer), while C++ applies K_L to L_q16 >> 16. The effective scaling differs because C++ also includes K_R, K_I, K_B, K_V terms and a final >> 16 normalization.

**Impact:** Exact profile indices will differ. The simulator is a behavioral approximation, not a consensus-exact replica.

- C++ location: `casert.cpp:234 (CASERT_K_L = 26214)`
- Python location: `v5_simulator.py:124 (lag * 0.25)`

## 3. BEHAVIORAL CHECKS

| ID | Check | Status | Detail |
|----|-------|--------|--------|
| BEH-001 | Determinism (same seed, same output) | PASS | Ran 500 blocks twice with seed=42. Identical=yes. |
| BEH-002 | No unexplained profile jumps (delta > 3 without lag_floor/safety justification) | PASS | Max observed jump: 4. Unexplained violations: 0. (Jumps > 3 from lag_floor or safety-rule-post-slew are expected.) |
| BEH-003 | Target mean near 600s over 5000 blocks | PASS | Mean block interval: 600.0s (target: 600s, tolerance: +/-15%). Within tolerance. |
| BEH-004 | Anti-stall monotonicity (profile never increases during stall) | PASS | Tested stall from 0 to 40000s. Monotonic=yes. Violations: 0. |
| BEH-005 | No undefined profile indices (outside H_MIN to H_MAX) | PASS | Observed profiles: [-4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6]. Valid range: [-4, 12]. Out-of-range: none. |

## 4. OVERALL VERDICT

**Confidence: MEDIUM**

Equalizer policy constants match, but the simulator uses a simplified PID model and omits bitsQ/EWMA computation. It is a behavioral approximation, not a bit-exact replica.

- Constants matched: 18/18
- Constants warned: 0
- Constants failed: 0
- Logic findings (HIGH): 2
- Logic findings (MEDIUM): 2
- Behavioral checks passed: 5/5

## 5. DISCREPANCIES

Found 4 discrepancy/discrepancies:

1. **LOGIC-001: PID controller is simplified in simulator** [HIGH]: Profile selection will differ between C++ and Python for the same chain state. The simulator is a behavioral model, not a bit-exact replica. This is documented in the simulator header.
2. **LOGIC-002: bitsQ primary controller absent from simulator** [MEDIUM]: Simulator cannot verify bitsQ-related behavior (delta caps, Ahead Guard on bitsQ). Equalizer policy is tested, bitsQ is not.
3. **LOGIC-003: EWMA signal computation absent from simulator** [MEDIUM]: Volatility-driven and integrator-driven profile adjustments are not captured. The simulator may under- or over-respond to sustained deviations.
4. **LOGIC-008: PID lag gain mismatch: C++ K_L=0.4000 vs Python lag*0.25** [HIGH]: Exact profile indices will differ. The simulator is a behavioral approximation, not a consensus-exact replica.


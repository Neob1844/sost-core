# cASERT V5 — Design Document (Internal)

## Determinism Fix (V5.0) + Potential Stability Enhancements (V5.1)

---

## 1. Executive Summary

This document defines the design rationale and implementation plan for the upcoming cASERT V5 update.

V5 is divided into two logically separate components:

- **V5.0 — Determinism Fix (mandatory)**
- **V5.1 — Stability Enhancements (conditional, data-driven)**

The primary objective is to:

> Ensure full consensus determinism under all execution paths, while evaluating potential improvements to chain stability under extreme lag conditions.

---

## 2. Current System Overview

cASERT currently operates with three interacting components:

### 2.1 bitsQ (Numerical Difficulty)

- Slow controller
- Adjusts per block
- Based on time deviation vs expected schedule

### 2.2 Equalizer (Profile System)

- Fast controller
- 17 discrete profiles (E4 → H12)
- Driven by PID-style multi-signal input:
  - rate
  - lag
  - integrator
  - burst
  - volatility

### 2.3 Anti-Stall

- Safety mechanism
- Activates when no block is found for extended periods
- Gradually reduces difficulty

---

## 3. V4 Ahead Guard — Identified Issue

### 3.1 Description

The current V4 Ahead Guard (commit `8c8d8bb`, `src/pow/casert.cpp` line ~123) introduces a coordination mechanism to prevent premature difficulty relaxation when the chain is ahead of schedule.

However, the implementation includes:

```cpp
static bool ahead_correction_mode = false;
if (schedule_lag >= CASERT_AHEAD_ENTER) ahead_correction_mode = true;
if (schedule_lag <= CASERT_AHEAD_EXIT)  ahead_correction_mode = false;
if (ahead_correction_mode) { /* clamp downward delta */ }
```

This introduces persistent internal state inside consensus-critical logic.

### 3.2 Why this is a problem

Consensus must be a **pure function of chain data**. The use of persistent internal state introduces risk in the following scenarios:

- Bootstrap from different entry points
- Node restarts
- Reorgs
- Divergent execution paths across function call sites

Two nodes processing the same chain could theoretically produce different `bitsQ` results depending on prior execution state.

### 3.3 Current Status

- **No divergence has been observed** in practice
- The issue is considered **latent risk**, not active bug
- Must be resolved before it can manifest in production

---

## 4. V5.0 — Determinism Fix

### 4.1 Objective

Remove all non-deterministic state from Ahead Guard.

### 4.2 Design

Replace stateful logic:

```cpp
static bool ahead_correction_mode = false;
if (schedule_lag >= CASERT_AHEAD_ENTER) ahead_correction_mode = true;
if (schedule_lag <= CASERT_AHEAD_EXIT)  ahead_correction_mode = false;
if (ahead_correction_mode) { ... }
```

with stateless logic:

```cpp
if (schedule_lag >= CASERT_AHEAD_ENTER) {
    int64_t ahead_max_drop = (int64_t)prev_bitsq / CASERT_AHEAD_DELTA_DEN;
    if (ahead_max_drop < 1) ahead_max_drop = 1;
    delta = std::max<int64_t>(-ahead_max_drop, delta);
}
```

### 4.3 Result

- No persistent state
- No hidden mode
- Fully deterministic behavior
- Identical results across:
  - fresh sync from genesis
  - long-running nodes
  - reorg scenarios
  - chain import via `chain.json`

### 4.4 Trade-off

- Loss of hysteresis (AHEAD_ENTER / AHEAD_EXIT dual threshold)
- Slightly more reactive behavior around the entry threshold
- This trade-off is acceptable in favor of correctness

### 4.5 Scope

V5.0 changes:

- **ONLY** Ahead Guard implementation
- **DOES NOT** modify:
  - equalizer profiles
  - PID controller
  - anti-stall logic
  - emission rules
  - economic structure

### 4.6 Consensus Impact

This is a consensus change. All nodes must upgrade before the activation block.

---

## 5. V5.1 — Potential Stability Enhancements (Under Evaluation)

**V5.1 is NOT part of the immediate deployment.**
It will only be implemented if justified by live network data.

### 5.2 Problem Observed

When the chain transitions from:

`ahead → normal → behind`

the equalizer may remain at high profiles (H8–H12) longer than desired due to slew rate constraints (±3 per block).

This can result in:

- delayed recovery
- overshoot into negative lag
- inefficient convergence

### 5.3 Proposed Solution — Combined Approach

#### A. Safety Rule Reordering

Apply the "never harden when behind" rule **after** the slew rate clamp:

```cpp
// Move this to AFTER the slew rate block:
if (lag <= 0) H = std::min<int32_t>(H, 0);
```

**Effect:**

- Guarantees no hardening when behind
- Eliminates lag-induced overshoot persistence

#### B. Emergency Behind Release (EBR)

Introduce stateless emergency easing with progressive cliffs:

```cpp
if (lag <= -10) {
    int32_t ebr_floor;
    if      (lag <= -25) ebr_floor = -4;  // E4
    else if (lag <= -20) ebr_floor = -3;  // E3
    else if (lag <= -15) ebr_floor = -2;  // E2
    else                 ebr_floor =  0;  // B0 (lag in [-14, -10])
    H = std::min<int32_t>(H, ebr_floor);
}
```

### 5.4 Design Principles

- Fully stateless (no `static` variables)
- Deterministic (depends only on chain data)
- Step-based (cliffs, not linear)
- Only activates under material lag (≥ 100 minutes behind)
- Does not interfere with normal variance

### 5.5 Why thresholds are conservative

- Entry at `lag <= -10` avoids triggering under normal variance
- Only activates after ~100+ minutes of delay
- Prevents overreaction in small networks
- Progressive cliffs match emergency severity

---

## 6. Measurement Phase (Critical)

Before implementing V5.1, the network must be observed under V4 rules.

### 6.1 Observation Window

**150–200 blocks** (approximately 24–32 hours at target 10 min/block)

### 6.2 Metrics to collect

| Metric | Definition |
|---|---|
| `overshoot_events` | Count of (profile ≥ H6) AND (subsequent lag ≤ -3) AND (block_time ≥ 20 min) |
| `time_in_H12` | Seconds accumulated with profile == 12 |
| `blocks_over_20min` | Count of blocks with interval ≥ 20 min |
| `blocks_over_40min` | Count of blocks with interval ≥ 40 min |
| `lag_min` | Minimum lag reached in the window |
| `lag_max` | Maximum lag reached in the window |
| `ahead_guard_activations` | Count of blocks where schedule_lag ≥ 16 |
| `chain_time_lost` | Sum of (block_interval - target) for blocks > target |

### 6.3 Overshoot Definition

```
overshoot_event = (max(profile[t-5..t]) >= 6)
                  AND (lag[t] <= -3)
                  AND (block_time[t] >= 20 minutes)
```

### 6.4 Decision Criteria

| Condition | Action |
|---|---|
| Ahead Guard divergence observed between nodes | **Immediate V5.0** — activate at next available fork height |
| `overshoot_events >= 2` per 200 blocks | **V5.1 justified** — fork after V5.0 |
| `blocks_over_40min >= 3` per 200 blocks | **V5.1 justified** — fork after V5.0 |
| `time_in_H12 >= 2 hours` per 200 blocks | **V5.1 borderline** — measure another 200 before deciding |
| None of the above | **Defer V5.1** — V5.0 ships alone |

---

## 7. Deployment Strategy

### V5.0

- **Mandatory**
- **Minimal scope** (only Ahead Guard statelessness)
- **Activated with advance notice** (minimum 200 blocks margin from announcement)
- **Fork height TBD** pending observation window

### V5.1

- **Conditional** — only activated if measurement phase data justifies it
- Deployed either:
  - Combined with V5.0 at same fork height (if data available in time)
  - Separately at a later fork height (if more observation needed)

### Communication plan

1. **ANN post** on BitcoinTalk with "No immediate action required" framing
2. **Explorer banner** (informational, green, not red panic) with countdown to activation
3. **GitHub issue** for technical tracking
4. **Activation notice** published minimum 48h before fork height

---

## 8. Guiding Principle

> **"Do not modify a control system twice in succession without measuring the response of the first change. But a determinism bug is fixed as soon as it is discovered, without waiting."**

Translation:
- V5.1 (feature enhancement) waits for data
- V5.0 (determinism fix) proceeds as soon as the patch is ready and reviewed

---

## 9. Conclusion

- ConvergenceX and cASERT architecture remain fundamentally sound
- V5.0 ensures correctness and determinism in the existing Ahead Guard
- V5.1 remains a controlled, data-driven improvement path
- The system is evolving through:

  **observation → validation → correction → stabilization**

This is expected for a protocol of this complexity in its pre-launch phase.

---

## 10. Status

| Component | Status |
|---|---|
| V5.0 design | Ready for implementation |
| V5.0 code | Not yet written |
| V5.1 design | Ready (conditional) |
| V5.1 code | Not yet written |
| Measurement monitor | To be activated |
| ANN (public) | Draft ready |
| Explorer banner | Pending update |
| GitHub issue | Pending creation |

---

## 11. References

- Commit `8c8d8bb` — V4 Ahead Guard introduction (contains `static bool` issue)
- Commit `e7625d5` — V4 slew-rate fallback elimination
- Commit `66c8629` — V4 compat patch (profile_index optional 4100-4169)
- `src/pow/casert.cpp` — main equalizer and bitsQ logic
- `include/sost/params.h` — consensus parameters
- `scripts/v31_monitor.py` — observation tooling (to be upgraded)

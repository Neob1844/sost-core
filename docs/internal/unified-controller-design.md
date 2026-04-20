# Unified Difficulty Controller — Design Memo

**Status**: Design phase — NOT for implementation yet.
**Target**: Block 10,000 fork (or later, pending validation).
**Author**: NeoB
**Date**: 2026-04-20

---

## 1. Problem statement

The current system uses two independent difficulty controllers:

- **bitsQ**: numeric difficulty (hash must be below target). Controlled by exponential adjustment with half-life and delta cap.
- **Equalizer**: structural difficulty (solution must pass stability basin test). Controlled by PID with 5 signals, 40 profiles.

These two controllers operate in parallel, each reacting to chain timing signals independently. Production data from blocks 5,000–5,155 has shown that this creates coordination problems:

1. **Burst desynchronization**: When hashrate surges, the equalizer climbs to H10 while bitsQ reacts slowly. The equalizer does all the braking, bitsQ barely moves.
2. **Stall amplification**: During a stall at H10, bitsQ doesn't know the equalizer is already braking. bitsQ keeps rising (because the anchor-based formula sees the chain is ahead), making the stall worse.
3. **Recovery overshoot**: After a stall, bitsQ is too high. When the equalizer drops (via anti-stall or lag cap), blocks become too slow because bitsQ is still elevated.
4. **Oscillation**: The chain oscillates between H9 (fast blocks, 6–24s) and H10 (slow blocks, 10–45min) because the two controllers settle at different equilibria.

## 2. Proposed solution: Unified Controller

Replace both controllers with a single computation that outputs the coordinated pair (bitsQ, profile) based on observed chain data.

### Core principle

Instead of two blind controllers, one informed calculator:

```
Input:  last N blocks { timestamp, interval, hashrate_est, bitsQ, profile, stability_observed }
Output: (optimal_bitsQ, optimal_profile) such that E[block_time] ≈ 600s
```

### How it works

1. **Estimate effective hashrate** from recent blocks:
   ```
   hashrate_eff = Σ(nonces) / Σ(intervals)
   ```
   This is noisy per-block but stable over 10–20 blocks.

2. **Estimate stability pass rate** per profile from recent data:
   ```
   stability[H] = stable_nonces[H] / total_nonces[H]
   ```
   This uses ACTUAL production data, not theoretical estimates.

3. **Compute target difficulty** for 600s blocks:
   ```
   For a given profile H with stability S[H]:
     E[dt] = (2^bitsQ) / (hashrate_eff × S[H] × C_calibration)
   
   We want E[dt] = 600, so:
     bitsQ_optimal = log2(600 × hashrate_eff × S[H] × C_cal)
   ```

4. **Select optimal profile** that minimizes variance:
   - Lower profiles (B0–H5) have high stability but less ASIC resistance
   - Higher profiles (H8–H10) have low stability but strong ASIC resistance
   - The optimal profile is the highest one where E[dt] ≈ 600s is achievable with reasonable bitsQ

5. **Apply smoothing and safety**:
   - Don't jump to the optimal instantly — use an EWMA or slew to transition
   - Safety rules: never harden when behind schedule
   - Anti-stall as pure last resort (should almost never activate)

### What changes

| Current | Unified |
|---------|---------|
| bitsQ computed from anchor + exponential | bitsQ computed from observed hashrate + target profile |
| Profile computed by PID with 5 signals | Profile selected to maximize ASIC resistance while keeping E[dt] ≈ 600s |
| Two controllers, no coordination | One controller, coordinated output |
| Lag-based reactive | Data-based predictive |

### What stays the same

- ConvergenceX proof of work (scratchpad, gradient, stability basin)
- Profile parameters (scale, k, steps, margin)
- Block structure, validation, consensus rules
- Anti-stall as safety net
- Miner lag-adjust (still useful for real-time adaptation)

## 3. Data requirements

To design and validate this controller, the following production data must be collected per block:

### Per-block data (block_samples)
- height
- timestamp
- interval (seconds since previous block)
- bitsQ (raw and float)
- profile_index
- profile_name
- stability_observed (% of nonces that passed stability in that profile)
- nonce (total attempts)
- hashrate_estimated (nonces / interval)
- miner_address
- lag_at_block

### Rolling aggregates (computed from last N blocks)
- hashrate_eff_20 (last 20 blocks)
- hashrate_eff_50 (last 50 blocks)
- stability_by_profile (map: profile → observed pass rate)
- mean_interval_20
- mean_interval_50
- bitsQ_trend (rising/falling/stable)
- profile_distribution (time in each profile)

### Events
- Burst events (3+ fast blocks in a row)
- Stall events (block > 20min)
- Hashrate changes (estimated hashrate changes > 20%)
- Profile transitions

## 4. Collection plan

A dedicated collector script runs continuously on the VPS, recording:

1. **data/unified_controller/block_data.jsonl** — one entry per block with all fields above
2. **data/unified_controller/rolling_stats.jsonl** — rolling aggregates every 10 blocks
3. **data/unified_controller/events.jsonl** — detected events

Target: collect 1,000+ blocks of data (about 7 days at 10min/block).

## 5. Validation approach

Once data is collected:

1. **Replay**: feed historical blocks into the unified controller and compare its (bitsQ, profile) output against what actually happened.
2. **Measure**: would the unified controller have prevented the observed stalls? The H9↔H10 oscillation? The bitsQ overshoot at block 5150?
3. **Simulate**: run Monte Carlo with the unified controller under burst/stall/volatile scenarios.

## 6. Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Hashrate estimation is noisy | Use 20–50 block window, EWMA smoothing |
| Stability estimates need many samples | Bootstrap from known profile parameters, refine with production data |
| Single controller = single point of failure | Keep anti-stall as independent safety net |
| Radical consensus change | Extensive replay + simulation before activation |
| Miners with very different hardware | The controller targets network-wide E[dt], not individual miners |

## 7. Timeline

- **Now → Block 10,000**: Collect data, design, validate
- **Block 10,000**: Activate if validation passes
- **Fallback**: If validation fails, keep current system with V6++ tuning

## 8. Relationship to Mode Arbiter

The Mode Arbiter (4 modes: NORMAL/BURST/STALL/RECOVERY) was proposed as an intermediate step. The Unified Controller subsumes it — if the controller is good enough, there are no "modes" because the system always knows the right (bitsQ, profile) pair. The Mode Arbiter becomes unnecessary.

However, if the Unified Controller proves too complex or unreliable, the Mode Arbiter remains a viable fallback architecture.

---

*This is the direction. Collect the data first, validate second, implement last.*

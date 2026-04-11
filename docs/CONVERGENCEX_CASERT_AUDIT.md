# ConvergenceX + cASERT — Reliability Audit

**Date:** 2026-03-24
**Chain data:** 1,252 blocks (8.9 days since genesis 2026-03-15)
**Status:** Read-only audit — no code modifications

---

## Executive Summary

ConvergenceX and cASERT are working correctly. The chain is producing blocks at the target 10-minute mean in the mature phase. The system handled a difficult bootstrap (single-miner, 346,915s first block gap) and converged to stable operation.

**ConvergenceX:** Solid memory-hard PoW. 8GB RAM per attempt (4GB dataset + 4GB scratchpad), 100K sequential rounds, pseudo-random state-dependent memory access. ASIC resistance is strong but not absolute — estimated low single-digit multiplier advantage for custom hardware, vs 1000x+ for SHA-256 ASICs. Transcript V2 verification is sound (11-phase, sampling-based, ~500MB node RAM).

**cASERT:** The per-block exponential adjustment with 24h halflife (V2), 12.5% delta cap (V2), and ±1 profile slew rate works well for steady-state operation. Anti-stall activated twice in real chain data and recovered correctly. Note: This audit was originally run against V1 parameters (48h/6.25%). V2 (activated at block 1,450) doubled responsiveness.

**Verdict:** LEAVE CORE ALGORITHM AS IS. Two parameter-level items worth monitoring. No ML/learning recommendation — determinism risk outweighs marginal benefit.

---

## 1. ConvergenceX PoW Audit

### 1.1 Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Dataset size | 4 GB (512M uint64_t) | params.h |
| Scratchpad size | 4 GB (1,073,741,824 words × 4B) | params.h |
| Total mining RAM | ~8 GB per thread | Confirmed |
| Rounds per attempt | 100,000 (mainnet) | params.h |
| Solution vector | 32 × int32 (128 bytes) | params.h |
| Matrix dimension | 32×32 | convergencex.cpp |
| Regularization λ | 100 | convergencex.cpp |
| Learning rate shift | 18 (lr = 2^-18) | convergencex.cpp |
| Scratchpad reads/round | 4 (pseudo-random indices) | convergencex.cpp |
| Total scratchpad reads | 400,000 per attempt | Derived |
| Node verification RAM | ~500 MB (no dataset/scratchpad) | Design |
| Benchmark hashrate | ~5.5 att/s (single core) | params.h calibration |

### 1.2 Sequential Dependency Chain

Each round r → r+1 has TRUE sequential dependency:

```
state[r] = SHA256(state[r-1] || m0..m3 || x[j0..j3] || r)
```

Round r+1 cannot begin until state[r] is computed because:
1. state[r] determines scratchpad read indices for round r+1 (via w0, w1 extraction)
2. state[r] feeds the SHA256 input for state[r+1]
3. x[r] (solution vector) evolves via gradient step that depends on scratchpad values read using state[r]-derived indices

**Parallelism:**
- Intra-attempt: **ZERO** (verified — each round strictly depends on prior)
- Inter-attempt: Multiple cores run independent nonce attempts (natural CPU advantage)

### 1.3 ASIC Resistance Analysis

| Property | Assessment | Rating |
|----------|-----------|--------|
| Sequential rounds | True sequential chain (SHA256) | Strong |
| Memory requirement | 8GB working set | Strong |
| Access pattern | Pseudo-random, state-dependent | Strong |
| Per-block program | 256 operations from block hash | Moderate |
| Cache utility | Dataset > L3 cache → no shortcut | Strong |
| TMTO resistance | Need all 100K states OR sequential compute | Strong |

**Comparison with other memory-hard algorithms:**

| Algorithm | Memory | Sequential | Access Pattern | ASIC Multiplier |
|-----------|--------|-----------|----------------|-----------------|
| **ConvergenceX** | 8 GB | 100K rounds | Pseudo-random | ~2-5x (est.) |
| RandomX (Monero) | 256 MB | VM execution | Random | ~2-3x |
| Ethash (ETH classic) | 4 GB DAG | Sequential | Pseudo-random | ~5-10x |
| Equihash (Zcash) | 700 MB | Wagner | Sequential | ~3-5x |
| Argon2id (passwords) | Configurable | Configurable | Mixed | ~1-2x |
| SHA-256 (Bitcoin) | ~0 | None | Sequential | 1000x+ |

**Honest assessment:** ConvergenceX's ASIC resistance is comparable to RandomX. The 8GB requirement raises the bar significantly. A dedicated ASIC could potentially gain 2-5x by optimizing the SHA256 pipeline and memory controller, but the sequential dependency prevents the massive parallelism that makes SHA-256 ASICs 1000x+ faster. The per-block program generation adds further resistance.

**Potential weakness:** The gradient descent operations themselves (integer multiply, add, shift) are simple. An ASIC could execute these faster than a general-purpose CPU. However, the bottleneck is SHA256(state) between rounds, not the arithmetic. SHA-256 ASICs are well-understood, but the sequential dependency means they can only speed up one round at a time, not pipeline thousands.

### 1.4 Transcript V2 Verification

**11-phase verification is sound:**

| Phase | Validates | Attack Blocked |
|-------|-----------|---------------|
| 1. Sanity | x_bytes length = n×4 | Malformed proofs |
| 2. Checkpoint Merkle | Checkpoint tree integrity | Fake checkpoint states |
| 3. Segment Merkle | Segment proof paths validate | Segment forgery |
| 4. Seed Recompute | Deterministic seed from nonce | Seed manipulation |
| 5. Commit Binding | Commit = H(state, x, metric, profile) | Commit tampering |
| 6. Challenge Derivation | Deterministic challenge from commit | Challenge manipulation |
| 7. Boundary Coherence | start ≤ end ≤ total_rounds | Out-of-bounds witnesses |
| 8. Round Witnesses | Full round recomputation (12 rounds) | Fake computation |
| 9. Stability Basin | x_final in attractor basin | Saddle point mining |
| 10. Metric Match | Computed metric = provided | Metric forgery |
| 11. Target | commit ≤ target | Difficulty bypass |

**Security of sampling approach:**
- 6 segments × 2 rounds = 12 round witnesses verified per block
- Out of 100,000 total rounds → 0.012% sampled
- Challenge is deterministic from commit (unbiasable — miner cannot choose which rounds are checked)
- Probability of faking k rounds and not being caught: (1 - 12/100000)^k ≈ e^(-0.00012k)
  - Fake 1000 rounds: ~88% chance of getting caught
  - Fake 10000 rounds: ~70% chance
  - Fake all 100000: effectively impossible without doing the work
- **Conclusion:** Sampling security is adequate for current network size. If network grows significantly, increasing CX_CHAL_SEGMENTS would strengthen it further.

**Node RAM:** ~500MB verified. Scratchpad and dataset values are recomputed on-demand via:
- `compute_single_scratch_block()` — O(1) per block (SHA256)
- `compute_single_dataset_value()` — O(1) per value (SplitMix64)

### 1.5 Benchmark

| Metric | Value |
|--------|-------|
| Calibrated hashrate | 5.5 att/s (params.h) |
| Genesis bitsQ | 765,730 (11.68 in Q16.16) |
| Expected block time at genesis | ~600s with 1 miner |
| Observed mean (mature chain) | 598s (last 500 blocks) |
| Alignment | Excellent (0.3% error) |

---

## 2. cASERT Difficulty Adjustment Audit

### 2.1 Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| Half-life | 86,400s (24h) — V2 | Time to double/halve difficulty (V1 was 48h) |
| Per-block delta cap | 12.5% (1/8) — V2 | Prevent oscillation (V1 was 6.25%) |
| Epoch length | 131,553 blocks | Anchor reset |
| Active profiles | E4 to H9 (14 levels) | Stability difficulty band |
| Reserved profiles | H10-H12 (3 levels) | Future headroom |
| Slew rate | ±1 level/block | Profile change damping |
| Anti-stall floor | 7,200s (2h) | Minimum stall detection |
| Anti-stall easing | 21,600s (6h at B0) | Emergency easing trigger |
| Future timestamp drift | 600s (10min) | Time manipulation limit |
| MTP window | 11 blocks | Past-time manipulation limit |
| dt clamp | [1, 86400]s | Outlier handling |

### 2.2 Real Chain Performance (1,252 blocks)

#### Block Time Statistics
| Metric | Value | Assessment |
|--------|-------|-----------|
| Mean | 611.9s (10.2 min) | Near-target (2% over) |
| Median | 87s (1.4 min) | Skewed by early fast blocks |
| Stdev | 9,848s | Inflated by 346,915s block 1 gap |
| Min | 29s | Normal for exponential distribution |
| Max | 346,915s (4 days) | Block 1 — genesis bootstrap |
| CV (coeff. of variation) | 16.1 | Far from ideal 1.0 — dominated by bootstrap |

#### Mature Chain (last 500 blocks)
| Metric | Value | Assessment |
|--------|-------|-----------|
| Mean | 598s | Excellent — within 0.3% of target |
| Stdev | 630s | Reasonable for exponential distribution |
| CV | 1.05 | Near-ideal for Poisson process |

#### Block Time Distribution
| Range | Count | Percentage |
|-------|-------|-----------|
| < 2 min | 689 | 55.1% |
| 2-10 min | 348 | 27.8% |
| 10-30 min | 183 | 14.6% |
| 30-60 min | 27 | 2.2% |
| 1-2 hours | 2 | 0.2% |
| > 2 hours | 2 | 0.2% |

The 55% of blocks under 2 minutes is consistent with an exponential distribution at λ=1/600 (expected: ~18% under 2 min). This elevated proportion reflects the early chain bootstrap where difficulty was still converging down from genesis.

#### Difficulty History
| Phase | bitsQ Range | Assessment |
|-------|-------------|-----------|
| Genesis | 765,730 (11.68) | Starting point |
| Early drop | → 199,249 (3.04) at block 22 | Correct — single miner needs lower difficulty |
| Recovery | → 776,385 (11.85) at block 1007 | Converged back to genesis-level |
| Current | 717,188 (10.94) | Stable near genesis |

#### Profile Distribution
| Profile | Blocks | Percentage | Meaning |
|---------|--------|-----------|---------|
| B0 (baseline) | 1,074 | 85.8% | Normal operation |
| E1 (easy 1) | 138 | 11.0% | Slight easing |
| H1 (hard 1) | 25 | 2.0% | Slight hardening |
| H2 (hard 2) | 13 | 1.0% | Moderate hardening |
| E4 (emergency) | 1 | 0.1% | Bootstrap emergency |

**Profile transitions:** 234 total. Most are B0↔E1 oscillations in the recent chain (blocks 600+). This is expected behavior: the control signal oscillates around the B0/E1 boundary when the chain is slightly behind schedule.

#### Anti-Stall
- Activated twice (blocks with gaps > 2 hours)
- Both in early chain bootstrap
- Recovered correctly — chain resumed normal operation

### 2.3 Theoretical Consistency

With 1 miner at 5.5 att/s:
- Expected difficulty: ~GENESIS_BITSQ (calibrated at genesis)
- Observed: 717,188 (93.7% of genesis) — consistent, slightly below because miner may run slightly faster than calibration

**Convergence time after hashrate change (simulation):**

| Scenario | Adjustment Blocks | Assessment |
|----------|-------------------|-----------|
| Constant (baseline) | 50 | Good |
| Hashrate ×2 | Not converged in 400 | **Slow** — 6.25% cap limits adjustment |
| Hashrate /2 | ~50 | Adequate |
| Oscillating (×2/÷2) | 57 | Tracks reasonably |
| Flash (100× for 10 blocks) | 50 | Good recovery |
| Selfish pattern | 57 | Reasonable |

### 2.4 Problem Detection

#### Issue 1: Slow Upward Adjustment (6.25% Cap)
When hashrate doubles, the 6.25% per-block cap means it takes:
- `log(2) / log(1.0625) ≈ 11.4 blocks` minimum to double difficulty
- But the cASERT formula also has exponential smoothing with 48h halflife
- Combined effect: **hundreds of blocks to fully converge after 2x hashrate increase**
- In simulation: scenario 2 never fully converged in 400 blocks

**Risk:** If a large miner joins, block times will be too fast for an extended period. With current single-miner network, this is low risk. If SOST grows to multiple miners, this could cause extended periods of fast blocks.

**Mitigation already in place:** The 48h halflife means the cASERT bitsQ formula itself adjusts exponentially, and the cap just limits the per-block rate. Over time it converges.

#### Issue 2: B0/E1 Profile Oscillation
234 profile transitions in 1,252 blocks means a transition every ~5.3 blocks on average. Most are B0↔E1 ping-pong in the recent chain. This is cosmetic — both profiles are very similar (B0: margin=185, E1: margin=205). The oscillation doesn't affect mining or security.

**Root cause:** The control signal U oscillates around the B0/E1 boundary. The lag-based safety rule (`if lag ≤ 0: H = min(H, 0)`) causes the profile to flip between B0 and E1 as the chain alternates between slightly ahead and slightly behind schedule.

#### Issue 3: No Time Warp Vulnerability
- Future timestamps limited to +600s (10 min)
- Past timestamps limited by MTP (median of last 11 blocks)
- Combined with per-block delta cap: manipulating timestamps to game difficulty requires sustained control over many blocks
- **Not vulnerable** to classic time warp attacks

#### Issue 4: Selfish Mining
Simulation scenario 6 shows selfish mining pattern produces 641s mean block time (7% above target) with higher variance. The cASERT responds correctly by adjusting difficulty. Selfish mining does not break the difficulty algorithm, though it can cause temporary instability in block times.

---

## 3. Margin of Improvement

### 3.1 ConvergenceX

| Aspect | Current | Mejorable? | Risk | Priority |
|--------|---------|------------|------|----------|
| RAM 8GB | Correct | No — good balance | Reducing → less ASIC resistant | None |
| 100K rounds | Correct | Could reduce to 50K | Faster mining, weaker sequential guarantee | Low |
| ASIC resistance | Strong (2-5x est.) | Hard to improve without fundamentally changing algorithm | — | Monitor |
| Transcript V2 | Sound (12 rounds sampled) | Could increase to 24 for stronger guarantees | Larger proofs | Low |
| Time per attempt | ~180ms at 5.5 att/s | Adequate | — | None |
| Per-block program | 256 operations, 8 opcodes | Could add more opcodes | More complexity | None |

### 3.2 cASERT

| Aspect | Current | Mejorable? | Risk | Priority |
|--------|---------|------------|------|----------|
| Target 600s | Yes (598s mature) | No change needed | — | None |
| Halflife 48h | Adequate | Could reduce to 24h for faster response | More oscillation | **Monitor** |
| 6.25% delta cap | Conservative | Could relax to 12.5% (1/8) | More oscillation | **Monitor** |
| 17 profiles | Adequate (14 active) | No change needed | — | None |
| Anti-stall | Works (activated 2x) | Adequate | — | None |
| Slew rate ±1 | Correct | No change needed | — | None |
| B0/E1 oscillation | Cosmetic | Could add hysteresis | Complexity | Low |

**Key recommendation:** The 6.25% delta cap + 48h halflife combination makes upward adjustment slow when hashrate increases suddenly. If SOST grows to multi-miner operation, consider:
1. Reducing halflife to 24h (faster response, consensus change)
2. Relaxing delta cap to 12.5% (faster per-block adjustment, consensus change)
3. Either change would require careful simulation before deployment

**For now:** With single-miner operation, the current parameters are well-calibrated. No change needed until network grows.

---

## 4. ML/Learning Evaluation

### 4.1 ML-Enhanced Difficulty (REJECTED)

**Concept:** Replace fixed formula with ML model that learns from chain history.

**Fundamental problem:** Difficulty adjustment is **consensus-critical**. Every node must compute EXACTLY the same next difficulty value. ML models are:
- Non-deterministic across hardware (floating-point rounding differences)
- Version-sensitive (model updates = hard fork)
- Opaque (harder to audit, harder to reason about attacks)

**No blockchain uses ML for difficulty adjustment.** Bitcoin, Ethereum, Monero, Zcash — all use deterministic formulas. This is not an accident.

**Verdict: REJECTED.** The risk of consensus divergence far outweighs any marginal improvement in block time variance.

### 4.2 Adaptive Parameters (CAUTIOUS)

**Concept:** Parameters (halflife, delta cap) auto-adjust based on chain state.

**Example:** If block time variance is high for 100+ blocks → reduce halflife temporarily.

**Analysis:**
- This is deterministic and reproducible (all nodes see same chain history)
- Similar to what the profile system already does (adjust stability difficulty)
- Could improve responsiveness without the risks of ML

**Risks:**
- More complex control logic → harder to audit
- Potential for oscillation if adaptation rules interact poorly
- Each adaptive rule is a consensus change

**Verdict: VIABLE but not needed yet.** The current profile system already provides adaptive behavior via the equalizer. Adding adaptive halflife/cap is over-engineering for a single-miner network.

### 4.3 Predictive Difficulty (REJECTED)

**Concept:** Use hashrate trend to anticipate changes.

**Problem:** Miners can game this. If the algorithm looks at the last 50 blocks to predict future hashrate, a miner can mine 50 easy blocks then stop, causing the algorithm to predict high hashrate and raise difficulty, freezing the chain for legitimate miners.

**Verdict: REJECTED.** Introduces a new manipulation vector. The cASERT formula's reactive approach is safer — it adjusts based on what happened, not what might happen.

### 4.4 Comparison with Other Projects

| Project | Difficulty Adjustment | ML Used? | Notes |
|---------|----------------------|----------|-------|
| Bitcoin | Fixed retarget every 2016 blocks | No | Simple, proven, slow response |
| Bitcoin Cash | Exponential per-block retarget | No | Closest to SOST's cASERT approach |
| Monero | Moving average, per-block | No | More reactive, some oscillation |
| Ethereum (pre-merge) | Bomb + adjustment | No | Complex but no ML |
| Zcash | Digishield variant | No | Per-block, momentum-based |
| **Any known project** | — | **No** | No production blockchain uses ML for difficulty |

**Academic papers:** A few papers explore ML-based difficulty prediction (e.g., "Machine Learning-Based Bitcoin Difficulty Prediction" — IEEE 2019), but these are for PREDICTION (off-chain forecasting), not for ON-CHAIN consensus. No paper proposes replacing the consensus difficulty formula with ML.

### 4.5 Recommendation

| Idea | Verdict | Reasoning |
|------|---------|-----------|
| ML-enhanced difficulty | **REJECT** | Non-determinism → consensus divergence |
| Adaptive parameters | **DEFER** | Viable but over-engineering for current network |
| Predictive difficulty | **REJECT** | Introduces manipulation vector |
| Current approach | **KEEP** | Working correctly, well-calibrated |

---

## 5. Simulation Results

### 5.1 Scenario Summary

| Scenario | Mean BT | Last 100 BT | % Fast (<2m) | % Slow (>30m) | Converge |
|----------|---------|-------------|-------------|---------------|----------|
| 1: Constant (5.5 att/s) | 607s | 676s | 20.4% | 5.8% | Block 50 |
| 2: Hashrate ×2 | 398s | 355s | 28.9% | 1.4% | Not converged |
| 3: Hashrate /2 | 864s | 784s | 14.4% | 12.0% | Block 50 |
| 4: Oscillating (×2/÷2) | 695s | 597s | 22.8% | 10.6% | Block 57 |
| 5: Flash (100× for 10 blocks) | 586s | 631s | 20.2% | 5.2% | Block 50 |
| 6: Selfish pattern | 641s | 673s | 31.3% | 9.0% | Block 57 |

### 5.2 Key Findings

**Scenario 1 (constant):** Perfect convergence. 607s mean is within 1.2% of target. This validates the genesis calibration.

**Scenario 2 (×2 hashrate):** The delta cap (6.25%) prevents rapid upward adjustment. After 400 blocks, mean block time is still 355s (41% below target). This is the primary weakness of the current configuration. However, the halflife-based exponential does eventually converge — it just takes much longer than the simulation window.

**Scenario 3 (÷2 hashrate):** Downward adjustment works faster because the cASERT bitsQ formula naturally reduces difficulty when blocks are slow. Last 100 blocks: 784s (30% above target) — still converging but functional.

**Scenario 5 (flash):** Excellent recovery. After 100× hashrate flash (10 blocks), post-flash mean is 679s and max is 2,532s. The delta cap prevents difficulty from spiking too high during the flash, and the cASERT bitsQ formula brings it back to equilibrium. This demonstrates robustness against temporary hashrate spikes.

**Scenario 6 (selfish):** Mean block time 641s (6.8% above target). The pattern of burst/pause creates moderate instability but the cASERT handles it without diverging.

---

## 6. CTO Recommendation

### Current State: HEALTHY

The ConvergenceX + cASERT system is operating correctly within its design parameters. The mature chain (last 500 blocks) shows:
- Mean block time 598s (0.3% from target)
- CV 1.05 (near-ideal exponential distribution)
- Difficulty converged to near-genesis level
- Profile stability: 85.8% B0, minimal easing/hardening
- Anti-stall activated and recovered correctly during bootstrap

### Action Items

| Priority | Item | Type | When |
|----------|------|------|------|
| **None** | Core algorithm | Keep as-is | — |
| **Monitor** | 6.25% delta cap + 48h halflife | Watch if multi-miner | Before 5+ miners |
| **Low** | B0/E1 oscillation | Cosmetic, add hysteresis if desired | Optional |
| **Low** | Transcript V2 sampling | Increase from 12 to 24 if network grows | Optional |
| **None** | ML/learning | Rejected — determinism risk | — |
| **None** | RAM/rounds | Keep 8GB/100K | — |

### What to Watch

1. **When a second miner joins:** Monitor if the 6.25% cap causes extended fast-block periods. If block times stay <300s for 100+ blocks, consider relaxing the cap (consensus change).

2. **When hashrate grows 10x:** The current profiles (E4-H12) cover a wide range. If hashrate grows beyond H9's capability, the reserved H10-H12 profiles exist but would need activation (consensus change).

3. **If an ASIC appears:** Monitor the stability ratio at different profiles. If stability tests become trivially easy (pass rate > 99.9%), the per-block program complexity may need increasing.

### What NOT to Do

- Do NOT add ML to the consensus difficulty formula
- Do NOT change the 100K rounds or 8GB requirement without extensive simulation
- Do NOT reduce the MTP window or future timestamp limit
- Do NOT remove the per-block delta cap (oscillation would be severe)

---

## cASERT V2 Fork (Block 1450)

Based on audit findings, a consensus upgrade was implemented:

| Parameter | V1 (blocks < 1450) | V2 (blocks >= 1450) |
|-----------|-------------------|-------------------|
| Halflife | 172,800s (48h) | 86,400s (24h) |
| Delta cap | 6.25% (1/16) | 12.5% (1/8) symmetric |
| Target spacing | 600s | 600s (unchanged) |
| Anti-stall | Unchanged | Unchanged |
| Profiles | Unchanged | Unchanged |

**Rationale:** Audit simulation showed hashrate doubling never converged in 400 blocks with V1 parameters. V2 doubles both response speed (halflife halved) and per-block adjustment rate (delta cap doubled). No regenesis — blocks 0-1449 validate with V1 rules.

---

## Appendix: Files Analyzed

| File | Purpose |
|------|---------|
| `include/sost/params.h` | All consensus constants |
| `include/sost/pow/convergencex.h` | ConvergenceX header |
| `src/pow/convergencex.cpp` | Full PoW + verification implementation |
| `src/pow/scratchpad.cpp` | Scratchpad generation/verification |
| `include/sost/pow/casert.h` | cASERT header |
| `src/pow/casert.cpp` | Full difficulty adjustment |
| `include/sost/sostcompact.h` | bitsQ encoding |
| `src/block_validation.cpp` | Timestamp validation |
| `src/sost-miner.cpp` | Mining loop |
| `build/chain.json` | Real chain data (1,252 blocks) |
| `scripts/analyze_casert_performance.py` | Chain analysis script |
| `scripts/simulate_casert.py` | Simulation script |

## Appendix: Graphs

See `docs/casert_audit/`:
- `casert_performance.png` — Real chain: block times, difficulty, profiles, distribution
- `casert_simulation.png` — 6 simulation scenarios
- `casert_analysis.json` — Chain statistics
- `casert_simulation.json` — Simulation results

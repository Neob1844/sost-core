# PoPC Reward Adjustment Proposal

**Date:** 2026-03-29
**Author:** NeoB (CTO)
**Status:** IMPLEMENTED (2026-03-29)
**Implementation:** Dynamic PUR system, Model B halved rates, anti-whale tiers, reservation mechanism

---

## 1. Current State

### Price Assumptions
- Gold: $10,000/oz (updated reference)
- SOST: $1.00
- ratio_bps = ($1 / $10,000) × 10,000 = **1 bps** → bracket `< 100` → **25% bond**

### Model A — Current Rewards (1 oz gold = $10,000, bond = 25% = $2,500 = 2,500 SOST)

| Duration | Reward Rate | Gross Reward | Net (after 5% fee) | APR on Bond | Pool Cost/year/participant |
|----------|-----------|-------------|--------------------|-----------|----|
| 1 month | 1% | 25.00 | 23.75 | 11.4% | 285.00 |
| 3 months | 4% | 100.00 | 95.00 | 15.2% | 380.00 |
| 6 months | 9% | 225.00 | 213.75 | 17.1% | 427.50 |
| 9 months | 15% | 375.00 | 356.25 | 19.0% | 475.00 |
| 12 months | 22% | 550.00 | 522.50 | 20.9% | 522.50 |

### Model B — Current Rewards (1 oz gold = $10,000, reward on gold value = 10,000 SOST equiv)

| Duration | Reward Rate | Gross Reward | Net (after 5% fee) | Pool Cost/year/participant |
|----------|-----------|-------------|--------------------|----|
| 1 month | 1% | 100.00 | 95.00 | 1,140.00 |
| 3 months | 4% | 400.00 | 380.00 | 1,520.00 |
| 6 months | 9% | 900.00 | 855.00 | 1,710.00 |
| 9 months | 15% | 1,500.00 | 1,425.00 | 1,900.00 |
| 12 months | 22% | 2,200.00 | 2,090.00 | 2,090.00 |

### Pool Income
- Year 1 (epoch 0): **~103,130 SOST/year**
- Year 3 (epoch 1): ~80,302 SOST/year
- Year 5 (epoch 2): ~62,531 SOST/year

### Max Participants per Year (12-month, 1 oz)
- **Model A:** 103,130 / 522.50 = **197**
- **Model B:** 103,130 / 2,090 = **49**
- **Ratio B cost / A cost = 4.0x** (unchanged from previous analysis)

---

## 2. Problems Identified

### Problem 1: Model B is 4x more expensive than Model A
Model B rewards are calculated on GOLD VALUE (10,000 SOST equiv at $10k gold) while Model A rewards are on BOND (2,500 SOST). Same percentages, 4x the base. At $10k gold this is even more extreme.

### Problem 2: Whale risk
A participant with 100 oz ($1M gold):
- Model A bond: 100 × 2,500 = 250,000 SOST (more than exists in circulation at launch)
- Model B reward (12mo): 100 × 2,090 = 209,000 SOST (drains pool 2x over in one year)

### Problem 3: No pool depletion protection
- Registration succeeds even if pool can't afford future rewards
- No reservation mechanism — "first come first served" by default
- Existing participants could lose promised rewards if pool drains

### Problem 4: No per-participant caps
- No maximum gold amount per participant
- No maximum reward per participant
- No tiered reward reduction for large positions

---

## 3. Proposed New Rewards — Model B

**Target:** Model B max participants ≈ 330 per year at 12 months (half of Model A's ~197... wait, with $10k gold Model A max is 197, so target for B is ~100).

Actually, recalculating with gold at $10,000:
- Model A max at 12mo: 103,130 / 522.50 = **197**
- Target Model B max at 12mo: ~100 (half of Model A)
- Required Model B cost per participant at 12mo: 103,130 / 100 = **1,031.30 SOST**

This means Model B net reward at 12mo should be ~1,031 SOST (instead of current 2,090).

**Proposed Model B rates (approximately 50% of current, applied to gold value):**

| Duration | Current Rate (bps) | Proposed Rate (bps) | Current Net Reward | Proposed Net Reward | Ratio B/A |
|----------|-------------------|--------------------|--------------------|--------------------|----|
| 1 month | 100 (1.0%) | 50 (0.5%) | 95.00 | 47.50 | 2.0x |
| 3 months | 400 (4.0%) | 200 (2.0%) | 380.00 | 190.00 | 2.0x |
| 6 months | 900 (9.0%) | 450 (4.5%) | 855.00 | 427.50 | 2.0x |
| 9 months | 1500 (15.0%) | 750 (7.5%) | 1,425.00 | 712.50 | 2.0x |
| 12 months | 2200 (22.0%) | 1100 (11.0%) | 2,090.00 | 1,045.00 | 2.0x |

**Result:** Model B reward is 2.0x Model A (instead of 4.0x). This is justified because:
- Model B user puts real gold in escrow (higher personal risk)
- Model B has no slash risk (no audits)
- 2x premium is fair for the added gold-custody commitment

**New max participants per year (12-month, 1 oz, $10k gold):**
- Model A: 103,130 / 522.50 = **197**
- Model B proposed: 103,130 / 1,045.00 = **99**
- Combined (if all Model A): 197
- Combined (if all Model B): 99
- Combined (50/50 mix): ~132

---

## 4. Anti-Whale Proposal

### Option A: Tiered Reward Reduction (RECOMMENDED)

| Gold Amount (oz) | Reward Multiplier | Effective Rate (12mo Model A) | Rationale |
|-----------------|-------------------|-------------------------------|-----------|
| 0-10 oz | 100% | 22% | Standard — accessible to individuals |
| 10-50 oz | 75% | 16.5% | Moderate holdings — slight reduction |
| 50-200 oz | 50% | 11% | Large — significant reduction |
| >200 oz | 25% | 5.5% | Whale — near-market rate only |

**Impact on 100 oz whale (Model A, 12 months):**
- Current: 100 × 522.50 = 52,250 SOST reward
- Tiered: (10 × 522.50) + (40 × 391.88) + (50 × 261.25) = 5,225 + 15,675 + 13,063 = **33,963 SOST** (35% reduction)

### Option B: Hard Cap per Participant

| Cap Type | Value | Rationale |
|----------|-------|-----------|
| Max gold per participant | 50 oz ($500,000) | Limits single-participant pool drain |
| Max reward per commitment | 10,000 SOST | Absolute ceiling regardless of gold amount |
| Max active bonds per address | 3 | Prevents position splitting |

### Option C: Combined (RECOMMENDED)
- Tiered reduction (Option A) for gradual discouragement
- Hard cap at 200 oz per address (Option B) as absolute ceiling
- Max 3 active commitments per SOST address

---

## 5. Pool Depletion Mechanism

### Proposed: Reservation + Warning System

**At Registration:**
1. Calculate projected pool balance at commitment end date:
   - Current pool balance + projected block income until end_height - sum of all reserved rewards
2. If projected balance >= reward: **RESERVE** the reward amount
   - Mark those SOST as "committed" — cannot be used for other rewards
   - Participant gets guarantee: "Your reward of XXX SOST is reserved"
3. If projected balance < reward but > 50%: **WARN + PARTIAL RESERVE**
   - "WARNING: Pool can only guarantee XX% of your reward. Full reward subject to pool availability."
   - Reserve what's available, rest is best-effort
4. If projected balance < 50% of reward: **WARN + NO RESERVE**
   - "WARNING: Pool balance is low. Your reward is not guaranteed."
   - Participant can still register (bond is still valuable for custody proof)
5. If projected balance <= 0: **SOFT BLOCK**
   - "Pool is fully committed. New registrations will be queued."
   - Create wait list, process as pool refills

**At Completion (Release):**
1. Check reserved amount
2. Pay reserved amount in full (guaranteed)
3. If additional unreserved amount is available, pay it too
4. If pool has less than owed: pay what's available, log shortfall
5. NEVER fail to return the bond — only reward is at risk

**Existing Participants Always Have Priority:**
- Reserved rewards are immutable once committed
- New registrations can only use unreserved pool balance
- This is FIFO + reservation, not "last one loses"

---

## 6. Three Reward Scenarios

### Scenario CONSERVADOR (50% of current)

| Duration | Model A Rate | Model B Rate | Model A APR | Model B APR |
|----------|-------------|-------------|-------------|-------------|
| 1 month | 0.5% | 0.25% | 5.7% | 5.7% on gold value |
| 3 months | 2.0% | 1.0% | 7.6% | 7.6% |
| 6 months | 4.5% | 2.25% | 8.6% | 8.6% |
| 9 months | 7.5% | 3.75% | 9.5% | 9.5% |
| 12 months | 11.0% | 5.5% | 10.5% | 10.5% |

Max participants/year (12mo, 1 oz, $10k gold):
- Model A: 103,130 / 261.25 = **395**
- Model B: 103,130 / 522.50 = **197**

Verdict: Competitive with Ethereum staking (3-5%) while being higher to compensate for experimental risk. Sustainable for 3+ years even with moderate adoption.

### Scenario MODERADO (75% of current) — RECOMMENDED

| Duration | Model A Rate | Model B Rate | Model A APR | Model B APR |
|----------|-------------|-------------|-------------|-------------|
| 1 month | 0.75% | 0.375% | 8.6% | 8.6% on gold value |
| 3 months | 3.0% | 1.5% | 11.4% | 11.4% |
| 6 months | 6.75% | 3.375% | 12.8% | 12.8% |
| 9 months | 11.25% | 5.625% | 14.3% | 14.3% |
| 12 months | 16.5% | 8.25% | 15.7% | 15.7% |

Max participants/year (12mo, 1 oz, $10k gold):
- Model A: 103,130 / 391.88 = **263**
- Model B: 103,130 / 783.75 = **132**

Verdict: Higher than DeFi (5-15% APR) to attract early adopters. Sustainable for 2+ years. Attractive but not reckless.

### Scenario ACTUAL (100% — no change)

| Duration | Model A Rate | Model B Rate | Model A APR | Model B APR |
|----------|-------------|-------------|-------------|-------------|
| 1 month | 1% | 0.5% (proposed) | 11.4% | 11.4% on gold value |
| 3 months | 4% | 2% (proposed) | 15.2% | 15.2% |
| 6 months | 9% | 4.5% (proposed) | 17.1% | 17.1% |
| 9 months | 15% | 7.5% (proposed) | 19.0% | 19.0% |
| 12 months | 22% | 11% (proposed) | 20.9% | 20.9% |

Max participants/year (12mo, 1 oz, $10k gold):
- Model A: **197**
- Model B: **99** (with proposed 50% reduction)

Verdict: Aggressive APR. Attracts early adopters. Sustainable only with <200 participants at 12 months. Riskier as adoption grows.

---

## 7. Comparison Table

| Metric | Conservador | Moderado | Actual (with B fix) |
|--------|------------|---------|-------------------|
| Model A APR (12mo) | 10.5% | 15.7% | 20.9% |
| Model B APR (12mo) | 10.5% | 15.7% | 20.9% |
| Model A max/year | 395 | 263 | 197 |
| Model B max/year | 197 | 132 | 99 |
| Mixed (50/50) max | ~264 | ~176 | ~132 |
| Sustainability epoch 0 | 3+ years | 2+ years | 1-2 years |
| Sustainability epoch 1 | 2+ years | 1-2 years | <1 year if full |
| Competitive vs ETH staking | Above (2x) | Well above (3x) | Very above (4-5x) |
| Competitive vs DeFi | Comparable | Above | Well above |
| Attractiveness | Moderate | High | Very high |
| Risk of pool drain | Low | Medium | High |

---

## 8. CTO Recommendation

### RECOMMENDED: Scenario ACTUAL with Model B fix + Anti-Whale + Reservation

**Rationale:**
1. **Keep Model A rates at current levels** (11-22% APR) — aggressive but justified for first-mover protocol. Early participants take real risk; high rewards compensate.

2. **Fix Model B: halve the rates** (proposed rates: 50, 200, 450, 750, 1100 bps). This makes Model B 2x Model A reward (justified by gold escrow commitment), not 4x.

3. **Implement anti-whale tiers:**
   - 0-10 oz: 100% reward
   - 10-50 oz: 75%
   - 50-200 oz: 50%
   - >200 oz: hard cap (no registration above 200 oz per address)

4. **Implement reservation:** Reserve rewards at registration. Warn + partial reserve if pool is low. Soft block if pool is fully committed.

5. **Review at epoch 1** (block 131,553, ~2.5 years): If participation is high, consider moving to Moderado scenario (75% rates).

**Why not Conservador?** SOST is a new, experimental protocol. 5-10% APR is barely competitive with established protocols. Early adopters need stronger incentive. We can always reduce later (operational, not consensus).

**Why not keep Model B unchanged?** 4x pool drain per participant is a design flaw, not a feature. Fixing to 2x is the minimum viable correction.

---

## 9. Impact on Code (If Approved)

| File | Change | Effort |
|------|--------|--------|
| `include/sost/popc.h` | No change (Model A rates stay) | — |
| `include/sost/popc_model_b.h` | Add `ESCROW_REWARD_RATES[]` constant array | 5 min |
| `src/popc_model_b.cpp` | Use `ESCROW_REWARD_RATES` instead of `POPC_REWARD_RATES` | 10 min |
| `src/popc.cpp` | Add anti-whale tier function `apply_whale_tier(gold_mg, reward)` | 30 min |
| `src/sost-node.cpp` | Add pool reservation logic to `handle_popc_register` and `handle_escrow_register` | 1 hour |
| `src/sost-node.cpp` | Add projected pool balance calculation | 30 min |
| `tests/test_escrow.cpp` | Update expected reward values for new rates | 15 min |
| `tests/test_popc.cpp` | Add whale tier tests | 30 min |
| `docs/POPC_DEPLOY_GUIDE.md` | Update reward tables | 15 min |
| `docs/POPC_ECONOMIC_ANALYSIS.md` | Update with new analysis | 30 min |

**Total estimated effort: ~4 hours**

---

## Appendix: Market Comparison

| Protocol / Product | APR | Risk Profile | Notes |
|-------------------|-----|-------------|-------|
| Ethereum staking (Lido) | 3.0-3.5% | Low | Established, liquid |
| Aave/Compound lending | 2-8% | Medium | DeFi, smart contract risk |
| Curve/Convex farming | 5-20% | High | Impermanent loss, complexity |
| Tether Gold (XAUT) holding | 0% | Low | No yield, just custody |
| SOST Model A (current) | 11-22% | Medium-High | Experimental, bond at risk |
| SOST Model B (current) | 11-22% on gold value | Medium | Escrow risk, new protocol |
| SOST Model A (proposed) | 11-22% | Medium-High | Same as current |
| SOST Model B (proposed) | 5.7-11% on gold value | Medium | Halved, still competitive |

SOST's higher APR is justified by:
- Brand-new protocol (higher adoption risk)
- No exchange listing yet (liquidity risk)
- Gold custody proof is novel (operational risk)
- SOST price may be volatile once traded

---

**This document is a PROPOSAL. No code changes until CTO explicit approval.**

# PoPC Economic Analysis

**Date:** 2026-03-29
**Author:** NeoB (CTO Analysis)

## 1. Code-Verified Constants

From `include/sost/popc.h` and `src/popc.cpp`:

**Reward rates (bps = basis points, 100 bps = 1%):**
```
POPC_REWARD_RATES[] = {100, 400, 900, 1500, 2200}
POPC_DURATIONS[]    = {  1,   3,   6,    9,   12}  // months
```

| Duration | Reward Rate (bps) | Reward % of bond |
|----------|-------------------|-----------------|
| 1 month  | 100 | 1% |
| 3 months | 400 | 4% |
| 6 months | 900 | 9% |
| 9 months | 1500 | 15% |
| 12 months | 2200 | 22% |

**Protocol fee:** 500 bps = 5% deducted from reward before payout.

**Bond sizing (`compute_bond_pct`) — based on SOST/gold price ratio, NOT duration:**
```cpp
ratio_bps < 100   → 25% bond  // SOST very cheap vs gold
ratio_bps < 500   → 20% bond
ratio_bps < 1000  → 15% bond
ratio_bps < 5000  → 12% bond
ratio_bps >= 5000 → 10% bond
```

**CRITICAL FINDING:** With SOST = $1 and gold = $3,000/oz:
- ratio_bps = ($1 / $3,000) × 10,000 = **3.33 bps**
- This falls in the `< 100` bracket → **25% bond for ALL durations**
- Bond does NOT vary by duration — it varies by price ratio only

## 2. Corrected Model A Table (1 oz gold, SOST=$1, Gold=$3,000)

| Duration | Bond % | Bond SOST | Reward % (of bond) | Gross Reward | Net Reward (after 5% fee) | Total Return |
|----------|--------|-----------|-------------------|-------------|--------------------------|-------------|
| 1 month | 25% | 750 | 1% | 7.50 | 7.125 | 757.125 |
| 3 months | 25% | 750 | 4% | 30.00 | 28.50 | 778.50 |
| 6 months | 25% | 750 | 9% | 67.50 | 64.125 | 814.125 |
| 9 months | 25% | 750 | 15% | 112.50 | 106.875 | 856.875 |
| 12 months | 25% | 750 | 22% | 165.00 | 156.75 | 906.75 |

**APR equivalents (annualized on bond amount):**

| Duration | Net Reward | APR on Bond |
|----------|-----------|-------------|
| 1 month | 7.125 / 750 = 0.95% | 0.95% × 12 = **11.4%** |
| 3 months | 28.50 / 750 = 3.8% | 3.8% × 4 = **15.2%** |
| 6 months | 64.125 / 750 = 8.55% | 8.55% × 2 = **17.1%** |
| 9 months | 106.875 / 750 = 14.25% | 14.25% × 1.33 = **19.0%** |
| 12 months | 156.75 / 750 = 20.9% | 20.9% × 1 = **20.9%** |

## 3. Model B — CRITICAL DIFFERENCE

From `src/popc_model_b.cpp:128`:
```cpp
int64_t calculate_escrow_reward(int64_t gold_value_stocks, uint16_t duration_months) {
    // reward applied to gold_value_stocks, NOT bond
```

**Model B rewards are calculated on GOLD VALUE, not on bond.** This is 4x the base for Model A.

| Duration | Gold Value (SOST equiv) | Reward % | Gross Reward | Net (after 5%) |
|----------|------------------------|----------|-------------|----------------|
| 1 month | 3,000 | 1% | 30.00 | 28.50 |
| 3 months | 3,000 | 4% | 120.00 | 114.00 |
| 6 months | 3,000 | 9% | 270.00 | 256.50 |
| 9 months | 3,000 | 15% | 450.00 | 427.50 |
| 12 months | 3,000 | 22% | 660.00 | 627.00 |

**Model B pays ~4x more than Model A** per oz of gold, and pays IMMEDIATELY (upfront). The participant risks nothing (no bond, no slash, gold in escrow).

| Duration | Model A Net Reward | Model B Net Reward | Ratio B/A |
|----------|-------------------|-------------------|-----------|
| 1 month | 7.125 | 28.50 | **4.0x** |
| 6 months | 64.125 | 256.50 | **4.0x** |
| 12 months | 156.75 | 627.00 | **4.0x** |

## 4. Pool Income

From `src/subsidy.cpp`:
- Genesis reward: 785,100,863 stocks = 7.85100863 SOST
- PoPC Pool share: 25% = 1.96275216 SOST/block
- q per epoch: 0.7788 (decay factor)
- Epoch length: 131,553 blocks (~2.5 years)

| Period | Blocks/year | Reward/block | Pool income/year |
|--------|------------|-------------|-----------------|
| Year 1 (epoch 0) | ~52,560 | 1.963 SOST | **103,130 SOST** |
| Year 3 (epoch 1) | ~52,560 | 1.528 SOST | **80,302 SOST** |
| Year 5 (epoch 2) | ~52,560 | 1.190 SOST | **62,531 SOST** |
| Year 8 (epoch 3) | ~52,560 | 0.927 SOST | **48,718 SOST** |

## 5. Sustainability Scenarios

### Model A (1 oz gold, 12-month commitment, net reward = 156.75 SOST)

| Scenario | Participants | Rewards/year | Pool Income (Y1) | Ratio | Verdict |
|----------|-------------|-------------|------------------|-------|---------|
| A: NeoB only | 1 | 156.75 | 103,130 | 658:1 | SUSTAINABLE |
| B: 10 participants | 10 | 1,567.50 | 103,130 | 65.8:1 | SUSTAINABLE |
| C: 100 participants | 100 | 15,675 | 103,130 | 6.6:1 | SUSTAINABLE |
| D: 500 participants | 500 | 78,375 | 103,130 | 1.32:1 | MARGINAL |
| E: 659 participants | 659 | 103,254 | 103,130 | **1.00:1** | **BREAKEVEN** |
| F: 1000 participants | 1000 | 156,750 | 103,130 | 0.66:1 | **UNSUSTAINABLE** |

**Model A max participants (12-month, 1 oz): ~659 per year in epoch 0.**

### Model B (1 oz gold, 12-month escrow, net reward = 627.00 SOST)

| Scenario | Participants | Rewards/year | Pool Income (Y1) | Ratio | Verdict |
|----------|-------------|-------------|------------------|-------|---------|
| A: NeoB only | 1 | 627.00 | 103,130 | 164:1 | SUSTAINABLE |
| B: 10 participants | 10 | 6,270 | 103,130 | 16.4:1 | SUSTAINABLE |
| C: 100 participants | 100 | 62,700 | 103,130 | 1.64:1 | MARGINAL |
| D: 164 participants | 164 | 102,828 | 103,130 | **1.00:1** | **BREAKEVEN** |
| E: 200 participants | 200 | 125,400 | 103,130 | 0.82:1 | **UNSUSTAINABLE** |

**Model B max participants (12-month, 1 oz): ~164 per year in epoch 0.**

### Breakeven Table by Duration

| Duration | Model A max/year | Model B max/year |
|----------|-----------------|-----------------|
| 1 month (annualized ×12) | 103,130 / (7.125 × 12) = **1,207** | 103,130 / (28.50 × 12) = **302** |
| 3 months (×4) | 103,130 / (28.50 × 4) = **905** | 103,130 / (114.00 × 4) = **226** |
| 6 months (×2) | 103,130 / (64.125 × 2) = **804** | 103,130 / (256.50 × 2) = **201** |
| 9 months (×1.33) | 103,130 / (106.875 × 1.33) = **725** | 103,130 / (427.50 × 1.33) = **181** |
| 12 months (×1) | 103,130 / 156.75 = **659** | 103,130 / 627.00 = **164** |

### Epoch Decay Impact

| Epoch | Years In | Pool Income/year | Model A max (12mo) | Model B max (12mo) |
|-------|---------|-----------------|-------------------|-------------------|
| 0 | 0-2.5 | 103,130 | 659 | 164 |
| 1 | 2.5-5 | 80,302 | 512 | 128 |
| 2 | 5-7.5 | 62,531 | 399 | 100 |
| 3 | 7.5-10 | 48,718 | 311 | 78 |

## 6. Pool Depletion Protection

**Current code checks (from `src/popc_tx_builder.cpp`):**
```cpp
if (pool_utxos.empty()) {
    if (err) *err = "PoPC Pool balance insufficient (no UTXOs)";
    return false;
}
// ... later:
if (err) *err = "PoPC Pool balance insufficient";
return false;
```

The code checks at REWARD DISTRIBUTION time (when building the reward TX). It does NOT check at REGISTRATION time.

**This means:**
- A user can register even if the pool can't afford their future reward
- The pool check only triggers when trying to actually send the reward
- Users may complete their commitment and find no reward available

## 7. Recommended Policy

**Option B (RECOMMENDED): Accept registrations but warn clearly.**

Reasoning:
1. Blocking registrations is overly restrictive — pool income continues
2. Dynamic reward reduction requires consensus changes (overcomplicated now)
3. First-come-first-served is unfair
4. Warning + best-effort is honest and simple

**Implementation:**
- At registration: calculate projected pool balance at commitment end
- If projected balance < reward: include warning in response:
  `"warning": "Pool may not have sufficient funds for full reward. Reward subject to pool availability."`
- At release: pay what's available, clearly report shortfall
- Never block registration — the bond + custody proof have value independent of reward

## 8. Gaming Attack Analysis

### Flash Loan Attack
- Buy XAUT → register → pass verification → sell XAUT next day
- **Current mitigation:** Periodic verification every 60 min catches this within 1 hour
- **Risk:** If the attacker sells XAUT within 60 minutes of verification, they pass 1 check but fail the next
- **Impact:** LOW — the bond is locked for 1-12 months. The attacker loses the bond if caught in ANY future audit
- **Recommendation:** Increase audit frequency for NEW participants (first 30 days: every 6 hours)

### Sybil Attack (Multiple Accounts)
- Same person, 10 ETH addresses, 0.1 oz each
- **Current mitigation:** Reputation system starts at 0 stars (30% audit rate)
- **Risk:** Each account needs its own bond. Total bond = same. Total reward = same.
- **Impact:** NONE — Sybil doesn't increase returns per oz of gold
- **Recommendation:** No action needed — the math is the same regardless of account count

### Minimum Bond/Gold
- **Current minimum:** Any amount > 0 stocks and > 0 mg gold
- **Risk:** Micro-bonds (0.001 oz = $3 gold → $0.75 bond → $0.165 reward) waste operational overhead
- **Recommendation:** Set minimum gold at 15,552 mg (0.5 oz, existing NEW tier max) = $1,500 worth

### Timing Attack
- Register when pool is full, complete before it empties
- **Risk:** Rational strategy, not exploitable — first registrations have highest certainty of reward
- **Impact:** NONE — this is working as intended (early adopters benefit)

## 9. CTO Recommendations

### 1. Reward Percentages — KEEP AS-IS (for now)
The 11-22% APR range is aggressive but sustainable with <500 participants per year. In early phases with 1-50 participants, the pool can easily support this. Consider reducing in epoch 2+ if participation grows.

### 2. Maximum Participants Cap — NOT NEEDED YET
At current adoption (0 participants), this is premature. Add a cap when participation approaches 50% of breakeven (~300 for Model A, ~80 for Model B at 12 months).

### 3. Bond Minimum — IMPLEMENT
Set `POPC_MIN_BOND_STOCKS = 100'000'000` (1 SOST) to prevent micro-bond spam.
Set `POPC_MIN_GOLD_MG = 15552` (0.5 oz) — already matches the NEW tier max.

### 4. Gold Minimum — ALREADY EXISTS
`POPC_MAX_MG_NEW = 15552` (0.5 oz) acts as a de facto minimum for new participants. Enforce this as a minimum at registration.

### 5. Pool Depletion Policy — IMPLEMENT WARNING
Add projected balance check at registration. Warn if projected pool < reward. Never block.

### 6. Dynamic Reward Adjustment — DEFER
Not needed until epoch 1 (2.5 years). If participation grows, consider reducing rates by 25% per epoch to match emission decay.

### 7. Model B Reward Base — CRITICAL ISSUE
Model B paying on GOLD VALUE (4x Model A) is too generous. Consider changing to match Model A (reward on bond-equivalent value) or reducing Model B rates to 25% of current values.

**Option 7A (RECOMMENDED):** Reduce Model B rates to 1/4 of Model A:
```
Model B rates: {25, 100, 225, 375, 550} bps (0.25%, 1%, 2.25%, 3.75%, 5.5%)
```
This equalizes the pool drain rate between Model A and Model B for the same oz of gold.

**Option 7B:** Change Model B to calculate reward on bond-equivalent amount.

## 10. Summary Table

| Metric | Model A | Model B | Issue? |
|--------|---------|---------|--------|
| Reward base | Bond (25% of gold value) | Gold value (100%) | YES — 4x mismatch |
| Net reward, 1 oz, 12 mo | 156.75 SOST | 627.00 SOST | Model B drains pool 4x faster |
| Max participants/year (12 mo) | 659 | 164 | Model B is 4x more expensive |
| APR equivalent (12 mo) | 20.9% | 20.9% on gold value | Same rate, different base |
| Pool depletion check | At distribution only | At distribution only | Should warn at registration |
| Minimum bond | None (>0 only) | N/A (no bond) | Should add 1 SOST minimum |
| Minimum gold | None (>0 only) | None (>0 only) | Should add 0.5 oz minimum |
| Flash loan protection | 60-min audit cycle | Escrow = immune | Model B is naturally protected |
| Sybil protection | Same math regardless | Same math regardless | No issue |

## Conclusion

The PoPC reward system is economically sustainable for early adoption (<500 participants/year). The primary concern is Model B's 4x higher pool drain rate. This should be addressed before production deployment by either reducing Model B rates or changing its reward base to match Model A.

**Canonical score: 22.8/40 UNCHANGED.** This analysis is operational, not a canonical change.

# PoPC Dynamic Reward Model — Proposal

**Date:** 2026-03-29
**Author:** NeoB (CTO)
**Status:** IMPLEMENTED (2026-03-29) — Dynamic PUR, anti-whale, Model B halved rates
**Decision required:** CTO explicit approval before any code changes

---

## 1. Concept

The PoPC reward system should be **self-regulating**: rewards adjust automatically based on real-time pool utilization. When few participants are active, rewards are high (incentivizing early adoption). As participation grows, rewards decrease proportionally, ensuring the pool never drains.

This eliminates the need for manual intervention, hard caps on participant count, or periodic rate adjustments.

**Core principle:** The pool is a shared resource. Your reward is your share of what's available.

---

## 2. Pool Utilization Ratio (PUR)

### Definition

```
PUR = committed_rewards / pool_balance

Where:
  pool_balance     = current SOST balance of the PoPC Pool address (on-chain, verifiable)
  committed_rewards = sum of all reserved rewards for active participants
```

### Behavior

| Event | Effect on PUR | Effect on Rewards |
|-------|--------------|-------------------|
| New participant registers | PUR rises (more committed) | Next participant gets slightly less |
| New block mined | PUR falls (pool grows by ~1.96 SOST) | Rewards increase slightly |
| Participant completes + receives reward | PUR falls (commitment released, pool pays out) | Rewards increase |
| Participant slashed | PUR falls significantly (commitment released + bond enters pool) | Rewards increase |
| No activity | PUR falls steadily (pool grows from coinbase) | Rewards increase |

---

## 3. Reward Adjustment Curve

### Chosen Model: Smooth Quadratic Decay

After evaluating three curves:

**Linear:** `factor = 1 - PUR`
- Simple but too generous at high PUR. At PUR=80%, factor=20% — still allows significant commitments.

**Exponential:** `factor = e^(-3 × PUR)`
- Drops too fast. At PUR=50%, factor=22%. Penalizes moderate utilization excessively.

**Quadratic (RECOMMENDED):** `factor = (1 - PUR)^2`
- Gentle at low PUR, aggressive at high PUR. Natural "soft landing."
- At PUR=50%: factor=25% — meaningful reduction.
- At PUR=80%: factor=4% — near-zero, effectively closed.
- At PUR=90%: factor=1% — only minimum floor applies.

### Comparison Table

| PUR | Linear | Exponential (k=3) | Quadratic (1-PUR)^2 |
|-----|--------|-------------------|---------------------|
| 0% | 100% | 100% | 100% |
| 10% | 90% | 74% | 81% |
| 25% | 75% | 47% | 56% |
| 50% | 50% | 22% | 25% |
| 75% | 25% | 10% | 6.3% |
| 90% | 10% | 7% | 1.0% |
| 95% | 5% | 6% | 0.25% |
| 100% | 0% | 5% | 0% |

**Quadratic is the best balance:** gentle enough to not scare early participants, aggressive enough to protect the pool at high utilization.

---

## 4. Reward Tables by PUR

### Model A — 12-Month Commitment (Bond = 2,500 SOST at $10k gold)

Maximum rate: 22% of bond = 550 SOST gross, 522.50 net (after 5% fee).
Minimum floor: 1% of bond = 25 SOST gross, 23.75 net.

| PUR | Factor | Effective Rate | Gross Reward | Net Reward | APR on Bond |
|-----|--------|---------------|-------------|-----------|-------------|
| 0% | 100% | 22.00% | 550.00 | 522.50 | 20.9% |
| 10% | 81.0% | 17.82% | 445.50 | 423.23 | 16.9% |
| 25% | 56.3% | 12.38% | 309.38 | 293.91 | 11.8% |
| 50% | 25.0% | 5.50% | 137.50 | 130.63 | 5.2% |
| 75% | 6.3% | 1.38% | 34.38 | 32.66 | 1.3% |
| 80% | 4.0% | 1.00% | 25.00 | 23.75 | 1.0% (FLOOR) |
| 90% | 1.0% | 1.00% | 25.00 | 23.75 | 1.0% (FLOOR) |
| 100% | — | CLOSED | — | — | — |

### Model B — 12-Month Escrow (Reward on gold value = 10,000 SOST equiv)

Maximum rate: 11% (proposed) of gold value = 1,100 SOST gross, 1,045 net.
Minimum floor: 0.5% of gold value = 50 SOST gross, 47.50 net.

| PUR | Factor | Effective Rate | Gross Reward | Net Reward |
|-----|--------|---------------|-------------|-----------|
| 0% | 100% | 11.00% | 1,100.00 | 1,045.00 |
| 10% | 81.0% | 8.91% | 891.00 | 846.45 |
| 25% | 56.3% | 6.19% | 618.75 | 587.81 |
| 50% | 25.0% | 2.75% | 275.00 | 261.25 |
| 75% | 6.3% | 0.69% | 68.75 | 65.31 |
| 80% | 4.0% | 0.50% | 50.00 | 47.50 (FLOOR) |
| 100% | — | CLOSED | — | — |

### All Durations at PUR = 25% (Typical Early Operation)

| Duration | Model A Rate | Model A Net | Model B Rate | Model B Net |
|----------|-------------|-------------|-------------|-------------|
| 1 month | 0.56% | 13.39 | 0.28% | 26.72 |
| 3 months | 2.25% | 53.44 | 1.13% | 106.88 |
| 6 months | 5.07% | 120.23 | 2.53% | 240.47 |
| 9 months | 8.44% | 200.44 | 4.22% | 400.31 |
| 12 months | 12.38% | 293.91 | 6.19% | 587.81 |

---

## 5. Reservation Mechanism

### At Registration

```
1. Read pool_balance (on-chain)
2. Read committed_rewards (from PoPCRegistry)
3. Compute PUR = committed_rewards / pool_balance
4. If PUR >= 100%: REJECT — "Pool fully committed. Try again later."
5. Compute factor = max(FLOOR_FACTOR, (1 - PUR)^2)
6. Compute reward = base_rate × factor × bond_or_gold_value
7. Apply anti-whale tier multiplier
8. Apply protocol fee (5%)
9. RESERVE the net reward: committed_rewards += net_reward
10. Return to participant:
    - "Your reward: XXX SOST (at current pool utilization of YY%)"
    - "Reward is RESERVED — guaranteed if you complete your commitment"
    - "Current effective rate: ZZ% (maximum: WW%)"
```

### At Completion (Release)

```
1. Pay the RESERVED reward amount (guaranteed)
2. Release from committed_rewards: committed_rewards -= reserved_amount
3. PUR drops → better rates for next participants
```

### At Slash

```
1. Release from committed_rewards (no reward paid)
2. Bond goes to pool (50% Pool + 50% Gold Vault)
3. PUR drops significantly (double effect: less committed + more in pool)
```

---

## 6. Anti-Whale Integration

The dynamic system naturally penalizes whales through PUR mechanics:

### Example: 100 oz whale vs 10 × 10 oz individuals

**Scenario A: Whale registers 100 oz at once (PUR before = 20%)**
- PUR before: 20% → factor = 64%
- Reward (100 oz, tier 50-200 = 50% multiplier): 10,000 × 11% × 64% × 50% = 3,520 SOST reserved
- PUR after: 20% + (3,520 / pool) → rises significantly
- Effective rate for whale: ~3.5% (heavily reduced)

**Scenario B: 10 individuals register 10 oz each (PUR before = 20%)**
- First person: PUR = 20%, factor = 64%, tier 0-10 = 100% → 1,000 × 11% × 64% = 704 net
- After each registration PUR rises slightly
- Last person: PUR ≈ 27%, factor ≈ 53% → 1,000 × 11% × 53% = 583 net
- Total for 10 individuals: ~6,400 SOST
- Average effective rate: ~6.4% (higher than whale)

**Result:** Individuals get better rates than whales. The system naturally distributes benefits.

### Combined Anti-Whale Tiers

| Gold (oz) | Tier Multiplier | PUR Impact | Double Penalty |
|-----------|-----------------|------------|---------------|
| 0-10 | 100% | Small | No |
| 10-50 | 75% | Medium | Mild |
| 50-200 | 50% | Large | Significant |
| >200 | REJECTED | — | Hard cap |

---

## 7. Simulation: 12 Months of Operation

### Parameters
- Pool starting balance: 3,700 SOST (current estimated)
- Daily coinbase income: ~282 SOST (25% of ~1,128 SOST/day)
- All participants: 1 oz gold, 6-month commitment, Model A
- Bond per participant: 2,500 SOST (locked, not in pool)
- Net reward per participant at PUR=0%: 213.75 SOST (9% × 2,500 × 95%)

### Month-by-Month

| Month | New | Active | Pool Balance | Committed | PUR | Eff. Rate (6mo A) | Completions | Rewards Paid |
|-------|-----|--------|-------------|-----------|-----|-------------------|-------------|-------------|
| 0 | — | 0 | 3,700 | 0 | 0.0% | 9.00% (max) | — | — |
| 1 | 5 | 5 | 12,260 | 1,069 | 8.7% | 7.52% | 0 | 0 |
| 2 | 10 | 15 | 20,820 | 2,904 | 13.9% | 6.65% | 0 | 0 |
| 3 | 20 | 35 | 29,380 | 6,113 | 20.8% | 5.65% | 0 | 0 |
| 4 | 10 | 45 | 37,940 | 7,410 | 19.5% | 5.83% | 0 | 0 |
| 5 | 10 | 55 | 46,500 | 8,590 | 18.5% | 5.99% | 0 | 0 |
| 6 | 10 | 60 | 55,060 | 8,844 | 16.1% | 6.35% | 5 | 1,069 |
| 7 | 10 | 55 | 62,551 | 8,120 | 13.0% | 6.82% | 15 | 2,904 |
| 8 | 15 | 50 | 68,207 | 7,690 | 11.3% | 7.11% | 20 | 3,334 |
| 9 | 15 | 45 | 73,433 | 6,889 | 9.4% | 7.39% | 20 | 3,145 |
| 10 | 15 | 50 | 78,848 | 7,495 | 9.5% | 7.37% | 10 | 1,560 |
| 11 | 15 | 55 | 83,848 | 8,115 | 9.7% | 7.35% | 10 | 1,590 |
| 12 | 15 | 60 | 88,818 | 8,720 | 9.8% | 7.33% | 10 | 1,610 |

**Key observations:**
- Pool NEVER drains — it grows continuously from coinbase income (~8,560 SOST/month)
- PUR peaks at ~21% in month 3 (when 35 active participants, many not yet completing)
- After month 7, completions start releasing reserved rewards → PUR stabilizes around 10%
- Effective 6-month rate stabilizes around 7.3% (reduced from 9.0% max) — still attractive
- At 60 active participants, the system is completely sustainable

### Stress Test: 500 Participants at Once

What if 500 participants register simultaneously (1 oz each, 12 months, Model A)?

- Pool balance: ~103,000 SOST (end of year 1)
- Each participant's reward at PUR=0%: 522.50 SOST
- Total committed if all at max: 261,250 SOST — exceeds pool by 2.5x

**With dynamic system:**
- First 50: PUR=0→25%, average reward ≈ 370 SOST each → 18,500 committed
- Next 50: PUR=25→40%, average reward ≈ 210 SOST → 10,500 committed
- Next 50: PUR=40→50%, average reward ≈ 145 SOST → 7,250 committed
- Next 50: PUR=50→55%, average reward ≈ 115 SOST → 5,750 committed
- Next 50: PUR=55→60%, average reward ≈ 90 SOST → 4,500 committed
- Next 50: PUR=60→63%, average reward ≈ 75 SOST → 3,750 committed
- After 300: PUR≈70%, reward ≈ 50 SOST (near floor)
- After 400: PUR≈80%, reward = floor (23.75 SOST)
- At 450: PUR≈90% → effectively closed for new registrations with meaningful rewards
- At ~480: PUR=100% → HARD STOP

**Result:** The system self-limits at ~450-480 participants (1 oz, 12 months). Nobody loses their reserved reward. The pool doesn't drain. Early participants get better rates. The system works.

---

## 8. Decision Flow at Registration

```
PARTICIPANT REGISTERS
        │
        ▼
   Read pool_balance (on-chain)
   Read committed_rewards (registry)
        │
        ▼
   Compute PUR = committed / balance
        │
        ├── PUR >= 100%
        │       → REJECT: "Pool fully committed"
        │
        ├── PUR >= 95%
        │       → WARN: "Pool nearly full. Minimum reward only."
        │       → Show minimum floor rate
        │       → Allow registration if participant accepts
        │
        └── PUR < 95%
                │
                ▼
        Compute factor = (1 - PUR)²
        Apply FLOOR: factor = max(factor, FLOOR_FACTOR)
                │
                ▼
        Compute base_reward = base_rate × factor
                │
                ▼
        Apply anti-whale tier
        (0-10oz: 100%, 10-50: 75%, 50-200: 50%, >200: REJECT)
                │
                ▼
        Apply protocol fee (5%)
                │
                ▼
        RESERVE reward in committed_rewards
                │
                ▼
        RETURN to participant:
        - Reserved reward amount (GUARANTEED)
        - Current effective rate
        - Pool utilization percentage
        - "Lock exactly XXX SOST as BOND_LOCK to activate"
```

---

## 9. Recommendations

### 9.1. Adopt Quadratic Decay: `factor = (1 - PUR)^2`
- Best balance between generosity and protection
- Natural "soft landing" as pool fills
- Mathematically simple, easy to audit

### 9.2. Reserve Rewards at Registration
- Guarantees the participant's reward
- Prevents "I custodied gold for 12 months and got nothing"
- First-come-first-served is fair and transparent

### 9.3. Model B at 50% of Model A Rates
- Reduces pool drain from 4x to 2x per oz
- Still more rewarding than Model A (justified by gold escrow commitment)
- Combined with PUR, Model B naturally self-limits

### 9.4. Keep Current Model A Rates as Maximum
- 22% at 12 months (PUR=0%) is the ceiling
- Aggressive but appropriate for bootstrapping
- System naturally reduces as adoption grows
- Review at epoch 1 (2.5 years)

### 9.5. Anti-Whale Tiers + Hard Cap at 200 oz
- Prevents single participant from monopolizing the pool
- Tier reduction discourages large positions
- Hard cap at 200 oz is absolute ceiling

### 9.6. Minimum Floor Rates
- Model A: 1% of bond (12 months)
- Model B: 0.5% of gold value (12 months)
- Even at PUR=95%, participants get something
- Below floor, registration is still possible but reward is minimal

### 9.7. Implementation Priority
1. **Phase 1:** PUR calculation + reservation (before first PoPC participant)
2. **Phase 2:** Anti-whale tiers (can ship with Phase 1)
3. **Phase 3:** Dynamic UI in wallet (show current rate, PUR, estimated reward)
4. **Phase 4:** Model B rate reduction (deploy with next binary update)

### 9.8. Code Changes Required (Estimated)

| File | Change | Effort |
|------|--------|--------|
| `include/sost/popc.h` | Add PUR constants, floor rates, whale tiers | 30 min |
| `src/popc.cpp` | Add `compute_pur()`, `apply_dynamic_factor()`, `apply_whale_tier()` | 2 hours |
| `src/sost-node.cpp` | Update `handle_popc_register` and `handle_escrow_register` with PUR | 1 hour |
| `include/sost/popc_model_b.h` | Add `ESCROW_REWARD_RATES[]` (halved) | 15 min |
| `src/popc_model_b.cpp` | Use `ESCROW_REWARD_RATES` + dynamic factor | 30 min |
| `tests/test_popc.cpp` | Add PUR tests, whale tier tests, floor tests | 1 hour |
| `tests/test_escrow.cpp` | Update for new rates | 30 min |
| `website/sost-wallet.html` | Show current rate and PUR in PoPC calculator | 1 hour |

**Total estimated: ~7 hours**

---

## Summary

The dynamic reward model transforms PoPC from a static "first-come-first-served until pool drains" system into a self-regulating market. Early participants are rewarded with higher rates. As the pool fills, rates naturally decrease. Nobody loses their guaranteed reward. The pool never drains. Whales are naturally penalized. The system finds its own equilibrium.

**This is how a constitutional, self-sovereign protocol should handle reward distribution: with math, not with manual intervention.**

---

**This document is a PROPOSAL. No code changes until CTO explicit approval.**

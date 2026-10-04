# Reward Model — fine simulation results (ANALYSIS ONLY · NOT CONSENSUS)

No activation height. No consensus change. No binaries changed. SOST amounts illustrative at the
current subsidy (7.851 SOST/block, epoch 0). Block time **verified 600 s (10 min)** ⇒ 144 blocks/day,
52,560/year. Reproducible: `sim/reward_sim.py` → `sim/reward_sim_results.{json,csv}`.
**The simulation does NOT pick a winner.** Current consensus remains **50% miner / 50% DTD**.

Models: CURRENT 50/50/0 · 75/20/5 · 80/15/5 · 80/10/10 · 70/25/5.
Intervals: 1,000 · 2,500 · 4,320 (~30 d) · 5,000 · 10,000 blocks.
Scenarios: S1 high-concentration (dominant 56%), S2 moderate, S3 healthy-decentralized, S4 many-small,
S5 Sybil.

## FACTS
- Supply conservation: miner+DTD+jackpot = **100%** for all five models (no new emission; cap 4,669,201 unchanged).
- The 5% jackpot is a *new* subsidy-funded stream in the proposal; today's live jackpot is reserve-funded (distinct).
- Current DTD selection seed = `sha256(domain || prev_block_hash || height)` (prior block, not the draw block);
  a multi-block-history variant exists (`select_lottery_winner_index_from_history`).

## SIMULATION RESULTS

### The core trade-off (S1 high-concentration, interval 5,000)
| model | small-miner uplift (×hash) | dominant share (56% hash) | Gini | HHI |
|---|---|---|---|---|
| **CURRENT 50/50/0** | **2.58×** | **36.3%** | **0.26** | 0.218 |
| 70/25/5 | 1.95× | 44.2% | 0.364 | 0.267 |
| 75/20/5 | 1.79× | 46.2% | 0.39 | 0.281 |
| 80/15/5 | 1.63× | 48.1% | 0.416 | 0.297 |
| 80/10/10 | 1.63× | 48.1% | 0.416 | 0.297 |

**MORE DIRECT POW WEIGHT vs MORE SMALL-MINER REDISTRIBUTION — quantified.** Moving 50/50 → 75/20/5
raises the dominant miner's take (36%→46% of emission for 56% hash), lowers the small miner's uplift
(2.58×→1.79×), and raises income inequality (Gini 0.26→0.39). 80/x pushes furthest toward PoW
(dominant 48%, Gini 0.416). 70/25/5 preserves the most redistribution of the candidates (Gini 0.364).
The jackpot's 5–10% adds **variance/opportunity**, not an equivalent substitute for continuous DTD.

### Interval comparison (75/20/5, S1) — prize vs variance vs small-miner shut-out
| interval | ~days | prize SOST | draws/yr | small-miner CoV | **P(small miner wins NO jackpot in 1 yr)** |
|---|---|---|---|---|---|
| 1,000 | 6.9 | 393 | 52.6 | 0.036 | 0.01% |
| 2,500 | 17.4 | 981 | 21.0 | 0.057 | 2.2% |
| 4,320 | 30.0 | 1,696 | 12.2 | 0.075 | 10.9% |
| 5,000 | 34.7 | 1,963 | 10.5 | 0.080 | 14.7% |
| 10,000 | 69.4 | 3,926 | 5.3 | 0.113 | 38.4% |

Longer interval = bigger prize but the small miner is far more likely to go a whole year with **no**
jackpot (10,000 → 38% shut out; 5,000 → 15%; 2,500 → 2%). That is the "jackpot feel vs small-miner
inclusion" tension, quantified. 1,000 is not a jackpot (too frequent/small).

### Gini across scenarios (interval 5,000; lower = more equal income)
| scenario | CURRENT | 75/20/5 | 80/15/5 | 80/10/10 | 70/25/5 |
|---|---|---|---|---|---|
| S1 high-concentration | 0.26 | 0.39 | 0.416 | 0.416 | 0.364 |
| S2 moderate | 0.162 | 0.243 | 0.260 | 0.260 | 0.227 |
| S3 healthy-decentralized | 0.108 | 0.134 | 0.158 | 0.158 | 0.112 |
| S4 many-small | 0.046 | 0.071 | 0.077 | 0.077 | 0.066 |
In every scenario 50/50 is the most equal; the gap narrows as the network decentralizes.

### S5 — Sybil (operator with 30% hash splits into K identities; 75/20/5; uniform-among-eligible)
| K identities | op eligible ids | op share of DTD/jackpot pool | op total emission share | verdict |
|---|---|---|---|---|
| 1 | 1 | 9.1% | 24.8% | baseline |
| 5 | 5 | 33.3% | 30.8% | gains by farming identities |
| 10 | 10 | 50.0% | 35.0% | gains more |
| 30 | 30 | 75.0% | 41.2% | dominates the pool |
| 100 | 0 | 0% | 22.5% | each identity <1 block/288 → recency drops them all |

**MAJOR FINDING — a uniform-among-identities jackpot/DTD is Sybil-gameable.** A 30%-hash operator can
raise its DTD+jackpot take substantially by splitting into many signed identities (K=10 → half the
pool; K=30 → three-quarters), because the existing anti-dominance gate (≥10% of 288 excluded when ≥11
miners) does **not** catch sub-10% split identities. Only extreme splitting (K≈100, each identity too
small to mine within the 288 recency window) self-defeats. **Conclusion: a large-value jackpot must NOT
use uniform-among-eligible-identities.** Use **PoW-weighting with a per-identity cap** (so chance rises
with real work but is bounded) — i.e. the V2 "node-gated + PoW linear weight" direction, not pure
uniform. This is the single most important design constraint from the simulation.

## DESIGN TRADE-OFFS
- Lower DTD → more issuance tied to hashrate (security incentive ↑) but less small-miner redistribution
  and higher Gini/HHI. Not a free improvement.
- The jackpot adds variance and discrete opportunity; it is not an equivalent substitute for continuous
  DTD (small miners can be shut out for a year at long intervals).
- Uniform selection is Sybil-vulnerable at jackpot scale; PoW-weighted-capped selection is required.
- Randomness: prev-block / multi-block-history seed is grindable only by prior-block producers / reorgs;
  bound prize below reorg-safety + coinbase maturity.

## RECOMMENDATION (RANGE, NOT A DECISION)
- **No single model is "best"** — it depends on the priority:
  - **70/25/5** — redistribution-leaning (smallest hit to small miners; Gini 0.364).
  - **75/20/5** — balanced middle.
  - **80/10/10** — PoW-and-lottery-leaning (highest concentration + variance).
- **Recommended ranges to study further:** Miner **70–80%** · DTD **15–25%** · Jackpot **5–10%**.
- **Interval range: 2,500–5,000 blocks (~17–35 days).** 2,500 keeps small miners rarely shut out (~2%)
  and lowest reorg incentive; 5,000 gives a bigger prize but ~15% annual small-miner shut-out. Avoid
  10,000 (38% shut-out) and 1,000 (not a jackpot).
- **Eligibility: PoW-weighted with a per-identity cap (V2-style), NOT uniform-among-identities.**

HARD FORK REQUIRED: YES. CONSENSUS CHANGED: NO. BINARIES CHANGED: NO. WHITEPAPER LIVE CHANGED: NO.

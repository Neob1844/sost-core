# ECONOMICS 80 / 15 / 5 — research simulation on the real mainnet chain

> **Update 2026-10-14:** the owner froze 80/15/5 of the block subsidy (fees 100 % to the
> miner, 5 % into the consensus accumulator J, jackpot funded from H first then J) for
> V17 at block #40,000. The normative rules are in
> [`V17_ECONOMICS_NORMATIVE.md`](V17_ECONOMICS_NORMATIVE.md). The research text below is
> kept unchanged as the record of the pre-decision analysis.

Status: **RESEARCH ONLY**. Nothing here changes consensus. No reward rule is
proposed for activation by this document. #40,000 is a target, not a commitment.

Verdict: **ECONOMIC_80_15_5 = WATCH** — do **not** include in the #40,000
consensus scope; re-evaluate for #50,000 or later, once the network has more
than two active producers (see §7).

Reproduce:

```
python3 tools/research/sim_80_15_5.py <mainnet-chain.json> --json out.json
```

Input used: mainnet chain dump, heights 0..30,428, tip
`849e95b1…f51f`, file SHA-256 `a46ead75…9ee9`. Standard library only, about 10 s.
Full output: `docs/v40000/sim_80_15_5_result.json`.

---

## 1. Current rule, verified from code

| Item | Value | Source |
|---|---|---|
| Subsidy | `R0 = 785,100,863` stocks (7.851 SOST), × e^(-1/4) per epoch of 131,553 blocks, hard cap 466,920,160,910,299 stocks | `src/subsidy.cpp` |
| DTD draw frequency | **every block** from V15_HEIGHT = 25,000 (3-of-3) | `include/sost/lottery.h` `is_lottery_block` |
| Split from 25,000 | `total_reward = subsidy + fees`; DTD = `total / 2` (integer division); miner = `total − DTD` | `phase2_coinbase_split` (lottery.h); coinbase shape decision in `src/sost-node.cpp` (V15 emission transition (T)) |
| Gold Vault / PoPC coinbase outputs | **0** from 25,000 | same; on chain the 0x02/0x03 outputs stop at 24,999 |
| DTD winner | uniform draw over the eligibility set (`roll % n`), seed = SHA-256("SOST_LOTTERY_V11" ‖ last 16 block hashes ‖ height); **from V17 (#40,000): SHA-256("SOST_DTD_V17" ‖ last 16 PoW commits ‖ height)** (DTD-F1, `docs/v40000/DTD_F1_SEED_POW_COMMIT.md`) | `src/lottery.cpp` `select_lottery_winner_index_from_history`, `lottery_seed_input_from_history` |
| DTD eligibility (V16, ≥ 30,000) | mined within the last 288 blocks; 6-block cooldown (retried without cooldown if the set would be empty); SbPoW identity; 10 % anti-dominance gate armed only with ≥ 11 distinct miners in the 288 window; PoPC gate inert on mainnet | `src/lottery.cpp` `compute_lottery_eligibility_set`, `include/sost/params.h` |
| Historical Jackpot | `TX_TYPE_JACKPOT` (0x02) every 288 blocks from 25,290; base 100 SOST, cap 500 incl. rollover; **spends the frozen historical reserve UTXOs** (Gold Vault + PoPC constitutional addresses); supply-neutral, **no new emission feeds it** | `params.h` `HIST_JACKPOT_*`, on-chain txs |
| Jackpot V2 (≥ 30,000) | own winner: NODE_BIND + heartbeat eligibility, linear PoW weight over 2,016 blocks; payout economics unchanged | `include/sost/jackpot_v2.h`, `params.h` |

So the current split is **50 % PoW miner / 50 % DTD normal / 0 % new emission to the
jackpot**. The jackpot pool is the historical reserve only.

Model validation: the script re-implements the mainnet DTD eligibility + winner
rule in Python and reproduces the on-chain DTD winner in **5,429 / 5,429** blocks
from 25,000 to 30,428 (exact match). The reserve balance is tracked by full UTXO
replay (txid = SHA-256d of the serialized tx).

## 2. Candidate (research)

Same `total_reward` per block, no new emission, no fee burn, no native burn:

* PoW miner: `total − DTD − J` (= 80 %, miner absorbs rounding)
* DTD normal: `total × 15 / 100` (integer division) to the same DTD winner as on chain
* Jackpot inflow J: `total × 5 / 100` (integer division) into the **existing** DTD Jackpot pool.
  The 5 % is **not** a direct node payment; it reaches participants only through
  the existing jackpot draw (Jackpot V2: node eligibility, PoW weight).

Accounting constraint: the historical Gold Vault stays frozen for the existing
Jackpot mechanism and must not be mixed with new inflow. The simulation therefore
keeps two ledgers — historical reserve H (unchanged draining) and new inflow pool
J — and pays the 100 SOST base from H first, then J. Implementing this needs a new
consensus accumulator (like `pending_lottery_amount`) or a new coinbase output to a
new jackpot address, plus a new jackpot payout source. Either way it is a
CONSENSUS_FORK touching coinbase validation, undo data and the jackpot path.

## 3. Results — flows (post-V15 window 25,000..30,428, 5,429 blocks, 37.7 days)

Fees in the whole window: 0.051 SOST — total reward is effectively the subsidy.

| Metric | Current 50/50 | 80/15/5 |
|---|---|---|
| PoW miner revenue per block | 3.9255 SOST | **6.2808 SOST** (+60 %) |
| DTD per block | 3.9255 | 1.1777 |
| New jackpot inflow per block | 0 | 0.3926 (2,131 SOST over the window) |
| Hash-proportional share of reward (security budget, strict) | 50 % | **80 %** |
| Distinct DTD recipients | 179 | 179 (same winners, scaled) |
| DTD Gini / HHI | 0.194 / 0.0089 | identical (pure scaling) |
| Top-1 share of ALL flows (miner + DTD + jackpot) | 28.2 % | **44.1 %** |
| Top-3 share of all flows | 49.9 % | **77.9 %** |
| Gini of all recipients | 0.558 | **0.815** |
| HHI of all recipients | 0.119 | **0.287** |
| Share received by small participants (< 10 % of blocks) | **52.4 %** | 25.7 % |

Producer concentration (blocks): top-1 53.6 %, top-3 94.7 %, 174 distinct
producers in the window. The historical "one miner ≈ 90 %" profile is honest
hardware (no PoW exploit). In the V16 window (30,000..30,428) only **2 producers**
exist (68.8 % / 31.2 %) and the DTD eligibility set averages **1.56**, so today the
DTD half also lands on those two miners (DTD Gini 0.05, HHI 0.51). In that window
the candidate moves the top-1 all-flow share from 56.8 % to 65.0 %.

Per producer (post-V15): the top producer would receive 18,591 SOST instead of
12,487 (+49 %); a typical 1–3-block producer who won DTD draws receives ~150
instead of ~240 (−37 %).

## 4. Jackpot pool sustainability

| Item | Value |
|---|---|
| Historical reserve at 24,999 | 68,174.29 SOST |
| Jackpots paid (25,290..29,898, all V15) | 17 × 100 SOST = 1,700 SOST |
| First V2 jackpot #30,186 | **not paid** (rolled over; first NODE_BIND appeared at 30,194) |
| Historical reserve at tip | 66,474.29 SOST |
| Drain at base | 100 SOST / 288 blocks = 0.347 SOST/block |
| **Runway, current (no inflow)** | **3.64 years** (empty ≈ height 221,660) |
| 5 % inflow per 288 blocks, epoch 0 / 1 / 2 / 3 | 113.1 / 88.0 / 68.6 / 53.4 SOST |
| **Runway at base payout, candidate** | **12.2 years** (≈ height 671,804); J peaks ≈ 66,500 SOST after ~4 y |

The 5 % inflow (113 SOST per cadence) exceeds the 100 SOST base during epoch 0 only;
from epoch 1 it no longer covers the base on its own. It extends the jackpot from
~3.6 to ~12 years — it does not make it perpetual. Payout sizes stay 100 SOST
(base), up to the 500 SOST cap after rollovers.

## 5. Small-miner variance (analytic, per day, 144 blocks)

A new miner with hash share p, joining a DTD eligibility set of size E
(mean ± sd of daily SOST; CV = sd/mean):

| E (set size) | p | Current mean / CV | 80/15/5 mean / CV |
|---|---|---|---|
| 2.56 (today, V16) | 1 % | 214.2 / 0.11 | 71.6 / 0.14 |
| 2.56 | 5 % | 249.1 / 0.10 | 111.5 / 0.16 |
| 20 | 1 % | 32.4 / 0.34 | 17.1 / 0.47 |
| 20 | 5 % | 56.5 / 0.26 | 53.7 / 0.31 |
| 153.8 (V15 average) | 1 % | 9.1 / 0.65 | 10.1 / 0.75 |
| 153.8 | 5 % | 31.9 / 0.34 | 46.3 / 0.36 |

Reading:

* While the eligible set is small, which it is today, the uniform DTD is a very large
  entry subsidy for a new small miner. 80/15/5 cuts a 1 % entrant's expected income
  about 3× (214 → 72 SOST/day) and raises their variance.
* The two rules only cross over once the eligible set is in the low hundreds.
* Uniform per-identity DTD is also a Sybil incentive: splitting hash across k
  identities multiplies the expected DTD take while the anti-dominance gate is
  unarmed (fewer than 11 miners). 80/15/5 reduces that incentive by 70 % (50 % → 15 %).
  That is the strongest argument for the candidate.

## 6. Operator incentives

* **Miners.** The candidate pays hash more directly (80 % vs 50 %), so it is a
  stronger and more predictable security budget per unit of hash.
* **Node operators.** The 5 % only reaches people through Jackpot V2 (NODE_BIND +
  heartbeats, PoW-weighted). It lengthens the life of the node-participation
  incentive from about 3.6 to about 12 years, but it is still a draw, not a
  payment for running a node.
* **Small and new participants.** They lose most of the DTD channel. In the V15
  window that channel carried more than half of all value to small participants.

## 7. Quantitative gates and verdict

| Gate | Threshold for GO | Measured | Result |
|---|---|---|---|
| Security budget (hash-proportional share) | ≥ +20 pp | +30 pp (50 → 80 %) | PASS |
| Top-3 all-flow share | must not rise more than 10 pp | +28 pp (49.9 → 77.9 %) | **FAIL** |
| Small-participant share of flows | must not fall more than 25 % relative | −51 % relative (52.4 → 25.7 %) | **FAIL** |
| Jackpot sustainability | runway ≥ 2× current | 3.4× (3.64 → 12.2 y) | PASS |
| Data sufficiency | ≥ 10 independent producers in the active window | 2 producers in the V16 window | **FAIL (weak evidence)** |
| Supply neutrality / no burn / no direct node pay | required | met by construction | PASS |

**ECONOMIC_80_15_5 = WATCH.** It gives a real security-budget and anti-Sybil gain
and roughly triples the jackpot's life, but on today's two-producer network it
sharply concentrates flows and removes most of the small-participant channel. The
evidence is weak (2 active producers, 3 days of V16 data, a fee market that does
not exist yet). Recommendation:

* **Defer beyond #40,000.**
* Re-run this script when the V16 window holds ≥ 10 independent producers over
  ≥ 4,000 blocks.
* Consider intermediate splits (for example 65 / 30 / 5) at that point.
* Any future version must keep the historical reserve ledger separate from new
  inflow.

## 8. Limits of this simulation

* It is counterfactual on the same winners and the same hash distribution; miners'
  behavioural response is not modelled.
* The variance model is analytic (binomial) and assumes the 600 s target.
* Jackpot V2 eligibility is not re-implemented. Actual payouts are reused, and the
  projection assumes a base payout every cadence.
* The epoch projection uses floating-point e^(-1/4) for the forward schedule only.
  The replay itself is integer-exact.

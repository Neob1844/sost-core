# Future Reward Evolution — analysis package (PROPOSAL, NOT CONSENSUS)

Status: **ANALYSIS / DOCUMENTATION ONLY.** No consensus change. No hard fork. No activation
height chosen. Deliverable for review before any protocol upgrade is considered.

Author: NeoB. Simulation subsidy S = 7.851 SOST/block (epoch 0; ~constant over 1k–10k horizons).
Block target 600 s ⇒ 288 blocks/day, 105,120 blocks/year.

---

## 1. Current reward system (verified in code)

- **Emission split (today, since V15 / block #25,000): 50% miner / 50% DTD.** Pre-V15 (blocks
  0–24,999): 50% miner / 25% Gold Vault / 25% PoPC. Source: `include/sost/params.h` (coinbase
  split), `src/subsidy.cpp` (hard-cap enforcement), `src/sost-node.cpp` (lottery/coinbase shape).
- **Subsidy:** Feigenbaum-δ decay toward hard cap **4,669,201 SOST**; ~7.851 SOST/block in epoch 0
  (epoch = 131,553 blocks; at height ~29k we are still in epoch 0). `TARGET_SPACING = 600 s`.
- **DTD (normal):** per-block, uniform among *eligible* miner identities (not weighted by balance
  or payment). Eligibility gates: SbPoW signed-miner (most recent block ≥ #7,100; enforced from
  #12,100), recency (≥1 block in last 5,000 from #25,000; tightens to last 288 from #30,000),
  recent-producer cooldown (previous 6 blocks; 5 before V13), anti-dominance (≥10% of last 288
  excluded when ≥11 distinct miners).
- **DTD Jackpot (V1, live):** funded by the frozen heritage reserve (Gold Vault + PoPC, ~66.8k
  SOST), cadence **288 blocks (~48 h)**, first #25,290, base 100 / cap 500 SOST, supply-neutral,
  drains over ~3 years. **It is NOT financed by a slice of the block subsidy** — it redistributes
  an already-accumulated reserve.
- **DTD Jackpot V2 (activates #30,000, first draw #30,186):** node-gated eligibility + PoW *linear*
  weight; no cooldown / no anti-dominance in V2. `src/node_participation.cpp`, `params.h`.

Key point for this proposal: **today there is NO ongoing "5% of block subsidy → jackpot" stream.**
The jackpot is reserve-funded. The proposal below introduces, as a *future* option, a jackpot
financed by a fixed fraction of each block's scheduled emission.

---

## 2. Proposed mature-network model (PROPOSAL)

**75% Block Miner · 20% Normal DTD · 5% Accumulated Jackpot Reserve.** 75+20+5 = 100% of the
*existing* scheduled emission — **no new emission, max supply unchanged**.

- 75% miner: strengthens the PoW security incentive; PoW still decides who produces the block.
- 20% DTD: keeps a second, non-hashrate-proportional distribution layer.
- 5% jackpot: a dedicated fraction accumulates into a periodic draw for eligible miners.

Supply conservation (simulated): ACTUAL 50/50/0, 75/20/5, 80/15/5, 80/10/10, 70/25/5 — **all sum
to 100%** (PASS). The jackpot creates no SOST; it redistributes a pre-reserved slice of emission.

---

## 3. Simulation — jackpot accumulation by interval (5% stream)

equiv = jackpot_fraction × interval, expressed in block-rewards (BR); SOST at 7.851/block.

| Interval | ~days | jackpots/yr | equiv (×BR) @5% | SOST @7.851 |
|---|---|---|---|---|
| 1,000 | 3.5 | 105 | 50× | ≈ 393 |
| 2,500 | 8.7 | 42 | 125× | ≈ 981 |
| **5,000** | **17.4** | **21** | **250×** | **≈ 1,963** |
| 10,000 | 34.7 | 10.5 | 500× | ≈ 3,926 |

At **10% (80/10/10)** the SOST doubles (e.g. 10,000 blocks → 1,000×BR ≈ 7,851 SOST).

**Recommendation: 5,000-block interval** (~17 days, ~1,963 SOST per draw). 1,000 (~3.5 d) is too
frequent to feel like a jackpot; 10,000 (~35 d) is more dramatic but less visible. Simulate 1k/2.5k/
5k/10k before fixing. Subsidy decays per epoch, so recompute SOST amounts at the actual height.

---

## 4. Simulation — expected share by miner class (5 miners; dominant = 56% hash)

block reward ∝ hashrate; DTD + jackpot uniform among eligible identities (small net, anti-dominance
gate OFF below 11 miners). Values = % of total emission; "vs hash" = uplift/penalty.

| model | small (2%) | medium (10%) | large (30%) | dominant (56%) | small-miner uplift |
|---|---|---|---|---|---|
| ACTUAL 50/50/0 | 11.0 (+9.0) | 15.0 (+5.0) | 25.0 (−5.0) | 38.0 (−18.0) | **5.50×** |
| **75/20/5** | 6.5 (+4.5) | 12.5 (+2.5) | 27.5 (−2.5) | 47.0 (−9.0) | **3.25×** |
| 80/15/5 | 5.6 (+3.6) | 12.0 (+2.0) | 28.0 (−2.0) | 48.8 (−7.2) | 2.80× |
| 80/10/10 | 5.6 (+3.6) | 12.0 (+2.0) | 28.0 (−2.0) | 48.8 (−7.2) | 2.80× |
| 70/25/5 | 7.4 (+5.4) | 13.0 (+3.0) | 27.0 (−3.0) | 45.2 (−10.8) | 3.70× |

Reading: the current 50/50/0 is *very* redistributive (dominant 56% hash → only 38% of emission).
75/20/5 raises the dominant to 47% (still sub-proportional, healthy) while small miners keep a
**3.25× uplift** — i.e. it strengthens PoW economics without collapsing into proportional PoW. 80/x
pushes further toward PoW; 70/25/5 keeps more redistribution. **75/20/5 is the balanced middle.**

> Caveat: this is a static expectation with few miners and the anti-dominance gate off (N<11). With
> ≥11 distinct miners the gate caps any >10%-of-288 identity out of the DTD pool, further flattening
> the dominant's DTD/jackpot share. A proper agent simulation (below) should confirm the dynamics.

---

## 5. Anti-Sybil — eligibility must be cryptographically demonstrated mining

**Do NOT allow 1 address = 1 ticket.** That is a trivial Sybil (mint 10,000 addresses → 10,000
tickets). SOST already has the primitives to bind eligibility to *real demonstrated work*:

- **SbPoW signed-miner identity:** every block from #7,100 carries a Schnorr signature over the PoW
  commitment ⇒ a draw "ticket" should be a *signed miner identity that actually produced blocks*,
  not an address.
- **Recency window:** must have mined ≥1 block in the last N blocks (5,000 today; 288 from #30,000).
- **Cooldown + anti-dominance:** already limit back-to-back and >10%/288 concentration.
- **NODE_BIND / NODE_HEARTBEAT (V16):** node participation gate.

Proposed draw eligibility = *signed miner identities with a qualifying recent block*, not addresses.
This makes Sybil require real PoW per identity, which defeats address farming.

### Small-miner protection — models compared
- **A. Uniform eligible-miner draw:** every eligible identity equal chance. Max decentralization;
  best "small miner lottery" message; but a large operator could split into many signed identities
  — mitigated by requiring real per-identity PoW + recency + anti-dominance.
- **B. Capped PoW weighting:** chance rises with PoW but capped (e.g. ≤10% per identity). Balances
  fairness vs rewarding work; harder to Sybil-game than pure uniform.
- **C. Tiered eligibility:** participation bands so one big operation can't dominate the draw.
- **D. Existing V2 logic (node-gated + PoW linear weight):** already live-designed for #30,000.
  If V2's linear weight + node gate already balances this, **adapt V2 rather than invent a new rule.**

Recommendation: start from **D (reuse/adapt V2)**; if a stronger small-miner bias is wanted, layer
**A with a per-identity cap (B)**. Do not create a parallel rule without justification.

---

## 6. Anti-gaming checklist (to analyse before any consensus change)

Sybil; hashrate splitting across addresses/identities; miner-identity farming; pool manipulation;
rapid join/leave; self-mining eligibility farming; repeated-winner dominance; jackpot sniping;
reorg incentives (a large jackpot block raises reorg value — size the jackpot and finality
accordingly); manipulation around the draw height; block withholding; predictable randomness.
**The winner must not be knowable or manipulable before the required state is cryptographically
fixed.**

---

## 7. Randomness

Current DTD/jackpot selection is **deterministic from chain state** (block-hash entropy at the draw
height), uniform among eligible, computed by the rules — not chosen by anyone. Requirements for the
jackpot draw:
- entropy source = the draw block's hash (and prior committed state), fixed only when the block is
  mined;
- **deterministic to verify, unpredictable before commitment**;
- the block producer must not be able to grind the winner (bound the selection to data they cannot
  cheaply bias — e.g. future-committed hashes / VDF-style delay if grinding risk is material);
- reproducible and verifiable by any node; **no centralized oracle.**
Audit item: quantify the block producer's ability to influence the draw by choosing which block to
publish (self-selection), and whether the reward justifies withholding/grinding.

---

## 8. Transition (PROPOSAL — heights NOT chosen)

`CURRENT (50/50/0)` → `TRANSITION (intermediate, e.g. 60/35/5 or 70/25/5)` → `MATURE (75/20/5)`.
A mature network does **NOT** mean 100/0. Keeping a DTD + jackpot fraction preserves an incentive
structure distinct from purely proportional PoW. Any heights are **PROPOSAL / NOT CONSENSUS** until
decided. Evaluate against: security, decentralization, miner retention, small-miner participation,
distribution, game theory.

---

## 9. Supply conservation test (to add)

Assert, per block and cumulatively: `miner + dtd + jackpot == scheduled_subsidy(height)` exactly
(integer stocks, no rounding leak), and that total issued never exceeds `SUPPLY_MAX_STOCKS`. The
jackpot reserve is a redistribution bucket, not new issuance.

---

## 10. Implementation notes (for later — NOT now)

- Hard fork: **YES** (changes coinbase split + a new jackpot-reserve output type + draw logic).
- Height-gated, deterministic activation (like V15/V30000); no operator switch.
- Tests: supply-conservation (per-block + cumulative), split-at-height, jackpot accumulation +
  payout + rollover-if-no-eligible, eligibility (signed-miner/recency/cooldown/anti-dominance),
  randomness verifiability, reorg-safety of the jackpot block, Sybil resistance of the draw.
- Activation height: **NOT chosen.**

## 11. Risks detected
- Reducing DTD from 50%→20% lowers small-miner uplift (5.5×→3.25×) — still meaningful, but a real
  shift; confirm it does not deter the current small-miner base before activating.
- A larger periodic jackpot raises the reorg value of the draw block — size + finality must be set
  so the jackpot never exceeds what honest finality protects.
- A subsidy-funded 5% jackpot is a *new* stream (today's jackpot is reserve-funded) — the whitepaper
  must not conflate the two.
- Any per-identity draw invites identity farming; eligibility must stay bound to real PoW.

---

## Whitepaper section (DRAFT) — "Future Reward Evolution"

### Current consensus
Since block #25,000 (V15), every block's scheduled emission is split **50% to the miner** and
**50% to Deterministic Token Distribution (DTD)**, which pays the non-miner half back to eligible
active miners on-chain (uniform among eligible identities; gated by signed-miner identity, recency,
cooldown and anti-dominance). A separate **DTD Jackpot** redistributes an already-accumulated
heritage reserve (not a slice of the subsidy) on a 288-block cadence; DTD Jackpot V2 activates at
#30,000.

### Proposed mature-network model
As the network matures, SOST may evolve the split toward **75% miner / 20% normal DTD / 5%
accumulated jackpot**, financed entirely from the existing scheduled emission (75+20+5 = 100%; no
new emission; max supply 4,669,201 unchanged). The intent: strengthen the PoW security incentive
while preserving a non-hashrate-proportional distribution and a periodic, visible jackpot for
eligible miners. Proposed jackpot cadence: ~5,000 blocks (~17 days), accumulating ≈250× the block
reward per draw (illustrative; recompute at the actual subsidy).

> **This model is a proposed future evolution and is NOT part of current consensus unless and until
> activated through a defined, height-gated protocol upgrade.** A mature network does not imply
> 100% miner / 0% DTD; SOST intends to keep a redistributive + probabilistic component permanently.

### Simple example
For every 100 SOST of scheduled block issuance (proposed): **75 → block producers, 20 → normal DTD,
5 → jackpot reserve**, which accumulates until the draw height. *Illustrative:* if the block reward
were 1 SOST, 5% × 5,000 blocks = **250 SOST** accumulated jackpot (real amount follows the real
subsidy at that height).

### Eligibility (anti-Sybil)
A jackpot "ticket" is a **cryptographically demonstrated miner identity** (SbPoW-signed, with a
qualifying recent block), **never a bare address** — so a chance at the jackpot requires real PoW,
not address farming.

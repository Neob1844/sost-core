# V11 — Technical Specification

**Status**: DRAFT v3 · author: SOST consensus working group

**Phase split (current decision)**:

| Phase | Components | Activation height | Status |
|---|---|---|---|
| **Phase 1** | A (extended cASERT cascade) + B (state-dependent dataset access) | **block 7,000** | code complete, tests written, awaiting compilation gate |
| **Phase 2** | C (SbPoW signature-bound proof) + D (PoP lottery + jackpot rollover) | **TBD** — when implementation passes verification, simulation, testnet and adversarial gates | NOT YET IMPLEMENTED · skeleton scaffold checked in for future work |

**No calendar pressure on Phase 2.** The chain will not run unfinished consensus code to meet a fixed block height. Phase 2 ships when ready.

**Phase 2 lottery frequency schedule** (when activated at height `H_PHASE2`):

```
First 5,000 blocks after Phase 2 activation:  2 of every 3 blocks  (high-freq bootstrap)
After H_PHASE2 + 5000, permanently:           1 of every 3 blocks  (steady state)
```

This document specifies the four V11 consensus changes: extended cASERT cascade (A), state-dependent dataset access (B), SbPoW signature-bound proof (C), and Proof-of-Participation lottery (D). Components A and B are designed for block 7,000. Components C and D are designed but deferred to a Phase 2 activation height to be announced when the implementation is verified.

---

## 1 · Component A — Linear cASERT cascade (no artificial cap)

### 1.1 Purpose
Replace the V10 continuous formula `drop = floor((elapsed - 540) / 60)` with a single linear formula that starts dropping at `elapsed >= 540 s` and **keeps growing every 60 s with no artificial cap**. This restores the cascade as the primary recovery mechanism for any natural profile up to H35, with anti-stall (~90 min) as the safety net rather than the rescuer.

### 1.2 Schedule
```
drop = 0                              if elapsed <  540 s
drop = 1 + (elapsed - 540) / 60       if elapsed >= 540 s
```

Examples:

| elapsed | drop | profile relative to base |
|---|---|---|
|  540 s |  1 | base − 1 |
|  600 s |  2 | base − 2 |
|  660 s |  3 | base − 3 |
|  720 s |  4 | base − 4 |
|  780 s |  5 | base − 5 |
|  840 s |  6 | base − 6  *(legacy cap, no longer enforced)* |
|  900 s |  7 | base − 7 |
| 1 020 s |  9 | base − 9 |
| 1 500 s | 17 | base − 17 |
| 2 940 s | 41 | base − 41 *(H35 → E6, one above floor)* |
| 3 000 s | 42 | base − 42 *(H35 → E7, worst-case reaches floor)* |

Floor stays at `E7` (CASERT_H_MIN). The natural floor is enforced by the existing `staged = max(effective_h_min, raw_base_H − drop)` clamp, so although `drop` can grow without bound, the resulting profile never crosses below E7.

**Worst-case math**: H35 → E7 requires `35 + 7 = 42` drops, reached at `540 + 41·60 = 3000 s = 50 min`, well inside the ~90 min anti-stall window. (An earlier draft of this section claimed 41 drops covered H35 → E7; that was off by one — 41 drops only reaches E6.)

bitsQ controller, anti-stall, lag clamp and future-drift cap are **unchanged**.

### 1.3 Activation
At block `CASERT_V11_HEIGHT = 7000`, conditional on gate G1 (§6).

### 1.4 Single source of truth — `compute_v11_cascade_drop`
The formula is implemented exactly once, in `src/pow/casert.cpp`, and exposed via `include/sost/pow/casert.h`. Both miner and validator paths route through `compute_v11_cascade_drop(block_elapsed_s)`. Any divergence between the two would partition the chain at the activation height; the single helper makes that error structurally impossible. Unit tests in `tests/test_casert_v11.cpp §5` lock the formula at every interesting boundary (0/539/540/600/840/900/1500/2940/3000/5400 s plus the negative-clock-skew edge), and explicitly distinguish drop=41 (H35 → E6) from drop=42 (H35 → E7).

### 1.5 Replaced "saturating cap at drop=6"
The earlier draft of this spec described a saturated piecewise table (`drop = 6` for any `elapsed >= 840 s`). That cap was sized for the H6-H12 operating range and could not save a block whose natural profile escalated to H32+. The linear cascade replaces it: `840 s → 6` is preserved as a point on the curve, but the curve continues past 840 s instead of saturating.

---

## 2 · Component B — State-dependent dataset access

### 2.1 Purpose
Close the prefetch optimization gap. The V10 dataset access pattern `dataset[r % dataset_size]` is strictly increasing in `r`, so the CPU prefetcher anticipates the next read while processing the current round. Setups with high RAM bandwidth (servers with 8-12 channel DDR5) benefit disproportionately.

### 2.2 Change
Round-by-round dataset index changes from:
```
ds_idx = r % dataset_size
```
to:
```
ds_idx = read_u32_le(state.data() + 8) % dataset_size
```
where `state` is the SHA-256 of the previous round's full output (already computed and committed inside the inner loop).

Each access depends on the previous round's output → no prefetchable pattern → RAM latency dominates. Multi-core scaling is reduced because all cores hit the same memory bus with unpredictable patterns.

### 2.3 Memory profile
**Unchanged**. Dataset stays at 4 GB, scratchpad cache stays at 4 GB peak. Total ConvergenceX memory remains 8 GB. **CPU mining minimum stays at 8 GB RAM.**

The Memory-Lock per-instance proposal (forcing dataset to be per-thread, not shared) is a separate research direction and is **not** part of V11. Earliest activation, if it ever ships, is block 12,000+ after independent simulation.

### 2.4 Activation
At block `CASERT_V11_HEIGHT = 7000`, conditional on gate G2 (§6). Gates G1 and G2 are independent — A can ship without B and vice versa.

---

> ## ⚠️  Boundary marker — end of Phase 1, start of Phase 2
>
> Sections **§1 (Component A)** and **§2 (Component B)** above describe **Phase 1**, which activates at `CASERT_V11_HEIGHT = 7000`.
>
> Sections **§3 (Component C — SbPoW)** and **§4 (Component D — Lottery)** below describe **Phase 2**, which activates at a separate height `V11_PHASE2_HEIGHT`. **`V11_PHASE2_HEIGHT` is currently `INT64_MAX` (sentinel — effectively disabled).** It is explicitly **NOT** equal to 7000, and is **NOT** scheduled for any specific height yet. Phase 2 ships only when the activation criteria in §6 are met and the owner sets a finite value.
>
> Anything below in §3-§4 (lottery, SbPoW, jackpot rollover, signature-bound proof, fair-share frequency, eligibility set, coinbase shape change for triggered blocks) belongs to Phase 2 and **must not be activated by, or interpreted as activating at, block 7000**.
>
> If a future commit changes `V11_PHASE2_HEIGHT` from `INT64_MAX` to a finite value, that commit MUST update this note and §6 simultaneously.

---

## 3 · Component C — SbPoW (Signature-bound Proof of Work)

### 3.1 Purpose
Bind the miner identity to the PoW commitment **before** the hash is computed, so post-hoc coinbase relabeling becomes impossible. Each block is provably the work of one specific keypair. This makes pool topologies (where workers mine without holding the payout key) structurally incompatible.

### 3.2 Header changes
The block header at `height >= V11_SBPOW_HEIGHT` carries two extra fields:

```
+------------------+-------+-----------------------------------------+
| field            | size  | meaning                                 |
+------------------+-------+-----------------------------------------+
| miner_pubkey     | 33 B  | secp256k1 compressed pubkey             |
| miner_signature  | 64 B  | Schnorr (BIP-340) over PoW commit + h   |
+------------------+-------+-----------------------------------------+
```

Total header growth: 97 bytes. Pre-fork blocks keep the original header serialization; nodes negotiate format by height.

### 3.3 PoW seed binding
Pre-V11 ConvergenceX seed:
```
seed = sha256(MAGIC || "SEED" || header_core || block_key || nonce || extra_nonce)
```
Post-V11 (`height >= V11_SBPOW_HEIGHT`):
```
seed_v11 = sha256(MAGIC || "SEED2" || header_core || block_key
                   || nonce || extra_nonce || miner_pubkey)
```
The pubkey is mixed into the seed, so the entire 100,000-round inner loop is a function of `miner_pubkey`. Switching pubkey re-runs the full work.

### 3.4 Signature
After ConvergenceX produces `commit`:
```
sig_message      = sha256("SOST/POW-SIG/v11" || commit || height)
miner_signature  = schnorr_sign(miner_privkey, sig_message)
```

### 3.5 Validation rules
A block at `height >= V11_SBPOW_HEIGHT` is valid only if **all** of:
1. `miner_pubkey` is a well-formed compressed secp256k1 point.
2. `miner_signature` is a valid BIP-340 Schnorr signature for `sig_message` under `miner_pubkey`.
3. The seed used to derive the commit was `seed_v11` including `miner_pubkey`.
4. The coinbase output paying the **miner subsidy** (50% of the block subsidy + fees) is sent to the address derived from `miner_pubkey`.

Failure of any of (1)-(4) → block rejected.

### 3.6 What this prevents and what it does not
✅ **Prevents**: post-hoc coinbase relabeling, key-delegation pool topologies (a pool operator cannot issue work and let workers mine without the key).
❌ **Does not prevent**: solo-miner dominance via raw hashrate. SbPoW makes pools structurally incompatible; it does **not** affect a single operator running their own keys.

This is a deliberate scope: SbPoW addresses pool centralization risk, not hashrate centralization. The lottery (§4) addresses redistribution.

### 3.7 Activation
**Deferred to Phase 2**. Original target was block 7,000 alongside A/B/D, but SbPoW requires non-trivial integration (header v2 serialization, wallet keystore access, libsecp256k1 Schnorr verification, cross-node validation) that cannot be safely shipped in the same activation window as A/B. Phase 2 activation height (`V11_PHASE2_HEIGHT`, shared with component D) is **TBD** — set when the implementation passes gates G3.1, G3.2 and G3.3 (§6). All `V11_SBPOW_HEIGHT` references in §3.2/§3.3/§3.5 of this document refer to that same `V11_PHASE2_HEIGHT` value.

---

## 4 · Component D — Proof-of-Participation lottery

### 4.1 Phasing schedule

The lottery activates at `V11_PHASE2_HEIGHT` (TBD — see §4.8). From that height:

| Window | Heights | Trigger rule | Source of lottery prize |
|---|---|---|---|
| **Bootstrap (first 5,000 blocks)** | `[V11_PHASE2_HEIGHT, V11_PHASE2_HEIGHT + LOTTERY_HIGH_FREQ_WINDOW)` | 2 of every 3 blocks | 50% of block subsidy (= 25% Gold Vault + 25% PoPC Pool) redirected to lottery winner |
| **Steady state (permanent)** | `>= V11_PHASE2_HEIGHT + LOTTERY_HIGH_FREQ_WINDOW` | 1 of every 3 blocks | same prize composition |

The 5,000-block bootstrap window is intentional: high-frequency redistribution at activation drives small-miner participation while the network adjusts. After the bootstrap, the rate stabilises at 1-of-3 forever.

### 4.2 Trigger function

Let `H` = `V11_PHASE2_HEIGHT` and `W` = `LOTTERY_HIGH_FREQ_WINDOW = 5000`.

```
triggered(h) =
    if H <= h < H + W:   (h - H) % 3 != 2        # 2-of-3 bootstrap
    if h >= H + W:        (h - (H + W)) % 3 == 0 # 1-of-3 steady state
    else:                 false
```

Bootstrap pattern (L = lottery, N = normal), starting at `H`:
```
offset:  0    1    2    3    4    5    …
state:   L    L    N    L    L    N    …
```

Steady-state pattern (after `H + 5000`):
```
offset:  0    1    2    3    4    5    …
state:   L    N    N    L    N    N    …
```

### 4.3 Eligibility set

For a block at height `h`, the eligibility set `E(h)` is computed deterministically from the chain prefix `[0, h-1]`:

```
E(h) = { addr |
    addr won the miner subsidy of at least 1 block in [0, h-1]
    AND  addr did not win a block reward (miner subsidy OR lottery prize)
         in [h - LOTTERY_REWARD_EXCLUSION_WINDOW, h-1]
    AND  addr is not the miner of block h itself }
```

Constants:
- `LOTTERY_REWARD_EXCLUSION_WINDOW = 30` blocks. Tunable post-Monte Carlo.
- Eligibility floor: "ever mined at least one block since genesis" — opens the pool wide and removes the prior 30-block-mining-history requirement.
- Exclusion: ANY block-reward winner (miner subsidy OR lottery prize) in the last 30 blocks. Stronger than excluding only past lottery winners.

### 4.4 Winner selection

Deterministic, reproducible by every node:
```
seed         = sha256("SOST/POP-LOTTERY/v11" || prev_block.hash)
sorted_E     = sort(E(h), by lex order of address bytes)
if  sorted_E.empty()   →  fallback (see §4.7)
winner_idx   = uint64_le(seed[0:8]) % len(sorted_E)
winner_addr  = sorted_E[winner_idx]
```

Selection seed comes from `prev_block.hash`, not the current block — so the miner of block `h` cannot grind the seed to favour their own addresses.

### 4.5 Coinbase construction

Lottery-triggered block:
```
output[0]  =  miner subsidy            (50% of subsidy + fees)  → block miner
output[1]  =  Gold Vault budget        (0)
output[2]  =  PoPC Pool budget         (0)
output[3]  =  lottery prize            (50% of subsidy)         → winner_addr
```

Normal (not triggered) block:
```
output[0]  =  miner subsidy            (50% of subsidy + fees)  → block miner
output[1]  =  Gold Vault budget        (25%)                    → Gold Vault
output[2]  =  PoPC Pool budget         (25%)                    → PoPC Pool
```

Fees stay with the block miner (output[0]) on every block. Lottery is on subsidy only — emission semantics match the whitepaper.

### 4.6 Validation rules

A block at `height >= 7000` is valid iff:
1. The trigger function (§4.2) for `h` matches the coinbase shape (3 outputs vs 4 outputs).
2. If triggered: `output[3].address == winner_addr` derived per §4.4 from the chain's prefix at `h-1`.
3. If not triggered: `output[1].address == GoldVault` and `output[2].address == PoPCPool`.
4. Miner subsidy `output[0]` always = 50% of `subsidy(h)` + tx fees.

Failure of any of (1)-(4) → block rejected.

### 4.7 Edge cases

| Case | Rule |
|---|---|
| `E(h) = ∅` (no eligible address) | Triggered block falls back to **normal** split (output[1] Gold Vault, output[2] PoPC Pool). The lottery silently does nothing. |
| `\|E(h)\| = 1` | The single eligible address auto-wins. |
| Tie (deterministic seed produces collision) | Impossible by construction — `winner_idx` is a single integer. The lex-sort of `E(h)` removes any address-ordering ambiguity. |
| Miner of block `h` is in `E(h)` | Excluded by §4.3. They cannot win their own block's lottery. |
| Network reorg after lottery payout | Standard reorg handling: the alternate chain's lottery selection is recomputed from its own prev block. Coinbase maturity (1,000 blocks) protects against the winner spending an orphaned prize. |

### 4.8 Activation
**Deferred to Phase 2**. Original target was block 7,000, but the lottery requires non-trivial integration (chain-state variable for `pending_lottery_amount`, eligibility-set scan, coinbase shape change, reorg-safe undo data) that cannot be safely shipped alongside Phase 1 (A/B). Phase 2 activation height (`V11_PHASE2_HEIGHT`) is **TBD** — set when the implementation passes gates G4.1 through G4.4 (§6). The 5,000-block 2-of-3 bootstrap window starts from that height; 1-of-3 steady state from `V11_PHASE2_HEIGHT + 5000`.

---

## 5 · Mathematical impact on lottery distribution

This section is **honest** about the redistribution mechanic. The lottery is not a magic equalizer — its effectiveness depends on how the dominant operator chooses to manage their addresses.

### 5.1 Notation
- `α` = dominant's hashrate share (currently ≈ 0.70 across windows, peaks ≈ 0.92 in 40-block samples)
- `W` = `LOTTERY_REWARD_EXCLUSION_WINDOW` = 30
- `N_dom` = number of distinct addresses the dominant operates
- `S` = number of distinct small-miner addresses with at least 1 block since genesis (currently ≈ 5-8)

### 5.2 Regime 1 — Dominant uses 1-3 addresses (current behaviour)

The address(es) the dominant uses to mine blocks are mostly excluded by the 30-block reward window (they keep winning). Result:

```
Dominant addresses in E(h):     ≈ 0  (all in cooldown)
Eligibility set size:           ≈ S (small miners)
Dominant lottery share:         ≈ 0%
Small-miner lottery share:      ≈ 100% / S each
```

**Total reward share for dominant**:
```
miner subsidy share  =  α × 50% of every block
lottery share        =  ~0% of triggered blocks
total reward share   ≈  α × 50%  ≈  35% (vs 70% pre-V11)
```

Drop of ~35 percentage points. Strong redistribution.

### 5.3 Regime 2 — Dominant uses N_dom > W addresses, rotated

The dominant generates many addresses and rotates per block. After the first 30 blocks, the addresses that won blocks in last 30 are `min(N_dom, 30)` excluded. The rest are eligible.

```
Dominant addresses in E(h):     ≈  max(0, N_dom - α·W)     # ones not in cooldown
                                ≈  N_dom - 21              # if α=0.70, W=30
Eligibility set size:           ≈  (N_dom - α·W) + S
Dominant lottery share:         ≈  (N_dom - α·W) / [(N_dom - α·W) + S]
```

Numerical example: `N_dom = 100`, `α = 0.70`, `S = 8`:
```
Dominant addresses eligible:    ≈ 100 - 21 = 79
Total eligibility set:          ≈ 79 + 8 = 87
Dominant lottery share:         ≈ 79/87 ≈ 91%
```

So with massive Sybil, dominant captures lottery roughly proportional to their hashrate. **Redistribution effect ≈ 0.**

### 5.4 The trade-off curve

| `N_dom` | Dominant addresses excluded | Dominant lottery share | Total reward share (α=0.70) |
|---|---|---|---|
| 1 | 1 | ~0% | 35% |
| 5 | 5 | ~0% | 35% |
| 21 | 21 | ~0% | 35% |
| 30 | 21 | ≈ 9 / 17 ≈ 53% | ~53% |
| 50 | 21 | ≈ 29 / 37 ≈ 78% | ~64% |
| 100 | 21 | ≈ 79 / 87 ≈ 91% | ~67% |
| 500 | 21 | ≈ 479 / 487 ≈ 98% | ~69% |

The lottery is a **pay-to-rotate** mechanism: the dominant must operate ≥ 30 distinct addresses to recover lottery share, and ≥ 100 to fully recover. This adds operational overhead (key management, address tracking, possibly wallet performance issues at scale). For some operators this overhead is non-trivial; for others it is automatic.

### 5.5 Honest expected outcome
- **Best case**: dominant stays with 1-3 addresses (current behaviour, possibly because of operational simplicity or visibility on the explorer). Drop from ~70% to ~35% total reward share. Strong redistribution.
- **Worst case**: dominant deploys 100+ addresses with automated rotation. Drop from ~70% to ~67%. Marginal redistribution.
- **Realistic case**: somewhere in between. The Monte Carlo simulation (§7) must quantify behaviour under both Sybil-aware and Sybil-naive assumptions before activation.

The lottery does **not** impose a hard cap on dominant share. It imposes an operational cost on maintaining that share. That is the honest framing.

---

## 6 · Per-component activation gates

Each V11 component has its own gate set. Components activate **independently** at block 7,000 if their gate set passes. A component that fails its gate is deferred to block 8,000 (or later) — components that pass activate as scheduled. The fork is **not** bundled atomically.

| Component | Gates | Pass criteria |
|---|---|---|
| **A** Extended cascade | G1.1 unit tests `tests/test_casert_v11.cpp` — boundary table 540/600/660/720/780/840 → drops 1-6 | All tests green. Pre-V11 boundary unchanged. |
| | G1.2 regression: pre-V11 blocks (0..6999) re-validate identically | No reorg, no rejection, byte-for-byte chain identical. |
| | G1.3 cascade simulation `tools/cascade_sim.py` over 5,000 sample slow blocks | Mean block time within ±2% of target post-fork. |
| **B** State-dataset | G2.1 unit tests `tests/test_convergencex_v11.cpp` — pre-V11 uses `r % size`, post-V11 uses `state_lo % size`, determinism | All tests green. |
| | G2.2 cross-platform reproducibility | Identical commits across x86-64, ARM64, with same seed. |
| | G2.3 perf bench: hashrate change vs V10 baseline | ≤ 15% per-thread degradation acceptable; > 15% → block activation pending review. |
| **C** SbPoW | G3.1 unit tests `tests/test_sbpow.cpp` — round-trip sign/verify, invalid sig rejection, seed-binding determinism | All tests green. |
| | G3.2 wallet support audit | Confirmed Schnorr (BIP-340) is supported by `sost-wallet` and key derivation matches spec. |
| | G3.3 adversarial test: wrong pubkey, wrong sig message, mismatched coinbase | All 3 attacks rejected. |
| **D** Lottery | G4.1 unit tests `tests/test_pop_lottery.cpp` — all §4.7 edge cases | All tests green. |
| | G4.2 Monte Carlo simulation `tools/lottery_sim.py` — Scenarios A/B/C (current state, dominant Sybils, mature network) | See §7. Must publish numbers before activation. |
| | G4.3 multi-node testnet 3,000 blocks, 3 operators | Coinbase determinism across nodes; orphan rate ≤ pre-fork baseline + 0.5 pp. |
| | G4.4 adversarial coinbase test | 5 attack patterns (wrong winner, wrong split on triggered block, etc.) all rejected. |

**Common gates** (apply to all 4 components together):
- G_ANN: 14 days minimum public notice with the per-component status before block 7,000.
- G_REVIEW: at least one independent reviewer signs off on each component's consensus changes.

If by block 6,800 (~33 hours of margin at 10 min/block) any component's gates are incomplete, that component is deferred. The chain still hard-forks at 7,000 for the components that pass. A component deferred at 7,000 can target 8,000 or later.

---

## 7 · Monte Carlo simulation plan (G4.2)

`tools/lottery_sim.py` (to be implemented). For each scenario, simulate 5,000 blocks of mining + lottery and report:
- top-entity miner share
- top-entity lottery share
- top-entity total reward share (miner + lottery)
- p10/p50/p90 of small-miner reward fractions
- variance per address per 1,000 blocks
- Sybil sensitivity: rerun with `N_dom ∈ {1, 10, 30, 100}`

### Scenarios

**Scenario A — Current chain state**: dominant 70%, 4 mid-miners 4-9%, 4 small.
**Scenario B — Dominant Sybil**: same hashrate distribution but dominant rotates across 10/30/100 addresses.
**Scenario C — Mature network**: top-1 at 20%, distributed across 50+ active addresses.

### Pass criteria
1. **Scenario A, regime 1** (1-3 dominant addresses): dominant total reward share ≤ 50%.
2. **Scenario B, regime 2** (100 dominant addresses): dominant total reward share ≤ regime 1 + 30 percentage points (so a Sybil attack adds at most 30 pp; full restoration of pre-V11 dominance is acceptable as worst case but should not exceed it).
3. **Scenario C**: top-1 miner total reward share within 5 percentage points of their hashrate share.
4. **Variance**: small miners (< 5% hashrate) earn at least 1 lottery prize per 1,000 blocks with > 99% probability under Scenario A regime 1.

If any criterion fails → tune `LOTTERY_REWARD_EXCLUSION_WINDOW` (try 15, 50, 100), retest. If still failing under reasonable parameters → defer D.

---

## 8 · Testnet plan

### 8.1 Local single-node testnet
Spin up `sost-node --profile testnet` with V11-modified binary applying components at testnet genesis. Mine 12,000 blocks across 5 simulated miners (multi-threaded, controlled hashrate ratios matching scenarios). Verify §4.6 validation passes. Re-validate end-to-end with separate node for determinism.

### 8.2 Multi-node testnet (3 VPS)
Three independent VPS, each with own keypair. Hashrate split 90/5/5. Run 3,000 blocks (~3 weeks at 10 min/block, or accelerated). Verify lottery distribution, eligibility-set determinism, SbPoW signatures cross-node, no spurious orphan rate increase.

### 8.3 Adversarial test
Attempt to mine V11 blocks with: wrong `miner_pubkey`, valid `miner_pubkey` but signature over wrong message, lottery output payable to address NOT in `E(h)`, lottery output present on non-triggered block, normal coinbase shape on triggered block, wrong cascade drop. All MUST be rejected.

---

## 9 · Open questions

1. **Address derivation for `miner_pubkey`**: P2WPKH (witness v0) or P2TR (Taproot)? SOST currently uses bech32 with witness v0. Confirm before implementation.
2. **Schnorr vs ECDSA**: BIP-340 Schnorr preferred. Confirm wallet support.
3. **`LOTTERY_REWARD_EXCLUSION_WINDOW = 30`**: pending Monte Carlo tuning. Candidates: 15 / 30 / 50 / 100.
4. **`LOTTERY_FALLBACK`**: when `E(h) = ∅`, route the prize to the normal split. Spec confirms this in §4.7.
5. **Component A↔D dependency**: extended cascade affects block timing distribution, which affects how often dominant accumulates exclusion-window state. Should be considered together in simulation but activation is still independent at the consensus level.

---

## 10 · Out of scope

The following are intentionally NOT part of V11:

- **Memory-Lock per-instance** (per-thread dataset, forcing dataset+scratchpad to be non-shareable). Studied separately; activation no earlier than block 12,000 if at all.
- **Useful Compute reward integration**. Tracked under M24 in the AI Engine roadmap.
- **Whale governance / staking weight on the lottery**. Out of PoW scope.
- **Pool resistance via VDF**. Future research direction (`docs/post_fork_gpu_pool_resistance.md`).

---

## 10.5 · Jackpot rollover — IN PHASE 2

**Decision update (DRAFT v3)**: jackpot rollover is part of Phase 2 (component D). The earlier "fallback to Gold Vault / PoPC Pool" rule has been replaced by the rollover mechanism described in §4.5 and §4.7. This section is retained as design rationale for reviewers.

### Mechanism (final spec — see §4 for normative text)
- New chain-state variable: `pending_lottery_amount` (stocks).
- Initialized to 0 at the activation height `V11_PHASE2_HEIGHT`.
- Update rule on each block at `height >= V11_PHASE2_HEIGHT`:
  - If `triggered(h)` is true and `E(h) ≠ ∅` → winner gets `lottery_share(h) + pending`; `pending := 0`.
  - If `triggered(h)` is true and `E(h) = ∅` → `pending += lottery_share(h)`; coinbase has 3 outputs with Gold Vault and PoPC Pool getting 0 for that block; no lottery winner output. The protocol-side allocation accumulates in the pending counter.
  - If `triggered(h)` is false → `pending` unchanged; coinbase has the standard 3 outputs (`50 / 25 / 25`).
- Validation: every full node recomputes `pending` from `V11_PHASE2_HEIGHT` (the consensus state initialised to 0 at fork activation, then updated block by block).
- Reorg: undo data per block records `pending_before_block`. On reorg, `pending` is restored to the pre-block value. This is the same model as UTXO undo data.
- Cap: **none**. The jackpot grows until a non-empty eligibility set clears it.

### Why kept in V11 Phase 2 (not deferred indefinitely)
- The fallback to Gold Vault / PoPC Pool was workable but messages "the lottery silently does nothing" to small miners — a bad UX signal.
- Rollover protects small networks: when most active miners are temporarily in cooldown, no protocol-side allocation is lost, and the next valid lottery becomes proportionally more attractive to small participants.
- The reorg-safe state-tracking work is non-trivial but is part of the Phase 2 implementation budget anyway (the lottery itself needs chain state for eligibility caching). Adding `pending` to that same undo-data mechanism is incremental, not a separate sprint.

### Implementation gate
Pass criteria for shipping rollover (subset of D's gates):
- G4.1c: unit test — empty `E(h)` on triggered block produces no winner output, increments `pending`, and the next triggered block with non-empty `E(h)` pays `share + pending`.
- G4.3b: multi-node testnet — simulated 100-block stretch with all miners in 30-block cooldown produces correct `pending` accumulation across all nodes.
- G4.4b: adversarial — block claiming `pending` payout when previous chain state had 0 pending must be rejected by all nodes.

### Constants the rollover fork would add
```cpp
inline constexpr int64_t  POP_LOTTERY_ROLLOVER_HEIGHT  = 10000;  // tentative
// pending_lottery_amount is part of chain state — not a constant.
// Serialization belongs in the block header or the chain undo data;
// final placement TBD when the rollover spec is opened.
```

These constants are NOT added to `params.h` for V11. They land at the same time as the rollover implementation, in a dedicated commit.

---

## 10.6 · Invariant — `pending_lottery_amount` lifecycle

This section names the three discrete lifecycle states of the jackpot rollover variable, so any Phase 2 implementer can reference them by name in code, tests and review comments. The behaviour is the same as §10.5 — only the naming is new.

`pending_lottery_amount` is a `uint64` chain-state variable that tracks SOST owed to future lottery winners when a triggered block has an empty eligibility set.

- **UPDATE** — on `is_lottery_block(h) == true` AND `compute_eligibility_set(h).empty()`:
  - `pending_lottery_amount += lottery_share_of_block` where `lottery_share_of_block = gold_vault_reward(h) + popc_pool_reward(h)` for that block's subsidy.
  - Coinbase: 3 outputs. Miner gets 50%; Gold Vault and PoPC Pool outputs receive 0; lottery slot empty.

- **PAYOUT** — on `is_lottery_block(h) == true` AND `!compute_eligibility_set(h).empty()`:
  - Winner receives `lottery_share_of_block + pending_lottery_amount`.
  - `pending_lottery_amount := 0`.
  - Coinbase: 4 outputs. Miner 50%; lottery winner gets the payout; Gold Vault and PoPC Pool outputs receive 0.

- **IDLE** — on `is_lottery_block(h) == false`:
  - `pending_lottery_amount` is **NEITHER read nor written**.
  - Coinbase: 3 outputs, normal `50 / 25 / 25` split.

**Implication for implementation**: a non-triggered block must never carry a lottery payout, even if `pending_lottery_amount > 0`. The jackpot is preserved across non-triggered blocks unchanged and waits for the next triggered block.

**Reorg safety**: `pending_lottery_amount` MUST be persisted in undo data so reorgs restore the value correctly. Disconnecting an UPDATE or PAYOUT block restores the saved `pending_before_block`. Disconnecting an IDLE block is a no-op for this variable. See §10.5 *Mechanism · Reorg* and the testnet gates G4.1c / G4.3b / G4.4b.

The same invariant is mirrored verbatim in `include/sost/lottery.h` (top-of-file comment) and pointed at from `src/lottery.cpp`, so any contributor reads it before touching consensus code.

---

## 11 · Constants required by V11 implementation

Constants are added to `include/sost/params.h` **at the time the corresponding component lands** (not before — adding placeholders without logic generates noise and risks shipping a binary with constants that nothing uses).

### 11.1 — Phase 1 constants (block 7,000) · LANDED

#### Component A — extended cascade
```cpp
inline constexpr int64_t  CASERT_V11_HEIGHT                = 7000;
// Drop table is hardcoded inline in src/pow/casert.cpp at the V11 branch
// (no separate table constants; the if/else if chain matches §1.2 exactly).
```

#### Component B — state-dependent dataset access
```cpp
// Reuses CASERT_V11_HEIGHT — same activation height, no new constant.
// The state-derived index uses bytes 8..11 of the SHA-256 state of the
// previous round (read_u32_le(state.data() + 8)). This offset is part of
// the consensus rule and must be the same in mining and validation.
```

### 11.2 — Phase 2 constants (TBD) · NOT YET LANDED

These constants are listed for design review only. They are **not** added to `params.h` until the corresponding Phase 2 implementation is verified, simulated, testnet-tested and adversarially audited. Activation height `V11_PHASE2_HEIGHT` is announced at that time.

#### Component C — SbPoW
```cpp
inline constexpr int64_t  V11_PHASE2_HEIGHT               = /* TBD */;  // shared by C and D
// Header v2 adds 33-byte miner_pubkey + 64-byte miner_signature.
// Signature scheme: BIP-340 Schnorr.
// Seed binding tag: "SEED2" (vs pre-fork "SEED").
// Sig message tag: "SOST/POW-SIG/v11".
```

#### Component D — lottery
```cpp
// Reuses V11_PHASE2_HEIGHT — same activation height as SbPoW.
inline constexpr int64_t  LOTTERY_HIGH_FREQ_WINDOW         = 5000;
inline constexpr int32_t  LOTTERY_REWARD_EXCLUSION_WINDOW  = 30;
// Trigger schedule (with H = V11_PHASE2_HEIGHT, W = LOTTERY_HIGH_FREQ_WINDOW):
//   For h in [H, H+W):       triggered  ⟺  (h - H) % 3 != 2     → 2-of-3 (bootstrap)
//   For h >= H + W:          triggered  ⟺  (h - H) % 3 == 0     → 1-of-3 (steady state)
// Selection seed tag: "SOST/POP-LOTTERY/v11"
// Eligibility set:    addrs with at least 1 block in [0, h-1]
//                     minus any block-reward winner in [h-W30, h-1]   (W30 = LOTTERY_REWARD_EXCLUSION_WINDOW)
//                     minus the miner of block h itself
// Winner pick:        deterministic (lex sort + uint64 mod)
```

#### Jackpot rollover (part of D)
```cpp
// pending_lottery_amount is part of chain state — not a constant.
// Initialized to 0 at V11_PHASE2_HEIGHT.
// Reorg-safe via per-block undo data (records pending_before_block).
// Cap: none. See §10.5 for the full rule.
```

These constants are documented here so reviewers can audit values against the banner copy and the spec text. The Phase 2 constants land in the implementation commit, in the same patch as the logic that uses them.

---

## 12 · Change log

| Date | Author | Change |
|---|---|---|
| 2026-05-02 | SOST consensus working group | DRAFT v1 — initial Phase 2 spec (SbPoW + lottery for block 10,000) |
| 2026-05-02 | SOST consensus working group | DRAFT v2 — restructured into V11 spec; SbPoW moved to block 7,000 with per-component independent activation; lottery eligibility widened to "≥1 block since genesis"; exclusion strengthened to "any block-reward winner in last 30"; added §5 honest mathematical analysis distinguishing Sybil regimes; added §11 constants list |
| 2026-05-02 | SOST consensus working group | DRAFT v2.1 — added §10.5 documenting jackpot rollover as a deferred future enhancement (NOT part of V11). Activation criteria proposed for block 10,000 conditional on V11 production data showing > 1 fallback per 1,000 blocks. |
| 2026-05-02 | SOST consensus working group | DRAFT v3 — restructured V11 into **two phases**. Phase 1 (block 7,000) ships A + B only (extended cASERT cascade + state-dependent dataset access). Phase 2 (height TBD, no calendar pressure) ships C + D (SbPoW + PoP lottery + jackpot rollover). Lottery frequency: 2-of-3 for the first `LOTTERY_HIGH_FREQ_WINDOW = 5000` blocks after Phase 2 activation, then 1-of-3 permanently. §10.5 jackpot rollover reclassified from "deferred fork" to "Phase 2 component D". §11 constants split into 11.1 (Phase 1, landed) and 11.2 (Phase 2, design-only). §3.7 / §4.8 activation rewritten to reference `V11_PHASE2_HEIGHT`. |
| 2026-05-02 | SOST consensus working group | DRAFT v3.1 — Component A cascade rewritten to a **linear formula** without an artificial cap (was: piecewise table capping at `drop = 6` for `elapsed >= 840 s`). New schedule: `drop = 1 + (elapsed − 540) / 60` for `elapsed >= 540 s`, growing without bound; floor enforced by existing `max(E7, base − drop)` clamp. Reaches E7 from any natural profile up to H35 within ~49 min, well inside the anti-stall window. Single source of truth: `compute_v11_cascade_drop` in `include/sost/pow/casert.h`, used by both miner and validator. |
| 2026-05-02 | SOST consensus working group | DRAFT v3.1.1 — doc fix: H35 → E7 worst case is **42 drops at 3000 s**, not 41 drops at 2940 s (off-by-one in the previous draft — 41 drops only reaches E6). §1.2 cascade table now lists both 2940 s (drop = 41, H35 → E6) and 3000 s (drop = 42, H35 → E7). Test `tests/test_casert_v11.cpp §5` updated to assert both. Added an explicit Phase 1 / Phase 2 boundary marker between §2 and §3 — Phase 2 components (SbPoW + lottery + jackpot rollover) do NOT activate at block 7000; their activation height is `V11_PHASE2_HEIGHT = INT64_MAX` (sentinel, effectively disabled). No code changes — cascade formula unchanged. |

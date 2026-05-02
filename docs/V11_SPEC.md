# V11 — Technical Specification

**Status**: DRAFT v2 · author: SOST consensus working group
**Target activation**: block **7,000** (per-component, conditional on testnet + Monte Carlo simulation gates)
**Phase B (block 10,000+)**: lottery-frequency change from 2-of-3 → 1-of-3, paired with PoPC Model A + B operational activation and dynamic fees (whitepaper-scheduled, separate doc).

This document specifies the four V11 consensus changes: extended cASERT cascade (A), state-dependent dataset access (B), SbPoW signature-bound proof (C), and Proof-of-Participation lottery (D). It is a design document, not implementation. Code lands only after the per-component simulation gates listed in §6 are passed.

---

## 1 · Component A — Extended cASERT cascade

### 1.1 Purpose
Replace the V10 continuous formula `drop = floor((elapsed - 540) / 60)` with a piecewise table that drops faster in the long tail (540-840 s window). This keeps block production closer to 600 s target after a slow block by accelerating the relief.

### 1.2 Schedule
```
elapsed <  540 s   →  drop 0   (no relief)
elapsed >= 540 s   →  drop 1
elapsed >= 600 s   →  drop 2
elapsed >= 660 s   →  drop 3
elapsed >= 720 s   →  drop 4
elapsed >= 780 s   →  drop 5
elapsed >= 840 s   →  drop 6
```

Floor stays at `E7` (CASERT_H_MIN). bitsQ controller, anti-stall, lag clamp and future-drift cap are **unchanged**.

### 1.3 Activation
At block `CASERT_V11_HEIGHT = 7000`, conditional on gate G1 (§6).

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
At block `V11_SBPOW_HEIGHT = 7000`, conditional on gate G3 (§6). Independent from A, B, D.

---

## 4 · Component D — Proof-of-Participation lottery

### 4.1 Phasing schedule

| Phase | Heights | Trigger rule | Source of lottery prize |
|---|---|---|---|
| **Phase A — bootstrap** | 7,000 ≤ h < 10,000 | 2 of every 3 blocks | 50% of block subsidy (= 25% Gold Vault + 25% PoPC Pool) redirected to lottery winner |
| **Phase B — steady state** | h ≥ 10,000 | 1 of every 3 blocks | same prize composition |

Phase B is paired with PoPC Model A + B operational activation and dynamic-fee policy (whitepaper-scheduled — separate spec).

### 4.2 Trigger function

```
triggered(h) =
    if 7000 ≤ h < 10000:  (h - 7000) % 3 != 2     # 2-of-3
    if h ≥ 10000:          (h - 10000) % 3 == 0   # 1-of-3
    else:                   false
```

Phase A pattern (L = lottery, N = normal):
```
height: 7000 7001 7002 7003 7004 7005 …
state:  L    L    N    L    L    N    …
```

Phase B pattern:
```
height: 10000 10001 10002 10003 10004 …
state:  L     N     N     L     N     …
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
At block 7,000 (phase A) with frequency change at 10,000 (phase B), conditional on gate G4 (§6). Independent from A, B, C.

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

## 11 · Constants required by V11 implementation

The following constants must be added to `include/sost/params.h` **at the time the corresponding component lands** (not before — adding placeholders without logic generates noise and risks shipping a binary with constants that nothing uses).

### Component A — extended cascade
```cpp
inline constexpr int64_t  CASERT_V11_HEIGHT                = 7000;
// Drop table is hardcoded inline in src/pow/casert.cpp at the V11 branch
// (no separate table constants; the if/else if chain matches §1.2 exactly).
```

### Component B — state-dependent dataset access
```cpp
// Reuses CASERT_V11_HEIGHT — same activation height, no new constant.
// The state-derived index uses bytes 8..11 of the SHA-256 state of the
// previous round (read_u32_le(state.data() + 8)). This offset is part of
// the consensus rule and must be the same in mining and validation.
```

### Component C — SbPoW
```cpp
inline constexpr int64_t  V11_SBPOW_HEIGHT                 = 7000;  // same height
// Header v2 adds 33-byte miner_pubkey + 64-byte miner_signature.
// Signature scheme: BIP-340 Schnorr.
// Seed binding tag: "SEED2" (vs pre-fork "SEED").
// Sig message tag: "SOST/POW-SIG/v11".
```

### Component D — lottery
```cpp
inline constexpr int64_t  POP_LOTTERY_HEIGHT_PHASE_A       = 7000;
inline constexpr int64_t  POP_LOTTERY_HEIGHT_PHASE_B       = 10000;
inline constexpr int32_t  LOTTERY_REWARD_EXCLUSION_WINDOW  = 30;
// Phase A trigger:  (h - 7000) % 3 != 2     → 2-of-3
// Phase B trigger:  (h - 10000) % 3 == 0    → 1-of-3
// Selection seed tag: "SOST/POP-LOTTERY/v11"
// Eligibility set:    addrs with at least 1 block in [0, h-1]
//                     minus any block-reward winner in [h-W, h-1]
//                     minus the miner of block h itself
// Winner pick:        deterministic (lex sort + uint64 mod)
```

These constants are documented here so reviewers can audit values against the banner copy and the spec text. The actual code addition happens in the implementation commit, in the same patch as the logic that uses them.

---

## 12 · Change log

| Date | Author | Change |
|---|---|---|
| 2026-05-02 | SOST consensus working group | DRAFT v1 — initial Phase 2 spec (SbPoW + lottery for block 10,000) |
| 2026-05-02 | SOST consensus working group | DRAFT v2 — restructured into V11 spec; SbPoW moved to block 7,000 with per-component independent activation; lottery eligibility widened to "≥1 block since genesis"; exclusion strengthened to "any block-reward winner in last 30"; added §5 honest mathematical analysis distinguishing Sybil regimes; added §11 constants list |

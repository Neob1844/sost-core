# V11 — Technical Specification

**Status**: DRAFT v3.8 · author: SOST consensus working group

**Phase split (current decision)**:

| Phase | Components | Activation height | Status |
|---|---|---|---|
| **Phase 1** | A (extended cASERT cascade) + B (state-dependent dataset access) | **block 7,000** | code complete, tests written, awaiting compilation gate |
| **Phase 2** | C (SbPoW signature-bound proof) + D (PoP lottery + jackpot rollover) | **block 7,100** (set by C13) | implementation complete · all C2-C9 gates PASS · C11/C12 wired the production miner · C13 finalised the activation height |

**Activation rationale.** Phase 2 ships at block 7,100 — separated from Phase 1 (block 7,000) by 100 blocks (~16-17h at the 600-second target). The spacing avoids overlapping two consensus changes at the same height while still keeping the deployment window tight enough for a single operational shift. Phase 1 lights up first; the team observes its behaviour, propagates Phase 2 binaries, and ANNs before Phase 2 fires.

**Phase 2 lottery frequency schedule** (when activated at height `H_PHASE2`):

```
First 5,000 blocks after Phase 2 activation:  2 of every 3 blocks  (high-freq bootstrap)
After H_PHASE2 + 5000, permanently:           1 of every 3 blocks  (steady state)
```

This document specifies the four V11 consensus changes: extended cASERT cascade (A), state-dependent dataset access (B), SbPoW signature-bound proof (C), and Proof-of-Participation lottery (D). Components A and B activate at block 7,000 (Phase 1). Components C and D activate at block 7,100 (Phase 2, set by C13).

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

## 1.5 · Slingshot — single-shot bitsQ relief

### 1.5.1 Purpose
Phase 1 (§1) addresses the **profile** side of recovery — when a block runs slow, the cASERT cascade lowers the equalizer profile so the next block is easier to solve. But the **bitsQ** controller still tracks the avg288 of the last 288 intervals, which is slow-moving. After a single 30+ minute block the chain remains schedule-behind and bitsQ has barely moved, so the **next** block is still mined against full difficulty even though the chain just visibly stalled.

Slingshot adds a **one-shot bitsQ drop of 12.5 %** for the block that immediately follows a slow block. It is the bitsQ-side counterpart to the cASERT cascade: cascade drops the profile, Slingshot drops the difficulty — together they buy the chain a meaningful chance to recover schedule on the very next block.

### 1.5.2 Rule
For a candidate block at `next_height` with chain history `chain` (tip = `chain.back()`):

```
if next_height >= V11_SLINGSHOT_HEIGHT (= 7000) and chain.size() >= 2:
    prev_elapsed = chain.back().time - chain[size-2].time
    bitsQ_avg288 = (existing avg288-derived value, after MIN/MAX clamp)
    if prev_elapsed > SLINGSHOT_THRESHOLD_SECONDS (1800):
        relieved   = bitsQ_avg288 * (10000 - SLINGSHOT_DROP_BPS) / 10000
                   = bitsQ_avg288 * 8750 / 10000   # 12.5 % off
        bitsQ_for_block = max(MIN_BITSQ, relieved)
    else:
        bitsQ_for_block = bitsQ_avg288
else:                       # pre-fork or chain too small
    bitsQ_for_block = bitsQ_avg288   # unchanged
```

Comparison is **strict `>`**: `prev_elapsed == 1800` does not trigger.

### 1.5.3 Worked example
- Chain tip at height 7,003, `prev_elapsed = 2400 s` (40 min)
- Normal avg288 says `bitsQ_avg288 = 1,000,000`
- Slingshot fires: `bitsQ = 1,000,000 * 8750 / 10000 = 875,000`
- Block 7,004 is mined against the relieved difficulty
- Block 7,004 takes 580 s (back to normal)
- For block 7,005: `prev_elapsed = 580` → Slingshot **does not** fire; bitsQ comes purely from avg288 (which now incorporates the recent recovery)

### 1.5.4 Safety constraints (consensus invariants)
1. **Single-shot per block**: only the block immediately following a slow block is relieved. The next block recomputes avg288 fresh; if its own previous block is fast, no relief is applied.
2. **No cumulative effect**: the drop never compounds. Even three consecutive slow blocks each receive an independent 12.5 % drop, **always computed against the current avg288 result, not against the previously-relieved bitsQ**.
3. **Floor preserved**: `relieved` is clamped to `MIN_BITSQ` after the multiplication, so Slingshot can never push difficulty below the absolute floor.
4. **Idempotent across miner and validator**: both sides route through `casert_next_bitsq` (single source of truth in `src/pow/casert.cpp`). No duplicated logic anywhere.
5. **Pre-fork unchanged**: at `next_height < V11_SLINGSHOT_HEIGHT` the avg288 path runs to completion and returns without any Slingshot post-processing — bit-for-bit identical to pre-Phase-3 behaviour.
6. **Short-chain guard**: when `chain.size() < 2` the rule is skipped (we cannot compute `prev_elapsed`); for genesis-adjacent heights the V6++ branch itself requires `chain.size() >= 10`, so Slingshot never reaches a chain too small to produce a meaningful avg288.

### 1.5.5 Activation
At block `V11_SLINGSHOT_HEIGHT = 7000`, paired with Phase 1 components A and B. No independent gate — Slingshot is part of the Phase 1 hard fork.

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

**RPC transport (submitblock).** The miner submits the v2 fields to the node as additional JSON keys on the existing `submitblock` payload:

| key                | type   | meaning                                                  |
|--------------------|--------|----------------------------------------------------------|
| `version`          | int    | header version (1 or 2; defaults to 1 if absent)         |
| `miner_pubkey`     | string | 66-hex-char (33-byte) compressed secp256k1 pubkey (v2)  |
| `miner_signature`  | string | 128-hex-char (64-byte) BIP-340 Schnorr signature (v2)   |

The `version`/pubkey/signature triple feeds both the block_id recompute (so v2 hashes the SbPoW extension) and the consensus `ValidateSbPoW` check. Pre-Phase-2 v1 submissions omit pubkey/signature and the parser defaults `version` to 1 — so legacy block submitters keep working unchanged at heights below `V11_PHASE2_HEIGHT`.

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
**Phase 2 — block 7,100** (set by C13). SbPoW requires non-trivial integration (header v2 serialization, wallet keystore access, libsecp256k1 Schnorr verification, cross-node validation) that was deliberately scheduled separately from Phase 1 (block 7,000) so the two forks could be observed independently in production. The 100-block window (~16-17h at the 600-second target) gives operators time to update binaries between the two activation heights. Phase 2 activation height `V11_PHASE2_HEIGHT = 7100` is shared with component D (lottery). All `V11_SBPOW_HEIGHT` references in §3.2/§3.3/§3.5 of this document refer to that same `V11_PHASE2_HEIGHT` value. Gates G3.1, G3.2, G3.3 + G4.1–G4.5 (§6) all PASS as of C9.

---

## 4 · Component D — Proof-of-Participation lottery

### 4.1 Phasing schedule

The lottery activates at `V11_PHASE2_HEIGHT = 7100` (see §4.8). From that height:

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
         in [h - LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW, h-1] }
```

**C7.1 revision (was a 3-clause rule; now 2 clauses):** the third clause `AND addr is not the miner of block h itself` has been removed. The current block's winner CAN now enter the lottery iff their address passes the recent-winner cooldown — i.e. they did not also win any of the previous `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` blocks. Rationale: the prior C6 rule penalised a miner for finding the current block even after a long silence; under C7.1 the rule is simpler ("if you didn't win in the previous N blocks, you participate") and a miner who keeps winning is naturally excluded by the cooldown.

Constants:
- `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW = 5` blocks (C5 default — provisional, **C9 confirmation pending**). Was `30` in earlier drafts; revised after the preliminary Monte Carlo in `docs/V11_PHASE2_DESIGN.md` §5.4 showed `cap_30` had ~12 % rollover rate and the largest sybil-incentive delta among evaluated variants while honest-miner median lottery share was essentially flat across all windows.
- Eligibility floor: "ever mined at least one block since genesis" — opens the pool wide and removes the prior 30-block-mining-history requirement.
- Exclusion: ANY block-reward winner (miner subsidy OR lottery prize) in the last `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` blocks. Stronger than excluding only past lottery winners.

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

### 4.5 Coinbase construction (revised in C8 — variable output count)

Phase 2 redirects the **entire 50% protocol-side allocation** (Gold Vault + PoPC Pool) to the lottery on triggered blocks. The PoW miner always keeps the other 50% (subsidy + all transaction fees). On triggered blocks the GOLD and POPC outputs are **omitted entirely** — emitting them with zero amounts would violate the existing CB R5 rule (`amount > 0`) and waste chain-state bytes for no semantic gain. Output count therefore varies by trigger kind:

Normal (not triggered) block — 3 outputs, unchanged from Phase 1:
```
output[0]  =  miner subsidy            (50% of subsidy + fees)  → block miner
output[1]  =  Gold Vault budget        (25%)                    → Gold Vault
output[2]  =  PoPC Pool budget         (25%)                    → PoPC Pool
```

Triggered + non-empty eligibility (PAYOUT) — 2 outputs:
```
output[0]  =  miner subsidy            (50% of subsidy + fees)              → block miner
output[1]  =  lottery prize            (lottery_share + pending_before)     → winner_addr
                                       where lottery_share = 50% of subsidy + fees
```

Triggered + empty eligibility (UPDATE) — 1 output:
```
output[0]  =  miner subsidy            (50% of subsidy + fees)  → block miner
                                       (chain-state pending_lottery_amount += lottery_share)
```

Fees stay with the block miner (`output[0]`) on every block, triggered or not.

### 4.6 Validation rules

A coinbase at `height >= V11_PHASE2_HEIGHT` is valid iff exactly one of the three shapes above matches the trigger kind:

1. Non-triggered → 3 outputs MINER/GOLD/POPC with the canonical 25/25 split, vault PKHs match the constitutional addresses (CB6 unchanged).
2. Triggered + non-empty `E(h)` → 2 outputs. `output[1].type == OUT_COINBASE_LOTTERY` (0x04). `output[1].amount == lottery_share + pending_before` exactly (no miner discretion). `output[1].pubkey_hash == winner_addr` derived per §4.4 from the chain's prefix at `h-1`.
3. Triggered + empty `E(h)` → 1 output (MINER only). The chain-state variable `pending_lottery_amount` advances by `lottery_share`.
4. Miner subsidy `output[0]` always = 50% of `subsidy(h) + total_fees`.
5. **Emission invariant** (height-gated, Phase 2):
   ```
   sum(coinbase_outputs) + (pending_after - pending_before) == subsidy + fees
   ```
   This holds trivially for non-triggered blocks (`Δpending == 0`), holds on UPDATE because the withheld `lottery_share` is recorded in chain state instead of an output, and holds on PAYOUT because the lottery output equals `lottery_share + pending_before` and `pending_after == 0`.

Failure of any rule → block rejected (consensus codes CB11_LOTTERY_SHAPE, CB12_LOTTERY_AMOUNT, CB13_LOTTERY_WINNER, CB14_LOTTERY_INVARIANT, plus the unchanged CB1-CB10 for the common header).

Pre-`V11_PHASE2_HEIGHT` blocks fall through to the legacy CB1-CB10 path with no behaviour change. With `V11_PHASE2_HEIGHT == 7100` (params.h, set by C13), the Phase 2 path is unreachable for chain heights below 7,100 and active from height 7,100 onwards.

### 4.7 Edge cases

| Case | Rule |
|---|---|
| `E(h) = ∅` (no eligible address) | UPDATE shape — coinbase has 1 output (MINER only). `pending_lottery_amount += lottery_share`. The next triggered block with non-empty `E(h)` pays `lottery_share + pending_before` to its winner and resets `pending_lottery_amount` to 0 (§10.5 / §10.6). |
| `\|E(h)\| = 1` | The single eligible address auto-wins (PAYOUT shape, 2 outputs). |
| Tie (deterministic seed produces collision) | Impossible by construction — `winner_idx` is a single integer. The lex-sort of `E(h)` removes any address-ordering ambiguity. |
| Miner of block `h` is in `E(h)` | Allowed since C7.1. The current block's miner is no longer auto-excluded; they pass §4.3 iff they did not also win any of the previous `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` blocks. |
| Network reorg after lottery payout | Standard reorg handling: the alternate chain's lottery selection is recomputed from its own prev block. `pending_lottery_amount` is restored from `BlockUndo::pending_lottery_before` (in-memory undo data per disconnected block). Coinbase maturity (1,000 blocks) protects against the winner spending an orphaned prize. |

### 4.8 Activation
**Phase 2 — block 7,100** (set by C13). The lottery activates at `V11_PHASE2_HEIGHT = 7100`, separated from Phase 1 (block 7,000) by 100 blocks (~16-17h at the 600-second target). The 5,000-block 2-of-3 bootstrap window covers blocks 7,100 to 12,099; 1-of-3 steady state begins at block 12,100 (first triggered permanent block: 12,102). Gates G4.1 through G4.5 (§6) all PASS as of C9 (formal Monte Carlo + accounting + reorg-safe undo).

---

## 5 · Mathematical impact on lottery distribution

This section is **honest** about the redistribution mechanic. The lottery is not a magic equalizer — its effectiveness depends on how the dominant operator chooses to manage their addresses.

### 5.1 Notation
- `α` = dominant's hashrate share (currently ≈ 0.70 across windows, peaks ≈ 0.92 in 40-block samples)
- `W` = `LOTTERY_REWARD_EXCLUSION_WINDOW` = 30
- `N_dom` = number of distinct addresses the dominant operates
- `S` = number of distinct small-miner addresses with at least 1 block since genesis (currently ≈ 5-8)

### 5.2 Regime 1 — Dominant uses 1-3 addresses (current behaviour)

The address(es) the dominant uses to mine blocks are mostly excluded by the `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` reward window (W = 5 in the C5 default; C9 may revise). They keep winning blocks at hashrate-proportional rate, so they sit in cooldown for most of the window. Result:

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

The dominant generates many addresses and rotates per block. After the first `W = LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` blocks, the addresses that won blocks in the last `W` are `min(N_dom, α·W)` excluded. The rest are eligible. (Pre-C5 drafts hard-coded `W = 30`; C5 lowered the default to `5` based on the preliminary Monte Carlo — the `α·W` figures below scale accordingly.)

```
Dominant addresses in E(h):     ≈  max(0, N_dom − α·W)     # ones not in cooldown
                                ≈  N_dom − 3.5             # if α = 0.70, W = 5
                                                            # (vs N_dom − 21 in the W = 30 draft)
Eligibility set size:           ≈  (N_dom − α·W) + S
Dominant lottery share:         ≈  (N_dom − α·W) / [(N_dom − α·W) + S]
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
3. **`LOTTERY_REWARD_EXCLUSION_WINDOW`**: revised C5 default = 5 (was 30). Pending C9 Monte Carlo confirmation. Candidates considered: 5 / 15 / 30 / 50 / 100.
4. ~~**`LOTTERY_FALLBACK`**: when `E(h) = ∅`, route the prize to the normal split.~~ **RESOLVED in C7/C8**: empty eligibility no longer falls back to Gold/PoPC. The lottery share accumulates in chain-state `pending_lottery_amount` and is paid out on the next triggered block with non-empty `E(h)`. See §4.5, §4.7, §10.5 / §10.6 for the normative spec.
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
- Update rule on each block at `height >= V11_PHASE2_HEIGHT` (revised in C8 — variable output count, see §4.5):
  - If `triggered(h)` is true and `E(h) ≠ ∅` (PAYOUT) → winner gets `lottery_share(h) + pending`; `pending := 0`. Coinbase has **2 outputs**: MINER + OUT_COINBASE_LOTTERY.
  - If `triggered(h)` is true and `E(h) = ∅` (UPDATE) → `pending += lottery_share(h)`; no lottery winner output. Coinbase has **1 output** (MINER only). GOLD and POPC outputs are omitted entirely — emitting them with zero amounts would violate CB R5. The protocol-side allocation accumulates in the pending counter.
  - If `triggered(h)` is false (IDLE) → `pending` unchanged; coinbase has the standard **3 outputs** (`50 / 25 / 25`).
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
- G4.3b: multi-node testnet — simulated 100-block stretch with all miners in `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW`-block cooldown produces correct `pending` accumulation across all nodes.
- G4.4b: adversarial — block claiming `pending` payout when previous chain state had 0 pending must be rejected by all nodes.

### Constants used by the rollover implementation
```cpp
// Rollover activates with the rest of Phase 2.
inline constexpr int64_t  V11_PHASE2_HEIGHT  = 7100;  // params.h, set by C13
// pending_lottery_amount is part of chain state — not a constant.
// Persisted on each StoredBlock as `pending_lottery_after`
// (chain.json with backward-compat default 0). BlockUndo carries the
// pre-block value as `pending_lottery_before` for reorg-safe undo.
```

These constants are part of `params.h`. C10 set `V11_PHASE2_HEIGHT = 10000`; C13 reduced it to `7100` after Phase 1 shipped on the live chain.

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

### 11.2 — Phase 2 constants (block 7,100) · LANDED

These constants are in `params.h`. C10 set `V11_PHASE2_HEIGHT = 10000` after C2-C9 cleared their gates; C13 reduced it to `7100` after Phase 1 (block 7,000) shipped on the live chain.

#### Component C — SbPoW
```cpp
inline constexpr int64_t  V11_PHASE2_HEIGHT               = 7100;  // shared by C and D
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
// Selection seed tag: "SOST_LOTTERY_V11"
// Eligibility set:    addrs with at least 1 block in [0, h-1]
//                     minus any block-reward winner in
//                       [h - LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW, h-1].
// (C7.1: the miner of block h itself is NO LONGER auto-excluded —
//  they pass iff they were not also a winner in the cooldown window.)
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
| 2026-05-02 | SOST consensus working group | DRAFT v3.2 — recent-winner exclusion window provisional default revised from 30 to **5** blocks (`LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW = 5`) following the preliminary Monte Carlo in `docs/V11_PHASE2_DESIGN.md` §5.4. `cap_30` had ~12 % rollover rate and the largest sybil-incentive delta in the realistic network shape; `cap_5` zeros out the dominant's no-sybil lottery share with ~0 % rollover rate and a smaller sybil-incentive delta. **Final value pending C9 confirmation.** §4.3, §5.2, §5.3 prose updated to reference the constant rather than a hard-coded 30. Public banner updated to v83 with matching wording. No consensus behaviour change for any height < `V11_PHASE2_HEIGHT` (which remains `INT64_MAX`). |
| 2026-05-02 | SOST consensus working group | DRAFT v3.3 — eligibility rule simplified (C7.1). The third clause "addr is not the miner of block h itself" has been **removed** from §4.3. Under the C7.1 rule, the current block winner CAN enter their own block's lottery iff they did not also win any of the previous `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` (= 5) blocks. Rationale: the prior auto-exclusion penalised a miner for finding the current block even after a long silence; the simpler "if you didn't win in the previous N blocks, you participate" rule is more permissive in benign cases and equivalent in the common case (a miner who keeps winning is naturally excluded by the cooldown). `compute_lottery_eligibility_set()` no longer consumes its `current_miner_pkh` parameter (kept for API source-compat). Public banner updated to v85. No consensus behaviour change for any height < `V11_PHASE2_HEIGHT` (still `INT64_MAX`). |
| 2026-05-02 | SOST consensus working group | DRAFT v3.4 — coinbase shape + persisted lottery state landed in C8. §4.5 / §4.6 / §4.7 / §10.5 rewritten to match the implemented variable-output-count shape (3 / 1 / 2 outputs for non-triggered / UPDATE / PAYOUT) — the earlier "3 outputs with Gold and PoPC = 0" wording was inconsistent with the existing CB R5 rule (`amount > 0` for every coinbase output). On triggered blocks the **full** protocol-side allocation (Gold Vault 25% + PoPC Pool 25%, together 50% of the block reward) is redirected to lottery / pending — the PoW miner's 50% share is never touched. Open question §9.4 (`LOTTERY_FALLBACK`) marked as RESOLVED. New consensus error codes CB11_LOTTERY_SHAPE / CB12_LOTTERY_AMOUNT / CB13_LOTTERY_WINNER / CB14_LOTTERY_INVARIANT. New StoredBlock field `pending_lottery_after` (persisted in chain.json with backward-compat default 0) and BlockUndo field `pending_lottery_before` (in-memory undo). Public banner updated to v88 (v11-phase2 branch) — phrasing changed from "50% of the protocol-side allocation" to "the full protocol-side allocation … 50% of the block reward" to remove ambiguity. No consensus behaviour change for any height < `V11_PHASE2_HEIGHT` (still `INT64_MAX`). |
| 2026-05-02 | SOST consensus working group | **DRAFT v3.5 — Phase 2 activation height set to block 10,000** (C10). `V11_PHASE2_HEIGHT` changed from `INT64_MAX` to `10000` in `include/sost/params.h`. Rationale: Phase 1 (cASERT cascade + state-dependent dataset) activates at block 7,000; spacing Phase 2 by ~3,000 blocks (~3 weeks at the 600-second target) keeps the two hard forks observable independently in production and gives miners a full update window. C9 Monte Carlo + accounting + reorg + determinism gates all PASS (`docs/V11_PHASE2_MONTE_CARLO.md`). §3.7 / §4.8 activation paragraphs rewritten; §10.5 + §11.2 constants table updated; the in-code `INT64_MAX` sentinel is retained as a TEST-ONLY value used by unit tests to exercise the dormant branch with a literal. The lottery's bootstrap window is blocks 10,000–14,999 (2-of-3); permanent steady state begins at block 15,000 (1-of-3). Caveat retained: the lottery improves redistribution but is NOT Sybil-proof (cap=5 chosen by C9 Monte Carlo; ~100 sybil pre-legitimated addresses defeat eligibility-based defences regardless of cap). On triggered blocks the full protocol-side allocation (50% of block reward) is redirected to the lottery winner; the PoW miner's 50% share is never touched. **Operational note**: production miners MUST update node + miner binaries before block 10,000 — see `docs/V11_PHASE2_RELEASE_NOTES.md`. The `sost-miner.cpp` mining loop still needs an eligibility-set RPC wired to `build_phase2_payout_coinbase_tx` / `build_phase2_update_coinbase_tx`; that wiring is a blocking follow-up commit before the chain reaches block 10,000. Public banner bumped to v92 with the activation announcement. |
| 2026-05-02 | SOST consensus working group | DRAFT v3.6 — C11 wired the production miner loop to the `getlotterystate` RPC (NORMAL / UPDATE_EMPTY / PAYOUT coinbase shape dispatch). C12 wired the SbPoW signed v2 header through the miner submitblock JSON path (version, miner_pubkey, miner_signature) and the node-side parser. Activation height stays at 10,000 in this entry. |
| 2026-05-02 | SOST consensus working group | **DRAFT v3.7 — Phase 2 activation height reduced to block 7,100** (C13). `V11_PHASE2_HEIGHT` changed from `10000` to `7100` in `include/sost/params.h` after Phase 1 (block 7,000) shipped on the live chain and the C11/C12 miner update path was confirmed deployable. Rationale: Phase 1 + Phase 2 are separated by 100 blocks (~16-17h at the 600-second target) — enough to observe Phase 1 in production, propagate binaries across the miner pool and ANN the activation, while keeping the deployment window tight enough for a single operational shift. The Phase 2 lottery bootstrap window is now blocks 7,100–12,099 (2-of-3); permanent steady state begins at block 12,100 (first triggered permanent block: 12,102, since 12,100%3==1, 12,101%3==2, 12,102%3==0). All boundary tests (test_lottery_frequency, test_lottery_eligibility, test_lottery_rollover, test_coinbase_phase2) updated for the new heights. §3.7 / §4.8 activation paragraphs rewritten; §11.2 constants table updated. **Operational note (still in force)**: MINERS MUST UPDATE node + miner binaries before block 7,100. Old miners will produce invalid coinbase on triggered Phase 2 blocks (CB11_LOTTERY_SHAPE) AND missing SbPoW signature (rejected by ValidateSbPoW). Public banner bumped to v94 with the final activation announcement. |
| 2026-05-02 | SOST consensus working group | **DRAFT v3.8 — Slingshot single-shot bitsQ relief (Phase 3) added to Phase 1 hard fork** (§1.5). New constants in `include/sost/params.h`: `V11_SLINGSHOT_HEIGHT = 7000`, `SLINGSHOT_THRESHOLD_SECONDS = 1800` (30 min), `SLINGSHOT_DROP_BPS = 1250` (12.5 %). Implementation lives in the V6++ branch of `casert_next_bitsq()` in `src/pow/casert.cpp` — the same single-source-of-truth function called by both miner and validator, so post-Slingshot bitsQ is identical on both sides by construction. Rule: at `next_height >= V11_SLINGSHOT_HEIGHT`, if the previous block's elapsed time exceeded 1800 s (strict `>`), the just-computed avg288-derived bitsQ is multiplied by `(10000 - 1250) / 10000 = 0.875` and re-clamped to `MIN_BITSQ`. Single-shot semantics: the relief applies to one block only; the next block recomputes avg288 fresh and only re-applies the relief if its own previous block also exceeded the threshold. **No ratcheting**: each drop is computed against the current avg288 result, never against a previously-relieved value, so three consecutive slow blocks produce three independent 12.5 % drops, never `0.875³ ≈ 67 %`. Activates alongside Phase 1 components A and B at block 7,000 (no independent gate — Slingshot is part of the Phase 1 hard fork). New test binary `test-slingshot` (registered in `CMakeLists.txt` next to `test-casert-v11`) covers: pre-fork unchanged · 1799 / 1800 / 1801 boundary · drop math at 5 seed values · `MIN_BITSQ` floor clamp · single-shot reset · no-ratcheting (verified across 3-block sequence using shifted-height twin chains so `prev_bitsq` matches and the avg288 path is identical) · genesis edge cases (size 0 and size 1) · 10× determinism. All 26 assertions PASS in both `-DSOST_ENABLE_PHASE2_SBPOW=ON` and `OFF` builds; `casert`, `casert-v11`, `convergencex-v11`, `coinbase-phase2`, `sbpow-*` all PASS with no regressions. Pre-existing failures (`bond-lock`, `checkpoints`, `popc`, `escrow`, `dynamic-rewards`) reproduce identically before and after the change — confirmed unaffected. Public banner stays at v100 (Slingshot announcement). |

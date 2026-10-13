# `--full-verify` and the early mainnet chain (heights 1..3300)

Status: **PARTIALLY VERIFIABLE BY DESIGN — decided and implemented (§8).**
No consensus rule changed. The default sync path (hard checkpoints +
assumevalid) is byte-for-byte unchanged and still accepts the canonical chain.

- Plain `--full-verify` stays strict. It now derives each transcript-less
  block's profile from `stab_*` (fail closed), runs every check that needs no
  transcript, classifies the block `UNVERIFIABLE_MISSING_HISTORICAL_DATA` and
  rejects it. Mainnet block 1 is still the first block it cannot accept.
- `--full-verify-anchored-history` (new, opt-in, implies `--full-verify`)
  accepts mainnet 1..3300 as `ASSUMED_FROM_HISTORICAL_RULE` once those checks
  pass. Block identity is pinned to the compiled-in hard checkpoints, and the
  node enforces their exact hashes in this mode. Every block from 3301 on must be
  `VERIFIED` (full Transcript V2).
- The sequential-work evidence for 1..3300 is never reported as verified. Only
  an offline full recompute (Option A, `cx-reverify`) can supply it.

Sections 1-7 record the original finding. §1 and §4 describe the behaviour
**before** this change; line numbers there refer to the parent commit
`11dc2fcc`.

## 1. The failing check

`sost-node --full-verify` syncing the real mainnet chain from genesis (local
server only) rejects block 1 every time:

```
[BLOCK-V2] Parsed: x_bytes=128 final_state=35330704b0b92bc5 segments_root=ebdd4475b59c6815 cp_leaves=0 seg_proofs=0 rw=0
[BLOCK] height=1: profile_index missing, assuming B0 (pre-V3 legacy)
[CX-VERIFY] Phase 1: sanity (x_bytes_len=128, n*4=128, cp_leaves=0)
[CX-VERIFY] Phase 1 FAILED: checkpoint_leaves empty
[BLOCK] REJECTED: CX Transcript V2 verification failed
```

- Check: `verify_cx_proof()` Phase 1 sanity, `src/pow/convergencex.cpp:596`
  (`if (checkpoint_leaves.empty()) ... return false;`). The Phase 1 line only
  prints with `--verbose`.
- Rejection: `src/sost-node.cpp:7807` (`[BLOCK] REJECTED: CX Transcript V2
  verification failed`), reached because `can_skip_cx_recomputation()`
  (`include/sost/checkpoints.h`) returns `false` as soon as
  `full_verify_mode` is set.
- Values: block 1 `02cd911c…6233d`, `cp_leaves=0 seg_proofs=0 rw=0`.

## 2. Why the default path accepts block 1

At `src/sost-node.cpp:7787-7795`, block 1 is below the assumevalid height
(3554, hash `5034a648…07ca`) and is treated as anchored, and the block-3300 hash
is a hard checkpoint. `can_skip_cx_recomputation()` returns `true`, so Layer 8
(CX transcript verification, `docs/verification-pipeline.md`) is skipped. Every
other layer (structure, time, cASERT `bits_q`, PoW target, coinbase split,
transactions, UTXO) still runs. `g_full_verify_mode` disables that skip, and
also the `trusted_block` / `is_trusted_height` shortcuts at lines 6688 and 7580.

## 3. Root cause: the transcripts were never stored

In the real chain, **every block from 0 to 3300** has no `checkpoint_leaves`,
`segment_proofs`, `round_witnesses` or `profile_index` field. From 3301 on, all
blocks carry them (16 checkpoint leaves, 12 round witnesses).

Cause: before commit `07e49b16` ("fix: save complete Transcript V2 proof data in
chain.json", 2026-04-08 01:23 +0200), `save_chain_internal()` rebuilt each
block's JSON field by field and dropped those four fields. After a restart, the
truncated JSON was all a node held and all it served to peers. Block 3300 was
mined at 2026-04-07 21:51 UTC, before the fix. Block 3301 was mined at
2026-04-08 21:34 UTC, after it.

The miners did produce the transcripts. Transcript V2 and `verify_cx_proof` have
existed since the regenesis (`d5df18f6`, `69f2b0ce`, 2026-03-15), and the nodes
of the time verified them when they first accepted each block. The data was
then lost at persistence. Unless someone kept an archive of the original
`submitblock` JSON, no node on the network can serve it.

This is **tooling / data-retention debt, not consensus debt.** No consensus rule
is missing or wrong for this window, and no height-aware historical *consensus*
rule is needed. What is missing is the input that the full verifier needs.

It is not the same as the two known historical exception classes (19 cASERT
`bits_q`/profile blocks and 47 parameter-table blocks at 4715-5038). Those apply
above 3300 and are handled by `historic_exception_at()` /
`historic_param_exception_at()`. The full-verify replay of 3301..30428 below
goes through them.

## 4. A second, latent defect in the same window

When `profile_index` is missing below `CASERT_V3_FORK_HEIGHT` (4100), the node
assumes B0 (`src/sost-node.cpp:7602-7614`). The commit binds the profile byte,
and the stored `stab_*` parameters show what each miner used:

| Profile (legacy table) | Blocks in 1..3300 | First example |
|---|---:|---|
| B0 `{1,4,4,185}` | 2347 | 1 |
| E1 `{1,4,4,205}` | 565 | 339 |
| H1 `{1,5,4,170}` | 353 | 931 |
| H2 `{1,5,5,160}` | 34 | 1001 |
| E4 `{1,2,3,280}` | 1 | 2 |

For the 953 non-B0 blocks the B0 assumption does not bind (Phase 5 would fail),
even if the transcripts were recovered. Any future full-verify path for this
window must derive the profile from `stab_*`. Each stored parameter set matches
exactly one legacy-table row, and the commit then authenticates the choice.
Default sync never reaches this code for these heights.

## 5. What can still be verified without the transcript

For all 3300 blocks, verified with the real chain
(`scripts/verification/full_verify_early_chain.sh scan`):

- the profile derived from `stab_*` matches exactly one legacy-table row;
- **commit binding** (verify_cx_proof Phases 4-5: header, seed, final_state,
  x_bytes, checkpoints_root, segments_root, metric and profile byte)
  recomputes to the block's `commit`;
- **stability basin + metric** (Phases 9-10) hold;
- `verify_cx_proof` itself rejects the block (no transcript).

Result: `3300 blocks, 19800 checks, 0 failures`.

What cannot be checked from stored data is the *sequential-work* evidence
(Phases 2, 3, 6-8: checkpoint/segment Merkle paths and the challenged round
witnesses). The only way to get that back without the transcripts is to recompute
the full ConvergenceX attempt.

Full recompute does work. `cx-reverify` (the prover, `convergencex_attempt`)
reproduces commit, checkpoints_root, segments_root, final_state and metric
exactly for real blocks of every profile class (see §7). It needs about
**8.4 GB RSS**: a 4 GB scratchpad built once, plus a 4 GB dataset regenerated
for every `prev_hash`.

Timing on the reference machine:

- Idle: 5 blocks in 1 min 49 s including the scratchpad build, about 20 s per
  block. That puts the whole window at roughly **18 h single-threaded**.
- One block took 5 min 47 s while a `-j3` build was running.

`scripts/verification/full_verify_early_chain.sh reverify` with
`REVERIFY_HEIGHTS=all` runs the whole window offline.

## 6. Options

| | Option | Assurance for 1..3300 | Cost | Changes |
|---|---|---|---|---|
| A | `--full-verify` falls back to **full recompute** (`convergencex_attempt`) for transcript-less blocks at h ≤ 3300, profile derived from `stab_*` and authenticated by the commit | Strongest: the work is redone | ~20 s and 8.4 GB per block (~18 h single-threaded for the window); shardable across machines | New expensive path in `process_block`, reachable only under `--full-verify` and only in that window |
| B | `--full-verify` accepts 1..3300 as **checkpoint-anchored** (hash chain to hard checkpoint 3300 `2894a6b3…a230`) after commit binding + basin + metric + target, and logs it as reduced verification | No sequential-work proof for 1..3300 | Seconds | Changes what `--full-verify` promises; needs explicit documentation and a flag name that says so |
| C | **Recover the original transcripts** from any archive (node or miner logs, raw `submitblock` JSON, 2026-03-19..2026-04-08) and serve them | Full Transcript V2 verification | Depends on whether an archive exists | Data only, plus the §4 profile fix |
| D | **Keep as is**: `--full-verify` is usable from a trusted snapshot at or above 3300 (as done in §7) | Full for 3301..tip only | — | Docs only |

### 6.1 Evaluation against the five requirements

| Requirement | A (recompute in node) | B (anchored) | C (recover) | D (as is) |
|---|---|---|---|---|
| Preserve the accepted chain | yes | yes (same block_ids, same persisted chain.json, §8.3) | yes | yes |
| Never invent missing data | yes (recomputes, does not invent) | yes, provided the missing evidence is labelled as missing, never as verified | yes, but only if an archive exists | yes |
| Never silently weaken current validation | yes | **only** as an explicit opt-in flag; as a silent change to `--full-verify` it would weaken what the flag promises | yes | yes |
| Never reinterpret old blocks wrongly | needs the §4 profile fix | needs the §4 profile fix | needs the §4 profile fix | the B0 default in the full-verify path is wrong for 953 blocks (latent) |
| Deterministically verify everything the data allows | yes, and more | yes, if every transcript-free check runs | yes | **no**: nothing in 1..3300 is checked |

- **A** gives the strongest result, but not inside the node. It holds 8.4 GB
  RSS in the node process for about 18 hours, on a machine class that also
  mines. It stays an **offline audit tool**
  (`full_verify_early_chain.sh reverify`, `REVERIFY_HEIGHTS=all`; shardable).
  It was not re-run here: the reference machine had 10 GB free (< 12 GB)
  next to a production miner. The six earlier samples (one per profile class,
  plus 3300) remain the evidence, all MATCH (§7).
- **C** is not available. The repository tree and the working scratch area
  were searched for any file that contains the commit of any of the 3300
  blocks (key and wallet files excluded). The only hits are copies of the
  canonical chain.json (13 copies, 0 blocks in 1..3300 with
  `checkpoint_leaves`, `segment_proofs` or `round_witnesses`), the regression
  fixture and earlier cx-reverify inputs. **No archive of the original
  transcripts exists there.** C stays open if one turns up elsewhere. Recovered
  data would go through the unchanged `verify_cx_proof()` path and be
  classified `VERIFIED`.
- **D** leaves the latent B0 defect in place and verifies nothing in the
  window.

### 6.2 Decision

**B + D, with the §4 profile fix, and A kept as an offline audit:**

1. **Profile fix (full-verify path only).** A missing `profile_index` is
   derived from the stored `stab_*` via the cASERT table that
   `casert_apply_profile` uses at that height. The derived profile must match
   exactly one row; otherwise the block is rejected (fail closed, no B0
   default). The commit check then authenticates it. The persisted per-block
   `profile_index` stays what the default path stores (B0), because that value
   feeds the cASERT recomputation of later blocks on every node.
2. **D is kept as the meaning of plain `--full-verify`.** It stays strict. What
   it gains: the transcript-free checks run, and the block is labelled
   `UNVERIFIABLE_MISSING_HISTORICAL_DATA` before it is rejected.
3. **B is available only behind `--full-verify-anchored-history`.** The flag
   name says what it does. Blocks accepted this way are labelled
   `ASSUMED_FROM_HISTORICAL_RULE`, never `VERIFIED`.

## 7. Evidence

- Reproduction (node): an empty `sost-node --full-verify --verbose` that syncs
  only from a local server holding the real chain (tip `849e95b1…f51f` @30428)
  rejects block 1 with the Phase 1 lines in §1.
  `scripts/verification/full_verify_early_chain.sh node`.
- Regression test: `test-full-verify-early-chain` (ctest
  `full-verify-early-chain`). It embeds real blocks 1, 2, 339, 931, 1001 and 3300
  and pins §1, §4 and §5. With a dumped window file as argv[1], it checks every
  block.
- Full recompute (`cx-reverify`), all MATCH on commit / cp / seg / final / metric:
  heights 1 (B0), 2 (E4), 339 (E1), 931 (H1), 1001 (H2) and 3300 (B0) are
  **6/6 MATCH**, with the profile index derived from the stored `stab_*`.
- Full verification **above** the window: a node seeded with the real chain
  truncated at 3300 (tip = hard checkpoint `2894a6b3…a230`), run with
  `--full-verify` and synced only from the local server:
  **27128 blocks (3301..30428) accepted, every one `CX Transcript V2 verified`,
  0 fast-sync skips, 0 rejections.** All 19 historic replay exceptions and all
  47 historic parameter exceptions were hit and confirmed by block_id.
  Wall time was 4 h 02 min, with max RSS 602 MB: Transcript V2 verification needs
  neither the 4 GB scratchpad nor the dataset. Final tip
  `849e95b1c7d632535e12955b112290430cb0bbdc319916b2fb296391b644f51f` @30428. All
  30429 block_ids are identical to the source chain. `--dry-run-replay` of the
  resulting chain.json gives `utxo_count 72486` and `utxo_set_root
  ebb8bf4b5c6fa1367e8852cef250131b3fdecc102c4a68584b85ed4d11ad2500`, both
  identical to the default-path replay. So the transcript-less window is the
  **only** obstacle to a from-genesis `--full-verify` of the mainnet chain.

## 8. Implementation

### 8.1 Classification

Each block that `process_block` connects under `--full-verify` gets exactly
one label in the log:

| Class | When | Accepted? |
|---|---|---|
| `VERIFIED` | `verify_cx_proof()` passed on the block's own Transcript V2 data (any height; a partial transcript also goes this way and must pass in full) | yes |
| `ASSUMED_FROM_HISTORICAL_RULE` | no `checkpoint_leaves`, `segment_proofs` or `round_witnesses` at all; mainnet; 1 ≤ h ≤ 3300; `--full-verify-anchored-history`; and every transcript-free check passed: x_bytes length, seed, commit binding including the profile byte, stability basin, metric (phases 1, 4, 5, 9, 10), plus the PoW target and cASERT `bits_q` checks that always run | yes, and the block_id at every hard-checkpoint height must equal the compiled-in hash |
| `UNVERIFIABLE_MISSING_HISTORICAL_DATA` | no Transcript V2 data and the historical rule does not apply (plain `--full-verify`, other networks, h > 3300) | **no** |

If a transcript-free check fails, the block is rejected with the failing phase
in the log, whatever the flag. Sequential work (phases 2, 3, 6-8) is logged as
`NOT_CHECKED` or `NOT_CHECKABLE`, never as passed. When a hard checkpoint is
reached, the node logs the range of assumed blocks that the hash chain now pins
to it. It prints a summary line at 3300 and every 1000 blocks:

```
[FULL-VERIFY] summary (end of transcript-less window): VERIFIED=0 ASSUMED_FROM_HISTORICAL_RULE=3300 UNVERIFIABLE_MISSING_HISTORICAL_DATA=0 assumed_anchored_through=3300 assumed_unanchored_from=-1
```

Limits, stated plainly:

- An assumed block is final only once the next hard checkpoint above it
  matches. Until then a peer could feed a fabricated block that passes the
  transcript-free checks, and the node would reject the branch at the
  checkpoint. This matches the optimistic assumevalid trust of the default
  path, and it applies only in the opt-in mode.
- The counters cover the current process. Blocks loaded from `chain.json` at
  startup are not re-verified or counted.

### 8.2 Code

- `include/sost/full_verify_history.h`, `src/full_verify_history.cpp`:
  `derive_profile_from_stab_params()`, `verify_cx_without_transcript()`,
  `FullVerifyClass`, `full_verify_historical_rule_applies()`. These are pure,
  in `sost-core`.
- `src/sost-node.cpp`:
  - flag and counters, `:666-686`;
  - profile derivation (fail closed), `:7738-7787`. The previous B0 branch is
    now `else if (pi_missing)` at `:7788`, unchanged and reached only when
    `--full-verify` is off;
  - transcript-free checks and classification, `:7985-8022`;
  - `VERIFIED`, `:8036`;
  - hard-checkpoint enforcement in the opt-in mode, `:8114-8129`;
  - counting and anchoring at connect time, `:8261-8283`;
  - CLI flag, `:10797`.

  Every new branch is guarded by `g_full_verify_mode` or
  `g_full_verify_anchored_history`, and both are false on the default path.

### 8.3 Evidence

- Unit (`ctest full-verify-early-chain`). It uses the real blocks 1 (B0),
  2 (E4), 339 (E1), 931 (H1), 1001 (H2) and 3300 (B0), so all five profile
  classes are covered, and checks that:
  - the library derivation equals the reference derivation;
  - `verify_cx_without_transcript` passes with the derived profile, and fails
    at phase 5 with the old B0 default for every non-B0 block;
  - a tampered final_state fails at phase 5, and a short x_bytes fails at
    phase 1;
  - both cASERT tables round-trip (40/40 legacy at h=1, 3300 and 5749; 43/43
    V8 at 5750);
  - unmatched, zero and `-1` (missing) `stab_*` values give no profile (fail
    closed);
  - the class names and the historical-rule predicate are correct (mainnet
    1 and 3300 with opt-in: yes; 3301, genesis, no opt-in, testnet, dev: no).
- Whole window: `full_verify_early_chain.sh scan` on the real chain gives
  3300 blocks, 33953 checks, 0 failures. Derived profiles:
  `E4=1 E1=565 B0=2347 H1=353 H2=34`.
- Real nodes: `full_verify_early_chain.sh classify` (TIP=3500, local server,
  `--noseed`):
  - strict `--full-verify`: block 1 is classified
    `UNVERIFIABLE_MISSING_HISTORICAL_DATA` and rejected;
  - `--full-verify-anchored-history` reaches 3500:
    `ASSUMED_FROM_HISTORICAL_RULE=3300`, all pinned through hard checkpoints
    500 … 3300; `VERIFIED=200` (3301..3500, full Transcript V2);
    `UNVERIFIABLE=0`; 0 fast-sync skips; 953 non-B0 derived profiles;
  - the default client reaches 3500;
  - block_id is identical at every height 0..3500 across the source chain,
    the anchored client and the default client (tip
    `ce08be1edad978c19a20b227a141742208c836e876585ffd94b5626aa696cf66`);
  - the anchored and default clients persist a byte-identical `chain.json`;
  - with `BASE_NODE` set to a sost-node built from the parent commit, its
    default sync persists the same bytes and logs the same `[BLOCK]`
    decisions (§8.4).
- Above the window, the existing evidence still holds (§7): 3301..30428 under
  `--full-verify`, 27128/27128 verified.

### 8.4 Default path unchanged

The default path of this binary and of a binary built from the parent commit
`11dc2fcc` were compared on the same local sync to 3500. Both persist the same
`chain.json` (SHA-256
`fdb0e9e9de77ec80a499e69fbaf3890115cc1f15151d34f5202fa96036c6aab1`, which is
also the `--full-verify-anchored-history` client's file) and make the same set
of `[BLOCK]` decisions. In code, every new branch sits behind
`g_full_verify_mode` or `g_full_verify_anchored_history`. The default path's
fast-sync and `verify_cx_proof()` branches, and its B0 assumption for a missing
`profile_index`, are textually unchanged.


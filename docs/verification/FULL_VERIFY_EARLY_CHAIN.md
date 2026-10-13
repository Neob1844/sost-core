# `--full-verify` and the early mainnet chain (heights 1..3300)

Status: **EXPLAINED AND GATED.** No consensus or validation code was changed.
The default sync path (hard checkpoints + assumevalid) is unaffected and still
accepts the canonical chain. `--full-verify` from genesis remains unable to pass
block 1. This document records why, what can and cannot be verified for that
window, and the options; the owner must pick one before anything is implemented.

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

## 6. Options (owner decision; none implemented)

| | Option | Guarantee for 1..3300 | Cost | Changes |
|---|---|---|---|---|
| A | `--full-verify` falls back to **full recompute** (`convergencex_attempt`) for transcript-less blocks at h ≤ 3300, profile derived from `stab_*` and authenticated by the commit | Strongest: the work is redone | ~20 s and 8.4 GB per block (~18 h single-threaded for the window); shardable across machines | New expensive path in `process_block`, reachable only under `--full-verify` and only in that window |
| B | `--full-verify` accepts 1..3300 as **checkpoint-anchored** (hash chain to hard checkpoint 3300 `2894a6b3…a230`) after commit binding + basin + metric + target, and logs it as reduced verification | No sequential-work proof for 1..3300 | Seconds | Changes what `--full-verify` promises; needs explicit documentation and a flag name that says so |
| C | **Recover the original transcripts** from any archive (node or miner logs, raw `submitblock` JSON, 2026-03-19..2026-04-08) and serve them | Full Transcript V2 verification | Depends on whether an archive exists | Data only, plus the §4 profile fix |
| D | **Keep as is**: `--full-verify` is usable from a trusted snapshot at or above 3300 (as done in §7) | Full for 3301..tip only | — | Docs only |

A and C both need the §4 profile derivation as well. Option A can be run today
as an offline audit, without touching the node: `full_verify_early_chain.sh
reverify` with `REVERIFY_HEIGHTS=all`. Putting it inside `sost-node
--full-verify` would hold 8.4 GB in the node process for the whole window. That
is a deployment decision, not a bug fix. Nothing here would change
which chain the default node accepts. B weakens the meaning of `--full-verify`,
and A adds a slow consensus-adjacent path. That is why this branch leaves the
behaviour gated and only adds the regression test and evidence.

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

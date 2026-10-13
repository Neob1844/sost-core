# Deep-fork P2P synchronisation on the v40000 base

Branch `fix/v40k-deep-fork-p2p`, based on `release/v40000-prep` @ `bc8a45d9`.
Node P2P/sync code only (`src/sost-node.cpp`). **No consensus rule, activation height or
wire message changes.** The serving side (`GETB` → `BLCK`… `DONE`) is untouched, so
production nodes interoperate unchanged.

## What was re-tested

`docs/bridge/CAPSULE_FAST_DEVNET.md` ("Finding: deep-fork recovery over P2P") reported, on an
older main-derived node, that two nodes forked two blocks below the shorter tip never
converged: orphan parents were never requested, orphans were not re-processed, and the
honest peer was penalised (+50, "empty DONE"). The canonical base now carries the emergency
fix `299cf2e6` (fork-point walk-back, orphan cascade, orphan-work fix).

A real-node regression harness was written first:
`tests/p2p/run_deep_fork_devnet.py`. It starts real `sost-node` processes (Profile DEV,
own loopback IP per node, ports 21000-21999 by default; any base inside 21000-25999), mines competing branches with the real
`sost-miner`, connects the nodes over P2P and checks convergence, chain equality from the
fork point, and the misbehaviour/ban lines each node logs about its peers. Some scenarios
use a scripted P2P peer (plain wire protocol) to deliver real blocks out of order, a
tampered block, junk orphans, or a dropped-then-restored connection.

Devnet limits (`SOST_DEVNET_FORKS`): `MAX_REORG_DEPTH` = 8, SACS V2 deep-reorg rule from
height 42, `MAX_ORPHAN_BLOCKS` = 200. Work per block depends only on height on this devnet,
so the longer branch is the heavier one.

| scenario | what it does |
|---|---|
| s1_race_1 | A +1 vs B +2, connect over P2P |
| s2_reorg_2 | A +2 vs B +3 |
| s3_reorg_5 | A +5 vs B +6 |
| s4_deep_at_cap | A +8 vs B +9: disconnect depth 8 = cap, must converge |
| s5_deep_over_cap | A +9 vs B +10: depth 9 > cap (fork point < 42), must be refused, honest B not penalised |
| s6_deep_sacsv2 | fork at 43 (after SACS V2): A +10 vs B +11, depth 10 > cap, must converge |
| s7_reverse_submit | B's branch submitted to A tip-first via `submitblock` |
| s8_reverse_p2p | peer answers `GETB` with the branch in reverse order |
| s9_unsolicited_tip | only B's tip is relayed; A must find the fork point itself |
| s10_invalid_fork | peer serves a heavier branch with one tampered block (real block ids); then the honest branch with the same ids (after a restart, and on the same running node) |
| s11_reconnect | peer is down when A starts and comes back; then a second fork while disconnected |
| s12_orphan_flood | 320 junk orphans with self-consistent ids from 8 IPs, then an honest fork |
| s13_reconnect_after_orphans | connection drops right after relaying the tip (orphans stored), the peer reconnects |

## Baseline: unmodified `release/v40000-prep` (`bc8a45d9`)

`checks: 44/51 PASS, scenarios: 9/13 PASS`

- **PASS:** s1, s2, s3, s4, s6, s7, s8, s9, s11. The original CAPSULE_FAST_DEVNET finding
  (2- and 5-block forks over P2P, out-of-order delivery, orphan cascade) **is fixed on the
  base** by `299cf2e6`.
- **FAIL s5_deep_over_cap:** the reorg is correctly refused, but A then re-requests B's tip,
  receives a block it already holds as a fork block, treats it as "nothing sent", and gives the
  honest peer **+50 "empty DONE spam"** on every connection, and stops syncing from it.
- **FAIL s10_invalid_fork (same running node):** the honest branch is never adopted and the
  honest peer gets +10, +10, +10, +50.
- **FAIL s12_orphan_flood:** with the orphan pool full, the honest fork never converges and
  the honest peer gets +10 ×3 and +50.
- **FAIL s13_reconnect_after_orphans:** no convergence; +50 against the honest peer.

## Root causes (line numbers at `bc8a45d9`)

1. **Known non-active blocks count as "nothing served".** `src/sost-node.cpp:9368`
   (`if (already_have) return true;`) drops a requested block that is already held as an
   ORPHAN or FORK without telling the sync state machine anything. When a peer re-serves
   blocks we hold only as orphans (s13, s10) the walk-back to the fork point never starts;
   when it re-serves fork blocks above our tip (s5, a refused deep reorg) the batch looks
   empty. Both end in the `MAX_EMPTY_DONE` path (`:9537`): +50 against an honest peer.
2. **Full orphan pool drops honest orphans and blames the sender.** `:6475` stores an orphan
   only while `g_orphans_by_prev.size() < MAX_ORPHAN_BLOCKS` and never evicts. After anyone
   fills the pool once (orphans are not validated), every new orphan is dropped, is not in
   the known-set, and the BLCK handler classifies it as an invalid block (`:9417`, +10), so
   the walk-back is never triggered either.
3. **A mutated body can take a genuine block id.** Fork and orphan blocks are stored
   (`:6473-6542`) before any check that the body hashes to its `block_id`. A peer that sends a
   tampered copy under a real id (s10) puts that id in the known-set and the fork index. The
   reorg then fails on it and `try_reorganize` marks the id and its descendants INVALID
   (`:8707`); the genuine block with the same id is dropped as a duplicate, and its
   descendants are rejected as "descends from invalid block", with +10 each against the
   honest peer.

## Fix (`src/sost-node.cpp`, P2P/sync only)

1. **BLCK handler:** a *requested* block we already hold still updates the sync batch: an
   ORPHAN counts as an orphan (starts or continues the fork-point walk-back), a FORK block
   counts as a placed block (follow the branch, or finish with "fork choice by work done").
   Still no validation and no penalty for these blocks.
2. **Orphan pool:** when it is full, one random orphan is evicted (index entry removed and
   the id un-marked as known) and the newcomer is stored. The pool stays at 200.
3. **`fork_block_id_check()`:** before a block that does not extend the tip is stored as a
   fork candidate or orphan, its id is recomputed from the body exactly as `process_block`
   does (transactions → merkle root → header v1/v2 → `compute_block_id`). A mismatching body
   is rejected (its sender gets the usual +10 for an invalid block). Header-only blocks
   without transactions are left to the existing path. Consensus already rejects such a body
   when it is connected; this only stops it from occupying the genuine id.

Fork choice is unchanged: strictly more cumulative work in `process_block` /
`try_reorganize`, with the existing reorg-depth cap and the SACS V2 rule.

## Results with the fix

`checks: 51/51 PASS, scenarios: 13/13 PASS` (full run, 560 s). A second run of
s1, s5, s8, s10, s12 and s13 on another port block also passed. s5 now ends with
"peer branch fully received; fork choice by work done", with no penalty. s10, s12 and s13
converge with no misbehaviour against the honest peer. The scripted malicious peer in s10
is still penalised (+10 per tampered block), and the orphan pool never exceeds 200 (RSS
grew by about 4 MB during the flood).

Full mainnet-profile suite (`-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF`,
`ctest -j3`): **127/127** before and after the change.

## Known residual of the first pass — now addressed (branch `fix/v40k-gate-deepfork`)

The first pass left two residuals: fork/orphan blocks were stored without a PoW check, and a
same-id copy with tampered uncommitted fields (witness, reward fields) could get the genuine id
marked INVALID. Both are handled below; the block_id coverage itself is audited in
`BLOCK_ID_COMMITMENT_AUDIT.md`.

## Fork / orphan PoW validation (follow-up, `fix/v40k-gate-deepfork`)

### Audit: does every fork block get full validation before it can become canonical?

Line numbers at this branch, `src/sost-node.cpp`.

- Storage: a block that does not extend the tip (`:6765-6768`) is classified fork/orphan and
  stored in `g_block_index` (orphans `:6833ff`, fork candidates `:6870ff`). Before this change
  only the id was checked there.
- Connect: the only way a stored block becomes canonical is `try_reorganize` → connect loop
  `:8875`, which calls `process_block(raw_json, reorg_connect=true)`. After the disconnect the
  block extends the tip, so it runs the SAME extends-tip path as any new block: timestamps,
  cASERT bits_q, merkle, coinbase/subsidy/reward fields, all tx rules, id recomputation
  (`:7744`), `commit <= target` (`:7769`), ConvergenceX transcript (`:8046`), profile_index
  rules, SbPoW (`:8112`), jackpot/node/asset state, `ConnectBlock`. `reorg_connect` skipped only
  the relay-dedup cache and the per-block chain save. Any failure rolls the reorg back atomically.
  Orphans re-enter through `process_orphans_for_parent` → `process_block` (normal path).
- **Gap found — trust shortcuts on the reorg path.** Three shortcuts are keyed on height alone
  (`height <= assumevalid height`, 3554 on mainnet, "optimistic trust during initial sync"): the
  header-only accept of a block without transactions (`:7069-7108`, no id, PoW, merkle or UTXO
  check at all), the ConvergenceX skip (`:8033`, `:8064`) and the profile_index leniency (`:7817`).
  They applied to reorg-connected fork blocks as well, so a stored fork block at a trusted height
  could become canonical with its PoW transcript (or, header-only, everything) unchecked. The
  hard-checkpoint trust is exact (height AND recomputed id) and is safe.
  On mainnet this is reachable only while a node is below ~4054 (MAX_REORG_DEPTH 500; SACS V2
  deep reorg is INT64_MAX on mainnet). On the devnet every height is below 3554, so the default
  devnet node never verified ConvergenceX on any block.

### Fix (P2P/sync only; no consensus rule, height or message changed)

1. **Pre-storage check `fork_block_precheck`** (`:6594`, call `:6824`), replacing
   `fork_block_id_check`: transactions present; merkle and block_id recomputed from the body;
   `commit <= target(bits_q)`; JSON reward fields vs coinbase outputs and the subsidy schedule;
   full ConvergenceX Transcript V2 (`verify_cx_proof`) with the declared, commit-bound
   profile_index, outside the same fast-sync trust under which `process_block` skips it. All of
   these are checks the connect path runs too, so no block full validation would accept is
   refused. Failing blocks are not stored (sender gets the usual +10 "invalid block"). The CX
   witness parsers were moved verbatim out of `process_block` into
   `parse_checkpoint_leaves_json` / `parse_segment_proofs_json` / `parse_round_witnesses_json` so
   both paths parse identically.
2. **No height-only trust on the reorg path** (`trust_shortcuts_ok`, `:7068`): a reorg-connected
   block gets the header-only accept, the CX skip and the profile_index leniency only if the
   branch being connected contains the assumevalid block itself, exact height and id
   (`g_reorg_trust_anchored`, set in `try_reorganize` `:8853`). The ids in the fork chain were
   recomputed before storage and each header commits to its parent, so that is exactly the
   ancestry assumevalid is meant to trust. Exact hard-checkpoint matches keep their trust. The
   normal tip-extending path is unchanged.
3. **Body-specific failures do not blacklist the id** (`reject_reason_is_body_malleable`,
   `:8619`; `:8889`, `:9001`): if a reorg fails on a field block_id does not commit to (reward
   fields, ConvergenceX witness, profile_index, missing tx data), the stored body is evicted and
   its id un-marked, and its descendants go back to the orphan pool to wait for the genuine
   parent. Failures in committed data still mark the block and its descendants INVALID.
   The relevant reject sites now record a reason (`record_block_reject`), which also shows up in
   `getminerstats` instead of "validation_failure".

Cost: a fork/orphan block above the assumevalid height is transcript-verified once at storage
(same cost as any block the node accepts) and again at connect. The cheap checks (id, PoW
inequality, rewards) run first.

### New harness scenarios (devnet, ports 25000-25999 for this run)

`--full-verify` on node A emulates mainnet heights above 3554 (devnet heights are all below
the assumevalid height).

| scenario | what it does |
|---|---|
| s14_valid_ooo_fullverify | valid fork served in reverse order; A verifies CX on every block; must converge, no refusal, honest peer not penalised |
| s15_invalid_pow_parent | first fork block gets `commit = ff..ff` (fails target), descendants relinked with self-consistent ids; refused before storage, no reorg attempted; then honest branch adopted |
| s16_invalid_pow_child | same, on the second fork block |
| s17_invalid_cx_witness | one round witness tampered, block_id unchanged, default fast sync (stored); reorg connect verifies CX, fails, rolls back, evicts the body without marking the id; the honest branch with the SAME ids is adopted on the same running node |
| s18_invalid_cx_witness_fullverify | same tamper, `--full-verify`: refused before storage |
| s19_invalid_longer_fork | heavier branch with a fabricated `commit = 00..00` (meets any target) and relinked ids; must NOT reorg; honest branch adopted after |
| s20_invalid_longer_fork_fullverify | same, refused before storage |
| s21_delayed_parent | children relayed first (orphans, no reorg), the parent arrives later from another peer; reorg completes from the orphans; no penalty |
| s22_blockid_mutation | Task B: same-id mutation of every block JSON field on the tip path and the relay path (see `BLOCK_ID_COMMITMENT_AUDIT.md`) |

In every scenario the honest peer must not be penalised.

### Results (this branch)

Full harness, all old and new scenarios, one run (`--base 25100`, 1059 s):
**checks 85/85 PASS, scenarios 22/22 PASS** (the 13 original scenarios: 51/51; the 9 new: 34/34).

- s15/s16: the bad block is refused before storage ("fork block: PoW invalid (commit above
  target)"), no reorg is attempted; the malicious peer collects +10 per bad block; the honest
  branch is adopted afterwards with no penalty.
- s17/s19 (default fast sync): the bad block is stored (devnet heights are inside the trust),
  the reorg verifies ConvergenceX on connect, fails, rolls back with the tip and UTXO root
  verified, and logs "Evicted the stored body ... ids NOT marked invalid"; the honest branch with
  the same ids is then adopted on the same running node. By code analysis the unmodified base
  would have connected s17's tampered witness without checking it (trust shortcut on the reorg
  path); s19's fabricated commit would still have been stopped there, but only by SbPoW.
- s18/s20 (`--full-verify`): refused before storage by `verify_cx_proof`.
- s21: children stay orphans with no reorg until the parent arrives from a second peer; the
  reorg then completes from the stored orphans; neither peer is penalised.
- s22: see `BLOCK_ID_COMMITMENT_AUDIT.md`. On the relay path every same-id mutation of a field
  validation reads is refused before storage, or (inside the trust) caught at connect and
  evicted; in all 36 relay cases the honest branch was adopted and the honest peer had 0
  penalties.

Full mainnet-profile suite (`-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF`,
`ctest -j2`, nice 19): **129/129 PASS**.

### Residuals

- Inside the fast-sync trust (mainnet heights <= 3554, initial sync only) the tip-extending
  path still has the header-only accept and an unbound profile_index (G1/G2 in
  `BLOCK_ID_COMMITMENT_AUDIT.md`). Design given there; not coded, because it changes tip-path
  validation of historical heights.
- Inside the trust a fork block's CX failure at connect evicts the body instead of marking it
  INVALID (the node cannot tell a fabricated commit from a tampered witness), so a peer can make
  the node retry such a reorg. Each attempt needs a heavier claimed branch and ends in an
  atomic rollback. Above the trust the block is refused before storage.
- Pre-storage transcript verification costs one CX verification per fork/orphan block above the
  trust; a peer sending invalid ones is banned after 10 (+10 each).

## How to run

```
# devnet build (separate dir)
cmake -DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF \
      -DSOST_DEVNET_FORKS=ON <src> && make -j3 sost-node sost-miner sost-cli
# all scenarios (~10-15 min; each miner block builds a 4 GB dataset, so they run one at a time)
python3 tests/p2p/run_deep_fork_devnet.py --bin <devnet-build> --work <new empty dir>
# a subset / another port block
python3 tests/p2p/run_deep_fork_devnet.py --bin <devnet-build> --work <dir> --only s5,s10,s12 --base 21400
# mainnet-profile suite
cmake -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF <src> && make -j3 && ctest -j3
```

The harness stops every process it started by PID (after checking `/proc/<pid>/cmdline`)
and exits non-zero if any check fails.

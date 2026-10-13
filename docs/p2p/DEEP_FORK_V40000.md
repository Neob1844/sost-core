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
own loopback IP per node, ports 21000-21999), mines competing branches with the real
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

## Known residual (not fixed here)

- Fork and orphan blocks are still stored without a PoW check (as before). A peer can
  still make a node try a reorg onto a fake branch with self-consistent ids. The reorg
  fails and is rolled back atomically. This is an existing cost/DoS concern, not a
  convergence bug. A cheap header pre-check before disconnecting would be a separate change.
- `block_id` does not commit to the ConvergenceX witness fields (segment proofs, round
  witnesses) or the redundant JSON reward fields. A copy that tampers only those still has
  the genuine id and can get it marked INVALID after a failed reorg. Closing this needs
  INVALID to be tied to the exact body. That is left for a follow-up.

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

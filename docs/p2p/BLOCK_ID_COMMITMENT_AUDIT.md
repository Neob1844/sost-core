# block_id commitment audit

Branch `fix/v40k-gate-deepfork` (base `release/v40000-prep` @ `11dc2fcc`). Question: what does
`block_id` commit to, which block JSON fields are outside it, and can a copy of a block with
the same id but a different body be accepted, or poison a peer's fork store / orphan pool?

Line numbers refer to `src/sost-node.cpp` on this branch unless stated otherwise.

## 1. What block_id hashes

`compute_block_id` (`src/pow/convergencex.cpp:268`):

```
block_id = SHA256( header_bytes || "ID" || commit )
```

`header_bytes` is built by `build_full_header_bytes` (`src/sost-node.cpp:1408`, mirror of the
miner) from `hc72` (`build_hc72`, `:1395`):

| bytes | field | notes |
|---|---|---|
| 10 | profile magic | `MAGIC_STR_BYTES()`; mainnet / testnet / dev differ, so ids are chain-specific |
| 4 | `"HDR2"` | |
| 32 | `prev_hash` | hc72[0..32] |
| 32 | `merkle_root` | hc72[32..64]; merkle of the serialized `transactions` |
| 4 | `timestamp` u32 LE | hc72[64..68] |
| 4 | `bits_q` u32 LE | hc72[68..72] |
| 32 | `checkpoints_root` | merkle_root_16 of `checkpoint_leaves` |
| 4 | `nonce` u32 LE | |
| 4 | `extra_nonce` u32 LE | |
| 4 | `version` u32 LE | only when version >= 2 (SbPoW, from V11 Phase 2 = 7100) |
| 33 | `miner_pubkey` | only v2 |
| 64 | `miner_signature` | only v2 (BIP-340 over the SbPoW message, below) |
| 2 + 32 | `"ID"` + `commit` | |

v1 header = 126 bytes, v2 = 227 bytes, + 34 for `"ID" || commit`.

Two further bindings reach fields that are not in the header bytes:

- **commit** (checked by `verify_cx_proof` Phase 5, `src/pow/convergencex.cpp:626`):
  `SHA256(magic || "COMMIT" || hc72 || seed || final_state || x_bytes || checkpoints_root ||
  segments_root || stability_metric u64 || profile_index i8)`, with
  `seed = SHA256(magic || "SEED" || hc72 || block_key(prev_hash) || nonce || extra_nonce)`.
  The segment proofs and round witnesses are verified against `segments_root` and against
  challenge indices derived from `commit` (Phases 3, 6-11). So the whole ConvergenceX witness
  is bound to the id **through `commit`, but only when the transcript is actually verified.**
- **SbPoW signature** (v2, in the header): the signed message (`include/sost/sbpow.h`) covers
  prev_hash, **height**, commit, nonce, extra_nonce, miner_pubkey, and from V13 also
  genesis_hash, timestamp, bits_q and merkle_root. `height` is therefore bound for v2 blocks.

## 2. Field classification

Classes: **CONSENSUS_COMMITTED** (hashed into the id, directly or through a binding that
validation checks), **NONCONSENSUS_METADATA** (never read by validation), **MALLEABLE_BUT_HARMLESS**
(outside the id; a mutated value is rejected by validation, or two values are consensus-equivalent),
**SECURITY_RELEVANT_UNCOMMITTED** (can change under the same id, is accepted, and matters).

| field | class | reasoning |
|---|---|---|
| `block_id` | CONSENSUS_COMMITTED | recomputed and compared (`:7744`; pre-storage in `fork_block_precheck`, `:6594`) |
| `prev_hash`, `merkle_root`, `timestamp`, `bits_q`, `checkpoints_root`, `nonce`, `extra_nonce` | CONSENSUS_COMMITTED | header bytes |
| `commit` | CONSENSUS_COMMITTED | hashed after `"ID"`; PoW inequality `pow_meets_target` (`:7769`) |
| `version`, `miner_pubkey`, `miner_signature` | CONSENSUS_COMMITTED | v2 header extension; for v1 `version` is 1 by rule (any other value turns the header into v2 → id mismatch) |
| `transactions` | CONSENSUS_COMMITTED (via merkle_root) — **see gap G1** | merkle recomputed (`:7141`). But a block with NO `transactions` is accepted header-only at heights <= assumevalid on the tip path (`:7080`), without even recomputing the id |
| `height` | MALLEABLE_BUT_HARMLESS | not hashed for v1; bound by the SbPoW signature for v2; always checked positionally (tip path: `height == g_blocks.size()`, `:6765`; fork path: parent height + 1) and it drives the subsidy check. A mutated height is rejected |
| `subsidy` | MALLEABLE_BUT_HARMLESS | not hashed; must equal `sost_subsidy_stocks(height)` (`:7499`), now also pre-storage |
| `miner`, `gold_vault`, `popc_pool` | MALLEABLE_BUT_HARMLESS | not hashed; must equal the coinbase outputs, which are in the merkle root (`:7622` and the Phase 2 branches), now also pre-storage |
| `profile_index` | CONSENSUS_COMMITTED via `commit` — **see gap G2** | bound by Phase 5 only when the transcript is verified. Inside the fast-sync trust the value is not bound, yet it is stored (`sb.profile_index`) and is the parent profile used by `casert_compute` for the NEXT block. Removing the field is equivalent to B0 below `CASERT_V4_FORK_HEIGHT` (4170) and rejected above it outside the trust |
| `stability_metric`, `x_bytes`, `final_state`, `segments_root` | CONSENSUS_COMMITTED via `commit` | verified by Phase 5 when the transcript runs; inside the trust: unverified, stored and relayed, not read by any other rule (harmless there) |
| `checkpoint_leaves` | CONSENSUS_COMMITTED via `checkpoints_root` | Phase 2 merkle check |
| `segment_proofs`, `round_witnesses` | MALLEABLE_BUT_HARMLESS | not hashed; checked against `segments_root` and commit-derived challenges; any mutation fails verification. Inside the trust: unverified, stored and relayed, unused |
| `stab_scale`, `stab_k`, `stab_margin`, `stab_steps`, `stab_lr_shift` | NONCONSENSUS_METADATA | copied into `StoredBlock` (`:8241`ff) for RPC; CX parameters come from the profile table, never from these |
| any other / unknown key | NONCONSENSUS_METADATA | ignored by validation, kept verbatim in `raw_block_json` and relayed |

## 3. Demonstration (devnet, real blocks, `tests/p2p/run_deep_fork_devnet.py` scenario `s22_blockid_mutation`)

A real devnet block (h=5, mined by `sost-miner`) is copied with exactly one field changed and the
original `block_id` kept. Two paths, each with the default fast sync and with `--full-verify`.
Devnet heights are all below the assumevalid height (3554), so **default = inside the trust,
`--full-verify` = what every mainnet block above 3554 gets.**

Tip path (`submitblock`, the block extends the node's tip):

| mutation | default (trusted range) | --full-verify (= mainnet > 3554) |
|---|---|---|
| nonce / timestamp / commit (controls) | rejected | rejected |
| `transactions` removed | **ACCEPTED, header-only (G1)** | rejected |
| height, subsidy, miner, gold_vault, popc_pool | rejected | rejected |
| profile_index -1 | **ACCEPTED, mutated value stored (G2)** | rejected |
| profile_index removed (genuine value 0 = B0) | accepted (equivalent) | accepted (equivalent) |
| stability_metric, x_bytes, final_state, segments_root, checkpoint_leaves[0], segment_proofs[0], round_witnesses[0] | accepted unverified (trust skips the transcript) | rejected |
| stab_*, unknown extra key | accepted (metadata) | accepted (metadata) |

After all the rejected copies the genuine block is still accepted on the tip path (both modes):
a rejected body never marks its id known or invalid on this path.

Relay / fork-store path (the mutated copy arrives FIRST from a malicious peer as a fork block,
then an honest peer serves the genuine heavier branch with the same ids), 18 mutations x 2 modes:

| mutation | default (trusted range) | --full-verify |
|---|---|---|
| transactions removed | refused before storage | refused before storage |
| height | rejected (parent height != h-1) | same |
| subsidy / miner / gold_vault / popc_pool | refused before storage | refused before storage |
| profile_index, stability_metric, x_bytes, final_state, segments_root, checkpoint_leaves, segment_proofs, round_witnesses | stored; at reorg connect CX fails, body evicted, id NOT marked invalid | refused before storage (CX) |
| profile_index removed (= B0, equivalent) | stored, connected (consensus-equivalent body) | same |
| stab_*, unknown key | stored, connected (metadata differs) | same |

In all 36 cases the honest branch was adopted and the honest peer had 0 penalties; for every
mutation of a field validation reads, the canonical body ended up byte-identical to the genuine
block. Before the fix (first-pass analysis, `DEEP_FORK_V40000.md`) the witness/reward cases
blacklisted the genuine id.

## 4. Peer-relay poisoning

Fork candidates and orphans are kept by id (`g_block_index`, known-set). Before this branch a
same-id copy with a bad uncommitted field (reward fields, witness, profile_index, missing txs)
could be stored first; the genuine copy was then dropped as a duplicate, the reorg failed on the
bad body and `try_reorganize` marked the **genuine id** INVALID with all its descendants, so the
honest branch could never be adopted (chain split by relay order).

Fixed (P2P/sync only, no consensus rule changed):

1. `fork_block_precheck` (`:6594`, called at `:6824`) runs before anything is stored: id
   recomputed from the body, `commit <= target`, reward fields vs coinbase and schedule, and the
   full ConvergenceX transcript outside the fast-sync trust. Every check is one the connect path
   also runs, so no block that full validation accepts can be refused here.
2. `reject_reason_is_body_malleable` (`:8619`): when a reorg fails on a reason that comes from a
   field block_id does not commit to, the stored body is evicted and its id un-marked (it stays
   receivable); its descendants go back to the orphan pool to wait for the genuine parent
   (`:9001`). Failures in committed data still mark INVALID as before.

Remaining relay effect: metadata fields (stab_*, unknown keys) can differ between copies of the
same block; whichever copy a node accepts first is what it stores and relays. Consensus ignores
them, so this is cosmetic (RPC output). A peer can pad an unknown key up to the 4 MB message
limit only for a block the victim has not seen yet.

## 5. Verdict: SAFE as a commitment — no block_id version needed — with one validation gap

Every field that consensus reads is bound to the id: header fields directly, transactions
through the merkle root, the ConvergenceX witness and profile_index through `commit`, and
height through the SbPoW signature (v2) or position. Fields outside the id are either enforced
by validation (a mutation is rejected) or never read. **No historical block id changes and no
new block_id version is required.**

The gap is in validation, not in the commitment, and only inside the fast-sync trust
(`height <= assumevalid` = 3554 on mainnet, without `--full-verify`). There the tip path
accepts the binding unchecked:

- **G1 — header-only accept** (`:7069-7108`): a block at a trusted height with no
  `transactions` is appended with no id recomputation, no merkle, no PoW inequality, no
  coinbase and no UTXO update. A peer serving a node in initial sync can feed fabricated or
  stripped blocks below 3554; the node's UTXO set then differs from the network's.
- **G2 — profile_index unbound** (`:7817ff` with the CX skip at `:8033`): at a trusted height
  the declared profile_index is range-checked against the chain but not bound to `commit`. A
  same-id copy with another in-range value is accepted and stored; it is the parent profile for
  the next block's cASERT decision (block 3555 on mainnet) and is persisted in chain.json.

Both are reachable only while a node syncs heights <= 3554 (a node above 4054 can no longer
reorg there: MAX_REORG_DEPTH 500, SACS V2 deferred on mainnet). Per the task rules these were
**not coded**: they change the tip-path validation of historical heights. Safest correction
(validation only, no activation height, no id change, does not change the accepted chain):

1. Remove the header-only accept (G1). Serving nodes already refuse to put a block without
   transaction data on the wire (`p2p_send_block`, "REFUSING to serve block ... no transaction
   data"), so honest sync never relies on it. Before shipping, prove on a full mainnet replay
   that every block 1..3554 is served with transactions.
2. Inside the trust, keep skipping the expensive transcript but always check the cheap Phase 5
   binding (one SHA-256) whenever `x_bytes`/`final_state`/`segments_root` are present, with the
   declared profile_index; reject on mismatch (G2). Blocks 0..3300 travel without
   `profile_index` and checkpoint data (docs/verification/FULL_VERIFY_EARLY_CHAIN.md: the B0
   fallback does not bind for 953 of them), so: below the last data-less height (3300) keep
   today's behaviour (field absent → B0); above it require the field and the binding. Validate
   the boundary with `test-full-verify-early-chain` and a full mainnet replay (tip, UTXO root).
3. Longer term: grant fast-sync trust only to blocks proven to be ancestors of the
   assumevalid/checkpoint block (headers-first), as the reorg path on this branch already
   does (`g_reorg_trust_anchored`).

## 6. G1/G2 closed (branch `feat/v40k-p2p`) — validation only, proven on the real chain first

**Order of work.** The stricter checks were first built into a test binary and the real
mainnet chain was replayed through them over P2P (server = a copy of the 30,428-block
`chain.json`, client from genesis, default fast sync, mainnet build flags). Only after every
real block passed were they kept.

Replay result (`tests/p2p/run_trusted_range_mutations.py` covers the negative side, the
replay itself is a plain genesis sync):

| item | result |
|---|---|
| blocks 1..3554 inside the trust | 3554/3554 accepted, 0 rejects |
| blocks carrying `transactions` | 3554/3554 (G1 removal cannot affect honest sync) |
| blocks carrying x_bytes / final_state / segments_root | 3554/3554 |
| commit binding computed (profile_index present, 3301..3554) | 254/254 bind |
| historical blocks without profile_index (1..3300) | 3300, stored as B0 exactly as before (unbound: 953 of them are not B0) |
| block ids 0..3700 vs the server chain | 0 mismatches |
| full sync genesis -> 30,428 with the final binary | see the branch report (state dump sha256 identical to the validated state) |

**G1 — fixed.** `process_block` no longer has a header-only accept: a block without
`transactions` is rejected at every height (`src/sost-node.cpp`, the `tx_hexes.empty()`
branch). `fork_block_precheck` already refused it.

**G2 — fixed.** `trusted_cx_binding_check` (`src/sost-node.cpp`) runs for every block whose
ConvergenceX transcript is skipped (fast-sync trust or exact hard checkpoint), on the tip path
(right after the block id is recomputed) and in `fork_block_precheck`. It recomputes the
cheap Phase 5 binding (seed + commit, two SHA-256) with the declared profile_index:

* profile_index present -> must bind;
* absent, MAINNET height > 3300 or DEV -> must bind as B0 (the value that is stored);
* absent, MAINNET height <= 3300 -> unchanged (B0, unbound; the historical window);
* MAINNET/DEV: x_bytes, final_state and segments_root are required inside the trust, so a
  stripped body can no longer leave the previous block's profile in `g_last_accepted_profile`;
* TESTNET: binds when the field is present; absent stays as before (no testnet replay exists).

Side effect, intended: inside the trust, a same-id copy with a changed `stability_metric`,
`x_bytes`, `final_state` or `segments_root` is now rejected wherever the binding is computed
(they are commit inputs). `checkpoint_leaves`, `segment_proofs`, `round_witnesses` remain
unverified inside the trust (not read by any rule there).

**Before / after on real mainnet blocks** (tip path, submitblock, mainnet build):

| mutation | base `4d8f9899` | this branch |
|---|---|---|
| block 100 / 3301 without transactions | ACCEPTED (header-only) | rejected |
| block 3301 profile_index -1 | ACCEPTED, stored | rejected |
| block 100 / 3301 without x_bytes | ACCEPTED (profile not bound, previous profile kept) | rejected |
| genuine block after the rejected copies | accepted | accepted |

`tests/p2p/run_trusted_range_mutations.py` (heights 100, 1777, 3300, 3301, 3400, 3554): 44/44
checks pass on this branch. Devnet: `run_deep_fork_devnet.py` s22 now asserts the default-mode
rejections. No block id, consensus rule or activation height changes; the accepted mainnet
chain is the same.

# SACS P4 + P5 — In-Node Reorg Monitor & Read-Only RPC

**Status:** IMPLEMENTED + TESTED (branch `research/sost-autonomous-chain-safety`).
**Consensus impact:** NONE. The monitor is an OBSERVER only — it never changes block
selection, difficulty, mining, or validation; deleting it would not change consensus.
It records no private keys and no wallet/sensitive data (only public block hashes,
heights, chainwork, depths, timestamps). Memory is bounded by a fixed 512-entry ring
(cannot OOM); the optional JSONL sink appends one bounded line per event.

## P4 — Monitor (`namespace sacs` in `src/sost-node.cpp`)
Events: `FORK_DETECTED, REORG_STARTED, REORG_COMPLETED, REORG_REJECTED,
DEEP_REORG_ALERT, TX_REORGED, TX_CONFLICTED, RECOVERY_STARTED, RECOVERY_COMPLETED,
CHAIN_DATA_INCOMPLETE, PERSISTENCE_ERROR`.

Reorg events carry: `old_tip_hash, new_tip_hash, common_ancestor_hash,
common_ancestor_height, disconnect_depth, connect_depth, old_chainwork, new_chainwork,
ts (timestamp), result`, plus a short bounded `detail`.

Emission points (all in the existing reorg code, no logic changed):
- fork stored (more/less work) → FORK_DETECTED
- try_reorganize depth-cap reject → REORG_REJECTED
- reorg decision (post work+depth checks) → REORG_STARTED (+ DEEP_REORG_ALERT if
  disconnect_depth ≥ threshold; devnet 6, mainnet 400 — advisory, never a gate)
- missing undo data → CHAIN_DATA_INCOMPLETE
- connect-phase failure → RECOVERY_STARTED, then RECOVERY_COMPLETED after atomic restore
- success → REORG_COMPLETED (+ TX_REORGED / TX_CONFLICTED from mempool recovery counts)
- chain auto-save failure → PERSISTENCE_ERROR

## P5 — Read-only RPC
- `getsacsstatus` → latest_seq, ring_size, ring_max, deep_reorg_threshold, per-type
  counts, last_event.
- `getsacsevents [after_seq] [limit]` → bounded page (limit clamped server-side to
  ≤200; ring itself ≤512), with `next_after` for cursor paging.
These ONLY read the in-memory ring: no unbounded loops, no mutation, cannot stop
mining/consensus, and are NOT wired to the public gateway. Bad params return a clean
JSON-RPC error (no crash).

## Evidence (executed, devnet, MAX_REORG_DEPTH=8)

### Happy path (converge A=9 / B=8) — `tests/sacs_p4_verify.sh`
- 9× FORK_DETECTED, cumulative work climbing `19b4 → … → 2ee2`; first 8 tagged
  `fork_has_less_or_equal_work`, the 9th `fork_has_more_work`.
- REORG_STARTED: common_ancestor=genesis (`6517…`), height=0, disconnect_depth=8,
  connect_depth=9, old_chainwork=`…2e65`, new_chainwork=`…2ee2`.
- DEEP_REORG_ALERT: `disconnect_depth 8 >= threshold 6`.
- REORG_COMPLETED: result=converged.
- RPC: getsacsstatus counts `{FORK_DETECTED:9, REORG_STARTED:1, DEEP_REORG_ALERT:1,
  REORG_COMPLETED:1}`; getsacsevents `[0,3]` returned exactly 3 with `next_after`;
  `[0,99999]` clamped; bad param → `-8` error, no crash; JSONL sink = 12 lines.

### Reject path (A=10 / B=9) — `tests/sacs_p4_rej_rec.sh`
- REORG_REJECTED: `disconnect 9 > MAX_REORG_DEPTH 8`; B tip unchanged (h=9).

### Recovery path (DEV connect failpoint @ ordinal 4) — `tests/sacs_p4_rej_rec.sh`
- REORG_STARTED → RECOVERY_STARTED (`rolling back 4 partially-connected fork blocks`)
  → RECOVERY_COMPLETED (`atomic rollback OK; original chain restored`); B kept its own
  chain (h=8).

## Honestly not yet runtime-exercised (code-complete, compiled, code-reviewed)
`TX_REORGED` / `TX_CONFLICTED` (needs non-coinbase txs in disconnected blocks — the
test chains are coinbase-only, so mempool recovery counted 0), `CHAIN_DATA_INCOMPLETE`
(needs corrupted/missing undo data), `PERSISTENCE_ERROR` (needs a chain-save failure).
These emit sites are wired at the corresponding code paths but were NOT triggered at
runtime here, so they are NOT marked PASS.

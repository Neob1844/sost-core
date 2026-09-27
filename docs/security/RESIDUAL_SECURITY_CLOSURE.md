# Residual security closure — ENOSPC, exception isolation, V16 literal heights

## Item 1 — disk-full / ENOSPC during a partially-completed write
### Code audit (decisive)
`save_chain_internal` writes to `<chain>.tmp`, then **flushes and checks `f.good()`; if the write
failed (ENOSPC mid-stream sets the stream badbit) it `return false` BEFORE the `std::rename`** — so
a partial `.tmp` is NEVER renamed over the good file. The atomic rename only runs after a fully
successful write. By construction, an ENOSPC mid-write cannot corrupt the real chain.json.
### Empirical reproduction (real partial write, isolated `setsid`+`ulimit -f`, no privileges)
A hard file-size limit cut the `.tmp` write mid-stream (SIGXFSZ killed the node while writing).
Result: **real chain.json byte-intact (md5 identical), JSON valid, restart recovered the last good
state (h=8), no corruption.** (The earlier directory-block test covered the open-fail path; this
covers the write-fail-mid-stream path.) Full-disk cleanup of the orphaned `.tmp` is the only minor
residual (overwritten on the next successful save).
### Mining-after-persistent-save-failure — RISK + PROPOSED POLICY (analysis; not yet coded)
Observed: the node keeps mining/accepting blocks in memory while saves fail (logs
`WARNING: chain auto-save failed!`). **Risk:** if the process then dies, the recent UNSAVED blocks
are lost locally. Severity is low — those blocks were broadcast to peers (recoverable by re-sync)
and, if the node was isolated, they were never persisted nor propagated (no consensus harm, no
corruption; restart cleanly loads the last saved state). **Proposed safe policy (to implement +
adversarially test on a dev branch BEFORE shipping):** after K consecutive save failures, refuse
`getblocktemplate` (halt local mining) and raise a critical alert / getinfo flag, bounding the
in-memory-only state and forcing operator attention. This is a LOCAL condition (not
attacker-triggerable), so low abuse risk, but it changes mining behavior and must be tested like the
IBD gate before merging.

## Item 2 — historical-exception guard isolated from ordinary PoW rejection
Throwaway mainnet build with ONE recorded hash corrupted:
- **Param exception 5038 corrupted:** `block_id confirmed` for 5038 = **0** (the special params were
  NOT applied). The block still validated with current params (that particular param delta does not
  flip 5038's outcome) — proving the guard is exact-hash-gated and does not fire on a wrong hash.
- **Replay exception 5150 corrupted (decisive):** sync **STALLED at h=5149** — block 5150 was
  REJECTED because, without its exception, its declared `bits_q` (964420) ≠ the recomputed value
  (859763): a **consensus/difficulty mismatch, NOT an invalid-PoW rejection**. `block_id confirmed`
  for 5150 = 0. This proves (a) a wrong hash does not activate the special params, (b) the exception
  is NECESSARY (the real block fails without it), and (c) the failure path is the param/consensus
  check, cleanly distinct from ordinary PoW-invalid.

## Item 3 — V16 behaviour at the LITERAL mainnet heights (no mining, no height change)
Verified by calling the real consensus predicates under mainnet params
(`tests/security/v16_height_predicates.cpp`). Constants (read-only; OWNER-LOCKED not changed):
`V15_HEIGHT=25000`, `HIST_JACKPOT_FIRST_HEIGHT=25290`, cadence `288`, `HIST_JACKPOT_V2_HEIGHT=30000`.
`node_participation_active_at(h) = h>=30000` (NODE_BIND/heartbeat txs accepted only from 30000).
| height | is_jackpot | is_v2_jackpot |
|---|---|---|
| 29899, 29900, 29999 | no | no |
| **30000** (V16 activation) | **no** | no |
| 30001, 30185, 30187 | no | no |
| **30186** | **YES** | ***** V2 JACKPOT ***** (first) |
| 30474 | YES | YES (next, +288) |
Confirms: #30,000 activates V16 and is NOT a jackpot; the first V2 jackpot is #30,186 (= 25290 +
17·288); cadence holds. The behavioural state machine (eligibility, heartbeats, rollover, no-payout)
is the identical code exercised by `run_v16_devnet_jackpot_v2` (9/0) at scaled heights — reaching
literal 30000 by mining is a ~1h run and a height override is forbidden, so the predicates are
verified literally and the behaviour via the scaled E2E (same code path). Marked accordingly.

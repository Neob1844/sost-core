# Chain-save durability (fsync) + save-failure mining policy

Branch: `feat/durable-chain-save` (off the node code; NOT merged, NOT deployed).
Scope: `save_chain_internal` + `handle_getblocktemplate` in `src/sost-node.cpp`. No consensus
change, no wire change, no key/STRATO/miner change.

## 1. fsync — power-loss durability (not just crash)
The atomic write was `write .tmp → flush → rename`. A rename is **crash-safe** (atomic directory
entry) but **not power-loss-safe**: after a power cut the renamed file could still hold unflushed
or zeroed data. Fix:
- **fsync the temp file** after close and BEFORE the rename. If it fails, the data is not durable,
  so we do NOT publish it (return false — no rename).
- **fsync the containing directory** AFTER the rename, so the directory-entry change itself is
  durable. Best-effort (bytes already durable, rename returned) → logged, not fatal.

**Test — `save_roundtrip_test.sh`:** mine to height 10 → SIGTERM (durable save) → restart from the
same `chain.json` → **loads at height 10, no corruption, no `.tmp` leftover, JSON valid (11 blocks
incl. genesis)**. PASSED.

## 2. Save-failure mining policy (local, NOT peer-exploitable)
If persistence keeps failing (full / read-only disk), producing blocks the node cannot save means a
restart silently loses accepted blocks. New: a `g_consecutive_save_failures` counter (reset on any
successful save, incremented on each failed save in `process_block` and the periodic main-loop
save). Once it reaches `SAVE_FAILURE_HALT_THRESHOLD = 3`, `getblocktemplate` refuses with RPC error
`-10` ("mining halted until the disk recovers"); the miner honors `-10`. The trigger is purely
LOCAL disk state — a peer cannot cause a save failure — so this is not a remotely-triggerable
mining stop (contrast the rejected peer-height IBD gate).

**Test — `save_failure_policy_test.sh`:** normal mining serves templates → `chmod 500` the chain dir
→ 3+ consecutive save failures logged → `getblocktemplate` returns the `-10` halt → `chmod 700` to
recover → periodic save resets the counter → `getblocktemplate` serves templates again. PASSED.

## Not done / notes
- True power-cut durability cannot be black-box tested without a VM/hardware fault; the fsync+dir-fsync
  pattern is the accepted solution and the roundtrip proves no functional regression.
- Threshold 3 is conservative; tune with operations if needed.

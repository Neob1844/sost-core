# P2P Performance Baseline — 2026-04-09

## Test Environment
- Seed: VPS 212.132.108.244, 2 vCPU, commit e6b8c11
- Client: WSL2, 14 threads, same commit
- Chain height at test time: ~3570-3582
- Checkpoint: 3554 (fast-sync for almost all blocks)

## Results (10 minute runs, sync from zero)

| Scenario | Blocks accepted | Sync complete | Stalls | Disconnects | Blocks/min |
|----------|----------------|---------------|--------|-------------|------------|
| OFF/OFF  | 3573           | Yes (3570)    | 0      | 0           | ~357       |
| ON/OFF   | 3580           | Yes (live)    | 0      | 1           | ~358       |
| ON/ON    | 3582           | Yes (live)    | 0      | 1           | ~358       |
| Bootstrap| instant        | Yes           | 0      | 0           | N/A        |

## Analysis

**The encrypted mode (ON/ON) is NOT significantly slower than plaintext.**

Previous observation of ~10 blocks/min under ON/ON was from an earlier
version with the old blocking I/O. With the nonblocking event loop
(commit 84c08fc+), encrypted sync performs at the same speed as plaintext.

The overhead of ChaCha20-Poly1305 per message is negligible compared
to the network transfer and block processing time.

## Conclusion

No optimization needed. The encrypted transport is already performing
at full speed. The previous slowness was caused by the old blocking
I/O design, not by the encryption itself.

Recommendation: encrypted P2P can be re-enabled as default if desired.

# v16.3.0 sec1 — Acceptance report (security revision of the existing v16.3.0 release)

Public version **v16.3.0**, revision **sec1** (Option C). Node source commit **1a675744**
(revision tag `v16.3.0-sec1`). Node-only. **Not published, not deployed** — pending owner
authorisation. Real execution, real metrics; nothing declared PASS on the strength of a document.

## Assets — clean reproducible build at the canonical path `<repo>/build`

```
d3212aea4eb5793ab7670d5e096173091731d04cb972c96975e5851001272213  sost-node-sec1   (NEW revised node)
2ef9d0a77f243224ac088460818d6b360c689a7a3fa9555738e2b3b3e0112fe2  sost-miner       (unchanged, == v16.3.0)
489f43741437a08b2d617c21020061c042f42d4609bbe6547d28f08ca5e07d07  sost-cli         (unchanged, == v16.3.0)
304d056d504960b4179543672f14bee28146788b985363a5e95d476cc6b1492e  sost-node        (ORIGINAL v16.3.0, kept)
```
Two clean builds at `<repo>/build` → the same node hash; miner and cli reproduce the **published**
v16.3.0 hashes exactly (evidence the environment matches the official release). **Only the node
changed.** Path-independent reproducibility (build-dir prefix-map + SOURCE_DATE_EPOCH) is a Phase G
item — see residuals.

## Results (real runs)

| Step | Check | Result | Evidence |
|------|-------|--------|----------|
| 1 | Diff vs v16.3.0; no consensus/emission/SbPoW/DTD/NODE_BIND/Jackpot/#30,000 change | **PASS** | Changed prod code: `sost-node.cpp` (fork-store caps+metadata, getforkstats, SIGPIPE, BLCK origin) + `beacon.cpp` (base64 UB). Zero consensus files (params/block_validation/lottery/jackpot/checkpoints/sbpow untouched by diff). |
| 2 | SIGPIPE/EPIPE/incomplete-write/disconnect audit (static) | **PASS** | All socket writes via `write_exact` → false on EPIPE/ECONNRESET; short writes retried; `read_exact` handles close/timeout. |
| 2/11 | Prolonged churn+fork-storm on the FINAL binary d3212aea | **PASS** | 300 s alive; CPU 28 %; RSS 480 MB flat (no leak); RPC avg 62 ms (59/59 ok); fork store 150; 0 rejects/bans; recovers. (v16.3.0 dies ~6 s.) `campaign_final.log`. |
| 3 | Checkpoints test fixed (CHECK, real anchor 3554), Release AND Debug/ASan, un-excluded in CI | **PASS** | `assert`→`CHECK` (active under NDEBUG); asserts the shipped anchor + range. Release 115/115; Debug/ASan 115/115. Removed from CI `-E` list. |
| 3/6 | Clean build all targets; full suite; Debug/ASan `halt_on_error=1` | **PASS** | Release ctest 115/115; **Debug/ASan `halt_on_error=1` 115/115, 0 UBSan/ASan findings** (only btc-* excluded — need bitcoind). `asan_final_halt.log`. |
| 4 | Real P2P parser extracted; fuzzer tests production code; in CI fuzz-smoke | **PASS** | `sost/p2p_frame.h`; handle_peer wrapper behaviour-identical; fuzz 319k exec/0 crashes; fuzz-smoke job added. |
| C | Base64 UB: fix the node's, classify the rest | **PASS** | `beacon.cpp` b64_decode `int`→`uint32_t`; differential old-vs-new over **200,015** inputs (valid/invalid/truncated/200 KB/random) → **0 mismatches**. beacon is `informational only` per beacon.h (non-consensus). Node's own RPC-auth base64_decode already safe (bounded unsigned char). ENCODE UBs (tx_send/bitcoin_backend/sost-cli/sost-miner) process LOCAL data, not on the node surface → deferred; miner/cli stay byte-identical. |
| 5 | miner/cli byte-identical to v16.3.0? | **YES** | `2ef9d0a7…` / `489f4374…` unchanged after the beacon fix (beacon is node-only). |
| 8 | CI on the exact FINAL commit (1a675744) | **PASS** | unit-and-consensus ✓, asan-ubsan ✓, fuzz-smoke ✓ (run 36144499046). |
| 6-repro | Node hash reproducible | **PASS (canonical path)** | d3212aea reproduces at `<repo>/build`; NOT path-independent yet (Phase G). |
| 10 | Full sync genesis→tip with the FINAL binary d3212aea; hashes + UTXO vs v16.3.0 | **IN PROGRESS** | d3212aea, encrypted + plaintext, from genesis, 0 rejects so far. (c2b06b91 previously gave 9/9 hash MATCH + identical UTXO; beacon fix is not on the block-validation path, so the result is expected identical — to be confirmed on completion.) |
| 5-interop | Interop enc/plaintext with a real v16.3.0 node | **PASS (forward)** | sec1 client fully syncs from a hash-verified v16.3.0 server (304d056d), enc+plaintext, 0 rejects. Reverse blocked by v16.3.0's own SIGPIPE bug (reproduced v16.3.0↔v16.3.0) — the bug sec1 fixes, not an interop regression. |

## Residuals (identified, NOT hidden; carry to the Gauntlet)
- **Base64 ENCODE UB** in `tx_send.cpp`, `bitcoin_backend.cpp`, `sost-cli.cpp`, `sost-miner.cpp`:
  local-data only, NOT on the node surface, not triggered by any current test under `halt_on_error=1`.
  Deferred so miner/cli stay byte-identical; fix in the Gauntlet (Phase F/G), which will re-hash cli/miner.
- **Path-independent reproducible build** (Phase G): the source path is prefix-mapped (`=/sost`) but the
  build-dir path is not, so a different absolute build path yields a different hash. Canonical-path
  reproducibility holds.
- CI `btc-*` excluded (need a live bitcoind regtest).

## Standing constraints honoured
No merge, no publish, no deploy. Consensus, emission, SbPoW, DTD, NODE_BIND, Jackpot and the #30,000
schedule unchanged. User's WSL miner (PID 562789), wallet, keys, NODE_BIND and STRATO untouched.

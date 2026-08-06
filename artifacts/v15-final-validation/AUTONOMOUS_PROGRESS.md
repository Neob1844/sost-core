# V15 Final Validation — Autonomous Progress Tracker

**Branch:** `feat/v15-jackpot-explorer-card` · **HEAD at last update:** `039dbbb3` (+ this setup commit)
**main:** `b822db4c` (untouched) · **Nothing merged/tagged/deployed.**
**Mainnet miner:** PID 574503, 13 threads @ :18232 — **LIVE, never touched.**
**Machine:** 14 cores, load ~13.9 (miner-saturated), 23 GiB RAM, 567 G free disk.

This file is the durable cross-session state for the CTO autonomous mission
(finish V15 → RC; advance Atomic Swap non-blocking). Update after every phase.

## Legend
✅ done+committed · 🔄 running · 🔲 not started · ⚠️ blocked (external/resource)

## V15 gates
| Phase | Status | Evidence / harness | Commit |
|---|---|---|---|
| Reorg deadlock fix (3 root causes) | ✅ | `run_v15_devnet_reorg.sh` green | 960afb6d |
| Failed-reorg atomicity (F00-F04 + 10 cycles) | ✅ 49/49 | `run_v15_devnet_failed_reorg.sh` + DEV failpoint | ecccd704 |
| Process-restart invariance | ✅ 27/27 | `run_v15_devnet_restart.sh` | cecaa8b0 |
| Reindex/load_chain + tamper rejection | ✅ | `run_v15_devnet_reindex.sh` | b6410ff0 |
| Rollover accumulation (no-winner preserves reserve) | ✅ 9/9 | `run_v15_devnet_rollover.sh` | afb3f29d |
| DEV failpoint isolation (absent from mainnet/testnet) | ✅ | `strings` check + builds | ecccd704 |
| DEV functional soak (3 rounds × 6 harnesses) | ✅ 18/18 | `run_v15_devnet_soak.sh`, no leak (~11MB flat) | bb1cf8f8/b242d4ea |
| **V15-A** valid-PoW attack matrix COMPLETE (~18 new cases) | 🔲 | needs new miner mutations + separate build | — |
| **V15-B** numeric rollover cap 100→500→500 (DEV RPC) | 🔲 | needs DEV-only rollover RPC | — |
| **V15-C** reserve edge cases E01-E20 | 🔲 | — | — |
| **V15-D** quick gate `run_v15_devnet_quick.sh` | 🔲 | — | — |
| **V15-E** full regression (ctest ×3 nets) + sanitizers + static | 🔲 | needs CPU (miner-saturated box) | — |
| pre-V15 compatibility proof | 🔲 | — | — |
| **V15-F** testnet long SbPoW run (V15=12500, ~8.5h) | ⚠️ | EXTERNAL_RESOURCE_BLOCKER — separate machine (box saturated by miner) | — |
| **V15-G** RC artifacts + rollout docs | 🔲 | — | — |

## Atomic Swap (non-blocking, parallel)
| Component | Status |
|---|---|
| EVM HTLC | ✅ ACTIVE on mainnet @ block 15000 (main 58e9cc9b, 92/92 ctest) |
| Policy layer (timeout/swapId/preimage/RPC) | ✅ 49 tests |
| BTC HTLC signing lifecycle | code-complete, GATE OFF, 121 ON/50 OFF; ⚠️ needs bitcoind regtest + external crypto review |
| EVM contract SafeERC20 | INTERNALLY TESTED (60 Foundry), ⚠️ external audit pending, NOT deployed |
| Consumer dashboard | FOUNDER/DEV validated, real quotes pending, not deployed |

## Timeline
Mainnet height 20696 / V15 @ 25000 → ~4304 blocks (~31 days, ~2026-09). Deployed binary
v0.3.2 has V15 gates DEFERRED → reaching 25000 with it activates nothing; the REAL deadline
is deploying the new V15 binary to all nodes/miners (coordinated) before 25000.

## Verdict (current)
**V15: READY FOR DEV FUNCTIONAL VALIDATION** (reorg/restart/reindex/rollover lifecycle proven).
Not RC yet: attack-matrix, rollover-cap, reserve-edges, quick-gate, regression, testnet remain.
**Atomic Swap: EVM live; BTC regtest + EVM audit are external work — decoupled from V15.**

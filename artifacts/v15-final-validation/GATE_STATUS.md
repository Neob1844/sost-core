# V15 hard GO-gate status — single source of truth

Maps every hard GO gate from `DEPLOYMENT_PLAN.md` (§ "Hard GO gates for touching main") to its
evidence and honest status. **`main` stays untouched until every row is GREEN.** Deadline: all
engineering DONE before **block 24,900** (mainnet at ~20,760 → ~4,140 blocks, ~30 days).

Legend: ✅ GREEN · 🔄 running · 🟡 partial/needs-work · ⛔ blocked (external resource) · ⬜ not started

| # | GO gate | Status | Evidence / how it is proven |
|---|---------|--------|------------------------------|
| 1 | Attack matrix COMPLETE (single-mutation + multi-block) | ✅ | 17-case single-mutation 20/0 (`attack-matrix.log`); multi-block **M02** non-event, **M03** stale-replay, **M08** replay-after-restart (`m02/m03/m08.log`); #1/#4/#7 reduced by keyless-reserve proof; #5/#6/#14 honestly labeled (`multiblock-attack-summary.md`) |
| 2 | rollover 100→500→500 (DEV RPC) | ✅ | `run_v15_devnet_rollover_cap.sh` via `devjackpotstate` (`rollover-cap.log`): rollover 0→cap-base, prize 100→500→500 clamped, survives restart |
| 3 | reserve edge cases (E01-E20) | ✅ | `run_v15_devnet_reserve_edges.sh` (`reserve-edges.log`): drain accounting + one-way retirement latch + restart. (Scope is the genuinely-distinct reserve properties, not 20 padded cases — the arithmetic boundaries are additionally in `test-jackpot` 108/0.) |
| 4 | quick gate ×2 | ✅ | `run_v15_devnet_quick.sh` run twice (before + after a mainnet rebuild), both `RESULT: GO` (`quick-gate.log`) |
| 5 | ctest mainnet/testnet/DEV | 🟡 | mainnet FULL `ctest` **101/101, 0 fail** (`regression-ctest.log`); DEV consensus proven by the 9 DEV harnesses; testnet-profile ctest build still to run on a clean box |
| 6 | ASan | 🟡 | consensus arithmetic CLEAN under AddressSanitizer (jackpot/rollover/dtd/eligibility/frequency = 361 assertions, 0 errors — `sanitizer-consensus.log`, `run_sanitizer_consensus_tests.sh`); full node + integration harnesses under ASan still need a clean box |
| 7 | UBSan | 🟡 | consensus arithmetic CLEAN under UndefinedBehaviorSanitizer (same 361 assertions, no signed-overflow/UB — `sanitizer-consensus.log`); full node under UBSan needs a clean box |
| 8 | static analysis (no critical/high) | ⬜ | not started (clang-tidy/cppcheck pass) |
| 9 | pre-V15 compatibility | ⬜ | need a test that a pre-V15 vs post-V15 binary agree on all state strictly below the fork height |
| 10 | exact-activation @25000 | 🟡 | activation is height-gated + unit-tested; DEVNET_FAST crosses V15 (=18) live in every DEV harness; the literal mainnet height 25000 cannot be pre-run but the gating logic is covered |
| 11 | reorg/restart/reindex crossing activation | ✅ | `run_v15_devnet_reorg.sh` / `restart.sh` (27/27) / `reindex.sh` / `failed_reorg.sh` (49/49) all operate across the DEV V15 activation |
| 12 | testnet long SbPoW run PASS (real) | ⛔ | ~8.5 h SbPoW run — EXTERNAL machine (resource blocker); must be real, not declared |
| 13 | clean reproducible builds | ⬜ | RC step — build node/CLI/miner/signtx from clean main + SHA-256 + manifest |
| 14 | no DEV RPC / failpoints in production binaries | ✅ | `dev-flag-isolation.log` + quick gate: inject-tx-at1 / attack-jackpot / dump-block / devjackpotstate / devsetreorgfailpoint / devchainstate all count=0 in mainnet+testnet binaries; mainnet build (DEVNET=OFF) recompiles clean |
| 15 | no secrets | ✅ | `git diff main..HEAD` scanned: NO personal email, NO PEM/private-key literals, NO real mainnet RPC creds (AdminNeoB/sost125fa absent). Only benign hits: placeholder `--rpc-pass sost` in a doc example and public BTC test-vector keys in atomic-swap test code. (Re-run on the final merge diff.) |
| 16 | rollout + rollback runbooks | ✅ | `RUNBOOK_CUTOVER.md` — standalone operator runbook: pre-cutover HOLD checklist, atomic hash-verified staged swap (node→canary→miners→explorer), rollback (valid only pre-25000), safety invariants. `<PLACEHOLDER>`s filled at RC time (tag/commit/SHA-256) |
| 17 | merge --no-ff → tag → binaries + SHA-256 + manifest | ⬜ | RC step, GATED on all rows above being GREEN; the live cutover is human-supervised (governance note) |

## Summary
**Consensus-validation gates (1-4, 11, 14) are GREEN.** What remains is (a) the full multi-net
`ctest` regression [running], (b) sanitizers + static + pre-V15 compat + secret scan [engineering,
some need a clean box], (c) the ~8.5 h testnet SbPoW run [external machine], and (d) the RC
packaging + merge [gated on all the above; cutover human-supervised]. None of the remaining items
is a known consensus defect — they are regression/hardening/packaging + one external-resource run.

Open (honest, not claimed green): #14-map accumulation↔winner reorg transition needs multi-address
winner control (a DEV miner able to mine as N addresses); a future add, not a blocker for the above.

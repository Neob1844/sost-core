# V15 test evidence index

Every V15 validation gate → its harness/test and its evidence artifact. Paths are relative to the
repo root. Consolidated status lives in `artifacts/v15-final-validation/GATE_STATUS.md`.

## Consensus lifecycle (DEVNET_FAST, crossing the live V15 activation)
| Property | Harness | Evidence |
|----------|---------|----------|
| Reorg deadlock fix + jackpot reorg | `tests/run_v15_devnet_reorg.sh` | green (commit 960afb6d) |
| Failed-reorg atomicity 49/49 | `tests/run_v15_devnet_failed_reorg.sh` + DEV failpoint | green (ecccd704) |
| Process-restart invariance 27/27 | `tests/run_v15_devnet_restart.sh` | green (cecaa8b0) |
| Reindex/load_chain + tamper reject | `tests/run_v15_devnet_reindex.sh` | green (b6410ff0) |
| No-winner rollover preserves reserve 9/9 | `tests/run_v15_devnet_rollover.sh` | green (afb3f29d) |
| DEV functional soak 18/18 | `tests/run_v15_devnet_soak.sh` | green (bb1cf8f8) |

## Jackpot attack surface
| Property | Harness | Evidence |
|----------|---------|----------|
| 17-case single-mutation valid-PoW matrix 20/0 | `tests/run_v15_devnet_attacks.sh` | artifacts/…/attack-matrix.log |
| Live payout end-to-end (winner, anti-self, EXACT accounting mint=burn=fee=0) | `tests/run_v15_devnet_payout.sh` | artifacts/…/revb1-payout.log |
| M02 jackpot at non-event height rejected | `run_v15_devnet_multiblock_attacks.sh --scenario M02` | artifacts/…/m02.log |
| M03 stale jackpot replayed at a later event rejected | `--scenario M03` | artifacts/…/m03.log |
| M08 rejected attack stays rejected across restart | `--scenario M08` | artifacts/…/m08.log |
| #1/#4/#7 reduce to M02/M03 (keyless reserve) | argument | artifacts/…/multiblock-attack-summary.md |

## Numeric / edge / boundary
| Property | Test | Evidence |
|----------|------|----------|
| Rollover-cap 100→200→300→400→500→500 (clamped, restart) | `tests/run_v15_devnet_rollover_cap.sh` + RPC `devjackpotstate` | artifacts/…/rollover-cap.log |
| Reserve drain + one-way retirement latch | `tests/run_v15_devnet_reserve_edges.sh` | artifacts/…/reserve-edges.log |
| Activation boundary 24999/25000, jackpot@25290 (MAINNET profile) | `tests/test_v15_activation_boundary.cpp` (ctest `v15-activation-boundary`) | docs/v15/ACTIVATION_BOUNDARY_REPORT.md |
| Consensus arithmetic unit suites 361/0 | `test-jackpot/lottery-rollover/dtd-control/lottery-eligibility/lottery-frequency` | artifacts/…/quick-gate.log |

## Regression / analysis / isolation
| Property | Tool | Evidence |
|----------|------|----------|
| Full mainnet ctest 101/101 | `ctest` (build) | artifacts/…/regression-ctest.log |
| ASan+UBSan on consensus arithmetic (361, 0 errors) | `artifacts/…/run_sanitizer_consensus_tests.sh` | artifacts/…/sanitizer-consensus.log |
| GCC `-fanalyzer` clean on all V15 code | g++ -fanalyzer | docs/v15/STATIC_ANALYSIS_REPORT.md |
| Consensus security audit (0 exploitable, B-1 fixed) | adversarial review | docs/v15/SECURITY_AUDIT_REPORT.md |
| DEV RPC/flag isolation (count=0 in mainnet/testnet) | quick gate + strings | artifacts/…/dev-flag-isolation.log, quick-gate.log |
| Secret scan clean (no PII/creds in diff) | git diff scan | GATE_STATUS.md #15 |
| Quick GO/NO-GO gate | `tests/run_v15_devnet_quick.sh` | artifacts/…/quick-gate.log |

## Network / deployment
| Item | Source | Value |
|------|--------|-------|
| Mainnet height / block time | getinfo (:18232, read-only) | 20795, ~596 s/block → ~29 days to 25000 |
| Deployed binary | getinfo | v0.3.2 |
| Cutover runbook | doc | artifacts/…/RUNBOOK_CUTOVER.md |
| Remaining-gate commands (2nd box) | doc | artifacts/…/REMAINING_GATES.md |

## WAITING_EXTERNAL_RESOURCE (second, non-miner box)
- Full sanitized `ctest` (ASan/UBSan over the whole suite) — REMAINING_GATES.md §6/7.
- testnet-profile `ctest` + long SbPoW run (~8.5 h, real) — §5/§12.
- pre-V15 binary-level compat A/C/E (needs deployed v0.3.2 + chain snapshot) — §9, PREV15_COMPAT_REPORT.md.
- cppcheck/clang-tidy cross-check — §8.

## WAITING_HUMAN_CUTOVER
- merge --no-ff → tag → deploy → coordinated staged restart (blocks 24,900–25,000). RUNBOOK_CUTOVER.md.

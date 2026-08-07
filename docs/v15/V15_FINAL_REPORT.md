# V15 — final technical report

## GATE | RESULT | EVIDENCE | COMMIT
| Gate | Result | Evidence | Commit |
|------|--------|----------|--------|
| Attack matrix (17 single-mutation) | **PASS** 20/0 | attack-matrix.log | f23afb4b |
| Multiblock M02/M03/M08 | **PASS** | m02/m03/m08.log, multiblock-attack-summary.md | 06fe4219 |
| Rollover-cap 100→500→500 | **PASS** | rollover-cap.log (RPC devjackpotstate) | 89e3d3bf |
| Reserve edges (drain + retirement latch) | **PASS** 8/8 | reserve-edges.log | 17341383 |
| Live payout end-to-end (mint=burn=fee=0) | **PASS** | revb1-payout.log | 934543b2 |
| Quick GO/NO-GO gate ×2 | **PASS** GO | quick-gate.log | ae23e51e |
| ctest mainnet (full) | **PASS** 101/101 | regression-ctest.log | fa36eb1e |
| Activation boundary @25000 (no off-by-one) | **PASS** 15/15 | ACTIVATION_BOUNDARY_REPORT.md | 4797696b |
| reorg/restart/reindex crossing activation | **PASS** | run_v15_devnet_{reorg,restart,reindex,failed_reorg}.sh | 960afb6d… |
| Consensus security audit | **PASS** 0 exploitable | SECURITY_AUDIT_REPORT.md (B-1 fixed, B-2→backlog) | 934543b2 |
| Static analysis (GCC -fanalyzer, all V15 code) | **PASS** clean | STATIC_ANALYSIS_REPORT.md | (this) |
| ASan+UBSan (consensus arithmetic 361/0) | **PASS** | sanitizer-consensus.log | 7be5496e |
| DEV RPC/flags/failpoints absent from prod | **PASS** count=0 | dev-flag-isolation.log, RC_MANIFEST.txt | — |
| Secret scan (diff) | **PASS** clean | GATE_STATUS.md #15 | fa36eb1e |
| Rollout + rollback runbook | **PASS** | RUNBOOK_CUTOVER.md | f6ad4296 |
| RC binaries + SHA-256 manifest | **PASS** built, leak-check CLEAN | RC_MANIFEST.txt | f3f1cfde |
| pre-V15 compat (code-level B/D) | **PASS** | PREV15_COMPAT_REPORT.md | 9bcf8504 |
| pre-V15 compat (binary A/C/E) | **WAITING_EXTERNAL_RESOURCE** | needs deployed v0.3.2 + chain snapshot on 2nd box | — |
| ctest testnet | **WAITING_EXTERNAL_RESOURCE** | 2nd box (REMAINING_GATES.md §5) | — |
| Full sanitized ctest (ASan/UBSan whole suite) | **WAITING_EXTERNAL_RESOURCE** | 2nd box (§6/7) | — |
| Testnet long SbPoW run (~8.5 h, real) | **WAITING_EXTERNAL_RESOURCE** | 2nd box (§12) | — |
| cppcheck / clang-tidy cross-check | **WAITING_EXTERNAL_RESOURCE** | tools not installable here (no sudo) | — |
| merge --no-ff → tag → deploy → cutover | **WAITING_HUMAN_CUTOVER** | RUNBOOK_CUTOVER.md; blocks 24,900–25,000 | — |

## Report items
1. **HEAD:** `f3f1cfde` (branch `feat/v15-jackpot-explorer-card`).
2. **git status:** clean for src/include/tests/docs/CMakeLists (all committed+pushed). Untracked =
   build dirs + pre-existing website/* edits (unrelated to V15, not touched).
3. **main:** `b822db4c` — UNTOUCHED (78 commits ahead on the branch, 0 merged).
4. **Mainnet miner:** PID 574503 ALIVE, up >1d16h, never OOM-killed, never touched.
5. **Mainnet height:** 20802.
6. **Blocks to 25000:** 4198 (~29 days at ~596 s/block); to the 24,900 freeze: 4098.
7. **Tests run this cycle:** consensus unit suites (jackpot/lottery-rollover/dtd/eligibility/
   frequency = 361 assertions), full mainnet ctest (101), activation-boundary (15), DEV harnesses
   (attacks 20-case, payout, M02/M03/M08, rollover-cap, reserve-edges), quick gate, plus reused
   green DEV lifecycle harnesses (reorg/restart/reindex/failed-reorg/rollover/soak).
8. **PASS/FAIL/SKIP:** PASS on every gate executed here; **0 FAIL**; SKIP = the 5
   WAITING_EXTERNAL_RESOURCE gates + WAITING_HUMAN_CUTOVER (deferred, not failed).
9. **Sanitizers:** ASan+UBSan clean on the consensus arithmetic (361/0). Full-suite sanitized ctest
   deferred to the 2nd box (RAM/wall-clock: DEV SbPoW is ~4 GB/block; full ASan suite alongside the
   miner is unsafe/slow here).
10. **Static analysis:** GCC `-fanalyzer` clean on sost-node.cpp (1 pre-existing unrelated warning),
    sost-miner.cpp (0), jackpot/params/lottery headers (0). cppcheck/clang-tidy = 2nd box.
11. **Testnet long SbPoW:** WAITING_EXTERNAL_RESOURCE (real ~8.5 h run on the 2nd, non-miner box).
12. **Compat OLD→NEW:** code-level (NEW pre-V15-compatible below fork; OLD incompatible after) PROVEN;
    binary-level A/C/E needs deployed v0.3.2 + a chain snapshot on the 2nd box.
13. **RC artifacts:** clean Release build of node/cli/miner/signtx (MAINNET profile, V15=25000),
    dev-symbol leak-check CLEAN, SHA-256 manifest. NOT merged, NOT tagged.
14. **SHA-256:** sost-node `801516da…`, sost-cli `304a0c20…`, sost-miner `f80cc606…`,
    sost-signtx `b294bfa4…` (full digests in RC_MANIFEST.txt; binaries built at commit 521dad48).
15. **Residual risk:** (a) 4 imperative gates lack REAL evidence pending the 2nd box (testnet long,
    full sanitizers, testnet ctest, pre-V15 binary compat) — none is a known defect; (b) audit B-2
    (failed-reorg restore failure mode) deferred to a tested post-fork hardening release; (c) the
    cutover is the only irreversible step and must be human-supervised before block 25,000.

## Verdict
No FAIL exists and every gate runnable on this (miner-saturated) box is GREEN, with the RC binaries
built and dev-clean. However, four HARD GO gates — the real ~8.5 h testnet SbPoW run, the full
sanitized ctest, the testnet-profile ctest, and the binary-level pre-V15 compat — have NO real
evidence yet because they require a second, non-miner machine (running DEV/testnet SbPoW here risks
OOM-killing the mainnet miner). Per the rule "do not declare READY FOR RC while an imperative gate
lacks real evidence":

**V15 TECHNICAL READINESS: NOT READY FOR RC** — blocked ONLY by WAITING_EXTERNAL_RESOURCE gates
(second machine), not by any defect. Once those four gates are green on the 2nd box, this flips to
READY FOR RC with no code change expected.

**V15 MAINNET: WAITING_HUMAN_CUTOVER.**

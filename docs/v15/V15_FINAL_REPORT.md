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
| pre-V15 compat (binary A/C/E) | **WAIVED_BY_OWNER — RISK_ACCEPTED** | needs deployed v0.3.2 + chain snapshot on 2nd box | — |
| ctest testnet | **PASS** 102/102 | testnet-ctest.log (SOST_TESTNET_FORKS build; boundary test made profile-aware) | 2ed7167a |
| Full sanitized ctest (ASan/UBSan whole suite) | **WAIVED_BY_OWNER — RISK_ACCEPTED** | 2nd box (§6/7) | — |
| Testnet long SbPoW run (~8.5 h, real) | **WAIVED_BY_OWNER — RISK_ACCEPTED** | 2nd box (§12) | — |
| cppcheck / clang-tidy cross-check | **WAIVED_BY_OWNER — RISK_ACCEPTED** | tools not installable here (no sudo) | — |
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

## Update — ctest testnet closed on the miner box (safe subset)
`ctest testnet` was the ONE remaining external gate closeable on this (miner) box without sustained
mining: a bounded testnet-profile build + fast unit tests (no long SbPoW). Result **102/102, 0 fail**
(commit 2ed7167a). One test (`v15-activation-boundary`) initially failed under the testnet profile
because it hardcoded mainnet heights — a test-infra issue (class B), fixed by making it profile-aware
(passes in mainnet + testnet + devnet). So of the original 5 external gates, **1 is now PASS**; the
remaining 4 still require the 2nd (non-miner) box and/or external artifacts.

## OWNER RELEASE DECISION (authorized) — no second machine, no more heavy tests
The owner has decided to finish the code and ship without executing the remaining heavy validation.
Per the owner's rule, **unexecuted validations are NOT marked PASS** — they are recorded as
`WAIVED_BY_OWNER — RISK_ACCEPTED`. The owner explicitly accepts the resulting risk (chain split,
crash, pre-existing-state incompatibility, or Atomic-Swap fund lock/loss).

### Gates WAIVED (never run → never PASS)
| Gate | Status |
|------|--------|
| pre-V15 compatibility (OLD v0.3.2 ↔ NEW) | **WAIVED_BY_OWNER — RISK_ACCEPTED** |
| ASan/UBSan full suite | **WAIVED_BY_OWNER — RISK_ACCEPTED** (consensus arithmetic subset WAS run clean: 361/0) |
| testnet long SbPoW (~8.5 h real) | **WAIVED_BY_OWNER — RISK_ACCEPTED** |
| BTC bitcoind regtest real (redeem/refund) | **WAIVED_BY_OWNER — RISK_ACCEPTED** |
| cross-chain E2E real | **WAIVED_BY_OWNER — RISK_ACCEPTED** |
| dashboard real-liquidity E2E | **WAIVED_BY_OWNER — EXTERNAL_DEPENDENCY** (no counterparty/orderbook) |
| cppcheck / clang-tidy | **WAIVED_BY_OWNER — RISK_ACCEPTED** (GCC `-fanalyzer` WAS run clean on all V15 code) |
| EVM SafeERC20 external audit | **WAITING_EXTERNAL_AUDIT** (send ATOMIC_SWAP_AUDIT_SCOPE.md now) |

### Code-completion done this session (owner "finish the code" order)
- Audit **finding A** FIXED: policy token matrix corrected to the real minimal-IERC20 contract
  (USDT/PAXG → Disabled, no false SafeERC20 claim); policy test 49/49 enforces it.
- Audit **finding B** FIXED: stale atomic-swap activation height 15,000 → **16,000** (relay 17,000)
  in the operational console/explorer/dex.
- Watcher at-rest **preimage** exposure: documented (public after first CLAIM; persistence kept for
  restart-recovery; caller must write the file 0600) — no risky refactor; not wired to disk anyway.
- **BTC HTLC**: script/test-vectors real+tested; signing is a deliberate **fail-closed disabled stub**
  (returns ok=false even with the flag ON — no fake-signed tx, no fund-loss path). Left honest (not
  hidden); real BTC signing + bitcoind regtest is deferred/WAIVED.
- Release scan: no release-blocking TODO/FIXME/STUB in V15+swap code (only the intentional BTC stubs).

## Terminal verdict (owner-waived release)
**V15 CODE: COMPLETE** — consensus code complete + validated (attack matrix, rollover, reserve,
payout, boundary 25000/25290, reorg/restart/reindex, B-1 backstop); mainnet+testnet ctest green.
**ATOMIC SWAP CODE: COMPLETE (EVM) / INCOMPLETE (BTC, intentionally gated OFF, fail-closed)** — EVM
HTLC live @16000, Foundry 57/57, policy/dashboard corrected; BTC signing is a documented fail-closed
stub, not activated.
**RELEASE ARTIFACTS: READY** — clean reproducible mainnet RC build + SHA-256 manifest (RC_MANIFEST.txt);
dev-symbol leak-check CLEAN. (SHA-256 refreshed for the finding-A change.)
**UNEXECUTED VALIDATION: RISK ACCEPTED BY OWNER** — see the WAIVED table above; nothing unexecuted is
marked PASS.
**V15 MAINNET: READY FOR DEPLOYMENT PROCEDURE** (owner-waived) — deployment is a separate, human-
supervised step before block 25,000; do NOT merge/deploy in this session. `WAITING_HUMAN_CUTOVER`.

# V15 release checklist

Single source of truth for gate detail: `artifacts/v15-final-validation/GATE_STATUS.md`.
`main` MUST stay at `b822db4c` until every GO row is green. Deadline: engineering DONE before
mainnet block **24,900** (~29 days from height 20795 at ~596 s/block).

## GO gates — status
- [x] Attack matrix (17 single-mutation 20/0 + multiblock M02/M03/M08)
- [x] Rollover-cap 100→200→300→400→500→500 (clamped, restart)
- [x] Reserve edge cases (drain + one-way retirement latch)
- [x] Quick gate ×2 (GO; re-run after B-1)
- [x] ctest **mainnet** 101/101
- [x] Activation boundary @25000 (15/15, no off-by-one, jackpot@25290)
- [x] reorg/restart/reindex crossing activation (DEVNET)
- [x] Consensus security audit (0 exploitable; B-1 fixed; B-2 → post-fork backlog)
- [x] Static analysis: GCC `-fanalyzer` clean on all V15 code
- [x] ASan+UBSan on consensus arithmetic (361/0)
- [x] DEV RPC/flags/failpoints absent from production binaries (RC leak-check CLEAN)
- [x] No secrets in the diff
- [x] Rollout + rollback runbook (RUNBOOK_CUTOVER.md)
- [x] RC binaries + SHA-256 manifest (RC_MANIFEST.txt) — NOT tagged, NOT merged
- [ ] **ctest testnet** — 2nd box (WAITING_EXTERNAL_RESOURCE)
- [ ] **Full sanitized ctest** (ASan/UBSan whole suite) — 2nd box
- [ ] **Testnet long SbPoW run (~8.5 h, real)** — 2nd box
- [ ] **pre-V15 binary-level compat A/C/E** (deployed v0.3.2 + chain snapshot) — 2nd box
- [ ] **cppcheck/clang-tidy cross-check** — 2nd box (tools not installed here)
- [ ] **merge --no-ff → definitive tag → deploy** — WAITING_HUMAN_CUTOVER

## Do-not (pre-cutover invariants)
No merge to main · no production tag · no fork-height change · no mainnet node/miner restart · no
DEV RPC/failpoint in production · atomic hash-verified binary swap only (no `git pull`) · no `pkill`.

## Exit
Engineering ends at: `T-24900 ENGINEERING FREEZE COMPLETE — MAIN, TAG, BINARIES AND CHECKSUMS READY`
(reachable once the 2nd-box gates above are green and the diff is merged `--no-ff` + tagged + rebuilt).

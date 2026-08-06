# V15 — Final objective: integrate to main + coordinated deployment (LAST consensus fork)

**Objective CHANGED (2026-08-06, user directive):** no longer "RC on a branch only". The end
goal is: finish all V15 gates → merge to `main` → build reproducible binaries from clean main
→ tag → **coordinated, staged restart of the mainnet node + miners** so the whole network runs
the same V15 binary **before block 25000**. Mainnet height ~20700; V15 @ 25000 (~4300 blocks,
~1 month). The DEPLOYED v0.3.2 has V15 gates DEFERRED → reaching 25000 with it activates
nothing; the real deadline is deploying the new binary network-wide, coordinated, before 25000.

Design note (user): V15 being "the last fork" is a project decision, NOT a code assumption —
do not hard-code anything that would prevent a future emergency fix. Keep V15 complete + robust.

## Hard GO gates for touching main (ALL must be green — none may be assumed)
Attack matrix COMPLETE (single-mutation ✅ 17-case + **multi-block scenarios PENDING**) ·
rollover 100→500→500 (DEV RPC) · E01-E20 · quick gate ×2 · ctest mainnet/testnet/DEV ·
ASan · UBSan · static analysis (no critical/high) · pre-V15 compatibility · exact-activation
@25000 · reorg/restart/reindex crossing activation · **testnet long SbPoW run PASS (real, not
declared)** · clean reproducible builds · no DEV RPC / failpoints in production binaries ·
no secrets · rollout + rollback docs. Merge only via `git merge --no-ff` (no history rewrite,
no force-push). Re-run quick gate + smoke + isolation FROM main after merge.

## ⚠️ CRITICAL GOVERNANCE NOTE (highest-risk step in the whole plan)
The **live coordinated restart of the mainnet node + miners for a hard fork** is irreversible
and outward-facing: a mistimed or PARTIAL deploy (some miners on old binary, some on new) can
cause a **chain split** at 25000. The user has pre-authorized autonomous execution GATED on all
GO criteria. Even so, this single step (stop node → swap binary → restart → staged miner
restart) SHOULD be executed with a human reachable at that moment, because:
  - it is the only step that cannot be rolled back cleanly after activation;
  - a canary-miner check + per-miner staged restart is mandatory (see mission §13);
  - the watchdog false-restart failure mode (documented in memory) must be watched.
Recommendation: perform the actual cutover as a human-supervised window, not unattended. This
does NOT block any of the engineering/build/test/merge-prep phases, which proceed autonomously.

## Atomic Swap in main (decoupled from V15 consensus)
EVM HTLC (already active @15000) stays. BTC HTLC may be merged **gated OFF** once regtest-green;
never activated in prod without external crypto review. SafeERC20 may be merged as **undeployed**
code once internal tests green; never deployed with fund custody without external audit. Dashboard
may be merged if it clearly labels mock/estimated quotes. Atomic Swap must NOT contaminate V15
consensus commits (separate commits). V15 must not be blocked by external audits/infra.

## Multi-block attack scenarios — coverage mapping (to avoid redoing proven work)
Several requested "multi-block scenarios" are ALREADY proven by existing green harnesses; the
next session should VERIFY/cite these and only build NEW harnesses for the genuinely-uncovered:
- replay after restart → covered by `run_v15_devnet_restart.sh` (27/27)
- replay after reindex + tampered-J rejection → covered by `run_v15_devnet_reindex.sh`
- failed reorg byte-identical rollback → covered by `run_v15_devnet_failed_reorg.sh` (49/49)
- A→B jackpot reorg (cross-branch J connect/disconnect) → `run_v15_devnet_reorg.sh`
- no-winner accumulation → `run_v15_devnet_rollover.sh` (9/9)
- bulk double-spend of reserve → covered by `dup-all-inputs` (attack matrix)
GENUINELY NEW (need a dedicated multi-block harness, fresh ports e.g. 18990):
  already-spent reserve input · J-at-non-event-height · old-J reused at a later event ·
  stale-state J (reserve changed between template & submit) · coinbase B→A / B→C retaining J ·
  keyless authorization valid-for-one-state-not-current · reorg accumulation↔winner transition.

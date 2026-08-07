# V15 rollout

The full, step-by-step operator procedure (pre-cutover HOLD, atomic hash-verified staged swap of
node → canary miner → miners → explorer, rollback, safety invariants) is
**`artifacts/v15-final-validation/RUNBOOK_CUTOVER.md`** — follow it verbatim at cutover time.

## Sequence (high level)
1. **Finish the 2nd-box gates** (testnet long SbPoW, full sanitizers, pre-V15 binary compat,
   cppcheck) → all green in GATE_STATUS.md / V15_RELEASE_CHECKLIST.md.
2. **Merge** `feat/v15-jackpot-explorer-card` → `main` with `git merge --no-ff` (no history rewrite,
   no force-push). Re-run quick gate + smoke + isolation FROM main.
3. **Tag** the release and **rebuild reproducibly from the tag**; publish binaries + SHA-256 +
   manifest (the RC build recipe is in build_rc.sh / RC_MANIFEST.txt). Pin tag+commit+SHA-256 in the
   operator/miner upgrade notice (covers node AND miners AND explorer).
4. **Reach PRE-CUTOVER HOLD before block 24,900.**
5. **Cutover window (24,900–25,000)** — human-supervised, per RUNBOOK_CUTOVER.md: confirm height →
   stop miners → backup+swap+verify node → canary miner → staged miners → explorer → watch to past 25,000.
6. **Block 25,000** — activation only; observe (50/50 DTD split, Gold Vault/PoPC 0% new emission,
   jackpot from 25290, no chain split).

## Timing (from height 20795, ~596 s/block)
- ~29 days to 25000; ~28 days to the 24,900 freeze. Start the 2nd-box gates + RC now; do NOT wait
  for the 24,900 window to begin deploying — that window is the FINAL check, not the discovery phase.

## Decoupled (does not block V15)
Atomic Swap BTC HTLC stays gated OFF (EVM HTLC already active @15000). It may ride along in the
merge as inert/gated code but must never be activated without external crypto review.

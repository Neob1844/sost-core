# V15 cutover runbook — node + miners + explorer (blocks 24,900 → 25,000)

**Scope:** the supervised, human-attended upgrade of the live mainnet to the V15 binary DURING
the public window (blocks 24,900–25,000), plus rollback. Engineering + build + merge + hashes must
already be DONE before 24,900 (T-24900 freeze). Block 25,000 = activation only (network already on
the new binary). This is the ONLY irreversible, outward-facing step — perform it with a human
reachable. Fill every `<PLACEHOLDER>` at RC time.

## 0. Values to pin at RC (fill before the window)
- TAG: `<v0.4.0-v15>` · COMMIT: `<40-hex>` (from clean `main` after `git merge --no-ff`)
- SHA-256 (from the reproducible build manifest):
  - sost-node   `<sha256>`
  - sost-miner  `<sha256>`
  - sost-cli    `<sha256>`
  - sost-signtx `<sha256>`
- Mainnet RPC (operator-local, NEVER in repo): user/pass via env or `~/.sost/…`, not pasted here.
- Miner inventory (each host, thread count, wallet label): `<list>` — includes the 13-thread CEX
  miner (PID at last check 574503) and any Beelink/laptop miners.

## 1. PRE-CUTOVER HOLD — must be reached BEFORE block 24,900
Do NOT enter the window until ALL are true (see GATE_STATUS.md — every row GREEN):
- [ ] All hard GO gates GREEN (attack matrix, rollover-cap, reserve-edges, quick gate ×2,
      ctest ×3 nets, ASan/UBSan, static, pre-V15 compat, testnet long PASS, isolation, no secrets).
- [ ] `main` has the V15 merge (`--no-ff`), pushed; definitive TAG created and pushed.
- [ ] Reproducible build FROM THE TAG done; binaries + SHA-256 + manifest published.
- [ ] `strings <bin> | grep -E 'devjackpotstate|devsetreorgfailpoint|devchainstate|inject-tx-at1|attack-jackpot|dump-block'`
      returns EMPTY for every production binary (node + miner + cli).
- [ ] Quick gate + smoke + isolation re-run FROM main after merge → GO.
- [ ] Operator/miner upgrade notice published (pins TAG + COMMIT + SHA-256; covers node+miner+explorer).
- [ ] A human operator is reachable for the whole window.

## 2. WINDOW procedure (blocks 24,900–25,000) — atomic, hash-verified, staged
Never use `git pull` as the deploy mechanism. Never `pkill` by name. Swap binaries by atomic
`mv` of a hash-verified file. Keep the OLD binary saved for rollback.

1. **Confirm state:** `getblockcount` / `getbestblockhash` on the live node; height in [24,900, 25,000).
2. **Verify new binaries:** `sha256sum -c` against the pinned manifest on EVERY host. Abort if any mismatch.
3. **Stop miners** (all of them) cleanly (SIGINT/stop, not pkill). Confirm no miner is producing.
4. **Node:** stop → BACKUP chain dir → atomically swap in the new `sost-node` (verified) → restart.
   Confirm it loads the existing chain with NO rejected historical blocks and same tip hash.
5. **Canary miner:** start ONE miner on the new binary. Watch for: block accepted, no `REJECTED`,
   no timestamp/fork warnings in the node log for several blocks. (Recall: `--realtime` is MANDATORY
   or blocks get "timestamp too far in future" → stall.)
6. **Staged miners:** bring the remaining miners up ONE AT A TIME on the new binary, each confirmed
   accepted before the next. Never leave miners split across old/new binaries near 25,000.
7. **Explorer:** deploy the matching explorer package; confirm it reports the same commit/version.
8. **Confirm uniformity:** every node/miner/explorer on the SAME commit + version.
9. **Watch to activation:** monitor the watchdog (false-restart failure mode), stalls, rejects,
   forks, until several blocks PAST 25,000.

## 3. Block 25,000 — activation (observe only)
Expect: DTD 50/50 split active, Gold Vault / PoPC 0% NEW emission (dormant, not removed), the
Historical Jackpot live per cadence, NO chain split. No dev/merge/build/deploy at this point.

## 4. ROLLBACK (only valid BEFORE activation at 25,000)
If the canary or any node shows rejects/split/instability while still below 25,000:
1. Stop the affected miners.
2. Node: stop → restore the OLD binary (kept from step 2.4) + the backed-up chain dir → restart.
3. Confirm the network re-converges on the old binary; miners restart on old binary (`--realtime`).
4. Post-mortem before re-attempting. NOTE: after 25,000 activates, a clean rollback is NOT possible
   (the fork rules are live) — which is why the canary + staged restart must finish before 25,000.

## 5. Terminal states
- Engineering: `T-24900 ENGINEERING FREEZE COMPLETE — MAIN, TAG, BINARIES AND CHECKSUMS READY`.
- Window:      `V15 UPGRADE COMPLETED BEFORE BLOCK 25,000 — NODE, MINERS AND EXPLORER READY FOR ACTIVATION`.

## Safety invariants (all phases)
Never touch the mainnet miner outside the staged procedure · atomic hash-verified binary swap ·
no `git pull` in production · no `pkill` by name (PID/port only) · human-supervised · keep OLD
binary + chain backup until several blocks past activation · `--realtime` on every miner.

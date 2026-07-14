# V15 Final Decentralization Fork + Historical DTD Jackpot — FINAL REVIEW PACKAGE

**Status:** Code-complete on the working tree. **NOT committed. NOT deployed. NOT on mainnet.** For Codex audit
before commit/PR/runtime. Build: `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release`.

## Build & tests
- `sost-node`, `sost-miner`, `sost-cli` — all compile clean.
- **ctest: 102/103 pass.** Jackpot suites: `v15-jackpot = 75/75`, `v15-jackpot-runtime = 11/11`
  (real UtxoSet ConnectBlock/DisconnectBlock), `v15-jackpot-reorg = 27/27` (revert-onto-fork +
  reconnect, zero residue). Base V15 = 37/37; coinbase-phase2 50/50; lottery-eligibility 77/77;
  lottery-rollover 53/53; lottery-frequency 71/71; v14-fork-gates pass; PoPC suites profile-aware
  (mainnet asserts retirement, green); tx-validation 53/53 (TC51b updated for retired-PoPC carrier).
- **The one failure — `htlc-expired-lock-template` — is PRE-EXISTING and unrelated to V15.** It
  fails identically (2/8) on a clean `main` HEAD with every V15 change stashed (verified 2026-07-13,
  `git stash -u` → build → run → same result). No V15/jackpot suite regresses.
- Runtime verification of Codex's 3 pre-runtime checks: `docs/V15_JACKPOT_RUNTIME_VERIFICATION.md`.
- Files changed: 22 (`+1790 / -47`) + 2 new runtime test files + verification doc. See
  `v15f_diff_stat.txt`, `v15f_files.txt`, `v15f_full.patch`.

## What the fork does
V15 (`V15_HEIGHT = 20000`) is the final consensus change: 50% miner / 50% DTD every block (Gold-Vault + PoPC
emission redirected to DTD), sliding-2016 DTD eligibility, PoPC/Gold-Vault automation retired. Plus the
**Historical DTD Jackpot**: the existing ~48–58k SOST in Gold Vault + PoPC are progressively returned to active
miners — a real supply-neutral protocol spend, no treasury, no founder.

## Jackpot — technical summary (the audit target)
1. **jackpot tx is a normal tx at fixed position `txs[1]`** — NOT a coinbase output. **No mint, no
   `OUT_COINBASE_JACKPOT`, no freeze-reissue, no reserve counter.** Reserve = live sum of Gold/PoPC UTXOs.
2. **Cadence** = every 96th DTD lottery block since V15 (~288 blocks, approximate). **First jackpot = height
   20,286** (off-by-one pinned by test). Reuses the DTD winner — identical eligibility (2016 / cooldown /
   anti-dominance / SbPoW / uniform); no separate eligibility path.
3. **Amount** (`compute_jackpot`): base 100 SOST + rollover, per-payout cap 500, never > reserve, exhaust →
   disabled forever. Overflow-guarded.
4. **FIFO** (`plan_jackpot_spend`): oldest reserve UTXOs first (`height, txid, vout` total order). **Change
   returns to `ADDR_GOLD_VAULT`** (canonical reserve-change address), re-locked by the address rule.
5. **Byte-exact build** (`build_expected_jackpot_tx`): both the miner (via node getlotterystate `jackpot_tx_hex`)
   and the validator (`validate_block_jackpot`) call the SAME function with the SAME inputs → identical bytes by
   construction. `UTXOEntry.height` provides the FIFO key (stop-condition satisfied).
6. **Block validation** (`validate_block_jackpot`, called from `process_block` — the SINGLE common path:
   submitblock, P2P, reorg, chain-load): on a jackpot opportunity with a winner+payout, requires `txs[1]`
   byte-exact or rejects; otherwise the **address-lock** rejects ANY tx spending Gold/PoPC UTXOs.
7. **Generic-tx-loop exemption** (the bug found): the jackpot tx has no signature and fee 0, so the generic
   `ValidateTransactionConsensus` would reject it. Reserve-spending txs are exempted from that check **but still
   connected** (UTXO effects apply); `validate_block_jackpot` is their sole authority.
8. **Mempool reject**: `handle_sendrawtransaction` rejects ANY tx spending Gold/PoPC UTXOs, unconditionally —
   the jackpot tx can never enter the mempool (even signed, even near an opportunity, even the change UTXO).
9. **State**: `StoredBlock.jackpot_pending_after` — optional field, missing == 0, emitted only when > 0,
   restored from the tip on reorg (identical pattern to `pending_lottery_after`; no historical-serialization change).

## Miner ↔ validator agreement
The node's `getlotterystate` builds the jackpot tx and returns `jackpot_tx_hex`; the miner prepends it to
`txs[1]`. Because both sides call `build_expected_jackpot_tx(plan_jackpot_spend(collect_reserve_utxos(...)), winner, gold)`
with the same (reserve UTXOs at tip, DTD winner, pending), the produced tx is byte-identical to what the
validator recomputes. Divergence is structurally impossible.

## Known risks / NOT yet done (deliberately, before commit)
- ~~No end-to-end runtime test~~ — **DONE.** `v15-jackpot-runtime` (11/11) connects a real jackpot block via
  `UtxoSet::ConnectBlock` (the same call `process_block` makes at acceptance): reserve UTXOs drop, winner paid,
  supply neutral, and `DisconnectBlock` undoes it exactly.
- ~~No runtime reorg test~~ — **DONE.** `v15-jackpot-reorg` (27/27) reverts the jackpot onto a competing
  higher-work fork and reconnects it, asserting the FULL UTXO map is bit-identical at each fork point (zero
  residue), plus the `jackpot_pending_after` undo semantics at the value level.
- **A two-process live-node mining run is still not done** — but it is infeasible pre-`V15_HEIGHT=20000`
  (would need ~20,286 mined PoW blocks) and the node's reorg path calls the very ConnectBlock/DisconnectBlock the
  two tests above exercise directly. The UTXO-/undo-level behavior is fully proven.
- **Explorer/cards not wired to real data** (reserve remaining, next jackpot, pending, last winner, history).
- **Audit focus points for Codex:** (a) the generic-tx-loop exemption (§7) — is `spends_reserve` detection
  airtight and can no non-jackpot reserve-spend slip through? (b) fee accounting for the zero-fee jackpot tx;
  (c) the FIFO determinism across the real UTXO map; (d) that `process_block` truly is the only block-acceptance
  path; (e) supply neutrality (Σ jackpot payouts ≤ reserve, no mint).

## After Codex sign-off
1. End-to-end runtime test (node+miner).  2. Runtime reorg test.  3. Explorer real data.  4. Commit / PR /
coordinated flag-day before block 20,000.  Nothing is deployed or committed until then.

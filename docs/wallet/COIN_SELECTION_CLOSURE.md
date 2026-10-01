# Coin selection — closure, root-cause of the "no-mempool" send, and review A–G

**Status:** DONE (algorithm + wiring + unit + regression + live e2e closure). See
`COIN_SELECTION_IMPL.md` / `COIN_SELECTION_AUDIT.md` for the design.

## 1. Root cause of the earlier "send returns a txid but B receives 0 / mempool empty"
NOT a protocol, CLI, serialization, signing or mempool bug, and NOT a coin-selection
regression. **The functional test harness omitted `--yes`.** `sost-cli send` prints a
TRANSACTION SUMMARY (which always echoes a locally-computed TXID) and then, unless
`--yes`/`-y` is given, blocks on `Confirm send? [yes/no]:`. With no TTY/stdin the
`fgets` returns null → "Transaction cancelled." → the CLI returns 0 **before ever
calling `sendrawtransaction`**. So the tx was never broadcast; the SUMMARY TXID was
mistaken for an acceptance. It reproduced under the base (greedy) build for the same
reason. Fix: the harness now passes `--yes`.

Diagnosis followed Ángel's checklist: isolated devnet node on **exclusive** ports
(rpc 18262 / p2p 20262, `--connect 127.0.0.1:1`), verified the listener PID and
`getinfo` (blocks:0, our node — not the mainnet node on 18444), and captured the full
send output. The CLI already distinguishes acceptance correctly: it prints
"TX accepted by node! Txid: …" only when `sendrawtransaction` returns a txid, else
"TX NOT CONFIRMED by the node (<reason>)" and leaves the inputs UNSPENT.

## 2. Mandatory closure test — PASSED
Wallet A (mature coinbase) → build+sign (unified selector, 6 inputs) → **explicit
node acceptance** ("TX accepted by node!") → **present in `getrawmempool` of the same
node** → mined into a block → confirmed (`getrawtransaction` on-chain) → **B credited
exactly 20.00000000 SOST** → A reconciled (39.25504327 → 27.10596522). A bare txid is
NOT accepted as proof; every one of these steps was checked. Reproducible via
`scripts/coin_selection_closure_test.sh`.

## 3. Review points A–G
- **A (effective-value vs BnB on nominal):** the caller passes `needed = amount + fee`
  (the CLI's exact two-pass fee), and `select()` splits economic (`amount - input_cost
  > 0`) vs uneconomic before BnB, so cost estimation does intervene. BnB matches within
  a change-cost window; documented as a heuristic, never the consensus fee.
- **B (fee-rate fixed at 10):** that value is the per-input **economic/dust heuristic**,
  NOT the fee — the real fee is the absolute `fee` argument from the CLI two-pass, so
  there is no underpayment and no unbounded re-adjust loop (fixed 3-pass). It equals
  `FEE_RATE_DEFAULT`; to remove the divergence when the user sets `--fee-rate`,
  `create_transaction` now takes a `fee_rate` param and the `send` path threads
  `g_fee_rate` into both selection and the dust threshold.
- **C (changeless vs always-make-change):** wallet.cpp created a change output for ANY
  positive surplus, so a BnB "changeless" pick could still emit a dust output. Fixed:
  all four builders now **absorb sub-dust change into the fee**
  (`change < dust_threshold(fee_rate)` → dropped); the recipient still gets the exact
  amount, the remainder goes to the miner.
- **D (lock_until with unknown height):** the old filter
  `lock_until != 0 && chain_height >= 0 && chain_height < lock_until` SKIPPED the lock
  check when the height was unknown (`chain_height < 0`) → a transient RPC failure could
  select and **spend a BOND/ESCROW-locked output**. Fixed to **fail closed**: a locked
  output is spendable only when the height is known AND has reached the unlock.
  Regression test `tests/test_lock_failclosed.cpp` (5/5).
- **E (BnB depth / overflow on huge wallets):** BnB already had a 100k-try cap; added a
  `BNB_MAX_CANDIDATES=256` cap on the candidate set (top-K largest) so recursion depth is
  bounded regardless of wallet size — the largest-first fallback still ranges over ALL
  economic UTXOs, so fundability is never reduced. SOST supply fits int64 with margin.
- **F (constraints preserved in all 4 callers):** `select_coins` is a strict SUPERSET:
  spendable-by-us, optional `--from` pin, never constitutional (Gold Vault / PoPC),
  never locked (adds the `lock_until` check two of the old loops lacked = a latent-bug
  fix), maturity already applied by `list_unspent`.
- **G (tests):** unit **20/20** (incl. new BnB-cap + dust-threshold cases); fail-closed
  lock regression **5/5**; live CLI e2e closure PASSED. **PSBT** (`psbt.cpp`) performs NO
  coin selection of its own — it takes caller-supplied `utxo_refs`, so `select_coins` is
  the single upstream selector and there is nothing to unify there. The **web wallet**
  has no client-side selector either. Mixed-amount metric (unit level, pure-coinbase
  devnet cannot mint varied amounts directly):

  | selector | inputs | change | note |
  |---|---:|---:|---|
  | old oldest-first greedy | 46 | 28.0 SOST | drags in all 40 dust UTXOs |
  | new unified | 1 | 40.0 SOST | picks the single 100-SOST UTXO; avoids dust |

## 4. Not claimed
No mainnet assertion is made from a devnet harness. PSBT/web-wallet "coin-selection
tests" are N/A (no selection logic there). The mixed-amount advantage is shown at unit +
micro-benchmark level, not via a varied-amount live send (devnet coinbases are equal).

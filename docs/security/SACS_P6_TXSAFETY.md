# SACS P6 — Tx-Safety State Machine Wired to Real Node RPC

**Status:** EXECUTED — full lifecycle demonstrated with a real devnet tx.
**Consensus impact:** NONE. The tx-safety tracker (`website/lab/sacs/sacs-tx-safety.js`)
is exchange/wallet-side credit logic, never a consensus rule.

## What was wired
`tests/sacs_txsafety_poll.js` builds a live `chainView` from node RPC and drives the
REAL `sacs-tx-safety.js` tracker:
- `txConfirmedIn(txid)` ← `getrawtransaction <txid> 1` (`confirmed`,`block_height`) —
  scans only the CANONICAL chain, so a reorged-out tx disappears from it.
- `inMempool(txid)` ← `getrawmempool`.
- `tipHeight` ← `getblockcount`; `blockHashAt` ← `getblockhash`.
The tracker is long-lived (its `everConfirmed` flag persists), so it distinguishes
reorged-out (`REORGED`) from re-entered (`REENTERED_MEMPOOL`).

## Scenario (isolated devnet, both nodes `--noseed`)
A & B share a 6-block prefix (fed B[1..6]→A) so the tx's funding coinbase@1 survives
the reorg. B sends a real tx spending its matured coinbase (`--from-label m ... --yes`),
mines it into block 7. A mines a heavier divergent chain 7..10 (no tx). Feeding
A[7..10]→B reorgs out B's block 7 (disconnect depth 1).

## Result — real RPC-driven transitions
```
tip=6  status=PENDING            inMempool=true
tip=7  status=CONFIRMED  confHeight=7 conf=1  inMempool=false
tip=10 status=REENTERED_MEMPOOL  inMempool=true  note="back in mempool after reorg"
```
Corroborated by the P4 monitor on the same node:
```
REORG_STARTED
REORG_COMPLETED   recovered 1 txs, 0 conflicts
TX_REORGED        1 tx re-entered mempool after disconnect
```
(This run also upgrades the monitor's `TX_REORGED` event from code-complete to
runtime-proven — see SACS_P4_P5_MONITOR.md.)

## The safety property
At `REENTERED_MEMPOOL` the tracker reports `confirmations=0` and status != CONFIRMED,
so `creditable()` returns false: a wallet/exchange UI reading this can NEVER show the
disappeared output as available/spendable. The confirmed→unconfirmed transition is
driven entirely by real chain state, not by any client-side guess.

Harness: `tests/sacs_p6_txsafety.sh` (+ `tests/sacs_txsafety_poll.js`,
`tests/sacs_feedchain.py`).

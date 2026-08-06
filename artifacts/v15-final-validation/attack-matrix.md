# V15 valid-PoW Attack Matrix — coverage inventory (V15-A)

`--attack-jackpot` mutations are compiled ONLY under `SOST_DEVNET_FORKS` in `src/sost-miner.cpp`.
The miner mutates the canonical jackpot, then its NORMAL path recomputes the merkle root and
mines valid DEV PoW → ordinary `submitblock` → node must reject with ZERO state mutation.

## Already implemented (16 mutations) & exercised (13) by `run_v15_devnet_attacks.sh`
| Mutation | In miner | In harness | Notes |
|---|---|---|---|
| wrong-winner | ✅ | ✅ | |
| winner-self (pay current miner) | ✅ | ✅ | anti-self-payout |
| payout-plus / payout-minus / payout-zero | ✅ | ✅ | amount tamper |
| reverse-inputs | ✅ | ✅ | input order |
| remove-input / dup-input / foreign-input | ✅ | ✅ | reserve input set |
| extra-output | ✅ | ✅ | |
| dup-jackpot / remove-jackpot | ✅ | ✅ | position/presence at tx[1] |
| coinbase-mutate | ✅ | ✅ | coinbase-derived cur_miner |
| remove-winner-output | ✅ | ✗ | UNBUILDABLE: 0-output tx fails Serialize (stronger guarantee) |
| move-jackpot | ✅ | ✗ | NO-OP in DEV (only 2 txs, no tx[2] to swap) |

## DONE 2026-08-06 — 4 new valid-PoW single-mutations (17-case matrix, all rejected, honest block accepted)
| Mutation | Rejected+atomic |
|---|---|
| input-index-bump (wrong vout on a reserve outpoint) | ✅ |
| input-txid-flip (nonexistent/noncanonical input txid) | ✅ |
| payout-intmax (INT64_MAX payout, serialization/overflow bound) | ✅ |
| dup-all-inputs (bulk double-spend of every reserve UTXO) | ✅ |
Evidence: artifacts/v15-final-validation/attack-matrix.log (RESULT: PASS, 20/0).

## STILL pending (multi-block scenarios — need harness scenarios, not simple mutations) — TODO
Some are single-mutation (add to miner + harness); several need MULTI-BLOCK setup
(a plain mutation can't express them) and belong in dedicated harness scenarios:

| # | Case | Kind | Notes |
|---|---|---|---|
| 1 | wrong reserve-change amount | miner mutation | new |
| 2 | wrong reserve-change script | miner mutation | new |
| 3 | artificial change when canonical change is 0 | miner mutation | needs a 0-change fixture height |
| 4 | missing required positive change | miner mutation | needs a positive-change fixture |
| 5 | alternative valid-but-noncanonical reserve UTXO | miner mutation | pick a different real UTXO |
| 6 | miner coinbase output used as J input | miner mutation | new |
| 7 | already-spent reserve input | scenario | needs a prior spend of that UTXO |
| 8 | J at a non-event height | scenario | submit a jackpot tx at a non-cadence height |
| 9 | old J reused at a later event | scenario | replay a prior height's canonical J |
| 10 | stale-state J (built from pre-block reserve) | scenario | reserve changed between template & submit |
| 11 | coinbase B→A while retaining old J | scenario | template for B, coinbase pays A |
| 12 | coinbase B→C while retaining old J | scenario | |
| 13 | template requested for B but final coinbase pays A | scenario | template/coinbase mismatch |
| 14 | serialization-boundary / max-min field mutations | miner mutation | fuzz-ish |

## Verification requirements (all cases)
valid serialization · recalculated txids · correct merkle · valid DEV PoW · ordinary
submitblock · EXACT rejection reason (not just "exit!=0") · zero state mutation (tip/height/
reserve byte-equal before==after) · node responsive after · run matrix ≥3× if any flakiness ·
then submit the HONEST canonical block and require acceptance.

## Build isolation
Use a SEPARATE build dir (e.g. `build-v15-attack-matrix`) — do NOT rebuild `build-devnet`
(shared by other DEV harnesses). Miner mutations are `#ifdef SOST_DEVNET_FORKS`.

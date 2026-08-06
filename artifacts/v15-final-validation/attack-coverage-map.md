# Multi-block attack scenarios — RIGOROUS coverage verification (V15-A)

Per the CTO rule: a scenario is "covered" ONLY if an existing harness asserts EXACTLY the
same property (with cited test + assertions + log). Conceptual similarity is NOT coverage.
This audit re-classifies each requested multi-block scenario honestly.

| # | Scenario | Existing harness | Exact assertion it proves | Coverage | Action |
|---|---|---|---|---|---|
| 1 | already-spent reserve input | — | none | **NONE** | NEW harness |
| 2 | J at non-event height | run_v15_devnet_attacks.sh | attacks only mutate an EXISTING jackpot AT a jackpot height; never injects one at a non-cadence height | **NONE** | NEW (needs miner inject-J flag) |
| 3 | old J reused at a later event | — | none | **NONE** | NEW |
| 4 | stale-state J (reserve changed between template & submit) | — | none | **NONE** | NEW |
| 5 | coinbase B→A retaining B's J | run_v15_devnet_attacks.sh `coinbase-mutate` | flips coinbase pkh @ SAME height (not a cross-branch B→A reorg) | **PARTIAL** | NEW scenario (reorg-context) |
| 6 | coinbase B→C retaining B's J | as #5 | — | **PARTIAL** | NEW |
| 7 | keyless auth valid for other state, invalid for current | — | none | **NONE** | NEW |
| 8 | replay of a REJECTED attack after restart | run_v15_devnet_restart.sh | proves HONEST chain reloads byte-identical — does NOT prove a rejected attack STAYS rejected post-restart | **PARTIAL** (honest side only) | extend: after an attack, restart, re-submit, assert still rejected + reserve intact |
| 9 | replay after reindex / tampered persisted J | run_v15_devnet_reindex.sh | a tampered persisted jackpot is rejected on load, reserve never spent | **FULL** | cite (add attack-block replay variant if time) |
| 10 | failed reorg byte-identical rollback | run_v15_devnet_failed_reorg.sh | 49/49: manifest before==after, g_blocks==g_block_undos, node healthy | **FULL** | cite |
| 11 | A→B jackpot reorg (cross-branch J connect/disconnect) | run_v15_devnet_reorg.sh | J_A disconnected, J_B connected, state==clean B | **FULL** | cite |
| 12 | no-winner accumulation preserves reserve | run_v15_devnet_rollover.sh | 9/9: reserve byte-stable across 5 no-winner events | **FULL** | cite |
| 13 | bulk double-spend of reserve | run_v15_devnet_attacks.sh `dup-all-inputs` | valid-PoW block duplicating all reserve inputs REJECTED, zero mutation | **FULL** | cite |
| 14 | reorg accumulation↔winner transition | reorg + rollover (separately) | neither proves the accumulation-then-winner transition across a reorg | **PARTIAL** | NEW scenario |

## Honest conclusion
- **FULL (cite, no new work):** #9, #10, #11, #12, #13.
- **PARTIAL (existing harness proves the honest half only — must be EXTENDED for the attack/transition half):** #5, #6, #8, #14.
- **NONE (genuinely new — dedicated multi-block harness required):** #1, #2, #3, #4, #7.

So the earlier "6 genuinely new" was optimistic: honestly it is **5 NONE + 4 PARTIAL = 9 scenarios of real new work** (plus citing 5 proven). The PARTIAL ones matter: e.g. #8 — the restart harness does NOT prove a rejected attack stays rejected after a restart; that is a real gap to close, not an assumed cover.

## Next build (fresh ports ~18990), needs new miner capabilities under #ifdef SOST_DEVNET_FORKS:
- `--inject-jackpot-at <height>`: build+include a canonical-looking jackpot tx at a non-event height (#2).
- `--replay-jackpot <height>`: include a prior height's jackpot tx again (#3, #7).
- `--stale-jackpot`: build the jackpot from a snapshot reserve, then submit after the reserve moved (#4).
- reorg-context coinbase substitution scenarios reuse the failed_reorg fork machinery (#5,#6,#14).
- already-spent-reserve (#1): pre-spend a reserve UTXO in an ordinary tx, then a jackpot that still lists it.
- restart/reindex-replay-of-attack (#8, extend): submit attack → restart/reindex → re-submit → assert still rejected, reserve intact.

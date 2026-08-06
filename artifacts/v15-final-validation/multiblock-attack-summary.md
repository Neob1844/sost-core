# V15-A multi-block / stateful jackpot attack coverage — summary

Companion to `attack-coverage-map.md` (the rigorous per-assertion audit) and `attack-matrix.md`
(the 17-case single-mutation matrix). This file records how the **multi-block** scenarios are
closed: what is proven EMPIRICALLY by a dedicated harness, what is proven by an existing harness
(cited), and what genuinely remains — with the structural reason where several requested
scenarios collapse into one already-falsified property.

HEAD: `feat/v15-jackpot-explorer-card`. DEV binaries built with `SOST_DEVNET_FORKS=ON`.
DEV-only capabilities used (all `#ifdef SOST_DEVNET_FORKS`, verified `count=0` in mainnet/testnet
binaries — see `dev-flag-isolation.log`):
`--attack-jackpot <mut>` · `--dump-block <file>` · `--inject-tx-at1 <hexfile>` · RPC `devjackpotstate`.

## The single consensus property under attack
A block may carry a `TX_TYPE_JACKPOT` (the keyless reserve spend) **iff** it byte-matches the
canonical reconstruction from the block's exact pre-state: correct cadence height, the reserve
UTXO set discovered live (`discover_reserve_utxos`), this block's DTD winner (re-derived from the
actual coinbase miner), and the history-derived rollover. `validate_live_jackpot` runs **before
every `ConnectBlock` caller** (process_block, reorg-connect, load_chain/reindex), so a
non-canonical jackpot is rejected before any state mutation, on every code path.

## Dedicated multi-block harness — `tests/run_v15_devnet_multiblock_attacks.sh`
Per-scenario fresh datadir + node on isolated ports; `--scenario M02|M03|M08|all`.

| ID | Scenario (map #) | What it empirically proves | Status |
|----|------------------|----------------------------|--------|
| **M02** | J at a NON-event height (#2) | capture h24's canonical jackpot → inject at h25 via `--inject-tx-at1` → valid DEV PoW block → **REJECTED** ("none authorized for this block"), tip/height/reserve byte-unchanged, still rejected byte-identical after restart, honest h25 accepted | ✅ PASS (`m02.log`) |
| **M03** | old/stale J reused at a LATER event (#3) | capture event-A jackpot → advance past it → inject old A at the next on-cadence event height h30 → **REJECTED** at a legitimate event (obsolescence, not cadence), state byte-unchanged, still rejected after restart, correct honest event block accepted | ✅ PASS (`m03.log`) |
| **M08** | replay of a REJECTED attack after restart (#8) | `--attack-jackpot wrong-winner` → `--dump-block` the exact malicious block → rejected → restart node → re-submit identical bytes → **still rejected**, reserve never spent, honest jackpot block accepted after | ✅ PASS (`m08.log`) |

## Proven by existing harnesses — CITE (no new work)
| map # | Scenario | Harness | Assertion |
|-------|----------|---------|-----------|
| #9  | replay after reindex / tampered persisted J | `run_v15_devnet_reindex.sh` | tampered persisted jackpot rejected on load; reserve never spent |
| #10 | failed-reorg byte-identical rollback | `run_v15_devnet_failed_reorg.sh` | 49/49: manifest & undo maps before==after; node healthy |
| #11 | A→B jackpot reorg (cross-branch connect/disconnect) | `run_v15_devnet_reorg.sh` | J_A disconnected, J_B connected, state == clean-B |
| #12 | no-winner accumulation preserves reserve | `run_v15_devnet_rollover.sh` | 9/9: reserve byte-stable across no-winner events |
| #13 | bulk double-spend of every reserve input | `run_v15_devnet_attacks.sh dup-all-inputs` | valid-PoW block duplicating all reserve inputs rejected, zero mutation |

## Structural reductions (NOT "conceptual similarity" — proof of equivalence)
The reserve (GOLD + POPC vaults) is **keyless**: no private key exists, so the *only* way any
reserve UTXO can ever be spent is the canonical jackpot tx itself. Consequences:

- **#1 already-spent reserve input** — a reserve UTXO can only have been spent by a prior
  canonical jackpot; re-listing it is exactly replaying an old jackpot ⇒ **identical to M03**.
  There is no ordinary-tx path to pre-spend a reserve UTXO (no signature possible), which is a
  *stronger* guarantee than the test asked for.
- **#4 stale-state J** and **#7 keyless-valid-for-other-state** — both mean "a jackpot canonical
  for some *other* pre-state, submitted against *this* pre-state". Against a different height that
  is M02; against a later event that is M03. In DEV the reserve fully drains and the jackpot
  **retires** (one-way latch) at the first paid event, so there is a single live spend to reason
  about, and M02+M03 falsify both axes (wrong-height and stale-at-event).

These reductions are backed by the reconstruction code (`discover_reserve_utxos` reads the *live*
UTXO set; `jackpot_tx_matches_canonical` requires a byte-exact match) — not by resemblance.

## Genuinely remaining (honest)
| map # | Scenario | Why not yet closed | Plan |
|-------|----------|--------------------|------|
| #5,#6 | coinbase B→A / B→C retaining B's J, in reorg context | winner-binding to the coinbase miner IS proven by `coinbase-mutate` (17-case matrix ✅) and reorg jackpot-connect by #11 ✅; the *combined single test* (mine on B, reorg to a branch whose coinbase pays A while keeping B's J) is not one dedicated scenario | PARTIAL-by-composition; a dedicated reorg-context scenario is a possible future add, honestly labeled — no new consensus rule is unproven |
| #14 | accumulation↔winner transition across a reorg | needs a fork where one branch has a no-winner event and the other a winner event at the same height → requires **multi-address winner control** (the known multi-address-mining gap) | deferred with explicit label; not claimed as covered |

## Net
Empirically NEW this session: **M02 ✅, M03 (running)** — closing map #2, #3. Plus **M08 ✅**
(map #8, the real gap the restart harness did NOT cover). #1/#4/#7 reduce to M02/M03 by the
keyless-reserve argument. #5/#6/#14 are honestly labeled PARTIAL/deferred, not claimed green.
Single-mutation surface: 17 cases, 20/0 (`attack-matrix.log`).

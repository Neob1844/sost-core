# `gethistoricaljackpotstatus` — read-only Historical DTD Jackpot status RPC

**Status:** PREPARED, NOT DEPLOYED. Built + committed on branch
`feat/jackpot-eligible-addresses-rpc`. Deploy AFTER the first jackpot `#25,290` is
confirmed and the mainnet node is stable (backup → deploy binary → controlled restart →
health/sync/RPC/Explorer checks). Do **not** restart the mainnet node before `#25,290`.

## Why
`getlotteryaudit <height>` already returns the canonical `eligible_count` + `winner_address`
for a mined jackpot height (it calls `compute_lottery_eligibility_set`, which applies
`dtd_recency_window_at(height)` internally → the 20,000-block jackpot recency window at a
jackpot height). What it does **not** return is the full per-address eligible list, and it
cannot preview a future height (requires `height <= tip`). This RPC adds both.

## Guarantees
- **READ-ONLY.** No consensus / miner / wallet / UTXO mutation. Only reads `g_blocks` +
  `g_utxo_set` under `g_chain_mu`.
- Reuses ONLY canonical helpers: `compute_lottery_eligibility_set`,
  `select_lottery_winner_index_from_history`, `derive_rollover_before`,
  `dtd_recency_window_at`, `is_hist_jackpot_height` — identical to the consensus path, so
  the eligible set matches what the block producer/validator computes.

## Call
`gethistoricaljackpotstatus [height]`

- **no arg** → PRELIMINARY set computed at the current tip *as if the next jackpot were
  drawn now* (uses the 20,000 jackpot recency window). `winner_address = ""` (undetermined
  until the real `TX_TYPE_JACKPOT` exists).
- **a past jackpot height `<= tip`** → FINAL set for that jackpot + canonical
  `winner_address`.
- a non-jackpot height `<= tip` → error `height is not a jackpot height`.
- a future height → PRELIMINARY for that height's window.

## Result fields
| field | meaning |
|---|---|
| `current_height` | chain tip |
| `next_jackpot_height` | next jackpot at/after tip+1 |
| `blocks_remaining` | `next_jackpot_height - current_height` |
| `is_historical_jackpot` | is the tip itself a jackpot height |
| `mode` | `"preliminary"` or `"final"` |
| `target_height` | height the eligibility was computed for |
| `recency_window` | `5000` normal / `20000` at a jackpot height |
| `reserve` / `reserve_stocks` | live balance of the frozen Gold Vault + PoPC Pool reserve addresses |
| `base_payout` | `100` SOST base |
| `cap_payout` | `500` SOST hard cap (rollover only) |
| `rollover` | rollover carried into `next_jackpot_height` (0 for the first) |
| `expected_payout` | `min(base + rollover, cap, reserve)` |
| `winner_address` | canonical winner (FINAL only; `""` in PRELIMINARY) |
| `eligible_count` | size of the eligible set |
| `eligible_addresses[]` | **the exact per-address eligible set** (`sost1…`) |

## Amount rule (consensus, params.h / jackpot.h)
`HIST_JACKPOT_BASE_STOCKS = 100 SOST` base; `HIST_JACKPOT_CAP_STOCKS = 500 SOST` hard cap
reachable ONLY via rollover from prior jackpots that had **no eligible winner**. The first
jackpot `#25,290` pays exactly **100 SOST** (no prior rollover). The Explorer must always
show the **real on-chain amount** parsed from the jackpot transaction — never a hardcoded
value. `500` is a real consensus maximum, not a synthetic test value.

## Explorer wiring (also on this branch, deploy together)
The dashboard (`SJP.openDash`) calls this RPC; when present it fills
`JACKPOT ELIGIBLE (20k)` with `eligible_count` + status `PRELIMINARY · final at #25,290`
(pre-jackpot) or `FINAL · verified on-chain` (post), and lists `eligible_addresses[]`.
Until the RPC is deployed, the call fails gracefully and the cell shows
`calculated at #25,290`.

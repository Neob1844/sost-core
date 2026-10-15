# V17 ECONOMICS (block #40,000) — 80 / 15 / 5 and the Jackpot accumulator J

Status: **NORMATIVE** for the V17 consensus package. Owner-frozen decisions of
2026-10-14 (E1, E2, E3 and the invariants). Implementation on branch
`feat/v40k-econ`; nothing is deployed by this document.

Pure rules: `include/sost/v17_economics.h`. Coinbase rules:
`src/tx_validation.cpp` (`ValidateCoinbaseV17`). Block jackpot rule:
`include/sost/jackpot_block.h` (`validate_block_jackpot_v17`). Node wiring:
`src/sost-node.cpp` (`compute_v17_jackpot_plan`, `validate_live_jackpot`,
`process_block`, `load_chain`). Tests: `tests/test_v17_economics.cpp` (ctest
`v17-economics`) and `tests/run_v17_devnet_e2e.sh`.

Units: integer stocks only (1 SOST = 100,000,000 stocks). No floating point
anywhere in monetary consensus.

---

## 1. Activation

| Network | `V17_HEIGHT` (`include/sost/params.h`) |
|---|---|
| mainnet | **40,000** |
| testnet | `INT64_MAX` (set by the testnet soak release) |
| devnet (`SOST_DEVNET_FORKS`) | 60 (a jackpot height; Jackpot V2 is active from 42) |

`v17_active_at(h) := V17_HEIGHT != INT64_MAX && h >= V17_HEIGHT`.
Every block with `h < V17_HEIGHT` validates exactly as before (50 % miner /
50 % DTD of `subsidy + fees` from V15, Historical Jackpot funded only by the
frozen reserve). `V17_HEIGHT > HIST_JACKPOT_V2_HEIGHT` and `> V15_HEIGHT` are
compile-time asserted, so every V17 jackpot is a Jackpot V2 jackpot and every
V17 block is a DTD draw block.

Mainnet boundary: #39,998 and #39,999 use the old rules, #40,000 and #40,001
the V17 rules. The last pre-V17 jackpot is #39,978; the first V17 jackpot is
#40,266 (25,290 + 52 × 288). #40,000 is not a jackpot height.

## 2. Canonical split of the block subsidy (rounding rule)

For a V17 block with subsidy `S = sost_subsidy_stocks(h)` (schedule unchanged)
and transaction fees `F`:

```
dtd_subsidy   = S * 15 / 100        (integer division, rounds down)
jackpot_j     = S *  5 / 100        (integer division, rounds down)
miner_subsidy = S - dtd_subsidy - jackpot_j
miner_total   = miner_subsidy + F   (fees: 100 % to the block miner, never split)
```

* `miner_subsidy + dtd_subsidy + jackpot_j == S` exactly, for every `S >= 0`.
* The miner absorbs both remainders: `0.80·S <= miner_subsidy < 0.80·S + 2 stocks`.
* The products are formed in `__int128`; the rule is overflow-free for every
  int64 `S >= 0` (tested up to `INT64_MAX`). A negative `S` is invalid.
* Initial reward `R0 = 785,100,863` → miner 628,080,691 · DTD 117,765,129 · J 39,255,043.
* Small values: S = 6 → (6, 0, 0); S = 7 → (6, 1, 0); S = 20 → (16, 3, 1);
  S = 99 → (81, 14, 4); S = 100 → (80, 15, 5).
* Same total emission: no subsidy increase, no fee burn, no native burn.
  `OUT_BURN 0x20` stays RESERVED/INACTIVE.

## 3. V17 coinbase

Outputs, in this order, nothing else (recognized trailing governance markers,
inactive on mainnet, are unchanged):

| # | type | amount | pkh | present when |
|---|---|---|---|---|
| 0 | `OUT_COINBASE_MINER` 0x01 | `miner_total` | miner | always |
| 1 | `OUT_COINBASE_LOTTERY` 0x04 | `dtd_subsidy + pending_before` | DTD winner | DTD paid out |
| next | `OUT_COINBASE_JACKPOT` 0x05 | `j_part` (§5) | Jackpot V2 winner | `j_part > 0` |

* No Gold Vault / PoPC outputs (unchanged since V15).
* DTD paid out ⇔ the eligibility set is non-empty **and**
  `dtd_subsidy + pending_before > 0` (`v17::dtd_paid_out`). When it is not
  paid out, `pending_after = pending_before + dtd_subsidy` (rollover, as
  before); when paid, `pending_after = 0`. The positive-amount condition only
  matters for `S <= 6` stocks at the very end of the schedule and prevents a
  zero-value output.
* Every output: empty payload, `0 < amount <= SUPPLY_MAX_STOCKS`.
* Normal DTD eligibility, cooldown + retry, anti-dominance, recency window and
  SbPoW identity are the **unchanged** helpers (`compute_lottery_eligibility_set`).
  No eligibility code was modified or refactored.
* **Winner seed (DTD-F1, V17):** from `V17_HEIGHT` the normal DTD seed is
  `sha256("SOST_DTD_V17" ‖ commit[h-16..h-1] ‖ u64le(h))` and the Jackpot V2 seed is
  `sha256("SOST_HIST_JACKPOT_V17" ‖ commit[h-16..h-1] ‖ u64le(h))`, where `commit` is
  the PoW commit, not the `block_id` (which covers the re-signable SbPoW signature).
  Selection (`roll % E`, weighted roll) is unchanged; below `V17_HEIGHT` the
  historical `block_id` seeds apply byte-for-byte. Normative spec:
  `docs/v40000/DTD_F1_SEED_POW_COMMIT.md`.
* Exact per-block invariant (CB14, `__int128`):
  `sum(outputs) + (pending_after − pending_before) + (J_after − J_before) == S + F`.

Validator error codes: CB4 (order/type), CB11 (output count), CB12 (miner or
DTD amount), CB13 (DTD winner), CB14 (pending / invariant), **CB15 (new:
`OUT_COINBASE_JACKPOT` amount/pkh or J accounting)**. A V17 coinbase validated
without the chain context is rejected.

## 4. J_BALANCE (consensus accumulator, E1)

* Integer consensus state, stocks. No address, no UTXO, no key, no custodian.
* `J = 0` for every block below `V17_HEIGHT`.
* Transition for a V17 block (`v17::j_transition`):

  ```
  J_after = J_before − j_paid + jackpot_j(S)
  0 <= j_paid <= J_before
  ```

  `J_before` is the balance after the parent block. A payment in block *h*
  can only use `J_before` (pre-block state, like H); the 5 % of block *h*
  itself is added after the payment.
* `j_paid` is the amount of the coinbase `OUT_COINBASE_JACKPOT` output (0 if none).
* Storage: `StoredBlock::j_balance_after`, one value per block; this per-block
  record is the undo data. Disconnecting blocks (reorg, failed-reorg rollback)
  truncates the active chain, so the parent's value becomes the live J again;
  the reorg restore path pushes back the saved blocks with their values.
* Persistence: `chain.json` carries `"v17_j_balance_after"` for every V17 block.
  On load / reindex J is **recomputed** from the block data (subsidy schedule +
  coinbase) and checked with `j_transition`; an invalid transition stops the
  load at that block (`chain_load_fail`), a persisted value that disagrees is
  reported and the recomputed value is used (the raw block JSON is not
  committed by the block id, so it is never an authority).
* A block at or above `V17_HEIGHT` is never accepted header-only (assumevalid
  fast path), because J is derived from its coinbase.
* RPC exposes J separately from H (§7). H and J are never merged.

## 5. Historical Jackpot funding: H first, then J (E2, E3)

Unchanged: cadence 288 (`is_hist_jackpot_height`), base 100 SOST, cap 500 SOST,
rollover rule (`derive_rollover_before`), Jackpot V2 winner (NODE_BIND +
heartbeats, linear PoW weight, `compute_v2_jackpot_winner`). Only the funding
changes.

Inputs, all pre-block: `H` = sum of the frozen reserve UTXOs
(`discover_reserve_utxos`), `J = J_before`, `R` = rollover, winner.

```
prize = min(BASE + R, CAP)
no winner              : pay 0;  R' = min(R + BASE, CAP − BASE)
winner and H + J == 0  : pay 0 (UNFUNDED); no tx, no output; counted as unpaid,
                         so R' = min(R + BASE, CAP − BASE)
winner and H + J  > 0  : payout = min(prize, H + J)
                         h_part = min(payout, H)
                         j_part = payout − h_part
                         R' = 0
```

* Example (owner): prize 100, H 30, J 500 → 30 from H + 70 from J → H 0, J 430.
* H covers the prize → J is not touched, even if J > 0.
* UNDERFUNDED (`0 < H + J < prize`): everything available is paid (H then J),
  rollover resets — the pre-V17 reserve-limited rule, without the pre-V17
  "retired" latch, because J keeps refilling.
* IMPOSSIBLE states (`H < 0`, `J < 0`, `H` or `J` above `SUPPLY_MAX_STOCKS`,
  `R` outside `[0, CAP − BASE]`, `j_paid > J_before`, overflow): the block is
  rejected (`JackpotFunding.ok == false` → `process_block` rejects; load
  stops). They cannot arise from valid history.
* H stays reserved for jackpot payments only (frozen reserve rule unchanged).

### 5.1 Materialization of the payment

* **H part** — the canonical `TX_TYPE_JACKPOT` at block index 1, built by the
  unchanged builder (`build_jackpot_tx_for_payout(h_part, ...)`: oldest-first
  reserve inputs, keyless, output 0 `OUT_TRANSFER h_part` to the winner,
  change back to the Gold Vault sink as `OUT_COINBASE_GOLD`). Value-conserving
  (inputs == outputs). Present iff `h_part > 0`.
* **J part** — one coinbase output `OUT_COINBASE_JACKPOT` (0x05) of exactly
  `j_part` to the same winner. Present iff `j_part > 0`. It creates new outputs
  from J; this is supply-neutral overall because the same stocks were withheld
  from earlier coinbases into J.

Why the coinbase and not the jackpot tx: a J-only payment has no reserve
input, and a zero-input `TX_TYPE_JACKPOT` paying the same winner the same
amount at two cadences would have the same txid. The coinbase is unique per
height (CB3 encodes the height in its input), keeps all value creation in one
place, and its outputs follow `COINBASE_MATURITY` like every other newly
emitted output (1,000 blocks on mainnet; the H part stays immediately
spendable, as before).

### 5.2 Block rule (validate_block_jackpot_v17, every V17 height)

* `h_part > 0` → exactly one `TX_TYPE_JACKPOT`, at index 1, field-exact to the
  reconstruction; `h_part == 0` → none.
* `j_part > 0` → exactly one `OUT_COINBASE_JACKPOT` in the coinbase with
  amount `j_part`, the winner's pkh and an empty payload; `j_part == 0` → none.
* No transaction other than the coinbase may carry `OUT_COINBASE_JACKPOT`
  (R11 already rejects it in standard transactions at every height).
* Runs on every connect path: `process_block` (including reorg connects),
  failed-reorg restore and `load_chain` / reindex.

### 5.3 Rollover derivation

A jackpot event at height *h* counts as paid iff its block has the
`TX_TYPE_JACKPOT` at index 1, or (from V17) its coinbase has an
`OUT_COINBASE_JACKPOT` output (`v17::jackpot_event_paid`,
`jackpot_event_paid_at`). Below V17 no coinbase can contain that output type
(coinbase shape rules; 0 occurrences in 30,428 mainnet coinbases), so the
predicate is identical to the historical one on every existing block.

## 6. Supply conservation

For every tip *T* (before and after V17):

```
sum(unspent outputs at T) + pending_lottery(T) + J_BALANCE(T)
    == sum_{h <= T} subsidy(h)
```

(fees net to zero; jackpot H spends are value-conserving; J outputs re-emit
exactly what J withheld). Per V17 block the CB14 invariant of §3 holds
exactly. Native SOST is never burned.

## 7. Interfaces

| Surface | V17 change |
|---|---|
| `getblocktemplate` | from V17: `v17_active`, `miner_subsidy`, `miner_total`, `dtd_subsidy`, `jackpot_j_alloc`, `j_balance_before/after`, `jackpot_height`, `jackpot_h_payout`, `jackpot_j_payout`, `jackpot_winner_pkh`; the jackpot tx (H part) is in `transactions[0]` when due |
| `getlotterystate` | from V17: amounts use the 15 % DTD share; adds `v17_active`, `miner_subsidy`, `dtd_subsidy`, `jackpot_j_alloc`, `j_balance_before` |
| `getblock` | V17 blocks: `v17_reward` {subsidy, fees, miner_subsidy, miner_total, dtd_subsidy, dtd_paid, jackpot_j_alloc, jackpot_h_paid, jackpot_j_paid, winners, j_balance_before/after, pending_lottery_after} |
| `getjackpotstate` (new, read-only, public) | H (`h_reserve_stocks`) and J (`j_balance_stocks`) separately, next jackpot, rollover, prize, H/J funding preview; with a height: J before/after and the H/J paid by that block |
| `gethistoricaljackpotstatus` | `expected_payout` includes projected J when the next jackpot is a V17 jackpot; adds H/J parts (fields only then) |
| `getsupplyinfo` | DTD distributed uses 15 % from V17; adds `jackpot_j_balance(_stocks)`; J is not counted as circulating |
| `sost-miner` | builds the V17 coinbase (80 % + fees, DTD 15 % + pending, J output from the template); refuses to mine a V17 block without a current V17 template |
| `sost-cli` | `getjackpotstate [height]`; `signtx` accepts 0x05 inputs; listunspent labels |
| wallet | `OUT_COINBASE_JACKPOT` is subject to coinbase maturity |
| explorer (`website/sost-explorer.html`, not deployed) | V17 split row in block detail; jackpot card shows H and J separately |

Pre-V17 outputs of every existing RPC are unchanged byte for byte (V17 fields
appear only once the relevant height is a V17 height).

## 8. Known limits (not introduced by V17)

* A block with `subsidy == 0` and `fees == 0` (after the supply cap, about
  two centuries away) would need a zero-value miner output, which R5 rejects.
  This is the pre-existing behaviour before and after V17.
* J-funded payouts mature after `COINBASE_MATURITY`; H-funded payouts do not
  (unchanged jackpot tx).

# Wallet coin selection — Phase 1 audit + Phase 2 design

Branch `feat/wallet-coin-selection` (separate). Wallet-only; NO consensus/emission/maturity/key
changes. Implementation + tests + benchmarks DEFERRED until the clean sync measurement completes
(so they don't contaminate it).

## Regression case (TX b4fdb5f7…545aa9, block 27951)
Pay 300 SOST, 77 inputs of ~3.9255 each (302.264 in), change 2.263, fee 0.00103510 (~11474 bytes,
~9 stock/byte), 29-byte capsule. Accounting is exact and it confirmed.

## Current selector (src/wallet.cpp) — the finding
- Comment: *"Select UTXOs (simple: oldest first) — maturity-aware"*. Algorithm = **naive greedy
  accumulate in list_unspent order** until `total_in >= amount + fee`, then break. **No** Branch-and-
  Bound, **no** effective-value, **no** knapsack, **no** waste metric, **no** largest/best-fit.
- **Verdict on the 77 inputs: NOT a bug.** With a pure-mining wallet whose UTXOs are all ~3.9255,
  reaching 300 needs ⌈300/3.9255⌉ = **77 inputs under ANY algorithm** — there are no larger UTXOs to
  pick. Inefficiency only bites when the wallet holds a MIX of sizes (then greedy-oldest can pick many
  small when a few large would do).
- Already-correct rules (keep): maturity-aware (immature coinbase excluded, 1000-conf), constitutional
  UTXOs (Gold Vault/PoPC) never spent, `--from` source pin.
- Fee unit = **stocks per physical byte** (default 10; consensus S8 min 1; flat floor 100 stocks),
  two-pass build→measure→fee=bytes×rate. (No segwit weight/vB — do NOT copy sat/vB verbatim.)
- **Code smell:** ≥4 near-duplicate selection loops in wallet.cpp (transfer/capsule/…) — must be
  unified into one selector so a fix applies everywhere.

## Phase 2 design (Bitcoin-Core-inspired, adapted; not a copy)
1. **Unify** into one `select_coins(unspent, target, fee_rate, capsule_bytes, chain_height)` used by
   all builders (CLI, and the web wallet mirrors the same logic).
2. **Effective value** per UTXO = `amount − input_spend_cost(fee_rate)`; drop UTXOs whose effective
   value ≤ 0 (uneconomic to spend at the current rate) unless needed to reach target.
3. **Branch-and-Bound** for an exact, changeless match within a cost window (target + change-cost
   tolerance); deterministic, bounded iterations.
4. **Fallback** knapsack/accumulative (largest-effective-value-first, then random draws) when BnB
   finds nothing.
5. **Waste metric** to pick the economically-best candidate (input cost now + expected future change
   spend cost + excess), NOT simply the fewest inputs.
6. Exact fee from the FINAL signed size incl. capsule bytes; prevent dust/uneconomic change; never
   underpay (S8). No arbitrary input cap that blocks legitimate spends.
7. Keep maturity/constitutional/pin rules; preserve PSBT/multisig compatibility; respect in-flight
   UTXO locks (the web wallet already tracks `inFlightUtxos`).

## Phase 4 — optional CONSOLIDATION (design)
Explicit, simulate-first, never automatic: show input count / outputs / total fee / final size; mature
UTXOs only; evaluate whether it pays; privacy warning; require explicit authorization to build/sign.

## Deferred (until after the sync measurement)
Implementation of the unified BnB selector, the Phase-5 test matrix (A–L incl. the 77-input case), and
the ANTES/DESPUÉS benchmarks (time/memory/#inputs/tx-size/fee/change). No real keys, no production tx.

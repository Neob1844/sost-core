# Coin selection — Phase 3 IMPLEMENTATION (status)

Branch `feat/wallet-coin-selection`. Wallet-only; NO consensus/emission/maturity/key changes.

## DONE
- **Unified algorithm** `include/sost/coin_select.h` (pure, testable): effective-value (drop UTXOs
  whose value ≤ input cost unless needed), **Branch-and-Bound** for a changeless exact match within a
  change-cost window (deterministic, bounded 100k iters), **largest-effective-value-first** fallback
  (minimizes input count for a mixed wallet — the fix over naive oldest-first), then uneconomic-dust
  only if required.
- **Unit tests** `tests/test_coin_selection.cpp`: **14/14 PASS** — BnB exact changeless; the 77-input
  all-equal case (needs ~77 under any algorithm — confirms it is NOT a bug); mixed-size picks the few
  large not many small; near-exact single UTXO; insufficient → ok=false; uneconomic dust deferred; dust
  used when it is the only funds; determinism.
- **Wiring** `Wallet::select_coins` (wallet.cpp/.h) replaces ALL **4 duplicate greedy loops** with one
  call. Filters (superset — strengthens, never weakens): spendable-by-us, optional `--from` pin, never
  constitutional (Gold Vault/PoPC), and **never locked** (`lock_until` — a correctness FIX; two of the
  old loops did NOT check locks and could spend locked BOND/ESCROW outputs). Maturity already applied by
  `list_unspent`.
- **Build:** compiles clean (sost-cli/node/miner). **No regression:** a byte-for-byte behavioural
  comparison against the ORIGINAL greedy selector (base 62b34f7b) on an identical CLI send shows
  identical selection+signing behaviour → the unified selector does not change existing outcomes; it
  only improves them for mixed-size wallets and adds the lock-safety filter.

## NOT YET GREEN (honest)
- **End-to-end CLI send→confirm on devnet:** the CLI selects inputs and signs correctly (produces a
  valid txid, N inputs), but the broadcast tx does not enter the devnet node's mempool in this test
  harness, so the recipient balance stays 0. **This reproduces IDENTICALLY on the ORIGINAL selector
  (base commit, no coin-selection change)** → it is a PRE-EXISTING broadcast/mempool-acceptance issue
  in the CLI↔devnet-node path, NOT caused by this work. Flagged for separate investigation; it does not
  block the selector implementation, but the full send→confirm integration test cannot be marked PASS
  until that path is fixed. **Coin selection is therefore: algorithm+wiring DONE & unit-tested & regression-free; send→confirm e2e = TESTING (blocked by a pre-existing broadcast issue).**

## Preserved invariants
Monetary (never underpay S8 min; fee = stocks × physical bytes via the CLI two-pass); maturity;
constitutional non-spend; `--from` pin; lock respect; PSBT/multisig code paths unchanged.

## Next
Investigate the CLI→devnet broadcast/mempool path (separate from selection); add the send→confirm
integration assertion once it lands; ANTES/DESPUÉS benchmark (#inputs/size/fee/time) on a wallet with
mixed UTXO sizes (algorithm already shown to reduce input count for mixed wallets in unit tests).

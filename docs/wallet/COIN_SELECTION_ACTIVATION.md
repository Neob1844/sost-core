# Wallet coin selection — terminology, consensus impact & POST-FORK activation

## What it is (precise terminology)
**Bitcoin-Core-inspired coin selection** — NOT identical to modern Bitcoin Core. It implements the main
efficient ideas:
- **Branch-and-Bound (BnB)** search for a changeless (no change output) match within a change-cost window;
- **effective value** (amount − per-input fee) with **uneconomic-UTXO filtering** (dust deferred);
- **changeless preference**;
- a **deterministic largest-effective-value-first fallback** (minimises input count).

Simplified vs modern Bitcoin Core (documented on purpose): the fallback is deterministic largest-first, **not
SRD (Single Random Draw)**; there is **no full waste-metric scoring** across candidate solutions and **no
privacy randomisation**. Header: `include/sost/coin_select.h`. A separate BTC-side funding selector lives in
`include/sost/btc_funding.h` (atomic-swap HTLC funding).

## Consensus impact
- CONSENSUS IMPACT = **NO** · V16 IMPACT = **NO** · STRATO IMPACT = **NO** · #30000 IMPACT = **NO**.
- This is wallet/CLI code only. It never runs in the node's block/transaction validation; it only chooses
  which of the caller's own UTXOs to spend when building a transaction. Consensus does not observe or check
  coin selection.

## Status
**CODE COMPLETE / MERGED to main (source).** RUNTIME ACTIVATION = **POST-FORK** (requires rebuilding the
wallet/CLI binary, which is frozen until after #30000). Algorithm unit tests **20/20** pass standalone on the
merged code; the fail-closed lock regression (5/5) links against `wallet.cpp` and re-runs in the post-fork build.

## POST-FORK activation plan (do NOT run before #30000)
1. After the fork has activated and the chain is stable, on a build host (NOT by touching the live node):
   `cmake --build build --target sost-cli` with the mandatory flags
   (`-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF`).
2. `sha256sum` the new `sost-cli`; record it; back up the current `sost-cli` binary to a dated path.
3. Replace ONLY the wallet/CLI component (`sost-cli`) — the node (`sost-node`) and miner are unaffected.
4. Smoke test: build+sign+broadcast a small send; verify coin selection picks the expected UTXOs; verify a
   locked (BOND/ESCROW) UTXO is never selected at unknown height (fail-closed).
5. Rollback = restore the backed-up `sost-cli`. No consensus/node rollback is involved.

# V15 Option B package manifest (V15 + EVM + BTC code) — BTC OFF by default

**PACKAGED, NOT ACTIVATED, NOT DEPLOYED.** Option A (BTC OFF) remains the
production build. This package is Option B for a future, separate BTC activation
after real bitcoind-regtest validation.

## Identity
- **Branch:** `reconcile/btc-option-b` (= `feat/btc-atomic-swap-complete` onto
  unchanged `origin/main`; merge-base == origin/main, so a trivial fast-forward).
- **HEAD:** `6560836d`
- **Reconciled onto origin/main:** `60d24d60`
- **CONSENSUS DIFF vs main:** NONE (params.h / sost-node.cpp / lottery / popc /
  tx_validation / block / emission / subsidy all untouched).
- **Compiler:** g++ 11.4.0
- **Build flags:** `-DSOST_BTC_HTLC_SIGNING=ON -DSOST_ENABLE_PHASE2_SBPOW=ON
  -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=RelWithDebInfo`

## Binaries (SHA256 — see SHA256SUMS.txt)
| File | SHA256 |
|------|--------|
| sost-node   | `1379fa652df8a9710276e9030d54c19f7c891485043ca39cfd0d554c76077993` |
| sost-cli    | `b50db08e78eb764437bbebe7afc5ca84b4c593519e28caee855292c171aa273e` |
| sost-miner  | `47ab3064211cd9056b8c4b3e056b543bdc2fae292550eac97083769136d891b1` |
| sost-signtx | `84f4d94b645f8b4bcae6d515ff4c5bc9af5c2a2c100180af2890af58c687fe6d` |

## Consensus / gate facts (verified in the binary)
- V15 = 25000, first jackpot = 25290, EVM HTLC = 16000, relay = 17000 (unchanged).
- SbPoW consensus path present (`POW-SIG/v11` ×4).
- **BTC runtime default OFF.** `SOST_BTC_ATOMIC_SWAP_ENABLED` unset ⇒ Null backend,
  fail-closed; `IsBtcHtlcSigningEnabled()` false.
- **The Option B `sost-node` binary has 0 `wally_` symbols** — the BTC signing
  code is dead-stripped from the node because the node has NO BTC callers (BTC
  signing/broadcast lives in the wallet/CLI/tooling layer). So the node is
  BTC-inert and consensus-identical to Option A; BTC never fires from the node.

## What still gates activation
Real `bitcoind`-regtest end-to-end validation (fund→lock→confirm→claim-with-
preimage; timeout→refund; adversarial). NOT run here (owner-waived). Until it
passes, `OPTION B: PACKAGED — NOT READY` for real funds. See
`docs/v15/BTC_ATOMIC_SWAP_RUNBOOK.md`.

## Option A is untouched
The deployed Option A (V15 + EVM, BTC OFF) is unchanged and always rebuildable
from `main` with `-DSOST_BTC_HTLC_SIGNING=OFF` (0 libwally, no bitcoind
dependency). Its manifest: `artifacts/v15-final-validation/SHA256SUMS_FINAL.txt`
(node `f7c625fd…`). This package does NOT replace or delete it.

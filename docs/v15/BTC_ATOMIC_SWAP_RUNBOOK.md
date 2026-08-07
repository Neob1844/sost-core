# BTC Atomic Swap — operator runbook (Option B)

How to configure, validate and (eventually) enable the BTC leg. **Nothing here
runs in the deployed Option A build.** BTC stays OFF until you deliberately flip
both gates AND complete the regtest validation.

## Requirements
- A reachable `bitcoind` (or compatible) JSON-RPC endpoint. `txindex=1` is
  required for `getrawtransaction` on arbitrary txids.
- A build compiled with `-DSOST_BTC_HTLC_SIGNING=ON` (vendors + links
  libwally-core). The default release is `OFF` (Option A).

## Configuration (environment only — never hardcode secrets)
| Variable | Meaning | Default |
|----------|---------|---------|
| `SOST_BTC_ATOMIC_SWAP_ENABLED` | runtime gate; `1` to enable | OFF |
| `BTC_RPC_HOST` | bitcoind RPC host | — |
| `BTC_RPC_PORT` | bitcoind RPC port (8332 mainnet / 18443 regtest) | — |
| `BTC_RPC_USER` | RPC user | — |
| `BTC_RPC_PASSWORD` | RPC password | — |
| `BTC_NETWORK` | `mainnet`\|`testnet`\|`regtest` | `mainnet` |
| `BTC_CONFIRMATIONS` | confs to treat a tx final | `1` |

Secrets live in the environment (or a 0600 env-file) — never in Git, never in
docs, never logged. The factory `MakeBitcoinBackendFromEnv()` returns a live
backend ONLY when the gate is `1` AND all four `BTC_RPC_*` are present; otherwise
a `NullBitcoinBackend`.

## Health
- `BitcoinBackend::IsConfigured()` — false ⇒ BTC disabled/unavailable (the UI
  shows "Coming soon" / disabled and refuses to create BTC swaps).
- `GetBlockHeight()` — a cheap liveness probe. If it fails, treat BTC as down.

## Lifecycle (happy path)
```
CREATE   → derive HTLC redeem-script + P2WSH address (BuildBtcHtlcRedeemScript / EncodeP2WSHAddress)
FUND     → SelectBtcFundingUtxos / PlanBtcHtlcFunding → SignBtcHtlcLockFunding → backend.BroadcastRawTransaction
CONFIRM  → poll backend.GetTransactionStatus(funding_txid) until confirmations >= BTC_CONFIRMATIONS
CLAIM    → (claimant, preimage known, before refund_height) SignBtcHtlcClaim → Broadcast
           (funder learns the preimage from the claim witness: ExtractBtcHtlcPreimageFromTxHex)
```
Timeout path:
```
REFUND   → (funder, current_height >= refund_height, still unspent) SignBtcHtlcRefund → Broadcast
```
Every state change is recorded in the `BtcSwapStore` (0600). The watcher decides
the next action via `DecideBtcWatchAction` (reorg-aware).

## Recovery (restart)
On startup: `BtcSwapStore::Load()` → for each non-terminal record
`ReconcileBtcSwapWithChain(record, backend)`. This queries the recorded
funding/claim/refund txids and advances the state to on-chain reality with
idempotent transitions — so recovery **never re-broadcasts** a tx already sent
(no double-spend). Only after reconciliation does the watcher act.

## Timeout safety (BTC ↔ EVM/SOST)
The responder/BTC refund timeout MUST open LATER than the counterparty's claim
window closes, with a safety margin — enforced by `EvaluateTimeoutOrder`
(`atomic_swap_policy.cpp`, responder T2 < initiator T1 + margin). Set
`refund_height` conservatively and account for `BTC_CONFIRMATIONS` in the margin.

## VALIDATION before enabling (mandatory, not yet run here)
Run the real `bitcoind`-regtest round-trip and confirm on a live node:
1. fund → lock → confirm → **claim with preimage** spends the HTLC;
2. **timeout → refund** spends it after `refund_height`;
3. adversarial: wrong preimage rejected, claim after refund rejected, refund
   before timeout rejected.
This validates byte-order / sighash / witness against a real network — the step
the owner waived in this pass. `scripts/otc_rehearsal_btc_regtest.sh` and
`docs/V15_OTC_BTC_REGTEST_GUIDE.md` are the starting points; wiring it into ctest
is the remaining task before any activation.

## Enable / Disable / Rollback
- **Enable:** only after the regtest validation passes — set the six env vars +
  `SOST_BTC_ATOMIC_SWAP_ENABLED=1` on the wallet/OTC tooling host (NOT the
  consensus node), flip `BTC_ENABLED` in the dashboard plumbing.
- **Disable / rollback:** unset `SOST_BTC_ATOMIC_SWAP_ENABLED` (→ Null backend,
  fail-closed) and set `BTC_ENABLED=false`. No consensus change, no node
  restart required; the SOST/V15 chain is entirely independent of BTC.

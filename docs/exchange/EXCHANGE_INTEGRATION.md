# SOST Exchange Integration Kit

For exchanges / custodians integrating SOST deposits and withdrawals. SOST is a UTXO PoW L1;
the RPC is JSON-RPC 2.0 over HTTP with HTTP Basic auth. All amounts are in SOST unless a method
documents base units ("stockshis", 1 SOST = 1e8 stockshis).

> Every RPC method named below is verified present in the node's dispatch table
> (`src/sost-node.cpp`). Endpoints: `--rpc-port` (default here 18332), auth `--rpc-user` +
> `--rpc-pass-file`. Use the read-only broadcast gateway for `sendrawtransaction` if you do not
> want to expose admin RPC (see the public-RPC proxy note at the end).

## 1. Connectivity & health
| Method | Use |
|---|---|
| `getinfo` | version, height, connections — liveness probe |
| `getblockcount` | current tip height |
| `getbestblockhash` | tip hash (pair with getblockcount for reorg detection) |
| `getblockchaininfo`/`getsupplyinfo` | chain + supply state |
| `getpeerinfo` | connected peers (alerting) |
| `getmempoolinfo`, `getrawmempool` | mempool depth |

Poll `getblockcount` + `getbestblockhash` together every few seconds; a height that stalls or a
best-hash that changes without height increasing is your reorg signal (§5).

## 2. Deposit detection
Two supported models — pick one:

**A. Address-indexed (simplest).** The node maintains address indexes:
- `getaddressinfo <addr>` — balance + summary.
- `getaddressutxos <addr>` — current UTXOs (txid, vout, amount, height, type).
- `getaddressbalance <addr>` — confirmed balance.
- `getaddressflows <addr>` — inbound/outbound history for reconciliation.

Assign each customer a unique deposit address via `getnewaddress`. On each new block, for every
watched address diff its UTXO set; a new UTXO at height H is a candidate deposit.

**B. Block-scan.** Walk blocks `getblockhash H` → `getblock <hash>`; for each tx
(`getrawtransaction`/`gettransaction`) inspect outputs and match against your address set.
Heavier but does not depend on the address index.

### Output types you MUST honor (from the tx `type` field)
- `0x00 TRANSFER` — a normal spendable deposit. **Credit only these** (plus, if you choose to
  accept them, matured coinbase `0x01`).
- `0x01–0x04 COINBASE_*` — mined outputs. **Immature until `COINBASE_MATURITY = 1000`
  confirmations** (mainnet, `include/sost/consensus_constants.h`). Never credit before maturity.
- `0x10 BOND_LOCK`, `0x11 ESCROW_LOCK` — locked; not spendable, do not credit.
- `0x12 HTLC_LOCK`, `0x13 HTLC_CLAIM_WITNESS` — atomic-swap outputs; do not treat as ordinary
  deposits.
- `0x20 BURN` — provably destroyed.
- A `TRANSFER` output may carry a **Capsule payload** (e.g. an `doc_ref` Asset-Passport anchor).
  It is still an ordinary payment for balance purposes; ignore the payload for crediting.

## 3. Confirmations & finality policy
- Use `gettxout <txid> <vout>` — it returns only **unspent** outputs and includes
  `confirmations`; a `null` result means spent or never existed.
- Recommended crediting thresholds (PoW, tune to your risk):
  - small deposits: **30** confirmations
  - large deposits: **100+** confirmations
  - coinbase: **1000** (maturity) — non-negotiable, it is a consensus rule.
- Never credit a 0-conf (mempool) deposit as final.

## 4. Withdrawals
1. Select UTXOs and build a transaction. If you run the node's wallet, `listunspent` +
   `getnewaddress` (change) are available; otherwise build/sign externally.
2. `validateaddress <addr>` before sending to any customer-supplied address.
3. `estimatefee` for the fee rate; fees are always paid in SOST.
4. Broadcast with `sendrawtransaction <hextx>`. **A returned txid is NOT acceptance** — the CLI/
   RPC distinguishes accept vs reject; confirm the tx is in `getrawmempool` on the SAME node,
   then wait for confirmations. (This exact "bare txid ≠ accepted" gotcha has bitten us; verify.)
5. Track the withdrawal txid to N confirmations like a deposit.

## 5. Reorg handling (mandatory)
UTXO PoW chains reorg. Protect credited balances:
- Store, for every credited deposit, the **block hash** (not just height) it confirmed in.
- Each poll, for the range you still consider "not final", re-fetch `getblockhash H` and compare
  to the stored hash. If it differs, that height was reorged: **roll back** every deposit whose
  confirming block is no longer on the main chain, then re-scan the new blocks.
- Only treat a deposit as irreversible once it is buried beyond your confirmation threshold AND
  the confirming block still matches on `getblockhash`.
- Alert if `getbestblockhash` changes while `getblockcount` does not advance (a same-height tip
  swap) or if the tip moves backwards.

## 6. Fee estimation
`estimatefee` returns a per-byte/relative rate; multiply by your signed tx size for the absolute
fee. The node applies a two-pass absolute fee internally for its own wallet sends, so if you use
the node wallet you generally do not need to pre-compute — but for externally-built txs, size ×
rate is the estimate. Dust threshold applies (sub-dust change is absorbed into the fee).

## 7. Security
- Keep admin RPC bound to localhost. To accept only broadcasts from the outside, front the node
  with the **public RPC proxy** (`sost-rpc-proxy`): it injects node auth for `sendrawtransaction`
  only and blocks admin methods with 401. Wallets broadcast to `/rpc/public`.
- RPC password lives in a mode-600 file (`--rpc-pass-file`), never in argv.
- Node key via `--node-key-file`, never argv.

## 8. Files in this kit
- `deploy/install/install-sost-node.sh` — production install/upgrade/rollback (systemd, hardened).
- `deploy/install/sost-node.service` — hardened unit (runs as `sost`, secrets from mode-600 files).
- `deploy/install/generate-sbom.sh` — SHA256SUMS + SBOM for a release bundle.
- `deploy/install/exchange-integration-example.py` — reference deposit poller with reorg handling.
- `deploy/install/test-harness.sh` — smoke test of the RPC surface an exchange depends on.

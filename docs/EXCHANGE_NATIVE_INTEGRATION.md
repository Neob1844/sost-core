# SOST — Native Exchange Integration

Compact integration guide for exchanges, custodians and wallet providers. SOST is a
**native Layer 1 UTXO Proof-of-Work blockchain** (its own chain — not an ERC-20 or a
token on another network). It integrates like a standard Bitcoin-style UTXO coin over
JSON-RPC.

## License & integration rights

SOST Core and ConvergenceX are released under the **MIT License**. You may build, run,
integrate and operate the node, wallet and RPC **without any license fee, security
deposit, permission requirement or commercial license**. Trademark rights are reserved
separately. There is **no memo/tag, no destination tag, and no on-chain license check** —
deposits/withdrawals are plain address-based UTXO transfers.

## Network facts

| | |
|---|---|
| Ticker | SOST |
| Type | Native Layer 1 UTXO Proof-of-Work blockchain |
| Block time | ~10 minutes (600 s target) |
| Address format | `sost1` + hex-encoded public-key hash (e.g. `sost1146b626fc1a0678c90fa8f833162b97f7d525f99`) |
| Smallest unit | "stocks" (integer base unit; amounts in RPC are integer stocks) |
| RPC port | `18232` (JSON-RPC over HTTP, HTTP Basic Auth) |
| P2P port | `19333` |
| Seed node | `seed.sostcore.com:19333` |
| Confirmations | PoW probabilistic finality — **recommended 10 confirmations** for credited deposits |
| Memo / tag | **Not used** — address only |

## Build

```bash
git clone https://github.com/Neob1844/sost-core
cd sost-core
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node -j$(nproc)
```

## Run the node

```bash
./build/sost-node \
  --genesis genesis_block.json \
  --chain chain.json \
  --rpc-user <USER> --rpc-pass <PASS> \
  --profile mainnet
```
Optional flags: `--rpc-port <n>` (default 18232), `--port <n>` (P2P, default 19333),
`--connect <host:port>` to add peers.

## RPC

JSON-RPC 2.0 over HTTP on port `18232`, authenticated with **HTTP Basic Auth** using the
`--rpc-user` / `--rpc-pass` credentials.

```bash
curl -s --user <USER>:<PASS> -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"getblockcount","params":[]}' \
  http://127.0.0.1:18232/
```

### Methods for deposits & withdrawals

Chain / blocks:
- `getblockcount` — current height
- `getbestblockhash` — tip hash
- `getblockhash` `[height]` — hash at height
- `getblock` `[hash]` — block with its transaction ids
- `getmempoolinfo` / `getrawmempool` — mempool state

Transactions:
- `getrawtransaction` `[txid]` — raw/decoded transaction
- `gettransaction` `[txid]` — transaction with confirmations
- `gettxout` `[txid, vout]` — unspent-output lookup (existence / amount / confirmations)
- `sendrawtransaction` `[hex]` — broadcast a signed transaction (withdrawals)

Addresses / balances / UTXOs:
- `getnewaddress` — derive a fresh deposit address
- `validateaddress` `[address]` — verify an address before crediting/withdrawing
- `getaddressinfo` `[address]` — address summary
- `getaddressbalance` `[address]` — confirmed balance
- `getaddressutxos` `[address]` / `listunspent` — spendable outputs for building withdrawals

Fees:
- `estimatefee` — suggested fee rate (stocks/byte)

### Deposit flow
1. Generate a per-user deposit address (`getnewaddress`) or derive from your own keys.
2. Poll new blocks (`getblockcount` → `getblockhash` → `getblock`) or scan addresses
   (`getaddressutxos` / `gettxout`).
3. Credit after **10 confirmations** (`gettransaction` reports confirmations).

### Withdrawal flow
1. Select inputs (`listunspent` / `getaddressutxos`), estimate fee (`estimatefee`).
2. Build and sign the transaction with your own keys/library (UTXO model).
3. Broadcast with `sendrawtransaction`; track with `gettransaction` / `gettxout`.

## Explorer & verification

Public block explorer for manual verification of deposits/withdrawals:
- https://sostcore.com/sost-explorer.html

## Support

- Email: **sost@sostcore.com**
- Website / contact form: https://sostcore.com
- Source (MIT): https://github.com/Neob1844/sost-core

---
*SOST is open source under the MIT License — free to integrate and operate, no fee or
deposit. The Gold Vault and PoPC components are transparent on-chain protocol mechanisms;
SOST is not fully gold-backed at issuance and this document makes no representation about
value. Informational only, not investment advice.*

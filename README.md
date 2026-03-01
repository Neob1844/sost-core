# SOST Protocol — Sovereign Gold-Backed Cryptocurrency

**CPU-friendly Proof-of-Work blockchain with constitutional gold reserves.**

Every block mined automatically allocates 25% to purchase physical gold (XAUT/PAXG) and 25% to Proof of Personal Custody rewards — hardcoded at genesis, immutable forever.

- Website: [sostcore.com](https://sostcore.com)
- GitHub: [github.com/Neob1844/sost-core](https://github.com/Neob1844/sost-core)
- Explorer: Open `explorer.html` and connect to your node at `http://localhost:18232`

## Quick Start

```bash
# 1. Create wallet
./sost-cli newwallet

# 2. Import genesis block UTXOs
./sost-cli importgenesis genesis_block.json

# 3. Start node
./sost-node --genesis genesis_block.json --chain chain.json --wallet wallet.json

# 4. Start mining (in another terminal)
./sost-miner --genesis genesis_block.json --chain chain.json --rpc 127.0.0.1:18232 --blocks 10

# 5. Send SOST (in another terminal)
./sost-cli --wallet wallet.json send <destination_address> 10.0 0.001
```

## Binaries

| Binary | Description |
|--------|-------------|
| `sost-node` | Full node — P2P networking, JSON-RPC server, chain validation, mempool |
| `sost-miner` | ConvergenceX PoW miner (CPU-only, requires 4GB RAM) |
| `sost-cli` | Wallet CLI — create keys, send transactions, check balances |

## Node

```
./sost-node [options]
  --genesis <path>       Genesis block JSON (required)
  --chain <path>         Chain state file (load/save)
  --wallet <path>        Wallet file (default: wallet.json)
  --port <n>             P2P port (default: 19333)
  --rpc-port <n>         RPC port (default: 18232)
  --connect <host:port>  Connect to peer node
```

## Miner

```
./sost-miner [options]
  --genesis <path>       Genesis block JSON (required)
  --chain <path>         Chain state file (required)
  --rpc <host:port>      Submit blocks to node via RPC (recommended)
  --blocks <n>           Number of blocks to mine (default: 5)
  --max-nonce <n>        Max nonce per round (default: 500000)
  --profile <p>          Network profile: mainnet|testnet|dev
  --realtime             Use real timestamps (default)
```

The miner can run in two modes:
- **RPC mode** (`--rpc 127.0.0.1:18232`): submits blocks to the node, includes mempool transactions, recommended.
- **Standalone mode** (no `--rpc`): writes directly to `chain.json`, no transaction support.

## Wallet CLI

```
./sost-cli [--wallet <path>] <command> [args...]

  newwallet                    Create new wallet file
  getnewaddress [label]        Generate new receiving address
  listaddresses                List all wallet addresses with balances
  importprivkey <hex>          Import a 32-byte private key (hex)
  importgenesis <path>         Import genesis block coinbase UTXOs
  getbalance [address]         Show balance in SOST
  listunspent [address]        List unspent transaction outputs
  createtx <to> <amt> [fee]   Create and sign a transaction (outputs hex)
  send <to> <amt> [fee]        Create, sign and broadcast to node
  dumpprivkey <address>        Reveal private key (DANGER)
  info                         Wallet summary
```

## RPC API (port 18232)

```bash
curl -s -X POST -d '{"method":"getinfo","id":1}' http://localhost:18232
```

| Method | Params | Description |
|--------|--------|-------------|
| `getinfo` | — | Node status, height, difficulty, balance, mempool |
| `getblockcount` | — | Current chain height |
| `getblockhash` | `height` | Block hash at given height |
| `getblock` | `hash` | Block details including cASERT mode |
| `getaddressinfo` | `address` | Address balance, UTXO count and list |
| `getbalance` | — | Wallet balance |
| `listunspent` | — | Wallet UTXOs |
| `gettxout` | `txid, vout` | Query specific UTXO |
| `validateaddress` | `address` | Check address validity and ownership |
| `getnewaddress` | `[label]` | Generate new wallet address |
| `sendrawtransaction` | `hex` | Submit signed transaction to mempool |
| `getmempoolinfo` | — | Mempool size, bytes, fees |
| `getrawmempool` | — | Pending transaction IDs |
| `getrawtransaction` | `txid [verbose]` | Get raw tx from mempool |
| `getpeerinfo` | — | Connected P2P peers |
| `submitblock` | `block_json` | Submit mined block (used by miner) |
| `getblocktemplate` | — | Get mempool txs for block building |

## Network Parameters

| Parameter | Value |
|-----------|-------|
| Algorithm | ConvergenceX (CPU, 4GB RAM, ASIC-resistant) |
| Block time | 10 minutes target |
| Difficulty | ASERT + cASERT overlay (24h half-life) |
| Block reward | ~7.8510 SOST (Feigenbaum decay) |
| Reward split | 50% miner · 25% Gold Vault · 25% PoPC Pool |
| Coinbase maturity | 100 blocks |
| Address format | `sost1` prefix, 20-byte pubkey hash |
| P2P port | 19333 |
| RPC port | 18232 |
| Signature | ECDSA secp256k1 with LOW-S enforcement |

## Constitutional Addresses

These addresses are hardcoded at genesis and cannot be changed.

| Role | Address | Allocation |
|------|---------|------------|
| **Miner / Founder** | `sost1f559e05f39486582231179a4985366961d8f8313` | 50% of block reward |
| **Gold Vault** | *(see `include/sost/params.h`)* | 25% → automatic XAUT/PAXG purchases |
| **PoPC Pool** | *(see `include/sost/params.h`)* | 25% → Proof of Personal Custody rewards |

## Build from Source

```bash
# Dependencies (Ubuntu 24.04)
sudo apt install build-essential cmake libssl-dev libsecp256k1-dev

# Build
git clone https://github.com/Neob1844/sost-core.git
cd sost-core
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

## Explorer

The block explorer is a standalone HTML file that connects to your node's RPC.

1. Open `explorer.html` in your browser
2. Set the RPC endpoint to `http://localhost:18232`
3. Click **CONNECT**

You can search by block height, block hash, or address.

## License

MIT

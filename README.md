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

# 3. Start node (terminal 1)
./sost-node --genesis genesis_block.json --chain chain.json --wallet wallet.json \
    --rpc-user=myuser --rpc-pass=mypass

# 4. Start mining (terminal 2)
./sost-miner --genesis genesis_block.json --chain chain.json \
    --rpc 127.0.0.1:18232 --rpc-user=myuser --rpc-pass=mypass --blocks 100

# 5. Send SOST (terminal 3 — requires 100+ confirmations on coinbase UTXOs)
./sost-cli --wallet wallet.json --rpc-user=myuser --rpc-pass=mypass \
    send <destination_address> 10.0

# 6. Mine 1 block to confirm the transaction
./sost-miner --genesis genesis_block.json --chain chain.json \
    --rpc 127.0.0.1:18232 --rpc-user=myuser --rpc-pass=mypass --blocks 1
```

## Binaries

| Binary | Version | Description |
|--------|---------|-------------|
| `sost-node` | v0.3.1 | Full node — P2P networking, JSON-RPC (17 methods), chain validation, mempool |
| `sost-miner` | v0.4 | ConvergenceX PoW miner with mempool integration via RPC |
| `sost-cli` | v1.3 | Wallet CLI — create keys, send transactions, auto fee calculation |

## Node

```
./sost-node [options]
  --genesis <path>       Genesis block JSON (required)
  --chain <path>         Chain state file (load/save)
  --wallet <path>        Wallet file (default: wallet.json)
  --port <n>             P2P port (default: 19333)
  --rpc-port <n>         RPC port (default: 18232)
  --rpc-user <user>      RPC Basic Auth username
  --rpc-pass <pass>      RPC Basic Auth password
  --connect <host:port>  Connect to peer node
```

The node:
- Validates all blocks and transactions against consensus rules (R1-R14, S1-S12, CB1-CB10)
- Maintains the UTXO set and mempool
- Rescans wallet UTXOs on startup and persists to disk
- Auto-saves chain state every 30 seconds
- Supports P2P block/tx relay between peers

## Miner

```
./sost-miner [options]
  --genesis <path>       Genesis block JSON (required)
  --chain <path>         Chain state file (required)
  --rpc <host:port>      Submit blocks to node via RPC (recommended)
  --rpc-user <user>      RPC Basic Auth username
  --rpc-pass <pass>      RPC Basic Auth password
  --blocks <n>           Number of blocks to mine (default: 5)
  --max-nonce <n>        Max nonce per round (default: 500000)
  --profile <p>          Network profile: mainnet|testnet|dev
  --realtime             Use real timestamps (default)
```

**RPC mode** (`--rpc 127.0.0.1:18232`): Fetches mempool transactions via `getblocktemplate`, includes them in the block, distributes fees across coinbase outputs, submits via `submitblock`. This is the recommended mode.

**Standalone mode** (no `--rpc`): Writes directly to `chain.json`, coinbase-only blocks, no transaction support.

## Wallet CLI

```
./sost-cli [options] <command> [args...]

Options:
  --wallet <path>        Wallet file (default: wallet.json)
  --rpc-user <user>      RPC Basic Auth username
  --rpc-pass <pass>      RPC Basic Auth password
  --node <host:port>     Node address (default: 127.0.0.1:18232)
  --fee-rate <n>         Fee rate in stocks/byte (default: 1)

Commands:
  newwallet                    Create new wallet file
  getnewaddress [label]        Generate new receiving address
  listaddresses                List all wallet addresses with balances
  importprivkey <hex>          Import a 32-byte private key (hex)
  importgenesis <path>         Import genesis block coinbase UTXOs
  getbalance [address]         Show balance in SOST
  listunspent [address]        List unspent transaction outputs
  createtx <to> <amt>         Create and sign a transaction (auto fee)
  send <to> <amt>              Create, sign and broadcast to node via RPC
  dumpprivkey <address>        Reveal private key (DANGER)
  info                         Wallet summary
```

**Fee calculation (v1.3):** Fees are computed automatically based on transaction size. The CLI builds the transaction, measures its byte count, and sets `fee = size × fee_rate`. Default rate is 1 stock/byte (consensus minimum per rule S8). Use `--fee-rate 2` for priority.

**Coinbase maturity:** Coinbase UTXOs require 100 confirmations before they can be spent. The CLI queries the node for the current chain height and filters immature UTXOs automatically.

## Transaction Flow

1. `sost-cli send` queries the node for chain height (maturity filter)
2. CLI selects only mature UTXOs, builds the transaction, calculates fee from real size
3. CLI signs and broadcasts the transaction to the node via RPC
4. Node validates the transaction and accepts it to the mempool
5. `sost-miner` fetches mempool via `getblocktemplate` and includes transactions in the next block
6. Node confirms the transaction when the block is accepted
7. Transaction outputs become spendable immediately (coinbase outputs require 100 blocks)

## RPC API (port 18232)

```bash
# With authentication:
curl -s -X POST -u myuser:mypass \
    -d '{"method":"getinfo","id":1}' http://localhost:18232
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
| Initial block reward | 7.85100863 SOST |
| Emission | Smooth exponential decay, q = e^(-1/4) |
| Epoch length | 131,553 blocks (~2.503 years, Feigenbaum α) |
| Max supply | ~4,669,201 SOST (Feigenbaum δ × 10⁶) |
| 95% supply | ~12 epochs (~30 years) |
| Reward split | 50% miner · 25% Gold Vault · 25% PoPC Pool |
| Coinbase maturity | 100 blocks |
| Address format | `sost1` + 40 hex chars (20-byte pubkey hash) |
| Signature | ECDSA secp256k1 (libsecp256k1) with LOW-S |
| P2P port | 19333 |
| RPC port | 18232 |

## Constitutional Addresses

These addresses receive coinbase rewards at every block. Hardcoded at genesis, immutable forever.

| Role | Allocation |
|------|------------|
| **Miner reward** | 50% → miner's configured address |
| **Gold Vault** | 25% → automatic XAUT/PAXG purchases (auditable on-chain) |
| **PoPC Pool** | 25% → Proof of Personal Custody rewards |

Gold Vault and PoPC Pool addresses are defined in `include/sost/params.h`.

## Explorer (v3.8)

Standalone HTML file (`explorer.html`) that connects to your node's RPC.

Features:
- Dashboard: block height, avg block time, total supply, Gold Vault reserves, mempool
- Chain timing panel: wall clock elapsed, chain time, expected vs actual blocks, block lag
- Difficulty progress bar with epoch tracking
- Gold Reserves tracker (25% of all rewards since genesis)
- Emission curve chart (smooth exponential decay, 12 epochs, interactive tooltip)
- Block detail with transaction list (coinbase split + standard txs)
- Mature/immature balance breakdown per address with UTXO maturity progress bars
- Smart search: block height, full/partial hash, txid, sost1 address
- Pagination with NEWEST/OLDEST and NEWER/OLDER navigation
- Copy-to-clipboard on hashes and addresses
- Auto-refresh (10s) with new block notification

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

## Security Status

| Component | Status |
|-----------|--------|
| Transaction signing (libsecp256k1) | ✅ Complete |
| Consensus validation (R1-R14, S1-S12, CB1-CB10) | ✅ Complete |
| ASERT + cASERT difficulty adjustment | ✅ Complete |
| Mempool validation and relay | ✅ Complete |
| Transaction confirmation in blocks | ✅ Complete |
| RPC authentication (Basic Auth) | ✅ Complete |
| Coinbase maturity filter in wallet | ✅ Complete |
| Dynamic fee calculation (S8 compliant) | ✅ Complete |
| Wallet encryption | ⏳ Pre-launch |
| PoW verification in block acceptance | ⏳ Pre-launch |
| P2P encryption | 📋 Post-launch |

## License

MIT

# SOST Protocol

Sovereign Gold-Backed Cryptocurrency

CPU-friendly Proof-of-Work blockchain with constitutional gold reserves. Every block mined automatically allocates 25% to purchase physical gold (XAUT/PAXG) and 25% to Proof of Personal Custody rewards — hardcoded at genesis, immutable forever.

- **Website:** https://sostcore.com
- **Explorer:** https://explorer.sostcore.com
- **GitHub:** https://github.com/Neob1844/sost-core
- **Whitepaper:** https://sostcore.com/whitepaper.pdf

## Quick Start

```bash
# 1. Build
sudo apt install build-essential cmake libssl-dev libsecp256k1-dev
git clone https://github.com/Neob1844/sost-core.git
cd sost-core && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc)

# 2. Create wallet
./sost-cli newwallet

# 3. Import genesis block UTXOs
./sost-cli importgenesis genesis_block.json

# 4. Start node (terminal 1) — connects to seed.sostcore.com automatically
./sost-node --genesis genesis_block.json --chain chain.json \
    --rpc-user <user> --rpc-pass <pass> --profile mainnet

# 5. Start mining (terminal 2) — use YOUR wallet address
./sost-miner --address $(./sost-cli listaddresses | head -1) \
    --genesis genesis_block.json --chain chain.json \
    --rpc 127.0.0.1:18232 \
    --rpc-user <user> --rpc-pass <pass> --threads 4 --blocks 100

# 6. Send SOST (requires 1,000+ confirmations on coinbase UTXOs)
./sost-cli --wallet wallet.json --rpc-user <user> --rpc-pass <pass> \
    send <destination_address> 10.0
```

## Binaries

| Binary | Version | Description |
|--------|---------|-------------|
| sost-node | v0.3.2 | Full node — P2P networking, JSON-RPC (17 methods), chain validation, mempool |
| sost-miner | v0.6 | ConvergenceX PoW miner with mempool integration via RPC |
| sost-cli | v1.3 | Wallet CLI — create keys, send transactions, automatic fee calculation |
| sost-rpc | v0.1 | Standalone RPC client for node queries |

## Node

```
./sost-node [options]
  --genesis <path>       Genesis block JSON (required)
  --chain <path>         Chain state file (load/save)
  --wallet <path>        Wallet file (default: wallet.json)
  --port <n>             P2P port (default: 19333)
  --rpc-port <n>         RPC port (default: 18232)
  --rpc-user <user>      RPC authentication username (required unless --rpc-noauth)
  --rpc-pass <pass>      RPC authentication password (required unless --rpc-noauth)
  --rpc-noauth           Disable RPC authentication (not recommended)
  --connect <host:port>  Connect to specific peer (default: seed.sostcore.com:19333)
  --profile <p>          Network profile: mainnet|testnet|dev (default: mainnet)
```

The node:
- Validates all blocks and transactions against consensus rules (R1-R14, S1-S12, CB1-CB10)
- Maintains the UTXO set and mempool
- Rescans wallet UTXOs on startup and persists to disk
- Auto-saves chain state after every accepted block
- P2P block/tx relay with DoS protection (ban scoring, 64 inbound peer limit)
- Checkpoint validation and max reorg depth (100 blocks)

## Miner

```
./sost-miner [options]
  --address <sost1..>    REQUIRED: your wallet address to receive mining rewards
  --genesis <path>       Genesis block JSON (required)
  --chain <path>         Chain state file (required)
  --rpc <host:port>      Submit blocks to node via RPC (recommended)
  --rpc-user <user>      RPC authentication username
  --rpc-pass <pass>      RPC authentication password
  --blocks <n>           Number of blocks to mine (default: 5)
  --max-nonce <n>        Max nonce per round (default: 500000)
  --profile <p>          Network profile: mainnet|testnet|dev
  --realtime             Use real timestamps (default)
```

**RPC mode** (`--rpc 127.0.0.1:18232`): Fetches mempool transactions via `getblocktemplate`, includes them in the block, distributes fees across coinbase outputs, submits via `submitblock`. Recommended.

**Standalone mode** (no `--rpc`): Writes directly to chain.json, coinbase-only blocks, no transaction support. Not recommended for production.

## Wallet CLI

```
./sost-cli [--wallet <path>] [--rpc-user <user> --rpc-pass <pass>] <command> [args...]

  newwallet                    Create new wallet file
  getnewaddress [label]        Generate new receiving address
  listaddresses                List all wallet addresses with balances
  importprivkey <hex>          Import a 32-byte private key (hex)
  importgenesis <path>         Import genesis block coinbase UTXOs
  getbalance [address]         Show balance in SOST
  listunspent [address]        List unspent transaction outputs
  createtx <to> <amount>       Create and sign a transaction (outputs hex)
  send <to> <amount>           Create, sign and broadcast to node via RPC
  dumpprivkey <address>        Reveal private key (DANGER)
  info                         Wallet summary
```

**Fee calculation:** CLI v1.3 calculates fees automatically based on transaction size (default: 1 stock/byte, minimum relay fee: 1,000 stocks). Use `--fee-rate <n>` to override.

**Coinbase maturity:** Coinbase UTXOs require 1,000 confirmations before they can be spent. The CLI automatically filters immature UTXOs and shows clear error messages.

**Wallet encryption:** AES-256-GCM with scrypt key derivation (N=32768, r=8, p=1). Encrypt via `save_encrypted()` / decrypt via `load_encrypted()`.

## Transaction Flow

1. `sost-cli send` queries the node for current chain height (maturity filtering)
2. CLI selects mature UTXOs, calculates fee, builds and signs TX
3. CLI broadcasts signed TX to the node via `sendrawtransaction` RPC
4. Node validates the transaction and accepts it to the mempool
5. `sost-miner` fetches mempool via `getblocktemplate` and includes transactions in the next block
6. Node confirms the transaction when the block is accepted
7. Transaction outputs become spendable immediately (coinbase outputs require 1,000 blocks)

## RPC API (port 18232)

```bash
curl -s -u <user>:<pass> -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"getinfo","params":[]}' \
    http://localhost:18232
```

| Method | Params | Description |
|--------|--------|-------------|
| getinfo | — | Node status, height, difficulty, balance, mempool |
| getblockcount | — | Current chain height |
| getblockhash | height | Block hash at given height |
| getblock | hash | Block details including cASERT mode |
| getaddressinfo | address | Address balance, UTXO count and list |
| getbalance | — | Wallet balance |
| listunspent | — | Wallet UTXOs |
| gettxout | txid, vout | Query specific UTXO |
| validateaddress | address | Check address validity and ownership |
| getnewaddress | [label] | Generate new wallet address |
| sendrawtransaction | hex | Submit signed transaction to mempool |
| getmempoolinfo | — | Mempool size, bytes, fees |
| getrawmempool | — | Pending transaction IDs |
| getrawtransaction | txid [verbose] | Get raw tx from mempool |
| getpeerinfo | — | Connected P2P peers |
| submitblock | block_json | Submit mined block (used by miner) |
| getblocktemplate | — | Get mempool txs for block building |

## Network Parameters

| Parameter | Value |
|-----------|-------|
| Algorithm | ConvergenceX (CPU, 4GB RAM, ASIC-resistant) |
| Block time | 10 minutes target |
| Difficulty | ASERT (24h half-life) + cASERT overlay (L1-L5+, unbounded, k=4) |
| Initial block reward | 7.85100863 SOST |
| Emission | Smooth exponential decay, q = e^(-1/4) |
| Epoch length | 131,553 blocks (~2.503 years, Feigenbaum alpha) |
| Max supply | ~4,669,201 SOST (Feigenbaum delta x 10^6) |
| 95% supply | ~12 epochs (~30 years) |
| Reward split | 50% miner / 25% Gold Vault / 25% PoPC Pool |
| Coinbase maturity | 1,000 blocks |
| Min relay fee | 1,000 stocks (0.00001 SOST) |
| Address format | sost1 + 40 hex chars (20-byte pubkey hash) |
| Signature | ECDSA secp256k1 (libsecp256k1) with LOW-S |
| P2P port | 19333 |
| RPC port | 18232 |
| Default seed | seed.sostcore.com:19333 |
| Mainnet genesis | 2026-03-13 00:00:00 UTC |

## Constitutional Addresses

These addresses receive coinbase rewards at every block. Hardcoded at genesis, immutable forever.

| Role | Allocation |
|------|-----------|
| Miner reward | 50% to miner's configured address |
| Gold Vault | 25% to automatic XAUT/PAXG purchases (auditable on-chain) |
| PoPC Pool | 25% to Proof of Personal Custody rewards |

Gold Vault and PoPC Pool addresses are defined in `include/sost/params.h`.

## Explorer (v4.2)

Standalone HTML file (`explorer.html`) that connects to your node's RPC with authentication.

Features: dashboard with block height/supply/hashrate, difficulty progress bar, Gold Reserves tracker, PoPC Pool tracker, emission curve chart, chain timing panel, block detail with cASERT levels (L1-L5+, unbounded), address view with mature/immature balances, Foundation Reserves page, smart search, RPC auth, auto-refresh (10s), responsive design.

## Security Status

| Component | Status |
|-----------|--------|
| Transaction signing (libsecp256k1) | Complete |
| Consensus validation (R1-R14, S1-S12, CB1-CB10) | Complete |
| ASERT + cASERT difficulty adjustment (L1-L5+, unbounded) | Complete |
| Mempool validation and relay | Complete |
| Transaction confirmation in blocks | Complete |
| RPC authentication (--rpc-user/--rpc-pass) | Complete |
| Coinbase maturity filter (1,000 blocks) | Complete |
| Dynamic fee calculation (CLI v1.3) | Complete |
| Wallet encryption (AES-256-GCM + scrypt) | Complete |
| P2P DoS protection (ban scoring, peer limits) | Complete |
| Checkpoints + reorg limit (100 blocks) | Complete |
| write_exact() reliable socket writes | Complete |
| P2P encryption | Post-launch |

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

# Run tests
ctest --output-on-failure
```

## Reporting Issues

- **Bugs and feature requests:** https://github.com/Neob1844/sost-core/issues
- **Security vulnerabilities:** Use [GitHub private vulnerability reporting](https://github.com/Neob1844/sost-core/security/advisories/new) only. Do not open public issues for security bugs.

## License

MIT

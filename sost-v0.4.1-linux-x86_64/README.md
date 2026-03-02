# SOST Protocol v0.4.1 — Linux x86_64

**CPU-friendly Proof-of-Work cryptocurrency with constitutional gold reserves.**

## Quick Start

```bash
# 1. Install dependencies
sudo apt install libssl3 libsecp256k1-0

# 2. Create wallet
./sost-cli newwallet

# 3. Start node
./sost-node --genesis genesis_block.json --wallet wallet.json

# 4. Start mining (in another terminal)
./sost-miner --genesis genesis_block.json --wallet wallet.json --chain chain.json
```

## Binaries

| Binary | Description |
|--------|-------------|
| `sost-node` | Full node with P2P networking + RPC server |
| `sost-miner` | ConvergenceX PoW miner (CPU, 4GB RAM) |
| `sost-cli` | Wallet management CLI |

## Node Options

```
./sost-node [options]
  --genesis <path>       Genesis block JSON (required)
  --wallet <path>        Wallet file (default: wallet.json)
  --chain <path>         Load/save chain state
  --port <n>             P2P port (default: 19333)
  --rpc-port <n>         RPC port (default: 18232)
  --connect <host:port>  Connect to peer
```

## Miner Options

```
./sost-miner [options]
  --genesis <path>       Genesis block JSON (required)
  --wallet <path>        Wallet file
  --chain <path>         Chain state file
  --blocks <n>           Number of blocks to mine (default: unlimited)
```

## RPC API (port 18232)

| Method | Params | Description |
|--------|--------|-------------|
| `getinfo` | — | Node status, height, difficulty, balance |
| `getblockcount` | — | Current chain height |
| `getblockhash` | height | Block hash at height |
| `getblock` | hash | Block details + cASERT mode |
| `getaddressinfo` | address | Address balance + UTXOs |
| `getbalance` | — | Wallet balance |
| `listunspent` | — | Wallet UTXOs |
| `gettxout` | txid, vout | Query specific UTXO |
| `validateaddress` | address | Check address validity |
| `getnewaddress` | [label] | Generate new address |
| `sendrawtransaction` | hex | Submit signed transaction |
| `getmempoolinfo` | — | Mempool statistics |
| `getrawmempool` | — | Pending transaction IDs |
| `getpeerinfo` | — | Connected peers |

Example:
```bash
curl -X POST -d '{"method":"getinfo","id":1}' http://localhost:18232
```

## Network

- **Algorithm:** ConvergenceX (CPU/GPU, 4GB RAM, ASIC-resistant)
- **Block time:** 10 minutes (ASERT + cASERT difficulty adjustment)
- **Block reward:** 7.8510 SOST (50% miner, 25% Gold Vault, 25% PoPC Pool)
- **Emission:** Feigenbaum decay, ~131,553 blocks per epoch
- **Addresses:** `sost1` prefix (20-byte pubkey hash)
- **P2P port:** 19333
- **RPC port:** 18232

## Constitutional Addresses

| Address | Role |
|---------|------|
| `sost1be23...` | Gold Vault (25% of rewards → automatic XAUT/PAXG purchases) |
| `sost18a22...` | PoPC Pool (25% of rewards → Proof of Personal Custody incentives) |

## Explorer

- Local: Open `explorer.html` and connect to `http://localhost:18232`
- Online: https://explorer.sostcore.com

## Links

- Website: https://sostcore.com
- Explorer: https://explorer.sostcore.com
- GitHub: https://github.com/sostprotocol/sost-core

## License

MIT

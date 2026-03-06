# SOST Mining Guide — From Zero to First Block

## Requirements

- **OS:** Ubuntu 24.04 (or any Linux with GCC 13+)
- **RAM:** 4GB minimum (ConvergenceX uses a 4GB scratchpad)
- **CPU:** Any modern CPU — SOST is CPU-mined (no GPU/ASIC advantage)
- **Disk:** 1GB free space
- **Network:** Connection to a SOST seed node

## Step 1: Install Dependencies

```bash
sudo apt update
sudo apt install -y build-essential cmake libssl-dev libsecp256k1-dev
```

## Step 2: Build from Source

```bash
git clone https://github.com/Neob1844/sost-core.git
cd sost-core
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

You should see four binaries: `sost-node`, `sost-miner`, `sost-cli`, `sost-rpc`.

## Step 3: Create Your Wallet

```bash
./sost-cli newwallet
```

This creates `wallet.json` with your first SOST address (`sost1...`). **Back up this file — it contains your private keys.**

Generate a dedicated mining address:
```bash
./sost-cli getnewaddress mining
```

**Optional:** Encrypt your wallet with a passphrase (AES-256-GCM + scrypt):
```bash
./sost-cli encryptwallet
```

## Step 4: Start the Node

Open **Terminal 1**:
```bash
./sost-node \
    --genesis genesis_block.json \
    --chain chain.json \
    --rpc-user YOUR_USER \
    --rpc-pass YOUR_PASS \
    --profile mainnet
```

The node connects to `seed.sostcore.com:19333` automatically. To use a specific peer instead:
```bash
./sost-node ... --connect <IP>:19333
```

The node will:
1. Connect to the seed node
2. Download and validate the full chain (Initial Block Download)
3. Start listening on P2P port 19333 and RPC port 18232

Wait until the chain is fully synced before mining. Check progress:
```bash
curl -s -u YOUR_USER:YOUR_PASS -X POST \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"getinfo","params":[]}' \
    http://127.0.0.1:18232
```

## Step 5: Start Mining

Open **Terminal 2**:
```bash
./sost-miner \
    --genesis genesis_block.json \
    --chain chain.json \
    --wallet wallet.json \
    --rpc 127.0.0.1:18232 \
    --rpc-user YOUR_USER \
    --rpc-pass YOUR_PASS \
    --threads 4 \
    --blocks 100
```

Adjust `--threads` to your CPU core count (leave 1-2 cores free for the node).

The miner will:
- Fetch pending transactions from the mempool
- Build a candidate block with the correct coinbase split (50% to you, 25% Gold Vault, 25% PoPC Pool)
- Run the ConvergenceX proof-of-work algorithm
- Submit solved blocks to your node via RPC
- Your node validates and broadcasts to the network

## Step 6: Check Your Balance

```bash
./sost-cli --wallet wallet.json \
    --rpc-user YOUR_USER --rpc-pass YOUR_PASS \
    getbalance
```

**Important:** Mined coins require **100 confirmations** before they can be spent (coinbase maturity). At 10 minutes per block, that's roughly 16-17 hours.

## Step 7: Send SOST

Once you have mature coins:
```bash
./sost-cli --wallet wallet.json \
    --rpc-user YOUR_USER --rpc-pass YOUR_PASS \
    send sost1DESTINATION_ADDRESS 10.0
```

Fees are calculated automatically based on transaction size (default: 1 stock/byte, minimum 1,000 stocks = 0.00001 SOST).

Then mine at least 1 block to confirm the transaction:
```bash
./sost-miner --genesis genesis_block.json --chain chain.json \
    --wallet wallet.json --rpc 127.0.0.1:18232 \
    --rpc-user YOUR_USER --rpc-pass YOUR_PASS \
    --threads 4 --blocks 1
```

## Network Parameters

| Parameter | Value |
|-----------|-------|
| Algorithm | ConvergenceX (CPU, 4GB RAM, ASIC-resistant) |
| Difficulty | ASERT (24h half-life) + cASERT overlay (L1-L5, k=4) |
| Block time | 10 minutes target |
| Initial reward | 7.85100863 SOST |
| Coinbase split | 50% miner / 25% Gold Vault / 25% PoPC Pool |
| Maturity | 100 confirmations |
| Max supply | ~4,669,201 SOST |
| Min relay fee | 0.00001 SOST (1,000 stocks) |
| P2P port | 19333 |
| RPC port | 18232 |
| Default seed | seed.sostcore.com:19333 |
| Mainnet genesis | 2026-03-13 00:00:00 UTC |

## Troubleshooting

**"401 Unauthorized" / blocks rejected:**
Your `--rpc-user` and `--rpc-pass` don't match between miner and node. They must be identical.

**Miner seems stuck / nonce keeps climbing:**
This is normal. ConvergenceX is computationally intensive — each nonce attempt involves 100,000 sequential iterations across a 4GB scratchpad. Higher difficulty = more attempts needed. Be patient.

**"insufficient mature balance":**
Your mined coins haven't reached 100 confirmations yet. Keep mining or wait for the chain to advance.

**Node not syncing / no peers:**
Check that port 19333 is open in your firewall and that you're using the correct seed node IP with `--connect`.

**Balance shows 0 but explorer shows coins:**
The CLI wallet only tracks UTXOs it knows about. If you mined via RPC mode, the node has the complete UTXO set. Use the explorer to check your real balance.

## Links

- **Website:** https://sostcore.com
- **Explorer:** https://explorer.sostcore.com
- **GitHub:** https://github.com/Neob1844/sost-core
- **BitcoinTalk:** [ANN thread — TBD]
- **Whitepaper:** https://sostcore.com/whitepaper.pdf

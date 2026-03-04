SOST Protocol — Sovereign Gold-Backed Cryptocurrency
CPU-friendly Proof-of-Work blockchain with constitutional gold reserves.
Every block mined automatically allocates 25% to purchase physical gold (XAUT/PAXG) and 25% to Proof of Personal Custody rewards — hardcoded at genesis, immutable forever.

Website: sostcore.com
GitHub: github.com/Neob1844/sost-core
Explorer: Open explorer.html and connect to your node at http://localhost:18232

Quick Start
bash# 1. Create wallet
./sost-cli newwallet

# 2. Import genesis block UTXOs
./sost-cli importgenesis genesis_block.json

# 3. Start node (terminal 1)
./sost-node --genesis genesis_block.json --chain chain.json \
    --rpc-user <user> --rpc-pass <pass>

# 4. Start mining (terminal 2)
./sost-miner --genesis genesis_block.json --chain chain.json \
    --wallet wallet.json \
    --rpc 127.0.0.1:18232 --rpc-user <user> --rpc-pass <pass> \
    --threads 4 --blocks 100

# 5. Send SOST (terminal 3 — requires 100+ confirmations on coinbase UTXOs)
./sost-cli --wallet wallet.json --rpc-user <user> --rpc-pass <pass> \
    send <destination_address> 10.0

# 6. Mine 1 block to confirm the transaction
./sost-miner --genesis genesis_block.json --chain chain.json \
    --wallet wallet.json \
    --rpc 127.0.0.1:18232 --rpc-user <user> --rpc-pass <pass> \
    --threads 4 --blocks 1
Binaries
BinaryVersionDescriptionsost-nodev0.3.2Full node — P2P networking, JSON-RPC (17 methods), chain validation, mempoolsost-minerv0.5ConvergenceX PoW miner with mempool integration via RPCsost-cliv1.3Wallet CLI — create keys, send transactions, automatic fee calculationsost-rpcv0.1Standalone RPC client for node queries
Node
./sost-node [options]
  --genesis <path>       Genesis block JSON (required)
  --chain <path>         Chain state file (load/save)
  --wallet <path>        Wallet file (default: wallet.json)
  --port <n>             P2P port (default: 19333)
  --rpc-port <n>         RPC port (default: 18232)
  --rpc-user <user>      RPC authentication username (required unless --rpc-noauth)
  --rpc-pass <pass>      RPC authentication password (required unless --rpc-noauth)
  --rpc-noauth           Disable RPC authentication (not recommended)
  --connect <host:port>  Connect to peer node
The node:

Validates all blocks and transactions against consensus rules (R1-R14, S1-S12, CB1-CB10)
Maintains the UTXO set and mempool
Rescans wallet UTXOs on startup and persists to disk
Auto-saves chain state every 30 seconds
Supports P2P block/tx relay between peers

Miner
./sost-miner [options]
  --genesis <path>       Genesis block JSON (required)
  --chain <path>         Chain state file (required)
  --wallet <path>        Wallet file (required for RPC mode)
  --rpc <host:port>      Submit blocks to node via RPC (recommended)
  --rpc-user <user>      RPC authentication username
  --rpc-pass <pass>      RPC authentication password
  --blocks <n>           Number of blocks to mine (default: 5)
  --threads <n>          Mining threads (default: 1)
  --max-nonce <n>        Max nonce per round (default: 500000)
  --profile <p>          Network profile: mainnet|testnet|dev
  --realtime             Use real timestamps (default)
RPC mode (--rpc 127.0.0.1:18232): Fetches mempool transactions via getblocktemplate, includes them in the block, distributes fees across coinbase outputs, submits via submitblock. This is the recommended mode.
Standalone mode (no --rpc): Writes directly to chain.json, coinbase-only blocks, no transaction support. Not recommended for production.
Wallet CLI
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
Fee calculation: CLI v1.3 calculates fees automatically based on transaction size (default: 1 stock/byte, minimum relay fee: 1000 stocks). Use --fee-rate <n> to override (e.g., --fee-rate 2 for priority).
Coinbase maturity: Coinbase UTXOs require 100 confirmations before they can be spent. The CLI automatically filters immature UTXOs and shows clear error messages distinguishing between immature and insufficient funds.
Transaction Flow

sost-cli send queries the node for current chain height (maturity filtering)
CLI selects mature UTXOs, calculates fee based on transaction size, builds and signs TX
CLI broadcasts signed TX to the node via sendrawtransaction RPC
Node validates the transaction and accepts it to the mempool
sost-miner fetches mempool via getblocktemplate and includes transactions in the next block
Node confirms the transaction when the block is accepted
Transaction outputs become spendable immediately (coinbase outputs require 100 blocks)

RPC API (port 18232)
bashcurl -s -u <user>:<pass> -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"getinfo","params":[]}' \
    http://localhost:18232
MethodParamsDescriptiongetinfo—Node status, height, difficulty, balance, mempoolgetblockcount—Current chain heightgetblockhashheightBlock hash at given heightgetblockhashBlock details including cASERT modegetaddressinfoaddressAddress balance, UTXO count and listgetbalance—Wallet balancelistunspent—Wallet UTXOsgettxouttxid, voutQuery specific UTXOvalidateaddressaddressCheck address validity and ownershipgetnewaddress[label]Generate new wallet addresssendrawtransactionhexSubmit signed transaction to mempoolgetmempoolinfo—Mempool size, bytes, feesgetrawmempool—Pending transaction IDsgetrawtransactiontxid [verbose]Get raw tx from mempoolgetpeerinfo—Connected P2P peerssubmitblockblock_jsonSubmit mined block (used by miner)getblocktemplate—Get mempool txs for block building
Network Parameters
ParameterValueAlgorithmConvergenceX (CPU, 4GB RAM, ASIC-resistant)Block time10 minutes targetDifficultyASERT + cASERT overlay (24h half-life, k=4)Initial block reward7.85100863 SOSTEmissionSmooth exponential decay, q = e^(-1/4)Epoch length131,553 blocks (~2.503 years, Feigenbaum α)Max supply~4,669,201 SOST (Feigenbaum δ × 10⁶)95% supply~12 epochs (~30 years)Reward split50% miner · 25% Gold Vault · 25% PoPC PoolCoinbase maturity100 blocksMin relay fee1,000 stocks (0.00001 SOST)Address formatsost1 + 40 hex chars (20-byte pubkey hash)SignatureECDSA secp256k1 (libsecp256k1) with LOW-SP2P port19333RPC port18232
Constitutional Addresses
These addresses receive coinbase rewards at every block. Hardcoded at genesis, immutable forever.
RoleAllocationMiner reward50% → miner's configured addressGold Vault25% → automatic XAUT/PAXG purchases (auditable on-chain)PoPC Pool25% → Proof of Personal Custody rewards
Gold Vault and PoPC Pool addresses are defined in include/sost/params.h.
Explorer (v3.14)
Standalone HTML file (explorer.html) that connects to your node's RPC with authentication.
Features:

Dashboard: block height, avg block time, total supply, miner rewards, Gold Vault, PoPC Pool, mempool, hashrate, countdown
Difficulty progress bar with epoch tracking (bits_q Q16.16 + bits_real decimal)
Gold Reserves tracker with real block-interval bar chart
PoPC Pool tracker with real block-interval bar chart
Emission curve chart (smooth exponential decay, 12 epochs, interactive tooltip)
Chain timing panel: wall clock, chain time, expected vs actual blocks, block lag
Block detail: bits_q, bits_real, cASERT level/signal, nonce, subsidy, coinbase split
cASERT panel: L1-L5+ level display with color coding and ConvergenceX parameter scaling
Address view: balance (mature/immature), UTXO list, transaction history, role tagging
Smart search: block height, full/partial hash, txid, sost1 address
RPC authentication support (username/password fields)
Auto-refresh (10s) with new block notification
Responsive design (desktop + mobile)

Build from Source
bash# Dependencies (Ubuntu 24.04)
sudo apt install build-essential cmake libssl-dev libsecp256k1-dev

# Build
git clone https://github.com/Neob1844/sost-core.git
cd sost-core
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
Security Status
ComponentStatusTransaction signing (libsecp256k1)✅ CompleteConsensus validation (R1-R14, S1-S12, CB1-CB10)✅ CompleteASERT + cASERT difficulty adjustment (k=4)✅ CompleteMempool validation and relay✅ CompleteTransaction confirmation in blocks✅ CompleteRPC authentication (--rpc-user/--rpc-pass)✅ CompleteCoinbase maturity filter (100 blocks)✅ CompleteDynamic fee calculation (CLI v1.3)✅ CompleteWallet encryption (AES-256)⏳ Pre-launchP2P encryption📋 Post-launch
License
MIT

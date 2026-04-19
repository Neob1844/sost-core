# SOST Protocol

Sovereign Gold-Backed Cryptocurrency

CPU-friendly Proof-of-Work blockchain with constitutional gold reserves. Every block mined automatically allocates 25% to purchase physical gold (XAUT/PAXG) and 25% to Proof of Personal Custody rewards — hardcoded at genesis, immutable forever.

The Foundation's manual operations during Phase 1 are transitional by design, not permanent — progressive decentralization toward full automation is a constitutional commitment, not a discretionary goal.

- **Website:** https://sostcore.com
- **Explorer:** https://sostcore.com/sost-explorer.html
- **GitHub:** https://github.com/Neob1844/sost-core
- **Whitepaper:** https://sostcore.com/whitepaper.pdf

## System Requirements

| Role | RAM | CPU | Notes |
|------|-----|-----|-------|
| **Full node** (verify/send/receive) | ~500 MB | Any modern CPU | Verifies blocks via Transcript V2 in ~0.2ms. 2 GB VPS sufficient. |
| **Miner** (find blocks) | 8 GB min (4 GB dataset + 4 GB scratchpad) | Multi-core recommended | 16 GB total system RAM recommended. Each thread = 1 independent attempt. |

Mining is memory-hard (ASIC resistant), but verification is lightweight — anyone can run a node.

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
| sost-miner | v0.6 | ConvergenceX Transcript V2 PoW miner with mempool integration via RPC |
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
- Checkpoint validation and max reorg depth (500 blocks)

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
| Algorithm | ConvergenceX Transcript V2 (CPU, 8GB RAM mining: 4GB dataset + 4GB scratchpad; ~500MB node validation via 11-phase segment/round verification at ~0.2ms, ASIC-resistant) |
| Block time | 10 minutes target |
| Difficulty | cASERT unified (bitsQ Q16.16, 40 equalizer profiles E4-H35). V1 (blocks <1450): 48h halflife, 6.25% delta cap. **V2 (blocks >=1450): 24h halflife, 12.5% delta cap.** |
| Initial block reward | 7.85100863 SOST |
| Emission | Smooth exponential decay, q = e^(-1/4) |
| Epoch length | 131,553 blocks (~2.503 years, Feigenbaum alpha) |
| Max supply | 4,669,201 SOST hard cap, enforced at consensus level (subsidy drops to zero when cap is reached; miners earn fees only) |
| 95% supply | ~12 epochs (~30 years) |
| Reward split | 50% miner / 25% Gold Funding Vault / 25% PoPC Pool |
| Coinbase maturity | 1,000 blocks |
| Min relay fee | 1,000 stocks (0.00001 SOST) |
| Address format | sost1 + 40 hex chars (20-byte pubkey hash) |
| Signature | ECDSA secp256k1 (libsecp256k1) with LOW-S |
| P2P port | 19333 |
| RPC port | 18232 |
| Default seed | seed.sostcore.com:19333 |
| Mainnet genesis | 2026-03-15 18:00:00 UTC |
| Chain selection | Best chain by cumulative work (NOT longest chain). work = floor(2^256 / (target+1)) per block |
| Fork resolution | Atomic reorg with full rollback on failure. MAX_REORG_DEPTH = 500 blocks (~3.5 days) |
| P2P encryption | X25519 + ChaCha20-Poly1305 (default on) |

## Constitutional Addresses

These addresses receive coinbase rewards at every block. Hardcoded at genesis, immutable forever.

| Role | Allocation |
|------|-----------|
| Miner reward | 50% to miner's configured address |
| Gold Funding Vault | 25% to automatic XAUT/PAXG purchases (auditable on-chain) |
| PoPC Pool | 25% to Proof of Personal Custody rewards |

Gold Funding Vault and PoPC Pool addresses are defined in `include/sost/params.h`.

### Transaction Fees

| Parameter | Value |
|-----------|-------|
| Min relay fee | 1 stock/byte (0.00000001 SOST/byte) |
| Typical TX (~250 bytes) | ~0.00000250 SOST |
| Fee split | 50% miner / 25% Gold Vault / 25% PoPC Pool |
| Fee market | RBF (Replace-by-Fee) + CPFP (Child-Pays-for-Parent) |
| Arithmetic | Rational integer (no floating-point in consensus) |

Fees follow the same constitutional 50/25/25 split as block subsidies. After emission ends, fees continue accumulating gold reserves in perpetuity.

## Native Financial Primitives

SOST does not support smart contracts. Instead, purpose-built transaction types provide financial primitives directly in the consensus layer — deterministic, auditable, and not exploitable through contract bugs.

| Phase | Timeline | Description |
|-------|----------|-------------|
| 0 | IMPLEMENTED | BOND_LOCK (0x10) + ESCROW_LOCK (0x11) — consensus types, activate at height 5000 |
| 0 | IMPLEMENTED | PoPC Model A (bond+custody) — 5 RPC commands, registry, rewards, slash |
| 0 | IMPLEMENTED | PoPC Model B (escrow) — 4 RPC commands, immediate rewards |
| 1 | Q2-Q3 2026 | Live custody verification via Etherscan + first PoPC participants |
| 2 | Q4 2027-Q1 2028 | Native metal tokens (XAUT-SOST, PAXG-SOST, SLVR-SOST) |
| 3 | Q2 2028 | Fully native PoPC — zero Ethereum dependency |

Active output types at height 5000: `OUT_BOND_LOCK` (0x10), `OUT_ESCROW_LOCK` (0x11). `OUT_BURN` (0x20) is reserved but **not planned for activation** — SOST supply is immutable by construction.

**PoPC RPC commands (10 total):** `popc_register`, `popc_status`, `popc_check`, `popc_release`, `popc_slash`, `escrow_register`, `escrow_status`, `escrow_verify`, `escrow_complete`, `getsostprice`. Dynamic rewards adjusted by Pool Utilization Ratio (PUR). Anti-whale tiers above 10 oz. Step-by-step guide: `website/sost-popc.html`.

**SOST Reference Price:** Calculated as `(gold committed in PoPC × gold price) ÷ total SOST supply`. Foundation commitment: 0.6 XAUT + 0.6 PAXG = 1.2 oz. Gold prices fetched live from CoinGecko (XAUT + PAXG average). This is NOT a market price — it will be replaced by exchange data when SOST is listed on a CEX/DEX.

## Explorer (v4.2)

Standalone HTML file (`explorer.html`) that connects to your node's RPC with authentication.

Features: dashboard with block height/supply/hashrate, difficulty progress bar, Gold Reserves tracker, PoPC Pool tracker, emission curve chart, chain timing panel, block detail with cASERT equalizer profiles (E4-H35), address view with mature/immature balances, Foundation Reserves page, smart search, RPC auth, auto-refresh (10s), responsive design.

## Security Status

| Component | Status |
|-----------|--------|
| Transaction signing (libsecp256k1) | Complete |
| Consensus validation (R1-R14, S1-S12, CB1-CB10) | Complete |
| cASERT bitsQ difficulty adjustment (L1-L5 fixed, L6+ unbounded) | Complete |
| Mempool validation and relay | Complete |
| Transaction confirmation in blocks | Complete |
| RPC authentication (--rpc-user/--rpc-pass) | Complete |
| Coinbase maturity filter (1,000 blocks) | Complete |
| Dynamic fee calculation (CLI v1.3) | Complete |
| Wallet encryption (AES-256-GCM + scrypt) | Complete |
| P2P DoS protection (ban scoring, peer limits) | Complete |
| Checkpoints + reorg limit (500 blocks) | Complete |
| write_exact() reliable socket writes | Complete |
| P2P encryption (X25519 + ChaCha20-Poly1305) | Active (default on) |
| HD Wallet BIP39 (12-word seed phrases) | Complete |
| SOST-PSBT offline signing | Complete |
| Native multisig (sost3 addresses, OP_CHECKMULTISIG) | Complete |
| Trusted address book (4 trust levels) | Complete |
| Treasury safety profile (daily limits, vault mode) | Complete |
| RBF (Replace-by-Fee) | Complete |
| CPFP (Child-Pays-for-Parent) | Complete |
| Build hardening (6 compiler/linker flags) | Complete |
| Capsule Protocol v1 (binary tx metadata, height 5000) | Complete |
| cASERT V2 fork (24h halflife, 12.5% cap, block 1450) | Complete |

**28/28 CTest targets pass.**

**cASERT profile update note:** No regenesis required. Genesis block hash, commit format, and Transcript V2 verification semantics are unchanged. However, the expanded cASERT profile range (E4-H35, 40 profiles) is consensus-affecting across software versions: the node validates the miner's declared profile against the permitted range. All nodes and miners must run the updated binary before launch to ensure consistent profile validation.

## Fast Sync

New nodes sync faster by skipping expensive ConvergenceX recomputation for trusted historical blocks. Structural, semantic, and economic validation always runs — only the expensive CX recompute (100K rounds, 4GB scratchpad + 4GB dataset, stability basin) is conditionally skipped. Note: with Transcript V2, node validation uses an 11-phase compact proof (segments_root + sampled round witnesses) at ~0.2ms per block — no scratchpad/dataset needed (both are independently indexable at O(1) via SplitMix64/SHA256).

This does not change consensus rules. A block that passes fast sync verification would also pass full verification. The only difference is computational cost.

**Trust model** (two independent mechanisms):
1. **Hard checkpoints**: A block is trusted ONLY if its height AND block hash match a hardcoded checkpoint exactly. Lower height alone is never sufficient.
2. **Assumevalid anchor**: If a known block hash exists on the active chain, ancestors of that branch can skip expensive CX recomputation. If the anchor is not on the active chain, no fast trust.

**Always verified** (all blocks, all modes): header structure, timestamps/MTP, cASERT bitsQ difficulty, commit<=target, coinbase split (50/25/25), constitutional addresses, transaction semantics, UTXO updates.

**Skipped** (trusted historical blocks only): full 100K-round gradient descent, 4GB scratchpad + 4GB dataset rebuild (miner-only memory), stability basin re-verification.

Flags:
- `--full-verify`: Force full ConvergenceX recomputation for every block
- `--no-fast-sync`: Same as --full-verify

Checkpoints and assumevalid anchor are updated with each source code release.

| Sync mode | 10K blocks | 50K blocks | 100K blocks |
|-----------|-----------|-----------|------------|
| --full-verify | ~3 days | ~15 days | ~30 days |
| default (fast) | ~2 min | ~5 min | ~10 min |

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

### GeaSpirit — Mineral Intelligence Platform

GeaSpirit is an advanced remote sensing and exploration intelligence platform based on multi-source fusion and zone-based validation. It identifies zones with high probability of containing mineral deposits — metallic AND non-metallic — from publicly available satellite, geophysical, geological, and mineralogical data.

**Canonical Objective:** "There is [MINERAL] at [DEPTH] at [COORDINATES] with [X%] certainty."

**Data sources:** Sentinel-2, Landsat 8/9, EMIT, SRTM DEM, MRDS, OZMIN, Macrostrat, Mindat.org, EarthMRI, Google Earth Engine.

**Validated commodity types:** Porphyry Cu (0.882 AUC), Orogenic Au (0.922 AUC), IOCG (0.841), SEDEX Cu-Pb-Zn (0.781), Sediment-hosted Cu (0.760), Lithium brines/salares (0.891), Epithermal Au-Ag (queued).

**Canonical Score: 25.1/40 (63%)** — Methodology frozen v4. Gravity integrated. 11+ zones across 4 continents.

**Remote-first multi-zone (Phase 53):** Roșia Montană 27.4/40, Pebble Alaska 24.2/40, Kalgoorlie 15.0/40 — all without local geophysics. 3-tier architecture: universal remote baseline + public evidence + optional local bonus.

**Case studies:** Pebble Mine Alaska (completed — 516 S2 images, 497 frontier targets, DS608 ground-truth integration), Roșia Montană Romania (epithermal Au-Ag, Golden Quadrilateral).

Current phase: Phase 53 — Remote-first global mineral search engine with public evidence fusion.

See `docs/GEASPIRIT_TECHNOLOGY_SUMMARY.md`.

### Materials Discovery Engine

Autonomous computational materials discovery platform. Predicts formation energy and electronic band gap from crystal structure without physical synthesis.

- **Corpus:** 76,193 validated crystalline materials (JARVIS DFT + AFLOW)
- **Campaign profiles:** 19 discovery profiles including battery, semiconductor, water/lithium/membrane
- **Functional discovery:** Ion separation, desalination, lithium recovery, membrane candidates
- **Full-corpus scan:** 35,589 functionally relevant materials screened, 11,339 multi-function candidates identified
- **Validation bridge:** Prediction → observation lifecycle with reconciliation
- **Cost:** $0/month — runs entirely on CPU

**Phase 30 — Consensus ranking:** Multi-track consensus ranker, PV false-positive risk flags (6 physics-informed), DFT triage queues (exploit/explore/cross-track). 21 candidates ranked → 11 DFT-queued. Cross-track winner: GaIn.

## Security

- Build hardening: stack protector, ASLR (PIE), RELRO, FORTIFY_SOURCE — 15/15 tests pass
- Transaction Safety Layer: trusted destinations, cooldown, anti-phishing (no consensus change)
- Fee system: 1 stock/byte minimum, rational fee-rate ordering, estimatefee advisory
- cASERT profile exposed via RPC getinfo (real-time from node)

## Reporting Issues

- **Bugs and feature requests:** https://github.com/Neob1844/sost-core/issues
- **Security vulnerabilities:** Use the private contact form at [sostcore.com/sost-contact.html](https://sostcore.com/sost-contact.html) and select "Security Vulnerability Report". Do NOT open a public GitHub issue for security disclosures.

---

## Disclaimer

SOST is **experimental, unaudited software**. It is a completely new proof-of-work protocol written from scratch — **NOT a fork** of Bitcoin, Litecoin, Monero, RandomX, Ethash, Equihash, CryptoNight, X11, Scrypt, or any other existing cryptocurrency or mining algorithm. The ConvergenceX proof-of-work, cASERT difficulty adjustment, and constitutional economic model are original designs.

**This codebase has NOT been audited by any external security firm.** Testing has been conducted using internal tools, 28 test suites, and manual code review. The protocol has NOT been stress-tested by a large number of independent miners. Undiscovered vulnerabilities may exist.

**Every participant is solely responsible for their own investment decisions.** You may lose your entire investment. The developer (NeoB) assumes NO liability for any losses resulting from the use of this software, whether caused by bugs, vulnerabilities, design flaws, or any other reason. This is not financial advice.

SOST is provided "AS IS" without warranty of any kind.

## License

**ConvergenceX License — Source-Available with Refundable Deposit.** See [LICENSE](LICENSE) for full terms.

The source code is publicly readable, auditable, and open to contribution. No license is required to read, study, audit, or contribute. Commercial deployment and production use require a valid license obtained by locking a refundable security deposit of $1,000 USD equivalent in SOST for one year. The deposit is returned in full — no fees, no deductions. License verification is trustless and on-chain.

The SOST name and ConvergenceX algorithm name are trademarks of the SOST Protocol Foundation.

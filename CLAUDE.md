# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SOST is a CPU-friendly, gold-backed cryptocurrency with a UTXO-based transaction model. Every block allocates 50% to miner, 25% to Gold Vault, 25% to PoPC Pool — hardcoded and immutable. C++17 codebase, built with CMake.

## Build Commands

```bash
# Dependencies (Ubuntu 24.04)
sudo apt install build-essential cmake libssl-dev libsecp256k1-dev

# Build (from project root)
mkdir -p build && cd build && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc)
# Or from project root with existing build dir:
cmake --build build -j$(nproc)

# Run all tests
cd build && ctest --output-on-failure

# Run a single test
./build/test-transaction       # or any test binary name
ctest -R transaction           # by CTest name pattern

# Safe rebuild (backs up chainstate + wallet before building)
./safe-rebuild.sh
```

### Test targets (CTest names → binaries)

| CTest name | Binary | Source |
|---|---|---|
| chunk1 | test-chunk1 | tests/test_chunk1.cpp |
| chunk2 | test-chunk2 | tests/test_chunk2.cpp |
| transaction | test-transaction | tests/test_transaction.cpp |
| tx-signer | test-tx-signer | tests/test_tx_signer.cpp |
| tx-validation | test-tx-validation | tests/test_tx_validation.cpp |
| capsule | test-capsule | tests/test_capsule_codec.cpp |
| utxo-set | test-utxo-set | tests/test_utxo_set.cpp |
| merkle-block | test-merkle-block | tests/test_merkle_block.cpp |
| mempool | test-mempool | tests/test_mempool.cpp |
| casert | test-casert | tests/test_casert.cpp |
| bond-lock | test-bond-lock | tests/test_bond_lock.cpp |
| checkpoints | test-checkpoints | tests/test_checkpoints.cpp |
| transcript-v2 | test-transcript-v2 | tests/test_transcript_v2.cpp |
| reorg | test-reorg | tests/test_reorg.cpp |
| chainwork | test-chainwork | tests/test_chainwork.cpp |
| addressbook | test-addressbook | tests/test_addressbook.cpp |
| wallet-policy | test-wallet-policy | tests/test_wallet_policy.cpp |
| rbf | test-rbf | tests/test_rbf.cpp |
| cpfp | test-cpfp | tests/test_cpfp.cpp |
| hd-wallet | test-hd-wallet | tests/test_hd_wallet.cpp |
| psbt | test-psbt | tests/test_psbt.cpp |
| multisig | test-multisig | tests/test_multisig.cpp |

Tests use a simple `TEST(name, condition)` macro — no external framework. 22/22 CTest targets pass.

## Architecture

### Static library (`sost-core`) + 4 binaries

The core static library contains all consensus, crypto, and data structures. Four binaries link against it:

- **sost-node** (`src/sost-node.cpp`) — Full node: P2P (port 19333), JSON-RPC (port 18232), chain validation, mempool
- **sost-miner** (`src/sost-miner.cpp`) — ConvergenceX PoW miner, `--address` required, submits via RPC
- **sost-cli** (`src/sost-cli.cpp`) — Wallet CLI: key management, tx creation/signing/broadcast, fee calculation
- **sost-rpc** (`src/sost-rpc.cpp`) — Standalone RPC client for node queries

### Consensus pipeline (block validation layers)

Defined in `include/sost/block_validation.h`:
- **L1**: Structure (size, tx count, coinbase at tx[0])
- **L2**: Header context (prev-link, timestamp, expected difficulty)
- **L3**: Transaction consensus (fees, subsidy, coinbase split)
- **L4**: Atomic UTXO connect with BlockUndo for reorgs

### Transaction validation rules

Defined in `include/sost/tx_validation.h`:
- **R-rules (R1-R14)**: Structural — version, types, counts, amounts, size, payload
- **S-rules (S1-S12)**: Spend — UTXO lookup, pubkey hash match, ECDSA verify, fees, maturity
- **CB-rules (CB1-CB10)**: Coinbase — output order, exact subsidy split, constitutional addresses

### PoW system (two layers)

1. **ConvergenceX** (`include/sost/pow/convergencex.h`) — CPU-friendly gradient descent over random 32x32 matrix. Mining requires ~8GB RAM total (4GB dataset + 4GB scratchpad); node validation requires only ~500MB (no dataset/scratchpad). ASIC-resistant. Checkpoint merkle tree for verification.
2. **cASERT** (`include/sost/pow/casert.h`) — Unified consensus-rate control system combining three integrated components: bitsQ Q16.16 primary hardness regulator, 17 equalizer profiles (E4 through H9, H10-H12 reserved for future), CASERT_H_MIN=-4, CASERT_H_MAX=9, slew rate limit (±1 level per block), and zone-based anti-stall recovery. **V1 (blocks <1450): 48h halflife, 6.25% delta cap. V2 (blocks >=1450): 24h halflife, 12.5% delta cap.**

Difficulty encoded as bitsQ Q16.16 fixed-point (`include/sost/sostcompact.h`).

### Key subsystems

- **Capsule Protocol v1** (`include/sost/capsule.h`) — Binary metadata in tx outputs (12-byte header + up to 243-byte body). Activates at height 5000 (mainnet).
- **UTXO Set** (`include/sost/utxo_set.h`) — In-memory, OutPoint-indexed. ConnectBlock/DisconnectBlock with undo entries for reorg.
- **Mempool** (`include/sost/mempool.h`) — Fee-rate indexed (rational arithmetic, no floats). BuildBlockTemplate selects by fee-rate. RBF (full Replace-by-Fee) and CPFP (BuildBlockTemplateCPFP) for dynamic fee market.
- **Emission** (`include/sost/emission.h`, `subsidy.h`) — Smooth exponential decay, q=e^(-1/4), epoch=131553 blocks (~2.5 years). Max supply ~4.669M SOST.
- **Crypto** — SHA256 via OpenSSL, ECDSA secp256k1 via libsecp256k1, LOW-S enforced.
- **Address** (`include/sost/address.h`) — Format: `sost1` + 40 hex chars (20-byte pubkey hash). Script hash: `sost3` + 40 hex chars (20-byte HASH160 of redeemScript).
- **HD Wallet** (`include/sost/hd_wallet.h`) — BIP39 seed phrases (12 words), PBKDF2-HMAC-SHA512 seed derivation. Compatible with web wallet.
- **PSBT** (`include/sost/psbt.h`) — SOST-PSBT offline signing format (JSON + base64). Supports P2PKH and multisig inputs.
- **Script Engine** (`include/sost/script.h`) — Minimal opcodes: OP_CHECKSIG, OP_CHECKMULTISIG, OP_HASH160, OP_EQUAL, etc. P2SH (redeemScript-hash) for multisig. MULTISIG_ACTIVATION_HEIGHT = 2000.
- **Address Book** (`include/sost/addressbook.h`) — Trusted address management with 4 trust levels.
- **Wallet Policy** (`include/sost/wallet_policy.h`) — Treasury safety: daily limits, per-TX limits, vault mode.

### Key constants (in `include/sost/params.h`)

- STOCKS_PER_SOST: 100,000,000 (1e-8 precision)
- COINBASE_MATURITY: 1000 blocks (~7 days)
- TARGET_SPACING: 600 seconds (10 min)
- BLOCKS_PER_EPOCH: 131,553
- GENESIS_REWARD: 785,100,863 stocks (7.85100863 SOST)
- MAX_TX_BYTES: 100,000 (consensus), 16,000 (policy)
- MAX_BLOCK_BYTES: 1,000,000
- MIN_RELAY_FEE: 1 stock/byte

### Source layout

- `include/sost/` — All public headers; `include/sost/pow/` for PoW subsystem
- `src/` — Implementation files; `src/pow/` for PoW; entry points: `sost-node.cpp`, `sost-miner.cpp`, `sost-cli.cpp`, `sost-rpc.cpp`
- `tests/` — Test files (chunk1/2 = legacy integration tests, rest = per-module)
- `deploy/` — systemd services, nginx config, VPS setup script, monitoring
- `docs/` — Design docs (capsule spec, TX design, ConvergenceX whitepaper)
- `explorer.html` — Standalone block explorer (connects to node RPC)

## Important conventions

- All monetary values are in **stocks** (integer i64), never floating-point. 1 SOST = 100,000,000 stocks.
- Fee calculations use rational arithmetic (fee/size as integer ratio) to avoid float consensus bugs.
- Constitutional addresses (Gold Vault, PoPC Pool) are immutable — defined in `params.h`.
- Coinbase output order is fixed: [0]=miner, [1]=gold, [2]=popc (validated by CB rules).
- The `main_node.cpp`, `main_miner.cpp`, `main_wallet.cpp` files are legacy entry points — the active binaries are `sost-node.cpp`, `sost-miner.cpp`, `sost-cli.cpp`.
- Some CMakeLists.txt targets are commented out (chunk4/6/7 tests, old binaries) — these use the old Block API.

## GeaSpirit Platform (Mineral Intelligence)

Located in `geaspirit/`. Python-based satellite mineral prospectivity mapping.

**Current state (Phase 9):**
- Multi-source exploration intelligence platform (not satellite-only)
- 6 supervised zones: Kalgoorlie (0.877 AUC), Chuquicamata (0.862), Peru (0.758), Arizona (0.718), Zambia (0.758), Pilbara (FAILED)
- Phase 9 information fusion: neighborhood context + hydrology + magnetics + isotonic calibration
- Kalgoorlie 0.8654 → 0.8770 (+0.012 AUC), Zambia 0.7366 → 0.7584 (+0.022 AUC)
- Neighborhood context multi-zone validated (generalized to Zambia)
- Isotonic calibration: all Brier scores below 0.17, Kalgoorlie 0.0999
- Canonical objective: 23.7/40 (59%). Mineral 3.3/10, Depth 4.1/10, Coords 7/10, Certainty 9.3/10
- Type-aware auto-selection: tests all families, selects best per zone
- Validated: satellite baseline (universal), thermal 20yr (modest), EMIT (porphyry-specific), PCA embeddings (Kalgoorlie-specific), magnetics (+0.009 real), neighborhood context (multi-zone validated)
- Rejected: spatial gradients, ML residuals, EMIT at orogenic Au, cross-zone transfer
- tpi_heterogeneity d=+0.878 = strongest single feature ever found
- Critical fix: Phase 7 magnetics were EMPTY (wrong tiles). Fixed with GA national TMI via NCI THREDDS
- Peru EMIT: blocked (truncated download), 50 granules available
- Blockers: Peru EMIT, GSWA geology maps, GA gravity, detailed AEM
- Scripts in `geaspirit/scripts/`, data in `~/SOST/geaspirit/data/`
- See: docs/GEASPIRIT_TECHNOLOGY_SUMMARY.md, docs/GEASPIRIT_CTO_NEXT_PHASE.md, docs/GEASPIRIT_FRONTIER_RESEARCH_V5.md (extended with CTO sprint findings + 13 sections)

## Materials Engine

Located in `materials-engine/`. Python-based computational materials discovery.

**Current state (v3.2.0):**
- 76,193 materials, 70+ API endpoints
- CGCNN formation energy (MAE 0.1528), ALIGNN-Lite band gap (MAE 0.3422)
- Material Mixer MVP: generates theoretical candidates from parent pairs
- Autonomous Discovery Engine: iterative candidate generation with error learning
- 22 elemental + 22 compound curated overrides
- Multilingual search (9 languages, 270+ common names)

## GeaSpirit Status

Located in `/home/sost/SOST/geaspirit/`. Multi-source exploration intelligence platform.

**Phase history:** Thermal V2 (confirmed d=-0.68) → Phase 5I (multi-zone thermal) → Phase 6A-6E (EMIT, PCA, gradients, type-aware selection, universal matrix) → Phase 7 (magnetics, embeddings) → CTO Sprint (multi-scale anomaly, neighborhood context) → Phase 8B (public sync, canonical assessment) → Phase 9 (information fusion: neighborhood + hydrology + magnetics + calibration).

**Selected families by zone (Phase 9):**
- Kalgoorlie: satellite + thermal + PCA + magnetics + neighborhood + hydrology → AUC 0.877
- Chuquicamata: satellite + thermal + EMIT → AUC 0.862
- Peru/Arizona: satellite + thermal → AUC 0.698/0.718
- Zambia: satellite + neighborhood + hydrology → AUC 0.758

**Canonical objective: 23.7/40 (59%).** Mineral 3.3/10, Depth 4.1/10, Coords 7/10, Certainty 9.3/10.
**Key insight:** The gap to 10/10 is a DATA problem (geology, geophysics, drill holes), not ML.
**Phase 9 result:** Neighborhood context + hydrology + magnetics fusion + isotonic calibration. Kalgoorlie +0.012, Zambia +0.022 AUC. Multi-zone validated.
**Full docs:** GEASPIRIT_TECHNOLOGY_SUMMARY.md, GEASPIRIT_CTO_NEXT_PHASE.md, GEASPIRIT_CANONICAL_PATH.md

**Language guardrails:**
- ALWAYS say: "thermal long-term proxy family", "moderate but real improvement"
- NEVER say: "direct subsurface detection", "detect minerals at depth", "nobody has published this"
- Thermal helps but does not dominate satellite spectral indices
- Thermal adds less where spectral/SAR baseline already saturates

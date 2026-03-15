# Synchronization and Verification in SOST vs Bitcoin vs Monero (RandomX)

## How SOST Node Synchronization Works Today

When a SOST node starts:

1. **Load local chain** from `chain.json` (genesis + all blocks with full transaction hex).
2. **Connect to peers** via P2P (port 19333). Exchange VERS messages (height + genesis hash).
3. **Request missing blocks** via GETB from the peer with highest height.
4. **For each received block**, validate:
   - L1: Structure (size ≤ 1MB, tx count, coinbase at tx[0], merkle root)
   - L2: Header context (prev_hash links, height, timestamp > MTP(11), timestamp ≤ now+600s, bitsQ matches cASERT)
   - L3: Transactions (R1-R14 structural, S1-S12 spend/signature, CB1-CB10 coinbase split)
   - L4: UTXO connect (atomic spend/create with BlockUndo for reorgs)
   - PoW: `commit <= target(bitsQ)` + `verify_cx_proof()` (merkle root of 16 checkpoint leaves, commit hash binding, stability basin on x_bytes)
5. **Accept block** into chain, index transactions, update UTXO set.
6. **Propagate** valid blocks to other peers via BLCK messages.

### What the node verifies per block

- Block structure and merkle root integrity
- Chain linkage (prev_hash, height)
- Timestamp rules (MTP, future drift)
- cASERT difficulty match
- ConvergenceX proof (commit hash, checkpoint merkle, stability basin) — ~1ms
- `commit <= target` inequality
- All transaction signatures (ECDSA secp256k1, LOW-S)
- Coinbase split (50/25/25 to miner/gold/popc)
- UTXO validity (no double spends, maturity)

### What the node does NOT need

- The 4GB dataset (only needed for mining)
- The 4GB scratchpad (only needed for mining)
- Full 100K-round gradient descent recomputation (verified via compact proof)

### What the miner verifies

The miner trusts the node for chain state and focuses on:
- Fetching block template via RPC (`getblocktemplate`)
- Running ConvergenceX: 100K gradient descent rounds with 4GB dataset + 4GB scratchpad
- Finding commit <= target with stable basin
- Submitting block with full proof data (x_bytes, final_state, checkpoint_leaves)

## Comparison Table

| Aspect | Bitcoin | Monero (RandomX) | SOST (ConvergenceX) |
|--------|---------|-------------------|---------------------|
| **PoW algorithm** | SHA256d (double SHA-256) | RandomX (random program execution) | ConvergenceX (gradient descent + stability basin) |
| **Mining hardware** | ASICs dominant | CPU-optimized (anti-ASIC) | CPU-optimized (8GB memory-hard) |
| **Mining memory** | Negligible | ~2GB (RandomX dataset) | ~8GB (4GB dataset + 4GB scratchpad) |
| **Node verification memory** | Negligible | ~2GB (must build RandomX dataset to verify) | **~500MB (no dataset/scratchpad needed)** |
| **Verification method** | Recompute SHA256d hash (trivial) | **Recompute full RandomX program** | Compact proof: commit hash + checkpoint merkle + stability basin (~1ms) |
| **Verification cost per block** | ~1μs (one SHA256d) | ~50-200ms (full RandomX execution) | ~1ms (SHA256 + 16 gradient steps) |
| **Block sync cost (1000 blocks)** | ~1ms total PoW | ~50-200 seconds PoW | ~1 second PoW |
| **Difficulty adjustment** | Every 2016 blocks (~2 weeks) | Every block (LWMA) | Every block (cASERT, 12h half-life) |
| **Node needs heavy dataset?** | No | **Yes** (~2GB RandomX dataset for verification) | **No** (verification is dataset-free) |
| **Proof data in block** | 80-byte header | 80-byte header | Header + x_bytes (128B) + final_state (32B) + 16 checkpoint leaves (512B) |

## Security Trade-offs

### Bitcoin
- **Strongest property**: Verification is trivially cheap (one hash).
- **Weakness**: ASIC-dominated mining concentrates hashpower.

### Monero (RandomX)
- **Strongest property**: Full recomputation at verification = no shortcuts possible.
- **Weakness**: Verification is expensive (~200ms per block). New nodes must build a 2GB dataset to verify ANY block. Sync is slow.

### SOST (ConvergenceX)
- **Strongest property**: Compact verification (~1ms) without heavy memory. Node can run on a 4GB VPS. Mining is genuinely memory-hard (8GB).
- **Trade-off**: Verification relies on cryptographic binding (commit hash + checkpoint merkle + stability basin) rather than full recomputation. This is sound because:
  - Forging checkpoint leaves requires SHA256 preimage attacks
  - Forging x_bytes that passes stability requires solving the optimization problem
  - The commit hash binds all components cryptographically
  - The 5-layer verification catches any inconsistency
- **Open question**: Unlike Bitcoin's single-hash verification or Monero's full recomputation, SOST uses a hybrid compact proof model. This is a deliberate design choice that trades full recomputation for lightweight verification with cryptographic guarantees.

## Summary

SOST achieves a unique position: mining is as memory-hard as Monero (actually harder at 8GB vs 2GB), but verification is nearly as cheap as Bitcoin. This enables running full nodes on modest VPS hardware (4GB RAM) while maintaining ASIC resistance at the mining layer. The compact proof model (checkpoint merkle + commit binding + stability verification) provides cryptographic assurance without requiring verifiers to possess the mining dataset.

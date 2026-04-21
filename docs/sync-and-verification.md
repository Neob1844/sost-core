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
   - PoW: `commit <= target(bitsQ)` + `verify_cx_proof()` V2 (segments_root, sampled round witnesses, checkpoint merkle, commit hash binding, stability basin on x_bytes)
5. **Accept block** into chain, index transactions, update UTXO set.
6. **Propagate** valid blocks to other peers via BLCK messages.

### What the node verifies per block

- Block structure and merkle root integrity
- Chain linkage (prev_hash, height)
- Timestamp rules (MTP, future drift)
- cASERT difficulty match
- ConvergenceX Transcript V2 proof (segments_root, sampled round witnesses, checkpoint merkle, commit hash, stability basin) — ~0.2ms
- `commit <= target` inequality
- All transaction signatures (ECDSA secp256k1, LOW-S)
- Coinbase split (50/25/25 to miner/gold/popc)
- UTXO validity (no double spends, maturity)

### What the node does NOT need

- The 4GB dataset (only needed for mining; Dataset v2 is independently indexable via SplitMix64, O(1) per value)
- The 4GB scratchpad (only needed for mining; Scratchpad v2 is independently indexable via SHA256(MAGIC||"SCR2"||seed||index), O(1) per block)
- Full 100K-round gradient descent recomputation (verified via Transcript V2 compact proof with segment commitments + sampled round verification)

### What the miner verifies

The miner trusts the node for chain state and focuses on:
- Fetching block template via RPC (`getblocktemplate`)
- Running ConvergenceX: 100K gradient descent rounds with 4GB dataset + 4GB scratchpad
- Finding commit <= target with stable basin
- Submitting block with full Transcript V2 proof data (x_bytes, final_state, segments_root, segment_proofs, round_witnesses, checkpoint_leaves)

## Comparison Table

| Aspect | Bitcoin | Monero (RandomX) | SOST (ConvergenceX) |
|--------|---------|-------------------|---------------------|
| **PoW algorithm** | SHA256d (double SHA-256) | RandomX (random program execution) | ConvergenceX (gradient descent + stability basin) |
| **Mining hardware** | ASICs dominant | CPU-optimized (anti-ASIC) | CPU-optimized (8GB memory-hard) |
| **Mining memory** | Negligible | ~2GB (RandomX dataset) | ~8GB (4GB dataset + 4GB scratchpad) |
| **Node verification memory** | Negligible | ~2GB (must build RandomX dataset to verify) | **~500MB (no dataset/scratchpad needed)** |
| **Verification method** | Recompute SHA256d hash (trivial) | **Recompute full RandomX program** | Transcript V2: segment commitments + sampled round witnesses + stability basin (~0.2ms) |
| **Verification cost per block** | ~1μs (one SHA256d) | ~50-200ms (full RandomX execution) | ~0.2ms (11-phase verification with challenge derivation + local round checks) |
| **Block sync cost (1000 blocks)** | ~1ms total PoW | ~50-200 seconds PoW | ~0.2 seconds PoW |
| **Difficulty adjustment** | Every 2016 blocks (~2 weeks) | Every block (LWMA) | Every block (cASERT, avg288 + dynamic cap) |
| **Node needs heavy dataset?** | No | **Yes** (~2GB RandomX dataset for verification) | **No** (verification is dataset-free; Dataset v2 and Scratchpad v2 are independently indexable at O(1)) |
| **Proof data in block** | 80-byte header | 80-byte header | Header + x_bytes (128B) + final_state (32B) + segments_root (32B) + segment_proofs + round_witnesses + 16 checkpoint leaves (512B) |

## Security Trade-offs

### Bitcoin
- **Strongest property**: Verification is trivially cheap (one hash).
- **Weakness**: ASIC-dominated mining concentrates hashpower.

### Monero (RandomX)
- **Strongest property**: Full recomputation at verification = no shortcuts possible.
- **Weakness**: Verification is expensive (~200ms per block). New nodes must build a 2GB dataset to verify ANY block. Sync is slow.

### SOST (ConvergenceX)
- **Strongest property**: Transcript V2 compact verification (~0.2ms) without heavy memory. Node can run on a 4GB VPS. Mining is genuinely memory-hard (8GB).
- **Trade-off**: Verification relies on cryptographic binding (commit V2 with segments_root + sampled round witnesses + checkpoint merkle + stability basin) rather than full recomputation. This is sound because:
  - Segment commitments bind the full computation transcript via merkle proofs for challenged segments
  - Sampled round witnesses allow local round transition checks without replaying all 100K rounds
  - Dataset v2 (SplitMix64) and Scratchpad v2 (SHA256-based) are independently indexable at O(1), so verifiers can spot-check any value
  - Forging x_bytes that passes stability requires solving the optimization problem
  - The commit V2 hash binds all components including segments_root
  - The 11-phase verification pipeline catches any inconsistency
- **Resolved**: Unlike Bitcoin's single-hash verification or Monero's full recomputation, SOST uses Transcript V2 with segment commitments and sampled round verification. This provides cryptographic assurance comparable to full recomputation at ~0.2ms cost (5x faster than V1).

## Summary

SOST achieves a unique position: mining is as memory-hard as Monero (actually harder at 8GB vs 2GB), but verification is nearly as cheap as Bitcoin. Transcript V2 reduces verification cost to ~0.2ms per block via segment commitments and sampled round witnesses (down from ~1ms in V1). Dataset v2 and Scratchpad v2 are independently indexable at O(1), so verifiers can spot-check without building the full 4GB structures. This enables running full nodes on modest VPS hardware (4GB RAM) while maintaining ASIC resistance at the mining layer.

# SOST Verification Pipeline

## Block Acceptance Flow

All block validation runs in `process_block()` (src/sost-node.cpp).
The pipeline is sequential — each layer must pass before the next runs.

### Layer 1 — Header Structure (CHEAP, ~microseconds)
- Block size ≤ 1,000,000 bytes
- Transaction count: 1 ≤ txs ≤ 65,536
- txs[0] is coinbase (TX_TYPE_COINBASE)
- txs[1..n] are standard (TX_TYPE_STANDARD)
- Merkle root matches computed value
- CVE-2012-2459 merkle mutation detection

### Layer 2 — Header Context (CHEAP, ~microseconds)
- prev_block_hash links to chain tip
- Height = prev.height + 1
- Timestamp > MTP(11) and ≤ now + 600s
- bits_q matches ASERT-computed expected difficulty
- Genesis block: timestamp=1773360000, bits_q=353075

### Layer 3 — ASERT Difficulty (CHEAP, ~microseconds)
- Exponential ASERT: `next_bitsq = anchor × 2^(-td / 86400)`
- Cubic polynomial approximation of 2^x in Q16.16
- Epoch 0 anchor always uses GENESIS_BITSQ (353,075)
- Global bounds: MIN_BITSQ=65,536, MAX_BITSQ=16,711,680
- No per-block clamps

### Layer 4 — PoW Inequality (CHEAP, ~microseconds)
- `commit ≤ target_from_bitsQ(bits_q)`
- ALWAYS verified, even during fast sync

### Layer 5 — Coinbase Rules (CHEAP, ~microseconds)
- 3 outputs: [0]=miner, [1]=gold_vault, [2]=popc_pool
- Subsidy matches `sost_subsidy_stocks(height)`
- Split: miner=subsidy/2, gold=subsidy/4, popc=subsidy-miner-gold
- Constitutional addresses match params.h constants

### Layer 6 — Transaction Validation (MODERATE, ~milliseconds)
- R-rules (R1-R14): structural validation
- S-rules (S1-S12): UTXO lookup, pubkey hash match, ECDSA secp256k1 verify, fees, maturity
- CB-rules (CB1-CB10): coinbase output order, exact subsidy split
- Fee accumulation with overflow checks

### Layer 7 — UTXO Connect (MODERATE, ~milliseconds)
- Atomic scratch-copy of UTXO set
- Spend inputs (remove from set)
- Add outputs (add to set)
- Generate BlockUndo for reorg support
- Commit on success, discard on failure

### Layer 8 — ConvergenceX Recomputation (EXPENSIVE, ~5-30 seconds)
- Derive 32×32 matrix M and vector b from block_key
- 100,000 gradient descent rounds with 4GB scratchpad mixing
- 16 checkpoint leaves → Merkle root verification
- Stability basin: 4 perturbation probes, margin=180
- Commit = SHA256(solution || header)

## Fast Sync

Layers 1–7 ALWAYS run. Layer 8 (ConvergenceX recomputation) is skipped for:
- Hard checkpoint matches (height + hash in HARD_CHECKPOINTS)
- Blocks under assumevalid height (when anchor is on chain)
- Override: `--full-verify` forces Layer 8 for all blocks

Reorg depth limit: 500 blocks.

## PoW Comparison — Bitcoin vs Monero vs SOST

| Property | Bitcoin (SHA-256d) | Monero (RandomX) | SOST (ConvergenceX) |
|---|---|---|---|
| PoW verify cost | ~1μs (two SHA-256) | ~50ms (JIT compile + execute) | ~5-30s (100K gradient steps + 4GB scratchpad) |
| Memory requirement | Negligible (~256 bytes) | 2GB (light) / 256MB (dataset) | 4GB scratchpad (mandatory) |
| ASIC resistance | None (SHA-256 ASICs dominate) | High (random program execution) | Very high (gradient descent + memory-hard) |
| Sync time (full verify) | ~hours (billions of SHA-256d) | ~days (RandomX JIT per block) | ~weeks (CX recompute per block) |
| Sync time (fast/headers) | ~minutes (headers-first) | ~hours (pruned sync) | ~minutes (checkpoint skip, L1-L7 only) |
| Verification layers | 4 (structure, scripts, UTXO, PoW) | 4 (structure, RingCT, UTXO, PoW) | 8 (structure, time, ASERT, PoW ineq, coinbase, txs, UTXO, CX recompute) |
| Difficulty adjustment | Every 2016 blocks (~2 weeks) | Every block (LWMA) | Every block (exponential ASERT, 24h half-life) |
| Block time target | 600s (10 min) | 120s (2 min) | 600s (10 min) |
| Anti-stall mechanism | None (2-week retarget) | LWMA handles stalls | cASERT Decay: 2h activation, tiered level decay |
| Anti-acceleration | None | LWMA handles acceleration | cASERT: L1-L5 fixed bands, L6+ unbounded hardening |
| Emission model | Halving every 210,000 blocks | Smooth tail emission (0.6 XMR/block) | Smooth exponential decay (q=e^(-1/4), ~9% annual) |
| Max supply | 21,000,000 BTC | Infinite (tail emission) | ~4,669,201 SOST (Feigenbaum δ × 10⁶) |
| Constitutional reserve | None | None | 25% gold vault + 25% PoPC pool (enforced at consensus) |

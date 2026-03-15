# SOST Protocol — Changelog

## v1.1.0 — Transcript V2 (Pre-Launch)

### ConvergenceX Transcript V2
- ConvergenceX now uses Transcript V2 with segment commitments + sampled round verification
- Dataset v2: independently indexable via SplitMix64 (O(1) per value, no full 4GB needed for verification)
- Scratchpad v2: independently indexable via SHA256(MAGIC||"SCR2"||seed||index) (O(1) per block)
- Block now includes: segments_root, segment_proofs (merkle proofs for challenged segments), round_witnesses
- Commit V2 format: includes segments_root in hash preimage
- verify_cx_proof V2: 11-phase verification pipeline, ~0.2ms (vs ~1ms in V1)

### New Genesis Block (Transcript V2)
- block_id: `a9547840f1daf5c0de8f2a2b2184dac82657be75e9d436f997097888af6b5164`
- commit: `0006fea7dc5625b5718851be426516dcb8c97d96041d7d7ffba5dd2165aa544e`
- segments_root: `6614cbf6c64d03e15a0369e5217f0fb8c68c855a8a3d0efa378e5f88da29b0d5`
- checkpoints_root: `3fdb1f5e336b540602e81aa6d16e0888c947b7676cd125efa33c2b3ec448d7cc`
- nonce: 3288, stability_metric: 83
- timestamp: 1773597600, bitsQ: 765730 (unchanged)

---

## v1.0.0 — June 16, 2026 (Public Launch)

### Genesis
- Mainnet genesis block: `a9547840f1daf5c0de8f2a2b2184dac82657be75e9d436f997097888af6b5164`
- Genesis timestamp: 2026-03-15 18:00:00 UTC
- Initial block reward: 7.85100863 SOST (785,100,863 stocks)
- Coinbase split: 50% miner / 25% Gold Vault / 25% PoPC Pool

### Node (sost-node v0.3.2)
- Full P2P networking on port 19333
- JSON-RPC server on port 18232 with 17 methods
- RPC authentication via `--rpc-user` / `--rpc-pass` flags
- UTXO set management with wallet rescan on startup
- Mempool with relay fee enforcement (minimum 1,000 stocks)
- Block size limit: 500KB
- Chain auto-save every 30 seconds
- Fixed: ACTIVE_PROFILE mismatch bug (v0.3.1)

### Miner (sost-miner v0.5)
- ConvergenceX PoW with 4GB RAM requirement
- RPC mode: fetches mempool via `getblocktemplate`, submits via `submitblock`
- Fee distribution across coinbase outputs
- Multi-threaded mining support

### CLI Wallet (sost-cli v1.3)
- Dynamic fee calculation based on transaction size (1 stock/byte default)
- Coinbase maturity filter: 100 confirmations required
- Detailed error messages distinguishing immature vs insufficient funds
- Commands: newwallet, getnewaddress, listaddresses, send, getbalance, listunspent, info
- Fixed: change address now returns to sender (not destination)
- Fixed: fee displayed in SOST, not stocks (v1.2 bug)

### Consensus
- Transaction validation: 42 rules (R1-R14, S1-S12, CB1-CB10), all passing
- Block validation: 4 layers (L1 structure, L2 header, L3 consensus, L4 UTXO)
- cASERT unified difficulty system: bitsQ Q16.16 primary (12h half-life, 6.25% delta cap) + equalizer profiles (E3-H6) + anti-stall
  - L2 (light): 5-25 blocks ahead, scale=2
  - L3 (moderate): 26-50 blocks ahead, scale=3
  - L4 (strong): 51-75 blocks ahead, scale=4
  - L5 (severe): 76-100 blocks ahead, scale=5
  - L6+ (unbounded): 101+ blocks ahead, level = 6 + floor((ahead-101)/50), scale=level
- Constants: CASERT_L2_BLOCKS=5, L3=26, L4=51, L5=76, L6=101
- Fixed parameters: k=4, steps=4, margin=180
- Decay anti-stall: activates at 7200s (2h), tiered recovery (L8+ 10min, L4-L7 20min, L2-L3 30min)

### Cryptography
- Transaction signing: libsecp256k1 (migrated from OpenSSL EC_KEY)
- ECDSA secp256k1 with LOW-S normalization
- Address format: `sost1` + 40 hex chars (RIPEMD160(SHA256(pubkey)))

### Explorer (v4.2)
- Dashboard: height, block time, supply, hashrate, mempool, countdown
- cASERT panel with L1-L5/L6+ color-coded display (unidirectional)
- Gold Reserves and PoPC Pool charts with real block-interval data
- Emission curve chart (12 epochs, interactive tooltip)
- Chain timing panel with expected vs actual blocks, lag display
- Address view with mature/immature balance, role tagging
- Smart search: height, hash, txid, sost1 address
- RPC authentication support
- SOST logo (red sigma) embedded
- Auto-refresh 10s with new block notification

### Documentation
- Whitepaper v3.6 with cASERT threshold correction + Appendix J errata
- README.md with correct versions, auth flags, fee documentation
- QUICKSTART.md with three-terminal architecture guide

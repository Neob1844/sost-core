# SOST Protocol — Changelog

## v1.0.0 — May 13, 2026 (Public Launch)

### Genesis
- Mainnet genesis block: `0a6c8e2b3b440ac69dcf8dbad9587cec99d1cbc4746017d1f6e6e3d73d02d793`
- Genesis timestamp: 2026-03-13 00:00:00 UTC
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
- ASERT difficulty adjustment with 24-hour half-life
- cASERT v3 unidirectional overlay:
  - L3 (neutral): 0-20 blocks ahead
  - L4 (light hardening): 21-50 blocks ahead
  - L5 (moderate): 51-100 blocks ahead
  - L6 (maximum): 101+ blocks ahead
- Operator: `<` (not `<=`) for threshold comparisons
- Constants: CASERT_L4_BLOCKS=21, L5=51, L6=101

### Cryptography
- Transaction signing: libsecp256k1 (migrated from OpenSSL EC_KEY)
- ECDSA secp256k1 with LOW-S normalization
- Address format: `sost1` + 40 hex chars (RIPEMD160(SHA256(pubkey)))

### Explorer (v4.2)
- Dashboard: height, block time, supply, hashrate, mempool, countdown
- cASERT panel with L3-L6 color-coded display (unidirectional)
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

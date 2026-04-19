# SOST Protocol — Consensus Feature Audit

**Date:** 2026-03-29
**Auditor:** NeoB
**Status:** ALL CONSENSUS FEATURES IMPLEMENTED

## Consensus Features Table

| Feature | Whitepaper | Consensus? | Implemented? | Tests? | Activation | Status |
|---------|-----------|------------|--------------|--------|------------|--------|
| ConvergenceX PoW | Section 3 | YES | YES | YES (chunk1, chunk2, transcript-v2) | Genesis | OK |
| cASERT v1 (48h halflife) | Section 3.12 | YES | YES | YES (casert) | Genesis | OK |
| cASERT v2 (24h halflife) | Section 3.12 | YES | YES | YES (casert) | Block 1450 | OK |
| 40 equalizer profiles E4-H35 | Section 3.12 | YES | YES | YES (casert) | Genesis | OK |
| Constitutional split 50/25/25 | Section 2 | YES | YES | YES (tx-validation, CB1-CB10) | Genesis | OK |
| Feigenbaum emission | Section 4 | YES | YES | YES (chunk1, chunk2) | Genesis | OK |
| UTXO-based transactions | Section 5 | YES | YES | YES (transaction, utxo-set) | Genesis | OK |
| R1-R14 structural rules | Section 5.2 | YES | YES | YES (tx-validation) | Genesis | OK |
| R15 BOND_LOCK payload (8 bytes) | Section 6 | YES | YES | YES (bond-lock) | Block 5000 | OK |
| R16 ESCROW_LOCK payload (28 bytes) | Section 6 | YES | YES | YES (bond-lock) | Block 5000 | OK |
| S1-S12 spend rules | Section 5.3 | YES | YES | YES (tx-validation) | Genesis | OK |
| S11 BOND/ESCROW time-lock | Section 6 | YES | YES | YES (bond-lock) | Block 5000 | OK |
| CB1-CB10 coinbase rules | Section 5.4 | YES | YES | YES (tx-validation) | Genesis | OK |
| BOND_LOCK (0x10) | Section 6.4 | YES | YES | YES (bond-lock) | Block 5000 | OK |
| ESCROW_LOCK (0x11) | Section 6.8 | YES | YES | YES (bond-lock) | Block 5000 | OK |
| Capsule Protocol v1 | Section 7 | YES | YES | YES (capsule) | Block 5000 | OK |
| Multisig P2SH (sost3) | Section 5.6 | YES | YES | YES (multisig) | Block 2000 | OK |
| Hard checkpoints | Section 8 | YES | YES | YES (checkpoints) | Genesis | OK |
| COINBASE_MATURITY = 1000 | Section 2.3 | YES | YES | YES (tx-validation) | Genesis | OK |
| MAX_BLOCK_BYTES = 1MB | Section 2.3 | YES | YES | YES (block_validation) | Genesis | OK |
| Block validation L1-L4 | Section 8 | YES | YES | YES (reorg, merkle-block) | Genesis | OK |

## Application-Layer Features (NOT consensus)

| Feature | Whitepaper | Consensus? | Implemented? | Tests? | Notes |
|---------|-----------|------------|--------------|--------|-------|
| PoPC Registry (Model A) | Section 6 | NO | YES | YES (popc, popc-tx) | 5 RPC commands |
| PoPC Model B (Escrow) | Section 6.8 | NO | YES | YES (escrow) | 4 RPC commands |
| Bond sizing table | Section 6.5 | NO | YES | YES (popc) | Operational |
| Reward calculation | Section 6.6 | NO | YES | YES (popc) | 1-20% base × 6 dynamic tiers |
| Reputation system | Section 6.7 | NO | YES | YES (popc) | 0/1/3/5 stars |
| Audit entropy | Section 6.3 | NO | YES | YES (popc) | SHA256-based |
| Etherscan checker | Section 6 | NO | YES (Python) | Manual | scripts/popc_etherscan_checker.py |
| HD Wallet (BIP39) | Section 9 | NO | YES | YES (hd-wallet) | 12-word seeds |
| PSBT offline signing | Section 9 | NO | YES | YES (psbt) | JSON + base64 |
| RBF + CPFP | Section 5.5 | NO | YES | YES (rbf, cpfp) | Fee market |
| Address Book | — | NO | YES | YES (addressbook) | 4 trust levels |
| Wallet Policy | — | NO | YES | YES (wallet-policy) | Limits |
| Mempool | Section 5.5 | NO | YES | YES (mempool) | Fee-rate indexed |

## Verdict

**ALL consensus features from the whitepaper are implemented and tested.**

No consensus changes are pending. The following features activate at their designated heights:
- Block 2000: Multisig P2SH (sost3 addresses)
- Block 5000: BOND_LOCK, ESCROW_LOCK, Capsule Protocol v1

Current chain height: ~1900. All activation heights are ahead of the chain — features will activate automatically when the chain reaches the designated height.

## What Does NOT Require Consensus

The whitepaper explicitly states: "No consensus changes. All PoPC logic remains operational/application-layer except that the PoPC Pool receives 25% coinbase by consensus."

This means:
- PoPC registration, rewards, slashing → application layer (implemented)
- Model B escrow → application layer (implemented)
- Etherscan verification → external tool (implemented)
- Pricing oracle → future, not consensus
- Reputation → application layer (implemented)

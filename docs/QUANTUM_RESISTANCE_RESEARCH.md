# Quantum Resistance Research — SOST Protocol

## The Threat

Quantum computers running Shor's algorithm can break ECDSA (secp256k1) — the signature scheme SOST uses. A sufficiently powerful quantum computer could:
- Derive private keys from public keys
- Forge transaction signatures
- Steal funds from any address whose public key has been exposed (by spending from it)

**Timeline estimate:** 10-20 years for cryptographically relevant quantum computers (2035-2045). But migration must start NOW because blockchain data is permanent — an attacker could store signed transactions today and break them later.

**SHA-256 is safer:** Grover's algorithm only reduces security from 256 to 128 bits. Still considered secure.

## What Other Projects Do

### QRL (Quantum Resistant Ledger)
- **Algorithm:** XMSS (eXtended Merkle Signature Scheme) — hash-based, stateful
- **Layer:** All signatures (transactions, blocks)
- **Status:** LIVE since 2018 — first blockchain designed from scratch for PQC
- **Signature size:** ~2.5 KB (vs 64 bytes ECDSA)
- **Key size:** ~132 bytes public key
- **Drawback:** Stateful — must track which keys have been used. Complex wallet management.
- **Standard:** RFC 8391

### IOTA
- **Algorithm:** Winternitz One-Time Signatures (WOTS) in original; migrating to Ed25519 + considering PQC
- **Layer:** Transaction signatures
- **Status:** Original WOTS was quantum-resistant but one-time-use only. New Stardust uses Ed25519 (NOT quantum resistant). PQC research ongoing.
- **Note:** IOTA's original design forced address reuse prevention (each address used only once), which inherently protected against quantum attacks on exposed public keys.

### Hedera Hashgraph (HBAR)
- **Algorithm:** No PQC signatures yet. Uses Ed25519/ECDSA currently.
- **Layer:** Planning PQC migration
- **Status:** Research phase. Hedera has stated quantum resistance as a future goal but has not implemented it.
- **Note:** Hedera's BFT consensus is separate from signature security.

### Algorand
- **Algorithm:** Announced FALCON integration (lattice-based signatures, NIST selected)
- **Layer:** State proofs / cross-chain verification
- **Status:** FALCON used in state proofs since 2022. Not yet in regular transaction signatures.
- **Signature size:** FALCON-512: ~666 bytes; FALCON-1024: ~1,280 bytes
- **Note:** Algorand is the most advanced major blockchain in PQC deployment.

### Cardano
- **Algorithm:** No PQC implemented. Research papers published.
- **Status:** Charles Hoskinson has discussed quantum resistance. No timeline.
- **Note:** Cardano's extended UTXO model could facilitate migration.

### Ethereum
- **Algorithm:** No PQC implemented. EIP-7212 discusses hybrid signatures.
- **Status:** Vitalik Buterin has discussed account abstraction as the migration path.
- **Timeline:** Post-merge, pre-quantum migration is on the long-term roadmap.
- **Note:** Ethereum's account model makes migration harder than UTXO models.

## NIST Post-Quantum Standards (2024)

### CRYSTALS-Dilithium (FIPS 204) — RECOMMENDED FOR SOST
- **Type:** Lattice-based digital signatures
- **Security levels:** 2 (128-bit), 3 (192-bit), 5 (256-bit)
- **Signature size:** 2,420 bytes (level 2) — 38x larger than ECDSA (64 bytes)
- **Public key:** 1,312 bytes (level 2) — vs 33 bytes ECDSA compressed
- **Signing speed:** Fast (~0.5ms)
- **Verification speed:** Fast (~0.3ms)
- **Pros:** Fast, compact for PQC, well-studied, NIST winner
- **Cons:** Larger signatures increase TX size and blockchain bloat

### SPHINCS+ (FIPS 205)
- **Type:** Hash-based stateless signatures
- **Signature size:** 7,856-49,856 bytes — VERY large
- **Public key:** 32-64 bytes — small
- **Pros:** Conservative security assumptions (only relies on hash functions). Stateless.
- **Cons:** HUGE signatures. Not practical for blockchain transactions.

### FALCON (proposed FIPS 206)
- **Type:** Lattice-based (NTRU lattices)
- **Signature size:** 666 bytes (FALCON-512) — most compact PQC signature
- **Public key:** 897 bytes
- **Pros:** Smallest PQC signatures. Used by Algorand.
- **Cons:** Complex implementation. Floating-point arithmetic needed. Side-channel risks.

### CRYSTALS-Kyber (FIPS 203) — Key Encapsulation
- **Type:** Lattice-based key exchange
- **Not directly relevant** for transaction signatures, but useful for encrypted P2P communication.

## SOST Current Vulnerability

```
SOST uses:
  Signatures: ECDSA secp256k1 — VULNERABLE to Shor's algorithm
  Hashing: SHA-256 — Relatively safe (Grover reduces to 128-bit, still OK)
  Addresses: HASH160(pubkey) — Safe until first spend (pubkey exposed when signing)
```

**Critical moment:** When you SPEND from an address, your public key is revealed in the transaction. A quantum attacker could derive your private key from the public key and steal remaining funds. Addresses that have NEVER spent are safe (only hash is public).

## Recommendation for SOST

### Algorithm: CRYSTALS-Dilithium (Level 2)
- Best balance of security, speed, and signature size
- NIST winner (highest confidence)
- Already implemented in multiple libraries (liboqs, pqcrypto)
- 2,420 byte signatures are manageable for SOST's 100KB max TX size

### Alternative: FALCON-512
- Smaller signatures (666 bytes) — less blockchain bloat
- Used by Algorand (production-tested)
- More complex implementation
- Consider as backup if Dilithium signatures are too large

### NOT recommended:
- SPHINCS+ — signatures too large (8KB-50KB) for blockchain use
- XMSS — stateful, complex wallet management

## Implementation Plan

### Phase 1: Research (NOW — completed with this document)
- Document what others do ✓
- Select algorithm candidates ✓
- Assess impact on TX size and performance ✓

### Phase 2: Library Integration (3-6 months)
- Integrate liboqs (Open Quantum Safe) or pqcrypto library
- Implement Dilithium signing/verification alongside ECDSA
- Create PQC address format: `sost2` prefix (vs current `sost1` for ECDSA)
- Unit tests for PQC signatures

### Phase 3: Dual Signature Support (6-12 months)
- Protocol upgrade: accept both ECDSA (`sost1`) and Dilithium (`sost2`) signatures
- Nodes validate both types
- Wallets can generate PQC addresses
- Mining rewards can go to PQC addresses

### Phase 4: Migration Period (12-24 months)
- Encourage users to migrate funds from `sost1` to `sost2` addresses
- New wallets default to PQC addresses
- Display warnings for ECDSA addresses

### Phase 5: ECDSA Deprecation (24-36 months, or when quantum threat is imminent)
- Set a block height after which new ECDSA signatures are rejected
- Existing ECDSA UTXOs can still be spent (to allow migration)
- Eventually: only PQC signatures accepted

## Impact Assessment

| Metric | Current (ECDSA) | With Dilithium | Factor |
|---|---|---|---|
| Signature size | 64 bytes | 2,420 bytes | 38x |
| Public key | 33 bytes | 1,312 bytes | 40x |
| Average TX size | ~250 bytes | ~4,000 bytes | 16x |
| MAX_BLOCK_BYTES | 1,000,000 | May need increase | TBD |
| TXs per block | ~4,000 | ~250 | 16x fewer |
| Signing speed | ~0.1ms | ~0.5ms | 5x slower |
| Verification speed | ~0.1ms | ~0.3ms | 3x slower |
| Address format | sost1... (40 hex) | sost2... (longer) | TBD |

**The main cost is TX size.** With Dilithium, each transaction is ~16x larger. This means fewer transactions per block, or the block size limit needs to increase.

## Timeline

| When | What | Priority |
|---|---|---|
| 2026 Q2 | This research document | DONE |
| 2026 Q3-Q4 | liboqs integration, prototype | Medium |
| 2027 Q1-Q2 | Dual signature testnet | Medium |
| 2027 Q3-Q4 | Mainnet dual signature activation | High |
| 2028+ | Migration period | High |
| 2030+ | ECDSA deprecation (if quantum threat materializes) | Critical |

## References

- NIST PQC Standards: https://csrc.nist.gov/projects/post-quantum-cryptography
- CRYSTALS-Dilithium: https://pq-crystals.org/dilithium/
- FALCON: https://falcon-sign.info/
- Open Quantum Safe (liboqs): https://openquantumsafe.org/
- QRL Technical Docs: https://docs.theqrl.org/
- Algorand State Proofs (FALCON): https://developer.algorand.org/docs/get-details/stateproofs/
- Bitcoin PQC Discussion: https://github.com/bitcoin/bips/wiki/Post-Quantum-Cryptography

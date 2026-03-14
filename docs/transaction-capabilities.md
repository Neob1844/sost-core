# SOST Transaction Capabilities

## 1. Current State

SOST uses a UTXO-based transaction model with fixed output types — no scripting engine.

### What SOST Can Do Today

| Capability | Status | Details |
|---|---|---|
| **P2PKH payments** | FULL | Single-key ECDSA secp256k1, compressed pubkeys, LOW-S enforced |
| **Multiple inputs** | FULL | Up to 256 (consensus), 128 (policy) |
| **Multiple outputs** | FULL | Up to 256 (consensus), 32 (policy) |
| **Fee market** | FULL | Rational fee-rate ordering (fee/size, no floats), MIN_RELAY_FEE = 1 stock/byte |
| **Mempool** | FULL | Fee-rate indexed, double-spend detection, BuildBlockTemplate by fee priority |
| **Coinbase maturity** | FULL | 1000 blocks (~7 days) |
| **Dust prevention** | FULL | 10,000 stocks minimum output |
| **Timelocks (height-based)** | IMPLEMENTED | BOND_LOCK (lock until height N), activates at height 5000 |
| **Escrow locks** | IMPLEMENTED | ESCROW_LOCK (lock + beneficiary PKH), activates at height 5000 |
| **Metadata (Capsule v1)** | IMPLEMENTED | 12-byte header + up to 243-byte body in OUT_TRANSFER outputs, activates at height 5000 |
| **Reorg support** | FULL | BlockUndo with complete UTXO rollback |
| **Batch transactions** | FULL | Multiple inputs and outputs in single tx (coin selection in wallet) |

### Signing & Verification

- ECDSA secp256k1 with mandatory LOW-S (canonical signatures)
- BIP143-simplified sighash: `SHA256d(version || type || hashPrevouts || prevout || spent_info || hashOutputs || genesis_hash)`
- Sighash commits to genesis_hash (chain-specific replay protection)
- 64-byte compact signatures (r||s, no DER encoding)

### Consensus Limits

| Parameter | Value |
|---|---|
| MAX_BLOCK_BYTES | 1,000,000 (1 MB) |
| MAX_BLOCK_TXS | 65,536 |
| MAX_TX_BYTES (consensus) | 100,000 |
| MAX_TX_BYTES (policy) | 16,000 |
| MAX_PAYLOAD | 512 bytes/output |
| COINBASE_MATURITY | 1000 blocks |
| MIN_RELAY_FEE | 1 stock/byte |
| DUST_THRESHOLD | 10,000 stocks |

### Validation Pipeline

- **R-rules (R1-R14)**: Structural — version, types, counts, amounts, size, payload format
- **S-rules (S1-S12)**: Spend — UTXO lookup, pubkey hash match, ECDSA verify, fees, maturity, lock checks
- **CB-rules (CB1-CB10)**: Coinbase — exact 50/25/25 split, constitutional addresses, height encoding
- **P-rules (P1-P9)**: Policy — size limits, dust, relay fee, capsule validation

## 2. Comparison with Bitcoin

| Capability | Bitcoin | SOST |
|---|---|---|
| P2PKH payments | Yes | **Yes** — native output type |
| P2SH (pay-to-script-hash) | Yes | **No** — no script system |
| Multisig (M-of-N) | Yes (via script) | **No** — single-key only |
| Timelock (absolute) | Yes (CLTV) | **Yes** — BOND_LOCK (height-based, post-h5000) |
| Timelock (relative) | Yes (CSV) | **No** — only absolute height locks |
| Script language | Bitcoin Script (stack) | **None** — fixed output types |
| SegWit | Yes | **No** — not needed (no script witness) |
| Taproot/Schnorr | Yes | **No** — ECDSA only |
| OP_RETURN (data) | Yes (80 bytes) | **Capsule Protocol** (255 bytes, structured metadata) |
| Lightning compatible | Yes | **No** — requires HTLC scripts |
| Fee market | Yes (sat/vB) | **Yes** (stock/byte, rational arithmetic) |
| RBF (Replace-by-Fee) | Yes | **No** — not implemented |
| CPFP (Child-Pays-for-Parent) | Yes | **No** — not implemented |
| Batch transactions | Yes | **Yes** — multiple inputs/outputs |
| Coinbase maturity | 100 blocks | **1000 blocks** (~7 days) |
| Max block size | 4 MB weight | **1 MB** raw |
| Max tx/block | ~4000 | **65,536** (theoretical) |
| Replay protection | None (same chain) | **Yes** — genesis_hash in sighash |
| Signature malleability | Fixed (SegWit) | **Fixed** (LOW-S + compact format) |
| Constitutional reserve | None | **25% gold + 25% PoPC** (consensus-enforced) |

### Key Differences from Bitcoin

1. **No scripting engine**: SOST intentionally omits Bitcoin Script. Output types are consensus-defined, not programmable. This dramatically reduces attack surface but limits smart contract capability.

2. **Structured metadata**: Instead of OP_RETURN's opaque data, SOST uses Capsule Protocol v1 with typed headers, encryption flags, and template support. More structured than OP_RETURN but less flexible than arbitrary scripts.

3. **Built-in timelocks**: BOND_LOCK and ESCROW_LOCK are native output types, not script opcodes. They're simpler to validate but less composable.

4. **Longer coinbase maturity**: 1000 blocks vs Bitcoin's 100. More conservative, prevents spending coinbase during potential reorgs.

5. **Replay protection**: SOST commits the genesis hash into the sighash, providing chain-specific signatures. Bitcoin relies on chain separation (different chains, different UTXOs).

## 3. Roadmap

### Phase 1: Operational Baseline (Current)
Everything needed for basic cryptocurrency function is **already implemented**:
- P2PKH payments with full UTXO model
- Fee market with mempool prioritization
- Coinbase with constitutional 50/25/25 split
- Wallet with coin selection and UTXO tracking
- Reorg support with BlockUndo

**Status**: Complete. Functional for single-key payments, mining, and basic transfers.

### Phase 2: Lock Mechanisms (Height 5000+)
Activates at mainnet height 5000:
- **BOND_LOCK**: Time-locked outputs (lock SOST until block height N). Used for PoPC Model B.
- **ESCROW_LOCK**: Time-locked with designated beneficiary. Used for Materials Engine access.
- **Capsule Protocol v1**: Structured metadata in transaction outputs.

**Complexity**: Low — already implemented, just awaiting activation height.

### Phase 3: Enhanced Functionality (Future Research)

The following capabilities are **not implemented** and would require consensus changes:

| Feature | Complexity | Dependencies | Notes |
|---|---|---|---|
| **RBF (Replace-by-Fee)** | Low | Mempool changes only | No consensus change needed. Mempool policy to accept higher-fee replacement. |
| **CPFP** | Low | Mempool changes only | Fee calculation considers unconfirmed parent tx fees. |
| **Relative timelocks (CSV-like)** | Medium | New output type + consensus | Enables payment channels. Requires sequence number field or new lock type. |
| **2-of-3 multisig** | Medium | New output type + consensus | Could be implemented as a fixed output type (OUT_MULTISIG_2_3) without full scripting. |
| **Hash timelocks (HTLC)** | High | New output type + consensus | Prerequisite for Lightning-style channels. Requires hash preimage reveal mechanism. |
| **Schnorr signatures** | Medium | Crypto library + consensus | Enables key aggregation, batch verification. Could coexist with ECDSA. |
| **Lightning Network** | Very High | HTLC + CSV + channel protocol | Full payment channel implementation. Years of engineering. |

### Design Philosophy

SOST deliberately chose a **type-based** model over Bitcoin's **script-based** model:

- **Pros**: Smaller attack surface, faster validation, simpler implementation, no script injection risks
- **Cons**: Less flexible, each new capability requires a consensus change, no arbitrary smart contracts

New transaction capabilities can be added via new output types with consensus activation heights, following the BOND_LOCK/ESCROW_LOCK pattern. This provides a controlled upgrade path without the complexity of a full scripting engine.

### What SOST Will NOT Implement

- **Inscriptions/Ordinals**: Not a priority. Capsule Protocol serves structured metadata needs.
- **Arbitrary smart contracts**: SOST is a payment chain with constitutional reserves, not a smart contract platform.
- **Account-based model**: SOST will remain UTXO-based.

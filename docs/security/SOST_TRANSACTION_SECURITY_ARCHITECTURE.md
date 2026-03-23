# SOST Transaction Security Architecture

## Current Architecture

### Signing Pipeline
```
User Input (address + amount)
  → Fee calculation (integer rational arithmetic)
  → UTXO selection (maturity-filtered, dust-excluded)
  → Transaction construction (UTXO model)
  → Sighash computation (BIP143-simplified, double SHA256)
  → ECDSA signing (secp256k1, compact 64-byte)
  → LOW-S normalization (S5 rule)
  → Broadcast to mempool
  → Node validation (R1-R14 + S1-S12)
  → Block inclusion
```

### Validation Layers
```
Layer 1 (Structure):  R1-R14  — format, size, types, counts
Layer 2 (Header):     Timestamp, difficulty, prev-link
Layer 3 (Consensus):  Fees, subsidy, coinbase split (50/25/25)
Layer 4 (UTXO):       Atomic connect with undo entries
```

### Key Security Properties
- **No float arithmetic**: All monetary values in stocks (i64)
- **Fee as rational**: fee/size computed as integer ratio
- **LOW-S enforced**: Eliminates signature malleability
- **Maturity gating**: 1000-block coinbase maturity
- **Dust prevention**: 10,000 stock minimum output

## Proposed Security Layers (No Consensus Change)

### Layer A: Wallet-Level Safety
```
Before signing:
  1. Display human-readable summary:
     - Amount in SOST (not just stocks)
     - Destination address (full)
     - Fee in SOST
     - Change address
     - Number of inputs consumed
  2. If destination is new (first send): warn + optional delay
  3. If amount exceeds configurable threshold: require re-entry of passphrase
  4. Log operation to local audit trail
```

### Layer B: Address Trust Framework
```
Wallet maintains local address book:
  - trusted: previously sent to, explicitly whitelisted
  - new: never sent to before
  - internal: own addresses
  - vault: treasury/foundation addresses

Policy (configurable):
  - send to trusted: normal flow
  - send to new: warning + optional 24h delay
  - send to vault: require elevated auth
```

### Layer C: Treasury Safety Profile
```
For wallets marked as "treasury":
  - Daily outflow cap (configurable)
  - Per-transaction limit (configurable)
  - Mandatory confirmation for all sends
  - Local audit log of every operation
  - No dumpprivkey allowed
```

### Layer D: PSBT Workflow (Future)
```
When implemented, enables:
  1. Create unsigned transaction (online/watch-only wallet)
  2. Transfer PSBT to air-gapped signer
  3. Sign on offline device
  4. Return signed PSBT to online wallet
  5. Broadcast

Benefits:
  - Private keys never touch internet-connected device
  - Hardware wallet compatibility (via HWI)
  - Multi-party signing (multisig)
```

## Implementation Roadmap

### Phase 1: Quick Wins (No C++ changes needed)
- Documentation (this document + companions)
- RPC hardening config template
- Operational runbooks
- Build hardening flags (**DONE**)

### Phase 2: Wallet Safety (C++ CLI changes)
- Pre-send summary display
- Address book with trust levels
- Local operation audit log
- Auto-lock timer
- Treasury safety profile flag

### Phase 3: Advanced (Significant C++ work)
- PSBT support
- HD wallet (BIP32)
- Watch-only mode
- Multisig (P2SH or native)
- Hardware wallet integration (HWI)

### Phase 4: Institutional (Architecture expansion)
- Role-based access control
- Approval workflows
- Notification service
- Monitoring dashboard
- HSM abstraction layer

## Honest Limitations

- **Single-key model**: Currently one key = full control. No multisig.
- **No offline signing**: Keys must be on the signing machine.
- **No address checksum**: Typos are not caught by the protocol.
- **No HD derivation**: Each key is independent; backup = entire file.
- **CLI only**: No GUI safety prompts; CLI users must be careful.

These limitations are **standard for early UTXO chains** and will be
addressed incrementally without consensus changes.

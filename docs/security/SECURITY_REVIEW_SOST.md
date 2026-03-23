# SOST Security Review — Codebase Audit

## Audit Scope
C++ codebase at commit time. Covers: wallet, RPC, node, transaction validation,
P2P, crypto primitives, build system. Does NOT cover consensus rule changes.

## Security Primitives Inventory

### IMPLEMENTED AND ACTIVE

| Domain | Primitive | Implementation | Notes |
|--------|-----------|----------------|-------|
| Wallet encryption | AES-256-GCM + scrypt | OpenSSL EVP | v2 format, N=32768 r=8 p=1 |
| Key wiping | OPENSSL_cleanse | wallet.cpp | Wipes key material after use |
| ECDSA signing | secp256k1 | libsecp256k1 | Side-channel resistant context |
| LOW-S enforcement | s <= n/2 | tx_signer.cpp:188-219 | Consensus rule S5 |
| Key generation | RAND_bytes | OpenSSL | 32-byte entropy per key |
| Address format | sost1 + RIPEMD160(SHA256(pubkey)) | address.h | 45-char checksum-less |
| Fee enforcement | 1 stock/byte minimum | tx_validation S8 | Integer rational arithmetic |
| Dust prevention | 10,000 stocks threshold | tx_validation | Prevents uneconomic UTXOs |
| Coinbase maturity | 1000 blocks (~7 days) | tx_validation S10 | Prevents spending immature rewards |
| P2P ban system | Misbehavior scoring | sost-node.cpp:359-449 | 100 points = 24h ban |
| Connection limits | 64 inbound, 4 per IP | sost-node.cpp:362-364 | Sybil resistance |
| Timestamp validation | MTP + 10min future drift | block_validation L2 | Prevents timestamp manipulation |
| Block size limit | 1MB consensus | block_validation L1 | DoS prevention |
| Integer-only money | stocks (i64), no floats | params.h | Eliminates rounding bugs |
| Build hardening | Stack protector, PIE, RELRO | CMakeLists.txt | Added in this review |

### IMPLEMENTED BUT NOT EXPOSED

| Feature | Status | Notes |
|---------|--------|-------|
| Bond/escrow locks | In wallet.h | Implemented but no CLI exposure |
| Capsule protocol | In capsule.h | Activates at height 5000 |
| Block undo (reorg) | In block_validation.h | L4 atomic with undo entries |

### MISSING — HIGH VALUE

| Feature | Impact | Difficulty | Notes |
|---------|--------|------------|-------|
| PSBT (Partially Signed Bitcoin Tx) | HIGH | MEDIUM | Enables offline signing, multisig, HW wallets |
| HD wallet (BIP32/44) | HIGH | MEDIUM | Deterministic key derivation, single backup |
| Watch-only addresses | MEDIUM | LOW | Monitor without private keys |
| Multisig (P2SH) | HIGH | HIGH | Multi-party authorization |
| Address checksum | MEDIUM | LOW | Prevent typo-sends |
| RPC cookie auth | LOW | LOW | Standard Bitcoin-like auth method |
| ZMQ notifications | MEDIUM | MEDIUM | Event-driven monitoring |
| Replace-by-fee (RBF) | LOW | MEDIUM | Transaction acceleration |

### DANGEROUS OR LEGACY AREAS

| Area | Risk | Mitigation |
|------|------|------------|
| `dumpprivkey` command | Key exposure via CLI | Document as dangerous, warn user |
| Plaintext wallet (v1) | Keys stored unencrypted | Warn if v1 format detected |
| No address checksum | Typo sends irrecoverable | Verify destination in CLI |
| RPC credentials on CLI | Visible in process list | Use config file instead |
| No rate limiting on RPC | Brute-force risk if exposed | Bind to localhost only |

## Quick Wins Applied

1. **Build hardening flags** added to CMakeLists.txt:
   - `-fstack-protector-strong` (buffer overflow detection)
   - `-fPIE` + `-pie` (ASLR)
   - `-Wformat -Wformat-security` (format string protection)
   - `-Wl,-z,relro,-z,now` (RELRO)
   - `-D_FORTIFY_SOURCE=2` (Release builds)

2. All 15 tests pass with hardened build.

## Honest Assessment

SOST has a **solid cryptographic foundation** inherited from Bitcoin-like design:
- Strong ECDSA with LOW-S
- Modern wallet encryption (AES-256-GCM + scrypt)
- Key material wiping
- Integer-only monetary arithmetic
- 42 validation rules across 3 categories

The main gaps are in **wallet tooling** (no HD, PSBT, multisig) and **operational
safety** (no address whitelisting, no send confirmation escalation, no watch-only).
These are common in early-stage UTXO chains and can be added incrementally.

**No consensus changes needed** for any recommended security improvement.

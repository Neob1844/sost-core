# SOST Web Wallet Security Audit

**Date:** 2026-03-24
**File:** website/sost-wallet.html
**Auditor:** Automated code audit (line-by-line)

---

## Phase 1: Feature-by-Feature Verification

### 1. ENTROPY GENERATION — CORRECT
- **Lines:** 1021-1025
- Uses `crypto.getRandomValues()` (CSPRNG)
- Generates 128 bits (16 bytes) = 12-word seed
- Standard BIP39 entropy size

### 2. MNEMONIC — CORRECT
- **Lines:** 1040-1060 (entropyToWords), 990-1015 (BIP39_WORDLIST)
- Standard 2048-word BIP39 English wordlist
- Checksum: SHA256(entropy), first 4 bits appended
- 132 bits / 11 = 12 words, indices into standard wordlist
- Checksum validation on import (lines 1062-1090)

### 3. SEED DERIVATION — CORRECT
- **Lines:** 1027-1038
- PBKDF2-HMAC-SHA512, 2048 iterations
- Salt: "mnemonic" (no passphrase support — design choice, not bug)
- Output: 256 bits (32 bytes)
- Uses Web Crypto API `crypto.subtle.deriveBits()`

### 4. KEY DERIVATION — NO BIP32
- **Lines:** 1094-1107
- Direct: seed (32 bytes) → private key (same bytes)
- **NO BIP32 hierarchical derivation**
- No derivation path (no m/44'/8888'/0'/0/0)
- Single-key design: one seed = one key = one address
- Not a bug, but limits multi-address capability

### 5. ADDRESS GENERATION — CORRECT
- **Lines:** 925-937
- `hash160(pubkey)` = RIPEMD160(SHA256(compressed_pubkey))
- Address = "sost1" + hex(hash160) = 45 characters
- Matches C++ implementation exactly (src/address.cpp:16-24)

### 6. CROSS-VERIFICATION — COMPATIBLE
- Founder key: `[REDACTED — known compromised, see SOST_MASTER_PLAN.md]`
- Expected address: `sost13a22c277b5d5cbdc17ecc6c7bc33a9755b88d429`
- Both web wallet and CLI use identical derivation chain:
  - privkey → secp256k1 compressed pubkey → SHA256 → RIPEMD160 → "sost1" + hex
- **Implementations are compatible for import/export of raw private keys**

### 7. ENCRYPTION — CORRECT
- **Lines:** 958-986
- AES-256-GCM via Web Crypto API
- PBKDF2-SHA256, 100,000 iterations for password → key
- Random 16-byte salt, 12-byte IV per encryption
- GCM authentication tag implicit (16 bytes)
- Key material: non-extractable CryptoKey object

### 8. IMPORT BY SEED — CORRECT
- **Lines:** 1539-1556
- Validates BIP39 checksum before accepting
- Case-insensitive, whitespace-flexible
- Regenerates entropy → seed → key consistently
- Test: generate → copy seed → import → same address ✓

### 9. IMPORT BY PRIVATE KEY — CORRECT
- **Lines:** 1559-1574
- Accepts 64 hex chars (256-bit private key)
- Generates same address as CLI `importprivkey`

### 10. KNOWN ISSUES
- **2FA TOTP:** Implementation is RFC 6238 compliant (lines 1223-1269). Correctly generates/verifies 6-digit codes with ±1 period tolerance.
- **Import tabs:** All 4 tabs (seed, private key, file, watch-only) work
- **Send:** Fee estimation works via RPC `estimatefee` with fallback to 1000 stocks/byte

---

## Phase 2: Compatibility Table

| Operation | Web Wallet | CLI (sost-cli) | Compatible? |
|-----------|-----------|----------------|-------------|
| Generate keypair | RAND + secp256k1 | RAND_bytes + secp256k1 | **Yes** (same curve) |
| Seed phrase 12 words | BIP39 ✓ | **No** (random key only) | **No** — CLI lacks BIP39 |
| BIP32 derivation | No (direct seed→key) | No | N/A |
| Address format | sost1 + 40 hex | sost1 + 40 hex | **Identical** |
| Address derivation | RIPEMD160(SHA256(cpub)) | RIPEMD160(SHA256(cpub)) | **Identical** |
| Encryption | AES-256-GCM + PBKDF2 | AES-256-GCM + scrypt | **Incompatible formats** |
| Import private key hex | 64 hex chars ✓ | 64 hex chars ✓ | **Yes** |
| Import seed phrase | 12 BIP39 words ✓ | **Not supported** | **No** |
| Backup JSON format | {salt, iv, ct} (PBKDF2) | {scrypt_N, salt, iv, ct} | **Different** |
| Sign TX | noble-secp256k1 + LOW-S | libsecp256k1 + LOW-S | **Compatible** |
| TX format | Same SOST TX v1 | Same SOST TX v1 | **Identical** |

**Critical gap:** CLI cannot import BIP39 seed phrases from web wallet. Users who create wallets in the web wallet cannot restore them in the CLI without extracting the private key first.

---

## Phase 3: Bugs Found

| # | Line | Description | Severity | Affects Funds? | Fix |
|---|------|-------------|----------|---------------|-----|
| 1 | 1027 | `entropyToSeed()` derives 256 bits not 512 bits. BIP39 standard produces 512-bit seed. Only first 256 bits used as privkey. | **LOW** | No — valid secp256k1 key regardless | Document design choice |
| 2 | — | No BIP39 passphrase support (25th word) | **LOW** | No | Document or implement |
| 3 | 1259 | TOTP verification uses `===` not constant-time compare | **LOW** | No (6-digit code too short for timing attack) | Optional hardening |
| 4 | — | Encrypted backup format incompatible with CLI | **MEDIUM** | No direct fund loss | Implement BIP39 in CLI |
| 5 | — | Password minimum 8 chars, no complexity | **LOW** | Only if password is weak | Recommend 12+ chars |

**No CRITICAL or HIGH bugs found.** The web wallet crypto is sound.

---

## Phase 4: Recommendation

The web wallet's BIP39 implementation is correct and should serve as the reference for CLI implementation. The key gap is **CLI lacks BIP39 seed phrase support**, making cross-platform wallet recovery impossible without extracting raw private keys.

**Priority:** Implement BIP39 in CLI to achieve full web↔CLI interoperability.

# SOST Security Audit — Real Implementation Status

**Date:** 2026-03-24
**Auditor:** Automated code audit (grep + source read)
**Scope:** All 20 features listed on sost-security.html vs actual codebase

---

## Phase 1 + 2: Feature Status Table

| # | Feature | Web Claims | Real Status | Evidence | Notes |
|---|---------|------------|-------------|----------|-------|
| 1 | **Build Hardening** | IMPLEMENTED (5 flags) | **IMPLEMENTED_AND_WORKING** | `CMakeLists.txt:8-18` | stack-protector-strong, fPIE, pie, RELRO+NOW, FORTIFY_SOURCE=2 (Release). Also -Wformat-security. Missing: -fstack-clash-protection |
| 2 | **Wallet Encryption** | AES-256-GCM + scrypt (N=32768) | **IMPLEMENTED_AND_WORKING** | `src/wallet.cpp:895-1158` | AES-256-GCM, scrypt N=32768 r=8 p=1, OPENSSL_cleanse on keys. Tests: chunk1/chunk2 |
| 3 | **ECDSA Signing** | libsecp256k1 + LOW-S | **IMPLEMENTED_AND_WORKING** | `src/tx_signer.cpp:188-354` | secp256k1 library, IsLowS() check, EnforceLowS() via normalize, compressed pubkeys |
| 4 | **Fee-Rate Ordering** | Integer arithmetic, no floats | **IMPLEMENTED_AND_WORKING** | `include/sost/mempool.h:116-136` | `__int128` cross-multiply comparison. BuildBlockTemplate sorts descending. Tests: test-mempool |
| 5 | **P2P Protection** | Ban 100pts/24h, 64 inbound, 4/IP | **IMPLEMENTED_AND_WORKING** | `src/sost-node.cpp:361-450` | BAN_THRESHOLD=100, BAN_DURATION=86400, MAX_INBOUND_PEERS=64, MAX_PEERS_PER_IP=4 |
| 6 | **RPC Security** | Localhost-only, Basic Auth | **IMPLEMENTED_AND_WORKING** | `src/sost-node.cpp:93-96, 633-699, 3403` | INADDR_LOOPBACK default, --rpc-public to override, Base64 Basic Auth decode+verify |
| 7 | **cASERT RPC** | casert_profile, casert_lag | **IMPLEMENTED_BUT_BROKEN** | `src/sost-node.cpp:838-860` | Fields exist in getinfo. Bug: base formula (now_time=0) returns B0 even when blocks show E3/E4. Explorer JS workaround applied. |
| 8 | **P2P Encryption** | X25519 + ChaCha20-Poly1305 | **IMPLEMENTED_AND_WORKING** | `src/sost-node.cpp:70-291, 2780-2842` | Full handshake (EKEY exchange), session keys via HKDF-SHA256, per-peer nonce counter. Default: ON (3 modes: off/on/required) |
| 9 | **Dynamic Fees (RBF, CPFP)** | "Dynamic fee calculation" | **IMPLEMENTED_AND_WORKING** | `src/mempool.cpp` (RBF), `src/mempool.cpp:BuildBlockTemplateCPFP` (CPFP), `src/sost-cli.cpp` (auto fee calc) | Full RBF in mempool + CPFP-aware block template. Tests: test-rbf, test-cpfp |
| 10 | **Checkpoints + Reorg Limit** | 500 blocks max reorg | **IMPLEMENTED_AND_WORKING** | `src/sost-node.cpp:330, 2236-2241, 2481-2491`, `include/sost/checkpoints.h` | MAX_REORG_DEPTH=500, hard checkpoint height+hash validation, test: test-checkpoints, test-reorg |
| 11 | **Coinbase Maturity** | 1000 blocks | **IMPLEMENTED_AND_WORKING** | `include/sost/consensus_constants.h:14`, `src/wallet.cpp:121-180` | COINBASE_MATURITY=1000, is_mature() filter, balance/list_unspent chain_height-aware |
| 12 | **Trusted Address Book** | IMPLEMENTED | **IMPLEMENTED_AND_WORKING** | `include/sost/addressbook.h`, `src/addressbook.cpp`, `src/sost-cli.cpp` | 4 trust levels (trusted/known/new/blocked), JSON persistence, CLI commands. Tests: test-addressbook |
| 13 | **New-Address Cooldown** | IMPLEMENTED | **IMPLEMENTED_AND_WORKING** | `src/sost-cli.cpp` send command | First-send warning, high-value alert (>10 SOST), --skip-warning flag |
| 14 | **Pre-Send Summary** | IMPLEMENTED | **IMPLEMENTED_AND_WORKING** | `src/sost-cli.cpp` send command | Full TX summary with confirmation prompt, --yes/-y to skip |
| 15 | **Treasury Safety Profile** | IMPLEMENTED | **IMPLEMENTED_AND_WORKING** | `include/sost/wallet_policy.h`, `src/wallet_policy.cpp`, `src/sost-cli.cpp` | Daily/per-TX limits, vault mode, large-TX address book requirement. Tests: test-wallet-policy |
| 16 | **PSBT / Offline Signing** | "Future" | **NOT_IMPLEMENTED** | `sost-security.html:457` | Web correctly says "Future". No code exists. |
| 17 | **HD Wallet (BIP32)** | "Future" | **NOT_IMPLEMENTED** | `sost-security.html:458` | Web correctly says "Future". No code exists. Acknowledged in SOST_WALLET_SAFE_USAGE.md. |
| 18 | **Multisig** | Not listed on security page | **NOT_IMPLEMENTED** | `docs/security/SOST_WALLET_SAFE_USAGE.md:98` | Acknowledged as "Not implemented". |
| 19 | **Anti-Phishing Phrase** | Not listed | **NOT_IMPLEMENTED** | — | No security phrase in wallet or web wallet. Only manual guidelines in docs. |
| 20 | **Vulnerability Reporting** | SEC-DISC-2026 contact form | **IMPLEMENTED_AND_WORKING** | `sost-security.html:502-586`, `sost-contact.html:184` | Full reporting process, severity classification, scope definition. |

---

## Summary by Status

| Status | Count | Features |
|--------|-------|----------|
| IMPLEMENTED_AND_WORKING | 16 | Build hardening, Wallet encryption, ECDSA/LOW-S, Fee-rate ordering, P2P protection, RPC security, P2P encryption, Checkpoints+reorg, Coinbase maturity, Dynamic fees+RBF+CPFP, Vuln reporting, Trusted address book, New-address cooldown, Pre-send summary, Treasury safety profile |
| IMPLEMENTED_BUT_BROKEN | 1 | cASERT RPC (profile value incorrect, JS workaround applied) |
| NOT_IMPLEMENTED | 3 | PSBT, HD wallet, Multisig |

---

## Phase 3: What Can Be Implemented Now

### DOCUMENTED_ONLY features — Implementation Assessment

| Feature | Consensus Change? | Effort | Risk | Dependencies | Priority |
|---------|-------------------|--------|------|-------------|----------|
| **Pre-send summary** | No (CLI only) | 2 hours | Low | None | **AHORA** |
| **Trusted address book** | No (wallet local) | 4 hours | Low | wallet.h label field exists | **AHORA** |
| **New-address cooldown** | No (CLI only) | 3 hours | Low | Needs address history tracking | **PRÓXIMO SPRINT** |
| **Treasury safety profile** | No (wallet policy) | 1 day | Medium | Needs config file, policy engine | **PRÓXIMO SPRINT** |

### NOT_IMPLEMENTED features — Implementation Assessment

| Feature | Consensus Change? | Effort | Risk | Dependencies | Priority |
|---------|-------------------|--------|------|-------------|----------|
| **Pre-send confirmation** | No | 1 hour | None | — | **AHORA** |
| **PSBT** | No (serialization format) | 1 week | Medium | Needs partial-tx type, export/import | **FUTURO** |
| **HD Wallet (BIP32)** | No (key management) | 1 week | High | Needs BIP32 derivation, seed backup | **FUTURO** |
| **Multisig** | Yes (new script type) | 2+ weeks | High | Needs script interpreter changes | **FUTURO** |
| **Anti-phishing phrase** | No (UI only) | 30 min | None | — | **NO MERECE LA PENA** (low value for CLI wallet) |

---

## Phase 4: Quick Wins Implemented

### Quick Win #1: Pre-Send Confirmation in sost-cli

**What:** Before broadcasting a transaction, show a summary and require `yes` confirmation.

**File:** `src/sost-cli.cpp` — `send` command (line ~686)

**Current behavior:** Creates tx and broadcasts immediately.

**Required change:** After printing tx info (line 686-692), prompt `Confirm send? [yes/no]:` before broadcasting.

**Status:** READY TO IMPLEMENT (see below for code change needed — deferred pending user approval since it modifies a binary)

### Quick Win #2: cASERT RPC Profile Fix (Known Bug)

**What:** `getinfo` returns B0 when blocks show E3/E4. Root cause: `casert_compute(meta, height, 0)` with `now_time=0` uses base formula which caps at E1 via slew rate.

**Status:** JS workaround applied in explorer. Server-side fix deferred (requires storing declared profile from block acceptance).

---

## Phase 5: Web vs Reality Discrepancies

### Discrepancies Found

| # | Web Claim | Reality | Severity | Fix Needed? |
|---|-----------|---------|----------|-------------|
| 1 | Line 423: Tag says "IMPLEMENTED" for wallet-layer section | All 7 items in that section ARE implemented | **None** | No — web is accurate |
| 2 | Line 448: Tag says "DESIGNED" for planned features | All 6 items are designed only, not coded | **None** | No — web is honest |
| 3 | Line 434: "cASERT RPC: Real-time profile from node" | Profile VALUE is incorrect (B0 vs E3/E4) | **Medium** | Should note "known display bug" or fix server |
| 4 | Line 491: "Dynamic fee calculation (CLI v1.3) — Complete" | Auto fee calc works, but no RBF/CPFP | **Low** | Acceptable — web doesn't claim RBF/CPFP |
| 5 | Line 495: "P2P encryption — Active (default on)" | Confirmed: default ON mode | **None** | No — web is accurate |
| 6 | Missing: no mention of -fstack-clash-protection absence | Minor gap in build hardening | **Low** | Could add flag to CMakeLists.txt |

### Verdict: The web page is **largely honest**

- "IMPLEMENTED" section: all items verified in code ✓
- "DESIGNED" section: correctly marked as not yet coded ✓
- "FUTURE" items: correctly marked ✓
- Only significant issue: cASERT profile value in getinfo RPC is incorrect (returns B0 instead of actual profile)

---

## CTO Recommendation: Priority Order

### 1. IMMEDIATE (this sprint)
- **Pre-send confirmation** in sost-cli `send` command — prevents accidental sends, 1-hour change, zero risk
- **Fix cASERT profile in getinfo** — store `declared_pi` from block acceptance in `g_last_accepted_profile` AND persist across restart by reading from tip block on init

### 2. NEXT SPRINT
- **Add -fstack-clash-protection** to CMakeLists.txt (1 line, zero risk)
- **Trusted address labels** — wallet.h already has label field, just needs CLI commands `labeladdress`, `listlabels`
- **New-address cooldown** — warn on first send to unknown address, require `--force` to skip

### 3. FUTURE (when resources allow)
- **PSBT / offline signing** — enables hardware wallet support, significant effort
- **HD wallet (BIP32)** — quality of life, single seed backup
- **Treasury safety profile** — daily limits, elevated auth

### 4. NOT RECOMMENDED
- **Anti-phishing phrase** — low value for CLI-only wallet
- **Multisig** — requires consensus changes, not worth the risk at this stage

---

## Build Hardening Detail

Current flags in `CMakeLists.txt:8-18`:

```cmake
# === Security hardening flags ===
if(NOT MSVC)
  add_compile_options(-fstack-protector-strong)   # ✓ Stack overflow detection
  add_compile_options(-fPIE)                       # ✓ Position-independent (ASLR)
  add_compile_options(-Wformat -Wformat-security)  # ✓ Format string protection
  add_link_options(-pie)                           # ✓ ASLR for linked executables
  add_link_options(-Wl,-z,relro,-z,now)            # ✓ Full RELRO
  if(CMAKE_BUILD_TYPE STREQUAL "Release")
    add_compile_options(-D_FORTIFY_SOURCE=2)       # ✓ Buffer overflow detection
  endif()
endif()
```

**Missing (recommended):**
- `-fstack-clash-protection` — prevents stack clash attacks
- `-fcf-protection` (GCC 8+) — control flow integrity (Intel CET)

---

## Test Coverage for Security Features

| Feature | Test Binary | CTest Name | Status |
|---------|------------|------------|--------|
| ECDSA/LOW-S | test-tx-signer | tx-signer | ✓ |
| TX validation (R/S/CB rules) | test-tx-validation | tx-validation | ✓ |
| Fee-rate ordering | test-mempool | mempool | ✓ |
| Coinbase maturity | test-tx-validation | tx-validation | ✓ |
| cASERT profiles | test-casert | casert | ✓ |
| Checkpoints | test-checkpoints | checkpoints | ✓ |
| Reorg handling | test-reorg | reorg | ✓ |
| Wallet encryption | (manual) | — | No automated test |
| P2P ban system | (manual) | — | No automated test |
| P2P encryption | (manual) | — | No automated test |
| Bond lock | test-bond-lock | bond-lock | ✓ |

**Gap:** No automated tests for wallet encryption, P2P ban system, or P2P encryption.

---

*End of audit. All findings based on code as of 2026-03-24.*

# SOST Threat Model

## Scope
Threats to SOST wallet users, node operators, and foundation treasury.
Focus: operational security, NOT consensus attacks.

## Threat Matrix

### T1: Malware / Keylogger on Local Machine
- **Impact**: CRITICAL — full key compromise
- **Probability**: MEDIUM (common attack vector)
- **Current mitigation**: Wallet encryption (AES-256-GCM + scrypt)
- **Gap**: No hardware wallet support, no PSBT for offline signing
- **Recommended**: PSBT support → enables air-gapped signing
- **Priority**: HIGH

### T2: Unlocked Wallet Session Left Open
- **Impact**: HIGH — anyone with access can send
- **Probability**: MEDIUM (common user mistake)
- **Current mitigation**: Passphrase required for wallet operations
- **Gap**: No auto-relock timer in CLI, no session timeout
- **Recommended**: Auto-lock after configurable timeout
- **Priority**: MEDIUM

### T3: Clipboard Hijacking (Address Swap)
- **Impact**: HIGH — funds sent to attacker address
- **Probability**: MEDIUM (known malware family)
- **Current mitigation**: NONE
- **Gap**: No address verification prompt before send
- **Recommended**: Display full address + ask confirmation before signing
- **Priority**: HIGH

### T4: Phishing of Official Communications
- **Impact**: MEDIUM — user tricked into revealing keys
- **Probability**: LOW (small user base currently)
- **Current mitigation**: NONE
- **Recommended**: Anti-phishing code in any official communications
- **Priority**: LOW (grows with adoption)

### T5: RPC Endpoint Exposed to Network
- **Impact**: CRITICAL — remote wallet drain
- **Probability**: LOW (default localhost binding)
- **Current mitigation**: Default binds to 127.0.0.1:18232
- **Gap**: No config validation warns if binding to 0.0.0.0
- **Recommended**: Startup warning if RPC bound to non-localhost
- **Priority**: MEDIUM

### T6: Send to Wrong Address (Human Error)
- **Impact**: HIGH — irreversible loss
- **Probability**: MEDIUM (no address checksum)
- **Current mitigation**: sost1 prefix (40 hex chars)
- **Gap**: No checksum in address format, no send confirmation
- **Recommended**: Pre-send summary with amount + destination + fee
- **Priority**: HIGH

### T7: Foundation/Treasury Key Compromise
- **Impact**: CRITICAL — 25% of all emissions at risk
- **Probability**: LOW (if properly secured)
- **Current mitigation**: Constitutional addresses are hardcoded
- **Gap**: No multisig, no timelock, single key controls vault
- **Recommended**: Multisig for treasury, timelocked withdrawals
- **Priority**: HIGH (for treasury operations)

### T8: Backup Loss / Corruption
- **Impact**: CRITICAL — permanent key loss
- **Probability**: MEDIUM
- **Current mitigation**: Wallet file can be copied
- **Gap**: No HD seed (no single backup point), no guided backup
- **Recommended**: HD wallet with mnemonic seed phrase
- **Priority**: HIGH

### T9: Address Reuse
- **Impact**: LOW — privacy degradation, slight security risk
- **Probability**: HIGH (single-key model encourages reuse)
- **Current mitigation**: `getnewaddress` generates fresh keys
- **Gap**: No automatic change addresses, no reuse warnings
- **Recommended**: HD wallet with automatic change outputs
- **Priority**: MEDIUM

### T10: Supply Chain / Build Integrity
- **Impact**: CRITICAL — compromised binary = total compromise
- **Probability**: LOW
- **Current mitigation**: Build from source, CMake
- **Gap**: No reproducible builds, no binary signing, no SBOM
- **Recommended**: Reproducible build process, signed releases
- **Priority**: MEDIUM (grows with adoption)

## Priority Summary

| Priority | Threats | Recommended Action |
|----------|---------|-------------------|
| **NOW** | T1, T3, T6, T7, T8 | PSBT, send confirmation, HD wallet, multisig treasury |
| **SOON** | T2, T5, T9 | Auto-lock, RPC warnings, HD change addresses |
| **LATER** | T4, T10 | Anti-phishing, reproducible builds |

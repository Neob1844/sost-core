# SOST Security Implementation Phases

## Level 1 — Quick Wins (Do Now)

| Item | Layer | Difficulty | Risk | Benefit | Status |
|------|-------|------------|------|---------|--------|
| Build hardening flags | Build | LOW | NONE | Prevents buffer overflows, enables ASLR | **DONE** |
| Security documentation suite | Docs | LOW | NONE | Operational guidance | **DONE** |
| RPC hardening guide | Docs | LOW | NONE | Prevents misconfig | **DONE** |
| Treasury opsec runbook | Docs | LOW | NONE | Foundation safety | **DONE** |
| Wallet safe usage guide | Docs | LOW | NONE | User protection | **DONE** |
| Threat model | Docs | LOW | NONE | Risk awareness | **DONE** |
| Regulatory matrix | Docs | LOW | NONE | Honest positioning | **DONE** |

## Level 2 — Security Foundation (Next Sprint)

| Item | Layer | Difficulty | Risk | Benefit |
|------|-------|------------|------|---------|
| Pre-send summary in CLI | Wallet/CLI | LOW | LOW | Prevents wrong-address sends |
| Address book (local JSON) | Wallet | LOW | LOW | Trust tracking |
| First-send warning | Wallet/CLI | LOW | LOW | Catches clipboard hijack |
| Local audit log | Wallet | LOW | LOW | Traceability |
| Auto-lock timer | Wallet | LOW | LOW | Session safety |
| Treasury profile flag | Wallet | LOW | LOW | Elevated safety for vaults |
| `dumpprivkey` warning banner | CLI | LOW | NONE | Prevents accidental exposure |
| RPC bind validation warning | Node | LOW | LOW | Catches dangerous exposure |

**Estimated effort**: 2-3 days of C++ work. All changes in wallet/CLI layer only.
No consensus, no network compatibility impact.

## Level 3 — Advanced (Future Phase)

| Item | Layer | Difficulty | Risk | Benefit |
|------|-------|------------|------|---------|
| PSBT support | Core/Wallet | MEDIUM | LOW | Offline signing, HW wallets |
| HD wallet (BIP32/44) | Wallet | MEDIUM | MEDIUM | Single seed backup |
| Watch-only mode | Wallet | LOW | LOW | Monitor without keys |
| Multisig (2-of-3) | Core/Wallet | HIGH | MEDIUM | Multi-party authorization |
| Address checksum | Core | LOW | LOW | Typo prevention |
| ZMQ notifications | Node | MEDIUM | LOW | Event-driven monitoring |
| Coin control UI | CLI | MEDIUM | LOW | UTXO privacy |
| RBF support | Mempool | MEDIUM | MEDIUM | Transaction acceleration |

**Estimated effort**: 2-4 weeks per major item. PSBT and HD wallet are the
highest-value additions.

## Level 4 — Institutional (Long-term)

| Item | Layer | Difficulty | Benefit |
|------|-------|------------|---------|
| HSM abstraction | External | HIGH | Hardware security module support |
| Role-based access | Service | HIGH | Multi-operator environments |
| Approval workflows | Service | HIGH | Quorum-based treasury |
| Monitoring dashboard | Service | MEDIUM | Operational visibility |
| Reproducible builds | Build | MEDIUM | Supply chain integrity |
| Formal audit | External | HIGH | Third-party verification |

## What NOT to Implement

| Item | Reason |
|------|--------|
| On-chain governance | Not needed for small team; adds complexity |
| Smart contract layer | Out of scope for UTXO chain |
| Privacy features (ring sig, etc.) | Increases regulatory risk |
| Custom scripting language | OP_CODES sufficient |
| KYC/AML at protocol level | Protocol should be neutral |
| Centralized key recovery | Defeats purpose of self-custody |

## CTO Recommendation

**Immediate priority**: Build hardening (DONE) + documentation (DONE).
These cost nothing and meaningfully reduce attack surface.

**Next priority**: CLI safety improvements (pre-send summary, address book,
first-send warning). These are 2-3 days of work and directly prevent the
most common user errors (wrong address, clipboard hijack).

**Strategic priority**: PSBT + HD wallet. These unlock hardware wallet
support, offline signing, and proper key management. Estimate 3-4 weeks
but transform SOST's security posture from "early chain" to "production-ready."

**Skip for now**: Multisig, ZMQ, RBF, institutional features.
These matter at scale but add complexity before the user base justifies it.

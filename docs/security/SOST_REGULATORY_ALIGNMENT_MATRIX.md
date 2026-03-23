# SOST Regulatory Alignment Matrix

## Disclaimer
SOST is a decentralized cryptocurrency protocol. It is NOT a stablecoin, NOT an
Electronic Money Token (EMT), NOT a CASP (Crypto-Asset Service Provider), and
does NOT currently operate custodial services or fiat ramps.

This matrix identifies which security practices from modern regulatory frameworks
are **advisable to adopt voluntarily** for operational security, and which would
become **mandatory only if** SOST were to offer regulated services in the future.

## Classification

### MANDATORY IF REGULATED SERVICE
These apply ONLY if SOST were to operate custodial wallets, exchanges,
withdrawal panels, or fiat ramps.

| Control | Framework | When Required |
|---------|-----------|---------------|
| KYC/AML identity verification | MiCA Art. 68, AMLD6 | Custodial service, exchange |
| Transaction monitoring | MiCA Art. 76, Travel Rule | Custodial service |
| Segregation of client assets | MiCA Art. 70 | Custodial service |
| Capital adequacy requirements | MiCA Art. 67 | Licensed CASP |
| Complaints procedure | MiCA Art. 71 | Licensed CASP |
| ICT risk management | DORA | Financial entity |
| Strong Customer Authentication | PSD2/PSD3 | Payment service |

**Status**: NOT APPLICABLE to SOST protocol. Would apply to any future
centralized service built on top.

### ADVISABLE EVEN FOR DECENTRALIZED PROJECT
Security practices that strengthen the project regardless of regulation.

| Practice | Inspired By | Implementation | Status |
|----------|-------------|----------------|--------|
| Wallet encryption at rest | ISO 27001, PCI DSS | AES-256-GCM + scrypt | DONE |
| Key material secure destruction | NIST SP 800-88 | OPENSSL_cleanse | DONE |
| Build hardening (ASLR, stack protector) | CIS Benchmarks | CMakeLists.txt flags | DONE |
| Integer-only monetary arithmetic | Financial engineering | stocks (i64) | DONE |
| Transaction validation rules | Consensus security | 42 rules (R/S/CB) | DONE |
| Anti-DoS peer management | Network security | Ban system, limits | DONE |
| Minimum fee enforcement | Spam prevention | 1 stock/byte | DONE |
| Coinbase maturity delay | Reorg safety | 1000 blocks | DONE |
| Localhost-only RPC default | Access control | 127.0.0.1 binding | DONE |
| Send confirmation before signing | UX safety | Pre-sign summary | RECOMMENDED |
| Address whitelisting | Operational safety | Trusted address book | RECOMMENDED |
| HD deterministic keys | Key management | BIP32/44 seed | RECOMMENDED |
| Offline signing support | Key isolation | PSBT workflow | RECOMMENDED |
| Audit logging of operations | Traceability | Local operation log | RECOMMENDED |

### PREMIUM SECURITY FEATURES
Valuable for high-value users, treasury operations, or institutional use.

| Feature | Pattern | Notes |
|---------|---------|-------|
| Multisig wallets | M-of-N authorization | Treasury protection |
| Timelocked withdrawals | Delayed execution | Operational vault |
| Hardware wallet integration | Key isolation | Via PSBT + HWI |
| Role-based access | Least privilege | Multi-operator environments |
| Quorum-based approvals | Multi-party auth | Foundation governance |
| Emergency freeze procedures | Incident response | Documented runbook |

### NOT NEEDED NOW

| Control | Reason |
|---------|--------|
| SCA (Strong Customer Authentication) | No custodial service |
| Travel Rule compliance | No regulated transfers |
| Capital reserves | No custodial obligations |
| Regulated audit reports | No regulated status |
| Formal penetration testing | Premature at current scale |

### DANGEROUS TO FAKE

| Claim | Why Dangerous |
|-------|---------------|
| "MiCA compliant" | SOST is not a CASP — claiming compliance is misleading |
| "PSD2 certified" | Not a payment service provider |
| "Bank-grade security" | No formal certification exists |
| "Insured deposits" | No insurance exists for SOST |

**Correct language**: "security-aligned", "inspired by best practices",
"future-ready architecture", "voluntary adoption of institutional patterns"

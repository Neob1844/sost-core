# Constitutional Addresses Audit

**Date:** 2026-03-28
**Auditor:** NeoB
**Chain height at audit:** 1799

## Address Status

| Address | Role | Balance | UTXOs | Mature? | Can Spend? | Consensus Restriction? |
|---------|------|---------|-------|---------|------------|----------------------|
| sost1059d1ef8639bcf47ec35e9299c17dc0452c3df33 | Genesis Miner | ~993 SOST | Yes | Yes | **YES** (confirmed — 10 SOST sent) | None |
| sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d | Gold Vault | 3,532.95 SOST | 1,800 | Yes (height 0-799 mature) | **YES** (no restriction) | **NONE** |
| sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f | PoPC Pool | 3,532.95 SOST | 1,800 | Yes (height 0-799 mature) | **YES** (no restriction) | **NONE** |

## Consensus Rules Found

### What IS enforced (coinbase INBOUND):
- CB6 rule (`tx_validation.cpp:604-609`): Coinbase output[1] MUST go to Gold Vault PKH
- CB6 rule: Coinbase output[2] MUST go to PoPC Pool PKH
- Coinbase split amounts: 50% miner, 25% gold, 25% popc (verified every block)

### What is NOT enforced (OUTBOUND spending):
- **No consensus rule prevents spending FROM Gold Vault or PoPC Pool**
- Standard UTXO spending rules apply — anyone with the private key CAN spend
- `ValidateInputs()` in `tx_validation.cpp` does NOT check source address
- There is no "frozen address" or "restricted UTXO" mechanism in the code

## Security Assessment

**CRITICAL FINDING:** The private keys for Gold Vault and PoPC Pool exist in `~/SOST/secrets/regenesis/` and could theoretically be used to drain both constitutional treasuries.

### Current Protection: Private Key Security Only
- Keys stored offline in WSL only (`~/SOST/secrets/regenesis/`)
- NOT on VPS
- NOT in any git repository
- Protection is operational (key management), NOT consensus-enforced

### Should There Be a Consensus Restriction?

**YES** — The whitepaper states these are constitutional addresses. Ideally:

1. **Gold Vault:** Should only be spendable under specific governance conditions
   - Possible implementation: require multi-sig or timelock for spending
   - Or: add a consensus rule that rejects TX spending from Gold Vault PKH

2. **PoPC Pool:** Should only be spendable for PoPC reward distribution
   - Possible implementation: add a consensus rule allowing spending only to registered PoPC participants
   - Or: require a special TX type for PoPC distribution

### Implementation Options:

| Option | Effort | Impact | Recommendation |
|--------|--------|--------|----------------|
| A. Hardcode "frozen" PKH list | 2 hours | Hard fork | NOT recommended — too inflexible |
| B. Multi-sig requirement | 1 week | Hard fork | Good for Gold Vault |
| C. Special TX type for PoPC | 2 weeks | Hard fork | Good for PoPC Pool |
| D. Timelock + governance vote | 3 weeks | Hard fork | Best long-term |
| E. Keep current (key security) | 0 | None | **Acceptable for now** |

### Recommendation:
**For launch (June 2026):** Option E — rely on key security. Keys are offline, not on VPS.
**Post-launch (Q4 2026):** Implement Option B (multi-sig for Gold Vault) + Option C (special TX for PoPC).
**Do NOT implement consensus restrictions before launch** — it's a hard fork and needs extensive testing.

## Document History
- 2026-03-28: Initial audit — NeoB

# PoPC Model A — Technical Specification

**Author:** NeoB
**Date:** 2026-03-28
**Status:** DESIGN — Awaiting CTO approval before implementation
**Whitepaper Reference:** Section 6 (Proof of Personal Custody)

---

## 1. Executive Summary

PoPC Model A is a voluntary time-bound commitment protocol. A participant declares custody of precious metals (XAUT/PAXG on Ethereum), locks a SOST bond on the SOST chain, and receives rewards from the PoPC Pool if they maintain custody for the committed period. Random audits derived from ConvergenceX block entropy verify custody without trusted oracles.

**Key properties:**
- Gold NEVER leaves the user's wallet — only SOST bond is at risk
- No custodian, no bridge, no oracle dependency for consensus
- Audit schedule is deterministic from PoW entropy (unpredictable, verifiable)
- Bond slashed automatically on custody violation — no human judge
- Rewards funded from the PoPC Pool (25% of every block reward)

---

## 2. Current State of Implementation

### What EXISTS in code:

| Component | Status | Location |
|-----------|--------|----------|
| PoPC Pool address | ACTIVE | `params.h:193` — `sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f` |
| 25% coinbase allocation | ACTIVE | Every block sends 25% to PoPC Pool address |
| BOND_LOCK tx type (0x10) | ACTIVE at height ≥5000 | `transaction.h:33`, `consensus_constants.h:22` |
| ESCROW_LOCK tx type (0x11) | ACTIVE at height ≥5000 | `transaction.h:34` |
| Bond/Escrow validation rules | ACTIVE | `tx_validation.cpp:25` — S11_BOND_LOCKED |
| Lock payload parsing | ACTIVE | `transaction.h:117` — WriteLockUntil/ReadLockUntil |
| Wallet bond management | ACTIVE | `wallet.h:88-107` — create_bond, create_escrow, list_bonds |
| CLI bond commands | ACTIVE | `sost-cli.cpp` — bond, escrow, listbonds |

### What does NOT exist yet:

| Component | Status | Needed for Model A |
|-----------|--------|-------------------|
| PoPC contract registration | NOT IMPLEMENTED | YES — user commitment records |
| Audit system (entropy-based) | NOT IMPLEMENTED | YES — custody verification |
| Ethereum wallet verification | NOT IMPLEMENTED | YES — XAUT/PAXG balance check |
| Reward distribution from Pool | NOT IMPLEMENTED | YES — automatic payout |
| Slash mechanism | NOT IMPLEMENTED | YES — bond confiscation |
| Reputation system | NOT IMPLEMENTED | YES — stars, limits |
| Price Bulletin system | NOT IMPLEMENTED | YES — bond sizing |
| Foundation signature verification | NOT IMPLEMENTED | YES — EIP-712 |

### PoPC Pool Accumulation

```
Genesis date: 2026-03-15
Genesis reward: 7.85100863 SOST
PoPC share: 25% = 1.96275216 SOST per block

Current accumulation (approximate, at height ~1800):
  1,800 blocks × 1.96275216 SOST ≈ 3,533 SOST in PoPC Pool

At 1 year (52,560 blocks):
  52,560 × 1.96275216 ≈ 103,123 SOST

Note: reward decays exponentially, so actual accumulation is slightly less.
```

---

## 3. User Flow — Step by Step

```
REGISTRATION FLOW (Model A):

1. USER prepares:
   - Has XAUT or PAXG in an Ethereum EOA wallet
   - Has SOST in their SOST wallet
   - Chooses: gold amount (oz), duration (1/3/6/9/12 months)

2. PRICE BULLETIN (daily, off-chain):
   - Foundation publishes: sost_usd_twap_7d, gold_usd_twap_7d
   - Sources: exchange APIs (public, reproducible)
   - Signed: EIP-712 Foundation signature
   - Published: website + GitHub + IPFS

3. BOND CALCULATION (client-side):
   ratio = sost_price / gold_oz_price
   bond_pct = lookup_table(ratio)   // 12%-30%
   bond_fiat = bond_pct × gold_amount × gold_price
   bond_sost = bond_fiat / sost_price

4. USER COMMITS:
   - Signs Bond Terms package (ECDSA on SOST chain)
   - Creates BOND_LOCK transaction locking bond_sost
   - Registers Ethereum wallet address + gold amount
   - Dual signature: Foundation (price attestation) + User (term acceptance)

5. ACTIVE CONTRACT:
   - Random audits triggered by ConvergenceX entropy
   - Audit checks: balanceOf(user_eth_wallet) >= committed_gold
   - Audit frequency: 5%-30% of periods depending on reputation
   - Continuous custody: historical balance also checked at deterministic checkpoints

6. COMPLETION (success):
   - User recovers: full bond (100% returned)
   - User receives: reward (1%-22% of bond depending on duration)
   - Protocol fee: 5% of reward to Foundation
   - Reputation: +1 toward next star level

7. FAILURE (slash):
   - User loses: entire bond
   - Distribution: 50% to PoPC Pool, 50% to Gold Vault
   - Reputation: reset to 0 stars
   - Address: blacklisted
```

---

## 4. Data Structures (C++ design)

```cpp
// include/sost/popc.h

// PoPC commitment record
struct PoPCCommitment {
    Hash256     commitment_id;      // unique ID (hash of terms)
    PubKeyHash  user_pkh;           // SOST address of participant
    std::string eth_wallet;         // Ethereum EOA address (0x...)
    std::string gold_token;         // "XAUT" or "PAXG"
    int64_t     gold_amount_mg;     // gold in milligrams (integer, no floats)
    int64_t     bond_sost_stocks;   // bond in stocks (integer)
    uint16_t    duration_months;    // 1, 3, 6, 9, or 12
    int64_t     start_height;       // block height at registration
    int64_t     end_height;         // block height at expiry
    uint16_t    bond_pct;           // bond percentage × 100 (e.g., 2500 = 25%)
    uint8_t     reputation_stars;   // 0, 1, 3, or 5
    uint8_t     status;             // 0=ACTIVE, 1=COMPLETED, 2=SLASHED, 3=EXPIRED

    // Frozen price reference (from bulletin at creation)
    int64_t     sost_price_usat;    // SOST price in micro-USD (integer)
    int64_t     gold_price_usat;    // gold/oz price in micro-USD (integer)
};

// PoPC audit record
struct PoPCAudit {
    Hash256     commitment_id;
    int64_t     audit_height;       // block height that triggered audit
    Hash256     entropy_seed;       // SHA256(block_id || commit || checkpoints_root)
    bool        passed;
    int64_t     balance_observed_mg; // gold balance observed (milligrams)
    int64_t     timestamp;
};

// Reputation
struct PoPCReputation {
    PubKeyHash  user_pkh;
    uint8_t     stars;              // 0, 1, 3, 5
    uint16_t    contracts_completed;
    uint16_t    contracts_slashed;
    bool        blacklisted;
};

// Bond sizing table (constitutional — from whitepaper Section 6.5)
// ratio = sost_price / gold_oz_price
// Returns bond percentage × 100
static uint16_t bond_pct_from_ratio(double ratio) {
    if (ratio < 0.0001) return 1200;   // 12%
    if (ratio < 0.001)  return 1500;   // 15%
    if (ratio < 0.01)   return 2000;   // 20%
    if (ratio < 0.1)    return 2500;   // 25%
    if (ratio < 0.2)    return 2600;   // 26%
    if (ratio < 0.3)    return 2700;   // 27%
    if (ratio < 0.4)    return 2800;   // 28%
    if (ratio < 0.5)    return 2900;   // 29%
    return 3000;                        // 30% maximum
}

// Reward table (operational — from whitepaper Section 6.7)
// Returns reward percentage × 100
static uint16_t reward_pct_from_duration(uint16_t months) {
    switch (months) {
        case 1:  return 100;    // 1%
        case 3:  return 400;    // 4%
        case 6:  return 900;    // 9%
        case 9:  return 1500;   // 15%
        case 12: return 2200;   // 22%
        default: return 0;
    }
}
```

---

## 5. New Transaction Types

No new consensus tx types needed. The existing infrastructure is sufficient:

| Existing Type | Use in PoPC |
|---------------|-------------|
| BOND_LOCK (0x10) | Lock SOST bond with `lock_until` height |
| ESCROW_LOCK (0x11) | Lock with beneficiary (for slash distribution) |
| TRANSFER (0x00) | Reward distribution from PoPC Pool |

The PoPC registration, audit, and slash logic is **application-layer**, not consensus-layer — as specified in the whitepaper: *"No consensus changes. All PoPC logic remains operational/application-layer except that the PoPC Pool receives 25% coinbase by consensus."*

---

## 6. Distribution Mathematics

```
REWARD CALCULATION:
  base_reward = bond_sost × reward_table[duration]
  protocol_fee = base_reward × 0.05
  user_reward = base_reward - protocol_fee

  User receives: bond_sost + user_reward
  Foundation receives: protocol_fee

SLASH DISTRIBUTION:
  50% of slashed bond → PoPC Pool (funds future rewards)
  50% of slashed bond → Gold Vault (buys more gold)

POOL SUSTAINABILITY:
  Pool income per block: ~1.963 SOST (25% of subsidy)
  Pool income per year: ~103,000 SOST

  Maximum payout example (if 100 contracts of 6.75 SOST bond, 12-month):
    Total bonds: 675 SOST
    Total rewards: 675 × 0.22 = 148.5 SOST
    Pool needs: 148.5 SOST/year
    Pool income: 103,000 SOST/year
    Sustainability ratio: 694:1 (very sustainable)
```

---

## 7. Activation Timeline

### Whitepaper statement:
*"Q1 2027 — PoPC Model A + B launch on Ethereum mainnet."* (line 2219)

The whitepaper targets Q1 2027 for PoPC launch. There is NO "90-day post-genesis" hard requirement for PoPC. The 90-day references in the whitepaper are for the **dissolution dead-man switch** (if the chain dies for 90 days), NOT for PoPC activation.

### Code status:
- BOND_LOCK activation: height 5000 (already passed if chain is at ~1800)
  - Wait — height 5000 has NOT been reached yet at ~1800 blocks
- BOND_LOCK and ESCROW_LOCK become valid at height 5000

### Can PoPC be activated earlier than Q1 2027?
**Technically yes** — the bond/escrow tx types activate at height 5000 (approximately block 5000 ÷ 6 blocks/hour = ~35 days from genesis = ~April 19, 2026).

However, the FULL PoPC system (Ethereum verification, audit system, reputation, Foundation signing) requires:
1. Ethereum smart contract deployment (for Model B escrow)
2. Foundation signing key (EIP-712)
3. Price Bulletin infrastructure
4. Audit watcher service
5. Reputation database

**Recommendation:** Bond locking can start at height 5000 (on-chain, no external dependency). Full PoPC with Ethereum verification should target Q4 2026 at earliest.

---

## 8. Security Analysis

### Vector 1: Fake Gold Declaration
**Attack:** User claims to hold XAUT but doesn't.
**Mitigation:** Audit system verifies `balanceOf(user_eth_wallet)` via Ethereum RPC. Continuous custody check samples historical balances. If balance ever dropped below commitment → slash.
**Residual risk:** LOW — Ethereum balance is publicly verifiable.

### Vector 2: Borrowed Gold (Flash Loan Style)
**Attack:** User borrows XAUT only during audit, returns it after.
**Mitigation:** Continuous custody check verifies balance at multiple deterministic checkpoints across the period, not just at audit time. Flash loans only work within a single transaction.
**Residual risk:** LOW — checkpoint sampling prevents just-in-time borrowing.

### Vector 3: Sybil Attack (Multiple Accounts)
**Attack:** Same person, multiple Ethereum wallets, each with small gold.
**Mitigation:** Reputation system limits new participants to 0.5 oz max. Economic cost: each sybil account requires its own SOST bond. Reputation progression is slow (1→3→5 contracts).
**Residual risk:** MEDIUM — possible but economically expensive.

### Vector 4: Smart Contract Wallet Masquerading as EOA
**Attack:** Use CREATE2 to deploy code at a previously-EOA address.
**Mitigation:** EOA check at every audit (`extcodesize == 0`). If code detected → automatic slash.
**Residual risk:** LOW.

### Vector 5: Foundation Malicious Pricing
**Attack:** Foundation publishes manipulated Price Bulletin.
**Mitigation:** Dual consent — user must sign the bond terms. User can reject unfavorable pricing. Bulletin sources are public and reproducible.
**Residual risk:** LOW.

### Vector 6: Replay Attack
**Attack:** Reuse old commitment signature.
**Mitigation:** Nonce + expiry in bond terms. Contract checks freshness.
**Residual risk:** NEGLIGIBLE.

### Vector 7: Double Claim (Same Gold, Two Contracts)
**Attack:** Use same XAUT to back two PoPC commitments.
**Mitigation:** Registry tracks (eth_wallet, gold_token) pairs. Same wallet can only have one active commitment per gold token.
**Residual risk:** LOW.

### Vector 8: PoPC Pool Depletion
**Attack:** Too many successful contracts drain the pool.
**Mitigation:** Pool income (103K SOST/year) vastly exceeds expected payouts. Reputation limits cap individual exposure. Reward rates are operational (can be adjusted with 30-day notice).
**Residual risk:** LOW (sustainability ratio 694:1).

---

## 9. Implementation Plan

### Phase 1: On-Chain Foundation (READY — already exists)
- [x] BOND_LOCK transaction type
- [x] ESCROW_LOCK transaction type
- [x] PoPC Pool accumulation (25% coinbase)
- [x] Lock/unlock validation rules
- [x] CLI bond/escrow commands

### Phase 2: PoPC Registry (estimated: 2-3 weeks)
- [ ] `include/sost/popc.h` — data structures
- [ ] `src/popc_registry.cpp` — commitment storage, lookup
- [ ] RPC methods: `popc_register`, `popc_status`, `popc_list`
- [ ] Persistence: SQLite or JSON file for commitment records

### Phase 3: Audit System (estimated: 2-3 weeks)
- [ ] Entropy derivation from ConvergenceX block headers
- [ ] Audit trigger logic (reputation-based probability)
- [ ] Ethereum RPC verification (balance check via HTTP)
- [ ] Continuous custody checkpoint verification
- [ ] Audit result recording

### Phase 4: Slash & Reward (estimated: 1-2 weeks)
- [ ] Slash execution (bond confiscation, distribution)
- [ ] Reward calculation and distribution from PoPC Pool
- [ ] Protocol fee (5%) to Foundation
- [ ] Reputation update (stars, blacklist)

### Phase 5: Foundation Infrastructure (estimated: 2-3 weeks)
- [ ] Price Bulletin system (daily publication)
- [ ] EIP-712 signing key management
- [ ] Foundation signature verification
- [ ] Web interface for commitment creation

### Phase 6: Testing & Audit (estimated: 2-4 weeks)
- [ ] Unit tests for all PoPC components
- [ ] Integration tests (full commitment lifecycle)
- [ ] Security review of attack vectors
- [ ] Testnet deployment

**Total estimated: 10-16 weeks of development**

---

## 10. Effort Estimation

| Component | Effort | Priority |
|-----------|--------|----------|
| PoPC data structures (popc.h) | 1 day | HIGH |
| PoPC registry (storage/lookup) | 3 days | HIGH |
| RPC methods (register/status/list) | 2 days | HIGH |
| Audit entropy derivation | 2 days | HIGH |
| Ethereum RPC verification | 3 days | MEDIUM |
| Continuous custody checking | 3 days | MEDIUM |
| Slash mechanism | 2 days | HIGH |
| Reward distribution | 2 days | HIGH |
| Reputation system | 1 day | MEDIUM |
| Price Bulletin system | 3 days | MEDIUM |
| EIP-712 signing | 2 days | MEDIUM |
| Web UI for commitments | 5 days | LOW |
| Test suite | 5 days | HIGH |
| **TOTAL** | **~34 days** | |

---

## CTO Recommendation

1. **Bond locking is ready NOW** — height 5000 will activate BOND_LOCK and ESCROW_LOCK
2. **Full PoPC Model A needs 10-16 weeks** of development
3. **Start with Phase 2 (Registry)** — can launch a "commitment preview" where users lock bonds while the audit system is built
4. **Target full PoPC: Q4 2026** — realistic given the scope
5. **Do NOT rush** — the security analysis shows this system is well-designed but complex. Better to launch solid than fast

---

## Document History
- 2026-03-28: Initial specification — NeoB

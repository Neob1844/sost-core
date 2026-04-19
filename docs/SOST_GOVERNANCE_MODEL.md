# SOST Governance Model

**Date:** 2026-03-25
**Status:** Analysis document — describes current state and recommends future direction

---

## Executive Summary

SOST has a clear but informal governance model: **constitutional rules are immutable at genesis; operational changes are deployed as height-gated hard forks by the developer, coordinated informally.** There is no on-chain signaling mechanism. The block header has a version field (currently fixed at 1) that could support future BIP9-style signaling but is not used for governance.

With a single miner and single node, the current flag-day model works correctly. As the network grows, a more formal process will be needed. This document defines what's constitutional, what's operational, and recommends a phased governance upgrade path.

---

## 1. Current Consensus Architecture

### 1.1 Validation Layers

| Layer | Function | Rules |
|-------|----------|-------|
| **L1** | Block structure | Size, tx count, coinbase position |
| **L2** | Header context | Prev-link, timestamps/MTP, expected bitsQ difficulty |
| **L3** | Transaction consensus | Fees, subsidy, coinbase split, UTXO semantics |
| **L4** | Atomic UTXO connect | Connect/disconnect with BlockUndo for reorgs |

### 1.2 Transaction Validation Rules

| Category | Rules | Scope |
|----------|-------|-------|
| **R-rules (R1-R14)** | Structural | Version, types, counts, amounts, size, payload |
| **S-rules (S1-S12)** | Spend | UTXO lookup, PKH match, ECDSA verify, fees, maturity |
| **CB-rules (CB1-CB10)** | Coinbase | Output order, exact subsidy split, constitutional addresses |

### 1.3 Chain Selection

- **Best chain by cumulative work** (NOT longest chain)
- `work_per_block = floor(2^256 / (target + 1))`
- **MAX_REORG_DEPTH = 500 blocks** (~3.5 days)
- **Hard checkpoints**: genesis only (LAST_HARD_CHECKPOINT_HEIGHT = 0)

### 1.4 Block Header

```cpp
struct BlockHeader {
    uint32_t version;     // Currently fixed at 1
    Bytes32  prev_hash;
    Bytes32  merkle_root;
    int64_t  timestamp;
    uint32_t bits_q;      // Q16.16 difficulty
    uint32_t nonce;
    uint32_t extra_nonce;
    // ... ConvergenceX fields
};
```

**Version field exists** but is currently enforced as `version == 1`. This field COULD support BIP9-style signaling in the future without changing the header format.

---

## 2. Fork History

| Fork | Height | Type | Change | Date |
|------|--------|------|--------|------|
| **Multisig** | 2000 | Hard fork (feature activation) | OP_CHECKMULTISIG, sost3 addresses, P2SH | At genesis |
| **cASERT V2** | 1450 | Hard fork (parameter change) | Halflife 48h→24h, delta cap 6.25%→12.5% | ~2026-03-23 |
| **Bond/Escrow** | 5000 | Hard fork (feature activation) | BOND_LOCK, ESCROW_LOCK output types | Planned |
| **Capsule v1** | 5000 | Hard fork (feature activation) | Binary metadata in tx outputs | Planned |

All forks are **height-gated flag days**: the new rules activate at a specific block height, with no miner signaling or voting. All nodes must upgrade before the fork height.

---

## 3. Constitutional vs Operational Rules

### 3.1 Constitutional Rules (IMMUTABLE)

These rules are encoded at genesis and cannot be changed without breaking the social contract. Changing any of these would be equivalent to creating a new cryptocurrency.

| Rule | Value | Source | Why Immutable |
|------|-------|--------|---------------|
| Max supply | ~4,669,201 SOST | emission.h | Monetary policy |
| Emission formula | q = e^(-1/4) per epoch | emission.h | Monetary policy |
| Epoch length | 131,553 blocks | params.h | Emission schedule |
| Coinbase split | 50/25/25 | params.h, CB rules | Constitutional allocation |
| Gold Vault address | Hardcoded | params.h | Constitutional recipient |
| PoPC Pool address | Hardcoded | params.h | Constitutional recipient |
| Proof-of-Work | ConvergenceX | consensus | Sybil resistance mechanism |
| Target spacing | 600 seconds | params.h | Block time |
| Coinbase maturity | 1,000 blocks | params.h | Reorg safety |
| Minimum unit | 1 stock = 10^-8 SOST | params.h | Precision |
| Address format | sost1 (P2PKH), sost3 (P2SH) | address.h | Identity |
| No tail emission | Subsidy → 0 at epoch ~81 | emission.h | Hard cap enforcement |
| No minting function | No code path creates SOST outside coinbase | All sources | Supply integrity |

**The whitepaper states:** "No consensus governance exists. Monetary rules, emission schedules, coinbase splits, and constitutional constraints are immutable at genesis."

### 3.2 Operational Rules (CHANGEABLE with consensus)

These can be modified via hard fork to adapt the protocol to network conditions. Changing them does NOT change the economic model or social contract.

| Rule | Current Value | Can Change Via | Example |
|------|--------------|----------------|---------|
| cASERT halflife | 24h (V2) | Hard fork | Was 48h, changed at block 1450 |
| cASERT delta cap | 12.5% (V2) | Hard fork | Was 6.25% |
| cASERT profiles | E4-H35 active | Hard fork | Profile range expansion via 75% signaling |
| Anti-stall parameters | Various | Hard fork | Thresholds, decay rates |
| Multisig max keys | 15 | Hard fork | Could increase |
| Script opcodes | Current set | Hard fork | Could add new opcodes |
| Capsule format | v1 (12B header) | Hard fork | Could add new capsule types |
| RBF/CPFP policy | Current | Relay policy | No consensus change needed |
| Fee policies | 1 stock/byte min | Relay policy | No consensus change needed |
| P2P parameters | Various | Software update | Ban thresholds, peer limits |
| Checkpoint list | Genesis only | Software update | Add new checkpoints |

### 3.3 Grey Area

| Rule | Status | Discussion |
|------|--------|-----------|
| MAX_REORG_DEPTH (500) | Semi-constitutional | Protects finality. Reducing is dangerous. |
| Block size (1,000,000 bytes) | Operational | Could be increased with consensus |
| MAX_TX_BYTES (100,000) | Operational | Could be changed |
| MTP window (11 blocks) | Operational | Changing affects timestamp gaming |
| Future timestamp drift (600s) | Operational | Changing affects timestamp gaming |

---

## 4. Current Governance Mechanism

### How Changes Happen Today

1. **Developer proposes change** (NeoB, currently sole developer)
2. **Code is written** with height-gated activation
3. **Binary is compiled and deployed** to VPS node + miner
4. **Block reaches activation height** → new rules take effect
5. **No signaling, no voting, no external coordination**

This is a **benevolent dictator** model, identical to early Bitcoin (Satoshi unilaterally deployed changes) and current Monero (developers coordinate hard forks every 6 months).

### Why This Works Now

- 1 node, 1 miner → no coordination problem
- Developer has full context on all changes
- No risk of chain split (nobody else is running a node)
- Fast iteration during bootstrap phase

### Why This Won't Scale

- When external miners join, they must be notified of upgrades
- If a miner doesn't upgrade → chain split
- No mechanism to measure readiness before activation
- No way for miners to reject a proposed change

---

## 5. Comparison with Other Projects

| Project | Mechanism | Threshold | Period | Notes |
|---------|-----------|-----------|--------|-------|
| **Bitcoin** | BIP9 miner signaling | 95% | 2016 blocks | Slow, conservative, tested |
| **Bitcoin Cash** | Flag day (height) | N/A | N/A | Developer-coordinated, no signaling |
| **Ethereum** | Hard fork (developer-led) | N/A | ~annual | Coordinated via EIPs |
| **Monero** | Hard fork (developer-led) | N/A | ~6 months | Scheduled, frequent |
| **Litecoin** | BIP9 (borrowed from Bitcoin) | 75% | 2016 blocks | Lower threshold than BTC |
| **SOST (current)** | Flag day (height) | N/A | N/A | Identical to BCH/Monero |

**SOST most resembles:** Bitcoin Cash and early Monero. This is appropriate for the current network size.

---

## 6. Recommended Governance Path

### Phase 1: Bootstrap (NOW — <10 miners)

**Keep flag-day model.** It works. No signaling overhead.

**Add:**
- Document each fork in a "SOST Improvement Proposal" (SIP) format
- Publish SIPs on GitHub before activation
- Announce on BTCTalk with at least 2 weeks notice
- Include "activation height" and "last safe binary version" in announcements

**SIP format:**
```
SIP-001: cASERT V2 Parameter Adjustment
Status: ACTIVE (block 1450)
Type: Operational (parameter change)
Author: NeoB
Created: 2026-03-23
Activation: Block 1450

Summary: Reduce halflife from 48h to 24h, increase delta cap from 6.25% to 12.5%.
Rationale: Audit showed slow upward adjustment with V1 parameters.
Impact: Faster difficulty response. No effect on blocks < 1450.
```

### Phase 2: Growth (10-50 miners)

**Add version-bit signaling** (use existing block version field):

```
Block version field (32 bits):
  Bits 0-7:   Protocol version (currently 1)
  Bits 8-28:  Available for BIP9-style signaling (21 bits = 21 concurrent proposals)
  Bits 29-31: Reserved
```

**Signaling rules:**
- Signal period: 1000 blocks (~7 days)
- Activation threshold: 75% of blocks in period must signal
- Lock-in period: 1000 blocks after threshold met
- Grace period: 1000 blocks after lock-in before enforcement

**This requires a consensus change** (version validation must allow bits 8-28 to vary). Implement as SIP-002 when the first external miner is active.

### Phase 3: Maturity (50+ miners)

**Raise threshold to 90%** for constitutional-adjacent changes (block size, reorg depth). Keep 75% for operational changes (difficulty parameters, new opcodes).

**Add node signaling** via P2P user-agent string (informational, not consensus-critical).

---

## 7. Emergency Mechanisms

### Already Defined (Whitepaper)

- **Emergency Catastrophe Procedure:** For Heritage Reserve — requires ≥75% miner signaling + Foundation Execution Order. This is the only mechanism that references miner signaling.

### Not Yet Defined (Recommended)

- **Dead Man Switch:** If no block is mined for 30 days, consider the chain inactive. Foundation publishes final state and UTXO snapshot.
- **Emergency Parameter Override:** If the chain is stuck (no blocks for >7 days despite miners attempting), Foundation can publish a binary with adjusted parameters. This is already how cASERT V2 was deployed — formalize it.

---

## 8. What's Missing

| Gap | Risk | Priority |
|-----|------|----------|
| No formal SIP process | Low (1 developer) | Create SIP template now |
| No miner signaling | Low (1 miner) | Implement at Phase 2 |
| No node version tracking | Low | Add user-agent version to P2P |
| Version field unused | None (works fine) | Reserve for future signaling |
| No formal fork announcement process | Medium | Publish on BTCTalk/GitHub |
| Checkpoints only at genesis | Low | Add checkpoints at key heights |

---

## 9. CTO Recommendation

### Do Now
1. Create `docs/SIP/` directory for improvement proposals
2. Write SIP-001 (cASERT V2) and SIP-002 (Multisig activation) retroactively
3. Add governance section to website (sost-security.html or new page)
4. Add checkpoints at blocks 1000 and 1450

### Do When First External Miner Joins
5. Announce flag-day forks 2+ weeks in advance on BTCTalk and GitHub
6. Plan SIP-003: version-bit signaling implementation

### Do When 10+ Miners Are Active
7. Implement BIP9-style signaling with 75% threshold
8. Require signaling for all future consensus changes

### Never Do
- Do NOT change the constitutional rules (supply, emission, split)
- Do NOT add on-chain governance tokens or DAO voting
- Do NOT allow arbitrary parameter changes without height-gated activation
- Do NOT remove the version field or change its position in the header

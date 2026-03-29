# Fork Mechanism and Future Consensus Changes

**Date:** 2026-03-29
**Author:** NeoB (CTO)
**Status:** Analysis document

---

## 1. How SOST Consensus Works Today

### Chain Selection
- **Best chain by cumulative work** (NOT longest chain by height)
- `work_per_block = floor(2^256 / (target + 1))`
- Implemented in `sost-node.cpp:2317` — "Fork-aware chain acceptance using cumulative work"
- `MAX_REORG_DEPTH = 500 blocks` (~3.5 days)
- Hard checkpoints at blocks 0, 500, 1000, 1500

### Block Header
```
uint32_t version;        // Currently fixed at 1 — COULD support future signaling
Bytes32  prev_hash;
Bytes32  merkle_root;
int64_t  timestamp;
uint32_t bits_q;         // Q16.16 difficulty
uint32_t nonce;
uint32_t extra_nonce;
Bytes32  commit;         // ConvergenceX commit
Bytes32  checkpoints_root;
int8_t   stab_profile_index;  // cASERT equalizer profile
```

**Key:** The `version` field (32 bits) exists in every block but is currently hardcoded to 1. Bits 8-28 are available for BIP9-style signaling without changing the header format.

### Validation Layers
- **L1:** Block structure (size, tx count, coinbase at tx[0])
- **L2:** Header context (prev-link, timestamp/MTP, difficulty)
- **L3:** Transaction consensus (R1-R16, S1-S12, CB1-CB10)
- **L4:** Atomic UTXO connect with BlockUndo for reorgs

### Current Network
- **Nodes:** 1 (VPS at sostcore.com)
- **Miners:** 1 (NeoB on WSL)
- **Chain height:** ~1,900
- **External participants:** 0

---

## 2. How Changes Are Activated (Flag Day)

All changes so far use **height-gated flag days** — new rules activate at a specific block height. No signaling, no voting, no coordination needed (because there's 1 miner).

### Fork History

| Fork | Height | Type | Change | Date |
|------|--------|------|--------|------|
| Genesis | 0 | — | All constitutional rules | 2026-03-15 |
| **cASERT V2** | 1450 | Hard fork (parameter) | Halflife 48h→24h, delta cap 6.25%→12.5% | ~2026-03-23 |
| **Multisig P2SH** | 2000 | Hard fork (feature) | OP_CHECKMULTISIG, sost3 addresses | Pending |
| **Bond/Escrow/Capsule** | 5000 | Hard fork (feature) | BOND_LOCK, ESCROW_LOCK, Capsule Protocol v1 | Pending |

### How It Works in Code

```cpp
// consensus_constants.h
inline constexpr int64_t BOND_ACTIVATION_HEIGHT_MAINNET = 5000;
inline constexpr int64_t CASERT_V2_FORK_HEIGHT = 1450;

// tx_validation.cpp — height-gated check
if (height >= bond_activation_height) {
    // New rules active
}

// params.h — cASERT V2
int64_t halflife = (next_height >= CASERT_V2_FORK_HEIGHT) ? BITSQ_HALF_LIFE_V2 : BITSQ_HALF_LIFE;
```

No miner signaling. No version check. Pure height comparison. If a node doesn't upgrade before the fork height, it silently follows incorrect rules and forks off.

---

## 3. Majority Requirements

### Today (1 miner, 1 node)
- **100% = you.** The developer writes the code, deploys it, and mines the blocks.
- No coordination problem exists.
- Flag day is perfectly adequate.

### Future (10+ miners)

| Scenario | Risk | Mitigation |
|----------|------|-----------|
| External miner doesn't upgrade before height 5000 | Their blocks after 5000 may be invalid (if they create BOND_LOCK outputs without the validation rules) or they may reject valid blocks | Announce 2+ weeks in advance, check node versions via P2P |
| Miner intentionally rejects a fork | Chain split — they mine a minority chain | Most-work-wins will resolve; minority chain dies without hashrate |
| 50% of hashrate doesn't upgrade | Real chain split with significant minority | This is the classic hard fork problem — requires coordination |

### When Signaling Becomes Necessary
- **<10 miners:** Flag day is fine. Announce on BTCTalk/Telegram.
- **10-50 miners:** Should implement version-bit signaling. 75% threshold.
- **50+ miners:** Require 90% signaling for anything constitutional-adjacent.

---

## 4. Future Features Requiring Consensus Changes

### From the Whitepaper (Section 10)

| Feature | WP Section | Change Type | Consensus? | Estimated Effort | Priority | Status |
|---------|-----------|-------------|-----------|-----------------|----------|--------|
| **H10-H12 profile activation** | 3.12 | Hard fork (parameter) | YES — increase CASERT_H_MAX from 9 to 12 | 1 day | LOW | Reserved in code, not active |
| **Native metal tokens (TOKEN_ISSUE, TOKEN_TRANSFER)** | 10.2 Phase 2 | Hard fork (new output types) | YES — new output type validation | 3-6 months | MEDIUM | Not started. Output types not reserved. |
| **Fully native PoPC** | 10.2 Phase 3 | Hard fork (validation rules) | YES — on-chain audit verification | 3-6 months | LOW | Depends on Phase 2 |
| **Additional metals (silver, platinum)** | 1.3 (allowlist) | Soft fork | NO — operational (Foundation can add issuers) | N/A | LOW | No code change needed |
| **ConvergenceX v2.0 dataset** | 3.7 | Hard fork (PoW change) | YES — changes mining algorithm | 6+ months | LOW | Described in WP, not planned |

### Not in Whitepaper but Foreseeable

| Feature | Change Type | Consensus? | Effort | Priority | Notes |
|---------|-------------|-----------|--------|----------|-------|
| **Post-quantum signatures** | Hard fork | YES — new signature scheme | 6-12 months | VERY LOW (2028+) | Would require migrating from secp256k1 to SPHINCS+/Dilithium |
| **Schnorr signatures** | Hard fork | YES — new opcode or sig type | 3-6 months | LOW | Batch verification, key aggregation |
| **Version-bit signaling (BIP9)** | Hard fork | YES — version field validation | 2-4 weeks | MEDIUM | Needed when 10+ miners exist |
| **Dynamic block size** | Hard fork | YES — change MAX_BLOCK_BYTES | 1-2 weeks | LOW | Only if blocks fill up |
| **New script opcodes** | Hard fork | YES — script engine changes | 1-4 weeks each | LOW | OP_CHECKSEQUENCEVERIFY, OP_CAT, etc. |
| **Cross-chain bridge** | Application layer | NO — whitepaper explicitly says no bridge | N/A | NONE | "No trustless cross-chain mechanism is used" |
| **On-chain governance/voting** | Hard fork | YES | Months | NONE | Whitepaper explicitly forbids: "No ongoing parameter governance" |
| **Tail emission** | CONSTITUTIONAL VIOLATION | NO — NEVER | N/A | NEVER | "No tail emission. Subsidy → 0 at epoch ~81." |

### What CANNOT Be Changed (Constitutional)

These are immutable by the social contract defined in the whitepaper:

| Rule | Why Immutable |
|------|---------------|
| Max supply (~4.669M SOST) | Monetary policy — changing this creates a different currency |
| Emission formula (q = e^(-1/4)) | Monetary policy |
| Coinbase split (50/25/25) | Constitutional allocation |
| Gold Vault / PoPC Pool addresses | Constitutional recipients |
| No minting outside coinbase | Supply integrity |
| No token burning | "No destruction mechanism exists or is planned" |
| ConvergenceX as PoW family | Sybil resistance mechanism |

---

## 5. Soft Fork vs Hard Fork Analysis

### What Can Be Soft Forked (Backward Compatible)

Soft forks add NEW restrictions that old nodes don't enforce but don't violate. Old nodes see new blocks as valid (they just don't understand the new rules).

| Change | Soft Fork? | How |
|--------|-----------|-----|
| Tighter payload validation | YES | Old nodes accept any payload; new nodes reject invalid ones |
| New capsule types | YES | Old nodes ignore unknown capsule types |
| Stricter script validation | YES | Old nodes accept; new nodes reject |
| Lower MAX_BLOCK_BYTES | YES | Old nodes accept smaller blocks |
| Additional checkpoint enforcement | YES | Old nodes don't check; new nodes do |
| Tighter fee policies | Relay policy only | Not consensus — just relay filtering |

### What Requires Hard Fork

| Change | Why Hard Fork |
|--------|---------------|
| New output types (TOKEN_ISSUE, etc.) | Old nodes reject unknown types (R11) |
| Increase CASERT_H_MAX | Old nodes reject profiles > H9 |
| Change PoW algorithm parameters | Old nodes reject invalid PoW |
| Change signature scheme | Old nodes can't verify new signatures |
| Increase MAX_BLOCK_BYTES | Old nodes reject larger blocks |
| Version-bit signaling | Old nodes reject version != 1 |

---

## 6. Recommendations

### 1. Flag Day Remains Primary Mechanism
With 1 miner and 1 node, flag day works perfectly for immediate changes.

### 2. Version-Bit Signaling: IMPLEMENTED
- `include/sost/proposals.h` — BIP9-style signaling framework
- 75% threshold over 288-block window (~48 hours)
- Foundation quality vote: +10% weight (29 blocks), expires automatically and irrevocably at end of Epoch 2 (block 263,106, ~5 years). Foundation may relinquish earlier but cannot extend.
- RPC command: `getproposals` shows current signaling status
- Placeholder proposal: Post-Quantum Migration (bit 8, DEFINED status)
- **Ready for activation when first external miner joins**

### 3. Minimum Version in P2P: Add at Phase 2
- When connecting to a peer, exchange version information
- If peer version < minimum required for next fork → warn (don't disconnect)
- This is already partially implemented via `p2p_send_version()`

### 4. Prepare Extensibility Now (Free)

These cost nothing to implement and prevent future hard fork complexity:

| Preparation | Benefit | Effort |
|-------------|---------|--------|
| Reserve output types 0x12-0x1F | No code change — just documentation | 0 |
| Reserve tx_types 0x02-0x0F | No code change — just documentation | 0 |
| Document version field bit allocation | Future signaling ready | 1 hour |
| Reserve opcodes 0xB0-0xFF in script engine | Future soft-fork ready | 0 |

### 5. What to Prepare NOW for Planned Features

| Feature | Preparation | When to Implement |
|---------|-------------|-------------------|
| H10-H12 activation | Code exists, just increase CASERT_H_MAX | When hashrate demands it |
| Native metal tokens | Reserve output types 0x30-0x3F | Phase 2 (Q4 2027) |
| Version-bit signaling | Document bit allocation | When 10+ miners exist |
| Post-quantum | Monitor NIST standardization | 2028+ earliest |

### 6. Timeline

| Phase | When | Action |
|-------|------|--------|
| **Now** | Block ~1900 | Document reserved types. Publish SIP format. Flag day works. |
| **Block 2000** | ~April 2026 | Multisig activates. Announce on BTCTalk 2 weeks before. |
| **Block 5000** | ~April 2026 | Bond/Escrow/Capsule activates. Major announcement. |
| **First external miner** | 2026 | Implement P2P version exchange. Plan version-bit signaling. |
| **10+ miners** | 2027? | Implement BIP9-style signaling (SIP-003). 75% threshold. |
| **Phase 2 tokens** | Q4 2027 | Hard fork: new output types for native metal tokens. |
| **50+ miners** | 2028? | Raise threshold to 90% for constitutional-adjacent changes. |

---

## 7. Emergency Mechanisms

### Already Defined (Whitepaper)
- **Emergency Catastrophe Procedure:** Heritage Reserve access requires >= 75% miner signaling over 144-block window + Foundation Execution Order. This is the ONLY mechanism that references miner signaling in the current protocol.

### Recommended Additions
- **Chain Stall Recovery:** If no block for 7+ days, Foundation publishes emergency binary with adjusted cASERT parameters (precedent: cASERT V2 was deployed reactively)
- **Dead Man Switch:** If no block for 30 days, Foundation publishes final UTXO snapshot and declares chain inactive

---

## Summary

SOST uses **height-gated flag days** for all consensus changes, identical to Bitcoin Cash and early Monero. This is correct for the current 1-miner, 1-node network. The block header version field (32 bits) provides a ready pathway to BIP9-style signaling when the network grows. All constitutional rules (supply, emission, split) are immutable. Operational rules (difficulty parameters, feature activation, new types) can be changed via hard fork with appropriate coordination.

**Key insight:** The biggest risk is not "how do we coordinate a fork" but "nobody else is mining yet." The fork mechanism works. The adoption mechanism is what needs work.

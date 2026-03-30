# SOST Protocol — Known Risks and Mitigations

**Date:** 2026-03-30
**Status:** Honest disclosure — updated continuously

---

## 1. Single Miner Risk

- **Status:** ACKNOWLEDGED
- **Impact:** If the sole miner goes offline, block production stops
- **Mitigation:** cASERT anti-stall decay allows recovery when miner returns. Chain data is preserved on disk. No blocks are lost — production simply pauses and resumes.
- **Resolution:** Community mining participation after public launch

---

## 2. No External Audit

- **Status:** ACKNOWLEDGED
- **Impact:** Undiscovered vulnerabilities may exist
- **Mitigation:** 27 test suites (616 individual tests), internal code review, continuous testing
- **Resolution:** External audit planned when funding allows. Community bug bounty at launch.
- **Disclosure:** The BTCTalk announcement explicitly states this risk

---

## 3. Etherscan Dependency

- **Status:** MITIGATED
- **Impact:** If Etherscan API changes, PoPC verification could break
- **Mitigation:** Multi-provider fallback (Etherscan V2 → Infura → Alchemy → public RPCs). Direct eth_call to ERC-20 contracts — works without any API key. Double-verification rule (2 consecutive failures on different days required before slash — transient outages do not trigger slashing).
- **Resolution:** No single point of failure. System operates without any API key via public RPCs.

---

## 4. Arbitrary SOST Price

- **Status:** ACKNOWLEDGED
- **Impact:** Bond calculations use $1.00 placeholder price
- **Mitigation:** Price is configurable in config/popc_pricing.json. Dynamic PUR system adjusts rewards automatically.
- **Resolution:** Updated when SOST trades on exchanges
- **Note:** The system works at ANY price — bonds are proportional to gold value

---

## 5. Gold Vault Security

- **Status:** CONSENSUS PROTECTED (from block 5000)
- **Impact:** Even with the private key, unauthorized spends are REJECTED by all nodes
- **Protection (4 rules, activated at block 5000):**
  - **GV1:** Gold purchases (marked payload) → allowed without vote
  - **GV2:** ≤10% monthly operational → allowed without vote
  - **GV3:** >10% or non-standard → requires 75% miner signaling (Epoch 0-1) or 95% (Epoch 2+)
  - **GV4:** No rule matched → REJECTED by ALL nodes
- **Foundation quality vote:** +10% equivalent until Epoch 2 (block 263,106). Expires automatically.
- **Key theft scenario:** Attacker steals key → tries to send to random address → GV4 rejects → funds safe
- **Additional protection:** AES-256 encryption, policy-level alerts, offline key storage

---

## 6. PoPC Pool Depletion

- **Status:** MITIGATED
- **Impact:** If too many participants, pool may not cover all rewards
- **Mitigation:** Dynamic PUR system (Pool Utilization Ratio) automatically reduces rewards as pool fills. Reservation mechanism guarantees rewards at registration. Anti-whale tiers limit large positions. Maximum 10 releases per day via auto-distribution.
- **Resolution:** Self-regulating — no manual intervention needed

---

## 7. Feature Activation Risk

- **Status:** MITIGATED
- **Impact:** Features activating at block 5000 could contain bugs
- **Mitigation:** All features (Bond Lock, Escrow Lock, Capsule Protocol) have dedicated test suites. Activation is by height — predictable and testable. Current chain height ~1900, giving time for additional testing.
- **Resolution:** Features can be tested on testnet before mainnet activation

---

## 8. P2P Network (Single Node)

- **Status:** ACKNOWLEDGED
- **Impact:** Single node = single point of failure for network access
- **Mitigation:** Chain data survives node restarts. Systemd auto-restart configured.
- **Resolution:** Additional nodes as community grows

---

## 9. No On-Chain Governance

- **Status:** BY DESIGN
- **Impact:** Changes require developer coordination (benevolent dictator model)
- **Mitigation:** Version-bit signaling implemented (75% threshold, 288-block window). Foundation quality vote with constitutional expiry (Epoch 2, ~5 years). SIP format documented.
- **Resolution:** Governance scales with network: flag day now → signaling with 10+ miners → full signaling with 50+

---

## 10. Experimental Status

- **Status:** FUNDAMENTAL
- **Impact:** SOST is experimental, unaudited software. Loss of funds is possible.
- **Mitigation:** All documentation states this clearly. BTCTalk disclaimer is comprehensive.
- **Resolution:** Time, testing, and community review reduce risk over time. Nothing replaces this process.

---

## Document History

- 2026-03-30: Initial version — NeoB

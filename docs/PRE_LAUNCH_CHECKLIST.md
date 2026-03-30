# SOST Protocol — Pre-Launch Checklist

**Target Date:** June 16, 2026
**Author:** NeoB
**Status:** IN PROGRESS — reorganized by priority tier 2026-03-30

---

## TIER 1: CRITICAL (Required on launch day)

These must all be DONE before the BTCTalk announcement goes live.

### 1A. Core Protocol — DONE

- [x] All 22 CTest suites pass on clean build
- [x] Sighash computation identical between CLI and node (E6 bug fixed)
- [x] Genesis hash consistent across all binaries
- [x] Constitutional addresses (Gold Vault, PoPC Pool) verified correct in params.h
- [x] Coinbase output order enforced: [0]=miner, [1]=gold, [2]=popc
- [x] Subsidy calculation matches emission schedule for blocks 0-10,000
- [x] LOW-S signature enforcement active
- [x] MAX_REORG_DEPTH = 500 verified
- [x] cASERT V2 active (blocks ≥1450): 24h halflife, 12.5% delta cap
- [x] RBF (Replace-by-Fee) functional
- [x] CPFP (Child-Pays-for-Parent) functional
- [x] HD wallet BIP39 seed generation verified
- [x] Address format: `sost1` + 40 hex chars verified

### 1B. Mining — DONE

- [x] ConvergenceX PoW produces valid blocks
- [x] Mining with `--address` flag works correctly
- [x] Miner submits blocks via RPC successfully
- [x] Difficulty adjusts correctly (cASERT V2)
- [x] Anti-stall zones activate on prolonged gaps
- [x] Block template includes correct coinbase split (50/25/25)

### 1C. Wallet & CLI — DONE

- [x] `sost-cli send` creates and broadcasts valid transactions
- [x] `sost-cli balance` shows correct balance
- [x] `sost-cli createtx` signs with correct sighash
- [x] UTXO sync from node works (`getaddressutxos` RPC)
- [x] Coinbase maturity enforced (1000 blocks)
- [x] Encrypted wallet (AES-256-GCM + scrypt) save/load works
- [x] HD wallet seed import/export works

### 1D. Explorer & Node — DONE

- [x] Node listens on port 19333 (P2P), serves JSON-RPC on port 18232
- [x] Mempool accepts valid transactions, rejects invalid
- [x] Fee-rate ordering in mempool verified
- [x] Explorer functional on sostcore.com
- [x] Explorer functional on sostprotocol.com (RPC fallback)
- [x] Block detail and TX detail overlays show real data from RPC
- [x] Node stable under sustained mining (OOM Killer resolved, zombie cleanup, auto-recovery)

### 1E. Infrastructure — DONE

- [x] VPS (212.132.108.244) running latest code
- [x] nginx proxying /rpc correctly on both domains
- [x] SSL certificates valid for sostcore.com + sostprotocol.com
- [x] UFW firewall: only 19333, 80, 443 open
- [x] systemd services: sost-node, sost-miner configured and enabled
- [x] Auto-restart on crash configured

---

## TIER 2: ACTIVE BUT NOT CRITICAL (Block 5000 activation)

These are implemented and tested but activate later. Monitor — no action needed at launch.

### 2A. PoPC Model A — IMPLEMENTED

- [x] PoPC pool funded (25% of every coinbase)
- [x] popc_etherscan_checker.py operational — multi-provider fallback (Etherscan V2 → Infura → Alchemy → public RPCs)
- [x] Double-verification rule: 2 consecutive failures required before slash (no transient API outage can trigger slash)
- [x] Auto-distribution script (max 10 releases/day)
- [x] SOST price reference: $1.00 placeholder — update when exchange listing occurs
- [ ] First external PoPC participant registered

### 2B. Capsule Protocol v1 — IMPLEMENTED

- [x] Activation height set (block 5000 mainnet)
- [x] 12-byte header + 243-byte max body validated
- [x] Dedicated test suite passes
- [ ] Test capsule TX broadcast before block 5000 (on testnet or early mainnet)

### 2C. Bond Lock & Feature Activation — IMPLEMENTED

- [x] Bond Lock activates at block 5000
- [x] P2SH multisig activates at block 2000 (current height ~1900 — imminent)
- [x] PSBT offline signing functional
- [x] All feature activation heights verified in params.h

---

## TIER 3: POST-LAUNCH (After announcement, no hard deadline)

These improve the protocol but are not required on launch day.

### 3A. Security Hardening

- [ ] External security audit (planned when funding available)
- [ ] Community bug bounty program published
- [ ] Gold Vault multisig 2-of-3 migration (planned hard fork)
- [ ] RPC authentication for write methods on public endpoint
- [ ] nginx rate limiting on /rpc endpoint

### 3B. Version Signaling & Governance

- [ ] Version-bit signaling tested with 2+ nodes (75% threshold, 288-block window)
- [ ] SIP-0 (SOST Improvement Proposal format) published
- [ ] Governance model documented for community

### 3C. Platform Extensions

- [ ] GeaSpirit operator data access (gravity, AEM, drill holes) — see GEASPIRIT_CTO_NEXT_PHASE.md
- [ ] Materials Engine public API documentation
- [ ] Web wallet (browser-compatible HD wallet)
- [ ] PWA installable on mobile (service worker v62+)

### 3D. Code Recommendations (carry over)

| Feature | Priority | Effort | Status |
|---------|----------|--------|--------|
| Hardcoded checkpoints every 500 blocks | HIGH | 1 hour | NOT STARTED |
| `verify_supply` RPC method | HIGH | 3 hours | NOT STARTED |
| `--maintenance-mode` flag | MEDIUM | 2 hours | NOT STARTED |
| `getpeerinfo` RPC method | MEDIUM | 2 hours | NOT STARTED |
| Alert message system | LOW | 8 hours | NOT STARTED |
| Minimum peer version check | MEDIUM | 2 hours | NOT STARTED |

---

## TIER 4: STANDARD CHECKS (Launch week)

### Security & Secrets

- [ ] GitHub 2FA enabled
- [ ] No secrets in public repository (scan for tokens, passwords, keys)
- [ ] Constitutional private keys stored offline (air-gapped USB)
- [ ] VPS SSH key-only authentication (no password login)

### Backups

- [ ] Wallet backup (encrypted) on USB
- [ ] Constitutional key backup in physical safe
- [ ] Genesis block data backed up
- [ ] Chain data (blockchain) backed up weekly
- [ ] WSL is source of truth, VPS is copy, GitHub is copy #2

### Documentation

- [ ] Whitepaper published and accessible
- [ ] BTCTalk announcement ready (btctalk_ann.html reviewed)
- [ ] README complete with setup instructions
- [ ] KNOWN_RISKS_AND_MITIGATIONS.md reviewed and current
- [ ] EMERGENCY_RESPONSE_PLAN.md reviewed

### Emergency Readiness

- [ ] Emergency Response Plan reviewed and understood
- [ ] Supply verification procedure tested
- [ ] Binary integrity check procedure tested
- [ ] Recovery from VPS compromise procedure tested
- [ ] Hard fork procedure documented (FORK_MECHANISM_AND_FUTURE_CONSENSUS.md)

---

## Code Reference Snippets

### Checkpoint Implementation (recommended before launch)
```cpp
// include/sost/checkpoints.h
static const std::map<int64_t, std::string> CHECKPOINTS = {
    {0, "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37"},
    {500, "<hash_at_500>"},
    {1000, "<hash_at_1000>"},
    {1500, "<hash_at_1500>"},
    // Add more as chain grows
};
```

### Verify Supply RPC (recommended before launch)
Add `verifysupply` RPC method that:
1. Sums all UTXO values via `GetTotalValue()`
2. Computes theoretical emission via `sost_subsidy_stocks()` for blocks 0..height
3. Returns match/mismatch with exact values

---

## Sign-Off

| Check | Date | Verified By |
|-------|------|-------------|
| Consensus tests | | |
| Network tests | | |
| Security audit | | |
| Documentation | | |
| Emergency plan | | |
| Final sign-off | | NeoB |

---

**Document History**
- 2026-03-28: Initial version — NeoB
- 2026-03-30: Reorganized into priority tiers (Critical/Active/Post-Launch/Standard). Marked DONE items. Added PoPC double-verification, Gold Vault alert, and Known Risks doc as completed items.

# SOST Protocol — Pre-Launch Checklist

**Target Date:** June 16, 2026
**Author:** NeoB
**Status:** IN PROGRESS

---

## 1. CONSENSUS & SECURITY

- [ ] All 22 CTest suites pass on clean build
- [ ] Sighash computation identical between CLI and node (E6 bug fixed)
- [ ] Genesis hash consistent across all binaries
- [ ] Constitutional addresses (Gold Vault, PoPC Pool) verified correct in params.h
- [ ] Coinbase output order enforced: [0]=miner, [1]=gold, [2]=popc
- [ ] Subsidy calculation matches emission schedule for blocks 0-10,000
- [ ] LOW-S signature enforcement active
- [ ] MAX_REORG_DEPTH = 500 verified
- [ ] cASERT V2 active (blocks ≥1450): 24h halflife, 12.5% delta cap
- [ ] RBF (Replace-by-Fee) functional
- [ ] CPFP (Child-Pays-for-Parent) functional
- [ ] P2SH multisig functional (activation height 2000)
- [ ] PSBT offline signing functional
- [ ] HD wallet BIP39 seed generation verified
- [ ] Capsule Protocol v1 activation height set (5000)

## 2. NETWORK & P2P

- [ ] Node listens on port 19333 (P2P)
- [ ] Node serves JSON-RPC on port 18232
- [ ] Peer discovery works (DNS seeds or hardcoded IPs)
- [ ] Peer banning (misbehavior score ≥100) functional
- [ ] Block propagation tested with 2+ nodes
- [ ] Transaction relay tested between nodes
- [ ] Mempool accepts valid transactions, rejects invalid
- [ ] Fee-rate ordering in mempool verified

## 3. MINING

- [ ] ConvergenceX PoW produces valid blocks
- [ ] Mining with `--address` flag works correctly
- [ ] Miner submits blocks via RPC successfully
- [ ] Difficulty adjusts correctly (cASERT V2)
- [ ] Anti-stall zones activate on prolonged gaps
- [ ] Block template includes correct coinbase split (50/25/25)

## 4. WALLET & CLI

- [ ] `sost-cli send` creates and broadcasts valid transactions
- [ ] `sost-cli balance` shows correct balance
- [ ] `sost-cli createtx` signs with correct sighash
- [ ] UTXO sync from node works (`getaddressutxos` RPC)
- [ ] Coinbase maturity enforced (1000 blocks)
- [ ] Encrypted wallet (AES-256-GCM + scrypt) save/load works
- [ ] HD wallet seed import/export works
- [ ] Address format: `sost1` + 40 hex chars verified

## 5. INFRASTRUCTURE

- [ ] VPS (212.132.108.244) running latest code
- [ ] nginx proxying /rpc correctly on both domains
- [ ] SSL certificates valid for sostcore.com + sostprotocol.com
- [ ] UFW firewall: only 19333, 80, 443 open
- [ ] systemd services: sost-node, sost-miner configured and enabled
- [ ] Auto-restart on crash configured
- [ ] Disk space sufficient (>50GB free)
- [ ] RAM sufficient (>8GB for miner)

## 6. WEBSITE & APP

- [ ] Explorer functional on sostcore.com
- [ ] Explorer functional on sostprotocol.com (RPC fallback)
- [ ] Pip-Boy app loads and connects to node
- [ ] Block detail overlay shows real data from RPC
- [ ] TX detail overlay shows real data from RPC
- [ ] PWA installable on mobile
- [ ] Service worker v62+ deployed
- [ ] All links functional (no broken hrefs)
- [ ] Tokenomics match params.h values

## 7. DOCUMENTATION

- [ ] Whitepaper published and accessible
- [ ] BTCTalk announcement ready
- [ ] README complete with setup instructions
- [ ] EMERGENCY_RESPONSE_PLAN.md reviewed
- [ ] GeaSpirit public docs (canonical score, validated zones)
- [ ] Materials Engine public docs (capabilities, no proprietary details)

## 8. SECURITY

- [ ] GitHub 2FA enabled
- [ ] No secrets in public repository (grep for tokens, passwords, keys)
- [ ] Constitutional private keys stored offline (air-gapped USB)
- [ ] VPS SSH key-only authentication (no password login)
- [ ] RPC requires authentication for write methods
- [ ] nginx rate limiting on /rpc endpoint

## 9. BACKUPS

- [ ] Wallet backup (encrypted) on USB
- [ ] Constitutional key backup in physical safe
- [ ] Genesis block data backed up
- [ ] Chain data (blockchain) backed up weekly
- [ ] WSL is source of truth, VPS is copy, GitHub is copy #2

## 10. EMERGENCY READINESS

- [ ] Emergency Response Plan reviewed and understood
- [ ] Supply verification procedure tested
- [ ] Binary integrity check procedure tested
- [ ] Recovery from VPS compromise procedure tested
- [ ] Hard fork procedure documented

---

## Code Recommendations for Launch

| Feature | Priority | Effort | Status |
|---------|----------|--------|--------|
| `--maintenance-mode` flag | MEDIUM | 2 hours | NOT STARTED |
| Hardcoded checkpoints every 500 blocks | HIGH | 1 hour | NOT STARTED |
| `verify_supply` RPC method | HIGH | 3 hours | NOT STARTED |
| Alert message system | LOW | 8 hours | NOT STARTED |
| Minimum peer version check | MEDIUM | 2 hours | NOT STARTED |
| `getpeerinfo` RPC method | MEDIUM | 2 hours | NOT STARTED |

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

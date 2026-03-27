# SOST Protocol — Emergency Response Plan

**Author:** NeoB
**Date:** 2026-03-28
**Status:** Active — review quarterly

---

## Existing Emergency Mechanisms in Code

| Mechanism | Status | Location |
|-----------|--------|----------|
| MAX_REORG_DEPTH = 500 | ACTIVE | `src/sost-node.cpp:330` |
| BlockUndo (atomic rollback) | ACTIVE | `src/utxo_set.cpp` — full UTXO undo per block |
| Peer misbehavior scoring | ACTIVE | `src/sost-node.cpp:306,431` — ban at score ≥100 |
| ConvergenceX checkpoints | ACTIVE | `src/pow/convergencex.cpp` — merkle tree verification |
| GetTotalValue() supply audit | AVAILABLE | `src/utxo_set.cpp:430` — sum all UTXO values |
| 4-layer block validation | ACTIVE | L1-L4 in `block_validation.h` |
| Coinbase maturity (1000 blocks) | ACTIVE | Prevents spend of potentially orphaned rewards |
| Alert message system | NOT IMPLEMENTED | No network-wide alert mechanism |
| Hardcoded chain checkpoints | NOT IMPLEMENTED | No hash-at-height checkpoints |
| Maintenance mode flag | NOT IMPLEMENTED | No `--maintenance-mode` flag |
| Minimum node version check | NOT IMPLEMENTED | No version enforcement between peers |

---

## 1. ESCENARIO: Bug Crítico de Consenso

**Severity:** CRITICAL
**Example:** Wrong sighash computation, incorrect subsidy calculation, validation bypass

### Immediate Actions (0-15 minutes)
1. **STOP THE MINER** — `systemctl stop sost-miner` on VPS
2. **DO NOT STOP THE NODE** — keep it running to maintain chain state
3. Assess: does the bug affect already-mined blocks or only future blocks?

### If Bug Affects Only Future Blocks
1. Patch the code in WSL (`~/SOST/sostcore/sost-core/`)
2. Compile: `cd build && cmake .. && make -j$(nproc)`
3. Run tests: `cd build && ctest --output-on-failure`
4. Push to GitHub, pull on VPS: `cd /opt/sost && git pull && cd build && cmake .. && make -j2`
5. Restart node: `systemctl restart sost-node`
6. Restart miner: `systemctl restart sost-miner`
7. Verify chain is healthy: `sost-rpc getinfo`

### If Bug Affects Past Blocks (chain corruption)
1. Identify the first affected block height
2. If within MAX_REORG_DEPTH (500 blocks): the node can reorg automatically after fix
3. If deeper than 500 blocks: requires `--reindex` flag or manual chain reset
4. Worst case: restart from genesis with corrected code

### Communication
- Update BTCTalk announcement thread
- Push commit with clear description to GitHub
- Update website status page

### If Hard Fork Required
1. Define activation height (current height + ~2000 blocks ≈ 2 weeks)
2. Publish new version with clear upgrade instructions
3. Announce on all channels
4. Monitor upgrade adoption before activation height
5. After activation: verify old nodes reject new blocks (fork is clean)

---

## 2. ESCENARIO: Compromiso de GitHub

**Severity:** HIGH
**Risk:** Malicious code injected into repository

### Detection
```bash
# Compare local binary hash vs VPS binary hash
sha256sum ~/SOST/sostcore/sost-core/build/sost-node
ssh root@212.132.108.244 sha256sum /opt/sost/build/sost-node
# Compare local git log vs GitHub
git log --oneline -5
```

### Immediate Response
1. **Do NOT pull from GitHub on VPS** until verified
2. WSL (`~/SOST/sostcore/sost-core/`) is the source of truth
3. VPS (`/opt/sost/`) is copy #2

### Recovery
1. Change GitHub password immediately
2. Revoke all Personal Access Tokens
3. Revoke SSH keys from GitHub
4. Enable 2FA if not already active
5. Force push from clean local copy: `git push --force origin main`
6. Verify all commits are signed by NeoB

### Prevention
- Enable GitHub 2FA
- Use GPG-signed commits
- Never store secrets (tokens, passwords, private keys) in the repo
- Rotate GitHub token quarterly

---

## 3. ESCENARIO: Compromiso del VPS (212.132.108.244)

**Severity:** CRITICAL
**Risk:** Modified binary, stolen RPC credentials, network compromise

### Detection
```bash
# Verify binary integrity
sha256sum /opt/sost/build/sost-node
# Check for unauthorized SSH access
last -20
journalctl -u ssh --since "24 hours ago"
# Check running processes
ps aux | grep sost
# Verify file modification times
ls -la /opt/sost/build/sost-*
```

### Immediate Containment
```bash
# Block all external access
ufw deny incoming
# Stop all SOST services
systemctl stop sost-miner sost-node
```

### Evaluation
1. Was the sost-node binary modified? (compare sha256 with local build)
2. Were RPC credentials exposed? (check nginx logs for unauthorized access)
3. Were any wallet files accessed? (wallet keys should NOT be on VPS)
4. Was the chain data corrupted?

### Recovery
1. Rebuild from WSL source of truth:
   ```bash
   # On VPS:
   cd /opt/sost && git fetch origin && git reset --hard origin/main
   cd build && cmake .. && make -j2
   ```
2. Rotate ALL credentials:
   - RPC username/password in sost-node config
   - SSH keys (regenerate on VPS, update local ~/.ssh/config)
   - GitHub token
   - Nginx auth passwords
3. Restore firewall: `ufw allow 19333/tcp && ufw allow 80/tcp && ufw allow 443/tcp`
4. Restart services: `systemctl start sost-node && systemctl start sost-miner`

### Critical Note
**Wallet private keys are NOT on the VPS.** They are in `~/SOST/secrets/` on WSL only. The VPS has the node, miner, and public wallet file — but NOT the private keys needed to spend funds.

---

## 4. ESCENARIO: Compromiso de Claves Constitucionales

**Severity:** CATASTROPHIC
**Risk:** Gold Vault or PoPC Pool address private key compromised

### Impact
If the Gold Vault or PoPC Pool private key is compromised, an attacker could drain the constitutional reserves. This is the worst possible scenario.

### Detection
- Monitor constitutional addresses for unexpected outgoing transactions
- Any transfer FROM Gold Vault or PoPC Pool that is not a known operation is a compromise

### Response: REGENESIS
This has been done before. The exact procedure:

1. **Generate new constitutional keypairs offline**
   ```bash
   # On air-gapped machine:
   ./sost-cli genkey --label "gold_vault_v2"
   ./sost-cli genkey --label "popc_pool_v2"
   ```

2. **Update params.h with new addresses**
   ```cpp
   // include/sost/params.h
   inline constexpr const char* ADDR_GOLD = "sost1<new_gold_address>";
   inline constexpr const char* ADDR_POPC = "sost1<new_popc_address>";
   ```

3. **Create new genesis block**
   ```bash
   ./sost-genesis --gold-addr <new> --popc-addr <new> --timestamp <now>
   ```

4. **Compile, test, deploy**
5. **All existing chain history is lost** — this is a full restart
6. **Communicate clearly:** new genesis, new chain, old chain is deprecated

### Prevention
- Constitutional private keys stored ONLY on air-gapped USB, encrypted
- Never connect the USB to a networked machine
- Store backup copy in a physical safe
- NEVER store constitutional keys in any file on WSL, VPS, or cloud

---

## 5. ESCENARIO: Ataque de 51% / Minero Malicioso

**Severity:** HIGH
**Current Risk:** LOW (single miner network, but will increase with more miners)

### Detection
- Monitor for reorgs > 2 blocks deep
- Script: compare chain tip every 10 minutes, alert if tip hash changes for same height

### Existing Protections
- **MAX_REORG_DEPTH = 500:** Reorgs deeper than 500 blocks are rejected
- **ConvergenceX (~8GB RAM):** ASIC-resistant, difficult to concentrate hashrate
- **cASERT:** Per-block difficulty adjustment prevents timestamp manipulation

### Response
1. If hostile miner detected: increase `MAX_REORG_DEPTH` check in node
2. If attack sustained: add hardcoded checkpoints at known-good block heights
3. Nuclear option: change ConvergenceX parameters (matrix size, iteration count) — requires hard fork

---

## 6. ESCENARIO: Inflation Bug (monedas creadas de la nada)

**Severity:** CATASTROPHIC
**Reference:** Bitcoin CVE-2018-17144

### Detection
Run a supply verification:
```bash
# In sost-rpc or custom script:
# Sum all UTXO values and compare with theoretical emission
theoretical_supply = sum(sost_subsidy_stocks(h) for h in range(0, current_height+1))
actual_supply = utxo_set.GetTotalValue()
assert actual_supply == theoretical_supply
```

### Verification Script (to be created)
```bash
#!/bin/bash
# verify_supply.sh — compare actual UTXO sum vs theoretical emission
HEIGHT=$(sost-rpc getinfo | jq .blocks)
ACTUAL=$(sost-rpc gettotalutxovalue)  # needs RPC method
THEORETICAL=$(sost-rpc gettheoreticalemission $HEIGHT)  # needs RPC method
echo "Height: $HEIGHT"
echo "Actual supply: $ACTUAL stocks"
echo "Theoretical: $THEORETICAL stocks"
if [ "$ACTUAL" != "$THEORETICAL" ]; then
    echo "!!! SUPPLY MISMATCH — INFLATION BUG DETECTED !!!"
    exit 1
fi
echo "Supply verified OK"
```

### Response if Detected
1. **STOP MINER IMMEDIATELY**
2. Identify the first block where supply diverged
3. If within reorg depth: fix the bug, let node reorg
4. If beyond reorg depth: hard fork with corrective transaction or reindex
5. Publish post-mortem with full technical details

---

## 7. Procedimientos Preventivos

### Weekly
- [ ] Backup chainstate to external storage
- [ ] Backup wallet file (encrypted) to USB
- [ ] Verify binary integrity: `sha256sum` local vs VPS
- [ ] Check node uptime and sync status
- [ ] Review nginx access logs for anomalies

### Monthly
- [ ] Rotate GitHub Personal Access Token
- [ ] Review and update this emergency plan
- [ ] Test recovery procedure from backup
- [ ] Verify constitutional address balances are correct

### Per 500 Blocks
- [ ] Consider hardcoding a checkpoint hash for that height
- [ ] Verify supply integrity

### Pre-Release (any code change)
- [ ] Run all 22 CTest suites
- [ ] Run Materials Engine tests (117+)
- [ ] Verify sighash compatibility between CLI and node
- [ ] Test on local testnet before VPS deployment

---

## Contact & Escalation

| Role | Contact | Availability |
|------|---------|-------------|
| CTO / Lead Dev | NeoB | Primary |
| VPS | 212.132.108.244 | SSH |
| Source of Truth | WSL ~/SOST/sostcore/sost-core/ | Local |
| Backup #2 | VPS /opt/sost/ | Remote |
| Backup #3 | GitHub Neob1844/sost-core | Cloud |

---

## Document History
- 2026-03-28: Initial version — NeoB

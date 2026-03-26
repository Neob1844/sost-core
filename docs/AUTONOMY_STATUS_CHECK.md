# SOST Protocol — Autonomy Status Check

**Date:** 2026-03-26
**Auditor:** CTO automated diagnostic
**Verdict:** The system is approximately **60% autonomous** — core operations run without AI, but monitoring, backups, documentation, and recovery are incomplete.

---

## 1. What ALREADY Works Without AI

| Component | Status | Details |
|-----------|--------|---------|
| **sost-miner** | RUNNING | PID active, mining with `--blocks 999999 --realtime --profile mainnet` |
| **SSH tunnel (autossh)** | RUNNING | autossh with ServerAliveInterval=30, auto-reconnect on drop |
| **RPC tunnel** | ACTIVE | Port 18232 forwarded via SSH to VPS (212.132.108.244) |
| **auto_mine.sh** | EXISTS | Kills zombie processes, checks tunnel, restarts miner. Loop-based. |
| **monitor_miner.sh** | EXISTS | Logs RSS/VSZ/CPU every 60s to CSV |
| **deploy/monitor.sh** | EXISTS | Health check script: restarts node+miner if down, queries RPC. **NOT installed in cron.** |
| **deploy/node-status.sh** | EXISTS | Writes JSON status file for explorer. **NOT installed in cron.** |
| **safe-rebuild.sh** | EXISTS | Backs up chainstate + wallet before building |
| **Code compiles** | YES | 22/22 tests pass, CMake build works |

## 2. What is MISSING or INCOMPLETE

### CRITICAL (system stops working without these)

| # | Item | Status | Risk |
|---|------|--------|------|
| 1 | **Crontab** | **EMPTY — no cron jobs at all** | If autossh dies and nobody restarts auto_mine.sh, mining stops |
| 2 | **systemd services** | **Cannot verify** (need sudo). Node/auth/nginx show as "inactive" from this user — likely running under root. Restart policy unknown. | If VPS reboots, services may not restart |
| 3 | **Backups** | **NO automatic backups exist**. One manual `website-backup-20260314` found. No chain/wallet/config backups. | Data loss risk if disk fails |

### HIGH (system degrades without these)

| # | Item | Status | Risk |
|---|------|--------|------|
| 4 | **Health monitoring in cron** | deploy/monitor.sh EXISTS but **NOT installed in crontab** | Nobody detects if node crashes |
| 5 | **node-status.sh in cron** | deploy/node-status.sh EXISTS but **NOT installed in crontab** | Explorer miner badge stays "CHECKING" |
| 6 | **SSL renewal** | No certbot timer visible from this user | SSL could expire undetected |
| 7 | **Runbook** | **DOES NOT EXIST** (docs/RUNBOOK_OPERATIONS.md) | Human operator can't troubleshoot without AI |
| 8 | **Troubleshooting guide** | **DOES NOT EXIST** (docs/TROUBLESHOOTING.md) | Same |
| 9 | **Disk monitoring** | **NONE** | Disk fills up silently |
| 10 | **Log rotation** | **NOT VERIFIED** — mining.log, miner_monitor.csv may grow unbounded | Disk fill risk |

### MEDIUM (nice to have for resilience)

| # | Item | Status |
|---|------|--------|
| 11 | System architecture doc | DOES NOT EXIST |
| 12 | Glossary | DOES NOT EXIST |
| 13 | Alerting (email/telegram) | DOES NOT EXIST |
| 14 | GeaSpirit auto-retrain | DOES NOT EXIST (scripts exist but no cron) |
| 15 | Dead man switch | NOT DOCUMENTED |
| 16 | Autonomy roadmap | EXISTS (docs/AUTONOMY_ROADMAP.md) but not implemented |

---

## 3. Scenario Analysis

### A) Node crashes
- **Protection:** deploy/monitor.sh would restart it — BUT it's not in cron
- **Current reality:** Nobody detects it. Mining continues locally but blocks can't submit to a dead node.
- **Fix:** Install monitor.sh in cron

### B) Miner disconnects
- **Protection:** autossh reconnects the tunnel. auto_mine.sh restarts miner if it dies.
- **Current reality:** autossh IS running. auto_mine.sh may or may not be running as a service.
- **Assessment:** PARTIALLY PROTECTED

### C) VPS reboots
- **Protection:** Unknown. systemd enable status can't be verified without sudo.
- **Risk:** HIGH — if services don't auto-start, everything goes down until manual intervention.
- **Fix:** Verify `systemctl is-enabled sost-node nginx sost-auth` on VPS

### D) Disk fills up
- **Protection:** NONE. No monitoring, no alerting, no log rotation.
- **Risk:** MEDIUM-HIGH — mining.log and miner_monitor.csv grow indefinitely.
- **Fix:** Add logrotate config + disk usage check in monitor.sh

### E) SSL expires
- **Protection:** Unknown. Certbot may be installed on VPS but timer not visible from WSL.
- **Fix:** Verify on VPS: `sudo systemctl list-timers | grep certbot`

### F) Founder unavailable 30 days
- **Chain continues:** YES (miner + autossh running)
- **Web continues:** YES (if nginx stays up on VPS)
- **Can someone troubleshoot?** NO — no runbook, no troubleshooting guide
- **Fix:** Write runbook + troubleshooting docs

### G) All external AI disappears
- **Node:** YES, works independently (C++ binary)
- **Miner:** YES, works independently
- **Web:** YES, static files
- **Diagnosis:** NO runbook — human would struggle
- **GeaSpirit retrain:** Scripts exist but require manual decisions
- **Code understanding:** CLAUDE.md + comments adequate for experienced developer

---

## 4. Full Autonomy Checklist

| # | Requirement | Status | Priority | Action |
|---|-------------|--------|----------|--------|
| 1 | Miner runs without AI | **DONE** | CRITICAL | — |
| 2 | Tunnel auto-reconnects | **DONE** (autossh) | CRITICAL | — |
| 3 | Node auto-restarts on crash | **INCOMPLETE** (script exists, not in cron) | CRITICAL | `crontab -e` on VPS: `*/5 * * * * /opt/sost/deploy/monitor.sh` |
| 4 | Services enabled at boot | **UNKNOWN** (need sudo) | CRITICAL | Verify on VPS: `systemctl is-enabled sost-node nginx` |
| 5 | Automatic backups | **NOT DONE** | HIGH | Create backup script + cron |
| 6 | Health check in cron | **NOT DONE** | HIGH | Install monitor.sh in crontab |
| 7 | node-status.sh in cron | **NOT DONE** | HIGH | `*/1 * * * * /opt/sost/deploy/node-status.sh` |
| 8 | SSL auto-renewal | **UNKNOWN** | HIGH | Verify certbot timer on VPS |
| 9 | Runbook | **NOT DONE** | HIGH | Write docs/RUNBOOK_OPERATIONS.md |
| 10 | Troubleshooting guide | **NOT DONE** | HIGH | Write docs/TROUBLESHOOTING.md |
| 11 | Disk monitoring | **NOT DONE** | MEDIUM | Add to monitor.sh |
| 12 | Log rotation | **NOT DONE** | MEDIUM | Add logrotate config |
| 13 | Alert system | **NOT DONE** | MEDIUM | Email or Telegram webhook |
| 14 | Architecture diagram | **NOT DONE** | MEDIUM | Write docs/SYSTEM_ARCHITECTURE.md |
| 15 | GeaSpirit auto-retrain | **NOT DONE** | LOW | Cron job for weekly retrain |
| 16 | Dead man switch | **NOT DONE** | LOW | Document recovery procedure |
| 17 | Code documentation | **ADEQUATE** | LOW | CLAUDE.md + inline comments sufficient |

---

## 5. Top 5 Urgent Actions

1. **Install monitor.sh in crontab on VPS:**
   ```
   sudo crontab -e
   */5 * * * * /opt/sost/deploy/monitor.sh >> /opt/sost/monitor.log 2>&1
   */1 * * * * /opt/sost/deploy/node-status.sh
   ```
   (Update RPC credentials in monitor.sh first)

2. **Verify systemd services on VPS:**
   ```
   sudo systemctl is-enabled sost-node nginx
   sudo grep Restart /etc/systemd/system/sost-*.service
   ```
   If not enabled: `sudo systemctl enable sost-node nginx`

3. **Create basic backup script:**
   Daily: chain state, wallet, auth config → /opt/sost/backups/
   Weekly: full snapshot
   Add to cron.

4. **Verify SSL auto-renewal:**
   ```
   sudo systemctl list-timers | grep certbot
   sudo certbot certificates
   ```

5. **Write RUNBOOK_OPERATIONS.md** with step-by-step for the 10 most common operations.

---

## 6. Estimated Work to 100% Autonomy

| Task | Effort | Status |
|------|--------|--------|
| Install cron jobs | 15 min | NOT DONE |
| Verify systemd | 10 min | NEED SUDO |
| Create backup script | 1 hour | NOT DONE |
| Verify SSL | 5 min | NEED SUDO |
| Write runbook (20 ops) | 3 hours | NOT DONE |
| Write troubleshooting (50 items) | 4 hours | NOT DONE |
| System architecture diagram | 1 hour | NOT DONE |
| Log rotation setup | 15 min | NOT DONE |
| Disk monitoring | 15 min | NOT DONE |
| Alert system (Telegram) | 30 min | NOT DONE |
| **Total remaining** | **~10 hours** | |

The system is **60% autonomous** today. The critical gap is not in the running software (which works fine) but in **monitoring, recovery automation, and operator documentation**. A single afternoon of focused work on VPS (cron, systemd, backups) would bring it to ~80%. The remaining 20% is documentation.

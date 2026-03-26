# SOST Protocol — Autonomy Roadmap

**Objective:** Make SOST Protocol 100% autonomous — running, self-diagnosing, self-repairing, and self-improving without external AI dependency.

---

## 1. Executive Summary

SOST Protocol's core blockchain infrastructure (node, miner, consensus, wallet) is already fully autonomous — it runs without any AI. The dependency on external AI is in **development, diagnosis, and improvement** — writing code, debugging, designing features, and making architectural decisions.

This roadmap ensures that if all external AI disappears tomorrow, the system continues operating, can be maintained by a non-technical human, and where possible, improves itself.

---

## 2. AI Dependency Audit

| Component | Runs without AI? | Maintains without AI? | Learns without AI? | Self-repairs? | Risk |
|-----------|:---:|:---:|:---:|:---:|------|
| **sost-node** | YES | YES (C++ binary) | N/A | PARTIAL (systemd restart) | LOW |
| **sost-miner** | YES | YES | N/A | PARTIAL (autossh reconnect) | LOW |
| **Consensus** | YES | YES (immutable rules) | N/A | N/A | NONE |
| **Explorer** | YES | YES (static HTML + RPC) | N/A | NO (needs nginx) | LOW |
| **Wallet (web)** | YES | YES (static HTML) | N/A | NO | LOW |
| **Wallet (CLI)** | YES | YES (C++ binary) | N/A | NO | LOW |
| **Website** | YES | YES (static files) | N/A | NO (needs nginx) | LOW |
| **Auth gateway** | YES | PARTIAL (config) | N/A | NO | MEDIUM |
| **SSL/domains** | YES | PARTIAL (certbot renew) | N/A | YES (cron) | MEDIUM |
| **GeaSpirit models** | YES (inference) | NO (retraining) | PARTIAL (auto-retrain script) | NO | HIGH |
| **GeaSpirit data pipeline** | PARTIAL (GEE scripts) | NO (API changes) | NO | NO | HIGH |
| **Materials Engine** | YES (API) | NO (new campaigns) | PARTIAL (auto-discovery) | NO | MEDIUM |
| **Backups** | NO (manual) | NO | N/A | NO | HIGH |
| **Monitoring** | NO (manual checks) | NO | N/A | NO | HIGH |
| **Documentation** | YES (static) | NO (updates) | N/A | N/A | MEDIUM |

**Critical gaps:** Backups, monitoring, GeaSpirit retraining, troubleshooting documentation.

---

## 3. Auto-Diagnosis Plan

### Health Check Scripts

**Node health** (`scripts/health/node_health.sh`):
- Check sost-node process running
- Check RPC responds (curl localhost:18232)
- Check chain advancing (last block < 30 min ago)
- Check disk space (< 90%)
- Check RAM (< 90%)
- If fails → restart via systemd
- If restart fails → log CRITICAL alert

**Miner health** (`scripts/health/miner_health.sh`):
- Check sost-miner process
- Check SSH tunnel active
- If tunnel down → reconnect via autossh
- If miner down → restart

**Web health** (`scripts/health/web_health.sh`):
- curl each page → check 200 OK
- Check nginx running
- Check SSL valid (days remaining)
- If SSL < 30 days → certbot renew
- If nginx down → restart

**Master recovery** (`scripts/health/auto_recovery.sh`):
- Runs all health checks
- Classifies alerts: CRITICAL / HIGH / MEDIUM / LOW
- Attempts automatic repair
- Logs everything to /var/log/sost-recovery.log

**Cron:** `*/5 * * * * /opt/sost/scripts/health/auto_recovery.sh`

---

## 4. Auto-Repair Plan

| Failure | Detection | Automatic Action | Fallback |
|---------|-----------|-----------------|----------|
| Node crash | RPC timeout | systemctl restart sost-node | Alert operator |
| Miner disconnect | Process check | Restart + reconnect tunnel | Alert operator |
| Nginx down | curl fails | systemctl restart nginx | Alert operator |
| SSL expiring | Days < 30 | certbot renew | Alert operator |
| Disk full | df > 90% | Prune old logs + backups | Alert operator |
| Chain stall | Block age > 60min | Restart node + check peers | Alert operator |
| Auth gateway down | Port check | Restart service | Alert operator |

---

## 5. Auto-Learning Plan

### GeaSpirit Auto-Retrain (`geaspirit/scripts/auto_retrain.py`):
1. Weekly cron: check for new labels (MINDAT, OZMIN updates)
2. For each zone with changes: retrain with spatial block CV
3. Compare new AUC vs current
4. If better → update model, log improvement
5. If worse → keep old model, log regression
6. Generate weekly report

### GeaSpirit Drift Detection:
- Monthly: KS test on feature distributions vs training data
- If drift > threshold → flag for retraining
- Log drift magnitude and affected features

### Materials Engine Auto-Discovery:
- Weekly: run balanced discovery campaign
- Compare new candidates against corpus
- If promising → add to validation queue
- Monthly: check JARVIS/AFLOW for new data

---

## 6. Backup Plan

### Schedule:
- **Daily (3 AM):** chain state, wallet files, auth config, nginx config
- **Weekly (Sunday 4 AM):** full node data, GeaSpirit models, Materials corpus
- **Monthly (1st, 5 AM):** complete system snapshot

### Retention: 30 daily, 12 weekly, 12 monthly

### Verification: SHA256 checksum on every backup, alert if corrupt

### Offsite: Copy critical backups to second location (USB, cloud, or second server)

---

## 7. Monitoring Plan

### Terminal Dashboard (`scripts/monitor/dashboard.sh`):
```
╔════════════════════════════════════════════╗
║  SOST SYSTEM STATUS       2026-03-26 14:30 ║
╠════════════════════════════════════════════╣
║  NODE:     OK  Block: 1352  Diff: 657K     ║
║  MINER:    OK  PID: 12345                  ║
║  NGINX:    OK  2 domains                   ║
║  SSL:      OK  89 days remaining           ║
║  DISK:     OK  4.3% used                   ║
║  BACKUP:   OK  Last: 2026-03-26 03:00      ║
╚════════════════════════════════════════════╝
```

### Alert channels (no external AI needed):
1. Log file: /var/log/sost-alerts.log
2. Email via local postfix/sendmail
3. Telegram bot webhook (simple curl)

---

## 8. Human Documentation

### Required documents:
- `docs/RUNBOOK_OPERATIONS.md` — 20 step-by-step procedures for common operations
- `docs/TROUBLESHOOTING.md` — 50 symptom → cause → solution entries
- `docs/SYSTEM_ARCHITECTURE.md` — complete system diagram
- `docs/GLOSSARY.md` — 200+ technical terms explained

### Each runbook entry format:
1. Title (what operation)
2. Context (when/why)
3. Prerequisites
4. Step-by-step commands (copy-paste)
5. Verification (how to confirm it worked)
6. If it fails (what to try next)

---

## 9. Local AI Backup (Future)

### Option A: Rule-Based Expert System
```python
# sost-doctor: symptom → diagnosis → action
RULES = {
    "node not responding": {
        "check": "systemctl status sost-node",
        "fix": "systemctl restart sost-node",
        "verify": "curl -s localhost:18232 | grep height"
    },
    # ... 50+ rules
}
```
No AI needed — pure pattern matching.

### Option B: Small Local LLM (when hardware allows)
- Model: Phi-3-mini or TinyLlama (4-bit quantized, ~2GB RAM)
- Purpose: answer questions about SOST using project docs as context
- RAG: index all docs, retrieve relevant chunks, generate answer
- Not needed for operations — useful for knowledge transfer

---

## 10. Sustainability

### Periodic renewals:
| Item | Frequency | Automated? |
|------|-----------|-----------|
| Domain registration | Annual | NO (manual payment) |
| SSL certificates | 90 days | YES (certbot cron) |
| VPS billing | Monthly | NO (manual payment) |
| GEE credentials | ~Annual | NO (manual renewal) |
| Earthdata credentials | ~Annual | NO (manual renewal) |

### If founder unavailable:
- All passwords in encrypted backup (location documented)
- README has build instructions
- RUNBOOK has operation procedures
- System continues running autonomously until domain/VPS expire
- Dead man switch: scheduled reminder email if no login for 30 days

---

## 11. Autonomy Checklist

| Requirement | Status | Priority | Action |
|-------------|--------|----------|--------|
| Node runs without AI | DONE | CRITICAL | — |
| Miner runs without AI | DONE | CRITICAL | — |
| Consensus immutable | DONE | CRITICAL | — |
| Web serves without AI | DONE | CRITICAL | — |
| SSL auto-renew | DONE (certbot) | HIGH | Verify cron |
| Auto-restart on crash | PARTIAL (systemd) | HIGH | Add health checks |
| Automatic backups | NOT DONE | HIGH | Create backup script |
| Health monitoring | NOT DONE | HIGH | Create dashboard |
| Alert system | NOT DONE | HIGH | Create alert script |
| Operations runbook | NOT DONE | HIGH | Write 20 procedures |
| Troubleshooting guide | NOT DONE | HIGH | Write 50 entries |
| Architecture diagram | NOT DONE | MEDIUM | Document system |
| GeaSpirit auto-retrain | NOT DONE | MEDIUM | Create retrain script |
| Materials auto-discovery | PARTIAL | MEDIUM | Cron job |
| Rule-based diagnostics | NOT DONE | LOW | Create sost-doctor |
| Local AI backup | NOT DONE | LOW | Future hardware |
| Dead man switch | NOT DONE | LOW | Setup reminder |

---

## 12. Implementation Timeline

| Week | Deliverable |
|------|------------|
| 1 | Health check scripts (node, miner, web) + cron |
| 2 | Backup script + cron + verification |
| 3 | Monitoring dashboard + alert system |
| 4 | Runbook (20 operations) |
| 5 | Troubleshooting guide (50 symptoms) |
| 6 | System architecture diagram |
| 7 | GeaSpirit auto-retrain pipeline |
| 8 | Rule-based diagnostic system |
| 9 | Testing + hardening |
| 10 | Documentation review + dead man switch |

**After 10 weeks:** SOST Protocol operates autonomously with self-diagnosis, self-repair, automatic backups, and comprehensive documentation for human operators.

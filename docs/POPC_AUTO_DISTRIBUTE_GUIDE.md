# PoPC Automatic Reward Distribution Guide

**Date:** 2026-03-29
**Security model:** Option B — Temporal key decryption
**Key exposure:** ~5 seconds per execution, only when rewards are pending

---

## 1. What It Does

A cron job runs daily at 04:00 UTC. It:

1. Checks if any PoPC commitments have completed their period
2. If NONE pending → exits immediately. **Key is NEVER decrypted.**
3. If rewards ARE pending → decrypts the PoPC Pool key (5 seconds)
4. Pays up to 10 rewards per day
5. Processes up to 5 slashes per day (from slash queue)
6. **SHREDS the decrypted key immediately** (even on crash/error)

Most days, the key is never touched. It only decrypts when there's actual work to do.

---

## 2. Installation (Step by Step)

### Step 1: Create the encryption password file

```bash
# As root on the VPS:
echo 'YOUR_ENCRYPTION_PASSWORD_HERE' > /root/.sost_auto_pass
chmod 600 /root/.sost_auto_pass
chown root:root /root/.sost_auto_pass
```

This file contains ONLY the encryption password (not the private key). To get the actual private key, an attacker needs: this file + the .enc file + openssl = three separate things.

### Step 2: Ensure the encrypted key exists on the VPS

The script searches for `popc_pool.json.enc` in these locations (first found wins):
1. `/opt/sost/secrets/popc_pool.json.enc` (VPS production — recommended)
2. `/root/SOST/secrets/popc_pool.json.enc`
3. `$HOME/SOST/secrets/popc_pool.json.enc`
4. `/home/sost/SOST/secrets/popc_pool.json.enc`

```bash
# On the VPS — create the directory:
mkdir -p /opt/sost/secrets && chmod 700 /opt/sost/secrets

# Copy the encrypted key from your local machine:
scp ~/SOST/secrets/popc_pool.json.enc root@YOUR_VPS_IP:/opt/sost/secrets/

# Or create fresh on the VPS:
openssl aes-256-cbc -pbkdf2 -in popc_pool_key.json -out /opt/sost/secrets/popc_pool.json.enc
shred -fuz popc_pool_key.json   # DELETE the unencrypted original immediately
```

The `.enc` file is safe to have on the VPS — without the password it's useless.

### Step 3: Install the cron job

```bash
cd ~/SOST/sostcore/sost-core
bash scripts/install_popc_cron.sh
```

### Step 4: Verify installation

```bash
crontab -l | grep popc     # Should show the daily job
cat /var/log/popc_auto_distribute.log   # Should show startup messages
```

---

## 3. How to Verify It Works

### Manual test run:

```bash
bash scripts/popc_auto_distribute.sh
cat /var/log/popc_auto_distribute.log
```

### Check logs:

```bash
# Normal operation:
tail -20 /var/log/popc_auto_distribute.log

# Alerts (critical events):
cat /var/log/popc_alerts.log
```

### Expected log output (no pending rewards):

```
2026-04-01 04:00:00 UTC — === PoPC auto-distribute started ===
2026-04-01 04:00:00 UTC — Active commitments: 3, Pool balance: 5432.12 SOST
2026-04-01 04:00:00 UTC — No eligible releases. Key NOT decrypted.
```

### Expected log output (with rewards):

```
2026-04-15 04:00:00 UTC — === PoPC auto-distribute started ===
2026-04-15 04:00:00 UTC — Active commitments: 5, Pool balance: 8200.50 SOST
2026-04-15 04:00:01 UTC — Pending work detected. Decrypting PoPC Pool key...
2026-04-15 04:00:01 UTC — Key decrypted. Processing releases...
2026-04-15 04:00:01 UTC — Current block height: 7500
2026-04-15 04:00:02 UTC — RELEASED: commitment=abc123 reward=213.75 SOST
2026-04-15 04:00:02 UTC — Releases completed: 1
2026-04-15 04:00:02 UTC — No slash queue or empty. Skipping slashes.
2026-04-15 04:00:02 UTC — === Distribution complete: 1 releases, 0 slashes ===
2026-04-15 04:00:02 UTC — Key explicitly shredded.
```

---

## 4. How to Disable

Any of these methods work:

```bash
# Method 1: Remove password file (safest — key can never be decrypted)
rm /root/.sost_auto_pass

# Method 2: Remove cron job
crontab -l | grep -v popc_auto_distribute | crontab -

# Method 3: Make script non-executable
chmod 000 scripts/popc_auto_distribute.sh
```

To re-enable: reverse the above steps.

---

## 5. Safety Features

| Feature | Protection Against |
|---------|-------------------|
| **Trap EXIT/ERR/INT/TERM** | Key shredded even if script crashes |
| **Max 10 releases/day** | Limits damage from bugs |
| **Max 5 slashes/day** | Prevents mass slash attack |
| **Reward > 30% pool → BLOCKED** | Catches bugs or manipulation |
| **Pool < 1000 SOST → ALERT** | Early warning of depletion |
| **5+ slashes/day → ALERT** | Detects anomalous patterns |
| **No password file → silent exit** | Easy kill switch |
| **No pending → key never decrypted** | Minimal exposure |
| **Per-process temp dir ($$)** | No collision between runs |
| **shred -fuz** | Overwrites key data before deletion |

---

## 6. Security Scenarios

### Scenario: Attacker gets root on VPS

- **Without auto-distribute:** Attacker cannot access PoPC Pool funds (key is encrypted)
- **With auto-distribute:** Attacker could read `/root/.sost_auto_pass`, but still needs `.enc` file + openssl. If they have all three, they can decrypt the key. **Mitigation:** max 10 releases/day limits damage. Alert logs would show anomalous activity.

### Scenario: Script crashes mid-execution

- Trap fires → key is shredded
- Unprocessed rewards remain pending → next day's run picks them up
- No funds are lost or locked

### Scenario: Node is down

- RPC call fails → script exits cleanly
- Key is never decrypted (no RPC = no pending check)
- Retries automatically next day

### Scenario: Pool runs out of funds

- `popc_release` returns error → logged but no crash
- Participant's bond is still returned on expiry (consensus-level, independent)
- Only the SOST reward is unpaid

---

## 7. Emergency Procedures

### Stop all auto-distribution immediately:

```bash
rm /root/.sost_auto_pass
```

### Check for anomalies:

```bash
cat /var/log/popc_alerts.log
grep "RELEASED\|SLASHED" /var/log/popc_auto_distribute.log | tail -20
```

### If incorrect rewards were paid:

Rewards are standard SOST transactions — they cannot be reversed on-chain. However:
1. Check the log for exact amounts and addresses
2. Verify each release was for a legitimate completed commitment
3. If a bug is found, fix the code and reduce the daily limit

---

## 8. Files

| File | Purpose |
|------|---------|
| `scripts/popc_auto_distribute.sh` | Main distribution script |
| `scripts/install_popc_cron.sh` | Installer |
| `/root/.sost_auto_pass` | Encryption password (VPS only, NOT in git) |
| `~/SOST/secrets/popc_pool.json.enc` | Encrypted PoPC Pool key |
| `/var/log/popc_auto_distribute.log` | Operation log |
| `/var/log/popc_alerts.log` | Critical alerts |
| `logs/popc_slash_queue.json` | Pending slashes from Etherscan checker |

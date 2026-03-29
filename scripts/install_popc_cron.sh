#!/bin/bash
# =============================================================================
# Install PoPC Auto-Distribution Cron Job
# =============================================================================
# Run this ONCE on the VPS to set up automatic reward distribution.
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DISTRIBUTE_SCRIPT="$SCRIPT_DIR/popc_auto_distribute.sh"
AUTO_PASS_FILE="/root/.sost_auto_pass"
CRON_LINE="0 4 * * * $DISTRIBUTE_SCRIPT"

# Search for encrypted key in multiple locations
ENCRYPTED_KEY=""
for candidate in \
    "/opt/sost/secrets/popc_pool.json.enc" \
    "/root/SOST/secrets/popc_pool.json.enc" \
    "$HOME/SOST/secrets/popc_pool.json.enc" \
    "/home/sost/SOST/secrets/popc_pool.json.enc"; do
    if [ -f "$candidate" ]; then
        ENCRYPTED_KEY="$candidate"
        break
    fi
done

echo "=== PoPC Auto-Distribution Installer ==="
echo ""

# Check 1: Script exists
if [ ! -f "$DISTRIBUTE_SCRIPT" ]; then
    echo "ERROR: $DISTRIBUTE_SCRIPT not found."
    exit 1
fi
echo "[OK] Distribution script found."

# Check 2: Script is executable
if [ ! -x "$DISTRIBUTE_SCRIPT" ]; then
    chmod +x "$DISTRIBUTE_SCRIPT"
    echo "[OK] Made distribution script executable."
else
    echo "[OK] Distribution script is executable."
fi

# Check 3: Encrypted key exists (searched multiple locations)
if [ -z "$ENCRYPTED_KEY" ]; then
    echo ""
    echo "WARNING: Encrypted key not found in any standard location."
    echo "  Searched: /opt/sost/secrets/, ~/SOST/secrets/, /home/sost/SOST/secrets/"
    echo ""
    echo "  To set up on the VPS:"
    echo "    mkdir -p /opt/sost/secrets && chmod 700 /opt/sost/secrets"
    echo "    scp ~/SOST/secrets/popc_pool.json.enc root@VPS_IP:/opt/sost/secrets/"
    echo ""
    echo "  Or create fresh:"
    echo "    openssl aes-256-cbc -pbkdf2 -in popc_pool.json -out /opt/sost/secrets/popc_pool.json.enc"
    echo ""
else
    echo "[OK] Encrypted key found: $ENCRYPTED_KEY"
fi

# Check 4: Auto-pass file
if [ ! -f "$AUTO_PASS_FILE" ]; then
    echo ""
    echo "SETUP REQUIRED: Create the auto-pass file."
    echo "  This file contains the encryption password (NOT the private key)."
    echo ""
    echo "  Run these commands as root:"
    echo "    echo 'YOUR_ENCRYPTION_PASSWORD' > $AUTO_PASS_FILE"
    echo "    chmod 600 $AUTO_PASS_FILE"
    echo "    chown root:root $AUTO_PASS_FILE"
    echo ""
    echo "  The script will not execute without this file."
    echo "  To DISABLE auto-distribution at any time: rm $AUTO_PASS_FILE"
    echo ""
else
    echo "[OK] Auto-pass file found."
    # Verify permissions
    PERMS=$(stat -c %a "$AUTO_PASS_FILE" 2>/dev/null)
    if [ "$PERMS" != "600" ]; then
        echo "WARNING: $AUTO_PASS_FILE permissions are $PERMS (should be 600)"
        echo "  Fix with: chmod 600 $AUTO_PASS_FILE"
    fi
fi

# Check 5: Create log files
touch /var/log/popc_auto_distribute.log 2>/dev/null || true
touch /var/log/popc_alerts.log 2>/dev/null || true
echo "[OK] Log files ready."

# Check 6: Install cron job
echo ""
echo "Installing cron job: runs daily at 04:00 UTC"
echo "  $CRON_LINE"
echo ""

# Check if already installed
if crontab -l 2>/dev/null | grep -q "popc_auto_distribute"; then
    echo "Cron job already exists. Updating..."
    crontab -l 2>/dev/null | grep -v "popc_auto_distribute" | { cat; echo "$CRON_LINE"; } | crontab -
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
fi

echo "[OK] Cron job installed."
echo ""
echo "=== Installation Complete ==="
echo ""
echo "Schedule:  Daily at 04:00 UTC"
echo "Log:       /var/log/popc_auto_distribute.log"
echo "Alerts:    /var/log/popc_alerts.log"
echo "Disable:   rm $AUTO_PASS_FILE (or: crontab -e and remove the line)"
echo ""
echo "Safety features:"
echo "  - Key decrypted ONLY when pending rewards exist (~5 seconds)"
echo "  - Maximum 10 releases per day"
echo "  - Maximum 5 slashes per day"
echo "  - Reward > 30% pool → blocked + alert"
echo "  - Key shredded on ANY exit (crash, error, interrupt)"
echo "  - No password file → script exits silently"

#!/bin/bash
# safe-rebuild.sh — Backup chainstate before recompiling sost-core
#
# USE THIS instead of raw 'cmake --build build' when you've changed
# consensus parameters (COINBASE_MATURITY, emission, etc.)
#
# What it does:
#   1. Backs up ~/.sost/chainstate → ~/.sost/chainstate_backup_YYYYMMDD_HHMMSS
#   2. Backs up wallet.json → wallet.json.backup_YYYYMMDD_HHMMSS
#   3. Runs cmake build
#   4. Shows diff of changed consensus files (so you know what changed)
#
# Usage:
#   cd ~/SOST/sostcore/sost-core
#   ./safe-rebuild.sh

set -e

CHAINSTATE_DIR="$HOME/.sost/chainstate"
WALLET_FILE="$HOME/SOST/sostcore/sost-core/wallet.json"
BUILD_DIR="build"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== SOST Safe Rebuild ==="
echo ""

# --- Step 1: Backup chainstate ---
if [ -d "$CHAINSTATE_DIR" ]; then
    BACKUP_DIR="${CHAINSTATE_DIR}_backup_${TIMESTAMP}"
    echo "[1/4] Backing up chainstate..."
    echo "  From: $CHAINSTATE_DIR"
    echo "  To:   $BACKUP_DIR"
    cp -r "$CHAINSTATE_DIR" "$BACKUP_DIR"
    echo "  Done. Size: $(du -sh "$BACKUP_DIR" | cut -f1)"
else
    echo "[1/4] No chainstate found at $CHAINSTATE_DIR — skip backup"
fi

# --- Step 2: Backup wallet ---
if [ -f "$WALLET_FILE" ]; then
    WALLET_BACKUP="${WALLET_FILE}.backup_${TIMESTAMP}"
    echo "[2/4] Backing up wallet..."
    echo "  From: $WALLET_FILE"
    echo "  To:   $WALLET_BACKUP"
    cp "$WALLET_FILE" "$WALLET_BACKUP"
else
    echo "[2/4] No wallet.json found — skip backup"
fi

# --- Step 3: Build ---
echo "[3/4] Building..."
echo ""
cmake --build "$BUILD_DIR" -j$(nproc)
echo ""

# --- Step 4: Summary ---
echo "[4/4] Build complete."
echo ""
echo "  Chainstate backup: ${CHAINSTATE_DIR}_backup_${TIMESTAMP}"
echo "  Wallet backup:     ${WALLET_FILE}.backup_${TIMESTAMP}"
echo ""
echo "  If the new build breaks your chain, restore with:"
echo "    rm -rf $CHAINSTATE_DIR"
echo "    cp -r ${CHAINSTATE_DIR}_backup_${TIMESTAMP} $CHAINSTATE_DIR"
echo ""

# --- Cleanup hint ---
BACKUP_COUNT=$(ls -d ${CHAINSTATE_DIR}_backup_* 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 5 ]; then
    echo "  WARNING: You have $BACKUP_COUNT chainstate backups."
    echo "  Consider cleaning old ones: ls -d ~/.sost/chainstate_backup_*"
fi

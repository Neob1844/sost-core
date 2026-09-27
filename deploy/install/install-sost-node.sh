#!/usr/bin/env bash
# SOST node installer (Linux, systemd). Idempotent; supports upgrade + rollback.
#
# Usage:
#   sudo ./install-sost-node.sh install   <path-to-sost-node-binary> [genesis.json]
#   sudo ./install-sost-node.sh upgrade   <path-to-new-sost-node-binary>
#   sudo ./install-sost-node.sh rollback
#   sudo ./install-sost-node.sh status
#
# Security posture (matches the SOST deploy workflow):
#   - service runs as the unprivileged 'sost' user (never root; root-owned data dir
#     makes the DB silently read-only for the service)
#   - RPC password + node key live in /etc/sost/*.pass|*.key at mode 600, NOT in argv
#   - binaries are hash-verified against SHA256SUMS before install
set -euo pipefail

SVC=sost-node
BIN_DIR=/usr/local/bin
BIN=$BIN_DIR/sost-node
CFG_DIR=/etc/sost
DATA_DIR=/var/lib/sost
BACKUP_DIR=/opt/sost/backups
UNIT=/etc/systemd/system/$SVC.service
HERE="$(cd "$(dirname "$0")" && pwd)"

need_root() { [ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }; }

verify_hash() {
  local f="$1"
  if [ -f "$HERE/SHA256SUMS" ]; then
    local want have base; base="$(basename "$f")"
    want="$(grep -E "  ($base|.*/$base)\$" "$HERE/SHA256SUMS" | awk '{print $1}' | head -1 || true)"
    if [ -n "$want" ]; then
      have="$(sha256sum "$f" | awk '{print $1}')"
      [ "$want" = "$have" ] || { echo "HASH MISMATCH for $base"; echo " want $want"; echo " have $have"; exit 1; }
      echo "hash OK: $base"
    else echo "WARN: no SHA256SUMS entry for $base (skipping verify)"; fi
  else echo "WARN: no SHA256SUMS next to installer (skipping verify)"; fi
}

ensure_user() { id sost >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin sost; }

ensure_layout() {
  install -d -o sost -g sost -m 750 "$DATA_DIR"
  install -d -o root -g sost -m 750 "$CFG_DIR"
  install -d -m 700 "$BACKUP_DIR"
  if [ ! -f "$CFG_DIR/rpc.pass" ]; then
    umask 077; head -c 32 /dev/urandom | base64 | tr -d '/+=' > "$CFG_DIR/rpc.pass"
    chmod 600 "$CFG_DIR/rpc.pass"; echo "generated $CFG_DIR/rpc.pass (mode 600)"
  fi
  if [ ! -f "$CFG_DIR/node.key" ]; then
    umask 077; openssl rand -hex 32 > "$CFG_DIR/node.key"; chmod 600 "$CFG_DIR/node.key"
    echo "generated $CFG_DIR/node.key (mode 600)"
  fi
  chown root:sost "$CFG_DIR"/rpc.pass "$CFG_DIR"/node.key; chmod 640 "$CFG_DIR"/rpc.pass "$CFG_DIR"/node.key
}

install_unit() { install -m 644 "$HERE/sost-node.service" "$UNIT"; systemctl daemon-reload; }

do_install() {
  need_root; local newbin="${1:?binary path required}"; local genesis="${2:-}"
  verify_hash "$newbin"; ensure_user; ensure_layout
  install -m 755 "$newbin" "$BIN"
  [ -n "$genesis" ] && install -o sost -g sost -m 644 "$genesis" "$DATA_DIR/genesis.json"
  install_unit
  systemctl enable "$SVC"; systemctl restart "$SVC"
  echo "installed. IMPORTANT: node/miner builds MUST use"
  echo "  -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF"
  echo "or the node rejects all blocks."
  do_status
}

do_upgrade() {
  need_root; local newbin="${1:?new binary path required}"; verify_hash "$newbin"
  local ts; ts="$(date +%Y%m%d_%H%M%S)"
  install -d "$BACKUP_DIR/$ts"; cp -a "$BIN" "$BACKUP_DIR/$ts/sost-node" 2>/dev/null || true
  echo "backed up current binary -> $BACKUP_DIR/$ts/sost-node"
  systemctl stop "$SVC" || true
  install -m 755 "$newbin" "$BIN"
  systemctl start "$SVC"
  echo "$ts" > "$BACKUP_DIR/.last"
  do_status
}

do_rollback() {
  need_root; local ts; ts="$(cat "$BACKUP_DIR/.last" 2>/dev/null || true)"
  [ -n "$ts" ] && [ -f "$BACKUP_DIR/$ts/sost-node" ] || { echo "no rollback point"; exit 1; }
  systemctl stop "$SVC" || true
  install -m 755 "$BACKUP_DIR/$ts/sost-node" "$BIN"
  systemctl start "$SVC"; echo "rolled back to $ts"; do_status
}

do_status() {
  systemctl --no-pager status "$SVC" 2>/dev/null | head -6 || true
  local pass; pass="$(cat "$CFG_DIR/rpc.pass" 2>/dev/null || echo '?')"
  echo "height: $(curl -s --data '{"jsonrpc":"2.0","id":1,"method":"getblockcount","params":[]}' \
      -u "sostrpc:$pass" http://127.0.0.1:18332/ 2>/dev/null || echo 'RPC not reachable')"
}

case "${1:-}" in
  install)  shift; do_install "$@";;
  upgrade)  shift; do_upgrade "$@";;
  rollback) do_rollback;;
  status)   do_status;;
  *) echo "usage: $0 {install <bin> [genesis]|upgrade <bin>|rollback|status}"; exit 1;;
esac

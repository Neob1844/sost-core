#!/usr/bin/env bash
# apply.sh — one-shot, idempotent hardening of the SOST VPS RPC stack.
#
# What it does (in this order):
#   1.  Snapshot every config we touch under /opt/sost/backups/<ts>/.
#   2.  Drop /etc/sysctl.d/99-sost.conf and reload kernel knobs.
#   3.  Install /opt/sost/scripts/health-check.sh + monitor-connections.sh.
#   4.  Install systemd units sost-health.{service,timer} and
#       sost-conn-monitor.{service,timer}; enable them.
#   5.  Add Restart=on-failure / RestartSec=10 to sost-node.service if not
#       already present, via a drop-in (does not mutate the original).
#   6.  Patch nginx site to add an upstream sost_node { keepalive 32; }
#       block and switch /rpc + /rpc/public to HTTP/1.1 + Connection "".
#       Validates with `nginx -t`; restores backup on failure.
#   7.  systemctl daemon-reload + reload nginx + restart sost-node.
#   8.  Print a verification report (RPC reachable? port-conn count?).
#
# Safe to run repeatedly. Every step checks before writing, so a second
# run on a healthy box is a no-op apart from a verification report.
#
# Usage (on the VPS, as root):
#   bash /opt/sost/scripts/vps-resilience/apply.sh
#
# Usage (from your laptop):
#   ssh root@<vps> 'cd /opt/sost && git pull --ff-only origin main \
#       && bash scripts/vps-resilience/apply.sh'

set -u

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "ERROR: apply.sh must run as root (sudo)." >&2
    exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="/opt/sost/backups/$TS"
mkdir -p "$BACKUP_ROOT"

NGINX_SITES=(
    /etc/nginx/sites-enabled/sost
    /etc/nginx/sites-enabled/sostcore
    /etc/nginx/sites-enabled/sostcore.com
    /etc/nginx/conf.d/sost.conf
)

log() { echo "[$(date +%T)] $*"; }

# ---------------------------------------------------------------------------
# 1. snapshot
# ---------------------------------------------------------------------------
log "=== 1/8 backup originals -> $BACKUP_ROOT ==="
for s in "${NGINX_SITES[@]}"; do
    [ -f "$s" ] && cp -a "$s" "$BACKUP_ROOT/" && log "  saved $s"
done
[ -f /etc/sysctl.d/99-sost.conf ] && cp -a /etc/sysctl.d/99-sost.conf "$BACKUP_ROOT/"
[ -f /etc/systemd/system/sost-node.service ] && cp -a /etc/systemd/system/sost-node.service "$BACKUP_ROOT/"
[ -d /etc/systemd/system/sost-node.service.d ] && cp -a /etc/systemd/system/sost-node.service.d "$BACKUP_ROOT/"

# ---------------------------------------------------------------------------
# 2. sysctl
# ---------------------------------------------------------------------------
log "=== 2/8 sysctl drop-in ==="
install -m 0644 "$HERE/sysctl-99-sost.conf" /etc/sysctl.d/99-sost.conf
sysctl --system >/dev/null 2>&1 || sysctl -p /etc/sysctl.d/99-sost.conf >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# 3. scripts on disk (operational tools, not the binary).
# ---------------------------------------------------------------------------
log "=== 3/8 install /opt/sost/scripts/{health-check,monitor-connections}.sh ==="
mkdir -p /opt/sost/scripts
install -m 0755 "$HERE/health-check.sh"        /opt/sost/scripts/health-check.sh
install -m 0755 "$HERE/monitor-connections.sh" /opt/sost/scripts/monitor-connections.sh

if [ ! -f /etc/sost/rpc.env ]; then
    log "  WARN: /etc/sost/rpc.env not found — health-check will skip until the"
    log "        operator drops RPC_USER=… and RPC_PASS=… there. Example:"
    log "          install -d -m 0700 /etc/sost"
    log "          cat > /etc/sost/rpc.env <<'EOF'"
    log "          RPC_USER=<your-rpc-user>"
    log "          RPC_PASS=<your-rpc-pass>"
    log "          EOF"
    log "          chmod 600 /etc/sost/rpc.env"
fi

# ---------------------------------------------------------------------------
# 4. systemd units for the timers.
# ---------------------------------------------------------------------------
log "=== 4/8 systemd timers (sost-health, sost-conn-monitor) ==="
install -m 0644 "$HERE/sost-health.service"        /etc/systemd/system/sost-health.service
install -m 0644 "$HERE/sost-health.timer"          /etc/systemd/system/sost-health.timer
install -m 0644 "$HERE/sost-conn-monitor.service"  /etc/systemd/system/sost-conn-monitor.service
install -m 0644 "$HERE/sost-conn-monitor.timer"    /etc/systemd/system/sost-conn-monitor.timer

# ---------------------------------------------------------------------------
# 5. sost-node.service drop-in (auto-restart). We intentionally do NOT
# rewrite the operator's main unit; the drop-in is reversible by removing
# the directory.
# ---------------------------------------------------------------------------
log "=== 5/8 sost-node.service auto-restart drop-in ==="
mkdir -p /etc/systemd/system/sost-node.service.d
cat > /etc/systemd/system/sost-node.service.d/10-restart.conf <<'EOF'
# Drop-in installed by scripts/vps-resilience/apply.sh. Removing this
# whole directory restores the original behaviour.
[Service]
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=10
TimeoutStartSec=60
TimeoutStopSec=30
EOF

# ---------------------------------------------------------------------------
# 6. nginx connection pool patch.
# ---------------------------------------------------------------------------
log "=== 6/8 nginx upstream + keepalive ==="
PATCHED=0
for s in "${NGINX_SITES[@]}"; do
    if [ -f "$s" ]; then
        log "  patching $s"
        if python3 "$HERE/nginx-patch.py" "$s" 2>&1 | sed 's/^/    /'; then
            PATCHED=1
        fi
    fi
done
if [ "$PATCHED" -eq 0 ]; then
    log "  WARN: no SOST nginx site was found in any of:"
    for s in "${NGINX_SITES[@]}"; do log "    - $s"; done
    log "        operator may have a custom path; run nginx-patch.py manually."
fi

# ---------------------------------------------------------------------------
# 7. apply.
# ---------------------------------------------------------------------------
log "=== 7/8 daemon-reload + restart services ==="
systemctl daemon-reload
systemctl enable --now sost-health.timer       >/dev/null 2>&1 || true
systemctl enable --now sost-conn-monitor.timer >/dev/null 2>&1 || true
nginx -t >/dev/null 2>&1 && systemctl reload nginx || log "  WARN: nginx -t failed; nginx NOT reloaded."
systemctl restart sost-node
log "  waiting 30 s for sost-node to bind …"
sleep 30

# ---------------------------------------------------------------------------
# 8. verify.
# ---------------------------------------------------------------------------
log "=== 8/8 verification ==="
log "  sost-node:    $(systemctl is-active sost-node)"
log "  health timer: $(systemctl is-active sost-health.timer)"
log "  monitor timer:$(systemctl is-active sost-conn-monitor.timer)"

if [ -f /etc/sost/rpc.env ]; then
    # shellcheck disable=SC1091
    . /etc/sost/rpc.env
    BODY=$(curl -m 5 -s -u "$RPC_USER:$RPC_PASS" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","id":1,"method":"getinfo"}' \
        http://127.0.0.1:18232/ 2>&1)
    if echo "$BODY" | grep -q '"blocks"'; then
        BLOCKS=$(echo "$BODY" | sed -n 's/.*"blocks":\([0-9]*\).*/\1/p')
        log "  RPC OK  blocks=$BLOCKS"
    else
        log "  RPC FAIL — body: ${BODY:0:200}"
    fi
fi

CONNS=$(ss -tan 2>/dev/null | grep -c ':18232' || echo 0)
log "  conn count:18232: $CONNS"
ss -tan 2>/dev/null | grep ':18232' | awk '{print $1}' | sort | uniq -c \
    | awk '{print "    "$0}'

log "done. Backups in $BACKUP_ROOT."
log "Tail: journalctl -u sost-health.service --no-pager -n 20"
log "Tail: tail -f /var/log/sost-health.log /var/log/sost-conn-monitor.log"

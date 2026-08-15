#!/usr/bin/env bash
# =============================================================================
# V15_NODE_ROLLBACK.sh — restore the pre-cutover node binaries on the VPS.
#
# Restores the four binaries from a timestamped backup created by
# V15_NODE_CUTOVER.sh, verifying every file against the SHA256SUMS recorded
# inside that backup before installing anything.
#
# Usage:
#   ./V15_NODE_ROLLBACK.sh                       # use the newest backup found
#   ./V15_NODE_ROLLBACK.sh --backup /opt/sost/rollback-v15final-YYYYmmdd_HHMMSS
#   ./V15_NODE_ROLLBACK.sh --list                # just list available backups
#   ./V15_NODE_ROLLBACK.sh --dry-run             # verify only, change nothing
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=v15-final.env
source "$HERE/v15-final.env"

BACKUP=""
DRY_RUN=0
LIST_ONLY=0
ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --backup)  BACKUP="$2"; shift 2;;
    --list)    LIST_ONLY=1; shift;;
    --dry-run) DRY_RUN=1; shift;;
    --yes|-y)  ASSUME_YES=1; shift;;
    -h|--help) sed -n '2,16p' "$0"; exit 0;;
    *) die "unknown argument: $1";;
  esac
done

SSH="ssh -o BatchMode=yes -o ConnectTimeout=15 -i $VPS_SSH_KEY $VPS_HOST"
$SSH true || die "cannot reach $VPS_HOST over ssh"

say "available backups on $VPS_HOST:"
$SSH "ls -1dt /opt/sost/rollback-v15final-* /opt/sost/rollback-v15-* 2>/dev/null || true"
[ $LIST_ONLY -eq 1 ] && exit 0

if [ -z "$BACKUP" ]; then
  BACKUP="$($SSH "ls -1dt /opt/sost/rollback-v15final-* 2>/dev/null | head -1" || true)"
  [ -n "$BACKUP" ] || die "no V15-FINAL backup found; pass --backup explicitly"
  warn "no --backup given, using the newest: $BACKUP"
fi

say "================================================================"
say "V15 FINAL — NODE ROLLBACK"
say "  restoring from : $BACKUP"
say "  target         : $VPS_HOST:$VPS_INSTALL_DIR"
say "  dry-run        : $([ $DRY_RUN -eq 1 ] && echo YES || echo no)"
say "================================================================"

# -----------------------------------------------------------------------------
# 1. the backup must exist, be complete, and match its own recorded checksums
# -----------------------------------------------------------------------------
say "step 1/4 — verifying the backup"
VERIFY="$($SSH "
  set -e
  [ -d '$BACKUP' ] || { echo NO_DIR; exit 0; }
  cd '$BACKUP'
  for b in sost-node sost-cli sost-miner sost-signtx; do
    [ -f \"\$b\" ] || { echo \"MISSING:\$b\"; exit 0; }
  done
  [ -f SHA256SUMS.pre-v15final.txt ] || { echo NO_SUMS; exit 0; }
  if sha256sum -c SHA256SUMS.pre-v15final.txt >/dev/null 2>&1; then echo BACKUP_OK; else echo SUMS_FAIL; fi
")"
case "$VERIFY" in
  BACKUP_OK) ok "backup complete and self-consistent";;
  NO_DIR)    die "backup directory does not exist: $BACKUP";;
  NO_SUMS)   die "backup has no SHA256SUMS.pre-v15final.txt — refusing to restore blind";;
  SUMS_FAIL) die "backup files do not match their recorded SHA256 — REFUSING to restore";;
  MISSING:*) die "backup is incomplete: ${VERIFY#MISSING:} is absent";;
  *)         die "unexpected verification result: $VERIFY";;
esac

say "backup contents:"
$SSH "cat '$BACKUP/SHA256SUMS.pre-v15final.txt'; echo; cat '$BACKUP/README.txt' 2>/dev/null || true"

if [ $DRY_RUN -eq 1 ]; then
  ok "dry-run complete — the backup is restorable; nothing was changed"
  exit 0
fi

if [ $ASSUME_YES -eq 0 ]; then
  echo
  c_ylw "This STOPS sost-node and restores the PRE-V15-FINAL binaries."
  read -r -p "[v15] proceed with rollback? type ROLLBACK: " a
  [ "$a" = "ROLLBACK" ] || die "aborted by operator"
fi

# -----------------------------------------------------------------------------
# 2. record what we are rolling back FROM (so the rollback is itself reversible)
# -----------------------------------------------------------------------------
TS="$(date -u +%Y%m%d_%H%M%S)"
PRE_ROLLBACK="/opt/sost/pre-rollback-v15final-${TS}"
say "step 2/4 — snapshotting the current (post-cutover) binaries to $PRE_ROLLBACK"
$SSH "
  set -e
  mkdir -p '$PRE_ROLLBACK'
  for b in sost-node sost-cli sost-miner sost-signtx; do
    [ -f $VPS_INSTALL_DIR/\$b ] && cp -a $VPS_INSTALL_DIR/\$b '$PRE_ROLLBACK'/\$b
  done
  (cd '$PRE_ROLLBACK' && sha256sum * > SHA256SUMS.txt)
"
ok "current binaries snapshotted (rollback is reversible)"

# -----------------------------------------------------------------------------
# 3. stop / restore / start
# -----------------------------------------------------------------------------
say "step 3/4 — stopping node, restoring, restarting"
set +e
$SSH "
  set -e
  systemctl stop $VPS_NODE_SERVICE
  for b in sost-node sost-cli sost-miner sost-signtx; do
    install -m 0755 '$BACKUP'/\$b $VPS_INSTALL_DIR/\$b
  done
  systemctl start $VPS_NODE_SERVICE
"
RC=$?
set -e
[ $RC -eq 0 ] || die "restore failed (rc=$RC) — node may be stopped. Investigate on the box NOW."

# -----------------------------------------------------------------------------
# 4. health check
# -----------------------------------------------------------------------------
say "step 4/4 — health check"
sleep 10
ACTIVE="$($SSH "systemctl is-active $VPS_NODE_SERVICE" || true)"
[ "$ACTIVE" = "active" ] && ok "service active" || die "service NOT active after rollback ($ACTIVE)"

H=""
for i in $(seq 1 30); do
  H="$($SSH "curl -s --max-time 8 -H 'content-type: application/json' \
       --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' $VPS_RPC_URL" \
     | grep -oE '\"result\":[0-9]+' | grep -oE '[0-9]+' || true)"
  [ -n "$H" ] && break
  sleep 10
done
[ -n "$H" ] || die "RPC never answered after rollback"
ok "RPC answering, height $H"

RSHA="$($SSH "sha256sum $VPS_INSTALL_DIR/sost-node | cut -d' ' -f1")"
say "restored sost-node sha256: $RSHA"
[ "$RSHA" = "$SHA_NODE_PRE" ] && ok "matches the known pre-cutover node" \
  || warn "does not match $SHA_NODE_PRE — check which backup you restored"

ok "rollback complete"
say "to undo this rollback, the post-cutover binaries are at $PRE_ROLLBACK"

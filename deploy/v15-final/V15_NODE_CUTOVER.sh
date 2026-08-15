#!/usr/bin/env bash
# =============================================================================
# V15_NODE_CUTOVER.sh — install the V15 FINAL binaries on the VPS.
#
# RUN THIS FIRST. The miner cutover (V15_MINER_CUTOVER.sh) must only run after
# this script has completed AND the chain has been observed healthy.
#
# What it does, in order:
#   1. verifies the four local binaries against the authoritative SHA256
#   2. refuses to run if the chain is already at/past the cutover deadline
#   3. uploads them to a staging dir on the VPS and re-verifies SHA256 there
#   4. backs up the four currently-installed binaries to a timestamped dir
#   5. stops the node, installs all four, starts the node
#   6. health-checks: service active, RPC answers, height >= pre-cutover height
#   7. on ANY failure after the service was stopped, prints the exact rollback
#      command and exits non-zero (it does not auto-rollback: a human decides)
#
# It NEVER touches: the miner, sost-miner.service (stays disabled), private
# keys, the website, or any consensus parameter.
#
# Usage:
#   ./V15_NODE_CUTOVER.sh [--dry-run] [--yes]
#     --dry-run   do every check and upload, but do not stop/install/start
#     --yes       skip the interactive confirmation
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=v15-final.env
source "$HERE/v15-final.env"

DRY_RUN=0
ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift;;
    --yes|-y)  ASSUME_YES=1; shift;;
    -h|--help) sed -n '2,26p' "$0"; exit 0;;
    *) die "unknown argument: $1";;
  esac
done

TS="$(date -u +%Y%m%d_%H%M%S)"
BACKUP_DIR="/opt/sost/rollback-v15final-${TS}"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15 -i $VPS_SSH_KEY $VPS_HOST"
SCP="scp -o BatchMode=yes -o ConnectTimeout=15 -i $VPS_SSH_KEY"

say "================================================================"
say "V15 FINAL — NODE CUTOVER"
say "  commit      : $V15_CODE_COMMIT"
say "  branch      : $V15_BRANCH"
say "  source      : $BUILD_DIR"
say "  target      : $VPS_HOST:$VPS_INSTALL_DIR"
say "  backup dir  : $BACKUP_DIR"
say "  dry-run     : $([ $DRY_RUN -eq 1 ] && echo YES || echo no)"
say "================================================================"

# -----------------------------------------------------------------------------
# 1. verify the local binaries — abort on any mismatch
# -----------------------------------------------------------------------------
say "step 1/7 — verifying local release binaries"
require_sha "$BUILD_DIR/sost-node"   "$SHA_NODE"   "sost-node"
require_sha "$BUILD_DIR/sost-cli"    "$SHA_CLI"    "sost-cli"
require_sha "$BUILD_DIR/sost-miner"  "$SHA_MINER"  "sost-miner"
require_sha "$BUILD_DIR/sost-signtx" "$SHA_SIGNTX" "sost-signtx"

# -----------------------------------------------------------------------------
# 2. preflight against the live chain
# -----------------------------------------------------------------------------
say "step 2/7 — preflight against the live chain"
$SSH true || die "cannot reach $VPS_HOST over ssh"

HEIGHT_PRE="$(
  $SSH "curl -s --max-time 10 -H 'content-type: application/json' \
        --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' $VPS_RPC_URL" \
  | grep -oE '\"result\":[0-9]+' | grep -oE '[0-9]+' || true
)"
[ -n "${HEIGHT_PRE:-}" ] || die "could not read the current chain height — is the node up?"
say "  current height: $HEIGHT_PRE"
say "  V15 activation: $V15_HEIGHT   deadline: $CUTOVER_DEADLINE_HEIGHT"

if [ "$HEIGHT_PRE" -ge "$CUTOVER_DEADLINE_HEIGHT" ]; then
  die "height $HEIGHT_PRE is at/past the cutover deadline $CUTOVER_DEADLINE_HEIGHT — escalate, do not improvise"
fi
ok "$(( CUTOVER_DEADLINE_HEIGHT - HEIGHT_PRE )) blocks of margin remain"

# sanity: is the installed node the one we think we are replacing?
INSTALLED_NODE_SHA="$($SSH "sha256sum $VPS_INSTALL_DIR/sost-node 2>/dev/null | cut -d' ' -f1" || true)"
say "  installed sost-node sha256: ${INSTALLED_NODE_SHA:-<none>}"
if [ "$INSTALLED_NODE_SHA" = "$SHA_NODE" ]; then
  ok "the release node is ALREADY installed — nothing to do"
  exit 0
fi
if [ "$INSTALLED_NODE_SHA" != "$SHA_NODE_PRE" ]; then
  warn "installed node is neither the expected pre-cutover binary ($SHA_NODE_PRE)"
  warn "nor the release binary. Someone changed it. Backup still proceeds, but VERIFY THIS."
  if [ $ASSUME_YES -eq 0 ]; then
    read -r -p "[v15] continue anyway? type YES: " a; [ "$a" = "YES" ] || die "aborted by operator"
  fi
fi

if [ $ASSUME_YES -eq 0 ] && [ $DRY_RUN -eq 0 ]; then
  echo
  c_ylw "This STOPS sost-node, replaces all four binaries and STARTS it again."
  read -r -p "[v15] proceed with the node cutover? type CUTOVER: " a
  [ "$a" = "CUTOVER" ] || die "aborted by operator"
fi

# -----------------------------------------------------------------------------
# 3. stage on the VPS and re-verify there
# -----------------------------------------------------------------------------
say "step 3/7 — staging binaries on the VPS"
$SSH "mkdir -p $VPS_STAGING_DIR"
for b in sost-node sost-cli sost-miner sost-signtx; do
  $SCP "$BUILD_DIR/$b" "$VPS_HOST:$VPS_STAGING_DIR/$b"
done

say "step 3b/7 — re-verifying SHA256 on the VPS (transfer integrity)"
REMOTE_OK="$($SSH "
  set -e
  cd $VPS_STAGING_DIR
  printf '%s  sost-node\n%s  sost-cli\n%s  sost-miner\n%s  sost-signtx\n' \
    '$SHA_NODE' '$SHA_CLI' '$SHA_MINER' '$SHA_SIGNTX' > .v15final.sha256
  sha256sum -c .v15final.sha256 >/dev/null 2>&1 && echo REMOTE_SHA_OK || echo REMOTE_SHA_FAIL
")"
[ "$REMOTE_OK" = "REMOTE_SHA_OK" ] || die "SHA256 mismatch on the VPS after upload — REFUSING to install"
ok "all four binaries verified on the VPS"

if [ $DRY_RUN -eq 1 ]; then
  ok "dry-run complete — nothing was stopped, installed or started"
  say "staged at $VPS_HOST:$VPS_STAGING_DIR (safe to leave; it is not on the service path)"
  exit 0
fi

# -----------------------------------------------------------------------------
# 4. backup
# -----------------------------------------------------------------------------
say "step 4/7 — backing up the currently-installed binaries"
$SSH "
  set -e
  mkdir -p $BACKUP_DIR
  for b in sost-node sost-cli sost-miner sost-signtx; do
    if [ -f $VPS_INSTALL_DIR/\$b ]; then cp -a $VPS_INSTALL_DIR/\$b $BACKUP_DIR/\$b; fi
  done
  (cd $BACKUP_DIR && sha256sum * > SHA256SUMS.pre-v15final.txt)
  printf 'backup taken %s UTC\nreplacing with commit %s\npre-cutover height %s\n' \
    '$TS' '$V15_CODE_COMMIT' '$HEIGHT_PRE' > $BACKUP_DIR/README.txt
"
ok "backup at $VPS_HOST:$BACKUP_DIR"

# -----------------------------------------------------------------------------
# 5. stop / install / start
# -----------------------------------------------------------------------------
say "step 5/7 — stopping the node, installing, restarting"
set +e
$SSH "
  set -e
  systemctl stop $VPS_NODE_SERVICE
  for b in sost-node sost-cli sost-miner sost-signtx; do
    install -m 0755 $VPS_STAGING_DIR/\$b $VPS_INSTALL_DIR/\$b
  done
  # sost-miner.service stays DISABLED — the VPS does not mine.
  systemctl start $VPS_NODE_SERVICE
"
INSTALL_RC=$?
set -e
if [ $INSTALL_RC -ne 0 ]; then
  c_red "[v15] install/restart FAILED (rc=$INSTALL_RC)"
  c_red "[v15] ROLL BACK NOW:"
  c_red "      $HERE/V15_NODE_ROLLBACK.sh --backup $BACKUP_DIR"
  exit 1
fi

# -----------------------------------------------------------------------------
# 6. health checks
# -----------------------------------------------------------------------------
say "step 6/7 — health checks"
sleep 10

FAILED=0
ACTIVE="$($SSH "systemctl is-active $VPS_NODE_SERVICE" || true)"
[ "$ACTIVE" = "active" ] && ok "service active" || { c_red "[v15] service NOT active ($ACTIVE)"; FAILED=1; }

POST_SHA="$($SSH "sha256sum $VPS_INSTALL_DIR/sost-node | cut -d' ' -f1" || true)"
[ "$POST_SHA" = "$SHA_NODE" ] && ok "installed node sha256 matches the release" \
  || { c_red "[v15] installed node sha256 is $POST_SHA, expected $SHA_NODE"; FAILED=1; }

HEIGHT_POST=""
for i in $(seq 1 30); do
  HEIGHT_POST="$(
    $SSH "curl -s --max-time 8 -H 'content-type: application/json' \
          --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' $VPS_RPC_URL" \
    | grep -oE '\"result\":[0-9]+' | grep -oE '[0-9]+' || true
  )"
  [ -n "$HEIGHT_POST" ] && break
  sleep 10
done
if [ -z "$HEIGHT_POST" ]; then
  c_red "[v15] RPC never answered after restart"; FAILED=1
else
  ok "RPC answering, height $HEIGHT_POST"
  if [ "$HEIGHT_POST" -lt "$HEIGHT_PRE" ]; then
    c_red "[v15] height REGRESSED: $HEIGHT_PRE -> $HEIGHT_POST"; FAILED=1
  else
    ok "chain height did not regress ($HEIGHT_PRE -> $HEIGHT_POST)"
  fi
fi

if [ $FAILED -ne 0 ]; then
  c_red "[v15] ================= HEALTH CHECK FAILED ================="
  c_red "[v15] ROLL BACK NOW:"
  c_red "      $HERE/V15_NODE_ROLLBACK.sh --backup $BACKUP_DIR"
  exit 1
fi

# -----------------------------------------------------------------------------
# 7. done
# -----------------------------------------------------------------------------
say "step 7/7 — node cutover complete"
ok "node now running commit $V15_CODE_COMMIT"
say "backup kept at: $VPS_HOST:$BACKUP_DIR"
echo
c_ylw "NEXT: do NOT run the miner cutover yet."
c_ylw "  1. watch the chain for at least 3 accepted blocks and confirm they keep coming"
c_ylw "  2. confirm no rejects:  ssh $VPS_HOST 'tail -50 /var/log/sost-node.log | grep -i reject'"
c_ylw "  3. only then run: $HERE/V15_MINER_CUTOVER.sh"

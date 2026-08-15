#!/usr/bin/env bash
# =============================================================================
# V15_NODE_ROLLBACK.sh — restore the pre-cutover node state on the VPS.
#
# Restores the four binaries from a timestamped backup written by
# V15_NODE_CUTOVER.sh, verifying every file against the SHA256SUMS recorded
# inside that backup before installing anything.
#
# It also knows how to restore the irreplaceable state that lives in the same
# directory (chain.json, wallet.json, genesis_block.json, popc_registry.json),
# but ONLY when --restore-data is passed explicitly. Restoring a 341 MB chain
# rewinds the node, so it is never done implicitly.
#
# Like the cutover, the critical section runs ON THE VPS as a transient systemd
# unit: a dropped SSH session cannot leave the node half-restored.
#
# This script is hardened for the case it exists to serve — a FAILED, PARTIAL
# cutover. It must work when the install dir is incomplete or empty, so it never
# depends on a bare glob matching anything (that exact bug aborted the previous
# version at the snapshot step).
#
# Usage:
#   ./V15_NODE_ROLLBACK.sh                        # newest backup, binaries only
#   ./V15_NODE_ROLLBACK.sh --backup /opt/sost/rollback-v15final-YYYYmmdd_HHMMSS
#   ./V15_NODE_ROLLBACK.sh --restore-data         # ALSO restore chain/wallet/genesis
#   ./V15_NODE_ROLLBACK.sh --list                 # list available backups
#   ./V15_NODE_ROLLBACK.sh --dry-run              # verify only, change nothing
#   ./V15_NODE_ROLLBACK.sh --monitor RUN_ID       # re-attach to a running rollback
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=v15-final.env
source "$HERE/v15-final.env"

BACKUP=""
DRY_RUN=0
LIST_ONLY=0
ASSUME_YES=0
RESTORE_DATA=0
NO_WAIT=0
MONITOR_ID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --backup)       BACKUP="${2:-}";     [ -n "$BACKUP" ]     || die "--backup needs a path";  shift 2;;
    --monitor)      MONITOR_ID="${2:-}"; [ -n "$MONITOR_ID" ] || die "--monitor needs a RUN_ID"; shift 2;;
    --restore-data) RESTORE_DATA=1; shift;;
    --list)         LIST_ONLY=1; shift;;
    --dry-run)      DRY_RUN=1; shift;;
    --yes|-y)       ASSUME_YES=1; shift;;
    --no-wait)      NO_WAIT=1; shift;;
    -h|--help)      sed -n '2,30p' "$0"; exit 0;;
    *) die "unknown argument: $1";;
  esac
done

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -i "$VPS_SSH_KEY")
rsh()  { ssh "${SSH_OPTS[@]}" "$VPS_HOST" "$@"; }
rput() { scp "${SSH_OPTS[@]}" "$1" "$VPS_HOST:$2"; }

state_get() { rsh "grep -a '^$2=' '$VPS_STATE_DIR/$1.state' 2>/dev/null | tail -1 | cut -d= -f2-" 2>/dev/null || true; }

monitor_run() {
  local rid="$1" last="" phase result ssh_lost=0
  say "monitoring rollback $rid (Ctrl-C is safe: it runs on the VPS, not here)"
  while :; do
    if ! rsh true >/dev/null 2>&1; then
      ssh_lost=1
      warn "SSH unreachable — this says NOTHING about the node. Rollback continues on the VPS."
      warn "Re-attach with: $0 --monitor $rid"
      sleep 15; continue
    fi
    [ $ssh_lost -eq 1 ] && { ok "SSH restored"; ssh_lost=0; }
    phase="$(state_get "$rid" PHASE)"
    result="$(state_get "$rid" RESULT)"
    if [ -n "$phase" ] && [ "$phase" != "$last" ]; then say "  phase: $phase"; last="$phase"; fi
    if [ -n "$result" ]; then
      echo
      case "$result" in
        SUCCESS)                       ok "RESULT: SUCCESS — rollback complete, next block accepted";;
        SUCCESS_TIMEOUT_INCONCLUSIVE)  ok "RESULT: SUCCESS (next block not observed in the window)"
                                       c_ylw "  Node healthy on every check; no block arrived in the window."
                                       c_ylw "  Normal with an external miner. Not a failure.";;
        *) c_red "[v15] RESULT: $result"
           c_red "[v15] detail: $(state_get "$rid" RESULT_DETAIL)"
           c_red "[v15] The node may be DOWN. Investigate on the box NOW:"
           c_red "      ssh $VPS_HOST 'systemctl status $VPS_NODE_SERVICE; tail -50 /var/log/sost-node.log'";;
      esac
      echo
      say "full state: ssh $VPS_HOST 'cat $VPS_STATE_DIR/$rid.state'"
      [ "$result" = "SUCCESS" ] || [ "$result" = "SUCCESS_TIMEOUT_INCONCLUSIVE" ]
      return $?
    fi
    sleep 10
  done
}

if [ -n "$MONITOR_ID" ]; then monitor_run "$MONITOR_ID"; exit $?; fi

rsh true >/dev/null 2>&1 || die "cannot reach $VPS_HOST over ssh"

say "available backups on $VPS_HOST:"
rsh "ls -1dt /opt/sost/rollback-v15final-* /opt/sost/rollback-v15-* 2>/dev/null || echo '  (none)'" || true
[ "$LIST_ONLY" -eq 1 ] && exit 0

if [ -z "$BACKUP" ]; then
  BACKUP="$(rsh "ls -1dt /opt/sost/rollback-v15final-* 2>/dev/null | head -1" 2>/dev/null || true)"
  [ -n "$BACKUP" ] || die "no V15-FINAL backup found; pass --backup explicitly"
  warn "no --backup given, using the newest: $BACKUP"
fi

RUN_ID="v15rollback-$(date -u +%Y%m%d_%H%M%S)"
UNIT="v15-rollback-${RUN_ID#v15rollback-}"

say "================================================================"
say "V15 FINAL — NODE ROLLBACK"
say "  restoring from : $BACKUP"
say "  target         : $VPS_HOST:$VPS_INSTALL_DIR"
say "  restore data   : $([ "$RESTORE_DATA" -eq 1 ] && echo "YES (chain/wallet/genesis)" || echo "no (binaries only)")"
say "  run id         : $RUN_ID"
say "  dry-run        : $([ "$DRY_RUN" -eq 1 ] && echo YES || echo no)"
say "================================================================"

# -----------------------------------------------------------------------------
# 1. verify the backup: complete, self-consistent, restorable
#    Uses an EXPLICIT file list — never a bare glob — so an empty or partial
#    install dir cannot make this step fail.
# -----------------------------------------------------------------------------
say "step 1/4 — verifying the backup"
VERIFY="$(rsh "
  set -u
  B='$BACKUP'
  [ -d \"\$B\" ] || { echo NO_DIR; exit 0; }
  for b in ${V15_BINARIES[*]}; do
    [ -f \"\$B/\$b\" ] || { echo \"MISSING:\$b\"; exit 0; }
  done
  [ -f \"\$B/SHA256SUMS.pre-v15final.txt\" ] || { echo NO_SUMS; exit 0; }
  if ( cd \"\$B\" && sha256sum -c SHA256SUMS.pre-v15final.txt >/dev/null 2>&1 ); then
    echo BACKUP_OK
  else
    echo SUMS_FAIL
  fi
" 2>/dev/null || echo SSH_FAIL)"

case "$VERIFY" in
  BACKUP_OK) ok "backup complete and self-consistent";;
  NO_DIR)    die "backup directory does not exist: $BACKUP";;
  NO_SUMS)   die "backup has no SHA256SUMS.pre-v15final.txt — refusing to restore blind";;
  SUMS_FAIL) die "backup files do not match their recorded SHA256 — REFUSING to restore";;
  SSH_FAIL)  die "could not verify the backup (ssh failed) — refusing to restore blind";;
  MISSING:*) die "backup is incomplete: ${VERIFY#MISSING:} is absent — REFUSING to restore a partial set";;
  *)         die "unexpected verification result: $VERIFY";;
esac

DATA_AVAIL="$(rsh "[ -f '$BACKUP/SHA256SUMS.data.txt' ] && echo yes || echo no" 2>/dev/null || echo no)"
say "  data backup available: $DATA_AVAIL"
if [ "$RESTORE_DATA" -eq 1 ]; then
  [ "$DATA_AVAIL" = "yes" ] || die "--restore-data requested but this backup has no data manifest"
  DVERIFY="$(rsh "cd '$BACKUP' && sha256sum -c SHA256SUMS.data.txt >/dev/null 2>&1 && echo DATA_OK || echo DATA_FAIL" 2>/dev/null || echo DATA_FAIL)"
  [ "$DVERIFY" = "DATA_OK" ] || die "the data backup does not match its manifest — REFUSING to restore chain/wallet state"
  ok "data backup verified (chain/wallet/genesis restorable)"
fi

say "backup contents:"
rsh "cat '$BACKUP/SHA256SUMS.pre-v15final.txt'; echo; [ -f '$BACKUP/SHA256SUMS.data.txt' ] && { echo 'data:'; cat '$BACKUP/SHA256SUMS.data.txt'; echo; }; cat '$BACKUP/README.txt' 2>/dev/null || true" || true

if [ "$DRY_RUN" -eq 1 ]; then
  echo
  ok "DRY RUN complete — the backup is restorable; the VPS was accessed READ-ONLY"
  exit 0
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  echo
  c_ylw "This STOPS sost-node and restores the PRE-CUTOVER binaries."
  [ "$RESTORE_DATA" -eq 1 ] && c_red "It will ALSO overwrite chain.json / wallet.json / genesis_block.json / popc_registry.json."
  read -r -p "[v15] proceed with rollback? type ROLLBACK: " a
  [ "$a" = "ROLLBACK" ] || die "aborted by operator"
fi

# -----------------------------------------------------------------------------
# 2. upload the executor and launch it as a transient unit
# -----------------------------------------------------------------------------
say "step 2/4 — staging the executor"
rsh "mkdir -p '$VPS_STAGING_DIR' '$VPS_STATE_DIR'"
rput "$HERE/v15-final.env"    "$VPS_STAGING_DIR/v15-final.env"
rput "$HERE/v15-node-exec.sh" "$VPS_STAGING_DIR/v15-node-exec.sh"
rsh "chmod 0755 '$VPS_STAGING_DIR/v15-node-exec.sh'"

RUNNING="$(rsh "systemctl list-units --state=running --no-legend 'v15-cutover-*' 'v15-rollback-*' 2>/dev/null | wc -l" 2>/dev/null || echo 0)"
[ "${RUNNING:-0}" -eq 0 ] || die "another v15 transient unit is already running on the VPS"

say "step 3/4 — launching the rollback on the VPS as transient unit $UNIT"
EXTRA=""
[ "$RESTORE_DATA" -eq 1 ] && EXTRA="--restore-data"
rsh "$SYSTEMD_RUN --unit='$UNIT' --description='SOST V15 FINAL node rollback $RUN_ID' \
       --property=RemainAfterExit=yes --property=TimeoutStartSec=infinity \
       /bin/bash '$VPS_STAGING_DIR/v15-node-exec.sh' \
         --mode rollback --run-id '$RUN_ID' --source '$BACKUP' $EXTRA" \
  || die "systemd-run failed to launch the rollback unit"

ok "rollback running on the VPS, detached from this SSH session"
say "  run id     : $RUN_ID"
say "  state file : $VPS_STATE_DIR/$RUN_ID.state"
echo
c_ylw "If this laptop drops off the network the rollback still completes."
c_ylw "Re-attach any time with:  $0 --monitor $RUN_ID"
echo

[ "$NO_WAIT" -eq 1 ] && { ok "launched (--no-wait); monitor with: $0 --monitor $RUN_ID"; exit 0; }

say "step 4/4 — monitoring"
monitor_run "$RUN_ID"

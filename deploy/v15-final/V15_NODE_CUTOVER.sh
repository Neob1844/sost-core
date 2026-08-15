#!/usr/bin/env bash
# =============================================================================
# V15_NODE_CUTOVER.sh — install the V15 FINAL binaries on the VPS.
#
# RUN THIS FIRST. The miner cutover must only run after this has completed AND
# the chain has been observed healthy.
#
# This script is only a DRIVER. The critical section (backup -> stop -> install
# -> start -> health) runs ON THE VPS as a transient systemd unit launched with
# systemd-run, so it does NOT depend on this laptop's SSH session surviving. If
# the link drops, the cutover carries on and a later, independent ssh session
# can read the whole story from the state file.
#
# Order of guarantees:
#   * the four binaries are hash-verified HERE, then again on the VPS after
#     transfer, then a third time inside the install shell immediately before
#     each install, and a fourth time after installation. Nothing installed is
#     touched until every one of those gates has passed.
#   * chain.json / wallet.json / genesis_block.json / popc_registry.json live in
#     the SAME directory as the binaries and are backed up (with sha256 + size,
#     each copy verified against its original) BEFORE the service is stopped.
#   * an installed binary that is neither the expected pre-cutover build nor the
#     release ABORTS the run. Overriding that needs --force-unknown-binary; it
#     is deliberately NOT folded into --yes.
#
# Usage:
#   ./V15_NODE_CUTOVER.sh [--dry-run] [--yes] [--force-unknown-binary]
#                         [--no-wait] [--monitor RUN_ID]
#     --dry-run                verify everything, READ-ONLY on the VPS, change nothing
#     --yes                    skip the interactive confirmation
#     --force-unknown-binary   proceed even if the installed node is unrecognised
#     --no-wait                launch and return; monitor later with --monitor
#     --monitor RUN_ID         just re-attach to a run already in progress
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=v15-final.env
source "$HERE/v15-final.env"

DRY_RUN=0
ASSUME_YES=0
FORCE_UNKNOWN=0
NO_WAIT=0
MONITOR_ID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)              DRY_RUN=1; shift;;
    --yes|-y)               ASSUME_YES=1; shift;;
    --force-unknown-binary) FORCE_UNKNOWN=1; shift;;
    --no-wait)              NO_WAIT=1; shift;;
    --monitor)              MONITOR_ID="${2:-}"; [ -n "$MONITOR_ID" ] || die "--monitor needs a RUN_ID"; shift 2;;
    -h|--help)              sed -n '2,36p' "$0"; exit 0;;
    *) die "unknown argument: $1";;
  esac
done

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -i "$VPS_SSH_KEY")
rsh()  { ssh "${SSH_OPTS[@]}" "$VPS_HOST" "$@"; }            # returns remote rc
rput() { scp "${SSH_OPTS[@]}" "$1" "$VPS_HOST:$2"; }

# read a key from the remote state file; prints empty if unreachable/absent
state_get() {                 # state_get <run-id> <key>
  rsh "grep -a '^$2=' '$VPS_STATE_DIR/$1.state' 2>/dev/null | tail -1 | cut -d= -f2-" 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# monitor-only mode
# -----------------------------------------------------------------------------
monitor_run() {               # monitor_run <run-id>
  local rid="$1" last="" phase result ssh_lost=0
  say "monitoring run $rid (Ctrl-C is safe: the cutover runs on the VPS, not here)"
  while :; do
    if ! rsh true >/dev/null 2>&1; then
      ssh_lost=1
      warn "SSH to $VPS_HOST is unreachable — this says NOTHING about the node."
      warn "The cutover continues on the VPS. Re-attach later with:"
      warn "    $0 --monitor $rid"
      sleep 15
      continue
    fi
    [ $ssh_lost -eq 1 ] && { ok "SSH restored, resuming monitoring"; ssh_lost=0; }
    phase="$(state_get "$rid" PHASE)"
    result="$(state_get "$rid" RESULT)"
    if [ -n "$phase" ] && [ "$phase" != "$last" ]; then say "  phase: $phase"; last="$phase"; fi
    if [ -n "$result" ]; then
      echo
      case "$result" in
        SUCCESS)
          ok "RESULT: SUCCESS — node cut over, next block accepted"
          ;;
        SUCCESS_TIMEOUT_INCONCLUSIVE)
          ok "RESULT: SUCCESS (next block not observed in the window)"
          c_ylw "  The node is healthy on every check. No block arrived within the wait"
          c_ylw "  window, which is NORMAL: the miner is external and gaps of 14.4 h have"
          c_ylw "  been measured. This is INCONCLUSIVE, not a failure. Do NOT roll back"
          c_ylw "  for this reason alone — just keep watching the height."
          ;;
        *)
          c_red "[v15] RESULT: $result"
          c_red "[v15] detail: $(state_get "$rid" RESULT_DETAIL)"
          c_red "[v15] installed so far: $(state_get "$rid" INSTALLED_SO_FAR)"
          c_red "[v15] ROLL BACK NOW:"
          c_red "      $HERE/V15_NODE_ROLLBACK.sh --backup $(state_get "$rid" BACKUP_DIR)"
          ;;
      esac
      echo
      say "full state: ssh $VPS_HOST 'cat $VPS_STATE_DIR/$rid.state'"
      [ "$result" = "SUCCESS" ] || [ "$result" = "SUCCESS_TIMEOUT_INCONCLUSIVE" ]
      return $?
    fi
    sleep 10
  done
}

if [ -n "$MONITOR_ID" ]; then
  monitor_run "$MONITOR_ID"
  exit $?
fi

RUN_ID="v15final-$(date -u +%Y%m%d_%H%M%S)"
BACKUP_DIR="/opt/sost/rollback-v15final-${RUN_ID#v15final-}"
UNIT="v15-cutover-${RUN_ID#v15final-}"

say "================================================================"
say "V15 FINAL — NODE CUTOVER"
say "  commit      : $V15_CODE_COMMIT"
say "  run id      : $RUN_ID"
say "  source      : $BUILD_DIR"
say "  target      : $VPS_HOST:$VPS_INSTALL_DIR"
say "  backup dir  : $BACKUP_DIR"
say "  dry-run     : $([ "$DRY_RUN" -eq 1 ] && echo YES || echo no)"
say "================================================================"

# -----------------------------------------------------------------------------
# 1. verify the local binaries — full 64-hex, abort on any mismatch
# -----------------------------------------------------------------------------
say "step 1/6 — verifying local release binaries"
require_sha "$BUILD_DIR/sost-node"   "$SHA_NODE"   "sost-node"
require_sha "$BUILD_DIR/sost-cli"    "$SHA_CLI"    "sost-cli"
require_sha "$BUILD_DIR/sost-miner"  "$SHA_MINER"  "sost-miner"
require_sha "$BUILD_DIR/sost-signtx" "$SHA_SIGNTX" "sost-signtx"

# -----------------------------------------------------------------------------
# 2. preflight — READ-ONLY on the VPS
# -----------------------------------------------------------------------------
say "step 2/6 — preflight (read-only on the VPS)"
rsh true >/dev/null 2>&1 || die "cannot reach $VPS_HOST over ssh"

HEIGHT_PRE="$(rsh "curl -s --max-time 10 -H 'content-type: application/json' --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' '$VPS_RPC_URL'" 2>/dev/null | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' || true)"
[ -n "$HEIGHT_PRE" ] || die "could not read the current chain height — is the node up?"
say "  current height : $HEIGHT_PRE"
say "  V15 activation : $V15_HEIGHT    deadline: $CUTOVER_DEADLINE_HEIGHT"
[ "$HEIGHT_PRE" -lt "$CUTOVER_DEADLINE_HEIGHT" ] \
  || die "height $HEIGHT_PRE is at/past the deadline $CUTOVER_DEADLINE_HEIGHT — escalate, do not improvise"
ok "$(( CUTOVER_DEADLINE_HEIGHT - HEIGHT_PRE )) blocks of margin remain"

# concurrent-run guard
RUNNING="$(rsh "systemctl list-units --state=running --no-legend 'v15-cutover-*' 'v15-rollback-*' 2>/dev/null | wc -l" 2>/dev/null || echo 0)"
[ "${RUNNING:-0}" -eq 0 ] || die "another v15 transient unit is already running on the VPS — refusing to start a second"

# installed binaries
INSTALLED_NODE_SHA="$(rsh "sha256sum '$VPS_INSTALL_DIR/sost-node' 2>/dev/null | cut -d' ' -f1" 2>/dev/null || true)"
say "  installed sost-node sha256: ${INSTALLED_NODE_SHA:-<unreadable>}"

if [ "$INSTALLED_NODE_SHA" = "$SHA_NODE" ]; then
  ok "the release node is ALREADY installed — nothing to do (idempotent no-op)"
  exit 0
fi

# ---- correction 13: unknown binary ABORTS, always ---------------------------
if [ -z "$INSTALLED_NODE_SHA" ]; then
  die "could not read the installed node's sha256 — refusing to proceed blind"
fi
if [ "$INSTALLED_NODE_SHA" != "$SHA_NODE_PRE" ]; then
  c_red "[v15] FATAL the installed sost-node is UNRECOGNISED."
  c_red "        installed        : $INSTALLED_NODE_SHA"
  c_red "        expected pre-cut : $SHA_NODE_PRE"
  c_red "        release          : $SHA_NODE"
  c_red "  Someone changed the binary outside this process. Establish what is running"
  c_red "  and why BEFORE cutting over."
  if [ "$FORCE_UNKNOWN" -eq 1 ]; then
    warn "--force-unknown-binary given: continuing against an unrecognised binary."
    warn "The backup will still capture whatever is currently installed."
  else
    c_red "  To override deliberately, re-run with --force-unknown-binary."
    c_red "  (--yes does NOT and will never imply this.)"
    exit 1
  fi
fi

# data files that must be backed up
say "  irreplaceable state in $VPS_INSTALL_DIR:"
rsh "for f in ${V15_DATA_FILES[*]}; do if [ -f '$VPS_INSTALL_DIR'/\$f ]; then printf '    %-22s %s bytes\n' \"\$f\" \"\$(stat -c %s '$VPS_INSTALL_DIR'/\$f)\"; else printf '    %-22s ABSENT\n' \"\$f\"; fi; done" 2>/dev/null || true

# disk headroom for binaries + chain.json copy
NEED_KB="$(rsh "du -sk $(printf "'%s/%s' " "$VPS_INSTALL_DIR" "${V15_BINARIES[@]}") $(printf "'%s/%s' " "$VPS_INSTALL_DIR" "${V15_DATA_FILES[@]}") 2>/dev/null | awk '{s+=\$1} END{print s+0}'" 2>/dev/null || echo 0)"
FREE_KB="$(rsh "df -Pk '$VPS_INSTALL_DIR' | awk 'NR==2{print \$4}'" 2>/dev/null || echo 0)"
say "  backup needs ~$(( NEED_KB / 1024 )) MB, free $(( FREE_KB / 1024 )) MB"
[ "${FREE_KB:-0}" -gt $(( NEED_KB * 2 )) ] || die "not enough free space for a verified backup (need ~2x $(( NEED_KB / 1024 )) MB)"
ok "preflight passed"

# -----------------------------------------------------------------------------
# 3. dry-run stops here — nothing has been written to the VPS
# -----------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  echo
  ok "DRY RUN complete — the VPS was accessed READ-ONLY and nothing was written"
  say "a real run would then:"
  say "  1. upload the 4 binaries + executor to $VPS_STAGING_DIR"
  say "  2. back up binaries AND ${V15_DATA_FILES[*]} to $BACKUP_DIR (verified)"
  say "  3. stop $VPS_NODE_SERVICE, install, start, health-check, stability-check"
  say "  4. wait up to ${NEXTBLOCK_WAIT_SECONDS}s for the next block (timeout = inconclusive, not failure)"
  exit 0
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  echo
  c_ylw "This STOPS sost-node, replaces all four binaries and STARTS it again."
  c_ylw "chain.json, wallet.json, genesis_block.json and popc_registry.json are"
  c_ylw "backed up first and are never written."
  read -r -p "[v15] proceed with the node cutover? type CUTOVER: " a
  [ "$a" = "CUTOVER" ] || die "aborted by operator"
fi

# -----------------------------------------------------------------------------
# 4. stage on the VPS and re-verify there
# -----------------------------------------------------------------------------
say "step 3/6 — staging binaries + executor on the VPS"
rsh "mkdir -p '$VPS_STAGING_DIR' '$VPS_STATE_DIR'"
for b in "${V15_BINARIES[@]}"; do rput "$BUILD_DIR/$b" "$VPS_STAGING_DIR/$b"; done
rput "$HERE/v15-final.env"     "$VPS_STAGING_DIR/v15-final.env"
rput "$HERE/v15-node-exec.sh"  "$VPS_STAGING_DIR/v15-node-exec.sh"
rsh "chmod 0755 '$VPS_STAGING_DIR/v15-node-exec.sh'"

say "step 4/6 — verifying SHA256 on the VPS after transfer"
REMOTE_OK="$(rsh "cd '$VPS_STAGING_DIR' && printf '%s  sost-node\n%s  sost-cli\n%s  sost-miner\n%s  sost-signtx\n' '$SHA_NODE' '$SHA_CLI' '$SHA_MINER' '$SHA_SIGNTX' > .v15final.sha256 && sha256sum -c .v15final.sha256 >/dev/null 2>&1 && echo REMOTE_SHA_OK || echo REMOTE_SHA_FAIL" 2>/dev/null || true)"
[ "$REMOTE_OK" = "REMOTE_SHA_OK" ] || die "SHA256 mismatch on the VPS after upload — REFUSING to install"
ok "all four binaries verified on the VPS"

# -----------------------------------------------------------------------------
# 5. launch the critical section as a transient systemd unit
# -----------------------------------------------------------------------------
say "step 5/6 — launching the cutover on the VPS as transient unit $UNIT"
rsh "$SYSTEMD_RUN --unit='$UNIT' --description='SOST V15 FINAL node cutover $RUN_ID' \
       --property=RemainAfterExit=yes --property=TimeoutStartSec=infinity \
       --setenv=BUILD_DIR='$VPS_STAGING_DIR' \
       /bin/bash '$VPS_STAGING_DIR/v15-node-exec.sh' \
         --mode cutover --run-id '$RUN_ID' \
         --source '$VPS_STAGING_DIR' --backup '$BACKUP_DIR'" \
  || die "systemd-run failed to launch the cutover unit"

ok "cutover running on the VPS, detached from this SSH session"
say "  run id     : $RUN_ID"
say "  unit       : $UNIT"
say "  state file : $VPS_STATE_DIR/$RUN_ID.state"
say "  backup dir : $BACKUP_DIR"
echo
c_ylw "If this laptop drops off the network the cutover still completes."
c_ylw "Re-attach any time with:  $0 --monitor $RUN_ID"
echo

if [ "$NO_WAIT" -eq 1 ]; then
  ok "launched (--no-wait); monitor with: $0 --monitor $RUN_ID"
  exit 0
fi

# -----------------------------------------------------------------------------
# 6. monitor
# -----------------------------------------------------------------------------
say "step 6/6 — monitoring"
if monitor_run "$RUN_ID"; then
  echo
  c_ylw "NEXT: do NOT run the miner cutover yet."
  c_ylw "  1. confirm the height keeps advancing over the next few blocks"
  c_ylw "  2. review the state file: ssh $VPS_HOST 'cat $VPS_STATE_DIR/$RUN_ID.state'"
  c_ylw "  3. only then consider the miner phase"
  exit 0
fi
exit 1

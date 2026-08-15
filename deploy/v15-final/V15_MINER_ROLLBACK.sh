#!/usr/bin/env bash
# =============================================================================
# V15_MINER_ROLLBACK.sh — restore the pre-cutover miner binary.
#
# Reverses V15_MINER_CUTOVER.sh using the state directory that script wrote.
# The miner is restarted with the SAME command line that was captured before
# the cutover, so --realtime (and every other flag) comes back exactly as it
# was. The binary is verified against the recorded SHA256 before installing.
#
# Usage:
#   ./V15_MINER_ROLLBACK.sh                      # newest state dir
#   ./V15_MINER_ROLLBACK.sh --state /path/to/state/dir
#   ./V15_MINER_ROLLBACK.sh --list
#   ./V15_MINER_ROLLBACK.sh --dry-run
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=v15-final.env
source "$HERE/v15-final.env"

STATE=""
DRY_RUN=0
LIST_ONLY=0
ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --state)   STATE="$2"; shift 2;;
    --list)    LIST_ONLY=1; shift;;
    --dry-run) DRY_RUN=1; shift;;
    --yes|-y)  ASSUME_YES=1; shift;;
    -h|--help) sed -n '2,16p' "$0"; exit 0;;
    *) die "unknown argument: $1";;
  esac
done

say "available miner cutover states under $MINER_STATE_DIR:"
ls -1dt "$MINER_STATE_DIR"/*/ 2>/dev/null || say "  (none)"
[ $LIST_ONLY -eq 1 ] && exit 0

if [ -z "$STATE" ]; then
  STATE="$(ls -1dt "$MINER_STATE_DIR"/*/ 2>/dev/null | head -1 || true)"
  [ -n "$STATE" ] || die "no miner cutover state found; pass --state explicitly"
  warn "no --state given, using the newest: $STATE"
fi
STATE="${STATE%/}"

say "================================================================"
say "V15 FINAL — MINER ROLLBACK"
say "  host      : $(hostname)"
say "  state dir : $STATE"
say "  dry-run   : $([ $DRY_RUN -eq 1 ] && echo YES || echo no)"
say "================================================================"

# -----------------------------------------------------------------------------
# 1. load and validate the recorded state
# -----------------------------------------------------------------------------
say "step 1/5 — loading recorded state"
[ -f "$STATE/miner.state" ]          || die "missing $STATE/miner.state"
[ -f "$STATE/sost-miner.backup" ]    || die "missing $STATE/sost-miner.backup"
[ -f "$STATE/sost-miner.backup.sha256" ] || die "missing $STATE/sost-miner.backup.sha256"

# shellcheck source=/dev/null
source "$STATE/miner.state"

: "${MINER_EXE:?state file has no MINER_EXE}"
: "${MINER_ARGC:?state file has no MINER_ARGC}"
: "${MINER_OLD_SHA:?state file has no MINER_OLD_SHA}"
MINER_CWD="${MINER_CWD:-/}"
MINER_UNIT="${MINER_UNIT:-}"

ARGV=()
for i in $(seq 0 $((MINER_ARGC - 1))); do
  v="MINER_ARGV_$i"
  ARGV+=("${!v}")
done

say "  exe  : $MINER_EXE"
say "  cwd  : $MINER_CWD"
say "  unit : ${MINER_UNIT:-<not under systemd>}"
say "  argv : ${ARGV[*]}"

# -----------------------------------------------------------------------------
# 2. verify the backup binary against BOTH recorded digests
# -----------------------------------------------------------------------------
say "step 2/5 — verifying the backup binary"
RECORDED="$(cat "$STATE/sost-miner.backup.sha256")"
ACTUAL="$(sha256_of "$STATE/sost-miner.backup")"
[ "$ACTUAL" = "$RECORDED" ]     || die "backup is corrupt: $ACTUAL != recorded $RECORDED"
[ "$ACTUAL" = "$MINER_OLD_SHA" ] || die "backup does not match MINER_OLD_SHA ($MINER_OLD_SHA)"
ok "backup binary verified ($ACTUAL)"

HAS_REALTIME=0
for a in "${ARGV[@]}"; do [ "$a" = "--realtime" ] && HAS_REALTIME=1; done
[ $HAS_REALTIME -eq 1 ] && ok "--realtime will be restored" \
                        || warn "the recorded command line has no --realtime (restoring as recorded)"

if [ $DRY_RUN -eq 1 ]; then
  ok "dry-run complete — the backup is restorable; nothing was changed"
  exit 0
fi

if [ $ASSUME_YES -eq 0 ]; then
  echo
  c_ylw "This STOPS the current miner and restores the PRE-CUTOVER binary."
  read -r -p "[v15] proceed with miner rollback? type ROLLBACK: " a
  [ "$a" = "ROLLBACK" ] || die "aborted by operator"
fi

# -----------------------------------------------------------------------------
# 3. stop whatever miner is running now
# -----------------------------------------------------------------------------
say "step 3/5 — stopping the current miner"
CUR_PID=""
for p in /proc/[0-9]*; do
  [ -r "$p/exe" ] || continue
  exe="$(readlink -f "$p/exe" 2>/dev/null || true)"
  case "$exe" in */sost-miner) CUR_PID="${p#/proc/}"; break;; esac
done

if [ -z "$CUR_PID" ]; then
  warn "no miner running — will just restore the binary and start it"
elif [ -n "$MINER_UNIT" ]; then
  systemctl stop "$MINER_UNIT"
  ok "stopped unit $MINER_UNIT"
else
  kill "$CUR_PID" 2>/dev/null || true
  for i in $(seq 1 30); do kill -0 "$CUR_PID" 2>/dev/null || break; sleep 1; done
  kill -0 "$CUR_PID" 2>/dev/null && { warn "SIGKILL required"; kill -9 "$CUR_PID" 2>/dev/null || true; sleep 2; }
  ok "stopped pid $CUR_PID"
fi

# -----------------------------------------------------------------------------
# 4. restore + restart with the recorded argv
# -----------------------------------------------------------------------------
say "step 4/5 — restoring the binary and restarting"
# keep the post-cutover binary so the rollback is itself reversible
if [ -f "$MINER_EXE" ]; then
  cp -a "$MINER_EXE" "$STATE/sost-miner.post-cutover" || true
fi
install -m 0755 "$STATE/sost-miner.backup" "$MINER_EXE"
require_sha "$MINER_EXE" "$MINER_OLD_SHA" "sost-miner (restored)"

if [ -n "$MINER_UNIT" ]; then
  systemctl start "$MINER_UNIT"
  ok "restarted via systemd unit $MINER_UNIT"
else
  LOG="$STATE/sost-miner.rollback.out"
  ( cd "$MINER_CWD" && setsid nohup "$MINER_EXE" "${ARGV[@]:1}" >> "$LOG" 2>&1 & )
  ok "restarted detached; stdout/stderr -> $LOG"
fi

# -----------------------------------------------------------------------------
# 5. health check
# -----------------------------------------------------------------------------
say "step 5/5 — health check"
sleep 8
NEW_PID=""
for p in /proc/[0-9]*; do
  [ -r "$p/exe" ] || continue
  exe="$(readlink -f "$p/exe" 2>/dev/null || true)"
  case "$exe" in */sost-miner) NEW_PID="${p#/proc/}"; break;; esac
done
[ -n "$NEW_PID" ] || die "miner did NOT come back up after rollback — investigate on this box NOW"

ok "miner running: pid=$NEW_PID"
say "  argv: $(tr '\0' ' ' < /proc/$NEW_PID/cmdline)"
ok "miner rollback complete"
say "the post-cutover binary was kept at $STATE/sost-miner.post-cutover"

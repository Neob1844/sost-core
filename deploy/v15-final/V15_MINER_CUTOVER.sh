#!/usr/bin/env bash
# =============================================================================
# V15_MINER_CUTOVER.sh — replace the sost-miner binary on the MINING MACHINE.
#
# RUN THIS SECOND, and only after V15_NODE_CUTOVER.sh has completed and the
# chain has been observed healthy. The script enforces that ordering: it
# refuses to run while the node still serves the pre-cutover binary.
#
# IT MUST BE RUN ON THE MACHINE WHERE THE MINER ACTUALLY RUNS.
# It auto-detects the live miner process and replays its command line
# VERBATIM — every flag, including --realtime, is preserved exactly. This
# cutover changes the binary and nothing else.
#
# If no miner process is running it ABORTS. It will not guess a command line:
# starting the miner with the wrong flags (notably a missing --realtime) makes
# the node reject every block.
#
# Usage:
#   ./V15_MINER_CUTOVER.sh [--dry-run] [--yes] [--binary /path/to/new/sost-miner]
#     --dry-run   detect, verify and back up, but do not stop/install/restart
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=v15-final.env
source "$HERE/v15-final.env"

DRY_RUN=0
ASSUME_YES=0
NEW_BIN="$BUILD_DIR/sost-miner"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift;;
    --yes|-y)  ASSUME_YES=1; shift;;
    --binary)  NEW_BIN="$2"; shift 2;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) die "unknown argument: $1";;
  esac
done

TS="$(date -u +%Y%m%d_%H%M%S)"
STATE_DIR="$MINER_STATE_DIR/$TS"
mkdir -p "$STATE_DIR"

say "================================================================"
say "V15 FINAL — MINER CUTOVER"
say "  host        : $(hostname)"
say "  new binary  : $NEW_BIN"
say "  state dir   : $STATE_DIR"
say "  dry-run     : $([ $DRY_RUN -eq 1 ] && echo YES || echo no)"
say "================================================================"

# -----------------------------------------------------------------------------
# 1. verify the replacement binary FIRST — never touch a miner for a bad file
# -----------------------------------------------------------------------------
say "step 1/7 — verifying the replacement binary"
require_sha "$NEW_BIN" "$SHA_MINER" "sost-miner (new)"

# -----------------------------------------------------------------------------
# 2. ordering guard — the node must already be the release build
# -----------------------------------------------------------------------------
say "step 2/7 — ordering guard: is the node already cut over?"
NODE_SHA=""
if command -v ssh >/dev/null 2>&1 && [ -f "$VPS_SSH_KEY" ]; then
  NODE_SHA="$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$VPS_SSH_KEY" "$VPS_HOST" \
              "sha256sum $VPS_INSTALL_DIR/sost-node 2>/dev/null | cut -d' ' -f1" || true)"
fi
if [ -z "$NODE_SHA" ]; then
  warn "could not read the node's sha256 over ssh — CANNOT verify the ordering guard"
  if [ $ASSUME_YES -eq 0 ]; then
    read -r -p "[v15] confirm MANUALLY that the node cutover is done. type NODEDONE: " a
    [ "$a" = "NODEDONE" ] || die "aborted by operator"
  fi
elif [ "$NODE_SHA" = "$SHA_NODE" ]; then
  ok "node is running the release build — ordering satisfied"
else
  die "node sha256 is $NODE_SHA, expected the release $SHA_NODE. Run V15_NODE_CUTOVER.sh FIRST."
fi

# -----------------------------------------------------------------------------
# 3. detect the live miner — abort if absent
# -----------------------------------------------------------------------------
say "step 3/7 — detecting the running miner"
MINER_PID=""
for p in /proc/[0-9]*; do
  [ -r "$p/exe" ] || continue
  exe="$(readlink -f "$p/exe" 2>/dev/null || true)"
  case "$exe" in */sost-miner) MINER_PID="${p#/proc/}"; break;; esac
done

if [ -z "$MINER_PID" ]; then
  c_red "[v15] FATAL no sost-miner process found on $(hostname)."
  c_red ""
  c_red "  This script REFUSES to invent a command line. Starting the miner"
  c_red "  without the flags it currently uses — above all --realtime — makes the"
  c_red "  node reject every block it produces and stalls the chain."
  c_red ""
  c_red "  Do this instead:"
  c_red "    1. find the machine that is actually mining (the block producer)"
  c_red "    2. run THIS script there, while the miner is running"
  c_red "  If the miner is stopped, start it exactly as before, then re-run."
  exit 1
fi

MINER_EXE="$(readlink -f /proc/$MINER_PID/exe)"
MINER_CWD="$(readlink -f /proc/$MINER_PID/cwd 2>/dev/null || echo /)"
MINER_USER="$(stat -c %U /proc/$MINER_PID 2>/dev/null || echo "$USER")"
mapfile -d '' -t MINER_ARGV < "/proc/$MINER_PID/cmdline"
MINER_CUR_SHA="$(sha256_of "$MINER_EXE")"

# is it under systemd?
MINER_UNIT=""
if command -v systemctl >/dev/null 2>&1; then
  MINER_UNIT="$(systemctl status "$MINER_PID" 2>/dev/null | head -1 | grep -oE '[A-Za-z0-9@._-]+\.service' || true)"
fi

ok "miner found: pid=$MINER_PID"
say "  exe    : $MINER_EXE"
say "  sha256 : $MINER_CUR_SHA"
say "  cwd    : $MINER_CWD"
say "  user   : $MINER_USER"
say "  unit   : ${MINER_UNIT:-<not under systemd>}"
say "  argv   : ${MINER_ARGV[*]}"

# --realtime must be preserved, never introduced, never dropped.
HAS_REALTIME=0
for a in "${MINER_ARGV[@]}"; do [ "$a" = "--realtime" ] && HAS_REALTIME=1; done
if [ $HAS_REALTIME -eq 1 ]; then
  ok "--realtime present — it will be preserved verbatim"
else
  warn "--realtime is NOT in the current command line."
  warn "This cutover will NOT add it (that is a behaviour change, out of scope),"
  warn "but a miner without --realtime stamps blocks ~600 s in the future and the"
  warn "node rejects them. Raise this with the operator BEFORE proceeding."
  if [ $ASSUME_YES -eq 0 ]; then
    read -r -p "[v15] keep the command line exactly as-is? type KEEPASIS: " a
    [ "$a" = "KEEPASIS" ] || die "aborted by operator"
  fi
fi

if [ "$MINER_CUR_SHA" = "$SHA_MINER" ]; then
  ok "the running miner is ALREADY the release binary — nothing to do"
  exit 0
fi

# -----------------------------------------------------------------------------
# 4. persist everything needed to restore this exact process
# -----------------------------------------------------------------------------
say "step 4/7 — recording state + backing up the current binary"
cp -a "$MINER_EXE" "$STATE_DIR/sost-miner.backup"
sha256_of "$STATE_DIR/sost-miner.backup" > "$STATE_DIR/sost-miner.backup.sha256"
{
  printf 'MINER_EXE=%q\n'  "$MINER_EXE"
  printf 'MINER_CWD=%q\n'  "$MINER_CWD"
  printf 'MINER_USER=%q\n' "$MINER_USER"
  printf 'MINER_UNIT=%q\n' "$MINER_UNIT"
  printf 'MINER_OLD_SHA=%q\n' "$MINER_CUR_SHA"
  printf 'MINER_NEW_SHA=%q\n' "$SHA_MINER"
  printf 'MINER_ARGC=%d\n'  "${#MINER_ARGV[@]}"
  for i in "${!MINER_ARGV[@]}"; do printf 'MINER_ARGV_%d=%q\n' "$i" "${MINER_ARGV[$i]}"; done
} > "$STATE_DIR/miner.state"
ok "state written to $STATE_DIR/miner.state"
ok "old binary backed up to $STATE_DIR/sost-miner.backup"

if [ $DRY_RUN -eq 1 ]; then
  ok "dry-run complete — the miner was NOT stopped and nothing was installed"
  say "rollback data is already in place at $STATE_DIR"
  exit 0
fi

if [ $ASSUME_YES -eq 0 ]; then
  echo
  c_ylw "This STOPS the miner (pid $MINER_PID), replaces $MINER_EXE and restarts it"
  c_ylw "with the IDENTICAL command line shown above."
  read -r -p "[v15] proceed with the miner cutover? type MINER: " a
  [ "$a" = "MINER" ] || die "aborted by operator"
fi

# -----------------------------------------------------------------------------
# 5. stop
# -----------------------------------------------------------------------------
say "step 5/7 — stopping the miner"
if [ -n "$MINER_UNIT" ]; then
  systemctl stop "$MINER_UNIT"
else
  kill "$MINER_PID" 2>/dev/null || true
  for i in $(seq 1 30); do kill -0 "$MINER_PID" 2>/dev/null || break; sleep 1; done
  if kill -0 "$MINER_PID" 2>/dev/null; then
    warn "miner did not exit on SIGTERM, sending SIGKILL"
    kill -9 "$MINER_PID" 2>/dev/null || true
    sleep 2
  fi
fi
kill -0 "$MINER_PID" 2>/dev/null && die "miner pid $MINER_PID is still alive — aborting before install" || ok "miner stopped"

# -----------------------------------------------------------------------------
# 6. install + restart with the identical argv
# -----------------------------------------------------------------------------
say "step 6/7 — installing the release miner and restarting"
install -m 0755 "$NEW_BIN" "$MINER_EXE"
require_sha "$MINER_EXE" "$SHA_MINER" "sost-miner (installed)"

if [ -n "$MINER_UNIT" ]; then
  systemctl start "$MINER_UNIT"
  ok "restarted via systemd unit $MINER_UNIT"
else
  LOG="$STATE_DIR/sost-miner.out"
  ( cd "$MINER_CWD" && setsid nohup "$MINER_EXE" "${MINER_ARGV[@]:1}" >> "$LOG" 2>&1 & )
  ok "restarted detached; stdout/stderr -> $LOG"
fi

# -----------------------------------------------------------------------------
# 7. health check
# -----------------------------------------------------------------------------
say "step 7/7 — health check"
sleep 8
NEW_PID=""
for p in /proc/[0-9]*; do
  [ -r "$p/exe" ] || continue
  exe="$(readlink -f "$p/exe" 2>/dev/null || true)"
  case "$exe" in */sost-miner) NEW_PID="${p#/proc/}"; break;; esac
done

if [ -z "$NEW_PID" ]; then
  c_red "[v15] miner did NOT come back up"
  c_red "[v15] ROLL BACK NOW:"
  c_red "      $HERE/V15_MINER_ROLLBACK.sh --state $STATE_DIR"
  exit 1
fi
ok "miner running again: pid=$NEW_PID"
say "  argv: $(tr '\0' ' ' < /proc/$NEW_PID/cmdline)"

echo
c_ylw "CONFIRM BEFORE WALKING AWAY:"
c_ylw "  * the next block is accepted (chain height advances within ~15 min)"
c_ylw "  * no rejects:  ssh $VPS_HOST 'tail -80 /var/log/sost-node.log | grep -i reject'"
c_ylw "  * if blocks are rejected for a future timestamp, the --realtime flag was lost:"
c_ylw "    roll back with $HERE/V15_MINER_ROLLBACK.sh --state $STATE_DIR"

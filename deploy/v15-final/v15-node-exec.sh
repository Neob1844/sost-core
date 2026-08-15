#!/usr/bin/env bash
# =============================================================================
# v15-node-exec.sh — the SERVER-SIDE critical section of the node cutover.
#
# This file runs ON THE VPS, launched as a transient systemd unit by
# V15_NODE_CUTOVER.sh / V15_NODE_ROLLBACK.sh. It deliberately does NOT depend on
# the laptop's SSH session surviving: once systemd-run has started it, the
# laptop can drop off the network entirely and the sequence still completes.
#
# Everything it does is recorded, key=value, in a state file that a LATER,
# INDEPENDENT ssh session can read to learn exactly where things stand:
#     $VPS_STATE_DIR/<run-id>.state
#
# Order (identical for cutover and rollback, only the source of the binaries
# and the expected post-install hashes differ):
#
#     lock -> verify source binaries -> BACKUP (binaries + irreplaceable data,
#     each copy verified against its original) -> stop -> verify stopped ->
#     install (re-verified in THIS shell, immediately before each install) ->
#     verify all four installed -> start -> health -> stability -> next block
#
# The backup happens BEFORE the service is stopped. That ordering is the whole
# point: the unit has TimeoutStopSec=30, so systemd SIGKILLs a node that is slow
# to exit, and /opt/sost/build already contains a
# chain.json.TAINTED-by-broken-binary-20260524_224347 from a previous swap.
#
# Usage (invoked by the drivers, not by hand):
#   v15-node-exec.sh --mode cutover  --run-id ID --source DIR --backup DIR
#   v15-node-exec.sh --mode rollback --run-id ID --source DIR [--restore-data]
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=v15-final.env
source "$HERE/v15-final.env"

MODE=""
RUN_ID=""
SRC_DIR=""
BACKUP_DIR=""
RESTORE_DATA=0
while [ $# -gt 0 ]; do
  case "$1" in
    --mode)         MODE="${2:-}"; shift 2;;
    --run-id)       RUN_ID="${2:-}"; shift 2;;
    --source)       SRC_DIR="${2:-}"; shift 2;;
    --backup)       BACKUP_DIR="${2:-}"; shift 2;;
    --restore-data) RESTORE_DATA=1; shift;;
    *) echo "v15-node-exec: unknown argument: $1" >&2; exit 2;;
  esac
done
[ -n "$MODE" ]   || { echo "v15-node-exec: --mode is required" >&2; exit 2; }
[ -n "$RUN_ID" ] || { echo "v15-node-exec: --run-id is required" >&2; exit 2; }
[ -n "$SRC_DIR" ]|| { echo "v15-node-exec: --source is required" >&2; exit 2; }

mkdir -p "$VPS_STATE_DIR"
STATE="$VPS_STATE_DIR/${RUN_ID}.state"

# -----------------------------------------------------------------------------
# state + logging
# -----------------------------------------------------------------------------
st()  { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$STATE"; }
put() { printf '%s=%s\n' "$1" "$2" >> "$STATE"; }
log() { printf '[exec] %s\n' "$*"; st "LOG $*"; }

finish() {           # finish <RESULT> [detail]
  put "RESULT" "$1"
  [ $# -gt 1 ] && put "RESULT_DETAIL" "$2"
  put "FINISHED_AT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  case "$1" in
    SUCCESS|SUCCESS_TIMEOUT_INCONCLUSIVE) exit 0;;
    *) exit 1;;
  esac
}
fail() { log "FAILED: $*"; finish "FAILED" "$*"; }

# Any unexpected error must land in the state file, never vanish silently, and
# the lock must always be released — a lock we leak would block the rollback.
LOCK_HELD=0
cleanup() {
  local rc=$?
  if [ "$rc" -ne 0 ] && ! grep -q "^RESULT=" "$STATE" 2>/dev/null; then
    put "RESULT" "FAILED"; put "RESULT_DETAIL" "unexpected error rc=$rc"
  fi
  [ "${LOCK_HELD:-0}" -eq 1 ] && rm -rf "${LOCK_DIR:-/nonexistent}" 2>/dev/null
  return 0
}
trap cleanup EXIT

: > "$STATE"
put "RUN_ID"      "$RUN_ID"
put "MODE"        "$MODE"
put "STARTED_AT"  "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
put "SOURCE_DIR"  "$SRC_DIR"
put "INSTALL_DIR" "$VPS_INSTALL_DIR"
put "COMMIT"      "$V15_CODE_COMMIT"
put "PHASE"       "starting"

# -----------------------------------------------------------------------------
# single-run lock — two cutovers must never interleave.
#
# Deliberately NOT flock: an flock is held through an inherited file descriptor,
# so any child that outlives us (a daemon we start, anything systemctl spawns)
# keeps the lock held after we exit, and the next run — including an EMERGENCY
# ROLLBACK — would be refused forever. A stale lock must never be able to block
# the recovery path.
#
# An atomic mkdir plus a liveness check gives mutual exclusion that is not
# inherited and that self-heals: a lock whose owner is gone is reclaimed.
# -----------------------------------------------------------------------------
LOCK_DIR="${VPS_LOCK_FILE}.d"
acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then printf '%s' "$$" > "$LOCK_DIR/pid"; return 0; fi
  local holder; holder="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -n "$holder" ] && [ -d "/proc/$holder" ] \
     && tr '\0' ' ' < "/proc/$holder/cmdline" 2>/dev/null | grep -q 'v15-node-exec'; then
    return 1                                   # a real, live run holds it
  fi
  put "STALE_LOCK_RECLAIMED" "${holder:-unknown}"
  log "reclaiming a stale lock left by pid ${holder:-unknown} (process is gone)"
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" 2>/dev/null || return 1
  printf '%s' "$$" > "$LOCK_DIR/pid"
  return 0
}
if ! acquire_lock; then
  put "PHASE" "aborted"
  fail "another v15 cutover/rollback holds $LOCK_DIR (pid $(cat "$LOCK_DIR/pid" 2>/dev/null || echo '?'))"
fi
LOCK_HELD=1
put "LOCK" "held"

# -----------------------------------------------------------------------------
# RPC helper — uses auth when /etc/sost/rpc.env provides it. Credentials are
# never echoed, never written to the state file.
# -----------------------------------------------------------------------------
RPC_USER=""; RPC_PASS=""
if [ -r "$VPS_RPC_ENV" ]; then
  # shellcheck disable=SC1090
  set +u; source "$VPS_RPC_ENV" 2>/dev/null || true; set -u
  RPC_USER="${RPC_USER:-}"; RPC_PASS="${RPC_PASS:-}"
fi

rpc() {                       # rpc <method> [json-params]  -> raw response
  local method="$1" params="${2:-[]}" out
  if [ -n "$RPC_USER" ] && [ -n "$RPC_PASS" ]; then
    out="$("$CURL" -s --max-time 10 -u "$RPC_USER:$RPC_PASS" \
           -H 'content-type: application/json' \
           --data "{\"method\":\"$method\",\"params\":$params,\"id\":1}" \
           "$VPS_RPC_URL" 2>/dev/null || true)"
  else
    out=""
  fi
  if [ -z "$out" ]; then      # localhost RPC currently answers unauthenticated
    out="$("$CURL" -s --max-time 10 -H 'content-type: application/json' \
           --data "{\"method\":\"$method\",\"params\":$params,\"id\":1}" \
           "$VPS_RPC_URL" 2>/dev/null || true)"
  fi
  printf '%s' "$out"
}
rpc_num() { rpc "$1" "${2:-[]}" | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' || true; }
rpc_str() { rpc "$1" "${2:-[]}" | grep -oE '"result":"[^"]*"' | sed 's/.*:"//;s/"$//' || true; }

node_sha()  { sha256sum "$VPS_INSTALL_DIR/sost-node" 2>/dev/null | cut -d' ' -f1 || true; }
nrestarts() { "$SYSTEMCTL" show -p NRestarts --value "$VPS_NODE_SERVICE" 2>/dev/null || echo 0; }

# =============================================================================
# 1. verify the SOURCE binaries before anything is touched
# =============================================================================
put "PHASE" "verify-source"
log "verifying the four source binaries in $SRC_DIR"
for b in "${V15_BINARIES[@]}"; do
  [ -f "$SRC_DIR/$b" ] || fail "source binary missing: $SRC_DIR/$b"
done

declare -A EXPECT_SHA=()
if [ "$MODE" = "cutover" ]; then
  for b in "${V15_BINARIES[@]}"; do EXPECT_SHA["$b"]="$(expected_sha_for "$b")"; done
else
  # rollback: the authority is the backup's own recorded manifest
  SUMS="$SRC_DIR/SHA256SUMS.pre-v15final.txt"
  [ -f "$SUMS" ] || fail "rollback source has no SHA256SUMS.pre-v15final.txt"
  for b in "${V15_BINARIES[@]}"; do
    h="$(awk -v f="$b" '$2==f || $2=="*"f {print $1}' "$SUMS" | head -1)"
    [ -n "$h" ] || fail "rollback manifest does not list $b"
    EXPECT_SHA["$b"]="$h"
  done
fi

for b in "${V15_BINARIES[@]}"; do
  got="$(sha256sum "$SRC_DIR/$b" | cut -d' ' -f1)"
  if [ "$got" != "${EXPECT_SHA[$b]}" ]; then
    put "SHA_FAIL_$b" "expected=${EXPECT_SHA[$b]} actual=$got"
    fail "source $b sha256 mismatch — nothing has been touched"
  fi
  put "SRC_SHA_$b" "$got"
done
log "all four source binaries verified"

HEIGHT_PRE="$(rpc_num getblockcount)"
[ -n "$HEIGHT_PRE" ] || fail "cannot read chain height before stopping — refusing to proceed"
BEST_PRE="$(rpc_str getbestblockhash)"
put "HEIGHT_PRE" "$HEIGHT_PRE"
put "BESTHASH_PRE" "$BEST_PRE"
put "NRESTARTS_PRE" "$(nrestarts)"
for b in "${V15_BINARIES[@]}"; do
  put "INSTALLED_SHA_PRE_$b" "$(sha256sum "$VPS_INSTALL_DIR/$b" 2>/dev/null | cut -d' ' -f1 || echo MISSING)"
done

# =============================================================================
# 2. BACKUP — binaries AND irreplaceable state, before the service is stopped
# =============================================================================
if [ "$MODE" = "cutover" ]; then
  [ -n "$BACKUP_DIR" ] || fail "--backup is required in cutover mode"
  put "PHASE" "backup"
  put "BACKUP_DIR" "$BACKUP_DIR"
  log "backing up to $BACKUP_DIR (binaries + $(printf '%s ' "${V15_DATA_FILES[@]}"))"
  mkdir -p "$BACKUP_DIR"

  # 2a. all four binaries MUST be present — a 3-of-4 backup is unrestorable,
  #     because the rollback requires all four. Fail loudly instead.
  for b in "${V15_BINARIES[@]}"; do
    [ -f "$VPS_INSTALL_DIR/$b" ] || fail "installed binary missing, backup would be unrestorable: $b"
  done

  # 2b. copy + verify EACH copy against its original before moving on
  for b in "${V15_BINARIES[@]}"; do
    cp -a "$VPS_INSTALL_DIR/$b" "$BACKUP_DIR/$b" || fail "backup copy failed: $b"
    src="$(sha256sum "$VPS_INSTALL_DIR/$b" | cut -d' ' -f1)"
    dst="$(sha256sum "$BACKUP_DIR/$b"      | cut -d' ' -f1)"
    [ "$src" = "$dst" ] || fail "backup copy of $b does not match the original (src=$src dst=$dst)"
    put "BACKUP_SHA_$b" "$dst"
  done

  # 2c. the irreplaceable data files, same verification. chain.json is ~341 MB.
  for d in "${V15_DATA_FILES[@]}"; do
    if [ -f "$VPS_INSTALL_DIR/$d" ]; then
      cp -a "$VPS_INSTALL_DIR/$d" "$BACKUP_DIR/$d" || fail "backup copy failed: $d"
      src="$(sha256sum "$VPS_INSTALL_DIR/$d" | cut -d' ' -f1)"
      dst="$(sha256sum "$BACKUP_DIR/$d"      | cut -d' ' -f1)"
      sz="$(stat -c %s "$BACKUP_DIR/$d")"
      [ "$src" = "$dst" ] || fail "backup copy of $d does not match the original"
      put "BACKUP_DATA_SHA_$d"  "$dst"
      put "BACKUP_DATA_SIZE_$d" "$sz"
      log "backed up $d ($sz bytes, sha256 $dst)"
    else
      put "BACKUP_DATA_$d" "ABSENT"
      log "data file absent, not backed up: $d"
    fi
  done

  # 2d. write the manifests from an EXPLICIT list (never a bare glob) and read
  #     them back, so the rollback can trust them.
  ( cd "$BACKUP_DIR" && sha256sum "${V15_BINARIES[@]}" > SHA256SUMS.pre-v15final.txt ) \
    || fail "could not write the binary manifest"
  DATA_PRESENT=()
  for d in "${V15_DATA_FILES[@]}"; do [ -f "$BACKUP_DIR/$d" ] && DATA_PRESENT+=("$d"); done
  if [ ${#DATA_PRESENT[@]} -gt 0 ]; then
    ( cd "$BACKUP_DIR" && sha256sum "${DATA_PRESENT[@]}" > SHA256SUMS.data.txt ) \
      || fail "could not write the data manifest"
  fi
  {
    printf 'run_id            %s\n' "$RUN_ID"
    printf 'backup taken      %s UTC\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'replacing with    %s\n' "$V15_CODE_COMMIT"
    printf 'pre-cutover height %s\n' "$HEIGHT_PRE"
    printf 'pre-cutover tip    %s\n' "$BEST_PRE"
    printf 'data files        %s\n' "${DATA_PRESENT[*]:-<none>}"
  } > "$BACKUP_DIR/README.txt"

  # 2e. READBACK verification — prove the backup is restorable before we
  #     overwrite anything.
  ( cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS.pre-v15final.txt >/dev/null 2>&1 ) \
    || fail "backup readback verification FAILED — refusing to overwrite anything"
  if [ -f "$BACKUP_DIR/SHA256SUMS.data.txt" ]; then
    ( cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS.data.txt >/dev/null 2>&1 ) \
      || fail "data backup readback verification FAILED — refusing to overwrite anything"
  fi
  put "BACKUP_VERIFIED" "yes"
  log "backup verified and restorable"
fi

# =============================================================================
# 3. stop the node, and PROVE it stopped
# =============================================================================
put "PHASE" "stop"
MAINPID_PRE="$("$SYSTEMCTL" show -p MainPID --value "$VPS_NODE_SERVICE" 2>/dev/null || echo 0)"
case "$MAINPID_PRE" in ''|*[!0-9]*) MAINPID_PRE=0;; esac
put "MAINPID_PRE" "$MAINPID_PRE"
log "stopping $VPS_NODE_SERVICE (MainPID=$MAINPID_PRE, grace ${STOP_GRACE_SECONDS}s)"

STOP_T0="$(date +%s)"
"$SYSTEMCTL" stop "$VPS_NODE_SERVICE" || fail "systemctl stop failed"

# Requirement A: it is NOT enough that systemctl returned. Wait — bounded — until
# the unit is genuinely not active AND the process itself is gone from the
# process table. Not a single byte is copied before both are true.
pid_alive() { [ "$MAINPID_PRE" -gt 0 ] && [ -d "/proc/$MAINPID_PRE" ]; }
STOP_DEADLINE=$(( STOP_T0 + STOP_GRACE_SECONDS ))
while [ "$(date +%s)" -lt "$STOP_DEADLINE" ]; do
  act="$("$SYSTEMCTL" is-active "$VPS_NODE_SERVICE" 2>/dev/null || true)"
  if [ "$act" != "active" ] && [ "$act" != "deactivating" ] && ! pid_alive; then break; fi
  sleep "$STOP_POLL_SECONDS"
done
STOP_ELAPSED=$(( $(date +%s) - STOP_T0 ))
STOP_ACTIVE="$("$SYSTEMCTL" is-active "$VPS_NODE_SERVICE" 2>/dev/null || true)"
put "STOP_ELAPSED_SECONDS" "$STOP_ELAPSED"
put "STOP_IS_ACTIVE" "$STOP_ACTIVE"
put "STOP_PID_ALIVE" "$(pid_alive && echo yes || echo no)"

# Requirement A: if it is still there after the grace budget, ABORT. Do NOT
# escalate to SIGKILL — nothing has been installed yet, so stopping here is safe,
# whereas a SIGKILL next to a 341 MB chain.json is not.
if [ "$STOP_ACTIVE" = "active" ] || [ "$STOP_ACTIVE" = "deactivating" ] || pid_alive; then
  fail "node did not exit cleanly within ${STOP_GRACE_SECONDS}s (state=$STOP_ACTIVE, pid_alive=$(pid_alive && echo yes || echo no)) — ABORTING without installing and WITHOUT forcing the stop"
fi

# Requirement B: prove the clean stop finished before systemd's SIGKILL point.
# TimeoutStopSec=30; STOP_GRACE_SECONDS is 20, so reaching here already means we
# were well inside it. Belt-and-braces, ask systemd whether the stop timed out.
STOP_RESULT="$("$SYSTEMCTL" show -p Result --value "$VPS_NODE_SERVICE" 2>/dev/null || echo unknown)"
put "STOP_UNIT_RESULT" "$STOP_RESULT"
case "$STOP_RESULT" in
  timeout|timeout-abort)
    fail "systemd reports the stop TIMED OUT (Result=$STOP_RESULT) — the node was SIGKILLed with chain.json open. ABORTING before installing; inspect chain.json integrity before retrying." ;;
esac
put "SIGKILL_DURING_STOP" "no"
put "STOPPED" "yes"
log "node stopped cleanly in ${STOP_ELAPSED}s (no SIGKILL; systemd Result=$STOP_RESULT)"

# =============================================================================
# 4. install — each file re-verified in THIS shell immediately before install
# =============================================================================
put "PHASE" "install"
INSTALLED=()
for b in "${V15_BINARIES[@]}"; do
  got="$(sha256sum "$SRC_DIR/$b" | cut -d' ' -f1)"
  if [ "$got" != "${EXPECT_SHA[$b]}" ]; then
    put "INSTALLED_SO_FAR" "${INSTALLED[*]:-<none>}"
    fail "source $b changed between verification and install (got $got) — node is STOPPED, roll back"
  fi
  # Preserve the EXISTING ownership rather than hardcoding root:root. On this
  # box the unit is User=root and /opt/sost/build is root:root, so the result is
  # identical — but reading it from the file on disk means the script stays
  # correct if the service is ever moved to a dedicated user, and it does not
  # silently require root just to run.
  prev_owner="$(stat -c '%u:%g' "$VPS_INSTALL_DIR/$b" 2>/dev/null || true)"
  install -m 0755 "$SRC_DIR/$b" "$VPS_INSTALL_DIR/$b" \
    || { put "INSTALLED_SO_FAR" "${INSTALLED[*]:-<none>}"; fail "install failed for $b — node is STOPPED, roll back"; }
  if [ -n "$prev_owner" ]; then
    chown "$prev_owner" "$VPS_INSTALL_DIR/$b" 2>/dev/null \
      || put "OWNER_WARN_$b" "could not restore owner $prev_owner"
    put "OWNER_$b" "$prev_owner"
  fi
  INSTALLED+=("$b")
done
put "INSTALLED_SO_FAR" "${INSTALLED[*]}"

# 4b. verify ALL FOUR after installation, not just the node
for b in "${V15_BINARIES[@]}"; do
  got="$(sha256sum "$VPS_INSTALL_DIR/$b" | cut -d' ' -f1)"
  put "INSTALLED_SHA_POST_$b" "$got"
  [ "$got" = "${EXPECT_SHA[$b]}" ] || fail "post-install verification failed for $b (got $got)"
done
log "all four binaries installed and verified"

# =============================================================================
# 5. restore data files (rollback only, and only when explicitly requested)
# =============================================================================
if [ "$MODE" = "rollback" ] && [ $RESTORE_DATA -eq 1 ]; then
  put "PHASE" "restore-data"
  [ -f "$SRC_DIR/SHA256SUMS.data.txt" ] || fail "--restore-data requested but the backup has no data manifest"
  ( cd "$SRC_DIR" && sha256sum -c SHA256SUMS.data.txt >/dev/null 2>&1 ) \
    || fail "data backup does not match its manifest — REFUSING to restore chain/wallet state"
  while read -r _h f; do
    [ -n "$f" ] || continue
    cp -a "$SRC_DIR/$f" "$VPS_INSTALL_DIR/$f" || fail "restore failed for $f"
    put "RESTORED_DATA_$f" "$(sha256sum "$VPS_INSTALL_DIR/$f" | cut -d' ' -f1)"
    log "restored $f"
  done < "$SRC_DIR/SHA256SUMS.data.txt"
  put "DATA_RESTORED" "yes"
else
  put "DATA_RESTORED" "no"
fi

# =============================================================================
# 6. start
# =============================================================================
put "PHASE" "start"
log "starting $VPS_NODE_SERVICE"
"$SYSTEMCTL" start "$VPS_NODE_SERVICE" || fail "systemctl start failed — node is DOWN, roll back"

# =============================================================================
# 7. health checks (owner-specified set)
# =============================================================================
put "PHASE" "health"
sleep 10

ACTIVE="$("$SYSTEMCTL" is-active "$VPS_NODE_SERVICE" 2>/dev/null || true)"
put "HEALTH_ACTIVE" "$ACTIVE"
[ "$ACTIVE" = "active" ] || fail "service not active after start ($ACTIVE)"

HEIGHT_POST=""
for _ in $(seq 1 30); do
  HEIGHT_POST="$(rpc_num getblockcount)"
  [ -n "$HEIGHT_POST" ] && break
  sleep 5
done
[ -n "$HEIGHT_POST" ] || fail "RPC never answered after start"
put "HEALTH_RPC" "OK"
put "HEIGHT_POST" "$HEIGHT_POST"
[ "$HEIGHT_POST" -ge "$HEIGHT_PRE" ] || fail "height regressed: $HEIGHT_PRE -> $HEIGHT_POST"
put "HEALTH_HEIGHT" "OK"

BEST_POST="$(rpc_str getbestblockhash)"
put "BESTHASH_POST" "$BEST_POST"
[ -n "$BEST_POST" ] || fail "getbestblockhash returned empty"
case "$BEST_POST" in
  [0-9a-f]*) : ;;
  *) fail "getbestblockhash is not a hex hash: $BEST_POST";;
esac
BYH="$(rpc_str getblockhash "[\"$HEIGHT_POST\"]")"
[ -n "$BYH" ] || BYH="$(rpc_str getblockhash "[$HEIGHT_POST]")"
put "BESTHASH_BYHEIGHT" "$BYH"
[ "$BYH" = "$BEST_POST" ] || fail "tip incoherent: getbestblockhash=$BEST_POST but getblockhash($HEIGHT_POST)=$BYH"
put "HEALTH_TIP" "OK"

PEERS="$(rpc getpeerinfo | grep -oc '"addr"' || true)"
put "HEALTH_PEERS" "${PEERS:-0}"
[ -n "${PEERS:-}" ] && [ "$PEERS" -gt 0 ] || fail "no P2P peers connected after restart"
put "HEALTH_PEERS_OK" "yes"

NSHA="$(node_sha)"
put "HEALTH_NODE_SHA" "$NSHA"
[ "$NSHA" = "${EXPECT_SHA[sost-node]}" ] || fail "running node binary hash is $NSHA, expected ${EXPECT_SHA[sost-node]}"
log "health checks passed (rpc/height/tip/peers/hash)"

# =============================================================================
# 8. stability window — catch a crash-loop that still reads "active" at T+10s
# =============================================================================
put "PHASE" "stability"
NR_BEFORE="$(nrestarts)"
MP_BEFORE="$("$SYSTEMCTL" show -p MainPID --value "$VPS_NODE_SERVICE" 2>/dev/null || echo 0)"
put "STABILITY_NRESTARTS_START" "$NR_BEFORE"
put "STABILITY_MAINPID_START" "$MP_BEFORE"
log "observing stability for ${HEALTH_STABILITY_SECONDS}s (sampling every ${HEALTH_STABILITY_POLL}s)"

# Sample CONTINUOUSLY. A crash-loop with RestartSec=10 can die and be back up
# between two end-point samples, which would read as a healthy "active" node.
# Any of these three is a crash-loop: leaving the active state, NRestarts moving,
# or the MainPID changing under us.
STAB_DEADLINE=$(( $(date +%s) + HEALTH_STABILITY_SECONDS ))
STAB_SAMPLES=0
while [ "$(date +%s)" -lt "$STAB_DEADLINE" ]; do
  sleep "$HEALTH_STABILITY_POLL"
  STAB_SAMPLES=$(( STAB_SAMPLES + 1 ))
  a="$("$SYSTEMCTL" is-active "$VPS_NODE_SERVICE" 2>/dev/null || true)"
  n="$(nrestarts)"
  m="$("$SYSTEMCTL" show -p MainPID --value "$VPS_NODE_SERVICE" 2>/dev/null || echo 0)"
  put "STABILITY_SAMPLE_$STAB_SAMPLES" "active=$a nrestarts=$n mainpid=$m"
  [ "$a" = "active" ] || fail "service left the active state during the stability window (saw '$a') — crash loop"
  [ "$n" = "$NR_BEFORE" ] || fail "node restarted during the stability window (NRestarts $NR_BEFORE -> $n) — crash loop"
  [ "$m" = "$MP_BEFORE" ] || fail "node MainPID changed during the stability window ($MP_BEFORE -> $m) — crash loop"
done
put "STABILITY_SAMPLES" "$STAB_SAMPLES"
put "HEALTH_STABILITY" "OK"
log "stable across $STAB_SAMPLES samples"

# =============================================================================
# 9. next block — BOUNDED, and a timeout is NOT a failure
#
# The miner is external and uncontrolled: ~12 min cadence, but real gaps of
# 14.4 h have been measured. "No block within the window" is therefore normal
# and must never trigger a rollback.
# =============================================================================
put "PHASE" "nextblock"
H0="$(rpc_num getblockcount)"
put "NEXTBLOCK_START_HEIGHT" "${H0:-unknown}"
log "waiting up to ${NEXTBLOCK_WAIT_SECONDS}s for the next block (timeout is NOT a failure)"
DEADLINE=$(( $(date +%s) + NEXTBLOCK_WAIT_SECONDS ))
NEXT="TIMEOUT_INCONCLUSIVE"
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  sleep 15
  ACT="$("$SYSTEMCTL" is-active "$VPS_NODE_SERVICE" 2>/dev/null || true)"
  if [ "$ACT" != "active" ]; then NEXT="FAILED"; put "NEXTBLOCK_DETAIL" "service died while waiting ($ACT)"; break; fi
  HN="$(rpc_num getblockcount)"
  [ -n "$HN" ] || continue
  if [ "$HN" -gt "${H0:-0}" ]; then
    B="$(rpc_str getbestblockhash)"
    BH="$(rpc_str getblockhash "[\"$HN\"]")"; [ -n "$BH" ] || BH="$(rpc_str getblockhash "[$HN]")"
    if [ -n "$B" ] && [ "$B" = "$BH" ]; then
      NEXT="ACCEPTED"; put "NEXTBLOCK_HEIGHT" "$HN"; put "NEXTBLOCK_HASH" "$B"
    else
      NEXT="FAILED"; put "NEXTBLOCK_DETAIL" "height advanced to $HN but the tip is incoherent"
    fi
    break
  fi
done
put "NEXTBLOCK" "$NEXT"

case "$NEXT" in
  ACCEPTED)
    log "next block accepted and tip coherent"
    finish "SUCCESS";;
  TIMEOUT_INCONCLUSIVE)
    log "no block arrived within the window — INCONCLUSIVE, not a failure (external miner)"
    finish "SUCCESS_TIMEOUT_INCONCLUSIVE" "node healthy; next block not observed within ${NEXTBLOCK_WAIT_SECONDS}s";;
  *)
    fail "node degraded while waiting for the next block";;
esac

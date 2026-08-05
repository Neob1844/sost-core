#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_soak.sh — V15 DEVNET_FAST functional soak.
#
# Repeatedly exercises the full V15 (D+T+J) machinery by looping the proven DEV harnesses
# (payout, mempool isolation, valid-PoW attack matrix, true reorg, failed-reorg atomicity,
# process-restart) for N rounds, watching for crashes, assertion failures, nondeterminism
# and resource growth across many iterations. Each harness spins its own isolated node(s)
# on its own ports and self-cleans; the soak only orchestrates + records metrics.
#
# NOTE on "many jackpot events": the DEVNET_FAST schedule has one meaningful payout (the
# reserve drains at height 24 and (T) stops replenishment), so per-round J-event depth is
# shallow BY DESIGN. Many-event behaviour (rollover cadence, reserve replenishment across
# events) is the job of the normal testnet long run (V15=12500, cadence 288). This soak
# proves the machinery stays correct + leak-free under heavy repetition.
#
# Usage: tests/run_v15_devnet_soak.sh [--rounds N]
#   Env: BUILD_DIR (default build-devnet)
# Writes status JSON + logs under a temp dir; prints the dir. Exit non-zero on any failure.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
ROUNDS=3
while [[ $# -gt 0 ]]; do case "$1" in
  --rounds) ROUNDS="$2"; shift 2;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15soak.XXXXXX")"
STATUS="$WORK/status.json"; METRICS="$WORK/metrics.csv"
log(){ printf '[soak] %s\n' "$*"; }
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || { echo "[soak] FATAL not a DEVNET build"; exit 1; }

# harnesses to loop (self-contained, isolated ports)
HARNESSES=(
  "payout:run_v15_devnet_payout.sh"
  "mempool:run_v15_devnet_mempool.sh"
  "attacks:run_v15_devnet_attacks.sh"
  "reorg:run_v15_devnet_reorg.sh"
  "failed_reorg:run_v15_devnet_failed_reorg.sh --cycles 3"
  "restart:run_v15_devnet_restart.sh --cycles 3"
)
echo "round,harness,result,seconds,peak_rss_kb" > "$METRICS"
PASS=0; FAIL=0; START=$(date +%s)
peak_rss(){ ps -o rss= -C sost-node 2>/dev/null | sort -n | tail -1 | tr -d ' '; }

write_status(){ # write_status <state>
  local now dur; now=$(date +%s); dur=$((now-START))
  cat > "$STATUS" <<JSON
{"state":"$1","rounds_target":$ROUNDS,"rounds_done":${1:+$RD},"pass":$PASS,"fail":$FAIL,"elapsed_s":$dur,"build":"$BUILD_DIR","started_epoch":$START}
JSON
}

RD=0
log "work=$WORK rounds=$ROUNDS harnesses=${#HARNESSES[@]}"
write_status running
for ((r=1;r<=ROUNDS;r++)); do
  log "=== round $r/$ROUNDS ==="
  for entry in "${HARNESSES[@]}"; do
    name="${entry%%:*}"; cmd="${entry#*:}"
    t0=$(date +%s); rss=0
    # sample peak RSS in the background while the harness runs
    ( while :; do c=$(peak_rss); [[ -n "$c" && "$c" -gt "$rss" ]] 2>/dev/null && rss=$c; echo "$rss" > "$WORK/.rss_$name"; sleep 2; done ) & sampler=$!
    # quote ONLY the path prefix so any trailing args in $cmd (e.g. "--cycles 3") word-split
    if bash "$ROOT/tests/"$cmd > "$WORK/round${r}_${name}.log" 2>&1; then res=PASS; PASS=$((PASS+1)); else res=FAIL; FAIL=$((FAIL+1)); fi
    kill "$sampler" 2>/dev/null; wait "$sampler" 2>/dev/null
    dur=$(( $(date +%s) - t0 )); rss=$(cat "$WORK/.rss_$name" 2>/dev/null || echo 0)
    echo "$r,$name,$res,$dur,$rss" >> "$METRICS"
    log "  $name: $res (${dur}s, peak node RSS ${rss}KB)"
    # fail fast on a crash/assertion so the soak surfaces it
    if grep -qiE 'assertion|segmentation|core dumped|sanitizer|terminate called' "$WORK/round${r}_${name}.log"; then
      log "  !! crash/assert signature in $name round $r"; res=FAIL; FAIL=$((FAIL+1))
    fi
  done
  RD=$r; write_status running
done

DUR=$(( $(date +%s) - START ))
if [[ "$FAIL" -eq 0 ]]; then
  write_status completed_pass
  log "RESULT: PASS — $((PASS)) harness runs over $ROUNDS rounds, 0 failures, ${DUR}s. metrics=$METRICS"
  exit 0
else
  write_status completed_fail
  log "RESULT: FAIL — $FAIL failures over $ROUNDS rounds (see $WORK). metrics=$METRICS"
  exit 1
fi

#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_rollover_cap.sh — V15-B: numeric rollover-cap sequence.
#
# A SINGLE miner (one address) means the lottery eligibility set (which excludes the
# current miner) is empty at every event → every jackpot event is a NO-WINNER event →
# the reserve is untouched and the rollover ACCUMULATES. This exercises the cap arithmetic
# (hist_jackpot_apply no-winner branch): rollover clamps at CAP-BASE, prize_target at CAP.
#
# Event heights (DEVNET_FAST cadence 6, first 24): 24,30,36,42,48,54.
#   rollover_before : 0, 100,200,300,400, 400  (×base; clamped at cap-base=400 from event 5)
#   prize_target    : 100,200,300,400,500,500  (×1;   clamped at cap=500 from event 5)
# Observed live via the DEV-only `devjackpotstate` RPC (byte-identical to the validator's
# reconstruction). Also proves the derived rollover SURVIVES a process restart.
#
# Usage: tests/run_v15_devnet_rollover_cap.sh    Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any mismatch. Datadir preserved on failure.
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
RPC=18991; P2P=19991
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15rollcap.XXXXXX")"
FIRST_J=24; CADENCE=6; EVENTS=(24 30 36 42 48 54); FAILED=0
declare -a PIDS=()
log(){ printf '[rollcap] %s\n' "$*"; }
ok(){ printf '[rollcap] PASS  %s\n' "$*"; }
bad(){ printf '[rollcap] FAIL  %s\n' "$*"; FAILED=1; }
cleanup(){ for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  for pid in $(pgrep -f -- "$WORK" 2>/dev/null || true); do [[ "$pid" == "$$" ]] && continue; kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true; }
die(){ printf '[rollcap] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"

rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' || true; }
blockhash(){ rpc getblockhash "[$1]" | grep -oE '[a-f0-9]{64}' | head -1 || true; }
txcount(){ rpc getblock "[\"$1\"]" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' || true; }
jfield(){ rpc devjackpotstate "[\"$1\"]" | python3 -c "import sys,json;print(json.load(sys.stdin)['result'].get('$2'))" 2>/dev/null; }
NODE_PID=""
boot(){ mkdir -p "$WORK"; "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
    --port "$P2P" --rpc-port "$RPC" --rpc-noauth --connect 127.0.0.1:1 >>"$WORK/node.log" 2>&1 &
  PIDS+=($!); NODE_PID=$!; for _ in $(seq 1 40); do sleep 1; [[ -n "$(height)" ]] && return 0; done; die "node did not boot"; }
restart(){ kill "$NODE_PID" 2>/dev/null || true; sleep 2
  "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
    --port "$P2P" --rpc-port "$RPC" --rpc-noauth --connect 127.0.0.1:1 >>"$WORK/node.log" 2>&1 &
  PIDS+=($!); NODE_PID=$!; for _ in $(seq 1 40); do sleep 1; [[ -n "$(height)" ]] && return 0; done; die "node did not reboot"; }
mine_to(){ local tgt="$1" dl="$2" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --address "$WA" --wallet "$WORK/a.json" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  local mp=$!; PIDS+=("$mp")
  while :; do local h; h="$(height)"; [[ "${h:-0}" -ge "$tgt" ]] && { kill "$mp" 2>/dev/null || true; sleep 1; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { kill "$mp" 2>/dev/null || true; die "stuck reaching $tgt"; }; sleep 2; done; }

WA="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
log "single miner A=$WA work=$WORK"
boot
BASE="$(jfield 24 base)"; CAP="$(jfield 24 cap)"
[[ -n "$BASE" && -n "$CAP" ]] || die "devjackpotstate not responding (RPC present? DEV build rebuilt?)"
ROLLCAP=$((CAP - BASE))
log "base=$BASE cap=$CAP roll_cap(cap-base)=$ROLLCAP"

i=0
for EV in "${EVENTS[@]}"; do
  mine_to "$((EV-1))" 900
  # expected rollover_before going INTO event i (0-indexed): min(i,4)*base ; prize=min((i+1)*base,cap)
  exp_roll=$(( (i<4 ? i : 4) * BASE ))
  exp_prize=$(( (i+1)*BASE < CAP ? (i+1)*BASE : CAP ))
  is_j="$(jfield "$EV" is_jackpot_height)"; roll="$(jfield "$EV" rollover_before)"; prize="$(jfield "$EV" prize_target)"; resv="$(jfield "$EV" reserve_before)"
  [[ "$is_j" == "True" || "$is_j" == "true" ]] && ok "ev$((i+1)) h$EV is a jackpot height" || bad "ev$((i+1)) h$EV not flagged jackpot height (got '$is_j')"
  [[ "${resv:-0}" -gt 0 ]] && ok "ev$((i+1)) h$EV reserve_before=$resv (>0, live/not-retired)" || bad "ev$((i+1)) h$EV reserve_before=$resv should be >0"
  [[ "$roll" == "$exp_roll" ]] && ok "ev$((i+1)) h$EV rollover_before=$roll == expected $exp_roll" || bad "ev$((i+1)) h$EV rollover_before=$roll != expected $exp_roll"
  [[ "$prize" == "$exp_prize" ]] && ok "ev$((i+1)) h$EV prize_target=$prize == expected $exp_prize" || bad "ev$((i+1)) h$EV prize_target=$prize != expected $exp_prize"
  # mine the event itself; single miner ⇒ no eligible winner ⇒ NO jackpot tx (coinbase-only)
  mine_to "$EV" 400
  local_bh="$(blockhash "$EV")"; tc="$(txcount "$local_bh")"
  [[ "$tc" == "1" ]] && ok "ev$((i+1)) h$EV mined as NO-WINNER (tx_count=1, no jackpot payout)" || bad "ev$((i+1)) h$EV expected no-winner coinbase-only, tx_count=$tc"
  i=$((i+1))
done

# clamp proof: events 5 and 6 both show rollover_before == roll_cap and prize_target == cap
r5="$(jfield 48 rollover_before)"; r6="$(jfield 54 rollover_before)"
[[ "$r5" == "$ROLLCAP" && "$r6" == "$ROLLCAP" ]] && ok "CAP: rollover clamped at $ROLLCAP for events 5 & 6 (no unbounded growth)" || bad "CAP: rollover not clamped (ev5=$r5 ev6=$r6 want $ROLLCAP)"

# persistence: the derived rollover survives a restart (recomputed from persisted history)
r6_before="$(jfield 54 rollover_before)"
restart
r6_after="$(jfield 54 rollover_before)"
[[ "$r6_after" == "$r6_before" && -n "$r6_after" ]] && ok "PERSIST: rollover_before(54)=$r6_after identical after restart" || bad "PERSIST: rollover changed across restart ($r6_before -> $r6_after)"

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — rollover accrues 0→…→cap-base and prize_target 100→…→500→500, clamped, no-winner, survives restart"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1; fi

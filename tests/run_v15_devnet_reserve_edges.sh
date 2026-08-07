#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_reserve_edges.sh — V15-C: reserve edge cases around the jackpot.
#
# The genuinely-distinct reserve properties not proven by the rollover-cap (no-winner) or the
# attack harnesses — they need a WINNER event that actually DRAINS the reserve:
#   RE-A  pre-event accounting: at the first event the reserve is >0 and a prize_target is set.
#   RE-B  drain accounting: a winner event pays min(prize, reserve_before); when reserve<prize
#         (the DEV case) the reserve is fully drained to 0 and the block carries the jackpot tx.
#   RE-C  RETIREMENT LATCH: once drained to 0, later on-cadence events are NOT paid — reserve
#         stays 0, no jackpot tx is emitted (coinbase-only), rollover stays 0. Post-V15 the
#         vault does not re-accrue, so the one-way latch holds forever.
#   RE-D  the latch holds across MULTIPLE later events (h30 and h36).
#   RE-E  the latch + reserve==0 SURVIVE a process restart (recomputed from persisted state).
#
# Uses two miners (A then B) so the first event has an eligible non-current winner, plus the
# DEV-only devjackpotstate RPC for numeric introspection.
#
# Usage: tests/run_v15_devnet_reserve_edges.sh    Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any mismatch. Datadir preserved on failure.
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
RPC=18992; P2P=19992
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15resedge.XXXXXX")"
FIRST_J=24; CADENCE=6; FAILED=0
declare -a PIDS=()
log(){ printf '[resedge] %s\n' "$*"; }
ok(){ printf '[resedge] PASS  %s\n' "$*"; }
bad(){ printf '[resedge] FAIL  %s\n' "$*"; FAILED=1; }
cleanup(){ for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  for pid in $(pgrep -f -- "$WORK" 2>/dev/null || true); do [[ "$pid" == "$$" ]] && continue; kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true; }
die(){ printf '[resedge] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
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
mine_to(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  local mp=$!; PIDS+=("$mp")
  while :; do local h; h="$(height)"; [[ "${h:-0}" -ge "$tgt" ]] && { kill "$mp" 2>/dev/null || true; sleep 1; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { kill "$mp" 2>/dev/null || true; die "stuck reaching $tgt"; }; sleep 2; done; }

WA="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
WB="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
log "A=$WA B=$WB work=$WORK"
boot

mine_to "$WA" "$WORK/a.json" "$((FIRST_J-11))" 900
# Snapshot the pre-event reserve with a 2-block margin (FIRST_J-2) so a 1-block miner overshoot
# still leaves tip < FIRST_J — devjackpotstate reports the LIVE reserve, which is only a valid
# "pre-event" reading while the tip has not yet reached (and drained at) the event height.
mine_to "$WB" "$WORK/b.json" "$((FIRST_J-2))" 900     # tip 22 (≤23 even with +1 overshoot), pre-event

# RE-A: pre-event accounting
r0="$(jfield "$FIRST_J" reserve_before)"; p0="$(jfield "$FIRST_J" prize_target)"; isj="$(jfield "$FIRST_J" is_jackpot_height)"
h_pre="$(height)"
[[ "${h_pre:-99}" -lt "$FIRST_J" ]] && [[ "$isj" == "True" || "$isj" == "true" ]] && [[ "${r0:-0}" -gt 0 ]] && [[ "${p0:-0}" -gt 0 ]] \
  && ok "RE-A: h$FIRST_J pre-event (tip=$h_pre) reserve_before=$r0 (>0), prize_target=$p0" || bad "RE-A: unexpected pre-event state (tip=$h_pre isj=$isj r0=$r0 p0=$p0)"

# RE-B: mine the winner event; it must carry a jackpot tx and drain the reserve
mine_to "$WB" "$WORK/b.json" "$FIRST_J" 400
tc="$(txcount "$(blockhash "$FIRST_J")")"
[[ "$tc" == "2" ]] && ok "RE-B1: winner event h$FIRST_J carries the jackpot tx (tx_count=2)" || bad "RE-B1: h$FIRST_J tx_count=$tc (expected 2, winner paid)"
r_after="$(jfield "$((FIRST_J+1))" reserve_before)"   # reserve going into h25 == reserve after h24 payout
[[ "${r_after:-x}" == "0" ]] && ok "RE-B2: reserve fully drained to 0 (payout=min(prize,reserve)=$r0, reserve<prize)" || bad "RE-B2: reserve_after=$r_after (expected 0, full drain)"

# RE-C: retirement latch at the next event h30
EV2=$((FIRST_J+CADENCE))
mine_to "$WB" "$WORK/b.json" "$EV2" 400
r2="$(jfield "$EV2" reserve_before)"; roll2="$(jfield "$EV2" rollover_before)"; tc2="$(txcount "$(blockhash "$EV2")")"
[[ "${r2:-x}" == "0" ]] && ok "RE-C1: h$EV2 reserve_before=0 (stays drained — no post-V15 re-accrual)" || bad "RE-C1: h$EV2 reserve_before=$r2 (expected 0)"
[[ "$tc2" == "1" ]] && ok "RE-C2: RETIREMENT LATCH — h$EV2 emits NO jackpot tx (coinbase-only, tx_count=1)" || bad "RE-C2: h$EV2 tx_count=$tc2 (expected 1, retired)"
[[ "${roll2:-x}" == "0" ]] && ok "RE-C3: rollover stays 0 after retirement (no accrual on a retired jackpot)" || bad "RE-C3: rollover_before=$roll2 (expected 0)"

# RE-D: latch holds at a further event h36
EV3=$((FIRST_J+2*CADENCE))
mine_to "$WB" "$WORK/b.json" "$EV3" 400
r3="$(jfield "$EV3" reserve_before)"; tc3="$(txcount "$(blockhash "$EV3")")"
[[ "${r3:-x}" == "0" && "$tc3" == "1" ]] && ok "RE-D: latch holds at h$EV3 (reserve=0, tx_count=1, no jackpot)" || bad "RE-D: h$EV3 reserve=$r3 tx_count=$tc3 (expected 0 / 1)"

# RE-E: latch + reserve==0 survive a restart
restart
r3b="$(jfield "$EV3" reserve_before)"; h_now="$(height)"
[[ "${r3b:-x}" == "0" && "$h_now" == "$EV3" ]] && ok "RE-E: reserve==0 + retirement recomputed identically after restart (tip h$h_now)" || bad "RE-E: post-restart reserve=$r3b tip=$h_now (expected 0 / $EV3)"

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — winner drain accounting + one-way retirement latch (no resurrection) + survives restart"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1; fi

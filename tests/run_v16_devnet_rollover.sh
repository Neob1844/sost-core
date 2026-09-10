#!/usr/bin/env bash
# =============================================================================
# run_v16_devnet_rollover.sh — DTD Jackpot V2 rollover -> 500 cap, end-to-end.
# build-devnet-v2e (V2@18; jackpots #24,#30,#36,#42,#48,#54 ...). NOBODY binds a
# node, so every V2 jackpot has 0 eligible -> rolls over. The pot must climb
# 100 -> 200 -> 300 -> 400 -> 500 and then HOLD at the 500 cap (no winner invented,
# no fallback to the DTD-normal winner, funds preserved).
#   Env: BUILD_DIR (default build-devnet-v2e)
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet-v2e}"
WORK="$(mktemp -d /tmp/v16roll.XXXXXX)"
P2P=$(( (RANDOM%20000)+22000 )); RPC=$(( P2P+1 ))
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"; FAILED=0
log(){ printf '[rollover] %s\n' "$*"; }
ok(){  printf '[rollover] PASS  %s\n' "$*"; }
bad(){ printf '[rollover] FAIL  %s\n' "$*"; FAILED=1; }
NODE_PID=""; MINER_PID=""
stopm(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; pkill -P $$ sost-miner 2>/dev/null; MINER_PID=""; true; }
cleanup(){ stopm; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; true; }
die(){ printf '[rollover] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
[[ -x "$NODE" && -x "$MINER" && -x "$CLI" ]] || die "binaries missing in $BUILD_DIR"
rpc(){ curl -s --max-time 15 -H 'content-type: application/json' --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
jget(){ rpc getjackpotv2audit "[$1]"; }   # -> json
field(){ echo "$1" | grep -oE "\"$2\":[0-9]+" | grep -oE '[0-9]+' | head -1; }
mine_to(){ local a="$1" w="$2" t="$3" dl="$4" t0; t0=$(date +%s); "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --address "$a" --wallet "$w" --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 & MINER_PID=$!; while :; do local h; h="$(height)"; [[ -z "$h" ]]&&{ sleep 1; continue; }; [[ "$h" -ge "$t" ]]&&{ stopm; return; }; [[ $(($(date +%s)-t0)) -ge "$dl" ]]&&{ stopm; die "did not reach $t"; }; sleep 2; done; }

log "work=$WORK rpc=$RPC (V2@18)"
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" --port "$P2P" --rpc-port "$RPC" --rpc-noauth --connect 127.0.0.1:1 >>"$WORK/node.log" 2>&1 & NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && break; done
[[ -n "$(height)" ]] || die "node no RPC"
M="$("$CLI" --wallet "$WORK/m.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"; [[ -n "$M" ]] || die wallet
log "miner=$M (NO node bind -> every V2 jackpot has 0 eligible)"

# mine past #54 so #24..#54 are all in the chain (nobody bound)
mine_to "$M" "$WORK/m.json" 55 260
log "height=$(height)"

# expected pot at the k-th empty jackpot = min(k*base, cap)
declare -a JH=(24 30 36 42 48 54)
k=0
for h in "${JH[@]}"; do
  k=$((k+1)); J="$(jget $h)"
  isv2="$(echo "$J" | grep -oE '"is_v2_jackpot":(true|false)' | cut -d: -f2)"
  pot="$(field "$J" current_pot_stocks)"; base="$(field "$J" base_stocks)"; cap="$(field "$J" cap_stocks)"; elig="$(field "$J" eligible_count)"
  exp=$(( k*base )); [[ $exp -gt $cap ]] && exp=$cap
  log "#$h: is_v2=$isv2 eligible=$elig current_pot=$pot expected=$exp (cap=$cap)"
  [[ "$isv2" == "true" ]] && ok "#$h is a V2 jackpot" || bad "#$h not v2"
  [[ "${elig:-x}" == "0" ]] && ok "#$h has 0 eligible (nobody bound)" || bad "#$h eligible=$elig (want 0)"
  [[ "${pot:-x}" == "$exp" ]] && ok "#$h pot = $exp stocks (rollover step $k)" || bad "#$h pot=$pot want $exp"
done

# cap held: #48 and #54 both at cap
P48="$(field "$(jget 48)" current_pot_stocks)"; P54="$(field "$(jget 54)" current_pot_stocks)"; CAP="$(field "$(jget 54)" cap_stocks)"
[[ "$P48" == "$CAP" && "$P54" == "$CAP" ]] && ok "pot HELD at 500 cap (#48==#54==cap, no overflow)" || bad "cap not held: #48=$P48 #54=$P54 cap=$CAP"

# no jackpot tx / no payout at any rolled-over height (tx_count must be 1)
for h in "${JH[@]}"; do
  bh="$(rpc getblockhash "[$h]" | grep -oE '[a-f0-9]{64}')"; tc="$(rpc getblock "[\"$bh\"]" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' | head -1)"
  [[ "$tc" == "1" ]] || bad "#$h tx_count=$tc (rolled-over jackpot must have NO jackpot tx)"
done
ok "every rolled-over jackpot has NO payout tx (funds preserved in reserve)"

[[ "$FAILED" == "0" ]] && echo "[rollover] RESULT: PASS — V2 rollover 100->200->300->400->500 then HELD at cap; no winner invented; funds preserved" || echo "[rollover] RESULT: FAIL"
exit "$FAILED"

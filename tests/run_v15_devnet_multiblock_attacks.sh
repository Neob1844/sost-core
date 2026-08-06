#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_multiblock_attacks.sh — V15-A multi-block / stateful attack coverage.
#
# Covers the consensus-attack properties that a single in-block mutation cannot express
# (they need real chain state, restart, reindex or cross-branch context). Fresh DEV ports
# (~18990), isolated datadir per scenario, no interference with other harnesses/the miner.
#
# Implemented so far:
#   M08 — replay of a REJECTED attack block AFTER a node restart (byte-exact).
#         The restart harness only proves HONEST reload; this proves a malicious block
#         rejected before a restart is STILL rejected, byte-for-byte, after the restart,
#         with the reserve never spent — then an honest block is accepted.
#         (Gap identified in attack-coverage-map.md #8.)
#
# Uses a DEV-only miner flag --dump-block <file> (#ifdef SOST_DEVNET_FORKS) to capture the
# exact JSON of the malicious block the miner submits, so it can be replayed verbatim.
#
# Usage: tests/run_v15_devnet_multiblock_attacks.sh
#   Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any mismatch. Datadirs/logs preserved on failure.
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
RPC=18990; P2P=19990
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15mbattack.XXXXXX")"
FIRST_J=24; PRE_J=23; FAILED=0
GOLD="sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"; POPC="sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"
declare -a PIDS=()
log(){ printf '[mbattack] %s\n' "$*"; }
ok(){ printf '[mbattack] PASS  %s\n' "$*"; }
bad(){ printf '[mbattack] FAIL  %s\n' "$*"; FAILED=1; }
cleanup(){
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  if [[ -n "${WORK:-}" ]]; then
    for pid in $(pgrep -f -- "$WORK" 2>/dev/null || true); do [[ "$pid" == "$$" ]] && continue; kill "$pid" 2>/dev/null || true; done
  fi
  wait 2>/dev/null || true
}
die(){ printf '[mbattack] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"

rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' || true; }
tiphash(){ rpc getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1 || true; }
blockhash(){ rpc getblockhash "[$1]" | grep -oE '[a-f0-9]{64}' | head -1 || true; }
txcount(){ rpc getblock "[\"$1\"]" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' || true; }
reserve_tc(){ rpc getaddressutxos "[\"$1\"]" | python3 -c 'import sys,json
try: d=json.load(sys.stdin); r=d.get("result",[]); print(sum(int(u.get("amount_stocks",0)) for u in r), len(r))
except Exception: print(0,0)'; }
reserve(){ local gs gc ps pc; read -r gs gc < <(reserve_tc "$GOLD"); read -r ps pc < <(reserve_tc "$POPC"); echo "$((gs+ps)):$((gc+pc))"; }
rejects(){ local c; c="$(grep -c 'REJECTED by process_block' "$WORK/node.log" 2>/dev/null)"; echo "${c:-0}"; }
start(){ "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" --port "$P2P" --rpc-port "$RPC" \
    --rpc-noauth --connect 127.0.0.1:1 >>"$WORK/node.log" 2>&1 &
  PIDS+=($!); NODE_PID=$!
  for _ in $(seq 1 40); do sleep 1; [[ -n "$(height)" ]] && return 0; done; die "node did not boot"; }
stop(){ [[ -n "${NODE_PID:-}" ]] && kill "$NODE_PID" 2>/dev/null || true; sleep 2; NODE_PID=""; }
mine_to(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  local mp=$!; PIDS+=("$mp")
  while :; do local h; h="$(height)"; [[ "${h:-0}" -ge "$tgt" ]] && { kill "$mp" 2>/dev/null || true; sleep 1; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { kill "$mp" 2>/dev/null || true; die "stuck reaching $tgt"; }; sleep 2; done; }
submit_file(){ rpc submitblock "[$(python3 -c 'import json,sys;print(json.dumps(open(sys.argv[1]).read()))' "$1")]" >/dev/null; }

WA="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
WB="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
log "A=$WA B=$WB work=$WORK (rpc=$RPC)"

# === pre-J fixture ===
start
mine_to "$WA" "$WORK/a.json" "$((FIRST_J-11))" 300
mine_to "$WB" "$WORK/b.json" "$PRE_J" 300
[[ "$(height)" == "$PRE_J" ]] || die "expected pre-J height $PRE_J"
RES0="$(reserve)"; TIP0="$(tiphash)"
[[ "${RES0%%:*}" -gt 0 ]] && ok "pre-J fixture h$PRE_J (reserve $RES0, tip ${TIP0:0:16}…)" || bad "reserve empty pre-J"

# === M08 — replay of a rejected attack block after restart (byte-exact) ===
log "M08: capturing an exact malicious block (--attack-jackpot wrong-winner --dump-block)…"
MAL="$WORK/mal_block.json"
rej0="$(rejects)"
"$MINER" --profile dev --rpc "127.0.0.1:$RPC" --address "$WB" --wallet "$WORK/b.json" \
  --mining-key-label default --attack-jackpot wrong-winner --dump-block "$MAL" \
  --blocks 100000 --threads 3 >>"$WORK/attack.log" 2>&1 &
AMP=$!; PIDS+=("$AMP")
t0=$(date +%s)
while :; do
  [[ -s "$MAL" ]] && [[ "$(rejects)" -gt "$rej0" ]] && break
  [[ $(($(date +%s)-t0)) -ge 60 ]] && break
  sleep 2
done
kill "$AMP" 2>/dev/null || true; sleep 1
[[ -s "$MAL" ]] || die "no malicious block captured (dump-block empty)"
MAL_H="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("height"))' "$MAL" 2>/dev/null || echo '?')"
[[ "$MAL_H" == "$FIRST_J" ]] && ok "captured exact malicious block at height $MAL_H" || bad "captured block height=$MAL_H (expected $FIRST_J)"
# pre-restart: attack was rejected, state unchanged
[[ "$(height)" == "$PRE_J" && "$(reserve)" == "$RES0" && "$(tiphash)" == "$TIP0" ]] \
  && ok "M08 pre-restart: attack REJECTED, tip/height/reserve unchanged" || bad "M08 pre-restart: state moved"

log "M08: restarting the node from the same datadir…"
stop
start
[[ "$(height)" == "$PRE_J" ]] || bad "M08: node did not reload to h$PRE_J after restart (got $(height))"
rej1="$(rejects)"
submit_file "$MAL"       # replay the IDENTICAL bytes
sleep 3
if [[ "$(height)" == "$PRE_J" && "$(reserve)" == "$RES0" && "$(tiphash)" == "$TIP0" && "$(rejects)" -gt "$rej1" ]]; then
  ok "M08 post-restart: the SAME malicious block is STILL rejected; reserve never spent ($RES0)"
else
  bad "M08 post-restart: replayed attack NOT rejected identically (h=$(height) res=$(reserve) tip=$(tiphash) rej=$(rejects) vs $rej1)"
fi

# honest control: an honest jackpot block is accepted after all of this
mine_to "$WB" "$WORK/b.json" "$FIRST_J" 200
BH="$(blockhash "$FIRST_J")"
[[ "$(height)" == "$FIRST_J" && "$(txcount "$BH")" == "2" ]] \
  && ok "honest jackpot block $FIRST_J accepted after the restart-replay (chain continues)" \
  || bad "honest block $FIRST_J not accepted after M08"
stop

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — M08: a rejected attack block stays rejected byte-for-byte across a node restart; reserve never spent; honest block accepted"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else
  log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1
fi

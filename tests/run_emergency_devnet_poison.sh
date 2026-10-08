#!/usr/bin/env bash
# =============================================================================
# run_emergency_devnet_poison.sh — LIVE node proof for the 2026-10-08 V30000 audit
# (CRITICAL #2): node-tx mempool poisoning must fail AT THE NODE, not at a proxy.
#
# DEVNET_FAST (participation live at #42, epoch length 6). Against a real sost-node:
#   P1  138-byte NODE_BIND with a corrupted signature  -> sendrawtransaction REJECTED
#   P2  heartbeat for a FUTURE epoch / unbound node     -> REJECTED
#   P3  two miners bind the SAME node key (each valid alone, together an invalid
#       block): the template must carry at most ONE of them
#   P4  the chain keeps advancing after every probe (no halt)
#   C1  a legitimate NODE_BIND is still accepted and mined (positive control)
# Usage: tests/run_emergency_devnet_poison.sh <devnet-build-dir>
# On the unfixed 7b9ac273 node P1/P3/P4 are expected to FAIL (the bug).
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/build-devnet}"
WORK="$(mktemp -d /tmp/emgpoison.XXXXXX)"
P2P_PORT=$(( (RANDOM % 20000) + 20000 )); RPC_PORT=$(( P2P_PORT + 1 ))
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
FAILED=0
log(){ printf '[poison] %s\n' "$*"; }
ok(){  printf '[poison] PASS  %s\n' "$*"; }
bad(){ printf '[poison] FAIL  %s\n' "$*"; FAILED=1; }
NODE_PID=""; MINER_PID=""
stop_miner(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null || true; wait "$MINER_PID" 2>/dev/null || true; MINER_PID=""; }
cleanup(){ stop_miner; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup EXIT
[[ -x "$NODE" && -x "$MINER" && -x "$CLI" ]] || { echo "binaries missing in $BUILD_DIR"; exit 2; }
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" || { echo "$BUILD_DIR is not DEVNET"; exit 2; }
rpc(){ curl -s --max-time 15 -H 'content-type: application/json' --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' || true; }
mempool_n(){ rpc getmempoolinfo | grep -oE '"size":[0-9]+' | grep -oE '[0-9]+'; }
# mine until height >= tgt or deadline; returns 0 if reached
mine_to(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0 h; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC_PORT" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  MINER_PID=$!
  while :; do h="$(height)"; [[ -n "$h" && "$h" -ge "$tgt" ]] && { stop_miner; return 0; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { stop_miner; return 1; }; sleep 2; done; }

log "work=$WORK build=$BUILD_DIR"
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
  --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-noauth --connect 127.0.0.1:1 >"$WORK/node.log" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && break; done
[[ -n "$(height)" ]] || { echo "node has no RPC"; exit 2; }
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
mine_to "$A" "$WORK/a.json" 43 900 || { echo "could not reach #43"; exit 2; }
log "height=$(height) (participation live from #42)"

# ---- P1: 138-byte NODE_BIND with corrupted signature ----
N1="$(openssl rand -hex 32)"
GOOD="$("$CLI" --wallet "$WORK/a.json" createnodebind 1 "$N1" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
[[ ${#GOOD} -gt 200 ]] || { echo "createnodebind failed"; exit 2; }
PL_LEN_HEX="${GOOD:$(( (4+1+1+1+8+1+20)*2 )):4}"
log "bind payload_len field = 0x$PL_LEN_HEX (138 = 0x8a00 LE)"
LAST="${GOOD: -2}"; FLIP=$(printf '%02x' $(( 0x$LAST ^ 0xff )))
POISON="${GOOD:0:${#GOOD}-2}$FLIP"
R1="$(rpc sendrawtransaction "[\"$POISON\"]")"; log "P1 response: ${R1:0:200}"
if echo "$R1" | grep -q '"error"' && [[ "$(mempool_n)" == "0" ]]; then ok "P1 138-byte bad-sig NODE_BIND REJECTED by the node (mempool empty)"
else bad "P1 poison ADMITTED (mempool=$(mempool_n))"; fi

# ---- P2: future-epoch heartbeat from an unbound node key ----
TIP="$(rpc getblockhash "[41]" | grep -oE '[a-f0-9]{64}')"
HB="$("$CLI" --wallet "$WORK/a.json" nodeheartbeat "$N1" 5 "$TIP" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
R2="$(rpc sendrawtransaction "[\"$HB\"]")"; log "P2 response: ${R2:0:200}"
echo "$R2" | grep -q '"error"' && ok "P2 future-epoch / unbound heartbeat REJECTED" || bad "P2 heartbeat ADMITTED"

H0="$(height)"
if mine_to "$A" "$WORK/a.json" $((H0+2)) 300; then ok "P4a chain advanced after P1/P2 ($H0 -> $(height))"
else bad "P4a chain HALTED after P1/P2 (stuck at $(height))"; fi

# ---- P3: same node key bound by two miners (each valid alone) ----
N2="$(openssl rand -hex 32)"
BA="$("$CLI" --wallet "$WORK/a.json" createnodebind 1 "$N2" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
BB="$("$CLI" --wallet "$WORK/b.json" createnodebind 1 "$N2" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
RA="$(rpc sendrawtransaction "[\"$BA\"]")"; RB="$(rpc sendrawtransaction "[\"$BB\"]")"
log "P3 A: ${RA:0:120}"; log "P3 B: ${RB:0:120}"
TC="$(rpc getblocktemplate "[\"$A\"]" | grep -oE '"count":[0-9]+' | grep -oE '[0-9]+')"
log "P3 template tx count=$TC mempool=$(mempool_n)"
[[ "${TC:-9}" -le 1 ]] && ok "P3 template carries at most ONE of the conflicting binds" || bad "P3 template carries $TC conflicting binds"
grep -q '\[TEMPLATE\] dropped invalid node tx' "$WORK/node.log" && log "node log: $(grep '\[TEMPLATE\]' "$WORK/node.log" | head -1)"
H1="$(height)"
if mine_to "$A" "$WORK/a.json" $((H1+3)) 300; then ok "P4b chain advanced after P3 ($H1 -> $(height))"
else bad "P4b chain HALTED after P3 (stuck at $(height))"; fi

# ---- C1: legitimate bind still mined (positive control) ----
N3="$(openssl rand -hex 32)"
BC="$("$CLI" --wallet "$WORK/b.json" createnodebind 2 "$N3" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
RC="$(rpc sendrawtransaction "[\"$BC\"]")"; log "C1 response: ${RC:0:160}"
H2="$(height)"; mine_to "$A" "$WORK/a.json" $((H2+2)) 300 || true
if echo "$RC" | grep -q '"result"' && [[ "$(height)" -gt "$H2" ]]; then ok "C1 legitimate NODE_BIND accepted and chain advanced"
else bad "C1 legitimate bind path broken (resp=${RC:0:80}, height=$(height))"; fi

log "rejections in node log: $(grep -cE 'REJECTED|node tx invalid' "$WORK/node.log" || true)"
[[ $FAILED -eq 0 ]] && log "RESULT: PASS — node-tx poisoning rejected at the node, chain live" \
                    || log "RESULT: FAIL (logs in $WORK)"
exit $FAILED

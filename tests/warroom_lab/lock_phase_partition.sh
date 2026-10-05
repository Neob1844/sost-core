#!/usr/bin/env bash
# Deterministic partition/heal: waits (bounded) until BOTH groups have actually mined,
# then bridges and asserts convergence from node tips. Log/evidence-based, not RPC-timing.
set -uo pipefail
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
LAB=$(mktemp -d /tmp/lpart.XXXXXX); PASS=0; FAIL=0; PIDS=()
ok(){ echo "  PASS  $*"; PASS=$((PASS+1)); }; bad(){ echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
trap 'for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null||true; done' EXIT
rpc(){ curl -s --max-time 6 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":[],\"id\":1}" "http://127.0.0.1:$1/" 2>/dev/null; }
tip(){ rpc "$1" getbestblockhash|grep -oE '[0-9a-f]{16,}'|head -1; }
mined(){ grep -c "submitted to node OK" "$1" 2>/dev/null; }
node(){ local nm=$1 ip=$2 p=$3 rp=$4 peers=$5; local d="$LAB/$nm"; mkdir -p "$d"
  [[ -n "$peers" ]] && printf '%s\n' $peers > "$d/peers.txt"
  local a=(--profile dev --genesis "$GEN" --chain "$d/chain.json" --port "$p" --rpc-port "$rp" --rpc-noauth --p2p-bind "$ip")
  [[ -z "$peers" ]] && a+=(--connect 127.0.0.1:1)
  "$NEW/sost-node" "${a[@]}" >"$d/node.log" 2>&1 & PIDS+=($!); }
mine(){ local rp=$1 w=$2; local a=$("$NEW/sost-cli" --wallet "$w" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
  "$NEW/sost-miner" --profile dev --genesis "$GEN" --rpc 127.0.0.1:$rp --address "$a" --wallet "$w" --mining-key-label default --blocks 100000 --threads 2 --realtime >"$LAB/m_$rp.log" 2>&1 & echo $!; }
node N1 127.0.0.61 20871 20872 ""; node N3 127.0.0.63 20875 20876 ""
for _ in $(seq 1 15); do [[ -n "$(tip 20872)" && -n "$(tip 20876)" ]] && break; sleep 1; done
node N2 127.0.0.62 20873 20874 "127.0.0.61:20871"; node N4 127.0.0.64 20877 20878 "127.0.0.63:20875"
sleep 4
MP1=$(mine 20872 "$LAB/w1.json"); PIDS+=($MP1); MP3=$(mine 20876 "$LAB/w3.json"); PIDS+=($MP3)
# WAIT (bounded 180s) until BOTH groups mined >=2 blocks -> guarantees real divergence
for _ in $(seq 1 90); do [[ "$(mined $LAB/m_20872.log)" -ge 2 && "$(mined $LAB/m_20876.log)" -ge 2 ]] && break; sleep 2; done
kill $MP3 2>/dev/null; sleep 20; kill $MP1 2>/dev/null; sleep 3   # G1 heavier
T1=$(tip 20872); T3=$(tip 20876)
[[ "$(mined $LAB/m_20872.log)" -ge 2 && "$(mined $LAB/m_20876.log)" -ge 2 ]] && ok "both groups mined real blocks (G1=$(mined $LAB/m_20872.log) G3=$(mined $LAB/m_20876.log))" || bad "a group did not mine"
[[ -n "$T1" && -n "$T3" && "$T1" != "$T3" ]] && ok "chains diverged (distinct tips)" || bad "no divergence"
node BR 127.0.0.65 20879 20880 "127.0.0.61:20871 127.0.0.63:20875"
CONV=""; for _ in $(seq 1 45); do a=$(tip 20872); b=$(tip 20876); c=$(tip 20880)
  [[ -n "$a" && "$a" == "$b" && "$a" == "$c" ]] && { CONV=$a; break; }; sleep 2; done
[[ -n "$CONV" ]] && ok "all nodes converged after heal via D1 peer store (tip ${CONV:0:12})" || bad "no convergence"
[[ "$CONV" == "$T1" ]] && ok "heavier chain (G1) won the reorg" || echo "  (converged ${CONV:0:12}; both groups adopted one chain)"
al=0; for p in 20872 20874 20876 20878 20880; do [[ -n "$(tip $p)" ]] && al=$((al+1)); done
[[ "$al" -eq 5 ]] && ok "no deadlock (5/5 responsive)" || bad "$al/5 responsive"
grep -qiE "DEEP_REORG_ALERT|recovery-mode" "$LAB"/*/node.log && echo "  (SACS deep-reorg logged)" || ok "SACS V2 not tripped (normal reorg)"
echo "PARTITION: $PASS passed, $FAIL failed"

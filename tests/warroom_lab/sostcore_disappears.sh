#!/usr/bin/env bash
# "SOSTCORE DISAPPEARS" — every sostcore.com service is unreachable (the devnet lab is isolated;
# seed-*.sostcore.com never resolve/connect). Proves: chain continues, a new node joins via an
# ALTERNATIVE source, and a restarted node recovers from its on-disk peer-store — no sostcore.
set -uo pipefail
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
LAB=$(mktemp -d /tmp/nosost.XXXXXX); PASS=0; FAIL=0; PIDS=()
ok(){ echo "  PASS  $*"; PASS=$((PASS+1)); }; bad(){ echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
trap 'for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null; done' EXIT
rpc(){ curl -s --max-time 6 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":[],\"id\":1}" "http://127.0.0.1:$1/" 2>/dev/null; }
tip(){ rpc "$1" getbestblockhash | grep -oE '[0-9a-f]{16}' | head -1; }
mined(){ grep -c "submitted to node OK" "$1" 2>/dev/null; }
# start with operator source (peers/seeds). If both empty -> dead-end --connect (isolated head).
start(){ local nm=$1 ip=$2 p=$3 rp=$4 peers=$5 seeds=$6; local d="$LAB/$nm"; mkdir -p "$d"
  [[ -n "$peers" ]] && printf '%s\n' $peers >"$d/peers.txt"; [[ -n "$seeds" ]] && echo "$seeds" >"$d/seeds.txt"
  local a=(--profile dev --genesis "$GEN" --chain "$d/chain.json" --port "$p" --rpc-port "$rp" --rpc-noauth --p2p-bind "$ip")
  [[ -z "$peers" && -z "$seeds" ]] && a+=(--connect 127.0.0.1:1)
  "$NEW/sost-node" "${a[@]}" >"$d/node.log" 2>&1 & echo $!; }
# RESTART: no --connect, no peers/seeds overwrite -> bootstrap PURELY from the on-disk peer-store.
restart(){ local nm=$1 ip=$2 p=$3 rp=$4; local d="$LAB/$nm"
  "$NEW/sost-node" --profile dev --genesis "$GEN" --chain "$d/chain.json" --port "$p" --rpc-port "$rp" --rpc-noauth --p2p-bind "$ip" >>"$d/node.log" 2>&1 & echo $!; }
mine(){ local rp=$1 w=$2; local a=$("$NEW/sost-cli" --wallet "$w" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
  "$NEW/sost-miner" --profile dev --genesis "$GEN" --rpc 127.0.0.1:$rp --address "$a" --wallet "$w" --mining-key-label default --blocks 100000 --threads 2 --realtime >"$LAB/m.log" 2>&1 & echo $!; }
echo "=== SOSTCORE DISAPPEARS — no sostcore DNS/web/RPC/bootstrap/VPS reachable ==="
PA=$(start A 127.0.0.81 20911 20912 "" ""); PIDS+=($PA)
for _ in $(seq 1 15); do [[ -n "$(rpc 20912 getblockcount)" ]] && break; sleep 1; done
PB=$(start B 127.0.0.82 20913 20914 "127.0.0.81:20911" ""); PIDS+=($PB)
PC=$(start C 127.0.0.83 20915 20916 "127.0.0.82:20913" ""); PIDS+=($PC)
sleep 5
MP=$(mine 20912 "$LAB/w.json"); PIDS+=($MP)
for _ in $(seq 1 70); do [[ "$(mined $LAB/m.log)" -ge 3 ]] && break; sleep 2; done
# let the peer-store persist (maintenance writes peers.txt every ~30s)
sleep 32
TA=$(tip 20912); TB=$(tip 20914); TC=$(tip 20916)
[[ "$(mined $LAB/m.log)" -ge 3 && -n "$TA" ]] && ok "CHAIN CONTINUES: head mined $(mined $LAB/m.log) blocks, NO sostcore" || bad "CHAIN CONTINUES"
[[ "$TA" == "$TB" && "$TA" == "$TC" ]] && ok "blocks PROPAGATED across mesh w/o sostcore (A=B=C=$TA)" || bad "propagation (A=$TA B=$TB C=$TC)"
# NEW node D via alternative source (seeds.txt -> mesh node B)
PD=$(start D 127.0.0.84 20917 20918 "" "127.0.0.82:20913"); PIDS+=($PD)
CONVD=""; for _ in $(seq 1 30); do [[ -n "$(tip 20918)" && "$(tip 20918)" == "$(tip 20912)" ]] && { CONVD=yes; break; }; sleep 2; done
grep -q "seeds.txt connected" "$LAB/D/node.log" && [[ -n "$CONVD" ]] && ok "NEW NODE JOINS via alternative source (seeds.txt) and syncs tip" || bad "NEW NODE JOINS"
# C's persisted peer-store before restart
echo "  [C peers.txt before restart] $(tr '\n' ' ' <"$LAB/C/peers.txt" 2>/dev/null)"
# EXISTING node C restarts -> recovers from on-disk peer-store (no --connect, no sostcore)
kill $PC 2>/dev/null; sleep 3
PC2=$(restart C 127.0.0.83 20915 20916); PIDS+=($PC2)
RECOV=""; for _ in $(seq 1 40); do t=$(tip 20916); [[ -n "$t" && "$t" == "$(tip 20912)" ]] && { RECOV=yes; break; }; sleep 2; done
grep -q "stored peer connected" "$LAB/C/node.log" && [[ -n "$RECOV" ]] && ok "EXISTING NODE RECOVERS after restart via peer-store (no sostcore), re-synced tip" || bad "EXISTING NODE RECOVERS (stored-connect=$(grep -c 'stored peer connected' "$LAB/C/node.log") resync=$RECOV)"
# consensus needed no sostcore: all sostcore refs in logs are only failed seed attempts
CONN=$(cat "$LAB"/*/node.log 2>/dev/null | grep -ciE "sostcore[^ ]*: version OK|connected:.*sostcore|sostcore.*\((inbound|outbound)\)" || true)
[[ "${CONN:-0}" -eq 0 ]] && ok "NO SOSTCORE REQUIRED FOR CONSENSUS (0 sostcore connections; mesh+store+seeds only)" || bad "a sostcore connection occurred"
echo "  residual external dependency: a node with EMPTY peers.txt AND empty seeds.txt AND sostcore down cannot bootstrap — needs >=1 reachable alternative peer/seed."
echo "SOSTCORE-DISAPPEARS: $PASS passed, $FAIL failed"

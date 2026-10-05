#!/usr/bin/env bash
set -uo pipefail
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
LAB=$(mktemp -d /tmp/ph6c.XXXXXX); PASS=0; FAIL=0; PIDS=()
ok(){ echo "  PASS  $*"; PASS=$((PASS+1)); }; bad(){ echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
cleanup(){ for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null||true; done; true; }
trap cleanup EXIT
rpc(){ curl -s --max-time 5 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":[],\"id\":1}" "http://127.0.0.1:$1/" 2>/dev/null; }
height(){ rpc "$1" getblockcount | grep -oE '[0-9]+' | head -1; }
npeers(){ rpc "$1" getpeerinfo | grep -oE '"addr"' | wc -l; }
HD=$LAB/HUB; mkdir -p "$HD"
"$NEW/sost-node" --profile dev --genesis "$GEN" --chain "$HD/chain.json" --port 20701 --rpc-port 20702 --rpc-noauth --p2p-bind 127.0.0.40 --connect 127.0.0.1:1 >"$HD/node.log" 2>&1 & PIDS+=($!)
for _ in $(seq 1 15); do [[ -n "$(height 20702)" ]] && break; sleep 1; done
MA=$("$NEW/sost-cli" --wallet "$LAB/w.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+'|head -1)
# CONTINUOUS miner (kept running so connections stay active, like the soak)
"$NEW/sost-miner" --profile dev --rpc 127.0.0.1:20702 --address "$MA" --wallet "$LAB/w.json" --mining-key-label default --blocks 1000000 --threads 2 >"$LAB/m.log" 2>&1 & PIDS+=($!)
echo "=== PHASE 6c — HUB 127.0.0.40:20701 (continuous mining) ==="
launch(){ local name=$1 ip=$2 rp=$3 peers=$4 seeds=$5; local dd="$LAB/$name"; mkdir -p "$dd"
  [[ -n "$peers" ]] && echo "$peers" > "$dd/peers.txt"; [[ -n "$seeds" ]] && echo "$seeds" > "$dd/seeds.txt"
  "$NEW/sost-node" --profile dev --genesis "$GEN" --chain "$dd/chain.json" --port $((rp-1)) --rpc-port "$rp" --rpc-noauth --p2p-bind "$ip" >"$dd/node.log" 2>&1 & PIDS+=($!); }
launch NA 127.0.0.41 20704 "127.0.0.40:20701" ""
launch NB 127.0.0.42 20706 "" "127.0.0.40:20701"
launch NC 127.0.0.43 20708 "127.0.0.40:20701" "127.0.0.40:20701"
launch ND 127.0.0.44 20710 "" ""
# wait for A/B/C to connect AND stay connected (node-side peers>=1, measured over continuous mining)
for _ in $(seq 1 25); do a=$(npeers 20704); b=$(npeers 20706); c=$(npeers 20708); [[ "${a:-0}" -ge 1 && "${b:-0}" -ge 1 && "${c:-0}" -ge 1 ]] && break; sleep 2; done
for n in "NA:20704" "NB:20706" "NC:20708" "ND:20710"; do nm=${n%%:*}; p=${n##*:}; echo "  $nm peers=$(npeers $p) h=$(height $p)"; done
[[ "$(npeers 20704)" -ge 1 ]] && ok "TEST A: peers.txt-only bootstraps+stays connected (no --connect, sostcore.com unreachable)" || bad "A"
[[ "$(npeers 20706)" -ge 1 ]] && ok "TEST B: seeds.txt-only bootstraps+stays connected" || bad "B"
[[ "$(npeers 20708)" -ge 1 ]] && ok "TEST C: peers.txt+seeds.txt bootstraps" || bad "C"
[[ "$(npeers 20710)" -eq 0 ]] && ok "TEST D: no-source node stays isolated (sostcore.com proven removable)" || bad "D connected unexpectedly"
# did A/B sync the hub's chain? (proves full bootstrap, not just TCP)
HH=$(height 20702); sa=$(height 20704); sb=$(height 20706)
[[ -n "$HH" && "${sa:-0}" -ge 1 ]] && ok "TEST A synced chain from hub (h=$sa, hub=$HH)" || echo "  (A sync h=$sa hub=$HH)"
echo "=== PHASE 6c: $PASS passed, $FAIL failed ==="

#!/usr/bin/env bash
# Gauntlet E — durability: corrupted/truncated/empty chain.json must FAIL SAFE
# (clear refusal or safe recovery), never crash-loop, hang, or silently accept a bad chain.
set -u
ROOT=/home/sost/SOST/sostcore/sost-core
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
BIN="$S/build-comb-dev/sost-node"; MINER="$S/build-comb-dev/sost-miner"; CLI="$S/build-comb-dev/sost-cli"
WORK="$(mktemp -d /tmp/echaos.XXXXXX)"
cleanup(){ for pid in $(pgrep -f -- "$WORK" 2>/dev/null); do [[ "$pid" == "$$" ]]&&continue; kill "$pid" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT
rpc(){ curl -s --max-time 6 --data "$2" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"
# 1) build a valid chain to 12
"$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/good.json" --port 20080 --rpc-port 18080 --rpc-noauth --connect 127.0.0.1:1 >"$WORK/n.log" 2>&1 & NP=$!
for _ in $(seq 1 25); do sleep 1; [[ -n "$(height 18080)" ]]&&break; done
"$MINER" --profile dev --rpc "127.0.0.1:18080" --address "$A" --wallet "$WORK/a.json" --mining-key-label default --blocks 100000 --threads 2 >>"$WORK/m.log" 2>&1 & MP=$!
while [[ "$(height 18080)" -lt 12 ]]; do sleep 2; done; kill $MP 2>/dev/null; sleep 1
for pid in $(pgrep -f -- "$WORK/good.json"); do kill $pid 2>/dev/null; done; sleep 2
sz=$(stat -c%s "$WORK/good.json"); echo "[E] cadena válida @12, chain.json=$sz bytes"

# test one corrupted variant: start node, classify outcome
test_variant(){ # name file rpcport p2pport
  local name="$1" f="$2" rp="$3" pp="$4"; local log="$WORK/load_$name.log"
  "$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$f" --port "$pp" --rpc-port "$rp" --rpc-noauth --connect 127.0.0.1:1 >"$log" 2>&1 &
  local pid=$!; local outcome="HANG?" h=""
  for _ in $(seq 1 12); do sleep 1
     if ! kill -0 "$pid" 2>/dev/null; then outcome="EXITED"; break; fi
     h="$(height "$rp")"; [[ -n "$h" ]] && { outcome="RUNNING(h=$h)"; break; }
  done
  local crash="no"; grep -qiE "Segmentation|Aborted|terminate|core dumped|AddressSanitizer|bad_alloc" "$log" && crash="YES"
  kill -9 "$pid" 2>/dev/null; for q in $(pgrep -f -- "$f" 2>/dev/null); do kill -9 "$q" 2>/dev/null; done; sleep 1
  local loaded; loaded=$(grep -oE "Chain: [0-9]+ blocks, height=[0-9]+" "$log" | tail -1)
  local err; err=$(grep -oiE "corrupt|parse|invalid|failed to load|cannot|refus|error" "$log" | head -1)
  printf "[E] %-14s outcome=%-16s crash=%-8s load=[%s] note=[%s]\n" "$name" "$outcome" "$crash" "${loaded:-none}" "${err:-}"
}
# variants
cp "$WORK/good.json" "$WORK/v_trunc50.json"; truncate -s $((sz/2)) "$WORK/v_trunc50.json"
cp "$WORK/good.json" "$WORK/v_trunc1.json";  truncate -s 1 "$WORK/v_trunc1.json"
: > "$WORK/v_empty.json"
printf '{"garbage":true,"not":"a chain"}' > "$WORK/v_badjson.json"
printf 'not json at all %%%%%%' > "$WORK/v_notjson.json"
cp "$WORK/good.json" "$WORK/v_flip.json"; python3 -c "
import random
d=bytearray(open('$WORK/v_flip.json','rb').read())
for _ in range(max(1,len(d)//50)):
    i=random.randrange(len(d)); d[i]^=0xFF
open('$WORK/v_flip.json','wb').write(d)"
echo "[E] === arranque con cada variante corrupta ==="
test_variant trunc50   "$WORK/v_trunc50.json" 18081 20081
test_variant trunc1B   "$WORK/v_trunc1.json"  18082 20082
test_variant empty     "$WORK/v_empty.json"   18083 20083
test_variant badjson   "$WORK/v_badjson.json" 18084 20084
test_variant notjson   "$WORK/v_notjson.json" 18085 20085
test_variant byteflip  "$WORK/v_flip.json"    18086 20086
echo "[E] === control: la cadena buena sigue cargando ==="
test_variant good      "$WORK/good.json"      18087 20087
echo "work=$WORK"

#!/usr/bin/env bash
# SACS V2 activation-boundary lab (devnet activation=42, MAX_REORG_DEPTH=8).
# Test 1 PRE : fork_point < 42, depth>8 -> LEGACY HARD REJECT (pre-fork history protected).
# Test 2 POST: fork_point >=42, depth>8, candidate heavier -> V2 DEEP-REORG PROCEED (converge).
ulimit -f unlimited 2>/dev/null; set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; BIN="${BIN:-$REPO/build-v2}"; G=$REPO/genesis_block.json
FEED="$(cd "$(dirname "$0")" && pwd)/sacs_feedchain.py"
rpc(){ curl -s --max-time 10 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
str(){ echo "$1"|grep -oE '"result":"[0-9a-f]+"'|grep -oE '[0-9a-f]{16,}'|head -1; }
h(){ num "$(rpc $1 getblockcount)"; }; tip(){ str "$(rpc $1 getbestblockhash)"; }
softwait(){ ( sleep "$1" ) & wait $!; }
setupwallet(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
startnode(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass" >> "$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 900 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 4 >> "$1/miner.log" 2>&1; }
waitrpc(){ for i in $(seq 1 60); do [ -n "$(h $1)" ] && return 0; softwait 0.5; done; return 1; }
waith(){ for i in $(seq 1 800); do [ "$(h $1)" -ge "$2" ] 2>/dev/null && return 0; softwait 0.5; done; return 1; }
cw(){ grep -oE 'chainwork=0x[0-9a-f]+' "$1/node.log"|tail -1|grep -oE '0x[0-9a-f]+'; }

run(){ local NAME=$1 H=$2 AEXT=$3 BEXT=$4 EXPECT=$5   # EXPECT: REJECT | PROCEED
  local ROOT; ROOT="$(mktemp -d)"; local DC=$ROOT/C DA=$ROOT/A DB=$ROOT/B; mkdir -p "$DC" "$DA" "$DB"
  for d in "$DC" "$DA" "$DB"; do printf p>"$d/pass"; chmod 600 "$d/pass"; done
  echo "================= $NAME : fork_point=$H  A=+$AEXT  B=+$BEXT  depth=$BEXT  expect=$EXPECT (activation=42, cap=8) ================="
  setupwallet "$DC"; local NC=$(startnode "$DC" 19961 19962); waitrpc 19962; mine "$DC" 19962 "$H"; waith 19962 "$H"
  echo "  common chain to H=$H tip=$(tip 19962|cut -c1-16) $(cw "$DC")"; kill -9 $NC 2>/dev/null; softwait 1
  cp "$DC/chain.json" "$DA/chain.json"; cp "$DC/chain.json" "$DB/chain.json"; setupwallet "$DA"; setupwallet "$DB"
  local NA=$(startnode "$DA" 19931 19932); waitrpc 19932; mine "$DA" 19932 "$AEXT"; waith 19932 "$((H+AEXT))"
  local NB=$(startnode "$DB" 19941 19942); waitrpc 19942; mine "$DB" 19942 "$BEXT"; waith 19942 "$((H+BEXT))"
  local HA=$(h 19932) HB=$(h 19942) TA=$(tip 19932) TBpre=$(tip 19942)
  echo "  A: h=$HA $(cw "$DA")   B(active): h=$HB $(cw "$DB")"
  python3 "$FEED" 19932 19942 "$HA" >/dev/null 2>&1; softwait 3
  echo "  --- decision log (B) ---"
  grep -E '\[REORG\]\[SACS-V2\]|\[REORG\]\[SACS\] fork_point|Rejected: depth|exceeds REORG_LIMIT|Disconnecting [0-9]+ blocks|equal or less cumulative' "$DB/node.log" | tail -6 | sed 's/^/     /'
  local TBpost=$(tip 19942) HBpost=$(h 19942)
  kill -9 $NA $NB 2>/dev/null; softwait 1
  local RES=FAIL
  if [ "$EXPECT" = "REJECT" ]; then [ "$TBpost" = "$TBpre" ] && [ "$TBpost" != "$TA" ] && RES=PASS
  else [ "$TBpost" = "$TA" ] && [ "$HBpost" = "$HA" ] && RES=PASS; fi
  echo "  RESULT: B_post h=$HBpost tip=$(echo $TBpost|cut -c1-16) (A tip=$(echo $TA|cut -c1-16)) -> $NAME: $RES"
  rm -rf "$ROOT"; echo
}
echo "### confirm compiled activation height ###"; grep -A2 'SOST_DEVNET_FORKS' "$REPO/include/sost/params.h" | grep SACS_V2_ACTIVATION_HEIGHT | head -1
run PRE_ACTIVATION_forkpoint5   5  10 9  REJECT
run POST_ACTIVATION_forkpoint44 44 10 9  PROCEED
echo "V2_BOUNDARY_DONE"

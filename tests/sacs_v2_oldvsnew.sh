#!/usr/bin/env bash
# SACS V2 · OLD-node (no V2, build-sacs) vs NEW-node (V2, build-v2). Common chain to
# H=44 (>= activation 42), A extends heavier, feed A to both. Expected: OLD rejects
# (legacy depth cap) -> keeps its chain; NEW proceeds (V2) -> converges. => HARD FORK.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
NEW="$SP/wt-v2/build-v2"; OLD="$SP/wt-tsan/build-sacs"; G="$SP/wt-v2/genesis_block.json"
FEED="$SP/wt-v2/tests/sacs_feedchain.py"
[ -f "$FEED" ] || FEED="$SP/wt-tsan/tests/sacs_feedchain.py"
ROOT="$(mktemp -d)"; echo "ROOT=$ROOT"
rpc(){ curl -s --max-time 10 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
str(){ echo "$1"|grep -oE '"result":"[0-9a-f]+"'|grep -oE '[0-9a-f]{16,}'|head -1; }
h(){ num "$(rpc $1 getblockcount)"; }; tip(){ str "$(rpc $1 getbestblockhash)"; }
sw(){ ( sleep "$1" ) & wait $!; }
wallet(){ "$1/sost-cli" newwallet --wallet "$2/w.json" >/dev/null 2>&1; "$1/sost-cli" getnewaddress m --wallet "$2/w.json" >/dev/null 2>&1; }
node(){ nice -n 19 "$1/sost-node" --profile dev --noseed --genesis "$G" --chain "$2/chain.json" --wallet "$2/w.json" --port $3 --rpc-port $4 --rpc-user u --rpc-pass-file "$2/pass" >>"$2/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 900 "$1/sost-miner" --profile dev --genesis "$G" --chain "$2/chain.json" --wallet "$2/w.json" --mining-key-label m --rpc 127.0.0.1:$3 --rpc-user u --rpc-pass-file "$2/pass" --blocks "$4" --realtime --threads 4 >>"$2/miner.log" 2>&1; }
waitrpc(){ for i in $(seq 1 60); do curl -s --max-time 3 -o /dev/null http://127.0.0.1:$1/ 2>/dev/null && return 0; sw 0.5; done; return 1; }
waith(){ for i in $(seq 1 800); do [ "$(h $1)" -ge "$2" ] 2>/dev/null && return 0; sw 0.5; done; return 1; }

DC=$ROOT/C DA=$ROOT/A DB=$ROOT/B; mkdir -p "$DC" "$DA" "$DB"; for d in "$DC" "$DA" "$DB"; do printf p>"$d/pass"; chmod 600 "$d/pass"; done
echo "=== common chain to H=44 (>= activation 42), built with NEW binary ==="
wallet "$NEW" "$DC"; NC=$(node "$NEW" "$DC" 19961 19962); waitrpc 19962; mine "$NEW" "$DC" 19962 44; waith 19962 44
echo "  common H=$(h 19962)"; kill -9 $NC 2>/dev/null; sw 1
cp "$DC/chain.json" "$DA/chain.json"; cp "$DC/chain.json" "$DB/chain.json"; wallet "$NEW" "$DA"; wallet "$NEW" "$DB"
NA=$(node "$NEW" "$DA" 19931 19932); waitrpc 19932; mine "$NEW" "$DA" 19932 10; waith 19932 54   # A heavier +10
NB2=$(node "$NEW" "$DB" 19941 19942); waitrpc 19942; mine "$NEW" "$DB" 19942 9; waith 19942 53    # B +9
AH=$(h 19932); ATIP=$(tip 19932); echo "  A h=$AH tip=$(echo $ATIP|cut -c1-12)  B h=$(h 19942)"
cp -r "$DB" "$ROOT/Bold"; kill -9 $NA $NB2 2>/dev/null; sw 1   # snapshot B chain for the OLD run

echo "=== NEW node B (build-v2) receives A -> expect V2 PROCEED (converge) ==="
NB=$(node "$NEW" "$DB" 19941 19942); waitrpc 19942; python3 "$FEED" 19932 19942 "$AH" >/dev/null 2>&1 &
NA=$(node "$NEW" "$DA" 19931 19932); waitrpc 19932; sw 1; python3 "$FEED" 19932 19942 "$AH" >/dev/null 2>&1; sw 3
NEWTIP=$(tip 19942); echo "  NEW B post: h=$(h 19942) tip=$(echo $NEWTIP|cut -c1-12)  decision: $(grep -oE 'SACS-V2\] Deep reorg|Rejected: depth' "$DB/node.log" | tail -1)"
kill -9 $NA $NB 2>/dev/null; sw 1

echo "=== OLD node B (build-sacs, NO V2) receives A -> expect LEGACY REJECT (keep own) ==="
rm -f "$ROOT/Bold/node.log"; wallet "$OLD" "$ROOT/Bold" 2>/dev/null
NA=$(node "$NEW" "$DA" 19931 19932); waitrpc 19932
OB=$(node "$OLD" "$ROOT/Bold" 19951 19952); waitrpc 19952; OLDPRE=$(tip 19952)
python3 "$FEED" 19932 19952 "$AH" >/dev/null 2>&1; sw 3
OLDTIP=$(tip 19952); echo "  OLD B post: h=$(h 19952) tip=$(echo $OLDTIP|cut -c1-12)  decision: $(grep -oE 'Rejected: depth|SACS-V2\] Deep reorg' "$ROOT/Bold/node.log" | tail -1)"
kill -9 $NA $OB 2>/dev/null; sw 1

echo "=== VERDICT ==="
echo "  A tip=$(echo $ATIP|cut -c1-12)  NEW-B tip=$(echo $NEWTIP|cut -c1-12)  OLD-B tip=$(echo $OLDTIP|cut -c1-12)"
[ "$NEWTIP" = "$ATIP" ] && [ "$OLDTIP" != "$ATIP" ] && echo "  >>> OLD-vs-NEW: PASS — NEW converges to A (V2), OLD keeps its chain (legacy). HARD-FORK divergence confirmed. <<<" || echo "  >>> OLD-vs-NEW: CHECK — NEW=$([ "$NEWTIP" = "$ATIP" ]&&echo conv||echo no) OLD=$([ "$OLDTIP" != "$ATIP" ]&&echo kept||echo conv) <<<"
rm -rf "$ROOT"; echo OLDVSNEW_DONE

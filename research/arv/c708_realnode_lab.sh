#!/usr/bin/env bash
# C708 real-node check, scaled to the devnet cap (MAX_REORG_DEPTH = 8 on devnet; fork point at
# genesis, below the devnet SACS V2 height 42, so the LEGACY cap applies — the same rule as mainnet).
#
#  R1  depth sweep: A mines d+1 blocks, B mines d of its own, then B receives A.
#      d = 7, 8 -> B reorgs to A (disconnect <= cap);  d = 9 -> B refuses (disconnect > cap).
#  R2  fresh nodes: one A chain (10 blocks) and one B chain (9 blocks) exist. Three EMPTY nodes
#      receive both, in different orders:
#        C1  B first, then A   -> refuses A (disconnect 9 > 8): stays on the LIGHTER chain
#        C2  A first, then B   -> stays on A
#        C3  B[1..3], then A   -> reorgs to A (disconnect 3)
#      Same blocks, same rules, different arrival order -> different histories: the cap gives
#      LOCAL_NODE_SAFETY, not NETWORK_CONVERGENCE / GLOBAL_CANONICALITY.
#
# Usage: c708_realnode_lab.sh <devnet build dir> <genesis_block.json> <feedchain.py> <work dir>
# Loopback only (run inside `unshare -rn sh -c 'ip link set lo up; ...'`). Every node is isolated
# (--noseed, no --connect); blocks move only through submitblock, which drives the real
# process_block / try_reorganize. oom_score_adj=1000 so an OOM never hits other processes first.
echo 1000 > /proc/self/oom_score_adj 2>/dev/null
set -uo pipefail
BIN=$1; G=$2; FEED=$3; ROOT=$4
mkdir -p "$ROOT"
rpc(){ curl -s --max-time 10 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1" | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1; }
str(){ echo "$1" | grep -oE '"result":"[0-9a-f]+"' | grep -oE '[0-9a-f]{16,}' | head -1; }
h(){ num "$(rpc $1 getblockcount)"; }
tip(){ str "$(rpc $1 getbestblockhash)"; }
softwait(){ ( sleep "$1" ) & wait $!; }
newnode(){ local D=$1; mkdir -p "$D"; printf p > "$D/pass"; chmod 600 "$D/pass"
  "$BIN/sost-cli" newwallet --wallet "$D/w.json" >/dev/null 2>&1
  "$BIN/sost-cli" getnewaddress m --wallet "$D/w.json" >/dev/null 2>&1; }
startnode(){ local D=$1 P=$2 R=$3
  nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$D/chain.json" --wallet "$D/w.json" \
    --port $P --rpc-port $R --rpc-user u --rpc-pass-file "$D/pass" >> "$D/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 600 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" \
    --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" \
    --blocks "$3" --realtime --threads 2 >> "$1/miner.log" 2>&1; }
waitrpc(){ for i in $(seq 1 60); do [ -n "$(h $1)" ] && return 0; softwait 0.5; done; return 1; }
waith(){ for i in $(seq 1 240); do [ "$(h $1)" = "$2" ] && return 0; softwait 0.5; done; return 1; }
PASS=0; FAIL=0
res(){ if [ "$2" = 1 ]; then echo "  PASS $1"; PASS=$((PASS+1)); else echo "  FAIL $1"; FAIL=$((FAIL+1)); fi; }

echo "=== R1 depth sweep (devnet cap 8) ==="
for d in 7 8 9; do
  DA=$ROOT/r1_$d/A; DB=$ROOT/r1_$d/B; newnode "$DA"; newnode "$DB"
  NA=$(startnode "$DA" 19951 19952); NB=$(startnode "$DB" 19961 19962); waitrpc 19952; waitrpc 19962
  mine "$DA" 19952 $((d+1)); waith 19952 $((d+1))
  mine "$DB" 19962 $d;       waith 19962 $d
  TA=$(tip 19952); TB=$(tip 19962)
  python3 "$FEED" 19952 19962 $((d+1)) > "$ROOT/r1_$d/feed.log" 2>&1; softwait 3
  TBP=$(tip 19962)
  if [ $d -le 8 ]; then res "d=$d: B (own $d blocks) reorgs to A (d+1 blocks)" "$([ "$TBP" = "$TA" ] && echo 1 || echo 0)"
  else res "d=$d: B refuses A (disconnect $d > 8), keeps its own tip" "$([ "$TBP" = "$TB" ] && grep -q 'exceeds REORG_LIMIT' "$DB/node.log" && echo 1 || echo 0)"; fi
  kill -9 $NA $NB 2>/dev/null; softwait 1
done

echo "=== R2 fresh nodes, same two chains, different arrival order ==="
DA=$ROOT/r2/A; DB=$ROOT/r2/B; newnode "$DA"; newnode "$DB"
NA=$(startnode "$DA" 19951 19952); NB=$(startnode "$DB" 19961 19962); waitrpc 19952; waitrpc 19962
mine "$DA" 19952 10; waith 19952 10
mine "$DB" 19962 9;  waith 19962 9
TA=$(tip 19952); TB=$(tip 19962)
echo "  A: h=$(h 19952) tip=${TA:0:16}   B: h=$(h 19962) tip=${TB:0:16}"
declare -A PORTS=([C1]=19971 [C2]=19981 [C3]=19991)
for c in C1 C2 C3; do
  D=$ROOT/r2/$c; newnode "$D"; P=${PORTS[$c]}; N=$(startnode "$D" $P $((P+1))); waitrpc $((P+1))
  case $c in
    C1) python3 "$FEED" 19962 $((P+1)) 9 > "$D/feed.log" 2>&1; python3 "$FEED" 19952 $((P+1)) 10 >> "$D/feed.log" 2>&1;;
    C2) python3 "$FEED" 19952 $((P+1)) 10 > "$D/feed.log" 2>&1; python3 "$FEED" 19962 $((P+1)) 9 >> "$D/feed.log" 2>&1;;
    C3) python3 "$FEED" 19962 $((P+1)) 3 > "$D/feed.log" 2>&1; python3 "$FEED" 19952 $((P+1)) 10 >> "$D/feed.log" 2>&1;;
  esac
  softwait 3; T=$(tip $((P+1)))
  case $c in
    C1) res "C1 (B then A): stays on the lighter chain B" "$([ "$T" = "$TB" ] && echo 1 || echo 0)";;
    C2) res "C2 (A then B): on A" "$([ "$T" = "$TA" ] && echo 1 || echo 0)";;
    C3) res "C3 (B[1..3] then A): reorgs to A" "$([ "$T" = "$TA" ] && echo 1 || echo 0)";;
  esac
  eval "T_$c=$T"; kill -9 $N 2>/dev/null; softwait 1
done
res "C1 and C2 end on DIFFERENT histories (no global canonicality from the cap)" "$([ "$T_C1" != "$T_C2" ] && echo 1 || echo 0)"
kill -9 $NA $NB 2>/dev/null
echo "C708 REAL-NODE LAB: PASS=$PASS FAIL=$FAIL"

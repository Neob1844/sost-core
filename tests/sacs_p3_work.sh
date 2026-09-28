#!/usr/bin/env bash
# SACS P3 — chain selection is by highest cumulative WORK, not block COUNT.
# Build A = FEWER blocks but MORE work (mine fast -> cASERT raises difficulty),
# B = MORE blocks but LESS work (mine slow -> difficulty drops). Keep both fork
# depths <= 8 so the depth cap is NOT the deciding factor. Feed A->B; if B adopts
# A's shorter chain, the node preferred WORK over COUNT.
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; BIN="${BIN:-$REPO/build-sacs}"; G=$REPO/genesis_block.json
ROOT="$(mktemp -d)"; FEED="$(cd "$(dirname "$0")" && pwd)/sacs_feedchain.py"
trap 'rm -rf "$ROOT"' EXIT
rpc(){ curl -s --max-time 10 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1" | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1; }
str(){ echo "$1" | grep -oE '"result":"[0-9a-f]+"' | grep -oE '[0-9a-f]{16,}' | head -1; }
h(){ num "$(rpc $1 getblockcount)"; }
tip(){ str "$(rpc $1 getbestblockhash)"; }
softwait(){ ( sleep "$1" ) & wait $!; }
setupwallet(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
startnode(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" \
    --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass" >> "$1/node.log" 2>&1 & echo $!; }
mineN(){ nice -n 19 timeout 200 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" \
    --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" \
    --blocks "$3" --realtime --threads "${4:-4}" >> "$1/miner.log" 2>&1; }
waitrpc(){ for i in $(seq 1 60); do [ -n "$(h $1)" ] && return 0; softwait 0.5; done; return 1; }
# cumulative work at tip = last chainwork in log (hex). Convert to decimal for compare.
cwhex(){ grep -oE 'chainwork=0x[0-9a-f]+' "$1/node.log" | tail -1 | grep -oE '[0-9a-f]+$'; }
cwdec(){ local x=$(cwhex "$1"); [ -n "$x" ] && printf "%d\n" "0x$x" || echo 0; }

rm -rf "$ROOT"; mkdir -p "$ROOT/A" "$ROOT/B"
printf p>"$ROOT/A/pass"; printf p>"$ROOT/B/pass"; chmod 600 "$ROOT/A/pass" "$ROOT/B/pass"
setupwallet "$ROOT/A"; setupwallet "$ROOT/B"

echo "=== A: FEWER blocks, mined FAST (difficulty should rise) ==="
NA=$(startnode "$ROOT/A" 19931 19932); waitrpc 19932
mineN "$ROOT/A" 19932 6 4      # 5 blocks, 4 threads, continuous
echo "  A height=$(h 19932) work=$(cwdec "$ROOT/A") (0x$(cwhex "$ROOT/A"))"

echo "=== B: MORE blocks, mined SLOW (1 at a time w/ 14s gaps; difficulty should drop) ==="
NB=$(startnode "$ROOT/B" 19941 19942); waitrpc 19942
for i in $(seq 1 7); do mineN "$ROOT/B" 19942 1 1; echo "   B block $i done h=$(h 19942)"; softwait 28; done
echo "  B height=$(h 19942) work=$(cwdec "$ROOT/B") (0x$(cwhex "$ROOT/B"))"

WA=$(cwdec "$ROOT/A"); WB=$(cwdec "$ROOT/B"); HA=$(h 19932); HB=$(h 19942); TA=$(tip 19932); TBpre=$(tip 19942)
echo
echo "=== SETUP SUMMARY ==="
echo "  A: blocks=$HA work=$WA   B: blocks=$HB work=$WB"
echo "  Higher COUNT : $([ "$HA" -gt "$HB" ] && echo A || echo B)"
echo "  Higher WORK  : $([ "$WA" -gt "$WB" ] && echo A || echo B)"
if [ "$HA" -ge "$HB" ] || [ "$WA" -le "$WB" ]; then
  echo "  NOTE: need A fewer-blocks AND A more-work for a clean discriminator."
  echo "        Got A_blocks=$HA B_blocks=$HB A_work=$WA B_work=$WB — difficulty divergence insufficient."
  echo "  P3-EMPIRICAL: INCONCLUSIVE (documented honestly; not marked PASS)."
  kill -9 $NA $NB 2>/dev/null; exit 2
fi
echo "  DISCRIMINATOR OK: A has FEWER blocks ($HA<$HB) but MORE work ($WA>$WB)."
echo
echo "=== Feed A[1..$HA] -> B (B currently on its longer, lower-work chain) ==="
python3 "$FEED" 19932 19942 "$HA" | sed 's/^/   /'
softwait 3
echo "  REORG LOG (B):"
grep -E "Alternative chain has MORE|Fork detected|Disconnecting [0-9]+|Connecting [0-9]+|LESS cumulative work|exceeds REORG_LIMIT" "$ROOT/B/node.log" | tail -6 | sed 's/^/     /'
TBpost=$(tip 19942); HBpost=$(h 19942)
echo "  B AFTER: h=$HBpost tip=$(echo $TBpost|cut -c1-16)  (A tip=$(echo $TA|cut -c1-16))"
kill -9 $NA $NB 2>/dev/null; softwait 1
if [ "$TBpost" = "$TA" ] && [ "$HBpost" = "$HA" ] && [ "$HA" -lt "$HB" ]; then
  echo "  >>> P3: PASS — B abandoned its LONGER ($HB-block) chain for A's SHORTER ($HA-block) HIGHER-WORK chain. Selection = WORK, not COUNT."
else
  echo "  >>> P3: FAIL/inconclusive — B tip=$TBpost expected A tip=$TA"
fi

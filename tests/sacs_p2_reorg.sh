#!/usr/bin/env bash
# SACS P2 v2 — isolated 2-node reorg at MAX_REORG_DEPTH=8 (devnet).
# Both nodes fully isolated (--noseed, NO --connect). The competing chain is
# delivered A->B via getrawblock+submitblock (parent-first), which drives the
# REAL consensus reorg engine (process_block/try_reorganize) directly, bypassing
# the naive P2P sync that will not backfill sub-tip fork parents (documented
# separately as a finding).
# Rigorous PASS: common ancestor + tip hashes + cumulative chainwork + exact
# disconnect depth + UTXO-set-root equality + restart persistence. Height alone
# is NOT accepted.
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
gen(){ str "$(rpc $1 getblockhash '[0]')"; }
softwait(){ ( sleep "$1" ) & wait $!; }
setupwallet(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
startnode(){ local D=$1 P=$2 R=$3
  nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$D/chain.json" --wallet "$D/w.json" \
    --port $P --rpc-port $R --rpc-user u --rpc-pass-file "$D/pass" >> "$D/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 400 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" \
    --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" \
    --blocks "$3" --realtime --threads 2 >> "$1/miner.log" 2>&1; }
waitrpc(){ for i in $(seq 1 60); do [ -n "$(h $1)" ] && return 0; softwait 0.5; done; return 1; }
waith(){ for i in $(seq 1 120); do [ "$(h $1)" = "$2" ] && return 0; softwait 0.5; done; return 1; }
utxoroot(){ "$BIN/sost-node" --profile dev --dry-run-replay --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" 2>/dev/null | grep -oE 'utxo_set_root: [0-9a-f]+' | grep -oE '[0-9a-f]{16,}'; }
cwtip(){ grep -oE 'chainwork=0x[0-9a-f]+' "$1/node.log" | tail -1; }

scenario(){ local NAME=$1 AH=$2 BH=$3 EXPECT=$4 DISC=$5
  local DA=$ROOT/$NAME/A DB=$ROOT/$NAME/B; rm -rf "$ROOT/$NAME"; mkdir -p "$DA" "$DB"
  printf p>"$DA/pass"; printf p>"$DB/pass"; chmod 600 "$DA/pass" "$DB/pass"
  setupwallet "$DA"; setupwallet "$DB"
  echo "==================================================================="
  echo "SCENARIO $NAME : A=$AH blocks, B=$BH blocks -> expect $EXPECT (disconnect $DISC vs limit 8)"
  echo "==================================================================="
  local NA=$(startnode "$DA" 19931 19932); waitrpc 19932 || { echo A_NORPC; kill -9 $NA; return; }
  mine "$DA" 19932 "$AH"; waith 19932 "$AH" || echo "  (A stuck at $(h 19932))"
  local NB=$(startnode "$DB" 19941 19942); waitrpc 19942 || { echo B_NORPC; kill -9 $NA $NB; return; }
  mine "$DB" 19942 "$BH"; waith 19942 "$BH" || echo "  (B stuck at $(h 19942))"
  local GA=$(gen 19932) GB=$(gen 19942) HA=$(h 19932) HB=$(h 19942) TA=$(tip 19932) TBpre=$(tip 19942)
  echo "  COMMON ANCESTOR (genesis): A=$(echo $GA|cut -c1-16) B=$(echo $GB|cut -c1-16) identical=$([ "$GA" = "$GB" ] && echo YES || echo NO)"
  echo "  PRE  A: h=$HA tip=$(echo $TA|cut -c1-16) $(cwtip "$DA")"
  echo "  PRE  B: h=$HB tip=$(echo $TBpre|cut -c1-16) $(cwtip "$DB")"
  echo "  DELIVER A[1..$AH] -> B via submitblock (parent-first):"
  python3 "$FEED" 19932 19942 "$AH" | sed 's/^/   /'
  softwait 3
  local TBpost=$(tip 19942) HBpost=$(h 19942)
  echo "  REORG LOG (B):"
  grep -E "\[REORG\] Fork detected|Active work|candidate work|Disconnecting [0-9]+ blocks|Connecting [0-9]+ blocks|exceeds REORG_LIMIT|beyond max reorg depth|\[FORK\] Alternative chain has MORE" "$DB/node.log" | tail -10 | sed 's/^/     /'
  echo "  POST A: h=$(h 19932) tip=$(echo $TA|cut -c1-16)"
  echo "  POST B: h=$HBpost tip=$(echo $TBpost|cut -c1-16)"
  kill -9 $NB 2>/dev/null; softwait 1
  local URA=$(utxoroot "$DA") URB=$(utxoroot "$DB")
  echo "  UTXO ROOT A=$(echo $URA|cut -c1-24) B=$(echo $URB|cut -c1-24) equal=$([ "$URA" = "$URB" ] && echo YES || echo NO)"
  NB=$(startnode "$DB" 19941 19942); waitrpc 19942; softwait 1
  local TBr=$(tip 19942) HBr=$(h 19942)
  echo "  RESTART B: h=$HBr tip=$(echo $TBr|cut -c1-16) stable=$([ "$TBr" = "$TBpost" ] && echo YES || echo NO)"
  kill -9 $NA $NB 2>/dev/null; softwait 1
  local ok=1
  [ "$GA" = "$GB" ] || { echo "  X genesis mismatch"; ok=0; }
  local dl=$(grep -oE "Disconnecting [0-9]+ blocks" "$DB/node.log" | grep -oE "[0-9]+" | tail -1)
  local rej=$(grep -c "exceeds REORG_LIMIT" "$DB/node.log")
  if [ "$EXPECT" = "CONVERGE" ]; then
    [ "$TBpost" = "$TA" ] || { echo "  X B tip != A tip"; ok=0; }
    [ "$HBpost" = "$HA" ] || { echo "  X B height != A height"; ok=0; }
    [ "$dl" = "$DISC" ] || { echo "  X disconnect depth=$dl expected $DISC"; ok=0; }
    [ "$URA" = "$URB" ] || { echo "  X UTXO roots differ"; ok=0; }
    [ "$TBr" = "$TBpost" ] || { echo "  X unstable after restart"; ok=0; }
  else
    [ "$TBpost" = "$TBpre" ] || { echo "  X B tip changed (should keep own chain)"; ok=0; }
    [ "$TBpost" != "$TA" ] || { echo "  X B adopted A (should NOT)"; ok=0; }
    [ "$rej" -ge 1 ] || { echo "  X no REORG_LIMIT rejection logged"; ok=0; }
    [ "$URA" != "$URB" ] || { echo "  X UTXO roots equal (should differ)"; ok=0; }
    [ "$TBr" = "$TBpost" ] || { echo "  X unstable after restart"; ok=0; }
  fi
  echo "  >>> SCENARIO $NAME: $([ $ok -eq 1 ] && echo PASS || echo FAIL) <<<"
  echo
}
rm -rf "$ROOT"; mkdir -p "$ROOT"
scenario converge_d8 9 8 CONVERGE 8
scenario reject_d9  10 9 REJECT   9
echo ALLDONE

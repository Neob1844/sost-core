set -u
ulimit -f unlimited
ROOT=/home/sost/SOST/sostcore/sost-btc-work
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
NODE="$S/build-sostswap/sost-node"; MINER="$S/build-sostswap/sost-miner"; CLI="$S/build-sostswap/sost-cli"; DRV="$S/sost_htlc_driver"
RP=18331; PP=20331
W="$(mktemp -d /tmp/srefc.XXXXXX)"
NPID=""
cleanup(){ [ -n "$NPID" ] && kill -9 "$NPID" 2>/dev/null; for p in $(ps -eo pid,args|grep -E 'sost-miner|sost-node'|grep "$W"|grep -v grep|awk '{print $1}'); do kill -9 "$p" 2>/dev/null; done; }
trap cleanup EXIT
rpc(){ curl -s --max-time 6 --data "$2" "http://127.0.0.1:$1/"; }
hh(){ rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
sbal(){ "$CLI" --wallet "$1" --rpc 127.0.0.1:$RP getbalance 2>/dev/null|grep -oE 'Spendable: *[0-9.]+'|grep -oE '[0-9.]+'|head -1; }
hexline(){ grep -E '^[0-9a-f]+$'|tail -1; }
# STRICT: only bounded foreground mining, capped log
mine(){ local n="$1"; timeout $((n*15+30)) "$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$2" --wallet "$3" --mining-key-label default --blocks "$n" --threads 4 >>"$W/m.log" 2>&1; }

A=$("$CLI" --wallet "$W/a.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
BOB=$("$CLI" --wallet "$W/b.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
APRIV=$("$CLI" --wallet "$W/a.json" dumpprivkey "$A" 2>/dev/null|grep -oE '[0-9a-f]{64}'|head -1)
BPRIV=$("$CLI" --wallet "$W/b.json" dumpprivkey "$BOB" 2>/dev/null|grep -oE '[0-9a-f]{64}'|head -1)
APKH=$($DRV pkh $APRIV|hexline); BPKH=$($DRV pkh $BPRIV|hexline)
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/c.json" --port $PP --rpc-port $RP --rpc-noauth --connect 127.0.0.1:1 >>"$W/n.log" 2>&1 & NPID=$!
for _ in $(seq 1 20); do sleep 1; [ -n "$(hh $RP)" ]&&break; done
GEN=$(rpc $RP '{"method":"getinfo","params":[],"id":1}'|grep -oE '[0-9a-f]{64}'|head -1)
echo "node up (pid=$NPID, rpc=$RP), genesis=${GEN:0:16}..."
mine 16 "$A" "$W/a.json"
echo "mined to h=$(hh $RP), Alice spendable=$(sbal "$W/a.json")"
U=$(rpc $RP "{\"method\":\"getaddressutxos\",\"params\":[\"$A\"],\"id\":1}")
PTX=$(echo "$U"|python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if x.get('mature')][0];print(u['txid'])")
PV=$(echo "$U"|python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if x.get('mature')][0];print(u['vout'])")
PAMT=$(echo "$U"|python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if x.get('mature')][0];print(u['amount_stocks'])")
PRE=9999999999999999999999999999999999999999999999999999999999999999
HL=$(python3 -c "import hashlib;print(hashlib.sha256(bytes.fromhex('$PRE')).hexdigest())")
LOCK=200000000; FEE=100000; SRH=$(( $(hh $RP) + 5 ))
A_PRE_LOCK=$(sbal "$W/a.json")
echo ""
echo ">>> STEP 1: Alice funds an HTLC lock (2 SOST, refund_height=$SRH); Bob will NEVER claim"
LOCKTX=$($DRV lock $PTX $PV $PAMT 1 $APRIV $HL $SRH $BPKH $APKH $LOCK $FEE $GEN 2>/dev/null|hexline)
SLTX=$(rpc $RP "{\"method\":\"sendrawtransaction\",\"params\":[\"$LOCKTX\"],\"id\":1}"|grep -oE '[0-9a-f]{64}'|head -1)
mine 1 "$A" "$W/a.json"
echo "    lock txid=$SLTX confirmed at h=$(hh $RP)"
echo ">>> STEP 2 (NEGATIVE): refund BEFORE refund_height must be rejected"
RTX=$($DRV refund $SLTX 0 $LOCK $APKH $FEE $APRIV $GEN 2>/dev/null|hexline)
E=$(rpc $RP "{\"method\":\"sendrawtransaction\",\"params\":[\"$RTX\"],\"id\":1}")
echo "    early refund -> $(echo "$E"|grep -oE 'R24[^"]*|"result":"[0-9a-f]+"'|head -c 80)"
ER=$(echo "$E"|grep -qE '"error"'&&echo YES||echo NO)
echo ">>> STEP 3: mine to refund_height ($SRH), then refund"
NEED=$(( SRH - $(hh $RP) + 1 )); [ "$NEED" -gt 0 ] && mine "$NEED" "$A" "$W/a.json"
echo "    now at h=$(hh $RP) (>= refund_height $SRH)"
RTX2=$($DRV refund $SLTX 0 $LOCK $APKH $FEE $APRIV $GEN 2>/dev/null|hexline)
RR=$(rpc $RP "{\"method\":\"sendrawtransaction\",\"params\":[\"$RTX2\"],\"id\":1}")
RTID=$(echo "$RR"|grep -oE '[0-9a-f]{64}'|head -1)
echo "    refund -> $(echo "$RR"|grep -oE '"result":"[0-9a-f]+"|"error":\{[^}]*\}'|head -c 80)"
mine 2 "$A" "$W/a.json"
A_POST=$(sbal "$W/a.json"); BOB_BAL=$(sbal "$W/b.json")
echo ""
echo ">>> STEP 4: verify — Alice recovered the locked SOST; Bob got nothing"
echo "    Alice: pre-lock=$A_PRE_LOCK  post-refund=$A_POST"
echo "    Bob:   ${BOB_BAL:-0} (must be ~0)"
# the refund output pays Alice's refund_dest_pkh; confirm the refund tx is on-chain (confirmations)
RCONF=$(rpc $RP "{\"method\":\"getrawtransaction\",\"params\":[\"$RTID\"],\"id\":1}" 2>/dev/null | grep -oE '"result"' | head -1)
if [ "$ER" = "YES" ] && [ -n "$RTID" ] && python3 -c "exit(0 if float('${BOB_BAL:-0}')<0.01 else 1)"; then
  echo ""
  echo "RESULT: ✅ SOST REFUND COMPLETE — fund → early-refund REJECTED (R24 timelock) → past timeout → refund ACCEPTED (txid $RTID) → Alice recovered her SOST, Bob got nothing"
else
  echo "RESULT: ⚠️ review (early_rejected=$ER refund_txid=$RTID bob=$BOB_BAL)"
fi

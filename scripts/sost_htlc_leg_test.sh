set -u
ulimit -f unlimited
ROOT=/home/sost/SOST/sostcore/sost-btc-work
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
B="$S/build-sostswap"; NODE="$B/sost-node"; MINER="$B/sost-miner"; CLI="$B/sost-cli"
DRV="$S/sost_htlc_driver"
RP=18292; PP=20292
W="$(mktemp -d /tmp/sostleg.XXXXXX)"
cleanup(){ for pid in $(pgrep -f -- "$W" 2>/dev/null); do [[ "$pid" == "$$" ]]&&continue; kill "$pid" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT
rpc(){ curl -s --max-time 8 --data "$2" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
gbal(){ "$CLI" --wallet "$1" --rpc 127.0.0.1:$RP getbalance 2>/dev/null | grep -oE 'Spendable: *[0-9]+\.?[0-9]*' | grep -oE '[0-9]+\.?[0-9]*' | head -1; }

# Alice (has SOST) and Bob (will receive via claim)
A=$("$CLI" --wallet "$W/alice.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
BOB=$("$CLI" --wallet "$W/bob.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
APRIV=$("$CLI" --wallet "$W/alice.json" dumpprivkey "$A" 2>/dev/null | grep -oE '[0-9a-f]{64}' | head -1)
BPRIV=$("$CLI" --wallet "$W/bob.json" dumpprivkey "$BOB" 2>/dev/null | grep -oE '[0-9a-f]{64}' | head -1)
echo "Alice=$A"; echo "Bob=$BOB"
echo "APRIV set=$([ -n "$APRIV" ]&&echo yes) BPRIV set=$([ -n "$BPRIV" ]&&echo yes)"

"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/c.json" --port $PP --rpc-port $RP --rpc-noauth --connect 127.0.0.1:1 >"$W/n.log" 2>&1 &
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height $RP)" ]]&&break; done
GEN=$(rpc $RP '{"method":"getinfo","params":[],"id":1}' | grep -oE '"genesis[^"]*":"[0-9a-f]+"' | grep -oE '[0-9a-f]{64}' | head -1)
echo "node up h=$(height $RP) genesis=$GEN"

# mine to Alice past V14_7=12
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$A" --wallet "$W/alice.json" --mining-key-label default --blocks 100000 --threads 3 >>"$W/m.log" 2>&1 & MP=$!
while [[ "$(height $RP)" -lt 18 ]]; do sleep 2; done; kill $MP 2>/dev/null; sleep 1
echo "mined h=$(height $RP) Alice_spendable=$(gbal "$W/alice.json")"

# get a mature coinbase UTXO for Alice
UTXOS=$(rpc $RP "{\"method\":\"getaddressutxos\",\"params\":[\"$A\"],\"id\":1}")
echo "utxo sample: $(echo "$UTXOS" | head -c 240)"
PTX=$(echo "$UTXOS" | python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if int(x.get('amount_stocks',0))>0 and x.get('mature')][0];print(u['txid'])" 2>/dev/null)
PV=$(echo "$UTXOS" | python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if int(x.get('amount_stocks',0))>0 and x.get('mature')][0];print(u['vout'])" 2>/dev/null)
PAMT=$(echo "$UTXOS" | python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if int(x.get('amount_stocks',0))>0 and x.get('mature')][0];print(u['amount_stocks'])" 2>/dev/null)
echo "Alice UTXO: txid=$PTX vout=$PV amt=$PAMT"

# hashlock/preimage + pkhs
PRE=7777777777777777777777777777777777777777777777777777777777777777
HL=$(python3 -c "import hashlib;print(hashlib.sha256(bytes.fromhex('$PRE')).hexdigest())")
APKH=$($DRV pkh $APRIV); BPKH=$($DRV pkh $BPRIV)
echo "hashlock=$HL  Alice_pkh=$APKH  Bob_pkh=$BPKH"
RH=$(( $(height $RP) + 500 ))
LOCK=200000000   # 2 SOST into the HTLC (amounts are stockshis; 1 SOST=1e8)
FEE=100000

echo "=== SOST LOCK: Alice -> OUT_HTLC_LOCK (claim=Bob, refund=Alice) ==="
LOCKTX=$($DRV lock $PTX $PV $PAMT 1 $APRIV $HL $RH $BPKH $APKH $LOCK $FEE $GEN 2>/dev/null | grep -E "^[0-9a-f]+$" | tail -1)
if [ -z "$LOCKTX" ]; then echo "LOCK build/sign FAILED"; tail -5 "$W/n.log"|sed 's/^/  n:/'; exit 1; fi
echo "  lock tx hexlen=${#LOCKTX} (parity=$(( ${#LOCKTX} % 2 ))) bytes=$(( ${#LOCKTX} / 2 ))"
LRES=$(rpc $RP "{\"method\":\"sendrawtransaction\",\"params\":[\"$LOCKTX\"],\"id\":1}")
echo "  sendraw(lock) => $(echo "$LRES" | head -c 200)"
LTXID=$(echo "$LRES" | grep -oE '"result":"[0-9a-f]{64}"' | grep -oE '[0-9a-f]{64}')
[ -z "$LTXID" ] && { echo "LOCK broadcast FAILED"; exit 1; }
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$A" --wallet "$W/alice.json" --mining-key-label default --blocks 2 --threads 3 >>"$W/m.log" 2>&1; sleep 2
echo "  lock txid=$LTXID mined; h=$(height $RP)"

echo "=== SOST CLAIM: Bob claims OUT_HTLC_LOCK with preimage ==="
# lock output is vout 0 of the lock tx (HTLC output first)
"$DRV" claim $LTXID 0 $LOCK $PRE $BPKH 10000 $FEE $BPRIV $GEN >"$W/claim.out" 2>"$W/claim.err" || true
  echo "  claim stderr: $(grep -v SIGHASH-DEBUG "$W/claim.err" | head -3 | tr "\n" " ")"
  CLAIMTX=$(grep -E "^[0-9a-f]+$" "$W/claim.out" | tail -1)
if [ -z "$CLAIMTX" ]; then echo "CLAIM build/sign FAILED"; exit 1; fi
echo "  claim tx bytes=$(( ${#CLAIMTX} / 2 ))"
CRES=$(rpc $RP "{\"method\":\"sendrawtransaction\",\"params\":[\"$CLAIMTX\"],\"id\":1}")
echo "  sendraw(claim) => $(echo "$CRES" | head -c 200)"
CTXID=$(echo "$CRES" | grep -oE '"result":"[0-9a-f]{64}"' | grep -oE '[0-9a-f]{64}')
[ -z "$CTXID" ] && { echo "CLAIM broadcast FAILED"; exit 1; }
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$A" --wallet "$W/alice.json" --mining-key-label default --blocks 2 --threads 3 >>"$W/m.log" 2>&1; sleep 2

# sync Bob's wallet from node + check balance
BBAL=$(gbal "$W/bob.json")
echo "  Bob spendable after claim = $BBAL SOST (expected ~2)"
if [ -n "$CTXID" ] && python3 -c "exit(0 if float('${BBAL:-0}')>=1.9 else 1)" 2>/dev/null; then
  echo "RESULT: ✅ SOST HTLC LEG LIVE — Alice locked, Bob claimed with preimage, Bob received ~2 SOST (real code, real node)"
else
  echo "RESULT: ⚠️ review (ctxid=$CTXID bbal=$BBAL)"
fi

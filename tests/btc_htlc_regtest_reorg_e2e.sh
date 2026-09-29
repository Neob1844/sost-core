set -e
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
export PATH="$S/bitcoin/bitcoin-27.1/bin:$PATH"
CLI="bitcoin-cli -regtest -datadir=$S/btcregtest -rpcuser=rt -rpcpassword=rt -rpcport=18443 -rpcwallet=w"
CLIN="bitcoin-cli -regtest -datadir=$S/btcregtest -rpcuser=rt -rpcpassword=rt -rpcport=18443"
DRV="$S/btc_htlc_driver"
MINE=$($CLI getnewaddress)
H=$($CLIN getblockcount)
PRE=5555555555555555555555555555555555555555555555555555555555555555
CPRIV=2222222222222222222222222222222222222222222222222222222222222222
RPRIV=3333333333333333333333333333333333333333333333333333333333333333
RH=$((H+1000))
$DRV addr $PRE $RH $CPRIV $RPRIV regtest > $S/htlc_reorg.txt
LADDR=$(grep ADDR= $S/htlc_reorg.txt|cut -d= -f2); REDEEM=$(grep REDEEM= $S/htlc_reorg.txt|cut -d= -f2)
echo "HTLC addr=$LADDR"
FTX=$($CLI sendtoaddress "$LADDR" 0.5); $CLI generatetoaddress 1 "$MINE" >/dev/null
DEC=$($CLIN getrawtransaction $FTX true)
VOUT=$(echo "$DEC"|python3 -c "import sys,json;d=json.load(sys.stdin);print(next(o['n'] for o in d['vout'] if o['scriptPubKey'].get('address')=='$LADDR'))")
AMT=$(echo "$DEC"|python3 -c "import sys,json;d=json.load(sys.stdin);print(int(round(next(o for o in d['vout'] if o['n']==$VOUT)['value']*1e8)))")
FTX_LE=$(python3 -c "print(bytes.fromhex('$FTX')[::-1].hex())")
echo "funded txid=$FTX vout=$VOUT amt=$AMT (confirmed at h=$($CLIN getblockcount))"

echo ""
echo "=== CLAIM, then confirm ==="
CTX=$($DRV claim $FTX $VOUT $AMT $REDEEM $PRE $CPRIV $MINE 1000 regtest)
CTXID=$($CLIN sendrawtransaction $CTX)
CLAIMBLK=$($CLI generatetoaddress 1 "$MINE" | python3 -c "import sys,json;print(json.load(sys.stdin)[0])")
echo "claim txid=$CTXID mined in block=$CLAIMBLK"
echo "claim confirmations=$($CLIN getrawtransaction $CTXID true | python3 -c "import sys,json;print(json.load(sys.stdin).get('confirmations',0))")"

echo ""
echo "=== REORG: invalidate the claim block (simulate a chain reorg) ==="
$CLIN invalidateblock "$CLAIMBLK"
# after invalidation, the claim tx should return to the mempool (recovery), still valid
sleep 1
INMEM=$($CLIN getrawmempool | python3 -c "import sys,json;print('$CTXID' in json.load(sys.stdin))")
echo "claim tx back in mempool after reorg = $INMEM"
CONF_AFTER=$($CLIN getrawtransaction $CTXID true 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('confirmations','unconfirmed'))" 2>/dev/null || echo "unconfirmed")
echo "claim confirmations after reorg = $CONF_AFTER (expect 0/unconfirmed)"

echo ""
echo "=== RECOVERY: re-mine — the claim must reconfirm on the new chain ==="
$CLI generatetoaddress 2 "$MINE" >/dev/null
RECONF=$($CLIN getrawtransaction $CTXID true | python3 -c "import sys,json;print(json.load(sys.stdin).get('confirmations',0))")
echo "claim confirmations after re-mine = $RECONF"
# verify preimage still revealed on the reconfirmed claim
PRE_OK=$($CLIN getrawtransaction $CTXID 2 | python3 -c "import sys,json;print(json.load(sys.stdin)['vin'][0]['txinwitness'][1]=='$PRE')")
echo "preimage still revealed & matches after reorg+recovery = $PRE_OK"
if [ "$INMEM" = "True" ] && [ "$RECONF" -ge 1 ] 2>/dev/null && [ "$PRE_OK" = "True" ]; then
  echo "RESULT: ✅ BTC HTLC survives reorg — claim returned to mempool, reconfirmed, preimage intact"
else
  echo "RESULT: ⚠️ review (inmem=$INMEM reconf=$RECONF pre_ok=$PRE_OK)"
fi

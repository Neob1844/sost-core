set -e
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
export PATH="$S/bitcoin/bitcoin-27.1/bin:$PATH"
CLI="bitcoin-cli -regtest -datadir=$S/btcregtest -rpcuser=rt -rpcpassword=rt -rpcport=18443 -rpcwallet=w"
CLIN="bitcoin-cli -regtest -datadir=$S/btcregtest -rpcuser=rt -rpcpassword=rt -rpcport=18443"
DRV="$S/btc_htlc_driver"
MINE=$($CLI getnewaddress); H=$($CLIN getblockcount)
PRE=6161616161616161616161616161616161616161616161616161616161616161
CPRIV=2222222222222222222222222222222222222222222222222222222222222222
RPRIV=3333333333333333333333333333333333333333333333333333333333333333
FPRIV=4444444444444444444444444444444444444444444444444444444444444444  # funder key
RH=$((H+1000))

echo "=== 1) funder P2WPKH address (from real EncodeP2WPKHAddress) ==="
FADDR=$($DRV p2wpkh $FPRIV regtest | grep P2WPKH= | cut -d= -f2); echo "  funder=$FADDR"
CHG=$FADDR  # send change back to funder

echo "=== 2) fund the funder's P2WPKH with 1.0 BTC ==="
FUND_IN=$($CLI sendtoaddress "$FADDR" 1.0); $CLI generatetoaddress 1 "$MINE" >/dev/null
DEC=$($CLIN getrawtransaction $FUND_IN true)
PV=$(echo "$DEC"|python3 -c "import sys,json;d=json.load(sys.stdin);print(next(o['n'] for o in d['vout'] if o['scriptPubKey'].get('address')=='$FADDR'))")
PAMT=$(echo "$DEC"|python3 -c "import sys,json;d=json.load(sys.stdin);print(int(round(next(o for o in d['vout'] if o['n']==$PV)['value']*1e8)))")
echo "  funder UTXO: txid=$FUND_IN vout=$PV amt=$PAMT sats"

echo "=== 3) build HTLC redeem+address ==="
$DRV addr $PRE $RH $CPRIV $RPRIV regtest > $S/htlc_fund.txt
LADDR=$(grep ADDR= $S/htlc_fund.txt|cut -d= -f2); REDEEM=$(grep REDEEM= $S/htlc_fund.txt|cut -d= -f2)
echo "  HTLC addr=$LADDR"

echo "=== 4) FUND HTLC via REAL SignBtcHtlcLockFunding (NOT sendtoaddress) ==="
LOCK=50000000  # 0.5 BTC into the HTLC
FEE=2000
FUNDTX=$($DRV fund "$FUND_IN" $PV $PAMT $FPRIV $CHG $REDEEM $LOCK $FEE regtest)
echo "  funding tx bytes=$(( ${#FUNDTX} / 2 ))"
FTXID=$($CLIN sendrawtransaction $FUNDTX)
echo "  broadcast funding txid=$FTXID"
$CLI generatetoaddress 1 "$MINE" >/dev/null
# verify the HTLC output exists at vout 0 with the lock amount
DEC2=$($CLIN getrawtransaction $FTXID true)
HTLC_ADDR_ONCHAIN=$(echo "$DEC2"|python3 -c "import sys,json;d=json.load(sys.stdin);print(d['vout'][0]['scriptPubKey'].get('address'))")
HTLC_AMT=$(echo "$DEC2"|python3 -c "import sys,json;d=json.load(sys.stdin);print(int(round(d['vout'][0]['value']*1e8)))")
echo "  on-chain vout0: addr=$HTLC_ADDR_ONCHAIN amt=$HTLC_AMT (expect $LADDR / $LOCK)"
[ "$HTLC_ADDR_ONCHAIN" = "$LADDR" ] && [ "$HTLC_AMT" = "$LOCK" ] && echo "  ✅ real funding created the exact HTLC P2WSH output" || { echo "  ❌ mismatch"; exit 1; }

echo "=== 5) CLAIM from the code-funded HTLC (display txid, no manual reversal) ==="
CTX=$($DRV claim "$FTXID" 0 $LOCK $REDEEM $PRE $CPRIV $MINE 1000 regtest)
CTXID=$($CLIN sendrawtransaction $CTX)
$CLI generatetoaddress 1 "$MINE" >/dev/null
CONF=$($CLIN getrawtransaction $CTXID true | python3 -c "import sys,json;print(json.load(sys.stdin).get('confirmations',0))")
PREOK=$($CLIN getrawtransaction $CTXID 2 | python3 -c "import sys,json;print(json.load(sys.stdin)['vin'][0]['txinwitness'][1]=='$PRE')")
echo "  claim confirmations=$CONF preimage_match=$PREOK"
# cross-check: driver's txid mode reproduces bitcoin-cli's display txid of the funding tx
DRV_TXID=$($DRV txid $FUNDTX)
echo "  driver txid(funding)=$DRV_TXID  bitcoin-cli=$FTXID  match=$([ "$DRV_TXID" = "$FTXID" ]&&echo YES||echo NO)"
if [ "$CONF" -ge 1 ] && [ "$PREOK" = "True" ] && [ "$DRV_TXID" = "$FTXID" ]; then
  echo "RESULT: ✅ CODE-DRIVEN FUNDING + CLAIM — SignBtcHtlcLockFunding funded the HTLC, claim confirmed, preimage revealed, API txid matches bitcoin-cli"
else
  echo "RESULT: ⚠️ review (conf=$CONF preok=$PREOK txidmatch)"
fi

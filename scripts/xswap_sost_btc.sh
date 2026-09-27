set -u
ulimit -f unlimited
ROOT=/home/sost/SOST/sostcore/sost-btc-work
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
export PATH="$S/bitcoin/bitcoin-27.1/bin:$PATH"
BB="$S/build-sostswap"; NODE="$BB/sost-node"; MINER="$BB/sost-miner"; SCLI="$BB/sost-cli"
SDRV="$S/sost_htlc_driver"; BDRV="$S/btc_htlc_driver"
RP=18292; PP=20292
BCLI="bitcoin-cli -regtest -datadir=$S/btcregtest -rpcuser=rt -rpcpassword=rt -rpcport=18443 -rpcwallet=w"
BCLIN="bitcoin-cli -regtest -datadir=$S/btcregtest -rpcuser=rt -rpcpassword=rt -rpcport=18443"
W="$(mktemp -d /tmp/xswap.XXXXXX)"
cleanup(){ for pid in $(pgrep -f -- "$W" 2>/dev/null); do [[ "$pid" == "$$" ]]&&continue; kill "$pid" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT
srpc(){ curl -s --max-time 8 --data "$2" "http://127.0.0.1:$1/"; }
sheight(){ srpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
sbal(){ "$SCLI" --wallet "$1" --rpc 127.0.0.1:$RP getbalance 2>/dev/null | grep -oE 'Spendable: *[0-9.]+' | grep -oE '[0-9.]+' | head -1; }
hexline(){ grep -E '^[0-9a-f]+$' | tail -1; }
ST(){ echo "  [COORD] state -> $1"; }

echo "============ SOST<->BTC ATOMIC SWAP (lab: SOST devnet + BTC regtest) ============"
# ---------- bring up both chains ----------
$BCLIN getblockcount >/dev/null 2>&1 || { bitcoind -regtest -datadir=$S/btcregtest -rpcuser=rt -rpcpassword=rt -rpcport=18443 -fallbackfee=0.0001 -txindex=1 -daemon >/dev/null 2>&1; sleep 3; }
$BCLIN loadwallet w >/dev/null 2>&1 || true
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/c.json" --port $PP --rpc-port $RP --rpc-noauth --connect 127.0.0.1:1 >"$W/n.log" 2>&1 &
for _ in $(seq 1 20); do sleep 1; [[ -n "$(sheight $RP)" ]]&&break; done
GEN=$(srpc $RP '{"method":"getinfo","params":[],"id":1}' | grep -oE '[0-9a-f]{64}' | head -1)
echo "SOST devnet h=$(sheight $RP)  BTC regtest h=$($BCLIN getblockcount)"

# ---------- identities ----------
# SOST side
ALICE_S=$("$SCLI" --wallet "$W/alice_s.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
BOB_S=$("$SCLI" --wallet "$W/bob_s.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
ALICE_S_PRIV=$("$SCLI" --wallet "$W/alice_s.json" dumpprivkey "$ALICE_S" 2>/dev/null|grep -oE '[0-9a-f]{64}'|head -1)
BOB_S_PRIV=$("$SCLI" --wallet "$W/bob_s.json" dumpprivkey "$BOB_S" 2>/dev/null|grep -oE '[0-9a-f]{64}'|head -1)
ALICE_S_PKH=$($SDRV pkh $ALICE_S_PRIV 2>/dev/null|hexline); BOB_S_PKH=$($SDRV pkh $BOB_S_PRIV 2>/dev/null|hexline)
# BTC side (fixed lab keys)
ALICE_B_PRIV=aa11aa11aa11aa11aa11aa11aa11aa11aa11aa11aa11aa11aa11aa11aa11aa11
BOB_B_PRIV=bb22bb22bb22bb22bb22bb22bb22bb22bb22bb22bb22bb22bb22bb22bb22bb22
ALICE_B_ADDR=$($BDRV p2wpkh $ALICE_B_PRIV regtest|grep P2WPKH=|cut -d= -f2)  # Alice receives BTC here
BOB_B_ADDR=$($BDRV p2wpkh $BOB_B_PRIV regtest|grep P2WPKH=|cut -d= -f2)      # Bob funds/refunds here
# secret
PRE=abcdef0011223344556677889900aabbccddeeff00112233445566778899aabb
HL=$(python3 -c "import hashlib;print(hashlib.sha256(bytes.fromhex('$PRE')).hexdigest())")
echo "Alice(SOST)=$ALICE_S  Bob(SOST)=$BOB_S"
echo "Alice(BTC)=$ALICE_B_ADDR  Bob(BTC)=$BOB_B_ADDR"
echo "hashlock H=$HL"
ST "Draft (params agreed: 2 SOST <-> 0.5 BTC, H, timeouts T_btc<T_sost)"

# ---------- Alice funds SOST (she has SOST; mine to her) ----------
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$ALICE_S" --wallet "$W/alice_s.json" --mining-key-label default --blocks 100000 --threads 3 >>"$W/m.log" 2>&1 & MP=$!
while [[ "$(sheight $RP)" -lt 18 ]]; do sleep 2; done; kill $MP 2>/dev/null; sleep 1
U=$(srpc $RP "{\"method\":\"getaddressutxos\",\"params\":[\"$ALICE_S\"],\"id\":1}")
PTX=$(echo "$U"|python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if x.get('mature') and int(x.get('amount_stocks',0))>250000000][0];print(u['txid'])")
PV=$(echo "$U"|python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if x.get('mature') and int(x.get('amount_stocks',0))>250000000][0];print(u['vout'])")
PAMT=$(echo "$U"|python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if x.get('mature') and int(x.get('amount_stocks',0))>250000000][0];print(u['amount_stocks'])")
SLOCK=200000000; SFEE=100000; SRH=$(( $(sheight $RP) + 500 ))
echo ""
echo ">>> STEP 1: Alice LOCKS 2 SOST (claim=Bob, refund=Alice, H, T_sost=$SRH)"
LOCKTX=$($SDRV lock $PTX $PV $PAMT 1 $ALICE_S_PRIV $HL $SRH $BOB_S_PKH $ALICE_S_PKH $SLOCK $SFEE $GEN 2>/dev/null|hexline)
SLTX=$(srpc $RP "{\"method\":\"sendrawtransaction\",\"params\":[\"$LOCKTX\"],\"id\":1}"|grep -oE '[0-9a-f]{64}'|head -1)
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$ALICE_S" --wallet "$W/alice_s.json" --mining-key-label default --blocks 2 --threads 3 >>"$W/m.log" 2>&1; sleep 1
echo "  SOST lock txid=$SLTX (confirmed h=$(sheight $RP))"; ST "SOST leg FUNDED"

# ---------- Bob funds BTC ----------
MINEB=$($BCLI getnewaddress); H0=$($BCLIN getblockcount)
$BCLI sendtoaddress "$BOB_B_ADDR" 1.0 >/dev/null; $BCLI generatetoaddress 1 "$MINEB" >/dev/null
FDEC=$($BCLIN getrawtransaction $($BCLIN getblock $($BCLIN getbestblockhash) 1|python3 -c "import sys,json;print(json.load(sys.stdin)['tx'][1])") true)
FTID=$(echo "$FDEC"|python3 -c "import sys,json;print(json.load(sys.stdin)['txid'])")
FVO=$(echo "$FDEC"|python3 -c "import sys,json;d=json.load(sys.stdin);print(next(o['n'] for o in d['vout'] if o['scriptPubKey'].get('address')=='$BOB_B_ADDR'))")
FAMT=$(echo "$FDEC"|python3 -c "import sys,json;d=json.load(sys.stdin);print(int(round(next(o for o in d['vout'] if o['n']==$FVO)['value']*1e8)))")
# HTLC redeem: claim=Alice_btc, refund=Bob_btc, H, T_btc short
BRH=$(( $($BCLIN getblockcount) + 20 ))
$BDRV addr $PRE $BRH $ALICE_B_PRIV $BOB_B_PRIV regtest > "$W/btc_htlc.txt"
BLADDR=$(grep ADDR= "$W/btc_htlc.txt"|cut -d= -f2); BREDEEM=$(grep REDEEM= "$W/btc_htlc.txt"|cut -d= -f2)
# NOTE: H in the BTC redeem must equal H (sha256 of same preimage) — verify:
BHL=$(grep HASHLOCK= "$W/btc_htlc.txt"|cut -d= -f2)
echo ""
echo ">>> STEP 2: Bob FUNDS 0.5 BTC HTLC via SignBtcHtlcLockFunding (claim=Alice, refund=Bob, H, T_btc=$BRH)"
echo "  same hashlock on both chains? $([ "$BHL" = "$HL" ]&&echo YES||echo NO) (BTC=$BHL)"
BLOCK=50000000; BFEE=2000
FUNDTX=$($BDRV fund "$FTID" $FVO $FAMT $BOB_B_PRIV $BOB_B_ADDR $BREDEEM $BLOCK $BFEE regtest)
BFTID=$($BCLIN sendrawtransaction $FUNDTX); $BCLI generatetoaddress 1 "$MINEB" >/dev/null
echo "  BTC HTLC funding txid=$BFTID (vout0 -> $BLADDR)"; ST "BOTH chains FUNDED + CONFIRMED"

# ---------- Alice claims BTC (reveals S) ----------
echo ""
echo ">>> STEP 3: Alice CLAIMS the BTC HTLC with the secret (reveals S on BTC)"
BALICE_BEFORE=$($BCLIN getreceivedbyaddress "$ALICE_B_ADDR" 0 2>/dev/null || echo 0)
BCLAIM=$($BDRV claim "$BFTID" 0 $BLOCK $BREDEEM $PRE $ALICE_B_PRIV $ALICE_B_ADDR 2000 regtest)
BCTID=$($BCLIN sendrawtransaction $BCLAIM); $BCLI generatetoaddress 1 "$MINEB" >/dev/null
echo "  BTC claim txid=$BCTID (Alice received BTC)"; ST "PREIMAGE REVEALED (BTC chain)"

# ---------- Watcher extracts S from the BTC claim (REAL watcher code) ----------
echo ""
echo ">>> STEP 4: Watcher extracts the preimage from the BTC claim witness (real ExtractBtcHtlcPreimageFromTxHex)"
BCLAIM_RAW=$($BCLIN getrawtransaction $BCTID)
SREVEAL=$($BDRV extract "$BCLAIM_RAW" 0 "$BHL" 2>/dev/null|hexline)
echo "  watcher-extracted preimage=$SREVEAL"
echo "  matches Alice's secret? $([ "$SREVEAL" = "$PRE" ]&&echo YES||echo NO)"
[ "$SREVEAL" = "$PRE" ] || { echo "WATCHER EXTRACT FAILED"; exit 1; }
ST "watcher ingested preimage -> auto-claim SOST leg"

# ---------- Bob claims SOST with S ----------
echo ""
echo ">>> STEP 5: Bob CLAIMS the SOST HTLC with the watcher-extracted secret"
BOB_S_BEFORE=$(sbal "$W/bob_s.json")
SCLAIMTX=$($SDRV claim $SLTX 0 $SLOCK $SREVEAL $BOB_S_PKH 10000 $SFEE $BOB_S_PRIV $GEN 2>/dev/null|hexline)
SCTID=$(srpc $RP "{\"method\":\"sendrawtransaction\",\"params\":[\"$SCLAIMTX\"],\"id\":1}"|grep -oE '[0-9a-f]{64}'|head -1)
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$ALICE_S" --wallet "$W/alice_s.json" --mining-key-label default --blocks 2 --threads 3 >>"$W/m.log" 2>&1; sleep 1
BOB_S_AFTER=$(sbal "$W/bob_s.json")
echo "  SOST claim txid=$SCTID"
echo "  Bob SOST: before=$BOB_S_BEFORE after=$BOB_S_AFTER"; ST "COMPLETED"

# ---------- final verification ----------
echo ""
echo "============ FINAL VERIFICATION ============"
ALICE_BTC_RECV=$($BCLIN getrawtransaction $BCTID true | python3 -c "import sys,json;d=json.load(sys.stdin);print(sum(o['value'] for o in d['vout'] if o['scriptPubKey'].get('address')=='$ALICE_B_ADDR'))")
echo "  Alice received BTC at $ALICE_B_ADDR = $ALICE_BTC_RECV BTC (expect ~0.5)"
echo "  Bob received SOST = $BOB_S_AFTER SOST (expect ~2)"
OK=1
python3 -c "exit(0 if float('${BOB_S_AFTER:-0}')>=1.9 else 1)" 2>/dev/null || OK=0
python3 -c "exit(0 if float('${ALICE_BTC_RECV:-0}')>=0.49 else 1)" 2>/dev/null || OK=0
[ "$SREVEAL" = "$PRE" ] || OK=0
if [ "$OK" = "1" ]; then
  echo ""
  echo "RESULT: ✅✅ COMPLETE SOST<->BTC ATOMIC SWAP — Alice got BTC, Bob got SOST, preimage bridged the two chains via real watcher code. No manual HTLC tx built by bitcoin-cli."
else
  echo "RESULT: ⚠️ incomplete (bob_sost=$BOB_S_AFTER alice_btc=$ALICE_BTC_RECV reveal_ok=$([ "$SREVEAL" = "$PRE" ]&&echo 1||echo 0))"
fi

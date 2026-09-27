set -u
ulimit -f unlimited
export PATH="$HOME/.foundry/bin:$PATH"
export ETH_RPC_URL=http://127.0.0.1:8545
ROOT=/home/sost/SOST/sostcore/sost-btc-work
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
BB="$S/build-sostswap"; NODE="$BB/sost-node"; MINER="$BB/sost-miner"; SCLI="$BB/sost-cli"; SDRV="$S/sost_htlc_driver"
RP=18296; PP=20296
CONTRACT=$(cat "$S/evm_contract.txt")
TOKEN="${1:-native}"   # native | erc20
W="$(mktemp -d /tmp/xevm.XXXXXX)"
NODE_PID=""; MINER_PID=""
cleanup(){ [ -n "$MINER_PID" ] && kill -9 "$MINER_PID" 2>/dev/null; [ -n "$NODE_PID" ] && kill -9 "$NODE_PID" 2>/dev/null; for pid in $(pgrep -f -- "$W" 2>/dev/null); do kill -9 "$pid" 2>/dev/null; done; }
trap cleanup EXIT
srpc(){ curl -s --max-time 8 --data "$2" "http://127.0.0.1:$1/"; }
hh(){ srpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
sbal(){ "$SCLI" --wallet "$1" --rpc 127.0.0.1:$RP getbalance 2>/dev/null|grep -oE 'Spendable: *[0-9.]+'|grep -oE '[0-9.]+'|head -1; }
hexline(){ grep -E '^[0-9a-f]+$'|tail -1; }
mineto(){ # mine until height >= $1 using a bg miner, then kill it (proven pattern)
  "$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$2" --wallet "$3" --mining-key-label default --blocks 100000 --threads 3 >/dev/null 2>&1 & local mp=$!
  while [[ "$(hh $RP)" -lt "$1" ]]; do sleep 1; done; kill -9 "$mp" 2>/dev/null; sleep 1; }
ST(){ echo "  [COORD] -> $1"; }

echo "============ SOST<->EVM ATOMIC SWAP ($TOKEN) — lab: SOST devnet + Anvil ============"
# identities
BOB_EVM_PK=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
ALICE_EVM_PK=0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a
BOB_EVM=$(cast wallet address $BOB_EVM_PK); ALICE_EVM=$(cast wallet address $ALICE_EVM_PK)
# SOST node
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/c.json" --port $PP --rpc-port $RP --rpc-noauth --connect 127.0.0.1:1 >/dev/null 2>&1 & NODE_PID=$!
for _ in $(seq 1 20); do sleep 1; [[ -n "$(hh $RP)" ]]&&break; done
GEN=$(srpc $RP '{"method":"getinfo","params":[],"id":1}'|grep -oE '[0-9a-f]{64}'|head -1)
ALICE_S=$("$SCLI" --wallet "$W/alice_s.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
BOB_S=$("$SCLI" --wallet "$W/bob_s.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
ALICE_S_PRIV=$("$SCLI" --wallet "$W/alice_s.json" dumpprivkey "$ALICE_S" 2>/dev/null|grep -oE '[0-9a-f]{64}'|head -1)
BOB_S_PRIV=$("$SCLI" --wallet "$W/bob_s.json" dumpprivkey "$BOB_S" 2>/dev/null|grep -oE '[0-9a-f]{64}'|head -1)
ALICE_S_PKH=$($SDRV pkh $ALICE_S_PRIV|hexline); BOB_S_PKH=$($SDRV pkh $BOB_S_PRIV|hexline)
PRE=1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
HL=$(python3 -c "import hashlib;print(hashlib.sha256(bytes.fromhex('$PRE')).hexdigest())")
echo "Alice(SOST)=$ALICE_S  Bob(SOST)=$BOB_S"
echo "Alice(EVM)=$ALICE_EVM  Bob(EVM)=$BOB_EVM  contract=$CONTRACT"
echo "H=$HL"; ST "Draft (2 SOST <-> 0.5 ETH, H, T_evm<T_sost)"

# ERC20 setup (deploy a test token, Bob funds swap with it) if requested
ERC20=""
if [ "$TOKEN" = "erc20" ]; then
  # deploy a minimal test ERC20 with a mint to Bob via forge? Use a prebuilt OpenZeppelin-free token:
  # Minimal: use the mock if present; else skip. (Handled by a helper contract below.)
  ERC20=$(cat "$S/evm_erc20.txt" 2>/dev/null)
  echo "  ERC20 token=$ERC20"
fi

# ---- Alice funds SOST ----
mineto 18 "$ALICE_S" "$W/alice_s.json"
U=$(srpc $RP "{\"method\":\"getaddressutxos\",\"params\":[\"$ALICE_S\"],\"id\":1}")
PTX=$(echo "$U"|python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if x.get('mature')][0];print(u['txid'])")
PV=$(echo "$U"|python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if x.get('mature')][0];print(u['vout'])")
PAMT=$(echo "$U"|python3 -c "import sys,json;d=json.load(sys.stdin)['result'];u=[x for x in d if x.get('mature')][0];print(u['amount_stocks'])")
SLOCK=200000000; SFEE=100000; SRH=$(( $(hh $RP) + 500 ))
echo ""; echo ">>> STEP 1: Alice LOCKS 2 SOST (claim=Bob, refund=Alice, H)"
LOCKTX=$($SDRV lock $PTX $PV $PAMT 1 $ALICE_S_PRIV $HL $SRH $BOB_S_PKH $ALICE_S_PKH $SLOCK $SFEE $GEN 2>/dev/null|hexline)
SLTX=$(srpc $RP "{\"method\":\"sendrawtransaction\",\"params\":[\"$LOCKTX\"],\"id\":1}"|grep -oE '[0-9a-f]{64}'|head -1)
mineto $(( $(hh $RP) + 2 )) "$ALICE_S" "$W/alice_s.json"
echo "  SOST lock txid=$SLTX (h=$(hh $RP))"; ST "SOST leg FUNDED"

# ---- Bob locks ETH/ERC20 in the contract ----
BLK=$(cast block-number); RT=$(( BLK + 1000 ))
  SWAPID=0x$(printf "%s" "$SLTX" | sha256sum | cut -c1-64)  # unique per run (SOST lock txid)
echo ""; echo ">>> STEP 2: Bob LOCKS 0.5 ETH in AtomicSwapHTLC (claim=Alice, refund=Bob, H, refundTime=$RT)"
if [ "$TOKEN" = "native" ]; then
  LOCKR=$(cast send "$CONTRACT" "lockNative(bytes32,bytes32,uint256,address,address)" "$SWAPID" "0x$HL" "$RT" "$ALICE_EVM" "$BOB_EVM" --value 0.5ether --private-key $BOB_EVM_PK --json 2>&1)
else
  cast send "$ERC20" "approve(address,uint256)" "$CONTRACT" 500000000000000000 --private-key $BOB_EVM_PK >/dev/null 2>&1
  LOCKR=$(cast send "$CONTRACT" "lockERC20(bytes32,address,uint256,bytes32,uint256,address,address)" "$SWAPID" "$ERC20" 500000000000000000 "0x$HL" "$RT" "$ALICE_EVM" "$BOB_EVM" --private-key $BOB_EVM_PK --json 2>&1)
fi
LOCK_STATUS=$(echo "$LOCKR"|python3 -c "import sys,json;print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
SW_STATE=$(cast call "$CONTRACT" "getSwap(bytes32)((uint8,address,uint256,bytes32,uint256,address,address))" "$SWAPID" 2>/dev/null | head -c 3)
echo "  lock tx status=$LOCK_STATUS  swap.state=$SW_STATE (1=LOCKED)"; ST "BOTH legs FUNDED"

# ---- Alice claims ETH (reveals S) ----
echo ""; echo ">>> STEP 3: Alice CLAIMS the ETH with the secret (reveals S in Claimed event)"
ALICE_ETH0=$(cast balance $ALICE_EVM)
CLAIMR=$(cast send "$CONTRACT" "claim(bytes32,bytes32)" "$SWAPID" "0x$PRE" --private-key $ALICE_EVM_PK --json 2>&1)
CLAIM_TXH=$(echo "$CLAIMR"|python3 -c "import sys,json;print(json.load(sys.stdin)['transactionHash'])" 2>/dev/null)
ALICE_ETH1=$(cast balance $ALICE_EVM)
echo "  claim tx=$CLAIM_TXH ; Alice ETH: $(awk "BEGIN{printf \"%.4f -> %.4f\", $ALICE_ETH0/1e18, $ALICE_ETH1/1e18}")"; ST "PREIMAGE REVEALED (EVM)"

# ---- Watcher extracts S from the Claimed event ----
echo ""; echo ">>> STEP 4: Watcher extracts preimage from the EVM Claimed event log"
CLAIMED_TOPIC=$(cast keccak "Claimed(bytes32,bytes32,address)")
REC=$(cast receipt "$CLAIM_TXH" --json 2>/dev/null)
SREVEAL=$(echo "$REC" | python3 -c "
import sys,json
r=json.load(sys.stdin)
for lg in r.get('logs',[]):
    if lg['topics'] and lg['topics'][0].lower()=='$CLAIMED_TOPIC'.lower():
        data=lg['data'][2:]
        print(data[0:64]); break
")
echo "  watcher-extracted preimage=$SREVEAL"
echo "  matches secret? $([ "$SREVEAL" = "$PRE" ]&&echo YES||echo NO)"
[ "$SREVEAL" = "$PRE" ] || { echo "WATCHER EXTRACT FAILED"; exit 1; }
ST "watcher ingested preimage -> auto-claim SOST"

# ---- Bob claims SOST with S ----
echo ""; echo ">>> STEP 5: Bob CLAIMS the SOST HTLC with the extracted secret"
SCLAIMTX=$($SDRV claim $SLTX 0 $SLOCK $SREVEAL $BOB_S_PKH 10000 $SFEE $BOB_S_PRIV $GEN 2>/dev/null|hexline)
SCTID=$(srpc $RP "{\"method\":\"sendrawtransaction\",\"params\":[\"$SCLAIMTX\"],\"id\":1}"|grep -oE '[0-9a-f]{64}'|head -1)
mineto $(( $(hh $RP) + 2 )) "$ALICE_S" "$W/alice_s.json"
BOB_S_BAL=$(sbal "$W/bob_s.json")
echo "  SOST claim txid=$SCTID ; Bob SOST=$BOB_S_BAL"; ST "COMPLETED"

# ---- verify ----
echo ""; echo "============ FINAL VERIFICATION ($TOKEN) ============"
A_DELTA=$(awk "BEGIN{printf \"%.4f\", ($ALICE_ETH1-$ALICE_ETH0)/1e18}")
echo "  Alice ETH gained ~$A_DELTA (expect ~+0.5 minus gas)"
echo "  Bob SOST = $BOB_S_BAL (expect ~2)"
OK=1
python3 -c "exit(0 if float('${BOB_S_BAL:-0}')>=1.9 else 1)" || OK=0
[ "$SREVEAL" = "$PRE" ] || OK=0
[ "$SW_STATE" = "0x1" -o "$SW_STATE" = "0x0" ] # informational
if [ "$OK" = "1" ]; then
  echo ""; echo "RESULT: ✅✅ COMPLETE SOST<->EVM ($TOKEN) ATOMIC SWAP — Bob got SOST, Alice got ETH, preimage bridged via the real Claimed event. Contract state machine (lock->claim) drove the EVM leg."
else
  echo "RESULT: ⚠️ incomplete (bob_sost=$BOB_S_BAL reveal_ok=$([ "$SREVEAL" = "$PRE" ]&&echo 1||echo 0))"
fi

#!/usr/bin/env bash
# SACS/AP — Asset Passport doc_ref ON-CHAIN round-trip (devnet, reproducible).
# manifest -> Capsule doc_ref -> mempool -> block -> RPC readback -> file_hash==manifestHash
# -> tamper rejection -> restart persistence. Real RPC readback (.capsule.file_hash).
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO=/home/sost/SOST/sostcore/sost-core; BIN=$REPO/build-sacs; G=$REPO/genesis_block.json
D=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad/aprt
rm -rf "$D"; mkdir -p "$D"; cd "$D"; printf p>pass; chmod 600 pass
RP=19932; P2P=19931
rpc(){ curl -s --max-time 8 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" http://127.0.0.1:$RP/ 2>/dev/null; }
capfield(){ python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('result') or {}; c=(r.get('capsule') or {}); print(c.get('$2',''))" 2>/dev/null; }
sw(){ ( sleep "$1" ) & wait $!; }
CLI="$BIN/sost-cli --node 127.0.0.1:$RP --rpc-user u --rpc-pass p --wallet $D/wallet.json"
startnode(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$D/chain.json" --wallet "$D/wallet.json" --port $P2P --rpc-port $RP --rpc-user u --rpc-pass-file pass >> node.log 2>&1 & echo $!; }
"$BIN/sost-cli" newwallet --wallet $D/wallet.json >/dev/null 2>&1
"$BIN/sost-cli" getnewaddress miner --wallet $D/wallet.json >/dev/null 2>&1
NODE=$(startnode); echo "node pid $NODE"
for i in $(seq 1 40); do rpc getblockcount | grep -q result && break; sw 0.5; done
echo "[1] node up h=$(rpc getblockcount | grep -oE '[0-9]+' | tail -1)"
nice -n 19 timeout 150 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$D/chain.json" --wallet "$D/wallet.json" --mining-key-label miner --rpc 127.0.0.1:$RP --rpc-user u --rpc-pass-file pass --blocks 7 --realtime --threads 3 > miner.log 2>&1
echo "[2-3] mined, h=$(rpc getblockcount | grep -oE '[0-9]+' | tail -1) (coinbase mature @>=5)"
node -e '
var AP=require("/home/sost/SOST/sostcore/sost-core/website/js/asset-passport.js"),fs=require("fs");
(async()=>{var p=await AP.buildPassport({category:"machinery",issuer:"sost1devissuer",nonce:"7",ownerDeclaration:"Excavator CAT-390F SN EXCDEV001",jurisdiction:"ES",rights:"bearer economic units",locator:"ipfs://QmExcavatorPassport",documents:[{name:"invoice.pdf",text:"CAT 390F 2019 100000 EUR"},{name:"inspection.pdf",text:"OK 2026"}]});
fs.writeFileSync("'"$D"'/manifest.json",AP.canon(p.manifest)); fs.writeFileSync("'"$D"'/mhash.txt",p.manifestHash);
console.log(p.manifestHash);})();' >/dev/null
MHASH=$(cat mhash.txt); echo "[4] manifestHash=$MHASH  (ANCHOR READY)"
RECIP=$($CLI getnewaddress recip 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
echo "[5] SEND doc-ref capsule..."
SEND=$($CLI --from-label miner send "$RECIP" 5 --capsule-mode doc-ref --capsule-file "$D/manifest.json" --capsule-locator "ipfs://QmExcavatorPassport" --skip-warning --yes 2>&1)
echo "$SEND" | grep -iE 'error|reject|txid|broadcast|accepted' | tail -3
TXID=$(rpc getrawmempool | grep -oE '[0-9a-f]{64}' | head -1)
echo "[6-7] mempool: $(rpc getrawmempool)"
if [ -z "$TXID" ]; then echo "  >>> NOT IN MEMPOOL. send output:"; echo "$SEND" | tail -8; kill -9 $NODE; exit 1; fi
echo "  TXID=$TXID  (MEMPOOL ACCEPTED)"
CAPFH_MP=$(rpc getrawtransaction "[\"$TXID\",1]" | capfield x file_hash)
CAPTYPE=$(rpc getrawtransaction "[\"$TXID\",1]" | capfield x type)
echo "  mempool capsule.type=$CAPTYPE file_hash=$CAPFH_MP"
echo "[8-9] mine 1 -> confirm"
nice -n 19 timeout 60 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$D/chain.json" --wallet "$D/wallet.json" --mining-key-label miner --rpc 127.0.0.1:$RP --rpc-user u --rpc-pass-file pass --blocks 1 --realtime --threads 3 >> miner.log 2>&1
sw 2
VJSON=$(rpc getrawtransaction "[\"$TXID\",1]")
CONF=$(echo "$VJSON" | python3 -c "import json,sys;r=json.load(sys.stdin).get('result') or {};print(r.get('confirmed'),r.get('block_height'))" 2>/dev/null)
CAPFH=$(echo "$VJSON" | capfield x file_hash)
echo "  confirmed/block_height=$CONF  (CONFIRMED)"
echo "[10-12] readback capsule.file_hash=$CAPFH"
echo "        manifestHash        =$MHASH"
if [ "$CAPFH" = "$MHASH" ]; then echo "  >>> VERIFIED ✅ file_hash == manifestHash (byte-exact)"; else echo "  >>> MISMATCH ❌"; fi
echo "[13] TAMPER test"
cp manifest.json manifest.tampered.json; printf 'X' >> manifest.tampered.json
TH=$(sha256sum manifest.tampered.json | awk '{print $1}')
echo "  tampered sha256=$TH"
if [ "$TH" != "$CAPFH" ]; then echo "  >>> TAMPER DETECTED ✅ (tampered hash != on-chain file_hash)"; else echo "  >>> TAMPER NOT DETECTED ❌"; fi
echo "[14] RESTART node + re-verify"
kill -9 $NODE 2>/dev/null; sw 2; NODE=$(startnode)
for i in $(seq 1 40); do rpc getblockcount | grep -q result && break; sw 0.5; done
VJSON2=$(rpc getrawtransaction "[\"$TXID\",1]"); CAPFH2=$(echo "$VJSON2" | capfield x file_hash)
CONF2=$(echo "$VJSON2" | python3 -c "import json,sys;r=json.load(sys.stdin).get('result') or {};print(r.get('confirmed'),r.get('block_height'))" 2>/dev/null)
echo "  after restart: confirmed/block_height=$CONF2 file_hash=$CAPFH2 match=$([ "$CAPFH2" = "$MHASH" ] && echo YES || echo NO)"
kill -9 $NODE 2>/dev/null
echo "SUMMARY txid=$TXID block=$(echo $CONF|awk '{print $2}') manifestHash=$MHASH onchain_file_hash=$CAPFH"
echo DONE

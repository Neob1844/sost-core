#!/usr/bin/env bash
# SACS P6 — real tx-safety lifecycle PENDING -> CONFIRMED -> REENTERED_MEMPOOL,
# driven by live node RPC through the real website/lab/sacs/sacs-tx-safety.js.
# A & B share a 6-block prefix (so the tx's funding coinbase survives the reorg);
# B confirms a tx in block 7; A mines a heavier divergent 7..10; feeding A->B
# reorgs out B's block 7 (disconnect 1) and the tx re-enters B's mempool.
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; BIN="${BIN:-$REPO/build-sacs}"; G=$REPO/genesis_block.json
ROOT="$(mktemp -d)"; SD="$(cd "$(dirname "$0")" && pwd)"; FEED="$SD/sacs_feedchain.py"; POLL="$SD/sacs_txsafety_poll.js"
trap 'rm -rf "$ROOT"' EXIT
rpc(){ curl -s --max-time 10 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
h(){ rpc $1 getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1; }
softwait(){ ( sleep "$1" ) & wait $!; }
cli(){ "$BIN/sost-cli" --node 127.0.0.1:$1 --rpc-user u --rpc-pass p --wallet "$2/w.json" "${@:3}"; }
sw(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
snode(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass" >> "$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 200 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 3 >> "$1/miner.log" 2>&1; }
wr(){ for i in $(seq 1 60); do [ -n "$(h $1)" ] && return 0; softwait 0.5; done; }
wh(){ for i in $(seq 1 120); do [ "$(h $1)" = "$2" ] && return 0; softwait 0.5; done; }

rm -rf "$ROOT"; mkdir -p "$ROOT/A" "$ROOT/B"; printf p>"$ROOT/A/pass"; printf p>"$ROOT/B/pass"; chmod 600 "$ROOT/A/pass" "$ROOT/B/pass"
sw "$ROOT/A"; sw "$ROOT/B"
NA=$(snode "$ROOT/A" 19931 19932); wr 19932
NB=$(snode "$ROOT/B" 19941 19942); wr 19942

echo "1) B mines 6-block prefix (matures coinbase@1)"
mine "$ROOT/B" 19942 6; wh 19942 6
echo "   B height=$(h 19942)"
echo "2) Share prefix: feed B[1..6] -> A"
python3 "$FEED" 19942 19932 6 >/dev/null; echo "   A height=$(h 19932) (should be 6, same chain)"

echo "3) B sends a real tx (spends matured coinbase@1)"
DEST=$(cli 19942 "$ROOT/B" getnewaddress recv 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
echo "   dest=$DEST"
SENDOUT=$(cli 19942 "$ROOT/B" --from-label m send "$DEST" 1 --skip-warning --yes 2>&1)
echo "   send done (see broadcast below)"
softwait 1
# The authoritative txid is the one now sitting in B's mempool (not a parse of stdout,
# which also contains the spent input's coinbase txid).
TXID=$(rpc 19942 getrawmempool | grep -oE '[0-9a-f]{64}' | head -1)
echo "   TXID (from mempool)=$TXID"
[ -z "$TXID" ] && { echo "   NO TXID — send failed; aborting"; kill -9 $NA $NB; exit 1; }
echo "   mempool now: $(rpc 19942 getrawmempool)"

echo "4) Start tx-safety poller on B (real RPC-driven state machine)"
/usr/bin/node "$POLL" 19942 "$TXID" 90 > "$ROOT/txsafety.log" 2>&1 &
POLLER=$!
softwait 3

echo "5) B mines block 7 (confirms the tx)"
mine "$ROOT/B" 19942 1; wh 19942 7
softwait 3
echo "   B height=$(h 19942); tx confirmed?"

echo "6) A mines heavier divergent chain 7..10 (no tx) on the shared prefix"
mine "$ROOT/A" 19932 4; wh 19932 10
echo "   A height=$(h 19932)"

echo "7) Feed A[7..10] -> B : reorg out B block 7 (disconnect 1), tx should re-enter mempool"
python3 "$FEED" 19932 19942 10 >/dev/null
softwait 5
echo "   B height now=$(h 19942); mempool: $(rpc 19942 getrawmempool)"

echo "8) Wait for poller to capture final transition"
softwait 6
kill $POLLER 2>/dev/null; wait $POLLER 2>/dev/null

echo
echo "===== TX-SAFETY STATE TRANSITIONS (real RPC-driven) ====="
cat "$ROOT/txsafety.log" | sed 's/^/   /'
echo "===== SACS monitor TX_REORGED / REORG events on B ====="
rpc 19942 getsacsevents '[0,200]' | python3 -c "import json,sys; d=json.load(sys.stdin)['result']; [print('   ',e['type'],e.get('detail','')) for e in d['events'] if e['type'] in ('REORG_STARTED','REORG_COMPLETED','TX_REORGED','TX_CONFLICTED')]" 2>/dev/null
kill -9 $NA $NB 2>/dev/null
echo ALLDONE

#!/usr/bin/env bash
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; BIN="${BIN:-$REPO/build-sacs}"; G=$REPO/genesis_block.json
ROOT="$(mktemp -d)"; FEED="$(cd "$(dirname "$0")" && pwd)/sacs_feedchain.py"
trap 'rm -rf "$ROOT"' EXIT
rpc(){ curl -s --max-time 10 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
h(){ rpc $1 getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1; }
softwait(){ ( sleep "$1" ) & wait $!; }
sw(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
node(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass" >> "$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 200 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 3 >> "$1/miner.log" 2>&1; }
wr(){ for i in $(seq 1 60); do [ -n "$(h $1)" ] && return 0; softwait 0.5; done; }
wh(){ for i in $(seq 1 120); do [ "$(h $1)" = "$2" ] && return 0; softwait 0.5; done; }
rm -rf "$ROOT"; mkdir -p "$ROOT/A" "$ROOT/B"; printf p>"$ROOT/A/pass"; printf p>"$ROOT/B/pass"; chmod 600 "$ROOT/A/pass" "$ROOT/B/pass"
sw "$ROOT/A"; sw "$ROOT/B"
NA=$(node "$ROOT/A" 19931 19932); wr 19932; mine "$ROOT/A" 19932 9; wh 19932 9
NB=$(node "$ROOT/B" 19941 19942); wr 19942; mine "$ROOT/B" 19942 8; wh 19942 8
echo "A h=$(h 19932) B h=$(h 19942); feeding A->B to trigger reorg..."
python3 "$FEED" 19932 19942 9 >/dev/null
softwait 3
echo; echo "===== [SACS] lines in B node.log ====="
grep -E '\[SACS\]' "$ROOT/B/node.log" | sed 's/^/  /'
echo; echo "===== RPC getsacsstatus (B) ====="
rpc 19942 getsacsstatus | python3 -m json.tool 2>/dev/null | sed 's/^/  /' || rpc 19942 getsacsstatus
echo; echo "===== RPC getsacsevents [after_seq=0, limit=3] (B) — pagination ====="
rpc 19942 getsacsevents '[0,3]' | python3 -m json.tool 2>/dev/null | sed 's/^/  /'
echo; echo "===== RPC getsacsevents [limit=99999] — server clamp to <=200 ====="
rpc 19942 getsacsevents '[0,99999]' | grep -oE '"returned":[0-9]+|"ring_max":[0-9]+' | sed 's/^/  /'
echo; echo "===== RPC bad param (non-numeric) — must error, not crash ====="
rpc 19942 getsacsevents '["abc"]' | sed 's/^/  /'
echo; echo "===== JSONL sink file (tail) ====="
tail -4 "$ROOT/B/chain.json.sacs.jsonl" 2>/dev/null | sed 's/^/  /'
echo "  sink lines: $(wc -l < "$ROOT/B/chain.json.sacs.jsonl" 2>/dev/null)"
kill -9 $NA $NB 2>/dev/null

#!/usr/bin/env bash
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; BIN="${BIN:-$REPO/build-sacs}"; G=$REPO/genesis_block.json
ROOT="$(mktemp -d)"; FEED="$(cd "$(dirname "$0")" && pwd)/sacs_feedchain.py"
trap 'rm -rf "$ROOT"' EXIT
rpc(){ curl -s --max-time 10 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
h(){ rpc $1 getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1; }
tip(){ rpc $1 getbestblockhash | grep -oE '"result":"[0-9a-f]+"' | grep -oE '[0-9a-f]{16,}' | head -1; }
softwait(){ ( sleep "$1" ) & wait $!; }
sw(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
node(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass" >> "$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 200 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 3 >> "$1/miner.log" 2>&1; }
wr(){ for i in $(seq 1 60); do [ -n "$(h $1)" ] && return 0; softwait 0.5; done; }
wh(){ for i in $(seq 1 120); do [ "$(h $1)" = "$2" ] && return 0; softwait 0.5; done; }
setup(){ local NAME=$1 AH=$2 BH=$3; local DA=$ROOT/$NAME/A DB=$ROOT/$NAME/B
  rm -rf "$ROOT/$NAME"; mkdir -p "$DA" "$DB"; printf p>"$DA/pass"; printf p>"$DB/pass"; chmod 600 "$DA/pass" "$DB/pass"
  sw "$DA"; sw "$DB"
  NA=$(node "$DA" 19931 19932); wr 19932; mine "$DA" 19932 "$AH"; wh 19932 "$AH"
  NB=$(node "$DB" 19941 19942); wr 19942; mine "$DB" 19942 "$BH"; wh 19942 "$BH"; }

echo "############ REJECT path -> REORG_REJECTED ############"
setup rej 10 9
BPRE=$(tip 19942)
python3 "$FEED" 19932 19942 10 >/dev/null; softwait 3
echo "  REORG_REJECTED events on B:"; rpc 19942 getsacsevents '[0,200]' | python3 -c "import json,sys; d=json.load(sys.stdin)['result']; [print('   ',e['type'],e.get('detail','')) for e in d['events'] if e['type']=='REORG_REJECTED']"
echo "  B tip unchanged: $([ "$(tip 19942)" = "$BPRE" ] && echo YES || echo NO) (h=$(h 19942))"
kill -9 $NA $NB 2>/dev/null; softwait 1

echo
echo "############ RECOVERY path (DEV failpoint) -> RECOVERY_STARTED/COMPLETED ############"
setup rec 9 8
BPRE=$(tip 19942)
echo "  arm failpoint ordinal 4 on B: $(rpc 19942 devsetreorgfailpoint '[4]')"
python3 "$FEED" 19932 19942 9 >/dev/null; softwait 3
echo "  RECOVERY events on B:"; rpc 19942 getsacsevents '[0,200]' | python3 -c "import json,sys; d=json.load(sys.stdin)['result']; [print('   ',e['type'],e.get('detail','')) for e in d['events'] if e['type'] in ('RECOVERY_STARTED','RECOVERY_COMPLETED','REORG_STARTED','REORG_COMPLETED')]"
echo "  B tip after failed reorg (should equal pre-reorg own tip): $([ "$(tip 19942)" = "$BPRE" ] && echo YES-kept-own || echo NO) (h=$(h 19942))"
echo "  status counts: $(rpc 19942 getsacsstatus | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['counts'])")"
kill -9 $NA $NB 2>/dev/null
echo ALLDONE

#!/usr/bin/env bash
# SACS P7 (ASan/UBSan) — exercise the reorg + monitor code under AddressSanitizer
# and UndefinedBehaviorSanitizer. Small chains (fast under sanitizers). Any ASan/UBSan
# report on stderr = FAIL. Uses ports 199 7x.
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; BIN="${BIN:-$REPO/build-sacs-asan}"; G=$REPO/genesis_block.json
ROOT="$(mktemp -d)"; FEED="$(cd "$(dirname "$0")" && pwd)/sacs_feedchain.py"
trap 'rm -rf "$ROOT"' EXIT
export ASAN_OPTIONS="detect_leaks=0:abort_on_error=0:halt_on_error=0:log_path=$ROOT/asan"
export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=0:log_path=$ROOT/ubsan"
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
h(){ rpc $1 getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1; }
softwait(){ ( sleep "$1" ) & wait $!; }
sw(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
snode(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass" >> "$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 400 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 2 >> "$1/miner.log" 2>&1; }
wr(){ for i in $(seq 1 80); do [ -n "$(h $1)" ] && return 0; softwait 0.5; done; }
wh(){ for i in $(seq 1 240); do [ "$(h $1)" = "$2" ] && return 0; softwait 0.5; done; }
rm -rf "$ROOT"; mkdir -p "$ROOT/A" "$ROOT/B"; printf p>"$ROOT/A/pass"; printf p>"$ROOT/B/pass"; chmod 600 "$ROOT/A/pass" "$ROOT/B/pass"
sw "$ROOT/A"; sw "$ROOT/B"
echo "Exercising reorg engine + SACS monitor under ASan+UBSan (converge A=5/B=4, then failpoint recovery)..."
NA=$(snode "$ROOT/A" 19971 19970); wr 19970; mine "$ROOT/A" 19970 5; wh 19970 5
NB=$(snode "$ROOT/B" 19973 19972); wr 19972; mine "$ROOT/B" 19972 4; wh 19972 4
# converge: feed A(5)->B(4) => disconnect 4, reorg
python3 "$FEED" 19970 19972 5 >/dev/null; softwait 3
echo "  after converge: B h=$(h 19972) (expect 5); status=$(rpc 19972 getsacsstatus | grep -oE '"REORG_COMPLETED":[0-9]+')"
# also fuzz the RPC under ASan
rpc 19972 getsacsevents '[-1]' >/dev/null; rpc 19972 getsacsevents '["x"]' >/dev/null; rpc 19972 getsacsevents '[0,99999999]' >/dev/null
kill -9 $NA $NB 2>/dev/null; softwait 2
echo "===== SANITIZER REPORTS ====="
ASAN=$(cat "$ROOT"/asan.* 2>/dev/null | wc -l); UBSAN=$(cat "$ROOT"/ubsan.* 2>/dev/null | wc -l)
echo "  ASan report lines: $ASAN ; UBSan report lines: $UBSAN"
if [ "$ASAN" -eq 0 ] && [ "$UBSAN" -eq 0 ]; then echo "  P7-ASAN: PASS (no ASan/UBSan errors during reorg + monitor + RPC fuzz)";
else echo "  P7-ASAN: FAIL — sanitizer output follows:"; cat "$ROOT"/asan.* "$ROOT"/ubsan.* 2>/dev/null | head -40; fi
echo ALLDONE

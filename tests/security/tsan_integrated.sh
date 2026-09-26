#!/usr/bin/env bash
# 2C — TSan on integrated binary: block production + P2P reception + reorg/convergence + concurrent RPC.
set -u
ROOT=/home/sost/SOST/sostcore/sost-core
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
TN="$S/build-integ-tsan/sost-node"; DN="$S/build-integ-dev/sost-node"; MINER="$S/build-integ-dev/sost-miner"; CLI="$S/build-integ-dev/sost-cli"
W="$(mktemp -d /tmp/tsi.XXXXXX)"
cleanup(){ for pid in $(pgrep -f -- "$W" 2>/dev/null); do [[ "$pid" == "$$" ]]&&continue; kill "$pid" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT
rpc(){ curl -s --max-time 8 --data "$2" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
export TSAN_OPTIONS="halt_on_error=0:history_size=4"
A="$("$CLI" --wallet "$W/a.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"
B="$("$CLI" --wallet "$W/b.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"
# honest peer B (non-TSan, fast) mines a divergent chain to 12
"$DN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/b.json" --port 20212 --rpc-port 18212 --rpc-noauth --connect 127.0.0.1:1 >"$W/b.log" 2>&1 &
for _ in $(seq 1 25); do sleep 1; [[ -n "$(height 18212)" ]]&&break; done
"$MINER" --profile dev --rpc 127.0.0.1:18212 --address "$B" --wallet "$W/b.json" --mining-key-label default --blocks 100000 --threads 3 >>"$W/mb.log" 2>&1 & MBB=$!
while [[ "$(height 18212)" -lt 12 ]]; do sleep 2; done; kill $MBB 2>/dev/null; sleep 1
# TSan victim: its own chain to ~4, then connect to B (reorg/converge under TSan) + concurrent RPC + own miner
"$TN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/t.json" --port 20210 --rpc-port 18210 --rpc-noauth --connect 127.0.0.1:1 >"$W/t.log" 2>&1 & TPID=$!
for _ in $(seq 1 40); do sleep 1; [[ -n "$(height 18210)" ]]&&break; done
"$MINER" --profile dev --rpc 127.0.0.1:18210 --address "$A" --wallet "$W/a.json" --mining-key-label default --blocks 100000 --threads 2 >>"$W/mt.log" 2>&1 & MT=$!
while [[ "$(height 18210)" -lt 4 ]]; do sleep 3; done; kill $MT 2>/dev/null; sleep 1
echo "[2C] TSan victim @h=$(height 18210), honest B @h=$(height 18212); connecting + concurrent RPC storm"
# connect victim to B (triggers reorg/convergence under TSan) by restarting with --connect
kill $TPID 2>/dev/null; sleep 2
"$TN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/t.json" --port 20210 --rpc-port 18210 --rpc-noauth --connect 127.0.0.1:20212 >>"$W/t.log" 2>&1 & TPID=$!
for _ in $(seq 1 40); do sleep 1; [[ -n "$(height 18210)" ]]&&break; done
# concurrent RPC storm during convergence
worker(){ local end=$(( $(date +%s)+40 )); local pls=('{"method":"getblockcount","params":[],"id":1}' '{"method":"getblocktemplate","params":["'"$A"'"],"id":1}' '{"method":"getblock","params":[[[[1]]]],"id":1}' '{"method":"getbestblockhash","params":[],"id":1}' '{"method":"getblockhash","params":["str"],"id":1}' '{"method":"getpeerinfo","params":[],"id":1}'); while [[ $(date +%s) -lt $end ]]; do curl -s --max-time 5 --data "${pls[$((RANDOM%6))]}" http://127.0.0.1:18210/ >/dev/null 2>&1; done; }
wpids=(); for w in 1 2 3 4 5; do worker & wpids+=($!); done
# also restart B's miner so blocks keep flowing to the victim (P2P reception under TSan)
"$MINER" --profile dev --rpc 127.0.0.1:18212 --address "$B" --wallet "$W/b.json" --mining-key-label default --blocks 100000 --threads 2 >>"$W/mb2.log" 2>&1 & MB2=$!
sleep 42; kill $MB2 "${wpids[@]}" 2>/dev/null; sleep 3
echo "[2C] victim final h=$(height 18210) (B@$(height 18212)); converged=$([ "$(height 18210)" -ge 12 ]&&echo sí||echo parcial)"
kill $TPID 2>/dev/null; sleep 3; kill $(pgrep -f -- "$W" 2>/dev/null) 2>/dev/null
races=$(grep -c 'ThreadSanitizer: data race' "$W/t.log" 2>/dev/null); tot=$(grep -c 'ThreadSanitizer:' "$W/t.log" 2>/dev/null)
echo "[2C] TSan: data_races=$races total_warnings=$tot"
[[ "$tot" -gt 0 ]] && { echo "  --- señales ---"; grep -A5 'ThreadSanitizer:' "$W/t.log"|head -30|sed 's/^/    /'; } || echo "  ✅ 0 reportes TSan (producción + P2P + reorg/convergencia + RPC concurrente simultáneos)"

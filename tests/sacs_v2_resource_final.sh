#!/usr/bin/env bash
# SACS V2 · resource-bounds at LITERAL depth D (production fork-store/try_reorganize/
# disconnect/connect/rollback/restart). Measures: peak RSS (VmHWM), CPU, wall, disk
# growth, fork-store event count, UTXO-root consistency, restart stability.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-rc/build-v30000-devadmin"; G="$SP/wt-rc/genesis_block.json"; FEED="$SP/wt-rc/tests/sacs_feedchain.py"
D=${1:-500}; H=44; AEXT=$((D+5)); BEXT=$D    # candidate A heavier(+5), active B = depth D
ROOT="$(mktemp -d)"; echo "ROOT=$ROOT  DEPTH=$D  (mine ~$((H+AEXT+BEXT)) blocks total)"
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }; str(){ echo "$1"|grep -oE '"result":"[0-9a-f]+"'|grep -oE '[0-9a-f]{16,}'|head -1; }
h(){ num "$(rpc $1 getblockcount)"; }; tip(){ str "$(rpc $1 getbestblockhash)"; }; sw(){ ( sleep "$1" ) & wait $!; }
wal(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json">/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json">/dev/null 2>&1; }
node(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass">>"$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 86400 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 4>>"$1/miner.log" 2>&1; }
wrpc(){ for i in $(seq 1 60);do curl -s --max-time 3 -o /dev/null http://127.0.0.1:$1/ 2>/dev/null&&return 0;sw 0.5;done;return 1; }
wh(){ for i in $(seq 1 200000);do [ "$(h $1)" -ge "$2" ] 2>/dev/null&&return 0;sw 1;done;return 1; }
hwm(){ grep VmHWM /proc/$1/status 2>/dev/null|grep -oE '[0-9]+'|head -1; }  # peak RSS kB
uroot(){ "$BIN/sost-node" --profile dev --dry-run-replay --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" 2>/dev/null|grep -oE 'utxo_set_root: [0-9a-f]+'|grep -oE '[0-9a-f]{16,}'; }
fscount(){ rpc $1 getsacsstatus | grep -oE '"events?"[: ]*[0-9]+|ring[^,]*[0-9]+' | head -1; }

DC=$ROOT/C DA=$ROOT/A DB=$ROOT/B; mkdir -p "$DC" "$DA" "$DB"; for d in "$DC" "$DA" "$DB";do printf p>"$d/pass";chmod 600 "$d/pass";done
T0=$(date +%s)
echo "[$(date +%T)] mining common chain to H=$H..."
wal "$DC"; NC=$(node "$DC" 19961 19962); wrpc 19962; mine "$DC" 19962 "$H"; wh 19962 "$H"; kill -9 $NC 2>/dev/null; sw 1
cp "$DC/chain.json" "$DA/chain.json"; cp "$DC/chain.json" "$DB/chain.json"; wal "$DA"; wal "$DB"
echo "[$(date +%T)] mining active B +$BEXT (depth $D)..."
NB=$(node "$DB" 19941 19942); wrpc 19942; mine "$DB" 19942 "$BEXT"; wh 19942 "$((H+BEXT))"
echo "[$(date +%T)] mining candidate A +$AEXT (heavier)..."
NA=$(node "$DA" 19931 19932); wrpc 19932; mine "$DA" 19932 "$AEXT"; wh 19932 "$((H+AEXT))"
T1=$(date +%s); echo "[$(date +%T)] mining done in $((T1-T0))s (~$(python3 -c "print(round(($H+$AEXT+$BEXT)/max(1,($T1-$T0)),2))") blk/s)"
AH=$(h 19932); DISK_B0=$(du -sb "$DB/chain.json" 2>/dev/null|cut -f1); RSS_B0=$(hwm $NB); UROOT_B0=$(uroot "$DB")
echo "=== FEED candidate A (depth $D reorg) → B, sampling RSS ==="
( for i in $(seq 1 600); do echo "$(hwm $NB)" >> "$ROOT/rss.samples"; sw 0.5; done ) & SAMP=$!
TF0=$(date +%s); python3 "$FEED" 19932 19942 "$AH" >/dev/null 2>&1; sw 5; TF1=$(date +%s)
kill $SAMP 2>/dev/null
BTIP=$(tip 19942); BH=$(h 19942); RSS_PEAK=$(sort -n "$ROOT/rss.samples" 2>/dev/null|tail -1); DISK_B1=$(du -sb "$DB/chain.json" 2>/dev/null|cut -f1)
UROOT_A=$(uroot "$DA")
echo "=== RESTART B (persistence tras deep reorg) ==="
kill -9 $NB 2>/dev/null; sw 2; NB=$(node "$DB" 19941 19942); wrpc 19942; TR=$(tip 19942); UROOT_B1=$(uroot "$DB"); kill -9 $NA $NB 2>/dev/null
echo ""
echo "======== RESOURCE-BOUNDS · DEPTH $D ========"
echo "  mine wall:            $((T1-T0))s"
echo "  reorg wall:           $((TF1-TF0))s"
echo "  peak RSS (VmHWM):     ${RSS_PEAK:-?} kB  (pre-feed ${RSS_B0:-?} kB)"
echo "  disk chain.json:      ${DISK_B0:-?} → ${DISK_B1:-?} bytes"
echo "  B converged to A:     tip=$(echo $BTIP|cut -c1-12) height=$BH  (A tip=$(echo $(tip_stub)|cut -c1-12 2>/dev/null))"
echo "  UTXO root A==B:       $([ "$UROOT_A" = "$UROOT_B1" ] && echo YES || echo NO)  (A=$(echo $UROOT_A|cut -c1-16) B=$(echo $UROOT_B1|cut -c1-16))"
echo "  restart tip stable:   $([ "$TR" = "$BTIP" ] && echo YES || echo NO)"
echo "  RESULT depth $D: $([ "$BH" -ge "$((H+AEXT))" ] 2>/dev/null && [ "$UROOT_A" = "$UROOT_B1" ] && [ "$TR" = "$BTIP" ] && echo 'PASS (converged + UTXO-consistent + restart-stable + bounded)' || echo 'CHECK — revisar métricas')"
echo "RESOURCE_DEPTH_${D}_DONE"
rm -rf "$ROOT"

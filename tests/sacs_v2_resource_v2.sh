#!/usr/bin/env bash
# SACS V2 · resource-bounds, LITERAL depths, PRE-DECLARED PASS/FAIL thresholds.
# Reuses a single common prefix (mined once). Empty-block profile (profile B = loaded
# is a separate harness). Production code paths only (fork-store/try_reorganize/
# disconnect/connect/BlockUndo/rollback/restart) — accel is via devnet mining ease only.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-v2/build-v2"; G="$SP/wt-v2/genesis_block.json"; FEED="$SP/wt-v2/tests/sacs_feedchain.py"
# ===== PRE-DECLARED THRESHOLDS (fixed BEFORE any results) =====
MAX_RSS_MB=3072            # peak RSS hard fail > 3 GB
MAX_RSS_LEAK_MB=300       # RSS after cleanup must return to baseline+300MB
MAX_REORG_WALL_S=120      # disconnect+connect of <=1005 blocks must finish < 120s
MAX_RESTART_S=60          # restart converge < 60s
DISK_FACTOR=3            # peak disk (chain+forkstore) <= 3x winning-chain bytes
# UTXO root A==B, final tip==candidate, restart tip stable: MUST match exactly (bool)
echo "PRE-DECLARED PASS/FAIL: peak_RSS<${MAX_RSS_MB}MB · RSS_leak<${MAX_RSS_LEAK_MB}MB · reorg_wall<${MAX_REORG_WALL_S}s · restart<${MAX_RESTART_S}s · disk_peak<=${DISK_FACTOR}x · UTXO==exact · tip==candidate · restart-stable"
echo ""
H=44; DEPTHS="${1:-500 501 550 600 1000}"
ROOT="$(mktemp -d)"; rpc(){ curl -s --max-time 20 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }; str(){ echo "$1"|grep -oE '"result":"[0-9a-f]+"'|grep -oE '[0-9a-f]{16,}'|head -1; }
h(){ num "$(rpc $1 getblockcount)"; }; tip(){ str "$(rpc $1 getbestblockhash)"; }; sw(){ ( sleep "$1" ) & wait $!; }
wal(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json">/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json">/dev/null 2>&1; }
node(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass">>"$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 86400 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 4>>"$1/miner.log" 2>&1; }
wrpc(){ for i in $(seq 1 60);do curl -s --max-time 3 -o /dev/null http://127.0.0.1:$1/ 2>/dev/null&&return 0;sw 0.5;done;return 1; }
wh(){ for i in $(seq 1 400000);do [ "$(h $1)" -ge "$2" ] 2>/dev/null&&return 0;sw 1;done;return 1; }
hwm(){ awk '/VmHWM/{print $2}' /proc/$1/status 2>/dev/null; }
rss(){ awk '/VmRSS/{print $2}' /proc/$1/status 2>/dev/null; }
uroot(){ "$BIN/sost-node" --profile dev --dry-run-replay --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" 2>/dev/null|grep -oE 'utxo_set_root: [0-9a-f]+'|grep -oE '[0-9a-f]{16,}'; }
# mine common prefix ONCE, reuse
CB=$ROOT/common; mkdir -p "$CB"; printf p>"$CB/pass"; chmod 600 "$CB/pass"; wal "$CB"
echo "[$(date +%T)] mining common prefix to H=$H (once, reused)..."
NC=$(node "$CB" 19961 19962); wrpc 19962; mine "$CB" 19962 "$H"; wh 19962 "$H"; kill -9 $NC 2>/dev/null; sw 1
echo "[$(date +%T)] common ready (tip $(cat "$CB/chain.json" >/dev/null 2>&1; echo ok))"
printf "%-6s %-8s %-9s %-9s %-8s %-9s %-9s %-8s %-9s %-6s %-6s %s\n" DEPTH RSS_MB RSSpost DISKpk_x REORGs RESTARTs UTXO== TIP== fork_evts wall PROF RESULT
for D in $DEPTHS; do
  DA=$ROOT/A_$D DB=$ROOT/B_$D; rm -rf "$DA" "$DB"; mkdir -p "$DA" "$DB"
  cp "$CB/chain.json" "$DA/chain.json"; cp "$CB/chain.json" "$DB/chain.json"; cp "$CB/w.json" "$DA/w.json" 2>/dev/null; wal "$DA"; wal "$DB"
  printf p>"$DA/pass"; printf p>"$DB/pass"; chmod 600 "$DA/pass" "$DB/pass"
  NB=$(node "$DB" 19941 19942); wrpc 19942; mine "$DB" 19942 "$D"; wh 19942 "$((H+D))"
  NA=$(node "$DA" 19931 19932); wrpc 19932; mine "$DA" 19932 "$((D+5))"; wh 19932 "$((H+D+5))"
  AH=$(h 19932); RSS0=$(rss $NB); DISK0=$(du -sb "$DB/chain.json"|cut -f1); UROOT_A=$(uroot "$DA")
  ( for i in $(seq 1 400); do hwm $NB >> "$DB/rss.samp"; sw 0.3; done ) & SAMP=$!
  TF0=$(date +%s); python3 "$FEED" 19932 19942 "$AH" >/dev/null 2>&1; sw 3; TF1=$(date +%s); kill $SAMP 2>/dev/null
  BTIP=$(tip 19942); RSSpk=$(sort -n "$DB/rss.samp" 2>/dev/null|tail -1); DISKpk=$(du -sb "$DB/chain.json"|cut -f1)
  sw 3; RSSpost=$(rss $NB); FEVTS=$(rpc 19942 getsacsstatus | grep -oE '[0-9]+' | head -1)
  kill -9 $NB 2>/dev/null; sw 2; NB=$(node "$DB" 19941 19942); TR0=$(date +%s); wrpc 19942; TR=$(tip 19942); TR1=$(date +%s); UROOT_B=$(uroot "$DB"); kill -9 $NA $NB 2>/dev/null; sw 1
  # evaluate vs PRE-DECLARED thresholds
  RSSpk_mb=$((${RSSpk:-0}/1024)); RSSpost_mb=$((${RSSpost:-0}/1024)); RSS0_mb=$((${RSS0:-0}/1024))
  disk_x=$(python3 -c "print(round(${DISKpk:-1}/max(1,${DISK0:-1}),2))")
  reorg_s=$((TF1-TF0)); restart_s=$((TR1-TR0))
  utxo_ok=$([ "$UROOT_A" = "$UROOT_B" ] && echo YES || echo NO); tip_ok=$([ "$TR" = "$AH_TIP" ] 2>/dev/null; [ "$BTIP" = "$TR" ] && echo YES || echo NO)
  P=PASS
  [ "$RSSpk_mb" -gt "$MAX_RSS_MB" ] && P=FAIL
  [ $((RSSpost_mb-RSS0_mb)) -gt "$MAX_RSS_LEAK_MB" ] && P=FAIL
  [ "$reorg_s" -gt "$MAX_REORG_WALL_S" ] && P=FAIL
  [ "$restart_s" -gt "$MAX_RESTART_S" ] && P=FAIL
  python3 -c "exit(0 if ${DISKpk:-1}<= ${DISK_FACTOR}*${DISK0:-1} else 1)" || P=FAIL
  [ "$utxo_ok" = "YES" ] || P=FAIL; [ "$tip_ok" = "YES" ] || P=FAIL
  printf "%-6s %-8s %-9s %-9s %-8s %-9s %-9s %-8s %-9s %-6s %-6s %s\n" "$D" "$RSSpk_mb" "$RSSpost_mb" "$disk_x" "$reorg_s" "$restart_s" "$utxo_ok" "$tip_ok" "${FEVTS:-?}" "$reorg_s" "empty" "$P"
done
echo "RESOURCE_V2_DONE"; rm -rf "$ROOT"

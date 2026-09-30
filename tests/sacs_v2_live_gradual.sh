#!/usr/bin/env bash
# SACS V2 · LIVE-GRADUAL-DEEP-FORK reproduction. Honest node keeps advancing while a
# deep fork (fork_point>=activation) arrives GRADUALLY, forcing early fork blocks below
# (active_tip - MAX_REORG_DEPTH) BEFORE the fork completes → confirm cleanup_old_forks
# erases them → try_reorganize can't assemble the heavier fork → reorg FAILS.
# devnet: activation=42, MAX_REORG_DEPTH=8. NO code change — reproduction only.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-v2/build-v2"; G="$SP/wt-v2/genesis_block.json"; FEED="$SP/wt-v2/tests/sacs_feedchain.py"
ROOT="$(mktemp -d)"; echo "ROOT=$ROOT (activation=42, MAX_REORG_DEPTH=8)"
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }; str(){ echo "$1"|grep -oE '"result":"[0-9a-f]+"'|grep -oE '[0-9a-f]{16,}'|head -1; }
h(){ num "$(rpc $1 getblockcount)"; }; tip(){ str "$(rpc $1 getbestblockhash)"; }; sw(){ ( sleep "$1" ) & wait $!; }
wal(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json">/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json">/dev/null 2>&1; }
node(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass">>"$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 900 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 2>>"$1/miner.log" 2>&1; }
wrpc(){ for i in $(seq 1 60);do curl -s --max-time 3 -o /dev/null http://127.0.0.1:$1/ 2>/dev/null&&return 0;sw 0.5;done;return 1; }
wh(){ for i in $(seq 1 4000);do [ "$(h $1)" -ge "$2" ] 2>/dev/null&&return 0;sw 1;done;return 1; }
F=44; ATTACK=20; BADV=16   # fork_point=44; attacker +20 (heavier, tip 64); honest advances +16 (tip 60, cutoff 52)
DC=$ROOT/C DA=$ROOT/ATT DB=$ROOT/HON; mkdir -p "$DC" "$DA" "$DB"; for d in "$DC" "$DA" "$DB";do printf p>"$d/pass";chmod 600 "$d/pass";done
echo "[$(date +%T)] common F=$F..."; wal "$DC"; NC=$(node "$DC" 19951 19952); wrpc 19952; mine "$DC" 19952 "$F"; wh 19952 "$F"; kill -9 $NC 2>/dev/null; sw 1
cp "$DC/chain.json" "$DA/chain.json"; cp "$DC/chain.json" "$DB/chain.json"; wal "$DA"; wal "$DB"
echo "[$(date +%T)] attacker pre-mina +$ATTACK (tip $((F+ATTACK)), más pesado)..."
NA=$(node "$DA" 19981 19982); wrpc 19982; mine "$DA" 19982 "$ATTACK"; wh 19982 "$((F+ATTACK))"; ATIP=$(tip 19982); AWH=$(h 19982)
echo "  attacker: h=$AWH tip=$(echo $ATIP|cut -c1-12)"
NB=$(node "$DB" 19971 19972); wrpc 19972
echo "[$(date +%T)] PASO 1: entregar fork parcial (hasta height $((F+6))=50) a honesto..."
python3 "$FEED" 19982 19972 "$((F+6))" >/dev/null 2>&1; sw 2
FORK_STORED=$(grep -cE 'SACS-V2\] Storing deep fork|fork.?stored|reject/fork' "$DB/node.log" 2>/dev/null)
echo "  bloques fork parciales entregados (honesto tip=$(h 19972))"
echo "[$(date +%T)] PASO 2: honesto AVANZA su cadena +$BADV (cutoff sube, cleanup corre)..."
mine "$DB" 19972 "$BADV"; wh 19972 "$((F+BADV))"
PRUNED=$(grep -cE 'Cleaned [0-9]+ stale fork' "$DB/node.log" 2>/dev/null)
echo "  honesto tip=$(h 19972) cutoff=$(( $(h 19972) - 8 )) · eventos 'Cleaned stale fork': $PRUNED"
grep -E 'Cleaned [0-9]+ stale fork' "$DB/node.log" 2>/dev/null | tail -3 | sed 's/^/     /'
echo "[$(date +%T)] PASO 3: entregar el RESTO del fork (hasta $((F+ATTACK))=64, más pesado) → ¿puede ensamblar?"
python3 "$FEED" 19982 19972 "$((F+ATTACK))" >/dev/null 2>&1; sw 3
BTIP=$(tip 19972); BH=$(h 19972)
echo "  === LOG de reorg del honesto ==="
grep -E 'Cannot build fork chain|Alternative chain has MORE|SACS-V2\] Deep reorg|Disconnecting|Rejected: depth|Cleaned [0-9]+ stale' "$DB/node.log" 2>/dev/null | tail -8 | sed 's/^/     /'
kill -9 $NA $NB 2>/dev/null; sw 1
echo ""
echo "======== RESULTADO LIVE-GRADUAL-DEEP-FORK ========"
CANNOT=$(grep -c 'Cannot build fork chain' "$DB/node.log" 2>/dev/null)
ADOPTED=$([ "$BTIP" = "$ATIP" ] && echo YES || echo NO)
echo "  attacker (más trabajo): h=$AWH tip=$(echo $ATIP|cut -c1-12)"
echo "  honesto final:          h=$BH tip=$(echo $BTIP|cut -c1-12)"
echo "  PRUNED_REQUIRED_BLOCKS      = $([ "${PRUNED:-0}" -gt 0 ] && echo YES || echo NO)"
echo "  REORG_FAILED_DUE_TO_PRUNING = $([ "${CANNOT:-0}" -gt 0 ] && echo YES || echo 'NO (o falló por otra razón)')"
echo "  LIVE_GRADUAL_DEEP_REORG     = $([ "$ADOPTED" = "YES" ] && echo 'PASS (convergió pese a poda)' || echo 'FAIL (NO adoptó la cadena de mayor trabajo → BUG confirmado)')"
echo "LIVE_GRADUAL_DONE"; rm -rf "$ROOT"

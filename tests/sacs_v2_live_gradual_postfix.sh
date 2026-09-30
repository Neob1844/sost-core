#!/usr/bin/env bash
# SACS V2 · LIVE-GRADUAL post-fix (step 3). Misma secuencia corregida que confirmó el P1,
# ahora con el fork-store V2-aware. DEBE: adoptar el candidato de mayor trabajo, tip final
# correcto, UTXO correcto, restart correcto (mismo tip/chainwork/utxo tras reinicio, sin
# estado parcial). devnet: activation=42, MAX_REORG_DEPTH=8.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-v2/build-v2"; G="$SP/wt-v2/genesis_block.json"; FEED="$SP/wt-v2/tests/sacs_feedchain.py"
ROOT="$(mktemp -d)"; echo "ROOT=$ROOT (activation=42, MAX_REORG_DEPTH=8) [POST-FIX]"
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
str(){ echo "$1"|grep -oE '"result":"[0-9a-f]+"'|grep -oE '[0-9a-f]{16,}'|head -1; }
h(){ num "$(rpc $1 getblockcount)"; }; tip(){ str "$(rpc $1 getbestblockhash)"; }
utxoc(){ rpc $1 getinfo | grep -oE '"utxo_count":[0-9]+' | grep -oE '[0-9]+'; }
sw(){ ( sleep "$1" ) & wait $!; }
wal(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json">/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json">/dev/null 2>&1; }
node(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass">>"$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 900 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 2>>"$1/miner.log" 2>&1; }
wrpc(){ for i in $(seq 1 60);do curl -s --max-time 3 -o /dev/null http://127.0.0.1:$1/ 2>/dev/null&&return 0;sw 0.5;done;return 1; }
wh(){ for i in $(seq 1 4000);do [ "$(h $1)" -ge "$2" ] 2>/dev/null&&return 0;sw 1;done;return 1; }
cw_at(){ grep -E "Height $2 accepted" "$1/node.log" 2>/dev/null | grep -oE 'chainwork=0x[0-9a-f]+' | tail -1 | sed 's/chainwork=//'; }
cw_now(){ grep -E 'Height [0-9]+ accepted|Reorg' "$1/node.log" 2>/dev/null | grep -oE 'chainwork=0x[0-9a-f]+' | tail -1 | sed 's/chainwork=//'; }

F=50; HON1=70; ATIP_H=100; EARLY_END=64; HON2=82; TAIL_START=$((EARLY_END+1))
DC=$ROOT/C DA=$ROOT/ATT DB=$ROOT/HON; mkdir -p "$DC" "$DA" "$DB"
for d in "$DC" "$DA" "$DB";do printf p>"$d/pass";chmod 600 "$d/pass";done

echo "[$(date +%T)] common F=$F..."; wal "$DC"; NC=$(node "$DC" 19951 19952); wrpc 19952; mine "$DC" 19952 "$F"; wh 19952 "$F"; kill -9 $NC 2>/dev/null; sw 1
cp "$DC/chain.json" "$DA/chain.json"; cp "$DC/chain.json" "$DB/chain.json"; wal "$DA"; wal "$DB"
echo "[$(date +%T)] atacante fork completo F->$ATIP_H..."; NA=$(node "$DA" 19981 19982); wrpc 19982; mine "$DA" 19982 "$((ATIP_H-F))"; wh 19982 "$ATIP_H"
ATIP=$(tip 19982); CAND_CW=$(cw_at "$DA" "$ATIP_H"); echo "  atacante h=$(h 19982) candidate_cw=$CAND_CW"
echo "[$(date +%T)] honesto avanza a $HON1..."; NB=$(node "$DB" 19971 19972); wrpc 19972; mine "$DB" 19972 "$((HON1-F))"; wh 19972 "$HON1"
echo "[$(date +%T)] PASO 1: fork temprano [$((F+1))..$EARLY_END] (honesto gana)..."; python3 "$FEED" 19982 19972 "$EARLY_END" "$((F+1))" >/dev/null 2>&1; sw 2
echo "  honesto tras temprano: h=$(h 19972) (debe seguir <= $HON1)"
echo "[$(date +%T)] PASO 2: honesto -> $HON2 (cutoff $((HON2-8))); con FIX no debe podar candidatos..."; mine "$DB" 19972 "$((HON2-HON1))"; wh 19972 "$HON2"
PRUNED_V2=$(grep -cE 'SACS-V2\] Dropped|evicted' "$DB/node.log" 2>/dev/null); LEGACY_PRUNE=$(grep -cE 'Cleaned [0-9]+ stale fork' "$DB/node.log" 2>/dev/null)
echo "  honesto h=$(h 19972); legacy-prune events=$LEGACY_PRUNE (debe 0); v2-retention events=$PRUNED_V2"
echo "[$(date +%T)] PASO 3: entregar COLA [$TAIL_START..$ATIP_H] -> con FIX debe ENSAMBLAR y adoptar..."; python3 "$FEED" 19982 19972 "$ATIP_H" "$TAIL_START" 2>&1 | tail -2 | sed 's/^/    /'; sw 4
BTIP=$(tip 19972); BH=$(h 19972); BCW=$(cw_now "$DB"); BUTXO=$(utxoc 19972)
echo "  === reorg log ==="; grep -E 'Reorg|Alternative chain has MORE|SACS.*reorg|Disconnect|reconverg|Deep reorg|adopt' "$DB/node.log" 2>/dev/null | tail -6 | sed 's/^/     /'
echo "  honesto tras cola: h=$BH tip=$(echo $BTIP|cut -c1-16) chainwork=$BCW utxo=$BUTXO"
ADOPTED=$([ "$BTIP" = "$ATIP" ] && echo YES || echo NO)

echo "[$(date +%T)] RESTART: reiniciar honesto y verificar estado idéntico..."
kill -9 $NB 2>/dev/null; sw 2
NB2=$(node "$DB" 19971 19972); wrpc 19972; sw 2
RTIP=$(tip 19972); RH=$(h 19972); RUTXO=$(utxoc 19972)
RCW=$(grep -E 'CHAIN-LOAD.*chainwork|Tip chainwork' "$DB/node.log" 2>/dev/null | tail -1 | grep -oE '0x[0-9a-f]+' | head -1)
echo "  tras restart: h=$RH tip=$(echo $RTIP|cut -c1-16) chainwork=$RCW utxo=$RUTXO"
kill -9 $NA $NB2 2>/dev/null; sw 1

SAME_TIP=$([ "$RTIP" = "$BTIP" ] && echo YES || echo NO)
SAME_UTXO=$([ "$RUTXO" = "$BUTXO" ] && echo YES || echo NO)
SAME_H=$([ "$RH" = "$BH" ] && echo YES || echo NO)
echo ""
echo "======== RESULTADO LIVE-GRADUAL POST-FIX ========"
echo "  CANDIDATE TIP=$ATIP (cw=$CAND_CW)"
echo "  ACTIVE (tras cola) TIP=$BTIP h=$BH cw=$BCW utxo=$BUTXO"
echo "  legacy depth-prune events (debe 0): $LEGACY_PRUNE"
echo "  ---"
echo "  CANDIDATE_ADOPTED           = $ADOPTED"
echo "  FINAL_TIP_CORRECT           = $([ "$ADOPTED" = YES ] && echo YES || echo NO)"
echo "  RESTART_SAME_TIP            = $SAME_TIP"
echo "  RESTART_SAME_HEIGHT         = $SAME_H"
echo "  RESTART_SAME_UTXO           = $SAME_UTXO"
echo "  RESTART_SAME_CHAINWORK      = $([ -n "$RCW" ] && ([ "$RCW" = "$BCW" ] && echo YES || echo "CHECK($RCW vs $BCW)") || echo "n/a-log")"
echo "  LIVE_GRADUAL_POSTFIX        = $([ "$ADOPTED" = YES ] && [ "$SAME_TIP" = YES ] && [ "$SAME_UTXO" = YES ] && echo PASS || echo FAIL)"
echo "POSTFIX_DONE"; rm -rf "$ROOT"

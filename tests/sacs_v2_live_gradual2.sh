#!/usr/bin/env bash
# SACS V2 · LIVE-GRADUAL-DEEP-FORK (CORREGIDO). Secuencia correcta:
#  F>=activation; honesto se adelanta CLARAMENTE; se entrega el fork TEMPRANO mientras
#  honesto gana (NO lo adopta); honesto avanza hasta que esos bloques cruzan cutoff
#  (height < tip-MAX_REORG_DEPTH) -> cleanup_old_forks los poda; SOLO DESPUES se entrega
#  la COLA (start>1, sin re-entregar los podados) que haría candidate_work>active_work.
#  Si la poda rompe el reorg: el padre podado => cola queda ORPHAN => no reorg => P1 confirmado.
#  CONTROL: nodo gemelo al mismo tip recibe el fork COMPLETO (re-entregando el rango podado)
#  y DEBE adoptarlo -> prueba que el candidato es valido y mas pesado; la unica causa del
#  fallo en el caso principal es la poda. devnet: activation=42, MAX_REORG_DEPTH=8. NO code change.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-v2/build-v2"; G="$SP/wt-v2/genesis_block.json"; FEED="$SP/wt-v2/tests/sacs_feedchain.py"
ROOT="$(mktemp -d)"; echo "ROOT=$ROOT (activation=42, MAX_REORG_DEPTH=8)"
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
str(){ echo "$1"|grep -oE '"result":"[0-9a-f]+"'|grep -oE '[0-9a-f]{16,}'|head -1; }
h(){ num "$(rpc $1 getblockcount)"; }; tip(){ str "$(rpc $1 getbestblockhash)"; }
sw(){ ( sleep "$1" ) & wait $!; }
wal(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json">/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json">/dev/null 2>&1; }
node(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass">>"$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 900 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 2>>"$1/miner.log" 2>&1; }
wrpc(){ for i in $(seq 1 60);do curl -s --max-time 3 -o /dev/null http://127.0.0.1:$1/ 2>/dev/null&&return 0;sw 0.5;done;return 1; }
wh(){ for i in $(seq 1 4000);do [ "$(h $1)" -ge "$2" ] 2>/dev/null&&return 0;sw 1;done;return 1; }
cw_at(){ grep -E "Height $2 accepted" "$1/node.log" 2>/dev/null | grep -oE 'chainwork=0x[0-9a-f]+' | tail -1 | sed 's/chainwork=//'; }

# ---- parametros (devnet MAX_REORG_DEPTH=8) ----
F=50               # common ancestor >= activation(42)
HON1=70            # honesto se adelanta a 70 (F+20)  -> claramente ganador
ATIP_H=100         # atacante pre-mina fork completo a 100 (mas pesado que el honesto final)
EARLY_END=64       # fork temprano entregado: [51..64]  (todos < cutoff cuando honesto llega a 82)
HON2=82            # honesto avanza a 82 -> cutoff=74 -> poda 51..64
TAIL_START=$((EARLY_END+1))   # cola entregada: [65..100]  (padre 64 podado)

DC=$ROOT/C DA=$ROOT/ATT DB=$ROOT/HON DK=$ROOT/CTRL; mkdir -p "$DC" "$DA" "$DB" "$DK"
for d in "$DC" "$DA" "$DB" "$DK";do printf p>"$d/pass";chmod 600 "$d/pass";done

echo "[$(date +%T)] common F=$F..."; wal "$DC"; NC=$(node "$DC" 19951 19952); wrpc 19952; mine "$DC" 19952 "$F"; wh 19952 "$F"; kill -9 $NC 2>/dev/null; sw 1
cp "$DC/chain.json" "$DA/chain.json"; cp "$DC/chain.json" "$DB/chain.json"; wal "$DA"; wal "$DB"

echo "[$(date +%T)] atacante pre-mina fork COMPLETO F->$ATIP_H (mas pesado)..."
NA=$(node "$DA" 19981 19982); wrpc 19982; mine "$DA" 19982 "$((ATIP_H-F))"; wh 19982 "$ATIP_H"
ATIP=$(tip 19982); AWH=$(h 19982); CAND_CW=$(cw_at "$DA" "$ATIP_H")
echo "  atacante: h=$AWH tip=$(echo $ATIP|cut -c1-16) candidate_chainwork=$CAND_CW"

echo "[$(date +%T)] honesto avanza PRIMERO a $HON1 (cadena propia, distinta del atacante)..."
NB=$(node "$DB" 19971 19972); wrpc 19972; mine "$DB" 19972 "$((HON1-F))"; wh 19972 "$HON1"
echo "  honesto: h=$(h 19972) tip=$(tip 19972|cut -c1-16)"

echo "[$(date +%T)] PASO 1: entregar fork TEMPRANO [$((F+1))..$EARLY_END] mientras honesto gana ($HON1)..."
python3 "$FEED" 19982 19972 "$EARLY_END" "$((F+1))" 2>&1 | sed 's/^/    /'
sw 2
ADOPT_EARLY=$([ "$(h 19972)" -le "$HON1" ] && echo "NO-adopta(correcto)" || echo "ADOPTA(mal)")
echo "  honesto tras fork temprano: h=$(h 19972) tip=$(tip 19972|cut -c1-16)  -> $ADOPT_EARLY"

echo "[$(date +%T)] PASO 2: honesto avanza a $HON2 -> cutoff=$((HON2-8)) -> cleanup poda [$((F+1))..$EARLY_END]..."
mine "$DB" 19972 "$((HON2-HON1))"; wh 19972 "$HON2"
PRUNED=$(grep -cE 'Cleaned [0-9]+ stale fork' "$DB/node.log" 2>/dev/null)
echo "  honesto: h=$(h 19972) cutoff=$(( $(h 19972) - 8 )) · eventos 'Cleaned stale fork': $PRUNED"
grep -E 'Cleaned [0-9]+ stale fork' "$DB/node.log" 2>/dev/null | tail -3 | sed 's/^/     /'
ACT_TIP=$(tip 19972); ACT_H=$(h 19972); ACT_CW=$(cw_at "$DB" "$ACT_H")
# hash del padre podado que la cola necesita (bloque atacante height=EARLY_END)
PARENT_NEEDED=$(python3 -c "import json,urllib.request;r=json.loads(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:19982/',data=json.dumps({'jsonrpc':'2.0','id':1,'method':'getblockhash','params':[$EARLY_END]}).encode(),headers={'Content-Type':'application/json','Authorization':'Basic dTpw'}),timeout=10).read());print(r.get('result',''))" 2>/dev/null)

echo "[$(date +%T)] PASO 3: entregar la COLA [$TAIL_START..$ATIP_H] (padre $EARLY_END podado) -> ¿ensambla?"
python3 "$FEED" 19982 19972 "$ATIP_H" "$TAIL_START" 2>&1 | sed 's/^/    /'
sw 3
BTIP=$(tip 19972); BH=$(h 19972)
echo "  === LOG reorg/orphan honesto ==="
grep -E 'ORPHAN|Cannot build fork|Alternative chain has MORE|Deep reorg|Disconnecting|Rejected: depth|Cleaned [0-9]+ stale|candidate_chainwork' "$DB/node.log" 2>/dev/null | tail -10 | sed 's/^/     /'
ORPHANED=$(grep -cE '\[ORPHAN\] Block' "$DB/node.log" 2>/dev/null)

echo "[$(date +%T)] CONTROL: nodo gemelo al mismo tip recibe el fork COMPLETO [$((F+1))..$ATIP_H]..."
cp "$DB/chain.json" "$DK/chain.json" 2>/dev/null; wal "$DK"
# parar honesto para liberar; arrancar control desde copia de la cadena honesta (tip HON2)
kill -9 $NB 2>/dev/null; sw 1
NK=$(node "$DK" 19961 19962); wrpc 19962
CTRL_H0=$(h 19962)
python3 "$FEED" 19982 19962 "$ATIP_H" "$((F+1))" 2>&1 | tail -2 | sed 's/^/    /'
sw 3
CTRL_TIP=$(tip 19962); CTRL_H=$(h 19962)
CTRL_ADOPT=$([ "$CTRL_TIP" = "$ATIP" ] && echo YES || echo NO)
echo "  control: h0=$CTRL_H0 -> h=$CTRL_H tip=$(echo $CTRL_TIP|cut -c1-16)  adoptó_candidato=$CTRL_ADOPT"

kill -9 $NA $NK 2>/dev/null; sw 1
# heights podados observados
FIRST_PRUNED=$((F+1)); LAST_PRUNED=$EARLY_END
CANNOT=$(grep -c 'Cannot build fork chain' "$DB/node.log" 2>/dev/null)
FAILED_PRUNE=$([ "${ORPHANED:-0}" -gt 0 ] || [ "${CANNOT:-0}" -gt 0 ] && echo YES || echo NO)
ADOPTED=$([ "$BTIP" = "$ATIP" ] && echo YES || echo NO)

echo ""
echo "======== RESULTADO LIVE-GRADUAL-DEEP-FORK (CORREGIDO) ========"
echo "  ACTIVE TIP        = $ACT_TIP (h=$ACT_H)"
echo "  CANDIDATE TIP     = $ATIP (h=$AWH)"
echo "  ACTIVE CHAINWORK  = $ACT_CW"
echo "  CANDIDATE CHAINWORK = $CAND_CW"
echo "  FIRST PRUNED HEIGHT = $FIRST_PRUNED"
echo "  LAST PRUNED HEIGHT  = $LAST_PRUNED"
echo "  MISSING BLOCK HASH  = $PARENT_NEEDED (atacante height=$EARLY_END, padre de la cola)"
echo "  fork temprano adoptado indebidamente? $ADOPT_EARLY"
echo "  orphans en honesto tras la cola: ${ORPHANED:-0}"
echo "  CONTROL adoptó candidato completo: $CTRL_ADOPT"
echo "  ---"
echo "  PRUNED_REQUIRED_BLOCKS      = $([ "${PRUNED:-0}" -gt 0 ] && echo YES || echo NO)"
echo "  REORG_FAILED_DUE_TO_PRUNING = $FAILED_PRUNE"
echo "  LIVE_GRADUAL_DEEP_REORG     = $([ "$ADOPTED" = "YES" ] && echo 'PASS (convergió a mayor trabajo)' || echo 'FAIL (NO adoptó la cadena de mayor trabajo)')"
echo "LIVE_GRADUAL_DONE"; rm -rf "$ROOT"

#!/usr/bin/env bash
# SACS V2 · resource PERFIL B (CARGADO). Bloques con transacciones reales (coinbase madura a
# los 5; se envían auto-pagos para llenar mempool) => raw_json/bloque mayor => presión de bytes
# en el fork-store durante un reorg profundo cargado. Profundidad representativa=120 (el
# byte-bound puro se prueba aparte en forkstore_stress con bound reducido). Umbrales
# pre-declarados; UTXO root A==B exacto; restart estable. devnet: activation=42, MRD=8.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-v2/build-v2"; G="$SP/wt-v2/genesis_block.json"; FEED="$SP/wt-v2/tests/sacs_feedchain.py"
MAX_RSS_MB=3072; MAX_REORG_WALL_S=180; MAX_RESTART_S=60; DEPTH="${1:-120}"; TXPB="${2:-15}"
echo "PRE-DECLARED: peak_RSS<${MAX_RSS_MB}MB · reorg_wall<${MAX_REORG_WALL_S}s · restart<${MAX_RESTART_S}s · UTXO_root A==B exacto · tip==candidate · restart-stable · depth=$DEPTH txs/bloque~$TXPB"
ROOT="$(mktemp -d)"; echo "ROOT=$ROOT [PERFIL-B CARGADO]"
rpc(){ curl -s --max-time 20 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }; str(){ echo "$1"|grep -oE '"result":"[0-9a-f]+"'|grep -oE '[0-9a-f]{16,}'|head -1; }
h(){ num "$(rpc $1 getblockcount)"; }; tip(){ str "$(rpc $1 getbestblockhash)"; }; sw(){ ( sleep "$1" ) & wait $!; }
addr(){ "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1; }
wal(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json">/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json">/dev/null 2>&1; }
node(){ nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass">>"$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 900 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 2>>"$1/miner.log" 2>&1; }
wrpc(){ for i in $(seq 1 60);do curl -s --max-time 3 -o /dev/null http://127.0.0.1:$1/ 2>/dev/null&&return 0;sw 0.5;done;return 1; }
wh(){ for i in $(seq 1 40000);do [ "$(h $1)" -ge "$2" ] 2>/dev/null&&return 0;sw 1;done;return 1; }
rss(){ awk '/VmRSS/{print $2}' /proc/$1/status 2>/dev/null; }; hwm(){ awk '/VmHWM/{print $2}' /proc/$1/status 2>/dev/null; }
uroot(){ "$BIN/sost-node" --profile dev --dry-run-replay --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" 2>/dev/null|grep -oE 'utxo_set_root: [0-9a-f]+'|grep -oE '[0-9a-f]{16,}'; }
# minar N bloques CARGADOS: por lote, enviar $TXPB auto-pagos y minar 1
mine_loaded(){ local D=$1 RP=$2 CNT=$3 A; A=$(addr "$D"); for b in $(seq 1 $CNT); do for t in $(seq 1 $TXPB); do "$BIN/sost-cli" send "$A" 1 --wallet "$D/w.json" --rpc 127.0.0.1:$RP --rpc-user u --rpc-pass-file "$D/pass" >/dev/null 2>&1; done; mine "$D" "$RP" 1; done; }

F=20
DC=$ROOT/C; mkdir -p "$DC"; printf p>"$DC/pass"; chmod 600 "$DC/pass"; wal "$DC"
echo "[$(date +%T)] common F=$F (fund; coinbase madura a 5)..."; NC=$(node "$DC" 19951 19952); wrpc 19952; mine "$DC" 19952 "$F"; wh 19952 "$F"; kill -9 $NC 2>/dev/null; sw 1
DA=$ROOT/A DB=$ROOT/B; mkdir -p "$DA" "$DB"; for d in "$DA" "$DB";do printf p>"$d/pass";chmod 600 "$d/pass";done
cp "$DC/chain.json" "$DA/chain.json"; cp "$DC/chain.json" "$DB/chain.json"; cp "$DC/w.json" "$DA/w.json"; cp "$DC/w.json" "$DB/w.json"
echo "[$(date +%T)] honesto B: +$DEPTH bloques CARGADOS (~$TXPB tx/bloque)..."; NB=$(node "$DB" 19941 19942); wrpc 19942
( for i in $(seq 1 2000); do hwm $NB >> "$DB/rss.samp"; sw 0.5; done ) & SAMP=$!
mine_loaded "$DB" 19942 "$DEPTH"; wh 19942 "$((F+DEPTH))"
echo "[$(date +%T)] atacante A: +$((DEPTH+5)) bloques CARGADOS (más pesado)..."; NA=$(node "$DA" 19931 19932); wrpc 19932
mine_loaded "$DA" 19932 "$((DEPTH+5))"; wh 19932 "$((F+DEPTH+5))"
ATIP=$(tip 19932); UROOT_A=$(uroot "$DA")
echo "[$(date +%T)] REORG cargado: entregar cadena A completa a B..."; TF0=$(date +%s)
python3 "$FEED" 19932 19942 "$((F+DEPTH+5))" "$((F+1))" >/dev/null 2>&1; sw 4; TF1=$(date +%s); kill $SAMP 2>/dev/null
BTIP=$(tip 19942); RSSpk=$(sort -n "$DB/rss.samp" 2>/dev/null|tail -1); RSSpk_mb=$((${RSSpk:-0}/1024)); REORG_S=$((TF1-TF0))
echo "[$(date +%T)] restart B..."; kill -9 $NB 2>/dev/null; sw 2; TR0=$(date +%s); NB=$(node "$DB" 19941 19942); wrpc 19942; TR1=$(date +%s); RTIP=$(tip 19942); UROOT_B=$(uroot "$DB")
kill -9 $NA $NB 2>/dev/null; sw 1
ADOPT=$([ "$BTIP" = "$ATIP" ] && echo YES || echo NO); SAME=$([ "$RTIP" = "$BTIP" ] && echo YES || echo NO)
UOK=$([ -n "$UROOT_A" ] && [ "$UROOT_A" = "$UROOT_B" ] && echo YES || echo "NO($UROOT_A vs $UROOT_B)")
RSS_OK=$([ "$RSSpk_mb" -lt "$MAX_RSS_MB" ] && echo YES || echo NO); RW_OK=$([ "$REORG_S" -lt "$MAX_REORG_WALL_S" ] && echo YES || echo NO); RS_OK=$([ "$((TR1-TR0))" -lt "$MAX_RESTART_S" ] && echo YES || echo NO)
echo ""
echo "======== RESULTADO PERFIL-B CARGADO (depth=$DEPTH) ========"
echo "  peak_RSS=${RSSpk_mb}MB (<$MAX_RSS_MB? $RSS_OK) · reorg_wall=${REORG_S}s (<$MAX_REORG_WALL_S? $RW_OK) · restart=$((TR1-TR0))s (<$MAX_RESTART_S? $RS_OK)"
echo "  CANDIDATE_ADOPTED=$ADOPT · RESTART_SAME_TIP=$SAME · UTXO_ROOT_A==B=$UOK"
echo "  LOADED_PROFILE = $([ "$ADOPT" = YES ] && [ "$SAME" = YES ] && [ "$UOK" = YES ] && [ "$RSS_OK" = YES ] && [ "$RW_OK" = YES ] && [ "$RS_OK" = YES ] && echo PASS || echo FAIL)"
echo "LOADED_DONE"; rm -rf "$ROOT"

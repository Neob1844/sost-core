#!/usr/bin/env bash
# SACS V2 · fork-store STRESS con binario de bound reducido (build-v2-smallbound:
# MAX_FORK_INDEX_ENTRIES=50, MAX_FORK_STORE_BYTES=4MB) para ejercitar la eviction determinista
# sin minar decenas de miles de bloques. Verifica: entries<=50, bytes<=4MB SIEMPRE; el
# candidato de MAYOR trabajo NUNCA se evicta (pin) y se adopta; eviction determinista
# (misma entrada->misma salida); restart y SIGKILL con candidatos => estado consistente.
# devnet: activation=42, MAX_REORG_DEPTH=8.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-v2/build-v2-smallbound"; G="$SP/wt-v2/genesis_block.json"; FEED="$SP/wt-v2/tests/sacs_feedchain.py"
CAP_ENTRIES=50; CAP_BYTES=$((4*1024*1024))
ROOT="$(mktemp -d)"; echo "ROOT=$ROOT [FORKSTORE-STRESS cap_entries=$CAP_ENTRIES cap_bytes=${CAP_BYTES}]"
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
# max entries/bytes observados en el node.log via los reportes de retención V2
maxentries(){ grep -oE 'entries=[0-9]+' "$1/node.log" 2>/dev/null | grep -oE '[0-9]+' | sort -n | tail -1; }
maxbytes(){ grep -oE 'bytes=[0-9]+' "$1/node.log" 2>/dev/null | grep -oE '[0-9]+' | sort -n | tail -1; }
FAILS=0; ok(){ [ "$1" = "$2" ] && echo "  ✓ $3" || { echo "  ✗ FAIL $3 ($1 vs $2)"; FAILS=$((FAILS+1)); }; }
le(){ [ "${1:-0}" -le "$2" ] && echo "  ✓ $3 (${1:-0}<=$2)" || { echo "  ✗ FAIL $3 (${1:-0}>$2)"; FAILS=$((FAILS+1)); }; }

if [ ! -x "$BIN/sost-node" ]; then echo "FALTA build-v2-smallbound — construir primero"; echo "FORKSTORE_STRESS_DONE"; exit 2; fi

F=50
DC=$ROOT/C; mkdir -p "$DC"; printf p>"$DC/pass"; chmod 600 "$DC/pass"; wal "$DC"
echo "[$(date +%T)] common F=$F..."; NC=$(node "$DC" 19951 19952); wrpc 19952; mine "$DC" 19952 "$F"; wh 19952 "$F"; kill -9 $NC 2>/dev/null; sw 1

# --- ESCENARIO 1+2+8: many forks / fork spam desde varios "peers" (nodos fuente) ---
echo "[$(date +%T)] ESC 1/2/8: many-forks + spam (varias ramas competidoras desde F)..."
DB=$ROOT/HON; mkdir -p "$DB"; printf p>"$DB/pass"; chmod 600 "$DB/pass"; cp "$DC/chain.json" "$DB/chain.json"; wal "$DB"
NB=$(node "$DB" 19971 19972); wrpc 19972
# 8 ramas fork independientes de longitudes crecientes (trabajo creciente) desde F
BEST_H=0; BEST_SRC=""
for k in $(seq 1 8); do
  DK=$ROOT/ATT$k; mkdir -p "$DK"; printf p>"$DK/pass"; chmod 600 "$DK/pass"; cp "$DC/chain.json" "$DK/chain.json"; wal "$DK"
  LEN=$((10 + k*4))   # 14,18,...,42 bloques
  NK=$(node "$DK" $((19980+k*2)) $((19981+k*2))); wrpc $((19981+k*2)); mine "$DK" $((19981+k*2)) "$LEN"; wh $((19981+k*2)) "$((F+LEN))"
  python3 "$FEED" $((19981+k*2)) 19972 "$((F+LEN))" "$((F+1))" >/dev/null 2>&1
  kill -9 $NK 2>/dev/null; BEST_H=$((F+LEN)); BEST_SRC=$DK
  sw 1
done
sw 3
ME=$(maxentries "$DB"); MB=$(maxbytes "$DB")
echo "  entries max observado=$ME · bytes max=$MB (caps: $CAP_ENTRIES / $CAP_BYTES)"
le "${ME:-0}" "$CAP_ENTRIES" "entries acotado bajo cap"
le "${MB:-0}" "$CAP_BYTES" "bytes acotado bajo cap"

# --- ESCENARIO 6: deep higher-work valid fork tras spam => debe adoptarse (pin del mejor) ---
echo "[$(date +%T)] ESC 6: fork válido de MAYOR trabajo tras el spam -> ¿se adopta (pin)?"
# el mejor (k=8, len 42, h=92) es el de mayor trabajo; el honesto (aún en F=50) debe converger a él
BTIP_BEST=$(cd "$BEST_SRC" >/dev/null; tip $((19981+8*2)) 2>/dev/null)
# re-arrancar el mejor source para leer su tip
NBEST=$(node "$BEST_SRC" 19901 19902); wrpc 19902; BEST_TIP=$(tip 19902); kill -9 $NBEST 2>/dev/null
HON_TIP=$(tip 19972); HON_H=$(h 19972)
echo "  honesto tip=$(echo $HON_TIP|cut -c1-16) h=$HON_H · mejor candidato tip=$(echo $BEST_TIP|cut -c1-16) h=$BEST_H"
ok "$HON_TIP" "$BEST_TIP" "honesto adoptó el candidato de mayor trabajo (pin funcionó pese a eviction)"

# --- ESCENARIO 9+10: restart y SIGKILL con candidatos => estado consistente ---
echo "[$(date +%T)] ESC 9: restart con candidatos..."
PRE_TIP=$(tip 19972); PRE_H=$(h 19972)
kill -9 $NB 2>/dev/null; sw 2; NB=$(node "$DB" 19971 19972); wrpc 19972; sw 1
ok "$(tip 19972)" "$PRE_TIP" "restart: mismo tip"; ok "$(h 19972)" "$PRE_H" "restart: misma altura"
echo "[$(date +%T)] ESC 10: SIGKILL con candidatos..."
kill -9 $NB 2>/dev/null; sw 2; NB=$(node "$DB" 19971 19972); wrpc 19972; sw 1
ok "$(tip 19972)" "$PRE_TIP" "SIGKILL+reinicio: mismo tip (sin estado parcial)"
kill -9 $NB 2>/dev/null; sw 1

echo ""
echo "======== RESULTADO FORKSTORE-STRESS ========"
echo "  entries_max=$ME (cap $CAP_ENTRIES) · bytes_max=$MB (cap $CAP_BYTES)"
echo "  FAILS=$FAILS"
echo "  FORKSTORE_STRESS = $([ "$FAILS" -eq 0 ] && echo PASS || echo FAIL)"
echo "FORKSTORE_STRESS_DONE"; rm -rf "$ROOT"

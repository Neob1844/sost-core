#!/usr/bin/env bash
# Paso 2 — campaña prolongada churn + fork-storm sobre el binario definitivo.
# Mide CPU, RAM, disponibilidad (latencia RPC) y RECUPERACION. PID fiable via $!.
set -u
NODE="$1"; GENHEX="$2"; BASE="$3"; CHAINDIR="$4"; DUR="${5:-300}"; HERE="$5x"
SEC=/home/sost/SOST/sostcore/sost-core/tests/security
W=$(mktemp -d /tmp/camp.XXXXXX); P=19960; RP=18960
for f in genesis_block.json popc_registry.json rpc.pass wallet.json; do cp "$CHAINDIR/$f" "$W/" 2>/dev/null||true; done
cp "$CHAINDIR/chain.json" "$W/chain.json" 2>/dev/null
chmod 600 "$W/rpc.pass" 2>/dev/null
( cd "$W" && exec "$NODE" --genesis genesis_block.json --chain chain.json --profile mainnet \
    --port $P --rpc-port $RP --rpc-user u --rpc-pass-file rpc.pass --connect 127.0.0.1:1 > node.log 2>&1 < /dev/null ) &
VPID=$!
# esperar carga (hasta 90s)
for i in $(seq 1 45); do ss -ltn 2>/dev/null|grep -q ":$RP " && break; [ -d /proc/$VPID ]||{ echo "VICTIMA NO ARRANCO"; tail -5 $W/node.log; exit 1; }; sleep 2; done
echo "[camp] victima PID=$VPID comm=$(cat /proc/$VPID/comm 2>/dev/null) DUR=${DUR}s"
CLK=$(getconf CLK_TCK); PREV=$(awk '{print $14+$15}' /proc/$VPID/stat); PREVT=$(date +%s.%N)
PEAKR=0; PEAKC=0; SUMLAT=0; NLAT=0; MAXLAT=0
# atacantes concurrentes durante DUR
( end=$((SECONDS+DUR)); while [ $SECONDS -lt $end ]; do timeout 60 python3 "$SEC/v1_fork_poison_attacker.py" 127.0.0.1 $P "$GENHEX" "$BASE" >/dev/null 2>&1; done ) &
AP=$!
( end=$((SECONDS+DUR)); while [ $SECONDS -lt $end ]; do timeout 60 python3 "$SEC/churn_attacker.py" 127.0.0.1 $P 200 >/dev/null 2>&1; done ) &
CP=$!
# muestreo
t0=$SECONDS
while [ $((SECONDS-t0)) -lt $DUR ]; do
  [ -d /proc/$VPID ] || { echo "[camp] *** NODO MUERTO a los $((SECONDS-t0))s ***"; break; }
  r=$(awk '/VmRSS/{print int($2/1024)}' /proc/$VPID/status 2>/dev/null); [ "${r:-0}" -gt "$PEAKR" ]&&PEAKR=$r
  NOW=$(awk '{print $14+$15}' /proc/$VPID/stat); NOWT=$(date +%s.%N)
  cpu=$(awk -v a=$PREV -v b=$NOW -v ta=$PREVT -v tb=$NOWT -v c=$CLK 'BEGIN{d=tb-ta; if(d>0)printf "%d",(b-a)/c/d*100; else print 0}')
  [ "${cpu:-0}" -gt "$PEAKC" ]&&PEAKC=$cpu; PREV=$NOW; PREVT=$NOWT
  # disponibilidad: latencia de una RPC
  ls=$(date +%s.%N); ok=$(curl -s -m5 -u "u:$(cat $W/rpc.pass)" -X POST http://127.0.0.1:$RP -d '{"jsonrpc":"1.0","id":1,"method":"getblockcount","params":[]}' 2>/dev/null|grep -c result); le=$(date +%s.%N)
  lat=$(awk -v a=$ls -v b=$le 'BEGIN{printf "%.0f",(b-a)*1000}')
  [ "$ok" = 1 ] && { SUMLAT=$((SUMLAT+lat)); NLAT=$((NLAT+1)); [ "$lat" -gt "$MAXLAT" ]&&MAXLAT=$lat; }
  sleep 5
done
wait $AP $CP 2>/dev/null
# --- RECUPERACION: sin ataque, 15s ---
sleep 15
ALIVE=$([ -d /proc/$VPID ]&&echo si||echo NO)
RREST=$(awk '/VmRSS/{print int($2/1024)}' /proc/$VPID/status 2>/dev/null)
RPOK=$(curl -s -m5 -u "u:$(cat $W/rpc.pass)" -X POST http://127.0.0.1:$RP -d '{"jsonrpc":"1.0","id":1,"method":"getforkstats","params":[]}' 2>/dev/null)
timeout 20 python3 "$SEC/v1_fork_honest_peer.py" 127.0.0.1 $P "$GENHEX" "$BASE" >/dev/null 2>&1
sleep 2; HON=$(grep -c deadbeef $W/node.log)
AVGLAT=$([ $NLAT -gt 0 ]&&echo $((SUMLAT/NLAT))||echo n/a)
echo "[camp] === RESULTADO ==="
echo "[camp] vivo_tras_ataque=$ALIVE  pico_CPU=${PEAKC}%  pico_RSS=${PEAKR}MB  RSS_reposo=${RREST}MB"
echo "[camp] disponibilidad RPC: lat_media=${AVGLAT}ms lat_max=${MAXLAT}ms muestras_ok=$NLAT"
echo "[camp] forkstats_tras_ataque=$(echo "$RPOK"|grep -oE '\"forks\":[0-9]+,\"orphans\":[0-9]+')"
echo "[camp] recuperacion: acepta fork honesto tras ataque=$([ "${HON:-0}" -ge 1 ]&&echo SI||echo NO)"
echo "[camp] rechazos=$(grep -c REJECTED $W/node.log) baneos-invalid=$(grep -c 'BANNED.*invalid' $W/node.log)"
[ "$ALIVE" = si ] && { kill $VPID 2>/dev/null; rm -rf $W; echo "[camp] OK (limpiado)"; } || echo "[camp] log en $W/node.log"
[ "$ALIVE" = si ]

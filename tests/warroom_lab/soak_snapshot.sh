#!/usr/bin/env bash
L=/home/sost/SOST/sostcore/lab/soak_run
rpc(){ curl -s --max-time 5 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":[],\"id\":1}" "http://127.0.0.1:$1/" 2>/dev/null; }
declare -A RP=( [OLD1]=20602 [NEW1]=20604 [NEW2]=20606 [OLD2]=20608 )
CK=$(getconf CLK_TCK)
printf "%-6s %7s %6s %6s %5s %4s %5s %8s %8s %8s %s\n" NODE RSS_KB CPU_s FD PEERS CAND PKTXT RECONN DISC ERR TIP
for n in OLD1 NEW1 NEW2 OLD2; do
  rp=${RP[$n]}; d=$L/$n
  pid=$(pgrep -f "rpc-port $rp" | head -1)
  rss=$(awk '/VmRSS/{print $2}' /proc/$pid/status 2>/dev/null)
  fd=$(ls /proc/$pid/fd 2>/dev/null|wc -l)
  # CPU seconds = (utime+stime)/CLK_TCK
  read -r _ _ _ _ _ _ _ _ _ _ _ _ _ ut st _ < <(cat /proc/$pid/stat 2>/dev/null) 2>/dev/null
  cpu=$(awk "BEGIN{printf \"%.1f\",(${ut:-0}+${st:-0})/$CK}")
  peers=$(rpc $rp getpeerinfo | grep -oE '"addr"' | wc -l)
  cand=$(grep -c "received ADDR" $d/node.log 2>/dev/null)
  pk=$([[ -f $d/peers.txt ]] && wc -l <$d/peers.txt || echo 0)
  reconn=$(grep -c "attempting reconnect" $d/node.log 2>/dev/null)
  disc=$(grep -c "Peer disconnected" $d/node.log 2>/dev/null)
  err=$(grep -ciE "error|crash|abort|bad_alloc|segfault|terminate" $d/node.log 2>/dev/null)
  h=$(rpc $rp getblockcount|grep -oE '[0-9]+'|head -1)
  tip=$(rpc $rp getbestblockhash|grep -oE '[a-f0-9]{16,}'|head -1|cut -c1-12)
  printf "%-6s %7s %6s %6s %5s %4s %5s %8s %8s %8s %s\n" "$n" "${rss:-?}" "$cpu" "$fd" "$peers" "${cand:-0}" "$pk" "${reconn:-0}" "${disc:-0}" "${err:-0}" "${tip:-?} (h=${h:-?})"
done
echo "rows_logged=$(wc -l <$L/metrics.csv) elapsed=$(( ($(date +%s) - $(stat -c %Y $L/status.txt)) / 60 ))min"

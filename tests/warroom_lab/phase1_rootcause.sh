#!/usr/bin/env bash
set -uo pipefail
OLD=/home/sost/SOST/sostcore/lab-old-v30000/build-devnet
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
N=3
rpc(){ curl -s --max-time 5 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":[],\"id\":1}" "http://127.0.0.1:$1/" 2>/dev/null; }
h(){ rpc "$1" getblockcount|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
tip(){ rpc "$1" getbestblockhash|grep -oE '[0-9a-f]{16}'|head -1; }
np(){ rpc "$1" getpeerinfo|grep -oE '"addr"'|wc -l; }
run_one(){
  local MB=$1 PB=$2 L; L=$(mktemp -d /tmp/p1rc.XXXXXX); local P=()
  "$MB/sost-node" --profile dev --genesis "$GEN" --chain "$L/m.json" --port 20421 --rpc-port 20422 --rpc-noauth --p2p-bind 127.0.0.11 --connect 127.0.0.1:1 >"$L/M.log" 2>&1 & P+=($!)
  for _ in $(seq 1 15); do [[ -n "$(h 20422)" ]] && break; sleep 1; done
  "$PB/sost-node" --profile dev --genesis "$GEN" --chain "$L/p.json" --port 20423 --rpc-port 20424 --rpc-noauth --p2p-bind 127.0.0.12 --connect 127.0.0.11:20421 >"$L/P.log" 2>&1 & P+=($!)
  sleep 3
  local base=$(h 20422); base=${base:-0}
  local MA=$("$MB/sost-cli" --wallet "$L/w.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
  "$MB/sost-miner" --profile dev --genesis "$GEN" --rpc 127.0.0.1:20422 --address "$MA" --wallet "$L/w.json" --mining-key-label default --blocks 50 --threads 2 --realtime >"$L/miner.log" 2>&1 & local MP=$!; P+=($MP)
  local ok_mine=0; for _ in $(seq 1 110); do local cur=$(h 20422); [[ -n "$cur" && "$cur" -ge $((base+N)) ]] && { ok_mine=1; break; }; sleep 2; done
  kill $MP 2>/dev/null; sleep 2
  local MH=$(h 20422) MT=$(tip 20422)
  for _ in $(seq 1 30); do [[ -n "$(tip 20424)" && "$(tip 20424)" == "$MT" && "$(h 20424)" == "$MH" ]] && break; sleep 2; done
  local PH=$(h 20424) PT=$(tip 20424) MPE=$(np 20422) PPE=$(np 20424)
  local subm=$(grep -c "submitted to node OK" "$L/miner.log" 2>/dev/null)
  local mis=$(cat "$L/M.log" "$L/P.log" 2>/dev/null | grep -ciE "unknown command|misbehav|ban score|genesis mismatch"); mis=${mis:-0}
  G_M="M h=$MH tip=${MT:0:12} peers=$MPE"; G_P="P h=$PH tip=${PT:0:12} peers=$PPE"
  G_MINE="submitted=$subm accepted=$((MH-base))"; G_MIS="$mis"
  local c_mined=$([[ "$((MH-base))" -ge $N ]] && echo 1 || echo 0)
  local c_tip=$([[ -n "$MT" && "$MT" == "$PT" ]] && echo 1 || echo 0)
  local c_ht=$([[ "$MH" == "$PH" && -n "$MH" ]] && echo 1 || echo 0)
  local c_split=$([[ "$MPE" -ge 1 && "$PPE" -ge 1 ]] && echo 1 || echo 0)
  local c_mis=$([[ "$mis" -eq 0 ]] && echo 1 || echo 0)
  G_CHECKS="mined=$c_mined sameTip=$c_tip sameHeight=$c_ht noSplit=$c_split zeroMisbehav=$c_mis"
  for p in "${P[@]}"; do kill $p 2>/dev/null; done; rm -rf "$L"
  [[ "$c_mined" -eq 1 && "$c_tip" -eq 1 && "$c_ht" -eq 1 && "$c_split" -eq 1 && "$c_mis" -eq 1 ]]
}
matrix(){ local name=$1 MB=$2 PB=$3 reps=$4 pass=0 st
  for i in $(seq 1 $reps); do
    if run_one "$MB" "$PB"; then pass=$((pass+1)); st=PASS; else st=FAIL; fi
    { [[ $i -eq 1 ]] || [[ "$st" == FAIL ]]; } && echo "  [$name run$i] $G_M | $G_P | $G_MINE | misbehav=$G_MIS | $G_CHECKS -> $st"
  done
  echo "$name: $pass/$reps PASS"
}
echo "=== PHASE1 ROOT-CAUSE MATRIX (event-based, N=$N accepted blocks) ==="
matrix "A_old-old"            "$OLD" "$OLD" 10
matrix "B_oldMiner-newPeer"   "$OLD" "$NEW" 10
matrix "C_new-new"            "$NEW" "$NEW" 10
matrix "B2_newMiner-oldPeer"  "$NEW" "$OLD" 5
echo "=== DONE ==="

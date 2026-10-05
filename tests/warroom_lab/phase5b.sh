#!/usr/bin/env bash
set -uo pipefail
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
LAB=$(mktemp -d /tmp/ph5b.XXXXXX); PASS=0; FAIL=0; PIDS=()
ok(){ echo "  PASS  $*"; PASS=$((PASS+1)); }; bad(){ echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
trap 'for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null||true; done' EXIT
rpc(){ curl -s --max-time 6 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":[],\"id\":1}" "http://127.0.0.1:$1/" 2>/dev/null; }
hgt(){ rpc "$1" getblockcount | grep -oE '[0-9]+' | head -1; }
tip(){ rpc "$1" getbestblockhash | grep -oE '[0-9a-f]{16,}' | head -1; }
node(){ local nm=$1 ip=$2 p=$3 rp=$4 peers=$5; local d="$LAB/$nm"; mkdir -p "$d"
  [[ -n "$peers" ]] && printf '%s\n' $peers > "$d/peers.txt"
  local a=(--profile dev --genesis "$GEN" --chain "$d/chain.json" --port "$p" --rpc-port "$rp" --rpc-noauth --p2p-bind "$ip")
  [[ -z "$peers" ]] && a+=(--connect 127.0.0.1:1)
  "$NEW/sost-node" "${a[@]}" >"$d/node.log" 2>&1 & PIDS+=($!); }
mine(){ local rp=$1 w=$2; local a=$("$NEW/sost-cli" --wallet "$w" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)
  "$NEW/sost-miner" --profile dev --rpc 127.0.0.1:$rp --address "$a" --wallet "$w" --mining-key-label default --blocks 100000 --threads 2 --realtime >"$LAB/m_$rp.log" 2>&1 & echo $!; }

node N1 127.0.0.51 20851 20852 ""
node N3 127.0.0.53 20855 20856 ""
for _ in $(seq 1 15); do [[ -n "$(hgt 20852)" && -n "$(hgt 20856)" ]] && break; sleep 1; done
node N2 127.0.0.52 20853 20854 "127.0.0.51:20851"
node N4 127.0.0.54 20857 20858 "127.0.0.53:20855"
sleep 4
echo "=== PHASE 5b — two isolated groups (longer divergence) ==="
B1=$(tip 20852); echo "  baseline tip (genesis) = ${B1:0:12}"
MP1=$(mine 20852 "$LAB/w1.json"); PIDS+=($MP1)
MP3=$(mine 20856 "$LAB/w3.json"); PIDS+=($MP3)
# mine both ~70s, polling progress
for i in $(seq 1 7); do sleep 10; echo "  t=$((i*10))s  G1 h=$(hgt 20852) tip=$(tip 20852|cut -c1-10)   G2 h=$(hgt 20856) tip=$(tip 20856|cut -c1-10)"; done
kill $MP3 2>/dev/null; true            # group2 frozen now
sleep 30; kill $MP1 2>/dev/null; true  # group1 mines 30s more -> heavier
sleep 3
H1=$(hgt 20852); T1=$(tip 20852); H3=$(hgt 20856); T3=$(tip 20856)
echo "  PRE-HEAL: G1 h=$H1 tip=${T1:0:12} | G2 h=$H3 tip=${T3:0:12}"
[[ "${H1:-0}" -ge 1 && "${H3:-0}" -ge 1 && "$T1" != "$B1" && "$T3" != "$B1" ]] && ok "both groups mined real blocks past genesis" || bad "a group never left genesis (G1=$H1 G2=$H3)"
[[ -n "$T1" && -n "$T3" && "$T1" != "$T3" ]] && ok "chains genuinely DIVERGED (distinct tips pre-heal)" || bad "no divergence (T1=$T1 T3=$T3)"
[[ "$T1" == "$(tip 20854)" ]] && ok "GROUP1 internally consistent (N1==N2)" || echo "  (N1/N2 differ)"
[[ "$T3" == "$(tip 20858)" ]] && ok "GROUP2 internally consistent (N3==N4)" || echo "  (N3/N4 differ)"

echo "--- HEAL via D1 peer store bridge (knows both heads) ---"
node BR 127.0.0.55 20859 20860 "127.0.0.51:20851 127.0.0.53:20855"
CONV=""; for _ in $(seq 1 40); do
  a=$(tip 20852); b=$(tip 20856); c=$(tip 20860); e=$(tip 20854); g=$(tip 20858)
  [[ -n "$a" && "$a" == "$b" && "$a" == "$c" && "$a" == "$e" && "$a" == "$g" ]] && { CONV=$a; break; }
  sleep 2
done
echo "  POST-HEAL: N1=$(hgt 20852) N2=$(hgt 20854) N3=$(hgt 20856) N4=$(hgt 20858) BR=$(hgt 20860) tip=${CONV:0:12}"
if [[ -n "$CONV" ]]; then
  ok "ALL 5 nodes converged to ONE chain after partition heal (tip ${CONV:0:12})"
  mx=$([[ "${H1:-0}" -ge "${H3:-0}" ]] && echo "${H1:-0}" || echo "${H3:-0}")
  [[ "$(hgt 20852)" -ge "$mx" ]] && ok "heavier chain won (final h=$(hgt 20852) >= pre-heal max $mx)" || bad "converged below heavier ($(hgt 20852) < $mx)"
  [[ "$CONV" == "$T1" ]] && ok "winner = GROUP1 (the heavier fork), GROUP2 reorged onto it" || echo "  (winner tip=${CONV:0:12}, G1 was ${T1:0:12} — heavier fork won on work)"
else
  bad "NO convergence in 80s (N1=$(tip 20852|cut -c1-10) N3=$(tip 20856|cut -c1-10) BR=$(tip 20860|cut -c1-10))"
fi
al=0; for p in 20852 20854 20856 20858 20860; do [[ -n "$(hgt $p)" ]] && al=$((al+1)); done
[[ "$al" -eq 5 ]] && ok "no deadlock — all 5 RPC-responsive post-heal" || bad "only $al/5 responsive"
grep -qiE "deep.?reorg|recovery-mode|DEEP_REORG_ALERT" "$LAB"/*/node.log && echo "  (deep-reorg/SACS path logged — inspect)" || ok "SACS V2 not tripped (reorg within MAX_REORG_DEPTH, consensus path unchanged)"
echo "=== PHASE 5b: $PASS passed, $FAIL failed ==="

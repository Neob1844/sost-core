#!/usr/bin/env bash
# =============================================================================
# run_v17_devnet_multisig.sh — native multisig end to end on DEVNET_FAST with the
# REAL node + REAL miner, crossing the devnet activation (V17_HEIGHT = 60).
#
#   Phase 1  activation boundary: wallet refuses to build before 60; a v2 funding
#            tx sent for next block 59 is REJECTED, the same tx sent for next block
#            60 is ACCEPTED and mined in block 60; node restart just BEFORE activation.
#   Phase 2  fund a 2-of-3 and spend it (buildtx -> 2 x signtx -> combinetx ->
#            verifytx -> sendrawtransaction); same for a 3-of-5; node restart just
#            AFTER activation (UTXOs persist); rotation 3-of-5 -> 2-of-3; node-level
#            adversarial: corrupted multisig signature, NODE_BIND outer version 2.
#   Phase 3  reorg across activation, both directions, with a multisig tx:
#            P (tip 59, pre-activation) reorgs onto Q (58..62, multisig tx in V17
#            blocks); then P reorgs back across activation onto R (58..65, no
#            multisig tx): the multisig output disappears, the tx returns to the
#            mempool and is mined again.
#
# Usage: tests/run_v17_devnet_multisig.sh <devnet build dir> [work dir]
# Ports: 30200-30239 only. Every process started here is stopped by exact PID
# after checking its cmdline carries this run's work dir. One miner at a time,
# 2 threads, nice 19.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
B="${1:?devnet build dir}"
WORK="${2:-$(mktemp -d "${TMPDIR:-/tmp}/v17ms.XXXXXX")}"; mkdir -p "$WORK"
NODE="$B/sost-node"; MINER="$B/sost-miner"; CLI="$B/sost-cli"
N_P2P=30200; N_RPC=30201; P_P2P=30210; P_RPC=30211; Q_P2P=30220; Q_RPC=30221; R_P2P=30230; R_RPC=30231
MH=60; PASS=0; FAIL=0
log(){ printf '[v17ms] %s\n' "$*"; }
ok(){  PASS=$((PASS+1)); printf '[v17ms] PASS  %s\n' "$*"; }
bad(){ FAIL=$((FAIL+1)); printf '[v17ms] FAIL  %s\n' "$*"; }
declare -A NPID=()
MPID=""
own_kill(){ local pid="$1"; [[ -z "$pid" ]] && return; if [[ -r /proc/$pid/cmdline ]] && tr '\0' ' ' </proc/$pid/cmdline | grep -qF -- "$WORK"; then
  kill "$pid" 2>/dev/null; for _ in $(seq 1 40); do [[ -d /proc/$pid ]] || break; sleep 0.25; done; fi; }
cleanup(){ own_kill "$MPID"; MPID=""; for k in "${!NPID[@]}"; do own_kill "${NPID[$k]}"; done; }
die(){ printf '[v17ms] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$B/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build: $B"

rpc(){ curl -s --max-time 20 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":${3:-[]},\"id\":1}" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
tiphash(){ rpc "$1" getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1; }
blockhash(){ rpc "$1" getblockhash "[$2]" | grep -oE '[a-f0-9]{64}' | head -1; }
blocktxids(){ rpc "$1" getblock "[\"$(blockhash "$1" "$2")\"]" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(" ".join(d.get("result",{}).get("txids",[])))'; }
mempool(){ rpc "$1" getrawmempool | python3 -c 'import sys,json;d=json.load(sys.stdin);r=d.get("result",[]);print(" ".join(x if isinstance(x,str) else x.get("txid","") for x in r))'; }
utxos(){ rpc "$1" getaddressutxos "[\"$2\"]" | python3 -c 'import sys,json
try:
  d=json.load(sys.stdin); r=d.get("result",[]); print(sum(int(u["amount_stocks"]) for u in r), len(r), ",".join(str(u.get("output_type")) for u in r))
except Exception: print(0,0,"")'; }
jget(){ python3 -c 'import sys,json;print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$1" "$2"; }

start_node(){ # start_node <tag> <chain> <p2p> <rpc>
  nice -n 19 "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$2" --port "$3" --rpc-port "$4" \
    --rpc-noauth --noseed --connect 127.0.0.1:1 >>"$WORK/node_$1.log" 2>&1 &
  NPID[$1]=$!
  for _ in $(seq 1 60); do sleep 1; [[ -n "$(height "$4")" ]] && return 0; done; die "node $1 did not boot"; }
stop_node(){ own_kill "${NPID[$1]:-}"; unset "NPID[$1]"; sleep 1; }
mine_to(){ # mine_to <rpc> <addr> <wallet> <target> <deadline-s>
  local port="$1" addr="$2" w="$3" tgt="$4" dl="$5" t0 h; t0=$(date +%s)
  [[ "$(height "$port")" -ge "$tgt" ]] && return 0
  local avail w0; w0=$(date +%s)
  while :; do avail=$(free -g | awk '/^Mem:/{print $7}'); [[ "$avail" -ge 6 ]] && break
    [[ $(($(date +%s)-w0)) -ge 3600 ]] && die "only ${avail} GB available for 1 h — refusing to start a devnet miner (needs >= 6)"
    sleep 10; done
  t0=$(date +%s)
  nice -n 19 "$MINER" --profile dev --rpc "127.0.0.1:$port" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 2 >>"$WORK/miner_$port.log" 2>&1 &
  MPID=$!
  while :; do h="$(height "$port")"; [[ -n "$h" && "$h" -ge "$tgt" ]] && break
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { own_kill "$MPID"; MPID=""; die "stuck reaching $tgt on :$port (at $h)"; }; sleep 1; done
  own_kill "$MPID"; MPID=""; sleep 1
  h="$(height "$port")"; [[ "$h" -ge "$tgt" ]] || die "height $h < $tgt after mining"; }
newwallet(){ "$CLI" --wallet "$WORK/$1.json" newwallet 2>/dev/null | grep -oE 'sost1[0-9a-f]{40}' | head -1; }
pubkey(){ "$CLI" --wallet "$WORK/$1.json" getpubkey 2>/dev/null | tr -d '[:space:]'; }
cli(){ "$CLI" --node "127.0.0.1:$1" "${@:2}"; }
sign(){ "$CLI" --wallet "$WORK/$1.json" signtx "$2" --out "$3" --network dev --yes >>"$WORK/cli.log" 2>&1; }
send_hex(){ rpc "$1" sendrawtransaction "[\"$2\"]"; }
export_import(){ # export_import <from_rpc> <to_rpc> <h0> <h1>
  for H in $(seq "$3" "$4"); do
    local bh raw; bh="$(blockhash "$1" "$H")"
    raw="$(rpc "$1" getrawblock "[\"$bh\"]" | python3 -c 'import sys,json;d=json.load(sys.stdin);r=d.get("result","");print(r if isinstance(r,str) else "")')"
    [[ -n "$raw" ]] || die "getrawblock empty at $H"
    rpc "$2" submitblock "[$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$raw")]" >/dev/null; sleep 1
  done; sleep 2; }

log "work=$WORK  build=$B"
MA=$(newwallet m); MB=$(newwallet mb); MC=$(newwallet mc); RCP=$(newwallet r)
for i in 1 2 3 4 5; do newwallet "s$i" >/dev/null; done
[[ -n "$MA" && -n "$MB" && -n "$MC" && -n "$RCP" ]] || die "wallets"
P1=$(pubkey s1); P2=$(pubkey s2); P3=$(pubkey s3); P4=$(pubkey s4); P5=$(pubkey s5)
"$CLI" createmultisig 2 "$P1" "$P2" "$P3" --network dev --out "$WORK/pol23.json" >/dev/null || die "createmultisig 2-of-3"
"$CLI" createmultisig 3 "$P1" "$P2" "$P3" "$P4" "$P5" --network dev --out "$WORK/pol35.json" >/dev/null || die "createmultisig 3-of-5"
A23=$(jget "$WORK/pol23.json" address); A35=$(jget "$WORK/pol35.json" address)
[[ "$A23" == dsostms1* && "$A35" == dsostms1* ]] && ok "devnet multisig addresses: 2-of-3 $A23 / 3-of-5 $A35" || bad "bad multisig addresses"

# ============================== Phase 1 =====================================
start_node n "$WORK/main.json" $N_P2P $N_RPC
mine_to $N_RPC "$MA" "$WORK/m.json" 52 900
log "main chain at $(height $N_RPC)"
if cli $N_RPC --from-address "$MA" buildtx "$A35" 5 --out "$WORK/early.json" --network dev >"$WORK/early.out" 2>&1; then
  bad "wallet built a multisig funding before activation"
else grep -q 'not active' "$WORK/early.out" && ok "wallet_refuses_sostms_before_MH (height $(height $N_RPC))" || bad "early refusal message: $(cat "$WORK/early.out")"; fi
cli $N_RPC --from-address "$MA" buildtx "$A35" 5 --out "$WORK/f0.json" --network dev --allow-before-activation >>"$WORK/cli.log" 2>&1 || die "buildtx f0"
sign m "$WORK/f0.json" "$WORK/f0s.json" || die "sign f0"
F0=$(jget "$WORK/f0s.json" final_hex); F0ID=$(jget "$WORK/f0s.json" txid)
[[ ${#F0} -gt 100 ]] && ok "v2 single-sig funding signed offline (txid ${F0ID:0:16}…)" || die "f0 not complete"
mine_to $N_RPC "$MA" "$WORK/m.json" 57 300
stop_node n; cp "$WORK/main.json" "$WORK/base57.json"; start_node n "$WORK/main.json" $N_P2P $N_RPC
mine_to $N_RPC "$MA" "$WORK/m.json" 58 300
R1=$(send_hex $N_RPC "$F0")
echo "$R1" | grep -q '"error"' && echo "$R1" | grep -q 'R1' && ok "v2 tx for next block 59 REJECTED (R1): $(echo "$R1" | grep -oE 'R1:[^"]*' | head -1)" || bad "v2 tx accepted before activation: $R1"
mine_to $N_RPC "$MA" "$WORK/m.json" 59 300
stop_node n; start_node n "$WORK/main.json" $N_P2P $N_RPC
[[ "$(height $N_RPC)" == "59" ]] && ok "restart just before activation: tip 59 reloaded" || bad "restart before activation: tip $(height $N_RPC)"
R2=$(send_hex $N_RPC "$F0")
echo "$R2" | grep -q "$F0ID" && ok "the SAME v2 tx for next block 60 ACCEPTED" || bad "v2 tx rejected at activation: $R2"
mine_to $N_RPC "$MA" "$WORK/m.json" 60 300
echo " $(blocktxids $N_RPC 60) " | grep -q " $F0ID " && ok "block 60 (first V17 block) carries the v2 funding tx" || bad "funding not in block 60: $(blocktxids $N_RPC 60)"
read -r S35 C35 T35 < <(utxos $N_RPC "$A35")
[[ "$S35" == "500000000" && "$C35" == "1" && "$T35" == "80" ]] && ok "3-of-5 vault holds 5 SOST in one OUT_MULTISIG (0x50) UTXO" || bad "3-of-5 vault: $S35 $C35 $T35"

# ============================== Phase 2 =====================================
cli $N_RPC --from-address "$MA" buildtx "$A23" 3 --out "$WORK/f23.json" --network dev >>"$WORK/cli.log" 2>&1 || die "buildtx f23"
sign m "$WORK/f23.json" "$WORK/f23s.json" || die "sign f23"
"$CLI" verifytx "$WORK/f23s.json" >>"$WORK/cli.log" 2>&1 && ok "verifytx: funding of 2-of-3 complete and valid" || bad "verifytx f23"
send_hex $N_RPC "$(jget "$WORK/f23s.json" final_hex)" | grep -q "$(jget "$WORK/f23s.json" txid)" || bad "send f23"
mine_to $N_RPC "$MA" "$WORK/m.json" 61 300
read -r S23 C23 _ < <(utxos $N_RPC "$A23")
[[ "$S23" == "300000000" && "$C23" == "1" ]] && ok "2-of-3 vault funded: 3 SOST" || bad "2-of-3 funding: $S23 $C23"

# spend the 2-of-3: 1 SOST to RCP, change back to the same MSH
cli $N_RPC buildtx --from-multisig "$WORK/pol23.json" "$RCP" 1 --out "$WORK/sp23.json" --network dev >>"$WORK/cli.log" 2>&1 || die "buildtx sp23"
sign s1 "$WORK/sp23.json" "$WORK/sp23_a.json" && sign s3 "$WORK/sp23.json" "$WORK/sp23_b.json" || die "sign sp23"
"$CLI" verifytx "$WORK/sp23_a.json" >/dev/null 2>&1; [[ $? -eq 2 ]] && ok "1 of 2 signatures: verifytx reports INCOMPLETE" || bad "verifytx incomplete exit code"
"$CLI" combinetx "$WORK/sp23_a.json" "$WORK/sp23_b.json" --out "$WORK/sp23_c.json" >>"$WORK/cli.log" 2>&1 || die "combine sp23"
"$CLI" verifytx "$WORK/sp23_c.json" >>"$WORK/cli.log" 2>&1 && ok "2-of-3 spend: combinetx + verifytx complete/valid" || bad "verifytx sp23"
SP23=$(jget "$WORK/sp23_c.json" final_hex); SP23ID=$(jget "$WORK/sp23_c.json" txid)
BADHEX="${SP23:0:500}$( [[ "${SP23:500:1}" == "0" ]] && echo 1 || echo 0 )${SP23:501}"
RB=$(send_hex $N_RPC "$BADHEX"); echo "$RB" | grep -qE 'S18|S17|S5|S4|R2[6-8]|decode' && ok "node rejects the 2-of-3 spend with a corrupted multisig byte: $(echo "$RB" | grep -oE '(S1[78]|S[45]|R2[6-8])[^"]{0,40}' | head -1)" || bad "corrupted spend: $RB"
send_hex $N_RPC "$SP23" | grep -q "$SP23ID" && ok "2-of-3 spend accepted by the node" || bad "2-of-3 spend rejected"
mine_to $N_RPC "$MA" "$WORK/m.json" 62 300
read -r SR CR _ < <(utxos $N_RPC "$RCP"); read -r S23 C23 _ < <(utxos $N_RPC "$A23")
[[ "$SR" == "100000000" ]] && ok "recipient received 1 SOST from the 2-of-3" || bad "recipient after 2-of-3: $SR"
[[ "$C23" == "1" && "$S23" -lt 200000000 && "$S23" -gt 199000000 ]] && ok "2-of-3 change returned to the same MSH ($S23 stocks)" || bad "2-of-3 change: $S23 $C23"

# spend the 3-of-5: 2 SOST to RCP
cli $N_RPC buildtx --from-multisig "$WORK/pol35.json" "$RCP" 2 --out "$WORK/sp35.json" --network dev >>"$WORK/cli.log" 2>&1 || die "buildtx sp35"
sign s5 "$WORK/sp35.json" "$WORK/sp35_a.json" && sign s2 "$WORK/sp35.json" "$WORK/sp35_b.json" && sign s4 "$WORK/sp35.json" "$WORK/sp35_c.json" || die "sign sp35"
"$CLI" combinetx "$WORK/sp35_a.json" "$WORK/sp35_b.json" "$WORK/sp35_c.json" --out "$WORK/sp35_x.json" >>"$WORK/cli.log" 2>&1 || die "combine sp35"
"$CLI" verifytx "$WORK/sp35_x.json" >>"$WORK/cli.log" 2>&1 && ok "3-of-5 spend: 3 independent signers, combinetx + verifytx valid" || bad "verifytx sp35"
send_hex $N_RPC "$(jget "$WORK/sp35_x.json" final_hex)" | grep -q "$(jget "$WORK/sp35_x.json" txid)" && ok "3-of-5 spend accepted" || bad "3-of-5 spend rejected"
mine_to $N_RPC "$MA" "$WORK/m.json" 63 300
read -r SR CR _ < <(utxos $N_RPC "$RCP")
[[ "$SR" == "300000000" && "$CR" == "2" ]] && ok "recipient holds 3 SOST (1 from 2-of-3 + 2 from 3-of-5)" || bad "recipient after 3-of-5: $SR $CR"

# restart just after activation: multisig UTXOs persist and stay spendable
B35=$(utxos $N_RPC "$A35"); B23=$(utxos $N_RPC "$A23"); TIP=$(tiphash $N_RPC)
stop_node n; start_node n "$WORK/main.json" $N_P2P $N_RPC
[[ "$(tiphash $N_RPC)" == "$TIP" && "$(utxos $N_RPC "$A35")" == "$B35" && "$(utxos $N_RPC "$A23")" == "$B23" ]] \
  && ok "restart after activation: tip and both vaults' UTXOs reloaded identically" || bad "restart after activation changed state"

# rotation: the 3-of-5 vault pays into the 2-of-3 policy (old threshold signs; no UTXO mutated)
read -r S23b C23b _ < <(utxos $N_RPC "$A23")
cli $N_RPC buildtx --from-multisig "$WORK/pol35.json" "$A23" 1 --out "$WORK/rot.json" --network dev >>"$WORK/cli.log" 2>&1 || die "buildtx rot"
sign s1 "$WORK/rot.json" "$WORK/rot_a.json" && sign s2 "$WORK/rot.json" "$WORK/rot_b.json" && sign s3 "$WORK/rot.json" "$WORK/rot_c.json" || die "sign rot"
"$CLI" combinetx "$WORK/rot_a.json" "$WORK/rot_b.json" "$WORK/rot_c.json" --out "$WORK/rot_x.json" >>"$WORK/cli.log" 2>&1 || die "combine rot"
send_hex $N_RPC "$(jget "$WORK/rot_x.json" final_hex)" | grep -q "$(jget "$WORK/rot_x.json" txid)" && ok "rotation tx (3-of-5 -> 2-of-3) accepted" || bad "rotation rejected"
mine_to $N_RPC "$MA" "$WORK/m.json" 64 300
read -r S23c C23c _ < <(utxos $N_RPC "$A23")
[[ "$C23c" == "$((C23b+1))" && "$S23c" == "$((S23b+100000000))" ]] && ok "rotation: new policy holds the moved 1 SOST as a new UTXO" || bad "rotation result: $S23b/$C23b -> $S23c/$C23c"

# NODE_BIND with outer version 2 is rejected from V17 (R30)
BH=$("$CLI" --wallet "$WORK/m.json" createnodebind 1 "$(openssl rand -hex 32)" 2>>"$WORK/cli.log" | tr -d '[:space:]')
if [[ ${#BH} -gt 200 && "${BH:0:8}" == "01000000" ]]; then
  RN=$(send_hex $N_RPC "02000000${BH:8}")
  echo "$RN" | grep -q 'node_tx_bad_version' && ok "NODE_BIND with outer version 2 rejected at h>=60 (node_tx_bad_version)" || bad "outer v2 node bind: $RN"
else bad "createnodebind produced no tx"; fi
stop_node n

# ============================== Phase 3: reorg ==============================
cp "$WORK/base57.json" "$WORK/P.json"; cp "$WORK/base57.json" "$WORK/Q.json"; cp "$WORK/base57.json" "$WORK/R.json"
start_node p "$WORK/P.json" $P_P2P $P_RPC
mine_to $P_RPC "$MB" "$WORK/mb.json" 59 300
P59=$(tiphash $P_RPC); stop_node p
start_node q "$WORK/Q.json" $Q_P2P $Q_RPC
mine_to $Q_RPC "$MC" "$WORK/mc.json" 59 300
cli $Q_RPC --from-address "$MA" buildtx "$A23" 2 --out "$WORK/fx.json" --network dev >>"$WORK/cli.log" 2>&1 || die "buildtx fx"
sign m "$WORK/fx.json" "$WORK/fxs.json" || die "sign fx"
FX=$(jget "$WORK/fxs.json" final_hex); FXID=$(jget "$WORK/fxs.json" txid)
send_hex $Q_RPC "$FX" | grep -q "$FXID" || die "fx not accepted on Q"
mine_to $Q_RPC "$MC" "$WORK/mc.json" 62 300
QTIP=$(tiphash $Q_RPC)
QIN=0; for h in 60 61 62; do echo " $(blocktxids $Q_RPC $h) " | grep -q " $FXID " && QIN=$h; done
[[ "$QIN" -ge 60 ]] && ok "branch Q: multisig funding mined in V17 block $QIN" || bad "fx not mined on Q"
start_node p "$WORK/P.json" $P_P2P $P_RPC
[[ "$(tiphash $P_RPC)" == "$P59" ]] || bad "P did not reload tip 59"
export_import $Q_RPC $P_RPC 58 62
[[ "$(tiphash $P_RPC)" == "$QTIP" ]] && ok "REORG pre->post activation: P (tip 59) switched to Q (tip 62) across block 60" || bad "P did not reorg onto Q"
read -r SX CX _ < <(utxos $P_RPC "$A23")
[[ "$SX" == "200000000" && "$CX" == "1" ]] && ok "after reorg P holds the multisig output created in a V17 block" || bad "P multisig after reorg 1: $SX $CX"
stop_node q
start_node r "$WORK/R.json" $R_P2P $R_RPC
mine_to $R_RPC "$MB" "$WORK/mb.json" 65 400
RTIP=$(tiphash $R_RPC)
export_import $R_RPC $P_RPC 58 65
[[ "$(tiphash $P_RPC)" == "$RTIP" ]] && ok "REORG post->pre->post: P disconnected 62..58 (back across activation) and connected R 58..65" || bad "P did not reorg onto R"
read -r SX CX _ < <(utxos $P_RPC "$A23")
[[ "$SX" == "0" && "$CX" == "0" ]] && ok "the disconnected multisig output is gone from P's UTXO set" || bad "multisig UTXO survived reorg: $SX $CX"
echo " $(mempool $P_RPC) " | grep -q " $FXID " && ok "the multisig tx returned to P's mempool (next height >= 60)" || bad "fx not back in mempool: $(mempool $P_RPC)"
stop_node r
mine_to $P_RPC "$MB" "$WORK/mb.json" 66 300
read -r SX CX _ < <(utxos $P_RPC "$A23")
[[ "$SX" == "200000000" && "$CX" == "1" ]] && ok "the multisig tx is mined again on the new branch" || bad "fx not re-mined: $SX $CX"
stop_node p

echo
log "RESULT: $PASS passed, $FAIL failed  (work dir $WORK)"
[[ "$FAIL" -eq 0 ]]

#!/usr/bin/env bash
# =============================================================================
# run_v17_dtd_f1_devnet.sh — V17 DTD-F1 (DTD + Jackpot V2 seeds from the PoW commit),
# real sost-node + sost-miner on DEVNET_FAST (V17_HEIGHT = 60, jackpot cadence 6 from 24,
# Jackpot V2 from 42, NODE epoch 6).
#
#   * four miners A/B/C/D in 3-block chunks (DTD eligible set >= 2 after the 6-block
#     cooldown); A and B node-bound with heartbeats every epoch (Jackpot V2 candidates).
#   * RE-SIGNING against a real node, before and after activation: block #53 (pre-V17
#     draw #54, a jackpot height) and block #65 (V17 draw #66, a jackpot height) are
#     re-signed K times with fresh BIP-340 signatures over the same PoW commit
#     (dtd-f1-resign-block). Each variant is submitted to a fresh node holding the chain
#     up to the parent; the node must ACCEPT it (full process_block validation incl.
#     SbPoW), and its getlotterystate / getjackpotv2audit for the next draw is recorded.
#       pre-V17 : K distinct block_ids -> K distinct DTD seeds and K distinct Jackpot seeds
#       V17     : K distinct block_ids -> ONE DTD seed/winner and ONE Jackpot seed/winner
#     One variant node is restarted: the stored commit reloads and the draw is unchanged.
#   * restarts of the main node just before (#59) and after (#66) activation.
#   * reorg ACROSS activation: a branch forked at #58 with more work replaces the main
#     chain; the independent audit (tests/dtd_f1/devnet_seed_audit.py) checks every DTD
#     draw and every Jackpot V2 seed before and after the reorg against the chain data.
#
# Env: BUILD_DIR (devnet build, required), WORK (default mktemp), PORT_BASE (31400), K (6).
# Kills ONLY processes it started, by exact PID, after checking /proc/PID/cmdline.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:?BUILD_DIR (devnet build dir) required}"
WORK="${WORK:-$(mktemp -d "${TMPDIR:-/tmp}/dtdf1e2e.XXXXXX")}"
PB="${PORT_BASE:-31400}"; K="${K:-6}"
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"; RESIGN="$BUILD_DIR/dtd-f1-resign-block"
GEN="$ROOT/genesis_block.json"
V17=60; A2=42; L=6
FAILED=0; PASSN=0
declare -A NPID=()
log(){ printf '[dtdf1] %s\n' "$*"; }
ok(){ printf '[dtdf1] PASS  %s\n' "$*"; PASSN=$((PASSN+1)); }
bad(){ printf '[dtdf1] FAIL  %s\n' "$*"; FAILED=$((FAILED+1)); }
argv0(){ tr '\0' '\n' < "/proc/$1/cmdline" 2>/dev/null | head -1; }
safe_kill(){ local p="$1"; [[ -n "$p" && -d "/proc/$p" ]] || return 0
  local a; a="$(argv0 "$p")"
  if [[ "$a" == "$NODE" || "$a" == "$MINER" ]]; then kill "$p" 2>/dev/null
    for _ in $(seq 1 120); do [[ -d "/proc/$p" ]] || return 0; sleep 0.5; done
  fi; }
cleanup(){ for k in "${!NPID[@]}"; do safe_kill "${NPID[$k]}"; done; [[ -n "${MP:-}" ]] && safe_kill "$MP"; true; }
die(){ printf '[dtdf1] FATAL %s\n' "$*" >&2; cleanup; log "work dir kept: $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"
[[ -x "$NODE" && -x "$MINER" && -x "$CLI" && -x "$RESIGN" ]] || die "binaries missing"

rpc(){ curl -s --max-time 30 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":${3:-[]},\"id\":1}" "http://127.0.0.1:$1/"; }
jq_(){ python3 -c 'import sys,json
d=json.load(sys.stdin); r=d.get("result")
try: print(eval(sys.argv[1], {"r": r}))
except Exception as e: print("ERR", e)' "$1"; }
height(){ rpc "$1" getblockcount | jq_ 'r'; }
bhash(){ rpc "$1" getblockhash "[$2]" | jq_ 'r'; }
start_node(){ # name chainfile p2p rpc
  nice -n 19 "$NODE" --profile dev --genesis "$GEN" --chain "$2" --port "$3" --rpc-port "$4" \
     --rpc-noauth --noseed --connect 127.0.0.1:1 >>"$WORK/$1.log" 2>&1 &
  NPID[$1]=$!
  for _ in $(seq 1 120); do sleep 0.5; [[ "$(height "$4")" =~ ^[0-9]+$ ]] && return 0; done; die "node $1 did not boot"; }
stop_node(){ safe_kill "${NPID[$1]:-}"; unset "NPID[$1]"; }
memcheck(){ for _ in $(seq 1 120); do local av; av=$(free -g | awk '/^Mem:/{print $7}'); [[ "$av" -ge 6 ]] && return 0; sleep 5; done; die "less than 6 GB available for a devnet miner"; }
mine(){ # rpcport wallet-letter n
  local h0; h0="$(height "$1")"; memcheck
  nice -n 19 "$MINER" --profile dev --genesis "$GEN" --rpc "127.0.0.1:$1" --address "${ADDR[$2]}" --wallet "$WORK/$2.json" \
     --mining-key-label default --blocks "$3" --threads 2 --realtime >>"$WORK/miner_$1.log" 2>&1 &
  MP=$!; local t0; t0=$(date +%s)
  while [[ -d "/proc/$MP" ]]; do sleep 1; [[ $(( $(date +%s) - t0 )) -gt 1200 ]] && { safe_kill "$MP"; die "miner timeout"; }; done
  MP=""
  local h1; h1="$(height "$1")"; [[ "$h1" -eq $((h0 + $3)) ]] || die "mined to $h1, expected $((h0 + $3))"; }
send_raw(){ rpc "$1" sendrawtransaction "[\"$2\"]"; }
heartbeat(){ # rpcport letter epoch
  local tr; tr="$(bhash "$1" $((A2 + L * $3 - 1)))"
  local hx; hx="$("$CLI" --wallet "$WORK/$2.json" nodeheartbeat --node-key-file "$WORK/node_$2.key" "$3" "$tr" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
  [[ ${#hx} -gt 100 ]] || die "nodeheartbeat $2 e$3 build failed"
  send_raw "$1" "$hx" | grep -q '"result"' || die "heartbeat $2 e$3 rejected"; }
export_import(){ # from_rpc to_rpc h_from h_to
  for h in $(seq "$3" "$4"); do
    local hh raw; hh="$(bhash "$1" "$h")"
    raw="$(rpc "$1" getrawblock "[\"$hh\"]" | python3 -c 'import sys,json;r=json.load(sys.stdin).get("result","");print(json.dumps(r) if isinstance(r,str) else "")')"
    [[ -n "$raw" ]] || die "getrawblock h=$h"
    rpc "$2" submitblock "[$raw]" >/dev/null
  done; sleep 3; }
rawblock(){ rpc "$1" getrawblock "[\"$(bhash "$1" "$2")\"]" | python3 -c 'import sys,json;r=json.load(sys.stdin).get("result","");sys.stdout.write(r if isinstance(r,str) else "")'; }
draw_state(){ # rpcport height_next -> "dtd_seed dtd_winner rule jp_seed jp_winner jp_rule"
  local ls jp; ls="$(rpc "$1" getlotterystate)"; jp="$(rpc "$1" getjackpotv2audit "[$2]")"
  printf '%s %s %s %s\n' \
    "$(echo "$ls" | jq_ '(r["seed_hex"], r["lottery_winner_pkh"] or "-", r["seed_rule"], r["height_next"])' | tr -d "(),'")" \
    "$(echo "$jp" | jq_ 'r.get("seed_hex","-")')" "$(echo "$jp" | jq_ 'r.get("winner_address") or "-"')" "$(echo "$jp" | jq_ 'r.get("seed_rule","-")')"; }

log "work=$WORK ports $PB..  V17=$V17  K=$K"
declare -A ADDR=()
for w in A B C D; do
  ADDR[$w]="$("$CLI" --wallet "$WORK/$w.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
  [[ -n "${ADDR[$w]}" ]] || die "wallet $w"
done
( umask 077; openssl rand -hex 32 > "$WORK/node_A.key"; openssl rand -hex 32 > "$WORK/node_B.key"
  python3 -c 'import json,sys;print([k["privkey"] for k in json.load(open(sys.argv[1]))["keys"] if k.get("label")=="default"][0])' "$WORK/A.json" > "$WORK/A.sk" ) \
  || die "key files"
[[ "$(wc -c < "$WORK/A.sk")" -ge 64 ]] || die "miner key of A not found in the wallet"
log "A=${ADDR[A]} B=${ADDR[B]} C=${ADDR[C]} D=${ADDR[D]}"
R1=$((PB+2)); R2=$((PB+12)); R3=$((PB+22))
start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
GENHEX="$(bhash "$R1" 0)"

# ---- pre-V17 history, A/B bound + heartbeats every epoch --------------------
for c in A B C D A B C D A B C D A B C; do mine "$R1" "$c" 3; done            # 1..45
mine "$R1" D 1                                                                  # 46
for w in A B; do
  BIND="$("$CLI" --wallet "$WORK/$w.json" createnodebind 1 --node-key-file "$WORK/node_$w.key" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
  send_raw "$R1" "$BIND" | grep -q '"result"' && ok "NODE_BIND($w) accepted" || die "bind $w rejected"
done
mine "$R1" C 1                                                                  # 47
heartbeat "$R1" A 1; heartbeat "$R1" B 1
mine "$R1" D 3; mine "$R1" C 2                                                  # 48..52
stop_node n1; cp "$WORK/c1.json" "$WORK/snap52.json"; start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
mine "$R1" A 1                                                                  # 53 (re-signed below, pre-V17)
heartbeat "$R1" A 2; heartbeat "$R1" B 2
PRE_ORIG="$(draw_state "$R1" 54)"
mine "$R1" B 3; mine "$R1" C 1                                                  # 54..57
mine "$R1" D 1                                                                  # 58
stop_node n1; cp "$WORK/c1.json" "$WORK/fork58.json"; start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
mine "$R1" A 1                                                                  # 59
heartbeat "$R1" A 3; heartbeat "$R1" B 3
# restart just BEFORE activation: next draw (#60, first V17 draw) identical
S59="$(draw_state "$R1" 60)"; stop_node n1; start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
[[ "$(draw_state "$R1" 60)" == "$S59" ]] && ok "restart at #59: draw #60 state identical ($S59)" || bad "restart #59 changed the draw"
echo "$S59" | grep -q "V17_POW_COMMIT .* V17_POW_COMMIT" && ok "draw #60 (activation) uses V17_POW_COMMIT for DTD and Jackpot" || bad "draw #60 rule: $S59"
mine "$R1" B 3; mine "$R1" C 1                                                  # 60..63
mine "$R1" D 1                                                                  # 64
stop_node n1; cp "$WORK/c1.json" "$WORK/snap64.json"; start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
mine "$R1" A 1                                                                  # 65 (re-signed below, V17)
heartbeat "$R1" A 4; heartbeat "$R1" B 4
POST_ORIG="$(draw_state "$R1" 66)"
mine "$R1" C 1                                                                  # 66 (V17 jackpot height)
S66="$(draw_state "$R1" 67)"; stop_node n1; start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
[[ "$(draw_state "$R1" 67)" == "$S66" ]] && ok "restart at #66 (after activation): draw #67 state identical" || bad "restart #66 changed the draw"
mine "$R1" D 3; mine "$R1" A 2                                                  # 67..71
heartbeat "$R1" A 5; heartbeat "$R1" B 5
mine "$R1" B 3; mine "$R1" C 1                                                  # 72..75
log "main chain tip $(height "$R1")"
python3 -I "$ROOT/tests/dtd_f1/devnet_seed_audit.py" "$R1" "$V17" 18 2>&1 | sed 's/^/[dtdf1]   audit| /'
[[ ${PIPESTATUS[0]} == 0 ]] && ok "independent seed audit of the main chain (every DTD draw + every Jackpot V2 seed, both rules)" || bad "seed audit main chain"

# ---- re-signing against a real node ----------------------------------------
resign_case(){ # label snapshot target_height draw_height expect(pre|post)
  local label="$1" snap="$2" th="$3" dh="$4" want="$5"
  rawblock "$R1" "$th" > "$WORK/blk$th.json"; [[ -s "$WORK/blk$th.json" ]] || die "getrawblock #$th"
  local orig_id; orig_id="$(bhash "$R1" "$th")"
  : > "$WORK/resign_$th.txt"
  for i in $(seq 0 $((K - 1))); do
    "$RESIGN" "$WORK/blk$th.json" "$WORK/A.sk" "$GENHEX" "$i" > "$WORK/v${th}_$i.json" 2>>"$WORK/resign.log" || die "resign #$th aux=$i"
    local vid; vid="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["block_id"])' "$WORK/v${th}_$i.json")"
    cp "$WORK/$snap" "$WORK/n2.json"; start_node n2 "$WORK/n2.json" $((PB+11)) "$R2"
    rpc "$R2" submitblock "[$(python3 -c 'import json,sys;print(json.dumps(open(sys.argv[1]).read()))' "$WORK/v${th}_$i.json")]" > "$WORK/submit_${th}_$i.txt"
    sleep 1
    local got; got="$(bhash "$R2" "$th")"
    if [[ "$got" != "$vid" ]]; then bad "$label aux=$i: node did not accept the re-signed block ($(cat "$WORK/submit_${th}_$i.txt"))"; stop_node n2; continue; fi
    local st; st="$(draw_state "$R2" "$dh")"
    echo "$i $vid $st" >> "$WORK/resign_$th.txt"
    if [[ "$i" == 1 ]]; then   # restart one variant node: commit reloaded from chain.json, same draw
      stop_node n2; start_node n2 "$WORK/n2.json" $((PB+11)) "$R2"
      [[ "$(draw_state "$R2" "$dh")" == "$st" ]] && ok "$label: variant node restarted, draw #$dh unchanged" || bad "$label: restart changed draw"
    fi
    stop_node n2
  done
  local n ids ds dw js jw rule; n=$(wc -l < "$WORK/resign_$th.txt")
  ids=$(awk '{print $2}' "$WORK/resign_$th.txt" | sort -u | wc -l)
  ds=$(awk '{print $3}' "$WORK/resign_$th.txt" | sort -u | wc -l); dw=$(awk '{print $4}' "$WORK/resign_$th.txt" | sort -u | wc -l)
  js=$(awk '{print $7}' "$WORK/resign_$th.txt" | sort -u | wc -l); jw=$(awk '{print $8}' "$WORK/resign_$th.txt" | sort -u | wc -l)
  rule=$(awk '{print $5"/"$9}' "$WORK/resign_$th.txt" | sort -u | tr '\n' ' ')
  log "$label: accepted $n/$K re-signed variants of #$th, block_ids=$ids, draw #$dh rule=$rule DTD seeds=$ds winners=$dw | Jackpot seeds=$js winners=$jw"
  sed 's/^/[dtdf1]     /' "$WORK/resign_$th.txt"
  [[ "$n" == "$K" && "$ids" == "$K" ]] && ok "$label: all $K re-signed variants accepted by a real node, $K distinct block_ids" || bad "$label: accepted $n, ids $ids"
  [[ "$(awk '$1==0{print $2}' "$WORK/resign_$th.txt")" == "$orig_id" ]] && ok "$label: aux 0 reproduces the mined block_id (tool fidelity)" || bad "$label: aux0 id != mined id"
  if [[ "$want" == pre ]]; then
    [[ "$ds" == "$K" && "$js" == "$K" ]] && ok "$label (pre-V17): every re-signature changes the DTD seed and the Jackpot seed ($dw DTD winners, $jw jackpot winners reached)" || bad "$label pre: seeds $ds/$js"
    [[ "$rule" == "V11_BLOCK_ID/V11_BLOCK_ID " ]] && ok "$label: rule V11_BLOCK_ID" || bad "$label rule $rule"
  else
    [[ "$ds" == 1 && "$dw" == 1 && "$js" == 1 && "$jw" == 1 ]] && ok "$label (V17): $K re-signatures -> ONE DTD seed, ONE DTD winner, ONE Jackpot seed, ONE Jackpot winner" || bad "$label V17: seeds/winners $ds/$dw/$js/$jw"
    [[ "$rule" == "V17_POW_COMMIT/V17_POW_COMMIT " ]] && ok "$label: rule V17_POW_COMMIT" || bad "$label rule $rule"
  fi; }
resign_case "PRE-V17 re-sign #53" snap52.json 53 54 pre
resign_case "V17 re-sign #65" snap64.json 65 66 post
[[ "$(awk '{print $3, $4, $7, $8}' "$WORK/resign_65.txt" | sort -u)" == "$(echo "$POST_ORIG" | awk '{print $1, $2, $5, $6}')" ]] \
  && ok "V17 re-signed variants give exactly the draw #66 the main node computed with the mined block" || bad "V17 variants differ from the main node: $POST_ORIG"

# ---- reorg across activation -------------------------------------------------
start_node n3 "$WORK/fork58.json" $((PB+21)) "$R3"
mine "$R3" B 3; mine "$R3" D 3; mine "$R3" C 3; mine "$R3" B 3; mine "$R3" D 3; mine "$R3" C 3   # 59..76 (branch Z)
T3="$(rpc "$R3" getbestblockhash | jq_ r)"
python3 -I "$ROOT/tests/dtd_f1/devnet_seed_audit.py" "$R3" "$V17" 18 2>&1 | tail -1 | sed 's/^/[dtdf1]   audit(branch)| /'
export_import "$R3" "$R1" 59 76
[[ "$(rpc "$R1" getbestblockhash | jq_ r)" == "$T3" ]] && ok "reorg across activation: main node switched to the branch forked at #58 (59..76)" || bad "no reorg"
[[ "$(draw_state "$R1" 77)" == "$(draw_state "$R3" 77)" ]] && ok "after the reorg the main node's next draw == clean branch node" || bad "post-reorg draw differs"
python3 -I "$ROOT/tests/dtd_f1/devnet_seed_audit.py" "$R1" "$V17" 18 2>&1 | sed 's/^/[dtdf1]   audit(after reorg)| /'
[[ ${PIPESTATUS[0]} == 0 ]] && ok "independent seed audit after the reorg: every draw re-derived from the new chain (pre and post 60)" || bad "seed audit after reorg"
stop_node n3
stop_node n1; start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
[[ "$(rpc "$R1" getbestblockhash | jq_ r)" == "$T3" ]] && ok "restart after the reorg: tip kept" || bad "restart after reorg"
python3 -I "$ROOT/tests/dtd_f1/devnet_seed_audit.py" "$R1" "$V17" 18 2>&1 | tail -1 | sed 's/^/[dtdf1]   audit(after restart)| /'
[[ ${PIPESTATUS[0]} == 0 ]] && ok "independent seed audit after restart" || bad "seed audit after restart"
stop_node n1
log "RESULT: $PASSN passed, $FAILED failed (work dir $WORK)"
[[ $FAILED == 0 ]] && echo "[dtdf1] RESULT: PASS" || echo "[dtdf1] RESULT: FAIL"
exit $FAILED

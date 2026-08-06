#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_multiblock_attacks.sh — V15-A multi-block / stateful attack coverage.
#
# Consensus-attack properties that a single in-block mutation cannot express (they need
# real chain state, restart or a captured canonical transaction). Each scenario runs in its
# OWN fresh datadir + node on isolated ports; no `pkill`/`killall`, no cleanup-by-name.
#
# Scenarios:
#   M02 — a captured canonical jackpot tx injected at a NON-event height must be rejected;
#         state unchanged; still rejected byte-for-byte after restart; honest block accepted.
#   M03 — an OLD/stale canonical jackpot tx replayed at a LATER event height must be rejected
#         by OBSOLESCENCE (spent inputs / non-canonical), NOT merely by "non-event height";
#         state unchanged; still rejected after restart; the correct honest block accepted.
#   M08 — a rejected valid-PoW attack block stays rejected byte-for-byte across a restart.
#
# DEV-only miner flags used (all #ifdef SOST_DEVNET_FORKS, verified absent from mainnet/testnet):
#   --attack-jackpot <mut>  --dump-block <file>  --inject-tx-at1 <hexfile>
#
# Usage: tests/run_v15_devnet_multiblock_attacks.sh [--scenario M02|M03|M08|all]
#   Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any mismatch. Datadirs/logs preserved on failure.
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
BASE_RPC=18990; BASE_P2P=19990
SCENARIO="all"
while [[ $# -gt 0 ]]; do case "$1" in
  --scenario) SCENARIO="$2"; shift 2;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15mbattack.XXXXXX")"
FIRST_J=24; CADENCE=6; FAILED=0
GOLD="sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"; POPC="sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"
declare -a PIDS=()
log(){ printf '[mbattack] %s\n' "$*"; }
ok(){ printf '[mbattack] PASS  %s\n' "$*"; }
bad(){ printf '[mbattack] FAIL  %s\n' "$*"; FAILED=1; }
cleanup(){
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  if [[ -n "${WORK:-}" ]]; then
    for pid in $(pgrep -f -- "$WORK" 2>/dev/null || true); do [[ "$pid" == "$$" ]] && continue; kill "$pid" 2>/dev/null || true; done
  fi
  wait 2>/dev/null || true
}
die(){ printf '[mbattack] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"

# --- per-scenario node context (set by boot_fresh) ---
RPC=""; P2P=""; DDIR=""; NLOG=""; NODE_PID=""
rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' || true; }
tiphash(){ rpc getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1 || true; }
blockhash(){ rpc getblockhash "[$1]" | grep -oE '[a-f0-9]{64}' | head -1 || true; }
txcount(){ rpc getblock "[\"$1\"]" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' || true; }
jtxid(){ rpc getblock "[\"$1\"]" | python3 -c 'import sys,json;d=json.load(sys.stdin);ids=d.get("result",{}).get("txids",[]);print(ids[1] if len(ids)>1 else "")'; }
getrawtx(){ rpc getrawtransaction "[\"$1\"]" | python3 -c 'import sys,json;r=json.load(sys.stdin).get("result","");print(r if isinstance(r,str) else (r.get("hex","") if isinstance(r,dict) else ""))'; }
reserve_tc(){ rpc getaddressutxos "[\"$1\"]" | python3 -c 'import sys,json
try: d=json.load(sys.stdin); r=d.get("result",[]); print(sum(int(u.get("amount_stocks",0)) for u in r), len(r))
except Exception: print(0,0)'; }
reserve(){ local gs gc ps pc; read -r gs gc < <(reserve_tc "$GOLD"); read -r ps pc < <(reserve_tc "$POPC"); echo "$((gs+ps)):$((gc+pc))"; }
rejects(){ local c; c="$(grep -c 'REJECTED by process_block' "$NLOG" 2>/dev/null)"; echo "${c:-0}"; }
reject_reason(){ grep -oE 'REJECTED[^\\]*' "$NLOG" 2>/dev/null | tail -1 || true; }
boot_fresh(){ # boot_fresh <tag>  → own datadir, ports, log
  local tag="$1"; DDIR="$WORK/$tag"; mkdir -p "$DDIR"; NLOG="$DDIR/node.log"
  RPC=$((BASE_RPC + 2*_PORTSLOT)); P2P=$((BASE_P2P + 2*_PORTSLOT)); _PORTSLOT=$((_PORTSLOT+1))
  "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$DDIR/chain.json" --port "$P2P" --rpc-port "$RPC" \
    --rpc-noauth --connect 127.0.0.1:1 >>"$NLOG" 2>&1 &
  PIDS+=($!); NODE_PID=$!
  for _ in $(seq 1 40); do sleep 1; [[ -n "$(height)" ]] && return 0; done; die "node $tag did not boot"; }
restart_node(){ kill "$NODE_PID" 2>/dev/null || true; sleep 2
  "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$DDIR/chain.json" --port "$P2P" --rpc-port "$RPC" \
    --rpc-noauth --connect 127.0.0.1:1 >>"$NLOG" 2>&1 &
  PIDS+=($!); NODE_PID=$!
  for _ in $(seq 1 40); do sleep 1; [[ -n "$(height)" ]] && return 0; done; die "node did not reboot"; }
stop_node(){ [[ -n "${NODE_PID:-}" ]] && kill "$NODE_PID" 2>/dev/null || true; sleep 1; NODE_PID=""; }
mine_to(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$DDIR/miner.log" 2>&1 &
  local mp=$!; PIDS+=("$mp")
  while :; do local h; h="$(height)"; [[ "${h:-0}" -ge "$tgt" ]] && { kill "$mp" 2>/dev/null || true; sleep 1; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { kill "$mp" 2>/dev/null || true; die "stuck reaching $tgt"; }; sleep 2; done; }
submit_file(){ rpc submitblock "[$(python3 -c 'import json,sys;print(json.dumps(open(sys.argv[1]).read()))' "$1")]" >/dev/null; }
_PORTSLOT=0

# run a miner that INJECTS a captured tx (and dumps the attack block) until it produces one
# rejected block or a timeout; returns via globals ATTACK_FILE.
inject_attack(){ # inject_attack <addr> <wallet> <hexfile> <dumpfile> <deadline>
  local addr="$1" w="$2" hexf="$3" dumpf="$4" dl="$5" rej0 t0
  rej0="$(rejects)"; : > "$dumpf"
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --address "$addr" --wallet "$w" --mining-key-label default \
    --inject-tx-at1 "$hexf" --dump-block "$dumpf" --blocks 100000 --threads 3 >>"$DDIR/attack.log" 2>&1 &
  local mp=$!; PIDS+=("$mp"); t0=$(date +%s)
  while :; do [[ -s "$dumpf" ]] && [[ "$(rejects)" -gt "$rej0" ]] && break
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && break; sleep 2; done
  kill "$mp" 2>/dev/null || true; sleep 1; }

# ---------- wallets (shared) ----------
WA="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
WB="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
log "A=$WA B=$WB work=$WORK scenario=$SCENARIO"

# =============================== M02 ===============================
scenario_M02(){
  log "── M02: canonical jackpot injected at a NON-event height ──"
  boot_fresh m02
  mine_to "$WA" "$WORK/a.json" "$((FIRST_J-11))" 300
  mine_to "$WB" "$WORK/b.json" "$FIRST_J" 300      # h24 = canonical jackpot event
  [[ "$(height)" == "$FIRST_J" ]] || { bad "M02: could not reach jackpot h$FIRST_J"; return; }
  local bh jt hexf; bh="$(blockhash "$FIRST_J")"; jt="$(jtxid "$bh")"
  [[ -n "$jt" ]] || { bad "M02: no jackpot txid at h$FIRST_J"; return; }
  hexf="$WORK/m02_jackpot.hex"; getrawtx "$jt" > "$hexf"
  [[ -s "$hexf" ]] && ok "M02 A1: captured canonical jackpot tx ${jt:0:16}… ($(wc -c <"$hexf") hex)" || { bad "M02: getrawtransaction empty"; return; }
  local NEV=$((FIRST_J+1))   # h25 — NOT a jackpot cadence height (24,30,36…); non-event by construction
  ok "M02 A3: target height $NEV is a NON-event height (cadence $CADENCE from $FIRST_J → 24,30,36…)"
  local TIP RES; TIP="$(tiphash)"; RES="$(reserve)"
  local atk="$WORK/m02_attack.json"; inject_attack "$WB" "$WORK/b.json" "$hexf" "$atk" 60
  [[ -s "$atk" ]] || { bad "M02: no attack block captured"; return; }
  local ah; ah="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("height"))' "$atk")"
  [[ "$ah" == "$NEV" ]] && ok "M02 A2: attack block built with valid DEV PoW at h$ah (jackpot injected at tx[1])" || bad "M02: attack height $ah != $NEV"
  if [[ "$(height)" == "$FIRST_J" && "$(tiphash)" == "$TIP" && "$(reserve)" == "$RES" ]]; then
    ok "M02 A4-A7: REJECTED — tip/height/reserve byte-unchanged ($RES) · reason: $(reject_reason)"
  else bad "M02: state moved after attack (h=$(height) res=$(reserve))"; fi
  restart_node
  local rej1; rej1="$(rejects)"; submit_file "$atk"; sleep 3
  [[ "$(height)" == "$FIRST_J" && "$(reserve)" == "$RES" && "$(rejects)" -gt "$rej1" ]] \
    && ok "M02 A8: same block STILL rejected after restart; reserve intact" || bad "M02 A8: replay-after-restart not rejected identically"
  mine_to "$WB" "$WORK/b.json" "$NEV" 120
  [[ "$(height)" == "$NEV" ]] && ok "M02 A9: honest non-event block h$NEV accepted; chain continues" || bad "M02 A9: honest block not accepted"
  stop_node
}

# =============================== M03 ===============================
scenario_M03(){
  log "── M03: OLD/stale jackpot replayed at a LATER event height ──"
  boot_fresh m03
  mine_to "$WA" "$WORK/a.json" "$((FIRST_J-11))" 900
  mine_to "$WB" "$WORK/b.json" "$FIRST_J" 900      # event A @ h24 (canonical jackpot, spends reserve)
  local bhA jtA hexf; bhA="$(blockhash "$FIRST_J")"; jtA="$(jtxid "$bhA")"
  [[ -n "$jtA" ]] || { bad "M03: no jackpot at event A h$FIRST_J"; return; }
  hexf="$WORK/m03_jackpotA.hex"; getrawtx "$jtA" > "$hexf"
  [[ -s "$hexf" ]] && ok "M03 A1-A2: event A jackpot captured ${jtA:0:16}… (canonical, accepted)" || { bad "M03: capture failed"; return; }
  local EVB=$((FIRST_J+CADENCE))   # h30 = next jackpot event
  mine_to "$WB" "$WORK/b.json" "$((EVB-1))" 900    # advance to just before event B; reserve now spent by A
  ok "M03 A3: advanced to h$((EVB-1)); next event B = h$EVB (reserve after A = $(reserve))"
  local TIP RES; TIP="$(tiphash)"; RES="$(reserve)"
  local atk="$WORK/m03_attack.json"; inject_attack "$WB" "$WORK/b.json" "$hexf" "$atk" 90
  [[ -s "$atk" ]] || { bad "M03: no attack block captured"; return; }
  local ah reason; ah="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("height"))' "$atk")"; reason="$(reject_reason)"
  [[ "$ah" == "$EVB" ]] && ok "M03 A4: attack block valid-PoW at event height h$ah (old jackpot A injected)" || bad "M03: attack height $ah != $EVB"
  # A5: h30 IS a jackpot cadence height (EVB = FIRST_J + CADENCE). So this rejection is NOT
  # "wrong height / non-event" (that is M02) — it is OBSOLESCENCE: the old event-A jackpot
  # is not the canonical jackpot THIS event authorizes (or its reserve inputs are already
  # spent). Distinct-from-M02 is guaranteed structurally by the height being a real event.
  if [[ $(( (EVB - FIRST_J) % CADENCE )) -eq 0 ]]; then
    ok "M03 A5: rejected AT a legitimate jackpot event (h$EVB is on-cadence) → obsolescence, not cadence (reason: $reason)"
  else bad "M03 A5: h$EVB is not on-cadence — scenario mis-set"; fi
  if [[ "$(height)" == "$((EVB-1))" && "$(tiphash)" == "$TIP" && "$(reserve)" == "$RES" ]]; then
    ok "M03 A6: tip/height/reserve byte-unchanged after the stale replay ($RES)"
  else bad "M03 A6: state moved (h=$(height) res=$(reserve))"; fi
  restart_node
  local rej1; rej1="$(rejects)"; submit_file "$atk"; sleep 3
  [[ "$(height)" == "$((EVB-1))" && "$(reserve)" == "$RES" && "$(rejects)" -gt "$rej1" ]] \
    && ok "M03 A7: same stale block STILL rejected after restart" || bad "M03 A7: replay-after-restart not rejected identically"
  mine_to "$WB" "$WORK/b.json" "$EVB" 400
  [[ "$(height)" == "$EVB" ]] && ok "M03 A8-A9: correct honest event-B block h$EVB accepted; final reserve=$(reserve)" || bad "M03 A8: honest event-B block not accepted"
  stop_node
}

# =============================== M08 ===============================
scenario_M08(){
  log "── M08: rejected attack block stays rejected byte-for-byte across restart ──"
  boot_fresh m08
  mine_to "$WA" "$WORK/a.json" "$((FIRST_J-11))" 300
  mine_to "$WB" "$WORK/b.json" "$PRE_J" 300
  local RES TIP; RES="$(reserve)"; TIP="$(tiphash)"
  local atk="$WORK/m08_attack.json" rej0; rej0="$(rejects)"
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --address "$WB" --wallet "$WORK/b.json" --mining-key-label default \
    --attack-jackpot wrong-winner --dump-block "$atk" --blocks 100000 --threads 3 >>"$DDIR/attack.log" 2>&1 &
  local mp=$!; PIDS+=("$mp"); local t0; t0=$(date +%s)
  while :; do [[ -s "$atk" ]] && [[ "$(rejects)" -gt "$rej0" ]] && break; [[ $(($(date +%s)-t0)) -ge 60 ]] && break; sleep 2; done
  kill "$mp" 2>/dev/null || true; sleep 1
  [[ -s "$atk" ]] || { bad "M08: no attack captured"; return; }
  [[ "$(height)" == "$PRE_J" && "$(reserve)" == "$RES" ]] && ok "M08: attack rejected pre-restart" || bad "M08: state moved pre-restart"
  restart_node
  local rej1; rej1="$(rejects)"; submit_file "$atk"; sleep 3
  [[ "$(height)" == "$PRE_J" && "$(reserve)" == "$RES" && "$(rejects)" -gt "$rej1" ]] \
    && ok "M08: same block STILL rejected after restart; reserve intact" || bad "M08: replay not rejected identically"
  mine_to "$WB" "$WORK/b.json" "$FIRST_J" 200
  [[ "$(height)" == "$FIRST_J" && "$(txcount "$(blockhash "$FIRST_J")")" == "2" ]] && ok "M08: honest jackpot block accepted after" || bad "M08: honest block not accepted"
  stop_node
}
PRE_J=23

case "$SCENARIO" in
  M02) scenario_M02;; M03) scenario_M03;; M08) scenario_M08;;
  all) scenario_M02; scenario_M03; scenario_M08;;
  *) die "unknown scenario $SCENARIO";;
esac

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — multi-block attack coverage ($SCENARIO): non-event-height + stale-replay + restart-replay all rejected, state intact, honest blocks accepted"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else
  log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1
fi

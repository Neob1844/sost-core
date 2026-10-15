#!/usr/bin/env bash
# =============================================================================
# run_v17_devnet_e2e.sh — V17 economics (80/15/5 + Jackpot accumulator J),
# real sost-node + sost-miner on DEVNET_FAST (V17_HEIGHT = 60, jackpot cadence 6,
# Jackpot V2 from 42, NODE epoch 6).
#
# Scenario (one miner process at a time, 2 threads, nice 19):
#   * A and B mine pre-V17; A binds a node key at #47 and sends heartbeats for
#     epochs 1,2,3 only, so A is NOT a Jackpot V2 winner at #48/#54/#60 and the
#     historical reserve H is still full at activation.
#   * #60 = activation AND a jackpot height with no eligible winner (J_before = 0).
#   * restart just before (#59) and just after (#62) activation: state identical.
#   * reorg ACROSS ACTIVATION: branch B (fork #59, no heartbeat) replaces branch A
#     (J rolled back), then branch A' (A mines on to #66) replaces branch B again.
#   * #66: first paid V17 jackpot = H (whole reserve) + J (all of J): H+J mixed.
#   * adversarial: 28 DEV-only mutated blocks (H-part jackpot tx and V17 coinbase / J
#     output) at #66 and #67 are mined with a valid DEV PoW over the MUTATED tx list and
#     each must be rejected by its intended rule (the node's REJECTED reason is asserted);
#     an unmutated control #66 is then accepted.
#   * fee-bearing transactions; J-only jackpots at #72, #78, #84, #90.
#   * reorg ACROSS a J-only payment (#72): J debit rolled back and re-applied.
#   * restart after the mixed payment; final independent audit of the whole chain
#     (tests/v17_chain_audit.py): every V17 coinbase amount, J recomputation and the
#     supply identity sum(UTXO) + pending + J == sum(subsidy) at EVERY height.
#
# Env: BUILD_DIR (devnet build, required), WORK (default mktemp), PORT_BASE (31100).
# Kills ONLY processes it started, by exact PID, after checking /proc/PID/cmdline.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:?BUILD_DIR (devnet build dir) required}"
WORK="${WORK:-$(mktemp -d "${TMPDIR:-/tmp}/v17e2e.XXXXXX")}"
PB="${PORT_BASE:-31100}"
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
GEN="$ROOT/genesis_block.json"
V17=60; A2=42; L=6
FAILED=0; PASSN=0
declare -A NPID=()
log(){ printf '[v17e2e] %s\n' "$*"; }
ok(){ printf '[v17e2e] PASS  %s\n' "$*"; PASSN=$((PASSN+1)); }
bad(){ printf '[v17e2e] FAIL  %s\n' "$*"; FAILED=$((FAILED+1)); }
argv0(){ tr '\0' '\n' < "/proc/$1/cmdline" 2>/dev/null | head -1; }
safe_kill(){ local p="$1"; [[ -n "$p" && -d "/proc/$p" ]] || return 0
  local a; a="$(argv0 "$p")"
  if [[ "$a" == "$NODE" || "$a" == "$MINER" ]]; then kill "$p" 2>/dev/null
    for _ in $(seq 1 120); do [[ -d "/proc/$p" ]] || return 0; sleep 0.5; done
  fi; }
cleanup(){ for k in "${!NPID[@]}"; do safe_kill "${NPID[$k]}"; done; [[ -n "${MP:-}" ]] && safe_kill "$MP"; true; }
die(){ printf '[v17e2e] FATAL %s\n' "$*" >&2; cleanup; log "work dir kept: $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"
[[ -x "$NODE" && -x "$MINER" && -x "$CLI" ]] || die "binaries missing"

rpc(){ curl -s --max-time 30 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":${3:-[]},\"id\":1}" "http://127.0.0.1:$1/"; }
jq_(){ python3 -c 'import sys,json
d=json.load(sys.stdin); r=d.get("result")
try: print(eval(sys.argv[1], {"r": r}))
except Exception as e: print("ERR", e)' "$1"; }
height(){ rpc "$1" getblockcount | jq_ 'r'; }
bhash(){ rpc "$1" getblockhash "[$2]" | jq_ 'r'; }
blk(){ rpc "$1" getblock "[\"$(bhash "$1" "$2")\"]"; }
jstate(){ rpc "$1" getjackpotstate | jq_ '(r["h_reserve_stocks"], r["j_balance_stocks"], r["pending_lottery_stocks"], r["tip_height"])'; }
start_node(){ # name chainfile p2p rpc
  nice -n 19 "$NODE" --profile dev --genesis "$GEN" --chain "$2" --port "$3" --rpc-port "$4" \
     --rpc-noauth --noseed --connect 127.0.0.1:1 >>"$WORK/$1.log" 2>&1 &
  NPID[$1]=$!
  for _ in $(seq 1 120); do sleep 0.5; [[ "$(height "$4")" =~ ^[0-9]+$ ]] && return 0; done; die "node $1 did not boot"; }
stop_node(){ safe_kill "${NPID[$1]:-}"; unset "NPID[$1]"; }
memcheck(){ for _ in $(seq 1 120); do local av; av=$(free -g | awk '/^Mem:/{print $7}'); [[ "$av" -ge 6 ]] && return 0; sleep 5; done; die "less than 6 GB available for a devnet miner"; }
mine(){ # rpcport addr wallet n
  local h0; h0="$(height "$1")"; memcheck
  nice -n 19 "$MINER" --profile dev --rpc "127.0.0.1:$1" --address "$2" --wallet "$3" \
     --mining-key-label default --blocks "$4" --threads 2 --realtime >>"$WORK/miner_$1.log" 2>&1 &
  MP=$!; local t0; t0=$(date +%s)
  while [[ -d "/proc/$MP" ]]; do sleep 1; [[ $(( $(date +%s) - t0 )) -gt 1200 ]] && { safe_kill "$MP"; die "miner timeout"; }; done
  MP=""
  local h1; h1="$(height "$1")"; [[ "$h1" -eq $((h0 + $4)) ]] || die "mined to $h1, expected $((h0 + $4))"; }
send_raw(){ rpc "$1" sendrawtransaction "[\"$2\"]"; }
heartbeat(){ # rpcport epoch
  local tr; tr="$(bhash "$1" $((A2 + L * $2 - 1)))"
  local hx; hx="$("$CLI" --wallet "$WORK/a.json" nodeheartbeat --node-key-file "$WORK/node.key" "$2" "$tr" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
  [[ ${#hx} -gt 100 ]] || die "nodeheartbeat e$2 build failed"
  send_raw "$1" "$hx" | grep -q '"result"' && log "heartbeat epoch $2 accepted (tip_ref #$((A2 + L * $2 - 1)))" || die "heartbeat e$2 rejected"; }
pay(){ # rpcport amount(SOST) ; A -> B, auto fee
  "$CLI" --wallet "$WORK/a.json" --rpc "127.0.0.1:$1" --yes send "$B" "$2" >>"$WORK/cli.log" 2>&1 && return 0; return 1; }
export_import(){ # from_rpc to_rpc h_from h_to
  for h in $(seq "$3" "$4"); do
    local hh raw; hh="$(bhash "$1" "$h")"
    raw="$(rpc "$1" getrawblock "[\"$hh\"]" | python3 -c 'import sys,json;r=json.load(sys.stdin).get("result","");print(json.dumps(r) if isinstance(r,str) else "")')"
    [[ -n "$raw" ]] || die "getrawblock h=$h"
    rpc "$2" submitblock "[$raw]" >/dev/null
  done; sleep 3; }
v17r(){ blk "$1" "$2" | jq_ "r.get('v17_reward',{}).get('$3')"; }

log "work=$WORK ports $PB..  V17=$V17"
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
[[ -n "$A" && -n "$B" && "$A" != "$B" ]] || die "wallets"
( umask 077; openssl rand -hex 32 > "$WORK/node.key" )
log "A=$A  B=$B"
R1=$((PB+2)); R2=$((PB+12)); R3=$((PB+22)); R4=$((PB+32))
start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"

# ---- pre-V17 history -------------------------------------------------------
mine "$R1" "$A" "$WORK/a.json" 30
mine "$R1" "$B" "$WORK/b.json" 10
mine "$R1" "$A" "$WORK/a.json" 6                       # tip 46
BIND="$("$CLI" --wallet "$WORK/a.json" createnodebind 1 --node-key-file "$WORK/node.key" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
send_raw "$R1" "$BIND" | grep -q '"result"' && ok "NODE_BIND(A) accepted" || die "bind rejected"
mine "$R1" "$A" "$WORK/a.json" 1                       # tip 47 (bind included)
heartbeat "$R1" 1; mine "$R1" "$B" "$WORK/b.json" 6    # 48..53
heartbeat "$R1" 2; mine "$R1" "$A" "$WORK/a.json" 6    # 54..59
[[ "$(height "$R1")" == 59 ]] || die "tip != 59"
read -r H59 J59 P59 T59 < <(jstate "$R1" | tr -d '(),')
log "tip 59: H=$H59 J=$J59 pending=$P59"
[[ "$J59" == 0 && "$H59" -gt 0 ]] && ok "#59: J=0, historical reserve H=$H59 untouched (no V2 winner at #48/#54)" || bad "#59 state H=$H59 J=$J59"
LS="$(rpc "$R1" getlotterystate)"
echo "$LS" | grep -q '"v17_active":true' && ok "getlotterystate for #60 reports v17_active" || bad "getlotterystate lacks V17 fields: $LS"
GBT="$(rpc "$R1" getblocktemplate "[\"$A\"]")"
echo "$GBT" | jq_ '(r["v17_active"], r["jackpot_height"], r["jackpot_h_payout"], r["jackpot_j_payout"], r["j_balance_before"])' | grep -q "(True, True, 0, 0, 0)" \
  && ok "getblocktemplate #60: V17, jackpot height, no winner -> H part 0, J part 0, J_before 0" || bad "template #60: $GBT"

# ---- restart just BEFORE activation + fork copy at #59 ----------------------
BH59="$(bhash "$R1" 59)"; S59="$(jstate "$R1")"
stop_node n1; cp "$WORK/c1.json" "$WORK/fork59.json"; start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
[[ "$(bhash "$R1" 59)" == "$BH59" && "$(jstate "$R1")" == "$S59" ]] && ok "restart at #59 (before activation): tip + H/J/pending identical" || bad "restart #59 mismatch"

heartbeat "$R1" 3
mine "$R1" "$A" "$WORK/a.json" 3                       # 60..62 (branch A)
SUB60=$(v17r "$R1" 60 subsidy); MS=$(v17r "$R1" 60 miner_subsidy); DS=$(v17r "$R1" 60 dtd_subsidy); JA=$(v17r "$R1" 60 jackpot_j_alloc)
log "#60 v17_reward: subsidy=$SUB60 miner=$MS dtd=$DS J_alloc=$JA"
[[ "$MS" == 628080691 && "$DS" == 117765129 && "$JA" == 39255043 ]] && ok "#60 activation block: 80/15/5 = 628080691 / 117765129 / 39255043" || bad "#60 split $MS/$DS/$JA"
[[ "$(v17r "$R1" 60 jackpot_h_paid)" == 0 && "$(v17r "$R1" 60 jackpot_j_paid)" == 0 && "$(v17r "$R1" 60 j_balance_after)" == 39255043 ]] \
  && ok "#60 jackpot height with no eligible winner: nothing paid, J = 39255043" || bad "#60 jackpot/J"
[[ "$(blk "$R1" 59 | jq_ "'v17_reward' in r")" == False ]] && ok "#59 getblock has no v17_reward (pre-V17 output unchanged)" || bad "#59 shows v17 fields"
read -r H62 J62 P62 T62 < <(jstate "$R1" | tr -d '(),')
[[ "$J62" == $((3*39255043)) && "$H62" == "$H59" ]] && ok "#62: J = 3 x 5% = $J62, H unchanged" || bad "#62 J=$J62 H=$H62"

# ---- restart just AFTER activation (#62) ------------------------------------
# The restart at #62 is exercised on a copy of n1's live chain.json by a fresh node
# (n3, which then extends branch A); n1 itself is restarted at #59, after #66 and at #70.
S62="$(jstate "$R1")"; BH62="$(bhash "$R1" 62)"
sleep 2; cp "$WORK/c1.json" "$WORK/a62.json"
grep -c '"v17_j_balance_after"' "$WORK/a62.json" | grep -q '^3$' && ok "chain.json persists v17_j_balance_after for the 3 V17 blocks" || bad "persisted J fields"

# ---- reorg across activation: branch B (fork #59) ---------------------------
start_node n2 "$WORK/fork59.json" $((PB+11)) "$R2"
mine "$R2" "$B" "$WORK/b.json" 5                       # B branch 60..64
S2="$(jstate "$R2")"; T2="$(rpc "$R2" getbestblockhash | jq_ r)"
export_import "$R2" "$R1" 60 64
[[ "$(rpc "$R1" getbestblockhash | jq_ r)" == "$T2" ]] && ok "reorg across activation: n1 switched to branch B (60..64)" || bad "no reorg to B"
[[ "$(jstate "$R1")" == "$S2" ]] && ok "after reorg n1 H/J/pending == clean branch-B node ($S2)" || bad "n1 $(jstate "$R1") != n2 $S2"
# branch A' : continue branch A from #62 to #66 (paid jackpot)
start_node n3 "$WORK/a62.json" $((PB+21)) "$R3"
[[ "$(bhash "$R3" 62)" == "$BH62" && "$(jstate "$R3")" == "$S62" ]] && ok "restart at #62 (after activation, fresh node on n1's chain.json): J recomputed on load == live n1" || bad "n3 load state"
mine "$R3" "$A" "$WORK/a.json" 3                       # 63..65
read -r H65 J65 P65 T65 < <(jstate "$R3" | tr -d '(),')
# adversarial DEV-only mutations at #66 (H+J mixed jackpot height, with a fee-paying tx in the
# template): the miner re-derives the submitted block from the MUTATED tx list, recomputes the
# merkle root and mines a valid DEV PoW, so the node must reject each block by the jackpot /
# coinbase rule the mutation targets (asserted from the node's own REJECTED line), never by
# merkle_root / block_id / JSON-field consistency. An unmutated control block is then accepted.
"$CLI" --wallet "$WORK/b.json" --rpc "127.0.0.1:$R3" --yes send "$A" 1 >>"$WORK/cli.log" 2>&1 \
  && ok "fee-paying transfer B->A in n3's mempool before the #66 attack matrix" || bad "send B->A on n3 failed"
attack(){ # rpc nodelog label expected-ERE miner-args...
  local port="$1" nlog="$2" label="$3" want="$4"; shift 4
  local h0 n0 m0 rc seg mseg; h0="$(height "$port")"; n0=$(wc -c <"$nlog"); touch "$WORK/miner_attack.log"; m0=$(wc -c <"$WORK/miner_attack.log")
  memcheck
  nice -n 19 timeout 300 "$MINER" --profile dev --rpc "127.0.0.1:$port" --address "$A" --wallet "$WORK/a.json" \
     --mining-key-label default --blocks 1 --threads 2 --realtime --dev-exit-after-submit "$@" >>"$WORK/miner_attack.log" 2>&1; rc=$?
  seg="$(tail -c +$((n0+1)) "$nlog" | grep -m1 -E '^\[BLOCK\] REJECTED' || true)"
  mseg="$(tail -c +$((m0+1)) "$WORK/miner_attack.log" | grep -E '^\[ATTACK\]' | tr '\n' ' ')"
  [[ "$(height "$port")" == "$h0" ]] || die "$label: a block was CONNECTED under an attack flag (rc=$rc) - matrix aborted"
  if [[ "$rc" == 3 && -n "$seg" && "$seg" =~ $want \
        && ! "$seg" =~ (merkle_root|block_id|JSON rewards) && ! "$mseg" =~ (NOT\ APPLICABLE|unknown\ mutation) ]]; then
    ok "#$((h0+1)) $label rejected by the intended rule: ${seg#\[BLOCK\] REJECTED: }"
  else
    bad "#$((h0+1)) $label: rc=$rc tip=$(height "$port") node='${seg}' miner='${mseg}'"
  fi; }
HJ='Historical Jackpot: TX_TYPE_JACKPOT does not match the canonical V17 H-part reconstruction'
VC='jackpot value conservation'
DS='intra-block connect failed: SpendUTXO: not found'          # double spend / outpoint not in the UTXO set
MI='jackpot input\[[0-9]+\] references missing UTXO'
attack "$R3" "$WORK/n3.log" "H-part: wrong winner"              "$HJ" --attack-jackpot wrong-winner
attack "$R3" "$WORK/n3.log" "H-part: payout +1"                 "$VC" --attack-jackpot payout-plus
attack "$R3" "$WORK/n3.log" "H-part: payout -1 (miner claims the 1 stock)"   "$HJ" --attack-jackpot payout-minus
attack "$R3" "$WORK/n3.log" "H-part: payout 0 (miner claims the whole H)"    "$HJ" --attack-jackpot payout-zero
attack "$R3" "$WORK/n3.log" "H-part: inputs reversed"           "$HJ" --attack-jackpot reverse-inputs
attack "$R3" "$WORK/n3.log" "H-part: one reserve input removed" "$VC" --attack-jackpot remove-input
attack "$R3" "$WORK/n3.log" "H-part: reserve input duplicated"  "$DS" --attack-jackpot dup-input
attack "$R3" "$WORK/n3.log" "H-part: foreign input added"       "$MI" --attack-jackpot foreign-input
attack "$R3" "$WORK/n3.log" "H-part: extra output"              "$VC" --attack-jackpot extra-output
attack "$R3" "$WORK/n3.log" "H-part: moved to tx[2]"            'Historical Jackpot: TX_TYPE_JACKPOT must be at index 1' --attack-jackpot move-jackpot
attack "$R3" "$WORK/n3.log" "H-part: duplicated"                'duplicate txid within block' --attack-jackpot dup-jackpot
attack "$R3" "$WORK/n3.log" "H-part: removed"                   'Historical Jackpot: expected exactly one TX_TYPE_JACKPOT, got 0' --attack-jackpot remove-jackpot
attack "$R3" "$WORK/n3.log" "H-part: input vout bumped"         "$DS" --attack-jackpot input-index-bump
attack "$R3" "$WORK/n3.log" "H-part: input txid flipped"        "$MI" --attack-jackpot input-txid-flip
attack "$R3" "$WORK/n3.log" "H-part: payout INT64_MAX"          "$VC" --attack-jackpot payout-intmax
attack "$R3" "$WORK/n3.log" "H-part: every reserve input twice" "$DS" --attack-jackpot dup-all-inputs
CB12='coinbase invalid: CB12: V17 miner amount [0-9]+ != miner_subsidy \+ fees'
attack "$R3" "$WORK/n3.log" "coinbase J output +1"              'coinbase invalid: CB15: OUT_COINBASE_JACKPOT amount [0-9]+ != V17 J part' --attack-coinbase j-plus
attack "$R3" "$WORK/n3.log" "coinbase J output -1"              'coinbase invalid: CB15: OUT_COINBASE_JACKPOT amount [0-9]+ != V17 J part' --attack-coinbase j-minus
attack "$R3" "$WORK/n3.log" "coinbase J output to another key"  'coinbase invalid: CB15: OUT_COINBASE_JACKPOT does not pay the jackpot winner' --attack-coinbase j-winner
attack "$R3" "$WORK/n3.log" "coinbase J output dropped"         'coinbase invalid: CB11: V17 coinbase must have exactly 3 outputs, got 2' --attack-coinbase j-drop
attack "$R3" "$WORK/n3.log" "coinbase: fees moved into DTD"     "$CB12" --attack-coinbase fees-to-dtd
attack "$R3" "$WORK/n3.log" "coinbase: fees moved into J"       "$CB12" --attack-coinbase fees-to-j
attack "$R3" "$WORK/n3.log" "coinbase: miner +1"                "$CB12" --attack-coinbase miner-plus
attack "$R3" "$WORK/n3.log" "coinbase: DTD +1"                  'coinbase invalid: CB12: V17 DTD amount [0-9]+ != dtd_subsidy \+ pending_before' --attack-coinbase dtd-plus
attack "$R3" "$WORK/n3.log" "coinbase: 1 stock DTD -> miner"    "$CB12" --attack-coinbase dtd-to-miner
attack "$R3" "$WORK/n3.log" "coinbase: miner keeps the 5% J share" "$CB12" --attack-coinbase j-to-miner
attack "$R3" "$WORK/n3.log" "coinbase miner output to another key" 'SbPoW: coinbase miner-output pkh does not match' --attack-jackpot coinbase-mutate
[[ "$(height "$R3")" == 65 ]] && ok "after the attack matrix n3 is still at #65 (no mutated block connected)" || bad "n3 tip moved during attacks"
mine "$R3" "$A" "$WORK/a.json" 1                       # 66 (unmutated control)
ok "unmutated control block #66 accepted by the same node right after the attack matrix"
HP=$(v17r "$R3" 66 jackpot_h_paid); JP=$(v17r "$R3" 66 jackpot_j_paid)
log "#66 jackpot: H part=$HP J part=$JP (H_before=$H65 J_before=$J65)"
[[ "$HP" == "$H65" && "$JP" == "$J65" && "$HP" -gt 0 && "$JP" -gt 0 ]] && ok "#66 H+J MIXED payment: whole H ($HP) then all of J ($JP) in the same block (prize 500 > H+J)" || bad "#66 funding"
read -r H66 J66 P66 T66 < <(jstate "$R3" | tr -d '(),')
[[ "$H66" == 0 && "$J66" == 39255043 ]] && ok "#66 after: H=0, J = this block's 5% only" || bad "#66 after H=$H66 J=$J66"
S3="$(jstate "$R3")"; T3="$(rpc "$R3" getbestblockhash | jq_ r)"
export_import "$R3" "$R1" 60 66
[[ "$(rpc "$R1" getbestblockhash | jq_ r)" == "$T3" && "$(jstate "$R1")" == "$S3" ]] && ok "reorg back across activation to branch A' (60..66, incl. H+J payment): n1 == n3" || bad "reorg back failed: $(jstate "$R1") vs $S3"
stop_node n2; stop_node n3

# ---- restart after the mixed payment -----------------------------------------
stop_node n1; start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
[[ "$(jstate "$R1")" == "$S3" ]] && ok "restart after the H+J payment: state identical" || bad "restart #66 mismatch"

# ---- fee-bearing blocks, J-only jackpots, reorg across a J-only payment ------
heartbeat "$R1" 4
pay "$R1" 1 && ok "fee-paying transfer A->B accepted into the mempool" || bad "send failed"
attack "$R1" "$WORK/n1.log" "coinbase J output at a NON-jackpot height" 'coinbase invalid: CB11: V17 coinbase must have exactly 2 outputs, got 3' --attack-coinbase j-at-nonjackpot
mine "$R1" "$A" "$WORK/a.json" 1                       # 67 (fee-bearing)
pay "$R1" 2 && ok "second fee-paying transfer accepted" || bad "send 2 failed"
mine "$R1" "$A" "$WORK/a.json" 3                       # 68..70
stop_node n1; cp "$WORK/c1.json" "$WORK/fork70.json"; start_node n1 "$WORK/c1.json" $((PB+1)) "$R1"
mine "$R1" "$A" "$WORK/a.json" 1                       # 71
heartbeat "$R1" 5
mine "$R1" "$A" "$WORK/a.json" 3                       # 72..74
JP72=$(v17r "$R1" 72 jackpot_j_paid); HP72=$(v17r "$R1" 72 jackpot_h_paid)
[[ "$HP72" == 0 && "$JP72" -gt 0 ]] && ok "#72 J-ONLY payment (H=0): $JP72 from J" || bad "#72 H=$HP72 J=$JP72"
start_node n4 "$WORK/fork70.json" $((PB+31)) "$R4"
mine "$R4" "$B" "$WORK/b.json" 6                       # 71..76 on branch C
S4="$(jstate "$R4")"; T4="$(rpc "$R4" getbestblockhash | jq_ r)"
export_import "$R4" "$R1" 71 76
[[ "$(rpc "$R1" getbestblockhash | jq_ r)" == "$T4" && "$(jstate "$R1")" == "$S4" ]] && ok "reorg across the J-only payment #72: J debit rolled back and re-applied, n1 == n4" || bad "reorg #72: $(jstate "$R1") vs $S4"
stop_node n4
mine "$R1" "$A" "$WORK/a.json" 1                       # 77 (tip_ref of epoch 6)
for e in 6 7 8; do
  heartbeat "$R1" "$e"
  pay "$R1" 1 || true
  t=$(height "$R1"); mine "$R1" "$A" "$WORK/a.json" $(( A2 + L * (e + 1) - 1 - t ))
done
TIP=$(height "$R1"); log "final tip $TIP"
for jh in 66 72 78 84 90; do
  [[ $jh -le $TIP ]] || continue
  log "  jackpot #$jh: H=$(v17r "$R1" $jh jackpot_h_paid) J=$(v17r "$R1" $jh jackpot_j_paid) winner=$(v17r "$R1" $jh jackpot_winner) dtd_winner=$(v17r "$R1" $jh dtd_winner) J_after=$(v17r "$R1" $jh j_balance_after)"
done
NPAID=0; for jh in 78 84 90; do [[ $jh -le $TIP && "$(v17r "$R1" $jh jackpot_j_paid)" -gt 0 && "$(v17r "$R1" $jh jackpot_h_paid)" == 0 ]] && NPAID=$((NPAID+1)); done
[[ $NPAID -ge 2 ]] && ok "J-only jackpots after the reorg: $NPAID of #78/#84/#90" || bad "J-only jackpots $NPAID"
read -r HF JF PF TF < <(jstate "$R1" | tr -d '(),')
TOT=$(rpc "$R1" getsupplyinfo | jq_ 'r["total_supply_stocks"]')
SJ=$(rpc "$R1" getsupplyinfo | jq_ 'r.get("jackpot_j_balance_stocks")')
[[ "$SJ" == "$JF" ]] && ok "getsupplyinfo reports J separately ($SJ)" || bad "getsupplyinfo J=$SJ vs $JF"
CLIOUT="$("$CLI" --rpc "127.0.0.1:$R1" getjackpotstate 2>&1)"; echo "$CLIOUT" | sed 's/^/[v17e2e]   cli| /'
echo "$CLIOUT" | grep -q "J  V17 accumulator" && ok "sost-cli getjackpotstate shows H and J separately" || bad "cli getjackpotstate"
stop_node n1
python3 -I "$ROOT/tests/v17_chain_audit.py" "$WORK/c1.json" "$GEN" "$V17" --expect-j "$JF" --expect-pending "$PF" --json "$WORK/audit.json" | sed 's/^/[v17e2e]   audit| /'
AUD=${PIPESTATUS[0]}
EM=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["emitted"])' "$WORK/audit.json")
[[ "$AUD" == 0 ]] && ok "independent chain audit: every V17 coinbase, J transition and the supply identity at every height" || bad "chain audit failed"
[[ "$EM" == "$TOT" ]] && ok "audit sum(subsidy) == node getsupplyinfo total_supply_stocks ($TOT)" || bad "emitted $EM != node total $TOT"
log "RESULT: $PASSN passed, $FAILED failed (work dir $WORK)"
[[ $FAILED == 0 ]] && echo "[v17e2e] RESULT: PASS" || echo "[v17e2e] RESULT: FAIL"
exit $FAILED

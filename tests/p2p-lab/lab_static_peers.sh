#!/usr/bin/env bash
# 3-node static-peer P2P lab (DEVNET_FAST, Profile::DEV). Asserts the behaviour of this branch:
# block + tx propagation over 2 hops, no relay starvation after +70 blocks, restart/reconnect,
# per-target redial, frozen peer. Nodes run WITHOUT a SIGPIPE mask (the fix must hold on its own).
# Against unmodified v16.3.0 the starvation/redial assertions FAIL (see docs/p2p/STATIC_PEERS_LAB.md).
set -uo pipefail
ulimit -f unlimited
# Env: LAB_DIR (work dir, default mktemp), BUILD (DEVNET_FAST build dir with sost-node/miner/cli),
#      GENESIS (genesis_block.json). Every process is started and killed by PID; ports 1896x/1996x.
S="${LAB_DIR:-$(mktemp -d)}"
B="${BUILD:?set BUILD to a SOST_DEVNET_FORKS=ON build dir}"
GEN="${GENESIS:-$(cd "$(dirname "$0")/../.." && pwd)/genesis_block.json}"
W=$S/lab; rm -rf "$W"; mkdir -p "$W"/{A,B,C}
declare -A RPCP=([A]=18961 [B]=18962 [C]=18963) P2PP=([A]=19961 [B]=19962 [C]=19963) PID=()
MINER_PID=""
PASS=0; FAIL=0
ok(){ echo "PASS  $*"; PASS=$((PASS+1)); }
bad(){ echo "FAIL  $*"; FAIL=$((FAIL+1)); }
log(){ echo "----  $*"; }
cleanup(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; for n in A B C; do [[ -n "${PID[$n]:-}" ]] && kill -CONT "${PID[$n]}" 2>/dev/null; [[ -n "${PID[$n]:-}" ]] && kill "${PID[$n]}" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT

rpc(){ curl -s --max-time 10 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":${3:-[]},\"id\":1}" "http://127.0.0.1:${RPCP[$1]}/"; }
res(){ python3 -c 'import sys,json
try: r=json.load(sys.stdin).get("result"); print(json.dumps(r) if isinstance(r,(dict,list)) else r)
except Exception: print("")'; }
height(){ rpc "$1" getblockcount | res; }
tip(){ rpc "$1" getbestblockhash | res; }
npeers(){ rpc "$1" getpeerinfo | python3 -c 'import sys,json
try: print(sum(1 for p in json.load(sys.stdin)["result"] if p.get("version_acked")))
except Exception: print(-1)'; }
peers(){ rpc "$1" getpeerinfo | python3 -c 'import sys,json
try: print(" ".join("%s/%s/h%s"%(p["addr"],p["direction"][:3],p.get("height")) for p in json.load(sys.stdin)["result"]))
except Exception: print("?")'; }
start(){ # start <node> [connect targets...]
  local n=$1; shift; local args=()
  if [[ $# -eq 0 ]]; then args+=(--connect 127.0.0.1:1); else for t in "$@"; do args+=(--connect "$t"); done; fi
  "$B/sost-node" --profile dev --genesis "$GEN" --chain "$W/$n/chain.json" --wallet "$W/$n/wallet.json" \
     --port "${P2PP[$n]}" --rpc-port "${RPCP[$n]}" --rpc-noauth --p2p-enc on "${args[@]}" >>"$W/$n/node.log" 2>&1 &
  PID[$n]=$!
  for _ in $(seq 1 30); do sleep 1; [[ -n "$(height $n)" ]] && return 0; done; bad "node $n did not answer RPC"; return 1; }
stopnode(){ kill "${PID[$1]}" 2>/dev/null; wait "${PID[$1]}" 2>/dev/null; PID[$1]=""; }
waitfor(){ # waitfor <secs> <cmd...>
  local t=$1; shift; local end=$(( $(date +%s) + t )); while (( $(date +%s) < end )); do "$@" && return 0; sleep 1; done; return 1; }
converged(){ local a b c; a=$(tip A); b=$(tip B); c=$(tip C); [[ -n "$a" && "$a" == "$b" && "$b" == "$c" ]]; }
converged2(){ local x y; x=$(tip "$1"); y=$(tip "$2"); [[ -n "$x" && "$x" == "$y" ]]; }
state(){ for n in A B C; do [[ -n "${PID[$n]:-}" ]] && echo "      $n h=$(height $n) tip=$(tip $n | cut -c1-12) peers=[$(peers $n)]"; done; }

ADDR=$("$B/sost-cli" --wallet "$W/miner.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)
DEST=$("$B/sost-cli" --wallet "$W/dest.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)
log "miner $ADDR   dest $DEST"

log "PHASE 1 — topology A <- B <- C (static --connect only, line topology)"
start A || exit 1
start B localhost:19961
sleep 31   # inbound per-IP cooldown is 30 s and every lab node shares 127.0.0.1
start C localhost:19962
waitfor 20 bash -c "[[ \$(curl -s -H 'content-type: application/json' --data '{\"method\":\"getpeerinfo\",\"params\":[],\"id\":1}' http://127.0.0.1:18963/ | grep -c version_acked\\\":true) -ge 1 ]]"
state
[[ $(npeers A) -ge 1 && $(npeers B) -ge 2 && $(npeers C) -ge 1 ]] && ok "handshake: A=1 B=2 C=1 acked peers (encrypted)" || bad "handshake counts A=$(npeers A) B=$(npeers B) C=$(npeers C)"
grep -q "encryption established" "$W/C/node.log" && ok "C<->B X25519+ChaCha20 session established" || bad "no encryption on C"

log "PHASE 2 — block propagation: miner submits ONLY to A; B and C must get blocks by P2P"
"$B/sost-miner" --profile dev --rpc 127.0.0.1:18961 --address "$ADDR" --wallet "$W/miner.json" \
   --mining-key-label default --blocks 100000 --threads 4 >"$W/miner.log" 2>&1 &
MINER_PID=$!
waitfor 240 bash -c "[[ \$(curl -s -H 'content-type: application/json' --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' http://127.0.0.1:18961/ | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"result\"])') -ge 12 ]]" || bad "A did not reach 12"
waitfor 30 converged && ok "tip converged A=B=C at h=$(height A) $(tip A | cut -c1-16)" || bad "no convergence"; state
# per-height hash equality over the whole chain, not just the tip
H=$(height A); mism=0
for h in $(seq 0 "$H"); do a=$(rpc A getblockhash "[$h]"|res); b=$(rpc B getblockhash "[$h]"|res); c=$(rpc C getblockhash "[$h]"|res); [[ "$a" == "$b" && "$b" == "$c" ]] || mism=$((mism+1)); done
[[ $mism -eq 0 ]] && ok "all $((H+1)) block hashes identical on A, B, C" || bad "$mism heights differ"
nb=$(grep -c "Accepted\|accepted" "$W/C/node.log"); relayB=$(grep -c "Broadcasting block" "$W/B/node.log")
[[ $relayB -gt 0 ]] && ok "B relayed $relayB blocks onward (C never talks to A)" || bad "B relayed nothing"
# latency: time between A's accept log and C's accept of the same height is visible in logs; measure live
h0=$(height C); t0=$(date +%s%N)
waitfor 120 bash -c "[[ \$(curl -s -H 'content-type: application/json' --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' http://127.0.0.1:18963/ | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"result\"])') -gt $h0 ]]"
waitfor 10 converged && ok "next block reached C (2 hops) and all tips equal" || bad "next block not converged"

log "PHASE 3 — transaction propagation A -> B -> C (mempool on every node before it is mined)"
kill -STOP "$MINER_PID"   # freeze mining so the tx sits in the mempools where we can see it
sleep 2
( timeout 60 "$B/sost-cli" --wallet "$W/miner.json" --node 127.0.0.1:18961 --yes --skip-warning send "$DEST" 1.5 > "$W/send.out" 2>&1 ) &
SENDP=$!
waitfor 30 grep -q 'TXID:' "$W/send.out"
TXID=$(grep 'TXID:' "$W/send.out" | grep -oiE '[0-9a-f]{64}' | head -1)
echo "      send: $(head -c 200 "$W/send.out" | tr '\n' ' ')"
echo "      A getrawmempool raw: $(rpc A getrawmempool | cut -c1-200)"
if [[ -n "$TXID" ]]; then
  inpool(){ rpc "$1" getrawmempool | grep -q "$TXID"; }
  waitfor 20 inpool A && ok "tx $(echo $TXID|cut -c1-16) in A mempool" || bad "tx not in A mempool"
  waitfor 20 inpool B && ok "tx reached B mempool by P2P" || bad "tx not in B mempool"
  waitfor 20 inpool C && ok "tx reached C mempool by P2P (2 hops)" || bad "tx not in C mempool"
else bad "could not create tx"; fi
kill -CONT "$MINER_PID"
if [[ -n "$TXID" ]]; then
  gone(){ ! rpc "$1" getrawmempool | grep -q "$TXID"; }
  waitfor 180 bash -c "! curl -s -H 'content-type: application/json' --data '{\"method\":\"getrawmempool\",\"params\":[],\"id\":1}' http://127.0.0.1:18963/ | grep -q $TXID" \
    && waitfor 15 converged && ok "tx mined; removed from all mempools; tips equal h=$(height A)" || bad "tx not confirmed everywhere"
  rpc C getrawtransaction "[\"$TXID\"]" | grep -q result && ok "C can serve the confirmed tx" || echo "      (note) getrawtransaction on C: $(rpc C getrawtransaction "[\"$TXID\"]" | cut -c1-120)"
fi

log "PHASE 3b — long run: >50 blocks with B, C connected since their handshake (relay-skip heuristic)"
echo "      A's view of B: [$(peers A)]"
hs=$(height A); waitfor 600 bash -c "[[ \$(curl -s -H 'content-type: application/json' --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' http://127.0.0.1:18961/ | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"result\"])') -ge $((hs+70)) ]]" || bad "A did not mine 70 more blocks"
sleep 5
echo "      after +70: A h=$(height A) B h=$(height B) C h=$(height C);  A's view: [$(peers A)]"
waitfor 30 converged && ok "FIXED: B and C still in sync after +70 blocks (no starvation)" || bad "STARVATION: A=$(height A) B=$(height B) C=$(height C)"

log "PHASE 4 — restart the middle node B (A and C keep running; mining continues)"
stopnode B; sleep 3
echo "      after B stop: A peers=$(npeers A)  C peers=$(npeers C)"
hA=$(height A); waitfor 180 bash -c "[[ \$(curl -s -H 'content-type: application/json' --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' http://127.0.0.1:18961/ | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"result\"])') -ge $((hA+3)) ]]"
echo "      while B down: A h=$(height A)  C h=$(height C)  (C isolated: its only peer was B)"
start B localhost:19961
waitfor 60 converged2 A B && ok "B restarted from its own chain.json, reconnected to A, caught up (h=$(height B))" || bad "B did not catch up"
waitfor 90 converged && ok "C auto-reconnected to B (zero-peer reconnect loop, <=30 s tick) and caught up h=$(height C)" || bad "C did not reconnect/catch up"; state

log "PHASE 5 — peer unavailable at start + partial loss (C configured with A AND B)"
stopnode C; sleep 31
start C localhost:19961 localhost:19962 localhost:19999
grep -q "Cannot connect to localhost:19999" "$W/C/node.log" && ok "unreachable static peer is skipped, node starts normally" || bad "no 'Cannot connect' for dead peer"
waitfor 30 bash -c "[[ \$(curl -s -H 'content-type: application/json' --data '{\"method\":\"getpeerinfo\",\"params\":[],\"id\":1}' http://127.0.0.1:18963/ | grep -o version_acked\\\":true | wc -l) -ge 2 ]]" && ok "C mesh: connected to A and B (A<->C direct)" || bad "C has <2 peers: [$(peers C)]"
waitfor 30 converged && ok "tips equal with triangle A-B-C" || bad "triangle not converged"; state
log "      kill A (the miner's node). C still has B -> does C redial A when A returns?"
kill -STOP "$MINER_PID"; stopnode A; sleep 5
echo "      C peers now: [$(peers C)]"
start A
sleep 70   # > two 30 s reconnect ticks
cA=$(rpc C getpeerinfo | grep -c ':19961'); bA=$(rpc B getpeerinfo | grep -c ':19961')
[[ $cA -ge 1 ]] && ok "FIXED: C redialled A while still connected to B (per-target redial)" || bad "C did not redial A"
[[ $bA -ge 1 ]] && ok "FIXED: B redialled A -> A is not isolated" || bad "B did not redial A"
echo "      A peers=$(npeers A)"
kill -CONT "$MINER_PID"
hA=$(height A); waitfor 120 bash -c "[[ \$(curl -s -H 'content-type: application/json' --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' http://127.0.0.1:18961/ | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"result\"])') -ge $((hA+2)) ]]"
waitfor 30 converged && ok "FIXED: mining resumed on A and B, C follow (no split) h=$(height A)" || bad "split: A=$(height A) B=$(height B) C=$(height C)"
log "      recovery: restart B (its --connect points at A) -> mesh heals"
stopnode B; sleep 31; start B localhost:19961
waitfor 90 converged && ok "after B restart: all tips equal h=$(height A)" || bad "not healed: A=$(height A) B=$(height B) C=$(height C)"; state

log "PHASE 6 — stale (frozen) peer: SIGSTOP B for 90 s while blocks flow A->C"
kill -STOP "${PID[B]}"
hA=$(height A); waitfor 150 bash -c "[[ \$(curl -s -H 'content-type: application/json' --data '{\"method\":\"getblockcount\",\"params\":[],\"id\":1}' http://127.0.0.1:18961/ | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"result\"])') -ge $((hA+2)) ]]"
sleep 20
echo "      frozen B still listed by A? $(rpc A getpeerinfo | grep -c ':19962\|inbound') entries   A h=$(height A) C h=$(height C)"
waitfor 20 converged2 A C && ok "A and C keep converging with a frozen peer attached" || bad "frozen B stalled A/C"
kill -CONT "${PID[B]}"
waitfor 90 converged && ok "B thawed and caught up; all tips equal h=$(height A)" || bad "B did not recover after thaw: B=$(height B) A=$(height A)"; state

log "PHASE 7 — duplicate connections"
echo "      A: [$(peers A)]"
echo "      B: [$(peers B)]"
echo "      C: [$(peers C)]"

kill "$MINER_PID"; MINER_PID=""
echo; echo "RESULT: $PASS pass, $FAIL fail   (logs in $W)"

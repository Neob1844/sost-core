#!/usr/bin/env bash
# =============================================================================
# run_v162_upgrade_inplace.sh — the upgrade an operator actually performs.
#
# run_v162_equivalence.sh proves the two releases AGREE. This proves the
# migration itself: a chain written by v16.1.0, stopped, its binary swapped for
# v16.2.0, restarted on the SAME chain file — same tip, no reindex, and mining
# continues. Then it goes back: v16.1.0 reopens the chain v16.2.0 wrote, which
# is what makes the published rollback real rather than hopeful.
#
#   Env: V161_DIR, V162_DIR (devnet builds), both defaulting to the release tree
# =============================================================================
set -Euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V161_DIR="${V161_DIR:-/home/sost/SOST/sostcore/rel-v161-a/build-devnet}"
V162_DIR="${V162_DIR:-/home/sost/SOST/sostcore/rel-v162-a/build-devnet}"
WORK="$(mktemp -d /tmp/v162up.XXXXXX)"
P2P=$(( (RANDOM % 9000) + 36000 )); RPC=$(( P2P + 1 ))
FAILED=0
ok(){  printf '[upgrade] PASS  %s\n' "$*"; }
bad(){ printf '[upgrade] FAIL  %s\n' "$*"; FAILED=1; }
log(){ printf '[upgrade] %s\n' "$*"; }
NODE_PID=""
cleanup(){ [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; true; }
trap cleanup EXIT
for f in "$V161_DIR/sost-node" "$V162_DIR/sost-node" "$V161_DIR/sost-miner" "$V162_DIR/sost-miner" "$V162_DIR/sost-cli"; do
  [[ -x "$f" ]] || { echo "[upgrade] FATAL missing $f"; exit 1; }
done

rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
        --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC/"; }
hgt(){ rpc getblockcount | python3 -c 'import sys,json
try: print(json.load(sys.stdin)["result"])
except Exception: print("")'; }
tip(){ local h; h="$(hgt)"; [[ -z "$h" ]] && { echo ""; return; }
       rpc getblockhash "[$h]" | grep -oE '[a-f0-9]{64}' | head -1; }

start_node(){ # start_node <dir> <tag>
  "$1/sost-node" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
    --port "$P2P" --rpc-port "$RPC" --rpc-noauth --connect 127.0.0.1:1 >>"$WORK/node_$2.log" 2>&1 &
  NODE_PID=$!
  for _ in $(seq 1 40); do sleep 1; [[ -n "$(hgt)" ]] && return 0; done
  return 1
}
stop_node(){ [[ -n "$NODE_PID" ]] && { kill "$NODE_PID" 2>/dev/null; wait "$NODE_PID" 2>/dev/null; NODE_PID=""; }; true; }
mine(){ # mine <dir> <n> <wallet> <tag>
  "$1/sost-miner" --profile dev --rpc "127.0.0.1:$RPC" --address "$4" \
    --wallet "$3" --mining-key-label default --blocks "$2" --threads 3 >>"$WORK/miner.log" 2>&1
}

log "1. a chain written by v16.1.0"
start_node "$V161_DIR" v161 || { bad "v16.1.0 node did not start"; exit 1; }
ADDR="$("$V162_DIR/sost-cli" --wallet "$WORK/w.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
mine "$V161_DIR" 12 "$WORK/w.json" "$ADDR"
H161="$(hgt)"; T161="$(tip)"
log "   v16.1.0 wrote up to height $H161 (tip ${T161:0:16})"
[[ "${H161:-0}" -ge 12 ]] && ok "v16.1.0 produced a chain to mine on" || bad "v16.1.0 did not mine"

log "2. stop, swap the binary, restart on the SAME chain file"
stop_node
CHAIN_MD5_BEFORE=$(md5sum "$WORK/chain.json" | cut -d' ' -f1)
start_node "$V162_DIR" v162 || { bad "v16.2.0 did not start on the v16.1.0 chain"; exit 1; }
H_AFTER="$(hgt)"; T_AFTER="$(tip)"
[[ "$H_AFTER" == "$H161" && "$T_AFTER" == "$T161" ]] \
  && ok "v16.2.0 reopened the chain at the same height and the same tip ($H_AFTER)" \
  || bad "height/tip changed across the upgrade: $H161/$T161 -> $H_AFTER/$T_AFTER"
# grep -c exits 1 when the count is zero, and zero is the result we want here,
# so the count is captured rather than piped into a test.
NOISE=$(grep -ciE 'reindex|rebuilding|corrupt|INVALID' "$WORK/node_v162.log" || true)
[[ "${NOISE:-0}" -eq 0 ]] \
  && ok "no reindex, no corruption report" \
  || { bad "the upgraded node reported $NOISE suspicious line(s)"; grep -iE 'reindex|corrupt|INVALID' "$WORK/node_v162.log" | head -3; }

log "3. mining continues under the new binary"
mine "$V162_DIR" 6 "$WORK/w.json" "$ADDR"
H162="$(hgt)"
[[ "${H162:-0}" -gt "$H_AFTER" ]] && ok "the upgraded node accepted $((H162-H_AFTER)) new blocks (height $H162)" \
                                 || bad "mining did not continue after the upgrade"

log "4. the blocks v16.1.0 wrote still hash the same under v16.2.0"
MIS=0
for h in $(seq 0 "$H161"); do
  [[ -z "$(rpc getblockhash "[$h]" | grep -oE '[a-f0-9]{64}')" ]] && MIS=$((MIS+1))
done
[[ $MIS -eq 0 ]] && ok "all $((H161+1)) pre-upgrade heights are readable under the new binary" \
                 || bad "$MIS pre-upgrade heights unreadable"

log "5. ROLLBACK — v16.1.0 reopens the chain v16.2.0 extended"
stop_node
start_node "$V161_DIR" v161_back || { bad "v16.1.0 could NOT reopen the chain (rollback broken)"; exit 1; }
H_BACK="$(hgt)"; T_BACK="$(tip)"
[[ "$H_BACK" == "$H162" ]] && ok "v16.1.0 reopened it at the same height ($H_BACK) — the rollback is real" \
                           || bad "rollback height mismatch: $H162 -> $H_BACK"
mine "$V161_DIR" 2 "$WORK/w.json" "$ADDR"
[[ "$(hgt)" -gt "$H_BACK" ]] && ok "and it keeps mining after the rollback (height $(hgt))" \
                             || bad "mining did not resume after the rollback"
stop_node

log "logs in $WORK (chain md5 before the swap: ${CHAIN_MD5_BEFORE:0:12})"
[[ $FAILED -eq 0 ]] && { echo "[upgrade] === UPGRADE AND ROLLBACK BOTH WORK ==="; exit 0; } \
                    || { echo "[upgrade] === UPGRADE PATH BROKEN ==="; exit 1; }

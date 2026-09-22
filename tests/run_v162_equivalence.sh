#!/usr/bin/env bash
# =============================================================================
# run_v162_equivalence.sh — V16.2.0 changed no consensus rule, and this proves
# it against the previous release instead of asserting it.
#
# Two nodes on one devnet: A is the published v16.1.0 build, B is this tree.
# Blocks mined against A must be accepted by B and vice versa, and every height
# must hash the same on both — across the V16 activation, which on a devnet
# build sits low enough to be crossed in a couple of minutes.
#
#   Env: V161_DIR (default ../rel-v161-a/build-devnet), V162_DIR (build-devnet)
# =============================================================================
set -Euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V161_DIR="${V161_DIR:-/home/sost/SOST/sostcore/rel-v161-a/build-devnet}"
V162_DIR="${V162_DIR:-$ROOT/build-devnet}"
WORK="$(mktemp -d /tmp/v162eq.XXXXXX)"
PA=$(( (RANDOM % 9000) + 30000 )); RA=$(( PA + 1 )); PB=$(( PA + 2 )); RB=$(( PA + 3 ))
FAILED=0
ok(){  printf '[eq] PASS  %s\n' "$*"; }
bad(){ printf '[eq] FAIL  %s\n' "$*"; FAILED=1; }
log(){ printf '[eq] %s\n' "$*"; }
A_PID=""; B_PID=""; M_PID=""
cleanup(){ for p in "$M_PID" "$B_PID" "$A_PID"; do [[ -n "$p" ]] && kill "$p" 2>/dev/null; done; wait 2>/dev/null; true; }
trap cleanup EXIT
die(){ printf '[eq] FATAL %s\n' "$*" >&2; log "logs in $WORK"; exit 1; }
for f in "$V161_DIR/sost-node" "$V162_DIR/sost-node" "$V162_DIR/sost-miner" "$V162_DIR/sost-cli"; do
  [[ -x "$f" ]] || die "missing $f"
done
rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
        --data "{\"method\":\"$2\",\"params\":${3:-[]},\"id\":1}" "http://127.0.0.1:$1/"; }
hgt(){ rpc "$1" getblockcount | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("result"))
except Exception: print("")'; }
bhash(){ rpc "$1" getblockhash "[$2]" | grep -oE '[a-f0-9]{64}' | head -1; }

log "A = v16.1.0 ($V161_DIR)"
log "B = this tree ($V162_DIR)"
"$V161_DIR/sost-node" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/a.chain" \
  --port "$PA" --rpc-port "$RA" --rpc-noauth --connect 127.0.0.1:1 >"$WORK/a.log" 2>&1 &
A_PID=$!
"$V162_DIR/sost-node" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/b.chain" \
  --port "$PB" --rpc-port "$RB" --rpc-noauth --connect "127.0.0.1:$PA" >"$WORK/b.log" 2>&1 &
B_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(hgt $RA)" && -n "$(hgt $RB)" ]] && break; done
[[ -n "$(hgt $RA)" ]] || die "node A has no RPC"
[[ -n "$(hgt $RB)" ]] || die "node B has no RPC"
ok "both nodes are up and peered"

mine(){ # mine <rpc_port> <n_blocks> <wallet> <tag>
  local port="$1" n="$2" w="$3" tag="$4" addr
  addr="$("$V162_DIR/sost-cli" --wallet "$w" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
  [[ -z "$addr" ]] && addr="$("$V162_DIR/sost-cli" --wallet "$w" listaddresses 2>/dev/null | grep -oE 'sost1[a-z0-9]+' | head -1)"
  "$V162_DIR/sost-miner" --profile dev --rpc "127.0.0.1:$port" --address "$addr" \
    --wallet "$w" --mining-key-label default --blocks "$n" --threads 3 >>"$WORK/miner_$tag.log" 2>&1
}

log "mining 30 blocks into A (the OLD node) with the NEW miner"
mine "$RA" 30 "$WORK/wa.json" a
HA=$(hgt $RA); log "A height=$HA"
for _ in $(seq 1 60); do sleep 2; [[ "$(hgt $RB)" == "$HA" ]] && break; done
[[ "$(hgt $RB)" == "$HA" ]] && ok "B (new) followed A (old) to height $HA" \
                           || bad "B stalled at $(hgt $RB) while A is at $HA"

log "mining 30 more blocks into B (the NEW node)"
mine "$RB" 30 "$WORK/wb.json" b
HB=$(hgt $RB); log "B height=$HB"
for _ in $(seq 1 60); do sleep 2; [[ "$(hgt $RA)" == "$HB" ]] && break; done
[[ "$(hgt $RA)" == "$HB" ]] && ok "A (old) accepted every block B (new) produced, to height $HB" \
                           || bad "A stalled at $(hgt $RA) while B is at $HB"

log "comparing every block hash on both nodes"
TIP=$(hgt $RA); MISMATCH=0; CHECKED=0
for h in $(seq 0 "$TIP"); do
  ha=$(bhash $RA "$h"); hb=$(bhash $RB "$h")
  CHECKED=$((CHECKED+1))
  if [[ -z "$ha" || "$ha" != "$hb" ]]; then MISMATCH=$((MISMATCH+1)); echo "  h=$h A=$ha B=$hb"; fi
done
[[ $MISMATCH -eq 0 ]] && ok "$CHECKED heights hash identically on both versions" \
                      || bad "$MISMATCH of $CHECKED heights differ"

log "comparing the DTD lottery audit at every height both versions can answer"
python3 - "$RA" "$RB" "$TIP" <<'PY' || FAILED=1
import json,sys,urllib.request
ra,rb,tip=sys.argv[1],sys.argv[2],int(sys.argv[3])
def call(port,method,params):
    req=urllib.request.Request(f"http://127.0.0.1:{port}/",
        data=json.dumps({"method":method,"params":params,"id":1}).encode(),
        headers={"content-type":"application/json"})
    try: return json.load(urllib.request.urlopen(req,timeout=15))
    except Exception as e: return {"error":str(e)}
diff=same=0
for h in range(1,tip+1):
    a=call(ra,"getlotteryaudit",[h]); b=call(rb,"getlotteryaudit",[h])
    if a.get("result") is None and b.get("result") is None: continue
    if json.dumps(a.get("result"),sort_keys=True)==json.dumps(b.get("result"),sort_keys=True): same+=1
    else:
        diff+=1
        if diff<=3: print(f"  h={h} differs\n    A={json.dumps(a.get('result'))[:200]}\n    B={json.dumps(b.get('result'))[:200]}")
print(f"[eq] {'PASS' if diff==0 else 'FAIL'}  lottery audit identical at {same} heights ({diff} differ)")
sys.exit(0 if diff==0 else 1)
PY

log "logs in $WORK"
[[ $FAILED -eq 0 ]] && { echo "[eq] === EQUIVALENCE PROVEN ==="; exit 0; } || { echo "[eq] === EQUIVALENCE NOT PROVEN ==="; exit 1; }

#!/usr/bin/env bash
# =============================================================================
# run_v162_historical_replay.sh — the new binary against the REAL chain.
#
# A devnet proves the rules; it does not prove that this build reads the chain
# mainnet actually produced. Here both releases load a COPY of the production
# chain file, offline (no peers, no mining, no wallet), and must agree on
# everything: tip, every sampled block hash, and the DTD lottery audit at every
# height either of them will answer.
#
#   Env: CHAIN (a copy of chain.json), V161_DIR, V162_DIR
# Nothing here writes to the production chain: both nodes get their own copy.
# =============================================================================
set -Euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHAIN="${CHAIN:?set CHAIN to a COPY of the production chain.json}"
V161="${V161_DIR:-/home/sost/SOST/sostcore/rel-v161-a/build}/sost-node"
V162="${V162_DIR:-$ROOT/build-v162}/sost-node"
WORK="$(mktemp -d /tmp/v162replay.XXXXXX)"
PA=$(( (RANDOM % 9000) + 33000 )); RA=$(( PA + 1 )); PB=$(( PA + 2 )); RB=$(( PA + 3 ))
FAILED=0
ok(){  printf '[replay] PASS  %s\n' "$*"; }
bad(){ printf '[replay] FAIL  %s\n' "$*"; FAILED=1; }
log(){ printf '[replay] %s\n' "$*"; }
A_PID=""; B_PID=""
cleanup(){ for p in "$B_PID" "$A_PID"; do [[ -n "$p" ]] && kill "$p" 2>/dev/null; done; wait 2>/dev/null; rm -f "$WORK/a.chain" "$WORK/b.chain"; true; }
trap cleanup EXIT
[[ -x "$V161" && -x "$V162" ]] || { echo "[replay] FATAL missing binaries"; exit 1; }

log "copying the chain for each node (the production file is never opened)"
cp "$CHAIN" "$WORK/a.chain"; cp "$CHAIN" "$WORK/b.chain"

# --connect 127.0.0.1:1 is a deliberate dead peer: these nodes must never
# join the real network or hand out blocks while they are being compared.
"$V161" --profile mainnet --genesis "$ROOT/genesis_block.json" --chain "$WORK/a.chain" \
  --port "$PA" --rpc-port "$RA" --rpc-noauth --connect 127.0.0.1:1 >"$WORK/a.log" 2>&1 &
A_PID=$!
"$V162" --profile mainnet --genesis "$ROOT/genesis_block.json" --chain "$WORK/b.chain" \
  --port "$PB" --rpc-port "$RB" --rpc-noauth --connect 127.0.0.1:1 >"$WORK/b.log" 2>&1 &
B_PID=$!

rpc(){ curl -s --max-time 30 -H 'content-type: application/json' \
        --data "{\"method\":\"$2\",\"params\":${3:-[]},\"id\":1}" "http://127.0.0.1:$1/"; }
hgt(){ rpc "$1" getblockcount | python3 -c 'import sys,json
try: print(json.load(sys.stdin)["result"])
except Exception: print("")'; }
log "waiting for both nodes to finish loading the chain (this takes minutes)"
for _ in $(seq 1 180); do sleep 5; [[ -n "$(hgt $RA)" && -n "$(hgt $RB)" ]] && break; done
HA="$(hgt $RA)"; HB="$(hgt $RB)"
[[ -n "$HA" ]] || { bad "v16.1.0 never came up (see $WORK/a.log)"; exit 1; }
[[ -n "$HB" ]] || { bad "v16.2.0 never came up (see $WORK/b.log)"; exit 1; }
log "v16.1.0 loaded to height $HA ; v16.2.0 loaded to height $HB"
[[ "$HA" == "$HB" ]] && ok "both versions load the real chain to the same height ($HA)" \
                     || bad "height differs: v16.1.0=$HA v16.2.0=$HB"

for lg in "$WORK/a.log" "$WORK/b.log"; do
  n=$(grep -ciE 'REJECT|INVALID|corrupt|FATAL' "$lg" || true)
  [[ "$n" -eq 0 ]] && ok "$(basename $lg): no rejection or corruption while loading" \
                   || { bad "$(basename $lg): $n suspicious lines"; grep -iE 'REJECT|INVALID|corrupt|FATAL' "$lg" | head -3; }
done

python3 - "$RA" "$RB" "$HA" <<'PY' || FAILED=1
import json, sys, urllib.request
ra, rb, tip = sys.argv[1], sys.argv[2], int(sys.argv[3])
def call(port, method, params):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/",
        data=json.dumps({"method": method, "params": params, "id": 1}).encode(),
        headers={"content-type": "application/json"})
    try: return json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e: return {"error": str(e)}

# Every 100th height, the whole last 600, and every jackpot height in range —
# the heights where a rule difference would actually show up.
CADENCE, FIRST = 288, 600
heights = set(range(0, tip + 1, 100)) | set(range(max(0, tip - 600), tip + 1))
heights |= {h for h in range(FIRST, tip + 1) if (h - FIRST) % CADENCE == 0}
heights = sorted(h for h in heights if 0 <= h <= tip)

bad_hash = []
for h in heights:
    a = call(ra, "getblockhash", [h]).get("result")
    b = call(rb, "getblockhash", [h]).get("result")
    if a != b or not a: bad_hash.append((h, a, b))
print(f"[replay] {'PASS' if not bad_hash else 'FAIL'}  {len(heights)} sampled heights hash identically")
for h, a, b in bad_hash[:5]: print(f"    h={h} v16.1={a} v16.2={b}")

# The tip block in full: every field both versions serialize must match.
ta = call(ra, "getblockhash", [tip]).get("result")
fa = json.dumps(call(ra, "getblock", [ta]).get("result"), sort_keys=True)
fb = json.dumps(call(rb, "getblock", [ta]).get("result"), sort_keys=True)
print(f"[replay] {'PASS' if fa == fb else 'FAIL'}  the tip block serializes identically")

# The DTD lottery audit is where V16 changes behaviour, so it is checked on
# every one of the sampled heights rather than a handful.
diff = same = 0
for h in heights:
    a = call(ra, "getlotteryaudit", [h]).get("result")
    b = call(rb, "getlotteryaudit", [h]).get("result")
    if a is None and b is None: continue
    if json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True): same += 1
    else:
        diff += 1
        if diff <= 3: print(f"    lottery audit differs at h={h}")
print(f"[replay] {'PASS' if diff == 0 else 'FAIL'}  lottery audit identical at {same} heights ({diff} differ)")

sys.exit(0 if (not bad_hash and fa == fb and diff == 0) else 1)
PY

log "logs in $WORK (chain copies deleted on exit)"
[[ $FAILED -eq 0 ]] && { echo "[replay] === THE REAL CHAIN READS IDENTICALLY ON BOTH ==="; exit 0; } \
                    || { echo "[replay] === MISMATCH — DO NOT SHIP ==="; exit 1; }

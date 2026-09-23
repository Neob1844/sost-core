#!/usr/bin/env bash
# =============================================================================
# audit_v162_rbf.sh — cancel-tx / bump-fee, the last path that still read the
# node's answer by scanning text.
#
# It matters because of what the numbers do: every vin's prev_value is summed
# into total_in, and `total_in - bumped_fee` is what the replacement sends back
# to the wallet. A vin the parser silently dropped is coins handed to the fee.
#
# The old parser: found "fee" from offset 0 (any earlier field of that name
# won), delimited a vin by the first '}' (one nested object truncated the
# list), and called std::stoll on whatever followed a key — which throws, and
# uncaught that aborts the process.
#
# A fake node serves each of those shapes. No wallet of yours is opened, no key
# is loaded, nothing is signed and nothing is broadcast.
#
#   Env: BIN (directory with sost-cli)
# =============================================================================
set -Euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${BIN:-/home/sost/SOST/sostcore/rel-v1621-a/build}"
CLI="$BIN/sost-cli"
W="$(mktemp -d /tmp/v162rbf.XXXXXX)"
PORT=$(( (RANDOM % 9000) + 43000 ))
PASS=0; FAIL=0
ok(){  printf '  [PASS] %s\n' "$*"; PASS=$((PASS+1)); }
bad(){ printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
SRV_PID=""
cleanup(){ [[ -n "$SRV_PID" ]] && kill "$SRV_PID" 2>/dev/null; wait 2>/dev/null; true; }
trap cleanup EXIT
[[ -x "$CLI" ]] || { echo "FATAL: no $CLI"; exit 1; }
echo "binary under audit: $(sha256sum "$CLI" | cut -c1-24)"

TXID=$(printf 'ab%.0s' {1..32})
ADDR=$("$CLI" --wallet "$W/w.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)
# The vins are credited to a DIFFERENT throwaway wallet, so the run always stops
# at the ownership check. Nothing is ever signed with a key this test controls,
# let alone broadcast.
FOREIGN=$("$CLI" --wallet "$W/foreign.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)

cat > "$W/fake.py" <<'PY'
import http.server, json, socketserver, sys
MODE_FILE = sys.argv[2]; TXID = sys.argv[3]; ADDR = sys.argv[4]
def vin(prev_value=500000, addr=None, nested=False, drop_value=False):
    v = {"txid": "cd"*32, "vout": 0, "prev_address": addr or ADDR, "prev_type": 0}
    if nested:                       # a nested object BEFORE prev_value
        v["script"] = {"asm": "x", "hex": "00"}
    if not drop_value:
        v["prev_value"] = prev_value
    return v
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get('content-length', 0))
        req = json.loads(self.rfile.read(n) or b'{}')
        method = req.get("method", "")
        mode = open(MODE_FILE).read().strip()
        if method == "getrawmempool":
            body = json.dumps({"jsonrpc":"2.0","id":1,"result":[TXID]}).encode()
            if mode == "mempool_garbage": body = b'{"jsonrpc":"2.0","id":1,"result":'
        elif method == "getrawtransaction":
            tx = {"txid": TXID, "size": 300, "fee": 300, "vin": [vin(), vin()], "vout": []}
            if mode == "fee_string":   tx["fee"] = "300"
            elif mode == "fee_null":   tx["fee"] = None
            elif mode == "no_size":    tx.pop("size")
            elif mode == "vin_novalue": tx["vin"] = [vin(), vin(drop_value=True)]
            elif mode == "vin_nested":  tx["vin"] = [vin(nested=True), vin(nested=True)]
            elif mode == "vin_empty":   tx["vin"] = []
            elif mode == "truncated":
                body = json.dumps({"jsonrpc":"2.0","id":1,"result":tx}).encode()[:120]
                self.send_response(200); self.send_header('content-length', str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            body = json.dumps({"jsonrpc":"2.0","id":1,"result":tx}).encode()
        else:
            body = json.dumps({"jsonrpc":"2.0","id":1,"result":0}).encode()
        self.send_response(200); self.send_header('content-type','application/json')
        self.send_header('content-length', str(len(body))); self.end_headers(); self.wfile.write(body)
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", int(sys.argv[1])), H) as s: s.serve_forever()
PY
echo ok > "$W/mode"
python3 "$W/fake.py" "$PORT" "$W/mode" "$TXID" "$FOREIGN" >/dev/null 2>&1 &
SRV_PID=$!
sleep 2

run(){ echo "$1" > "$W/mode"
  "$CLI" --wallet "$W/w.json" --rpc "127.0.0.1:$PORT" --rpc-user u --rpc-pass p \
     cancel-tx "$TXID" > "$W/out" 2>&1; echo $?; }

echo
echo "=== a malformed answer must stop the replacement, not skew it ==="
rc=$(run truncated)
grep -qi "getrawtransaction failed" "$W/out" && ok "a truncated transaction body is refused (exit $rc)" \
                                             || { bad "truncated body not refused"; head -3 "$W/out"; }
rc=$(run fee_string)
grep -qi "no integer size/fee" "$W/out" && ok "a fee delivered as a STRING is refused, not coerced (exit $rc)" \
                                        || { bad "string fee accepted"; head -3 "$W/out"; }
rc=$(run fee_null)
grep -qi "no integer size/fee" "$W/out" && ok "a null fee is refused (exit $rc)" \
                                        || { bad "null fee mishandled"; head -3 "$W/out"; }
grep -qiE "segmentation|core dumped|terminate called|std::invalid_argument" "$W/out" \
  && bad "...but it crashed doing so" || ok "...without throwing (the old std::stoll path aborted here)"
rc=$(run no_size)
grep -qi "no integer size/fee" "$W/out" && ok "a missing size is refused (exit $rc)" \
                                        || { bad "missing size accepted"; head -3 "$W/out"; }
rc=$(run vin_empty)
grep -qi "missing or empty vin" "$W/out" && ok "an empty vin[] is refused (exit $rc)" \
                                         || { bad "empty vin accepted"; head -3 "$W/out"; }
rc=$(run vin_novalue)
grep -qi "missing prev_value" "$W/out" && ok "one vin without prev_value refuses the WHOLE plan (exit $rc)" \
                                       || { bad "partial input set accepted"; head -3 "$W/out"; }
rc=$(run mempool_garbage)
grep -qi "Refusing to replace" "$W/out" && ok "an unreadable mempool answer is not 'the tx is gone' (exit $rc)" \
                                        || { bad "unreadable mempool misread"; head -3 "$W/out"; }

echo
echo "=== a vin carrying a nested object: the case that truncated the old parser ==="
rc=$(run vin_nested)
# Both vins belong to a throwaway address this wallet does not own, so the run
# must reach the OWNERSHIP check — which proves both vins were parsed. The old
# parser stopped at the nested object's '}' and reported a missing prev_value.
if grep -qi "not in this wallet" "$W/out"; then
  ok "both vins parsed through the nested object (it reaches the ownership check)"
elif grep -qi "missing prev_value" "$W/out"; then
  bad "the nested object still truncates the vin (old behaviour)"
else
  bad "unexpected outcome (exit $rc)"; head -4 "$W/out"
fi
grep -qi "Cannot sign a replacement" "$W/out" && ok "...and it refuses to sign what it does not own" \
                                               || bad "no ownership refusal"

printf '\n=== %d passed, %d failed ===\n' "$PASS" "$FAIL"
echo "logs: $W"
[[ $FAIL -eq 0 ]] || exit 1

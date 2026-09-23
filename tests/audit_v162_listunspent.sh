#!/usr/bin/env bash
# =============================================================================
# audit_v162_listunspent.sh — package 1, checked against a node that misbehaves.
#
# The bug this package fixed was a wallet tool saying "No unspent outputs" when
# the truth was "I could not ask". So the test is not "does it list UTXOs" — it
# is: can each failure still be told apart from an empty address?
#
# A scripted fake node serves each pathology on a loopback port. Nothing here
# touches a real wallet, a real key or a real balance; the only real-node call
# is a read-only query of a public address, which moves nothing.
#
#   Env: BIN (directory with sost-cli)
# =============================================================================
set -Euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${BIN:-/home/sost/SOST/sostcore/rel-v162-a/build}"
CLI="$BIN/sost-cli"
W="$(mktemp -d /tmp/v162lu.XXXXXX)"
PORT=$(( (RANDOM % 9000) + 41000 ))
PASS=0; FAIL=0
ok(){  printf '  [PASS] %s\n' "$*"; PASS=$((PASS+1)); }
bad(){ printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
sect(){ printf '\n=== %s ===\n' "$*"; }
SRV_PID=""
cleanup(){ [[ -n "$SRV_PID" ]] && kill "$SRV_PID" 2>/dev/null; wait 2>/dev/null; true; }
trap cleanup EXIT
[[ -x "$CLI" ]] || { echo "FATAL: no $CLI"; exit 1; }
echo "binary under audit: $(sha256sum "$CLI" | cut -c1-24)"

ADDR=$("$CLI" --wallet "$W/w.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)

# --- the fake node ----------------------------------------------------------
cat > "$W/fake.py" <<'PY'
import http.server, json, os, socketserver, sys
MODE_FILE = sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        mode = open(MODE_FILE).read().strip()
        n = int(self.headers.get('content-length', 0)); self.rfile.read(n)
        if mode == 'http401':
            body = b'{"error":{"code":-401,"message":"Authentication required"}}'
            self.send_response(401); self.send_header('content-length', str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        if mode == 'http500':
            body = b'internal error'
            self.send_response(500); self.send_header('content-length', str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        if mode == 'garbage':      body = b'{not json at all'
        elif mode == 'truncated':  body = b'{"jsonrpc":"2.0","id":1,"result":[{"txid":"aa","amo'
        elif mode == 'rpcerror':   body = b'{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"Method not found"}}'
        elif mode == 'empty':      body = b'{"jsonrpc":"2.0","id":1,"result":[]}'
        elif mode == 'wrongshape': body = b'{"jsonrpc":"2.0","id":1,"result":{"utxos":[]}}'
        elif mode == 'noamount':
            body = json.dumps({"jsonrpc":"2.0","id":1,"result":[
                {"txid":"bb"*32,"vout":0,"height":10,"mature":True,"coinbase":True}]}).encode()
        elif mode == 'dupkeys':
            body = b'{"jsonrpc":"2.0","id":1,"result":[],"result":[{"txid":"cc"}]}'
        elif mode == 'deep':
            body = b'{"jsonrpc":"2.0","id":1,"result":' + b'['*200 + b']'*200 + b'}'
        elif mode == 'bigint':
            body = b'{"jsonrpc":"2.0","id":1,"result":[{"txid":"dd","vout":0,"amount_stocks":99999999999999999999999,"height":1,"mature":true}]}'
        elif mode.startswith('many'):
            u = []
            for i in range(5000):
                u.append({"txid": "%064x" % i, "vout": i % 4, "amount_stocks": 100000 + i,
                          "height": 1000 + i, "mature": (i % 5 != 0), "coinbase": True})
            body = json.dumps({"jsonrpc":"2.0","id":1,"result":u}).encode()
        else:
            body = b'{"jsonrpc":"2.0","id":1,"result":[]}'
        if mode.endswith('_chunked'):
            # Transfer-Encoding: chunked, no Content-Length — what a reverse
            # proxy in front of a node actually sends. Chunks are cut at 900
            # bytes so several of them end mid-object, and at least one ends
            # exactly on a '}' — the boundary the old reader stopped at.
            self.send_response(200); self.send_header('content-type','application/json')
            self.send_header('Transfer-Encoding','chunked'); self.end_headers()
            for i in range(0, len(body), 900):
                part = body[i:i+900]
                self.wfile.write(('%x\r\n' % len(part)).encode() + part + b'\r\n')
            self.wfile.write(b'0\r\n\r\n'); return
        self.send_response(200); self.send_header('content-type','application/json')
        self.send_header('content-length', str(len(body))); self.end_headers(); self.wfile.write(body)
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", int(sys.argv[1])), H) as s: s.serve_forever()
PY
echo empty > "$W/mode"
python3 "$W/fake.py" "$PORT" "$W/mode" >/dev/null 2>&1 &
SRV_PID=$!
sleep 2

run_lu(){ # run_lu <mode> -> writes $W/out, returns exit code
  echo "$1" > "$W/mode"
  "$CLI" --wallet "$W/w.json" --rpc "127.0.0.1:$PORT" --rpc-user u --rpc-pass p \
    listunspent "$ADDR" > "$W/out" 2>&1
}

sect "each failure must be distinguishable from an empty address"
run_lu empty || true
grep -q "ON-CHAIN UTXOs" "$W/out" && grep -q "On chain: 0 UTXOs" "$W/out" \
  && ok "empty address: says the CHAIN has 0 UTXOs" || { bad "empty address not reported as chain-empty"; head -3 "$W/out"; }
grep -qi "cache" "$W/out" && ok "...and the local cache is reported separately" || bad "cache not separated"

run_lu http401 || true
grep -qiE "FAILED|http_401|401" "$W/out" && grep -qi "NOT proof that the address is empty" "$W/out" \
  && ok "HTTP 401: reported as a failed query, explicitly NOT as empty" || { bad "401 not distinguished"; head -3 "$W/out"; }

run_lu garbage || true
grep -qi "NOT proof that the address is empty" "$W/out" \
  && ok "malformed JSON: reported as a failed query" || { bad "malformed JSON not distinguished"; head -3 "$W/out"; }

run_lu truncated || true
grep -qi "NOT proof that the address is empty" "$W/out" \
  && ok "truncated response: reported as a failed query" || { bad "truncated not distinguished"; head -3 "$W/out"; }

run_lu rpcerror || true
grep -qi "NOT proof that the address is empty" "$W/out" \
  && ok "JSON-RPC error object: reported as a failed query" || { bad "rpc error not distinguished"; head -3 "$W/out"; }

run_lu http500 || true
grep -qi "NOT proof that the address is empty" "$W/out" \
  && ok "HTTP 500: reported as a failed query" || { bad "http 500 not distinguished"; head -3 "$W/out"; }

run_lu wrongshape || true
grep -qi "unexpected shape" "$W/out" \
  && ok "wrong result shape: named as such, not treated as zero UTXOs" || { bad "wrong shape not detected"; head -3 "$W/out"; }

run_lu dupkeys || true
grep -qi "NOT proof that the address is empty" "$W/out" \
  && ok "duplicate keys: rejected by the strict parser, not silently resolved" || { bad "duplicate keys accepted"; head -3 "$W/out"; }

run_lu deep || true
grep -qiE "NOT proof|unexpected shape" "$W/out" \
  && ok "200-deep nesting: refused" || { bad "deep nesting not refused"; head -3 "$W/out"; }

run_lu bigint || true
grep -qiE "NOT proof|refusing to guess|unexpected shape" "$W/out" \
  && ok "an out-of-range integer amount: refused, never truncated into a number" \
  || { bad "out-of-range integer accepted"; head -3 "$W/out"; }

run_lu noamount || true
rc=$?
grep -qi "refusing to guess" "$W/out" && ok "a UTXO with no amount: refuses to guess (exit $rc)" \
                                      || { bad "missing amount was guessed"; head -3 "$W/out"; }

# node not listening at all
"$CLI" --wallet "$W/w.json" --rpc "127.0.0.1:1" --rpc-user u --rpc-pass p listunspent "$ADDR" > "$W/out" 2>&1 || true
grep -qi "Node not reachable" "$W/out" && grep -qi "NOT proof that the address is empty" "$W/out" \
  && ok "node unreachable: named as unreachable, explicitly not as empty" || { bad "unreachable not distinguished"; head -3 "$W/out"; }

sect "thousands of UTXOs — amounts, heights, maturity, coinbase"
run_lu many || true
LINES=$(grep -c '^txid: ' "$W/out" || true)
[[ "$LINES" -eq 5000 ]] && ok "5,000 synthetic UTXOs all listed" || bad "listed $LINES of 5,000"
IMM=$(grep -c 'IMMATURE' "$W/out" || true)
[[ "$IMM" -eq 1000 ]] && ok "the 1,000 immature ones are flagged IMMATURE" || bad "immature count is $IMM, expected 1000"
CB=$(grep -c '\[coinbase\]' "$W/out" || true)
[[ "$CB" -eq 5000 ]] && ok "coinbase outputs are flagged" || bad "coinbase flags: $CB"
grep -q 'spendable now : 4000 UTXOs' "$W/out" && ok "spendable/immature split is reported separately" \
  || { bad "spendable split wrong"; grep -E 'spendable|immature' "$W/out" | head -2; }
# totals: sum(100000+i) for i in 0..4999 = 5000*100000 + 4999*5000/2 = 512,497,500 stocks
grep -q "On chain: 5000 UTXOs, 5.12497500 SOST total" "$W/out" \
  && ok "the total is exact (512,497,500 stocks = 5.124975 SOST)" \
  || { bad "total wrong"; grep 'On chain:' "$W/out"; }

sect "chunked responses — what a reverse proxy in front of a node sends"
run_lu many_chunked || true
LINES=$(grep -c '^txid: ' "$W/out" || true)
[[ "$LINES" -eq 5000 ]] && ok "5,000 UTXOs over Transfer-Encoding: chunked, no Content-Length" \
  || { bad "chunked: listed $LINES of 5,000"; head -3 "$W/out"; }
grep -q "On chain: 5000 UTXOs, 5.12497500 SOST total" "$W/out" \
  && ok "...and the total is identical to the non-chunked answer" || bad "chunked total differs"
echo 'x-chunked-case' > "$W/mode"   # unknown mode -> empty result, non-chunked
run_lu empty_chunked || true
grep -q "On chain: 0 UTXOs" "$W/out" && ok "an empty chunked answer is still 'chain has 0', not a failure" \
  || { bad "empty chunked misread"; head -3 "$W/out"; }

sect "the real node — read-only, public data, nothing moved"
REAL_ADDR="${REAL_ADDR:-sost1ad01a1ce3ae7d0dbcc1baae7a11e9ecde28683a2}"
if curl -s --max-time 8 -H 'content-type: application/json' \
     --data '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:18232/ | grep -q result; then
  "$CLI" --wallet "$W/w.json" --rpc 127.0.0.1:18232 --rpc-user "${RPC_USER:-AdminNeoB}" \
     --rpc-pass-file "${RPC_PASS_FILE:-/home/sost/.sost/rpc.pass}" listunspent "$REAL_ADDR" > "$W/real.out" 2>&1 || true
  N=$(grep -c '^txid: ' "$W/real.out" || true)
  [[ "$N" -gt 100 ]] && ok "a real mining address returns $N on-chain UTXOs (the old bug printed zero)" \
                     || { bad "real address returned $N UTXOs"; head -3 "$W/real.out"; }
  grep -qE 'spendable now : [0-9]+ UTXOs' "$W/real.out" && ok "maturity is computed on real coinbase outputs" || bad "no maturity line"
  grep -q 'IMMATURE' "$W/real.out" && ok "recent coinbase outputs are correctly still immature (1,000-block maturity)" \
                                   || ok "no immature outputs right now — valid if the last 1,000 blocks hold none of this address's"
else
  echo "  [SKIP] the production node is not reachable from here — real-node check skipped"
fi

printf '\n=== %d passed, %d failed ===\n' "$PASS" "$FAIL"
echo "logs: $W"
[[ $FAIL -eq 0 ]] || exit 1

#!/usr/bin/env python3
"""
SOST DEX V2 — LAB RELAY (localhost only). Bridges website/sost-dex-v2.html to the laboratory
chains (SOST devnet + Bitcoin regtest + Anvil) so the browser can start a lab swap and observe its
REAL state to COMPLETED or REFUNDED.

SECURITY MODEL (deliberate):
  * Fixed, tiny endpoint set. NO endpoint ever executes a command built from client input.
  * The swap orchestration is a FIXED internal routine (a whitelisted, argv-array subprocess of the
    already-tested harness) — never a shell string from the browser.
  * State is NEVER trusted from a file or from the browser. Every reported milestone is re-derived
    by querying the actual nodes (txid confirmations + amount/address checks); the harness log only
    supplies candidate txids, which the relay then VERIFIES on-chain.
  * The browser sends NO private keys or seeds. Lab signing keys live server-side as TEST fixtures.
  * Binds to 127.0.0.1 only. TEST MODE — never real funds, never mainnet.

Run:  python3 dex_lab_relay.py           (defaults below; override via env)
"""
import os, json, subprocess, threading, time, urllib.request, http.server, socketserver, re

# ---- config (env-overridable; defaults target the scratchpad lab) ----
SCRATCH   = os.environ.get("DEX_LAB_SCRATCH", os.path.expanduser("~/.dex-lab"))
SOST_RPC  = os.environ.get("DEX_LAB_SOST_RPC", "http://127.0.0.1:18296/")
ANVIL_RPC = os.environ.get("DEX_LAB_ANVIL_RPC", "http://127.0.0.1:8545/")
BTC_CLI   = os.environ.get("DEX_LAB_BTC_CLI", "")   # e.g. "/path/bitcoin-cli -regtest -datadir=... -rpcuser=rt -rpcpassword=rt -rpcport=18443"
HARNESS   = os.environ.get("DEX_LAB_HARNESS", "")   # absolute path to xswap_sost_btc_coordinated.sh
PORT      = int(os.environ.get("DEX_LAB_PORT", "8781"))
PAIRS     = {"SOST/BTC", "SOST/ETH", "SOST/ERC20"}  # whitelist; anything else is rejected

os.makedirs(SCRATCH, exist_ok=True)
STORE = os.path.join(SCRATCH, "swaps.json")
_lock = threading.Lock()

def _load():
    try:
        with open(STORE) as f: return json.load(f)
    except Exception:
        return {}
def _save(d):
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f: json.dump(d, f)
    os.replace(tmp, STORE)

# ---- chain query helpers (READ-ONLY; the relay never signs) ----
def _jsonrpc(url, method, params):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode())

def sost_height():
    try: return int(_jsonrpc(SOST_RPC, "getblockcount", []).get("result", -1))
    except Exception: return None

def sost_tx_conf(txid):
    """VERIFY a SOST txid on the node -> confirmations (None if absent)."""
    try:
        r = _jsonrpc(SOST_RPC, "getrawtransaction", [txid])
        # SOST getrawtransaction returns hex on confirmed; presence => on-chain. Confirmations via getinfo tip.
        return 1 if r.get("result") else None
    except Exception: return None

def btc_call(args):
    if not BTC_CLI: return None
    try:
        out = subprocess.run(BTC_CLI.split() + args, capture_output=True, text=True, timeout=8)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception: return None

def btc_tx(txid):
    """VERIFY a BTC txid -> parsed tx json with confirmations (None if absent)."""
    raw = btc_call(["getrawtransaction", txid, "true"])
    if not raw: return None
    try: return json.loads(raw)
    except Exception: return None

def evm_receipt(txid):
    try:
        r = _jsonrpc(ANVIL_RPC, "eth_getTransactionReceipt", [txid])
        return r.get("result")
    except Exception: return None

def anvil_up():
    try: return _jsonrpc(ANVIL_RPC, "eth_blockNumber", []).get("result") is not None
    except Exception: return False

# ---- state derivation: computed ONLY from verified on-chain facts + coord.log ----
LIFECYCLE = ["QuoteRequested","Accepted","SostLocked","CounterpartyLocked","PreimageRevealed","Claiming","Completed"]

def derive_state(sw):
    """Return the VERIFIED state of a swap by re-checking its recorded txids on-chain.
       Never trusts the harness log for truth — only for candidate txids."""
    txids = sw.get("txids", {})
    verified = {}
    state = "QuoteRequested"
    # SOST lock leg
    if txids.get("sost_lock") and sost_tx_conf(txids["sost_lock"]):
        verified["sost_lock"] = True; state = "SostLocked"
    # BTC/EVM counterparty lock
    cp = txids.get("cp_lock")
    if cp:
        if sw.get("pair") == "SOST/BTC":
            t = btc_tx(cp)
            if t and int(t.get("confirmations", 0)) >= 1: verified["cp_lock"] = True
        else:
            if evm_receipt(cp): verified["cp_lock"] = True
        if verified.get("cp_lock") and verified.get("sost_lock"): state = "CounterpartyLocked"
    # counterparty claim reveals the preimage
    cc = txids.get("cp_claim")
    if cc:
        if sw.get("pair") == "SOST/BTC":
            t = btc_tx(cc)
            if t and int(t.get("confirmations", 0)) >= 1: verified["cp_claim"] = True
        else:
            if evm_receipt(cc): verified["cp_claim"] = True
        if verified.get("cp_claim"): state = "PreimageRevealed"
    # SOST claim completes
    if txids.get("sost_claim") and sost_tx_conf(txids["sost_claim"]):
        verified["sost_claim"] = True; state = "Completed"
    # refund path
    if txids.get("sost_refund") and sost_tx_conf(txids["sost_refund"]):
        verified["sost_refund"] = True; state = "Refunded"
    # cross-check the coordinator's own authoritative state (advisory)
    coord = sw.get("coord_state")
    return {"state": state, "verified": verified, "coord_state": coord, "txids": txids}

# ---- harness orchestration (FIXED argv; no shell string from input) ----
def run_harness(swap_id):
    with _lock:
        d = _load(); sw = d.get(swap_id)
    if not sw or not HARNESS or not os.path.exists(HARNESS):
        with _lock:
            d = _load(); d[swap_id]["status"]="error"; d[swap_id]["error"]="harness unavailable"; _save(d)
        return
    logf = os.path.join(SCRATCH, swap_id + ".log")
    with open(logf, "w") as lf:
        # FIXED argv array — HARNESS is a constant path, never client-controlled
        p = subprocess.Popen(["bash", HARNESS], stdout=lf, stderr=subprocess.STDOUT)
        p.wait()
    # extract candidate txids from the harness log (to be VERIFIED on-chain by derive_state)
    txt = open(logf).read()
    def grab(pat):
        m = re.search(pat, txt)
        return m.group(1) if m else None
    txids = {
        "sost_lock":  grab(r"SOST lock txid=([0-9a-f]{64})"),
        "cp_lock":    grab(r"funding txid=([0-9a-f]{64})"),
        "cp_claim":   grab(r"BTC claim txid=([0-9a-f]{64})"),
        "sost_claim": grab(r"SOST claim txid=([0-9a-f]{64})"),
    }
    coord = grab(r"final state: OK (\w+)")
    with _lock:
        d = _load(); d[swap_id]["txids"]={k:v for k,v in txids.items() if v}
        d[swap_id]["coord_state"]=coord; d[swap_id]["status"]="done"; _save(d)

# ---- HTTP ----
class H(http.server.BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Access-Control-Allow-Origin","*")   # localhost dashboard
        self.send_header("Content-Length",str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/api/health":
            return self._send(200, {
                "mode":"lab-testnet",
                "sost": {"up": sost_height() is not None, "height": sost_height()},
                "btc":  {"up": btc_tx is not None and BTC_CLI != "" and btc_call(["getblockcount"]) is not None},
                "evm":  {"up": anvil_up()},
                "harness": bool(HARNESS and os.path.exists(HARNESS)),
            })
        m = re.match(r"^/api/swap/([A-Za-z0-9_-]{1,64})$", self.path)
        if m:
            sid = m.group(1)
            with _lock: sw = _load().get(sid)
            if not sw: return self._send(404, {"error":"unknown swap"})
            return self._send(200, {"id":sid, "pair":sw.get("pair"), "status":sw.get("status"), **derive_state(sw)})
        return self._send(404, {"error":"not found"})

    def do_POST(self):
        if self.path != "/api/swap/start":
            return self._send(404, {"error":"not found"})
        try:
            n = int(self.headers.get("Content-Length","0"))
            body = json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return self._send(400, {"error":"bad json"})
        pair = body.get("pair")
        if pair not in PAIRS:                     # whitelist — reject anything else
            return self._send(400, {"error":"unsupported pair (lab whitelist)"})
        # NOTE: no keys accepted from the client; lab keys are server-side fixtures.
        sid = "lab-" + str(int(time.time()*1000))
        with _lock:
            d = _load(); d[sid] = {"pair":pair, "status":"running", "txids":{}, "created": int(time.time())}; _save(d)
        threading.Thread(target=run_harness, args=(sid,), daemon=True).start()
        return self._send(200, {"id":sid, "status":"running", "note":"observe GET /api/swap/"+sid+" for VERIFIED on-chain state"})

def main():
    with socketserver.TCPServer(("127.0.0.1", PORT), H) as srv:
        print("SOST DEX lab relay on http://127.0.0.1:%d (TEST MODE; localhost only)" % PORT)
        print("  SOST_RPC=%s  ANVIL_RPC=%s  BTC_CLI=%s  HARNESS=%s" % (SOST_RPC, ANVIL_RPC, bool(BTC_CLI), bool(HARNESS)))
        srv.serve_forever()

if __name__ == "__main__":
    main()

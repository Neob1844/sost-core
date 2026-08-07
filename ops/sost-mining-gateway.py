#!/usr/bin/env python3
# =============================================================================
# SOST public MINING gateway — REFERENCE IMPLEMENTATION. NOT DEPLOYED.
# =============================================================================
# Purpose: let external miners point a miner at sostcore.com and mine WITHOUT
# running their own full node, by exposing ONLY the mining triple
# (getlotterystate, getblocktemplate, submitblock) with hard safety limits.
#
# SECURITY MODEL (see docs/design/PUBLIC_MINING_ENDPOINT_DESIGN.md):
#   * STRICT ALLOWLIST — exactly the mining triple passes; every other method is
#     rejected with 403 and NEVER forwarded (no wallet / funds / admin).
#   * submitblock is auth-injected toward the node (node RPC creds never exposed).
#     Consensus fully validates every submitted block, so bad blocks are rejected.
#   * getblocktemplate is served from a SHORT CACHE so N miners share ONE node
#     computation instead of hammering the node N times.
#   * per-IP + global RATE LIMITS reject floods cheaply, BEFORE touching the node.
#   * KILL SWITCH: this is a SEPARATE systemd service; `systemctl stop
#     sost-mining-gateway` (or MINING_ENABLED=0) closes the endpoint instantly
#     without touching the node.
#
# DO NOT DEPLOY until: (1) load-tested on a >=8GB staging node to fix a safe
# RATE_GLOBAL, (2) the node's intermittent RPC degradation is understood, (3) it
# runs on a node with real headroom. The current 3.8GB production node degrades
# at near-zero load and MUST NOT host this yet.
# =============================================================================
import json, os, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlreq

NODE_URL     = os.environ.get("SOST_NODE_URL", "http://127.0.0.1:18232/")
NODE_USER    = os.environ.get("SOST_NODE_USER", "")          # injected ONLY for submitblock
NODE_PASS    = os.environ.get("SOST_NODE_PASS", "")
LISTEN_PORT  = int(os.environ.get("SOST_MINING_PORT", "18400"))
MINING_ENABLED = os.environ.get("MINING_ENABLED", "1") == "1"  # kill switch

# Exactly these methods are reachable. Nothing else is ever forwarded.
READ_METHODS  = {"getlotterystate", "getblocktemplate", "getblockcount"}
WRITE_METHODS = {"submitblock"}                     # auth-injected toward node
ALLOWED       = READ_METHODS | WRITE_METHODS

TEMPLATE_CACHE_TTL = 2.0        # s: N miners share one getblocktemplate computation
RATE_PER_IP        = 5          # requests/s/IP (429 above)
RATE_GLOBAL        = 40         # requests/s across all IPs — TUNE VIA LOAD TEST
MAX_BODY           = 256 * 1024 # bytes

_cache = {"getblocktemplate": (0.0, None), "getlotterystate": (0.0, None)}
_cache_lock = threading.Lock()
_ip_hits, _global_hits, _win = {}, [0, 0.0], threading.Lock()

def _rate_ok(ip):
    now = time.time()
    with _win:
        if now - _global_hits[1] >= 1.0:
            _global_hits[0] = 0; _global_hits[1] = now; _ip_hits.clear()
        if _global_hits[0] >= RATE_GLOBAL: return False
        c = _ip_hits.get(ip, 0)
        if c >= RATE_PER_IP: return False
        _ip_hits[ip] = c + 1; _global_hits[0] += 1
        return True

def _node_call(method, params, inject_auth):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params if isinstance(params, list) else []}).encode()
    req = urlreq.Request(NODE_URL, data=body, headers={"content-type": "application/json"})
    if inject_auth and NODE_USER:
        import base64
        tok = base64.b64encode(f"{NODE_USER}:{NODE_PASS}".encode()).decode()
        req.add_header("Authorization", "Basic " + tok)
    with urlreq.urlopen(req, timeout=15) as r:
        return r.read()

def _cached_read(method, params):
    with _cache_lock:
        ts, val = _cache.get(method, (0.0, None))
        if val is not None and (time.time() - ts) < TEMPLATE_CACHE_TTL:
            return val
    out = _node_call(method, params, inject_auth=False)
    with _cache_lock:
        _cache[method] = (time.time(), out)
    return out

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())

    def do_POST(self):
        if not MINING_ENABLED:
            return self._send(503, {"error": "mining endpoint disabled"})
        ip = self.client_address[0]
        if not _rate_ok(ip):
            return self._send(429, {"error": "rate limited"})
        n = int(self.headers.get("content-length", 0) or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "body too large"})
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        method = str(data.get("method", ""))
        # STRICT allowlist — anything else is refused and never reaches the node.
        if method not in ALLOWED:
            return self._send(403, {"error": "method not allowed on mining endpoint"})
        params = data.get("params", [])
        try:
            if method in READ_METHODS:
                return self._send(200, _cached_read(method, params))
            # submitblock: auth-injected; consensus validates the block.
            return self._send(200, _node_call(method, params, inject_auth=True))
        except Exception as e:
            return self._send(502, {"error": "node unavailable", "detail": str(e)[:120]})

    def log_message(self, *a):  # quiet
        pass

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), Handler)
    print(f"[sost-mining-gateway] REFERENCE on :{LISTEN_PORT} enabled={MINING_ENABLED} "
          f"allow={sorted(ALLOWED)} rate/ip={RATE_PER_IP} global={RATE_GLOBAL}")
    srv.serve_forever()

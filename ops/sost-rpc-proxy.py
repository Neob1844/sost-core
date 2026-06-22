#!/usr/bin/env python3
"""SOST public RPC gateway — see docs/RPC_PROXY_ARCHITECTURE.md.

Why it exists: the SOST node gates RPC by method (reads need no auth; writes incl.
`sendrawtransaction` require the node RPC credentials). Without this, only an operator
with the node creds + an SSH tunnel could broadcast. This gateway lets ANY user broadcast
a SIGNED transaction (safe to expose publicly — the keys never leave the user's browser)
while keeping every other authenticated/admin method blocked.

Policy:
  * method == sendrawtransaction  -> inject the node RPC credentials, forward.
  * any other method              -> forward WITHOUT credentials, so the node's own gate
                                     applies: reads succeed, every other write returns -401.
The request body is reserialized to a canonical single-method JSON-RPC object so a crafted
body cannot smuggle a second method past the node.

Listens on 127.0.0.1:18299; nginx /rpc and /rpc/public proxy_pass to it. Credentials are
read at startup from /etc/sost/rpc.env (RPC_USER / RPC_PASS) — never hardcoded here.
"""
import json
import base64
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NODE_URL = 'http://127.0.0.1:18232/'
RPC_ENV = '/etc/sost/rpc.env'
LISTEN = ('127.0.0.1', 18299)

# The only method(s) the gateway will authenticate on behalf of the public.
# Broadcasting a signed transaction is safe to expose (cf. Bitcoin's public sendrawtransaction).
BROADCAST_METHODS = {'sendrawtransaction'}


def needs_node_auth(method):
    """True iff the gateway should inject node credentials for this RPC method."""
    return method in BROADCAST_METHODS


def clean_request(data):
    """Reserialize to a canonical single-method JSON-RPC body. Drops any extra fields so a
    crafted request cannot smuggle a second `method` past the node; the node then parses
    exactly the method the gateway used for its auth decision."""
    return json.dumps({
        'jsonrpc': '2.0',
        'id': data.get('id', 1),
        'method': str(data.get('method', '')),
        'params': data.get('params', []),
    })


def _load_auth(path=RPC_ENV):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return 'Basic ' + base64.b64encode((env['RPC_USER'] + ':' + env['RPC_PASS']).encode()).decode()


def make_handler(auth_header):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body):
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body if isinstance(body, bytes) else body.encode())

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            self.end_headers()

        def do_POST(self):
            method = '?'
            try:
                n = int(self.headers.get('Content-Length', 0) or 0)
                data = json.loads(self.rfile.read(n))
                if not isinstance(data, dict):
                    return self._send(400, '{"error":"single requests only"}')
                method = str(data.get('method', ''))
                body = clean_request(data).encode()
                req = urllib.request.Request(NODE_URL, data=body, headers={'Content-Type': 'application/json'})
                if needs_node_auth(method):
                    req.add_header('Authorization', auth_header)
                try:
                    with urllib.request.urlopen(req, timeout=20) as r:
                        out, code = r.read(), r.status
                except urllib.error.HTTPError as e:
                    out, code = e.read(), e.code
                self._send(code, out)
                # Audit line (captured by journald). Never logs params/credentials.
                sys.stderr.write('[rpc-proxy] method=%s code=%s auth_injected=%s\n'
                                 % (method, code, needs_node_auth(method)))
            except Exception as e:
                self._send(400, json.dumps({'error': str(e)[:160]}))
                sys.stderr.write('[rpc-proxy] method=%s ERROR %s\n' % (method, str(e)[:120]))

        def log_message(self, *a):  # silence default access log; we emit our own audit line
            pass

    return Handler


if __name__ == '__main__':
    ThreadingHTTPServer(LISTEN, make_handler(_load_auth())).serve_forever()

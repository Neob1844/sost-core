#!/usr/bin/env python3
"""SOST public RPC gateway — see docs/RPC_PROXY_ARCHITECTURE.md.

Why it exists: the SOST node gates RPC by method (reads need no auth; writes incl.
`sendrawtransaction` require the node RPC credentials). Without this, only an operator
with the node creds + an SSH tunnel could broadcast. This gateway lets ANY user broadcast
a SIGNED transaction (safe to expose publicly — the keys never leave the user's browser)
while keeping every other authenticated/admin method blocked.

Policy:
  * method == sendrawtransaction  -> inject the node RPC credentials, forward.
  * method == getnetworksummary   -> answered by the gateway itself from node READS only
                                     (see summarize_network); nothing is forwarded as-is.
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
import threading
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NODE_URL = 'http://127.0.0.1:18232/'
RPC_ENV = '/etc/sost/rpc.env'
LISTEN = ('127.0.0.1', 18299)

# The only method(s) the gateway will authenticate on behalf of the public.
# Broadcasting a signed transaction is safe to expose (cf. Bitcoin's public sendrawtransaction).
BROADCAST_METHODS = {'sendrawtransaction'}

# Methods the gateway refuses outright for anonymous callers, even though the node would
# answer them without credentials.
#
# getblocktemplate is not a read: it assembles a full candidate block (coinbase, mempool
# selection, merkle root) on every call, on a node that is already CPU-bound by SbPoW.
# Exposed anonymously it is a cheap way to degrade the node — and nothing public needs
# it: the explorer never calls it (it reads the counter via getrpcstats), and a miner
# talks to its OWN node, authenticated, not to this gateway. Refused here rather than in
# the node so the published v16.1.0 binaries and their hashes stay untouched.
PUBLIC_DENY_METHODS = {'getblocktemplate'}


# ── getnetworksummary ────────────────────────────────────────────────────────
# A synthetic, read-only method answered HERE, not by the node. It is the source of
# truth for the Explorer's UNIQUE NODES card, which used to count only acked peers from
# getpeerinfo — so the node serving the Explorer, the one actually holding the chain,
# never counted itself and the card read 0 while the network was producing blocks.
#
# Built only from node reads (getinfo, getblock of the tip, getpeerinfo); nothing on the
# node, the P2P protocol or consensus changes. The local node counts as 1 ONLY when those
# reads prove it is up, on mainnet, on the right genesis and with a fresh tip — never a
# fixed +1. External peers are counted as distinct machines, with this node's own
# loopback pair removed so it can never be counted twice.
NETWORK_SUMMARY_METHOD = 'getnetworksummary'
MAINNET_GENESIS = '6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37'
# 12 target blocks. A slow stretch under a high cASERT profile can leave a tip 1-2 h old
# on a healthy chain; past this the node is serving a chain that has stopped moving.
TIP_STALE_S = 7200
SUMMARY_CACHE_S = 10


def _peer_host(addr):
    t = str(addr or '')
    i = t.rfind(':')
    return t[:i] if i > 0 else t


def self_connection_indexes(peers):
    """Indexes of peers that are the two ends of this node dialling itself.

    A node that dials its own seed address sees ONE connection twice: an outbound entry
    and an inbound entry, opened in the same second, announcing the same height, over the
    same transport. Not grouped by host — the outbound half reads as the hostname and the
    inbound half as a (masked) numeric address. Same signature the Explorer used."""
    marked, used = set(), set()
    for a, pa in enumerate(peers):
        if pa.get('direction') != 'outbound' or a in used:
            continue
        for b, pb in enumerate(peers):
            if a == b or b in used or pb.get('direction') != 'inbound':
                continue
            if (abs((pa.get('conntime') or 0) - (pb.get('conntime') or 0)) <= 2
                    and pa.get('height') == pb.get('height')
                    and pa.get('enc_mode') == pb.get('enc_mode')):
                marked.update((a, b))
                used.update((a, b))
                break
    return marked


def summarize_network(info, tip_time, peers, now, info_error=None):
    """Pure function: node reads -> network summary. See NETWORK_SUMMARY_METHOD."""
    reasons = []
    if info_error or not isinstance(info, dict):
        status = 'OFFLINE'
        reasons.append('rpc_unreachable')
    else:
        if info.get('profile') != 'mainnet' or info.get('testnet'):
            reasons.append('not_mainnet')
        if info.get('genesis_hash') != MAINNET_GENESIS:
            reasons.append('wrong_genesis')
        if not isinstance(info.get('blocks'), int) or info.get('blocks') <= 0:
            reasons.append('no_height')
        if not isinstance(tip_time, (int, float)):
            reasons.append('no_tip_time')
        elif now - tip_time > TIP_STALE_S:
            reasons.append('tip_stale')
        status = 'ONLINE' if not reasons else ('STALE' if reasons == ['tip_stale'] else 'DEGRADED')
    local_online = status == 'ONLINE'

    peers = peers if isinstance(peers, list) else []
    self_idx = self_connection_indexes(peers)
    ext_hosts, ext_acked = set(), set()
    for i, p in enumerate(peers):
        if i in self_idx:
            continue
        h = _peer_host(p.get('addr'))
        ext_hosts.add(h)
        if p.get('version_acked'):
            ext_acked.add(h)
    connected_external = len(ext_acked)
    local = 1 if local_online else 0
    return {
        'local_node': {
            'status': status,
            'online': local_online,
            'height': info.get('blocks') if isinstance(info, dict) else None,
            'tip_age_s': int(now - tip_time) if isinstance(tip_time, (int, float)) else None,
            'reasons': reasons,
        },
        'local_nodes': local,
        'connections': len(peers),
        'self_connections': len(self_idx),
        'external_hosts_seen': len(ext_hosts),
        'connected_external': connected_external,
        # The P2P protocol has no address exchange (EKEY/VERS/VACK/GETB/PING/PONG only),
        # so this node cannot learn of peers it is not connected to. Reported as null,
        # never as a guessed number.
        'discovered_active': None,
        'discovered_note': 'no address exchange in the P2P protocol',
        'unique_active_nodes': local + connected_external,
        'tip_stale_after_s': TIP_STALE_S,
        'generated_at': int(now),
    }


def _node_read(method, params=None, timeout=10):
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or []}).encode()
    req = urllib.request.Request(NODE_URL, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    if d.get('error'):
        raise RuntimeError(str(d['error'])[:120])
    return d.get('result')


_summary_lock = threading.Lock()
_summary_cache = {'at': 0.0, 'value': None}


def network_summary(read=_node_read, clock=time.time):
    with _summary_lock:
        now = clock()
        if _summary_cache['value'] is not None and now - _summary_cache['at'] < SUMMARY_CACHE_S:
            return _summary_cache['value']
        info = tip_time = peers = err = None
        try:
            info = read('getinfo')
            tip = read('getblock', [read('getbestblockhash')])
            tip_time = tip.get('time') if isinstance(tip, dict) else None
        except Exception as e:  # node down or wedged: report OFFLINE, don't raise
            err = str(e)[:120]
        try:
            peers = read('getpeerinfo')
        except Exception:
            peers = []
        value = summarize_network(info, tip_time, peers, now, info_error=err)
        _summary_cache.update(at=now, value=value)
        return value


def needs_node_auth(method):
    """True iff the gateway should inject node credentials for this RPC method."""
    return method in BROADCAST_METHODS


def denied_to_public(method):
    """True iff the gateway refuses this method for anonymous callers."""
    return method in PUBLIC_DENY_METHODS


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
                if denied_to_public(method):
                    sys.stderr.write('[rpc-proxy] method=%s code=403 denied_public=1\n' % method)
                    return self._send(403, json.dumps({
                        'jsonrpc': '2.0', 'id': data.get('id', 1),
                        'error': {'code': -32601,
                                  'message': 'method not available on the public gateway; '
                                             'run your own node'}}))
                if method == NETWORK_SUMMARY_METHOD:
                    self._send(200, json.dumps({'jsonrpc': '2.0', 'id': data.get('id', 1),
                                                'result': network_summary()}))
                    sys.stderr.write('[rpc-proxy] method=%s code=200 synthetic=1\n' % method)
                    return
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

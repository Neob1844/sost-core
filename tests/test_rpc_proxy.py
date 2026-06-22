"""Tests for the SOST public RPC gateway policy (ops/sost-rpc-proxy.py).

These are pure-function tests of the security policy — no socket, no node, no rpc.env.
They lock in the invariant that ONLY sendrawtransaction is authenticated and that the
request body is reduced to a single, canonical method (anti-smuggling)."""
import json
import os
import importlib.util

_PATH = os.path.join(os.path.dirname(__file__), '..', 'ops', 'sost-rpc-proxy.py')
_spec = importlib.util.spec_from_file_location('sost_rpc_proxy', _PATH)
proxy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proxy)


def test_only_sendrawtransaction_is_authenticated():
    assert proxy.needs_node_auth('sendrawtransaction') is True


def test_reads_and_admin_methods_are_never_authenticated():
    # Reads (forwarded no-auth, node allows) and dangerous writes (node -401) must NOT be elevated.
    for method in [
        'getblockcount', 'getbalance', 'getinfo', 'getrawtransaction', 'listunspent',
        'estimatesmartfee', 'scantxoutset',                      # reads
        'stop', 'setban', 'clearbanned', 'addnode', 'disconnectnode',  # admin
        'generate', 'generatetoaddress', 'submitblock',          # mining/admin
        'dumpprivkey', 'walletpassphrase', 'sendtoaddress', 'importprivkey',  # wallet
        '', 'SENDRAWTRANSACTION', ' sendrawtransaction ',        # empty / case / whitespace must NOT match
    ]:
        assert proxy.needs_node_auth(method) is False, method


def test_clean_request_is_single_canonical_method():
    # Even with duplicate keys / extra fields, the forwarded body has exactly the four
    # canonical fields and a single method — the node cannot see a smuggled second method.
    raw = '{"method":"stop","method":"sendrawtransaction","id":7,"params":["ab"],"evil":"stop"}'
    data = json.loads(raw)  # JSON parsers keep the last duplicate -> sendrawtransaction
    out = json.loads(proxy.clean_request(data))
    assert set(out.keys()) == {'jsonrpc', 'id', 'method', 'params'}
    assert out['method'] == data['method']
    assert out['id'] == 7
    assert out['params'] == ['ab']


def test_clean_request_defaults():
    out = json.loads(proxy.clean_request({}))
    assert out == {'jsonrpc': '2.0', 'id': 1, 'method': '', 'params': []}

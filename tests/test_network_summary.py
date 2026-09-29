"""Tests for the Explorer UNIQUE NODES source of truth: getnetworksummary in
ops/sost-rpc-proxy.py. Pure-function tests — no socket, no node."""
import os
import importlib.util

_PATH = os.path.join(os.path.dirname(__file__), '..', 'ops', 'sost-rpc-proxy.py')
_spec = importlib.util.spec_from_file_location('sost_rpc_proxy_ns', _PATH)
proxy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proxy)

NOW = 1_790_000_000
INFO = {'blocks': 28484, 'profile': 'mainnet', 'testnet': False,
        'genesis_hash': proxy.MAINNET_GENESIS, 'connections': 0}


def peer(addr, direction='outbound', acked=True, conntime=NOW - 5000, height=28484, enc='encrypted'):
    return {'addr': addr, 'direction': direction, 'version_acked': acked,
            'conntime': conntime, 'height': height, 'enc_mode': enc}


def summ(peers, info=INFO, tip_age=300, err=None):
    return proxy.summarize_network(info, NOW - tip_age, peers, NOW, info_error=err)


def test_a_local_online_no_peers_is_one():
    s = summ([])
    assert s['local_node']['status'] == 'ONLINE'
    assert (s['local_nodes'], s['connected_external'], s['unique_active_nodes']) == (1, 0, 1)
    assert s['discovered_active'] is None  # not available, never guessed


def test_b_two_distinct_external_peers_is_three():
    s = summ([peer('81.10.x.x:19333'), peer('95.20.x.x:51234', 'inbound', conntime=NOW - 900)])
    assert s['connected_external'] == 2
    assert s['unique_active_nodes'] == 3


def test_c_same_machine_twice_counts_once():
    s = summ([peer('81.10.x.x:19333'), peer('81.10.x.x:40111', 'inbound', conntime=NOW - 100, height=28480)])
    assert s['connected_external'] == 1
    assert s['unique_active_nodes'] == 2


def test_d_local_offline_does_not_pretend():
    s = summ([], info=None, err='connection refused')
    assert s['local_node']['status'] == 'OFFLINE'
    assert s['local_nodes'] == 0
    assert s['unique_active_nodes'] == 0


def test_d2_stale_tip_is_not_online():
    s = summ([], tip_age=proxy.TIP_STALE_S + 1)
    assert s['local_node']['status'] == 'STALE'
    assert s['unique_active_nodes'] == 0


def test_e_self_connection_pair_counts_local_once():
    t = NOW - 3000
    peers = [peer('seed.sostcore.com:19333', 'outbound', conntime=t),
             peer('212.132.x.x:44512', 'inbound', conntime=t + 1)]
    s = summ(peers)
    assert s['self_connections'] == 2
    assert s['connected_external'] == 0
    assert s['unique_active_nodes'] == 1


def test_unacked_peer_is_seen_but_not_counted():
    s = summ([peer('81.10.x.x:19333', acked=False)])
    assert s['external_hosts_seen'] == 1
    assert s['connected_external'] == 0
    assert s['unique_active_nodes'] == 1


def test_wrong_network_or_genesis_is_not_online():
    assert summ([], info=dict(INFO, profile='testnet'))['local_nodes'] == 0
    assert summ([], info=dict(INFO, genesis_hash='00' * 32))['local_nodes'] == 0


def test_network_summary_survives_node_down_and_caches():
    calls = []

    def dead(method, params=None):
        calls.append(method)
        raise OSError('refused')
    proxy._summary_cache.update(at=0.0, value=None)
    s = proxy.network_summary(read=dead, clock=lambda: NOW)
    assert s['local_node']['status'] == 'OFFLINE' and s['unique_active_nodes'] == 0
    n = len(calls)
    proxy.network_summary(read=dead, clock=lambda: NOW + 1)
    assert len(calls) == n  # served from cache within SUMMARY_CACHE_S
    proxy._summary_cache.update(at=0.0, value=None)


def test_network_summary_is_not_authenticated():
    assert proxy.needs_node_auth(proxy.NETWORK_SUMMARY_METHOD) is False

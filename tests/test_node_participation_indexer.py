#!/usr/bin/env python3
"""Tests for ops/node-participation-indexer.py against a fake chain (no network)."""
import hashlib
import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('npi', os.path.join(ROOT, 'ops', 'node-participation-indexer.py'))
npi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(npi)

# A real mainnet NODE_BIND (block #30,194, txid 36c2fc8c…), v2 202-byte payload.
REAL_BIND = ("010000002000010000000000000000300000000000000000000000000000000000000000ca00028a798bf382ff700317ca0193b6"
             "5f21d65cbb573bbcda69da096d85f3f6bb76c302beca632a308ffc5f054778b05caa076961c46a07bfe322869e2cd15345d85696"
             "0100000000000000a639d9e7b3f5a06edea216530efd794a29e8776971563ead2c1a81313cd43e798dc1d2e23a5212c842941b84"
             "566ae561ac22c7d8dfd4a3d02a38b17b37ba6804f518b758ddeccaf3921913f1e59420fc37f0e4164c3067ed5c0a7b0ee33df199"
             "5757302cb505a158d64a83a7340c1adc4acef09c363f1480e6397dde121df32c")


def pub(n):
    return bytes([2]) + hashlib.sha256(b'k%d' % n).digest()


def node_tx(tx_type, payload):
    return ('01000000' + '%02x' % tx_type + '00' + '01' + '00' * 8 + '30' + '00' * 20
            + len(payload).to_bytes(2, 'little').hex() + payload.hex())


def bind_hex(mpub, npub, seq, v2=True):
    return node_tx(0x20, mpub + npub + seq.to_bytes(8, 'little') + b'\x11' * 64 + (b'\x22' * 64 if v2 else b''))


def hb_hex(npub, epoch):
    return node_tx(0x21, npub + epoch.to_bytes(8, 'little') + b'\x33' * 32 + b'\x44' * 64)


class FakeChain:
    def __init__(self, start):
        self.start, self.blocks, self.raw, self.audit = start, [], {}, None

    def add(self, txs=(), salt=''):
        h = self.start + len(self.blocks)
        ids = ['cb%d%s' % (h, salt)]
        for i, t in enumerate(txs):
            tid = 't%d_%d%s' % (h, i, salt)
            self.raw[tid] = t
            ids.append(tid)
        prev = self.blocks[-1]['hash'] if self.blocks else 'genesis'
        self.blocks.append({'hash': 'h%d%s' % (h, salt), 'height': h, 'previousblockhash': prev, 'txids': ids})

    def rpc(self, method, params=None):
        if method == 'getblockcount':
            return self.start + len(self.blocks) - 1
        if method == 'getblockhash':
            return self.blocks[params[0] - self.start]['hash']
        if method == 'getblock':
            return next(b for b in self.blocks if b['hash'] == params[0])
        if method == 'getrawtransaction':
            return {'hex': self.raw.get(params[0], '01000000000000')}
        if method == 'getjackpotv2audit':
            return self.audit
        raise AssertionError(method)


def make(chain):
    ix = npi.Indexer('fake')
    ix.rpc = chain.rpc
    return ix


class T(unittest.TestCase):
    def test_ripemd160_vectors(self):
        self.assertEqual(npi._ripemd160_py(b'').hex(), '9c1185a5c5e9fc54612808977ee8f548b2258d31')
        self.assertEqual(npi._ripemd160_py(b'abc').hex(), '8eb208f7e05d987a9b044a8e98c6b087f15a0bfc')
        self.assertEqual(npi._ripemd160_py(b'a' * 1000), npi.ripemd160(b'a' * 1000) if hasattr(hashlib, 'new') else npi._ripemd160_py(b'a' * 1000))

    def test_real_mainnet_bind_decodes_to_the_bound_miner(self):
        kind, b = npi.parse_node_tx(REAL_BIND)
        self.assertEqual(kind, 'bind')
        self.assertEqual(b['miner'], 'sost1ad01a1ce3ae7d0dbcc1baae7a11e9ecde28683a2')
        self.assertEqual(b['seq'], 1)
        self.assertEqual(b['v'], 2)

    def test_non_node_txs_ignored(self):
        self.assertIsNone(npi.parse_node_tx('01000000' + '02' + '01' + '00' * 133 + '01' + '00' * 29))
        self.assertIsNone(npi.parse_node_tx('zz'))
        self.assertIsNone(npi.parse_node_tx(node_tx(0x20, b'\x00' * 100)))   # wrong payload size

    def test_coverage_streak_status_and_window(self):
        c = FakeChain(npi.A)
        m, n = pub(1), pub(2)
        c.add([bind_hex(m, n, 1)])                       # bind in epoch 0
        c.add([hb_hex(n, 0)])
        for _ in range(npi.L - 2):
            c.add()
        for e in (1, 2):                                 # heartbeats in epochs 1 and 2, then miss epoch 3
            c.add([hb_hex(n, e)])
            for _ in range(npi.L - 1):
                c.add()
        for _ in range(npi.L + 5):                       # epoch 3 complete, no heartbeat; 5 blocks into epoch 4
            c.add()
        ix = make(c)
        ix.step()
        d = ix.document()
        self.assertEqual(d['completed_epochs'], 4)
        x = d['nodes'][0]
        self.assertEqual(x['miner'], npi.address_of_pubkey(m))
        self.assertEqual((x['epochs_expected'], x['epochs_covered']), (4, 3))
        self.assertEqual(x['streak'], 0)
        self.assertEqual(x['status'], 'LAPSED')
        nj = x['next_jackpot']
        self.assertEqual(nj['height'], npi.next_jackpot_after(d['tip']))

    def test_rebind_moves_identity_and_old_key_heartbeats_stop_counting(self):
        c = FakeChain(npi.A)
        m, n1, n2 = pub(1), pub(2), pub(3)
        c.add([bind_hex(m, n1, 1)])
        c.add([bind_hex(m, n2, 2)])
        c.add([hb_hex(n1, 0)])                           # old key: not the active binding any more
        ix = make(c)
        ix.step()
        x = ix.document()['nodes'][0]
        self.assertEqual(x['node_key'], n2.hex())
        self.assertEqual(x['binds_total'], 2)
        self.assertEqual(x['heartbeats'], 0)

    def test_reorg_drops_orphaned_heartbeat(self):
        c = FakeChain(npi.A)
        m, n = pub(1), pub(2)
        c.add([bind_hex(m, n, 1)])
        c.add([hb_hex(n, 0)])
        ix = make(c)
        ix.step()
        self.assertEqual(ix.document()['nodes'][0]['heartbeats'], 1)
        c.blocks.pop()
        c.add(salt='x')                                  # competing block without the heartbeat
        c.add(salt='x')
        ix.step()
        self.assertEqual(ix.document()['nodes'][0]['heartbeats'], 0)
        self.assertTrue(ix.reorgs)

    def test_audit_cross_check(self):
        c = FakeChain(npi.A)
        m, n = pub(1), pub(2)
        c.add([bind_hex(m, n, 1)])
        c.add([hb_hex(n, 0)])
        while c.start + len(c.blocks) <= 30186:          # past the first V2 draw: next one (#30,474) has 1 completed epoch
            c.add()
        c.audit = {'candidates': [{'address': npi.address_of_pubkey(m), 'node_bound': True, 'heartbeats': 1}]}
        ix = make(c)
        ix.step()
        ix.refresh_audit()
        self.assertTrue(ix.document()['nodes'][0]['audit']['match'])
        c.audit['candidates'][0]['heartbeats'] = 0
        ix.refresh_audit()
        self.assertFalse(ix.document()['nodes'][0]['audit']['match'])

    def test_eligibility_explained_like_mainnet_30301(self):
        """Mainnet at #30,301: A bound in epoch 0 with heartbeats in epochs 0 and 1; B (dominant PoW) bound at
        #30,289 (epoch 1) with a heartbeat in epoch 1. Node audit for #30,474: A eligible, B 0/1."""
        c = FakeChain(npi.A)
        ma, na, mb, nb = pub(1), pub(2), pub(3), pub(4)
        while c.start + len(c.blocks) < 30194:
            c.add()
        c.add([bind_hex(ma, na, 1)])                                   # #30,194
        c.add(); c.add([hb_hex(na, 0)])                                # #30,196
        while c.start + len(c.blocks) < 30288:
            c.add()
        c.add([hb_hex(na, 1)])                                         # #30,288
        c.add([bind_hex(mb, nb, 1)])                                   # #30,289
        c.add(); c.add(); c.add([hb_hex(nb, 1)])                       # #30,292
        while c.start + len(c.blocks) <= 30301:
            c.add()
        A_, B_ = npi.address_of_pubkey(ma), npi.address_of_pubkey(mb)
        c.audit = {"height": 30474, "completed_epochs": 1, "heartbeat_required": 1, "heartbeat_window": 1, "total_weight": 545,
                   "eligible_count": 1, "candidates": [
                       {"address": B_, "pow_blocks": 1299, "node_bound": True, "heartbeats": 0, "heartbeats_required": 1, "eligible": False, "weight": 0},
                       {"address": A_, "pow_blocks": 545, "node_bound": True, "heartbeats": 1, "heartbeats_required": 1, "eligible": True, "weight": 545}]}
        ix = make(c)
        ix.step()
        ix.refresh_audit()
        j = ix.document()["jackpot"]
        a, b = j["candidates"]
        self.assertEqual((a["address"], a["eligible"], a["share"]), (A_, True, 1.0))
        self.assertEqual(a["earliest"]["status"], "eligible_now")
        self.assertEqual(b["checks"]["pow"]["result"], "pass")
        self.assertEqual(b["checks"]["heartbeats"]["result"], "fail")
        self.assertEqual(b["epochs"][0]["status"], "before_bind")
        self.assertEqual(b["earliest"]["height"], 31338)                   # 3 of epochs 0-3, epoch 0 impossible
        self.assertEqual([e["status"] for e in b["earliest"]["epochs"]], ["before_bind", "confirmed", "pending", "pending"])
        self.assertTrue(any("was not a heartbeat failure" in r for r in b["reasons"]))
        self.assertFalse(any("dominan" in r.lower() for r in b["reasons"]))

    def _row(self, pow_blocks, bound, hb, req, eligible=False, weight=0):
        return {"address": "sost1" + "e" * 40, "pow_blocks": pow_blocks, "node_bound": bound, "heartbeats": hb,
                "heartbeats_required": req, "eligible": eligible, "weight": weight}

    def test_genuine_missing_after_bind_is_not_before_bind(self):
        b = {"h": npi.A + 5}                                            # bound early in epoch 0, never a heartbeat in it
        eps = {1: [npi.A + npi.L + 3, "t"]}
        x = npi.explain_candidate(self._row(50, True, 0, 1), b, eps, npi.A + npi.L + 20, 30474)
        self.assertEqual(x["epochs"][0]["status"], "missing")
        self.assertTrue(any("although the identity was already bound" in r for r in x["reasons"]))
        self.assertFalse(any("not a heartbeat failure" in r for r in x["reasons"]))

    def test_pending_and_heartbeat_height(self):
        b = {"h": npi.A + 1}
        eps = {0: [npi.A + 7, "t"]}
        x = npi.explain_candidate(self._row(50, True, 1, 1, True, 50), b, eps, npi.A + npi.L + 2, 30474)
        self.assertEqual(x["epochs"][0]["heartbeat_height"], npi.A + 7)
        self.assertEqual(x["earliest"]["status"], "eligible_now")

    def test_steady_state_three_of_four(self):
        b = {"h": npi.A + 1}                                            # bound in epoch 0, heartbeats in 1, 2, 3 only
        eps = {1: [1, ""], 2: [2, ""], 3: [3, ""]}
        tip = npi.A + 4 * npi.L + 3                                      # epoch 4 open; #31,338 counts epochs 0-3
        win, req = npi.draw_window(31338)
        self.assertEqual((win, req), ([0, 1, 2, 3], 3))
        x = npi.explain_candidate(self._row(50, True, 3, 3, True, 50), b, eps, tip, 31338)
        self.assertEqual([e["status"] for e in x["epochs"]], ["missing", "confirmed", "confirmed", "confirmed"])
        self.assertEqual(x["checks"]["heartbeats"]["result"], "pass")
        # one more miss (epoch 2) breaks 3-of-4: next reachable draw moves on
        eps2 = {1: [1, ""], 3: [3, ""]}
        y = npi.explain_candidate(self._row(50, True, 2, 3), b, eps2, tip, 31338)
        self.assertEqual(y["checks"]["heartbeats"]["result"], "fail")
        self.assertGreater(y["earliest"]["height"], 31338)

    def test_pow_below_minimum_has_no_promised_height(self):
        b = {"h": npi.A + 1}
        eps = {0: [npi.A + 7, ""]}
        x = npi.explain_candidate(self._row(1, True, 1, 1), b, eps, npi.A + npi.L + 2, 30474)
        self.assertEqual(x["checks"]["pow"]["result"], "fail")
        self.assertEqual(x["earliest"]["pow_needed"], 2)
        self.assertIn("no exact height can be promised", x["earliest"]["why_pow"])

    def test_no_node_bind_cannot_be_dated(self):
        x = npi.explain_candidate(self._row(40, False, 0, 1), None, {}, npi.A + npi.L + 2, 30474)
        self.assertEqual(x["checks"]["node_bind"]["result"], "fail")
        self.assertEqual(x["earliest"]["status"], "cannot_determine")
        self.assertTrue(all(e["status"] == "before_bind" for e in x["epochs"]))

    def test_ramp_and_generic_example(self):
        self.assertEqual([(r["height"], r["required"], r["window"]) for r in npi.ramp_table()],
                         [(30186, 0, 0), (30474, 1, 1), (30762, 2, 2), (31050, 3, 3), (31338, 3, 4)])
        ex = npi.example_bind_in_epoch1()
        self.assertEqual([(d["height"], d["eligible_by_heartbeats"]) for d in ex["draws"]],
                         [(30474, False), (30762, False), (31050, False), (31338, True)])

    def test_state_roundtrip(self):
        c = FakeChain(npi.A)
        c.add([bind_hex(pub(1), pub(2), 1)])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 's.json')
            ix = make(c)
            ix.state_path = p
            ix.step()
            ix.save()
            iy = make(c)
            iy.state_path = p
            iy.load()
            self.assertEqual(iy.rows, ix.rows)

    def test_read_only(self):
        ix = npi.Indexer('http://127.0.0.1:1/')
        with self.assertRaises(PermissionError):
            ix.rpc('sendrawtransaction', [])


if __name__ == '__main__':
    unittest.main()

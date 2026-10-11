#!/usr/bin/env python3
"""Tests for ops/address-earnings-indexer.py against a fake chain (no network)."""
import importlib.util
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('aei', os.path.join(ROOT, 'ops', 'address-earnings-indexer.py'))
aei = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aei)

A, B, C = 'sost1' + 'a' * 40, 'sost1' + 'b' * 40, 'sost1' + 'c' * 40


def jackpot_hex(winner, sat, tx_type=0x02, out_type=0x00):
    """version(4) tx_type nin=1 input(133) nout=1 amount out_type pkh(20)."""
    return ('01000000' + '%02x' % tx_type + '01' + '00' * 133 + '01' + sat.to_bytes(8, 'little').hex()
            + '%02x' % out_type + winner[5:])


class FakeChain:
    def __init__(self):
        self.blocks = []      # dicts
        self.raw = {}
        self.calls = []

    def add(self, miner, mine=100, dtd_addr='', dtd=0, extra_txs=(), salt=''):
        h = len(self.blocks)
        bh = ('%064x' % (h + 1)) if not salt else (salt * 64)[:64]
        prev = self.blocks[-1]['hash'] if self.blocks else None
        txids = ['cb%062x' % h] + [t[0] for t in extra_txs]
        for txid, hx in extra_txs:
            self.raw[txid] = hx
        self.blocks.append({'hash': bh, 'height': h, 'previousblockhash': prev, 'miner_address': miner,
                            'miner_reward': mine, 'lottery_winner_address': dtd_addr, 'lottery_payout': dtd,
                            'txids': txids})

    def __call__(self, method, params=None):
        self.calls.append(method)
        if method == 'getblockcount':
            return len(self.blocks) - 1
        if method == 'getblockhash':
            return self.blocks[params[0]]['hash']
        if method == 'getblock':
            return next(b for b in self.blocks if b['hash'] == params[0])
        if method == 'getrawtransaction':
            return {'hex': self.raw[params[0]]}
        raise AssertionError(method)


def make(chain):
    ix = aei.Indexer('http://unused/')
    real = ix.rpc
    ix.rpc = lambda m, p=None: (real(m, p) if m not in aei.READ_ONLY else chain(m, p))
    return ix


class TestIndexer(unittest.TestCase):
    def setUp(self):
        self.old = (aei.JP_FIRST, aei.JP_STEP, aei.V2_HEIGHT)
        aei.JP_FIRST, aei.JP_STEP, aei.V2_HEIGHT = 4, 4, 10     # jackpot heights 4, 8, 12 ...; V2 from 10

    def tearDown(self):
        aei.JP_FIRST, aei.JP_STEP, aei.V2_HEIGHT = self.old

    def chain(self):
        c = FakeChain()
        for h in range(14):
            extra = ()
            if h == 4:
                extra = (('jp4', jackpot_hex(B, 10000000000)),)                 # V1 jackpot to B
            if h == 8:
                extra = (('jp8', jackpot_hex(C, 10000000000, out_type=0x04)),)  # not a jackpot output -> ignored
            if h == 12:
                extra = (('jp12', jackpot_hex(B, 20000000000)), ('t12', jackpot_hex(A, 5, tx_type=0x00)))  # V2 to B + a normal tx
            c.add(A if h % 2 == 0 else B, 100, dtd_addr=(B if h % 3 == 0 else ''), dtd=(40 if h % 3 == 0 else 0), extra_txs=extra)
        return c

    def test_totals_are_split_by_kind(self):
        ix = make(self.chain())
        ix.step()
        t, jps = ix.totals()
        self.assertEqual(t[A][:2], [700, 7])                 # 7 blocks mined by A
        self.assertEqual(t[B][:2], [700, 7])
        self.assertEqual(t[B][2:4], [200, 5])                # DTD normal at 0,3,6,9,12
        self.assertEqual(t[B][4:6], [30000000000, 2])        # jackpots really paid: #4 (V1) and #12 (V2)
        self.assertEqual(t[B][6:8], [10000000000, 1])        # of which V1
        self.assertEqual(t[A][4:6], [0, 0])                  # a normal tx at a jackpot height is not a jackpot
        self.assertNotIn(C, t)                               # wrong output type: not credited
        self.assertEqual([j['h'] for j in jps], [4, 12])

    def test_no_winner_draw_credits_nothing(self):
        c = self.chain()
        ix = make(c)
        ix.step()
        self.assertEqual(ix.rows[8][6], [])                  # height 8: no valid jackpot tx

    def test_only_read_methods(self):
        ix = aei.Indexer('http://127.0.0.1:9/')
        for m in ('sendrawtransaction', 'submitblock', 'stop', 'getjackpotv2audit'):
            with self.assertRaises(PermissionError):
                ix.rpc(m)

    def test_incremental_after_first_pass(self):
        c = self.chain()
        ix = make(c)
        ix.step()
        c.calls.clear()
        c.add(A, 100)
        ix.step()
        self.assertLessEqual(len(c.calls), 6)               # tip check + one new block, not a rescan
        self.assertEqual(ix.tip, 14)

    def test_reorg_removes_orphaned_rewards(self):
        c = self.chain()
        ix = make(c)
        ix.step()
        self.assertEqual(ix.totals()[0][B][4:6], [30000000000, 2])
        # replace blocks 11..13 with a competing branch where #12 has no jackpot and C mines
        del c.blocks[11:]
        for h in range(11, 15):
            c.add(C, 100, salt='f%d' % h)
        dropped = ix.unwind_to_canonical()
        self.assertEqual(dropped, 3)
        ix.step()
        t, jps = ix.totals()
        self.assertEqual(t[B][4:6], [10000000000, 1])        # the orphaned V2 jackpot is gone
        self.assertEqual(t[C][:2], [400, 4])
        self.assertEqual(ix.tip, 14)
        self.assertEqual(ix.reorgs[-1]['depth'], 3)

    def test_state_round_trip_and_resume(self):
        d = tempfile.mkdtemp()
        try:
            c = self.chain()
            ix = make(c)
            ix.state_path = os.path.join(d, 's.json')
            ix.step()
            ix.save()
            ix2 = make(c)
            ix2.state_path = ix.state_path
            ix2.load()
            self.assertEqual(ix2.rows, ix.rows)
            c.calls.clear()
            ix2.step()
            self.assertNotIn('getrawtransaction', c.calls)   # nothing re-read
        finally:
            shutil.rmtree(d)

    def test_document_shape(self):
        ix = make(self.chain())
        ix.step()
        doc = ix.document()
        self.assertEqual(doc['tip'], 13)
        self.assertEqual(len(doc['fields']), 8)
        self.assertEqual(doc['addresses'][B][4], 30000000000)

    def test_parallel_first_pass_equals_sequential(self):
        c = self.chain()
        seq = make(c); seq.step()
        par = make(c); par.workers = 4
        old = aei.BATCH; aei.BATCH = 5
        try:
            par.step()
        finally:
            aei.BATCH = old
        self.assertEqual(par.rows, seq.rows)

    def test_parser_matches_explorer_layout(self):
        p = aei.parse_jackpot_tx(jackpot_hex(B, 12345))
        self.assertEqual((p['tx_type'], p['out_type'], p['amount_sat'], p['winner']), (2, 0, 12345, B))
        self.assertIsNone(aei.parse_jackpot_tx('zz'))
        self.assertIsNone(aei.parse_jackpot_tx('0100'))


if __name__ == '__main__':
    unittest.main()

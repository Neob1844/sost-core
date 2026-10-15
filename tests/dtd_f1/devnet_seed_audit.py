#!/usr/bin/env python3
"""Independent DTD-F1 audit of a running node (devnet E2E). Written from the spec
(docs/v40000/DTD_F1_SEED_POW_COMMIT.md), not from the C++ code.

For every height h in [lo, tip] with a DTD draw (getlotteryaudit is_lottery_block):
  * the 16 window entries are the chain's block hashes (getblockhash) and PoW commits (getblock)
  * seed_rule is V11_BLOCK_ID for h < V17 and V17_POW_COMMIT for h >= V17
  * seed_input == domain || entries || u64le(h), with domain/entries chosen by the rule
  * seed == sha256(seed_input); winner_index == u64le(seed[0:8]) % eligible_count
  * winner_address == the DTD winner actually paid in block h (getblock lottery_winner_address)
For every Jackpot V2 height (getjackpotv2audit is_v2_jackpot) in range:
  * seed_hex == sha256(SOST_HIST_JACKPOT[_V17] || ids|commits || u64le(h))
  * from V17: winner_address == the jackpot winner paid by block h (v17_reward.jackpot_winner)
Usage: devnet_seed_audit.py RPC_PORT V17_HEIGHT LO [HI]
"""
import hashlib, json, struct, sys, urllib.request

port, V17, lo = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
def rpc(m, p=()):
    req = urllib.request.Request('http://127.0.0.1:%d/' % port, json.dumps({'method': m, 'params': list(p), 'id': 1}).encode(),
                                 {'content-type': 'application/json'})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    if d.get('error'): raise RuntimeError('%s %s: %s' % (m, p, d['error']))
    return d['result']
tip = int(rpc('getblockcount'))
hi = int(sys.argv[4]) if len(sys.argv) > 4 else tip
blocks = {}
def blk(h):
    if h not in blocks:
        bh = rpc('getblockhash', [h]); blocks[h] = rpc('getblock', [bh])
    return blocks[h]
u64 = lambda x: struct.pack('<Q', x)
fails, draws, v17draws, jps, jpv17 = 0, 0, 0, 0, 0
def bad(msg):
    global fails; fails += 1; print('FAIL', msg)
for h in range(max(lo, 17), hi + 1):
    a = rpc('getlotteryaudit', [h])
    if a.get('is_lottery_block'):
        draws += 1
        v17 = h >= V17
        v17draws += v17
        want_rule = 'V17_POW_COMMIT' if v17 else 'V11_BLOCK_ID'
        dom = b'SOST_DTD_V17' if v17 else b'SOST_LOTTERY_V11'
        win = a['rng_history_blocks']
        if [w['height'] for w in win] != list(range(h - 16, h)): bad('h=%d window heights' % h); continue
        for w in win:
            b = blk(w['height'])
            if w['hash'] != b['hash'] or w['commit'] != b['commit']: bad('h=%d window entry %d != chain' % (h, w['height']))
        ent = b''.join(bytes.fromhex(w['commit'] if v17 else w['hash']) for w in win)
        pre = dom + ent + u64(h)
        seed = hashlib.sha256(pre).digest()
        if a.get('seed_rule') != want_rule: bad('h=%d seed_rule %s' % (h, a.get('seed_rule')))
        if a['seed_input_hex'] != pre.hex(): bad('h=%d seed_input' % h)
        if a['seed_hex'] != seed.hex(): bad('h=%d seed' % h)
        E = a['eligible_count']
        if E > 0:
            if a['winner_index'] != struct.unpack('<Q', seed[:8])[0] % E: bad('h=%d winner_index' % h)
        paid = blk(h).get('lottery_winner_address', '') or ''
        if (a['winner_address'] or '') != paid and int(blk(h).get('lottery_payout', 0) or 0) > 0:
            bad('h=%d audit winner %s != paid %s' % (h, a['winner_address'], paid))
    j = rpc('getjackpotv2audit', [h])
    if j.get('is_v2_jackpot'):
        jps += 1
        v17 = h >= V17
        jpv17 += v17
        dom = b'SOST_HIST_JACKPOT_V17' if v17 else b'SOST_HIST_JACKPOT'
        ent = b''.join(bytes.fromhex(blk(x)['commit'] if v17 else blk(x)['hash']) for x in range(h - 16, h))
        if j.get('seed_hex') != hashlib.sha256(dom + ent + u64(h)).hexdigest(): bad('jackpot h=%d seed' % h)
        if j.get('seed_rule') != ('V17_POW_COMMIT' if v17 else 'V11_BLOCK_ID'): bad('jackpot h=%d rule' % h)
        if v17:
            vr = blk(h).get('v17_reward') or {}
            pw = vr.get('jackpot_winner', '') or ''
            if (j.get('winner_address') or '') != pw: bad('jackpot h=%d audit winner %s != paid %s' % (h, j.get('winner_address'), pw))
        print('jackpot h=%d rule=%s eligible=%s winner=%s' % (h, j.get('seed_rule'), j.get('eligible_count'), j.get('winner_address') or '-'))
print('AUDIT heights %d..%d: DTD draws %d (V17 %d), V2 jackpots %d (V17 %d), failures %d' % (lo, hi, draws, v17draws, jps, jpv17, fails))
sys.exit(1 if fails else 0)

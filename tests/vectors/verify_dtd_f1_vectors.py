#!/usr/bin/env python3
"""Independent check of the V17 DTD-F1 normative vectors (tests/vectors/dtd_f1_v17.json).

Written from the spec (docs/v40000/DTD_F1_SEED_POW_COMMIT.md), not from the C++ code:
  DTD     seed = sha256("SOST_DTD_V17"          || commit[h-16..h-1] || u64le(h)); idx = u64le(seed[0:8]) % E
  Jackpot seed = sha256("SOST_HIST_JACKPOT_V17" || commit[h-16..h-1] || u64le(h));
          roll = u64le(seed[0:8]) % total_weight; winner = first i with cumulative weight > roll
  pre-V17 DTD control: sha256("SOST_LOTTERY_V11"  || block_id[h-16..h-1] || u64le(h))
Usage: python3 -I verify_dtd_f1_vectors.py [dtd_f1_v17.json]
"""
import hashlib, json, os, struct, sys

def u64le(x): return struct.pack('<Q', x)
def sha(b): return hashlib.sha256(b).digest()
def tagged(tag, x): return sha(tag + u64le(x))

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dtd_f1_v17.json')
v = json.load(open(path))
fails = 0
def check(name, cond):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name)
    if not cond: fails += 1

h = v['draw_height']
check('domains', v['dtd_domain'] == 'SOST_DTD_V17' and v['jackpot_domain'] == 'SOST_HIST_JACKPOT_V17')
ins = v['input_commitments']
check('16 input commitments for [h-16, h-1] ascending', [c['height'] for c in ins] == list(range(h - 16, h)))
check('commit(x) = sha256("commit" || u64le(x)) (block h-1 included)',
      all(bytes.fromhex(c['commit']) == tagged(b'commit', c['height']) for c in ins))
commits = b''.join(bytes.fromhex(c['commit']) for c in ins)

dseed = sha(b'SOST_DTD_V17' + commits + u64le(h))
check('DTD seed', dseed.hex() == v['dtd_seed'])
E = len(v['dtd_eligible_set'])
check('DTD eligible set is raw-pkh sorted', v['dtd_eligible_set'] == sorted(v['dtd_eligible_set']))
wi = struct.unpack('<Q', dseed[:8])[0] % E
check('DTD winner index = u64le(seed[0:8]) %% E (E=%d -> %d)' % (E, wi), wi == v['dtd_winner_index'])
check('DTD winner', v['dtd_eligible_set'][wi] == v['dtd_winner'])

jseed = sha(b'SOST_HIST_JACKPOT_V17' + commits + u64le(h))
check('Jackpot seed', jseed.hex() == v['jackpot_seed'])
ws = v['jackpot_weighted_set']
check('Jackpot set is raw-pkh sorted', [w['pkh'] for w in ws] == sorted(w['pkh'] for w in ws))
tot = sum(w['weight'] for w in ws)
roll = struct.unpack('<Q', jseed[:8])[0] % tot
cum, jw = 0, -1
for i, w in enumerate(ws):
    cum += w['weight']
    if roll < cum: jw = i; break
check('Jackpot winner index (total weight %d, roll %d -> %d)' % (tot, roll, jw), jw == v['jackpot_winner_index'])
check('Jackpot winner', ws[jw]['pkh'] == v['jackpot_winner'])
check('DTD and Jackpot seeds differ (domain separation)', dseed != jseed)

rb = v['resigned_block']
ids = [x['block_id'] for x in rb['variants']]
sigs = [x['miner_signature'] for x in rb['variants']]
check('re-signed block is h-1 and its commit is in the window', rb['height'] == h - 1 and rb['commit'] == ins[-1]['commit'])
check('variants: distinct signatures and distinct block_ids', len(set(ids)) == len(ids) == len(set(sigs)) >= 3)
# The V17 seeds read only the commits: substituting any variant block_id leaves them unchanged.
legacy = [sha(b'SOST_LOTTERY_V11' + b''.join(tagged(b'blockid', x) for x in range(h - 16, h - 1)) + bytes.fromhex(i) + u64le(h))
          for i in ids]
check('legacy (block_id) seed would differ per variant', len(set(legacy)) == len(ids))
check('V17 result identical for every variant (flags)', rb['all_variants_same_dtd_seed_and_winner'] and rb['all_variants_same_jackpot_seed_and_winner'])

pc = v['pre_v17_control']
pids = b''.join(tagged(b'mainnet-shape', x) for x in range(pc['height'] - 16, pc['height']))
check('pre-V17 control seed (SOST_LOTTERY_V11 over block_ids)', sha(b'SOST_LOTTERY_V11' + pids + u64le(pc['height'])).hex() == pc['seed'])

print('%d failure(s)' % fails)
sys.exit(1 if fails else 0)

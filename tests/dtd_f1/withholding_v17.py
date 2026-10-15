#!/usr/bin/env python3
"""DTD-F1 residual: block withholding / PoW re-grinding once re-signing is closed.

With the V17 rule each candidate block h-1 is a NEW PoW solution (new commit). This Monte Carlo
uses the real V17 seed formulas (sha256("SOST_DTD_V17" || commit[h-16..h-1] || u64le(h)) and
"SOST_HIST_JACKPOT_V17" with the linear weighted roll) with random commits for each candidate
h-1, and the miner keeps the best of n. Then the economics of discarding a valid block:
rational iff  gain = q*Prize  >  loss = (1-alpha)*R_m   (R_m = what the discarded block pays
its miner). Amounts at the current subsidy S = 7.85100863 SOST, fees ~ 0.
"""
import hashlib, os, struct, random
u64 = lambda x: struct.pack('<Q', x)
rng = random.Random(17)
S = 7.85100863
H = 40266
base = b''.join(hashlib.sha256(b'c' + u64(i)).digest() for i in range(15))
def dtd_idx(c, E):
    s = hashlib.sha256(b'SOST_DTD_V17' + base + c + u64(H)).digest(); return struct.unpack('<Q', s[:8])[0] % E
def jp_win(c, w_att, total):
    s = hashlib.sha256(b'SOST_HIST_JACKPOT_V17' + base + c + u64(H)).digest()
    return struct.unpack('<Q', s[:8])[0] % total < w_att          # attacker holds the first w_att units (canonical order is arbitrary)
T = 4000
print('(1) NORMAL DTD, V17 seed: P(attacker ticket wins | best of n valid PoW blocks for h-1), k=1 ticket   theory / Monte Carlo')
print('     E ' + ''.join('   n=%-2d theory/sim   ' % n for n in (1, 2, 3, 5, 10)))
for E in (2, 5, 10, 50, 74, 100):
    row = []
    for n in (1, 2, 3, 5, 10):
        hit = sum(1 for _ in range(T) if any(dtd_idx(rng.randbytes(32), E) == 0 for _ in range(n)))
        row.append('%.4f / %.4f' % (1 - (1 - 1 / E) ** n, hit / T))
    print('  %4d   ' % E + '    '.join(row))
print('\n(1b) JACKPOT V2, V17 seed: P(attacker weight share w wins | best of n)   theory / Monte Carlo')
for w in (0.05, 0.1, 0.3, 0.5):
    row = []
    for n in (1, 2, 3, 5):
        hit = sum(1 for _ in range(T) if any(jp_win(rng.randbytes(32), int(w * 2016), 2016) for _ in range(n)))
        row.append('n=%d %.4f/%.4f' % (n, 1 - (1 - w) ** n, hit / T))
    print('  w=%.2f  ' % w + '   '.join(row))

regimes = {'pre-V17 (50/50)': (S / 2, S / 2), 'V17 (80/15/5)': (S * 0.80, S * 0.15)}
print('\n(2a) NORMAL DTD: discard rational iff q > q* = (1-alpha)*R_m/DTD  (q = attacker ticket share, <= 1)')
alphas = (0.05, 0.10, 0.30, 0.50, 0.70, 0.90)
print('  %-16s' % 'regime' + ''.join('alpha=%-6.2f' % a for a in alphas))
for k, (Rm, D) in regimes.items():
    print('  %-16s' % k + ''.join(('%-12s' % ('%.3f' % ((1 - a) * Rm / D)) if (1 - a) * Rm / D < 1 else '%-12s' % 'never') for a in alphas))
Rm, D = regimes['V17 (80/15/5)']
print('  V17 example E=74 k=1: gain/discard <= %.4f SOST vs loss %.4f SOST at alpha=0.5' % (D / 74, 0.5 * Rm))
print('  V17 even k=E-1 of E=2 (q=0.5) at alpha=0.9: q*=%.3f -> %s' % (0.1 * Rm / D, 'rational' if 0.5 > 0.1 * Rm / D else 'irrational'))
print('\n(2b) JACKPOT: gain = w*P (w = attacker weight share), loss = (1-alpha)*R_m; break-even alpha with w = alpha')
for P in (100, 400, 500):
    for k, (Rm, D) in regimes.items():
        be = next(a / 1000 for a in range(1, 1000) if (a / 1000) * P > (1 - a / 1000) * Rm)
        print('  P=%3d %-16s break-even alpha=%.3f   at alpha=0.3: gain %.1f vs loss %.2f SOST' % (P, k, be, 0.3 * P, 0.7 * Rm))

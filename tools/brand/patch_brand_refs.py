#!/usr/bin/env python3
"""Cache-bust brand asset URLs (only those) and re-aim the Explorer loader's Sigma pulse at the new emblem's glyph.
Usage: patch_brand_refs.py SRC_DIR DST_DIR [loader_css.json]   (DST gets only files that changed; SRC untouched)"""
import json, os, re, sys, difflib
SRC, DST = sys.argv[1], sys.argv[2]
VER = 'rs20261112'
NAMES = r'(?:wsost-eye[-a-z0-9]*|sost-eye[-a-z0-9]*|favicon[-a-z0-9x]*|apple-touch-icon|android-chrome[-a-z0-9x]*|og-sost-logo|sost-logo|wsost-gold-vault[-a-z0-9]*|wsost-logo[-0-9]*|sost-app/icon[-a-z0-9]*)'
RX = re.compile(r'(?<![A-Za-z0-9_-])(' + NAMES + r'\.(?:png|ico|svg|webp))(\?v=[A-Za-z0-9._-]*)?(?![A-Za-z0-9_?.-])')
LOADER = None
if len(sys.argv) > 3:
    L = json.load(open(sys.argv[3]))['loader_css']
    LOADER = [('#exLoadOv .sx-sig{left:38.18%;top:37.89%;width:25.39%;height:25.39%;',
               '#exLoadOv .sx-sig{left:%.2f%%;top:%.2f%%;width:%.2f%%;height:%.2f%%;' % (L['sig']['left'], L['sig']['top'], L['sig']['size'], L['sig']['size'])),
              ('#exLoadOv .sx-halo{left:32.32%;top:32.03%;width:37.11%;height:37.11%;',
               '#exLoadOv .sx-halo{left:%.2f%%;top:%.2f%%;width:%.2f%%;height:%.2f%%;' % (L['halo']['left'], L['halo']['top'], L['halo']['size'], L['halo']['size']))]
rep = {}
for root, _, files in os.walk(SRC):
    for f in files:
        p = os.path.join(root, f); rel = os.path.relpath(p, SRC)
        t = open(p, encoding='utf-8', errors='surrogateescape').read()
        n = [0]
        def sub(m):
            n[0] += 1; return m.group(1) + '?v=' + VER
        t2 = RX.sub(sub, t)
        ld = 0
        if LOADER and rel == 'sost-explorer.html':
            for a, b in LOADER:
                assert t2.count(a) == 1, a; t2 = t2.replace(a, b); ld += 1
        if t2 != t:
            # safety: every changed line may differ only by version tokens / loader geometry
            for a, b in zip(t.splitlines(), t2.splitlines()):
                if a != b:
                    na = RX.sub(lambda m: m.group(1) + '?v=X', a); nb = RX.sub(lambda m: m.group(1) + '?v=X', b)
                    if LOADER:
                        for x, y in LOADER: na = na.replace(x, y)
                    assert na == nb, (rel, a[:200], b[:200])
            assert len(t.splitlines()) == len(t2.splitlines()), rel
            q = os.path.join(DST, rel); os.makedirs(os.path.dirname(q), exist_ok=True)
            open(q, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(t2)
            rep[rel] = dict(refs=n[0], loader_lines=ld)
print(json.dumps(dict(files=len(rep), refs=sum(v['refs'] for v in rep.values()), loader=sum(v['loader_lines'] for v in rep.values())), indent=0))
json.dump(rep, open(os.path.join(DST, '..', 'patch_report.json'), 'w'), indent=1)

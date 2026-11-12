#!/usr/bin/env python3
"""Gold Sigma / Rainbow Edition (owner GO 12-Nov-2026): visual-only text patch over EXACT production bytes.
usage: patch_gold.py SRC DST build_report.json GOLD_PNG_256
  1. cache token  ?v=rs20261112  ->  ?v=rs20261112g  (brand image URLs only; set by patch_brand_refs.py this morning)
  2. Explorer loader pulse CSS: two position rules, values measured by build_rainbow.py on the new Sigma
  3. hidden (display:none) legacy header <img> in both explorers: embedded old red-Sigma PNG -> new logo PNG
  4. universe/core/u-emblem.js: header glow overlay retired (it paints the OLD eye's Sigma geometry over the logo)
Every changed line is asserted to differ only in those parts; line counts are preserved."""
import base64, io, json, os, re, sys
SRC, DST, REP, GOLD = sys.argv[1:5]
L = json.load(open(REP))['loader_css']
f2 = lambda v: '%.2f%%' % v
OLD_SIG = '.sx-sig{left:33.75%;top:35.00%;width:33.12%;height:33.12%;'
OLD_HALO = '.sx-halo{left:26.09%;top:27.34%;width:48.44%;height:48.44%;'
NEW_SIG = '.sx-sig{left:%s;top:%s;width:%s;height:%s;' % (f2(L['sig']['left']), f2(L['sig']['top']), f2(L['sig']['size']), f2(L['sig']['size']))
NEW_HALO = '.sx-halo{left:%s;top:%s;width:%s;height:%s;' % (f2(L['halo']['left']), f2(L['halo']['top']), f2(L['halo']['size']), f2(L['halo']['size']))
GOLD_URI = 'data:image/png;base64,' + base64.b64encode(open(GOLD, 'rb').read()).decode()
HDR = re.compile(r'<a href="https://sostcore\.com" class="logo" style="text-decoration:none">\s*<img src="(data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=]+)')
EMB_OLD = "    if (!el || el.__emb) return; el.__emb = 1;"
EMB_NEW = "    return;   // owner 12-Nov-2026: Gold Sigma / Rainbow Edition logo; this overlay painted the OLD eye's Sigma geometry over it (retired)\n" + EMB_OLD
rep = {'files': {}}
for dp, _, fs in os.walk(SRC):
    for f in fs:
        src = os.path.join(dp, f); rel = os.path.relpath(src, SRC)
        if not rel.endswith(('.html', '.js', '.css', '.webmanifest', '.json')): continue
        t = open(src, encoding='utf-8').read(); n = {}
        t2 = t.replace('v=rs20261112', 'v=rs20261112g'); n['token'] = t.count('v=rs20261112')
        n['loader'] = t2.count(OLD_SIG) + t2.count(OLD_HALO); t2 = t2.replace(OLD_SIG, NEW_SIG).replace(OLD_HALO, NEW_HALO)
        m = HDR.search(t2); old_uri = m.group(1) if m else None
        if old_uri: assert t2.count(old_uri) == 1; t2 = t2.replace(old_uri, GOLD_URI); n['hidden_header'] = 1
        if rel.replace(os.sep, '/') == 'universe/core/u-emblem.js':
            assert t2.count(EMB_OLD) == 1; t2 = t2.replace(EMB_OLD, EMB_NEW); n['emblem'] = 1
        if t2 == t: continue
        a, b = t.split('\n'), t2.split('\n')
        if 'emblem' in n: b = [x for x in b if not x.startswith("    return;   // owner 12-Nov-2026")]
        assert len(a) == len(b), rel
        for x, y in zip(a, b):
            if x == y: continue
            yy = y.replace('v=rs20261112g', 'v=rs20261112').replace(NEW_SIG, OLD_SIG).replace(NEW_HALO, OLD_HALO)
            yy = yy.replace(GOLD_URI, old_uri) if old_uri else yy; xx = x
            assert xx == yy, (rel, x[:120], y[:120])
        out = os.path.join(DST, rel); os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'w', encoding='utf-8', newline='').write(t2); rep['files'][rel] = {k: v for k, v in n.items() if v}
rep['totals'] = {k: sum(v.get(k, 0) for v in rep['files'].values()) for k in ('token', 'loader', 'hidden_header', 'emblem')}
rep['loader_css'] = dict(sig=NEW_SIG, halo=NEW_HALO)
json.dump(rep, open(os.path.join(DST, 'patch_gold_report.json'), 'w'), indent=1); print(len(rep['files']), 'files', rep['totals'])

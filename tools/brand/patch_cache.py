#!/usr/bin/env python3
"""Cache-busting for the brand identity (owner P0 visual order, 12-Nov-2026). Changes ONLY `?v=` version tokens.
usage: patch_cache.py SRC DST
Root cause fixed: nginx sends no Cache-Control for images/JS, so browsers keep heuristically-fresh copies under unchanged URLs.
The header is built by universe/core/u-nav.js (?v=u1-20261105, unchanged since 5-Nov) -> a cached old u-nav.js still asked for
sost-eye-128.png?v=id30000 (cached red eye) and loaded u-emblem.js (no version) whose cached copy paints the OLD eye's Sigma glow.
Every reference to a brand image, video poster, brand-drawing script or web manifest gets ?v=TOKEN (new URL = no stale cache).
Each changed line is asserted to be identical to the original once all `?v=...` tokens are removed."""
import os, re, sys, json
SRC, DST = sys.argv[1:3]; TOK = 'rs20261112g'
END = r'''(?=["'`)\s\\,;&<]|$)'''
IMG = (r'(?:sost-eye|wsost-eye|sost-logo|wsost-logo|favicon|apple-touch-icon|android-chrome|og-sost|sost-avatar|wsost-gold-vault|'
       r'sost-icon-|wsost-icon-|sigma-emblem|sost-intro-poster|sost-mechanisms-poster)[\w.-]*\.(?:png|webp|ico|svg|jpe?g)|coins/sost\.png')
RES = r'(?:u-nav|nav-toggle|asset-registry|u-emblem|u-legacy-skin)\.js|site\.webmanifest'
PAT = re.compile(r'((?:' + IMG + r'|' + RES + r'))(?:\?v=[A-Za-z0-9._-]*)?' + END)
APP_ICON = re.compile(r'((?:^|["\'/])icon(?:-maskable)?-\d+\.png)(?:\?v=[A-Za-z0-9._-]*)?' + END)   # sost-app/ only
APP_MANIFEST = re.compile(r'(href="manifest\.json)(?:\?v=[A-Za-z0-9._-]*)?(")')
STRIP = re.compile(r'\?v=[A-Za-z0-9._-]*')
rep = {}
for dp, _, fs in os.walk(SRC):
    for f in fs:
        src = os.path.join(dp, f); rel = os.path.relpath(src, SRC).replace(os.sep, '/')
        if not f.endswith(('.html', '.js', '.css', '.webmanifest', '.json')): continue
        try: t = open(src, encoding='utf-8').read()
        except UnicodeDecodeError: continue
        t2, n = PAT.subn(lambda m: m.group(1) + '?v=' + TOK, t)
        if '/sost-app/' in '/' + rel:
            t2, n2 = APP_ICON.subn(lambda m: m.group(1) + '?v=' + TOK, t2); n += n2
            t2, n3 = APP_MANIFEST.subn(lambda m: m.group(1) + '?v=' + TOK + m.group(2), t2); n += n3
        if rel == 'brand/index.html':                      # JS-built image/download URLs on the brand page
            for a in ('.png" width="', '.png" download><b>'):
                t2 = t2.replace("'" + a, "'" + a.replace('.png"', '.png?v=' + TOK + '"'))
        if t2 == t: continue
        a, b = t.split('\n'), t2.split('\n'); assert len(a) == len(b), rel
        changed = 0
        for x, y in zip(a, b):
            if x != y:
                changed += 1
                assert STRIP.sub('', x) == STRIP.sub('', y), (rel, x[:160], y[:160])
        out = os.path.join(DST, rel); os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'w', encoding='utf-8', newline='').write(t2); rep[rel] = changed
# Explorer PWA service worker: new cache name so the next activation purges the old shell cache (caches only; IndexedDB /
# localStorage wallet data are never touched by a service worker). Network-first is unchanged.
for h in ('sost-app/sw.js',):
    sp, dp_ = os.path.join(SRC, h), os.path.join(DST, h)
    if os.path.exists(sp):
        cur = open(dp_ if os.path.exists(dp_) else sp, encoding='utf-8').read()
        m = re.search(r"const CACHE_NAME = 'sost-app-v(\d+)';", cur); assert m, h
        new = cur.replace(m.group(0), "const CACHE_NAME = 'sost-app-v%d';   // %s: brand identity (Gold Sigma) cache refresh" % (int(m.group(1)) + 1, TOK))
        os.makedirs(os.path.dirname(dp_), exist_ok=True); open(dp_, 'w', encoding='utf-8', newline='').write(new); rep[h] = rep.get(h, 0) + 1
json.dump(rep, open(os.path.join(DST, 'patch_cache_report.json'), 'w'), indent=1, sort_keys=True)
print(len(rep), 'files,', sum(rep.values()), 'lines changed')

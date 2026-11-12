#!/usr/bin/env python3
"""Deterministic SOST_OFFICIAL_BRAND_KIT.zip + downloads/SHA256SUMS.txt (zip line first, then every file in the kit)."""
import hashlib, os, sys, zipfile
B = sys.argv[1]                                    # website/brand
DIRS = ['exchange', 'guidelines', 'legacy', 'sost', 'wsost']
files = sorted(os.path.relpath(os.path.join(r, f), B) for d in DIRS for r, _, fs in os.walk(os.path.join(B, d)) for f in fs)
sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
inner = ''.join(f'{sha(os.path.join(B, f))}  {f}\n' for f in files)
zp = os.path.join(B, 'downloads', 'SOST_OFFICIAL_BRAND_KIT.zip'); os.makedirs(os.path.dirname(zp), exist_ok=True)
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for f in files + ['SHA256SUMS.txt']:
        zi = zipfile.ZipInfo('SOST_OFFICIAL_BRAND_KIT/' + f, (2026, 11, 12, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o644 << 16
        z.writestr(zi, inner.encode() if f == 'SHA256SUMS.txt' else open(os.path.join(B, f), 'rb').read())
open(os.path.join(B, 'downloads', 'SHA256SUMS.txt'), 'w').write(f'{sha(zp)}  SOST_OFFICIAL_BRAND_KIT.zip\n' + inner)
print(len(files) + 1, 'entries', os.path.getsize(zp), 'bytes', sha(zp))

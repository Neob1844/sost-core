#!/usr/bin/env python3
"""Build the SOST / wSOST brand assets from the two official originals (owner-supplied PNGs, 1254x1254 RGB on black).
Geometry, proportions and symbols are NOT altered: only resampling and an exact unblend of the black background."""
import json, hashlib, sys, os
import numpy as np
from PIL import Image
SRC = {'sost': '/mnt/c/Users/ferna/Downloads/Emblema del ojo rojo con Sigma luminoso.png',
       'wsost': '/mnt/c/Users/ferna/Downloads/Emblema ocular rojo con WΣ luminoso.png'}
OUT = sys.argv[1]; SIZES = [2048, 1024, 512, 256, 128, 64]; EXCH = [512, 256, 200, 128, 64, 32]
report = {}
def resize_rgba(im, s):   # resample in premultiplied space: no dark/coloured halos at the glow edge
    return im.convert('RGBa').resize((s, s), Image.LANCZOS).convert('RGBA')
def save(im, path):
    im.save(path, 'PNG', optimize=True)   # Pillow writes no EXIF / text chunks here: no personal metadata
for name, src in SRC.items():
    o = Image.open(src).convert('RGB'); a = np.asarray(o).astype(np.float64); H, W, _ = a.shape
    mx = a.max(axis=2)
    # disc: bright red rim. centre/radius from the rim pixels (R high), robust to the glow
    ys, xs = np.nonzero((a[..., 0] > 120))
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2; r = ((xs.max() - xs.min()) + (ys.max() - ys.min())) / 4
    yy, xx = np.mgrid[0:H, 0:W]; d = np.hypot(xx - cx, yy - cy)
    inside = d <= r - 6                                    # emblem body: fully opaque
    alpha = np.clip(mx / 255.0, 0, 1)
    alpha[mx < 4] = 0                                      # JPEG-like noise in the black field -> fully transparent
    alpha[inside] = 1.0
    rgb = np.where(alpha[..., None] > 0, a / np.maximum(alpha[..., None], 1e-6), 0)
    rgb = np.clip(rgb, 0, 255)
    rgba = np.dstack([rgb, alpha * 255]).round().astype(np.uint8)
    T = Image.fromarray(rgba, 'RGBA')
    # check: transparent master composited over black must reproduce the original
    comp = (rgba[..., :3].astype(np.float64) * (rgba[..., 3:] / 255.0)); diff = np.abs(comp - a)
    rep = dict(source=os.path.basename(src), source_sha256=hashlib.sha256(open(src, 'rb').read()).hexdigest(), source_size=[W, H],
               disc_centre=[round(cx, 1), round(cy, 1)], disc_radius=round(r, 1),
               recomposite_over_black_max_abs_diff=float(diff.max()), recomposite_mean_abs_diff=round(float(diff.mean()), 4),
               transparent_pixels_pct=round(100 * float((rgba[..., 3] == 0).mean()), 2), files=[])
    for s in SIZES:
        t = resize_rgba(T, s); p = f'{OUT}/{name}/png/{name}-emblem-{s}-transparent.png'; save(t, p)
        b = o.resize((s, s), Image.LANCZOS); p2 = f'{OUT}/{name}/png/{name}-emblem-{s}-black.png'; save(b, p2)
        rep['files'] += [p, p2]
    for s in EXCH:
        t = resize_rgba(T, s); p = f'{OUT}/exchange/{name}-{s}.png'; save(t, p); rep['files'].append(p)
    report[name] = rep
json.dump(report, open(f'{OUT}/guidelines/build_report.json', 'w'), indent=1)
for k, v in report.items(): print(k, {x: v[x] for x in ('disc_centre', 'disc_radius', 'recomposite_over_black_max_abs_diff', 'recomposite_mean_abs_diff', 'transparent_pixels_pct')})

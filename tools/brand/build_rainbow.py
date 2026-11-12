#!/usr/bin/env python3
"""SOST official identity (owner order 12-Nov-2026): rainbow Sigma (SOST) and rainbow wSigma (wSOST).

The two owner-supplied PNGs are the canonical artwork. Nothing is redrawn or regenerated: every output is the original
pixels, only (a) placed on a square canvas centred on the emblem's own alpha bounding box (the circle sits ~10 px off
centre on the 1254 px source canvas; nothing is cropped) and (b) resampled in premultiplied-alpha space with Lanczos.
Outside the circle stays fully transparent (alpha 0) in every transparent variant; '-black' / RGB variants are the
same image composited over #000 (the site background).

Usage: build_rainbow.py OUT_DIR WEB_ROOT
  OUT_DIR  : kit + report (brand kit layout)
  WEB_ROOT : website/ tree whose existing brand files are replaced in place (same names, same pixel sizes, same modes)
"""
import hashlib, io, json, os, shutil, sys
import numpy as np
from PIL import Image, ImageFilter

# SOST: definitive CEX logo 'Gold Sigma / Rainbow Edition' (owner GO 12-Nov-2026, 19:35 local file). The rainbow-disc Sigma
# ('Emblema Sigma de Energía Arcoíris.png', d93e1364…) of the same morning is historical (brand/legacy/rainbow-disc/).
SRC = {'sost': os.environ.get('SOST_SRC', '/mnt/c/Users/ferna/Downloads/Sigma dorada en órbita multicolor.png'),
       'wsost': '/mnt/c/Users/ferna/Downloads/Emblema wΣ de Neón Arcoíris.png'}
OUT, WEB = sys.argv[1], sys.argv[2]
KIT_SIZES = [2048, 1024, 512, 256, 128, 64, 32]
EXCH = [1024, 512, 256, 200, 128, 64, 32]
REPORT = {'sources': {}, 'outputs': []}


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def centred(name):
    im = Image.open(SRC[name]).convert('RGBA')
    a = np.asarray(im)
    ys, xs = np.nonzero(a[..., 3] > 8)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    side = int(max(x1 - x0 + 1, y1 - y0 + 1)) + 6                     # 3 px clear margin each side, glow never touches the edge
    cx, cy = (x0 + x1 + 1) / 2, (y0 + y1 + 1) / 2
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.paste(im, (int(round(side / 2 - cx)), int(round(side / 2 - cy))))
    REPORT['sources'][name] = dict(file=os.path.basename(SRC[name]), sha256=sha(SRC[name]), size=list(im.size), mode=im.mode,
                                   alpha_bbox=[int(x0), int(y0), int(x1), int(y1)], centred_canvas=side,
                                   transparent_pct=round(100 * float((a[..., 3] == 0).mean()), 2))
    return canvas


def rs(im, s):                                                         # premultiplied Lanczos: no dark halo on the glow
    return im.convert('RGBa').resize((s, s), Image.LANCZOS).convert('RGBA')


def on_black(im):
    b = Image.new('RGBA', im.size, (0, 0, 0, 255)); b.alpha_composite(im); return b


def inset(im, s, frac, bg=(0, 0, 0, 255)):                             # emblem at frac of an s x s canvas (maskable safe zone)
    c = Image.new('RGBA', (s, s), bg); e = rs(im, int(round(s * frac))); c.alpha_composite(e, ((s - e.width) // 2, (s - e.height) // 2)); return c


def save(im, path, mode=None, fmt=None, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if mode: im = im.convert(mode)
    fmt = fmt or {'png': 'PNG', 'webp': 'WEBP', 'ico': 'ICO'}[path.rsplit('.', 1)[1].lower()]
    if fmt == 'PNG': kw.setdefault('optimize', True)
    im.save(path, fmt, **kw)
    REPORT['outputs'].append(dict(path=path, size=list(im.size), mode=im.mode, sha256=sha(path)))


def web_replace(rel, im_fn):
    """Replace WEB/rel only if it exists; keep its pixel size and mode."""
    p = os.path.join(WEB, rel)
    if not os.path.exists(p):
        return
    old = Image.open(p); size, mode = old.size, old.mode
    if rel.endswith('.ico'):
        sizes = sorted(old.info.get('sizes') or [size])
        big = max(s[0] for s in sizes)
        save(im_fn(big), p, sizes=sizes)
        return
    new = im_fn(size[0])
    if mode in ('RGB', 'P', 'L'):
        new = on_black(new).convert('RGB')
    if rel.endswith('.webp'):
        save(new, p, quality=92, method=6)
    else:
        save(new, p)


M = {n: centred(n) for n in SRC}

# ---------- brand kit ----------
for n, m in M.items():
    shutil.copyfile(SRC[n], f'{OUT}/{n}/original/{n}-rainbow-original.png') if os.path.isdir(f'{OUT}/{n}/original') else None
    for s in KIT_SIZES:
        t = rs(m, s)
        save(t, f'{OUT}/{n}/png/{n}-logo-{s}-transparent.png')
        save(on_black(t).convert('RGB'), f'{OUT}/{n}/png/{n}-logo-{s}-black.png')
    for s in EXCH:
        save(rs(m, s), f'{OUT}/exchange/{n}-icon-{s}.png')
s = M['sost']
save(rs(s, 48), f'{OUT}/sost/favicon/favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)])
for px in (16, 32, 48, 96, 144):
    save(rs(s, px), f'{OUT}/sost/favicon/favicon-{px}x{px}.png')
save(on_black(rs(s, 180)).convert('RGB'), f'{OUT}/sost/favicon/apple-touch-icon.png')
for px in (192, 512):
    save(rs(s, px), f'{OUT}/sost/favicon/android-chrome-{px}x{px}.png')
    save(inset(s, px, 0.80).convert('RGB'), f'{OUT}/sost/favicon/android-chrome-maskable-{px}x{px}.png')

# ---------- website: same names, same sizes ----------
SOST_FILES = ['sost-logo.png', 'favicon.ico', 'favicon-48x48.png', 'favicon-96x96.png', 'favicon-144x144.png',
              'android-chrome-192x192.png', 'android-chrome-512x512.png', 'sost-app/icon-192.png', 'sost-app/icon-512.png',
              'sost-avatar-transparent-100.png', 'sost-avatar-transparent-150.png',
              'media/sost-sigma-emblem.png', 'media/sost-sigma-emblem-512.png', 'media/sost-sigma-emblem-flat.png',
              'media/sost-sigma-emblem-flat-512.png', 'media/sost-sigma-emblem-black.png', 'media/sost-sigma-emblem-black-512.png',
              'universe/assets/brand/sost-eye.ico', 'universe/assets/brand/sost-eye-loader-640.webp', 'assets/coins/sost.png'] + \
             [f'universe/assets/brand/sost-eye-{px}.png' for px in (16, 32, 48, 64, 96, 128, 180, 192, 256, 512, 1024)]
for rel in SOST_FILES:
    web_replace(rel, lambda px: rs(s, px))
for rel, frac in [('apple-touch-icon.png', 0.94), ('android-chrome-maskable-192x192.png', 0.80), ('android-chrome-maskable-512x512.png', 0.80),
                  ('sost-app/icon-maskable-192.png', 0.80), ('sost-app/icon-maskable-512.png', 0.80)] + \
                 [(f'sost-avatar-{v}.png', 0.96) for v in ('80', '80-tight', '100', '100-tight', '120', '150', '150-tight')]:
    web_replace(rel, lambda px, f=frac: inset(s, px, f))
# favicon.svg: same wrapper (256 viewBox, embedded 96 px PNG), new pixels
p = os.path.join(WEB, 'favicon.svg')
if os.path.exists(p):
    import base64, re
    b = io.BytesIO(); rs(s, 96).save(b, 'PNG', optimize=True)
    t = open(p).read()
    t2 = re.sub(r'data:image/png;base64,[A-Za-z0-9+/=]+', 'data:image/png;base64,' + base64.b64encode(b.getvalue()).decode(), t, count=1)
    assert "data:image/png;base64," in t
    open(p, 'w').write(t2); REPORT['outputs'].append(dict(path=p, sha256=sha(p)))
# Open Graph 1200x630: same layout, old emblem disc replaced by the new emblem at the same centre and diameter
p = os.path.join(WEB, 'og-sost-logo.png')
if os.path.exists(p):
    og = Image.open(p).convert('RGB'); a = np.asarray(og).astype(int)
    LIM = 575                                                          # the title / spectrum rule start at x=584: never touch them
    left = a[:, :LIM]; ys, xs = np.nonzero((left[..., 0] > 60) & (left[..., 0] > left[..., 1] * 1.6))
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max(); cx, cy = (x0 + x1) / 2, (y0 + y1) / 2; d = max(x1 - x0, y1 - y0) + 1
    pad = 14; box = (int(cx - d / 2 - pad), int(cy - d / 2 - pad), int(cx + d / 2 + pad), int(cy + d / 2 + pad))
    box = (0, 0, LIM, og.height)                                       # whole left panel: removes the old emblem's red glow too
    bg = a.copy(); bg[(bg[..., 0] <= 30) & (bg[..., 1] <= 2) & (bg[..., 2] <= 2)] = 0   # old emblem's faint red glow on the black field
    og2 = Image.fromarray(bg.astype(np.uint8), 'RGB').convert('RGBA'); og2.paste((0, 0, 0, 255), box)
    e = rs(s, int(d)); og2.alpha_composite(e, (int(round(cx - d / 2)), int(round(cy - d / 2))))
    save(og2.convert('RGB'), p)
    REPORT['og'] = dict(old_disc_bbox=[int(x0), int(y0), int(x1), int(y1)], new_diameter=int(d))
    shutil.copyfile(p, f'{OUT}/sost/social/og-sost-1200x630.png') if os.path.isdir(f'{OUT}/sost/social') else None

# Explorer loader pulse layers, cut from the NEW emblem's own Sigma glyph (same technique as before)
LS = 640
base = rs(s, LS); A = np.asarray(base).astype(np.float64)
lum = A[..., :3].mean(-1) * (A[..., 3] / 255)
yy, xx = np.mgrid[0:LS, 0:LS]; central = np.hypot(xx - LS / 2, yy - LS / 2) < LS * 0.22
R_, G_, B_ = A[..., 0], A[..., 1], A[..., 2]
box_c = (np.abs(xx - LS / 2) < LS * 0.21) & (np.abs(yy - LS / 2) < LS * 0.21)
warm_white = (R_ > 235) & (G_ > 200) & (B_ > 150)                                    # rainbow-disc edition: white-hot Sigma
import matplotlib.colors as _mc
_h = _mc.rgb_to_hsv(np.clip(A[..., :3] / 255, 0, 1)); _hue, _sat, _val = _h[..., 0] * 360, _h[..., 1], _h[..., 2]
gold = (R_ > 140) & (_val > 0.5) & (((_hue >= 28) & (_hue <= 56)) | (_sat < 0.35))   # gold body + its near-white highlights
if os.path.basename(SRC['sost']).startswith('Sigma dorada'):
    from scipy import ndimage as _nd
    _g = _nd.binary_closing(box_c & (A[..., 3] > 200) & gold, structure=np.ones((9, 9)))
    _lab, _n = _nd.label(_g)
    gold = _lab == (1 + int(np.argmax(_nd.sum(_g, _lab, range(1, _n + 1)))))       # largest connected region = the Sigma
    _hl, _hn = _nd.label(_nd.binary_fill_holes(gold) & ~gold)                       # fill only small holes (specular highlights)
    if _hn: gold |= np.isin(_hl, 1 + np.nonzero(_nd.sum(np.ones_like(_hl), _hl, range(1, _hn + 1)) < 400)[0])
glyph = box_c & (A[..., 3] > 200) & (gold if os.path.basename(SRC['sost']).startswith('Sigma dorada') else warm_white)
gy, gx = np.nonzero(glyph)
g0x, g1x, g0y, g1y = gx.min(), gx.max(), gy.min(), gy.max()
m = 12; sx0, sy0 = g0x - m, g0y - m; sw = max(g1x - g0x, g1y - g0y) + 2 * m + 1
sig_mask = Image.fromarray((glyph * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
sig = Image.new('RGBA', (LS, LS), (255, 209, 163, 0)); sig.putalpha(sig_mask)
sig = sig.crop((sx0, sy0, sx0 + sw, sy0 + sw))
hw = int(round(sw * 37.11 / 25.39)); hx0 = int(round(sx0 + sw / 2 - hw / 2)); hy0 = int(round(sy0 + sw / 2 - hw / 2))
halo_mask = Image.fromarray((glyph * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(9))
halo = Image.new('RGBA', (LS, LS), (255, 190, 128, 0)); halo.putalpha(halo_mask.point(lambda v: min(255, int(v * 1.6))))
halo = halo.crop((hx0, hy0, hx0 + hw, hy0 + hw))
if os.path.exists(os.path.join(WEB, 'universe/assets/brand/sost-eye-loader-sigma.png')):
    save(sig.resize((260, 260), Image.LANCZOS), os.path.join(WEB, 'universe/assets/brand/sost-eye-loader-sigma.png'))
    save(halo.resize((380, 380), Image.LANCZOS), os.path.join(WEB, 'universe/assets/brand/sost-eye-loader-halo.png'))
pc = lambda v: round(100 * v / LS, 2)
REPORT['loader_css'] = dict(sig=dict(left=pc(sx0), top=pc(sy0), size=pc(sw)), halo=dict(left=pc(hx0), top=pc(hy0), size=pc(hw)))

# ---------- wSOST ----------
w = M['wsost']
W_FILES = ['universe/assets/brand/wsost/wsost-eye.ico', 'media/wsost-logo.png', 'media/wsost-logo-512.png'] + \
          [f'universe/assets/brand/wsost/wsost-eye-{px}.png' for px in (16, 32, 48, 64, 96, 128, 180, 192, 256, 512, 1024)] + \
          [f'universe/assets/brand/wsost/wsost-eye-small-{px}.png' for px in (16, 32, 48, 64)] + \
          [f'assets/wsost/wsost-gold-vault{v}-{px}.{e}' for v in ('', '-nav') for px in (128, 256, 512, 1024) for e in ('png', 'webp')]
for rel in W_FILES:
    web_replace(rel, lambda px: rs(w, px))

json.dump(REPORT, open(f'{OUT}/build_rainbow_report.json', 'w'), indent=1)
print(json.dumps({k: REPORT[k] for k in ('sources', 'loader_css')}, indent=1), REPORT.get('og'), len(REPORT['outputs']), 'files')

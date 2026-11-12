#!/usr/bin/env python3
"""Video posters: replace only the old red-Sigma squircle icon by the official Gold Sigma / Rainbow Edition logo.
usage: poster_gold.py IN.jpg OUT.jpg LOGO_TRANSPARENT.png   (the videos themselves are not touched)"""
import sys, json
import numpy as np, cv2
from PIL import Image
src, dst, logo = sys.argv[1:4]
im = np.array(Image.open(src).convert('RGB')); H, W = im.shape[:2]
lum = im.astype(int).sum(-1)
dark = ((lum < 12) * 255).astype(np.uint8)
n, lab, st, cen = cv2.connectedComponentsWithStats(dark, 8)
# the squircle: the largest near-black component in the upper-middle band whose bbox is roughly square
best = None
for i in range(1, n):
    x, y, w, h, a = st[i]
    if a < 3000 or not (0.75 < w / h < 1.33) or abs((x + w / 2) - W / 2) > W * 0.15 or y > H * 0.6: continue
    if best is None or a > st[best][4]: best = i
x, y, w, h, a = st[best]
mask = np.zeros((H, W), np.uint8); mask[y - 2:y + h + 2, x - 2:x + w + 2] = (lab[y - 2:y + h + 2, x - 2:x + w + 2] == best) * 255
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE); cv2.drawContours(mask, cnts, -1, 255, -1)   # include the red glyph
red = (im[..., 0] > 70) & (im[..., 0] > im[..., 1] * 2) & (im[..., 0] > im[..., 2] * 1.6)
near = cv2.dilate(mask, np.ones((61, 61), np.uint8)) > 0
mask2 = cv2.dilate(mask, np.ones((27, 27), np.uint8)) | ((red & near) * 255).astype(np.uint8)       # squircle + its red rim glow
m = (mask2 > 0).astype(np.float32); keep = (1 - m) * (lum < 110)                                  # smooth fill: normalized convolution of the surroundings
num = cv2.GaussianBlur(im.astype(np.float32) * keep[..., None], (0, 0), 45); den = cv2.GaussianBlur(keep, (0, 0), 45)[..., None]
fill = num / np.maximum(den, 1e-4); feather = cv2.GaussianBlur(m, (0, 0), 3)[..., None]
out = np.clip(im * (1 - feather) + fill * feather, 0, 255).astype(np.uint8)
L = Image.open(logo).convert('RGBA'); s = int(round(max(w, h) * 1.30))
L = L.convert('RGBa').resize((s, s), Image.LANCZOS).convert('RGBA')
o = Image.fromarray(out).convert('RGBA'); cx, cy = x + w / 2, y + h / 2
o.alpha_composite(L, (int(round(cx - s / 2)), int(round(cy - s / 2))))
o.convert('RGB').save(dst, 'JPEG', quality=90, optimize=True, progressive=True)
print(json.dumps(dict(file=src, squircle=[int(x), int(y), int(w), int(h)], logo_px=s)))

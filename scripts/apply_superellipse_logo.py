#!/usr/bin/env python3
"""Give the SOST mark the same curved silhouette GeaSpirit uses.

The shape is a SUPERELLIPSE — a squircle — not a rounded rectangle, and the difference is
visible side by side: a rounded rectangle has straight edges with an arc pasted into each
corner, and the join is where the eye catches it. A superellipse has continuous curvature all
the way round.

It is baked into the PNG's alpha channel rather than applied with CSS border-radius, for the
same reason it is on the GeaSpirit side: `border-radius: 20%` was on the logo inline in the
markup, so the shape lived in whichever stylesheet happened to reach the element, differed
between the site and the explorer, and disappeared entirely anywhere the image was used outside
a browser — an OG card, a PDF, an exchange listing form. A shape that belongs to the mark
belongs in the file.

The mask is taken from the GeaSpirit logo itself rather than re-derived from an exponent, so the
two silhouettes are identical by construction and cannot drift apart later.
"""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "website")
REFERENCE = "/home/sost/SOST/geaspirit-platform/public/assets/img/geaspirit-logo.png"

# Every square asset that IS the SOST mark. og-sost-logo.png is a 1200x630 social banner, not
# the mark, and convergencex-logo.png is a different brand — neither is touched.
TARGETS = [
    "sost-logo.png",
    "apple-touch-icon.png",
    "android-chrome-192x192.png", "android-chrome-512x512.png",
    "favicon-48x48.png", "favicon-96x96.png", "favicon-144x144.png",
    "sost-avatar-80.png", "sost-avatar-100.png", "sost-avatar-120.png", "sost-avatar-150.png",
    "sost-avatar-80-tight.png", "sost-avatar-100-tight.png", "sost-avatar-150-tight.png",
]


def mask_for(size):
    """The reference silhouette, resampled to the target size.

    LANCZOS on the alpha alone keeps the curve smooth at 48 px, where a nearest-neighbour
    resample would give the corners a visible staircase.
    """
    ref = Image.open(REFERENCE).convert("RGBA")
    return ref.split()[3].resize((size, size), Image.LANCZOS)


def main():
    if not os.path.exists(REFERENCE):
        print(f"FAIL: reference silhouette not found at {REFERENCE}", file=sys.stderr)
        return 2
    changed = []
    for name in TARGETS:
        path = os.path.join(WEB, name)
        if not os.path.exists(path):
            print(f"  skip (absent): {name}")
            continue
        im = Image.open(path).convert("RGBA")
        w, h = im.size
        if w != h:
            print(f"  skip (not square, {w}x{h}): {name}")
            continue
        m = mask_for(w)
        # Multiply into whatever alpha the file already has, so an asset that is already
        # partly transparent keeps its own transparency as well as gaining the silhouette.
        existing = im.split()[3]
        combined = Image.eval(Image.merge("L", [existing]), lambda v: v)
        px_e, px_m = existing.load(), m.load()
        out = Image.new("L", (w, h))
        px_o = out.load()
        for y in range(h):
            for x in range(w):
                px_o[x, y] = (px_e[x, y] * px_m[x, y]) // 255
        im.putalpha(out)
        im.save(path, "PNG", optimize=True)
        opaque = sum(1 for p in out.getdata() if p > 200) / float(w * h)
        changed.append(f"{name} ({w}x{h}, {100 * opaque:.1f}% opaque)")
    print(f"silhouette applied to {len(changed)} asset(s):")
    for c in changed:
        print(f"  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

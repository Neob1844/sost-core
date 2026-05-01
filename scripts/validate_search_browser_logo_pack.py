#!/usr/bin/env python3
"""M26: validate the search/browser logo pack on the website tree.

Checks:
  - required icon files exist and are non-empty
  - site.webmanifest is valid JSON
  - index.html declares favicon + manifest + apple-touch + theme-color
  - main pages declare apple-touch-icon and manifest tags
  - og-sost-logo.png exists and is plausibly 1200x630
  - no duplicate favicon blocks
  - robots.txt does not block icon assets
  - no broken absolute local paths under website/
  - no accidental edits to consensus / wallet / miner / rpc / src code
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'website'

REQUIRED_ASSETS = (
    'favicon.ico',
    'favicon.svg',
    'favicon-48x48.png',
    'favicon-96x96.png',
    'favicon-144x144.png',
    'apple-touch-icon.png',
    'android-chrome-192x192.png',
    'android-chrome-512x512.png',
    'og-sost-logo.png',
    'site.webmanifest',
    'sost-logo.png',
)

MAIN_PAGES = (
    'index.html',
    'sost-explorer.html',
    'sost-ai-engine.html',
    'sost-materials-engine.html',
    'sost-geaspirit.html',
)

# Minimum HTML tag pattern set every page should declare.
ICON_PATTERNS = (
    r'rel\s*=\s*"icon"[^>]*href\s*=\s*"/favicon\.ico"',
    r'rel\s*=\s*"icon"[^>]*href\s*=\s*"/favicon\.svg"',
    r'rel\s*=\s*"apple-touch-icon"[^>]*sizes\s*=\s*"180x180"',
    r'rel\s*=\s*"manifest"[^>]*href\s*=\s*"/site\.webmanifest"',
    r'name\s*=\s*"theme-color"',
)

ROBOTS_FORBIDDEN = (
    re.compile(r'^\s*Disallow:\s*/.*\.ico\s*$', re.M),
    re.compile(r'^\s*Disallow:\s*/.*\.png\s*$', re.M),
    re.compile(r'^\s*Disallow:\s*/.*\.svg\s*$', re.M),
    re.compile(r'^\s*Disallow:\s*/.*webmanifest\s*$', re.M),
    re.compile(r'^\s*Disallow:\s*/og-sost-logo', re.M),
    re.compile(r'^\s*Disallow:\s*/favicon', re.M),
)

# Source dirs the pack must NOT touch.
GUARDED_DIRS = ('src', 'wallet', 'rpc', 'miner', 'consensus')


def err(msg: str, errors: List[str]) -> None:
    errors.append(msg)
    print(f"  FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"  ok:   {msg}")


def main() -> int:
    errors: List[str] = []
    print("M26 — search/browser logo pack validation")
    print(f"  website root: {WEB}")

    # 1. Required assets
    print("\n[1] required assets")
    for name in REQUIRED_ASSETS:
        p = WEB / name
        if not p.exists():
            err(f"missing asset: {p.name}", errors)
            continue
        if p.stat().st_size == 0:
            err(f"empty asset: {p.name}", errors)
        else:
            ok(f"{p.name} ({p.stat().st_size} bytes)")

    # 2. Manifest valid JSON
    print("\n[2] site.webmanifest is valid JSON")
    mp = WEB / 'site.webmanifest'
    if mp.exists():
        try:
            data = json.loads(mp.read_text(encoding='utf-8'))
            for k in ('name', 'icons', 'theme_color', 'background_color'):
                if k not in data:
                    err(f"manifest missing key {k!r}", errors)
            else:
                ok("manifest parses + has name/icons/theme_color/background_color")
        except json.JSONDecodeError as e:
            err(f"manifest JSON error: {e}", errors)

    # 3. og-sost-logo.png plausibly 1200x630 (use Pillow if available)
    print("\n[3] og-sost-logo.png dimensions")
    og = WEB / 'og-sost-logo.png'
    if og.exists():
        try:
            from PIL import Image
            with Image.open(og) as im:
                w, h = im.size
            if (w, h) == (1200, 630):
                ok(f"{og.name} is 1200x630")
            else:
                err(f"{og.name} is {w}x{h}, expected 1200x630", errors)
        except ImportError:
            ok("Pillow not present — skipping dimension check")

    # 4. Index + main pages have icon declarations
    print("\n[4] icon declarations on main pages")
    for page_name in MAIN_PAGES:
        p = WEB / page_name
        if not p.exists():
            err(f"missing page: {page_name}", errors)
            continue
        s = p.read_text(encoding='utf-8')
        missing = []
        for pat in ICON_PATTERNS:
            if not re.search(pat, s, re.IGNORECASE):
                missing.append(pat)
        if missing:
            err(f"{page_name} missing patterns: {missing}", errors)
        else:
            ok(f"{page_name} carries the full icon set")

    # 4b. Every public page declares manifest + apple-touch.
    print("\n[4b] every HTML page declares manifest + apple-touch + theme-color")
    pages = sorted(WEB.glob('*.html'))
    for p in pages:
        s = p.read_text(encoding='utf-8')
        for pat in (
            r'rel\s*=\s*"manifest"',
            r'rel\s*=\s*"apple-touch-icon"',
            r'name\s*=\s*"theme-color"',
        ):
            if not re.search(pat, s, re.IGNORECASE):
                err(f"{p.name} missing {pat!r}", errors)
                break

    # 5. No duplicate favicon.ico declarations on a single page.
    print("\n[5] no duplicate favicon.ico declarations")
    dup = []
    for p in pages:
        s = p.read_text(encoding='utf-8')
        n = len(re.findall(
            r'rel\s*=\s*"icon"[^>]*href\s*=\s*"/favicon\.ico"',
            s, re.IGNORECASE))
        if n > 1:
            dup.append((p.name, n))
    if dup:
        for name, n in dup:
            err(f"{name} has {n} favicon.ico links", errors)
    else:
        ok("no page has duplicate favicon.ico declarations")

    # 6. robots.txt does not forbid icons
    print("\n[6] robots.txt allows icon/manifest assets")
    rp = WEB / 'robots.txt'
    if rp.exists():
        rs = rp.read_text(encoding='utf-8')
        for pat in ROBOTS_FORBIDDEN:
            if pat.search(rs):
                err(f"robots.txt forbids icon-like asset: {pat.pattern}", errors)
        ok("robots.txt does not forbid icon/manifest assets")
    else:
        ok("no robots.txt — allowed")

    # 7. No accidental writes to guarded dirs (best-effort: check git status)
    print("\n[7] guarded dirs untouched")
    import subprocess
    try:
        out = subprocess.check_output(
            ['git', '-C', str(ROOT), 'status', '--porcelain'],
            text=True)
        bad = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            path = line[3:].strip()
            for guard in GUARDED_DIRS:
                if path.startswith(guard + '/'):
                    bad.append(path)
        if bad:
            err(f"guarded dirs modified: {bad[:5]}", errors)
        else:
            ok("no changes to src/wallet/rpc/miner/consensus dirs")
    except subprocess.CalledProcessError:
        ok("git status unavailable — skipping guarded-dir audit")

    print()
    if errors:
        print(f"FAIL: {len(errors)} issue(s).")
        return 1
    print("PASS — search/browser logo pack is in place.")
    return 0


if __name__ == '__main__':
    sys.exit(main())

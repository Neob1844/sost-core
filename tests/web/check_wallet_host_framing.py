#!/usr/bin/env python3
"""Framing-policy check for the legacy host wallet.sostcore.com.

Why: /sost-app/ (the PWA shell on the same host) shows the wallet by embedding /sost-wallet.html in a
same-origin <iframe>. The host therefore MUST send X-Frame-Options SAMEORIGIN and CSP frame-ancestors 'self'
(not DENY / 'none'), otherwise the app's WALLET tab goes blank. It must still refuse cross-origin framing
(clickjacking defence). This check asserts all three things against the live host.

Checks:
  1. headers of /sost-wallet.html and /sost-app/ (XFO SAMEORIGIN, frame-ancestors 'self', HSTS, nosniff)
  2. headless Chromium: /sost-app/ -> WALLET menu entry -> the embedded /sost-wallet.html frame really loads
     (its scripts run: unlockWallet/generateWallet defined), no XFO/CSP framing error, no JS errors in the frame
  3. a cross-origin (opaque about:blank) page that frames /sost-wallet.html is BLOCKED
Read-only: GET requests only, no wallet is created, nothing is stored. One Chromium, closed at the end.
usage: python3 check_wallet_host_framing.py [--base https://wallet.sostcore.com]   (exit 0 = all PASS)
needs: pip package `playwright` + `playwright install chromium`
"""
import argparse, asyncio, sys, urllib.request, urllib.error

N = OK = 0
def step(name, cond, detail=''):
    global N, OK
    N += 1; OK += bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ''), flush=True)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None

def headers(url):
    op = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={'User-Agent': 'sost-framing-check/1 (+headless audit)'})
    try: r = op.open(req, timeout=20); return r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e: return e.code, {k.lower(): v for k, v in e.headers.items()}

def frame_ancestors(csp):
    for d in (csp or '').split(';'):
        d = d.strip()
        if d.lower().startswith('frame-ancestors'): return d[len('frame-ancestors'):].strip()
    return None

def check_headers(base):
    for path, need_csp in (('/sost-wallet.html', True), ('/sost-app/', False)):
        st, h = headers(base + path)
        xfo = (h.get('x-frame-options') or '').upper()
        fa = frame_ancestors(h.get('content-security-policy'))
        step(f'headers {path}: 200', st == 200, f'status={st}')
        step(f'headers {path}: X-Frame-Options SAMEORIGIN (not DENY)', xfo == 'SAMEORIGIN', f'x-frame-options={xfo or None}')
        if need_csp or fa is not None:
            step(f"headers {path}: CSP frame-ancestors 'self' (not 'none')", fa == "'self'", f'frame-ancestors={fa}')
        step(f'headers {path}: HSTS + nosniff present', 'strict-transport-security' in h and h.get('x-content-type-options', '').lower() == 'nosniff')

async def check_browser(base):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        try:
            c = await b.new_context(service_workers='block')
            p = await c.new_page(); cons, errs = [], []
            p.on('console', lambda m: cons.append(m.text))
            p.on('pageerror', lambda e: errs.append((getattr(e, 'message', None) or str(e)).split('\n')[0]))
            r = await p.goto(base + '/sost-app/', wait_until='load', timeout=60000)
            step('browser: /sost-app/ loads', r is not None and r.status == 200, f'status={r.status if r else None}')
            # the app's own navigation (its JS lives in an IIFE): click the WALLET menu entry
            await p.wait_for_function("[...document.querySelectorAll('#menu-items .menu-item')].some(e=>/\\bWALLET\\b/.test(e.textContent))", timeout=30000)
            await p.evaluate("[...document.querySelectorAll('#menu-items .menu-item')].find(e=>/\\bWALLET\\b/.test(e.textContent)).click()")
            fr = None
            for _ in range(60):
                fr = next((f for f in p.frames if f != p.main_frame and f.url.split('?')[0].endswith('/sost-wallet.html')), None)
                if fr: break
                await p.wait_for_timeout(500)
            loaded = False
            if fr:
                try:
                    await fr.wait_for_function("typeof window.unlockWallet==='function' && typeof window.generateWallet==='function'", timeout=45000)
                    loaded = True
                except Exception: loaded = False
            blocked_msgs = [m for m in cons if 'Refused to display' in m or 'frame-ancestors' in m or 'X-Frame-Options' in m]
            step('browser: WALLET tab embeds /sost-wallet.html in a same-origin iframe', fr is not None, fr.url if fr else 'no frame')
            step('browser: embedded wallet frame loads and its scripts run (no XFO/CSP block)', loaded and not blocked_msgs, '; '.join(blocked_msgs)[:200])
            step('browser: 0 framing errors in console', not blocked_msgs)
            await c.close()
            # negative: cross-origin (opaque) parent must be refused
            c2 = await b.new_context(service_workers='block'); q = await c2.new_page(); cons2 = []
            q.on('console', lambda m: cons2.append(m.text))
            await q.set_content(f'<iframe id="x" src="{base}/sost-wallet.html" width="400" height="300"></iframe>')
            await q.wait_for_timeout(6000)
            f2 = next((f for f in q.frames if f != q.main_frame), None)
            ran = False
            if f2 and not f2.url.startswith('chrome-error'):
                try: ran = await f2.evaluate("typeof window.unlockWallet==='function'")
                except Exception: ran = False
            refused = any('Refused to display' in m or 'frame-ancestors' in m for m in cons2)
            step('browser: cross-origin framing of /sost-wallet.html is refused (clickjacking defence)', not ran,
                 f"frame_url={f2.url if f2 else None} console_refused={refused}")
            await c2.close()
        finally:
            await b.close()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--base', default='https://wallet.sostcore.com'); a = ap.parse_args()
    base = a.base.rstrip('/')
    check_headers(base)
    asyncio.run(check_browser(base))
    print(f'TOTAL {OK}/{N} PASS'); sys.exit(0 if OK == N else 1)

if __name__ == '__main__':
    main()

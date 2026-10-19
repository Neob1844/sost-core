#!/usr/bin/env python3
"""C701 bridge page UI / accessibility checks + screenshots (desktop and 390 px).

usage: python3 tests/c701bridge/ui_check.py <website_dir> <screenshot_out_dir>
Serves the static site on 127.0.0.1:<free port>, never touches any remote service.
"""
import functools
import http.server
import json
import os
import socket
import sys
import threading

from playwright.sync_api import sync_playwright

SITE, OUT = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
os.makedirs(OUT, exist_ok=True)
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=SITE))
threading.Thread(target=httpd.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{port}/sost-wsost-gold-vault.html"

REMOVE_OVERLAYS = "document.querySelectorAll('#sjp-ov').forEach(function(e){e.remove();});"

with sync_playwright() as p:
    b = p.chromium.launch()
    external = []
    for name, vp in (("desktop", {"width": 1440, "height": 900}), ("mobile390", {"width": 390, "height": 844})):
        ctx = b.new_context(viewport=vp, device_scale_factor=1)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # block every non-local request: the demo must work offline and must not phone home
        page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(f"http://127.0.0.1:{port}") else (external.append(r.request.url), r.abort()))
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.evaluate(REMOVE_OVERLAYS)
        sw = page.evaluate("document.documentElement.scrollWidth")
        cw = page.evaluate("document.documentElement.clientWidth")
        check(f"{name}: no horizontal scroll", sw <= cw, f"scrollWidth={sw} clientWidth={cw}")
        check(f"{name}: no JS errors", not errors, "; ".join(errors[:2]))
        page.locator("#bridge").scroll_into_view_if_needed()
        page.evaluate(REMOVE_OVERLAYS)
        page.locator("#bridge").screenshot(path=os.path.join(OUT, f"bridge-dashboard-{name}.png"))
        if name == "desktop":
            txt = page.inner_text("#bridge")
            for t in ("SEND", "RECEIVE", "GOLD ACCESS KEY", "XAUT required", "GOLD RESERVE V2", "ETHEREUM GAS", "CONNECT WALLETS", "PREPARE CONVERSION", "DEMO MODE"):
                check(f"dashboard shows '{t}'", t in txt)
            states = page.eval_on_selector_all("#cbSteps li", "els => els.map(e => e.textContent.trim())")
            check("10 visible states", len(states) == 10, ", ".join(states))
            rows = page.eval_on_selector_all("#gold-access-key ~ .tw table tr", "els => els.length")
            check("fee table has 20 data rows", rows - 1 == 20 if rows else False, f"rows={rows}")
            # simulator matches the contract table
            for v, want in (("1000", "0.000270"), ("100", "0.000135"), ("1000000", "0.013466"), ("7500", "0.002020")):
                page.fill("#cbSimV", v)
                check(f"simulator {v} EUR -> {want} XAUT", page.inner_text("#cbFeeX") == want)
            page.fill("#cbSimV", "99.99")
            check("simulator rejects 99.99 EUR", "REJECTED" in page.inner_text("#cbFeeS"))
            page.fill("#cbSend", "2500")
            check("receive mirrors send 1:1", page.inner_text("#cbRecv") == "2,500")
            page.click("#cbConnect")
            check("connect wallets is disabled in demo", "disabled" in page.inner_text("#cbLog"))
            page.click("#cbPrepare")
            page.wait_for_timeout(9800)
            check("demo walkthrough reaches Completed", page.get_attribute("#cbSteps li[data-s=COMPLETED]", "aria-current") == "step")
            check("completed message says no transaction exists", "NO TRANSACTION EXISTS" in page.inner_text("#cbLog"))
            page.locator("#bridge").screenshot(path=os.path.join(OUT, "bridge-dashboard-desktop-completed.png"))
            page.click(".cb-chip[data-path=security]")
            page.wait_for_timeout(7600)
            check("security error path shown", page.get_attribute("#cbSteps li[data-s=SECURITY_ERROR]", "aria-current") == "step")
            page.locator("#bridge").screenshot(path=os.path.join(OUT, "bridge-dashboard-desktop-security-error.png"))
            # accessibility basics
            unlabeled = page.evaluate("""() => [...document.querySelectorAll('#bridge input')].filter(i => !(i.labels&&i.labels.length) && !i.getAttribute('aria-labelledby') && !i.getAttribute('aria-label')).length""")
            check("all dashboard inputs have labels", unlabeled == 0)
            check("status log is aria-live", page.get_attribute("#cbLog", "aria-live") == "polite")
            check("buttons are real <button>s", page.evaluate("[...document.querySelectorAll('#bridge .cb-btn, #bridge .cb-chip')].every(e=>e.tagName==='BUTTON')"))
            page.keyboard.press("Tab")
            # page-wide wording checks
            body = page.inner_text("body").lower()
            claims = page.evaluate("""() => { const c=document.body.cloneNode(true);
                [...c.querySelectorAll('.card')].filter(e=>/NEVER SAID/.test(e.textContent)).forEach(e=>e.remove());
                return (c.innerText||c.textContent).toLowerCase(); }""")
            check("no gold-backed / peg / redemption claim outside the NEVER SAID list",
                  not any(w in claims for w in ("gold-backed sost", "backed by gold", "redeemable for gold")))
            check("public text present (EN + ES)", "does not guarantee the price of sost" in body and "ni garantiza el precio de sost" in body)
            check("desk / observers only as historical", page.inner_text("#superseded").count("HISTORICAL") >= 1 and page.locator("#desk").count() == 0)
            page.screenshot(path=os.path.join(OUT, "page-desktop-full.png"), full_page=True)
        else:
            page.screenshot(path=os.path.join(OUT, "page-mobile390-full.png"), full_page=True)
            # every bridge element fits
            over = page.evaluate("""() => [...document.querySelectorAll('#bridge *')].filter(e => { const r=e.getBoundingClientRect(); return r.right > document.documentElement.clientWidth + 1 && getComputedStyle(e).position!=='fixed' && !e.closest('.tw'); }).length""")
            check("mobile390: no bridge element overflows", over == 0, f"overflowing={over}")
        ctx.close()
    check("no external requests attempted by the bridge demo", not [u for u in external if "rpc" in u or "infura" in u or "etherscan" in u], json.dumps(external[:5]))
    b.close()
httpd.shutdown()
ok = sum(1 for _, c in results if c)
print(f"\nUI checks: {ok}/{len(results)} passed")
sys.exit(0 if ok == len(results) else 1)

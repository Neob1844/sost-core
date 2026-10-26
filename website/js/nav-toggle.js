/* SOST shared top-nav toggle.
   Auto-injects a pulsing red/gold "HIDE NAV / SHOW NAV" button into
   every page that has a <nav> element, and wires up a sessionStorage-
   backed collapsed state shared across pages.
   Compatible with the existing index.html implementation: when a button
   with id="navToggleBtn" already exists, the script only attaches its
   visual styling and lets the in-page handler do the toggling. */
/* Nav first paint (C706). The script loads synchronously in <head>, so every block
   below that builds the nav registers through __sostNavReady and runs the moment the
   parser has closed </nav> — before the next paint — instead of after the whole page
   (the Explorer is ~900 KB of HTML, so DOMContentLoaded came seconds after the raw
   nav was already on screen and then got replaced). The nav stays invisible only for
   those few milliseconds; DOMContentLoaded is the fallback if anything goes wrong. */
(function () {
  "use strict";
  var q = [], done = false, mo = null, de = document.documentElement;
  function navClosed() {
    var nav = document.querySelector("nav");
    if (!nav) return false;
    for (var e = nav; e && e !== document.body && e !== de; e = e.parentNode) {
      if (e.nextSibling) return true;
    }
    return false;
  }
  function run(fn) { try { fn(); } catch (e) { if (window.console) console.error(e); } }
  function flush() {
    if (done) return;
    done = true;
    if (mo) { mo.disconnect(); mo = null; }
    for (var i = 0; i < q.length; i++) run(q[i]);
    q.length = 0;
    de.classList.remove("sost-nav-pending");
  }
  // Every logo module of the canonical bar is 110 px (the SOST mark's size). Modules are now
  // built while the page is still parsing, when a measured sibling can come out smaller
  // because not every stylesheet has been applied yet; so the canonical bar uses the
  // constant and only other navs fall back to measuring.
  window.__sostModSize = function (nav, measured) {
    if (nav && nav.classList.contains("sost-canon-nav")) return 110;
    return measured || 110;
  };
  window.__sostNavReady = function (fn) {
    if (done) { run(fn); return; }
    q.push(fn);
    if (document.readyState !== "loading" || navClosed()) flush();
  };
  if (document.readyState === "loading") {
    de.classList.add("sost-nav-pending");
    var st = document.createElement("style");
    st.id = "sost-nav-pending-style";
    st.textContent = "html.sost-nav-pending nav{visibility:hidden!important}";
    (document.head || de).appendChild(st);
    try {
      mo = new MutationObserver(function () { if (navClosed()) flush(); });
      mo.observe(de, { childList: true, subtree: true });
    } catch (e) { /* DOMContentLoaded below still runs everything */ }
    document.addEventListener("DOMContentLoaded", flush, { once: true });
  }
})();

(function () {
  "use strict";

  // Pre-paint flicker fix: if the previous page collapsed the nav,
  // toggle the html-level marker before the first paint so the nav
  // renders collapsed from frame 0.
  try {
    if (sessionStorage.getItem("sost_nav_collapsed") === "1") {
      document.documentElement.classList.add("pre-nav-collapsed");
    }
  } catch (e) { /* ignore */ }

  // Inject the shared CSS exactly once.
  if (!document.getElementById("sost-nav-toggle-style")) {
    var style = document.createElement("style");
    style.id = "sost-nav-toggle-style";
    style.textContent = [
      ".sost-nav-toggle, .nav-toggle {",
      "  position: relative;",
      "  background: linear-gradient(135deg, rgba(251,1,13,0.22), rgba(245,158,11,0.14) 65%, rgba(34,211,238,0.10));",
      "  border: 1px solid rgba(251,1,13,0.65);",
      "  color: #fff5f5;",
      "  font-family: 'JetBrains Mono', ui-monospace, monospace;",
      "  font-size: 11px;",
      "  font-weight: 700;",
      "  letter-spacing: 1.6px;",
      "  padding: 7px 14px;",
      // 12px, not 6. One shape scale for the whole site: 20% on the large square
      // modules, 12px on medium controls like this one and Watch, 10px on chips.
      // The glow below is untouched — the pulse is the brand, not a rough edge.
      "  border-radius: 12px;",
      "  cursor: pointer;",
      "  flex: 0 0 auto;",
      "  transition: transform .18s ease, color .18s ease, border-color .2s ease;",
      "  box-shadow: 0 0 8px rgba(251,1,13,0.42), 0 0 18px rgba(245,158,11,0.22);",
      "  text-shadow: 0 0 6px rgba(251,1,13,0.55);",
      "  animation: sostNavPulse 3.1s ease-in-out infinite;",
      "  -webkit-tap-highlight-color: transparent;",
      "}",
      // Watch is the one nav link that HAS a box, and it inherited .nav-links a at 4px —
      // nearly square beside the 12px Hide Nav it sits next to. Given its own rule rather
      // than rounding all twenty text links, which would be the bubble UI the owner ruled
      // out. The first attempt put this in the video-modal stylesheet, which returns early
      // on any page that ships its own modal — so it never reached the home page at all.
      /* Page furniture must not sit over the Watch player. Fifty-four pages ship their own
         #sv-modal and their own openSv, so this cannot live inside the shared modal's builder —
         it goes in the stylesheet every page gets. Hidden only while Watch is open; the banner
         is never removed from the site. */
      "body.sv-open #v15banner, body.sv-open .v15banner, body.sv-open nav,",
      "body.sv-open .developer-note, body.sv-open #developer-note {",
      "  visibility: hidden !important;",
      "}",
      "body.sv-open { overflow: hidden; }",
      "nav .nav-links a[data-watch] {",
      "  border-radius: 12px;",
      "  padding: 5px 12px;",
      "}",
      ".sost-nav-toggle:hover, .nav-toggle:hover {",
      "  color: #ffffff;",
      "  border-color: rgba(255,200,87,0.95);",
      "  transform: translateY(-1px);",
      "}",
      ".sost-nav-toggle:focus-visible, .nav-toggle:focus-visible {",
      "  outline: none;",
      "  border-color: rgba(34,211,238,0.95);",
      "  box-shadow: 0 0 14px rgba(34,211,238,0.7), 0 0 28px rgba(34,211,238,0.35);",
      "}",
      "@keyframes sostNavPulse {",
      "  0%, 100% {",
      "    box-shadow: 0 0 8px rgba(251,1,13,0.42),",
      "                0 0 18px rgba(245,158,11,0.22);",
      "  }",
      "  50% {",
      "    box-shadow: 0 0 16px rgba(251,1,13,0.85),",
      "                0 0 30px rgba(245,158,11,0.5),",
      "                0 0 48px rgba(251,1,13,0.28);",
      "  }",
      "}",
      "body.nav-collapsed nav { padding: 4px 0 !important; min-height: 0 !important; height: auto !important; }",
      "body.nav-collapsed nav .nav-logo,",
      "body.nav-collapsed nav .nav-links,",
      "body.nav-collapsed nav #vcx-sost,",
      "body.nav-collapsed nav a[href=\"casert-spec.html\"],",
      "body.nav-collapsed nav a[href=\"sost-dex.html\"],",
      "body.nav-collapsed nav a[href=\"sost-popc.html\"],",
      "body.nav-collapsed nav a[href=\"atomic-swap-console.html\"],",
      "body.nav-collapsed nav a[onclick=\"openSv()\"] {",
      "  display: none !important;",
      "}",
      "body.nav-collapsed nav .container {",
      "  justify-content: flex-end !important;",
      "}",
      /* Keep the hamburger ALWAYS visible while collapsed so the user ALWAYS has
         a visible control to reopen the menu (in addition to the SHOW NAV button),
         and let clicking it actually reveal the links despite the collapse rule
         above (otherwise the !important display:none would keep them hidden). */
      "body.nav-collapsed nav .nav-hamburger {",
      "  display: block !important;",
      "}",
      "body.nav-collapsed nav .nav-links.open {",
      "  display: flex !important;",
      "  width: 100% !important;",
      "}",
      /* Explorer-style nav: <nav><div style=...> with no .container class.
         Hide the entire flex layout so HIDE NAV reclaims the SOST logo,
         the EXPLORER label, and the right-side header-link group too.
         The toggle button itself is appended directly to <nav> as a
         sibling of this inner div, so it stays visible. Pages that use
         <nav><div class="container"> (homepage + 45 section pages)
         are unaffected because the :not(.container) qualifier excludes
         them — their button lives inside .container and is preserved. */
      "body.nav-collapsed nav > div:not(.container) {",
      "  display: none !important;",
      "}",
      "html.pre-nav-collapsed body.nav-collapsed nav { padding: 4px 0 !important; }",
      /* ---- Unified logo bar across all sections ----
         SOST logo + text stays left; ConvergenceX, PoPC DEX, Watch and News
         group together on the right (drop ConvergenceX's flex:1 grow and push
         the whole right group with margin-left:auto). */
      "nav .container > a[href=\"casert-spec.html\"] {",
      "  flex: 0 0 auto !important;",
      "  margin-left: auto !important;",
      "}",
      /* SOST nav text identical on every page (some pages used a
      "   smaller 18px override — force the standard size everywhere). */
      "nav .nav-logo { font-size: 26px !important; letter-spacing: 3px !important; gap: 14px !important; }",
      /* ---- Nav geometry = the Explorer's (canonical) ----
         The Explorer's own nav CSS (sost-explorer.html, #explorer-global-nav-css) is the
         reference. Section pages reused their page-wide .container (max-width 1100px), so the
         bar was narrower: HIDE NAV wrapped under the logo and the button block broke into more
         rows. Same container, padding, gap and logo/toggle metrics on every page.
         Scoped to the full bar (logo image present, class set in init below); the minimal
         text-only navs of a few help sub-pages keep their own layout. */
      "nav.sost-canon-nav { padding: 12px 0 !important; font-size: 13px; line-height: normal;",
      "  border-bottom-color: #1a1a1a !important; }",
      "nav.sost-canon-nav > .container { max-width: 1400px !important; margin: 0 auto !important; padding: 0 24px !important;",
      "  display: flex !important; align-items: center !important; justify-content: space-between !important;",
      "  gap: 16px !important; flex-wrap: wrap !important; box-sizing: border-box; }",
      "nav.sost-canon-nav .nav-logo { font-family: 'Space Grotesk', sans-serif !important; font-weight: 700 !important; line-height: normal !important; }",
      "nav.sost-canon-nav .nav-logo .brand-sost { font-size: 1.76em !important; }",
      "nav.sost-canon-nav .nav-logo img { width: 110px !important; height: 110px !important; }",
      "nav.sost-canon-nav .nav-toggle, nav.sost-canon-nav .sost-nav-toggle { font-family: monospace !important;",
      "  font-size: 11px !important; letter-spacing: 1px !important;",
      "  padding: 5px 10px !important; border-width: 1px !important; line-height: normal !important; }",
      /* Pinned box: the Explorer does not load the JetBrains Mono web font (it renders the
         system monospace) while section pages did, so a content-sized button came out 1px
         taller and a few px narrower or wider depending on the OS — enough to shift every
         module in the row. 98x25 is what the Explorer renders. */
      "nav.sost-canon-nav .nav-toggle, nav.sost-canon-nav .sost-nav-toggle { box-sizing: border-box !important; width: 98px !important; height: 25px !important;",
      "  padding: 0 !important; display: inline-flex !important; align-items: center !important; justify-content: center !important;",
      "  white-space: nowrap !important; overflow: hidden; }",
      /* Geometry that must not depend on page content, web fonts or the OS:
         - Logo block: the Explorer's ("SOST EXPLORER", Space Grotesk, loaded on every page)
           measures 407.0625px; every page reserves exactly that, so the modules and HIDE NAV
           start at the same x and the top row wraps at the same width.
         - Button and toggle text: the Explorer does not load JetBrains Mono / IBM Plex Mono,
           section pages do. Their buttons came out wider than the Explorer's on systems whose
           monospace is narrower (Windows: Consolas), so the row split differed. Both now use
           the Explorer's effective stack (no web font), so the rows are the same everywhere.
         - Scrollbar: section pages set a thin scrollbar, the Explorer did not, so the
           Explorer's bar was a few px narrower. Thin on every page that has this bar. */
      "@media (min-width: 769px) { nav.sost-canon-nav .nav-logo { flex: 0 0 407.0625px !important; width: 407.0625px !important; box-sizing: border-box; } }",
      "nav.sost-canon-nav .nav-links a.sx { font-family: ui-monospace, Menlo, Consolas, monospace !important; }",
      "html:has(nav.sost-canon-nav) { scrollbar-width: thin; }",
      /* Collapsed bar = the Explorer's: SHOW NAV alone at the right edge, no hamburger. */
      "body.nav-collapsed nav.sost-canon-nav .nav-hamburger { display: none !important; }",
      "nav.sost-canon-nav .nav-hamburger { font-size: 20px !important; padding: 4px 8px !important; line-height: 1 !important; border-width: 1px !important; }",
      /* The ONLY pulsing logo on the whole site: the SOST mark — min->max glow. */
      "nav .nav-logo img { animation: sostLogoPulse 4.7s ease-in-out infinite; }",
      "@keyframes sostLogoPulse {",
      "  0%, 100% { filter: drop-shadow(0 0 4px rgba(251,1,13,.45)) drop-shadow(0 0 10px rgba(251,1,13,.25)); }",
      "  50% { filter: drop-shadow(0 0 22px rgba(251,1,13,1)) drop-shadow(0 0 52px rgba(251,1,13,.92)) drop-shadow(0 0 88px rgba(251,1,13,.6)); }",
      "}",
      /* Watch: fixed glow at maximum, no pulse (matches the other logos). */
      "nav a[onclick=\"openSv()\"] {",
      "  box-shadow: 0 0 18px rgba(34,211,238,.95), 0 0 36px rgba(34,211,238,.6) !important;",
      "  animation: none !important;",
      "}",
    ].join("\n");
    (document.head || document.documentElement).appendChild(style);
  }

  function applyState(collapsed) {
    document.body.classList.toggle("nav-collapsed", collapsed);
    // MOBILE: HIDE NAV must also fold away the expanded hamburger menu. The
    // mobile menu is shown via `.nav-links.open` (display:flex !important),
    // which out-specifies the collapse rule and would otherwise keep the full
    // link list on screen. Dropping `.open` when collapsing lets the collapse
    // rule hide it; the hamburger stays visible to reopen it. No-op on desktop
    // (nav-links has no `.open` there).
    if (collapsed) {
      var _nl = document.querySelector("nav .nav-links");
      if (_nl) _nl.classList.remove("open");
    }
    var btns = document.querySelectorAll(".sost-nav-toggle, #navToggleBtn");
    btns.forEach(function (b) {
      b.textContent = collapsed ? "▼ SHOW NAV" : "▲ HIDE NAV";
      b.setAttribute("aria-pressed", collapsed ? "true" : "false");
    });
    try {
      sessionStorage.setItem("sost_nav_collapsed", collapsed ? "1" : "0");
    } catch (e) { /* ignore */ }
  }

  function toggleHandler(ev) {
    if (ev) ev.preventDefault();
    applyState(!document.body.classList.contains("nav-collapsed"));
  }

  // Expose a global so existing inline onclick="toggleNav()" handlers
  // (e.g. the one in index.html) keep working.
  window.toggleNav = function () { toggleHandler(); };

  function init() {
    var collapsed = false;
    try { collapsed = sessionStorage.getItem("sost_nav_collapsed") === "1"; }
    catch (e) { /* ignore */ }
    var nav = document.querySelector("nav");
    if (!nav) {
      // No nav on this page — still apply the state so a future inject
      // is consistent.
      if (collapsed) document.body.classList.add("nav-collapsed");
      return;
    }
    // Full canonical bar (main logo image) -> Explorer geometry (CSS above).
    if (nav.querySelector(".nav-logo img")) nav.classList.add("sost-canon-nav");
    var existing = nav.querySelector("#navToggleBtn, .sost-nav-toggle");
    if (!existing) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sost-nav-toggle";
      btn.id = "navToggleBtn";
      btn.title = "Hide / show the top navigation";
      btn.textContent = collapsed ? "▼ SHOW NAV" : "▲ HIDE NAV";
      btn.addEventListener("click", toggleHandler);
      // Insert just before the hamburger so it lands next to the nav
      // controls in the same flex row. Fall back to appending into the
      // .container if the structure differs.
      var hamburger = nav.querySelector(".nav-hamburger");
      var container = nav.querySelector(".container") || nav;
      if (hamburger && hamburger.parentNode === container) {
        container.insertBefore(btn, hamburger);
      } else {
        container.appendChild(btn);
      }
    } else if (!existing.dataset.sostBound) {
      // Existing index.html button: keep its inline onclick but make
      // sure we react to history-restored collapsed states too.
      existing.dataset.sostBound = "1";
    }
    applyState(collapsed);
  }

  window.__sostNavReady(init);
})();

/* ============================================================================
   SOST canonical shared nav-links — single source of truth.
   Replaces each page's <nav><div class="nav-links"> content with the canonical
   link list (incl. Beacon) so navs never drift and every section is reachable
   from every page. Active link is set from the current filename. Explorer uses
   a bespoke nav (no .nav-links) and is skipped. Edit THIS list to change the
   nav everywhere — no per-page HTML edits.
   ========================================================================== */
(function(){
  "use strict";
  var SOST_NAV_LINKS = `
            <a href="javascript:void(0)" data-watch="1" onclick="openSv()" title="Watch · SOST videos">▶ Watch</a>
            <a href="index.html">Home</a>
      <a href="sost-genesis.html">Genesis</a>
      <a href="sost-technology.html">Technology</a>
      <a href="sost-transactions.html">Transactions</a>
      <a href="sost-gold-reserve.html">Metals Reserve</a>
      <a href="sost-reference.html" style="color:#e3b23c">SOST Price Reference</a>
      <a href="sost-universal-assets.html" style="color:#DAA520">Tokenization &amp; Offers</a>
      <a href="sost-popc.html">PoPC</a>
      <a href="sost-tokenomics.html">Tokenomics</a>
      <a href="sost-roadmap.html">Roadmap</a>
      <a href="sost-protocol-spec.html">Protocol Spec</a>
      <a href="sost-whitepaper.html">Whitepaper</a>
      <a href="sost-mine.html" style="color:var(--red-primary)">Mine</a>
      <a href="sost-network-status.html">Network</a>
      <a href="sost-mining-calculator.html">Calculator</a>
      <a href="sost-why-no-pools.html">Why No Pools</a>
      <a href="sost-getting-started.html">Getting Started</a>
      <a href="sost-quickstart.html">Quick Start</a>
      <a href="sost-community.html">Community</a>
      <a href="sost-foundation.html">Governance</a>
      <a href="sost-foundation-balances.html">Governance Balances</a>
      <a href="sost-popc-contracts.html">PoPC Contracts</a>
      <a href="sost-popc-quickstart.html" style="color:var(--green-primary)">PoPC Quick Start</a>
      <a href="sost-e2e.html" style="color:var(--green-primary)">E2E Protocol</a>
      <!-- DEX link replaced by rainbow button next to logo -->
      <a href="sost-gold-dex.html">DEX Spec</a>
      <a href="sost-security.html">Security</a>
      <a href="sost-faq.html">FAQ</a>
      <a href="beacon.html" style="color:#22d3ee">Beacon</a>
      <a href="protocol-registry.html" style="color:#d946ef">Protocol Registry</a>
      <a href="casert-spec.html">cASERT</a>
      <a href="sost-explorer.html" style="color:#fbbf24">Explorer</a>
      <a href="sost-help.html">Help</a>
      <a href="sost-miner-troubleshooter.html">Troubleshooter</a>
      <a href="sost-markets.html">Markets <span style="display:inline-block;font-size:7px;color:#4ade80;background:rgba(74,222,128,0.1);border:1px solid rgba(74,222,128,0.25);border-radius:3px;padding:1px 4px;vertical-align:middle;margin-left:2px;letter-spacing:0.5px;font-weight:600;line-height:1;text-shadow:0 0 6px rgba(74,222,128,0.4);">LIVE</span></a>
      <a href="sost-infrastructure.html">Infrastructure</a>
      <a href="sost-otc.html" style="color:var(--green-primary)">OTC / P2P</a>
      <a href="sost-wallet.html">Wallet</a>
      <a href="sost-app/" style="color:var(--cyan-primary)">📱 App</a>
      <a href="sost-talk.html" style="color:var(--gold)"><span style="color:var(--red-primary)">SOST</span> Talk</a>
      <a href="sost-contact.html">Contact</a>
`;
  /* Console-style nav buttons: every section gets its OWN colour, all taken from colours the
     site already uses; no two neighbours (window of 4) are alike — min ΔE76 31. Mine=bright SOST red,
     Price Reference=gold, Explorer=amber, Markets=LIVE green are kept on purpose. */
  var SOST_NAV_COLORS = {"javascript:void(0)":"#f59e0b","index.html":"#d946ef","sost-genesis.html":"#22d3ee","sost-technology.html":"#00ff88","sost-transactions.html":"#ff8a8a","sost-gold-reserve.html":"#ff6600","sost-reference.html":"#d4af37","sost-universal-assets.html":"#ff00ff","sost-popc.html":"#00aaff","sost-tokenomics.html":"#39ff14","sost-roadmap.html":"#26a17b","sost-protocol-spec.html":"#b8860b","sost-whitepaper.html":"#ff5ccd","sost-mine.html":"#ff2d3b","sost-network-status.html":"#88ff00","sost-mining-calculator.html":"#38bdf8","sost-why-no-pools.html":"#fde68a","sost-getting-started.html":"#f472b6","sost-quickstart.html":"#ff6b35","sost-community.html":"#d7ff00","sost-foundation.html":"#9fe8ff","sost-foundation-balances.html":"#ffd166","sost-popc-contracts.html":"#ec4899","sost-popc-quickstart.html":"#cfe88a","sost-e2e.html":"#4488ff","sost-gold-dex.html":"#7ee2a8","sost-security.html":"#ffb86b","sost-faq.html":"#cbb6e6","beacon.html":"#e879f9","protocol-registry.html":"#a3e635","casert-spec.html":"#ff6b6b","sost-explorer.html":"#fbbf24","sost-help.html":"#7fb3ff","sost-miner-troubleshooter.html":"#c084fc","sost-markets.html":"#4ade80","sost-infrastructure.html":"#e6d9b6","sost-otc.html":"#ffff00","sost-wallet.html":"#ff8800","sost-app/":"#00ffff","sost-talk.html":"#8b9bf4","sost-contact.html":"#f5c889"};
  function sxRgba(h,a){ var n=parseInt(h.slice(1),16); return 'rgba('+(n>>16&255)+','+(n>>8&255)+','+(n&255)+','+a+')'; }
  function styleNavButtons(nl){
    if(!document.getElementById('sost-nav-sx-style')){ var st=document.createElement('style'); st.id='sost-nav-sx-style';
      st.textContent="nav .nav-links{gap:6px!important;row-gap:6px!important}\nnav .nav-links.sx-rect{flex-direction:column!important;align-items:stretch!important;flex-wrap:nowrap!important;flex:1 1 100%!important;width:100%!important;max-width:100%!important;box-sizing:border-box}\nnav .nav-links .sx-row{display:flex;gap:6px;width:100%}\nnav .nav-links.sx-rect a.sx{justify-content:center;white-space:nowrap;min-width:0}\nnav .nav-links a.sx{position:relative;display:inline-flex!important;align-items:center;gap:7px;padding:5px 11px 5px 9px!important;border-radius:3px!important;font-family:ui-monospace,\"JetBrains Mono\",Menlo,Consolas,monospace!important;font-size:10.5px!important;font-weight:600!important;letter-spacing:1.1px!important;text-transform:uppercase;line-height:1.15!important;color:var(--c)!important;text-decoration:none!important;text-shadow:0 0 8px var(--c45);border:1px solid var(--c35)!important;border-bottom-color:var(--c55)!important;background:linear-gradient(var(--c),var(--c)) 0 0/7px 1.5px no-repeat,linear-gradient(var(--c),var(--c)) 0 0/1.5px 7px no-repeat,linear-gradient(var(--c),var(--c)) 100% 100%/7px 1.5px no-repeat,linear-gradient(var(--c),var(--c)) 100% 100%/1.5px 7px no-repeat,linear-gradient(180deg,rgba(255,255,255,.07) 0%,rgba(255,255,255,0) 48%,rgba(0,0,0,.28) 100%),linear-gradient(90deg,var(--c10),rgba(9,11,15,.94) 62%)!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.06),inset 0 -1px 0 rgba(0,0,0,.7),0 1px 0 rgba(0,0,0,.85),0 0 12px -7px var(--c);transition:transform .15s ease,box-shadow .2s ease,border-color .2s ease,filter .2s ease}\nnav .nav-links a.sx{overflow:hidden}nav .nav-links a.sx::after{content:\"\";position:absolute;top:0;bottom:0;left:-60%;width:45%;pointer-events:none;background:linear-gradient(105deg,rgba(255,255,255,0) 0%,rgba(255,255,255,.22) 50%,rgba(255,255,255,0) 100%);transform:skewX(-18deg);opacity:0}nav .nav-links a.sx:hover::after{animation:sxSweep .65s ease-out 1}@keyframes sxSweep{0%{left:-60%;opacity:1}100%{left:125%;opacity:1}}\nnav .nav-links a.sx::before{content:\"\";width:5px;height:5px;border-radius:50%;flex:0 0 auto;background:var(--c);box-shadow:0 0 6px var(--c),0 0 2px var(--c);opacity:.9}\nnav .nav-links a.sx:hover{transform:translateY(-1px);filter:brightness(1.18);border-color:var(--c)!important;background-color:transparent!important;box-shadow:inset 0 0 12px -5px var(--c),0 0 16px -4px var(--c),0 2px 0 rgba(0,0,0,.85)}\nnav .nav-links a.sx:focus-visible{outline:1px solid var(--c);outline-offset:2px}\nnav .nav-links a.sx.active{border:1px solid var(--c)!important;box-shadow:inset 0 0 14px -4px var(--c),0 0 18px -3px var(--c)}\nnav .nav-links a.sx.active::before{animation:sxLed 1.3s ease-in-out infinite}\n@keyframes sxLed{0%,100%{opacity:1;box-shadow:0 0 8px var(--c),0 0 3px var(--c)}50%{opacity:.25;box-shadow:none}}\n@media (prefers-reduced-motion:reduce){nav .nav-links a.sx,nav .nav-links a.sx::before,nav .nav-links a.sx::after{transition:none!important;animation:none!important}}"; (document.head||document.documentElement).appendChild(st); }
    var as=nl.querySelectorAll('a[href]');
    for(var i=0;i<as.length;i++){ var c=SOST_NAV_COLORS[as[i].getAttribute('href')]; if(!c) continue;
      as[i].style.color=''; as[i].classList.add('sx'); as[i].style.setProperty('--c',c);
      as[i].style.setProperty('--c10',sxRgba(c,.10)); as[i].style.setProperty('--c35',sxRgba(c,.35));
      as[i].style.setProperty('--c45',sxRgba(c,.45)); as[i].style.setProperty('--c55',sxRgba(c,.55)); }
  }

  /* RECTANGLE LAYOUT: the buttons are split, IN ORDER, into the fewest rows that fit, with the rows
     balanced (linear partition minimising the widest row). Each row then stretches to the full width,
     every button growing in proportion to its natural width — so the block is an exact rectangle
     (both edges aligned on every row, the last one included). Re-run on resize / when the mobile menu
     opens (ResizeObserver) and once fonts are ready. */
  var SX_GAP = 6;
  function sxPartition(w, avail){
    var n=w.length, pre=[0]; for(var i=0;i<n;i++) pre.push(pre[i]+w[i]);
    function rowW(a,b){ return pre[b]-pre[a]+SX_GAP*(b-a-1); }
    for(var R=1;R<=n;R++){
      // dp[k][j] = minimal possible max-row-width placing first j items in k rows
      var dp=[], cut=[]; for(var k=0;k<=R;k++){ dp.push(new Array(n+1).fill(Infinity)); cut.push(new Array(n+1).fill(0)); }
      dp[0][0]=0;
      for(var k=1;k<=R;k++) for(var j=k;j<=n;j++) for(var t=k-1;t<j;t++){
        var v=Math.max(dp[k-1][t], rowW(t,j)); if(v<dp[k][j]){ dp[k][j]=v; cut[k][j]=t; } }
      if(dp[R][n]<=avail){ var rows=[], j2=n; for(var k2=R;k2>=1;k2--){ var t2=cut[k2][j2]; rows.unshift([t2,j2]); j2=t2; } return rows; }
    }
    return w.map(function(_,i){ return [i,i+1]; });
  }
  function layoutNavRect(nl){
    var as=[].slice.call(nl.querySelectorAll('a.sx')); if(!as.length) return;
    nl.classList.add('sx-rect');
    var cs=getComputedStyle(nl), avail=nl.clientWidth-parseFloat(cs.paddingLeft||0)-parseFloat(cs.paddingRight||0)-2; if(avail<=0) return;
    if(nl._sxW===avail && nl._sxDone) return;
    // flatten (undo a previous layout) and measure natural widths
    nl.classList.remove('sx-rect');
    as.forEach(function(a){ a.style.flex='0 0 auto'; nl.appendChild(a); });
    [].slice.call(nl.querySelectorAll('.sx-row')).forEach(function(r){ r.remove(); });
    var w=as.map(function(a){ return Math.ceil(a.getBoundingClientRect().width); });
    var rows=sxPartition(w, avail);
    rows.forEach(function(r){
      var row=document.createElement('div'); row.className='sx-row';
      for(var i=r[0];i<r[1];i++){ as[i].style.flex=w[i]+' 0 auto'; row.appendChild(as[i]); }
      nl.appendChild(row);
    });
    nl.classList.add('sx-rect'); nl._sxW=avail; nl._sxDone=true;
  }
  function sxWatch(nl){
    var run=function(){ nl._sxDone=false; layoutNavRect(nl); };
    if(window.ResizeObserver){ var last=0; new ResizeObserver(function(){ var cw=nl.clientWidth; if(cw && cw!==last){ last=cw; run(); } }).observe(nl); }
    else window.addEventListener('resize',run);
    if(document.fonts&&document.fonts.ready) document.fonts.ready.then(run);
    run();
  }
  function injectNav(){
    var nl = document.querySelector("nav .nav-links");
    if(!nl) return;
    nl.innerHTML = SOST_NAV_LINKS;
    var page = (location.pathname.split("/").pop() || "index.html").toLowerCase();
    if(!page) page = "index.html";
    var as = nl.querySelectorAll("a[href]");
    for(var i=0;i<as.length;i++){
      if((as[i].getAttribute("href")||"").toLowerCase() === page){ as[i].classList.add("active"); }
    }
    styleNavButtons(nl);
    sxWatch(nl);
  }
  window.__sostNavReady(injectNav);
})();

/* ============================================================================
   SOST "News & Updates" button — injected into the logo-button row (next to
   the WATCH button) of every page that has it, sized to match its sibling so
   it lines up on both the 110px standard nav and the 72px explorer nav. Edit
   here to change the button everywhere — no per-page HTML edits.
   ========================================================================== */
(function(){
  "use strict";
  if(!document.getElementById('sost-news-btn-style')){
    var st=document.createElement('style');
    st.id='sost-news-btn-style';
    st.textContent=[
      '@keyframes newsBtnGlow{0%,100%{box-shadow:0 0 12px rgba(245,158,11,.42),0 0 22px rgba(251,1,13,.14)}50%{box-shadow:0 0 20px rgba(245,158,11,.82),0 0 36px rgba(251,1,13,.32),0 0 52px rgba(245,158,11,.20)}}',
      /* ------------------------------------------------------------------------------------
         The four large modules, in one silhouette — body, border AND glow.

         The first attempt kept each tile's box-shadow on a 20%-rounded box and masked only the
         body to a superellipse. The two shapes did not coincide, so at every corner a wedge of
         the nav's dark background showed between them: the "thick black corners" the owner saw.
         A glow must never reveal a second, different shape behind the thing it belongs to.

         So nothing keeps a rounded rectangle any more. The construction is:

           wrapper  filter: drop-shadow(...) — a drop-shadow follows the ALPHA of what it wraps,
                    so the halo takes the superellipse for free. Animated here, so the pulse
                    lives on the glow rather than on a box-shadow that cannot follow a mask.
           element  masked to the superellipse; its background IS the 1px outline colour.
           ::before masked identically, inset by 1px, carrying the gradient — so the outline is a
                    true superellipse ring rather than a square border clipped at the corners.

         Exponent n = 2.466: the curve whose enclosed area is 84.2% of its bounding square, which
         is what the logo PNG's own alpha measures. Read from the file, not chosen by eye.
         ------------------------------------------------------------------------------------ */
      '.sq-wrap{display:inline-flex;flex:0 0 auto;line-height:0;',
      '  animation:sqPulse 2.9s ease-in-out infinite}',
      '@keyframes sqPulse{',
      '  0%,100%{filter:drop-shadow(0 0 9px var(--g1)) drop-shadow(0 0 20px var(--g2))}',
      '  50%{filter:drop-shadow(0 0 20px var(--g1)) drop-shadow(0 0 42px var(--g2))',
      '       drop-shadow(0 0 66px var(--g3,var(--g2)))}}',
      '.sq{-webkit-mask-image:url(\"data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%20100%20100%22%20preserveAspectRatio%3D%22none%22%3E%3Cpath%20d%3D%22M100.0%2050.0L99.7%2058.5L99.0%2064.8L97.7%2070.4L95.9%2075.4L93.7%2080.0L91.0%2084.1L87.7%2087.7L84.1%2091.0L80.0%2093.7L75.4%2095.9L70.4%2097.7L64.8%2099.0L58.5%2099.7L50.0%20100.0L41.5%2099.7L35.2%2099.0L29.6%2097.7L24.6%2095.9L20.0%2093.7L15.9%2091.0L12.3%2087.7L9.0%2084.1L6.3%2080.0L4.1%2075.4L2.3%2070.4L1.0%2064.8L0.3%2058.5L0.0%2050.0L0.3%2041.5L1.0%2035.2L2.3%2029.6L4.1%2024.6L6.3%2020.0L9.0%2015.9L12.3%2012.3L15.9%209.0L20.0%206.3L24.6%204.1L29.6%202.3L35.2%201.0L41.5%200.3L50.0%200.0L58.5%200.3L64.8%201.0L70.4%202.3L75.4%204.1L80.0%206.3L84.1%209.0L87.7%2012.3L91.0%2015.9L93.7%2020.0L95.9%2024.6L97.7%2029.6L99.0%2035.2L99.7%2041.5Z%22%2F%3E%3C%2Fsvg%3E\");mask-image:url(\"data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%20100%20100%22%20preserveAspectRatio%3D%22none%22%3E%3Cpath%20d%3D%22M100.0%2050.0L99.7%2058.5L99.0%2064.8L97.7%2070.4L95.9%2075.4L93.7%2080.0L91.0%2084.1L87.7%2087.7L84.1%2091.0L80.0%2093.7L75.4%2095.9L70.4%2097.7L64.8%2099.0L58.5%2099.7L50.0%20100.0L41.5%2099.7L35.2%2099.0L29.6%2097.7L24.6%2095.9L20.0%2093.7L15.9%2091.0L12.3%2087.7L9.0%2084.1L6.3%2080.0L4.1%2075.4L2.3%2070.4L1.0%2064.8L0.3%2058.5L0.0%2050.0L0.3%2041.5L1.0%2035.2L2.3%2029.6L4.1%2024.6L6.3%2020.0L9.0%2015.9L12.3%2012.3L15.9%209.0L20.0%206.3L24.6%204.1L29.6%202.3L35.2%201.0L41.5%200.3L50.0%200.0L58.5%200.3L64.8%201.0L70.4%202.3L75.4%204.1L80.0%206.3L84.1%209.0L87.7%2012.3L91.0%2015.9L93.7%2020.0L95.9%2024.6L97.7%2029.6L99.0%2035.2L99.7%2041.5Z%22%2F%3E%3C%2Fsvg%3E\");-webkit-mask-size:100% 100%;mask-size:100% 100%;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;border-radius:0 !important;box-shadow:none !important;border:0 !important;',
      '  position:relative;isolation:isolate;background:var(--sq-line) !important;',
      '  animation:none !important}',
      '.sq::before{content:"";position:absolute;inset:0;z-index:-1;-webkit-mask-image:url(\"data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%20100%20100%22%20preserveAspectRatio%3D%22none%22%3E%3Cpath%20d%3D%22M100.0%2050.0L99.7%2058.5L99.0%2064.8L97.7%2070.4L95.9%2075.4L93.7%2080.0L91.0%2084.1L87.7%2087.7L84.1%2091.0L80.0%2093.7L75.4%2095.9L70.4%2097.7L64.8%2099.0L58.5%2099.7L50.0%20100.0L41.5%2099.7L35.2%2099.0L29.6%2097.7L24.6%2095.9L20.0%2093.7L15.9%2091.0L12.3%2087.7L9.0%2084.1L6.3%2080.0L4.1%2075.4L2.3%2070.4L1.0%2064.8L0.3%2058.5L0.0%2050.0L0.3%2041.5L1.0%2035.2L2.3%2029.6L4.1%2024.6L6.3%2020.0L9.0%2015.9L12.3%2012.3L15.9%209.0L20.0%206.3L24.6%204.1L29.6%202.3L35.2%201.0L41.5%200.3L50.0%200.0L58.5%200.3L64.8%201.0L70.4%202.3L75.4%204.1L80.0%206.3L84.1%209.0L87.7%2012.3L91.0%2015.9L93.7%2020.0L95.9%2024.6L97.7%2029.6L99.0%2035.2L99.7%2041.5Z%22%2F%3E%3C%2Fsvg%3E\");mask-image:url(\"data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%20100%20100%22%20preserveAspectRatio%3D%22none%22%3E%3Cpath%20d%3D%22M100.0%2050.0L99.7%2058.5L99.0%2064.8L97.7%2070.4L95.9%2075.4L93.7%2080.0L91.0%2084.1L87.7%2087.7L84.1%2091.0L80.0%2093.7L75.4%2095.9L70.4%2097.7L64.8%2099.0L58.5%2099.7L50.0%20100.0L41.5%2099.7L35.2%2099.0L29.6%2097.7L24.6%2095.9L20.0%2093.7L15.9%2091.0L12.3%2087.7L9.0%2084.1L6.3%2080.0L4.1%2075.4L2.3%2070.4L1.0%2064.8L0.3%2058.5L0.0%2050.0L0.3%2041.5L1.0%2035.2L2.3%2029.6L4.1%2024.6L6.3%2020.0L9.0%2015.9L12.3%2012.3L15.9%209.0L20.0%206.3L24.6%204.1L29.6%202.3L35.2%201.0L41.5%200.3L50.0%200.0L58.5%200.3L64.8%201.0L70.4%202.3L75.4%204.1L80.0%206.3L84.1%209.0L87.7%2012.3L91.0%2015.9L93.7%2020.0L95.9%2024.6L97.7%2029.6L99.0%2035.2L99.7%2041.5Z%22%2F%3E%3C%2Fsvg%3E\");-webkit-mask-size:100% 100%;mask-size:100% 100%;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;',
      /* inset:0 on purpose. Insetting this by a pixel exposes a real ring of
         --sq-line and measures BRIGHTER at the bottom edge (+14.8 vs +9.8 at dpr3 with
         the pulse frozen), which is the opposite of what it looks like it should do. */
      '  background:var(--sq-bg)}',
      /* per module: its own colours, unchanged. Only the geometry is shared. */
      '.sq-dtd{--sq-line:#39ff14;--sq-bg:radial-gradient(circle at 50% 35%,#0f2417,#07120b)}',
      '.sq-wrap-dtd{--g1:rgba(57,255,20,.75);--g2:rgba(57,255,20,.45);--g3:rgba(57,255,20,.25)}',
      '.sq-as{--sq-line:#f5c518;--sq-bg:linear-gradient(135deg,#2a0f2c,#4a1f4d)}',
      '.sq-wrap-as{--g1:rgba(255,212,0,.75);--g2:rgba(123,45,126,.5);--g3:rgba(91,42,94,.3)}',
      '.sq-news{--sq-line:rgba(245,158,11,.7);--sq-bg:linear-gradient(135deg,#1b1206,#2c1d08,#3a2a0a)}',
      '.sq-wrap-news{--g1:rgba(245,158,11,.8);--g2:rgba(245,158,11,.45);--g3:rgba(245,158,11,.22)}',
      /* ConvergenceX was a bare image floating beside three tiles. It now sits in the same
         module: identical silhouette, a dark ground of its own, and the logo inside it. */
      '.sq-cx{--sq-line:rgba(34,211,238,.55);--sq-bg:#000003}',
      '.sq-wrap-cx{--g1:rgba(34,211,238,.8);--g2:rgba(34,211,238,.45);--g3:rgba(34,211,238,.22)}',
      '.sq-cx::before{inset:1px}',
      '.sq-cx img{width:100%;height:100%;object-fit:contain;padding:4%;box-sizing:border-box;',
      '  filter:none !important;border-radius:0 !important;display:block;background:#000003}',
      '.sost-news-btn{display:inline-flex;flex-direction:column;align-items:center;justify-content:center;border-radius:20%;background:linear-gradient(135deg,#1b1206,#2c1d08,#3a2a0a);border:1px solid rgba(245,158,11,.6);text-decoration:none;line-height:1;flex:0 0 auto;box-shadow:0 0 20px rgba(245,158,11,.95),0 0 40px rgba(245,158,11,.55);overflow:hidden;-webkit-tap-highlight-color:transparent}',
      '.sost-news-btn:hover{border-color:rgba(255,200,87,.95);transform:translateY(-1px);transition:transform .15s ease,border-color .2s ease}',
      '/* inner-logo enlargement: inner content only, outer circle unchanged */',
      'nav img[src*="convergencex-logo"]{transform:scale(1.3125)}',
      'nav a.atomix-btn .atomix-icon{transform:translateY(7px) scale(1.25)}',
      'nav a.atomix-btn .atomix-label{transform:translateY(7px) scale(0.906)}',
      'nav .sost-news-btn>span{transform:translateY(7px) scale(1.25)}',
      'nav .sost-news-btn>span:last-child{transform:translateY(7px) scale(0.997)}',
      'nav a[href$="#dtd"]>span,nav .sost-dtd-btn>span{transform:scale(1.05)}',
      'body.nav-collapsed nav .sost-news-btn{display:none !important}'
    ].join('\n');
    (document.head||document.documentElement).appendChild(st);
  }
  function injectNewsBtn(){
    var nav=document.querySelector('nav');
    if(!nav) return;
    if(nav.querySelector('a[href="news.html"]')) return;          // already present
    // Anchor on the big Atomic Swap tile so NEWS lands in the large-button row, right
    // after it (NOT in the small Watch/Home row). Match by its asBtnGlow animation so it
    // is immune to href changes (the tile now points to sost-dex.html, formerly the
    // founder console). Fall back to the legacy hrefs / WATCH icon for old structures.
    var watch=nav.querySelector('a.atomix-btn')||nav.querySelector('a[style*="asBtnGlow"]')||nav.querySelector('a[href="sost-dex.html"]')||nav.querySelector('a[href="atomic-swap-console.html"]')||nav.querySelector('a[onclick="openSv()"]');
    if(!watch) return;                                            // need the logo-button row
    var sz=window.__sostModSize(nav, watch.offsetWidth);          // match the sibling box
    var a=document.createElement('a');
    a.href='news.html'; a.title='News & Updates';
    a.className='sost-news-btn';
    a.style.width=sz+'px'; a.style.height=sz+'px'; a.style.minWidth=sz+'px';
    var ic=Math.round(sz*0.26), tx=Math.max(8,Math.round(sz*0.093));
    a.innerHTML='<span style="font-size:'+ic+'px;line-height:1;margin-bottom:2px">📰</span>'
      +'<span style="color:#f59e0b;font-size:'+tx+'px;font-weight:900;letter-spacing:.5px;line-height:1.08;text-align:center;text-shadow:0 0 8px rgba(245,158,11,.6)">NEWS &amp;<br>UPDATES</span>';
    watch.parentNode.insertBefore(a, watch.nextSibling);
  }
  window.__sostNavReady(injectNewsBtn);
})();

/* ============================================================================
   SOST "Watch" (2-video) overlay — shared. Pages that already embed their own
   #sv-modal + openSv() (e.g. Home) keep theirs untouched; every other page gets
   this self-contained version so the nav "▶ Watch" link works everywhere.
   ========================================================================== */
(function(){
  "use strict";
  if(document.getElementById('sv-modal') || typeof window.openSv === 'function') return; // page has its own
  function build(){
    if(document.getElementById('sv-modal')) return;
    var st=document.createElement('style');
    st.textContent=[
      '.sv-modal{display:none;position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.975);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);align-items:center;justify-content:center}',
      '.sv-modal.open{display:flex}',
      /* The V15 banner and the sticky nav are page furniture, and the modal is an overlay on
         top of the page — so they were showing through and across the player. Hidden only while
         Watch is open, and restored on close: the banner is not removed from the site. */
      'body.sv-open #v15banner,body.sv-open .v15banner,body.sv-open nav,',
      'body.sv-open .developer-note,body.sv-open #developer-note{visibility:hidden !important}',
      'body.sv-open{overflow:hidden}',
      '.sv-content{position:relative;max-width:92vw;max-height:88vh;display:flex;flex-direction:column;gap:14px;align-items:center}',
      '.sv-video{max-width:92vw;max-height:80vh;background:#000;border-radius:10px;box-shadow:0 0 60px rgba(251,1,13,.18);outline:none}',
      '.sv-close{position:absolute;top:-46px;right:-2px;background:rgba(0,0,0,.8);border:1px solid rgba(255,255,255,.22);color:#fff;width:38px;height:38px;border-radius:50%;font-size:22px;line-height:1;cursor:pointer;padding:0;display:flex;align-items:center;justify-content:center}',
      '.sv-close:hover{background:rgba(251,1,13,.4);border-color:#fb010d}',
      '.sv-caption{text-align:center;font-size:11px;letter-spacing:3px;color:#94a3b8;font-family:ui-monospace,Menlo,Consolas,monospace;text-transform:uppercase}',
      '.sv-ch-title{text-align:center;font-size:12px;letter-spacing:4px;color:#22d3ee;font-family:ui-monospace,Menlo,Consolas,monospace;text-transform:uppercase;margin-bottom:6px}',
      '.sv-cards .sv-card:only-child{width:560px;max-width:76vw}',
      '.sv-cards .sv-card:only-child .sv-thumb{aspect-ratio:16/9}',
      '.sv-cards{display:flex;gap:22px;flex-wrap:wrap;justify-content:center;max-width:92vw}',
      '.sv-card{width:340px;max-width:42vw;min-width:240px;background:linear-gradient(160deg,#0a1117,#0c1620);border:1px solid rgba(34,211,238,.30);border-radius:14px;padding:0 0 16px;cursor:pointer;display:flex;flex-direction:column;align-items:stretch;overflow:hidden;text-align:left;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}',
      '.sv-card:hover{transform:translateY(-4px)}',
      '.sv-card-sost:hover{border-color:#22d3ee;box-shadow:0 0 26px rgba(34,211,238,.35)}',
      '.sv-card-mech:hover{border-color:#fb010d;box-shadow:0 0 26px rgba(251,1,13,.35)}',
      '.sv-thumb{position:relative;width:100%;aspect-ratio:16/9;background:#000 center/cover no-repeat;display:flex;align-items:center;justify-content:center}',
      '.sv-play{width:58px;height:58px;border-radius:50%;background:rgba(0,0,0,.55);border:2px solid rgba(255,255,255,.85);color:#fff;font-size:22px;display:flex;align-items:center;justify-content:center;padding-left:4px}',
      '.sv-card-h{font-size:18px;font-weight:800;color:#e5e7eb;margin:14px 16px 2px;font-family:Inter,system-ui,sans-serif}',
      '.sv-card-s{font-size:12.5px;color:#94a3b8;margin:0 16px;font-family:Inter,system-ui,sans-serif}',
      '.sv-back{background:transparent;border:1px solid rgba(255,255,255,.22);color:#cbd5e1;border-radius:8px;padding:7px 14px;font-size:12px;cursor:pointer;letter-spacing:1px}',
      '.sv-back:hover{border-color:#22d3ee;color:#22d3ee}',
      '@media(max-width:560px){.sv-card{max-width:88vw}.sv-cards{gap:14px}}'
    ].join('');
    document.head.appendChild(st);
    var m=document.createElement('div');
    m.id='sv-modal'; m.className='sv-modal'; m.setAttribute('aria-hidden','true');
    m.onclick=function(e){ window.closeSv(e); };
    m.innerHTML=''
      +'<div class="sv-content" onclick="event.stopPropagation()">'
      +'<button class="sv-close" type="button" onclick="closeSv(null,true)" aria-label="Close">&times;</button>'
      +'<div id="sv-chooser" class="sv-chooser"><div class="sv-ch-title">&#9654; CHOOSE A VIDEO</div>'
      +'<div class="sv-cards">'
      +'<button class="sv-card sv-card-sost" type="button" onclick="pickSv(\'sost-intro.mp4?v=20261011b\',\'SOST in 3 Minutes &middot; protocol, mining &amp; tokenization\')">'
      +'<span class="sv-thumb" style="background-image:url(\'sost-intro-poster.jpg?v=20261011b\')"><span class="sv-play">&#9654;</span></span>'
      +'<span class="sv-card-h">SOST in 3 Minutes</span><span class="sv-card-s">Protocol, mining &amp; tokenization</span></button>'
      +'<button class="sv-card sv-card-mech" type="button" onclick="pickSv(\'sost-mechanisms.mp4?v=20261011c\',\'SOST Mechanisms &middot; Atomic Swap, DTD &amp; DTD Jackpot\')">'
      +'<span class="sv-thumb" style="background-image:url(\'sost-mechanisms-poster.jpg?v=20261011\')"><span class="sv-play">&#9654;</span></span>'
      +'<span class="sv-card-h">SOST Mechanisms</span><span class="sv-card-s">Atomic Swap, DTD &amp; DTD Jackpot &middot; how the three mechanisms work</span></button>'
      +'</div></div>'
      +'<div id="sv-player" class="sv-player" style="display:none">'
      +'<video id="sv-video" class="sv-video" controls preload="metadata" playsinline><source id="sv-source" src="" type="video/mp4">Your browser does not support HTML5 video.</video>'
      +'<div class="sv-caption" id="sv-caption"></div>'
      +'<button class="sv-back" type="button" onclick="backSv()">&larr;&nbsp; Choose another video</button>'
      +'</div></div>';
    document.body.appendChild(m);
  }
  window.openSv=function(){ try{document.body.classList.add('sv-open');}catch(e){}
     build(); var m=document.getElementById('sv-modal'); if(!m)return;
    m.classList.add('open'); m.setAttribute('aria-hidden','false'); document.body.style.overflow='hidden'; window.backSv(); };
  window.pickSv=function(src,cap){ document.getElementById('sv-chooser').style.display='none';
    document.getElementById('sv-player').style.display='flex'; document.getElementById('sv-caption').innerHTML=cap;
    var v=document.getElementById('sv-video'),s=document.getElementById('sv-source'); s.setAttribute('src',src); v.load();
    try{ v.currentTime=0; v.play().catch(function(){}); }catch(e){} };
  window.backSv=function(){ var v=document.getElementById('sv-video'); try{ v.pause(); }catch(e){}
    document.getElementById('sv-player').style.display='none'; document.getElementById('sv-chooser').style.display='block'; };
  window.closeSv=function(evt,force){ if(evt&&!force&&evt.target.id!=='sv-modal')return;
    try{document.body.classList.remove('sv-open');}catch(e){}
    var m=document.getElementById('sv-modal'); if(!m)return; m.classList.remove('open'); m.setAttribute('aria-hidden','true');
    document.body.style.overflow=''; var v=document.getElementById('sv-video'); try{ v.pause(); }catch(e){} };
  document.addEventListener('keydown',function(e){ if(e.key==='Escape') window.closeSv(null,true); });
})();

/* ============================================================================
   DTD — injected into the large-button row on every page.

   It existed on the home page only. Not "everywhere but the explorer": the explorer was simply
   the page where its absence was noticed, and fifty-five others were missing it too. Pasting the
   markup into each would have recreated the drift this file exists to prevent, so it is built
   here once and anchored on the Atomic Swap tile — the same technique injectNewsBtn already
   uses, and immune to href changes for the same reason.

   Order matches the home page: ConvergenceX, DTD, Atomic Swap, News. DTD goes BEFORE the
   anchor; News goes after it.
   ========================================================================== */
(function(){
  "use strict";
  function styleOnce(){
    if(document.getElementById('sost-dtd-btn-style')) return;
    var st=document.createElement('style'); st.id='sost-dtd-btn-style';
    st.textContent=[
      '@keyframes dtdBtnGlow{0%,100%{box-shadow:0 0 12px rgba(57,255,20,.45),0 0 22px rgba(57,255,20,.18)}',
      '50%{box-shadow:0 0 26px rgba(57,255,20,.9),0 0 52px rgba(57,255,20,.55),0 0 78px rgba(57,255,20,.3)}}',
      '.sost-dtd-btn{display:inline-flex;flex-direction:column;align-items:center;justify-content:center;',
      'border-radius:20%;background:radial-gradient(circle at 50% 35%,#0f2417,#07120b);',
      'border:1px solid #39ff14;text-decoration:none;line-height:1;flex:0 0 auto;',
      'animation:dtdBtnGlow 2.6s ease-in-out infinite;overflow:hidden;',
      '-webkit-tap-highlight-color:transparent}',
      '.sost-dtd-btn:hover{border-color:#7CFFA0;transform:translateY(-1px);transition:transform .15s ease,border-color .2s ease}',
      'body.nav-collapsed nav .sost-dtd-btn{display:none !important}'
    ].join('');
    (document.head||document.documentElement).appendChild(st);
  }
  function injectDtdBtn(){
    var nav=document.querySelector('nav');
    if(!nav) return;
    // Already there — the home page ships its own inline copy and must not gain a second.
    if(nav.querySelector('.sost-dtd-btn') || nav.querySelector('a[href$="#dtd"]')) return;
    var anchor=nav.querySelector('a.atomix-btn')||nav.querySelector('a[style*="asBtnGlow"]')||nav.querySelector('a[href="sost-dex.html"]');
    if(!anchor) return;                       // no large-button row on this page
    styleOnce();
    var sz=anchor.offsetWidth; if(!sz||sz<90) sz=110;   // match the sibling box; guard the CSS-load race (avoid the old 72 fallback)
    sz=window.__sostModSize(nav, sz);
    var a=document.createElement('a');
    a.href='index.html#dtd'; a.title='DTD — Deterministic Token Distribution';
    a.className='sost-dtd-btn';
    a.style.width=sz+'px'; a.style.height=sz+'px'; a.style.minWidth=sz+'px';
    var big=Math.max(16,Math.round(sz*0.28)), small=Math.max(6,Math.round(sz*0.09));
    a.innerHTML='<span style="color:#39ff14;font-size:'+big+'px;font-weight:900;letter-spacing:1px;'
      +'text-shadow:0 0 14px rgba(57,255,20,.85)">DTD</span>'
      +'<span style="color:#7CFFA0;font-size:'+small+'px;font-weight:700;letter-spacing:.4px;'
      +'text-align:center;margin-top:2px">DETERMINISTIC<br>TOKEN<br>DISTRIBUTION</span>';
    anchor.parentNode.insertBefore(a, anchor);
  }
  window.__sostNavReady(injectDtdBtn);
})();

/* ============================================================================
   Wrap the four large modules so body, border and glow share one silhouette.

   A wrapper is needed rather than a class alone: filter: drop-shadow follows the alpha of what
   it is applied to, and mask clips a filter applied to the same element. Putting the glow on a
   parent of the masked tile is what makes the halo take the superellipse instead of revealing a
   rounded rectangle behind it.

   Done here, once, rather than in fifty-seven files: the shape belongs to the component.
   ========================================================================== */
(function(){
  "use strict";
  function wrap(el, kind){
    if(!el || el.parentElement.classList.contains('sq-wrap')) return;
    var w=document.createElement('span');
    w.className='sq-wrap sq-wrap-'+kind;
    el.parentNode.insertBefore(w, el);
    w.appendChild(el);
    el.classList.add('sq','sq-'+kind);
  }
  function tag(){
    var nav=document.querySelector('nav');
    if(!nav) return;
    // ConvergenceX: the <img> gains a tile of its own so it reads as the same kind of module.
    var cx=nav.querySelector('img[src*="convergencex-logo"]');
    if(cx && !cx.parentElement.classList.contains('sq')){
      var box=document.createElement('span');
      box.style.cssText='display:inline-flex;width:'+window.__sostModSize(nav, cx.offsetWidth)+'px;height:'
        +window.__sostModSize(nav, cx.offsetHeight)+'px;flex:0 0 auto';
      cx.parentNode.insertBefore(box, cx); box.appendChild(cx);
      wrap(box,'cx');
    }
    nav.querySelectorAll('a[style*="dtdBtnGlow"],.sost-dtd-btn').forEach(function(e){ wrap(e,'dtd'); });
    nav.querySelectorAll('a[style*="asBtnGlow"]').forEach(function(e){ wrap(e,'as'); });
    // ATOMIC SWAP DEX: same module geometry, its own paint (css/atomix-btn.css).
    nav.querySelectorAll('a.atomix-btn').forEach(function(e){ wrap(e,'ax'); });
    nav.querySelectorAll('.sost-news-btn').forEach(function(e){ wrap(e,'news'); });
  }
  window.__sostNavReady(tag);
  window.__sostNavReady(function(){ setTimeout(tag,0); setTimeout(tag,400); setTimeout(tag,1200); });
})();

/* ============================================================================
   Flip a body class around whatever Watch implementation the page owns.

   Fifty-four pages define their own openSv/closeSv inline, so the shared modal in this file
   returns early on nearly all of them. Wrapping the globals reaches every one of them from a
   single place — and if a page has no Watch at all, this does nothing.
   ========================================================================== */
(function(){
  "use strict";
  function wrapSv(){
    if(window.__svWrapped) return;
    var o=window.openSv, c=window.closeSv;
    if(typeof o!=='function') return;
    window.__svWrapped=1;
    window.openSv=function(){ try{document.body.classList.add('sv-open');}catch(e){}
      return o.apply(this,arguments); };
    if(typeof c==='function'){
      window.closeSv=function(){ var r=c.apply(this,arguments);
        // only drop the class if the modal really closed — closeSv ignores clicks inside it
        try{ if(!document.querySelector('.sv-modal.open')) document.body.classList.remove('sv-open'); }catch(e){}
        return r; };
    }
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',wrapSv,{once:true});
  else wrapSv();
  setTimeout(wrapSv,0); setTimeout(wrapSv,600);
})();

/* ============================================================================
   SOST TOKENIZATION (Asset Layer) — global nav logo. A COLOUR-INVERTED TWIN of the
   SOST logo: identical size, shape and silhouette (asset-layer-logo.png is a pixel
   swap of sost-logo.png — red body, black Σ). No text, no badge. PULSING WHITE glow
   (in sync with the SOST mark). Sits IMMEDIATELY BEFORE the
   ConvergenceX logo. Links to sost-universal-assets.html. Additional module; never
   replaces the SOST logo. No consensus/backend involvement.
   ========================================================================== */
(function(){
  "use strict";
  var LOGO='asset-layer-logo.png?v=v434';
  function styleOnce(){
    if(document.getElementById('sost-tok-logo-style')) return;
    var st=document.createElement('style'); st.id='sost-tok-logo-style';
    st.textContent=[
      'a.sost-tok-logo{display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;',
      'text-decoration:none;-webkit-tap-highlight-color:transparent;transition:transform .15s ease}',
      'a.sost-tok-logo img{object-fit:cover;display:block;animation:tokLogoPulse 4.7s ease-in-out infinite}',
      '@keyframes tokLogoPulse{0%,100%{filter:drop-shadow(0 0 4px rgba(255,255,255,.5)) drop-shadow(0 0 10px rgba(255,255,255,.3))}50%{filter:drop-shadow(0 0 22px rgba(255,255,255,1)) drop-shadow(0 0 52px rgba(255,255,255,.9)) drop-shadow(0 0 88px rgba(255,255,255,.6))}}',
      'a.sost-tok-logo:hover{transform:translateY(-1px)}',
      '@media(prefers-reduced-motion:reduce){a.sost-tok-logo img{animation:none;filter:drop-shadow(0 0 14px rgba(255,255,255,.95)) drop-shadow(0 0 34px rgba(255,255,255,.6))}}',
      /* start the right-hand group, immediately before ConvergenceX (steal its margin) */
      'nav .container > a.sost-tok-logo{margin-left:auto !important}',
      'nav .container > a.sost-tok-logo + a[href="casert-spec.html"]{margin-left:0 !important;flex:0 0 auto !important}',
      /* hide with the rest of the bar under HIDE NAV */
      'body.nav-collapsed nav a.sost-tok-logo{display:none !important}'
    ].join('');
    (document.head||document.documentElement).appendChild(st);
  }
  function inject(){
    var nav=document.querySelector('nav'); if(!nav) return;
    if(nav.querySelector('a.sost-tok-logo')) return;
    var cx=nav.querySelector('a[href="casert-spec.html"]'); if(!cx) return; // no canonical bar here
    styleOnce();
    // EXACTLY the SOST logo size (110 on every page); fall back to ConvergenceX/110.
    var sImg=nav.querySelector('.nav-logo img');
    var sz=window.__sostModSize(nav, (sImg&&sImg.offsetWidth) || (cx.querySelector('img')&&cx.querySelector('img').offsetWidth) || cx.offsetWidth || 110);
    var a=document.createElement('a');
    a.href='sost-universal-assets.html'; a.className='sost-tok-logo';
    a.title='SOST Tokenization & Offers';
    a.setAttribute('aria-label','SOST Tokenization & Offers');
    var img=document.createElement('img');
    img.src=LOGO; img.alt='SOST Tokenization';
    img.width=sz; img.height=sz; img.style.width=sz+'px'; img.style.height=sz+'px';
    a.appendChild(img);
    cx.parentNode.insertBefore(a, cx);   // JUST BEFORE ConvergenceX
  }
  window.__sostNavReady(inject);
  window.__sostNavReady(function(){ setTimeout(inject,0); setTimeout(inject,350); setTimeout(inject,800); });
})();


/* ============================================================================
   SITE-VISIT COUNTER — on every page's top nav (same place & behaviour as Home).
   Reuses a page's existing #vcx-sost host (Home/Explorer ship one inline); on all
   other pages it injects the host as a sibling of .nav-links so HIDE NAV folds it
   away too. Collapsed by default (a discreet "▸ site visits" button); one shared
   /counter backend (site=sostcore) so the number is identical everywhere.
   ========================================================================== */
(function(){
  "use strict";
  if(!document.getElementById('vcx-counter-style')){
    var st=document.createElement('style'); st.id='vcx-counter-style';
    st.textContent=".vcx{display:inline-flex;align-items:center;gap:9px;padding:7px 14px;border:1px solid var(--vcx-bd);border-radius:999px;background:var(--vcx-bg);font-family:ui-monospace,Menlo,Consolas,monospace;vertical-align:middle}"
    +".vcx-dot{width:7px;height:7px;border-radius:50%;background:var(--vcx-ac);box-shadow:0 0 8px var(--vcx-ac);animation:vcxP 1.8s ease-in-out infinite;flex:0 0 auto}"
    +"@keyframes vcxP{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.75)}}"
    +".vcx-num{display:inline-flex;font-weight:700;font-size:15px;letter-spacing:.5px;color:var(--vcx-ac);text-shadow:0 0 10px var(--vcx-ac)}"
    +".vcx-d{display:inline-block;height:1.25em;width:.64em;overflow:hidden}"
    +".vcx-s{display:flex;flex-direction:column;transition:transform 1.6s cubic-bezier(.16,1,.3,1)}"
    +".vcx-s>i{height:1.25em;line-height:1.25em;text-align:center;font-style:normal}"
    +".vcx-sep{display:inline-block;width:.32em;text-align:center;opacity:.65;color:var(--vcx-ac)}"
    +".vcx-lbl{font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:var(--vcx-mut)}"
    +".vcx-btn{font:600 10px/1 ui-monospace,Menlo,Consolas,monospace;letter-spacing:1.3px;text-transform:uppercase;color:var(--vcx-mut);background:transparent;border:1px solid var(--vcx-bd);border-radius:999px;padding:6px 12px;cursor:pointer;opacity:.7;transition:opacity .2s,color .2s,border-color .2s}"
    +".vcx-btn:hover{opacity:1;color:var(--vcx-ac);border-color:var(--vcx-ac)}";
    (document.head||document.documentElement).appendChild(st);
  }
  function fmt(n){ return Number(n).toLocaleString('en-US'); }
  function build(el,val){
    var s=fmt(val); el.innerHTML='';
    for(var i=0;i<s.length;i++){ var ch=s[i];
      if(ch<'0'||ch>'9'){ var sp=document.createElement('span'); sp.className='vcx-sep'; sp.textContent=ch; el.appendChild(sp); continue; }
      var d=document.createElement('span'); d.className='vcx-d';
      var stc=document.createElement('span'); stc.className='vcx-s';
      for(var k=0;k<=9;k++){ var it=document.createElement('i'); it.textContent=k; stc.appendChild(it); }
      d.appendChild(stc); el.appendChild(d);
      (function(stc,t){ stc.style.transform='translateY(0)'; setTimeout(function(){ stc.style.transform='translateY(-'+(t*10)+'%)'; },80); })(stc,+ch);
    }
  }
  function ensureHost(){
    var h=document.getElementById('vcx-sost'); if(h) return h;
    var nav=document.querySelector('nav'); if(!nav) return null;
    var nl=nav.querySelector('.nav-links'); var parent=(nl&&nl.parentNode)||nav;
    h=document.createElement('span'); h.id='vcx-sost';
    h.style.cssText='margin-left:auto;display:inline-flex;align-items:center';
    if(nl&&nl.parentNode){ nl.parentNode.insertBefore(h, nl.nextSibling); } else { parent.appendChild(h); }
    return h;
  }
  function mountCounter(){
    var host=ensureHost(); if(!host) return;
    if(host.querySelector('.vcx-btn')) return;        // already mounted (Home/Explorer inline, or earlier call)
    var o={site:'sostcore',seed:3375,base:'/counter',btn:'▸ site visits',accent:'#4ade80',border:'#16331f',bg:'rgba(8,16,10,.7)',mut:'#5f7a68',label:'site visits'};
    host.style.setProperty('--vcx-ac',o.accent); host.style.setProperty('--vcx-bd',o.border);
    host.style.setProperty('--vcx-bg',o.bg); host.style.setProperty('--vcx-mut',o.mut);
    var sk='vcx_'+o.site, hit=!sessionStorage.getItem(sk);
    if(hit){ try{sessionStorage.setItem(sk,'1');}catch(e){} }
    // ONE request on load: registers the visit (first page of the session) and returns the real count,
    // so the odometer rolls ONCE, straight to the live number. seed is only a fallback if /counter is down.
    var real=null, shown=false;
    var ready=fetch(o.base+'?site='+encodeURIComponent(o.site)+(hit?'&hit=1':'')).then(function(r){return r.json();}).then(function(d){
      if(d&&typeof d.count==='number') real=d.count;
    }).catch(function(){});
    var btn=document.createElement('button'); btn.type='button'; btn.className='vcx-btn'; btn.textContent=o.btn;
    var box=document.createElement('span'); box.className='vcx'; box.style.display='none';
    var dot=document.createElement('span'); dot.className='vcx-dot';
    var num=document.createElement('span'); num.className='vcx-num';
    var lbl=document.createElement('span'); lbl.className='vcx-lbl'; lbl.textContent=o.label;
    box.appendChild(dot); box.appendChild(num); box.appendChild(lbl);
    host.appendChild(btn); host.appendChild(box);
    function show(){ if(shown) return; shown=true; build(num, real!==null?real:o.seed); }
    btn.addEventListener('click',function(){
      btn.style.display='none'; box.style.display='inline-flex';
      if(real!==null){ show(); return; }
      num.textContent='\u2026'; ready.then(show); setTimeout(show,4000);
    });
  }
  window.__sostNavReady(mountCounter);
  window.__sostNavReady(function(){ setTimeout(mountCounter,600); setTimeout(mountCounter,1600); });
})();

/* ============================================================================
   wSOST & GOLD VAULT — large circular nav module (research roadmap page).
   Sits between ATOMIC SWAP DEX and NEWS & UPDATES in the large-button row of every
   page that has one (Explorer included). Circular by design: the emblem is the SOST
   Sigma inside a single red ring ("wrapped"). Links to sost-wsost-gold-vault.html.
   Research page only — no consensus, bridge or wallet involvement.
   ========================================================================== */
(function(){
  "use strict";
  var IMG='assets/wsost/wsost-gold-vault-nav-256.webp?v=v554', IMG_PNG='assets/wsost/wsost-gold-vault-nav-256.png?v=v554';
  function styleOnce(){
    if(document.getElementById('sost-wsost-btn-style')) return;
    var st=document.createElement('style'); st.id='sost-wsost-btn-style';
    st.textContent=[
      'a.sost-wsost-btn{display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;border-radius:50%;',
      'text-decoration:none;-webkit-tap-highlight-color:transparent;transition:transform .15s ease;line-height:0}',
      'a.sost-wsost-btn img{display:block;width:100%;height:100%;object-fit:contain;border-radius:50%;',
      'animation:wsostGlow 3.4s ease-in-out infinite}',
      '@keyframes wsostGlow{0%,100%{filter:drop-shadow(0 0 6px rgba(255,30,40,.55)) drop-shadow(0 0 14px rgba(255,30,40,.3))}',
      '50%{filter:drop-shadow(0 0 16px rgba(255,30,40,.95)) drop-shadow(0 0 34px rgba(255,30,40,.55)) drop-shadow(0 0 4px rgba(255,209,102,.5))}}',
      'a.sost-wsost-btn:hover{transform:translateY(-1px) scale(1.03)}',
      'a.sost-wsost-btn:focus-visible{outline:2px solid #ffd166;outline-offset:3px}',
      '@media(prefers-reduced-motion:reduce){a.sost-wsost-btn img{animation:none;filter:drop-shadow(0 0 12px rgba(255,30,40,.8))}}',
      'body.nav-collapsed nav a.sost-wsost-btn{display:none !important}'
    ].join('');
    (document.head||document.documentElement).appendChild(st);
  }
  function inject(){
    var nav=document.querySelector('nav'); if(!nav) return;
    if(nav.querySelector('a.sost-wsost-btn')) return;
    var ax=nav.querySelector('a.atomix-btn')||nav.querySelector('a[style*="asBtnGlow"]')||nav.querySelector('a[href="sost-dex.html"]');
    if(!ax) return;                                         // no large-button row on this page
    styleOnce();
    var sz=ax.offsetWidth; if(!sz||sz<60) sz=110;
    sz=window.__sostModSize(nav, sz);
    sz=Math.round(sz*1.2*0.93*1.02);                        // +20%, -7%, then +2% vs the sibling modules (owner requests)
    var a=document.createElement('a');
    a.href='sost-wsost-gold-vault.html'; a.className='sost-wsost-btn';
    a.title='wSOST & Gold Vault — bridge, Gold Reserve V2 and governance (research roadmap, not live)';
    a.setAttribute('aria-label','wSOST & Gold Vault');
    a.style.width=sz+'px'; a.style.height=sz+'px'; a.style.minWidth=sz+'px';
    var pic=document.createElement('picture');
    pic.innerHTML='<source srcset="'+IMG+'" type="image/webp">';
    var img=document.createElement('img'); img.src=IMG_PNG; img.alt='wSOST & Gold Vault'; img.width=sz; img.height=sz;
    pic.appendChild(img); a.appendChild(pic);
    pic.style.cssText='display:block;width:100%;height:100%';
    // Before NEWS & UPDATES (or its square wrapper); otherwise right after ATOMIC SWAP DEX.
    var news=nav.querySelector('.sost-news-btn')||nav.querySelector('a[href="news.html"]');
    var newsBox=news&&news.parentElement&&news.parentElement.classList.contains('sq-wrap')?news.parentElement:news;
    var axBox=ax.parentElement&&ax.parentElement.classList.contains('sq-wrap')?ax.parentElement:ax;
    if(newsBox&&newsBox.parentNode===axBox.parentNode) newsBox.parentNode.insertBefore(a,newsBox);
    else axBox.parentNode.insertBefore(a,axBox.nextSibling);
  }
  function run(){ inject(); }
  window.__sostNavReady(run);
  window.__sostNavReady(function(){ setTimeout(run,0); setTimeout(run,450); setTimeout(run,1300); });
})();


/* ============================================================================
   "CLICK HERE TO OPEN EXPLORER" — red callout beside the main SOST logo.
   Same pattern and timing as the Explorer's jackpot hint (visible 15 s, hidden 15 s,
   1.6 s soft pulse), in SOST red. A real <a> to the Explorer. Only on pages whose main
   logo already opens the Explorer (the Explorer itself keeps its HOME logo, no callout).
   It floats over the bar and reserves NO room: the nav geometry must stay identical to the
   Explorer's. It points LEFT at the logo and sits in the free space after the wordmark. It never
   covers the logo or the wordmark: below 769px (the nav's own mobile breakpoint) it is not shown
   at all, and at any wider width where that free space is too narrow it is hidden too.
   ========================================================================== */
(function(){
  "use strict";
  if(/sost-explorer\.html$/.test(location.pathname)) return;
  function styleOnce(){
    if(document.getElementById('sost-xp-callout-style')) return;
    var st=document.createElement('style'); st.id='sost-xp-callout-style';
    st.textContent=[
      'nav.has-xp-callout .container{position:relative}',
      'a.sost-xp-callout{--xp:#fb010d;position:absolute;z-index:60;display:flex;align-items:center;box-sizing:border-box;',
      'background:linear-gradient(135deg,rgba(8,6,8,.97),rgba(26,2,4,.97));border:1px solid var(--xp);border-radius:9px;',
      'padding:8px 13px;white-space:nowrap;font:600 14px/1.3 var(--font-mono,ui-monospace,monospace);color:#ff5c63;',
      'letter-spacing:.4px;text-decoration:none;opacity:0;pointer-events:none;transition:opacity .35s ease;',
      'animation:xpRedPulse 1.6s ease-in-out infinite}',
      'a.sost-xp-callout.show,a.sost-xp-callout:focus-visible{opacity:1;pointer-events:auto}',
      'a.sost-xp-callout:focus-visible{outline:2px solid #ffd6d8;outline-offset:3px}',
      'a.sost-xp-callout::after{content:"";position:absolute;right:100%;top:50%;transform:translateY(-50%);',
      'border:8px solid transparent;border-right-color:var(--xp)}',
      'a.sost-xp-callout .xp-hand{display:inline-block;margin-right:8px;transform:rotate(-90deg);animation:xpBob 1s ease-in-out infinite}',
      '@keyframes xpBob{0%,100%{transform:rotate(-90deg) translateY(0)}50%{transform:rotate(-90deg) translateY(-3px)}}',
      '@keyframes xpRedPulse{0%,100%{box-shadow:0 0 8px rgba(251,1,13,.35),0 0 16px rgba(251,1,13,.15)}',
      '50%{box-shadow:0 0 16px rgba(251,1,13,.75),0 0 32px rgba(251,1,13,.35)}}',
      '@media (prefers-reduced-motion:reduce){a.sost-xp-callout,a.sost-xp-callout .xp-hand{animation:none}}',
      '@media (max-width:768px){a.sost-xp-callout{display:none !important}}',
      'a.sost-xp-callout.xp-noroom{display:none !important}',
      'body.nav-collapsed nav a.sost-xp-callout{display:none !important}'
    ].join('');
    (document.head||document.documentElement).appendChild(st);
  }
  var el=null, img=null, box=null, logo=null, nav=null;
  function place(){
    if(!el||!img||!box||!logo) return;
    el.classList.remove('xp-noroom');
    var b=box.getBoundingClientRect(), i=img.getBoundingClientRect();
    if(!i.width) return;
    var w=el.offsetWidth, h=el.offsetHeight, ARROW=8, PAD=10;
    var vw=document.documentElement.clientWidth;
    // Free space after the wordmark: up to the next element on the logo's row, or the bar's edge.
    var word=logo.querySelector('span'), wr=word?word.getBoundingClientRect():i;
    var limit=Math.min(vw-8, b.right);
    for(var n=logo.nextElementSibling;n;n=n.nextElementSibling){
      if(n===el) continue;
      var r=n.getBoundingClientRect();
      if(!r.width||!r.height) continue;
      if(r.top<i.bottom&&r.bottom>i.top&&r.left>=wr.right){ limit=Math.min(limit,r.left); break; }
    }
    // Measure with the no-room class off (display:none has no size), then decide.
    var room=(wr.right+ARROW+PAD+w<=limit-PAD);
    el.classList.toggle('xp-noroom',!room);
    if(!room) return;
    var left=wr.right+ARROW+PAD;
    el.style.left=(left-b.left)+'px';
    el.style.top=(i.top+i.height/2-h/2-b.top)+'px';
  }
  function inject(){
    nav=document.querySelector('nav'); if(!nav||nav.querySelector('a.sost-xp-callout')) return;
    logo=nav.querySelector('a.nav-logo[href$="sost-explorer.html"]'); if(!logo) return;
    img=logo.querySelector('img'); if(!img) return;
    box=logo.parentNode;
    styleOnce();
    nav.classList.add('has-xp-callout');
    el=document.createElement('a');
    el.href='https://sostcore.com/sost-explorer.html';
    el.className='sost-xp-callout';
    el.setAttribute('aria-label','Open SOST Explorer');
    el.innerHTML='<span class="xp-hand" aria-hidden="true">&#128070;</span><span>CLICK HERE TO<br>OPEN EXPLORER</span>';
    box.appendChild(el);
    place();
    window.addEventListener('resize',place);
    if(img.complete===false) img.addEventListener('load',place);
    setTimeout(place,400); setTimeout(place,1500);
    if(document.fonts&&document.fonts.ready) document.fonts.ready.then(place);
    function show(){ place(); el.classList.add('show'); setTimeout(hide,15000); }
    function hide(){ el.classList.remove('show'); setTimeout(show,15000); }
    show();
  }
  window.__sostNavReady(inject);
  window.__sostNavReady(function(){ setTimeout(inject,500); });
})();

/* ============================================================================
   Mobile menu: keep the open hamburger menu inside the viewport.
   The nav is position:sticky; with the menu open on a phone it is ~1100px tall,
   so once it sticks its lower links (Contact, the last row) sit below the screen
   and can never be reached. While the menu is open (and only at the mobile
   breakpoint) the nav is capped to the visible height below its own top edge
   and scrolls internally. Desktop and the closed menu are untouched; page
   scrolling keeps working (inner scroll chains to the page at its ends).
   ========================================================================== */
(function(){
  "use strict";
  if(window.__sostNavMenuScroll) return;
  window.__sostNavMenuScroll = true;
  var st=document.createElement('style'); st.id='sost-nav-menu-scroll-style';
  st.textContent='@media (max-width:768px){nav.sost-menu-open{max-height:calc(100vh - var(--sost-nav-top,0px));'+
    'max-height:calc(100dvh - var(--sost-nav-top,0px));overflow-y:auto;-webkit-overflow-scrolling:touch}}';
  (document.head||document.documentElement).appendChild(st);
  var nav=null, raf=0;
  function findNav(){
    var nl=document.querySelector('nav .nav-links');
    return nl ? nl.closest('nav') : null;
  }
  function place(){
    raf=0;
    if(!nav || !nav.classList.contains('sost-menu-open')) return;
    var t=Math.max(0, Math.round(nav.getBoundingClientRect().top));
    nav.style.setProperty('--sost-nav-top', t+'px');
  }
  function sync(){
    if(!nav || !document.contains(nav)) nav=findNav();
    if(!nav) return;
    var nl=nav.querySelector('.nav-links');
    var on=!!(nl && nl.classList.contains('open'));
    if(on===nav.classList.contains('sost-menu-open')){ if(on) place(); return; }
    nav.classList.toggle('sost-menu-open', on);
    if(on) place(); else { nav.style.removeProperty('--sost-nav-top'); nav.scrollTop=0; }
  }
  function onScroll(){ if(nav && !raf && nav.classList.contains('sost-menu-open')) raf=requestAnimationFrame(place); }
  function init(){
    nav=findNav();
    if(!nav) return;
    try{ new MutationObserver(sync).observe(nav,{attributes:true,attributeFilter:['class'],subtree:true}); }catch(e){}
    window.addEventListener('scroll',onScroll,{passive:true});
    window.addEventListener('resize',onScroll,{passive:true});
    sync();
  }
  window.__sostNavReady(init);
})();

/* ============================================================================
   SOST nav "Contact" -> floating image -> contact form.
   A plain left click on the nav's Contact item shows the contact emblem
   (media/sost-contact-email.png) floating over the page. A click on the emblem
   (or Enter / Space) turns it, with a short fade, into a small contact form
   in the same dialog. Sending is gated by CONTACT_SEND_ENABLED below: while it
   is false the SEND button is disabled, a "not active yet" note is shown and
   NOTHING is posted anywhere. Once the /api/contact service (ops/sost-contact-
   api.py, deploy/contact/) is installed and its SMTP config tested, set it to
   true and the form posts JSON to that same-origin endpoint. The destination
   inbox exists ONLY in the server config: nothing in this file, the page or
   the response names it.
   The emblem PNG has a 1-2px light antialiased fringe baked into the edge of
   its black circle, which showed as a thin grey ring over the dim backdrop. It
   is hidden with a circular clip-path just inside that fringe (the image file
   itself is left untouched).
   Progressive enhancement: the link keeps href="sost-contact.html", so no-JS,
   middle-click, ctrl/cmd/shift-click and "open in new tab" still go to the page.
   Only links inside <nav> whose text is "Contact" are intercepted.
   Closes on Escape and on a click outside the emblem / form. One overlay per page
   (built on first use, reused after). Focus moves into the dialog, stays trapped
   there while open and returns to the link on close.
   ========================================================================== */
(function(){
  "use strict";
  if(window.__sostContactFloat) return;
  window.__sostContactFloat = true;
  // ONE switch for sending. true since the /api/contact service went live with the STRATO
  // SMTP config (deploy/contact/README.md). Set false to fall back to the disabled form.
  var CONTACT_SEND_ENABLED = true;
  var ENDPOINT='/api/contact';
  var LIM={name:100,email:254,subject:200,message:5000};
  var T_OK='YOUR MESSAGE HAS BEEN SENT.';
  var T_FAIL='UNABLE TO SEND THE MESSAGE. PLEASE TRY AGAIN LATER.';
  var T_REQ='Please fill in the required fields.';
  var T_EMAIL='Please enter a valid email address.';
  var T_OFF='Sending is not active yet \u2014 coming soon.';
  var ov=null, img=null, panel=null, form=null, statusEl=null, btn=null, done=null, back=null;
  var opener=null, isOpen=false, hideTimer=null, view='image', sending=false, sent=false, idem='';
  var downOnBackdrop=false;
  // Resolve the image next to this script (js/../media/), so it works from any page path.
  var BASE='media/';
  try{ var cs=document.currentScript; if(cs && cs.src) BASE=new URL('../media/', cs.src).href; }catch(e){}
  var SRC=BASE+'sost-contact-email.png', SRC512=BASE+'sost-contact-email-512.png';
  function reduced(){ try{ return window.matchMedia('(prefers-reduced-motion: reduce)').matches; }catch(e){ return false; } }
  function styleOnce(){
    if(document.getElementById('sost-contact-float-style')) return;
    var st=document.createElement('style'); st.id='sost-contact-float-style';
    var P='#sost-contact-ov ';
    st.textContent=[
      '#sost-contact-ov{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;',
      'box-sizing:border-box;padding:4vh 5vw 10vh;background:rgba(0,0,0,.45);opacity:0;transition:opacity .18s ease;',
      'cursor:pointer;-webkit-tap-highlight-color:transparent;outline:none;touch-action:none;overscroll-behavior:contain}',
      '#sost-contact-ov[hidden]{display:none}',
      '#sost-contact-ov.open{opacity:1}',
      '#sost-contact-ov:not(.open){pointer-events:none}',
      '#sost-contact-ov > img{display:block;width:min(420px,90vw,80vh);height:auto;max-width:90vw;max-height:85vh;',
      'object-fit:contain;transform:scale(.96);transition:transform .18s ease;-webkit-user-drag:none;user-select:none;',
      // Hide the light fringe baked into the PNG's circle edge (outer ~0.5% of the radius).
      '-webkit-clip-path:circle(49.4% at 50% 50%);clip-path:circle(49.4% at 50% 50%);border:0;outline:0;box-shadow:none;background:transparent}',
      '#sost-contact-ov.open > img{transform:scale(1)}',
      '#sost-contact-ov.form{padding:16px;background:rgba(0,0,0,.72);touch-action:auto}',
      '#sost-contact-ov.form > img{display:none}',
      // Centred on the overlay by default; placePanel() then re-centres and re-sizes it on the
      // VISUAL viewport (see there). Fixed, so it does not depend on the overlay's box.
      P+'.scf-panel{display:none;position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);box-sizing:border-box;',
      'width:min(460px,calc(100% - 32px));max-height:calc(100vh - 32px);max-height:calc(100dvh - 32px);',
      'overflow-y:auto;overscroll-behavior:contain;cursor:auto;text-align:left;color:#f1f1f1;background:linear-gradient(160deg,#0b0b0d,#120507);',
      'border:1px solid rgba(251,1,13,.55);border-radius:14px;box-shadow:0 0 34px rgba(251,1,13,.22),0 18px 60px rgba(0,0,0,.6);',
      'padding:22px 22px 20px;font-family:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace;font-size:13px;line-height:1.5;-webkit-tap-highlight-color:initial}',
      '#sost-contact-ov.form .scf-panel{display:block;animation:scf-in .22s ease both}',
      '@keyframes scf-in{from{opacity:0;transform:translate(-50%,-50%) scale(.94)}to{opacity:1;transform:translate(-50%,-50%) scale(1)}}',
      P+'.scf-h{margin:0 120px 16px 0;font-size:15px;font-weight:700;letter-spacing:2px;color:#fff;text-transform:uppercase}',
      P+'.scf-h b{color:#fb010d;font-weight:700}',
      P+'.scf-x{position:absolute;top:12px;right:12px;width:32px;height:32px;display:flex;align-items:center;justify-content:center;',
      'background:transparent;border:1px solid rgba(255,255,255,.18);border-radius:10px;color:#ddd;font:20px/1 sans-serif;cursor:pointer;padding:0}',
      P+'.scf-x:hover,'+P+'.scf-x:focus-visible{border-color:#fb010d;color:#fff;outline:none}',
      P+'.scf-f{display:block;margin:0 0 12px}',
      P+'.scf-f label{display:block;margin:0 0 5px;font-size:11px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:#cfcfcf}',
      P+'.scf-f label span{font-weight:400;letter-spacing:.5px;text-transform:none;color:#8b8b8b}',
      P+'.scf-f input,'+P+'.scf-f textarea{display:block;box-sizing:border-box;width:100%;margin:0;padding:10px 12px;font:16px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;',
      'color:#fff;background:#0a0a0a;border:1px solid #3a3a3a;border-radius:8px;outline:none;-webkit-appearance:none;appearance:none}',
      P+'.scf-f textarea{min-height:120px;resize:vertical}',
      P+'.scf-f input:focus,'+P+'.scf-f textarea:focus{border-color:#fb010d;box-shadow:0 0 0 2px rgba(251,1,13,.25)}',
      P+'.scf-f [aria-invalid="true"]{border-color:#ff5a5f}',
      P+'.scf-hp{position:absolute!important;left:-10000px!important;top:auto!important;width:1px!important;height:1px!important;overflow:hidden!important}',
      P+'.scf-st{min-height:1.5em;margin:2px 0 12px;font-size:12.5px;color:#ff8a8d}',
      P+'.scf-st.ok{color:#7ee2a8}',
      P+'.scf-b{display:block;width:100%;padding:12px 14px;font:700 13px/1 "JetBrains Mono",ui-monospace,monospace;letter-spacing:2px;color:#fff;cursor:pointer;',
      'background:linear-gradient(135deg,#fb010d,#a8000a);border:1px solid rgba(255,120,120,.6);border-radius:10px;box-shadow:0 0 16px rgba(251,1,13,.35)}',
      P+'.scf-b:hover{filter:brightness(1.1)}',
      P+'.scf-b:focus-visible{outline:2px solid #fff;outline-offset:2px}',
      P+'.scf-b[disabled]{opacity:.6;cursor:progress;filter:none}',
      P+'.scf-b.off[disabled]{opacity:.45;cursor:not-allowed;box-shadow:none;background:#3a3a3a;border-color:#555}',
      P+'.scf-off{margin:0 0 12px;padding:9px 11px;font-size:12.5px;color:#f5c889;background:rgba(245,200,137,.08);border:1px solid rgba(245,200,137,.35);border-radius:8px}',
      P+'.scf-back{position:absolute;top:12px;right:52px;height:32px;display:flex;align-items:center;padding:0 10px;background:transparent;',
      'border:1px solid rgba(255,255,255,.18);border-radius:10px;color:#ddd;font:700 11px/1 "JetBrains Mono",ui-monospace,monospace;letter-spacing:1px;cursor:pointer}',
      P+'.scf-back:hover,'+P+'.scf-back:focus-visible{border-color:#fb010d;color:#fff;outline:none}',
      P+'.scf-done{display:none;text-align:center;padding:18px 0 6px}',
      P+'.scf-done p{margin:0 0 18px;font-size:15px;color:#7ee2a8}',
      '#sost-contact-ov.sent .scf-form{display:none}',
      '#sost-contact-ov.sent .scf-done{display:block}',
      '@media (prefers-reduced-motion:reduce){#sost-contact-ov,#sost-contact-ov > img{transition:none;transform:none}#sost-contact-ov .scf-panel{animation:none!important}}'
    ].join('');
    (document.head||document.documentElement).appendChild(st);
  }
  function el(tag, attrs, text){
    var e=document.createElement(tag);
    if(attrs) for(var k in attrs){ if(Object.prototype.hasOwnProperty.call(attrs,k)) e.setAttribute(k,attrs[k]); }
    if(text!=null) e.textContent=text;
    return e;
  }
  function fieldRow(id, label, hint, ctl){
    var row=el('div',{'class':'scf-f'});
    var lb=el('label',{'for':id}, label);
    if(hint){ lb.appendChild(document.createTextNode(' ')); lb.appendChild(el('span',null,hint)); }
    row.appendChild(lb); row.appendChild(ctl);
    return row;
  }
  function buildPanel(){
    panel=el('div',{'class':'scf-panel'});
    var h=el('h2',{'class':'scf-h',id:'scf-title'}); h.appendChild(document.createTextNode('Contact ')); h.appendChild(el('b',null,'SOST'));
    var x=el('button',{type:'button','class':'scf-x','aria-label':'Close'},'×');
    x.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); close(); });
    back=el('button',{type:'button','class':'scf-back','aria-label':'Back to the contact emblem'},'\u2190 BACK');
    back.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); showImage(); });
    form=el('form',{'class':'scf-form',novalidate:'',autocomplete:'on','aria-labelledby':'scf-title'});
    form.appendChild(fieldRow('scf-name','Name','(optional)',el('input',{id:'scf-name',name:'name',type:'text',maxlength:String(LIM.name),autocomplete:'name'})));
    form.appendChild(fieldRow('scf-email','Email','(required)',el('input',{id:'scf-email',name:'email',type:'email',required:'',maxlength:String(LIM.email),autocomplete:'email',inputmode:'email',spellcheck:'false'})));
    form.appendChild(fieldRow('scf-subject','Subject','(required)',el('input',{id:'scf-subject',name:'subject',type:'text',required:'',maxlength:String(LIM.subject)})));
    form.appendChild(fieldRow('scf-message','Message','(required)',el('textarea',{id:'scf-message',name:'message',required:'',maxlength:String(LIM.message),rows:'6'})));
    // Honeypot: invisible to people (and to assistive tech), tempting to form-filling bots.
    var hp=el('div',{'class':'scf-hp','aria-hidden':'true'});
    hp.appendChild(el('label',{'for':'scf-website'},'Leave this field empty'));
    hp.appendChild(el('input',{id:'scf-website',name:'website',type:'text',tabindex:'-1',autocomplete:'off'}));
    form.appendChild(hp);
    statusEl=el('p',{'class':'scf-st',role:'status','aria-live':'polite'});
    form.appendChild(statusEl);
    btn=el('button',{type:'submit','class':'scf-b'},'SEND MESSAGE');
    if(!CONTACT_SEND_ENABLED){
      form.appendChild(el('p',{'class':'scf-off',id:'scf-off'},T_OFF));
      btn.disabled=true; btn.className='scf-b off';
      btn.setAttribute('aria-describedby','scf-off');
    }
    form.appendChild(btn);
    form.addEventListener('submit',onSubmit);
    form.addEventListener('input',function(e){ if(e.target && e.target.getAttribute('aria-invalid')) e.target.removeAttribute('aria-invalid'); });
    done=el('div',{'class':'scf-done',role:'status'});
    done.appendChild(el('p',null,T_OK));
    var cb=el('button',{type:'button','class':'scf-b'},'CLOSE');
    cb.addEventListener('click',function(e){ e.preventDefault(); close(); });
    done.appendChild(cb);
    panel.appendChild(h); panel.appendChild(back); panel.appendChild(x); panel.appendChild(form); panel.appendChild(done);
    return panel;
  }
  function build(){
    if(ov) return ov;
    styleOnce();
    ov=document.createElement('div');
    ov.id='sost-contact-ov';
    ov.setAttribute('role','dialog');
    ov.setAttribute('aria-modal','true');
    ov.setAttribute('aria-label','Contact');
    ov.tabIndex=-1;
    ov.hidden=true;
    img=document.createElement('img');
    img.src=SRC;
    img.srcset=SRC512+' 512w, '+SRC+' 980w';
    img.sizes='min(420px, 90vw, 80vh)';
    img.width=980; img.height=980;
    img.alt='SOST contact. Select to open the contact form';
    img.decoding='async';
    img.draggable=false;
    ov.appendChild(img);
    ov.appendChild(buildPanel());
    // Emblem click -> form. A click whose press AND release are both on the backdrop closes.
    // (A text selection dragged out of a field must not close the form and lose the draft.)
    ov.addEventListener('pointerdown',function(e){ downOnBackdrop=(e.target===ov); });
    ov.addEventListener('click',function(e){
      if(e.target===img){ e.preventDefault(); showForm(); return; }
      if(e.target===ov){ e.preventDefault(); if(downOnBackdrop || view==='image') close(); }
      downOnBackdrop=false;
    });
    ov.addEventListener('wheel',swallow,{passive:false});
    ov.addEventListener('touchmove',swallow,{passive:false});
    document.body.appendChild(ov);
    return ov;
  }
  // Scroll lock WITHOUT touching overflow: changing html/body overflow re-lays out pages whose
  // content is wider than a phone viewport (the nav re-wraps behind the backdrop) and on desktop
  // removes the scrollbar. Instead the overlay swallows wheel/touch scrolling and the keydown
  // handler swallows the scroll keys, so nothing behind the overlay moves or re-flows. Inside
  // the form, scrolling is allowed only where something can actually scroll (panel/textarea).
  function canScroll(t){
    for(var n=t; n && n!==ov; n=n.parentNode){
      if(n.nodeType===1 && n.scrollHeight>n.clientHeight+1){
        var oy=getComputedStyle(n).overflowY;
        if(oy==='auto'||oy==='scroll') return true;
      }
    }
    return false;
  }
  function swallow(e){
    if(!isOpen || !e.cancelable) return;
    if(view==='form' && panel.contains(e.target) && canScroll(e.target)) return;
    e.preventDefault();
  }
  // On phones the area the visitor actually sees (the visual viewport) can differ from the
  // layout viewport the fixed overlay follows: pages wider than the screen, pinch zoom, and
  // above all the on-screen keyboard, which shrinks only the visual viewport. Keep the form
  // centred in, and no taller/wider than, what is visible; it scrolls inside if needed.
  function placePanel(){
    if(!isOpen || view!=='form' || !panel) return;
    var v=window.visualViewport;
    if(!v || !(v.width>0) || !(v.height>0)) return;
    panel.style.left=(v.offsetLeft+v.width/2)+'px';
    panel.style.top=(v.offsetTop+v.height/2)+'px';
    panel.style.width=Math.max(200,Math.min(460,v.width-32))+'px';
    panel.style.maxHeight=Math.max(160,v.height-32)+'px';
  }
  try{ if(window.visualViewport){ visualViewport.addEventListener('resize',placePanel); visualViewport.addEventListener('scroll',placePanel); } }catch(e){}
  function newKey(){
    try{ if(window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g,''); }catch(e){}
    try{ var a=new Uint8Array(16); crypto.getRandomValues(a); return Array.prototype.map.call(a,function(b){return ('0'+b.toString(16)).slice(-2);}).join(''); }catch(e){}
    return String(Date.now())+String(Math.random()).slice(2,12);
  }
  function focusables(){
    var root=(view==='form') ? panel : ov;
    return Array.prototype.filter.call(root.querySelectorAll('button,input,textarea,a[href],[tabindex]:not([tabindex="-1"])'),function(n){
      return !n.disabled && n.tabIndex>=0 && n.getClientRects().length>0;
    });
  }
  function focusEl(n){ try{ n.focus({preventScroll:true}); }catch(e){ n.focus(); } }
  function showForm(){
    if(!isOpen) return;
    if(sent) resetForm();
    view='form';
    ov.classList.add('form');
    panel.scrollTop=0;
    placePanel();
    if(!idem) idem=newKey();
    var f=focusables(); focusEl(f.length ? f.filter(function(n){return n.tagName==='INPUT';})[0]||f[0] : ov);
  }
  function showImage(){
    if(!isOpen) return;
    view='image';
    ov.classList.remove('form');
    focusEl(ov);
  }
  function resetForm(){
    sent=false; idem='';
    ov.classList.remove('sent');
    form.reset();
    statusEl.textContent=''; statusEl.className='scf-st';
    Array.prototype.forEach.call(form.querySelectorAll('[aria-invalid]'),function(n){ n.removeAttribute('aria-invalid'); });
  }
  var EMAIL_RE=/^[A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]+)*@([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/;
  function setStatus(t, ok){ statusEl.textContent=t; statusEl.className='scf-st'+(ok?' ok':''); }
  function invalid(n, msg){
    n.setAttribute('aria-invalid','true');
    setStatus(msg,false);
    focusEl(n);
    return false;
  }
  function validate(){
    var E=form.elements;
    Array.prototype.forEach.call(form.querySelectorAll('[aria-invalid]'),function(n){ n.removeAttribute('aria-invalid'); });
    var req=[E.email,E.subject,E.message];
    for(var i=0;i<req.length;i++){ if(!req[i].value.trim()) return invalid(req[i],T_REQ); }
    var em=E.email.value.trim(), local=em.split('@')[0];
    if(em.length>LIM.email || local.length>64 || !EMAIL_RE.test(em)) return invalid(E.email,T_EMAIL);
    if(E.name.value.trim().length>LIM.name) return invalid(E.name,T_REQ);
    if(E.subject.value.trim().length>LIM.subject) return invalid(E.subject,T_REQ);
    if(E.message.value.trim().length>LIM.message) return invalid(E.message,T_REQ);
    return true;
  }
  function onSubmit(e){
    e.preventDefault();
    if(!CONTACT_SEND_ENABLED) return;    // sending not active: never post, never pretend it was sent
    if(sending || sent) return;          // the button is disabled too; this guards Enter-key repeats
    if(!validate()) return;
    var E=form.elements;
    var payload={
      name:E.name.value.trim(), email:E.email.value.trim(), subject:E.subject.value.trim(),
      message:E.message.value.trim(), website:E.website.value, idempotency_key:idem||(idem=newKey())
    };
    sending=true; btn.disabled=true; btn.textContent='SENDING…'; form.setAttribute('aria-busy','true');
    setStatus('',false);
    var ctrl=null, timer=null;
    try{ ctrl=new AbortController(); timer=setTimeout(function(){ try{ctrl.abort();}catch(x){} },30000); }catch(x){}
    var finish=function(ok, msg){
      if(timer) clearTimeout(timer);
      sending=false; form.removeAttribute('aria-busy'); btn.textContent='SEND MESSAGE';
      if(ok){
        sent=true; ov.classList.add('sent');
        var c=done.querySelector('button'); if(c && isOpen) focusEl(c);
      }else{
        btn.disabled=false;
        setStatus(msg||T_FAIL,false);
      }
    };
    fetch(ENDPOINT,{method:'POST',credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json','Accept':'application/json'},
      body:JSON.stringify(payload), signal:ctrl?ctrl.signal:undefined})
      .then(function(r){ return r.json().catch(function(){ return {}; }).then(function(j){ return {status:r.status,j:j||{}}; }); })
      .then(function(res){
        if(res.status===200 && res.j.ok===true) return finish(true);
        if(res.status===400 && res.j.field==='email'){ finish(false,T_EMAIL); E.email.setAttribute('aria-invalid','true'); return; }
        finish(false,T_FAIL);
      })
      .catch(function(){ finish(false,T_FAIL); });
  }
  function open(link){
    if(isOpen) return;              // single instance: a second click never stacks overlays
    build();
    if(hideTimer){ clearTimeout(hideTimer); hideTimer=null; }
    isOpen=true; opener=link||null;
    view='image'; ov.classList.remove('form');
    ov.hidden=false;
    void ov.offsetWidth;            // commit the hidden->shown frame so the fade runs
    ov.classList.add('open');
    focusEl(ov);
  }
  function close(){
    if(!isOpen) return;
    isOpen=false;
    ov.classList.remove('open');
    var done_=function(){
      hideTimer=null;
      if(!isOpen){ ov.hidden=true; ov.classList.remove('form'); view='image'; if(sent && !sending) resetForm(); }
    };
    if(reduced()) done_(); else hideTimer=setTimeout(done_,200);
    var o=opener; opener=null;
    if(o && document.contains(o)) focusEl(o);
  }
  var SCROLL_KEYS={' ':1,'Spacebar':1,'PageUp':1,'PageDown':1,'Home':1,'End':1,'ArrowUp':1,'ArrowDown':1,'ArrowLeft':1,'ArrowRight':1};
  function navContactLink(t){
    var a=t && t.closest ? t.closest('a[href]') : null;
    if(!a || !a.closest('nav')) return null;
    var h=(a.getAttribute('href')||'').trim();
    if(!/(^|\/)sost-contact\.html(?:[?#].*)?$/i.test(h)) return null;
    if((a.textContent||'').replace(/\s+/g,' ').trim().toLowerCase()!=='contact') return null;
    return a;
  }
  // Capture phase + stopImmediatePropagation: crt-effects.js binds its page-transition
  // handler directly on every nav <a>. Since the nav is built during parsing (C706) those
  // handlers sit on the final Contact link and would navigate to sost-contact.html before a
  // bubbling document listener ever ran. Capturing on document runs first and stops them.
  document.addEventListener('click',function(e){
    if(e.defaultPrevented || e.button!==0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    var a=navContactLink(e.target);
    if(!a) return;
    var tgt=(a.getAttribute('target')||'').toLowerCase();
    if(tgt && tgt!=='_self') return;
    e.preventDefault();
    e.stopImmediatePropagation();
    open(a);
  },true);
  document.addEventListener('keydown',function(e){
    if(!isOpen) return;
    if(e.key==='Escape' || e.key==='Esc'){ e.preventDefault(); e.stopPropagation(); close(); return; }
    if(view==='image' && (e.key==='Enter' || e.key===' ' || e.key==='Spacebar')){ e.preventDefault(); showForm(); return; }
    if(e.key==='Tab'){
      var f=focusables();
      if(!f.length){ e.preventDefault(); focusEl(ov); return; }
      var i=f.indexOf(document.activeElement);
      if(e.shiftKey && i<=0){ e.preventDefault(); focusEl(f[f.length-1]); }
      else if(!e.shiftKey && (i===-1 || i===f.length-1)){ e.preventDefault(); focusEl(f[0]); }
      return;
    }
    // Keys typed into the form keep their normal meaning (space, arrows, Home/End...).
    if(view==='form' && panel.contains(e.target)) return;
    if(SCROLL_KEYS[e.key]) e.preventDefault();
  },true);
  document.addEventListener('focusin',function(e){
    if(isOpen && ov && !ov.contains(e.target)){ var f=focusables(); focusEl(f[0]||ov); }
  });
  // Build the (hidden) overlay as soon as the pointer or focus reaches the nav Contact link,
  // so the browser fetches the right srcset candidate before the click.
  function warm(e){ if(navContactLink(e.target)){ build(); document.removeEventListener('mouseover',warm); document.removeEventListener('focusin',warm); document.removeEventListener('touchstart',warm); } }
  document.addEventListener('mouseover',warm);
  document.addEventListener('focusin',warm);
  document.addEventListener('touchstart',warm,{passive:true});
})();

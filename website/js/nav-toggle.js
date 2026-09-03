/* SOST shared top-nav toggle.
   Auto-injects a pulsing red/gold "HIDE NAV / SHOW NAV" button into
   every page that has a <nav> element, and wires up a sessionStorage-
   backed collapsed state shared across pages.
   Compatible with the existing index.html implementation: when a button
   with id="navToggleBtn" already exists, the script only attaches its
   visual styling and lets the in-page handler do the toggling. */
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
      "  animation: sostNavPulse 2.4s ease-in-out infinite;",
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
      /* SOST PROTOCOL nav text identical on every page (some pages used a
      "   smaller 18px override — force the standard size everywhere). */
      "nav .nav-logo { font-size: 26px !important; letter-spacing: 3px !important; gap: 14px !important; }",
      /* The ONLY pulsing logo on the whole site: the SOST mark — min->max glow. */
      "nav .nav-logo img { animation: sostLogoPulse 3.6s ease-in-out infinite; }",
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
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
      <a href="sost-ai-engine.html" style="color:#22d3ee">AI Engine</a>
      <a href="sost-materials-engine.html">Materials Engine</a>
      <a href="sost-trinity.html" style="color:#d946ef">Trinity</a>
      <a href="sost-transactions.html">Transactions</a>
      <a href="sost-gold-reserve.html">Metals Reserve</a>
      <a href="sost-reference.html" style="color:#e3b23c">SOST Price Reference</a>
      <a href="sost-popc.html">PoPC</a>
      <a href="sost-tokenomics.html">Tokenomics</a>
      <a href="sost-roadmap.html">Roadmap</a>
      <a href="sost-protocol-spec.html">SOST Spec</a>
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
      <a href="sost-e2e.html" style="color:var(--green-primary)">E2E Swap</a>
      <!-- DEX link replaced by rainbow button next to logo -->
      <a href="sost-gold-dex.html">DEX Spec</a>
      <a href="sost-security.html">Security</a>
      <a href="sost-faq.html">FAQ</a>
      <a href="beacon.html" style="color:#22d3ee">Beacon</a>
      <a href="sost-registry.html" style="color:#d946ef">SOST Registry</a>
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
  }
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", injectNav, {once:true});
  else injectNav();
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
      '  animation:sqPulse 2.2s ease-in-out infinite}',
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
    var watch=nav.querySelector('a[style*="asBtnGlow"]')||nav.querySelector('a[href="sost-dex.html"]')||nav.querySelector('a[href="atomic-swap-console.html"]')||nav.querySelector('a[onclick="openSv()"]');
    if(!watch) return;                                            // need the logo-button row
    var sz=watch.offsetWidth||110;                               // match the sibling box
    var a=document.createElement('a');
    a.href='news.html'; a.title='News & Updates';
    a.className='sost-news-btn';
    a.style.width=sz+'px'; a.style.height=sz+'px'; a.style.minWidth=sz+'px';
    var ic=Math.round(sz*0.30), tx=Math.max(9,Math.round(sz*0.115));
    a.innerHTML='<span style="font-size:'+ic+'px;line-height:1;margin-bottom:2px">📰</span>'
      +'<span style="color:#f59e0b;font-size:'+tx+'px;font-weight:900;letter-spacing:1px;text-shadow:0 0 8px rgba(245,158,11,.6)">NEWS</span>';
    watch.parentNode.insertBefore(a, watch.nextSibling);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',injectNewsBtn,{once:true});
  else injectNewsBtn();
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
      +'<button class="sv-card sv-card-sost" type="button" onclick="pickSv(\'sost-intro.mp4\',\'SOST in 2 Minutes &middot; V15\')">'
      +'<span class="sv-thumb" style="background-image:url(\'sost-intro-poster.jpg\')"><span class="sv-play">&#9654;</span></span>'
      +'<span class="sv-card-h">SOST in 2 Minutes</span><span class="sv-card-s">SOST &middot; V15</span></button>'
      +'<button class="sv-card sv-card-mech" type="button" onclick="pickSv(\'sost-mechanisms.mp4\',\'SOST Mechanisms &middot; Atomic Swap &amp; DTD\')">'
      +'<span class="sv-thumb" style="background-image:url(\'sost-mechanisms-poster.jpg\')"><span class="sv-play">&#9654;</span></span>'
      +'<span class="sv-card-h">SOST Mechanisms</span><span class="sv-card-s">Atomic Swap &amp; DTD &middot; how the two core mechanisms work</span></button>'
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
      'animation:dtdBtnGlow 2s ease-in-out infinite;overflow:hidden;',
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
    var anchor=nav.querySelector('a[style*="asBtnGlow"]')||nav.querySelector('a[href="sost-dex.html"]');
    if(!anchor) return;                       // no large-button row on this page
    styleOnce();
    var sz=anchor.offsetWidth||72;            // match the sibling box, whatever this page uses
    var a=document.createElement('a');
    a.href='index.html#dtd'; a.title='DTD — Deterministic Token Distribution';
    a.className='sost-dtd-btn';
    a.style.width=sz+'px'; a.style.height=sz+'px'; a.style.minWidth=sz+'px';
    var big=Math.max(16,Math.round(sz*0.28)), small=Math.max(6,Math.round(sz*0.09));
    a.innerHTML='<span style="color:#39ff14;font-size:'+big+'px;font-weight:900;letter-spacing:1px;'
      +'text-shadow:0 0 14px rgba(57,255,20,.85)">DTD</span>'
      +'<span style="color:#7CFFA0;font-size:'+small+'px;font-weight:700;letter-spacing:.4px;'
      +'text-align:center;margin-top:2px">TOKEN<br>DISTRIBUTION</span>';
    anchor.parentNode.insertBefore(a, anchor);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',injectDtdBtn,{once:true});
  else injectDtdBtn();
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
      box.style.cssText='display:inline-flex;width:'+(cx.offsetWidth||110)+'px;height:'
        +(cx.offsetHeight||110)+'px;flex:0 0 auto';
      cx.parentNode.insertBefore(box, cx); box.appendChild(cx);
      wrap(box,'cx');
    }
    nav.querySelectorAll('a[style*="dtdBtnGlow"],.sost-dtd-btn').forEach(function(e){ wrap(e,'dtd'); });
    nav.querySelectorAll('a[style*="asBtnGlow"]').forEach(function(e){ wrap(e,'as'); });
    nav.querySelectorAll('.sost-news-btn').forEach(function(e){ wrap(e,'news'); });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',tag,{once:true});
  else tag();
  setTimeout(tag,0); setTimeout(tag,400); setTimeout(tag,1200);
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

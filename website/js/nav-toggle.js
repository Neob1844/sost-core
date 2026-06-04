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
      "  border-radius: 6px;",
      "  cursor: pointer;",
      "  flex: 0 0 auto;",
      "  transition: transform .18s ease, color .18s ease, border-color .2s ease;",
      "  box-shadow: 0 0 8px rgba(251,1,13,0.42), 0 0 18px rgba(245,158,11,0.22);",
      "  text-shadow: 0 0 6px rgba(251,1,13,0.55);",
      "  animation: sostNavPulse 2.4s ease-in-out infinite;",
      "  -webkit-tap-highlight-color: transparent;",
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
      "body.nav-collapsed nav { padding: 4px 0 !important; }",
      "body.nav-collapsed nav .nav-logo,",
      "body.nav-collapsed nav .nav-links,",
      "body.nav-collapsed nav .nav-hamburger,",
      "body.nav-collapsed nav a[href=\"casert-spec.html\"],",
      "body.nav-collapsed nav a[href=\"sost-dex.html\"],",
      "body.nav-collapsed nav a[onclick=\"openSv()\"] {",
      "  display: none !important;",
      "}",
      "body.nav-collapsed nav .container {",
      "  justify-content: flex-end !important;",
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
         SOST logo + text stays left; ConvergenceX, GeaSpirit, PoPC DEX, Watch
         and News group together on the right (drop ConvergenceX's flex:1 grow
         and push the whole right group with margin-left:auto). */
      "nav .container > a[href=\"casert-spec.html\"] {",
      "  flex: 0 0 auto !important;",
      "  margin-left: auto !important;",
      "}",
      /* SOST PROTOCOL nav text identical on every page (the GeaSpirit page used",
      "   a smaller 18px override — force the standard size everywhere). */
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
            <a href="index.html">Home</a>
      <a href="sost-genesis.html">Genesis</a>
      <a href="sost-technology.html">Technology</a>
      <a href="sost-ai-engine.html" style="color:#22d3ee">AI Engine</a>
      <a href="sost-materials-engine.html">Materials Engine</a>
      <a href="sost-geaspirit.html" style="color:#00ff41">GeaSpirit</a>
      <a href="sost-trinity.html" style="color:#d946ef">Trinity</a>
      <a href="sost-transactions.html">Transactions</a>
      <a href="sost-gold-reserve.html">Metals Reserve</a>
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
    var watch=nav.querySelector('a[onclick="openSv()"]');
    if(!watch) return;                                            // need the logo-button row
    var sz=watch.offsetWidth||110;                               // match the sibling box
    var a=document.createElement('a');
    a.href='news.html'; a.title='News & Updates'; a.className='sost-news-btn';
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
   Every GeaSpirit logo on the site links out to geaspirit.com. Logos already
   wrapped in a single-purpose <a> get their href pointed there; bare logos are
   wrapped. Logos inside a larger composite link are left untouched.
   ========================================================================== */
(function(){
  "use strict";
  var GEA = "https://geaspirit.com/";
  function linkGeaLogos(){
    var imgs = document.querySelectorAll('img[src*="geaspirit-logo.png"], img[src*="geaspirit-logo.svg"]');
    for(var i=0;i<imgs.length;i++){
      var img = imgs[i];
      if(img.id === 'gea-splash-logo') continue;            // splash artwork, not a link
      var a = img.parentNode && img.parentNode.tagName === 'A' ? img.parentNode : null;
      if(a){
        if(a.children.length === 1){                        // link wraps only the logo
          a.setAttribute('href', GEA); a.setAttribute('target','_blank'); a.setAttribute('rel','noopener noreferrer');
        }
        continue;
      }
      var w = document.createElement('a');
      w.href = GEA; w.target = '_blank'; w.rel = 'noopener noreferrer';
      w.style.display = 'inline-flex'; w.style.cursor = 'pointer'; w.title = 'GeaSpirit — geaspirit.com';
      img.parentNode.insertBefore(w, img); w.appendChild(img);
    }
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', linkGeaLogos, {once:true});
  else linkGeaLogos();
})();

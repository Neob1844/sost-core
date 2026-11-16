/* SOST Universe — site map, five-section navigation, module status vocabulary and the Ctrl/Cmd+K command palette.
 * One source for the nav, the palette, the ecosystem map and the footer directory, so no page can drift.
 * Every href of the current site nav (index.html inline nav + js/nav-toggle.js?v=rs20261112g canonical list) is present here
 * (see audits/sost-universe/K_REGISTRO_CONTENIDO.md §1). Paths are relative to website/universe/.
 */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  // Module status vocabulary (mandate §14). Text + shape, never colour alone.
  var STATUS = {
    active: { label: 'ACTIVE', desc: 'Operational and verified on mainnet' },
    experimental: { label: 'EXPERIMENTAL', desc: 'Available only under explicit test conditions' },
    research: { label: 'RESEARCH', desc: 'Concept, study or development with no public activation' },
    retired: { label: 'HISTORICAL · RETIRED', desc: 'Kept for transparency; not in force' },
    blocked: { label: 'BLOCKED', desc: 'Must not be used until the corresponding controls are passed' }
  };
  function badge(k) { var s = STATUS[k]; return s ? '<span class="ms ' + k + '" title="' + s.desc + '">' + s.label + '</span>' : ''; }
  var P = '../';
  // [title, href, status|null, keywords]
  var MAP = [
    { id: 'home', title: 'Home', href: 'home.html', items: [
      ['Home', 'home.html', null, 'start overview'],
      ['News & updates', P + 'news.html', null, 'announcements releases'],
      ['Watch: SOST in 3 minutes', 'home.html#watch', null, 'video intro'],
      ['Research notice #40,000', 'home.html#research', 'research', 'reward evolution 80 15 5'],
      ['Developer note', 'home.html#devnote', null, 'experimental not guaranteed'],
    ] },
    { id: 'technology', title: 'Technology', href: 'technology.html', items: [
      ['Technology overview', 'technology.html', null, 'convergence memory validation consensus'],
      ['Technology', P + 'sost-technology.html', null, 'convergencex'],
      ['ConvergenceX & cASERT spec', P + 'casert-spec.html', 'active', 'equalizer bitsq difficulty'],
      ['Protocol spec (Layer 1)', P + 'sost-protocol-spec.html', null, 'consensus'],
      ['Whitepaper', P + 'sost-whitepaper.html', null, 'paper pdf'],
      ['Tokenomics', P + 'sost-tokenomics.html', null, 'supply emission'],
      ['Roadmap', P + 'sost-roadmap.html', null, 'plan'],
      ['Security', P + 'sost-security.html', null, 'audit advisory'],
      ['Protocol registry', P + 'protocol-registry.html', null, 'registry'],
      ['E2E protocol', P + 'sost-e2e.html', 'research', 'encrypted coordination'],
      ['FAQ', P + 'sost-faq.html', null, 'questions'],
      ['Help', P + 'sost-help.html', null, 'support'],
      ['Documentation library', 'docs.html', null, 'docs documents library read'],
      ['Whitepaper reader', P + 'whitepaper-reader.html', null, 'whitepaper full documentation'],
      ['Wallet & backup security', P + 'sost-wallet-security.html', null, 'keys backup seed'],
      ['Trinity (retired)', P + 'sost-trinity.html', 'retired', 'trinity'],
      ['Useful Compute console (retired)', P + 'trinity-useful-compute.html', 'retired', 'useful compute'],
      ['Useful Compute trial (retired)', P + 'useful-compute-trial.html', 'retired', 'useful compute trial'],
      ['AI Engine (retired)', P + 'sost-ai-engine.html', 'retired', 'ai'],
      ['Knowledge Engine (retired)', P + 'sost-knowledge-engine.html', 'retired', 'knowledge'],
      ['Materials Engine (retired)', P + 'sost-materials-engine.html', 'retired', 'materials'],
    ] },
    { id: 'blockchain', title: 'Blockchain', href: 'blockchain.html', items: [
      ['Blockchain overview', 'blockchain.html', null, 'chain blocks network how it works'],
      ['Explorer · blocks, transactions, addresses, Mining Observatory & Galaxy', P + 'sost-explorer.html', 'active', 'explorer blocks tx address search galaxy observatory mosaic control room dtd jackpot'],
      ['Control Room (current)', P + 'sost-control-room.html', 'active', 'live window archive'],
      ['Network status', P + 'sost-network-status.html', 'active', 'peers nodes'],
      ['Decentralization', P + 'sost-decentralization.html', null, 'concentration producers'],
      ['Transactions', P + 'sost-transactions.html', null, 'tx format'],
      ['Genesis', P + 'sost-genesis.html', null, 'block 0 history'],
      ['DTD & Jackpot: 288 Orbit', 'proto-c-orbit.html', 'active', 'lottery dtd jackpot'],
      ['Markets (gold reference)', P + 'sost-markets.html', null, 'xaut paxg reference not a price'],
      ['Beacon', P + 'beacon.html', null, 'beacon'],
    ] },
    { id: 'mining', title: 'Mining', href: 'mining.html', items: [
      ['Mining overview', 'mining.html', null, 'convergencex memory commands start'],
      ['Mining Launchpad', 'proto-d-launchpad.html', 'active', 'start mining guide wsl linux'],
      ['Mine SOST', P + 'sost-mine.html', 'active', 'miner'],
      ['Quick Start', P + 'sost-quickstart.html', 'active', 'install build'],
      ['Getting Started (full setup)', P + 'sost-getting-started.html', 'active', 'node wallet'],
      ['Mining calculator', P + 'sost-mining-calculator.html', null, 'estimate'],
      ['Why no pools', P + 'sost-why-no-pools.html', null, 'solo'],
      ['Miner troubleshooter', P + 'sost-miner-troubleshooter.html', null, 'errors diagnose'],
      ['Infrastructure', P + 'sost-infrastructure.html', null, 'seed nodes'],
      ['Upgrade to V30000', P + 'sost-upgrade.html', 'active', 'node miner cli upgrade 30000'],
      ['Upgrade guide v1.6.2.2 (moved)', P + 'sost-upgrade-v1622.html', 'retired', 'old upgrade'],
    ] },
    { id: 'ecosystem', title: 'Ecosystem', href: 'ecosystem.html', items: [
      ['Ecosystem overview', 'ecosystem.html', null, 'modules status tools wallet dtd jackpot'],
      ['Ecosystem map (home)', 'home.html#ecosystem', null, 'modules status'],
      ['Community', P + 'sost-community.html', null, 'forum telegram'],
      ['SOST Talk', P + 'sost-talk.html', null, 'chat'],
      ['Community rules', P + 'sost-community-rules.html', null, 'talk rules moderation'],
      ['BitcoinTalk announcement', P + 'sost-btctalk-ann.html', null, 'ann launch thread'],
      ['Governance', P + 'sost-foundation.html', null, 'foundation commitments'],
      ['Governance balances', P + 'sost-foundation-balances.html', null, 'balances'],
      ['wSOST · SOST Atomic Bridge (research)', P + 'sost-wsost-gold-vault.html', 'research', 'bridge wsost atomic wrapped'],
      ['Tokenization & offers', P + 'sost-universal-assets.html', 'blocked', 'native assets deferred fail-closed'],
      ['Metals reserve (historical)', P + 'sost-gold-reserve.html', 'retired', 'gold reserve 25%'],
      ['Metals reserve detail (historical)', P + 'sost-metals-reserve.html', 'retired', 'xaut paxg'],
      ['SOST price reference', P + 'sost-reference.html', null, 'gold reference not a market price'],
      ['PoPC (legacy)', P + 'sost-popc.html', 'retired', 'proof of personal custody'],
      ['PoPC contracts (legacy)', P + 'sost-popc-contracts.html', 'retired', 'escrow'],
      ['PoPC quick start (legacy)', P + 'sost-popc-quickstart.html', 'retired', 'popc'],
      ['DEX spec', P + 'sost-gold-dex.html', 'blocked', 'dex settlement'],
      ['Atomic swap DEX (H-01)', P + 'sost-dex.html', 'retired', 'htlc swap retired'],
      ['OTC / P2P (H-01)', P + 'sost-otc.html', 'retired', 'otc swap retired'],
      ['OTC desk: quote requests', P + 'sost-otc-alpha.html', null, 'otc quote'],
      ['OTC / swap desk (H-01)', P + 'sost-position-desk.html', 'retired', 'desk swap retired'],
      ['Signed offers (H-01)', P + 'sost-position-market.html', 'retired', 'offers swap retired'],
      ['Live offers (H-01)', P + 'sost-positions.html', 'retired', 'offers swap retired'],
      ['Swap DEX & OTC channels (H-01)', P + 'sost-dex-otc.html', 'retired', 'deal channel swap retired'],
      ['Deal channels', P + 'sost-deal-channel.html', null, 'encrypted coordination otc'],
      ['Atomic swap (H-01)', P + 'atomic-swap.html', 'retired', 'htlc swap retired'],
      ['Install the SOST app', P + 'universe/install.html', 'active', 'pwa install app android iphone windows'],
      ['Contact', P + 'sost-contact.html', null, 'email'],
      ['License', P + 'sost-license.html', null, 'mit'],
      ['Privacy policy', P + 'sost-privacy.html', null, 'privacy data'],
    ] },
  ];
  // owner GO definitivo 14-Nov-2026: ONE public Explorer, sostcore.com/sost-explorer.html (the classic one: Control Room, Mining
  // Observatory, Galaxy, DTD, Jackpot). Explorer 2.0 and /sost-app/ are retired (301 to it). One «Explorer» button.
  var TOOLS = [['Wallet', P + 'sost-wallet.html'], ['Explorer', P + 'sost-explorer.html'], ['Install App', P + 'universe/install.html']];
  // owner 13-Nov-2026 (P0): «Install App» opens universe/install.html, which installs the main SOST app (/site.webmanifest, name SOST)
  // (Chrome/Edge/Android) or Add-to-Home-Screen steps (iPhone/iPad). No .exe/.apk. Digital Vault (self-custody wallet) is NOT part of it.
  var APPT = ' title="Install the SOST Explorer app (read-only). The Digital Vault wallet is separate."', DLI = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M8 1.5v8.2M4.6 6.6 8 10l3.4-3.4M2.5 11.5v2h11v-2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var EXTRA = [['GitHub', 'https://github.com/Neob1844/sost-core'], ['Whitepaper', P + 'sost-whitepaper.html']];

  // Pages outside universe/ (DIRECTIVA 4D §5-E: the documents keep their address and get the shared header) set
  // window.SOSTU_NAV_FROM_ROOT = true before loading this file: links written for universe/ are then rewritten for the site root.
  function lk(h) { if (!root.SOSTU_NAV_FROM_ROOT || h == null) return h; h = String(h); if (h.indexOf('../') === 0) return h.slice(3); return /^(?:[a-z]+:|#|\/)/i.test(h) ? h : 'universe/' + h; }
  function esc(x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function here(h) { var f = root.SOSTU_HERE || location.pathname.split('/').pop() || 'index.html'; return h === f || String(h).split('/').pop() === f; }   // TOOLS carry the ../ prefix   // SOSTU_HERE: the site root serves the Home

  var SECT = { home: '', blockchain: 'Blockchain', explorer: 'Explorer', mining: 'Mining', technology: 'Technology', ecosystem: 'Ecosystem', dtd: 'DTD', wallet: 'Wallet' };
  var WMSECT = { explorer: 'EXPLORER', wallet: 'WALLET' };   // sections whose name is part of the brand (Goldman wordmark pair)
  function renderNav(el, current, label) {
    var sect = label != null ? label : (SECT[current] || '');
    var cur = current === 'explorer' || current === 'dtd' ? 'blockchain' : current;
    el.classList.add('hud');
    // owner P0 «unificación» §3 (5 Nov 2026), real links (click, tap, Enter, new tab, Back all work): on Home the logo / wordmark opens
    // the Explorer; on the Explorer it returns to the site root (Home); everywhere else it goes to Home as before.
    var isHome = current === 'home' && here('home.html'), isLegacy = here(P + 'sost-explorer.html');
    var bHref = isHome ? lk(P + 'sost-explorer.html') : isLegacy ? '/' : lk('home.html'), bLab = isHome ? 'SOST: open the Explorer' : 'SOST home';
    var wmS = WMSECT[current] || '';
    var h = '<a class="brand' + (wmS ? ' has-sect-m wm-pair' : '') + '" id="navBrand" href="' + bHref + '" aria-label="' + bLab + '"><span class="eyemark" aria-hidden="true"><img class="sig" src="' + lk(P + 'universe/assets/brand/sost-eye-128.png?v=sl20261113') + '" srcset="' + lk(P + 'universe/assets/brand/sost-eye-128.png?v=sl20261113') + ' 2x, ' + lk(P + 'universe/assets/brand/sost-eye-180.png?v=sl20261113') + ' 3x" width="56" height="56" alt="" decoding="async"><canvas></canvas></span><span class="wm">SOST</span>' + (sect ? '<span class="sect' + (wmS ? ' wm' : '') + '">' + esc(wmS || sect) + '</span>' : '') + '' + '</a><ul class="nv" id="navList">';
    current = cur;
    MAP.forEach(function (s) {
      // phones / tablets (≤ 980 px): the section name is a real link to its page and the ▾ next to it opens the sub-menu explicitly
      // (owner P0 mobile hotfix, 4 Nov 2026: tapping BLOCKCHAIN used to open an empty sub-menu instead of navigating). Desktop unchanged.
      h += '<li class="nv-s' + (s.id === current ? ' cur' : '') + '"><a class="nv-go" href="' + esc(lk(s.href)) + '"' + (here(s.href) ? ' aria-current="page"' : '') + '>' + esc(s.title) + '</a>' +
        '<button type="button" class="nv-b" aria-expanded="false" aria-controls="nv-' + s.id + '" aria-label="' + esc(s.title) + ' pages"><span class="nv-t">' + esc(s.title) + '</span><span class="nv-c" aria-hidden="true">▾</span></button>' +
        '<div class="nv-m" id="nv-' + s.id + '" hidden><ul>' + s.items.map(function (it) {
          return '<li><a href="' + esc(lk(it[1])) + '"' + (here(it[1]) ? ' aria-current="page"' : '') + '>' + esc(it[0]) + (it[2] ? ' ' + badge(it[2]) : '') + '</a></li>';
        }).join('') + '</ul></div></li>';
    });
    // phones / tablets: the header has room only for the brand and ☰ Menu, so the tools are the last row of the open menu
    h += '<li class="nv-tools-m">' + TOOLS.map(function (t) { return '<a href="' + lk(t[1]) + '"' + (here(t[1]) ? ' aria-current="page"' : '') + (t[0] === 'Install App' ? APPT + ' class="app">' + DLI + t[0] : '>' + t[0]) + '</a>'; }).join('') + '<button type="button" class="nv-k-m">Search</button></li>';
    h += '</ul><div class="tools">' + TOOLS.map(function (t) { return '<a class="btn small' + (t[0] === 'Explorer' && !here(t[1]) ? ' primary' : '') + '' + (t[0] === 'Wallet' ? ' wallet' : '') + (t[0] === 'Install App' ? ' app' : '') + (here(t[1]) ? ' on' : '') + '" href="' + lk(t[1]) + '"' + (t[0] === 'Install App' ? APPT + ' aria-label="Install App">' + DLI + '<span class="lb">' + t[0] + '</span>' : '>' + t[0]) + '</a>'; }).join('') +
      // 981–1099 px: Explorer and Install App share one dropdown
      '<span class="xg"><button class="btn small xg-b" type="button" aria-expanded="false" aria-haspopup="true">Explorer ▾</button><span class="xg-m" hidden>' +
        TOOLS.filter(function (t) { return /^(Explorer|Install App)/.test(t[0]); }).map(function (t) { return '<a href="' + lk(t[1]) + '"' + (here(t[1]) ? ' aria-current="page"' : '') + '>' + t[0] + '</a>'; }).join('') + '</span></span>' +
      '<button class="btn small kbtn" type="button" id="kOpen" aria-haspopup="dialog" aria-keyshortcuts="Control+K Meta+K">Search <kbd>' + (/Mac|iP/.test(navigator.platform) ? '⌘' : 'Ctrl') + ' K</kbd></button></div>' +
      '<button class="btn small menu-btn" type="button" aria-expanded="false" aria-controls="navList">☰ Menu</button>';
    el.innerHTML = h; el.dataset.managed = '1'; mobileCss();
    var btns = el.querySelectorAll('.nv-b');
    function closeAll(except) { btns.forEach(function (b) { if (b !== except) { b.setAttribute('aria-expanded', 'false'); document.getElementById(b.getAttribute('aria-controls')).hidden = true; } }); }
    btns.forEach(function (b) {
      b.addEventListener('click', function () { var o = b.getAttribute('aria-expanded') !== 'true'; closeAll(b); b.setAttribute('aria-expanded', String(o)); document.getElementById(b.getAttribute('aria-controls')).hidden = !o; });
    });
    var mb = el.querySelector('.menu-btn');
    function menu(o) { el.classList.toggle('open', o); mb.setAttribute('aria-expanded', String(o)); mb.textContent = o ? '✕ Close' : '☰ Menu'; if (!o) closeAll(); }
    function closeNav() { if (el.classList.contains('open')) menu(false); else closeAll(); }
    document.addEventListener('click', function (e) { if (!el.contains(e.target)) closeNav(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { var open = el.querySelector('.nv-b[aria-expanded="true"]'), wasMenu = el.classList.contains('open'); closeNav(); if (open) open.focus(); else if (wasMenu) mb.focus(); } });
    mb.addEventListener('click', function () { var o = !el.classList.contains('open'); menu(o); if (o) { var f = el.querySelector('.nv-go'); if (f && f.offsetParent) f.focus({ preventScroll: true }); } });
    // a followed link closes the menu (and a page restored from the back/forward cache never comes back with it open)
    el.addEventListener('click', function (e) { var a = e.target.closest && e.target.closest('a[href]'); if (a && el.contains(a)) closeNav(); });
    root.addEventListener('pageshow', closeNav);
    if (root.matchMedia) { var mq = root.matchMedia('(min-width: 981px)'); (mq.addEventListener ? mq.addEventListener('change', closeNav) : mq.addListener(closeNav)); }
    U.navClose = closeNav;
    document.getElementById('kOpen').addEventListener('click', openPalette);
    var xb = el.querySelector('.xg-b'), xm = el.querySelector('.xg-m');
    if (xb) { xb.addEventListener('click', function (e) { e.stopPropagation(); var o = xm.hidden; xm.hidden = !o; xb.setAttribute('aria-expanded', String(o)); if (o) xm.querySelector('a').focus(); });
      document.addEventListener('click', function (e) { if (!xm.hidden && !xm.contains(e.target)) { xm.hidden = true; xb.setAttribute('aria-expanded', 'false'); } });
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !xm.hidden) { xm.hidden = true; xb.setAttribute('aria-expanded', 'false'); xb.focus(); } }); }
    // old js/nav-toggle.js?v=rs20261112g may append its own buttons to this header later: tag it once (a class, not a costly :has() selector)
    [400, 1500, 4000].forEach(function (t) { setTimeout(function () { if (el.querySelector(':scope > .sost-nav-toggle')) el.classList.add('has-foreign'); }, t); });
    var km = el.querySelector('.nv-k-m'); if (km) km.addEventListener('click', function () { closeNav(); openPalette(); });
    // dynamic lighting: the header glass follows the pointer (one CSS variable, no layout)
    // header emblem animation (eye + Σ pulse): loaded only after the page load and an idle slot, so it never competes with the LCP
    (function () { var em = el.querySelector('.eyemark'); if (!em) return; function go() { var f = function () { if (U.emblem) U.emblem.mount(em, root.SOSTU_NAV_FROM_ROOT ? '' : P); else { var sc = document.createElement('script'); sc.src = lk(P + 'universe/core/u-emblem.js?v=rs20261112g'); sc.onload = function () { U.emblem.mount(em, root.SOSTU_NAV_FROM_ROOT ? '' : P); }; document.head.appendChild(sc); } }; (root.requestIdleCallback || function (c) { setTimeout(c, 300); })(f, { timeout: 2500 }); }
      if (document.readyState === 'complete') go(); else addEventListener('load', go, { once: true }); })();
    if (!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches)) el.addEventListener('pointermove', function (e) { var r = el.getBoundingClientRect(); el.style.setProperty('--mx', ((e.clientX - r.left) / r.width * 100).toFixed(1) + '%'); }, { passive: true });
  }

  // Mobile menu layout (≤ 980 px), injected once by this script so the Universe pages and the legacy pages share one source and
  // a cached stylesheet can never pair with this markup: opaque panel under the header, no horizontal scroll, section link + ▾,
  // sub-menus in normal flow (core/u-ui.css and u-legacy-skin.css position every `.u-nav.open ul` absolutely, which emptied them).
  function mobileCss() {
    if (document.getElementById('u-nav-m')) return;
    var x = ':not(#_m)', st = document.createElement('style'); st.id = 'u-nav-m';
    // while a menu or a sub-menu is open the header sits above the page layers (legacy pages: developer-note strip z 9000, search bar
    // z 50 — they covered the dropdowns and took the taps meant for them)
    st.textContent = 'nav.u-nav.open' + x + ',nav.u-nav:has(.nv-b[aria-expanded="true"])' + x + '{z-index:9600!important}' +
      // legacy js/nav-toggle.js?v=rs20261112g drops its 110 px tokenization / wSOST logos into the first <nav> of the page, which is now this header
      'nav.u-nav a.sost-tok-logo,nav.u-nav a.sost-wsost-btn{display:none!important}' +
      // [EYE] SOST EXPLORER: both words are the wordmark (Goldman 700, same size, tracking and baseline as SOST on Home)
      '.u-nav.hud .brand.wm-pair .sect.wm' + x + '{display:inline-block!important;font:700 31px/1 var(--f-wordmark,"SOST Wordmark"),sans-serif!important;letter-spacing:-.09em!important;color:#fff!important;padding:0 0 0 .3em!important;margin:0!important;border:0!important;text-transform:uppercase;transform:none!important}' +
      '.u-nav.hud .brand.wm-pair' + x + '{gap:10px}' +
      '@media (min-width:981px) and (max-width:1439px){.u-nav.hud .brand.wm-pair .wm' + x + ',.u-nav.hud .brand.wm-pair .sect.wm' + x + '{font-size:26px!important}}' +
      '@media (max-width:520px){.u-nav.hud .brand.wm-pair .wm' + x + ',.u-nav.hud .brand.wm-pair .sect.wm' + x + '{font-size:21px!important}.u-nav.hud .brand.wm-pair' + x + '{gap:7px}}' +
      '@media (max-width:370px){.u-nav.hud .brand.wm-pair .wm' + x + ',.u-nav.hud .brand.wm-pair .sect.wm' + x + '{font-size:18px!important}.u-nav.hud .brand.wm-pair' + x + '{gap:5px!important}.u-nav.hud .brand.wm-pair .eyemark' + x + '{width:40px!important;height:40px!important}}' +
      'nav.u-nav .nv-tools-m' + x + '{display:none}' +
      'nav.u-nav .tools .btn' + x + ',nav.u-nav .menu-btn' + x + '{white-space:nowrap}' +
      // «Install App»: same pill as the other tools, thin official-rainbow border, download glyph; icon-only where the header is tight
      'nav.u-nav .tools .btn.app' + x + '{display:inline-flex;align-items:center;gap:6px;border:1px solid transparent;background:linear-gradient(#050505,#050505) padding-box,linear-gradient(90deg,#FC1506,#FC7901,#FDF902,#36EF3E,#00CEFC,#0078FC,#8001F4,#F202C2) border-box}' +
      'nav.u-nav .tools .btn.app svg' + x + ',nav.u-nav .nv-tools-m a.app svg' + x + '{width:13px;height:13px;flex:0 0 auto}nav.u-nav .nv-tools-m a.app' + x + '{gap:7px}' +
      '@media (min-width:981px) and (max-width:1599px){nav.u-nav .tools .btn.app .lb' + x + '{display:none}nav.u-nav .tools .btn.app' + x + '{gap:0;padding-left:8px!important;padding-right:8px!important}}' +
      'nav.u-nav .xg' + x + '{display:none;position:relative}' +
      // pages whose old js/nav-toggle.js?v=rs20261112g puts its own buttons into this header (e.g. Wallet security): the tools tighten so nothing overflows
      '@media (min-width:981px) and (max-width:1599px){nav.u-nav.has-foreign .kbtn kbd' + x + '{display:none}nav.u-nav.has-foreign .tools .btn' + x + '{padding-left:8px!important;padding-right:8px!important}nav.u-nav.has-foreign .tools' + x + '{gap:4px!important}}' +
      '@media (min-width:981px) and (max-width:1099px){nav.u-nav .xg' + x + '{display:inline-flex}nav.u-nav .tools .btn.primary' + x + ',nav.u-nav .tools .btn.legacy' + x + ',nav.u-nav .tools a.btn[href$="explorer.html"]' + x + '{display:none!important}}' +
      'nav.u-nav .xg-m' + x + '{position:absolute;top:calc(100% + 8px);right:0;z-index:40;display:flex;flex-direction:column;min-width:210px;padding:6px;border:1px solid #ffffff22;border-radius:12px;background:#07080cf7;box-shadow:0 18px 40px #000c}' +
      'nav.u-nav .xg-m[hidden]' + x + '{display:none}' +
      'nav.u-nav .xg-m a' + x + '{padding:10px 12px;border-radius:8px;color:#e5e7eb;text-decoration:none;font:600 13px var(--f-head,sans-serif);white-space:nowrap}' +
      'nav.u-nav .xg-m a' + x + ':hover,nav.u-nav .xg-m a' + x + ':focus-visible{background:#ffffff12;color:#fff;outline:none}' +
      'nav.u-nav .xg-m a[aria-current]' + x + '{box-shadow:inset 2px 0 0 #22d3ee}' +
      // 4 tools on desktop: tighter between 981 and 1365 px so the row never wraps
      '@media (min-width:981px) and (max-width:1439px){nav.u-nav .tools' + x + '{gap:5px!important}nav.u-nav .tools .btn' + x + '{padding-left:9px!important;padding-right:9px!important}nav.u-nav .kbtn kbd' + x + '{display:none}}' +
      // ≤980 px the header keeps brand + Search + ☰ Menu; Wallet / Explorer / Install App are the last row of the open menu
      '@media (max-width:980px){nav.u-nav .tools .btn:not(.kbtn)' + x + ',nav.u-nav .xg' + x + '{display:none!important}nav.u-nav .kbtn kbd' + x + '{display:none}}' +
      '@media (max-width:520px){nav.u-nav .tools .btn' + x + '{display:none!important}}' +
      // «Install App» needs ~40 px: 1440-1599 the Search key hint folds (as below 1440), 1100-1439 the tool pills tighten 2 px a side,
      // 981-1099 the button moves into the «Explorers ▾» dropdown (it is the Explorer app); nothing else is removed
      '@media (min-width:1440px) and (max-width:1599px){nav.u-nav .kbtn kbd' + x + '{display:none}}' +
      '@media (min-width:1100px) and (max-width:1439px){nav.u-nav .tools' + x + '{gap:4px!important}nav.u-nav .tools .btn' + x + '{padding-left:7px!important;padding-right:7px!important}}' +
      '@media (min-width:981px) and (max-width:1099px){nav.u-nav .tools .btn.app' + x + '{display:none!important}}' +
      // 981–1199 px: every entry stays; only sizes tighten (wordmark pair 22 px, menu 12 px, Search as a glyph with its label for AT)
      '@media (min-width:981px) and (max-width:1199px){.u-nav.hud .brand.wm-pair .wm' + x + ',.u-nav.hud .brand.wm-pair .sect.wm' + x + '{font-size:21px!important}.u-nav.hud .brand.wm-pair .eyemark' + x + '{width:46px!important;height:46px!important}' +
        'nav.u-nav .nv-b' + x + '{font-size:11.5px!important;padding-left:7px!important;padding-right:7px!important;letter-spacing:.03em!important}nav.u-nav.hud' + x + '{gap:8px!important;padding-left:8px!important;padding-right:8px!important}' +
        'nav.u-nav .tools .btn' + x + '{padding-left:8px!important;padding-right:8px!important;font-size:12px!important}nav.u-nav .tools' + x + '{gap:4px!important}}' +
      '@media (min-width:1100px) and (max-width:1199px){nav.u-nav .tools .btn' + x + '{padding-left:6px!important;padding-right:6px!important}nav.u-nav .tools' + x + '{gap:3px!important}' +
        '.u-nav.hud .brand .sect:not(.wm)' + x + '{letter-spacing:.16em!important}}' +
      '@media (max-width:980px){body:has(nav.u-nav.open) .ua{visibility:hidden!important}}' +
      '@media (min-width:981px){.u-nav .nv-go,.u-nav .nv-c{display:none!important}}' +
      '.u-nav .brand:has(.leg){position:relative}.u-nav .brand .leg{position:absolute;right:2px;bottom:-1px;color:#fb7185;font:700 8.5px/1 "Space Grotesk",Inter,system-ui,sans-serif;letter-spacing:.32em;pointer-events:none;opacity:.9}' +
      '@media (max-width:980px){' +
      // one breakpoint for every page: legacy skin only switched to the menu at 820 px, so from 821 to 980 px (phones in landscape,
      // small tablets) its sections were hidden and no Menu button was shown
      'nav.u-nav .menu-btn' + x + '{display:inline-flex!important}' +
      'nav.u-nav:not(.open) .nv' + x + '{display:none!important}' +
      'nav.u-nav.open .nv' + x + '{display:flex!important;flex-direction:column;position:absolute!important;top:calc(100% + 8px)!important;left:0!important;right:0!important;margin:0!important;padding:6px!important;' +
        'background:#050507!important;opacity:1!important;-webkit-backdrop-filter:none!important;backdrop-filter:none!important;border:1px solid #ffffff1f!important;border-radius:14px!important;box-shadow:0 26px 70px #000!important;' +
        'max-height:calc(100dvh - 96px)!important;overflow-x:hidden!important;overflow-y:auto!important;overscroll-behavior:contain;z-index:60}' +
      'nav.u-nav .nv-s' + x + '{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;border-bottom:1px solid #ffffff0f}' +
      'nav.u-nav .nv-s' + x + ':last-child{border-bottom:0}' +
      'nav.u-nav .nv-go' + x + '{display:block;min-width:0;padding:14px;border-radius:10px;color:#e5e7eb;text-decoration:none;font-weight:700;font-size:15px;letter-spacing:.12em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;-webkit-tap-highlight-color:transparent}' +
      'nav.u-nav .nv-go' + x + ':active,nav.u-nav .nv-go' + x + ':focus-visible{background:#ffffff12;color:#fff}' +
      'nav.u-nav .nv-s.cur .nv-go' + x + '{color:#fff;box-shadow:inset 3px 0 0 #fb010d}' +
      'nav.u-nav .nv-b' + x + '{display:inline-flex!important;align-items:center;justify-content:center;width:46px;height:46px;padding:0!important;margin:0 2px 0 0;border-radius:10px;box-shadow:none!important}' +
      'nav.u-nav .nv-b' + x + ':after{display:none!important}' +
      'nav.u-nav .nv-b' + x + ' .nv-t{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}' +
      'nav.u-nav .nv-c' + x + '{display:inline-block;font-size:15px;line-height:1;color:#aab4c3;transition:transform .2s}' +
      'nav.u-nav .nv-b[aria-expanded="true"] .nv-c' + x + '{transform:rotate(180deg);color:#fff}' +
      'nav.u-nav .nv-m' + x + '{grid-column:1/-1;position:static!important;min-width:0!important;max-height:none!important;margin:0 0 6px!important;padding:2px 0 4px 12px!important;background:none!important;border:0!important;box-shadow:none!important;-webkit-backdrop-filter:none!important;backdrop-filter:none!important;animation:none!important}' +
      'nav.u-nav .nv-m[hidden]' + x + '{display:none!important}' +
      'nav.u-nav.open .nv-m ul' + x + '{display:grid!important;position:static!important;inset:auto!important;margin:0!important;padding:0!important;background:none!important;border:0!important;border-radius:0!important;box-shadow:none!important}' +
      'nav.u-nav .nv-m a' + x + '{padding:11px 12px!important;font-size:14px!important;white-space:normal;overflow-wrap:anywhere}' +
      'nav.u-nav.open .nv-tools-m' + x + '{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;padding:10px 6px 4px;border-top:1px solid #ffffff1f}' +
      'nav.u-nav .nv-tools-m a' + x + ',nav.u-nav .nv-tools-m button' + x + '{all:unset;box-sizing:border-box;cursor:pointer;display:flex;align-items:center;justify-content:center;min-height:46px;padding:0 10px;border:1px solid #ffffff26;border-radius:10px;color:#e5e7eb;font:600 14px var(--f-head,sans-serif);text-align:center;-webkit-tap-highlight-color:transparent}' +
      'nav.u-nav .nv-tools-m a[aria-current]' + x + '{border-color:#22d3ee99;color:#fff}' +
      'nav.u-nav .nv-tools-m a' + x + ':focus-visible,nav.u-nav .nv-tools-m button' + x + ':focus-visible{outline:2px solid #22d3ee;outline-offset:1px}' +
      '}';
    document.head.appendChild(st);
  }

  // ---- command palette ----
  var dlg = null, list = [], sel = 0;
  function classify(q) {
    q = q.trim();
    if (/^#?\d{1,9}$/.test(q)) return { kind: 'block', q: q.replace('#', ''), label: 'Block #' + q.replace('#', '') + ' in the Explorer' };
    if (/^[0-9a-fA-F]{64}$/.test(q)) return { kind: 'hash', q: q, label: 'Block or transaction hash ' + q.slice(0, 12) + '… in the Explorer' };
    if (/^sost1[0-9a-fA-F]{40}$/.test(q)) return { kind: 'address', q: q, label: 'Address ' + q.slice(0, 14) + '… in the Explorer' };
    return null;
  }
  function explorerHref(q) { return P + 'sost-explorer.html?search=' + encodeURIComponent(q); }
  function all() { var a = []; MAP.forEach(function (s) { s.items.forEach(function (it) { a.push({ t: it[0], h: it[1], s: it[2], k: (it[3] || '') + ' ' + s.title }); }); }); TOOLS.concat(EXTRA).forEach(function (t) { a.push({ t: t[0], h: t[1], k: 'tool' }); }); return a; }
  function openPalette() {
    if (!dlg) {
      dlg = document.createElement('dialog'); dlg.className = 'kpal'; dlg.setAttribute('aria-label', 'Search pages, blocks, transactions and addresses');
      dlg.innerHTML = '<div class="kpal-top" aria-hidden="true"><img class="sig" src="' + lk(P + 'universe/assets/brand/sost-eye-48.png?v=sl20261113') + '" width="24" height="24" alt=""><span class="wm">SOST</span>COMMAND CONSOLE<span class="live" id="kLive"></span></div><form method="dialog" class="kpal-f"><label class="sr" for="kIn">Search</label><input id="kIn" type="search" autocomplete="off" spellcheck="false" placeholder="Pages, docs, block height, hash or sost1… address" role="combobox" aria-controls="kList" aria-expanded="true">' +
        '<button class="btn small" value="close" type="submit">Esc</button></form><ul id="kList" role="listbox"></ul><p class="kpal-h">↑ ↓ to move · Enter to open · block, tx and address lookups run on demand in the Explorer</p>';
      document.body.appendChild(dlg);
      var inp = dlg.querySelector('#kIn');
      inp.addEventListener('input', function () { draw(inp.value); });
      inp.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowDown') { sel = Math.min(list.length - 1, sel + 1); mark(); e.preventDefault(); }
        else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); mark(); e.preventDefault(); }
        else if (e.key === 'Enter') { e.preventDefault(); if (list[sel]) location.href = lk(list[sel].h); }
      });
      dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
    }
    if (!dlg.open) dlg.showModal(); var i = dlg.querySelector('#kIn'); i.value = ''; draw(''); i.focus();
    try { var L = U.data && U.data.last && U.data.last(); dlg.querySelector('#kLive').textContent = L && L.state ? 'TIP #' + Number(L.state.meta.height).toLocaleString('en-US') + ' · ' + String(L.status).toUpperCase() : ''; } catch (e) {}
  }
  function draw(q) {
    var c = classify(q), items = all(), ql = q.toLowerCase().trim();
    list = (c ? [{ t: c.label, h: explorerHref(c.q), k: 'explorer' }] : []).concat(ql ? items.filter(function (x) { return (x.t + ' ' + x.k).toLowerCase().indexOf(ql) >= 0; }) : items).slice(0, 40);
    sel = 0;
    dlg.querySelector('#kList').innerHTML = list.map(function (x, i) { return '<li role="option" id="ko' + i + '"><a href="' + esc(lk(x.h)) + '">' + (x.k === 'explorer' ? '<span class="kind">LOOKUP</span>' : '') + esc(x.t) + (x.s ? ' ' + badge(x.s) : '') + '<span>' + esc(x.h.replace(/^\.\.\//, '/')) + '</span></a></li>'; }).join('') || '<li class="none">No page matches. Try a block height, a 64-hex hash or a sost1… address.</li>';
    mark();
  }
  function mark() { var lis = dlg.querySelectorAll('#kList li[role=option]'); lis.forEach(function (l, i) { l.setAttribute('aria-selected', String(i === sel)); }); var inp = dlg.querySelector('#kIn'); if (lis[sel]) { inp.setAttribute('aria-activedescendant', 'ko' + sel); lis[sel].scrollIntoView({ block: 'nearest' }); } }
  document.addEventListener('keydown', function (e) { if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); openPalette(); } });

  function directory(el) {
    el.innerHTML = MAP.map(function (s) { return '<div><h3>' + esc(s.title) + '</h3><ul>' + s.items.map(function (it) { return '<li><a href="' + esc(lk(it[1])) + '">' + esc(it[0]) + '</a>' + (it[2] ? ' ' + badge(it[2]) : '') + '</li>'; }).join('') + '</ul></div>'; }).join('') +
      '<div><h3>Tools &amp; source</h3><ul>' + TOOLS.concat(EXTRA).map(function (t) { return '<li><a href="' + esc(lk(t[1])) + '">' + esc(t[0]) + '</a></li>'; }).join('') + '<li><a href="' + lk('music-credits.html') + '">Music credits &amp; licences</a></li><li><a href="' + lk('legacy/matrix-legacy.html') + '">Matrix Legacy splash</a></li><li><a href="' + lk('../index-legacy.html') + '">Previous home page</a></li></ul></div>';
  }
  U.nav = { MAP: MAP, STATUS: STATUS, badge: badge, render: renderNav, open: openPalette, classify: classify, directory: directory, explorerHref: explorerHref };
  U.nav.close = function () { if (U.navClose) U.navClose(); };
})(window);

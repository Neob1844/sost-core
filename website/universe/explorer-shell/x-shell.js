/* SOST Explorer shell (DIRECTIVAS 4F/4G) — header, section nav, compact status strip, notices group, footer, and (version 2)
 * the integrated live console. PRESENTATION ONLY:
 *  - never calls /rpc and never fetches anything itself; the status strip copies the figures the Explorer engine has already
 *    written into its own cards (MutationObserver), so it adds 0 requests;
 *  - the header search writes the query into the engine's own #searchIn and presses its own FIND button (same code path);
 *  - version 2 loads the Control Room renderer UNMODIFIED (control-room/state.js, adapter.js, ui.js) into .xcr, reading the
 *    same static /api/control_room.json + /api/block_series.json the Control Room reads (0 RPC), only when the console is
 *    about to be seen or opened.
 * ?shell=v1 shows version 1 (no console). Load order: after u-nav.js?v=rs20261112g, at the end of <body>. */
(function (root) {
  'use strict';
  var d = document, U = root.SOSTU || {}, de = d.documentElement;
  var qs = new URLSearchParams(location.search);
  var V1 = qs.get('shell') === 'v1';
  var RM = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function $(id) { return d.getElementById(id); }
  function txt(el) { return el ? (el.textContent || '').replace(/\s+/g, ' ').trim() : ''; }
  function idle(fn, t) { (root.requestIdleCallback || function (c) { return setTimeout(c, 200); })(fn, { timeout: t || 2000 }); }

  // ---------- 1. shared header: [EYE Σ] SOST · EXPLORER, site menus, Wallet, Ctrl/Cmd+K ----------
  var uNav = $('uNav');
  if (uNav && U.nav) { try { U.nav.render(uNav, 'explorer'); } catch (e) { /* header stays as static brand */ } }

  // ---------- 2. anchors for blocks that have no id (ids added at runtime only; engine markup untouched) ----------
  function tagId(el, id) { if (el && !el.id) el.id = id; return el && el.id; }
  var searches = d.querySelectorAll('body > .search');
  tagId(searches[0], 'xsFind'); tagId(searches[1], 'xsInspect');
  var cfg = d.querySelector('body > .config'); tagId(cfg, 'xsRpc');
  // the optional own-node RPC row moves next to the Network section (same inputs, same ids, same handlers)
  var nh = $('netHealthSection'); if (cfg && nh && nh.parentNode) nh.parentNode.insertBefore(cfg, nh);
  var sp = $('sparkTooltip'); if (sp) tagId(sp.closest('.diff-bar-wrap') || sp.parentNode, 'xsDiffHist');
  var em = $('emStats'); if (em) tagId(em.parentNode, 'xsEmission');
  var cs = $('csWall'); if (cs) { var c2 = cs.parentNode; while (c2 && c2.parentNode && !/margin|padding/.test(c2.getAttribute('style') || '') && c2.parentNode !== d.body) c2 = c2.parentNode; tagId(c2, 'xsTiming'); }
  var ov = $('ovxautpaxgPct'); if (ov) tagId(ov.closest('.price-card') || ov.parentNode, 'xsOverlays');

  // ---------- 3. section nav + contextual sub-anchors + scrollspy ----------
  var SECTIONS = [
    ['overview', [['dashboard', 'Network at a glance'], ['convxCRWrap', 'Equalizer · intervals · bitsQ'], ['statsCode', 'Node stats']]],
    ['blocks', [['blocksSection', 'Latest blocks'], ['networkMosaicWrap', 'Network mosaic'], ['chartBlockTimeWrap', 'Block times'], ['chartProdWrap', 'Block production'], ['chartBurstWrap', 'Burst & volatility'], ['xsDiffHist', 'Difficulty history']]],
    ['transactions', [['txSection', 'Latest transactions'], ['mpSection', 'Mempool']]],
    ['addresses', [['xsObs', 'Producer addresses (observatory)'], ['ainOut', 'Address inspector result'], ['producerDistSection', 'Producers distribution']]],
    ['mining', [['miningSection', 'Mining status'], ['xsObs', 'Mining observatory'], ['producerDistSection', 'Producers distribution'], ['xsEmission', 'Emission'], ['xsTiming', 'Chain timing']]],
    ['galaxy', [['xsObs', 'Galaxy · Mining observatory']]],   // owner P0: own tab right after Mining (opens the observatory in GALAXY view)
    ['dtd', [['dtdWinnersSection', 'DTD & Jackpot winners'], ['jackpotCard', 'Jackpot card']]],
    ['network', [['netHealthSection', 'Network health'], ['nodesSection', 'Active nodes'], ['boundNodesWrap', 'Bound nodes'], ['xsAdvCfg', 'Advanced settings (own node, optional)']]],
    ['markets', [['priceChartsRow', 'Gold prices'], ['xsOverlays', 'Overlays'], ['sostDisclaimer', 'Gold reference · not a price']]]
  ];
  var tabs = d.querySelectorAll('#xsTabs a[data-sec]'), ctx = $('xsCtx'), cur = null;
  var map = {}; SECTIONS.forEach(function (s) { map[s[0]] = s[1].filter(function (a) { return $(a[0]); }); });
  function go(id, ev, hash, instant) {
    var el = $(id); if (!el) return;
    if (ev) ev.preventDefault();
    if (id === 'xsConsole' || id === 'xsHistorical') loadConsole(); if (id === 'xsObs') loadGalaxy();
    el.scrollIntoView({ behavior: RM || instant ? 'instant' : 'smooth', block: 'start' });   // scroll-margin-top = measured header height + 12
    try { history.replaceState(null, '', '#' + (hash || id)); } catch (e) {}
  }
  // GALAXY: observatory + GALAXY view (the observatory keeps its selection, window and filter; only the view changes)
  function openGalaxy(ev) {
    try { localStorage.setItem('sost_xs_obs_mode', 'galaxy'); } catch (e) {}
    var g = U.explorerGalaxy; if (g && g.state.mode !== 'galaxy') { g.state.mode = 'galaxy'; g.render(); }
    // instant jump (a long smooth scroll fights the corrections below while lazy panels above are still growing)
    go('xsObs', ev, 'galaxy', true); setCur('galaxy'); lockSpy();
    var o = $('xsObs'); if (!o) return;
    // Lazy panels above keep growing while the page loads (seconds on a slow phone): hold the Observatory under the header,
    // re-checked every 250 ms and on every layout change, for at most 120 checks (~30 s). It stops for good the moment the
    // visitor takes over: wheel, touch, key, pointer, or any scroll this code did not make (scrollbar drag included).
    var n = 0, done = false, lastY = root.scrollY, ro = null, iv;
    function stop() { if (done) return; done = true; clearInterval(iv); if (ro) ro.disconnect(); EV.forEach(function (t) { removeEventListener(t, stop, true); }); }
    var EV = ['wheel', 'touchstart', 'keydown', 'pointerdown'];
    EV.forEach(function (t) { addEventListener(t, stop, { capture: true, passive: true }); });
    function hold() {
      if (done) return; if (++n > 120) return stop();
      var want = (parseFloat(getComputedStyle(de).getPropertyValue('--xs-head')) || 0) + 12, top = o.getBoundingClientRect().top, off = Math.abs(top - want) > 8;
      if (Math.abs(root.scrollY - lastY) > 2) { if (off) return stop(); lastY = root.scrollY; return; }   // moved by someone else: the visitor, or the browser's own scroll anchoring (still aligned)
      if (off) { root.scrollBy({ top: top - want, behavior: 'instant' }); lockSpy(); setCur('galaxy'); }
      lastY = root.scrollY;
    }
    iv = setInterval(hold, 250);
    if ('ResizeObserver' in root) { ro = new ResizeObserver(function () { hold(); }); ro.observe(d.body); }
  }
  // a click on a tab wins over the scrollspy while the smooth scroll runs (xsObs is shared by Mining and Galaxy)
  var spyLock = 0; function lockSpy() { spyLock = Date.now() + 1200; }
  function setCur(sec) {
    if (sec === cur) return; cur = sec;
    tabs.forEach(function (a) { a.setAttribute('aria-current', String(a.dataset.sec === sec)); });
    var list = map[sec] || [];
    ctx.innerHTML = list.length > 1 ? list.map(function (a) { return '<a href="#' + a[0] + '" data-go="' + a[0] + '">' + a[1] + '</a>'; }).join('') : '';
    ctx.classList.toggle('on', list.length > 1);
  }
  tabs.forEach(function (a) {
    var list = map[a.dataset.sec] || [];
    if (!list.length) { a.hidden = true; return; }
    if (a.dataset.sec === 'galaxy') { a.href = '#galaxy'; a.addEventListener('click', openGalaxy); return; }
    a.href = '#' + list[0][0];
    a.addEventListener('click', function (e) { go(list[0][0], e); setCur(a.dataset.sec); lockSpy(); });
  });
  ctx.addEventListener('click', function (e) { var a = e.target.closest('a[data-go]'); if (a) go(a.dataset.go, e); });
  var spy = [];
  // scrollspy: each block counts for one tab only (cards inside the dashboard, e.g. the Jackpot card, stay Overview)
  var SPY_SKIP = { 'addresses:producerDistSection': 1, 'addresses:xsObs': 1, 'mining:xsObs': 1, 'dtd:jackpotCard': 1, 'overview:xsConsole': 1 };
  function buildSpy() {
    spy = [];
    SECTIONS.forEach(function (s) { (map[s[0]] || []).forEach(function (a) { var el = $(a[0]); if (el && !SPY_SKIP[s[0] + ':' + a[0]]) spy.push([el, s[0]]); }); });
  }
  var ticking = false;
  function onScroll() {
    if (ticking) return; ticking = true;
    requestAnimationFrame(function () {
      ticking = false; if (Date.now() < spyLock) return;
      var line = (parseFloat(getComputedStyle(de).getPropertyValue('--xs-head')) || 142) + 40, best = 'overview', bestTop = -1e9;
      spy.forEach(function (p) { var r = p[0].getBoundingClientRect(); if (r.height && r.top <= line && r.top > bestTop) { bestTop = r.top; best = p[1]; } });
      setCur(best);
    });
  }
  buildSpy(); setCur('overview');
  addEventListener('scroll', onScroll, { passive: true });

  // Help / Docs menu (every documentation link of the old nav + the Explorer's own Watch and ConvergenceX panels)
  var hb = $('xsHelpBtn'), hp = $('xsHelp');
  function closeHelp() { if (hp && !hp.hidden) { hp.hidden = true; hb.setAttribute('aria-expanded', 'false'); } }
  if (hb && hp) {
    hb.addEventListener('click', function (e) {
      e.stopPropagation();
      if (!hp.hidden) { closeHelp(); return; }
      var r = hb.getBoundingClientRect();
      hp.style.top = Math.round(r.bottom + 6) + 'px'; hp.style.left = Math.max(8, Math.min(innerWidth - 280, Math.round(r.left))) + 'px';
      hp.hidden = false; hb.setAttribute('aria-expanded', 'true'); var f = hp.querySelector('a'); if (f) f.focus();
    });
    d.addEventListener('click', function (e) { if (!hp.contains(e.target)) closeHelp(); });
    d.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !hp.hidden) { closeHelp(); hb.focus(); } });
    addEventListener('scroll', closeHelp, { passive: true });
    hp.addEventListener('click', function (e) {
      var a = e.target.closest('a[data-call]'); if (!a) return;
      e.preventDefault(); closeHelp();
      try { if (a.dataset.call === 'watch' && typeof root.openSv === 'function') root.openSv(); if (a.dataset.call === 'cx' && typeof root.showCXInfo === 'function') root.showCXInfo(); } catch (er) {}
    });
  }

  // Header search → the engine's own search box and FIND button (identical code path to typing there)
  var qf = $('xsQ');
  function find(v) {
    v = String(v == null ? '' : v).trim(); var box = $('searchIn'); if (!v || !box) return;
    box.value = v;
    var btn = box.parentNode.querySelector('button'); if (btn) btn.click(); else if (typeof root.doSearch === 'function') root.doSearch();
    // the engine opens #detailPanel asynchronously (after its own RPC): wait until it is really on the page, then bring it into
    // view (owner P0, 4 Nov 2026: «Open address» used to scroll before the panel existed, so the result appeared out of sight)
    var dp = $('detailPanel'), t0 = Date.now();
    (function wait() { if (dp && dp.offsetHeight > 0) { dp.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }); return; }
      if (Date.now() - t0 < 8000) setTimeout(wait, 120); else { var t = $('xsFind'); if (t) t.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }); } })();
  }
  if (qf) qf.addEventListener('submit', function (e) { e.preventDefault(); find(qf.querySelector('input').value || ''); });
  // INSPECT → the engine's own inspector (#ainAddr + ainInspect), same code path; result renders in #ainOut
  function inspect(v) {
    v = String(v == null ? '' : v).trim(); var box = $('ainAddr'); if (!v || !box) return;
    box.value = v; if (typeof root.ainInspect === 'function') root.ainInspect();
    var out = $('ainOut'); setTimeout(function () { if (out) out.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }); }, 60);
  }
  var qi = $('xsQi'); if (qi && qf) qi.addEventListener('click', function () { inspect(qf.querySelector('input').value || ''); });

  // HIDE NAV / SHOW NAV (owner P0, 5 Nov 2026): hides ALL navigation (header, brand, global menu, tools, header search, FIND /
  // INSPECT, Ctrl K, section row, sub-anchors, open menus) with no reserved space; one small floating SHOW NAV restores it. No reload:
  // the observatory, charts, search results and filters are untouched. Preference in localStorage (applied before first paint by
  // the inline <head> script). Keyboard: the buttons, and Alt+N anywhere.
  var nt = $('xsNavT'), ns = $('xsNavShow'), hd = $('xsHead');
  var lastHead = -1;   // a root custom property restyles the whole document: write it only when the height really changes
  function headH(h) { if (!hd) return; h = de.classList.contains('xs-navoff') ? 0 : typeof h === 'number' ? h : hd.offsetHeight; if (!h && !de.classList.contains('xs-navoff')) return; h = Math.round(h); if (h === lastHead) return; lastHead = h; de.style.setProperty('--xs-head', h + 'px'); }
  function closeMenus() { closeHelp(); var un = $('uNav'); if (un && (un.classList.contains('open') || un.querySelector('.nv-b[aria-expanded="true"]'))) d.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));   // u-nav.js?v=rs20261112g closeNav()
    var kp = d.querySelector('dialog.kpal'); if (kp && kp.open) try { kp.close(); } catch (e) {} }
  function anchorEl() {   // the first in-flow top-level block still visible under the header line (fixed / sticky layers excluded)
    var y = hd && !de.classList.contains('xs-navoff') ? hd.getBoundingClientRect().bottom : 0, k = d.body.children;
    for (var i = 0; i < k.length; i++) { var e = k[i]; if (e === hd || /^(SCRIPT|STYLE|LINK|TEMPLATE)$/.test(e.tagName)) continue; var cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.position === 'fixed' || cs.position === 'sticky' || cs.position === 'absolute') continue;
      var r = e.getBoundingClientRect(); if (r.height && r.bottom > y + 4) return e; }
    return null;
  }
  function navState(off, save, focus) {
    if (off && de.classList.contains('xs-navoff') === false) closeMenus();
    // keep what the reader looks at in place: measure one visible anchor before and after (the browser's own scroll anchoring
    // is not relied on: it differs between engines and with the sticky header)
    var change = off !== de.classList.contains('xs-navoff'), an = change && root.scrollY > 0 ? anchorEl() : null, a0 = an ? an.getBoundingClientRect().top : 0;   // no layout read at start-up
    de.classList.toggle('xs-navoff', off);
    if (nt) nt.setAttribute('aria-pressed', String(off));
    if (ns) ns.setAttribute('aria-expanded', String(!off));
    headH();
    if (an && root.scrollY > 0) { var dy = an.getBoundingClientRect().top - a0; if (Math.abs(dy) > 1) root.scrollBy(0, dy); }
    if (save) { try { localStorage.setItem('sost_xs_nav', off ? 'off' : 'on'); } catch (e) {} }
    if (focus) { var f = off ? ns : nt; if (f) try { f.focus({ preventScroll: true }); } catch (e) {} }
  }
  navState(de.classList.contains('xs-navoff'), false);
  if (nt) nt.addEventListener('click', function () { navState(true, true, true); });
  if (ns) ns.addEventListener('click', function () { navState(false, true, true); });
  d.addEventListener('keydown', function (e) { if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'n' || e.key === 'N' || e.code === 'KeyN')) { e.preventDefault(); navState(!de.classList.contains('xs-navoff'), true, true); } });
  // while hidden, Ctrl/Cmd+K is navigation too: it does nothing
  d.addEventListener('keydown', function (e) { if (de.classList.contains('xs-navoff') && (e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) { e.stopImmediatePropagation(); e.preventDefault(); } }, true);
  if (hd && 'ResizeObserver' in root) new ResizeObserver(function (es) { var b = es[0].borderBoxSize && es[0].borderBoxSize[0]; headH(b ? b.blockSize : undefined); }).observe(hd); else { headH(); addEventListener('load', function () { headH(); }, { once: true }); }

  // ---------- 4. compact network-status strip (copies of the engine's own figures) ----------
  var STRIP = [['sHeight', 'dHeight'], ['sAvg', 'dAvgTime'], ['sNext', 'dCountdown'], ['sMiners', 'dMiners'], ['sSupply', 'dSupply'], ['sMempool', 'dMempool'], ['sJack', 'dJackReserve']];
  var lastChange = 0;
  function mirror(dst, src) {
    var a = $(dst), b = $(src); if (!a || !b) return;
    function upd() { var t = txt(b) || '—'; if (a.textContent !== t) { a.textContent = t; if (t !== '—') { lastChange = Date.now(); if (!RM) { a.classList.add('tick'); setTimeout(function () { a.classList.remove('tick'); }, 700); } } } }
    upd(); new MutationObserver(upd).observe(b, { childList: true, characterData: true, subtree: true });
  }
  STRIP.forEach(function (p) { mirror(p[0], p[1]); });
  var stDot = $('sDot'), stTx = $('sState'), off = $('offBanner');
  function state() {
    if (!stDot) return;
    var offline = off && getComputedStyle(off).display !== 'none' && off.offsetHeight > 0;
    var has = /\d/.test(txt($('dHeight')));
    var age = lastChange ? Math.round((Date.now() - lastChange) / 1000) : null;
    stDot.className = 'xs-dot ' + (offline ? 'off' : has ? 'live' : 'wait');
    stTx.textContent = offline ? 'node unreachable' : has ? ('synced' + (age == null ? '' : ' · ' + (age < 60 ? age + 's' : Math.floor(age / 60) + 'm'))) : 'loading…';
  }
  state(); setInterval(state, 1000);

  // gentle highlight when an engine card value changes (class toggle only; text untouched)
  if (!RM) d.querySelectorAll('#dashboard .dash-val').forEach(function (v) {
    var prev = txt(v);
    new MutationObserver(function () { var t = txt(v); if (t !== prev && prev && /\d/.test(prev)) { v.classList.remove('xs-tick'); void v.offsetWidth; v.classList.add('xs-tick'); } prev = t; }).observe(v, { childList: true, characterData: true, subtree: true });
  });

  // ---------- 5. notices: one compact group (content and scripts unchanged). Owner order 13-Nov-2026: the H-01 security notice
  // lives inside this group (static HTML); its red chip is always visible in the summary and opens the full text + history ----------
  (function () {
    var host = $('xsNotices'), body = host && host.querySelector('.xs-nbody'), chips = host && host.querySelector('.xs-chips'); if (!host) return;
    var items = [], sec = body.querySelector('.xs-h01') ? 1 : 0;
    function add(el, label) { if (el && el.parentNode && !host.contains(el)) { body.appendChild(el); items.push(label); } }
    function wrapOf(el) { while (el && el.parentNode !== d.body) el = el.parentNode; return el; }
    // 14-Nov-2026 (owner order V17): the network-upgrade banner is NOT folded into this group — it stays visible right below it
    var v17m = $('sost-v16-notice-mount'); if (v17m && host.parentNode) { host.parentNode.insertBefore(v17m, host.nextSibling); v17m.style.margin = '8px auto 0';   /* keeps its own 0 24px padding: aligned with the cards */ }
    var dev = $('devNoteBody'); add(dev && wrapOf(dev), 'Developer note');
    d.querySelectorAll('body > div > details > summary').forEach(function (s) { if (/official SOST community/i.test(s.textContent)) add(s.parentNode.parentNode, 'Community channels'); });
    chips.innerHTML = (sec ? '<span class="xs-chip" style="color:#ffb3b3;border-color:#fb010d;background:#2a0606">&#9940; Security notice · H-01</span>' : '') +
      items.map(function (t) { return '<span class="xs-chip">' + t + '</span>'; }).join('');
    host.hidden = !(items.length + sec);
    de.classList.add('xs-ready');   // releases the pre-hide of x-shell.css (no layout shift: these blocks never occupy the top of the page)
  })();
  // HIDE NAV covers the whole top area (owner P0 14-Nov-2026): every top-level block placed before the FIND row, except the
  // header (already hidden), the statistics strip and fixed / sticky layers (toasts, overlays), is marked .xs-top; x-shell.css
  // hides .xs-top only under html.xs-navoff. Re-marked when scripts add blocks to <body> later (e.g. a site banner).
  (function () {
    var fr = $('xsFind'); if (!fr || fr.parentNode !== d.body) return;
    function mark() {
      for (var e = d.body.firstElementChild; e && e !== fr; e = e.nextElementSibling) {
        if (e === hd || e === ns || /^(SCRIPT|STYLE|LINK|TEMPLATE|NOSCRIPT)$/.test(e.tagName) || e.classList.contains('xs-strip') || e.classList.contains('xs-top')) continue;
        var p = getComputedStyle(e).position; if (p === 'fixed' || p === 'sticky') continue;
        e.classList.add('xs-top');
      }
    }
    mark(); if ('MutationObserver' in root) new MutationObserver(mark).observe(d.body, { childList: true });
  })();

  // ---------- 6. footer: site directory + every link of the previous Explorer menu ----------
  var dir = $('xsDir'); if (dir && U.nav) { try { U.nav.directory(dir); } catch (e) {} }
  var vc = $('vcx-sost'), vh = $('xsVisits'); if (vc && vh) vh.appendChild(vc);

  // ---------- 7. version 2: integrated live console (Control Room renderer, unmodified) ----------
  var consoleLoaded = false;
  function loadConsole() {
    if (V1 || consoleLoaded || !$('xsConsole')) return; consoleLoaded = true;
    var files = ['control-room/state.js?v=3', 'control-room/adapter.js?v=3', 'control-room/ui.js?v=5'];
    (function next(i) { if (i >= files.length) return; var s = d.createElement('script'); s.src = files[i]; s.onload = function () { next(i + 1); }; d.body.appendChild(s); })(0);
  }
  var con = $('xsConsole'), hist = $('xsHistorical');
  if (V1) { if (con) con.remove(); if (hist) hist.remove(); var ob1 = $('xsObs'); if (ob1) ob1.remove(); ['mining', 'addresses'].forEach(function (k) { map[k] = map[k].filter(function (x) { return x[0] !== 'xsObs'; }); }); map.overview = map.overview.filter(function (a) { return a[0] !== 'xsConsole'; }); var adv = d.querySelector('#xsTabs a[data-sec="advanced"]'); if (adv) adv.hidden = true; buildSpy(); de.classList.add('xs-v1'); }
  else if (con) {
    if (/^#xs(Console|Historical)$/.test(location.hash)) loadConsole();
    if ('IntersectionObserver' in root) { var io = new IntersectionObserver(function (es) { if (es.some(function (x) { return x.isIntersecting; })) { io.disconnect(); loadConsole(); } }, { rootMargin: '120px 0px' }); io.observe(con); if (hist) io.observe(hist); }
    else addEventListener('load', function () { idle(loadConsole, 4000); }, { once: true });
  }
  // ---------- 8. Galaxy Mining Observatory (4J §2): x-galaxy.js loads when the panel is about to be seen ----------
  var obs = $('xsObs'), galLoaded = false;
  function loadGalaxy() { if (galLoaded || !obs) return; galLoaded = true; var s = d.createElement('script'); s.src = 'universe/explorer-shell/x-galaxy.js?v=gxfx50-20261116'; d.body.appendChild(s); }
  if (obs) {
    if (location.hash === '#galaxy') setTimeout(function () { openGalaxy(); }, 60);
    // ?galaxy=1206|genesis|24|72|144|288: a direct link to the Galaxy view (owner order 15-Nov-2026)
    if (/[?&]galaxy=(1206|all|recent|genesis|full|24|72|144|288)(&|$)/i.test(location.search) && !location.hash) { loadGalaxy(); setTimeout(function () { if (obs) obs.scrollIntoView({ block: 'start' }); }, 400); }
    if (location.hash === '#xsObs' || /^#(obs=sost1|blk=\d)/i.test(location.hash)) { loadGalaxy(); if (/^#(obs|blk)=/.test(location.hash)) setTimeout(function () { if (obs) obs.scrollIntoView({ block: 'start' }); }, 400); }
    if ('IntersectionObserver' in root) { var io2 = new IntersectionObserver(function (es) { if (es.some(function (x) { return x.isIntersecting; })) { io2.disconnect(); loadGalaxy(); } }, { rootMargin: '300px 0px' }); io2.observe(obs); }
    else addEventListener('load', function () { idle(loadGalaxy, 4000); }, { once: true });
  }
  // ---------- P0: the engine's clickable identifiers (spans with onclick: heights, hashes, txids, addresses) become keyboard links ----------
  var LINKY = '.td-link,.td-hash,.td-height,.v-hash';
  function linky(el) { var l = (el || d).querySelectorAll(LINKY + ':not([tabindex])'); for (var i = 0; i < l.length; i++) { if (!l[i].onclick && !l[i].getAttribute('onclick')) continue; l[i].setAttribute('tabindex', '0'); l[i].setAttribute('role', 'link'); } }
  d.addEventListener('keydown', function (e) { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches(LINKY) && e.target.getAttribute('role') === 'link') { e.preventDefault(); e.target.click(); } });
  // started by the first Tab key only: mouse and touch visitors pay nothing (no attribute writes on every engine re-render)
  var linkyOn = false;
  d.addEventListener('keydown', function (e) { if (linkyOn || e.key !== 'Tab') return; linkyOn = true; linky();
    if ('MutationObserver' in root) { var lq = 0; new MutationObserver(function () { if (lq) return; lq = setTimeout(function () { lq = 0; linky(); }, 250); }).observe(d.body, { childList: true, subtree: true }); } });
  U.explorerShell = { version: V1 ? 1 : 2, loadConsole: loadConsole, loadGalaxy: loadGalaxy, openGalaxy: openGalaxy, find: find, sections: map, nav: navState };
})(window);

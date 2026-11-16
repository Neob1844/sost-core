/* SOST Explorer — Phase 4b hybrid layer (AJUSTE DIRECCIÓN ARTÍSTICA 1 §4). Runs on top of u-explorer.js (Explorer 2.0):
 * same SOSTU.data subscription (no extra fetch, 0 RPC), same ids, same parity rows. Adds only presentation:
 *   - branded hero tip counter, search hints from the real series;
 *   - chain strip of the latest 8 blocks as cards, with an arrival animation on a genuinely new block (never on a replay);
 *   - classic producer donut (last 288 of the series, model M.producers — the same function the parity test checks);
 *   - value-change flash on the dashboard cards;
 *   - look switch CLASSIC / CONSOLE / CONSTELLATION (?look=… or localStorage); the constellation canvas renders only while
 *     visible and on screen, stops when the tab is hidden, draws one static frame under prefers-reduced-motion.
 */
(function (root) {
  'use strict';
  var U = root.SOSTU, UI = U.ui, M = U.xmodel, D = U.data;
  var $ = function (i) { return document.getElementById(i); };
  var RM = UI.RM, PAL = ['#22d3ee', '#e879f9', '#a3e635', '#facc15', '#fb923c', '#8b5cf6', '#3b82f6', '#4ade80'], OTHER = '#64748b';
  var last = null, prevTip = null, prevCards = [], colorOf = {}, look = 'classic';
  function esc(x) { return UI.esc(x); }
  function lab(s) { return s.status === 'live' ? '<span class="tag live">LIVE</span>' : '<span class="tag nl">LAST KNOWN · ' + String(s.status).toUpperCase() + '</span>'; }

  // ---------- look switch
  function setLook(l, save) {
    look = l; document.body.classList.toggle('look-console', l === 'console'); document.body.classList.toggle('look-constel', l === 'constel');
    $('pConst').hidden = l !== 'constel';
    [].forEach.call(document.querySelectorAll('[data-look]'), function (b) { b.setAttribute('aria-pressed', String(b.dataset.look === l)); });
    if (save) try { localStorage.setItem('sostx_look', l); } catch (e) {}
    if (l === 'constel') C.start(); else C.stop();
  }

  // ---------- hero + hints
  function hero(s) {
    var h = s.state.meta.height, a = $('xTip');
    a.textContent = '#' + UI.num(h); a.href = '#search=' + h;
    $('xTipS').innerHTML = lab(s) + ' tip age ' + UI.dur(s.state.active.chain.tipAge.value) + ' · Equalizer ' + esc(s.state.active.consensus.equalizerNext.value || '—');
    if (prevTip != null && h !== prevTip && !s.replay) { a.classList.remove('xflash'); void a.offsetWidth; a.classList.add('xflash'); }
    var r = s.rows[s.rows.length - 1], top = s.rows.length ? s.rows[s.rows.length - 1].miner : null;
    $('xHint').innerHTML = 'Try: <a href="#search=' + h + '">#' + UI.num(h) + ' (tip)</a>' + (r && r.hash ? '<a href="#search=' + esc(r.hash) + '">tip hash</a>' : '') + (top ? '<a href="#search=' + esc(top) + '">' + esc(UI.short(top)) + ' (latest producer)</a>' : '') + '<a href="#view=advanced&amp;panel=jackpot">next Jackpot</a><span>· Ctrl/⌘ K anywhere</span>';
  }

  // ---------- chain strip
  function strip(s) {
    var rs = s.rows.slice(-8).reverse(), fresh = s.newBlocks && s.newBlocks.length && !s.replay && prevTip != null;
    $('xTrack').innerHTML = rs.map(function (r, i) {
      var c = colorOf[r.miner] || OTHER, jp = M.isJackpot(r.h);
      return '<a class="xb' + (i === 0 ? ' tip' : '') + (jp ? ' jp' : '') + (fresh && i === 0 ? ' new' : '') + '" style="--c:' + c + '" href="#search=' + r.h + '" aria-label="Block ' + r.h + '">' +
        '<span class="t">' + (i === 0 ? 'TIP' : jp ? '◆ JACKPOT' : 'BLOCK') + '</span><span class="h">#' + UI.num(r.h) + '</span>' +
        '<span class="r"><span>interval</span><b>' + UI.dur(r.dt) + '</b></span><span class="r"><span>Equalizer</span><b>' + esc(M.profName(r.prof)) + '</b></span>' +
        '<span class="r"><span>bitsQ</span><b>' + UI.num(r.bq) + '</b></span><span class="who"><i></i>' + esc(UI.short(r.miner)) + '</span></a>';
    }).join('');
  }

  // ---------- producer donut (classic)
  function donut(s) {
    var p = M.producers(s.rows.map(function (r) { return { h: r.h, m: r.miner }; }), 288), a0 = -Math.PI / 2, R = 104, r0 = 64, cx = 120, cy = 120, segs = '';
    $('distTag').innerHTML = '<span class="tag win">WINDOW · ' + p.n + (s.status !== 'live' ? ' · ' + String(s.status).toUpperCase() : '') + '</span>';
    var items = p.list.slice(0, 8).map(function (x, i) { return { a: x.addr, v: x.blocks, sh: x.share, c: PAL[i], last: x.last }; });
    var rest = p.list.slice(8).reduce(function (t, x) { return t + x.blocks; }, 0); if (rest) items.push({ a: null, v: rest, sh: rest / p.n * 100, c: OTHER });
    items.forEach(function (it) {
      var a1 = a0 + it.v / p.n * Math.PI * 2, big = a1 - a0 > Math.PI ? 1 : 0, f = function (r, a) { return (cx + r * Math.cos(a)).toFixed(2) + ' ' + (cy + r * Math.sin(a)).toFixed(2); };
      if (it.v === p.n) segs += '<circle cx="120" cy="120" r="84" fill="none" stroke="' + it.c + '" stroke-width="40"/>';
      else segs += '<path d="M' + f(R, a0) + 'A' + R + ' ' + R + ' 0 ' + big + ' 1 ' + f(R, a1) + 'L' + f(r0, a1) + 'A' + r0 + ' ' + r0 + ' 0 ' + big + ' 0 ' + f(r0, a0) + 'Z" fill="' + it.c + '" stroke="#000" stroke-width="1.5"><title>' + esc(it.a ? UI.short(it.a) : 'others') + ': ' + it.sh.toFixed(1) + ' %</title></path>';
      a0 = a1;
    });
    $('distSvg').innerHTML = '<circle cx="120" cy="120" r="112" fill="none" stroke="#fb010d55"/>' + segs + '<circle cx="120" cy="120" r="58" fill="#050102"/><text x="120" y="114" text-anchor="middle" fill="#fff" font-family="ui-monospace,monospace" font-size="24" font-weight="700">' + p.unique + '</text><text x="120" y="134" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="10">addresses · ' + p.n + ' blocks</text>';
    $('distTbl').innerHTML = '<table class="tbl"><thead><tr><th>#</th><th>Producer address</th><th class="r">Blocks</th><th class="r">Share</th><th>Last block</th></tr></thead><tbody>' +
      items.map(function (it, i) { return '<tr><td><svg width="9" height="9" aria-hidden="true"><rect width="9" height="9" fill="' + it.c + '"/></svg> ' + (it.a ? i + 1 : '') + '</td><td>' + (it.a ? '<a class="bl addr" href="#search=' + esc(it.a) + '" title="' + esc(it.a) + '">' + esc(UI.short(it.a)) + '</a>' : 'others (' + (p.unique - 8) + ')') + '</td><td class="r">' + UI.num(it.v) + '</td><td class="r">' + it.sh.toFixed(2) + ' %</td><td>' + (it.last ? '<a class="bl" href="#search=' + it.last + '">#' + UI.num(it.last) + '</a>' : '—') + '</td></tr>'; }).join('') + '</tbody></table>';
  }

  // ---------- dashboard value flash (only values that changed between two real snapshots)
  function flashCards(s) {
    var cs = document.querySelectorAll('#cards .c'), now = [].map.call(cs, function (c) { var n = c.querySelector('.n'); return n ? n.textContent : ''; });
    if (prevCards.length && !s.replay) cs.forEach(function (c, i) { if (now[i] !== prevCards[i]) { c.classList.remove('upd'); void c.offsetWidth; c.classList.add('upd'); } });
    prevCards = now;
  }

  // ---------- constellation (Canvas 2D, on demand)
  var C = (function () {
    var cv = $('constCv'), ctx = null, raf = 0, on = false, vis = true, stars = [], hover = -1, t0 = performance.now(), W = 0, H = 0, dpr = 1, pulseAt = -1e9;
    function layout() {
      var r = cv.getBoundingClientRect(); dpr = Math.min(root.devicePixelRatio || 1, 1.75); W = r.width; H = r.height; cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      if (!ctx) ctx = cv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); build();
    }
    function build() {
      if (!last) return; var rs = last.rows.slice(-288).reverse(), n = rs.length, cx = W / 2, cy = H / 2, maxR = Math.min(W, H) * .47;
      stars = rs.map(function (r, i) { var u = i / Math.max(1, n - 1), ang = i * 2.399963 * .55, rad = 14 + Math.sqrt(u) * maxR;
        return { r: r, ang: ang, rad: rad, sz: 1.6 + 3.4 * Math.sqrt(Math.min(r.dt || 600, 3600) / 3600) + (i === 0 ? 3 : 0), c: colorOf[r.miner] || OTHER, j: M.isJackpot(r.h), cx: cx, cy: cy }; });
    }
    function pos(s, rot) { var a = s.ang + rot; return [s.cx + Math.cos(a) * s.rad, s.cy + Math.sin(a) * s.rad * .72]; }
    function draw(now) {
      var t = (now - t0) / 1000, rot = RM ? 0 : t * .03; ctx.clearRect(0, 0, W, H);
      var ps = stars.map(function (s) { return pos(s, rot); });
      ctx.globalCompositeOperation = 'lighter';
      ctx.strokeStyle = '#fb010d'; ctx.lineWidth = 1; ctx.globalAlpha = .28; ctx.beginPath();
      ps.forEach(function (p, i) { if (i) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); }); ctx.stroke();
      for (var i = stars.length - 1; i >= 0; i--) {
        var s = stars[i], p = ps[i], tw = RM ? 1 : .75 + .25 * Math.sin(t * 2 + i * 1.7), sz = s.sz * (i === hover ? 1.8 : 1);
        ctx.globalAlpha = .18 * tw; ctx.fillStyle = s.c; ctx.beginPath(); ctx.arc(p[0], p[1], sz * 3.2, 0, 7); ctx.fill();
        ctx.globalAlpha = .95 * tw;
        if (s.j) { ctx.beginPath(); ctx.moveTo(p[0], p[1] - sz * 1.8); ctx.lineTo(p[0] + sz * 1.3, p[1]); ctx.lineTo(p[0], p[1] + sz * 1.8); ctx.lineTo(p[0] - sz * 1.3, p[1]); ctx.closePath(); ctx.fillStyle = '#facc15'; ctx.fill(); }
        else { ctx.fillStyle = s.c; ctx.beginPath(); ctx.arc(p[0], p[1], sz, 0, 7); ctx.fill(); }
      }
      // the tip: SOST-red core with a pulse when a real new block arrives
      if (ps.length) { var p0 = ps[0], k = Math.max(0, 1 - (now - pulseAt) / 1600);
        ctx.globalAlpha = 1; ctx.strokeStyle = '#ff2d3b'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p0[0], p0[1], 11 + (RM ? 0 : Math.sin(t * 3) * 1.5), 0, 7); ctx.stroke();
        if (k > 0) { ctx.globalAlpha = k; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(p0[0], p0[1], 11 + (1 - k) * 120, 0, 7); ctx.stroke(); } }
      ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1;
      C.ps = ps;
    }
    function loop(now) { raf = 0; if (!on || !vis || document.hidden) return; draw(now); if (!RM) raf = requestAnimationFrame(loop); }
    function kick() { if (!raf && on) raf = requestAnimationFrame(loop); }
    function start() { if (!last) return; on = true; layout(); kick(); }
    function stop() { on = false; if (raf) cancelAnimationFrame(raf); raf = 0; }
    function pick(e) { var r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, best = -1, bd = 400; (C.ps || []).forEach(function (p, i) { var d = (p[0] - x) * (p[0] - x) + (p[1] - y) * (p[1] - y); if (d < bd) { bd = d; best = i; } }); return best; }
    cv.addEventListener('pointermove', function (e) {
      var i = pick(e), tip = $('constTip'); hover = i;
      if (i < 0) { tip.hidden = true; cv.style.cursor = 'crosshair'; } else { var s = stars[i].r, p = C.ps[i]; tip.hidden = false; cv.style.cursor = 'pointer';
        tip.innerHTML = '<b>#' + UI.num(s.h) + '</b>' + (M.isJackpot(s.h) ? ' ◆ Jackpot height' : '') + '<br>interval ' + UI.dur(s.dt) + ' · ' + esc(M.profName(s.prof)) + '<br>' + esc(UI.short(s.miner));
        tip.style.left = Math.min(p[0] + 14, cv.clientWidth - 220) + 'px'; tip.style.top = Math.max(0, p[1] - 30) + 'px'; }
      if (RM) draw(performance.now());
    });
    cv.addEventListener('pointerleave', function () { hover = -1; $('constTip').hidden = true; });
    cv.addEventListener('click', function (e) { var i = pick(e); if (i >= 0) location.hash = 'search=' + stars[i].r.h; });
    if (root.IntersectionObserver) new IntersectionObserver(function (es) { vis = es[0].isIntersecting; if (vis) kick(); }).observe(cv);
    document.addEventListener('visibilitychange', kick);
    var rz = 0; addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { if (on) { layout(); kick(); } }, 150); });
    return { start: start, stop: stop, update: function (fresh) { if (!on) return; build(); if (fresh) pulseAt = performance.now(); if (RM) draw(performance.now()); else kick(); }, get on() { return on; } };
  })();

  function legend() {
    var p = M.producers(last.rows.map(function (r) { return { h: r.h, m: r.miner }; }), 288);
    $('constLeg').innerHTML = p.list.slice(0, 8).map(function (x, i) { return '<span><i style="background:' + PAL[i] + '"></i>' + esc(UI.short(x.addr)) + ' ' + x.share.toFixed(1) + ' %</span>'; }).join('') + '<span><i style="background:' + OTHER + '"></i>others</span><span><i style="background:#facc15;transform:rotate(45deg)"></i>Jackpot height</span>';
    $('constTag').innerHTML = '<span class="tag win">WINDOW · ' + Math.min(288, last.rows.length) + (last.status !== 'live' ? ' · ' + String(last.status).toUpperCase() : '') + '</span>';
  }

  function onSnap(s) {
    if (!s.state) return; last = s;
    var p = M.producers(s.rows.map(function (r) { return { h: r.h, m: r.miner }; }), 288); colorOf = {}; p.list.forEach(function (x, i) { colorOf[x.addr] = i < PAL.length ? PAL[i] : OTHER; });
    var fresh = s.newBlocks && s.newBlocks.length && !s.replay && prevTip != null;
    hero(s); strip(s); donut(s); flashCards(s); legend(); C.update(fresh);
    prevTip = s.state.meta.height;
  }
  // bind
  [].forEach.call(document.querySelectorAll('[data-look]'), function (b) { b.onclick = function () { setLook(b.dataset.look, true); }; });
  var q = new URLSearchParams(location.search).get('look'), saved = null; try { saved = localStorage.getItem('sostx_look'); } catch (e) {}
  D.subscribe(function (s) { onSnap(s); if (!setLook.done && s.state) { setLook.done = true; setLook(/^(classic|console|constel)$/.test(q || '') ? q : saved || 'classic', false); } });
  U.explorerX = { setLook: setLook, constellation: C };
})(window);

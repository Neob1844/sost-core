/* ============================================================================
 * SOST ConvergenceX Control Room — explorer dashboard card
 * ----------------------------------------------------------------------------
 * One 288-block window, four linked panels on a shared x-axis:
 *   1. SCHEDULE LAG -> EQUALIZER : how far the chain is ahead of the 600 s schedule and
 *      the Equalizer profile the node selected for each block. The panel recomputes the
 *      consensus selection (direct lag map, ceiling H35, V12 triangular cascade) and
 *      shows live how many blocks in view it reproduces exactly.
 *   2. BLOCK INTERVALS : time since the previous block, coloured by producer (or by
 *      timing band), with the consensus thresholds drawn as reference lines.
 *   3. DIFFICULTY ENGINE (bitsQ) : the avg288 deviation the node uses for bitsQ, drawn
 *      against the dead band (+/-15 s) and the 0.5/1/2/3 % step bands, plus bitsQ itself.
 *   4. BURST & VOLATILITY : rolling 72-interval burst (% < 5 min) and stdev/600.
 * Every number comes from public block data (time, bits_q, casert_profile_index,
 * miner_address); nothing is simulated.
 *
 * Data: /api/block_series.json (last 1,200 blocks, refreshed every 5 min by the
 * read-only ops/dtd-history-snapshot.py) merged with window._diffHistory (the
 * explorer's live 288-block buffer), so the warm-up windows (avg288 needs 288
 * earlier blocks, the 72-block rolling stats need 72) are always full.
 * ========================================================================== */
(function () {
  'use strict';
  var GENESIS_TIME = 1773597600, SPACING = 600, VIEW = 288, H_MAX = 35, E_MIN = -7;
  var series = null, seriesAt = 0, seriesBusy = false;
  var rows = [], lastTip = 0, crossIdx = -1, colorMode = 'timing';
  var anim = { k: 0, start: 0 }, rafId = 0;
  var mount, chipsEl, readEl, storyEl, legEl, panels = [], built = false;
  try { var cm = localStorage.getItem('sost_cr_color'); if (cm === 'miner') colorMode = 'miner'; } catch (e) {}

  /* -- shared helpers (same producer colours as the Network Mosaic) --------- */
  function hashHue(s) {
    s = s || 'unknown';
    var h = 5381;
    for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
    return ((h % 360) + 360) % 360;
  }
  window.sostProducerColor = function (addr, l) { return 'hsl(' + hashHue(addr) + ',66%,' + (l || 54) + '%)'; };
  function profName(p) { return p == null ? '—' : (p < 0 ? 'E' + (-p) : (p === 0 ? 'B0' : 'H' + p)); }
  function profColor(p, l) {
    p = p || 0;
    var hue = p <= 0 ? 150 + (-p / 7) * 70 : 150 - Math.min(1, p / 35) * 150;
    return 'hsl(' + Math.round(hue) + ',72%,' + (l || 50) + '%)';
  }
  function timingColor(dt) {
    if (dt == null) return '#444';
    if (dt < 300) return '#38bdf8';
    if (dt < 900) return '#22c55e';
    if (dt < 1800) return '#eab308';
    if (dt < 3600) return '#f97316';
    return '#ef4444';
  }
  function fmtDur(s) {
    if (s == null || isNaN(s)) return '—';
    var neg = s < 0; s = Math.abs(Math.round(s));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    var out = h ? (h + 'h ' + (m < 10 ? '0' : '') + m + 'm') : (m ? (m + 'm ' + (r < 10 ? '0' : '') + r + 's') : (r + 's'));
    return (neg ? '−' : '') + out;
  }
  function shortA(a) { return a ? a.slice(0, 10) + '…' + a.slice(-4) : 'unknown'; }
  function el(tag, css, html) { var e = document.createElement(tag); if (css) e.style.cssText = css; if (html != null) e.innerHTML = html; return e; }

  /* -- data --------------------------------------------------------------- */
  function fetchSeries(force) {
    if (seriesBusy || (!force && series && Date.now() - seriesAt < 240000)) return;
    seriesBusy = true;
    fetch('api/block_series.json?t=' + Math.floor(Date.now() / 60000), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j && j.rows && j.rows.length) { series = j; seriesAt = Date.now(); window.__sostSeriesRows = j.rows; refresh(); } })
      .catch(function () {})
      .then(function () { seriesBusy = false; });
  }
  function assemble() {
    var map = {}, k;
    if (series) series.rows.forEach(function (r) { map[r[0]] = { h: r[0], t: r[1], d: r[2], p: r[3], m: r[4] || '' }; });
    (window._diffHistory || []).forEach(function (b) {
      if (!b || b.h == null) return;
      var o = map[b.h] || {};
      map[b.h] = { h: b.h, t: b.t, d: b.d, p: (b.p != null ? b.p : o.p), m: b.miner || o.m || '' };
    });
    var hs = Object.keys(map).map(Number).sort(function (a, b) { return a - b; });
    var arr = [];
    for (k = hs.length - 1; k >= 0; k--) { if (arr.length && hs[k] !== arr[0].h - 1) break; arr.unshift(map[hs[k]]); }
    return arr;
  }
  function derive(arr) {
    var n = arr.length, out = [];
    if (n < 3) return out;
    // prefix sums of consensus-clamped intervals (clamp(dt, 1, 86400)) for avg288
    var pre = [0];
    for (var i = 1; i < n; i++) { var c = Math.min(Math.max(arr[i].t - arr[i - 1].t, 1), 86400); pre.push(pre[i - 1] + c); }
    var start = Math.max(1, n - VIEW);
    for (var k = start; k < n; k++) {
      var b = arr[k], pv = arr[k - 1], dt = b.t - pv.t;
      var lag = (b.h - 1) - Math.floor((pv.t - GENESIS_TIME) / SPACING);
      var base = lag <= 0 ? 0 : Math.min(lag, H_MAX), drop = 0;
      if (dt >= 540) { var nn = Math.min(1 + Math.floor((dt - 540) / 60), 7); drop = nn * (nn + 1) / 2; }
      var model = drop ? Math.max(E_MIN, base - drop) : base;
      var dev = null;
      if (k >= 288) { var cnt = 287, sum = pre[k - 1] - pre[k - 288]; dev = Math.floor(sum / cnt) - SPACING; }
      var burst = null, vol = null;
      if (k >= 72) {
        var bc = 0, s1 = 0, s2 = 0;
        for (var j = k - 71; j <= k; j++) { var x = arr[j].t - arr[j - 1].t; if (x < 300) bc++; s1 += x; s2 += x * x; }
        var mean = s1 / 72; burst = bc / 72 * 100; vol = Math.sqrt(Math.max(0, s2 / 72 - mean * mean)) / SPACING * 100;
      }
      out.push({ h: b.h, t: b.t, d: b.d, p: b.p, m: b.m, dt: dt, lag: lag, base: base, drop: drop, model: model,
                 match: (b.p != null) ? (b.p === model) : null, dev: dev, burst: burst, vol: vol,
                 dq: (pv.d ? (b.d - pv.d) / pv.d * 100 : 0) });
    }
    return out;
  }

  /* -- card --------------------------------------------------------------- */
  var CSS = '#convxCR{background:var(--bg2);border:1px solid var(--border);padding:14px 16px 12px;position:relative;overflow:hidden}' +
    '#convxCR:before{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(1200px 140px at 12% -40px,rgba(34,211,238,.07),transparent),radial-gradient(900px 120px at 90% -40px,rgba(192,132,252,.07),transparent)}' +
    '.cr-chip{display:inline-flex;flex-direction:column;gap:2px;padding:6px 10px;border:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.28);border-radius:3px;min-width:96px}' +
    '.cr-chip b{font-size:13px;letter-spacing:.3px}.cr-chip span{font-size:8px;letter-spacing:1.3px;color:var(--text3)}' +
    '.cr-chip.flash{animation:crFlash 1.1s ease-out}@keyframes crFlash{0%{box-shadow:0 0 0 0 rgba(34,211,238,.75);border-color:rgba(34,211,238,.9)}100%{box-shadow:0 0 0 14px rgba(34,211,238,0)}}' +
    '.cr-pt{font-size:8.5px;letter-spacing:1.6px;color:var(--text3);display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin:12px 0 4px}' +
    '.cr-pt b{color:var(--text2);font-weight:700}.cr-pt i{font-style:normal;color:var(--text3);letter-spacing:.4px;font-size:8.5px}' +
    '.cr-cv{width:100%;display:block;cursor:crosshair;touch-action:pan-y}' +
    '.cr-btn{background:transparent;color:var(--text2);border:1px solid var(--border);font-family:var(--code);font-size:8px;letter-spacing:1.2px;padding:3px 8px;cursor:pointer;border-radius:2px}' +
    '.cr-btn.on{color:var(--cyan);border-color:var(--cyan);background:var(--bg4)}' +
    '#crRead{font-family:var(--code);font-size:10px;line-height:1.7;color:var(--text2);padding:7px 10px;border:1px solid rgba(255,255,255,.06);background:rgba(0,0,0,.35);border-radius:3px;margin-top:10px;min-height:36px}' +
    '#crRead .k{color:var(--text3)}';

  function build() {
    var anchor = document.getElementById('chartProdWrap');
    if (!anchor || document.getElementById('convxCRWrap')) return !!document.getElementById('convxCRWrap');
    var st = document.createElement('style'); st.id = 'convxCRCss';
    st.textContent = CSS + '#producerDistSection{max-width:1352px;margin:12px auto 0;background:var(--bg2);border:1px solid var(--border);padding:14px 16px;box-sizing:border-box}' +
      '@media(max-width:1400px){#producerDistSection{margin-left:24px;margin-right:24px}}@media(max-width:600px){#producerDistSection{margin-left:12px;margin-right:12px;padding:12px}}' +
      '#chartProdWrap,#chartBlockTimeWrap,#chartBurstWrap,.sparkline-wrap:not(.sparkline-wrap-5k-disabled){display:none!important}';
    document.head.appendChild(st);
    var wrap = el('div'); wrap.className = 'diff-bar-wrap'; wrap.id = 'convxCRWrap';
    mount = el('div'); mount.id = 'convxCR';
    wrap.appendChild(mount);
    anchor.parentNode.insertBefore(wrap, anchor);

    var head = el('div', 'display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px;position:relative');
    head.appendChild(el('div', '', '<div style="font-size:11px;letter-spacing:2px;color:var(--text3)">// <b style="color:var(--cyan)">CONVERGENCEX CONTROL ROOM</b></div>' +
      '<div style="font-size:9px;letter-spacing:.8px;color:var(--text3);margin-top:3px">last 288 blocks &middot; difficulty = bitsQ + Equalizer &middot; every value recomputed from public block data with the consensus rules</div>'));
    mount.appendChild(head);
    chipsEl = el('div', 'display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;position:relative');
    mount.appendChild(chipsEl);

    function panel(id, title, sub, h, hm) {
      var t = el('div', '', '<span><b>' + title + '</b> &nbsp;<i>' + sub + '</i></span><span id="' + id + 'Side"></span>'); t.className = 'cr-pt';
      var cv = document.createElement('canvas'); cv.className = 'cr-cv'; cv.id = id;
      mount.appendChild(t); mount.appendChild(cv);
      var P = { id: id, cv: cv, h: h, hm: hm, off: null, geo: null, draw: null };
      panels.push(P);
      bindCross(cv, P);
      return P;
    }
    var et = el('div', '', '<span><b>EQUALIZER</b> &nbsp;<i>how the chain sets the structural work of each block</i></span><span id="crLagSide"></span>'); et.className = 'cr-pt';
    mount.appendChild(et);
    storyEl = el('div', 'display:flex;flex-wrap:wrap;align-items:stretch;gap:6px;margin:4px 0 6px');
    mount.appendChild(storyEl);
    var sc = document.createElement('canvas'); sc.className = 'cr-cv'; sc.id = 'crScale'; sc.style.cursor = 'default';
    mount.appendChild(sc);
    var ps = { id: 'crScale', cv: sc, h: 92, hm: 92, off: null, geo: null, draw: drawScale, noX: true };
    panels.push(ps);
    var p1 = panel('crLag', 'SCHEDULE LAG', 'blocks ahead of the 600 s timetable &middot; this is what sets the Equalizer target', 96, 80);
    p1.draw = drawLag;
    var p2 = panel('crInt', 'BLOCK TIMES', 'how long each block took &middot; target 10 min', 150, 120); p2.draw = drawIntervals;
    legEl = el('div', 'display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;font-size:8.5px;color:var(--text3);margin:2px 0 0 0');
    mount.insertBefore(legEl, p2.cv);
    var rib = panel('crRib', 'PROFILE OF EACH BLOCK',
      'one slice per block, aligned with the block times above &middot; ' +
      '<span style="display:inline-block;vertical-align:middle;width:84px;height:7px;border-radius:2px;background:linear-gradient(90deg,' + profColor(-7, 50) + ',' + profColor(0, 50) + ',' + profColor(17, 50) + ',' + profColor(35, 50) + ')"></span> ' +
      'E7 easiest &middot; B0 &middot; H35 hardest &middot; long blocks get easier profiles', 22, 20);
    rib.draw = drawRibbon;
    var p3 = panel('crDiff', 'DIFFICULTY ENGINE &middot; bitsQ', 'avg288 deviation from 600 s (line) against the consensus step bands; gold = bitsQ', 140, 118); p3.draw = drawDiff;
    var p4 = panel('crBV', 'BURST &amp; VOLATILITY', 'rolling 72 intervals &middot; orange = % blocks &lt; 5 min &middot; cyan = stdev / 600 s', 110, 96); p4.draw = drawBV;
    readEl = el('div'); readEl.id = 'crRead'; mount.appendChild(readEl);
    mount.appendChild(el('div', 'font-size:8px;color:var(--text3);margin-top:8px;line-height:1.7',
      'Equalizer model = consensus direct lag map (#5,323+): target profile = B0 if lag &le; 0, else min(lag, H35); a block that took &ge; 9 min is eased by the V12 triangular cascade ' +
      '(1, 3, 6, 10, 15, 21, 28 levels at 9, 10, 11 … &ge; 15 min). bitsQ (#5,270+): mean of the last 287 clamped intervals; no change inside &plusmn;15 s, then 0.5 / 1 / 2 / 3 % per block. ' +
      'Data: node blocks via /api/block_series.json + the live explorer buffer. Hover / tap any panel &mdash; the same block lights up in every panel and in the Network Mosaic.'));
    built = true;
    return true;
  }

  /* -- geometry + painting -------------------------------------------------- */
  function geom(P) {
    var W = Math.max(240, P.cv.parentNode.clientWidth - 32 || 300);
    var mob = W < 560;
    var H = mob ? P.hm : P.h;
    var pad = { l: mob ? 30 : 42, r: mob ? 34 : 64, t: 6, b: P.id === 'crRib' ? 2 : 14 };
    if (P.id === 'crRib') { pad.t = 2; }
    var n = rows.length || 1, cw = W - pad.l - pad.r, colW = cw / n;
    return { W: W, H: H, pad: pad, n: n, cw: cw, ch: H - pad.t - pad.b, colW: colW, mob: mob, dpr: window.devicePixelRatio || 1 };
  }
  function xOf(G, i) { return G.pad.l + (i + 0.5) * G.colW; }
  function paintAll() {
    if (!built || !rows.length) return;
    for (var i = 0; i < panels.length; i++) {
      var P = panels[i], G = geom(P);
      P.geo = G;
      P.cv.width = Math.round(G.W * G.dpr); P.cv.height = Math.round(G.H * G.dpr); P.cv.style.height = G.H + 'px';
      P.off = document.createElement('canvas'); P.off.width = P.cv.width; P.off.height = P.cv.height;
      var c = P.off.getContext('2d'); c.setTransform(G.dpr, 0, 0, G.dpr, 0, 0);
      c.font = '8px "Fira Code",monospace';
      try { P.draw(c, G, P); } catch (e) { if (window.console) console.warn('[control-room]', P.id, e); }
    }
    blitAll(performance.now());
  }
  function gridY(c, G, y, label, col) {
    c.strokeStyle = col || 'rgba(255,255,255,.05)'; c.lineWidth = 1;
    c.beginPath(); c.moveTo(G.pad.l, y + 0.5); c.lineTo(G.W - G.pad.r, y + 0.5); c.stroke();
    if (label != null) { c.fillStyle = '#5b6473'; c.textAlign = 'right'; c.fillText(label, G.pad.l - 4, y + 3); }
  }

  function drawLag(c, G) {
    var lo = 0, hi = 4, i;
    rows.forEach(function (r) { lo = Math.min(lo, r.lag); hi = Math.max(hi, r.lag); });
    hi = Math.ceil((hi + 2) / 5) * 5; lo = Math.min(0, Math.floor(lo / 5) * 5);
    var Y = function (v) { return G.pad.t + G.ch - (v - lo) / (hi - lo) * G.ch; };
    gridY(c, G, Y(0), '0', 'rgba(255,255,255,.14)');
    gridY(c, G, Y(hi), '+' + hi);
    var grad = c.createLinearGradient(0, G.pad.t, 0, G.pad.t + G.ch);
    grad.addColorStop(0, 'rgba(34,211,238,.45)'); grad.addColorStop(1, 'rgba(34,211,238,.03)');
    c.beginPath(); c.moveTo(xOf(G, 0), Y(0));
    for (i = 0; i < rows.length; i++) c.lineTo(xOf(G, i), Y(rows[i].lag));
    c.lineTo(xOf(G, rows.length - 1), Y(0)); c.closePath(); c.fillStyle = grad; c.fill();
    c.beginPath(); for (i = 0; i < rows.length; i++) { var y = Y(rows[i].lag); if (i) c.lineTo(xOf(G, i), y); else c.moveTo(xOf(G, i), y); }
    c.strokeStyle = '#22d3ee'; c.lineWidth = 1.6; c.shadowColor = 'rgba(34,211,238,.7)'; c.shadowBlur = 6; c.stroke(); c.shadowBlur = 0;
    var last = rows[rows.length - 1];
    c.fillStyle = '#22d3ee'; c.textAlign = 'left'; c.font = 'bold 10px "Fira Code",monospace';
    c.fillText((last.lag > 0 ? '+' : '') + last.lag, G.W - G.pad.r + 5, Y(last.lag) + 4);
  }
  // Equalizer scale: E7 ... B0 ... H35, histogram of the profiles used in view,
  // target (from the schedule lag) and the profile the selected block was mined at.
  function drawScale(c, G) {
    var r = rows[crossIdx >= 0 ? crossIdx : rows.length - 1];
    var L = G.pad.l, R = G.W - G.pad.r, w = R - L, P0 = -7, P1 = 35;
    var X = function (p) { return L + (p - P0 + 0.5) / (P1 - P0 + 1) * w; };
    var cnt = {}, mx = 1, i;
    rows.forEach(function (x) { if (x.p != null) { cnt[x.p] = (cnt[x.p] || 0) + 1; mx = Math.max(mx, cnt[x.p]); } });
    var barY = G.mob ? 40 : 44, hh = barY - 14, cw = w / (P1 - P0 + 1);
    for (var p = P0; p <= P1; p++) {
      var v = cnt[p] || 0; if (!v) continue;
      var bh = Math.max(2, v / mx * hh);
      c.fillStyle = profColor(p, 46); c.globalAlpha = 0.55; c.fillRect(X(p) - cw * 0.38, barY - 3 - bh, cw * 0.76, bh); c.globalAlpha = 1;
    }
    for (i = 0; i <= w; i += 2) { c.fillStyle = profColor(P0 + (i / w) * (P1 - P0 + 1) - 0.5, 44); c.fillRect(L + i, barY, 2, 9); }
    c.fillStyle = '#5b6473'; c.textAlign = 'center'; c.font = '8px "Fira Code",monospace';
    [-7, 0, 5, 10, 15, 20, 25, 30, 35].forEach(function (q) { if (G.mob && (q === 5 || q === 15 || q === 25)) return; c.fillText(profName(q), X(q), barY + 20); });
    c.fillStyle = '#7a8794'; c.textAlign = 'left'; c.fillText('← easier', L, barY + 31);
    c.textAlign = 'right'; c.fillText('harder →', R, barY + 31);
    if (!r) return;
    var xt = X(r.base), xa = X(r.p == null ? r.model : r.p);
    if (r.drop && r.p != null) {   // cascade arrow: target -> mined
      c.strokeStyle = 'rgba(192,132,252,.9)'; c.lineWidth = 1.5; c.setLineDash([3, 2]);
      c.beginPath(); c.moveTo(xt, barY + 4.5); c.lineTo(xa + 6, barY + 4.5); c.stroke(); c.setLineDash([]);
    }
    c.fillStyle = '#22d3ee'; c.beginPath(); c.moveTo(xt, barY - 1); c.lineTo(xt - 6, barY - 10); c.lineTo(xt + 6, barY - 10); c.closePath(); c.fill();
    c.font = 'bold 9px "Fira Code",monospace'; c.textAlign = 'center'; c.fillText('target ' + profName(r.base), Math.min(R - 30, Math.max(L + 30, xt)), barY - 13);
    c.beginPath(); c.arc(xa, barY + 4.5, 6.5, 0, 7); c.fillStyle = profColor(r.p, 58); c.fill(); c.lineWidth = 2; c.strokeStyle = '#fff'; c.stroke();
    c.fillStyle = '#fff'; c.textAlign = 'center'; c.fillText('mined ' + profName(r.p), Math.min(R - 34, Math.max(L + 34, xa)), barY + 44);
  }
  function drawRibbon(c, G) {
    for (var i = 0; i < rows.length; i++) {
      c.fillStyle = rows[i].p == null ? '#222' : profColor(rows[i].p, 50);
      c.fillRect(G.pad.l + i * G.colW, G.pad.t, Math.max(1, G.colW - (G.colW > 3 ? 0.6 : 0)), G.ch);
    }
  }
  function drawIntervals(c, G) {
    var mx = 1800, i;
    rows.forEach(function (r) { if (r.dt > mx) mx = r.dt; });
    mx = Math.min(mx, 4 * 3600);
    var Y = function (s) { return G.pad.t + G.ch - Math.sqrt(Math.max(0, Math.min(s, mx)) / mx) * G.ch; };
    [[0, '0'], [300, '5m'], [1800, '30m'], [3600, '1h'], [7200, '2h']].forEach(function (g) { if (g[0] <= mx) gridY(c, G, Y(g[0]), g[1]); });
    for (i = 0; i < rows.length; i++) {
      var r = rows[i], x = G.pad.l + i * G.colW, w = Math.max(1, G.colW - (G.colW > 3 ? 1 : 0.2));
      var col = colorMode === 'timing' ? timingColor(r.dt) : window.sostProducerColor(r.m, 52);
      var y = Y(r.dt);
      c.fillStyle = col; c.globalAlpha = 0.9; c.fillRect(x, y, w, G.pad.t + G.ch - y); c.globalAlpha = 1;
    }
    // the 10-minute target: the one line that matters
    var yt = Y(600);
    c.strokeStyle = 'rgba(255,255,255,.9)'; c.lineWidth = 1.4; c.shadowColor = 'rgba(255,255,255,.6)'; c.shadowBlur = 4;
    c.beginPath(); c.moveTo(G.pad.l, yt + 0.5); c.lineTo(G.W - G.pad.r, yt + 0.5); c.stroke(); c.shadowBlur = 0;
    c.fillStyle = '#fff'; c.textAlign = 'left'; c.font = 'bold 9px "Fira Code",monospace';
    c.fillText(G.mob ? '10m' : '10 min', G.W - G.pad.r + 4, yt + 3);
    c.font = '8px "Fira Code",monospace';
    if (!G.mob) {
      [[1200, 'difficulty relief', 'rgba(249,115,22,.75)'], [3600, 'anti-stall', 'rgba(239,68,68,.8)']].forEach(function (rf) {
        if (rf[0] > mx) return;
        var y = Y(rf[0]); c.save(); c.setLineDash([2, 4]); c.strokeStyle = rf[2]; c.lineWidth = 1;
        c.beginPath(); c.moveTo(G.pad.l, y + 0.5); c.lineTo(G.W - G.pad.r, y + 0.5); c.stroke(); c.restore();
        c.fillStyle = rf[2]; c.textAlign = 'left'; c.fillText((rf[0] / 60) + 'm ' + rf[1], G.W - G.pad.r + 4, y + 3);
      });
    }
  }
  function drawDiff(c, G) {
    var R = 80, i, have = rows.filter(function (r) { return r.dev != null; });
    have.forEach(function (r) { R = Math.max(R, Math.abs(r.dev) * 1.25); });
    R = Math.min(R, 600);
    var Y = function (v) { return G.pad.t + G.ch / 2 - Math.max(-R, Math.min(R, v)) / R * (G.ch / 2); };
    var bands = [[15, 60, 'rgba(234,179,8,.07)', '0.5%'], [60, 120, 'rgba(249,115,22,.08)', '1%'], [120, 240, 'rgba(239,68,68,.09)', '2%'], [240, 9999, 'rgba(239,68,68,.14)', '3%']];
    bands.forEach(function (b) {
      [1, -1].forEach(function (s) {
        var a = Y(s * b[0]), z = Y(s * Math.min(b[1], R)); if (Math.abs(z - a) < 1) return;
        c.fillStyle = b[2]; c.fillRect(G.pad.l, Math.min(a, z), G.cw, Math.abs(z - a));
        if (Math.abs(z - a) > 9) { c.fillStyle = 'rgba(255,255,255,.35)'; c.textAlign = 'left'; c.fillText((s > 0 ? '−' : '+') + b[3] + (G.mob ? '' : '/blk'), G.W - G.pad.r + 4, (a + z) / 2 + 3); }
      });
    });
    var d1 = Y(15), d2 = Y(-15);
    c.fillStyle = 'rgba(34,197,94,.16)'; c.fillRect(G.pad.l, d1, G.cw, d2 - d1);
    c.strokeStyle = 'rgba(34,197,94,.55)'; c.lineWidth = 1; c.strokeRect(G.pad.l + 0.5, d1 + 0.5, G.cw - 1, d2 - d1);
    c.fillStyle = 'rgba(34,197,94,.9)'; c.textAlign = 'left'; c.fillText(G.mob ? '±15s' : 'dead band ±15 s', G.W - G.pad.r + 4, Y(0) + 3);
    c.fillStyle = '#5b6473'; c.textAlign = 'right';
    c.fillText('+' + Math.round(R) + 's', G.pad.l - 4, G.pad.t + 8); c.fillText('−' + Math.round(R) + 's', G.pad.l - 4, G.pad.t + G.ch - 1); c.fillText('0', G.pad.l - 4, Y(0) + 3);
    if (!G.mob) {
      c.textAlign = 'left'; c.fillStyle = 'rgba(255,255,255,.28)';
      c.fillText('slower than 600 s → bitsQ eases', G.pad.l + 6, G.pad.t + 9);
      c.fillText('faster than 600 s → bitsQ hardens', G.pad.l + 6, G.pad.t + G.ch - 3);
    }
    // bitsQ (gold, own scale)
    var qlo = Infinity, qhi = -Infinity; rows.forEach(function (r) { qlo = Math.min(qlo, r.d); qhi = Math.max(qhi, r.d); });
    var QY = function (q) { return qhi === qlo ? G.pad.t + 14 : G.pad.t + 6 + (1 - (q - qlo) / (qhi - qlo)) * (G.ch - 12); };
    c.beginPath(); for (i = 0; i < rows.length; i++) { var x0 = G.pad.l + i * G.colW, yq = QY(rows[i].d); if (i) c.lineTo(x0, yq); else c.moveTo(x0, yq); c.lineTo(x0 + G.colW, yq); }
    c.strokeStyle = 'rgba(255,209,102,.8)'; c.lineWidth = 1.2; c.setLineDash([4, 3]); c.stroke(); c.setLineDash([]);
    var lq = rows[rows.length - 1].d;
    c.fillStyle = 'rgba(255,209,102,.9)'; c.textAlign = 'right';
    c.fillText('bitsQ ' + (lq / 65536).toFixed(4) + (qhi === qlo ? ' · unchanged in view' : ''), G.W - G.pad.r - 4, QY(lq) - 4);
    // avg288 deviation
    c.beginPath(); var started = false;
    for (i = 0; i < rows.length; i++) { if (rows[i].dev == null) continue; var y = Y(rows[i].dev); if (started) c.lineTo(xOf(G, i), y); else { c.moveTo(xOf(G, i), y); started = true; } }
    c.strokeStyle = '#f8fafc'; c.lineWidth = 1.5; c.shadowColor = 'rgba(255,255,255,.5)'; c.shadowBlur = 4; c.stroke(); c.shadowBlur = 0;
  }
  function drawBV(c, G) {
    var bMax = 50, vMax = 50, i;
    rows.forEach(function (r) { if (r.burst != null) bMax = Math.max(bMax, r.burst); if (r.vol != null) vMax = Math.max(vMax, r.vol); });
    var YB = function (v) { return G.pad.t + G.ch - v / bMax * G.ch; }, YV = function (v) { return G.pad.t + G.ch - v / vMax * G.ch; };
    gridY(c, G, YB(bMax / 2), Math.round(bMax / 2) + '%'); gridY(c, G, YB(0), '0%');
    c.fillStyle = '#5b6473'; c.textAlign = 'left'; c.fillText(Math.round(vMax / 2) + '%', G.W - G.pad.r + 4, YV(vMax / 2) + 3);
    function line(key, Yf, col) {
      c.beginPath(); var s = false;
      for (var i2 = 0; i2 < rows.length; i2++) { var v = rows[i2][key]; if (v == null) continue; var y = Yf(v); if (s) c.lineTo(xOf(G, i2), y); else { c.moveTo(xOf(G, i2), y); s = true; } }
      c.strokeStyle = col; c.lineWidth = 1.5; c.stroke();
    }
    line('vol', YV, 'rgba(103,232,249,.9)'); line('burst', YB, 'rgba(251,146,60,.95)');
  }

  /* -- live layer: crosshair + new-block slide -------------------------------- */
  function blitAll(now) {
    var k = 0, e = 1;
    if (anim.k) { var a = (now - anim.start) / 750; if (a >= 1) anim.k = 0; else { e = 1 - Math.pow(1 - a, 3); k = anim.k; } }
    for (var i = 0; i < panels.length; i++) {
      var P = panels[i], G = P.geo; if (!P.off || !G) continue;
      var c = P.cv.getContext('2d');
      c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, P.cv.width, P.cv.height);
      if (P.noX) { c.drawImage(P.off, 0, 0); continue; }
      if (k) {
        var shift = (1 - e) * k * G.colW * G.dpr, px = G.pad.l * G.dpr, pw = P.cv.width - px - G.pad.r * G.dpr;
        c.drawImage(P.off, 0, 0, px, P.cv.height, 0, 0, px, P.cv.height);
        c.drawImage(P.off, P.cv.width - G.pad.r * G.dpr, 0, G.pad.r * G.dpr, P.cv.height, P.cv.width - G.pad.r * G.dpr, 0, G.pad.r * G.dpr, P.cv.height);
        c.save(); c.beginPath(); c.rect(px, 0, pw, P.cv.height); c.clip();
        c.drawImage(P.off, shift, 0); c.restore();
      } else c.drawImage(P.off, 0, 0);
      c.setTransform(G.dpr, 0, 0, G.dpr, 0, 0);
      if (k) {   // the newly arrived block(s) glow while sliding in
        c.fillStyle = 'rgba(255,255,255,' + (0.35 * (1 - e)).toFixed(3) + ')';
        c.fillRect(G.pad.l + (G.n - k) * G.colW, G.pad.t, k * G.colW, G.ch);
      }
      if (crossIdx >= 0 && crossIdx < rows.length && !P.noX) {
        var x = xOf(G, crossIdx);
        c.strokeStyle = 'rgba(255,255,255,.55)'; c.lineWidth = 1; c.beginPath(); c.moveTo(x + 0.5, 0); c.lineTo(x + 0.5, G.H); c.stroke();
        c.fillStyle = 'rgba(255,255,255,.07)'; c.fillRect(G.pad.l + crossIdx * G.colW, 0, Math.max(2, G.colW), G.H);
      }
    }
    if (anim.k) rafId = requestAnimationFrame(blitAll); else rafId = 0;
  }
  function setCross(i, fromMosaic) {
    if (i === crossIdx) return;
    crossIdx = i;
    readout(); story(); repaintScale();
    if (!rafId) blitAll(performance.now());
    if (!fromMosaic) {
      window.__sostCrossH = (i >= 0 && rows[i]) ? rows[i].h : null;
      try { window.dispatchEvent(new CustomEvent('sost-cross', { detail: { h: window.__sostCrossH, src: 'cr' } })); } catch (e) {}
    }
  }
  function bindCross(cv, P) {
    function idxAt(clientX) {
      var G = P.geo; if (!G) return -1; var r = cv.getBoundingClientRect();
      var i = Math.floor((clientX - r.left - G.pad.l) / G.colW);
      return (i >= 0 && i < rows.length) ? i : -1;
    }
    cv.addEventListener('mousemove', function (e) { setCross(idxAt(e.clientX)); });
    cv.addEventListener('mouseleave', function () { setCross(-1); });
    cv.addEventListener('touchstart', function (e) { if (e.touches[0]) setCross(idxAt(e.touches[0].clientX)); }, { passive: true });
    cv.addEventListener('touchmove', function (e) { if (e.touches[0]) setCross(idxAt(e.touches[0].clientX)); }, { passive: true });
    cv.addEventListener('click', function (e) {
      var i = idxAt(e.clientX); if (i < 0) return;
      if (e.pointerType === 'touch' || (e.sourceCapabilities && e.sourceCapabilities.firesTouchEvents)) return;
      try { if (typeof window.showBlockByHeight === 'function') window.showBlockByHeight(rows[i].h); } catch (er) {}
    });
  }
  window.addEventListener('sost-cross', function (ev) {
    if (!ev.detail || ev.detail.src === 'cr') return;
    var h = ev.detail.h, i = -1;
    if (h != null) for (var k = rows.length - 1; k >= 0; k--) if (rows[k].h === h) { i = k; break; }
    setCross(i, true);
  });

  /* -- chips + readout -------------------------------------------------------- */
  function chips(flash) {
    var last = rows[rows.length - 1], n = rows.length;
    var matched = 0, known = 0, frozen = 0;
    rows.forEach(function (r) { if (r.match != null) { known++; if (r.match) matched++; } });
    for (var i = rows.length - 1; i >= 0 && rows[i].dq === 0; i--) frozen++;
    var inBand = last.dev != null && Math.abs(last.dev) <= 15;
    var dts = rows.map(function (r) { return r.dt; }).sort(function (a, b) { return a - b; });
    var avg = rows.reduce(function (s, r) { return s + r.dt; }, 0) / n;
    var shares = {}; rows.forEach(function (r) { shares[r.m] = (shares[r.m] || 0) + 1; });
    var nMiners = Object.keys(shares).length;
    function chip(label, val, col, id) { return '<div class="cr-chip' + (flash && id ? ' flash' : '') + '"><span>' + label + '</span><b style="color:' + col + '">' + val + '</b></div>'; }
    chipsEl.innerHTML =
      chip('TIP', '#' + last.h.toLocaleString('en-US'), 'var(--text)', 1) +
      chip('SCHEDULE LAG', (last.lag > 0 ? '+' : '') + last.lag + ' blk', '#22d3ee', 1) +
      chip('EQUALIZER', profName(last.p), profColor(last.p, 62), 1) +
      chip('bitsQ', (last.d / 65536).toFixed(4), '#ffd166') +
      chip('AVG288 DEV', last.dev == null ? '—' : (last.dev > 0 ? '+' : '') + last.dev + ' s', inBand ? '#22c55e' : '#f97316') +
      chip(inBand ? 'IN DEAD BAND' : 'bitsQ STEPPING', inBand ? 'bitsQ held ' + frozen + ' blk' : (last.dq > 0 ? '+' : '') + last.dq.toFixed(2) + '%', inBand ? '#22c55e' : '#f97316') +
      chip('INTERVAL avg · median', fmtDur(avg) + ' · ' + fmtDur(dts[Math.floor(n / 2)]), 'var(--text2)') +
      chip('PRODUCERS', String(nMiners), 'var(--text2)') +
      chip('EQUALIZER MODEL', known ? matched + '/' + known + ' ✓' : '—', matched === known ? '#22c55e' : '#f97316');
    if (legEl) {
      var lg = '';
      if (colorMode === 'timing') {
        [['#38bdf8', 'under 5 min'], ['#22c55e', '5–15 min (on target)'], ['#eab308', '15–30 min'], ['#f97316', '30–60 min'], ['#ef4444', 'over 1 h']].forEach(function (x) {
          lg += '<span><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' + x[0] + ';vertical-align:middle;margin-right:4px"></span>' + x[1] + '</span>';
        });
      } else {
        Object.keys(shares).sort(function (a, b) { return shares[b] - shares[a]; }).slice(0, 6).forEach(function (a) {
          lg += '<span><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' + window.sostProducerColor(a, 52) + ';vertical-align:middle;margin-right:4px"></span>' + shortA(a) + ' · ' + shares[a] + '</span>';
        });
      }
      lg += '<span style="margin-left:auto;display:inline-flex;gap:4px;align-items:center">COLOUR BY ' +
        '<button class="cr-btn' + (colorMode === 'timing' ? ' on' : '') + '" data-cm="timing">SPEED</button>' +
        '<button class="cr-btn' + (colorMode === 'miner' ? ' on' : '') + '" data-cm="miner">MINER</button></span>';
      legEl.innerHTML = lg;
      [].forEach.call(legEl.querySelectorAll('button'), function (bt) {
        bt.onclick = function () { colorMode = bt.getAttribute('data-cm'); try { localStorage.setItem('sost_cr_color', colorMode); } catch (e) {} chips(false); paintAll(); };
      });
    }
    var s4 = document.getElementById('crIntSide');
    if (s4) s4.innerHTML = '<span style="color:var(--text2)">avg ' + fmtDur(avg) + ' &middot; median ' + fmtDur(dts[Math.floor(n / 2)]) + '</span>';
    var side = document.getElementById('crLagSide');
    if (side) side.innerHTML = '<span style="color:' + (matched === known ? '#22c55e' : '#f97316') + '">' + (matched === known ? '✓ ' : '') + 'rule check: ' + matched + '/' + known + ' blocks match the node</span>';
    var s2 = document.getElementById('crDiffSide');
    if (s2) s2.innerHTML = inBand ? '<span style="color:#22c55e">inside the dead band → bitsQ unchanged</span>' : '<span style="color:#f97316">outside the dead band → bitsQ moving</span>';
    var s3 = document.getElementById('crBVSide');
    if (s3 && last.burst != null) s3.innerHTML = '<span style="color:#fb923c">BURST ' + last.burst.toFixed(1) + '%</span> · <span style="color:#67e8f9">VOL ' + last.vol.toFixed(1) + '%</span>';
  }
  function repaintScale() {
    for (var i = 0; i < panels.length; i++) {
      var P = panels[i]; if (!P.noX || !P.off || !P.geo) continue;
      var c = P.off.getContext('2d'); c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, P.off.width, P.off.height);
      c.setTransform(P.geo.dpr, 0, 0, P.geo.dpr, 0, 0); c.font = '8px "Fira Code",monospace'; P.draw(c, P.geo, P);
    }
  }
  function story() {
    if (!storyEl || !rows.length) return;
    var r = rows[crossIdx >= 0 ? crossIdx : rows.length - 1];
    function card(k, v, col, sub, big) {
      return '<div style="flex:1 1 150px;min-width:130px;padding:8px 11px;border:1px solid ' + col.replace(')', ',.35)').replace('rgb(', 'rgba(').replace('hsl(', 'hsla(') +
        ';border-left:3px solid ' + col + ';background:rgba(0,0,0,.3);border-radius:3px"><div style="font-size:8px;letter-spacing:1.4px;color:var(--text3)">' + k + '</div>' +
        '<div style="font-size:' + (big ? 17 : 14) + 'px;font-weight:800;color:' + col + ';margin-top:2px">' + v + '</div>' +
        '<div style="font-size:9px;color:var(--text3);margin-top:2px;line-height:1.4">' + sub + '</div></div>';
    }
    var narrow = (mount.clientWidth || 800) < 620;
    var arrow = narrow ? '<div style="flex:1 1 100%;text-align:center;color:var(--text3);font-size:12px;line-height:10px">&darr;</div>'
                       : '<div style="display:flex;align-items:center;color:var(--text3);font-size:15px;padding:0 1px">&rarr;</div>';
    var ahead = r.lag > 0;
    var c1 = card('SCHEDULE', ahead ? '+' + r.lag + ' blocks' : (r.lag === 0 ? 'on time' : r.lag + ' blocks'),
      '#22d3ee', ahead ? 'chain is ahead of the 10-min timetable' : 'chain is on / behind the timetable');
    var c2 = card('TARGET', profName(r.base), profColor(r.base, 60), ahead ? 'target = blocks ahead (max H35)' : 'not ahead &rarr; easiest normal level B0');
    var c3 = r.drop
      ? card('THIS BLOCK TOOK', fmtDur(r.dt), '#c084fc', 'over 9 min &rarr; eased ' + r.drop + ' level' + (r.drop > 1 ? 's' : '') + ' (V12 cascade)')
      : card('THIS BLOCK TOOK', fmtDur(r.dt), '#64748b', 'under 9 min &rarr; no easing');
    var c4 = card('MINED AT', profName(r.p) + (r.match ? ' <span style="font-size:12px;color:#22c55e">✓</span>' : (r.match === false ? ' <span style="font-size:12px;color:#ef4444">≠</span>' : '')),
      profColor(r.p, 62), 'block #' + r.h.toLocaleString('en-US') + (r.match ? ' &middot; matches the node' : ''), true);
    storyEl.innerHTML = c1 + arrow + c2 + arrow + c3 + arrow + c4;
  }
  function readout() {
    if (!readEl || !rows.length) return;
    var r = rows[crossIdx >= 0 ? crossIdx : rows.length - 1], live = crossIdx < 0;
    var K = function (k) { return '<span class="k">' + k + '</span> '; };
    var casc = r.drop ? ' − cascade ' + r.drop + ' (' + fmtDur(r.dt) + ')' : '';
    readEl.innerHTML =
      '<b style="color:var(--text)">#' + r.h.toLocaleString('en-US') + '</b>' + (live ? ' <span style="color:#22c55e">● newest</span>' : '') +
      ' &nbsp;' + K('miner') + '<span style="color:' + window.sostProducerColor(r.m, 62) + '">' + shortA(r.m) + '</span>' +
      ' &nbsp;' + K('interval') + '<span style="color:' + timingColor(r.dt) + '">' + fmtDur(r.dt) + '</span>' +
      '<br>' + K('Equalizer') + 'lag ' + (r.lag > 0 ? '+' : '') + r.lag + ' → ' + profName(r.base) + casc + ' = <b style="color:' + profColor(r.model, 62) + '">' + profName(r.model) + '</b>' +
      ' · node <b style="color:' + profColor(r.p, 62) + '">' + profName(r.p) + '</b> ' + (r.match == null ? '' : (r.match ? '<span style="color:#22c55e">✓</span>' : '<span style="color:#ef4444">≠</span>')) +
      '<br>' + K('bitsQ') + (r.d / 65536).toFixed(4) + ' (' + (r.dq === 0 ? 'unchanged' : (r.dq > 0 ? '+' : '') + r.dq.toFixed(2) + '%') + ')' +
      ' &nbsp;' + K('avg288 dev') + (r.dev == null ? '—' : (r.dev > 0 ? '+' : '') + r.dev + ' s' + (Math.abs(r.dev) <= 15 ? ' <span style="color:#22c55e">dead band</span>' : '')) +
      (r.burst != null ? ' &nbsp;' + K('burst') + r.burst.toFixed(1) + '% ' + K('vol') + r.vol.toFixed(1) + '%' : '');
  }

  /* -- lifecycle ------------------------------------------------------------- */
  function refresh() {
    if (!build()) return;
    var arr = assemble();
    if (arr.length < 10) { if (readEl) readEl.textContent = 'Waiting for block data…'; return; }
    var grew = !window.__sostChainRows || arr.length !== window.__sostChainRows.length || arr[arr.length - 1].h !== window.__sostChainRows[window.__sostChainRows.length - 1].h;
    window.__sostChainRows = arr;
    if (grew) { try { if (typeof window.renderProducerDist === 'function') window.renderProducerDist(); } catch (e) {} }
    var nr = derive(arr);
    if (!nr.length) return;
    var tip = nr[nr.length - 1].h, k = (lastTip && tip > lastTip) ? Math.min(tip - lastTip, 6) : 0;
    var flash = !!k;
    rows = nr; lastTip = tip;
    if (crossIdx >= rows.length) crossIdx = -1;
    chips(flash); readout(); story();
    paintAll();
    var reduce = false; try { reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}
    if (k && !reduce) { anim.k = k; anim.start = performance.now(); if (!rafId) rafId = requestAnimationFrame(blitAll); }
  }
  function init() {
    if (!build()) return;
    fetchSeries(true);
    refresh();
    var tgt = document.getElementById('dMinersSub');
    if (tgt && typeof MutationObserver === 'function') {
      var sch = false;
      new MutationObserver(function () { if (sch) return; sch = true; setTimeout(function () { sch = false; fetchSeries(false); refresh(); }, 120); })
        .observe(tgt, { childList: true, characterData: true, subtree: true });
    }
    var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(paintAll, 150); });
    if (typeof ResizeObserver === 'function') { var lw = 0; new ResizeObserver(function () { var w = mount.clientWidth; if (w && Math.abs(w - lw) > 2) { lw = w; clearTimeout(rt); rt = setTimeout(paintAll, 80); } }).observe(mount); }
    var tries = 0, poke = setInterval(function () { tries++; if ((window._diffHistory && window._diffHistory.length) || tries > 40) { clearInterval(poke); refresh(); } }, 500);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

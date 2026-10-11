/* SOST Explorer — real OHLC candles on every market chart.
 *
 * Adds a [ LINE ] [ CANDLES ] switch to every chart that is one traded market. LINE is the existing
 * chart, untouched: its canvases, its data layer and its timeframe handlers are not
 * modified — CANDLES only hides that chart-wrap and shows its own canvas beside it, and
 * switching back shows the line chart exactly as it was (a resize event makes the existing
 * code redraw it at the current width). Cards with two series get a selector (e.g. XAUT/USD
 * | XAUT/BTC): candles are always ONE real market, never two scales mixed in one chart.
 *
 * Data: /api/market-history?mode=ohlc — the SOST gateway, never a provider from the browser.
 * Each candle is one real interval of one real traded market, exactly as the venue returned
 * it: X/USD from Yahoo Finance, XAUT/BTC and PAXG/BTC from Binance spot, PAXG/ETH from
 * Kraken spot. A cross rate is never computed from two USD series. XAUT/ETH has no market
 * on any venue, so it has no candles and says so. Thin markets: every interval that traded is
 * drawn at its own time; intervals without trades stay EMPTY GAPS (the gateway removes the
 * exchange's carried-forward rows, nothing is filled). "CANDLES UNAVAILABLE" only at 0 real candles.
 */
(function () {
  'use strict';
  var S = function (asset, vs, label) { return { asset: asset, vs: vs, label: label }; };
  var XU = S('tether-gold', 'usd', 'XAUT / USD'), PU = S('pax-gold', 'usd', 'PAXG / USD'),
      BU = S('bitcoin', 'usd', 'BTC / USD'), EU = S('ethereum', 'usd', 'ETH / USD'),
      XB = S('tether-gold', 'btc', 'XAUT / BTC'), PB = S('pax-gold', 'btc', 'PAXG / BTC'),
      PE = S('pax-gold', 'eth', 'PAXG / ETH');
  // Candles only where a chart IS one traded market. The comparison overlays (two series on two
  // axes) are not a market and stay LINE; XAUT/ETH has no market anywhere, so it gets no switch.
  // The BTC + ETH overlay is the only BTC and ETH chart, so it offers each one's own market.
  var CARDS = [
    { key: 'xaut', series: [XU] }, { key: 'paxg', series: [PU] },
    { key: 'xautbtc', series: [XB] }, { key: 'paxgbtc', series: [PB] }, { key: 'paxgeth', series: [PE] },
    { key: 'ovbtceth', series: [BU, EU] }
  ];
  var UNIT = { usd: '$', btc: '₿', eth: 'Ξ' };
  var UP = '#2ee66b', DOWN = '#ff3b47', GRID = 'rgba(255,255,255,.06)', AXIS = '#6a6a6a';
  var NO_OHLC = 'Real OHLC not available for this timeframe.';
  var SPARSE_NOTE = 0.1;    // show the "sparse market" note when >= 10% of the intervals had no trade
  var REFRESH_MS = 60000, RETRY_MS = 20000;
  var data = {}, inflight = {};

  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function num(v, vs) {
    if (v == null || isNaN(v)) return '—';
    if (vs === 'btc' || vs === 'eth') return Number(v).toPrecision(6);   // cross rates: significant digits
    var d = v >= 1 ? 2 : 6;
    return Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function money(v, vs) { return vs === 'usdt' ? num(v, vs) + ' USDT' : UNIT[vs] + num(v, vs); }
  function axis(v, vs) {
    if ((vs === 'usd' || vs === 'usdt') && v >= 10000) return (vs === 'usd' ? '$' : '') + Math.round(v).toLocaleString('en-US');
    return vs === 'usdt' ? num(v, vs) : money(v, vs);
  }
  function fmtVol(v) {
    if (v == null) return '—';
    if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B';
    if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
    return v >= 10 ? String(Math.round(v)) : Number(v).toFixed(2);
  }
  function daily(iv) { return /d|wk|mo/.test(iv); }
  function when(ms, iv) {
    var iso = new Date(ms).toISOString();
    return daily(iv) ? iso.slice(0, 10) + ' UTC' : iso.slice(0, 16).replace('T', ' ') + ' UTC';
  }
  function venue(src) { return /^binance/.test(src) ? 'Binance ' + src.split(' ')[1] + ' spot' : /^kraken/.test(src) ? 'Kraken ' + src.split(' ')[1] + ' spot' : 'Yahoo Finance'; }

  /* p.kind: 'ok' (>= 1 real candle) | 'no_market' (no venue lists the pair) | 'none' (0 real candles in
     this range) | 'error' (transient). Intervals without trades are gaps, never filled. */
  function load(s, range, cb) {
    var k = s.asset + '|' + s.vs + '|' + range, have = data[k];
    if (have && Date.now() - have._at < (have.kind === 'error' ? RETRY_MS : REFRESH_MS)) return cb(have);
    if (inflight[k]) { inflight[k].push(cb); return; }
    inflight[k] = [cb];
    var done = function (p) { p._at = Date.now(); if (p.kind !== 'error' || !have) data[k] = p; var cbs = inflight[k] || []; delete inflight[k]; cbs.forEach(function (f) { try { f(p.kind === 'error' && have ? have : p); } catch (e) {} }); };
    fetch('/api/market-history?asset=' + encodeURIComponent(s.asset) + '&vs=' + s.vs + '&range=' + encodeURIComponent(range) + '&mode=ohlc')
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (x) {
        var p = x.j || {};
        if (p.source_status === 'no_market') { p.kind = 'no_market'; return done(p); }
        if (x.ok && p.mode === 'ohlc' && p.candles) { p.kind = p.candles.length ? 'ok' : 'none'; return done(p); }
        done({ kind: 'error', error: p.error || 'unavailable' });
      }, function () { done({ kind: 'error', error: 'network' }); });
  }

  /* cfg: { key, series } on the Explorer (ids <key>TfBtns inside a .price-card), or explicit
     { key, series, tf, card, wrap, btnSel, attr, rangeEl } for any other page (SOSTCandles.attach). */
  function Card(cfg) {
    this.btnSel = cfg.btnSel || '.tf-btn'; this.attr = cfg.attr || 'data-tf';
    var tf = cfg.tf || document.getElementById(cfg.key + 'TfBtns');
    if (!tf) return;
    var card = cfg.card || tf.closest('.price-card');
    var wrap = cfg.wrap || (card && card.querySelector('.chart-wrap'));
    if (!wrap) return;
    var line = wrap.querySelector('canvas');
    this.h = (line && parseInt(line.style.height, 10)) || 150;
    this.cfg = cfg; this.tf = tf; this.wrap = wrap; this.card = card;
    this.lineRange = cfg.rangeEl !== undefined ? cfg.rangeEl : card.querySelector('.price-card-range');   // describes the LINE series: hidden while candles show
    this.mode = store('sost_cdl_mode_' + cfg.key) === 'candles' ? 'candles' : 'line';
    var saved = store('sost_cdl_series_' + cfg.key);
    this.si = Math.max(0, cfg.series.findIndex(function (x) { return x.asset + ':' + x.vs === saved; }));
    this.candles = null; this.hover = -1; this.status = {};
    this.build();
    if (this.mode === 'candles') this.setMode('candles');
  }

  Card.prototype.s = function () { return this.cfg.series[this.si]; };

  Card.prototype.build = function () {
    var self = this, cfg = this.cfg;
    var bar = document.createElement('div');
    bar.className = 'cdl-bar';
    var html = '<button type="button" class="cdl-mode" data-m="line">LINE</button><button type="button" class="cdl-mode" data-m="candles">CANDLES</button>';
    if (cfg.series.length > 1) html += '<span class="cdl-sep"></span>' + cfg.series.map(function (x, i) { return '<button type="button" class="cdl-asset" data-i="' + i + '">' + x.label.replace(/ /g, '') + '</button>'; }).join('');
    bar.innerHTML = html;
    this.tf.parentNode.insertBefore(bar, this.tf);
    this.bar = bar;
    var box = document.createElement('div');
    box.className = 'cdl-wrap';
    box.style.display = 'none';
    box.innerHTML = '<div class="cdl-info"></div><div class="cdl-stage" style="height:' + this.h + 'px"><canvas></canvas><div class="cdl-msg"></div><div class="cdl-tip"></div></div>';
    this.wrap.parentNode.insertBefore(box, this.wrap.nextSibling);
    this.box = box; this.canvas = box.querySelector('canvas'); this.tip = box.querySelector('.cdl-tip');
    this.msg = box.querySelector('.cdl-msg'); this.info = box.querySelector('.cdl-info');
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      if (b.dataset.m) self.setMode(b.dataset.m);
      if (b.dataset.i != null) {
        self.si = +b.dataset.i; store('sost_cdl_series_' + cfg.key, self.s().asset + ':' + self.s().vs);
        if (self.mode !== 'candles') self.setMode('candles'); else { self.resetRanges(); self.fetch(); }
      }
    });
    // The existing line handler runs first and marks the clicked button active; read it after.
    this.tf.addEventListener('click', function (e) {
      if (self.mode === 'candles' && e.target.closest(self.btnSel)) setTimeout(function () { self.fetch(); }, 0);
    });
    var move = function (e) {
      if (!self.candles) return;
      var r = self.canvas.getBoundingClientRect();
      var pt = e.touches ? e.touches[0] : e;
      self.pointer(pt.clientX - r.left);
    };
    this.canvas.addEventListener('mousemove', move);
    this.canvas.addEventListener('touchstart', move, { passive: true });
    this.canvas.addEventListener('touchmove', move, { passive: true });
    this.canvas.addEventListener('mouseleave', function () { self.hover = -1; self.tip.style.display = 'none'; self.draw(); });
    this.syncBar();
  };

  Card.prototype.range = function () {
    var a = this.tf.querySelector(this.btnSel + '.active');
    return a ? a.getAttribute(this.attr) : '24H';
  };

  Card.prototype.syncBar = function () {
    var self = this;
    this.bar.querySelectorAll('.cdl-mode').forEach(function (b) { b.classList.toggle('on', b.dataset.m === self.mode); });
    this.bar.querySelectorAll('.cdl-asset').forEach(function (b) { b.classList.toggle('on', self.mode === 'candles' && +b.dataset.i === self.si); });
  };

  Card.prototype.resetRanges = function () {
    this.tf.querySelectorAll(this.btnSel).forEach(function (b) {
      b.classList.remove('cdl-off'); b.removeAttribute('aria-disabled');
      if (b.dataset.cdlOldTitle != null) { b.title = b.dataset.cdlOldTitle; delete b.dataset.cdlOldTitle; }
    });
  };

  Card.prototype.setMode = function (m) {
    this.mode = m; store('sost_cdl_mode_' + this.cfg.key, m); this.syncBar();
    var btns = this.tf.querySelectorAll(this.btnSel);
    if (m === 'candles') {
      // A LINE-only "disabled" (provider history cap) must not block a range that has real candles.
      btns.forEach(function (b) { if (b.classList.contains('disabled')) { b.dataset.cdlWasDisabled = '1'; b.classList.remove('disabled'); } });
      this.wrap.style.display = 'none'; this.box.style.display = '';
      if (this.lineRange) this.lineRange.style.display = 'none';
      this.fetch();
    } else {
      this.resetRanges();
      btns.forEach(function (b) { if (b.dataset.cdlWasDisabled) { b.classList.add('disabled'); delete b.dataset.cdlWasDisabled; } });
      this.box.style.display = 'none'; this.wrap.style.display = '';
      if (this.lineRange) this.lineRange.style.display = '';
      try { window.dispatchEvent(new Event('resize')); } catch (e) {}   // existing code redraws the line at today's width
    }
  };

  Card.prototype.markRange = function (range, ok, why) {
    var b = this.tf.querySelector(this.btnSel + '[' + this.attr + '="' + range + '"]');
    if (!b) return;
    if (ok) {
      b.classList.remove('cdl-off'); b.removeAttribute('aria-disabled');
      if (b.dataset.cdlOldTitle != null) { b.title = b.dataset.cdlOldTitle; delete b.dataset.cdlOldTitle; }
    } else {
      if (b.dataset.cdlOldTitle == null) b.dataset.cdlOldTitle = b.title || '';
      b.classList.add('cdl-off'); b.setAttribute('aria-disabled', 'true'); b.title = NO_OHLC + (why ? ' ' + why : '');
    }
  };

  // After the visible range has loaded, learn which other ranges have readable real candles,
  // one request at a time (the gateway caches and deduplicates them for every visitor).
  Card.prototype.scan = function () {
    var self = this, s = this.s(), tag = s.asset + s.vs, ranges = [];
    this.tf.querySelectorAll(this.btnSel).forEach(function (b) { ranges.push(b.getAttribute(self.attr)); });
    if (this.scanned === tag) return;
    this.scanned = tag;
    (function next(i) {
      if (i >= ranges.length || self.mode !== 'candles' || self.scanned !== tag) return;
      load(s, ranges[i], function (p) {
        if (p.kind === 'none') self.markRange(ranges[i], false, NONE_WHY);
        else if (p.kind === 'ok') self.markRange(ranges[i], true);
        setTimeout(function () { next(i + 1); }, 350);
      });
    })(0);
  };

  var NONE_WHY = 'The market returned 0 real OHLC candles for this range (no trades).';

  Card.prototype.show = function (text, info) {
    this.candles = null; this.shown = null; this.clear();
    this.msg.innerHTML = text; this.msg.style.display = 'flex';
    this.info.innerHTML = info || '';
  };

  Card.prototype.fetch = function () {
    var self = this, range = this.range(), s = this.s(), tag = s.asset + '|' + s.vs + '|' + range;
    clearTimeout(this.retry);
    if (this.shown !== tag) {          // a background refresh never blanks the chart
      this.candles = null; this.clear();
      this.msg.textContent = 'loading real OHLC…'; this.msg.style.display = 'flex';
    }
    load(s, range, function (p) {
      if (self.mode !== 'candles' || self.range() !== range || self.s() !== s) return;
      if (p.kind === 'no_market') {
        self.tf.querySelectorAll(self.btnSel).forEach(function (b) { self.markRange(b.getAttribute(self.attr), false, 'No ' + s.label.replace(/ /g, '') + ' market exists.'); });
        return self.show('<b>NO REAL ' + s.label.replace(/ /g, '') + ' MARKET</b><span>No exchange lists ' + s.label.replace(/ /g, '') + ', so real candles do not exist. LINE stays available.</span>',
          'CANDLES UNAVAILABLE FOR THIS PAIR');
      }
      if (p.kind === 'none') {
        self.markRange(range, false, NONE_WHY);
        self.scan();
        return self.show('<b>CANDLES UNAVAILABLE FOR THIS RANGE</b><span>' + NONE_WHY + ' LINE stays available.</span>',
          s.label + ' · ' + venue(p.source));
      }
      if (p.kind === 'error') {
        self.retry = setTimeout(function () { self.fetch(); }, RETRY_MS);
        return self.show('<b>CANDLES TEMPORARILY UNAVAILABLE</b><span>The market source is busy; retrying. LINE stays available.</span>', '');
      }
      self.markRange(range, true);
      self.candles = p.candles; self.payload = p; self.hover = -1; self.shown = tag;
      self.msg.style.display = 'none';
      var last = p.candles[p.candles.length - 1], first = p.candles[0][0];
      var listed = range.match(/Y$/) && first > Date.now() - ({ '1Y': 340, '3Y': 1000, '5Y': 1700 }[range] || 0) * 86400000;
      self.info.innerHTML = '<b>' + s.label + '</b> · ' + p.candles.length + ' real ' + p.interval + ' candles · ' + venue(p.source) +
        (listed ? ' · <span style="color:#fbbf24">history since ' + new Date(first).toISOString().slice(0, 10) + '</span>' : '') +
        (p.source_status === 'stale' ? ' · <span style="color:#fbbf24">stale ' + Math.round(p.age_s / 60) + ' min</span>' : '') +
        (p.expected_intervals && p.empty_intervals / p.expected_intervals >= SPARSE_NOTE ? ' · <span style="color:#94a3b8">Sparse market · ' +
          p.empty_intervals + ' of ' + p.expected_intervals + ' intervals had no trades (gaps)</span>' : '') +
        ' · last close <b>' + money(last[4], s.vs) + '</b>';
      self.draw();
      self.scan();
    });
  };

  Card.prototype.geom = function () {
    var c = this.canvas, dpr = window.devicePixelRatio || 1;
    var w = c.parentNode.clientWidth, h = this.h;
    c.style.width = w + 'px'; c.style.height = h + 'px';
    c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
    var ctx = c.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: h, L: 4, R: w < 420 ? 62 : 74, T: 8, B: 18 };
  };

  Card.prototype.clear = function () { var g = this.geom(); g.ctx.clearRect(0, 0, g.w, g.h); };

  Card.prototype.draw = function () {
    if (this.mode !== 'candles' || !this.candles || this.box.style.display === 'none') return;
    var g = this.geom(), ctx = g.ctx, k = this.candles, n = k.length, vs = this.s().vs;
    var lo = Infinity, hi = -Infinity;
    k.forEach(function (c) { if (c[3] < lo) lo = c[3]; if (c[2] > hi) hi = c[2]; });
    var pad = (hi - lo) * 0.06 || hi * 0.001; lo -= pad; hi += pad;
    var pw = g.w - g.L - g.R, ph = g.h - g.T - g.B;
    var y = function (v) { return g.T + (hi - v) / (hi - lo) * ph; };
    // Time axis: every candle sits at its own interval; intervals without trades stay empty (gaps).
    var P = this.payload, ivMs = P.interval_s ? P.interval_s * 1000 : (n > 1 ? (k[n - 1][0] - k[0][0]) / (n - 1) : 1);
    var t0 = P.window_start_ms != null ? Math.min(P.window_start_ms, k[0][0]) : k[0][0];
    var t1 = Math.max(P.window_end_ms != null ? P.window_end_ms : 0, k[n - 1][0] + ivMs);
    var slots = Math.max(1, (t1 - t0) / ivMs), slot = pw / slots, bw = Math.max(1, Math.min(14, slot * 0.68));
    var x = function (i) { return g.L + ((k[i][0] - t0) / ivMs + 0.5) * slot; };
    this.geo = { x: x, slot: slot, L: g.L, n: n, t0: t0, ivMs: ivMs };
    ctx.clearRect(0, 0, g.w, g.h);
    ctx.font = '9px "Fira Code", monospace'; ctx.textBaseline = 'middle';
    for (var i = 0; i <= 4; i++) {
      var v = lo + (hi - lo) * i / 4, yy = Math.round(y(v)) + 0.5;
      ctx.strokeStyle = GRID; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(g.L, yy); ctx.lineTo(g.w - g.R, yy); ctx.stroke();
      ctx.fillStyle = AXIS; ctx.textAlign = 'left'; ctx.fillText(axis(v, vs), g.w - g.R + 5, yy);
    }
    var iv = this.payload.interval;
    ctx.textBaseline = 'alphabetic';
    [t0, (t0 + t1) / 2, t1 - ivMs].forEach(function (tt, j) {
      var t = when(tt, iv).replace(' UTC', ''), s = daily(iv) ? t : t.slice(5);
      ctx.textAlign = j === 0 ? 'left' : j === 2 ? 'right' : 'center';
      ctx.fillStyle = AXIS; ctx.fillText(s, j === 0 ? g.L : j === 2 ? g.w - g.R : g.L + pw / 2, g.h - 4);
    });
    for (i = 0; i < n; i++) {
      var c = k[i], up = c[4] >= c[1], col = up ? UP : DOWN, cx = Math.round(x(i)) + 0.5;
      ctx.strokeStyle = col; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(cx, Math.round(y(c[2]))); ctx.lineTo(cx, Math.round(y(c[3]))); ctx.stroke();   // wick: low -> high
      var top = y(Math.max(c[1], c[4])), bot = y(Math.min(c[1], c[4]));
      ctx.fillStyle = col;
      ctx.fillRect(Math.round(cx - bw / 2), Math.round(top), Math.max(1, Math.round(bw)), Math.max(1, Math.round(bot - top)));  // body: open -> close
    }
    if (this.hover >= 0 && this.hover < n) {
      var hx = Math.round(x(this.hover)) + 0.5;
      ctx.strokeStyle = 'rgba(255,255,255,.25)'; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(hx, g.T); ctx.lineTo(hx, g.h - g.B); ctx.stroke(); ctx.setLineDash([]);
    }
  };

  Card.prototype.pointer = function (px) {
    if (!this.geo) return;
    // Tooltip only over an interval that has a real candle; a gap shows nothing.
    var G = this.geo, si = Math.floor((px - G.L) / G.slot), i = -1;
    for (var q = 0; q < G.n; q++) if (Math.floor((this.candles[q][0] - G.t0) / G.ivMs) === si) { i = q; break; }
    if (i < 0) { this.hover = -1; this.tip.style.display = 'none'; this.draw(); return; }
    this.hover = i; this.draw();
    var c = this.candles[i], p = this.payload, vs = this.s().vs;
    this.tip.innerHTML = '<div class="d">' + when(c[0], p.interval) + ' · ' + p.interval + '</div>' +
      '<div>OPEN <b>' + money(c[1], vs) + '</b></div><div>HIGH <b>' + money(c[2], vs) + '</b></div>' +
      '<div>LOW <b>' + money(c[3], vs) + '</b></div><div>CLOSE <b style="color:' + (c[4] >= c[1] ? UP : DOWN) + '">' + money(c[4], vs) + '</b></div>' +
      (c[2] === c[3] ? '<div class="v">no trade in this interval</div>' : '') +
      (c[5] != null ? '<div class="v">VOLUME ' + fmtVol(c[5]) + ' ' + (p.volume_unit || '') + ' <span>(' + venue(p.source) + ')</span></div>' : '');
    var sw = this.tip.parentNode.clientWidth;
    this.tip.style.display = 'block';
    var tw = this.tip.offsetWidth, cx = this.geo.x(i);
    this.tip.style.left = Math.max(0, Math.min(sw - tw, cx + 12 + tw > sw ? cx - tw - 12 : cx + 12)) + 'px';
    this.tip.style.top = '4px';
  };

  function css() {
    var s = document.createElement('style');
    s.textContent = '.cdl-bar{display:flex;gap:4px;margin:0 0 6px;flex-wrap:wrap;align-items:center}' +
      '.cdl-bar button{background:#141414;border:1px solid #262626;color:#777;font-family:var(--code,monospace);font-size:9px;padding:4px 9px;cursor:pointer;letter-spacing:1px;line-height:1}' +
      '.cdl-bar button:hover{color:#aaa;border-color:#383838}.cdl-bar button.on{background:rgba(46,230,107,.10);border-color:rgba(46,230,107,.45);color:#2ee66b}' +
      '.cdl-sep{width:1px;height:12px;background:#2a2a2a;margin:0 4px}' +
      '.cdl-off{opacity:.3!important;cursor:not-allowed;pointer-events:none}' +
      '.cdl-info{font-family:var(--code,monospace);font-size:9.5px;color:#7a7a7a;letter-spacing:.3px;margin:0 0 4px;min-height:13px;overflow-wrap:anywhere}.cdl-info b{color:#c8c8c8;font-weight:600}' +
      '.cdl-stage{position:relative;width:100%}.cdl-stage canvas{display:block;width:100%;touch-action:pan-y}' +
      '.cdl-msg{position:absolute;inset:0;display:none;flex-direction:column;gap:6px;align-items:center;justify-content:center;font-family:var(--code,monospace);font-size:10px;letter-spacing:.6px;color:#888;text-align:center;padding:0 14px;line-height:1.5}' +
      '.cdl-msg b{color:#fbbf24;letter-spacing:1px}.cdl-msg span{color:#8a8a8a;max-width:440px}' +
      '.cdl-tip{position:absolute;display:none;background:rgba(10,10,10,.95);border:1px solid #333;padding:6px 10px;font-family:var(--code,monospace);font-size:10px;line-height:1.55;color:#888;pointer-events:none;z-index:10;white-space:nowrap}' +
      '.cdl-tip b{color:#c8c8c8;font-weight:600}.cdl-tip .d{color:#666}.cdl-tip .v span{color:#555}';
    document.head.appendChild(s);
  }

  var cards = [];
  function live(c) { return document.body.contains(c.box); }
  function init() {
    css();
    CARDS.forEach(function (c) { var k = new Card(c); if (k.cfg) cards.push(k); });   // Explorer cards, if present
    var t;
    window.addEventListener('resize', function () { clearTimeout(t); t = setTimeout(function () { cards.forEach(function (c) { if (live(c)) c.draw(); }); }, 80); });
    setInterval(function () {      // candles reload through the SOST gateway (Explorer API), never a provider
      if (document.hidden) return;
      for (var i = cards.length - 1; i >= 0; i--) if (!live(cards[i])) cards.splice(i, 1);   // closed modals
      cards.forEach(function (c) { if (c.mode === 'candles' && c.candles) c.fetch(); });
    }, REFRESH_MS);
  }
  window.SOSTCandles = {
    cards: cards,
    series: S,
    attach: function (cfg) { var k = new Card(cfg); if (!k.cfg) return null; cards.push(k); return k; }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

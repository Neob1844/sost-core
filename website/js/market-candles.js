/* SOST Explorer — real OHLC candles for BTC, ETH, PAXG and XAUT.
 *
 * Adds a [ LINE ] [ CANDLES ] switch to the XAUT PRICE card, the PAXG PRICE card and the
 * BTC + ETH overlay card. LINE is the existing chart, untouched: its canvases, its data
 * layer and its timeframe handlers are not modified — CANDLES only hides that chart-wrap
 * and shows its own canvas beside it, and switching back shows the line chart exactly
 * as it was (a resize event makes the existing code redraw it at the current width).
 *
 * Data: /api/market-history?mode=ohlc — the SOST gateway, never the provider from the
 * browser. Each candle is one real provider interval (open/high/low/close/volume as
 * returned upstream). Nothing here derives a candle from the close series, aggregates,
 * resamples or interpolates. A range without real OHLC shows "CANDLES UNAVAILABLE FOR
 * THIS RANGE" and its timeframe button is disabled while in CANDLES mode.
 */
(function () {
  'use strict';
  var CARDS = [
    { key: 'xaut', assets: [['tether-gold', 'XAUT']], h: 150 },
    { key: 'paxg', assets: [['pax-gold', 'PAXG']], h: 150 },
    { key: 'ovbtceth', assets: [['bitcoin', 'BTC'], ['ethereum', 'ETH']], h: 220 }
  ];
  var UP = '#2ee66b', DOWN = '#ff3b47', GRID = 'rgba(255,255,255,.06)', AXIS = '#5a5a5a';
  var NO_OHLC = 'Real OHLC not available for this timeframe.';
  var REFRESH_MS = 60000;
  var data = {};            // asset|range -> payload
  var inflight = {};

  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function fmt(v) {
    if (v == null || isNaN(v)) return '—';
    var d = v >= 1000 ? 2 : v >= 1 ? 2 : 6;
    return Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function fmtAxis(v) { return v >= 10000 ? '$' + Math.round(v).toLocaleString('en-US') : '$' + fmt(v); }
  function fmtVol(v) {
    if (v == null) return '—';
    if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B';
    if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
    return String(Math.round(v));
  }
  function when(ms, iv) {
    var d = new Date(ms), iso = d.toISOString();
    return /d|wk|mo/.test(iv) ? iso.slice(0, 10) + ' UTC' : iso.slice(0, 16).replace('T', ' ') + ' UTC';
  }

  function load(asset, range, cb) {
    var k = asset + '|' + range, have = data[k];
    if (have && Date.now() - have._at < REFRESH_MS) return cb(have);
    if (inflight[k]) { inflight[k].push(cb); return; }
    inflight[k] = [cb];
    var done = function (p) { var cbs = inflight[k] || []; delete inflight[k]; cbs.forEach(function (f) { try { f(p); } catch (e) {} }); };
    fetch('/api/market-history?asset=' + encodeURIComponent(asset) + '&vs=usd&range=' + encodeURIComponent(range) + '&mode=ohlc')
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (x) {
        var p = x.j || {};
        if (x.ok && p.mode === 'ohlc' && p.candles && p.candles.length) { p._at = Date.now(); data[k] = p; done(p); }
        else done(have || { error: p.error || 'unavailable' });
      }, function () { done(have || { error: 'network' }); });
  }

  function Card(cfg) {
    var tf = document.getElementById(cfg.key + 'TfBtns');
    if (!tf) return;
    var card = tf.closest('.price-card');
    var wrap = card && card.querySelector('.chart-wrap');
    if (!wrap) return;
    this.cfg = cfg; this.tf = tf; this.wrap = wrap; this.card = card;
    this.lineRange = card.querySelector('.price-card-range');   // describes the LINE series: hidden while candles show
    this.mode = store('sost_cdl_mode_' + cfg.key) === 'candles' ? 'candles' : 'line';
    var a = store('sost_cdl_asset_' + cfg.key);
    this.asset = cfg.assets.some(function (x) { return x[0] === a; }) ? a : cfg.assets[0][0];
    this.candles = null; this.hover = -1;
    this.build();
    if (this.mode === 'candles') this.setMode('candles');
  }

  Card.prototype.build = function () {
    var self = this, cfg = this.cfg;
    var bar = document.createElement('div');
    bar.className = 'cdl-bar';
    var html = '<button type="button" class="cdl-mode" data-m="line">LINE</button><button type="button" class="cdl-mode" data-m="candles">CANDLES</button>';
    if (cfg.assets.length > 1) html += '<span class="cdl-sep"></span>' + cfg.assets.map(function (x) { return '<button type="button" class="cdl-asset" data-a="' + x[0] + '">' + x[1] + '</button>'; }).join('');
    bar.innerHTML = html;
    this.tf.parentNode.insertBefore(bar, this.tf);
    this.bar = bar;
    var box = document.createElement('div');
    box.className = 'cdl-wrap';
    box.style.display = 'none';
    box.innerHTML = '<div class="cdl-info"></div><div class="cdl-stage" style="height:' + cfg.h + 'px"><canvas></canvas><div class="cdl-msg"></div><div class="cdl-tip"></div></div>';
    this.wrap.parentNode.insertBefore(box, this.wrap.nextSibling);
    this.box = box; this.canvas = box.querySelector('canvas'); this.tip = box.querySelector('.cdl-tip');
    this.msg = box.querySelector('.cdl-msg'); this.info = box.querySelector('.cdl-info');
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      if (b.dataset.m) self.setMode(b.dataset.m);
      if (b.dataset.a) { self.asset = b.dataset.a; store('sost_cdl_asset_' + cfg.key, self.asset); if (self.mode !== 'candles') self.setMode('candles'); else self.fetch(); }
    });
    // The existing line handler runs first and marks the clicked button active; read it after.
    this.tf.addEventListener('click', function (e) {
      if (self.mode === 'candles' && e.target.closest('.tf-btn')) setTimeout(function () { self.fetch(); }, 0);
    });
    var move = function (e) {
      if (!self.candles) return;
      var r = self.canvas.getBoundingClientRect();
      var pt = e.touches ? e.touches[0] : e;
      self.pointer(pt.clientX - r.left, pt.clientY - r.top);
    };
    this.canvas.addEventListener('mousemove', move);
    this.canvas.addEventListener('touchstart', move, { passive: true });
    this.canvas.addEventListener('touchmove', move, { passive: true });
    this.canvas.addEventListener('mouseleave', function () { self.hover = -1; self.tip.style.display = 'none'; self.draw(); });
    this.syncBar();
  };

  Card.prototype.range = function () {
    var a = this.tf.querySelector('.tf-btn.active');
    return a ? a.getAttribute('data-tf') : '24H';
  };

  Card.prototype.syncBar = function () {
    var self = this;
    this.bar.querySelectorAll('.cdl-mode').forEach(function (b) { b.classList.toggle('on', b.dataset.m === self.mode); });
    this.bar.querySelectorAll('.cdl-asset').forEach(function (b) { b.classList.toggle('on', self.mode === 'candles' && b.dataset.a === self.asset); });
  };

  Card.prototype.setMode = function (m) {
    this.mode = m; store('sost_cdl_mode_' + this.cfg.key, m); this.syncBar();
    var btns = this.tf.querySelectorAll('.tf-btn');
    if (m === 'candles') {
      // A LINE-only "disabled" (provider history cap) must not block a range that has real candles.
      btns.forEach(function (b) { if (b.classList.contains('disabled')) { b.dataset.cdlWasDisabled = '1'; b.classList.remove('disabled'); } });
      this.wrap.style.display = 'none'; this.box.style.display = '';
      if (this.lineRange) this.lineRange.style.display = 'none';
      this.fetch();
    } else {
      btns.forEach(function (b) {
        b.classList.remove('cdl-off'); b.removeAttribute('aria-disabled');
        if (b.dataset.cdlOldTitle != null) { b.title = b.dataset.cdlOldTitle; delete b.dataset.cdlOldTitle; }
        if (b.dataset.cdlWasDisabled) { b.classList.add('disabled'); delete b.dataset.cdlWasDisabled; }
      });
      this.box.style.display = 'none'; this.wrap.style.display = '';
      if (this.lineRange) this.lineRange.style.display = '';
      try { window.dispatchEvent(new Event('resize')); } catch (e) {}   // existing code redraws the line at today's width
    }
  };

  Card.prototype.markRange = function (range, ok) {
    var b = this.tf.querySelector('.tf-btn[data-tf="' + range + '"]');
    if (!b) return;
    if (ok) {
      b.classList.remove('cdl-off'); b.removeAttribute('aria-disabled');
      if (b.dataset.cdlOldTitle != null) { b.title = b.dataset.cdlOldTitle; delete b.dataset.cdlOldTitle; }
    } else {
      if (b.dataset.cdlOldTitle == null) b.dataset.cdlOldTitle = b.title || '';
      b.classList.add('cdl-off'); b.setAttribute('aria-disabled', 'true'); b.title = NO_OHLC;
    }
  };

  Card.prototype.fetch = function () {
    var self = this, range = this.range(), asset = this.asset;
    if (this.shown !== asset + '|' + range) {          // a background refresh never blanks the chart
      this.candles = null; this.clear();
      this.msg.textContent = 'loading real OHLC…'; this.msg.style.display = 'flex';
    }
    load(asset, range, function (p) {
      if (self.mode !== 'candles' || self.range() !== range || self.asset !== asset) return;
      if (!p || !p.candles) {
        self.candles = null; self.shown = null; self.markRange(range, false);
        self.msg.textContent = 'CANDLES UNAVAILABLE FOR THIS RANGE'; self.msg.style.display = 'flex';
        self.info.textContent = NO_OHLC + ' LINE stays available.';
        self.clear();
        return;
      }
      self.markRange(range, true);
      self.candles = p.candles; self.payload = p; self.hover = -1; self.shown = asset + '|' + range;
      self.msg.style.display = 'none';
      var label = self.cfg.assets.filter(function (x) { return x[0] === asset; })[0][1];
      var last = p.candles[p.candles.length - 1];
      self.info.innerHTML = '<b>' + label + ' / USD</b> · ' + p.candles.length + ' real ' + p.interval + ' candles · source ' + p.source +
        (p.source_status === 'stale' ? ' · <span style="color:#fbbf24">stale ' + Math.round(p.age_s / 60) + ' min</span>' : '') +
        ' · last close <b>$' + fmt(last[4]) + '</b>';
      self.draw();
    });
  };

  Card.prototype.geom = function () {
    var c = this.canvas, dpr = window.devicePixelRatio || 1;
    var w = c.parentNode.clientWidth, h = this.cfg.h;
    c.style.width = w + 'px'; c.style.height = h + 'px';
    c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
    var ctx = c.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: h, L: 4, R: w < 420 ? 58 : 70, T: 8, B: 18 };
  };

  Card.prototype.clear = function () { var g = this.geom(); g.ctx.clearRect(0, 0, g.w, g.h); };

  Card.prototype.draw = function () {
    if (this.mode !== 'candles' || !this.candles || this.box.style.display === 'none') return;
    var g = this.geom(), ctx = g.ctx, k = this.candles, n = k.length;
    var lo = Infinity, hi = -Infinity;
    k.forEach(function (c) { if (c[3] < lo) lo = c[3]; if (c[2] > hi) hi = c[2]; });
    var pad = (hi - lo) * 0.06 || hi * 0.001; lo -= pad; hi += pad;
    var pw = g.w - g.L - g.R, ph = g.h - g.T - g.B;
    var y = function (v) { return g.T + (hi - v) / (hi - lo) * ph; };
    var slot = pw / n, bw = Math.max(1, Math.min(14, slot * 0.68));
    var x = function (i) { return g.L + slot * (i + 0.5); };
    this.geo = { x: x, slot: slot, L: g.L, n: n };
    ctx.clearRect(0, 0, g.w, g.h);
    ctx.font = '9px "Fira Code", monospace'; ctx.textBaseline = 'middle';
    for (var i = 0; i <= 4; i++) {
      var v = lo + (hi - lo) * i / 4, yy = Math.round(y(v)) + 0.5;
      ctx.strokeStyle = GRID; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(g.L, yy); ctx.lineTo(g.w - g.R, yy); ctx.stroke();
      ctx.fillStyle = AXIS; ctx.textAlign = 'left'; ctx.fillText(fmtAxis(v), g.w - g.R + 5, yy);
    }
    var iv = this.payload.interval;
    ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    [0, Math.floor(n / 2), n - 1].forEach(function (i, j) {
      var t = when(k[i][0], iv).replace(' UTC', ''), s = /d|wk|mo/.test(iv) ? t : t.slice(5);
      ctx.textAlign = j === 0 ? 'left' : j === 2 ? 'right' : 'center';
      ctx.fillStyle = AXIS; ctx.fillText(s, j === 0 ? g.L : j === 2 ? g.w - g.R : x(i), g.h - 4);
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

  Card.prototype.pointer = function (px, py) {
    if (!this.geo) return;
    var i = Math.max(0, Math.min(this.geo.n - 1, Math.floor((px - this.geo.L) / this.geo.slot)));
    this.hover = i; this.draw();
    var c = this.candles[i], iv = this.payload.interval;
    this.tip.innerHTML = '<div class="d">' + when(c[0], iv) + ' · ' + iv + '</div>' +
      '<div>OPEN <b>$' + fmt(c[1]) + '</b></div><div>HIGH <b>$' + fmt(c[2]) + '</b></div>' +
      '<div>LOW <b>$' + fmt(c[3]) + '</b></div><div>CLOSE <b style="color:' + (c[4] >= c[1] ? UP : DOWN) + '">$' + fmt(c[4]) + '</b></div>' +
      (c[5] != null ? '<div class="v">VOLUME ' + fmtVol(c[5]) + ' <span>(provider)</span></div>' : '');
    var stage = this.tip.parentNode, sw = stage.clientWidth;
    this.tip.style.display = 'block';
    var tw = this.tip.offsetWidth, cx = this.geo.x(i);
    this.tip.style.left = Math.max(0, Math.min(sw - tw, cx + 12 + tw > sw ? cx - tw - 12 : cx + 12)) + 'px';
    this.tip.style.top = '4px';
  };

  function css() {
    var s = document.createElement('style');
    s.textContent = '.cdl-bar{display:flex;gap:4px;margin:0 0 6px;flex-wrap:wrap;align-items:center}' +
      '.cdl-bar button{background:#141414;border:1px solid #262626;color:#666;font-family:var(--code,monospace);font-size:9px;padding:3px 9px;cursor:pointer;letter-spacing:1px;line-height:1}' +
      '.cdl-bar button:hover{color:#999;border-color:#383838}.cdl-bar button.on{background:rgba(46,230,107,.10);border-color:rgba(46,230,107,.45);color:#2ee66b}' +
      '.cdl-sep{width:1px;height:12px;background:#2a2a2a;margin:0 4px}' +
      '.tf-btn.cdl-off{opacity:.3;cursor:not-allowed;pointer-events:none}' +
      '.cdl-info{font-family:var(--code,monospace);font-size:9.5px;color:#777;letter-spacing:.3px;margin:0 0 4px;min-height:13px;overflow-wrap:anywhere}.cdl-info b{color:#c8c8c8;font-weight:600}' +
      '.cdl-stage{position:relative;width:100%}.cdl-stage canvas{display:block;width:100%;touch-action:pan-y}' +
      '.cdl-msg{position:absolute;inset:0;display:none;align-items:center;justify-content:center;font-family:var(--code,monospace);font-size:10px;letter-spacing:1px;color:#888;text-align:center;padding:0 8px}' +
      '.cdl-tip{position:absolute;display:none;background:rgba(10,10,10,.95);border:1px solid #333;padding:6px 10px;font-family:var(--code,monospace);font-size:10px;line-height:1.55;color:#888;pointer-events:none;z-index:10;white-space:nowrap}' +
      '.cdl-tip b{color:#c8c8c8;font-weight:600}.cdl-tip .d{color:#666}.cdl-tip .v span{color:#555}';
    document.head.appendChild(s);
  }

  function init() {
    css();
    var cards = CARDS.map(function (c) { return new Card(c); }).filter(function (c) { return c.cfg; });
    window.SOSTCandles = { cards: cards };
    var t;
    window.addEventListener('resize', function () { clearTimeout(t); t = setTimeout(function () { cards.forEach(function (c) { c.draw(); }); }, 80); });
    setInterval(function () {
      if (document.hidden) return;
      cards.forEach(function (c) { if (c.mode === 'candles') c.fetch(); });
    }, REFRESH_MS);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

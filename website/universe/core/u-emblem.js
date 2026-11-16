/* SOST Universe — header emblem: the owner's eye with the Chromatic Sigma Glow (DIRECTIVA 4D §1, 3 nov 2026).
 *
 * The static emblem (<img>, assets/brand/sost-eye-*.png: the owner's image exactly, circular) is always there and is identical to the
 * favicon / exchange set. This module paints a transparent overlay canvas on top of it (the stroke is recoloured, the halo is a
 * translucent glow over the dark iris):
 *   the WHOLE Σ glows from inside in one of the 10 official colours, chosen at random and never the same twice in a row;
 *   each colour holds 2–4 s (random), then cross-fades to the next over 0.8–1.2 s (smoothstep, no flash, no strobe);
 *   near-white core along the centreline of the strokes, the colour at the stroke edges, a coloured outer halo (selective bloom) that is
 *   windowed to zero a few pixels outside the Σ silhouette (never a rectangle);
 *   the iris and the skin are never painted (owner, 4 Nov 2026). The geometry of the Σ is the one in the image (field assets/sigma/sigma-eye-field.png).
 *   Intensity is balanced per colour by its relative luminance (yellow / cyan are dimmed, violet / blue / red lifted).
 *   ?glow=normal | premium (default premium).
 * Cost: the 10 tinted layers are built once per size (a few ms, after load, in idle time); a frame is two drawImage calls and runs only
 * during a cross-fade (~1 s every 3–5 s). Paused when the tab is hidden. prefers-reduced-motion: one static colour, no animation.
 * API: SOSTU.emblem.mount(el, base) where el = .eyemark (img + canvas); SOSTU.emblem.sweep() = go to the next colour now;
 *      SOSTU.emblem.perf; SOSTU.emblem.PALETTE.
 */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  // owner 4 Nov 2026 (final): the eye and its living iris stay exactly as in the image; only the energy light of the Σ changes colour.
  // No black / dark Σ, no colour over the iris.
  var PAL = ['#fb010d', '#f0abfc', '#e879f9', '#8b5cf6', '#3b82f6', '#60a5fa', '#22d3ee', '#67e8f9', '#a3e635', '#facc15'];
  var M = { c: [615.5, 621.5], r: 598.5, cr: [515, 513, 228], ic: [630.65, 627.22], ir: 210.57 };   // assets/eye/eye-meta.json (image px, emblem of 4 Nov 2026)
  var RM = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var Q = new URLSearchParams(location.search), MODE = Q.get('glow') === 'normal' ? 'normal' : 'premium';
  var K = MODE === 'premium' ? { core: 1, halo: 1.1, hr: 4.5, white: .62, bloom: [1.3, .6], bloomA: [.6, .75], boost: .35 } : { core: .8, halo: .6, hr: 4.5, white: .9, bloom: null, bloomA: null, boost: 0 };
  function rgb(h) { var n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
  function lum(c) { var f = function (v) { v /= 255; return v <= .04045 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); }
  var COLS = PAL.map(function (h) { var c = rgb(h); return { hex: h, c: c, g: Math.max(.72, Math.min(1.3, Math.pow(.3 / lum(c), .42))) }; });   // perceptual balance
  var perf = { mounted: 0, changes: 0, frames: 0, longestMs: 0, buildMs: 0, mode: MODE, current: null, sequence: [] };
  var fieldData = null, field = null, inst = [];
  function rnd() { try { var a = new Uint32Array(1); root.crypto.getRandomValues(a); return a[0] / 4294967296; } catch (e) { return Math.random(); } }
  function loadField(base, cb) {
    if (fieldData) return cb();
    if (!field) { field = new Image(); field.decoding = 'async'; field.src = base + 'universe/assets/sigma/sigma-eye-field.png'; }
    var go = function () { try { var c = document.createElement('canvas'); c.width = field.naturalWidth; c.height = field.naturalHeight; var g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(field, 0, 0); fieldData = { w: c.width, d: g.getImageData(0, 0, c.width, c.height).data }; } catch (e) { fieldData = null; } cb(); };
    if (field.complete && field.naturalWidth) go(); else field.addEventListener('load', go, { once: true });
  }
  function Emblem(el) {
    var cv = el.querySelector('canvas'), ctx = cv.getContext('2d'), layers = [], sepL = null, cur = -1, nxt = -1, tf = 0, dur = 1000, raf = 0, timer = 0;
    function build() {
      var t0 = performance.now(), css = el.getBoundingClientRect().width || 56, dpr = Math.min(root.devicePixelRatio || 1, 3), P = Math.round(css * dpr);
      cv.width = cv.height = P; var k = P / (2 * M.r), ox = (M.cr[0] - (M.c[0] - M.r)) * k, oy = (M.cr[1] - (M.c[1] - M.r)) * k, side = M.cr[2] * k;
      var N = Math.max(24, Math.ceil(side * 2)), fw = fieldData.w, d = fieldData.d, px = fw / N;
      // DIRECTIVA 4E §1, small sizes (header 56 / 44 px: the Σ is only ~10 px wide): same geometry (same field), the halo stays as tight as
      // in 4D (it does not blur the letter), a thin dark separation band (~1 device px) outlines the strokes against the red iris,
      // the near-white core is a little stronger and the iris reflection lower. Large sizes keep the 4D look.
      // DIRECTIVA 4H (SIGMA SUPERNOVA GLOW) replaces that band in premium mode: a double layer, an inner emission (saturated colour with
      // a luminous core that stays tinted, white mix 0.5) and an outer chromatic glow (two blurred copies of the stroke itself, so the
      // glow follows the silhouette and is never a rectangle), a stronger iris reflection, and a short intensity rise during each change.
      var small = css < 72 && MODE !== 'premium', hr = K.hr, hw = 11, coreK = css < 72 ? 1.3 : 1.15, dpx = px * N / side;   // dpx: field px per device px
      var bs = P / 56;                                                                           // blur radii scale with the emblem pixel size
      var sep = new Float32Array(N * N);
      // per-pixel masks, computed once: core (near-white centreline), edge colour, halo (outside, windowed)
      var core = new Float32Array(N * N), body = new Float32Array(N * N), halo = new Float32Array(N * N);
      for (var y = 0; y < N; y++) for (var x = 0; x < N; x++) {
        var fx = Math.min(fw - 1, Math.floor((x + .5) / N * fw)), fy = Math.min(fw - 1, Math.floor((y + .5) / N * fw)), q = (fy * fw + fx) * 4;
        var sd = (d[q] / 255 - .5) * 48, cl = d[q + 2] / 255 * 64, i = y * N + x;
        var cov = Math.max(0, Math.min(1, (sd / px + .7) / 1.4)); body[i] = cov; core[i] = cov * Math.exp(-cl * cl / 26);
        var out = Math.max(0, -sd), win = Math.max(0, 1 - out / hw); halo[i] = (1 - cov) * Math.exp(-out / hr) * win * win;
        if (small) { var o1 = out / dpx - .7; sep[i] = o1 > 0 ? Math.min(1, o1 / .5) * Math.exp(-Math.max(0, o1 - .5) / 1.1) * .8 : 0; }   // starts ~0.7 device px outside the stroke: the letter keeps its full body
      }
      sepL = null;
      if (small) { var sc = document.createElement('canvas'); sc.width = sc.height = N; var sg = sc.getContext('2d'), si = sg.createImageData(N, N);
        for (var q2 = 0; q2 < N * N; q2++) { si.data[q2 * 4] = 22; si.data[q2 * 4 + 1] = 0; si.data[q2 * 4 + 2] = 3; si.data[q2 * 4 + 3] = sep[q2] * 255; }
        sg.putImageData(si, 0, 0); sepL = document.createElement('canvas'); sepL.width = sepL.height = P; var sl = sepL.getContext('2d'); sl.imageSmoothingEnabled = true; sl.drawImage(sc, ox, oy, side, side); }
      layers = COLS.map(function (C) {
        var lc = document.createElement('canvas'); lc.width = lc.height = P; var g = lc.getContext('2d');
        // only the Σ and a tight glow around its strokes are painted: the iris and the rest of the image stay untouched
        var oc = document.createElement('canvas'); oc.width = oc.height = N; var og = oc.getContext('2d'), im = og.createImageData(N, N), a = im.data, gg = C.g;
        for (var i = 0; i < N * N; i++) {
          var j = i * 4, w = Math.min(1, core[i] * coreK * K.core), b = body[i], h = halo[i] * K.halo * gg;
          var al = Math.min(1, b * .97 + h * (1 - b)), m = al > 0 ? b / Math.max(al, 1e-4) : 0;   // m: share of the stroke vs the halo
          var r = C.c[0] * gg, gr = C.c[1] * gg, bl = C.c[2] * gg;
          a[j] = Math.min(255, r + (255 - r) * w * K.white * m); a[j + 1] = Math.min(255, gr + (250 - gr) * w * K.white * m); a[j + 2] = Math.min(255, bl + (246 - bl) * w * K.white * m); a[j + 3] = al * 255;
        }
        og.putImageData(im, 0, 0); g.imageSmoothingEnabled = true;
        if (K.bloom) {                                   // outer glow: the stroke in its colour, blurred twice, added ('lighter')
          var bc = document.createElement('canvas'); bc.width = bc.height = N; var bg = bc.getContext('2d'), bi = bg.createImageData(N, N);
          for (var i2 = 0; i2 < N * N; i2++) { bi.data[i2 * 4] = Math.min(255, C.c[0] * gg); bi.data[i2 * 4 + 1] = Math.min(255, C.c[1] * gg); bi.data[i2 * 4 + 2] = Math.min(255, C.c[2] * gg); bi.data[i2 * 4 + 3] = body[i2] * 255; }
          bg.putImageData(bi, 0, 0); g.globalCompositeOperation = 'lighter';
          for (var L = 0; L < 2; L++) { g.filter = 'blur(' + (K.bloom[L] * bs).toFixed(2) + 'px)'; g.globalAlpha = K.bloomA[L]; g.drawImage(bc, ox, oy, side, side); }
          g.filter = 'none'; g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
        }
        g.drawImage(oc, ox, oy, side, side);             // inner emission on top: crisp stroke, tinted luminous core
        return lc;
      });
      perf.buildMs = Math.round(performance.now() - t0);
    }
    function pick() { var n; do { n = Math.floor(rnd() * PAL.length); } while (n === cur); return n; }
    function paint(x) {
      ctx.clearRect(0, 0, cv.width, cv.height); if (sepL) ctx.drawImage(sepL, 0, 0); ctx.globalCompositeOperation = 'lighter';
      var e = x * x * (3 - 2 * x), op = function () { return 'lighter'; };
      if (cur >= 0 && e < 1) { ctx.globalCompositeOperation = op(cur); ctx.globalAlpha = 1 - e; ctx.drawImage(layers[cur], 0, 0); }
      if (nxt >= 0) { ctx.globalCompositeOperation = op(nxt); ctx.globalAlpha = e; ctx.drawImage(layers[nxt], 0, 0); if (K.boost && x > 0 && x < 1) { ctx.globalAlpha = K.boost * Math.sin(Math.PI * x); ctx.drawImage(layers[nxt], 0, 0); } }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    }
    function frame(now) {
      raf = 0; var t0 = performance.now(), x = Math.min(1, (now - tf) / dur); paint(x); perf.frames++;
      var dt = performance.now() - t0; if (dt > perf.longestMs) perf.longestMs = +dt.toFixed(2);
      if (x < 1) raf = requestAnimationFrame(frame); else { cur = nxt; nxt = -1; hold(); }
    }
    function change() {
      if (document.hidden || !layers.length) return; clearTimeout(timer);
      if (nxt >= 0) cur = nxt; nxt = pick(); dur = 800 + rnd() * 400; tf = performance.now(); perf.changes++; perf.current = PAL[nxt];
      perf.sequence.push(PAL[nxt]); if (perf.sequence.length > 40) perf.sequence.shift();
      if (!raf) raf = requestAnimationFrame(frame);
    }
    function hold() { clearTimeout(timer); timer = setTimeout(change, 2000 + rnd() * 2000); }
    build();
    if (RM) { cur = 0; nxt = -1; paint(0); perf.current = PAL[0]; return { next: function () {}, show: function (i) { cur = i; paint(0); } }; }   // static, recognisable Σ (official red)
    cur = -1; change();                                       // first colour fades in from the plain image
    var a = el.closest('a') || el;
    a.addEventListener('pointerenter', function () { if (nxt < 0) change(); });      // interaction: go to the next colour now (same smooth fade)
    document.addEventListener('visibilitychange', function () { if (document.hidden) { clearTimeout(timer); if (raf) cancelAnimationFrame(raf); raf = 0; if (nxt >= 0) { cur = nxt; nxt = -1; } paint(1); } else hold(); });
    var rz = 0; addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { var w = Math.round((el.getBoundingClientRect().width || 56) * Math.min(root.devicePixelRatio || 1, 3)); if (w !== cv.width) { build(); paint(nxt >= 0 ? 0 : 1); } }, 150); });
    return { next: function () { if (nxt < 0) change(); }, show: function (i) { clearTimeout(timer); if (raf) cancelAnimationFrame(raf); raf = 0; cur = i; nxt = -1; paint(0); } };
  }
  function mount(el, base) {
    return;   // owner 12-Nov-2026: Gold Sigma / Rainbow Edition logo; this overlay painted the OLD eye's Sigma geometry over it (retired)
    if (!el || el.__emb) return; el.__emb = 1;
    loadField(base || '../', function () { if (!fieldData) return; inst.push(Emblem(el)); perf.mounted++; el.classList.add('live'); });
  }
  U.emblem = { mount: mount, perf: perf, PALETTE: PAL, mode: MODE, sweep: function () { inst.forEach(function (e) { e.next(); }); },
    show: function (i) { inst.forEach(function (e) { e.show(i); }); } };   // tests only: hold colour i (static)
})(window);

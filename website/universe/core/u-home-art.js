/* SOST Universe — Home layout v2 art (owner mockup HOME_LAYOUT_owner_2026-11-04.png).
 *  - #chainCv: a chain of glass blocks leaving the singularity towards the right edge (the chain the computation converges into).
 *    It starts outside the singularity's centre (DIRECTIVAS 4C-1: the centre stays free) and reads the shared geometry of
 *    #coreAnchor (--ex, --ey, --ed), so it follows the scene on every size. Desktop layouts only (CSS hides it below 1100 px).
 *  - .hc canvas: the four animated cards (15-11-2026): Real PoW two crests, SOST Blockchain 3D cubes, Accessible Mining energy
 *    field, Expanding Ecosystem orbits. One rAF loop, paused off-screen / hidden tab, still frame under reduced motion.
 * The chain is drawn once per resize (its soft glow is a CSS opacity animation).
 * No data, no network, no dependency on the scene engine. */
(function (root) {
  'use strict';
  var doc = root.document;
  function hex(h) { h = h.replace('#', ''); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]; }
  function mix(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
  function ramp(pal, t) { t = Math.max(0, Math.min(1, t)) * (pal.length - 1); var i = Math.min(pal.length - 2, Math.floor(t)); return mix(pal[i], pal[i + 1], t - i); }
  function rgba(c, a) { return 'rgba(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ',' + a + ')'; }
  function fit(cv) {
    var r = cv.getBoundingClientRect(), d = Math.min(2, root.devicePixelRatio || 1), w = Math.max(1, Math.round(r.width * d)), h = Math.max(1, Math.round(r.height * d));
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    var g = cv.getContext('2d'); g.setTransform(d, 0, 0, d, 0, 0); g.clearRect(0, 0, r.width, r.height); return { g: g, w: r.width, h: r.height };
  }
  // an axis-aligned glass cube seen slightly from the left and above: front face, top and right side
  function cube(g, x, y, s, col, a) {
    var dx = s * .34, dy = s * .22;
    var F = [[x, y], [x + s, y], [x + s, y + s], [x, y + s]], T = [[x, y], [x + dx, y - dy], [x + s + dx, y - dy], [x + s, y]], R = [[x + s, y], [x + s + dx, y - dy], [x + s + dx, y + s - dy], [x + s, y + s]];
    function poly(P, fill) { g.beginPath(); g.moveTo(P[0][0], P[0][1]); for (var i = 1; i < P.length; i++) g.lineTo(P[i][0], P[i][1]); g.closePath(); if (fill) { g.fillStyle = fill; g.fill(); } }
    var gr = g.createLinearGradient(x, y, x + s, y + s); gr.addColorStop(0, rgba(col, .32 * a)); gr.addColorStop(1, rgba(col, .08 * a));
    poly(F, gr); poly(T, rgba(col, .26 * a)); poly(R, rgba(col, .16 * a));
    g.lineJoin = 'round';
    [[14, .22], [5, .45], [1.2, 1]].forEach(function (L) {
      g.shadowColor = rgba(col, .9 * a); g.shadowBlur = L[0]; g.strokeStyle = rgba(mix(col, [255, 255, 255], L[1] === 1 ? .45 : 0), L[1] * a); g.lineWidth = L[0] > 10 ? 2.2 : 1.2;
      poly(F); g.stroke(); poly(T); g.stroke(); poly(R); g.stroke();
    });
    g.shadowBlur = 0;
    // inner light
    var c = g.createRadialGradient(x + s * .5, y + s * .5, 0, x + s * .5, y + s * .5, s * .7); c.addColorStop(0, rgba(mix(col, [255, 255, 255], .5), .35 * a)); c.addColorStop(1, rgba(col, 0));
    g.fillStyle = c; g.fillRect(x - s * .2, y - s * .3, s * 1.6, s * 1.6);
  }
  var CHAIN = ['#fb923c', '#facc15', '#fb010d', '#e879f9', '#a3e635', '#22d3ee', '#3b82f6', '#8b5cf6', '#e879f9', '#22d3ee'].map(hex);
  function drawChain() {
    var cv = doc.getElementById('chainCv'), an = doc.getElementById('coreAnchor'); if (!cv || !an || cv.offsetParent === null) return;
    if (cv.getAttribute('data-live') === '1') return;   // P3: the interactive cubes (u-cubes.js) own the canvas; CUBES OFF gives it back
    var o = fit(cv), g = o.g, cs = root.getComputedStyle(an);
    var ex = parseFloat(cs.getPropertyValue('--ex')) || o.w * .66, ey = parseFloat(cs.getPropertyValue('--ey')) || o.h * .5, R = (parseFloat(cs.getPropertyValue('--ed')) || 480) / 2;
    // the chain: consecutive blocks with a small gap, each a little smaller and higher (receding towards the right edge)
    var pts = [], x = ex + R * .5, sz = R * .27, y0 = ey;
    while (x < o.w - 4 && pts.length < 40) {
      var s = sz; if (x + s * 1.34 > o.w - 4) { s = (o.w - 4 - x) / 1.34; if (s < 10) break; }
      pts.push([x, y0 - s * .5, s, 0]); x += s * 1.34 + s * .22; sz *= .9; y0 -= s * .09;
    }
    pts.forEach(function (p, i) { p[3] = pts.length > 1 ? i / (pts.length - 1) : 0; });
    // link light between blocks
    g.strokeStyle = 'rgba(255,255,255,.35)'; g.lineWidth = 1.2; g.shadowColor = '#22d3ee'; g.shadowBlur = 8; g.beginPath();
    pts.forEach(function (p, i) { var cx = p[0] + p[2] * .5, cy = p[1] + p[2] * .5; if (i) g.lineTo(cx, cy); else g.moveTo(cx, cy); }); g.stroke(); g.shadowBlur = 0;
    pts.forEach(function (p) { cube(g, p[0], p[1], p[2], ramp(CHAIN, p[3]), .55 + .45 * Math.sin(Math.PI * Math.min(1, p[3] * 1.4 + .1))); });
    g.globalCompositeOperation = 'source-over';
  }
  /* ---- The four Home cards (owner order 15-11-2026: «cuatro tarjetas cinematográficas, perfectamente legibles») ----------
   * Each card keeps its text in the top-left. The art lives only in the space the text leaves free:
   *  - free[x] is the lowest text edge above column x (from the real line boxes of the title and description, plus the icon),
   *    so a short title leaves room for the art to rise on its right;
   *  - a feathered mask built once per layout removes any pixel near a line of text (safety net, never the main design tool).
   * One requestAnimationFrame loop drives the four cards. It runs only while a card is on screen and the tab is visible,
   * at 30 fps on small or modest devices, and never under prefers-reduced-motion or effects OFF (then one still frame). */
  var PAL = {
    pow: ['#fb010d', '#ff2d6f', '#e879f9', '#8b5cf6'].map(hex),
    chain: ['#22d3ee', '#38bdf8', '#3b82f6', '#8b5cf6'].map(hex),
    mine: ['#22d3ee', '#2dd4bf', '#34d399', '#a3e635'].map(hex),
    eco: ['#8b5cf6', '#e879f9', '#fb923c', '#facc15', '#22d3ee', '#8b5cf6'].map(hex)
  };
  var sprites = {};
  function sprite(c) {          // a soft round light, drawn once per colour and reused (no per-frame gradients for particles)
    var k = c.map(function (v) { return v | 0; }).join(',');
    if (sprites[k]) return sprites[k];
    var s = doc.createElement('canvas'); s.width = s.height = 32; var g = s.getContext('2d'), r = g.createRadialGradient(16, 16, 0, 16, 16, 16);
    r.addColorStop(0, rgba(mix(c, [255, 255, 255], .55), 1)); r.addColorStop(.25, rgba(c, .65)); r.addColorStop(1, rgba(c, 0));
    g.fillStyle = r; g.fillRect(0, 0, 32, 32); return (sprites[k] = s);
  }
  function dot(g, c, x, y, r, a) { if (a <= .01) return; g.globalAlpha = Math.min(1, a); g.drawImage(sprite(c), x - r, y - r, 2 * r, 2 * r); g.globalAlpha = 1; }
  function smooth(e) { e = Math.max(0, Math.min(1, e)); return e * e * (3 - 2 * e); }

  // layout of one card: canvas size, text boxes, free-space profile and the feathered mask
  function layout(C) {
    var cv = C.cv, r = cv.getBoundingClientRect(), small = r.width < 420 || root.innerWidth < 760;
    var d = Math.min(small ? 1.5 : 2, root.devicePixelRatio || 1), W = Math.max(1, r.width), H = Math.max(1, r.height);
    cv.width = Math.round(W * d); cv.height = Math.round(H * d);
    var g = cv.getContext('2d'); g.setTransform(d, 0, 0, d, 0, 0);
    var boxes = [], pad = small ? 7 : 8;
    function add(b) { if (b.width > 0 && b.height > 0) boxes.push({ l: b.left - r.left - pad, t: b.top - r.top - pad, r: b.right - r.left + pad, b: b.bottom - r.top + pad }); }
    var icon = C.el.querySelector('svg'); if (icon) add(icon.getBoundingClientRect());
    C.el.querySelectorAll('h3,p').forEach(function (n) {
      try { var rg = doc.createRange(); rg.selectNodeContents(n); Array.prototype.forEach.call(rg.getClientRects(), add); } catch (e) { add(n.getBoundingClientRect()); }
    });
    var free = new Float32Array(Math.ceil(W) + 1), tb = 0, tr = 0;
    boxes.forEach(function (b) { tb = Math.max(tb, b.b); tr = Math.max(tr, b.r); });
    for (var x = 0; x < free.length; x++) { var f = 6; for (var i = 0; i < boxes.length; i++) if (x >= boxes[i].l && x <= boxes[i].r) f = Math.max(f, boxes[i].b); free[x] = f; }
    // soften the profile (dilate 26 px, then two 10 px box blurs): the art bends smoothly around the text, never in steps,
    // and the softened ceiling always stays at or above the real one
    var N = free.length, dl = new Float32Array(N), tmp = new Float32Array(N);
    for (x = 0; x < N; x++) { var mx = 0; for (var j = Math.max(0, x - 26); j <= Math.min(N - 1, x + 26); j++) mx = Math.max(mx, free[j]); dl[x] = mx; }
    for (var pass = 0; pass < 2; pass++) {
      for (x = 0; x < N; x++) { var sm = 0, cn = 0; for (j = Math.max(0, x - 10); j <= Math.min(N - 1, x + 10); j++) { sm += dl[j]; cn++; } tmp[x] = sm / cn; }
      dl.set(tmp);
    }
    for (x = 0; x < N; x++) free[x] = Math.max(free[x], dl[x]);
    // mask: 1 where art may show, 0 on the text, a soft edge in between and a gentle fade at the card's left/right edges
    var m = C.mask || doc.createElement('canvas'); m.width = cv.width; m.height = cv.height;
    var mg = m.getContext('2d'); mg.setTransform(d, 0, 0, d, 0, 0); mg.globalCompositeOperation = 'source-over'; mg.clearRect(0, 0, W, H);
    var ed = mg.createLinearGradient(0, 0, W, 0); ed.addColorStop(0, 'rgba(0,0,0,0)'); ed.addColorStop(Math.min(.2, 14 / W), '#000'); ed.addColorStop(Math.max(.8, 1 - 10 / W), '#000'); ed.addColorStop(1, 'rgba(0,0,0,0)');
    mg.fillStyle = ed; mg.fillRect(0, 0, W, H);
    mg.globalCompositeOperation = 'destination-out';
    var F = 6, steps = 6;
    boxes.forEach(function (b) { for (var s = steps; s >= 0; s--) { var k = F * s / steps; mg.fillStyle = 'rgba(0,0,0,' + (s === 0 ? 1 : .32) + ')'; mg.fillRect(b.l - k, b.t - k, b.r - b.l + 2 * k, b.b - b.t + 2 * k); } });
    C.mask = m; C.g = g; C.W = W; C.H = H; C.d = d; C.free = free; C.tb = tb; C.tr = tr; C.small = small;
    C.freeAt = function (x) { return free[Math.max(0, Math.min(free.length - 1, x | 0))]; };
    C.grad = null; C.fit = null;   // per-layout caches
  }

  // 1. REAL PoW — two smooth crests (sum of two Gaussians) drawn as fine light strands, with work pulses running along them
  function artPow(C, t) {
    var g = C.g, W = C.W, H = C.H, y0 = H - Math.max(9, H * .09), n = C.small ? 7 : 11;
    if (!C.grad) { C.grad = g.createLinearGradient(0, 0, W, 0); PAL.pow.forEach(function (c, i) { C.grad.addColorStop(i / (PAL.pow.length - 1), rgba(c, 1)); }); }
    var room = function (x) { return Math.max(8, y0 - C.freeAt(x) - 5); };
    var b2 = .79; if (room(W * b2) < H * .35) b2 = Math.max(b2, Math.min(.9, (C.tr + W * .03) / W));   // move the crest to free space
    var c1 = W * (.5 + .015 * Math.sin(t * .23)), c2 = W * (b2 + .012 * Math.sin(t * .19 + 1.3));
    var A1 = Math.min(room(c1), H * .62), A2 = Math.min(room(c2), H * .74), s1 = W * .085, s2 = W * .07;
    function y(x, k, ph) {
      var e1 = (x - c1) / s1, e2 = (x - c2) / s2, br = 1 + .07 * Math.sin(t * .8 + ph);
      return y0 - (A1 * Math.exp(-e1 * e1) * (1 - .05 * k) + A2 * Math.exp(-e2 * e2) * (1 - .04 * k)) * br * .94 + Math.sin(x * .045 + t * .9 + k * .6) * (1 + k * .18) + k * 1.15;
    }
    g.globalCompositeOperation = 'lighter'; g.strokeStyle = C.grad; g.lineJoin = 'round';
    for (var k = n - 1; k >= 0; k--) {
      var ph = k * .55; g.globalAlpha = .1 + .55 * Math.pow(1 - k / n, 1.6); g.lineWidth = k === 0 ? 1.4 : .9;
      g.beginPath(); for (var x = 0; x <= W; x += 2) { var yy = y(x, k, ph); if (x) g.lineTo(x, yy); else g.moveTo(x, yy); } g.stroke();
    }
    g.globalAlpha = .22; g.lineWidth = 5; g.beginPath(); for (var q = 0; q <= W; q += 3) { var yq = y(q, 0, 0); if (q) g.lineTo(q, yq); else g.moveTo(q, yq); } g.stroke();
    g.globalAlpha = 1;
    // work pulses: they climb the two crests from left to right and wrap off-screen (the edge mask hides the wrap)
    var P = C.small ? 5 : 8;
    for (var i = 0; i < P; i++) {
      var u = ((t * (.045 + .012 * (i % 3)) + i / P) % 1), x2 = u * W, ci = ramp(PAL.pow, u);
      dot(g, ci, x2, y(x2, i % 3, (i % 3) * .55), C.small ? 5 : 6, .85 * Math.sin(Math.PI * u));
    }
  }

  // 2. SOST BLOCKCHAIN — glass cubes in perspective, joined by light links; the row recedes to the upper right, new blocks
  //    appear far away and the whole chain drifts slowly towards the viewer. A visual metaphor only (no chain data).
  function cube3(g, x, y, s, a, c) {
    var dx = s * .36, dy = s * .24;
    function P(pts) { g.beginPath(); g.moveTo(pts[0], pts[1]); for (var i = 2; i < pts.length; i += 2) g.lineTo(pts[i], pts[i + 1]); g.closePath(); }
    var Fr = [x, y, x + s, y, x + s, y + s, x, y + s], Tp = [x, y, x + dx, y - dy, x + s + dx, y - dy, x + s, y], Rt = [x + s, y, x + s + dx, y - dy, x + s + dx, y + s - dy, x + s, y + s];
    g.fillStyle = rgba(c, .16 * a); P(Fr); g.fill(); g.fillStyle = rgba(c, .2 * a); P(Tp); g.fill(); g.fillStyle = rgba(c, .1 * a); P(Rt); g.fill();
    [[3.2, .16], [1, .95]].forEach(function (L) {
      g.lineWidth = L[0]; g.strokeStyle = rgba(L[1] > .5 ? mix(c, [255, 255, 255], .35) : c, L[1] * a);
      P(Fr); g.stroke(); P(Tp); g.stroke(); P(Rt); g.stroke();
    });
    dot(g, c, x + s * .5, y + s * .5, s * .55, .45 * a);
  }
  function artChain(C, t) {
    var g = C.g, W = C.W, H = C.H, n = C.small ? 5 : 6, per = 3.2, ph = (t / per) % 1, qf = .82, step = 1.62;
    var nearX = Math.max(W * .3, W - (C.small ? 270 : 300)), farX = W - 12, yN = H - 9;
    // geometric row: block e (continuous) has size sN*qf^e and starts at nearX + sN*step*(1-qf^e)/(1-qf), so size and spacing
    // shrink together with depth (no block ever overlaps its neighbour)
    var span = function (e) { return (1 - Math.pow(qf, e)) / (1 - qf); };
    var sN = Math.min(H * .4, 48, (farX - nearX) / (step * span(n) + 1.36 * Math.pow(qf, n)));
    var list = [];
    for (var i = -1; i <= n + 1; i++) {
      var e = i - ph; if (e < -1 || e > n) continue;
      var dd = e / n, s = sN * Math.pow(qf, e);
      var x = nearX + sN * step * span(e), yb = yN - sN * .42 * span(e);     // bottom of the front face
      var top = C.freeAt(x + s * .5) + 3, need = yb - s - s * .24;
      if (need < top) { yb += top - need; }                                    // keep clear of the text above
      if (yb > H - 4) { s -= yb - (H - 4); yb = H - 4; }
      var a = smooth((e + 1) / 1.1) * smooth((n - e) / 1.2);
      list.push({ x: x, y: yb - s, s: s, a: a, dd: dd });
    }
    list.sort(function (p, q) { return q.dd - p.dd; });
    g.globalCompositeOperation = 'lighter';
    var ord = list.slice().sort(function (p, q) { return p.dd - q.dd; });
    for (var j = 0; j + 1 < ord.length; j++) {                                 // links + a pulse running towards the newest block
      var A = ord[j], B = ord[j + 1], ax = A.x + A.s * .5, ay = A.y + A.s * .5, bx = B.x + B.s * .5, by = B.y + B.s * .5, la = Math.min(A.a, B.a);
      g.strokeStyle = rgba(PAL.chain[1], .35 * la); g.lineWidth = 1; g.beginPath(); g.moveTo(ax, ay); g.lineTo(bx, by); g.stroke();
      var u = (t * .55 + j * .37) % 1; dot(g, PAL.chain[0], ax + (bx - ax) * u, ay + (by - ay) * u, 4, .8 * la * Math.sin(Math.PI * u));
    }
    list.forEach(function (p) { cube3(g, p.x, p.y, p.s, p.a * (.75 + .25 * (1 - p.dd)), ramp(PAL.chain, Math.max(0, Math.min(1, p.dd)))); });
  }

  // 3. ACCESSIBLE MINING — many small contributions: a field of thin light bars whose tops form one soft energy line, with
  //    sparks rising from it (each bar a participant). Different from Real PoW: vertical, granular, wide and calm.
  function artMine(C, t) {
    var g = C.g, W = C.W, H = C.H, gap = C.small ? 6 : 5, base = H - 8, x0 = 10, x1 = W - 8;
    function lvl(x) { return .5 + .24 * Math.sin(x * .021 + t * .55) + .16 * Math.sin(x * .049 - t * .8 + 1.7) + .1 * Math.sin(x * .093 + t * 1.15); }
    function top(x) { var room = Math.max(6, base - C.freeAt(x) - 6), env = Math.sin(Math.PI * (x - x0) / (x1 - x0)); return base - Math.min(room, H * .5) * (.18 + .82 * lvl(x)) * (.35 + .65 * env); }
    g.globalCompositeOperation = 'lighter';
    for (var x = x0; x <= x1; x += gap) {
      var yt = top(x), c = ramp(PAL.mine, (x - x0) / (x1 - x0)), gr = g.createLinearGradient(0, yt, 0, base);
      gr.addColorStop(0, rgba(c, .75)); gr.addColorStop(1, rgba(c, .03)); g.strokeStyle = gr; g.lineWidth = 1.2;
      g.beginPath(); g.moveTo(x, base); g.lineTo(x, yt); g.stroke();
    }
    if (!C.grad) { C.grad = g.createLinearGradient(0, 0, W, 0); PAL.mine.forEach(function (c, i) { C.grad.addColorStop(i / (PAL.mine.length - 1), rgba(c, 1)); }); }
    g.strokeStyle = C.grad; g.lineJoin = 'round';
    [[4, .18], [1.3, .9]].forEach(function (L) { g.lineWidth = L[0]; g.globalAlpha = L[1]; g.beginPath(); for (var q = x0; q <= x1; q += 2) { var yq = top(q) - 1.5; if (q > x0) g.lineTo(q, yq); else g.moveTo(q, yq); } g.stroke(); });
    g.globalAlpha = 1;
    var S = C.small ? 7 : 12;
    for (var i = 0; i < S; i++) {                                               // sparks: shares rising from the line
      var sx = x0 + ((i * 0.618034 + Math.floor(t / 4 + i / S) * .29) % 1) * (x1 - x0), life = (t / 4 + i / S) % 1;
      var sy = top(sx) - life * Math.min(26, H * .22);
      if (sy < C.freeAt(sx) + 2) continue;
      dot(g, ramp(PAL.mine, (sx - x0) / (x1 - x0)), sx, sy, 3.5, .9 * Math.sin(Math.PI * life));
    }
  }

  // 4. EXPANDING ECOSYSTEM — a small universe of connected nodes on tilted orbits around a bright core, with rings expanding
  //    outwards and new nodes travelling out to join the network.
  function artEco(C, t) {
    var g = C.g, W = C.W, H = C.H, tilt = .36;
    if (!C.fit) {                       // once per layout: the largest tilted orbit that fits in the space the text leaves free
      var best = { R: 0, cx: W * .7, cy: H * .7 }, Rmax = Math.min(W * .34, C.small ? 118 : 140);
      for (var cx0 = W * .4; cx0 <= W - 30; cx0 += 6) {
        var lo = 0, hi = Math.min(Rmax, W - 12 - cx0, cx0 - 10);
        for (var b = 0; b < 12 && hi > 0; b++) {
          var R0 = (lo + hi) / 2, ry0 = R0 * tilt, cy0 = H - ry0 - 8, ok = true;
          for (var xx = -R0; xx <= R0 && ok; xx += 3) if (cy0 - ry0 * Math.sqrt(Math.max(0, 1 - (xx / R0) * (xx / R0))) < C.freeAt(cx0 + xx) + 4) ok = false;
          if (ok) lo = R0; else hi = R0;
        }
        if (lo > best.R + .5 || (Math.abs(lo - best.R) <= .5 && cx0 > best.cx)) best = { R: lo, cx: cx0, cy: H - lo * tilt - 8 };
      }
      C.fit = best;
    }
    var R = C.fit.R, cx = C.fit.cx, cy = C.fit.cy, ryMax = R * tilt;
    if (R < 16) return;
    var orb = [[.38, 4, .5], [.68, 6, -.32], [1, 8, .2]], nodes = [];
    g.globalCompositeOperation = 'lighter';
    orb.forEach(function (o, oi) {
      var rx = R * o[0], ry = rx * tilt;
      g.strokeStyle = rgba(PAL.eco[oi * 2], .16); g.lineWidth = 1; g.beginPath(); g.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2); g.stroke();
      for (var i = 0; i < o[1]; i++) {
        var an = t * o[2] * .35 + i * Math.PI * 2 / o[1] + oi, z = Math.sin(an);
        nodes.push({ x: cx + Math.cos(an) * rx, y: cy + z * ry, z: z, c: ramp(PAL.eco, (i / o[1] + oi * .3 + t * .02) % 1), o: oi });
      }
    });
    for (var a = 0; a < nodes.length; a++) for (var b = a + 1; b < nodes.length; b++) {     // links between near nodes
      var p = nodes[a], q = nodes[b], dx = p.x - q.x, dy = p.y - q.y, dd = Math.sqrt(dx * dx + dy * dy), lim = R * .48;
      if (dd < lim && Math.abs(p.o - q.o) <= 1) {
        g.strokeStyle = rgba(mix(p.c, q.c, .5), .32 * (1 - dd / lim) * (.55 + .45 * (p.z + q.z + 2) / 4)); g.lineWidth = .9;
        g.beginPath(); g.moveTo(p.x, p.y); g.lineTo(q.x, q.y); g.stroke();
      }
    }
    for (var e = 0; e < 2; e++) {                                                // rings expanding from the core
      var u = (t / 5.5 + e * .5) % 1, rr = R * (.15 + 1.05 * u);
      g.strokeStyle = rgba(ramp(PAL.eco, u), .3 * Math.sin(Math.PI * u)); g.lineWidth = 1.2; g.beginPath(); g.ellipse(cx, cy, rr, rr * tilt, 0, 0, Math.PI * 2); g.stroke();
    }
    for (var m = 0; m < 3; m++) {                                                // new nodes leaving the core to join the network
      var v = (t / 3.7 + m / 3) % 1, an2 = m * 2.1 + Math.floor(t / 3.7 + m / 3) * 1.3;
      dot(g, ramp(PAL.eco, (m / 3 + v * .3) % 1), cx + Math.cos(an2) * R * v, cy + Math.sin(an2) * R * tilt * v, 4, Math.sin(Math.PI * v) * .9);
    }
    nodes.sort(function (p, q) { return p.z - q.z; }).forEach(function (p) { dot(g, p.c, p.x, p.y, 3 + 2.2 * (p.z + 1), .5 + .4 * (p.z + 1) / 2); });
    dot(g, [255, 255, 255], cx, cy, 9, .55); dot(g, PAL.eco[1], cx, cy, 16, .55);
  }

  var ART = { wave: artPow, cubes: artChain, mine: artMine, eco: artEco };
  var cards = [], motion = true, raf = 0, prev = 0, slow = false;
  function frame(C, t) {
    var g = C.g; g.globalCompositeOperation = 'source-over'; g.globalAlpha = 1; g.clearRect(0, 0, C.W, C.H);
    try { (ART[C.kind] || artPow)(C, t); } catch (e) {}
    g.globalCompositeOperation = 'destination-in'; g.globalAlpha = 1; g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(C.mask, 0, 0); g.setTransform(C.d, 0, 0, C.d, 0, 0);
    g.globalCompositeOperation = 'source-over';
  }
  var STILL = 7.3;   // the composed still frame (reduced motion, effects OFF, or before the loop starts)
  function want() { return motion && !doc.hidden && !doc.body.classList.contains('static') && cards.some(function (C) { return C.vis; }); }
  var clock = STILL;  // continuous: advances only while the loop runs, so pausing and resuming never jumps
  function tick(now) {
    raf = 0; if (!want()) { prev = 0; return; }
    raf = root.requestAnimationFrame(tick);
    if (slow && prev && now - prev < 31) return;
    if (prev) clock += Math.min(.1, (now - prev) / 1000); prev = now;
    cards.forEach(function (C) { if (C.vis && C.g) frame(C, clock); });
  }
  function run() { if (!raf && want()) raf = root.requestAnimationFrame(tick); }
  function still() { cards.forEach(function (C) { if (C.g) frame(C, clock); }); }
  function relayout() { cards.forEach(function (C) { try { layout(C); } catch (e) {} }); still(); run(); }
  function initCards() {
    doc.querySelectorAll('.hc').forEach(function (el) {
      var cv = el.querySelector('canvas'); if (!cv) return;
      cards.push({ el: el, cv: cv, kind: el.getAttribute('data-art') || 'wave', vis: true });
    });
    if (!cards.length) return;
    var mq = root.matchMedia ? root.matchMedia('(prefers-reduced-motion: reduce)') : null;
    var nav = root.navigator || {};
    slow = root.innerWidth < 760 || (nav.hardwareConcurrency && nav.hardwareConcurrency <= 4) || (nav.deviceMemory && nav.deviceMemory <= 4) || (nav.connection && nav.connection.saveData);
    function setMotion() { motion = !(mq && mq.matches); if (!motion) { still(); } else run(); }
    if (mq) { if (mq.addEventListener) mq.addEventListener('change', setMotion); else if (mq.addListener) mq.addListener(setMotion); }
    motion = !(mq && mq.matches);
    if ('IntersectionObserver' in root) {
      var io = new IntersectionObserver(function (es) { es.forEach(function (e) { cards.forEach(function (C) { if (C.el === e.target) C.vis = e.isIntersecting; }); }); run(); }, { rootMargin: '80px' });
      cards.forEach(function (C) { io.observe(C.el); });
    }
    if ('ResizeObserver' in root) { var ro = new ResizeObserver(laterCards); cards.forEach(function (C) { ro.observe(C.el); }); }
    doc.addEventListener('visibilitychange', run);
    if ('MutationObserver' in root) new MutationObserver(function () { if (doc.body.classList.contains('static')) still(); else run(); }).observe(doc.body, { attributes: true, attributeFilter: ['class'] });
    relayout();
  }
  var tc = 0; function laterCards() { clearTimeout(tc); tc = setTimeout(relayout, 100); }
  root.SOSTCardArt = { still: still, relayout: relayout, frame: function (t, only) { cards.forEach(function (C, i) { if (C.g && (only === undefined || only === i)) frame(C, t); }); } };

  function all() { try { drawChain(); } catch (e) {} }
  var tm = 0; function later() { clearTimeout(tm); tm = setTimeout(all, 120); }
  function boot() { all(); try { initCards(); } catch (e) {} root.addEventListener('resize', later); if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(function () { all(); try { relayout(); } catch (e) {} }); }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot); else boot();
  root.SOSTHomeArt = { redraw: all };
})(window);

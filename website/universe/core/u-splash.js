/* SOST Universe — Matrix Genesis splash (DIRECTIVAS 4C-1 §5, 3 nov 2026). Canvas 2D on the CPU, 7.8 s, skippable from the first frame,
 * never blocks the header or the content underneath. Never an eye in the core, never SOST text (the name lives in the header only).
 *
 *  0.0–2.4 s  MATRIX GENESIS   dense, clearly visible red Matrix rain (white glowing heads, long trails), boot log with the real tip
 *  2.2–3.6 s  DISINTEGRATION   the glyphs break into particles that turn into the official spectrum (css/atomix-btn.css); the code
 *                              becomes mathematical geometry (a five-petal rose, a polar grid)
 *  3.4–5.8 s  CONVERGENCE      the particles accelerate onto the singularity: the tilted torus and the rim of its black heart
 *  5.8–7.8 s  REVEAL           energy wave; the backdrop dissolves into the hero, where the restored singularity (poster, then WebGL)
 *                              sits exactly where the splash converged (geometry from window.__coreGeo)
 * Starts after the first frame has been presented (two rAF: the WSLg / D3D12 first-frame stall stays outside the animation).
 * Light mode (≤ 4 cores, ≤ 4 GB, Save-Data, ?splash=light, or slow first frames): fewer particles, DPR 1. Reduced motion: a still card.
 * API: SOSTU.splash.play({ overlay, canvas, target:fn->{x,y,r}, scene, tip:fn->{h,status}|null, onReveal, onDone }) -> { skip, perf }
 */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  // once per browsing SESSION (owner P0, 5 Nov 2026): sessionStorage, so a new session shows the intro again and moving between pages
  // of the same session never replays it. It was localStorage (sostu_splash_seen_v3): seen once, never again in that browser.
  var KEY = 'sostu_splash_session_v4', TOTAL = 7.8;
  var SPEC = ['#8b5cf6', '#e879f9', '#3b82f6', '#22d3ee', '#a3e635', '#facc15', '#fb923c'];
  var REDS = ['#fb010d', '#ff2d3b', '#fb010d', '#8b1a22', '#fb010d', '#ff2d3b'];
  // spectrum of the Chromatic Sigma Pulse (same order and values as the shader)
  var SP = [[251, 1, 13], [232, 121, 249], [139, 92, 246], [59, 130, 246], [34, 211, 238], [163, 230, 53], [250, 204, 21], [251, 146, 60], [251, 1, 13]];
  var GLY = 'アイウエオカキクケコサシスセソタチツテトΣ0123456789ABCDEF$#@&*+=<>'.split('');
  function ease(x) { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); }
  function eo(x) { x = Math.max(0, Math.min(1, x)); return 1 - Math.pow(1 - x, 3); }
  function seen() { try { return sessionStorage.getItem(KEY) === '1'; } catch (e) { return false; } }
  function mark() { try { sessionStorage.setItem(KEY, '1'); } catch (e) {} }
  function lightWanted() {
    var q = new URLSearchParams(location.search).get('splash'); if (q === 'light') return true; if (q === 'full') return false;
    var n = navigator, c = n.connection || {};
    return (n.hardwareConcurrency || 8) <= 4 || (n.deviceMemory || 8) <= 4 || !!c.saveData;
  }
  function spec(x, out) { x = Math.max(0, Math.min(1, x)) * 8; var i = Math.min(7, Math.floor(x)), f = x - i, a = SP[i], b = SP[i + 1]; out[0] = a[0] + (b[0] - a[0]) * f; out[1] = a[1] + (b[1] - a[1]) * f; out[2] = a[2] + (b[2] - a[2]) * f; return out; }
  function sprite(r, col) {
    var c = document.createElement('canvas'), s = r * 2; c.width = c.height = s; var g = c.getContext('2d'), gr = g.createRadialGradient(r, r, 0, r, r, r);
    gr.addColorStop(0, col); gr.addColorStop(.25, col + 'aa'); gr.addColorStop(1, col + '00'); g.fillStyle = gr; g.fillRect(0, 0, s, s); return c;
  }
  function img(src) { var i = new Image(); i.decoding = 'async'; i.src = src; return i; }
  function ok(i) { return i && i.complete && i.naturalWidth > 0; }

  /** CPU Chromatic Sigma Pulse: the official Σ field resampled to N×N device px; per frame only the texels near the glyph are shaded. */
  function SigmaCPU(field) {
    var src = null, N = 0, idx = null, sd = null, uu = null, cl = null, cv = document.createElement('canvas'), cx = cv.getContext('2d'), id = null, tmp = [0, 0, 0];
    function prep(n) {
      if (!ok(field)) return false; n = Math.max(24, Math.round(n)); if (n === N && idx) return true;
      if (!src) { var c = document.createElement('canvas'); c.width = field.naturalWidth; c.height = field.naturalHeight; var g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(field, 0, 0); src = { w: c.width, h: c.height, d: g.getImageData(0, 0, c.width, c.height).data }; }
      N = n; cv.width = cv.height = N; id = cx.createImageData(N, N); var I = [], S = [], Uu = [], Cl = [];
      for (var y = 0; y < N; y++) for (var x = 0; x < N; x++) {
        var fx = Math.min(src.w - 1, Math.floor((x + .5) / N * src.w)), fy = Math.min(src.h - 1, Math.floor((y + .5) / N * src.h)), k = (fy * src.w + fx) * 4;
        var s = (src.d[k] / 255 - .5) * 48; if (s < -23) continue;
        I.push((y * N + x) * 4); S.push(s); Uu.push(src.d[k + 1] / 255); Cl.push(src.d[k + 2] / 255 * 64);
      }
      idx = I; sd = S; uu = Uu; cl = Cl; return true;
    }
    return {
      // a: overall alpha of the Σ; sw: sweep position (−0.15 … 1.15); k: 0 soft / 1 energetic
      draw: function (ctx, X, Y, side, dpr, a, sw, k) {
        if (!prep(side * dpr)) return; var d = id.data; d.fill(0);
        var act = ease((sw + .2) / .2) * ease((1.2 - sw) / .2), wf = k ? .075 : .10, tl = k ? .22 : .30, px = 512 / N, boost = k ? 1.5 : 1;
        for (var i = 0; i < idx.length; i++) {
          var s = sd[i], u = uu[i], cov = Math.max(0, Math.min(1, (s / px + .7) / 1.4)), out = Math.max(0, -s), du = u - sw;
          var fr = Math.exp(-du * du / (wf * wf)) * act, tr = du < 0 ? Math.exp(du / tl) * act * .55 : 0; spec(u, tmp);
          var core = Math.max(0, Math.min(1, (s - 3) / 12)), r = (251 + (255 - 251) * core) * cov, g = (1 + 157 * core) * cov, b = (13 + 155 * core) * cov;   // red Σ, white-hot core
          var bl = Math.exp(-out / 6) * .5 * (1 - cov); r += 251 * bl; g += bl; b += 13 * bl;
          var em = (fr * 1.9 + tr * .85) * cov + (1 - cov) * Math.exp(-out / (k ? 11 : 7)) * (fr * 1.3 + tr * .4), gl = fr * Math.exp(-cl[i] * cl[i] / 90) * 1.3 * cov;
          r += (tmp[0] * em + 255 * gl) * boost; g += (tmp[1] * em + 247 * gl) * boost; b += (tmp[2] * em + 242 * gl) * boost;
          var j = idx[i]; d[j] = r; d[j + 1] = g; d[j + 2] = b; d[j + 3] = 255;
        }
        cx.putImageData(id, 0, 0);
        var op = ctx.globalCompositeOperation; ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = a; ctx.drawImage(cv, X - side / 2, Y - side / 2, side, side); ctx.globalCompositeOperation = op;
      }
    };
  }

  /* 40 TRANSFORMATION EFFECTS (20-Nov-2026, owner request): the Matrix rain stays exactly as it was; what the particles become after it is
   * drawn at random on every intro (never the same one twice in a row in this browser; ?fx=1..40 forces one). Effect 1 is the original
   * five-petal rose. Each effect = a shape the particles are drawn onto (pt: particle index n, angle th, jitter rr, time t -> unit coords,
   * radius ≈ 1), whether its outline is drawn as a guide line, the backdrop grid, the turn speed/direction and the swirl of the
   * convergence. Every effect still converges onto the same singularity, so the hand-over to the hero is unchanged. */
  var TAU = 6.283185307179586, NFX = 2800;
  function hsh(n) { var x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }
  function pol(r, a) { return [r * Math.cos(a), r * Math.sin(a)]; }
  function poly(k, th, skip) {   // regular polygon / star outline (skip 2 = pentagram-style star), parameter th
    skip = skip || 1; var u = th / TAU * k, i = Math.floor(u), f = u - i, a0 = i * skip / k * TAU - TAU / 4, a1 = (i + 1) * skip / k * TAU - TAU / 4;
    return [Math.cos(a0) + (Math.cos(a1) - Math.cos(a0)) * f, Math.sin(a0) + (Math.sin(a1) - Math.sin(a0)) * f];
  }
  function rot3(x, y, z, ax, ay) { var c = Math.cos(ax), s = Math.sin(ax), y2 = y * c - z * s, z2 = y * s + z * c; c = Math.cos(ay); s = Math.sin(ay); var x3 = x * c + z2 * s, z3 = -x * s + z2 * c, f = 3 / (3 + z3); return [x3 * f, y2 * f]; }
  var ATT = {};
  function attractor(kind) {   // precomputed once per load, only for the effect drawn
    if (ATT[kind]) return ATT[kind]; var a = [], i, x = .1, y = 0, z = 0, mx = 0;
    if (kind === 'lorenz') { for (i = 0; i < NFX + 400; i++) { for (var k = 0; k < 4; k++) { var dx = 10 * (y - x), dy = x * (28 - z) - y, dz = x * y - 8 / 3 * z; x += dx * .004; y += dy * .004; z += dz * .004; } if (i >= 400) a.push([x / 22, (z - 25) / 22]); } }
    else if (kind === 'clifford') { for (i = 0; i < NFX + 50; i++) { var nx = Math.sin(-1.4 * y) + Math.cos(1.6 * x), ny = Math.sin(1.7 * x) + .7 * Math.cos(-1.4 * y); x = nx; y = ny; if (i >= 50) a.push([x / 2.1, y / 1.8]); } }
    else if (kind === 'dejong') { for (i = 0; i < NFX + 50; i++) { var mx2 = Math.sin(1.641 * y) - Math.cos(1.902 * x), my2 = Math.sin(.316 * x) - Math.cos(1.525 * y); x = mx2; y = my2; if (i >= 50) a.push([x / 2, y / 2]); } }
    else if (kind === 'sierpinski') { var V = [[0, -1], [-.95, .75], [.95, .75]]; x = 0; y = 0; for (i = 0; i < NFX + 20; i++) { var v = V[Math.floor(hsh(i) * 3)]; x = (x + v[0]) / 2; y = (y + v[1]) / 2; if (i >= 20) a.push([x, y]); } }
    else if (kind === 'fern') { x = 0; y = 0; for (i = 0; i < NFX + 20; i++) { var r = hsh(i * 3.1), nx3, ny3; if (r < .01) { nx3 = 0; ny3 = .16 * y; } else if (r < .86) { nx3 = .85 * x + .04 * y; ny3 = -.04 * x + .85 * y + 1.6; } else if (r < .93) { nx3 = .2 * x - .26 * y; ny3 = .23 * x + .22 * y + 1.6; } else { nx3 = -.15 * x + .28 * y; ny3 = .26 * x + .24 * y + .44; } x = nx3; y = ny3; if (i >= 20) a.push([x / 5.2, 1 - y / 5]); } }
    return (ATT[kind] = a);
  }
  var SIG = [[.62, -.78], [-.62, -.78], [.12, 0], [-.62, .78], [.62, .78]], SIGL = [];
  (function () { var L = 0; for (var i = 0; i < 4; i++) { var d = Math.hypot(SIG[i + 1][0] - SIG[i][0], SIG[i + 1][1] - SIG[i][1]); SIGL.push(L); L += d; } SIGL.push(L); })();
  function sigma(th) { var u = th / TAU * SIGL[4], i = 0; while (i < 3 && u > SIGL[i + 1]) i++; var f = (u - SIGL[i]) / (SIGL[i + 1] - SIGL[i]); return [SIG[i][0] + (SIG[i + 1][0] - SIG[i][0]) * f, SIG[i][1] + (SIG[i + 1][1] - SIG[i][1]) * f]; }
  var CUBE = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]], CV = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]];
  // [name, pt(n, th, rr, t), guide line?, grid ('polar' | 'rings' | 'spokes' | 'none'), turn speed (rad/s, sign = direction), convergence swirl (rad, sign = direction), size (default 1)]
  var FXS = [
    ['Five-petal rose', function (n, th) { return pol(Math.cos(5 * th), th); }, 1, 'polar', .35, 2.4],
    ['Three-petal rose', function (n, th) { return pol(Math.cos(3 * th), th); }, 1, 'polar', -.4, -2.4],
    ['Eight-petal rose', function (n, th) { return pol(Math.cos(4 * th), th); }, 1, 'polar', .3, 2.8],
    ['Seven-half rose', function (n, th) { var a = th * 2; return pol(Math.cos(3.5 * a), a); }, 1, 'rings', -.3, 2.2],
    ['Cardioid', function (n, th) { var p = pol((1 + Math.cos(th)) * .55, th); return [p[0] - .3, p[1]]; }, 1, 'polar', .5, -2.6],
    ['Lemniscate', function (n, th) { var d = 1 + Math.sin(th) * Math.sin(th); return [Math.cos(th) / d, Math.sin(th) * Math.cos(th) / d]; }, 1, 'spokes', .45, 3],
    ['Lissajous 3:2', function (n, th) { return [Math.sin(3 * th + .5), Math.sin(2 * th)]; }, 1, 'none', .25, -2.4, 0.72],
    ['Lissajous 5:4', function (n, th) { return [Math.sin(5 * th + .3), Math.sin(4 * th)]; }, 1, 'none', -.25, 2.4, 0.72],
    ['Spirograph', function (n, th) { var a = th * 3; return [(2 * Math.cos(a) + 1.6 * Math.cos(2 * a / 3 * 5 / 2)) / 3.6, (2 * Math.sin(a) - 1.6 * Math.sin(2 * a / 3 * 5 / 2)) / 3.6]; }, 1, 'rings', .3, 2.6, 0.85],
    ['Epitrochoid', function (n, th) { var a = th; return [(Math.cos(a) * 1.5 - .7 * Math.cos(6 * a)) / 2.2, (Math.sin(a) * 1.5 - .7 * Math.sin(6 * a)) / 2.2]; }, 1, 'polar', -.35, -2.8],
    ['Astroid', function (n, th) { return [Math.pow(Math.cos(th), 3), Math.pow(Math.sin(th), 3)]; }, 1, 'spokes', .4, 2.4],
    ['Deltoid', function (n, th) { return [(2 * Math.cos(th) + Math.cos(2 * th)) / 3, (2 * Math.sin(th) - Math.sin(2 * th)) / 3]; }, 1, 'polar', -.5, -2.2],
    ['Heart', function (n, th) { return [Math.pow(Math.sin(th), 3), -(13 * Math.cos(th) - 5 * Math.cos(2 * th) - 2 * Math.cos(3 * th) - Math.cos(4 * th)) / 17]; }, 1, 'none', 0, 2.4, 0.85],
    ['Butterfly', function (n, th) { var a = th * 6, r = Math.exp(Math.sin(a)) - 2 * Math.cos(4 * a) + Math.pow(Math.sin((2 * a - Math.PI) / 24), 5); return [Math.sin(a) * r / 3.6, -Math.cos(a) * r / 3.6]; }, 1, 'none', 0, -2.6, 0.85],
    ['Sunflower', function (n) { return pol(Math.sqrt((n % NFX) / NFX), n * 2.399963); }, 0, 'rings', .3, 3, 0.72],
    ['Archimedean spiral', function (n, th) { var a = th * 3; return pol(a / (TAU * 3), a); }, 1, 'polar', .9, 3.2],
    ['Twin log spiral', function (n, th) { var a = th * 2, r = Math.exp(.18 * a) / Math.exp(.18 * TAU * 2); return pol(r, a + (n % 2) * Math.PI); }, 0, 'polar', -.8, -3.2],
    ['Four-arm galaxy', function (n, th, rr) { var r = Math.sqrt(hsh(n)), arm = n % 4; return pol(r * rr, arm / 4 * TAU + r * 4.2 + (hsh(n + 7) - .5) * .5 * (1 - r * .5)); }, 0, 'none', .6, 3, 0.85],
    ['Orbit rings', function (n, th) { return pol([.35, .58, .8, 1][n % 4], th); }, 0, 'rings', .5, -2.4],
    ['Hexagon', function (n, th) { return poly(6, th); }, 1, 'spokes', .35, 2.2, 0.85],
    ['Pentagram', function (n, th) { return poly(5, th * 2, 2); }, 1, 'polar', -.4, -2.6],
    ['Hexagram', function (n, th) { var p = poly(3, th); return n % 2 ? p : [p[0], -p[1]]; }, 0, 'polar', .3, 2.4],
    ['Squircle', function (n, th) { var c = Math.cos(th), s = Math.sin(th); return [Math.sign(c) * Math.pow(Math.abs(c), .4), Math.sign(s) * Math.pow(Math.abs(s), .4)]; }, 1, 'spokes', -.3, 2.6, 0.68],
    ['Trefoil knot', function (n, th) { return [(Math.sin(th) + 2 * Math.sin(2 * th)) / 3, (Math.cos(th) - 2 * Math.cos(2 * th)) / 3]; }, 1, 'none', .45, -2.8],
    ['Torus knot 2:5', function (n, th) { var a = th * 2, r = (2 + Math.cos(5 * a / 2)) / 3; return pol(r, a); }, 1, 'rings', -.4, 2.8],
    ['Gear', function (n, th) { return pol(.85 + .15 * Math.tanh(4 * Math.sin(12 * th)), th); }, 1, 'spokes', .6, 2.2],
    ['Double helix', function (n, th, rr, t) { var x = th / TAU * 2 - 1, ph = x * 9 + t * 2; return [x * 1.1, Math.sin(ph + (n % 2) * Math.PI) * .32]; }, 0, 'none', 0, -3, 0.8],
    ['Sigma', function (n, th) { return sigma(th); }, 1, 'none', 0, 2.4, 0.58],
    ['Square lattice', function (n) { var k = 22, i = n % (k * k); return [(i % k) / (k - 1) * 2 - 1, Math.floor(i / k) / (k - 1) * 2 - 1]; }, 0, 'none', .25, 3, 0.5],
    ['Hex lattice', function (n) { var k = 21, i = n % (k * k), r = Math.floor(i / k), c = i % k; return [((c + (r % 2) * .5) / (k - .5) * 2 - 1) * .95, (r / (k - 1) * 2 - 1) * .86]; }, 0, 'none', -.25, -3, 0.52],
    ['Starburst', function (n, th, rr) { var k = 16, a = (n % k) / k * TAU; return pol(hsh(n) * rr, a); }, 0, 'spokes', .5, 2.6],
    ['Maurer rose', function (n, th) { var q = Math.floor(th / TAU * 361), f = th / TAU * 361 - q, a0 = q * 71 * Math.PI / 180, a1 = (q + 1) * 71 * Math.PI / 180, p0 = pol(Math.sin(6 * a0), a0), p1 = pol(Math.sin(6 * a1), a1); return [p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f]; }, 1, 'none', .2, -2.4],
    ['Sierpinski', function (n) { return attractor('sierpinski')[n % NFX]; }, 0, 'none', 0, 2.8, 0.8],
    ['Lorenz', function (n) { return attractor('lorenz')[n % NFX]; }, 0, 'none', .2, -2.6, 0.85],
    ['Clifford', function (n) { return attractor('clifford')[n % NFX]; }, 0, 'rings', -.2, 2.6, 0.8],
    ['De Jong', function (n) { return attractor('dejong')[n % NFX]; }, 0, 'none', .25, -2.6, 0.8],
    ['Fern', function (n) { var p = attractor('fern')[n % NFX]; return [p[0] * 1.6, p[1] * 1.9 - .95]; }, 0, 'none', 0, 3, 0.7],
    ['Spinning cube', function (n, th, rr, t) { var e = CUBE[n % 12], u = hsh(n), a = CV[e[0]], b = CV[e[1]]; return rot3((a[0] + (b[0] - a[0]) * u) * .62, (a[1] + (b[1] - a[1]) * u) * .62, (a[2] + (b[2] - a[2]) * u) * .62, t * .9, t * 1.3); }, 0, 'none', 0, 2.4, 0.8],
    ['Fibonacci sphere', function (n, th, rr, t) { var i = n % NFX, y = 1 - 2 * (i + .5) / NFX, r = Math.sqrt(1 - y * y), a = i * 2.399963; return rot3(Math.cos(a) * r * .95, y * .95, Math.sin(a) * r * .95, .4, t * 1.1); }, 0, 'none', 0, -2.4, 0.68],
    ['Atom orbitals', function (n, th) { var k = n % 3, a = k / 3 * Math.PI, e = pol(1, th); e[1] *= .3; return [e[0] * Math.cos(a) - e[1] * Math.sin(a), e[0] * Math.sin(a) + e[1] * Math.cos(a)]; }, 0, 'polar', .5, 2.6]
  ];
  /* 40 CONVERGENCE ENDINGS (20-Nov-2026, owner request «el círculo rojo prevalece en todas»): what the particles converge onto and the
   * centre they light up are drawn at random too, independently of the transformation effect (?cv=1..40 forces one; never the same one
   * twice in a row). Ending 1 is the original tilted torus with the black heart and its scene-coloured rim (red in the vortex scene). */
  function tgtShape(kind, p, i, t, R) {   // -> [dx, dy, z] relative to the centre
    var a, r, q, k;
    switch (kind) {
      case 'ring': a = p.th + t * .6; return pol(R * (.92 + .16 * hsh(i)), a).concat(0);
      case 'disk': r = R * (.42 + .8 * hsh(i)); a = p.th + t * 1.2 * R / r; q = pol(r, a); return [q[0], q[1] * .34, Math.sin(a)];
      case 'shell': q = (function () { var y = 1 - 2 * ((i % 997) + .5) / 997, rr = Math.sqrt(1 - y * y), b = i * 2.399963; return rot3(Math.cos(b) * rr, y, Math.sin(b) * rr, .35, t * 1.1); })(); return [q[0] * R * .85, q[1] * R * .85, 0];
      case 'spiral2': r = (i % 500) / 500; a = (i % 2) * Math.PI + r * 5.5 - t * .9; return pol(R * (.12 + r), a).concat(0);
      case 'saturn': if (i % 5 < 2) { q = rot3(Math.cos(p.th) * Math.sin(i), Math.cos(i * 1.3), Math.sin(p.th) * Math.sin(i), .3, t * .8); return [q[0] * R * .42, q[1] * R * .42, 0]; }
        a = p.th + t * .7; q = pol(R * (.85 + .45 * hsh(i)), a); return [q[0], q[1] * .26, Math.sin(a)];
      case 'atom3': k = i % 3; a = p.th + t * (1.3 + k * .3); q = pol(R, a); q[1] *= .32; var b2 = k / 3 * Math.PI; return [q[0] * Math.cos(b2) - q[1] * Math.sin(b2), q[0] * Math.sin(b2) + q[1] * Math.cos(b2), 0];
      case 'gyro': k = i % 3; a = p.th + t * .9; var c3 = [Math.cos(a), Math.sin(a)], v = k === 0 ? [c3[0], c3[1], 0] : k === 1 ? [c3[0], 0, c3[1]] : [0, c3[0], c3[1]]; q = rot3(v[0], v[1], v[2], t * .7, t * 1.1); return [q[0] * R * .9, q[1] * R * .9, 0];
      case 'flower': a = p.th + t * .5; return pol(R * (.72 + .32 * Math.cos(6 * a - t)), a).concat(0);
      case 'nebula': r = R * Math.min(1.3, Math.sqrt(-2 * Math.log(1 - hsh(i) * .98)) * .42); a = p.th + t * (.9 - r / R * .4); return pol(r, a).concat(0);
      case 'pulsar': if (i % 10 < 3) { var s2 = i % 2 ? 1 : -1, d = .35 + 1.3 * ((hsh(i) + t * .35) % 1); return [(hsh(i + 3) - .5) * R * .12 * d, s2 * R * d, 0]; }
        a = p.th + t * 1.5; q = pol(R * (.5 + .5 * hsh(i)), a); return [q[0], q[1] * .22, 0];
      case 'tunnel': k = i % 6; a = p.th + t * (k % 2 ? .8 : -.8); q = pol(R * (.25 + .17 * k), a); return [q[0], q[1] * .62 + R * .05 * k, 0];
      case 'galaxy': r = Math.pow(hsh(i), .7); a = (i % 3) / 3 * TAU + r * 4.5 + t * .5 + (hsh(i + 5) - .5) * .45; q = pol(R * 1.15 * r, a); return [q[0], q[1] * .6, 0];
      case 'mandala': k = i % 5; a = p.th + t * (k % 2 ? .4 : -.4); return pol(R * (.3 + .18 * k) * (1 + .09 * Math.cos(8 * a)), a).concat(0);
      case 'sigma': q = sigma(p.th); return [q[0] * R * .85, q[1] * R * .85, 0];
      case 'hexring': q = poly(6, p.th); a = t * .4; return [(q[0] * Math.cos(a) - q[1] * Math.sin(a)) * R, (q[0] * Math.sin(a) + q[1] * Math.cos(a)) * R, 0];
      case 'star': q = poly(5, p.th * 2, 2); a = -t * .3; return [(q[0] * Math.cos(a) - q[1] * Math.sin(a)) * R * 1.05, (q[0] * Math.sin(a) + q[1] * Math.cos(a)) * R * 1.05, 0];
      case 'lemni': a = p.th + t * .8; var dd = 1 + Math.sin(a) * Math.sin(a); return [R * 1.25 * Math.cos(a) / dd, R * 1.25 * Math.sin(a) * Math.cos(a) / dd, 0];
      case 'cube': var e = CUBE[i % 12], u = hsh(i), A1 = CV[e[0]], B1 = CV[e[1]]; q = rot3(A1[0] + (B1[0] - A1[0]) * u, A1[1] + (B1[1] - A1[1]) * u, A1[2] + (B1[2] - A1[2]) * u, t * .8, t * 1.2); return [q[0] * R * .55, q[1] * R * .55, 0];
      case 'dnaring': a = p.th + t * .45; return pol(R * (1 + .2 * Math.sin(12 * a + t * 3 + (i % 2) * Math.PI)), a).concat(0);
      case 'heart': q = [Math.pow(Math.sin(p.th), 3), -(13 * Math.cos(p.th) - 5 * Math.cos(2 * p.th) - 2 * Math.cos(3 * p.th) - Math.cos(4 * p.th)) / 17]; return [q[0] * R, q[1] * R, 0];
      case 'double': k = i % 2; a = p.th + t * (k ? 1 : -1); return pol(R * (k ? .62 : 1.05), a).concat(0);
    }
    return null;
  }
  // [name, particle target, centre style, colour]
  var CVS = [
    ['Singularity (original)', 'torus', 'heart', ''], ['Spectral ring', 'ring', 'spectral', ''], ['Accretion eclipse', 'disk', 'eclipse', '#e2e8f0'],
    ['Plasma sphere', 'shell', 'orb', '#22d3ee'], ['Golden twin spiral', 'spiral2', 'ring', '#facc15'], ['Ringed planet', 'saturn', 'ring', '#facc15'],
    ['Atom', 'atom3', 'orb', '#ffffff'], ['Gyroscope', 'gyro', 'spectral', ''], ['Pulsing flower', 'flower', 'pulse', ''], ['Nebula star', 'nebula', 'star', '#ffffff'],
    ['Pulsar', 'pulsar', 'orb', '#22d3ee'], ['Tunnel', 'tunnel', 'none', ''], ['Golden galaxy', 'galaxy', 'orb', '#facc15'], ['Mandala', 'mandala', 'spectral', ''],
    ['Sigma constellation', 'sigma', 'star', '#facc15'], ['Hexagon gate', 'hexring', 'hex', ''], ['Golden pentagram', 'star', 'ring', '#facc15'],
    ['Infinity', 'lemni', 'orb', '#8b5cf6'], ['Tesseract', 'cube', 'none', ''], ['DNA halo', 'dnaring', 'ring', '#22d3ee'], ['Heart', 'heart', 'ring', '#e879f9'],
    ['Counter-rotation', 'double', 'eclipse', '#e2e8f0'], ['Spectral torus', 'torus', 'spectral', ''], ['Sigma ring', 'ring', 'sigma', '#facc15'],
    ['Disk flare', 'disk', 'star', '#fb923c'], ['Eclipsed sphere', 'shell', 'eclipse', '#e2e8f0'], ['Violet spiral', 'spiral2', 'ring', '#8b5cf6'],
    ['Spectral planet', 'saturn', 'spectral', ''], ['Sigma atom', 'atom3', 'sigma', '#facc15'], ['Glowing gyroscope', 'gyro', 'orb', '#a3e635'],
    ['Golden flower', 'flower', 'ring', '#facc15'], ['Nebula pulse', 'nebula', 'pulse', ''], ['Pulsar flare', 'pulsar', 'star', '#ffffff'],
    ['Spectral tunnel', 'tunnel', 'spectral', ''], ['Eclipsed galaxy', 'galaxy', 'eclipse', '#e2e8f0'], ['Hex mandala', 'mandala', 'hex', ''],
    ['Green hexagon', 'hexring', 'orb', '#a3e635'], ['Spectral DNA', 'dnaring', 'spectral', ''], ['Sigma orbits', 'double', 'sigma', '#facc15'], ['Pulsing cube', 'cube', 'pulse', '']
  ];
  function pickRnd(key, n, param) {
    var q = new URLSearchParams(location.search).get(param); if (q && +q >= 1 && +q <= n) return +q - 1;
    var last = -1, i; try { last = +(localStorage.getItem(key) || -1); } catch (e) {}
    function rnd() { if (root.crypto && crypto.getRandomValues) { var a = new Uint32Array(1); crypto.getRandomValues(a); return a[0] / 4294967296; } return Math.random(); }
    do { i = Math.floor(rnd() * n); } while (i === last && n > 1);
    try { localStorage.setItem(key, String(i)); } catch (e) {}
    return i;
  }
  function pickFx() { return pickRnd('sostu_splash_fx', FXS.length, 'fx'); }

  function play(o) {
    var ov = o.overlay, cv = o.canvas, RM = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var perf = { mode: RM ? 'reduced' : lightWanted() ? 'light' : 'full', frames: 0, longest: 0, startedAt: null, totalMs: null, skipped: false, firstFrameAt: null, plates: null };
    var done = false, raf = 0, t0 = 0, revealed = false, light = perf.mode === 'light', timers = [];
    var V = o.variant || 'a', B = o.base || '', K = V === 'a' ? 0 : 1;
    var FI = pickFx(), FX = FXS[FI], CI = pickRnd('sostu_splash_cv', CVS.length, 'cv'), CVE = CVS[CI]; perf.fx = { id: FI + 1, name: FX[0] }; perf.cv = { id: CI + 1, name: CVE[0] }; U.splash.perf = perf; mark();          // seen as soon as it starts: a reload mid-splash never replays it
    function finish() {
      if (done) return; done = true; if (raf) cancelAnimationFrame(raf); timers.forEach(clearTimeout); mark();
      perf.totalMs = Math.round(performance.now() - (perf.startedAt || performance.now()));
      if (!revealed) { revealed = true; if (o.onReveal) o.onReveal(); }
      ov.classList.add('gone'); setTimeout(function () { ov.remove(); }, 380);
      if (o.onDone) o.onDone(perf);
    }
    function skip() { if (done) return; perf.skipped = true; finish(); }
    if (RM) { ov.classList.add('still'); perf.startedAt = performance.now(); timers.push(setTimeout(finish, 1600)); return { skip: skip, perf: perf }; }
    var SCN = o.scene || 'vortex', RIM = SCN === 'horizon' ? null : SCN === 'spiral' ? '#ffc759' : '#fb010d';
    var ctx = null;   // created only after the first frame is on screen (measured: creating it during parse put the WSLg 2 s GPU start-up on the main thread)
    var W, H, dpr, COLW, cols, colSpd = [], colPh = [], P = [], NP, tgt, scan, glowW, glowS = [];
    function resize() {
      W = innerWidth; H = innerHeight; dpr = light ? 1 : Math.min(root.devicePixelRatio || 1, 1.5);
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      COLW = W < 600 ? 15 : light ? 22 : 18; cols = Math.ceil(W / COLW);
      for (var i = 0; i < cols; i++) { colSpd[i] = .32 + .5 * ((i * .6180339) % 1); colPh[i] = (i * .3819) % 1; }
      tgt = o.target();
      scan = document.createElement('canvas'); scan.width = 4; scan.height = 4; var sg = scan.getContext('2d'); sg.fillStyle = '#000'; sg.fillRect(0, 0, 4, 1); scan = ctx.createPattern(scan, 'repeat');
    }
    function setup() { ctx = cv.getContext('2d', { alpha: true, willReadFrequently: true }); resize();   // CPU-backed: no accelerated-canvas start-up
    glowW = sprite(32, '#ffffff'); SPEC.forEach(function (h) { glowS.push(sprite(16, h)); }); glowS.push(sprite(16, '#ff2d3b')); }
    NP = light ? 1700 : 2800;
    var boot = ['CONVERGENCEX // PROOF-OF-WORK CORE', 'NATIVE LAYER 1 · GENESIS 2026-03-15 18:00:00 UTC', 'cASERT · bitsQ Q16.16 · EQUALIZER E7–H35', null, 'CONVERGING ▌'];
    function tipLine() { var s = o.tip && o.tip(); return s && s.h ? 'SNAPSHOT · TIP #' + Number(s.h).toLocaleString('en-US') + ' · ' + String(s.status || '').toUpperCase() : 'SNAPSHOT · CONNECTING TO THE COLLECTOR'; }
    var RINGS = [{ tx: 1.22, ry: 0, sp: .55 }, { tx: 1.22, ry: 2.094, sp: -.42 }, { tx: 1.22, ry: 4.189, sp: .36 }];
    function cam(t) { return 1.14 - .14 * ease((t - 5.9) / 1.4); }           // camera: slightly close, pulls back into the hero
    function ringPt(k, th, t, R) {
      var r = RINGS[k], a = th + t * r.sp, x = Math.cos(a) * R, y = Math.sin(a) * R, z = 0;
      var cy = Math.cos(r.tx), sy = Math.sin(r.tx); var y2 = y * cy - z * sy, z2 = y * sy + z * cy;
      var ry = r.ry + t * .18, cr = Math.cos(ry), sr = Math.sin(ry); var x3 = x * cr + z2 * sr, z3 = -x * sr + z2 * cr;
      var f = 900 / (900 + z3); return { x: tgt.x + x3 * f, y: tgt.y + y2 * f * .92, z: z3, f: f };
    }
    function spawn(t) {
      var cells = [];
      for (var c = 0; c < cols; c++) {
        var fy = (colPh[c] + t * colSpd[c] * .55) % 1.25, y = fy * H, x = (c + .5) * COLW;
        for (var k = 0; k < 24; k++) { var yy = y - k * COLW; if (yy < -COLW) break; if (yy < H + COLW) cells.push([x, yy, colSpd[c], k]); }
      }
      var per = Math.max(1, Math.ceil(NP / Math.max(1, cells.length))), step = Math.max(1, cells.length * per / NP);
      for (var i = 0, n = 0; i < cells.length * per && n < NP; i += step, n++) {
        var ce = cells[Math.floor(i / per)], jx = ((n * .618) % 1 - .5) * COLW * .8, jy = ((n * .382) % 1 - .5) * COLW * .8;
        P.push({ x: ce[0] + COLW * .35 + jx, y: ce[1] + COLW * .5 + jy, vx: jx * .08, vy: ce[2] * H * .55 / 60, red: REDS[n % REDS.length], col: n % 6 === 5 ? REDS[n % REDS.length] : SPEC[n % 7], si: n % 7,
          ring: n % 5 === 4 ? -1 : n % 3, th: (n * 2.399963) % 6.2832, rr: .96 + .08 * Math.sin(n * 1.7), del: (n % 9) * .04, big: n % 23 === 0 });
      }
    }
    function frame(now) {
      raf = 0; if (done) return;
      if (!t0) { t0 = now; perf.startedAt = now; perf.firstFrameAt = Math.round(now); ov.classList.add('run'); }
      var dt = now - (frame.l || now); frame.l = now; perf.frames++; if (perf.frames > 3 && dt > perf.longest) perf.longest = dt;
      if (perf.frames === 30 && !light && (now - t0) / 30 > 40) { light = true; perf.mode = 'light(auto)'; NP = 1100; if (P.length > NP) P.length = NP; }
      var t = (now - t0) / 1000;
      if (t >= TOTAL) return finish();
      var bgA = t < 6.4 ? 1 : Math.max(0, 1 - (t - 6.4) / 1.0), F = W < 600 ? .8 : 1, CS = cam(t), R = tgt.r * CS, X = tgt.x, Y = tgt.y;
      ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1; ctx.clearRect(0, 0, W, H);
      if (bgA > 0) { ctx.globalAlpha = bgA; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H); }
      // ---------- MATRIX GENESIS (red dominant)
      var rainA = t < 2.4 ? Math.min(1, t / .15) : Math.max(0, 1 - (t - 2.4) / .9);
      if (rainA > 0) {
        ctx.font = '700 ' + COLW + 'px ui-monospace,monospace'; ctx.textBaseline = 'top';
        var fg = Math.floor(t * 16);
        for (var c = 0; c < cols; c++) {
          var fy = (colPh[c] + t * colSpd[c] * .55) % 1.25, y = fy * H, x = c * COLW + 2;
          for (var k = 0; k < 24; k++) {
            var yy = y - k * COLW; if (yy < -COLW) break; if (yy > H) continue;
            ctx.globalAlpha = rainA * Math.pow(1 - k / 24, .6);
            if (k === 0 && !light) { ctx.globalCompositeOperation = 'lighter'; ctx.drawImage(glowS[7], x - COLW * .4, yy - COLW * .45, COLW * 1.8, COLW * 1.8); ctx.globalCompositeOperation = 'source-over'; }
            ctx.fillStyle = k === 0 ? '#ffffff' : k < 4 ? '#ff5a63' : k < 10 ? '#ff2d3b' : k < 16 ? '#fb010d' : '#b3121c';
            ctx.fillText(GLY[(c * 7 + k * 13 + fg + (k === 0 ? c : 0)) % GLY.length], x, yy);
          }
        }
        var gs = Math.floor(t * 12);
        for (var g = 0; g < (light ? 3 : 7); g++) { var hs = Math.sin(gs * 12.9898 + g * 78.233) * 43758.5453; hs -= Math.floor(hs); ctx.globalAlpha = rainA * .2 * hs; ctx.fillStyle = g % 3 ? '#fb010d' : '#ffffff'; ctx.fillRect(0, hs * H, W, 1 + (g % 4) * 2); }
        ctx.globalAlpha = rainA * .3; ctx.fillStyle = scan; ctx.fillRect(0, 0, W, H);
        ctx.font = '600 ' + (W < 600 ? 10.5 : 12.5) + 'px ui-monospace,monospace'; ctx.textBaseline = 'alphabetic';
        var bx = W < 600 ? 16 : 40, by = H - (W < 600 ? 118 : 150);
        for (var b = 0; b < boot.length; b++) {
          var st = .15 + b * .34, txt = boot[b] || tipLine(), shown = Math.floor(Math.max(0, Math.min(1, (t - st) / .22)) * txt.length); if (!shown) continue;
          ctx.globalAlpha = rainA; ctx.fillStyle = '#000c'; ctx.fillRect(bx - 6, by + b * 19 - 13, ctx.measureText(txt.slice(0, shown)).width + 12, 18);
          ctx.fillStyle = b === 3 ? '#e2e8f0' : '#ff2d3b'; ctx.fillText(txt.slice(0, shown), bx, by + b * 19);
          if (b < boot.length - 1 && shown === txt.length) { ctx.fillStyle = '#a3e635'; ctx.fillText('OK', bx + ctx.measureText(txt).width + 10, by + b * 19); }
        }
      }
      // ---------- TRANSFORMATION: mathematical geometry (rose r = cos 5θ, polar grid) drawn in the official spectrum
      var geoA = ease((t - 2.4) / .5) * (1 - ease((t - 3.6) / .6));
      if (geoA > 0) {
        ctx.globalCompositeOperation = 'lighter'; var Rg = tgt.r * 2.3 * (1 - .25 * ease((t - 2.9) / 1.2)), rot = t * .35;
        rot = t * FX[4]; Rg *= FX[6] || 1; var GRID = FX[3];
        if (GRID === 'polar' || GRID === 'rings') for (var ring = 1; ring <= 4; ring++) { ctx.globalAlpha = geoA * .14; ctx.strokeStyle = SPEC[(ring * 2) % 7]; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(X, Y, Rg * ring / 4, 0, 7); ctx.stroke(); }
        if (GRID === 'polar' || GRID === 'spokes') { ctx.globalAlpha = geoA * .08; ctx.strokeStyle = '#e2e8f0'; ctx.beginPath(); for (var sp = 0; sp < 12; sp++) { var an = sp / 12 * 6.2832 + rot * .3; ctx.moveTo(X, Y); ctx.lineTo(X + Math.cos(an) * Rg, Y + Math.sin(an) * Rg); } ctx.stroke(); }
        if (FX[2]) {
          var gr = ctx.createLinearGradient(X - Rg, Y, X + Rg, Y); SPEC.forEach(function (h, j) { gr.addColorStop(j / 6, h); });
          ctx.globalAlpha = geoA * .55; ctx.strokeStyle = gr; ctx.lineWidth = 1.4; ctx.beginPath(); var cr0 = Math.cos(rot), sr0 = Math.sin(rot);
          for (var q = 0; q <= 720; q++) { var gp = FX[1](q, q / 720 * 6.2832, 1, t); ctx.lineTo(X + (gp[0] * cr0 - gp[1] * sr0) * Rg, Y + (gp[0] * sr0 + gp[1] * cr0) * Rg); } ctx.stroke();
        }
      }
      // ---------- particles: detach → spectrum → rose → orbital structure
      if (t >= 2.2 && !P.length) spawn(2.2);
      if (P.length) {
        ctx.globalCompositeOperation = 'lighter';
        var conv = (t - 3.4) / 1.9, shock = t > 2.3 && t < 2.75 ? (1 - (t - 2.3) / .45) : 0, pA = t < 2.5 ? (t - 2.2) / .3 : t > 6.5 ? Math.max(0, 1 - (t - 6.5) / 1.1) : 1;
        var cT = ease((t - 2.3) / .8), geoW = ease((t - 2.6) / .7) * (1 - ease((t - 3.5) / .5));
        var Rg2 = tgt.r * 2.3 * (FX[6] || 1) * (1 - .25 * ease((t - 2.9) / 1.2)), rot2 = t * FX[4], cr2 = Math.cos(rot2), sr2 = Math.sin(rot2);
        for (var i = 0; i < P.length; i++) {
          var p = P[i];
          var fx = Math.cos(p.y * .011 + t * 1.3) + .6 * Math.sin((p.x + p.y) * .007 - t), fyv = Math.sin(p.x * .009 - t * 1.1) - .5 * Math.cos((p.x - p.y) * .006 + t * .7);
          p.vx = p.vx * .94 + fx * .16; p.vy = p.vy * .94 + fyv * .16;
          if (shock) { var dx = p.x - X, dy = p.y - Y, dd = Math.sqrt(dx * dx + dy * dy) + 30; p.vx += dx / dd * shock * 1.0; p.vy += dy / dd * shock * 1.0; }
          p.x += p.vx; p.y += p.vy;
          if (geoW > 0) { var gq = FX[1](i, p.th, p.rr, t), gu = gq[0] * (FX[2] ? p.rr : 1), gv = gq[1] * (FX[2] ? p.rr : 1); var gx = X + (gu * cr2 - gv * sr2) * Rg2, gy = Y + (gu * sr2 + gv * cr2) * Rg2; p.x += (gx - p.x) * geoW * .12; p.y += (gy - p.y) * geoW * .12; }
          var kq = eo((conv - p.del) / .8), Xp = p.x, Yp = p.y, z = 0, f = 1;
          if (kq > 0) {
            var qq;
            // targets = the singularity: rim of the black heart (radius .40 R) and the tilted torus (radius R, vertical ratio sin .62)
            var a = p.th + t * (p.ring < 0 ? 1.1 : .35), ts = CVE[1] === 'torus' ? null : tgtShape(CVE[1], p, i, t, R);
            if (ts) qq = { x: X + ts[0], y: Y + ts[1], z: ts[2], f: 1 };
            else if (p.ring < 0) { var rr3 = R * .41 * p.rr; qq = { x: X + Math.cos(a) * rr3, y: Y + Math.sin(a) * rr3, z: 0, f: 1 }; }
            else { var tub = R * (.24 + .06 * p.ring) * Math.sin(p.th * 3 + p.ring), rr4 = R * p.rr + tub * Math.cos(p.th * 5); qq = { x: X + Math.cos(a) * rr4, y: Y + Math.sin(a) * rr4 * .58 + tub * .5 * Math.sin(p.th * 5), z: Math.sin(a), f: 1 }; }
            var swr = (1 - kq) * FX[5], ca = Math.cos(swr), sa = Math.sin(swr), ox = qq.x - X, oy = qq.y - Y;
            var qx = X + (ox * ca - oy * sa) * (1 + (1 - kq) * .6), qy = Y + (ox * sa + oy * ca) * (1 + (1 - kq) * .6);
            Xp = p.x + (qx - p.x) * kq; Yp = p.y + (qy - p.y) * kq; z = qq.z * kq; f = qq.f;
            if (kq > .995) { p.x = Xp; p.y = Yp; p.vx = p.vy = 0; }
          }
          var back = z > 0 ? .55 : 1, sz = (p.big ? 3.6 : 2.4) * F * (kq > 0 ? f : 1) * (light ? 1.25 : 1);
          ctx.globalAlpha = Math.max(0, Math.min(1, pA)) * back * .85;
          if (p.big && !light) ctx.drawImage(glowS[p.si], Xp - 8, Yp - 8, 16, 16);
          ctx.fillStyle = cT < 1 && (i % 10) / 10 > cT ? p.red : p.col; ctx.fillRect(Xp - sz / 2, Yp - sz / 2, sz, sz);
        }
      }
      // ---------- the black heart of the singularity and its rim (scene colour: red / spectral photon ring / gold) — the centre stays free
      var coreA = ease((t - 4.0) / 1.0) * (t < 7.0 ? 1 : Math.max(0, 1 - (t - 7.0) / .7)), CS2 = CVE[2], CC = CVE[3];
      if (coreA > 0 && CS2 === 'heart') {
        var rc = R * .40;
        ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = coreA * bgA; ctx.fillStyle = '#000'; ctx.beginPath(); ctx.arc(X, Y, rc * .97, 0, 7); ctx.fill();
        ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = coreA; ctx.lineWidth = 3 * F;
        if (RIM) ctx.strokeStyle = RIM; else { var cg = ctx.createConicGradient ? ctx.createConicGradient(t * .3, X, Y) : null; if (cg) { SPEC.concat(SPEC[0]).forEach(function (h, j) { cg.addColorStop(j / 7, h); }); ctx.strokeStyle = cg; } else ctx.strokeStyle = '#22d3ee'; }
        ctx.beginPath(); ctx.arc(X, Y, rc, 0, 7); ctx.stroke(); ctx.globalAlpha = coreA * .5; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(X, Y, rc * 1.07, 0, 7); ctx.stroke();
        ctx.globalAlpha = coreA * .55; ctx.drawImage(RIM === '#fb010d' ? glowS[7] : glowS[RIM ? 5 : 3], X - rc * 1.9, Y - rc * 1.9, rc * 3.8, rc * 3.8);
      }
      if (coreA > 0 && CS2 !== 'heart' && CS2 !== 'none') {
        var rc2 = R * .40, cgS = null; ctx.globalCompositeOperation = 'lighter';
        if (ctx.createConicGradient) { cgS = ctx.createConicGradient(t * .5, X, Y); SPEC.concat(SPEC[0]).forEach(function (h, j) { cgS.addColorStop(j / 7, h); }); }
        var STK = CC || cgS || '#22d3ee';
        if (CS2 === 'eclipse') {   // black disc with a silver corona
          ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = coreA * bgA; ctx.fillStyle = '#000'; ctx.beginPath(); ctx.arc(X, Y, rc2 * .97, 0, 7); ctx.fill();
          ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = coreA * .9; ctx.drawImage(glowW, X - rc2 * 1.6, Y - rc2 * 1.6, rc2 * 3.2, rc2 * 3.2);
          ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = coreA * bgA; ctx.fillStyle = '#000'; ctx.beginPath(); ctx.arc(X, Y, rc2 * .95, 0, 7); ctx.fill();
          ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = coreA * .8; ctx.strokeStyle = CC; ctx.lineWidth = 1.6 * F; ctx.beginPath(); ctx.arc(X, Y, rc2, 0, 7); ctx.stroke();
        } else if (CS2 === 'orb') {   // bright glowing core
          var og = ctx.createRadialGradient(X, Y, 0, X, Y, rc2 * 1.5); og.addColorStop(0, '#ffffff'); og.addColorStop(.25, CC); og.addColorStop(1, CC + '00');
          ctx.globalAlpha = coreA * (.75 + .25 * Math.sin(t * 6)); ctx.fillStyle = og; ctx.beginPath(); ctx.arc(X, Y, rc2 * 1.5, 0, 7); ctx.fill();
        } else if (CS2 === 'star') {   // lens-flare star
          ctx.globalAlpha = coreA; ctx.drawImage(glowW, X - rc2, Y - rc2, rc2 * 2, rc2 * 2); ctx.strokeStyle = CC; ctx.lineWidth = 1.4 * F;
          for (var sk = 0; sk < 4; sk++) { var sa2 = sk / 4 * Math.PI + t * .4, ln = rc2 * (sk % 2 ? 1.6 : 2.6) * (.9 + .1 * Math.sin(t * 5)); ctx.globalAlpha = coreA * .7; ctx.beginPath(); ctx.moveTo(X - Math.cos(sa2) * ln, Y - Math.sin(sa2) * ln); ctx.lineTo(X + Math.cos(sa2) * ln, Y + Math.sin(sa2) * ln); ctx.stroke(); }
        } else if (CS2 === 'pulse') {   // rings pulsing outwards in the spectrum
          ctx.lineWidth = 2 * F; for (var pk = 0; pk < 4; pk++) { var ph = (t * .7 + pk / 4) % 1; ctx.globalAlpha = coreA * (1 - ph) * .8; ctx.strokeStyle = SPEC[(pk * 2) % 7]; ctx.beginPath(); ctx.arc(X, Y, rc2 * (.3 + ph * 1.6), 0, 7); ctx.stroke(); }
        } else if (CS2 === 'hex') {
          ctx.globalAlpha = coreA; ctx.strokeStyle = STK; ctx.lineWidth = 2.6 * F; ctx.beginPath();
          for (var hk = 0; hk <= 6; hk++) { var ha = hk / 6 * TAU + t * .3; ctx.lineTo(X + Math.cos(ha) * rc2, Y + Math.sin(ha) * rc2); } ctx.stroke();
        } else if (CS2 === 'sigma') {   // the gold Σ in the centre
          ctx.globalAlpha = coreA * .6; ctx.drawImage(glowS[5], X - rc2 * 1.6, Y - rc2 * 1.6, rc2 * 3.2, rc2 * 3.2);
          ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = coreA; ctx.fillStyle = CC; ctx.font = '700 ' + Math.round(rc2 * 1.5) + 'px Georgia,serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('Σ', X, Y + rc2 * .05); ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';
        } else {   // 'ring' and 'spectral': a coloured ring, no black disc
          ctx.globalAlpha = coreA; ctx.strokeStyle = STK; ctx.lineWidth = 3 * F; ctx.beginPath(); ctx.arc(X, Y, rc2, 0, 7); ctx.stroke();
          ctx.globalAlpha = coreA * .5; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(X, Y, rc2 * 1.07, 0, 7); ctx.stroke();
          ctx.globalAlpha = coreA * .45; ctx.drawImage(CC === '#facc15' ? glowS[5] : CC === '#8b5cf6' ? glowS[0] : CC === '#e879f9' ? glowS[1] : glowS[3], X - rc2 * 1.9, Y - rc2 * 1.9, rc2 * 3.8, rc2 * 3.8);
        }
      }
      // ---------- UNIVERSE REVEAL: multicolour energy wave, camera pull-back (cam()), the backdrop dissolves into the home
      if (t > 5.9) {
        var w = (t - 5.9) / 1.3;
        if (w < 1) {
          ctx.globalCompositeOperation = 'lighter'; ctx.lineWidth = 2.6 * (1 - w) + .6;
          var gg = ctx.createLinearGradient(X - R * 5, Y, X + R * 5, Y); SPEC.forEach(function (h, j) { gg.addColorStop(j / 6, h); }); ctx.strokeStyle = gg;
          ctx.globalAlpha = (1 - w) * .85; ctx.beginPath(); ctx.arc(X, Y, R * (1.05 + w * 4.6), 0, 7); ctx.stroke();
          ctx.globalAlpha = (1 - w) * .45; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(X, Y, R * (1.0 + w * 3.4), 0, 7); ctx.stroke();
        }
        if (!revealed && t > 6.5) { revealed = true; ov.classList.add('reveal'); if (o.onReveal) o.onReveal(); }
      }
      raf = requestAnimationFrame(frame);
    }
    var rz = 0; addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { if (!done && ctx) resize(); }, 100); });
    requestAnimationFrame(function () { requestAnimationFrame(function () { if (done) return; setup(); raf = requestAnimationFrame(function (n) { frame(n); var pr = o.overlay && o.overlay.querySelector('.sp-rain'); if (pr) { setTimeout(function () { pr.classList.add('off'); }, 1100); setTimeout(function () { pr.remove(); }, 2000); /* overlap while the canvas rain fills the screen */ } }); }); });
    timers.push(setTimeout(function () { if (!done && !t0) finish(); }, 4000));   // a page that cannot animate at all never stays black
    return { skip: skip, perf: perf };
  }
  U.splash = { play: play, seen: seen, TOTAL: TOTAL, KEY: KEY, lightWanted: lightWanted, SigmaCPU: SigmaCPU };
})(window);

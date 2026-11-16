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

  function play(o) {
    var ov = o.overlay, cv = o.canvas, RM = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var perf = { mode: RM ? 'reduced' : lightWanted() ? 'light' : 'full', frames: 0, longest: 0, startedAt: null, totalMs: null, skipped: false, firstFrameAt: null, plates: null };
    var done = false, raf = 0, t0 = 0, revealed = false, light = perf.mode === 'light', timers = [];
    var V = o.variant || 'a', B = o.base || '', K = V === 'a' ? 0 : 1;
    U.splash.perf = perf; mark();          // seen as soon as it starts: a reload mid-splash never replays it
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
        for (var ring = 1; ring <= 4; ring++) { ctx.globalAlpha = geoA * .14; ctx.strokeStyle = SPEC[(ring * 2) % 7]; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(X, Y, Rg * ring / 4, 0, 7); ctx.stroke(); }
        ctx.globalAlpha = geoA * .08; ctx.strokeStyle = '#e2e8f0'; ctx.beginPath(); for (var sp = 0; sp < 12; sp++) { var an = sp / 12 * 6.2832 + rot * .3; ctx.moveTo(X, Y); ctx.lineTo(X + Math.cos(an) * Rg, Y + Math.sin(an) * Rg); } ctx.stroke();
        var gr = ctx.createLinearGradient(X - Rg, Y, X + Rg, Y); SPEC.forEach(function (h, j) { gr.addColorStop(j / 6, h); });
        ctx.globalAlpha = geoA * .55; ctx.strokeStyle = gr; ctx.lineWidth = 1.4; ctx.beginPath();
        for (var q = 0; q <= 360; q++) { var th = q / 360 * 6.2832, rr = Rg * Math.cos(5 * th); ctx.lineTo(X + Math.cos(th + rot) * rr, Y + Math.sin(th + rot) * rr); } ctx.stroke();
      }
      // ---------- particles: detach → spectrum → rose → orbital structure
      if (t >= 2.2 && !P.length) spawn(2.2);
      if (P.length) {
        ctx.globalCompositeOperation = 'lighter';
        var conv = (t - 3.4) / 1.9, shock = t > 2.3 && t < 2.75 ? (1 - (t - 2.3) / .45) : 0, pA = t < 2.5 ? (t - 2.2) / .3 : t > 6.5 ? Math.max(0, 1 - (t - 6.5) / 1.1) : 1;
        var cT = ease((t - 2.3) / .8), geoW = ease((t - 2.6) / .7) * (1 - ease((t - 3.5) / .5));
        var Rg2 = tgt.r * 2.3 * (1 - .25 * ease((t - 2.9) / 1.2)), rot2 = t * .35;
        for (var i = 0; i < P.length; i++) {
          var p = P[i];
          var fx = Math.cos(p.y * .011 + t * 1.3) + .6 * Math.sin((p.x + p.y) * .007 - t), fyv = Math.sin(p.x * .009 - t * 1.1) - .5 * Math.cos((p.x - p.y) * .006 + t * .7);
          p.vx = p.vx * .94 + fx * .16; p.vy = p.vy * .94 + fyv * .16;
          if (shock) { var dx = p.x - X, dy = p.y - Y, dd = Math.sqrt(dx * dx + dy * dy) + 30; p.vx += dx / dd * shock * 1.0; p.vy += dy / dd * shock * 1.0; }
          p.x += p.vx; p.y += p.vy;
          if (geoW > 0) { var th2 = p.th, rr2 = Rg2 * Math.cos(5 * th2) * p.rr; var gx = X + Math.cos(th2 + rot2) * rr2, gy = Y + Math.sin(th2 + rot2) * rr2; p.x += (gx - p.x) * geoW * .12; p.y += (gy - p.y) * geoW * .12; }
          var kq = eo((conv - p.del) / .8), Xp = p.x, Yp = p.y, z = 0, f = 1;
          if (kq > 0) {
            var qq;
            // targets = the singularity: rim of the black heart (radius .40 R) and the tilted torus (radius R, vertical ratio sin .62)
            var a = p.th + t * (p.ring < 0 ? 1.1 : .35); if (p.ring < 0) { var rr3 = R * .41 * p.rr; qq = { x: X + Math.cos(a) * rr3, y: Y + Math.sin(a) * rr3, z: 0, f: 1 }; }
            else { var tub = R * (.24 + .06 * p.ring) * Math.sin(p.th * 3 + p.ring), rr4 = R * p.rr + tub * Math.cos(p.th * 5); qq = { x: X + Math.cos(a) * rr4, y: Y + Math.sin(a) * rr4 * .58 + tub * .5 * Math.sin(p.th * 5), z: Math.sin(a), f: 1 }; }
            var swr = (1 - kq) * 2.4, ca = Math.cos(swr), sa = Math.sin(swr), ox = qq.x - X, oy = qq.y - Y;
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
      var coreA = ease((t - 4.0) / 1.0) * (t < 7.0 ? 1 : Math.max(0, 1 - (t - 7.0) / .7));
      if (coreA > 0) {
        var rc = R * .40;
        ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = coreA * bgA; ctx.fillStyle = '#000'; ctx.beginPath(); ctx.arc(X, Y, rc * .97, 0, 7); ctx.fill();
        ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = coreA; ctx.lineWidth = 3 * F;
        if (RIM) ctx.strokeStyle = RIM; else { var cg = ctx.createConicGradient ? ctx.createConicGradient(t * .3, X, Y) : null; if (cg) { SPEC.concat(SPEC[0]).forEach(function (h, j) { cg.addColorStop(j / 7, h); }); ctx.strokeStyle = cg; } else ctx.strokeStyle = '#22d3ee'; }
        ctx.beginPath(); ctx.arc(X, Y, rc, 0, 7); ctx.stroke(); ctx.globalAlpha = coreA * .5; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(X, Y, rc * 1.07, 0, 7); ctx.stroke();
        ctx.globalAlpha = coreA * .55; ctx.drawImage(RIM === '#fb010d' ? glowS[7] : glowS[RIM ? 5 : 3], X - rc * 1.9, Y - rc * 1.9, rc * 3.8, rc * 3.8);
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

/* SOST Universe — P3 interactive cubes (owner order 4 Nov 2026, «P3 — CUBOS DINÁMICOS E INTERACTIVOS EN HOME»).
 * The glass-block chain that leaves the singularity (#chainCv, drawn statically by u-home-art.js) becomes a set of 3D cubes the
 * visitor can select, drag, rotate, flip, separate, reorder and join magnetically into chains. It is a visual metaphor of linked
 * blocks: nothing here reads or changes the real blockchain.
 *
 *  - one canvas (#chainCv, pointer-events:none): the page below keeps every click. A press is taken only when it lands on a cube
 *    and NOT on text, a link, a button, a form field, the nav, the cards, the step labels or the music player;
 *  - modes (toolbar .cubeBar): AUTO (autonomous float + flip ripple, default), CHAIN (assembled at the original slots; drop a
 *    dragged cube on another slot to reorder), FREE (free manipulation; cubes that come close show a link signal and join),
 *    SCATTER (break every link, spread them), RESET (original order, position and orientation);
 *  - gestures: drag = move (a linked chain follows), double-click / double-tap = flip, wheel while dragging or Shift+drag or a
 *    second finger twist = rotate, long press = detach from its chain, a fast yank also breaks a link;
 *  - keyboard: the CUBE controller in the toolbar (Tab): [ ] select, arrows move, R rotate, F flip, D detach;
 *  - effects follow the site quality control (AUTO/HIGH/BAL/LITE/OFF in the bottom bar): flash, edge lighting, particles, trail,
 *    proximity glow; AUTO measures frame time and steps down;
 *  - prefers-reduced-motion: no autonomous motion, no particles, trails or flashes, no inertia; cubes stay fully usable;
 *  - Immersive Mode: the toolbar hides and the cubes return to the original chain with interaction paused; leaving Immersive
 *    brings back their previous arrangement. CUBES OFF (remembered) restores the static chain;
 *  - the loop runs only while something moves (or AUTO), and pauses when the tab is hidden or the hero is off screen;
 *  - integration with the 100 scenes: anchored to the shared singularity geometry (#coreAnchor), re-anchored and rippled on
 *    every scene change, rippled by a click on the scene, glowing subtly with the soundtrack energy;
 *  - events for other layers (gravitational cursor): window 'sost:cubes' {type: grab|drop|snap|break|flip, x, y} in client px.
 * No data, no network. */
(function (root) {
  'use strict';
  var doc = root.document, H = doc.documentElement;
  var Q = new URLSearchParams(root.location.search);
  var KEY = 'sostu_cubes_v1';
  function lsGet() { try { return JSON.parse(root.localStorage.getItem(KEY) || '{}') || {}; } catch (e) { return {}; } }
  function lsSet(o) { try { root.localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} }
  var pref = lsGet(); if (Q.get('cubes') === '0') pref.on = false; if (Q.get('cubes') === '1') pref.on = true;
  var RM = root.matchMedia ? root.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };

  // ---- colour helpers (same official spectrum as the static chain) ----
  function hex(h) { h = h.replace('#', ''); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]; }
  function mix(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
  function ramp(pal, t) { t = Math.max(0, Math.min(1, t)) * (pal.length - 1); var i = Math.min(pal.length - 2, Math.floor(t)); return mix(pal[i], pal[i + 1], t - i); }
  function rgba(c, a) { return 'rgba(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ',' + Math.max(0, Math.min(1, a)).toFixed(3) + ')'; }
  var CHAIN = ['#fb923c', '#facc15', '#fb010d', '#e879f9', '#a3e635', '#22d3ee', '#3b82f6', '#8b5cf6', '#e879f9', '#22d3ee'].map(hex);
  var WHITE = [255, 255, 255];

  // ---- quality tiers ----
  var TIERS = {
    high: { dpr: 2, glow: 2, parts: 220, trail: 8, fps: 60 },
    balanced: { dpr: 1.5, glow: 1, parts: 90, trail: 4, fps: 60 },
    lite: { dpr: 1, glow: 0, parts: 0, trail: 0, fps: 30 },
    off: { dpr: 1, glow: 0, parts: 0, trail: 0, fps: 30 }
  };
  var tierReq = 'auto', tier = 'high', autoNote = '';

  var cv, g, W = 0, Hh = 0, dpr = 1, anchor = null;
  var cubes = [], slots = [], links = [], parts = [], waves = [];
  var mode = 'auto', on = pref.on !== false, imm = false, saved = null;
  var running = false, lastT = 0, visible = true, inView = true, raf = 0;
  var grab = null, hoverC = null, ptr = { x: -1e4, y: -1e4, in: false }, pointers = {}, twist = null;
  var slowW = 0, fastW = 0, tierTop = 'high', kbSel = 0, kbFocus = false, tAuto = 0, nextRipple = 4, ftimes = [], energy = 0;
  var bar = null, live = null, perf = { n: 0, sum: 0, max: 0, frames: 0 };

  // ---- geometry: the original chain slots (identical to u-home-art.js drawChain) ----
  function computeSlots() {
    var cs = anchor ? root.getComputedStyle(anchor) : null;
    var ex = (cs && parseFloat(cs.getPropertyValue('--ex'))) || W * .66, ey = (cs && parseFloat(cs.getPropertyValue('--ey'))) || Hh * .5;
    var R = ((cs && parseFloat(cs.getPropertyValue('--ed'))) || 480) / 2;
    var pts = [], x = ex + R * .5, sz = R * .27, y0 = ey;
    while (x < W - 4 && pts.length < 40) {
      var s = sz; if (x + s * 1.34 > W - 4) { s = (W - 4 - x) / 1.34; if (s < 10) break; }
      pts.push({ x: x + s * .5 + s * .17, y: y0 - s * .5 + s * .5 - s * .11, s: s }); x += s * 1.34 + s * .22; sz *= .9; y0 -= s * .09;
    }
    pts.forEach(function (p, i) { p.t = pts.length > 1 ? i / (pts.length - 1) : 0; p.a = .55 + .45 * Math.sin(Math.PI * Math.min(1, p.t * 1.4 + .1)); });
    return pts;
  }
  function fit() {
    var r = cv.getBoundingClientRect(), T = TIERS[tier] || TIERS.high;
    dpr = Math.min(T.dpr, root.devicePixelRatio || 1); W = r.width; Hh = r.height;
    var w = Math.max(1, Math.round(W * dpr)), h = Math.max(1, Math.round(Hh * dpr));
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    g = cv.getContext('2d');
  }
  function build(keep) {
    fit(); measureZones(); var old = cubes; slots = computeSlots();
    if (keep && old.length === slots.length) { old.forEach(function (c) { var sl = slots[c.slot]; c.s = sl.s; c.col = ramp(CHAIN, sl.t); c.base = sl.a; clampPos(c); }); return; }
    cubes = slots.map(function (sl, i) {
      return { i: i, slot: i, home: i, x: sl.x, y: sl.y, vx: 0, vy: 0, s: sl.s, col: ramp(CHAIN, sl.t), base: sl.a,
        yaw: 0, pitch: 0, roll: 0, wy: 0, wp: 0, wr: 0, ty: 0, tp: 0, tr: 0, flash: 0, glow: 0, sig: 0, trail: [], tap: 0, links: [] };
    });
    links = []; if (mode === 'chain' || mode === 'auto') chainLinks();
  }
  function chainLinks() { links = []; cubes.forEach(function (c) { c.links = []; });
    var ord = cubes.slice().sort(function (a, b) { return a.slot - b.slot; });
    for (var k = 1; k < ord.length; k++) addLink(ord[k - 1], ord[k], true); }
  function restLen(a, b) { return (a.s + b.s) * .5 * 1.56; }
  function addLink(a, b, quiet) { if (linked(a, b)) return; var L = { a: a, b: b, L: restLen(a, b), born: quiet ? 1 : 0 }; links.push(L); a.links.push(L); b.links.push(L); return L; }
  function linked(a, b) { return a.links.some(function (L) { return L.a === b || L.b === b; }); }
  function dropLink(L) { links = links.filter(function (x) { return x !== L; }); L.a.links = L.a.links.filter(function (x) { return x !== L; }); L.b.links = L.b.links.filter(function (x) { return x !== L; }); }
  // separate a cube from its chain: it may not re-join for 1.6 s, and it is pushed a little away from its former neighbours
  function detach(c) {
    var nb = c.links.map(function (L) { return L.a === c ? L.b : L.a; }); c.links.slice().forEach(dropLink); c.noJoin = tAuto + 1.6;
    nb.forEach(function (o) { o.noJoin = tAuto + 1.6; var dx = c.x - o.x, dy = c.y - o.y, d = Math.sqrt(dx * dx + dy * dy) || 1; if (RM.matches) { c.x += dx / d * c.s * .6; c.y += dy / d * c.s * .6; clampPos(c); } else { c.vx += dx / d * 260; c.vy += dy / d * 260; o.vx -= dx / d * 120; o.vy -= dy / d * 120; } });
  }
  function group(c) { var seen = [c], q = [c]; while (q.length) { var x = q.pop(); x.links.forEach(function (L) { var o = L.a === x ? L.b : L.a; if (seen.indexOf(o) < 0) { seen.push(o); q.push(o); } }); } return seen; }
  // reading zones (owner order: the cubes may use the visual area but never prevent reading or navigation): the headline, lede,
  // buttons and latest blocks, the step labels and the cards. A cube left there drifts out; a held cube may pass over them.
  var KEEP = '.hcopy .eyebrow,.hcopy h1,.hcopy .lede,.hcopy .ctas,.hcopy .latest,#hstepsW,.hcards,#nav,.cubeBar,.ua,.u-bar', zones = [];
  function measureZones() {
    zones = []; if (!cv) return; var o = cv.getBoundingClientRect();
    doc.querySelectorAll(KEEP).forEach(function (e) { var r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return; zones.push({ l: r.left - o.left - 10, t: r.top - o.top - 10, r: r.right - o.left + 10, b: r.bottom - o.top + 10 }); });
  }
  function keepOut(c, dt) {
    var h = c.s * .62;
    zones.forEach(function (z) {
      if (c.x + h < z.l || c.x - h > z.r || c.y + h < z.t || c.y - h > z.b) return;
      var dl = c.x + h - z.l, dr = z.r - (c.x - h), du = c.y + h - z.t, dd = z.b - (c.y - h), m = Math.min(dl, dr, du, dd), f = 2600 * dt;
      if (m === dl) c.vx -= f; else if (m === dr) c.vx += f; else if (m === du) c.vy -= f; else c.vy += f;
      if (RM.matches) { if (m === dl) c.x -= dl; else if (m === dr) c.x += dr; else if (m === du) c.y -= du; else c.y += dd; }
    });
  }
  function clampPos(c) { var m = c.s * .62; c.x = Math.max(m, Math.min(W - m, c.x)); c.y = Math.max(m + 8, Math.min(Hh - m, c.y)); }

  // ---- 3D cube: 8 vertices, rotation, light perspective ----
  var V = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]];
  var FACES = [[0, 1, 2, 3, 0, 0, -1, 'f'], [5, 4, 7, 6, 0, 0, 1, 'k'], [4, 0, 3, 7, -1, 0, 0, 'l'], [1, 5, 6, 2, 1, 0, 0, 'r'], [4, 5, 1, 0, 0, -1, 0, 't'], [3, 2, 6, 7, 0, 1, 0, 'b']];
  var BY = -.36, BP = -.30;  // base view: slightly from the left and above, like the static chain (front, top and right faces)
  function rot(p, c) {
    var y = c.yaw + BY, x = c.pitch + BP, z = c.roll;
    var X = p[0], Y = p[1], Z = p[2], cy = Math.cos(y), sy = Math.sin(y), cx = Math.cos(x), sx = Math.sin(x), cz = Math.cos(z), sz = Math.sin(z);
    var x1 = X * cy + Z * sy, z1 = -X * sy + Z * cy;              // yaw
    var y2 = Y * cx - z1 * sx, z2 = Y * sx + z1 * cx;             // pitch
    var x3 = x1 * cz - y2 * sz, y3 = x1 * sz + y2 * cz;           // roll
    return [x3, y3, z2];
  }
  function project(c, sc) {
    var h = c.s * .5 * (sc || 1), P = [], f = 6;
    for (var k = 0; k < 8; k++) { var r = rot(V[k], c), w = f / (f + r[2] * .5); P.push([c.x + r[0] * h * w, c.y + r[1] * h * w, r[2]]); }
    return P;
  }
  function poly(P, idx) { g.beginPath(); g.moveTo(P[idx[0]][0], P[idx[0]][1]); for (var k = 1; k < 4; k++) g.lineTo(P[idx[k]][0], P[idx[k]][1]); g.closePath(); }
  function drawCube(c, alpha, ghost) {
    var T = TIERS[tier] || TIERS.high, P = project(c, 1 + c.flash * .06), col = c.col, a = alpha;
    var vis = [];
    FACES.forEach(function (F) { var n = rot([F[4], F[5], F[6]], c); if (n[2] < 0.02) vis.push({ F: F, n: n }); });
    vis.forEach(function (o) {
      var lit = Math.max(0, -o.n[1] * .55 - o.n[0] * .25 - o.n[2] * .5);  // light from the top-left, towards the viewer
      var P0 = P[o.F[0]], P2 = P[o.F[2]], gr = g.createLinearGradient(P0[0], P0[1], P2[0], P2[1]);
      gr.addColorStop(0, rgba(col, (.16 + .2 * lit) * a)); gr.addColorStop(1, rgba(col, (.05 + .06 * lit) * a));
      poly(P, o.F); g.fillStyle = gr; g.fill();
    });
    if (ghost) return;
    var edge = Math.min(1, .55 + c.glow * .45 + c.flash * .6 + c.sig * .3 + energy * .25);
    g.lineJoin = 'round';
    // edge light without shadowBlur (a GPU blur per stroke halved the frame rate of the scene on integrated GPUs): layered strokes,
    // wide and faint first, additive, then the crisp edge
    var boost = 1 + c.flash * .8 + c.glow * .5, passes = T.glow === 2 ? [[9, .07], [4.5, .16], [2.2, .34]] : T.glow === 1 ? [[5, .12], [2.4, .3]] : [];
    if (passes.length) { g.globalCompositeOperation = 'lighter'; passes.forEach(function (L) { g.strokeStyle = rgba(col, L[1] * a * boost); g.lineWidth = L[0] * (1 + c.flash * .4); vis.forEach(function (o) { poly(P, o.F); g.stroke(); }); }); g.globalCompositeOperation = 'source-over'; }
    g.strokeStyle = rgba(mix(col, WHITE, .45 + c.flash * .4), a * edge); g.lineWidth = 1.2 + c.glow * .5 + c.flash;
    vis.forEach(function (o) { poly(P, o.F); g.stroke(); });
    var r = c.s * .7, gl = g.createRadialGradient(c.x, c.y, 0, c.x, c.y, r * (1 + c.flash * .8));
    gl.addColorStop(0, rgba(mix(col, WHITE, .5), (.3 + c.glow * .2 + c.flash * .5) * a)); gl.addColorStop(1, rgba(col, 0));
    g.fillStyle = gl; g.fillRect(c.x - r * 1.8, c.y - r * 1.8, r * 3.6, r * 3.6);
  }

  // ---- effects ----
  function burst(x, y, col, n, sp) { var T = TIERS[tier]; if (!T.parts || RM.matches) return; n = Math.min(n, T.parts - parts.length); for (var k = 0; k < n; k++) { var an = Math.random() * 6.283, v = (sp || 160) * (.3 + Math.random()); parts.push({ x: x, y: y, vx: Math.cos(an) * v, vy: Math.sin(an) * v, life: 1, d: .5 + Math.random() * .6, col: ramp(CHAIN, Math.random()) || col }); } }
  function flash(c, k) { if (RM.matches) { c.glow = 1; return; } c.flash = Math.max(c.flash, k || 1); }
  function emit(type, c) { try { var r = cv.getBoundingClientRect(); root.dispatchEvent(new CustomEvent('sost:cubes', { detail: { type: type, x: r.left + (c ? c.x : 0), y: r.top + (c ? c.y : 0), mode: mode, col: c ? c.col.map(Math.round) : null } })); } catch (e) {} }
  function say(t) { if (live) live.textContent = t; }

  // ---- modes ----
  function setMode(m, why) {
    if (!on && m !== 'off') return; measureZones();
    if (m === 'auto' && RM.matches) m = 'chain';
    if (m === 'scatter') {
      links.slice().forEach(dropLink); mode = 'free';
      cubes.forEach(function (c) {
        if (RM.matches) { c.x = W * .55 + Math.random() * (W * .42); c.y = 120 + Math.random() * (Hh * .5); c.vx = c.vy = 0; clampPos(c); keepOut(c, 0); return; }
        var an = -1.2 + Math.random() * 2.4, v = 420 + Math.random() * 520; c.vx = Math.cos(an) * v * (Math.random() < .25 ? -.6 : 1); c.vy = Math.sin(an) * v; c.wy = (Math.random() - .5) * 14; c.wp = (Math.random() - .5) * 10; c.wr = (Math.random() - .5) * 6; flash(c, .8); burst(c.x, c.y, c.col, 10, 220);
      });
      markBar('scatter'); say('Cubes scattered. Drag them, or bring two close together to join them.'); wake(); return;
    }
    if (m === 'reset') {
      cubes.forEach(function (c) { c.slot = c.home; }); mode = RM.matches ? 'chain' : 'auto'; chainLinks();
      cubes.forEach(function (c) { c.ty = c.tp = c.tr = 0; c.yaw = wrapNear(c.yaw, 0); c.pitch = wrapNear(c.pitch, 0); c.roll = wrapNear(c.roll, 0); if (RM.matches) { var sl = slots[c.slot]; c.x = sl.x; c.y = sl.y; c.yaw = c.pitch = c.roll = 0; c.vx = c.vy = 0; } flash(c, .5); });
      markBar('reset'); say('Cubes restored to the original chain.'); wake(); return;
    }
    if (m === 'chain' || m === 'auto') { if (mode === 'free' || !links.length) chainLinks(); cubes.forEach(function (c) { c.tp = snapAng(c.tp); c.ty = snapAng(c.ty); c.tr = 0; }); if (RM.matches) cubes.forEach(function (c) { var sl = slots[c.slot]; c.x = sl.x; c.y = sl.y; c.vx = c.vy = 0; }); }
    mode = m; markBar(m); say(m === 'auto' ? 'Autonomous animation.' : m === 'chain' ? 'Cubes assembled into a chain. Drop a cube on another position to reorder.' : 'Free manipulation. Bring two cubes close to join them; pull hard or long-press to separate.'); wake();
  }
  function snapAng(a) { var q = Math.PI / 2; return Math.round(a / q) * q; }
  function wrapNear(a, t) { var p = Math.PI * 2; return t + ((a - t) % p + p * 1.5) % p - p * .5; }

  // ---- physics ----
  function step(dt) {
    var reduce = RM.matches, chainLike = mode === 'chain' || mode === 'auto';
    tAuto += dt;
    if (mode === 'auto' && !grab && !reduce && tAuto > nextRipple) { nextRipple = tAuto + 7 + Math.random() * 4; cubes.slice().sort(function (a, b) { return a.slot - b.slot; }).forEach(function (c, k) { setTimeout(function () { if (mode === 'auto') { c.tp += Math.PI; flash(c, .35); } }, k * 110); }); }
    cubes.forEach(function (c) {
      if (grab && grab.c === c) return;
      if (chainLike) {
        var sl = slots[c.slot] || slots[0], tx = sl.x, ty = sl.y;
        if (mode === 'auto' && !reduce) { var ph = tAuto * .9 + c.slot * .55; tx += Math.cos(ph * .7) * c.s * .05; ty += Math.sin(ph) * c.s * .12; }
        if (reduce && !grab) { c.x = tx; c.y = ty; c.vx = c.vy = 0; }
        else { var k = 70, d = 2 * Math.sqrt(k) * .75; c.vx += ((tx - c.x) * k - c.vx * d) * dt; c.vy += ((ty - c.y) * k - c.vy * d) * dt; }
      } else {
        var damp = Math.exp(-1.6 * dt); c.vx *= damp; c.vy *= damp; keepOut(c, dt);
      }
    });
    if (!chainLike) {
      // magnetic links: spring to rest length; break when stretched far
      links.slice().forEach(function (L) {
        var a = L.a, b = L.b, dx = b.x - a.x, dy = b.y - a.y, dd = Math.sqrt(dx * dx + dy * dy) || 1, st = dd - L.L;
        if (dd > L.L * 2.3) { dropLink(L); a.noJoin = b.noJoin = tAuto + 1.2; flash(a, .6); flash(b, .6); burst((a.x + b.x) / 2, (a.y + b.y) / 2, a.col, 14, 200); emit('break', b); say('Link broken.'); return; }
        var k = 90, f = st * k * dt, ux = dx / dd, uy = dy / dd, rv = ((b.vx - a.vx) * ux + (b.vy - a.vy) * uy) * 6 * dt;
        if (!(grab && grab.c === a)) { a.vx += ux * (f + rv); a.vy += uy * (f + rv); }
        if (!(grab && grab.c === b)) { b.vx -= ux * (f + rv); b.vy -= uy * (f + rv); }
        L.born = Math.min(1, L.born + dt * 2.5);
      });
      // soft collisions between cubes that are not linked
      for (var i = 0; i < cubes.length; i++) for (var j = i + 1; j < cubes.length; j++) {
        var A = cubes[i], B = cubes[j]; if (linked(A, B)) continue;
        var dx2 = B.x - A.x, dy2 = B.y - A.y, d2 = Math.sqrt(dx2 * dx2 + dy2 * dy2) || 1, min = (A.s + B.s) * .5 * 1.1;
        if (d2 < min) {
          var push = (min - d2) * .5, nx = dx2 / d2, ny = dy2 / d2, rel = (B.vx - A.vx) * nx + (B.vy - A.vy) * ny;
          if (!(grab && grab.c === A)) { A.x -= nx * push; A.y -= ny * push; }
          if (!(grab && grab.c === B)) { B.x += nx * push; B.y += ny * push; }
          if (rel < 0) { var im = rel * .8; if (!(grab && grab.c === A)) { A.vx += nx * im; A.vy += ny * im; } if (!(grab && grab.c === B)) { B.vx -= nx * im; B.vy -= ny * im; } if (-rel > 380) { burst(A.x + nx * A.s * .5, A.y + ny * A.s * .5, A.col, 6, 140); flash(A, .3); flash(B, .3); } }
        }
      }
    }
    // magnetic attraction signal + join (FREE)
    cubes.forEach(function (c) { c.sig = Math.max(0, c.sig - dt * 3); });
    if (!chainLike) {
      for (var p = 0; p < cubes.length; p++) for (var q = p + 1; q < cubes.length; q++) {
        var a2 = cubes[p], b2 = cubes[q]; if (linked(a2, b2) || a2.links.length > 1 || b2.links.length > 1 || tAuto < (a2.noJoin || 0) || tAuto < (b2.noJoin || 0)) continue;
        var ddx = b2.x - a2.x, ddy = b2.y - a2.y, dist = Math.sqrt(ddx * ddx + ddy * ddy), R = restLen(a2, b2) * 1.35;
        if (dist < R && group(a2).indexOf(b2) < 0) {
          a2.sig = b2.sig = 1;
          // joining is the visitor's gesture: one of the two is held, or was let go / moved with the keyboard less than 1.2 s ago
          var moving = grab && (grab.c === a2 || grab.c === b2), slow = Math.abs(a2.vx) + Math.abs(a2.vy) + Math.abs(b2.vx) + Math.abs(b2.vy) < 260;
          var handled = moving || tAuto - Math.max(a2.touchT || -9, b2.touchT || -9) < 1.2; if (!handled) { a2.sig = b2.sig = 0; continue; }
          a2.near = a2.near || {}; var key = b2.i; a2.near[key] = (a2.near[key] || 0) + dt;
          if ((!moving && slow) || a2.near[key] > (moving ? .4 : .25)) {
            addLink(a2, b2); a2.near[key] = 0; flash(a2, 1); flash(b2, 1); burst((a2.x + b2.x) / 2, (a2.y + b2.y) / 2, a2.col, 22, 240);
            waves.push({ x: (a2.x + b2.x) / 2, y: (a2.y + b2.y) / 2, r: 4, life: 1, col: mix(a2.col, b2.col, .5) }); emit('snap', b2); say('Linked: chain of ' + group(a2).length + ' cubes.');
          }
        } else if (a2.near) a2.near[b2.i] = 0;
      }
    }
    // integrate
    cubes.forEach(function (c) {
      if (!(grab && grab.c === c)) {
        c.x += c.vx * dt; c.y += c.vy * dt;
        var m = c.s * .62;
        if (c.x < m) { c.x = m; c.vx = Math.abs(c.vx) * .55; } if (c.x > W - m) { c.x = W - m; c.vx = -Math.abs(c.vx) * .55; }
        if (c.y < m + 8) { c.y = m + 8; c.vy = Math.abs(c.vy) * .55; } if (c.y > Hh - m) { c.y = Hh - m; c.vy = -Math.abs(c.vy) * .55; }
      }
      // rotation: free spin decays and settles flat on the nearest quarter turn
      var ks = reduce ? 400 : 30, ds = 2 * Math.sqrt(ks) * .8;
      c.wy += ((c.ty - c.yaw) * ks - c.wy * ds) * dt; c.wp += ((c.tp - c.pitch) * ks - c.wp * ds) * dt; c.wr += ((c.tr - c.roll) * ks - c.wr * ds) * dt;
      c.yaw += c.wy * dt; c.pitch += c.wp * dt; c.roll += c.wr * dt;
      // proximity reaction: glow, and a slight lean towards the pointer (never accumulated: the cube rights itself)
      var near = 0, lean = 0; if (ptr.in) { var px = ptr.x - c.x, py = ptr.y - c.y, pd = Math.sqrt(px * px + py * py); near = Math.max(0, 1 - pd / (c.s * 2.4)); if (!reduce) lean = (px / (pd || 1)) * near * .14; }
      c.tr = grab && grab.c === c ? Math.max(-.5, Math.min(.5, grab.vx * .0007)) : lean;
      var tg = Math.max(near * .8, hoverC === c ? 1 : 0, grab && grab.c === c ? 1 : 0, kbFocus && cubes[kbSel] === c ? 1 : 0);
      c.glow += (tg - c.glow) * Math.min(1, dt * 8); c.flash = Math.max(0, c.flash - dt * 2.2);
      var T = TIERS[tier]; var sp = Math.abs(c.vx) + Math.abs(c.vy);
      if (T.trail && !reduce && sp > 260) { c.trail.push({ x: c.x, y: c.y, yaw: c.yaw, pitch: c.pitch, roll: c.roll, s: c.s, col: c.col, flash: 0, glow: 0, sig: 0, a: 1 }); if (c.trail.length > T.trail) c.trail.shift(); }
      else if (c.trail.length) c.trail.shift();
    });
    parts = parts.filter(function (p) { p.life -= dt / p.d; p.x += p.vx * dt; p.y += p.vy * dt; p.vx *= .96; p.vy *= .96; return p.life > 0; });
    waves = waves.filter(function (w) { w.life -= dt * 1.8; w.r += dt * 260; return w.life > 0; });
    energy *= Math.exp(-dt * 2);
  }
  function busy() {
    if (grab || mode === 'auto' || parts.length || waves.length || twist) return true;
    return cubes.some(function (c) {
      var sl = slots[c.slot], far = (mode === 'chain') && sl && (Math.abs(sl.x - c.x) + Math.abs(sl.y - c.y) > .3);
      return far || Math.abs(c.vx) + Math.abs(c.vy) > 1.5 || Math.abs(c.wy) + Math.abs(c.wp) + Math.abs(c.wr) > .01 || Math.abs(c.ty - c.yaw) + Math.abs(c.tp - c.pitch) > .002 || c.flash > .01 || Math.abs(c.glow - (hoverC === c ? 1 : 0)) > .02 || c.trail.length || c.sig > 0;
    }) || links.some(function (L) { return L.born < 1; });
  }

  // ---- render ----
  function render() {
    g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, Hh);
    var T = TIERS[tier];
    // links: the chain light between linked blocks (+ signal for a near join)
    g.lineCap = 'round';
    links.forEach(function (L) {
      var a = L.a, b = L.b, al = .35 * L.born + .3 * Math.max(a.flash, b.flash);
      g.strokeStyle = 'rgba(255,255,255,' + al.toFixed(3) + ')'; g.lineWidth = 1.2 + Math.max(a.flash, b.flash) * 1.5;
      g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
      if (T.glow) { g.globalCompositeOperation = 'lighter'; g.strokeStyle = rgba(mix(a.col, b.col, .5), .16 * L.born + .2 * Math.max(a.flash, b.flash)); g.lineWidth = 5; g.stroke(); g.globalCompositeOperation = 'source-over'; }
    });
    if (mode === 'free') {
      for (var p = 0; p < cubes.length; p++) for (var q = p + 1; q < cubes.length; q++) {
        var A = cubes[p], B = cubes[q]; if (!A.sig || !B.sig || linked(A, B)) continue;
        var dx = B.x - A.x, dy = B.y - A.y, dd = Math.sqrt(dx * dx + dy * dy); if (dd > restLen(A, B) * 1.4) continue;
        g.setLineDash([4, 6]); g.lineDashOffset = -tAuto * 40; g.strokeStyle = rgba(mix(A.col, B.col, .5), .75); g.lineWidth = 1.4; g.beginPath(); g.moveTo(A.x, A.y); g.lineTo(B.x, B.y); g.stroke(); g.setLineDash([]);
      }
    }
    waves.forEach(function (w) { g.strokeStyle = rgba(mix(w.col, WHITE, .4), w.life * .6); g.lineWidth = 1.5; g.beginPath(); g.arc(w.x, w.y, w.r, 0, 6.283); g.stroke(); });
    // trails, then cubes far-to-near by size (bigger = nearer)
    cubes.forEach(function (c) { c.trail.forEach(function (t, k) { drawCube(t, (k + 1) / (c.trail.length + 1) * .16, true); }); });
    var ord = cubes.slice().sort(function (a, b) { return (grab && grab.c === a ? 1 : 0) - (grab && grab.c === b ? 1 : 0) || a.s - b.s; });
    ord.forEach(function (c) { drawCube(c, c.base); });
    if (kbFocus && cubes[kbSel]) { var k = cubes[kbSel]; g.setLineDash([3, 4]); g.strokeStyle = 'rgba(255,255,255,.85)'; g.lineWidth = 1.5; g.beginPath(); g.arc(k.x, k.y, k.s * .95, 0, 6.283); g.stroke(); g.setLineDash([]); }
    if (parts.length) { g.globalCompositeOperation = 'lighter'; parts.forEach(function (p) { g.fillStyle = rgba(p.col, p.life * .9); var z = 1.2 + p.life * 1.6; g.fillRect(p.x - z / 2, p.y - z / 2, z, z); }); g.globalCompositeOperation = 'source-over'; }
  }
  function frame(t) {
    raf = 0; if (!running) return;
    if (!lastT) lastT = t - 34;   // first frame after waking: draw at once
    var T = TIERS[tier], dtms = t - lastT;
    var ambient = mode === 'auto' && !grab && !parts.length && !waves.length && !cubes.some(function (c) { return c.flash > .01 || c.glow > .05; });
    var cap = ambient ? 30 : T.fps;   // the slow autonomous float needs no more than 30 frames per second
    if (cap < 60 && dtms < 1000 / cap - 2) { raf = root.requestAnimationFrame(frame); return; }
    lastT = t; var dt = Math.min(1 / 30, dtms / 1000);
    measure(dtms);
    var c0 = performance.now(); step(dt); render(); var cost = performance.now() - c0; perf.n++; perf.sum += cost; if (cost > perf.max) perf.max = cost; perf.frames++;
    if (busy() && visible && inView && !imm) raf = root.requestAnimationFrame(frame); else { running = false; lastT = 0; }
  }
  function wake() { if (!on || !g) return; if (!running && visible && inView) { running = true; lastT = 0; raf = root.requestAnimationFrame(frame); } }
  // AUTO tier: steps down when the frame time stays high (the WebGL scene shares the frame)
  function measure(dtms) {
    if (tierReq !== 'auto' || dtms > 250) return; ftimes.push(dtms); if (ftimes.length < 90) return;
    var avg = ftimes.reduce(function (a, b) { return a + b; }, 0) / ftimes.length; ftimes = [];
    // hysteresis: two slow windows in a row (> 26 ms ≈ < 38 fps) step down; four fast ones (< 18 ms) step back up to the start tier
    slowW = avg > 26 ? slowW + 1 : 0; fastW = avg < 18 ? fastW + 1 : 0;
    var order = ['lite', 'balanced', 'high'], i = order.indexOf(tier), top = order.indexOf(tierTop);
    if (slowW >= 2 && i > 0) { tier = order[i - 1]; slowW = 0; }
    else if (fastW >= 4 && i < top) { tier = order[i + 1]; fastW = 0; } else return;
    autoNote = tier === tierTop ? '' : 'AUTO → ' + (tier === 'balanced' ? 'BAL' : 'LITE'); fit(); markTier();
  }
  // ---- input ----
  var EXCL = 'a,button,input,select,textarea,label,summary,details,[role="button"],[contenteditable],nav,.u-nav,.hcards,.hc,#hstepsW,.hsteps-w,.ua,.cubeBar,h1,h2,h3,p,li,.lede,.ctas,.eyebrow,.latest,.u-bar,dialog,#immT,#immNavTab,#immCardsTab,#immEye';
  function local(e) { var r = cv.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top, ok: e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom }; }
  function hit(x, y) { var best = null, bd = 1e9; cubes.forEach(function (c) { var dx = x - c.x, dy = y - c.y, d = Math.sqrt(dx * dx + dy * dy); if (d < c.s * .66 && (d < bd || (best && c.s > best.s && d < c.s * .5))) { best = c; bd = d; } }); return best; }
  function usable() { return on && !imm && g && cv.offsetParent !== null; }
  function onDown(e) {
    if (!usable() || (e.button && e.button !== 0)) return;
    if (grab && e.pointerType === 'touch' && e.pointerId !== grab.id) { pointers[e.pointerId] = { x: e.clientX, y: e.clientY }; twist = { id: e.pointerId, a0: angTo(e), yaw0: grab.c.ty }; return; }
    var t = e.target; if (t && t.closest && t.closest(EXCL)) return;
    var p = local(e); if (!p.ok) return; var c = hit(p.x, p.y); if (!c) return;
    e.preventDefault();
    var now = performance.now();
    if (now - c.tap < 330) { flip(c); c.tap = 0; return; }
    c.tap = now;
    if (mode === 'auto') setMode('free');
    grab = { c: c, id: e.pointerId, dx: c.x - p.x, dy: c.y - p.y, vx: 0, vy: 0, lx: p.x, ly: p.y, lt: now, t0: now, moved: 0, shift: e.shiftKey, rx: e.clientX, slot0: c.slot };
    pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
    c.vx = c.vy = 0; flash(c, 1); burst(c.x, c.y, c.col, 16, 180); H.classList.add('cube-drag'); emit('grab', c);
    kbSel = cubes.indexOf(c); say('Cube ' + (kbSel + 1) + ' of ' + cubes.length + ' selected.'); wake();
    clearTimeout(grab.lp); grab.lp = setTimeout(function () { if (grab && grab.c === c && grab.moved < 6 && c.links.length) { detach(c); flash(c, 1); burst(c.x, c.y, c.col, 18, 220); emit('break', c); say('Cube detached from its chain.'); wake(); } }, 560);
  }
  function angTo(e) { var g0 = grab ? pointers[grab.id] : null; return g0 ? Math.atan2(e.clientY - g0.y, e.clientX - g0.x) : 0; }
  function onMove(e) {
    if (twist && e.pointerId === twist.id && grab) { pointers[e.pointerId] = { x: e.clientX, y: e.clientY }; grab.c.ty = twist.yaw0 + (angTo(e) - twist.a0); wake(); return; }
    if (grab && e.pointerId === grab.id) {
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      var p = local(e), now = performance.now(), c = grab.c, dtm = Math.max(1, now - grab.lt);
      if (grab.shift || e.shiftKey) { c.ty += (e.clientX - grab.rx) * .02; grab.rx = e.clientX; wake(); return; }
      var nx = p.x + grab.dx, ny = p.y + grab.dy; grab.moved += Math.abs(nx - c.x) + Math.abs(ny - c.y);
      grab.vx = grab.vx * .6 + ((nx - c.x) / dtm * 1000) * .4; grab.vy = grab.vy * .6 + ((ny - c.y) / dtm * 1000) * .4;
      c.x = nx; c.y = ny; clampPos(c); grab.lt = now;
      if (mode === 'chain') reorder(c);
      ptr = { x: p.x, y: p.y, in: true }; wake(); return;
    }
    if (e.pointerType === 'touch' || !usable()) return;
    var q = local(e); ptr = { x: q.x, y: q.y, in: q.ok };
    var t = e.target, over = q.ok && !(t && t.closest && t.closest(EXCL)) ? hit(q.x, q.y) : null;
    if (over !== hoverC) { hoverC = over; H.classList.toggle('cube-hover', !!over); }
    if (q.ok && cubes.some(function (c) { return Math.abs(q.x - c.x) + Math.abs(q.y - c.y) < c.s * 3; })) wake();
  }
  function onUp(e) {
    if (twist && e.pointerId === twist.id) { twist = null; delete pointers[e.pointerId]; return; }
    if (!grab || e.pointerId !== grab.id) return;
    var c = grab.c; clearTimeout(grab.lp); delete pointers[e.pointerId];
    if (performance.now() - grab.lt > 80) { grab.vx = 0; grab.vy = 0; }   // held still before letting go: it stays where it was put
    if (mode === 'chain') { var sl = slots[c.slot]; c.vx = c.vy = 0; if (sl && grab.slot0 !== c.slot) say('Cube moved to position ' + (c.slot + 1) + ' of the chain.'); }
    else if (!RM.matches) { c.vx = Math.max(-1600, Math.min(1600, grab.vx)); c.vy = Math.max(-1600, Math.min(1600, grab.vy)); c.ty = snapAng(c.ty + grab.vx * .0016); c.tp = snapAng(c.tp - grab.vy * .0016); }   // a flick spins it, it lands flat
    else { c.vx = c.vy = 0; }
    measureZones(); c.touchT = tAuto; flash(c, .6); emit('drop', c); grab = null; twist = null; H.classList.remove('cube-drag'); wake();
  }
  function reorder(c) {
    var best = -1, bd = 1e9; slots.forEach(function (sl, i) { var d = Math.abs(sl.x - c.x) + Math.abs(sl.y - c.y); if (d < bd) { bd = d; best = i; } });
    if (best < 0 || best === c.slot || bd > slots[best].s * .9) return;
    var other = cubes.filter(function (o) { return o.slot === best; })[0]; if (other) { other.slot = c.slot; flash(other, .4); }
    c.slot = best; chainLinks(); burst(c.x, c.y, c.col, 8, 140);
  }
  function flip(c) { c.tp += Math.PI; flash(c, 1); burst(c.x, c.y, c.col, 14, 200); emit('flip', c); say('Cube flipped.'); wake(); }
  function onWheel(e) { if (!grab) return; e.preventDefault(); grab.c.ty += (e.deltaY > 0 ? 1 : -1) * Math.PI / 4; grab.c.ty = snapAng(grab.c.ty * 2) / 2; wake(); }
  function onTouchStart(e) { if (grab) e.preventDefault(); }   // a touch that grabbed a cube never scrolls the page

  // ---- keyboard controller ----
  function onKey(e) {
    var c = cubes[kbSel]; if (!c) return; var k = e.key, d = e.shiftKey ? 6 : 24, used = true;
    if (k === '[' || k === 'PageUp') kbSel = (kbSel + cubes.length - 1) % cubes.length;
    else if (k === ']' || k === 'PageDown') kbSel = (kbSel + 1) % cubes.length;
    else if (/^Arrow/.test(k)) {
      if (mode === 'auto' || mode === 'chain') setMode('free');
      var mx = k === 'ArrowLeft' ? -d : k === 'ArrowRight' ? d : 0, my = k === 'ArrowUp' ? -d : k === 'ArrowDown' ? d : 0;
      group(c).forEach(function (o) { o.x += mx; o.y += my; o.vx = o.vy = 0; clampPos(o); o.touchT = tAuto; }); flash(c, .3);   // a linked chain moves as one (D detaches first)
    } else if (k === 'r' || k === 'R') { c.ty += Math.PI / 2; flash(c, .5); say('Cube rotated.'); }
    else if (k === 'f' || k === 'F') flip(c);
    else if (k === 'd' || k === 'D') { detach(c); flash(c, .6); say('Cube detached.'); }
    else used = false;
    if (used) { e.preventDefault(); if (/^\[|\]|Page/.test(k)) say('Cube ' + (kbSel + 1) + ' of ' + cubes.length + ' selected.'); wake(); }
  }

  // ---- toolbar ----
  function markBar(m) { if (!bar) return; bar.querySelectorAll('[data-m]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-m') === m || (m === 'scatter' && b.getAttribute('data-m') === 'scatter'))); }); }
  function markTier() { if (!bar) return; var n = bar.querySelector('.cb-tier'); if (n) n.textContent = on ? (tierReq === 'auto' ? (autoNote || 'AUTO') : tierReq === 'balanced' ? 'BAL' : tierReq.toUpperCase()) + (RM.matches ? ' · reduced motion' : '') : ''; }
  function placeBar() {
    if (!bar || !slots.length) return;
    var low = 0; slots.forEach(function (s) { low = Math.max(low, s.y + s.s * .7); });
    bar.style.top = Math.round(low + 26) + 'px';
  }
  function makeBar() {
    bar = doc.createElement('div'); bar.className = 'cubeBar'; bar.setAttribute('role', 'toolbar'); bar.setAttribute('aria-label', 'Interactive cubes');
    bar.innerHTML = '<span class="cb-l" aria-hidden="true">CUBES</span>' +
      ['scatter', 'chain', 'free', 'reset', 'auto'].map(function (m) { return '<button type="button" data-m="' + m + '" aria-pressed="false">' + m.toUpperCase() + '</button>'; }).join('') +
      '<button type="button" class="cb-kb" aria-label="Cube keyboard controller: [ and ] select a cube, arrows move it, R rotates, F flips, D detaches">⌨ CUBE</button>' +
      '<button type="button" class="cb-on" aria-pressed="true" title="Turn the interactive cubes off or on">ON</button><span class="cb-tier" aria-hidden="true"></span>' +
      '<span class="cb-live" aria-live="polite"></span>';
    cv.parentNode.appendChild(bar); live = bar.querySelector('.cb-live');
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      if (b.classList.contains('cb-on')) { setOn(!on); return; }
      if (b.classList.contains('cb-kb')) return;
      var m = b.getAttribute('data-m'); if (m) setMode(m);
    });
    var kb = bar.querySelector('.cb-kb');
    kb.addEventListener('focus', function () { kbFocus = true; say('Cube ' + (kbSel + 1) + ' of ' + cubes.length + ' selected. [ and ] choose, arrows move, R rotates, F flips, D detaches.'); wake(); });
    kb.addEventListener('blur', function () { kbFocus = false; wake(); });
    kb.addEventListener('keydown', onKey);
    if (RM.matches) { var ab = bar.querySelector('[data-m="auto"]'); ab.setAttribute('aria-disabled', 'true'); ab.title = 'Autonomous animation is off: your system asks for reduced motion'; }
  }
  function setOn(v) {
    on = !!v; pref.on = on; lsSet(pref); bar.classList.toggle('off', !on); var b = bar.querySelector('.cb-on'); b.textContent = on ? 'ON' : 'CUBES OFF'; b.setAttribute('aria-pressed', String(on));
    if (on) { cv.setAttribute('data-live', '1'); build(false); mode = RM.matches ? 'chain' : 'auto'; markBar(mode); placeBar(); render(); wake(); say('Interactive cubes on.'); }
    else { running = false; grab = null; H.classList.remove('cube-drag', 'cube-hover'); cv.removeAttribute('data-live'); parts = []; waves = []; if (root.SOSTHomeArt) root.SOSTHomeArt.redraw(); say('Interactive cubes off: static chain.'); }
    markTier();
  }

  // ---- immersive: controls hidden, cubes back to the original chain, arrangement restored on exit ----
  function onImm() {
    var v = H.classList.contains('u-imm'); if (v === imm) return; imm = v;
    if (!on || !g) return;
    if (imm) {
      saved = { mode: mode, links: links.map(function (L) { return [L.a.i, L.b.i]; }), c: cubes.map(function (c) { return { x: c.x, y: c.y, slot: c.slot, yaw: c.ty, pitch: c.tp }; }) };
      grab = null; H.classList.remove('cube-drag', 'cube-hover'); hoverC = null;
      cubes.forEach(function (c) { c.slot = c.home; var sl = slots[c.slot]; c.x = sl.x; c.y = sl.y; c.vx = c.vy = 0; c.yaw = c.pitch = c.roll = c.ty = c.tp = c.tr = 0; c.wy = c.wp = c.wr = 0; c.trail = []; c.flash = c.glow = 0; });
      parts = []; waves = []; chainLinks(); running = false; render();
    } else if (saved) {
      cubes.forEach(function (c, k) { var s = saved.c[k]; if (!s) return; c.x = s.x; c.y = s.y; c.slot = s.slot; c.ty = c.yaw = s.yaw; c.tp = c.pitch = s.pitch; clampPos(c); });
      links = []; cubes.forEach(function (c) { c.links = []; }); saved.links.forEach(function (p) { addLink(cubes[p[0]], cubes[p[1]], true); });
      mode = saved.mode; saved = null; markBar(mode); render(); wake();
    }
  }

  // ---- boot ----
  function boot() {
    cv = doc.getElementById('chainCv'); anchor = doc.getElementById('coreAnchor');
    if (!cv || !cv.getContext) return;
    makeBar(); imm = H.classList.contains('u-imm');
    if (!on) { bar.classList.add('off'); var b0 = bar.querySelector('.cb-on'); b0.textContent = 'CUBES OFF'; b0.setAttribute('aria-pressed', 'false'); markTier(); return start(false); }
    start(true);
  }
  function start(active) {
    var qb = doc.querySelector('.qual button[aria-pressed="true"]'); setTierReq(qb ? qb.getAttribute('data-q') : 'auto');
    doc.querySelectorAll('.qual button[data-q]').forEach(function (b) { b.addEventListener('click', function () { setTierReq(b.getAttribute('data-q')); }); });
    var ready = function () {
      if (cv.offsetParent === null) { root.addEventListener('resize', function once() { if (cv.offsetParent !== null) { root.removeEventListener('resize', once); ready(); } }); return; }
      if (active) { cv.setAttribute('data-live', '1'); build(false); mode = RM.matches ? 'chain' : 'auto'; markBar(mode); placeBar(); if (imm) { imm = false; onImm(); } else { render(); wake(); } }
      else { var r0 = cv.getBoundingClientRect(); W = r0.width; Hh = r0.height; slots = computeSlots(); placeBar(); }   // off: only place the toolbar (never resize the static canvas)
    };
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(ready); else ready();
    doc.addEventListener('pointerdown', onDown, { capture: true });
    doc.addEventListener('pointermove', onMove, { capture: true, passive: true });
    doc.addEventListener('pointerup', onUp, { capture: true }); doc.addEventListener('pointercancel', onUp, { capture: true });
    doc.addEventListener('touchstart', onTouchStart, { capture: true, passive: false });
    doc.addEventListener('touchmove', function (e) { if (grab) e.preventDefault(); }, { capture: true, passive: false });
    root.addEventListener('wheel', onWheel, { passive: false });
    doc.addEventListener('dblclick', function (e) { if (grab || !usable()) return; var t = e.target; if (t && t.closest && t.closest(EXCL)) return; var p = local(e), c = hit(p.x, p.y); if (c) e.preventDefault(); });
    cv.parentNode.addEventListener('pointerleave', function () { ptr.in = false; if (hoverC) { hoverC = null; H.classList.remove('cube-hover'); } wake(); });
    doc.addEventListener('visibilitychange', function () { visible = !doc.hidden; if (visible) wake(); });
    try { new IntersectionObserver(function (es) { inView = es[0].isIntersecting; if (inView) wake(); }).observe(cv); } catch (e) {}
    try { new MutationObserver(onImm).observe(H, { attributes: true, attributeFilter: ['class'] }); } catch (e) {}
    var tm = 0; root.addEventListener('resize', function () { clearTimeout(tm); tm = setTimeout(function () { if (cv.offsetParent === null) return; if (!on) { var r1 = cv.getBoundingClientRect(); W = r1.width; Hh = r1.height; slots = computeSlots(); placeBar(); return; } build(true); placeBar(); render(); wake(); }, 140); });
    if (RM.addEventListener) RM.addEventListener('change', function () { if (mode === 'auto' && RM.matches) setMode('chain'); markTier(); });
    // the scene: re-anchor and ripple on every scene change, ripple from a click on the scene, glow with the soundtrack
    try { root.SOSTUniverse.scene.on(function (d) { if (!on || !g || !cubes.length || d.reason === 'current') return; setTimeout(function () { build(true); placeBar(); cubes.slice().sort(function (a, b) { return a.slot - b.slot; }).forEach(function (c, k) { setTimeout(function () { flash(c, .7); wake(); }, k * 70); }); }, 60); }); } catch (e) {}
    cv.parentNode.addEventListener('pointerdown', function (e) {
      if (!usable() || grab || RM.matches) return; var t = e.target; if (t && t.closest && t.closest(EXCL)) return;
      var p = local(e); if (!p.ok) return; waves.push({ x: p.x, y: p.y, r: 4, life: .8, col: [34, 211, 238] });
      cubes.forEach(function (c) { var dx = c.x - p.x, dy = c.y - p.y, d = Math.sqrt(dx * dx + dy * dy) || 1, f = Math.max(0, 1 - d / 420); if (!f) return; flash(c, f * .6); if (mode === 'free') { c.vx += dx / d * f * 420; c.vy += dy / d * f * 420; } }); wake();
    }, { passive: true });
    root.addEventListener('sost:audio-energy', function (e) { if (!on || RM.matches || tier === 'lite' || tier === 'off') return; var v = e.detail && e.detail.energy || 0; if (v > energy) energy = v * .6; });
  }
  function setTierReq(q) {
    tierReq = q || 'auto'; autoNote = ''; ftimes = [];
    tier = tierReq === 'auto' ? ((navigator.hardwareConcurrency || 4) >= 8 ? 'high' : 'balanced') : tierReq === 'off' ? 'lite' : (TIERS[tierReq] ? tierReq : 'high');
    tierTop = tier; slowW = fastW = 0;
    if (g) { fit(); render(); wake(); } markTier();
  }
  root.SOSTCubes = {
    perf: function (reset) { var r = { frames: perf.frames, avg_ms: perf.n ? +(perf.sum / perf.n).toFixed(3) : 0, max_ms: +perf.max.toFixed(2) }; if (reset) perf = { n: 0, sum: 0, max: 0, frames: 0 }; return r; },
    state: function () { return { on: on, mode: mode, tier: tier, tierReq: tierReq, imm: imm, running: running, grab: !!grab, links: links.length, parts: parts.length,
      groups: (function () { var seen = [], n = []; cubes.forEach(function (c) { if (seen.indexOf(c) >= 0) return; var gr = group(c); seen = seen.concat(gr); n.push(gr.length); }); return n; })(),
      cubes: cubes.map(function (c) { var r = cv.getBoundingClientRect(); return { i: c.i, slot: c.slot, chain: group(c).map(function (o) { return o.i; }).sort(), x: Math.round(r.left + c.x), y: Math.round(r.top + c.y), lx: Math.round(c.x), ly: Math.round(c.y), s: Math.round(c.s), pitch: +c.pitch.toFixed(2), yaw: +c.yaw.toFixed(2), links: c.links.length }; }) }; },
    setMode: setMode, setOn: function (v) { setOn(v); }, flip: function (i) { if (cubes[i]) flip(cubes[i]); },
    tier: function (q) { setTierReq(q); return tier; }
  };
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot); else boot();
})(window);

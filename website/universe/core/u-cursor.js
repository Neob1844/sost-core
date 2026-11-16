/* SOST Universe — Gravitational Cursor (owner order 4 Nov 2026, «SOST CONVERGENCE UNIVERSE — GRAVITATIONAL CURSOR»).
 * A micro-singularity travels with the pointer: a deep black core, a multicolour SOST photon ring with a lensing arc brighter towards
 * the direction of travel, a curved particle trail whose intensity follows the speed, and a gravitational wave with a neutral
 * ~4000 K flash on every click. Over buttons and links the ring contracts and steadies ("target acquired"); while a Home cube is
 * dragged it takes the cube's colour and the trail lengthens.
 *
 * It never gets in the way:
 *  - the native arrow stays visible and exact; this is one fixed transparent canvas with pointer-events:none, drawn slightly off the
 *    arrow tip; listeners are passive and never call preventDefault — clicks, hover, scroll, text selection and keys are untouched;
 *  - no full-screen filter, nothing of the page is distorted; one shared engine for the whole site (guarded against double load);
 *  - off on touch-only devices, with prefers-reduced-motion, on wallet / security / key / trading pages (same guard as the
 *    soundtrack); it fades out over form fields and while one has focus;
 *  - strict limits: particles per tier, the loop sleeps when the pointer is still, and it steps down and finally switches itself off
 *    when the page's frame time stays high; it follows the site quality control (AUTO/HIGH/BAL/LITE/OFF) where there is one;
 *  - CURSOR FX ON/OFF pill (bottom-left, above the music player), remembered in localStorage.
 * No data, no network. */
(function (root) {
  'use strict';
  var doc = root.document, H = doc.documentElement;
  if (root.SOSTCursor) return;
  var BLOCK = /(wallet|vault|security|seed|keys?[-_.]|sign(er|ing)?[-_.]|login|swap|dex|otc|cli-tools|e2e|troubleshooter|explorer|control-room|sost-app)/i;
  var ALLOW = /\/(sost-explorer|universe\/explorer)\.html$/i;   // owner P0: both Explorers (the word 'explorer' alone stays blocked: Control Room, legacy twins)
  var path = root.location.pathname;
  if (BLOCK.test(path) && !ALLOW.test(path)) return;
  var mm = function (q) { try { return root.matchMedia(q); } catch (e) { return { matches: false, addEventListener: function () {} }; } };
  var FINE = mm('(hover: hover) and (pointer: fine)'), RM = mm('(prefers-reduced-motion: reduce)');
  var KEY = 'sostu_cursor_v1';
  function lsGet() { try { return JSON.parse(root.localStorage.getItem(KEY) || '{}') || {}; } catch (e) { return {}; } }
  function lsSet(o) { try { root.localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} }
  var pref = lsGet(), Q = new URLSearchParams(root.location.search);
  if (Q.get('cursorfx') === '0') pref.on = false; if (Q.get('cursorfx') === '1') pref.on = true;

  var SPEC = [[251, 1, 13], [251, 146, 60], [250, 204, 21], [163, 230, 53], [34, 211, 238], [59, 130, 246], [139, 92, 246], [232, 121, 249]];
  var K4000 = [255, 209, 163];
  function rgba(c, a) { return 'rgba(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ',' + Math.max(0, Math.min(1, a)).toFixed(3) + ')'; }
  function mix(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
  function spec(t) { t = ((t % 1) + 1) % 1 * SPEC.length; var i = Math.floor(t), f = t - i; return mix(SPEC[i], SPEC[(i + 1) % SPEC.length], f); }

  var LEVELS = { high: { parts: 140, dpr: 2, halo: 1 }, balanced: { parts: 70, dpr: 1.5, halo: 1 }, lite: { parts: 24, dpr: 1, halo: 0 } };
  var level = (navigator.hardwareConcurrency || 4) >= 8 ? 'high' : 'balanced', levelTop = level, siteQ = 'auto', fpsOff = false;
  var cv = null, g = null, W = 0, Hh = 0, dpr = 1, btn = null;
  var on = pref.on !== false, active = false, running = false, raf = 0, lastT = 0;
  var P = { x: -100, y: -100, tx: -100, ty: -100, vx: 0, vy: 0, sp: 0, ang: 0, inside: false, seen: false };
  var parts = [], waves = [], flashA = 0, spin = 0, targ = 0, texty = 0, veil = 0, fade = 0, formHide = 0, dragCol = null, dragging = false, lastMove = 0;
  var ft = [], slowW = 0, fastW = 0, perf = { n: 0, sum: 0, max: 0 };
  var OFF_X = 9, OFF_Y = 11;   // the singularity sits just below-right of the arrow tip: the tip and what it points at stay clear

  function allowed() { return on && FINE.matches && !RM.matches && siteQ !== 'off' && !fpsOff; }
  // a small canvas (S × S px) that travels with the singularity: only that square is repainted and composited each frame. A
  // full-viewport canvas made the compositor redraw the whole page (backdrop blurs included) and cost up to 15 fps on static pages
  var S = 380, ox = 0, oy = 0;
  function fit() {
    var L = LEVELS[level]; dpr = Math.min(L.dpr, root.devicePixelRatio || 1); W = root.innerWidth; Hh = root.innerHeight;
    var w = Math.round(S * dpr); if (cv.width !== w || cv.height !== w) { cv.width = w; cv.height = w; }
  }
  function mount() {
    cv = doc.createElement('canvas'); cv.id = 'sostCursorFx'; cv.setAttribute('aria-hidden', 'true');
    cv.style.cssText = 'position:fixed;left:0;top:0;width:' + S + 'px;height:' + S + 'px;pointer-events:none;z-index:2147483600;contain:strict;will-change:transform;transform:translate3d(-9999px,0,0)';
    doc.body.appendChild(cv); g = cv.getContext('2d'); fit();
  }
  // ---- target / form detection (read only) ----
  var INTER = 'a[href],button,[role="button"],[role="tab"],[role="link"],summary,label[for],select,input[type="submit"],input[type="button"],input[type="checkbox"],input[type="radio"],.btn';
  var FORMY = 'input:not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]),textarea,select,[contenteditable="true"],[contenteditable=""]';
  function classify(t) {
    if (!t || !t.closest) return 0;
    if (t.closest(FORMY)) return 2;
    if (t.closest(INTER)) return 1;
    return 0;
  }
  // over text (and anything clickable) the core turns translucent and the halo goes: the effect must never hide what is written
  var TEXTY = 'p,h1,h2,h3,h4,h5,h6,li,td,th,dd,dt,blockquote,pre,code,label,a,button,span,small,strong,em,b,i,figcaption,.lede,.eyebrow';
  function hasText(t) {
    if (!t || !t.closest) return false; if (t.closest(TEXTY)) return true;
    for (var n = t.firstChild; n; n = n.nextSibling) if (n.nodeType === 3 && /\S/.test(n.nodeValue)) return true;
    return false;
  }
  function focusedForm() { var a = doc.activeElement; return !!(a && a.matches && a.matches(FORMY)); }

  // ---- input (passive, never prevents anything) ----
  function onMove(e) {
    if (e.pointerType && e.pointerType !== 'mouse' && e.pointerType !== 'pen') return;
    if (!active) return;
    var now = performance.now(), x = e.clientX + OFF_X, y = e.clientY + OFF_Y;
    if (!P.seen) { P.x = P.tx = x; P.y = P.ty = y; P.seen = true; }
    var dt = Math.max(1, now - lastMove); lastMove = now;
    var vx = (x - P.tx) / dt * 1000, vy = (y - P.ty) / dt * 1000;
    P.vx = P.vx * .7 + vx * .3; P.vy = P.vy * .7 + vy * .3; P.tx = x; P.ty = y; P.inside = true;
    var k = classify(e.target); targ = k === 1 ? 1 : 0; texty = targ || hasText(e.target) ? 1 : 0; formHide = k === 2 || focusedForm() ? 1 : 0;
    wake();
  }
  function onDown(e) {
    if (!active || (e.pointerType && e.pointerType !== 'mouse' && e.pointerType !== 'pen')) return;
    if (classify(e.target) === 2) return;   // a click into a field: no wave over the form
    var L = LEVELS[level], col = dragCol || K4000;
    waves.push({ x: e.clientX + OFF_X * .4, y: e.clientY + OFF_Y * .4, r: 6, life: 1, col: col });
    flashA = 1; spray(e.clientX + OFF_X * .4, e.clientY + OFF_Y * .4, Math.min(18, L.parts / 6), 220, true); wake();
  }
  function spray(x, y, n, sp, ring) {
    var L = LEVELS[level]; n = Math.min(n | 0, L.parts - parts.length);
    for (var i = 0; i < n; i++) {
      var a = Math.random() * 6.283, v = sp * (.35 + Math.random() * .8);
      parts.push({ x: x, y: y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, d: .35 + Math.random() * .45, col: ring ? mix(K4000, spec(Math.random()), .5) : spec(Math.random()), sw: (Math.random() < .5 ? -1 : 1) * (2 + Math.random() * 3) });
    }
  }

  // ---- simulation + render ----
  function step(dt) {
    // the singularity follows the pointer with a short, stiff lag (never behind the click: clicks use the real pointer position)
    var k = 1 - Math.exp(-dt * 26); P.x += (P.tx - P.x) * k; P.y += (P.ty - P.y) * k;
    var idle = performance.now() - lastMove > 90; if (idle) { P.vx *= Math.exp(-dt * 10); P.vy *= Math.exp(-dt * 10); }
    P.sp = Math.min(2600, Math.sqrt(P.vx * P.vx + P.vy * P.vy)); if (P.sp > 30) P.ang = Math.atan2(P.vy, P.vx);
    spin += dt * (targ ? .35 : 1.1 + P.sp / 1400); veil += (texty - veil) * Math.min(1, dt * 12);
    fade += ((P.inside && !formHide ? 1 : 0) - fade) * Math.min(1, dt * (formHide ? 14 : 8));
    // trail: emission follows the speed; particles curve around the singularity and fade in under a second
    var L = LEVELS[level], rate = Math.min(1, P.sp / 1500) * (dragging ? 1.6 : 1) * fade;
    var emit = rate * (L.parts / .55) * dt; if (Math.random() < emit - Math.floor(emit)) emit = Math.floor(emit) + 1; else emit = Math.floor(emit);
    for (var i = 0; i < emit && parts.length < L.parts; i++) {
      var a = P.ang + Math.PI + (Math.random() - .5) * 1.4, r0 = 12 + Math.random() * 8;
      parts.push({ x: P.x + Math.cos(a) * r0, y: P.y + Math.sin(a) * r0, vx: Math.cos(a) * 40 - P.vx * .08, vy: Math.sin(a) * 40 - P.vy * .08, life: 1,
        d: (.45 + Math.random() * .4) * (dragging ? 1.4 : 1), col: dragCol && Math.random() < .7 ? mix(dragCol, [255, 255, 255], Math.random() * .3) : spec(spin * .15 + Math.random()), sw: (Math.random() < .5 ? -1 : 1) * (1.5 + Math.random() * 2.5) });
    }
    parts = parts.filter(function (p) {
      var dx = P.x - p.x, dy = P.y - p.y, d2 = dx * dx + dy * dy + 120, d = Math.sqrt(d2), gk = 9000 / d2;
      p.vx += (dx / d * gk + (-dy / d) * p.sw * 14) * dt * 2; p.vy += (dy / d * gk + (dx / d) * p.sw * 14) * dt * 2;   // pull + swirl = curved paths
      p.vx *= Math.exp(-dt * 2.4); p.vy *= Math.exp(-dt * 2.4); p.x += p.vx * dt; p.y += p.vy * dt; p.life -= dt / p.d;
      if (Math.abs(p.x - P.x) > S / 2 - 4 || Math.abs(p.y - P.y) > S / 2 - 4) p.life -= dt * 4;   // leaving the square: fade out quickly
      return p.life > 0;
    });
    waves = waves.filter(function (w) { w.life -= dt / .62; w.r += dt * (120 + 60 * w.life); return w.life > 0; });
    flashA = Math.max(0, flashA - dt / .2);
  }
  function box() {}
  function render() {
    ox = Math.round(P.x - S / 2); oy = Math.round(P.y - S / 2);
    g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height);
    var L = LEVELS[level], a = fade;
    if (a < .01 && !parts.length && !waves.length) { cv.style.transform = 'translate3d(-9999px,0,0)'; return; }
    cv.style.transform = 'translate3d(' + ox + 'px,' + oy + 'px,0)';
    g.setTransform(dpr, 0, 0, dpr, -ox * dpr, -oy * dpr);   // draw in viewport coordinates
    var R = (targ ? 13 : 17) * (1 - flashA * .12), st = Math.min(.28, P.sp / 7000) * (targ ? .3 : 1), x = P.x, y = P.y;
    g.globalCompositeOperation = 'lighter';
    // waves
    waves.forEach(function (w) { box(w.x, w.y, w.r + 4); g.strokeStyle = rgba(mix(w.col, [255, 255, 255], .3), w.life * .55); g.lineWidth = 1.2 + w.life * 1.6; g.beginPath(); g.arc(w.x, w.y, w.r, 0, 6.283); g.stroke(); if (L.halo) { g.strokeStyle = rgba(w.col, w.life * .18); g.lineWidth = 6; g.stroke(); } });
    // particles
    parts.forEach(function (p) { box(p.x, p.y, 3); g.fillStyle = rgba(p.col, p.life * .85); var z = .8 + p.life * 1.6; g.fillRect(p.x - z / 2, p.y - z / 2, z, z); });
    if (a > .01) {
      box(x, y, R * 2.6 + 6);
      g.save(); g.translate(x, y); g.rotate(P.ang); g.scale(1 + st, 1 - st * .55);   // stretched along the motion, like a moving lens
      // soft halo
      if (L.halo && veil < .9) { var hg = g.createRadialGradient(0, 0, R * .6, 0, 0, R * 2.4); hg.addColorStop(0, rgba(dragCol || [139, 92, 246], .16 * a * (1 - veil))); hg.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = hg; g.beginPath(); g.arc(0, 0, R * 2.4, 0, 6.283); g.fill(); }
      // photon ring: SOST spectrum, rotating; brighter on the leading side (beaming)
      var segs = 28, lead = Math.min(1, P.sp / 900);
      for (var s = 0; s < segs; s++) {
        var t0 = s / segs * 6.283, t1 = (s + 1.08) / segs * 6.283, mid = (t0 + t1) / 2, beam = .55 + .45 * Math.cos(mid) * lead;
        var col = dragCol ? mix(dragCol, spec(s / segs + spin * .1), .35) : spec(s / segs + spin * .1);
        g.strokeStyle = rgba(mix(col, [255, 255, 255], targ * .25 + flashA * .5), (.75 + .25 * beam) * a * (targ ? 1 : .9)); g.lineWidth = (targ ? 2.2 : 1.7) + beam * 1.1;
        g.beginPath(); g.arc(0, 0, R, t0 + spin, t1 + spin); g.stroke();
      }
      // Einstein arc (lensing) on the leading side
      g.strokeStyle = rgba(mix(K4000, [255, 255, 255], .3), (.35 + lead * .4) * a); g.lineWidth = 1; g.beginPath(); g.arc(0, 0, R * 1.32, -.9, .9); g.stroke();
      g.restore();
      // dark core (a true black hole cannot be additive)
      g.globalCompositeOperation = 'source-over';
      var ca = a * (1 - .8 * veil), cg = g.createRadialGradient(x, y, 0, x, y, R * .82); cg.addColorStop(0, 'rgba(0,0,0,' + (.78 * ca).toFixed(3) + ')'); cg.addColorStop(.62, 'rgba(0,0,0,' + (.55 * ca).toFixed(3) + ')'); cg.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = cg; g.beginPath(); g.arc(x, y, R * .82, 0, 6.283); g.fill();
      g.globalCompositeOperation = 'lighter';
    }
    // click flash, neutral ~4000 K
    if (flashA > 0) waves.slice(-1).forEach(function (w) { box(w.x, w.y, 26); var fg = g.createRadialGradient(w.x, w.y, 0, w.x, w.y, 24); fg.addColorStop(0, rgba([255, 244, 230], flashA)); fg.addColorStop(.35, rgba(K4000, flashA * .7)); fg.addColorStop(1, rgba(K4000, 0)); g.fillStyle = fg; g.fillRect(w.x - 26, w.y - 26, 52, 52); });
    g.globalCompositeOperation = 'source-over';
  }
  function busy() { return parts.length || waves.length || flashA > 0 || Math.abs(P.tx - P.x) + Math.abs(P.ty - P.y) > .3 || P.sp > 20 || Math.abs(fade - (P.inside && !formHide ? 1 : 0)) > .01 || performance.now() - lastMove < 600; }
  function frame(t) {
    raf = 0; if (!running) return; if (!lastT) lastT = t - 16.7;
    var dtms = t - lastT; lastT = t; var dt = Math.min(1 / 30, dtms / 1000);
    watch(dtms);
    var c0 = performance.now(); step(dt); render(); var c = performance.now() - c0; perf.n++; perf.sum += c; if (c > perf.max) perf.max = c;
    if (busy() && active && !doc.hidden) raf = root.requestAnimationFrame(frame); else { running = false; lastT = 0; if (!busy()) { render(); } }
  }
  function wake() { if (!active || running) return; running = true; lastT = 0; raf = root.requestAnimationFrame(frame); }
  // the scenes come first: two slow windows step the effect down; at LITE it switches itself off for this page
  function watch(dtms) {
    if (dtms > 250) return; ft.push(dtms); if (ft.length < 60) return;
    var avg = ft.reduce(function (a, b) { return a + b; }, 0) / ft.length; ft = [];
    slowW = avg > 28 ? slowW + 1 : 0; fastW = avg < 18 ? fastW + 1 : 0;
    if (slowW >= 2) { slowW = 0; if (level !== 'lite') { level = level === 'high' ? 'balanced' : 'lite'; fit(); } }   // P0: LITE is the floor; it no longer switches itself off while the pill says ON
    else if (fastW >= 6 && level !== levelTop) { fastW = 0; level = level === 'lite' ? 'balanced' : 'high'; if (LEVELS[level].dpr > LEVELS[levelTop].dpr) level = levelTop; fit(); }
  }
  function setQ(q) {
    siteQ = q || 'auto';
    if (siteQ === 'high' || siteQ === 'balanced' || siteQ === 'lite') level = siteQ; else if (siteQ === 'auto') level = levelTop;
    if (siteQ !== 'auto') levelTop = siteQ === 'off' ? levelTop : siteQ;
    if (cv) fit(); refresh();
  }
  function refresh() {
    var v = allowed(); if (v === active) { mark(); return; }
    active = v; if (!active) { running = false; parts = []; waves = []; flashA = 0; fade = 0; if (g) { g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height); cv.style.transform = 'translate3d(-9999px,0,0)'; } } mark();
  }

  // ---- CURSOR FX ON/OFF pill ----
  // the pill shows the REAL state: ON only while the effect is drawn; PAUSED names the reason; OFF is the visitor's choice
  function why() { return RM.matches ? 'reduced motion is on in this system' : siteQ === 'off' ? 'the page effects are set to OFF' : fpsOff ? 'paused on this page' : !FINE.matches ? 'no mouse pointer' : ''; }
  function mark() { if (!btn) return; var paused = on && !active;
    btn.textContent = 'CURSOR FX ' + (!on ? 'OFF' : paused ? 'PAUSED' : 'ON'); btn.setAttribute('aria-pressed', String(on));
    btn.title = paused ? 'Gravitational cursor paused: ' + why() + '. Click to turn it off.' : on ? 'Gravitational cursor effect · click to turn off' : 'Gravitational cursor effect · click to turn on';
    btn.setAttribute('aria-label', btn.title); btn.classList.toggle('dim', paused); }
  function placeBtn() {
    if (!btn) return; var ua = doc.querySelector('.ua .ua-fab'), b = 12, l = 12;
    if (ua) { var r = ua.getBoundingClientRect(); if (r.height) { b = Math.round(root.innerHeight - r.top + 8); l = Math.round(r.left); } }
    btn.style.bottom = b + 'px'; btn.style.left = l + 'px';
  }
  function makeBtn() {
    btn = doc.createElement('button'); btn.type = 'button'; btn.id = 'sostCursorBtn';
    btn.style.cssText = 'position:fixed;z-index:9991;left:12px;bottom:12px;font:600 9.5px/1 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:.14em;' +
      'color:#cbd5e1;background:#05060acc;border:1px solid #ffffff22;border-radius:999px;padding:6px 10px;cursor:pointer;opacity:.55;transition:opacity .2s,border-color .2s';
    btn.addEventListener('mouseenter', function () { btn.style.opacity = '1'; }); btn.addEventListener('mouseleave', function () { btn.style.opacity = '.55'; });
    btn.addEventListener('focus', function () { btn.style.opacity = '1'; }); btn.addEventListener('blur', function () { btn.style.opacity = '.55'; });
    btn.addEventListener('click', function () { on = !on; pref.on = on; lsSet(pref); if (on) fpsOff = false; refresh(); });
    doc.body.appendChild(btn); mark(); placeBtn();
    [600, 1500, 3500].forEach(function (t) { setTimeout(placeBtn, t); });
    try { new MutationObserver(placeBtn).observe(doc.body, { childList: true }); } catch (e) {}
  }

  function boot() {
    if (!FINE.matches) { FINE.addEventListener && FINE.addEventListener('change', function () { if (FINE.matches && !cv) boot(); }); return; }   // touch-only: nothing at all
    mount(); makeBtn();
    var qb = doc.querySelector('.qual button[aria-pressed="true"]'); if (qb) siteQ = qb.getAttribute('data-q') || 'auto';
    doc.addEventListener('click', function (e) { var b = e.target.closest && e.target.closest('.qual button[data-q]'); if (b) setQ(b.getAttribute('data-q')); }, { passive: true });
    doc.addEventListener('pointermove', onMove, { passive: true, capture: true });
    doc.addEventListener('pointerdown', onDown, { passive: true, capture: true });
    doc.addEventListener('mouseout', function (e) { if (!e.relatedTarget) { P.inside = false; wake(); } }, { passive: true });
    doc.addEventListener('focusin', function () { if (focusedForm()) { formHide = 1; wake(); } }, { passive: true });
    doc.addEventListener('focusout', function () { setTimeout(function () { if (!focusedForm()) { formHide = 0; wake(); } }, 0); }, { passive: true });
    doc.addEventListener('keydown', function () { if (focusedForm()) { formHide = 1; wake(); } }, { passive: true });
    root.addEventListener('resize', function () { if (cv) fit(); placeBtn(); }, { passive: true });
    doc.addEventListener('visibilitychange', function () { if (!doc.hidden) wake(); });
    if (RM.addEventListener) RM.addEventListener('change', refresh);
    // Home cubes: colour and a longer trail while one is dragged
    root.addEventListener('sost:cubes', function (e) { var d = e.detail || {}; if (d.type === 'grab') { dragging = true; dragCol = d.col || null; } else if (d.type === 'drop') { dragging = false; dragCol = null; } else if (d.type === 'snap' && active) { spray(d.x, d.y, 10, 160, false); wake(); } });
    refresh();
  }
  root.SOSTCursor = {
    state: function () { return { on: on, active: active, running: running, level: level, siteQ: siteQ, fpsOff: fpsOff, fine: FINE.matches, rm: RM.matches, parts: parts.length, waves: waves.length, fade: +fade.toFixed(2), targ: targ, veil: +veil.toFixed(2), formHide: formHide, dragging: dragging, x: Math.round(P.x), y: Math.round(P.y) }; },
    perf: function (reset) { var r = { frames: perf.n, avg_ms: perf.n ? +(perf.sum / perf.n).toFixed(3) : 0, max_ms: +perf.max.toFixed(2) }; if (reset) perf = { n: 0, sum: 0, max: 0 }; return r; },
    set: function (v) { on = !!v; pref.on = on; lsSet(pref); if (on) fpsOff = false; refresh(); }
  };
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot); else boot();
})(window);

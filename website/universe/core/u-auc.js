/* Autonomous Useful Compute — conceptual animation for the Home section (27-Nov-2026).
 * Conceptual only: no live data, no job counts, no prices. Starts when the section is near the viewport, pauses when it
 * leaves or the tab is hidden, caps DPR at 2, and draws a single still frame under prefers-reduced-motion. No dependencies. */
(function () {
  'use strict';
  var root = document.getElementById('auc');
  if (!root || root.__aucInit) return;
  root.__aucInit = true;

  var PH = [
    { k: 'REQUEST', t: 'A company or researcher submits a computational job, its input data and the price it is willing to pay.' },
    { k: 'MATCH',   t: 'The market selects compatible CPU / GPU providers whose capacity and asking price fit the request.' },
    { k: 'EXECUTE', t: 'The job is split into work units and independent computers execute them.' },
    { k: 'VERIFY',  t: 'Results are checked objectively — recomputation, proofs or redundancy — wherever a reliable method exists.' },
    { k: 'SETTLE',  t: 'Verified results return to the customer and SOST payments are released to providers under the contract rules.' }
  ];
  var PDUR = 2600;                                   // ms per phase
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var stage = root.querySelector('.auc-stage'), cv = stage.querySelector('canvas'), ctx = cv.getContext('2d');
  var steps = [].slice.call(root.querySelectorAll('.auc-step'));
  var exK = root.querySelector('[data-auc-k]'), exT = root.querySelector('[data-auc-t]'), play = root.querySelector('.auc-play');

  /* ---------- state ---------- */
  var W = 0, H = 0, DPR = 1, stars = [], nodes = [], cust = [];
  var phase = 0, t0 = 0, auto = !reduce, running = false, raf = 0, rot = 0, lastNow = 0, sel = [], ci = 0;
  var NP = 10;
  for (var i = 0; i < NP; i++) nodes.push({ a: i / NP * Math.PI * 2 + (i % 2) * .18, gpu: i % 3 !== 1, lift: ((i * 37) % 7 - 3) * .03 });

  function rnd(seed) { var x = Math.sin(seed * 9301 + 49297) * 233280; return x - Math.floor(x); }
  function pickCycle(n) {
    ci = n % 2; sel = []; var start = (n * 3) % NP;
    for (var j = 0; j < 3; j++) sel.push((start + j * 3 + (n % 2)) % NP);
  }
  var cycle = 0; pickCycle(0);

  function size() {
    var r = stage.getBoundingClientRect(); DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = Math.max(1, r.width); H = Math.max(1, r.height);
    cv.width = Math.round(W * DPR); cv.height = Math.round(H * DPR); ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    stars = []; var n = Math.round(W * H / 2600);
    for (var s = 0; s < n; s++) stars.push({ x: rnd(s) * W, y: rnd(s + 99) * H, r: rnd(s + 7) * 1.1 + .2, a: rnd(s + 3) * .5 + .1 });
    cust = [{ x: W * .1, y: H * .78 }, { x: W * .1, y: H * .22 }];
  }

  /* ---------- geometry ---------- */
  function proj(nd) {
    var R = Math.min(W * .40, H * .62), a = nd.a + rot, tilt = .36;
    var x = Math.cos(a) * R, z = Math.sin(a) * R, y = nd.lift * R;
    var y2 = y * Math.cos(tilt) - z * Math.sin(tilt), z2 = y * Math.sin(tilt) + z * Math.cos(tilt);
    var f = R * 3.2, s = f / (f + z2);
    return { x: W / 2 + x * s, y: H / 2 + y2 * s * .9, s: s, z: z2 };
  }
  function ease(t) { return t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }
  function bez(a, b, t, bend) {
    var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - (bend || 0);
    var u = 1 - t; return { x: u * u * a.x + 2 * u * t * mx + t * t * b.x, y: u * u * a.y + 2 * u * t * my + t * t * b.y };
  }
  function glow(x, y, r, c, a) {
    var g = ctx.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, c.replace('A', a)); g.addColorStop(1, c.replace('A', 0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  }
  var CY = 'rgba(94,234,212,A)', BL = 'rgba(96,165,250,A)', VI = 'rgba(167,139,250,A)', GO = 'rgba(250,204,21,A)', GR = 'rgba(74,222,128,A)';

  /* ---------- drawing ---------- */
  function drawCore(now, pulse, tint) {
    var cx = W / 2, cy = H / 2, R = Math.min(W, H) * .15;
    glow(cx, cy, R * 3.1, tint || BL, .16 + pulse * .22);
    var g = ctx.createRadialGradient(cx - R * .3, cy - R * .35, R * .1, cx, cy, R);
    g.addColorStop(0, 'rgba(30,58,110,1)'); g.addColorStop(.7, 'rgba(12,26,58,1)'); g.addColorStop(1, 'rgba(8,16,36,1)');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();
    // latitude rings (pseudo-3D)
    ctx.lineWidth = 1;
    for (var k = 0; k < 3; k++) {
      var ph = now / 4200 + k * 2.1;
      ctx.strokeStyle = 'rgba(94,234,212,' + (.18 + .1 * Math.sin(ph)) + ')';
      ctx.beginPath(); ctx.ellipse(cx, cy, R * .98, R * Math.abs(Math.sin(ph)) * .98 + .5, k * 1.05, 0, Math.PI * 2); ctx.stroke();
    }
    var lg = ctx.createLinearGradient(cx - R, cy - R, cx + R, cy + R);
    lg.addColorStop(0, '#5eead4'); lg.addColorStop(.5, '#60a5fa'); lg.addColorStop(1, '#a78bfa');
    ctx.strokeStyle = lg; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
    return R;
  }
  function drawNode(p, nd, on, prog) {
    var r = (nd.gpu ? 9 : 7.5) * p.s * Math.max(.8, Math.min(W, H) / 520);
    glow(p.x, p.y, r * 3.2, on ? CY : BL, on ? .55 : .14 * p.s);
    ctx.fillStyle = on ? 'rgba(8,30,40,1)' : 'rgba(10,18,36,1)';
    ctx.strokeStyle = on ? 'rgba(94,234,212,.95)' : 'rgba(96,165,250,' + (.35 + .25 * p.s) + ')'; ctx.lineWidth = on ? 2 : 1.2;
    ctx.beginPath();
    if (nd.gpu) { if (ctx.roundRect) ctx.roundRect(p.x - r, p.y - r, r * 2, r * 2, r * .35); else ctx.rect(p.x - r, p.y - r, r * 2, r * 2); }
    else ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = on ? '#5eead4' : 'rgba(148,163,184,.6)';
    ctx.beginPath(); ctx.arc(p.x, p.y, r * .32, 0, Math.PI * 2); ctx.fill();
    if (prog > 0) { ctx.strokeStyle = 'rgba(94,234,212,.9)'; ctx.lineWidth = 2.2;
      ctx.beginPath(); ctx.arc(p.x, p.y, r * 1.75, -Math.PI / 2, -Math.PI / 2 + prog * Math.PI * 2); ctx.stroke(); }
  }
  function drawCust(c, on) {
    var r = Math.max(8, Math.min(W, H) * .018);
    glow(c.x, c.y, r * 3, VI, on ? .5 : .15);
    ctx.save(); ctx.translate(c.x, c.y); ctx.rotate(Math.PI / 4);
    ctx.fillStyle = 'rgba(20,14,40,1)'; ctx.strokeStyle = on ? 'rgba(196,181,253,.95)' : 'rgba(167,139,250,.45)'; ctx.lineWidth = 1.6;
    ctx.fillRect(-r * .75, -r * .75, r * 1.5, r * 1.5); ctx.strokeRect(-r * .75, -r * .75, r * 1.5, r * 1.5); ctx.restore();
  }
  function packet(a, b, t, col, size, bend) {
    var p = bez(a, b, ease(Math.max(0, Math.min(1, t))), bend);
    glow(p.x, p.y, size * 4, col, .85); ctx.fillStyle = col.replace('A', 1); ctx.beginPath(); ctx.arc(p.x, p.y, size, 0, Math.PI * 2); ctx.fill();
  }
  function link(a, b, alpha, col, bend) {
    ctx.strokeStyle = (col || CY).replace('A', alpha); ctx.lineWidth = 1; ctx.setLineDash([3, 6]);
    var m = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - (bend || 0) };
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(m.x, m.y, b.x, b.y); ctx.stroke(); ctx.setLineDash([]);
  }

  function frame(now, ph, t) {
    ctx.clearRect(0, 0, W, H);
    for (var s = 0; s < stars.length; s++) { var st = stars[s]; ctx.fillStyle = 'rgba(203,213,225,' + st.a * (.75 + .25 * Math.sin(now / 1400 + s)) + ')'; ctx.fillRect(st.x, st.y, st.r, st.r); }
    var C = { x: W / 2, y: H / 2 };
    // orbit guide
    var R = Math.min(W * .40, H * .62);
    ctx.strokeStyle = 'rgba(96,165,250,.13)'; ctx.lineWidth = 1; ctx.setLineDash([5, 8]);
    ctx.beginPath(); ctx.ellipse(C.x, C.y, R * .98, R * .33, 0, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
    var P = nodes.map(proj), cu = cust[ci];
    var isSel = function (i) { return sel.indexOf(i) >= 0; };
    var showSel = ph >= 1;
    // links core <-> nodes
    for (var i = 0; i < NP; i++) {
      var a = .08 + .07 * P[i].s;
      if (ph === 1) { var reveal = Math.min(1, t * 1.6 - i / NP * .6); if (reveal > 0) a += (isSel(i) ? .55 : .12) * reveal; }
      else if (showSel && isSel(i)) a += .4;
      link(C, P[i], Math.min(.85, a), CY, 0);
    }
    // customers + their link
    for (var c = 0; c < cust.length; c++) { link(cust[c], C, c === ci ? .35 : .1, VI, -H * .06); }
    // back nodes
    var order = P.map(function (p, i) { return i; }).sort(function (x, y) { return P[y].z - P[x].z; });
    function nodesPass(front) {
      order.forEach(function (i) {
        if ((P[i].z < 0) !== front) return;
        var on = showSel && isSel(i), prog = 0;
        if (ph === 2 && on) prog = Math.max(0, (t - .45) / .55);
        if (ph > 2 && on) prog = 1;
        drawNode(P[i], nodes[i], on, prog);
      });
    }
    nodesPass(false);
    var pulse = 0, tint = BL;
    if (ph === 0) { pulse = t > .85 ? (t - .85) / .15 : 0; tint = VI; }
    if (ph === 3 && t > .6) { pulse = (t - .6) / .4; tint = GR; }
    if (ph === 4) { pulse = 1 - t; tint = GO; }
    var cr = drawCore(now, pulse, tint);
    if (ph === 3 && t > .6) {           // verification sweep
      ctx.strokeStyle = 'rgba(74,222,128,.9)'; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(C.x, C.y, cr * 1.18, -Math.PI / 2, -Math.PI / 2 + ease((t - .6) / .4) * Math.PI * 2); ctx.stroke();
    }
    nodesPass(true);
    for (c = 0; c < cust.length; c++) drawCust(cust[c], c === ci && (ph === 0 || ph === 4));
    // packets
    if (ph === 0) packet(cu, C, t / .9, VI, 4.5, -H * .06);
    if (ph === 2) sel.forEach(function (i, k) { packet(C, P[i], (t - k * .06) / .42, BL, 3.4, 0); });
    if (ph === 3) sel.forEach(function (i, k) { packet(P[i], C, (t - k * .05) / .55, CY, 3.4, 0); });
    if (ph === 4) {
      sel.forEach(function (i, k) { for (var q = 0; q < 3; q++) packet(C, P[i], (t - q * .12 - k * .04) / .6, GO, 2.6, 0); });
      packet(C, cu, (t - .1) / .75, CY, 4.5, H * .06);
    }
  }

  /* ---------- control ---------- */
  function setPhase(p, user) {
    phase = p; t0 = performance.now();
    steps.forEach(function (b, i) { b.setAttribute('aria-pressed', i === p ? 'true' : 'false'); });
    exK.textContent = PH[p].k; exT.textContent = PH[p].t;
    if (user) { auto = false; if (play) { play.hidden = false; play.textContent = '▶ Play cycle'; } }
    if (reduce || !running) frame(performance.now(), phase, .72);
  }
  steps.forEach(function (b, i) { b.addEventListener('click', function () { setPhase(i, true); }); });
  if (play) play.addEventListener('click', function () {
    auto = !auto; play.textContent = auto ? '❚❚ Pause' : '▶ Play cycle';
    if (auto) { t0 = performance.now(); start(); }
  });

  function loop(now) {
    if (!running) return;
    var dt = lastNow ? Math.min(64, now - lastNow) : 16; lastNow = now; rot += dt * .000045;
    var t = (now - t0) / PDUR;
    if (t >= 1) {
      if (auto) { var np = (phase + 1) % 5; if (np === 0) pickCycle(++cycle); setPhase(np); t = 0; }
      else { t0 = now; t = 0; }
    }
    frame(now, phase, Math.min(1, t));
    raf = requestAnimationFrame(loop);
  }
  function start() { if (running || reduce) return; running = true; stage.classList.add('live'); lastNow = 0; raf = requestAnimationFrame(loop); }
  function stop() { running = false; cancelAnimationFrame(raf); }

  size(); stage.classList.add('live'); setPhase(0);
  if (reduce) { if (play) play.hidden = true; frame(0, 0, .72); }
  window.addEventListener('resize', function () { size(); if (!running) frame(performance.now(), phase, .72); }, { passive: true });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting && !document.hidden) start(); else stop(); }); },
      { rootMargin: '120px 0px' }).observe(stage);
  } else start();
  document.addEventListener('visibilitychange', function () { if (document.hidden) stop(); else if (stage.getBoundingClientRect().top < innerHeight) start(); });

  /* ---------- journeys (I NEED / I PROVIDE) ---------- */
  var tabs = [].slice.call(root.querySelectorAll('.auc-tab'));
  tabs.forEach(function (tb) {
    tb.addEventListener('click', function () {
      tabs.forEach(function (x) { var on = x === tb; x.setAttribute('aria-selected', on ? 'true' : 'false'); x.tabIndex = on ? 0 : -1;
        document.getElementById(x.getAttribute('aria-controls')).hidden = !on; });
    });
    tb.addEventListener('keydown', function (e) {
      var i = tabs.indexOf(tb), n = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (n) { e.preventDefault(); var nx = tabs[(i + n + tabs.length) % tabs.length]; nx.focus(); nx.click(); }
    });
  });
})();

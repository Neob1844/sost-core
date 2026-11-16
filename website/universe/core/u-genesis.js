/* SOST Universe — Matrix Genesis (Phase 4). Canvas 2D, runs from the first paint, ~2.0 s in total, never blocks input.
 *
 *  0.00–0.45 s  red Matrix rain (official #fb010d / #cc0000, white heads)
 *  0.35–0.90 s  every glyph disintegrates into particles that keep the rain's momentum (one particle per glyph cell)
 *  0.75–1.60 s  the particles leave red for the full official spectrum and converge onto the Convergence Core ring
 *  1.55–2.00 s  chromatic shock wave; SOST appears in the real wordmark font (Goldman 700, 'SOST Wordmark'); fade out
 *
 * The WebGL core (u-core.js) boots in the background and takes over the same ring geometry when ready; if it is not
 * ready (slow GPU, no WebGL2) the static poster underneath is what remains. First visit only (localStorage, try/catch);
 * skippable (Esc, button, wheel, touch, any key/click). Never runs with prefers-reduced-motion.
 * API: SOSTU.genesis.play({ canvas, center:fn->{x,y,a,b}, onDone:fn, onPhase:fn }) -> { skip }
 */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  var SPEC = ['#8b5cf6', '#e879f9', '#3b82f6', '#22d3ee', '#a3e635', '#facc15', '#fb923c'];
  var GLY = 'アイウエオカキクケコサシスセソ0123456789ABCDEFXYZ$#@&*+=<>'.split('');
  var TOTAL = 2.0;
  function ease(x) { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); }
  function mix(a, b, k) { return a + (b - a) * k; }
  function hex(h) { var n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
  var SP = SPEC.map(hex), RED = hex('#fb010d'), DRED = hex('#cc0000');

  function play(o) {
    // CPU-backed 2D context: avoids a main-thread stall while the GPU process creates an accelerated canvas (measured 1.5 s on
    // a real GPU under WSLg); 2,800 rects per frame are cheap on the CPU rasteriser.
    var cv = o.canvas, ctx = cv.getContext('2d', { willReadFrequently: true }), W = innerWidth, H = innerHeight, dpr = Math.min(root.devicePixelRatio || 1, 1.5);
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var COLW = W < 600 ? 14 : 18, cols = Math.floor(W / COLW), t0 = performance.now(), raf = 0, done = false, perf = { frames: 0, longest: 0, last: t0 };
    var c = o.center(); // core centre + ring semi-axes in CSS px
    // particles: one per glyph cell of the rain trails (≤ 2,800)
    var P = [], per = Math.max(3, Math.min(9, Math.floor(2800 / Math.max(1, cols))));
    for (var col = 0; col < cols; col++) {
      var spd = .25 + .35 * ((col * .6180339) % 1), ph = (col * .131) % 1;
      for (var k = 0; k < per; k++) {
        var i = P.length, band = i % 7, th = (i / 2800) * Math.PI * 2 * 7 + col * .37;
        P.push({ col: col, k: k, spd: spd, ph: ph, band: band, th: th, r: 1 + .09 * Math.sin(i * 1.7), rel: .35 + .5 * ((i * .618) % 1) * .55, vx: 0, vy: 0, x: 0, y: 0 });
      }
    }
    var font = '700 ' + Math.round(Math.min(W * .16, 170)) + "px 'SOST Wordmark'";
    function frame(now) {
      raf = 0; if (done) return;
      var dt = now - perf.last; perf.last = now; perf.frames++; if (perf.frames > 3 && dt > perf.longest) perf.longest = dt;
      var t = (now - t0) / 1000;
      if (t >= TOTAL) return finish();
      if (o.onPhase) o.onPhase(t < .9 ? 0 : t < 1.6 ? 1 : 2);
      ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
      var rainA = t < .45 ? 1 : Math.max(0, 1 - (t - .45) / .45);
      // ---- rain glyphs (fading out as they disintegrate)
      if (rainA > 0) {
        ctx.font = COLW + 'px monospace';
        for (var cc = 0; cc < cols; cc++) {
          var sp = .25 + .35 * ((cc * .6180339) % 1), fy = ((cc * .131 + t * sp * 1.6) % 1), x = (cc + .5) * W / cols, y = fy * H;
          for (var kk = 0; kk < 7; kk++) {
            var yy = y - kk * COLW; if (yy < 0) break;
            ctx.globalAlpha = rainA * (1 - kk / 7);
            ctx.fillStyle = kk === 0 ? '#ffffff' : kk < 3 ? '#fb010d' : kk < 5 ? '#cc0000' : '#880000';
            ctx.fillText(GLY[(cc * 7 + kk * 13 + Math.floor(t * 14)) % GLY.length], x - COLW / 3, yy);
          }
        }
      }
      // ---- particles
      ctx.globalCompositeOperation = 'lighter';
      var conv = ease((t - .75) / .85), spec = ease((t - .7) / .6), fade = t > 1.75 ? Math.max(0, 1 - (t - 1.75) / .25) : 1;
      for (var i = 0; i < P.length; i++) {
        var p = P[i]; if (t < p.rel) continue;
        if (!p.born) {             // born at its glyph cell, inheriting the rain's downward speed
          var fy0 = ((p.col * .131 + p.rel * p.spd * 1.6) % 1); p.x = (p.col + .5) * W / cols; p.y = fy0 * H - p.k * COLW; p.vy = p.spd * H * 1.6 * .016; p.vx = 0; p.born = 1;
        }
        // chaos: advected by a smooth swirl field (sin/cos stream function, no randomness per frame)
        var fx = Math.cos(p.y * .011 + t * 1.3) + .6 * Math.sin((p.x + p.y) * .007 - t), fyv = Math.sin(p.x * .009 - t * 1.1) - .5 * Math.cos((p.x - p.y) * .006 + t * .7);
        p.vx = p.vx * .92 + fx * .9; p.vy = p.vy * .92 + fyv * .9; p.x += p.vx; p.y += p.vy;
        // convergence onto the ring (rotating), staggered by particle
        var kq = ease((conv - (i % 5) * .04) / .8);
        var ang = p.th + t * .9, tx = c.x + Math.cos(ang) * c.a * p.r, ty = c.y + Math.sin(ang) * c.b * p.r;
        var X = mix(p.x, tx, kq), Y = mix(p.y, ty, kq);
        if (kq > 0.98) { p.x = X; p.y = Y; }
        var s = SP[p.band], base = (i % 3 === 0) ? DRED : RED, cr = mix(base[0], s[0], spec), cg = mix(base[1], s[1], spec), cb = mix(base[2], s[2], spec);
        ctx.globalAlpha = .75 * fade; ctx.fillStyle = 'rgb(' + (cr | 0) + ',' + (cg | 0) + ',' + (cb | 0) + ')';
        var sz = mix(2.2, 1.6, kq); ctx.fillRect(X - sz / 2, Y - sz / 2, sz, sz);
      }
      // ---- core: dark centre + red rim, then the chromatic shock wave and the wordmark
      var coreA = ease((t - .9) / .6) * fade;
      if (coreA > 0) {
        ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = coreA; ctx.fillStyle = '#000';
        ctx.beginPath(); ctx.ellipse(c.x, c.y, c.a * .36, c.a * .36, 0, 0, 7); ctx.fill();
        ctx.globalCompositeOperation = 'lighter'; ctx.strokeStyle = '#fb010d'; ctx.lineWidth = 3; ctx.beginPath(); ctx.ellipse(c.x, c.y, c.a * .37, c.a * .37, 0, 0, 7); ctx.stroke();
      }
      if (t > 1.55) {
        var w = (t - 1.55) / .45, R = c.a * (.37 + w * 2.2);
        ctx.globalAlpha = (1 - w) * .9; ctx.lineWidth = 2;
        var g = ctx.createLinearGradient(c.x - R, c.y, c.x + R, c.y); SPEC.forEach(function (h, j) { g.addColorStop(j / 6, h); }); ctx.strokeStyle = g;
        ctx.beginPath(); ctx.ellipse(c.x, c.y, R, R * (c.b / c.a), 0, 0, 7); ctx.stroke();
        ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = Math.min(1, (t - 1.55) / .15) * fade;
        ctx.font = font; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#fff';
        ctx.shadowColor = '#fb010d'; ctx.shadowBlur = 24; ctx.fillText('SOST', c.x, c.y); ctx.shadowBlur = 0; ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';
      }
      raf = requestAnimationFrame(frame);
    }
    function finish() {
      if (done) return; done = true; if (raf) cancelAnimationFrame(raf);
      try { localStorage.setItem('sostu_genesis_seen', '1'); } catch (e) {}
      cv.width = cv.height = 0; cv.remove(); perf.totalMs = Math.round(performance.now() - t0); U.genesis.perf = perf;
      if (o.onDone) o.onDone(perf);
    }
    raf = requestAnimationFrame(frame);
    return { skip: finish, perf: perf };
  }
  function seen() { try { return localStorage.getItem('sostu_genesis_seen') === '1'; } catch (e) { return false; } }
  U.genesis = { play: play, seen: seen, TOTAL: TOTAL };
})(window);

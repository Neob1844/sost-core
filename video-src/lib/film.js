/* SOST films (2026-10) — scene engine for render2.js.
 *
 * A film page defines window.FILM = { title, scenes:[{ name, dur, pal, acc, corner, draw(t) }] }
 * and includes this file. ?scene=i selects the scene; window.frame(t) redraws it at local time
 * t (seconds) as a pure function of t: the ambient layer, the corner mark's 2.4 s pulse, the
 * chapter rail and the scene's own HTML. No CSS animations, no timers, no randomness.
 */
(function () {
  'use strict';
  var F = window.F = {};
  F.cl = function (x, a, b) { return Math.max(a, Math.min(b, x)); };
  F.p = function (t, a, b) { return F.cl((t - a) / (b - a), 0, 1); };            // linear 0..1
  F.eo = function (x) { return 1 - Math.pow(1 - x, 3); };                          // ease-out cubic
  F.eio = function (x) { return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  F.back = function (x) { var c = 1.4; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
  F.k = function (t, a, d) { return F.eo(F.p(t, a, a + (d || .8))); };              // eased reveal 0..1
  /* reveal style: fade + rise (+ optional scale) */
  F.in = function (t, a, d, dy, sc) {
    var k = F.k(t, a, d), s = 'opacity:' + k.toFixed(3) + ';transform:translateY(' + ((1 - k) * (dy == null ? 34 : dy)).toFixed(1) + 'px)';
    if (sc) s += ' scale(' + (sc + (1 - sc) * F.eo(F.p(t, a, a + (d || .8)))).toFixed(4) + ')';
    return s;
  };
  F.fromL = function (t, a, d, dx) { var k = F.k(t, a, d); return 'opacity:' + k.toFixed(3) + ';transform:translateX(' + (-(1 - k) * (dx || 60)).toFixed(1) + 'px)'; };
  F.fromR = function (t, a, d, dx) { var k = F.k(t, a, d); return 'opacity:' + k.toFixed(3) + ';transform:translateX(' + ((1 - k) * (dx || 60)).toFixed(1) + 'px)'; };
  F.num = function (v, dec) { return Number(v).toLocaleString('en-US', { minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0 }); };
  F.count = function (t, a, d, to, dec) { return F.num(to * F.eio(F.p(t, a, a + d)), dec); };
  F.type = function (t, a, text, cps) { var n = Math.floor(F.cl((t - a) * (cps || 30), 0, text.length)); return text.slice(0, n); };
  /* Ken Burns for a photo: slow zoom + drift over the whole scene */
  F.kb = function (t, dur, z0, z1, dx, dy) {
    var k = F.eio(F.p(t, 0, dur)), z = z0 + (z1 - z0) * k;
    return 'transform:scale(' + z.toFixed(4) + ') translate(' + ((dx || 0) * k).toFixed(2) + '%,' + ((dy || 0) * k).toFixed(2) + '%)';
  };
  F.pulse = function (t, period) { return 0.5 - 0.5 * Math.cos(2 * Math.PI * t / (period || 2.4)); };
  F.glow = function (el, t) {
    var k = F.pulse(t), e = 0.62 + 0.38 * k;
    el.style.filter =
      'drop-shadow(0 0 ' + (12 + 8 * k).toFixed(1) + 'px rgba(255,16,36,' + (0.55 * e).toFixed(3) + ')) ' +
      'drop-shadow(0 0 ' + (34 + 18 * k).toFixed(1) + 'px rgba(255,16,36,' + (0.40 * e).toFixed(3) + ')) ' +
      'drop-shadow(0 0 ' + (78 + 34 * k).toFixed(1) + 'px rgba(255,16,36,' + (0.24 * e).toFixed(3) + '))';
  };

  var q = new URLSearchParams(location.search);
  var idx = parseInt(q.get('scene') || '0', 10);

  function imgsReady(root) {
    var imgs = Array.prototype.slice.call(root.querySelectorAll('img'));
    return Promise.all(imgs.map(function (im) { return im.decode ? im.decode().catch(function () {}) : Promise.resolve(); }));
  }

  window.frame = function (t) {
    var film = window.FILM, s = film.scenes[idx];
    document.documentElement.style.setProperty('--acc', s.acc || '#FF3D4F');
    var sc = document.getElementById('sc');
    sc.innerHTML = s.draw(t);
    GeaAmbient.paint(document.getElementById('amb'), t, s.pal || 'red', { n: s.particles || 150, grid: s.grid !== false });
    var cn = document.getElementById('corner');
    if (s.corner === false) cn.style.display = 'none'; else { cn.style.display = ''; F.glow(document.getElementById('cmk'), t); }
    var mk = sc.querySelector('.mark'); if (mk) F.glow(mk, t);
    var rail = document.getElementById('rail');
    if (s.rail === false) rail.style.display = 'none';
    else {
      rail.style.display = '';
      var n = film.scenes.filter(function (x) { return x.rail !== false; }).length;
      var pos = film.scenes.slice(0, idx + 1).filter(function (x) { return x.rail !== false; }).length;
      rail.style.opacity = F.k(t, .3, .8).toFixed(3);
      rail.innerHTML = '<span>' + String(pos).padStart(2, '0') + ' / ' + String(n).padStart(2, '0') + '</span><span class="bar"><span style="width:' +
        (100 * (pos - 1 + F.p(t, 0, s.dur)) / n).toFixed(2) + '%"></span></span><span>' + (s.name || '') + '</span>';
    }
    return imgsReady(sc);
  };
  window.addEventListener('load', function () { window.frame(parseFloat(q.get('t') || '0')); document.documentElement.setAttribute('data-ready', '1'); });
})();

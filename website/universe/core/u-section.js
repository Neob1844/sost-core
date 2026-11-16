/* SOST Universe — section pages helper (DIRECTIVA 4D §5).
 * SOSTU.section.scene(canvas, draw(ctx, w, h, t, dt), opts) runs a Canvas 2D scene with: DPR cap 2, resize, pause when the tab is hidden
 * or the hero is off screen, one static frame under prefers-reduced-motion, and a perf record (frames, worst frame).
 * SOSTU.section.links(el, sectionId, overrides) renders the section's items from the ONE nav map (core/u-nav.js?v=rs20261112g), so links and
 * status badges cannot drift from the header and the footer directory. */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  var RM = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var perf = { frames: 0, worstMs: 0, startedAt: null };
  function scene(cv, draw, o) {
    o = o || {}; var ctx = null, w = 0, h = 0, raf = 0, on = true, vis = true, last = 0, t0 = performance.now();
    function size() { var d = Math.min(root.devicePixelRatio || 1, 2), r = cv.getBoundingClientRect(); w = r.width; h = r.height; cv.width = Math.round(w * d); cv.height = Math.round(h * d); if (ctx) ctx.setTransform(d, 0, 0, d, 0, 0); if (o.resize) o.resize(w, h); }
    function frame(now) {
      raf = 0; if (!ctx) { ctx = cv.getContext('2d', { willReadFrequently: true }); size(); }   // CPU-backed 2D, created after the first paint: no GPU canvas start-up stall (measured 1.6–2 s on WSLg)
      var a = performance.now(), dt = Math.min(64, last ? now - last : 16); last = now;
      draw(ctx, w, h, (now - t0) / 1000, dt / 1000); perf.frames++; var ms = performance.now() - a; if (ms > perf.worstMs) perf.worstMs = +ms.toFixed(2);
      if (!RM && on && vis && !document.hidden) raf = requestAnimationFrame(frame);
    }
    function go() { if (!raf) { last = 0; raf = requestAnimationFrame(frame); } }
    perf.startedAt = Math.round(performance.now());
    var rz = 0; addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { size(); if (RM) go(); }, 120); });
    document.addEventListener('visibilitychange', function () { if (!document.hidden && !RM) go(); });
    if (root.IntersectionObserver) new IntersectionObserver(function (es) { vis = es[0].isIntersecting; if (vis && !RM) go(); }).observe(cv);
    // start after the first paint so the hero text is the LCP and the scene never delays it
    requestAnimationFrame(function () { setTimeout(go, 60); });
    return { stop: function () { on = false; }, redraw: go };
  }
  function esc(x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function links(el, id, ov) {
    ov = ov || {}; var S = (U.nav && U.nav.MAP || []).filter(function (s) { return s.id === id; })[0]; if (!S) return;
    el.innerHTML = S.items.filter(function (it) { return !ov.skip || ov.skip.indexOf(it[1]) < 0; }).map(function (it) {
      var o = ov[it[1]] || {}, st = o.status !== undefined ? o.status : it[2], lab = o.label || (st && U.nav.STATUS[st] ? U.nav.STATUS[st].label : st === 'notactive' ? 'NOT ACTIVE' : '');
      return '<li><a href="' + esc(it[1]) + '">' + (lab ? '<i class="st-badge st-' + esc(st) + '">' + esc(lab) + '</i>' : '') + '<b>' + esc(it[0]) + '</b><span>' + esc(o.desc || '') + '</span></a></li>';
    }).join('');
  }
  U.section = { scene: scene, links: links, perf: perf, RM: RM, esc: esc };
})(window);

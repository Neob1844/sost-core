/* SOST Universe — Phase 3 shared UI helpers (status bar, provenance labels, copy, formatting, mobile nav). */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  var LABEL = { verified: 'VERIFIED ON-CHAIN', observed: 'OBSERVED · PUBLIC NODE', estimated: 'ESTIMATE', historical: 'HISTORICAL',
    simulated: 'SIMULATED', projected: 'PROJECTED', unavailable: 'UNAVAILABLE' };
  function esc(x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function pv(kind, text) { return '<span class="pv ' + kind + '">' + esc(text || LABEL[kind]) + '</span>'; }
  var STATUS = { live: 'LIVE', stale: 'STALE', offline: 'OFFLINE', fixture: 'FIXTURE', loading: 'LOADING' };
  function st(s) { return '<span class="st ' + s + '">' + STATUS[s] + '</span>'; }
  function utc(t) { return t ? new Date(t * 1000).toISOString().replace('T', ' ').slice(0, 19) + ' UTC' : '—'; }
  function hm(ms) { return new Date(ms).toISOString().slice(11, 19) + ' UTC'; }
  function dur(s) { if (s == null) return '—'; s = Math.round(s); if (s < 60) return s + ' s'; var m = Math.floor(s / 60); if (m < 60) return m + ' min ' + (s % 60) + ' s'; var h = Math.floor(m / 60); return h + ' h ' + (m % 60) + ' min'; }
  function num(n, d) { return n == null ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); }
  function short(a, k) { k = k || 8; return a && a.length > 2 * k + 4 ? a.slice(0, k + 2) + '…' + a.slice(-k / 2 - 2) : (a || '—'); }
  function profile(i) { return i == null ? '—' : i < 0 ? 'E' + (-i) : i === 0 ? 'B0' : 'H' + i; }

  /** Renders the connection/provenance strip into #uBar and the offline/stale banner into #uOffline. */
  function bindStatus(snap) {
    var bar = document.getElementById('uStatus'), ban = document.getElementById('uOffline');
    var compact = bar && bar.getAttribute('data-compact') === '1';
    if (compact) {   // 13-Nov-2026 (owner GO, Home): no collector diagnostics on Home, only LIVE or one discreet notice.
      var s0 = snap.status || 'loading', okd = s0 === 'live' || s0 === 'fixture' || s0 === 'loading', hh = snap.state ? ' <span>#' + num(snap.state.meta.height) + '</span>' : '';
      // P0 13-Nov-2026: LIVE / LAST VERIFIED (with age) / OFFLINE; a stale or stored document is still shown, never blanked
      var ag = snap.collectedAt ? Math.max(0, Date.now() / 1000 - snap.collectedAt) : null;
      bar.innerHTML = (okd ? st(s0) + (s0 !== 'loading' ? hh : '') : snap.state ? '<span class="st lv">' + (s0 === 'offline' ? 'OFFLINE · LAST VERIFIED' : 'LAST VERIFIED') + '</span>' + hh + (ag != null ? ' <span class="age">' + esc(dur(ag)) + ' ago</span>' : '') : '<span class="st na">OFFLINE · source unreachable</span>') +
        ' <a class="u-ns" href="/sost-network-status.html">Network status</a>';
    } else if (bar) {
      var s = snap.status || 'loading', parts = [st(s)];
      parts.push('<span class="prov">' + esc(snap.provenance || (s === 'offline' ? 'OFFLINE · no snapshot reachable' : '')) + '</span>');
      if (snap.state) parts.push('<span>tip #' + num(snap.state.meta.height) + '</span>');
      if (snap.mode === 'live') parts.push('<span>last check ' + hm(snap.checkedAt) + '</span>');
      if (snap.integrity && !snap.integrity.ok) parts.push(pv('estimated', 'INTEGRITY: ' + snap.integrity.problems[0]));
      if (snap.reorg) parts.push(pv('observed', 'REORG #' + snap.reorg.fromHeight + ' → #' + snap.reorg.toHeight));
      if (snap.fallback) parts.push(snap.fallback.ok ? pv('observed', 'DIRECT NODE: tip #' + num(snap.fallback.height) + ' at ' + hm(snap.fallback.at)) : pv('unavailable', 'DIRECT NODE FALLBACK FAILED'));
      bar.innerHTML = parts.join(' ');
    }
    // 13-Nov-2026 (owner GO): no pop-up banner over the page any more. The LIVE / STALE / OFFLINE badge in the stats bar is the
    // only visible indicator; it carries the data age and the reason, so old values are never presented as current.
    // Detection (u-data.js) and diagnostics are unchanged: details go to the badge tooltip and to the console.
    if (ban) { ban.className = 'u-offline'; ban.innerHTML = ''; ban.removeAttribute('role'); }
    var why = '';
    if (snap.status === 'offline') why = 'OFFLINE: collector snapshot unreachable (' + (snap.error || 'network') + '). ' +
      (snap.state ? 'Stored data from ' + utc(snap.collectedAt) + ' — nothing here is live.' : 'No stored data yet.') + ' Retrying every ' + (U.data.REFRESH_MS / 1000) + ' s.';
    else if (snap.status === 'stale') why = 'STALE: data collected ' + utc(snap.collectedAt) + ' (' + dur(snap.ageS) + ' ago, threshold ' + U.data.STALE_S + ' s)' +
      (snap.integrity && !snap.integrity.ok ? '; integrity: ' + snap.integrity.problems.join('; ') : '') + '. Values are not presented as live.';
    if (bar) {
      var badge = bar.querySelector('.st');
      if (badge) { badge.title = why || 'LIVE: collector data ' + dur(snap.ageS) + ' old'; badge.setAttribute('aria-label', badge.title); }
      if (why && snap.state && !compact) bar.insertAdjacentHTML('beforeend', ' <span class="age">data ' + esc(dur(snap.ageS)) + ' old</span>');
    }
    if (why && why !== U._lastWhy) { try { console.warn('[SOST status] ' + why); } catch (e) {} }
    U._lastWhy = why;
  }
  function copy(btn, text) {
    function ok() { btn.classList.add('ok'); var o = btn.dataset.label || btn.textContent; btn.dataset.label = o; btn.textContent = 'copied ✓'; live('Copied: ' + text);
      setTimeout(function () { btn.classList.remove('ok'); btn.textContent = o; }, 1600); }
    if (navigator.clipboard && root.isSecureContext) navigator.clipboard.writeText(text).then(ok, fallback); else fallback();
    function fallback() { var t = document.createElement('textarea'); t.value = text; t.setAttribute('readonly', ''); t.style.cssText = 'position:fixed;left:-9999px'; document.body.appendChild(t); t.select();
      try { document.execCommand('copy'); ok(); } catch (e) { live('Copy failed: select the text manually'); } t.remove(); }
  }
  function live(msg) { var r = document.getElementById('uLive'); if (!r) { r = document.createElement('div'); r.id = 'uLive'; r.className = 'sr'; r.setAttribute('aria-live', 'polite'); document.body.appendChild(r); } r.textContent = ''; setTimeout(function () { r.textContent = msg; }, 30); }
  function mobileNav() {
    var nav = document.querySelector('.u-nav'), b = nav && nav.querySelector('.menu-btn'); if (!b || nav.dataset.managed) return;   // u-nav.js?v=rs20261112g manages its own menu
    b.addEventListener('click', function () { var o = nav.classList.toggle('open'); b.setAttribute('aria-expanded', o); if (o) { var a = nav.querySelector('ul a'); if (a) a.focus(); } });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && nav.classList.contains('open')) { nav.classList.remove('open'); b.setAttribute('aria-expanded', 'false'); b.focus(); } });
  }
  /** Explorer block detail (existing explorer resolves ?search=<height>). */
  function explorerBlock(h) { return '../sost-explorer.html?search=' + encodeURIComponent(h); }
  /** WebGL2 availability (also honours ?gl=0 for tests). */
  function hasGL2() { if (new URLSearchParams(location.search).get('gl') === '0') return false; try { var c = document.createElement('canvas'); return !!(root.WebGL2RenderingContext && c.getContext('webgl2')); } catch (e) { return false; } }
  var RM = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
  U.ui = { esc: esc, pv: pv, st: st, utc: utc, hm: hm, dur: dur, num: num, short: short, profile: profile, bindStatus: bindStatus, copy: copy, live: live, explorerBlock: explorerBlock, hasGL2: hasGL2, RM: RM };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mobileNav); else mobileNav();
})(window);

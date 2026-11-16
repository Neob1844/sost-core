/* SOST blockchain link router (owner P0, 5 Nov 2026). ONE place that turns a blockchain identifier into a link to its real record.
 *
 *  SOSTU.chain.classify(v)         → 'address' | 'height' | 'hash' (64 hex: block hash or TXID, the Explorer resolves which) | null
 *  SOSTU.chain.href(v, opts)       → URL of the record, or null for anything that is not a valid identifier
 *  SOSTU.chain.link(v, label, o)   → '<a …>label</a>' (+ optional copy button) or the escaped label when v is not valid
 *  SOSTU.chain.linkify(root, o)    → links elements marked data-chain="<full id>" (static pages, late renders, canvas lists)
 *
 * Targets (verified in the engines, nothing invented):
 *  - Explorer (the only public Explorer, 14-Nov-2026)  sost-explorer.html?search=<id>   (sost-explorer.html: URLSearchParams 'search' →
 *    #searchIn → doSearch(): height → getblockhash → showBlock; sost1+40 hex → showAddress; 64 hex → getblock, else gettxout /
 *    getrawtransaction → showTxDetail; anything else → the engine's own "not found" message)
 *  (Explorer 2.0, universe/explorer.html, retired 14-Nov-2026: 301 to sost-explorer.html; the option explorer:'modern' is ignored)
 * The FULL identifier always comes from the record the page rendered, never from shortened text: callers pass the original value.
 * Only these exact shapes are links; free 64-hex strings in prose (file hashes, commits, code samples) are never scanned. */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  if (U.chain) return;
  var d = document;
  // site root from this script's own URL (works with <base>, from /universe/ pages and from root pages)
  var ROOT = (function () { try { var s = d.currentScript && d.currentScript.src; if (s) return new URL('../../', s).href; } catch (e) {} return '/'; })();
  var RE = { address: /^sost1[0-9a-f]{40}$/, height: /^\d{1,9}$/, hash: /^[0-9a-f]{64}$/ };
  var ICO = '<svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><rect x="5" y="5" width="9" height="9" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M3 11V3.5A1.5 1.5 0 0 1 4.5 2H11" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>', ICO_OK = '<svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
  function esc(x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function norm(v) { v = String(v == null ? '' : v).trim(); if (/^#\d{1,9}$/.test(v)) v = v.slice(1); if (/^sost1[0-9a-fA-F]{40}$/.test(v) || /^[0-9a-fA-F]{64}$/.test(v)) v = v.toLowerCase(); return v; }
  function classify(v) { v = norm(v); for (var k in RE) if (RE[k].test(v)) return k; return null; }
  function href(v, o) {
    v = norm(v); if (!classify(v)) return null; o = o || {};
    return ROOT + 'sost-explorer.html?search=' + encodeURIComponent(v);
  }
  var KIND = { address: 'address', height: 'block', hash: 'block or transaction' };
  function link(v, label, o) {
    o = o || {}; var n = norm(v), k = classify(n), lab = label == null ? String(v) : String(label);
    if (!k) return esc(lab);
    var h = href(n, o), t = o.title || ('Open ' + KIND[k] + ' ' + n + ' in the Explorer');
    var a = '<a class="u-cl u-cl-' + k + (o.cls ? ' ' + esc(o.cls) : '') + '" href="' + esc(h) + '" data-chain-id="' + esc(n) + '" title="' + esc(t) + '"' + (o.newTab ? ' target="_blank" rel="noopener"' : '') + '>' + (o.html ? lab : esc(lab)) + '</a>';
    return a + (o.copy ? ' <button type="button" class="u-cl-copy" data-copy-id="' + esc(n) + '" aria-label="Copy ' + KIND[k] + ' ' + esc(n) + '" title="Copy the full ' + KIND[k] + '">' + ICO + '</button>' : '');
  }
  // empty copy buttons written in static HTML get the icon
  function icons(el) { var l = (el || d).querySelectorAll ? (el || d).querySelectorAll('button.u-cl-copy:empty') : []; for (var i = 0; i < l.length; i++) l[i].innerHTML = ICO; }
  // static markup: <span data-chain="sost1…">sost1…74aea3</span> → link with the full id from the attribute
  function linkify(el, o) {
    el = el || d; o = o || {};
    var list = el.querySelectorAll ? el.querySelectorAll('[data-chain]:not([data-chain-done])') : [];
    for (var i = 0; i < list.length; i++) {
      var x = list[i], v = x.getAttribute('data-chain'); x.setAttribute('data-chain-done', '');
      if (!classify(v) || x.closest('a,button,code,pre,textarea,input,[data-no-chain]')) continue;
      var w = d.createElement('span'); w.innerHTML = link(v, x.innerHTML, { html: true, copy: x.hasAttribute('data-chain-copy') || o.copy, explorer: x.getAttribute('data-chain-explorer') || o.explorer });
      while (w.firstChild) x.parentNode.insertBefore(w.firstChild, x); x.parentNode.removeChild(x);
    }
  }
  // one delegated copy handler for every page
  d.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('button.u-cl-copy[data-copy-id]'); if (!b) return;
    e.preventDefault(); e.stopPropagation();
    var v = b.getAttribute('data-copy-id'), done = function () { b.classList.add('ok'); b.innerHTML = ICO_OK; setTimeout(function () { b.classList.remove('ok'); b.innerHTML = ICO; }, 1300); };
    try { if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(v).then(done, function () {}); else { var t = d.createElement('textarea'); t.value = v; d.body.appendChild(t); t.select(); d.execCommand('copy'); t.remove(); done(); } } catch (er) {}
  });
  // style (once): readable link, visible focus, discreet copy button
  var st = d.createElement('style'); st.id = 'u-chain-css';
  st.textContent = 'a.u-cl{color:#7dd3fc;text-decoration:none;border-bottom:1px dotted #7dd3fc66;cursor:pointer}a.u-cl:hover{color:#fff;border-bottom-color:#fff}' +
    'a.u-cl:focus-visible{outline:2px solid #22d3ee;outline-offset:2px;border-radius:2px}' +
    'button.u-cl-copy{all:unset;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;min-width:18px;min-height:18px;vertical-align:middle;color:#8b98a8;padding:2px 3px;border-radius:4px;vertical-align:baseline}' +
    'button.u-cl-copy:hover{color:#fff;background:#ffffff14}button.u-cl-copy:focus-visible{outline:2px solid #22d3ee}button.u-cl-copy.ok{color:#4ade80}' +
    '@media (pointer:coarse){button.u-cl-copy{min-width:28px;min-height:28px;line-height:28px}}';
  (d.head || d.documentElement).appendChild(st);
  U.chain = { classify: classify, href: href, link: link, linkify: linkify, root: ROOT, version: 'p0-20261105' };
  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', function () { linkify(d); icons(d); }); else { linkify(d); icons(d); }
  if ('MutationObserver' in root) { var q = 0; new MutationObserver(function () { if (q) return; q = requestAnimationFrame(function () { q = 0; linkify(d); icons(d); }); }).observe(d.documentElement, { childList: true, subtree: true }); }
})(window);

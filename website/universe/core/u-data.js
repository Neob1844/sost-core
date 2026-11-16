/* SOST Convergence Universe — the ONE data layer for every prototype page.
 *
 * Reuses the production Control Room logic as-is:
 *   control-room/adapter.js  (CRSource: GET of the collector snapshots, Date-header clock skew)
 *   control-room/state.js    (CRState: normalize, mergeSeries, contiguousTail, producersInWindow …)
 * It never calls /rpc. One refresh loop per tab (setTimeout chain), paused while the tab is hidden.
 *
 * Sources (provenance is always shown on screen):
 *   fixture : data/*.json — local copies captured from sostcore.com (data/PROVENANCE.json). Loaded once,
 *             no loop, labelled FIXTURE · captured … · not live.
 *   live    : ../api/*.json — same-origin collector snapshots (production path). Locally they are served by
 *             tools/serve_universe.py --live, a read-only relay that GETs sostcore.com at most once per interval.
 *             LIVE only while the collector document is fresh (≤ 45 s, the Control Room rule); STALE above that;
 *             OFFLINE when the fetch fails (last good data kept and shown with its time).
 * Choose with ?src=fixture|live. Default: live on sostcore.com, fixture anywhere else.
 */
(function (root) {
  'use strict';
  var Q = new URLSearchParams(location.search);
  var onProd = /(^|\.)sostcore\.com$/.test(location.hostname);
  var CFG = root.SOSTU_CONFIG || {};   // optional per-page bases (the PWA at /sost-app/ uses the same layer)
  var MODE = Q.get('src') === 'live' ? 'live' : Q.get('src') === 'fixture' ? 'fixture' : (CFG.mode || (onProd ? 'live' : 'fixture'));
  var FIXBASE = CFG.fixtureBase || 'data/';
  var BASE = MODE === 'live' ? (CFG.apiBase || '../api/') : FIXBASE;
  var REFRESH_MS = 15000;          // collector doc: one GET per 15 s per tab (304 when unchanged)
  var EARN_MS = 300000;            // address_earnings.json (confirmed jackpots): only for pages that ask, every 5 min
  var STALE_S = 45;                // same threshold as the Control Room badge
  var CACHE_KEY = 'sostu_last_good_v1';

  var src = new root.CRSource({ docUrl: BASE + 'control_room.json', seriesUrl: BASE + 'block_series.json' });
  var subs = [], timer = 0, started = false, inflight = false;
  var last = null;                  // last snapshot object given to subscribers
  var prevHeight = null, earn = null, earnAt = 0, wantEarn = false, fixtureMeta = null;
  var stats = { docGets: 0, seriesGets: 0, earnGets: 0, failures: 0, rpc: 0, startedAt: Date.now() };
  // Bounded fallback when the collector is missing or stale (the collector must not be a functional single point of
  // failure): in live mode only, after 2 consecutive bad refreshes, at most 2 read-only RPC reads (getblockcount +
  // getbestblockhash) per FALLBACK_MIN_MS. Shown as a direct node observation, never as the full LIVE state.
  var FALLBACK_MIN_MS = 60000, RPC_URL = '/rpc', badRuns = 0, fbAt = 0, fallback = null, prevTip = null;
  var fallbackOn = MODE === 'live' && Q.get('fallback') !== '0';
  async function rpc(method) {
    stats.rpc++;
    var r = await fetch(RPC_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: method, params: [] }) });
    if (!r.ok) throw new Error('rpc HTTP ' + r.status); var j = await r.json(); if (j.error) throw new Error('rpc ' + (j.error.message || 'error')); return j.result;
  }
  async function maybeFallback() {
    if (!fallbackOn || badRuns < 2 || Date.now() - fbAt < FALLBACK_MIN_MS) return;
    fbAt = Date.now();
    try { var h = await rpc('getblockcount'), hash = await rpc('getbestblockhash'); fallback = { height: h, hash: hash, at: Date.now(), ok: true }; }
    catch (e) { fallback = { ok: false, error: String(e && e.message || e), at: Date.now() }; }
  }
  /** Integrity checks on every collector document before its values are used. */
  function integrity(doc, state, rows) {
    var p = [];
    if (doc.schema !== 2) p.push('unknown schema ' + doc.schema);
    if (doc.height != null && state.meta.height != null && doc.height !== state.meta.height) p.push('doc.height ' + doc.height + ' ≠ getinfo.blocks ' + state.meta.height);
    if (!rows.length || rows[rows.length - 1].h !== state.meta.height) p.push('block series does not reach the tip');
    for (var i = 1; i < rows.length; i++) if (rows[i].h !== rows[i - 1].h + 1) { p.push('gap in series at #' + rows[i].h); break; }
    if (!state.active.chain.tipHash.value) p.push('tip hash missing');
    if (doc.errors && Object.keys(doc.errors).length) p.push('collector reported errors: ' + Object.keys(doc.errors).join(', '));
    return { ok: !p.length, problems: p };
  }

  function emit(s) { last = s; subs.forEach(function (f) { try { f(s); } catch (e) { console.error(e); } }); }

  async function getFixtureMeta() {
    if (fixtureMeta || MODE !== 'fixture') return fixtureMeta;
    try { fixtureMeta = await (await fetch(FIXBASE + 'PROVENANCE.json', { cache: 'no-cache' })).json(); } catch (e) { fixtureMeta = {}; }
    return fixtureMeta;
  }
  async function getEarn() {
    if (!wantEarn || (earn && Date.now() - earnAt < EARN_MS)) return;
    try { stats.earnGets++; var r = await fetch(BASE + 'address_earnings.json', { cache: 'no-cache' }); if (!r.ok) throw new Error('HTTP ' + r.status); earn = await r.json(); earnAt = Date.now(); }
    catch (e) { /* keep previous */ }
  }

  function rowsFrom(bundle, height) {
    return root.CRState.contiguousTail(root.CRState.mergeSeries(bundle.series, bundle.deltaBlocks), height)
      .map(function (r, i, a) { return { h: r.h, t: r.t, bq: r.bits_q, prof: r.profile, miner: r.miner, hash: r.hash || null, mode: r.mode || null, dt: i ? r.t - a[i - 1].t : null }; });
  }

  function concentration(rows, n) {
    var w = rows.slice(Math.max(0, rows.length - n)), c = {};
    w.forEach(function (r) { c[r.miner] = (c[r.miner] || 0) + 1; });
    var list = Object.keys(c).map(function (a) { return { addr: a, n: c[a], pct: 100 * c[a] / w.length }; }).sort(function (a, b) { return b.n - a.n; });
    // HHI on percentage shares (0–10,000) and Nakamoto coefficient (fewest addresses with > 50 % of the blocks)
    var hhi = 0, acc = 0, nak = null; list.forEach(function (p, i) { hhi += p.pct * p.pct; acc += p.pct; if (nak == null && acc > 50) nak = i + 1; });
    return { window: w.length, from: w.length ? w[0].h : null, to: w.length ? w[w.length - 1].h : null, producers: list.length,
      fromT: w.length ? w[0].t : null, toT: w.length ? w[w.length - 1].t : null, hhi: Math.round(hhi), nakamoto: nak,
      top1: list[0] ? list[0].pct : null, top2: list.length > 1 ? list[0].pct + list[1].pct : (list[0] ? list[0].pct : null), list: list };
  }

  // Per-window history: consecutive, non-overlapping windows of n blocks ending at the newest row (oldest partial dropped).
  function concentrationSeries(rows, n) {
    var out = [];
    for (var end = rows.length; end - n >= 0; end -= n) {
      var c = concentration(rows.slice(end - n, end), n);
      out.unshift({ from: c.from, to: c.to, fromT: c.fromT, toT: c.toT, top2: c.top2, hhi: c.hhi, nakamoto: c.nakamoto, producers: c.producers });
    }
    return out;
  }

  async function refresh(opts) {
    if (inflight) return; inflight = true;
    var status, doc, bundle, err = null;
    try {
      var seriesBefore = src.seriesAt;
      var out = await src.load();
      stats.docGets++; if (src.seriesAt !== seriesBefore) stats.seriesGets++;
      doc = out.doc; bundle = out.bundle;
      if (MODE === 'fixture') { bundle.now = doc.collected_at; bundle.source = 'fixture'; }   // ages relative to capture time
      await getEarn();
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({ at: Date.now(), mode: MODE, doc: doc, series: src.series })); } catch (e) {}
    } catch (e) {
      stats.failures++; err = String(e && e.message || e);
    }
    inflight = false;
    var fetchedAt = Date.now();
    if (!doc) {
      // OFFLINE: keep what we had; if nothing yet, try the stored copy from a previous visit.
      badRuns++; await maybeFallback();
      if (last && last.state) { emit(Object.assign({}, last, { status: 'offline', error: err, checkedAt: fetchedAt, newBlocks: [], reorg: null, fallback: fallback })); return schedule(); }
      var cached = null; try { cached = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null'); } catch (e) {}
      if (cached && cached.doc && cached.mode === MODE) {
        doc = cached.doc; bundle = Object.assign({}, doc.bundle, { series: cached.series });
        var db = doc.bundle.deltaBlocks;
        if (db && db.fields) { bundle.deltaBlocks = db.rows.map(function (r) { var o = {}; db.fields.forEach(function (f, i) { o[f] = r[i]; }); return o; }); if (bundle.deltaBlocks.length) bundle.deltaBlocks[bundle.deltaBlocks.length - 1].hash = db.tip_hash; }
        bundle.now = Math.floor(Date.now() / 1000); bundle.source = 'stored'; bundle.recordedAt = doc.collected_at;
        status = 'offline';
      } else { emit({ status: 'offline', mode: MODE, error: err, checkedAt: fetchedAt, state: null, rows: [], newBlocks: [], stats: stats, fallback: fallback }); return schedule(); }
    }
    var state = root.CRState.normalize(bundle);
    var nowS = MODE === 'fixture' ? doc.collected_at : src.now();
    var age = Math.max(0, Math.round(nowS - doc.collected_at));
    if (!status) status = MODE === 'fixture' ? 'fixture' : (age > STALE_S ? 'stale' : 'live');
    var height = state.meta.height, rows = rowsFrom(bundle, height);
    var integ = integrity(doc, state, rows);
    if (!integ.ok && status === 'live') status = 'stale';          // never call inconsistent data LIVE
    var nb = [], reorg = null, tipHash = state.active.chain.tipHash.value;
    if (prevTip && status !== 'offline') {
      if (height < prevTip.h || (height === prevTip.h && tipHash && prevTip.hash && tipHash !== prevTip.hash)) reorg = { fromHeight: prevTip.h, fromHash: prevTip.hash, toHeight: height, toHash: tipHash };
      else if (height > prevTip.h) for (var h = prevTip.h + 1; h <= height; h++) nb.push(h);
    }
    if (status !== 'offline') prevTip = { h: height, hash: tipHash };
    prevHeight = height;
    badRuns = (status === 'live' || status === 'fixture') ? 0 : badRuns + 1;
    if (badRuns === 0) fallback = null; else await maybeFallback();
    var meta = await getFixtureMeta();
    emit({
      status: status, mode: MODE, error: err, checkedAt: fetchedAt, collectedAt: doc.collected_at, ageS: age,
      provenance: MODE === 'fixture'
        ? 'FIXTURE · collector snapshot captured ' + ((meta && meta['control_room.json'] && meta['control_room.json'].captured_utc) || '?') + ' from sostcore.com · not live'
        : (status === 'offline' ? 'OFFLINE · showing stored data collected ' + iso(doc.collected_at)
          : 'Collector snapshot (public node) · same-origin ' + BASE + ' · collected ' + iso(doc.collected_at)),
      doc: doc, state: state, rows: rows, tipHash: tipHash, newBlocks: nb, reorg: reorg, integrity: integ, fallback: fallback,
      concentration: { w288: concentration(rows, 288), w1200: concentration(rows, 1200), series288: concentrationSeries(rows, 288) },
      earnings: earn, earnMeta: meta && meta['address_earnings.json'], stats: stats
    });
    schedule();
  }
  function iso(t) { return t ? new Date(t * 1000).toISOString().replace('.000', '') : '?'; }
  function schedule() {
    clearTimeout(timer); timer = 0;
    if (MODE === 'fixture' || document.hidden) return;   // fixtures never change; hidden tab = no network
    timer = setTimeout(refresh, REFRESH_MS);
  }
  document.addEventListener('visibilitychange', function () {
    if (!started) return;
    if (document.hidden) { clearTimeout(timer); timer = 0; }
    else if (MODE === 'live' && !timer && !inflight) refresh();
  });
  addEventListener('online', function () { if (started && MODE === 'live') refresh(); });

  root.SOSTU = root.SOSTU || {};
  root.SOSTU.data = {
    MODE: MODE, BASE: BASE, REFRESH_MS: REFRESH_MS, STALE_S: STALE_S, stats: stats,
    /** fn(snapshot) is called on every refresh (and immediately with the last one if any). */
    subscribe: function (fn) { subs.push(fn); if (last) fn(last); if (!started) { started = true; refresh(); } },
    /** Ask for address_earnings.json too (confirmed jackpot events). Call before subscribe. */
    wantEarnings: function () { wantEarn = true; },
    /** Re-emit the tip block as a new arrival, flagged replay:true (HISTORICAL replay, never claimed as new). */
    replayTip: function () { if (last && last.state) emit(Object.assign({}, last, { newBlocks: [last.state.meta.height], replay: true })); },
    refreshNow: function () { return refresh(); },
    last: function () { return last; },
    concentration: concentration, concentrationSeries: concentrationSeries
  };
})(window);

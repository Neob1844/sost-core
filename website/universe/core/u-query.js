/* SOST Universe — on-demand queries for Explorer 2.0 (Phase 5).
 * Snapshots (u-data.js) carry state, stats, series and history. RPC is used ONLY when a person asks for one block, tx or
 * address, and is bounded:
 *   - read-only method allow-list; ≤ 2 calls in flight; ≤ 40 calls per rolling minute (then queued, never dropped silently)
 *   - 12 s timeout, one retry on network error only; 429/5xx pause the queue 10 s
 *   - per-request cache (blocks by hash forever, other reads 30 s)
 * Own node: OFF by default. URL + user + password live only in this closure (never localStorage/sessionStorage/URL).
 * Public node by default on sostcore.com; fixture mode (?src=fixture, or any other host without ?src=live) answers from
 * data/rpc/ondemand.json captured read-only, and anything not captured is UNAVAILABLE (stated as fixture, never as live).
 */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  var READ = { getblockhash: 1, getblock: 1, getrawtransaction: 1, gettransaction: 1, gettxout: 1, getaddressinfo: 1, getaddressflows: 1,
    getblockcount: 1, getbestblockhash: 1, getrawmempool: 1, getmempoolinfo: 1, getjackpotv2audit: 1, getlotteryaudit: 1, getrpcstats: 1 };
  // same rule as u-data.js: live on sostcore.com, fixture anywhere else; ?src=live|fixture forces either (owner P0, 4 Nov 2026:
  // before this, the public site answered every block / tx / address lookup from the captured fixture → "UNAVAILABLE")
  var onProd = /(^|\.)sostcore\.com$/.test(location.hostname), srcQ = (location.search.match(/[?&]src=(live|fixture)\b/) || [])[1];
  var live = srcQ ? srcQ === 'live' : onProd;
  var url = (U.SOSTU_CONFIG && U.SOSTU_CONFIG.rpc) || (root.SOSTU_CONFIG && root.SOSTU_CONFIG.rpc) || '/rpc', user = '', pass = '', own = false;
  var MAX_INFLIGHT = 2, PER_MIN = 40, TIMEOUT = 12000, inflight = 0, q = [], stamps = [], pauseUntil = 0, cache = {}, fixture = null;
  var stats = { calls: 0, errors: 0, cached: 0, queuedMax: 0, perMinute: function () { var t = Date.now(); return stamps.filter(function (s) { return t - s < 60000; }).length; } };

  function loadFixture() {
    if (!fixture) fixture = fetch((root.SOSTU_CONFIG && root.SOSTU_CONFIG.fixtureBase || 'data/') + 'rpc/ondemand.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : { responses: {} }; }).catch(function () { return { responses: {} }; });
    return fixture;
  }
  function key(m, p) { return m + '|' + JSON.stringify(p || []); }
  function pump() {
    while (inflight < MAX_INFLIGHT && q.length) {
      var t = Date.now(); stamps = stamps.filter(function (s) { return t - s < 60000; });
      if (t < pauseUntil || stamps.length >= PER_MIN) { setTimeout(pump, Math.max(250, t < pauseUntil ? pauseUntil - t : 60000 - (t - stamps[0]))); return; }
      var job = q.shift(); inflight++; stamps.push(t); stats.calls++; run(job, 0);
    }
  }
  function run(job, attempt) {
    var ctl = root.AbortController ? new AbortController() : null, to = setTimeout(function () { if (ctl) ctl.abort(); }, TIMEOUT);
    var h = { 'Content-Type': 'application/json' }; if (own && user) h.Authorization = 'Basic ' + btoa(user + ':' + pass);
    fetch(url, { method: 'POST', headers: h, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: job.m, params: job.p }), signal: ctl && ctl.signal, cache: 'no-store', credentials: 'omit' })
      .then(function (r) {
        if (r.status === 429 || r.status >= 500) { pauseUntil = Date.now() + 10000; throw new Error('HTTP ' + r.status + ' (paused 10 s)'); }
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (j) { if (j.error) throw new Error(j.error.message || JSON.stringify(j.error)); done(job, null, j.result); },
        function (e) { if (attempt === 0 && (e.name === 'AbortError' || e instanceof TypeError)) return run(job, 1); stats.errors++; done(job, e); })
      .then(function () { clearTimeout(to); });
  }
  function done(job, err, res) {
    inflight--; if (!err) cache[job.k] = { at: Date.now(), v: res, ttl: job.m === 'getblock' ? Infinity : 30000 };
    if (err) job.no(err); else job.ok(res); pump();
  }
  /** call(method, params) -> Promise(result). Rejects for non read-only methods. */
  function call(m, p) {
    if (!READ[m]) return Promise.reject(new Error('method not allowed: ' + m));
    var k = key(m, p), c = cache[k];
    if (c && Date.now() - c.at < c.ttl) { stats.cached++; return Promise.resolve(c.v); }
    if (!live && !own) return loadFixture().then(function (f) {
      var r = f.responses && f.responses[k];
      if (r && r.result != null) return r.result;
      throw new Error('UNAVAILABLE in fixture mode (only captured queries answer offline)');
    });
    return new Promise(function (ok, no) { q.push({ m: m, p: p || [], k: k, ok: ok, no: no }); stats.queuedMax = Math.max(stats.queuedMax, q.length); pump(); });
  }
  function classify(s) {
    s = String(s || '').trim();
    if (/^\d{1,9}$/.test(s)) return { kind: 'height', v: +s };
    if (/^sost1[0-9a-f]{40}$/i.test(s)) return { kind: 'address', v: s.toLowerCase() };
    if (/^[0-9a-f]{64}$/i.test(s)) return { kind: 'hash', v: s.toLowerCase() };
    if (/^sost1/i.test(s)) return { kind: 'bad', v: s, why: 'An address is sost1 followed by 40 hex characters.' };
    return { kind: 'bad', v: s, why: 'Enter a block height, a 64-hex block hash or txid, or a sost1 address.' };
  }
  /** search(q) -> {kind:'block'|'tx'|'address', data, calls} using the fewest calls (EX doSearch order). */
  async function search(s) {
    var c = classify(s), n0 = stats.calls;
    if (c.kind === 'bad') throw new Error(c.why);
    if (c.kind === 'height') { var hh = await call('getblockhash', [c.v]); return { kind: 'block', data: await call('getblock', [hh]), calls: stats.calls - n0 }; }
    if (c.kind === 'address') {
      var info = await call('getaddressinfo', [c.v]), flows = null; try { flows = await call('getaddressflows', [c.v]); } catch (e) {}
      return { kind: 'address', data: { info: info, flows: flows }, calls: stats.calls - n0 };
    }
    try { return { kind: 'block', data: await call('getblock', [c.v]), calls: stats.calls - n0 }; } catch (e) {}
    try { return { kind: 'tx', data: await call('getrawtransaction', [c.v, true]), calls: stats.calls - n0 }; } catch (e) {}
    return { kind: 'tx', data: await call('gettransaction', [c.v]), calls: stats.calls - n0 };
  }
  /** Own node: memory only. Pass url '' to disconnect. Never persisted. */
  function setNode(u, us, pw) { cache = {}; if (!u) { own = false; url = '/rpc'; user = pass = ''; return; } own = true; url = u; user = us || ''; pass = pw || ''; }
  U.query = { call: call, search: search, classify: classify, setNode: setNode, stats: stats, mode: function () { return own ? 'own-node' : live ? 'public' : 'fixture'; },
    LIMITS: { inflight: MAX_INFLIGHT, perMinute: PER_MIN, timeoutMs: TIMEOUT } };
})(window);

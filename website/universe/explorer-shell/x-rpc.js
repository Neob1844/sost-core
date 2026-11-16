/* SOST Explorer · RPC transport cache (DIRECTIVA FINAL §A.6: measure and optimise RPC without changing meanings).
 *
 * Sits in front of window.fetch, BEFORE the engine runs. The engine's rpc() code is not modified.
 *   1. Immutable answers are remembered across visits (IndexedDB): getblockhash [h] and getblock [hash] for blocks at
 *      least RPC_REORG_DEPTH (12, the engine's own rule) below the tip seen by this page. A repeat visit answers the
 *      ~2,000 block-history reads from the browser instead of the node; the response body is the node's own JSON.
 *   2. At most MAX_INFLIGHT /rpc requests go to the network at once (first visit: same calls, spread over a few
 *      seconds instead of a ~1,000/s burst). A request queued here still honours the engine's AbortController.
 * Only the public endpoint is touched: same-origin POST to /rpc, single JSON-RPC call, no Authorization header.
 * Anything else (own node with credentials, writes, batches, other URLs) passes straight through. If IndexedDB is
 * unavailable (private mode, blocked storage) the cache is simply off. Never stores anything but public chain data. */
(function (root) {
  'use strict';
  var nativeFetch = root.fetch && root.fetch.bind(root); if (!nativeFetch) return;
  var DEPTH = 12, MAX_INFLIGHT = 48, KEEP = 3000, DB = 'sost-explorer-rpc', STORE = 'v1', WAIT_DB_MS = 1500;
  var CACHEABLE = { getblock: 1, getblockhash: 1 };
  var tip = 0, mem = new Map(), db = null, ready, pending = [], stats = { hit: 0, net: 0, stored: 0, queued: 0, peak: 0 };

  ready = new Promise(function (res) {
    var t = setTimeout(res, WAIT_DB_MS);
    try {
      var rq = root.indexedDB.open(DB, 1);
      rq.onupgradeneeded = function () { rq.result.createObjectStore(STORE); };
      rq.onsuccess = function () {
        db = rq.result;
        try {   // one bulk read (getAllKeys + getAll) instead of a cursor walk: ~2,000 entries load in a few tens of ms
          var os = db.transaction(STORE, 'readonly').objectStore(STORE), gk = os.getAllKeys(), gv = os.getAll();
          gv.onsuccess = function () { var k = gk.result || [], v = gv.result || []; for (var i = 0; i < k.length && i < v.length; i++) mem.set(k[i], v[i]); clearTimeout(t); res(); };
          gv.onerror = gk.onerror = function () { clearTimeout(t); res(); };
        } catch (e) { clearTimeout(t); res(); }
      };
      rq.onerror = rq.onblocked = function () { clearTimeout(t); res(); };
    } catch (e) { clearTimeout(t); res(); }
  });

  function put(k, v, h) {
    if (mem.has(k)) return; mem.set(k, { b: v, h: h }); stats.stored++;
    if (!db) return;
    try { db.transaction(STORE, 'readwrite').objectStore(STORE).put({ b: v, h: h }, k); } catch (e) {}
  }
  function setTip(t) {   // answers seen before the tip was known are kept until their depth can be checked
    if (!(t > tip)) return; tip = t;
    if (pending.length) { var keep = []; pending.forEach(function (x) { if (x.h <= tip - DEPTH) put(x.k, x.b, x.h); else if (x.h > tip - 400) keep.push(x); }); pending = keep; }
    prune();
  }
  function candidate(k, b, h) { if (tip && h <= tip - DEPTH) put(k, b, h); else if (!tip && pending.length < 5000) pending.push({ k: k, b: b, h: h }); }
  function prune() {   // keep the newest KEEP heights (a 1,206-block window needs ~2,400 entries)
    if (mem.size <= KEEP * 2 || !tip) return;
    var floor = tip - KEEP;
    mem.forEach(function (v, k) { if (v.h < floor) { mem.delete(k); try { db && db.transaction(STORE, 'readwrite').objectStore(STORE).delete(k); } catch (e) {} } });
  }
  function publicRpc(input, init) {
    try {
      if (!init || String(init.method || 'GET').toUpperCase() !== 'POST' || typeof init.body !== 'string') return null;
      var u = new URL(typeof input === 'string' ? input : input.url, location.href);
      if (u.origin !== location.origin || u.pathname !== '/rpc') return null;
      var h = init.headers || {}; if (h.Authorization || h.authorization || (h.get && h.get('Authorization'))) return null;
      var j = JSON.parse(init.body); if (!j || Array.isArray(j) || typeof j.method !== 'string') return null;
      return j;
    } catch (e) { return null; }
  }
  function answer(j, body) {   // the node's own response, with the caller's id
    var o = JSON.parse(body); o.id = j.id;
    return new Response(JSON.stringify(o), { status: 200, headers: { 'Content-Type': 'application/json', 'X-SOST-Cache': 'browser' } });
  }

  var inflight = 0, queue = [];
  function slot(signal) {
    if (inflight < MAX_INFLIGHT) { inflight++; stats.peak = Math.max(stats.peak, inflight); return Promise.resolve(); }
    stats.queued++;
    return new Promise(function (res, rej) {
      var item = { go: function () { inflight++; stats.peak = Math.max(stats.peak, inflight); res(); } };
      if (signal) {
        if (signal.aborted) return rej(new DOMException('Aborted', 'AbortError'));
        signal.addEventListener('abort', function () { var i = queue.indexOf(item); if (i >= 0) { queue.splice(i, 1); rej(new DOMException('Aborted', 'AbortError')); } }, { once: true });
      }
      queue.push(item);
    });
  }
  function release() { inflight--; var n = queue.shift(); if (n) n.go(); }

  root.fetch = function (input, init) {
    var j = publicRpc(input, init);
    if (!j) return nativeFetch(input, init);
    var m = j.method, p = Array.isArray(j.params) ? j.params : [], key = null;
    if (CACHEABLE[m] && p.length === 1) key = m + '|' + String(p[0]);
    return (key ? ready : Promise.resolve()).then(function () {   // only cacheable reads wait (≤ 1.5 s, normally a few ms) for the stored answers
      var c = key && mem.get(key);
      if (c) { stats.hit++; return answer(j, c.b); }
      return slot(init.signal).then(function () {
        stats.net++;
        return nativeFetch(input, init).then(function (r) {
          release();
          if (!r.ok) return r;
          return r.clone().text().then(function (txt) {
            try {
              var o = JSON.parse(txt), v = o && o.result;
              if (o && !o.error && v != null) {
                if (m === 'getblockcount' && typeof v === 'number') setTip(v);
                else if (m === 'getblock' && typeof v === 'object' && typeof v.height === 'number') {
                  if (key && v.hash === p[0] && !('confirmations' in v)) candidate(key, txt, v.height);
                } else if (m === 'getblockhash' && key && typeof v === 'string') {
                  var hh = parseInt(p[0], 10); if (hh >= 0) candidate(key, txt, hh);
                }
              }
            } catch (e) {}
            return r;
          });
        }, function (e) { release(); throw e; });
      });
    });
  };
  root.SOSTRpcCache = { stats: stats, size: function () { return mem.size; }, clear: function () { mem.clear(); try { db && db.transaction(STORE, 'readwrite').objectStore(STORE).clear(); } catch (e) {} } };
})(window);

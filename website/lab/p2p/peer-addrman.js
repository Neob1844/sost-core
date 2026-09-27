/* SOST peer address manager — REFERENCE for the anti-poisoning discovery core.
 *
 * Reference algorithm (to be ported to C++ behind a default-OFF flag with adversarial
 * tests before enablement — see docs/p2p/PEER_DISCOVERY.md). NOT wired into the node.
 * Purely decides WHO to dial; never affects block validity (PoW is the sole arbiter).
 *
 * Eclipse defenses implemented here:
 *  - new/tried tables (only successfully-connected peers become 'tried' & preferred)
 *  - per-source share cap on 'new' (one source cannot flood the table)
 *  - network-group diversity for outbound selection (/16 buckets by default)
 *  - bounded deterministic eviction (evict worst, never a good tried peer)
 *  - ADDR rate-limit per source per interval
 */
(function (root) {
  "use strict";

  function groupOf(ip) {
    // /16 for IPv4; for anything else use the first 2 dot/colon-separated fields
    var sep = ip.indexOf(":") >= 0 ? ":" : ".";
    return ip.split(sep).slice(0, 2).join(sep);
  }

  function makeAddrMan(opts) {
    opts = opts || {};
    var NEW_CAP = opts.newCap || 1024;
    var TRIED_CAP = opts.triedCap || 256;
    var MAX_SHARE_PER_SOURCE = opts.maxSharePerSource || 0.10; // 10% of NEW_CAP
    var ADDR_PER_INTERVAL = opts.addrPerInterval || 100;       // unsolicited ADDR cap / source / interval

    var neu = new Map();   // key -> {addr, source, group, added, attempts, lastFail}
    var tried = new Map(); // key -> {addr, source, group, added, attempts}
    var perSourceCount = new Map(); // source -> count in NEW
    var rate = new Map();  // source -> count this interval

    function key(a) { return a; }
    function sourceCap() { return Math.max(1, Math.floor(NEW_CAP * MAX_SHARE_PER_SOURCE)); }

    // Feed an address heard from `source`. clock = monotonic tick supplied by caller.
    function addAddr(addr, source, clock) {
      // ADDR rate-limit per source per interval
      var r = (rate.get(source) || 0) + 1; rate.set(source, r);
      if (r > ADDR_PER_INTERVAL) return { accepted: false, reason: "rate_limited" };
      var k = key(addr);
      if (tried.has(k) || neu.has(k)) return { accepted: false, reason: "known" };
      // per-source share cap on NEW
      if ((perSourceCount.get(source) || 0) >= sourceCap()) return { accepted: false, reason: "source_cap" };
      if (neu.size >= NEW_CAP) evictWorstNew();
      neu.set(k, { addr: addr, source: source, group: groupOf(addr), added: clock, attempts: 0, lastFail: 0 });
      perSourceCount.set(source, (perSourceCount.get(source) || 0) + 1);
      return { accepted: true };
    }

    function evictWorstNew() {
      // worst = most attempts, then oldest
      var worstK = null, worst = null;
      neu.forEach(function (v, k) {
        if (!worst || v.attempts > worst.attempts || (v.attempts === worst.attempts && v.added < worst.added)) { worst = v; worstK = k; }
      });
      if (worstK != null) { neu.delete(worstK); perSourceCount.set(worst.source, Math.max(0, (perSourceCount.get(worst.source) || 1) - 1)); }
    }

    // Record a successful connection -> promote to tried.
    function markGood(addr, clock) {
      var k = key(addr);
      var e = neu.get(k);
      if (e) { neu.delete(k); perSourceCount.set(e.source, Math.max(0, (perSourceCount.get(e.source) || 1) - 1)); }
      else e = tried.get(k) || { addr: addr, source: "self", group: groupOf(addr), added: clock, attempts: 0 };
      e.attempts = 0; e.added = clock;
      if (!tried.has(k) && tried.size >= TRIED_CAP) evictWorstTried(clock);
      tried.set(k, e);
    }

    function evictWorstTried(clock) {
      // demote the entry idle longest (smallest added); tried peers only leave on age, never randomly
      var oldestK = null, oldest = null;
      tried.forEach(function (v, k) { if (!oldest || v.added < oldest.added) { oldest = v; oldestK = k; } });
      if (oldestK != null) tried.delete(oldestK);
    }

    // Record a failed connection attempt.
    function markFail(addr, clock) {
      var e = tried.get(addr) || neu.get(addr);
      if (!e) return;
      e.attempts++; e.lastFail = clock;
      // repeated failure demotes a tried peer back to new
      if (tried.has(addr) && e.attempts >= (opts.demoteAfter || 3)) {
        tried.delete(addr);
        if (neu.size < NEW_CAP) neu.set(addr, e);
      }
    }

    // Select up to n outbound targets with network-group diversity, preferring tried.
    function selectOutbound(n) {
      var out = [], usedGroups = new Set();
      function take(map) {
        var arr = Array.from(map.values()).sort(function (a, b) { return a.attempts - b.attempts || b.added - a.added; });
        for (var i = 0; i < arr.length && out.length < n; i++) {
          if (usedGroups.has(arr[i].group)) continue; // one per group first pass
          out.push(arr[i].addr); usedGroups.add(arr[i].group);
        }
      }
      take(tried);
      if (out.length < n) take(neu);
      // second pass: relax group diversity only if still short (rather than starve)
      if (out.length < n) {
        var pool = Array.from(tried.values()).concat(Array.from(neu.values()));
        for (var j = 0; j < pool.length && out.length < n; j++) if (out.indexOf(pool[j].addr) < 0) out.push(pool[j].addr);
      }
      return out;
    }

    function resetInterval() { rate.clear(); }

    function stats() {
      var bySource = {}; perSourceCount.forEach(function (v, k) { bySource[k] = v; });
      var groups = new Set(); tried.forEach(function (v) { groups.add(v.group); });
      return { new: neu.size, tried: tried.size, new_by_source: bySource, tried_groups: groups.size, source_cap: sourceCap() };
    }

    return { addAddr: addAddr, markGood: markGood, markFail: markFail, selectOutbound: selectOutbound, resetInterval: resetInterval, stats: stats, groupOf: groupOf };
  }

  var API = { makeAddrMan: makeAddrMan, groupOf: groupOf };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.SOSTAddrMan = API;
})(typeof window !== "undefined" ? window : this);

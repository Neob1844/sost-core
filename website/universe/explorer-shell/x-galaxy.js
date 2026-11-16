/* SOST Explorer — Galaxy Mining Observatory (DIRECTIVA 4J §2). Optional view of the mined blocks, four modes:
 * GALAXY · MOSAIC · CHARTS · TABLE. PRESENTATION ONLY, 0 RPC:
 *  - blocks: /api/block_series.json (last 1,200 blocks: h, t, bits_q, profile, miner) merged with the deltaBlocks rows of
 *    /api/control_room.json (newest 300 rows), the same static collector snapshots js/control-room.js and the live console
 *    already read (reused from window.__crDoc when the console has loaded it);
 *  - observed rewards: /api/address_earnings.json (collector, block by block since genesis), fetched once, only when a
 *    producer is selected or the TABLE is opened;
 *  - block / address links go through the engine's own search (U.explorerShell.find), exactly as if typed in the search box;
 *  - MINING OBSERVATORY 2.0 (owner, 4 Nov 2026): selecting a producer opens the ADDRESS INSPECTOR (universe/core/u-addr.js) under
 *    the galaxy: current balance / UTXO from the node (2 read-only RPC, on demand, cached 30 s), historical rewards and NODE_BIND
 *    from the collector, window statistics from the snapshot. Decentralization radar, zoom / pan, selected-block marker, new-block
 *    flash. Permalinks: #obs=<address> (this view) and ?search=<address> (the engine's full address page).
 * GALAXY WINDOWS (owner order, 15 Nov 2026): default = all recent blocks (≈1,206: block_series + control_room); the
 *    last-288 card carries CONSENSUS (the DTD recency / reference window); GENESIS loads, only on demand, the full chain from
 *    /api/block_series_genesis.json (compact: delta times, producer index) with a progress state, merged with the recent rows
 *    up to the tip. URL: ?galaxy=1206|genesis|24|72|144|288 (no parameter = 1206). The window choice is not persisted.
 * Rendering: one Canvas 2D, stars grouped per producer and recency bucket (one path + one fill per group, never one object
 * per block); animation only while visible, ~30 fps, paused on hover; reduced-motion = static frame. Loaded lazily by x-shell.js. */
(function (root) {
  'use strict';
  var d = document, U = root.SOSTU = root.SOSTU || {};
  var host = d.getElementById('xsObs'); if (!host) return;
  var RM = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var WIN = [24, 72, 144, 288];
  var $ = function (s) { return host.querySelector(s); };
  var esc = function (x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var fmt = function (n, dd) { return n == null || isNaN(n) ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: dd || 0, maximumFractionDigits: dd || 0 }); };
  var pct = function (a, b) { return b ? (100 * a / b).toFixed(1) + ' %' : '—'; };
  var short = function (a) { return a ? a.slice(0, 9) + '…' + a.slice(-6) : '—'; };
  function hue(s) { s = s || 'unknown'; var h = 5381; for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return ((h % 360) + 360) % 360; }
  // same producer colour as the Network Mosaic and the Equalizer card (js/control-room.js window.sostProducerColor)
  function col(a, l) { return root.sostProducerColor ? root.sostProducerColor(a, l || 58) : 'hsl(' + hue(a) + ',66%,' + (l || 58) + '%)'; }
  function rnd(h, k) { var x = Math.sin(h * 12.9898 + k * 78.233) * 43758.5453; return x - Math.floor(x); }
  function find(q) { if (U.explorerShell && U.explorerShell.find) U.explorerShell.find(String(q)); }

  var M = { rows: [], recent: [], recentN: 0, full: null, fullBusy: false, fullErr: null, fullProg: 0, fullPerf: null, tip: null, prod: [], byAddr: {}, src: '', at: null, earn: null, earnBusy: false };
  var st = { mode: 'galaxy', wk: 'recent', sel: null, hover: null, win: 288, filter: '', sort: ['n288', -1], blk: null, z: 1, ox: 0, oy: 0 };
  var flash = null;   // newest block that arrived with a refresh: { h, t0 }
  try { var sm = localStorage.getItem('sost_xs_obs_mode'); if (/^(galaxy|mosaic|charts|table)$/.test(sm)) st.mode = sm; } catch (e) {}
  // window from the URL (?galaxy=…); without it the default is the recent window (all ≈1,206 loaded blocks)
  function wkOf(v) { v = String(v == null ? '' : v).toLowerCase(); return /^(genesis|full)$/.test(v) ? 'genesis' : /^(24|72|144|288)$/.test(v) ? v : /^(1206|all|recent)$/.test(v) ? 'recent' : null; }
  try { var gq = wkOf(new URLSearchParams(location.search).get('galaxy')); if (gq) { st.wk = gq; st.mode = 'galaxy'; } } catch (e) {}

  // ---------------- data (static snapshots only) ----------------
  function getJSON(u) { return fetch(u, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(u + ' HTTP ' + r.status); return r.json(); }); }
  function load() {
    var crP = root.__crDoc ? Promise.resolve(root.__crDoc) : getJSON('api/control_room.json').catch(function () { return null; });
    var bsP = getJSON('api/block_series.json').catch(function () { return null; });
    return Promise.all([bsP, crP]).then(function (r) {
      var bs = r[0], cr = r[1], by = {};
      if (bs && bs.rows && bs.fields) { var f = bs.fields, ih = f.indexOf('h'), it = f.indexOf('t'), im = f.indexOf('miner'), iq = f.indexOf('bits_q');
        bs.rows.forEach(function (x) { by[x[ih]] = { h: x[ih], t: x[it], m: x[im], bq: iq >= 0 ? x[iq] : null }; }); }
      var db = cr && cr.bundle && cr.bundle.deltaBlocks;
      if (db && db.fields) { var g = db.fields, jh = g.indexOf('height'), jt = g.indexOf('time'), jm = g.indexOf('miner_address'), jq = g.indexOf('bits_q');
        db.rows.forEach(function (x) { by[x[jh]] = { h: x[jh], t: x[jt], m: x[jm], bq: jq >= 0 ? x[jq] : null }; }); }
      var rows = Object.keys(by).map(function (k) { return by[k]; }).filter(function (x) { return x.m; }).sort(function (a, b) { return a.h - b.h; });
      // keep one contiguous run ending at the tip (a gap would make the age rings lie)
      for (var i = rows.length - 1; i > 0; i--) if (rows[i].h - rows[i - 1].h !== 1) { rows = rows.slice(i); break; }
      var prevTip = M.tip; M.recent = rows; M.recentN = rows.length; M.rows = compose(); M.tip = M.rows.length ? M.rows[M.rows.length - 1].h : null;
      if (prevTip && M.tip > prevTip) flash = { h: M.tip, t0: performance.now() };
      M.dt = rows.length > 1 ? (rows[rows.length - 1].t - rows[0].t) / (rows.length - 1) : 600;
      M.src = [bs ? 'block_series.json' : null, cr ? 'control_room.json' : null].filter(Boolean).join(' + ');
      M.at = cr && cr.collected_at ? cr.collected_at : (bs && bs.updated_at) || null;
      // provenance of the snapshot: the collector stores the getinfo of the node it read (profile, genesis hash, height)
      var si = cr && cr.bundle && cr.bundle.info;
      M.snap = { net: si && si.profile ? String(si.profile) : null, gen: si && si.genesis_hash ? String(si.genesis_hash) : null, h: si && si.blocks != null ? +si.blocks : null };
      index();
      M.probeP = probeNode().then(function () { if (!host.classList.contains('loading')) render(); });   // never blocks the snapshot view
    });
  }
  // recent rows, or (GENESIS) the full-chain rows below the first recent height followed by the recent rows up to the tip
  function compose() {
    var r = M.recent, f = M.full;
    if (st.wk !== 'genesis' || !f || !f.length) return r;
    if (!r.length) return f;
    var h0 = r[0].h, last = f[f.length - 1].h;
    if (last < h0 - 1) { M.fullErr = 'the full-chain series ends at #' + fmt(last) + ', before the recent window (#' + fmt(h0) + '): showing the recent window'; return r; }
    var out = []; for (var i = 0; i < f.length && f[i].h < h0; i++) out.push(f[i]);
    return out.concat(r);
  }
  function syncWin() { var N = M.rows.length; st.win = st.wk === 'genesis' ? N : st.wk === 'recent' ? (M.recentN || N) : +st.wk; }
  // windows shown as cards / rings: 24 · 72 · 144 · 288 · all recent (≈1,206) · and, with GENESIS, the full chain
  function WL() { var N = M.rows.length, L = WIN.slice(); if (M.recentN && M.recentN < N) L.push(M.recentN); L.push(N); return L; }
  function wlab(w) { var N = M.rows.length; return w === N && st.wk === 'genesis' && N > M.recentN ? 'genesis · ' + fmt(N) : w === N || w === M.recentN ? 'all ' + fmt(w) : 'last ' + w; }
  function cons(w) { return w === 288 ? ' <em class="xs-cons" title="288 blocks: the consensus reference window (DTD recency, operational reading)">CONSENSUS</em>' : ''; }
  function index() {
    var N = M.rows.length, by = {}, WS = WIN.concat(M.recentN && M.recentN < N ? [M.recentN] : []);
    M.rows.forEach(function (r, i) {
      var p = by[r.m] || (by[r.m] = { a: r.m, n: 0, w: {}, last: 0, first: r.h, hs: [] });
      p.n++; p.last = r.h; p.hs.push(r.h);
      var age = N - 1 - i; for (var k = 0; k < WS.length; k++) if (age < WS[k]) p.w[WS[k]] = (p.w[WS[k]] || 0) + 1;
    });
    syncWin();
    M.byAddr = by;
    M.prod = Object.keys(by).map(function (k) { return by[k]; }).sort(function (a, b) { return b.n - a.n || b.last - a.last; });
    layout();
  }
  // ---------------- GENESIS: full chain on demand (static, 0 RPC) ----------------
  function loadFull() {
    if (M.full || M.fullBusy) return Promise.resolve();
    M.fullBusy = true; M.fullErr = null; M.fullProg = 0; var t0 = performance.now(), t1;
    return fetch('api/block_series_genesis.json', { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      if (!/json/i.test(r.headers.get('content-type') || '')) throw new Error('not published on this server');
      if (!r.body || !r.body.getReader) return r.text();
      var rd = r.body.getReader(), parts = [], n = 0, dec = new TextDecoder();
      function pump() { return rd.read().then(function (x) { if (x.done) return parts.join('') + dec.decode(); n += x.value.length; M.fullProg = n; parts.push(dec.decode(x.value, { stream: true })); radar(); return pump(); }); }
      return pump();
    }).then(function (txt) {
      t1 = performance.now(); var j = JSON.parse(txt), rows = [], t = 0, q = 0, mi = j.miners || [];
      if (!j.t || !j.m || j.t.length !== j.m.length || (j.count != null && j.count !== j.t.length) || (j.tip != null && j.tip !== (j.h0 || 0) + j.t.length - 1)) throw new Error('unexpected format');
      for (var i = 0; i < j.t.length; i++) { t += j.t[i]; q += j.bits_q ? j.bits_q[i] : 0; var m = mi[j.m[i]]; if (m && (j.h0 || 0) + i > 0) rows.push({ h: (j.h0 || 0) + i, t: t, m: m, bq: j.bits_q ? q : null }); }
      for (var k = rows.length - 1; k > 0; k--) if (rows[k].h - rows[k - 1].h !== 1) throw new Error('gap at #' + rows[k].h);
      M.full = rows; M.fullTip = j.tip; M.fullHash = j.tip_hash || null; M.fullCp = j.checkpoints ? Object.keys(j.checkpoints).length : 0;
      M.fullPerf = { bytes: txt.length, fetch_ms: Math.round(t1 - t0), decode_ms: Math.round(performance.now() - t1), rows: rows.length };
    }).catch(function (e) { M.fullErr = 'Full-chain series unavailable (' + (e && e.message || e) + '). The recent window is unchanged.'; if (st.wk === 'genesis') st.wk = 'recent'; })
      .then(function () { M.fullBusy = false; });
  }
  function setWk(k) {
    if (!k) return; st.wk = k;
    try { var u = new URL(location.href); if (k === 'recent') u.searchParams.delete('galaxy'); else u.searchParams.set('galaxy', k === 'recent' ? '1206' : k); history.replaceState(null, '', u.pathname + u.search + u.hash); } catch (e) {}
    var go = function () { var t2 = performance.now(); M.rows = compose(); M.tip = M.rows.length ? M.rows[M.rows.length - 1].h : M.tip; index(); render(); if (M.fullPerf && st.wk === 'genesis') M.fullPerf.layout_render_ms = Math.round(performance.now() - t2); };
    if (k === 'genesis' && !M.full) { var lp = loadFull(); render(); lp.then(go); } else go();   // loadFull() sets the busy flag first: the card shows the loading state
  }
  function rowOf(h) { var r = M.rows[M.rows.length - 1 - (M.tip - h)]; return r && r.h === h ? r : null; }
  // ---------------- selected block: full record from the node, on click only (never on hover), cached per height ----------------
  var BI = {}, biFor = null;
  function rpc(m, p) { return typeof root.rpc === 'function' ? root.rpc(m, p) : fetch('/rpc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: m, params: p }) }).then(function (r) { return r.json(); }).then(function (j) { if (j.error) throw new Error(j.error.message || 'rpc'); return j.result; }); }
  // ---- data provenance (P5): the observatory figures come from the public collector SNAPSHOT; block details come from
  // the CONNECTED NODE (/rpc). They are only combined when both are the same chain (same genesis hash).
  function netName(n) { n = String(n || '').toLowerCase(); return n === 'dev' || n === 'devnet' ? 'DEVNET' : n === 'testnet' ? 'TESTNET' : n === 'mainnet' ? 'MAINNET' : n ? n.toUpperCase() : 'UNKNOWN NETWORK'; }
  function probeNode() {
    var to = new Promise(function (_, rj) { setTimeout(function () { rj(new Error('timeout')); }, 8000); });
    return Promise.race([rpc('getinfo', []), to]).then(function (i) {
      M.node = { ok: true, net: i && i.profile ? String(i.profile) : null, gen: i && i.genesis_hash ? String(i.genesis_hash) : null, h: i && i.blocks != null ? +i.blocks : null };
    }, function () { M.node = { ok: false }; }).then(function () { M.mismatch = nodeMismatch(); });
  }
  // true when the connected node is NOT the chain of the snapshot. Network AND genesis must both agree: a devnet node can
  // share the mainnet genesis block (it does in the lab), so a matching genesis alone proves nothing.
  function nodeMismatch() {
    var s = M.snap || {}, n = M.node || {};
    if (!n.ok) return false;
    if (!s.net || !n.net) return true;   // provenance unknown on one side: never present node data as snapshot data
    if (netName(s.net) !== netName(n.net)) return true;
    return !!(s.gen && n.gen && s.gen !== n.gen);
  }
  function srcStrip() {
    var s = M.snap || {}, n = M.node;
    var at = M.at ? new Date(M.at * 1000).toISOString().slice(0, 16).replace('T', ' ') + 'Z' : '';
    var sb = '<span class="xs-src snap"><b>' + netName(s.net) + '</b> · public collector snapshot (historical) · #' + fmt(M.tip) + (at ? ' · collected ' + at : '') + '</span>';
    var nb = !n ? '<span class="xs-src node dim">connected node: checking…</span>'
           : !n.ok ? '<span class="xs-src node dim">connected node: not reachable (block details unavailable)</span>'
           : '<span class="xs-src node' + (M.mismatch ? ' other' : '') + '"><b>' + netName(n.net) + '</b> · connected node · #' + fmt(n.h) + '</span>';
    var warn = M.mismatch
      ? '<p class="xs-rad-alert xs-src-warn" role="status"><b>Different chains:</b> the connected node is on <b>' + netName(n.net) + '</b>' +
        (s.gen && n.gen && s.gen === n.gen ? ' (same genesis block, different network and rules)' : n.gen ? ' (genesis ' + esc(n.gen.slice(0, 12)) + '…)' : '') +
        ', while every figure of this observatory is the <b>' + netName(s.net) + '</b> collector snapshot' + (s.gen && !(n.gen && s.gen === n.gen) ? ' (genesis ' + esc(s.gen.slice(0, 12)) + '…)' : '') +
        '. Block details are therefore not fetched from this node, and none of its data is shown here.</p>' : '';
    return '<div class="xs-src-row" data-src-mismatch="' + (M.mismatch ? '1' : '0') + '">' + sb + nb + '</div>' + warn;
  }
  function blockInfo(h) {
    biFor = h; if (BI[h] && BI[h].state !== 'error') { detail(); return; }
    if (!M.node && M.probeP) { BI[h] = { state: 'loading' }; detail(); M.probeP.then(function () { delete BI[h]; if (biFor === h) blockInfo(h); }); return; }
    if (M.mismatch) { BI[h] = { state: 'othernet' }; detail(); return; }   // never show another chain's block as this one
    BI[h] = { state: 'loading' }; detail();
    rpc('getblockhash', [String(h)]).then(function (hash) { if (!hash) throw new Error('not found'); return rpc('getblock', [hash]); })
      .then(function (b) { BI[h] = b && b.hash ? { state: 'ready', b: b } : { state: 'notfound' }; }, function (er) { BI[h] = { state: /not found|out of range/i.test(String(er && er.message || er)) ? 'notfound' : 'error', msg: String(er && er.message || er).slice(0, 120) }; })
      .then(function () { if (biFor === h) detail(); });
  }
  function jackpotAt(h) { var E = M.earn, J = E && E.jackpots; if (!J) return null; if (Array.isArray(J)) { for (var i = 0; i < J.length; i++) { var j = J[i]; if (j && (j.height === h || j.h === h || j[0] === h)) return j; } } else if (J[h]) return J[h]; return null; }
  function blockCard(h) {
    var r = rowOf(h); if (!r) return ''; loadEarn();
    var prev = rowOf(h - 1), I = BI[h] || { state: 'idle' }, b = I.b || {}, ok = I.state === 'ready';
    var row = function (k, v) { return '<tr><th scope="row">' + k + '</th><td>' + v + '</td></tr>'; };
    var pend = I.state === 'loading' ? '<span class="dim">loading…</span>' : I.state === 'notfound' ? '<span class="dim">not found on the node</span>' : I.state === 'error' ? '<span class="dim">node unreachable</span>' : I.state === 'othernet' ? '<span class="dim">not queried: the connected node is on ' + netName(M.node && M.node.net) + ', this block is ' + netName(M.snap && M.snap.net) + ' snapshot data</span>' : '—';
    var jp = jackpotAt(h);
    return '<div class="xs-obs-blk" aria-live="polite"><p class="xs-obs-k">Selected block <span class="pv ' + (ok ? 'verified">NODE · ' + netName(M.node && M.node.net) : 'observed">SNAPSHOT · ' + netName(M.snap && M.snap.net)) + '</span></p>' +
      '<table class="xs-obs-kv"><tbody>' +
      row('Height', '<b>#' + fmt(h) + '</b> · ' + (M.tip - h === 0 ? 'the tip' : fmt(M.tip - h) + ' blocks ago')) +
      row('Hash', ok ? '<code class="hash" title="' + esc(b.hash) + '">' + esc(b.hash) + '</code>' : pend) +
      row('Time', new Date(r.t * 1000).toISOString().slice(0, 19).replace('T', ' ') + ' UTC') +
      row('Producer', '<button type="button" class="xs-a" data-a="' + esc(r.m) + '" title="' + esc(r.m) + '"><i style="background:' + col(r.m, 54) + '"></i>' + esc(short(r.m)) + '</button>') +
      row('Miner reward', ok && b.miner_reward != null ? fmt(b.miner_reward / 1e8, 8) + ' SOST' : pend) +
      row('DTD', ok ? (b.lottery_payout ? fmt(b.lottery_payout / 1e8, 8) + ' SOST → ' + (b.lottery_winner_address ? '<a href="sost-explorer.html?search=' + esc(b.lottery_winner_address) + '" data-find="' + esc(b.lottery_winner_address) + '" title="' + esc(b.lottery_winner_address) + '">' + esc(short(b.lottery_winner_address)) + '</a>' : '—') : 'no payout in this block') : pend) +
      row('Jackpot', jp ? '<b>' + fmt((jp.sat || 0) / 1e8, 8) + ' SOST</b>' + (jp.addr ? ' → <a href="sost-explorer.html?search=' + esc(jp.addr) + '" data-find="' + esc(jp.addr) + '" title="' + esc(jp.addr) + '">' + esc(short(jp.addr)) + '</a>' : '') + (jp.txid ? ' · <a href="sost-explorer.html?search=' + esc(jp.txid) + '" data-find="' + esc(jp.txid) + '" title="' + esc(jp.txid) + '">tx ' + esc(jp.txid.slice(0, 10)) + '…</a>' : '') : M.earn && !M.earn.error ? 'no' : M.earn ? '<span class="dim">not verifiable</span>' : '<span class="dim">…</span>') +
      row('Difficulty (bitsQ)', fmt(ok && b.bits_q != null ? b.bits_q : r.bq)) +
      row('Interval', prev ? fmt(r.t - prev.t) + ' s after #' + fmt(prev.h) : '<span class="dim">previous block not loaded</span>') +
      row('Transactions', ok ? fmt(b.tx_count != null ? b.tx_count : (b.txids || []).length) : pend) +
      row('Size', ok ? (b.size != null ? fmt(b.size) + ' bytes' : '<span class="dim">not reported by the node</span>') : pend) +
      '</tbody></table><div class="xs-obs-act">' +
      '<a class="b" href="sost-explorer.html?search=' + h + '" data-find="' + h + '">Open block</a>' +
      '<button type="button" class="b" data-inspect="' + esc(r.m) + '">Inspect producer</button>' +
      '<a class="b" href="sost-explorer.html?search=' + (ok ? esc(b.hash) : h) + '" data-find="' + (ok ? esc(b.hash) : h) + '" title="The block page lists its transactions">View transactions</a>' +
      '<button type="button" class="b copy" data-copy="' + (ok ? esc(b.hash) : '') + '"' + (ok ? '' : ' disabled') + '>Copy hash</button></div></div>';
  }
  function loadEarn() {
    if (M.earn || M.earnBusy) return; M.earnBusy = true;
    getJSON('api/address_earnings.json').then(function (e) { M.earn = e; }).catch(function () { M.earn = { error: true }; }).then(function () { M.earnBusy = false; detail(); if (st.mode === 'table') table(); });
  }

  // ---------------- galaxy geometry (polar, computed once per data load) ----------------
  var P = []; // per block: [rNorm, theta, producerIndex, ageBucket, height]
  function layout() {
    var N = M.rows.length; P = [];
    if (!N) return;
    var start = {}, acc = 0, idx = {};
    M.prod.forEach(function (p, i) { idx[p.a] = i; start[p.a] = acc; acc += p.n / N * Math.PI * 2; });
    M.rows.forEach(function (r, i) {
      var p = M.byAddr[r.m], age = N - 1 - i, rn = Math.sqrt((age + .5) / N);
      var width = p.n / N * Math.PI * 2, f = .12 + .76 * rnd(r.h, 1);
      var th = start[r.m] + f * width + 2.4 * rn;                 // log-spiral twist: arms wind outwards
      rn = Math.min(1, Math.max(.02, rn + (rnd(r.h, 2) - .5) * .018));
      P.push([rn, th, idx[r.m], age < 24 ? 0 : age < 144 ? 1 : age < 288 ? 2 : 3, r.h]);
    });
  }

  // ---------------- canvas ----------------
  var cv = $('#xsGal'), ctx = cv.getContext('2d'), tip = $('#xsGalTip'), W = 0, H = 0, R = 0, dpr = 1, rot = 0, raf = 0, visible = false, over = false, lastT = 0;
  function size() {
    var w = cv.parentNode.clientWidth || 600, h = Math.round(Math.max(w < 600 ? 250 : 340, Math.min(560, w * .62)));
    if (host.classList.contains('xs-fs')) { var top = cv.parentNode.getBoundingClientRect().top - host.getBoundingClientRect().top + host.scrollTop;
      h = Math.max(240, Math.round((root.innerHeight || 700) - top - 12));
      if ((root.innerHeight || 0) > (root.innerWidth || 0)) h = Math.min(h, Math.max(300, Math.round(w * 1.15))); }   // portrait: the disc is width-bound, keep the cards one scroll away
    dpr = Math.min(root.devicePixelRatio || 1, 2); cv.style.height = h + 'px'; cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    W = w; H = h; R = Math.max(80, Math.min(w / 2 - 54, (h / 2 - 14) / TILT)); dust();
    var mz = $('#xsMos'); if (mz) { mz.width = Math.round(w * dpr); }
    if (typeof fxSize === 'function') fxSize();
  }
  var ALPHA = [1, .9, .74, .56], TILT = .6, dustCv = null;
  // static background dust, drawn once per resize into an offscreen canvas (no per-frame cost beyond one drawImage)
  function dust() {
    dustCv = d.createElement('canvas'); dustCv.width = cv.width; dustCv.height = cv.height; var c = dustCv.getContext('2d'); c.scale(dpr, dpr);
    for (var i = 0; i < 260; i++) { var x = rnd(i, 7) * W, y = rnd(i, 9) * H, a = .05 + rnd(i, 11) * .22; c.fillStyle = 'rgba(200,215,255,' + a.toFixed(3) + ')'; c.fillRect(x, y, rnd(i, 13) < .9 ? 1 : 1.6, 1); }
    var g = c.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, R * 1.1); g.addColorStop(0, '#8b5cf614'); g.addColorStop(.5, '#22d3ee08'); g.addColorStop(1, '#0000');
    c.fillStyle = g; c.fillRect(0, 0, W, H);
  }
  function xy(p) { var a = p[1] + rot; return [W / 2 + st.ox + Math.cos(a) * p[0] * R * st.z, H / 2 + st.oy + Math.sin(a) * p[0] * R * TILT * st.z]; } // tilted disc, zoom / pan
  // Stars are drawn once into an offscreen canvas in flat disc coordinates (grouped: one path + one fill per producer and
  // recency bucket) and re-drawn only when the data, the size, the selection or the hover change. Each animation frame is then
  // one drawImage under rotate(rot)·scale(1, TILT): the per-frame cost no longer grows with the number of blocks.
  var starCv = null, starKey = '', HALF = 0;
  function buildStars() {
    var key = [P.length, P.length ? P[P.length - 1][4] : 0, W, H, dpr, st.sel, st.hover].join('|');
    if (key === starKey && starCv) return; starKey = key;
    HALF = R + 12; var side = Math.ceil(HALF * 2 * dpr);
    if (!starCv) starCv = d.createElement('canvas');
    starCv.width = side; starCv.height = side;
    var c = starCv.getContext('2d'); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, HALF * 2, HALF * 2);
    var sel = st.sel, hv = st.hover, groups = {};
    for (var i = 0; i < P.length; i++) { var k = P[i][2] * 4 + P[i][3]; (groups[k] || (groups[k] = [])).push(P[i]); }
    Object.keys(groups).forEach(function (k) {
      var g = groups[k], pi = Math.floor(k / 4), b = k % 4, a = M.prod[pi].a, on = !sel || sel === a, hl = hv === a;
      c.globalAlpha = ALPHA[b] * (on ? 1 : .2);
      c.fillStyle = col(a, b === 0 ? 74 : sel === a ? 70 : 62);
      if ((sel === a || hl) && !RM) { c.shadowColor = col(a, 66); c.shadowBlur = sel === a ? 14 : 9; } else c.shadowBlur = 0;
      var s = (b === 0 ? 4.6 : b === 1 ? 3.4 : b === 2 ? 2.7 : 2.2) * (sel === a ? 1.35 : 1), k2, q2 = [];
      for (k2 = 0; k2 < g.length; k2++) q2.push([HALF + Math.cos(g[k2][1]) * g[k2][0] * R, HALF + Math.sin(g[k2][1]) * g[k2][0] * R]);
      c.beginPath(); for (k2 = 0; k2 < q2.length; k2++) { c.moveTo(q2[k2][0] + s / 2, q2[k2][1]); c.arc(q2[k2][0], q2[k2][1], s / 2, 0, Math.PI * 2); } c.fill();
      // soft halo: the same group again, larger and faint (still one path + one fill)
      c.globalAlpha *= .18; var S = s * 3; c.shadowBlur = 0;
      c.beginPath(); for (k2 = 0; k2 < q2.length; k2++) { c.moveTo(q2[k2][0] + S / 2, q2[k2][1]); c.arc(q2[k2][0], q2[k2][1], S / 2, 0, Math.PI * 2); } c.fill();
    });
    c.globalAlpha = 1; c.shadowBlur = 0;
  }
  function span(w) { var s = (M.dt || 600) * w; return s < 5400 ? '≈' + Math.round(s / 60) + ' min' : s < 172800 ? '≈' + Math.round(s / 3600) + ' h' : '≈' + Math.round(s / 86400) + ' d'; }
  function drawGalaxy() {
    var c = ctx; c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, cv.width, cv.height); if (dustCv) c.drawImage(dustCv, 0, 0);
    var N = M.rows.length; if (!N) { c.setTransform(dpr, 0, 0, dpr, 0, 0); c.fillStyle = '#5f6b7a'; c.font = '12px ui-monospace,monospace'; c.fillText('No block snapshot available.', 16, 24); return; }
    // zoom / pan: everything below is drawn around the (moved) centre at scale st.z
    c.setTransform(dpr * st.z, 0, 0, dpr * st.z, dpr * (W / 2 + st.ox - W / 2 * st.z), dpr * (H / 2 + st.oy - H / 2 * st.z));
    // age rings: 24 / 72 / 144 / 288 / all loaded (radius = sqrt(blocks ago / N))
    c.lineWidth = 1; c.font = '10px ui-monospace,monospace';
    var lastLX = -1e9, LA = -.5;
    WL().forEach(function (w) {
      var rr = Math.sqrt(Math.min(w, N) / N) * R, on = w === st.win;
      // inner reference rings in the same cyan as the outer one (a faint 3 px glow under a 1 px line); the selected window stays the strongest
      if (!on) { c.strokeStyle = '#22d3ee12'; c.lineWidth = 3; c.beginPath(); c.ellipse(W / 2, H / 2, rr, rr * TILT, 0, 0, Math.PI * 2); c.stroke(); c.lineWidth = 1; }
      c.strokeStyle = on ? '#22d3ee55' : '#22d3ee3a';
      var lx = W / 2 + Math.cos(LA) * rr, ly = H / 2 + Math.sin(LA) * rr * TILT, lbl = (w === N ? (st.wk === 'genesis' && N > M.recentN ? 'genesis · ' : '') + fmt(N) + ' blocks' : w === M.recentN ? 'all ' + fmt(w) : 'last ' + w + (w === 288 ? ' · consensus' : '')) + ' · ' + span(Math.min(w, N));
      c.beginPath(); c.ellipse(W / 2, H / 2, rr, rr * TILT, 0, 0, Math.PI * 2); c.stroke();
      c.fillStyle = on ? '#22d3eeee' : '#bfeaf5b8'; if (lx - lastLX > 34 / st.z || w === st.win) { c.font = (10.5 / st.z).toFixed(2) + 'px ui-monospace,monospace'; c.fillText(lbl, Math.min(lx + 3 / st.z, W / 2 + (W / 2 - 4 - st.ox) / st.z - c.measureText(lbl).width), ly - 3 / st.z); lastLX = lx; }
    });
    var core = c.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, R * .22);
    core.addColorStop(0, '#fff8'); core.addColorStop(.25, '#e879f933'); core.addColorStop(1, '#0000');
    c.fillStyle = core; c.beginPath(); c.ellipse(W / 2, H / 2, R * .22, R * .22 * TILT, 0, 0, Math.PI * 2); c.fill();
    buildStars();
    c.save(); c.translate(W / 2, H / 2); c.scale(1, TILT); c.rotate(rot); c.drawImage(starCv, -HALF, -HALF, HALF * 2, HALF * 2); c.restore();
    // tip: pulsing ring at the core
    c.setTransform(dpr, 0, 0, dpr, 0, 0);   // markers in screen space (xy() already applies zoom / pan)
    var ph = RM ? .5 : (performance.now() / 1600) % 1, last = P[P.length - 1], q = xy(last);
    c.strokeStyle = col(M.rows[N - 1].m, 70); c.globalAlpha = 1 - ph; c.beginPath(); c.arc(q[0], q[1], 3 + ph * 12, 0, Math.PI * 2); c.stroke(); c.globalAlpha = 1;
    pulsar();
    lens();
    // new block that arrived with the last refresh: a short bright flash and its height (static marker with reduced motion)
    if (flash) { var fp = null; for (var fi = P.length - 1; fi >= 0 && fi >= P.length - 3; fi--) if (P[fi][4] === flash.h) fp = P[fi];
      var ft = RM ? .4 : (performance.now() - flash.t0) / 2600;
      if (fp && ft < 1) { var fq = xy(fp); c.globalAlpha = 1 - ft; c.strokeStyle = '#fff6e8'; c.lineWidth = 2; c.beginPath(); c.arc(fq[0], fq[1], 4 + ft * 30, 0, Math.PI * 2); c.stroke();
        c.fillStyle = '#fff6e8'; c.font = '600 11px ui-monospace,monospace'; c.fillText('NEW BLOCK #' + fmt(flash.h), fq[0] + 10, fq[1] - 10); c.globalAlpha = 1; c.lineWidth = 1; }
      else if (!RM) flash = null; }
    // selected block: a ring around its star
    // selected block (clicked star) or, for a producer chosen elsewhere, its newest block in the window: a white ring
    var mk = st.blk != null ? st.blk : st.sel && M.byAddr[st.sel] ? M.byAddr[st.sel].last : null;
    if (mk != null) { for (var bi = P.length - 1; bi >= 0; bi--) if (P[bi][4] === mk) { var bq = xy(P[bi]); c.strokeStyle = '#ffffff'; c.lineWidth = 1.5; c.beginPath(); c.arc(bq[0], bq[1], 7, 0, Math.PI * 2); c.stroke();
      c.globalAlpha = .45; c.beginPath(); c.arc(bq[0], bq[1], 12, 0, Math.PI * 2); c.stroke(); c.globalAlpha = 1; c.lineWidth = 1; break; } }
  }
  // GENESIS view: the origin of the chain breathes like a pulsar (soft halo, two faint slowly turning beams, a label).
  // Block #0 has no coinbase and is not a star; the marker sits on the first mined block (#1), the outermost star.
  // Pure decoration in screen space: it never changes positions, selection or hit testing. Reduced motion: static.
  function pulsar() {
    if (st.wk !== 'genesis' || !P.length || P[0][4] > 1) return;
    var c = ctx, q = xy(P[0]), now = performance.now(), b = RM ? .5 : Math.pow(.5 + .5 * Math.sin(now / 2400 * Math.PI * 2), 1.6);
    var zz = Math.min(1.6, Math.sqrt(st.z)), hr = (20 + 8 * b) * zz, g = c.createRadialGradient(q[0], q[1], 0, q[0], q[1], hr);
    g.addColorStop(0, 'rgba(240,252,255,' + (.7 + .3 * b).toFixed(3) + ')'); g.addColorStop(.16, 'rgba(160,236,252,' + (.4 + .25 * b).toFixed(3) + ')'); g.addColorStop(.5, 'rgba(34,211,238,' + (.1 + .08 * b).toFixed(3) + ')'); g.addColorStop(1, 'rgba(34,211,238,0)');
    c.fillStyle = g; c.beginPath(); c.arc(q[0], q[1], hr, 0, Math.PI * 2); c.fill();
    var a = RM ? .6 : now / 7000, bl = (24 + 10 * b) * zz, k, ex, ey, lg;
    for (k = 0; k < 2; k++) { ex = Math.cos(a + k * Math.PI) * bl; ey = Math.sin(a + k * Math.PI) * bl * .55;
      lg = c.createLinearGradient(q[0], q[1], q[0] + ex, q[1] + ey); lg.addColorStop(0, 'rgba(215,247,255,' + (.5 + .3 * b).toFixed(3) + ')'); lg.addColorStop(1, 'rgba(210,245,255,0)');
      c.strokeStyle = lg; c.lineWidth = 1.3; c.beginPath(); c.moveTo(q[0], q[1]); c.lineTo(q[0] + ex, q[1] + ey); c.stroke(); }
    if (!RM) { var ph = (now / 2400 + .25) % 1; c.strokeStyle = 'rgba(160,236,252,' + (.32 * (1 - ph)).toFixed(3) + ')'; c.lineWidth = 1; c.beginPath(); c.ellipse(q[0], q[1], (5 + ph * 26) * zz, (5 + ph * 26) * zz * .7, 0, 0, Math.PI * 2); c.stroke(); }   // one soft pulse per beat
    c.lineWidth = 1; c.fillStyle = '#ffffff'; c.beginPath(); c.arc(q[0], q[1], 2.3 * zz, 0, Math.PI * 2); c.fill();
    c.font = '600 10.5px ui-monospace,monospace'; c.fillStyle = 'rgba(214,246,255,' + (.72 + .2 * b).toFixed(3) + ')';
    var lab = 'GENESIS', lx = q[0] + 12, ly = q[1] - 9; if (lx + c.measureText(lab).width > W - 4) lx = q[0] - 12 - c.measureText(lab).width; c.fillText(lab, lx, Math.max(12, ly));
  }
  // meteor graze (FX layer, only when FX are allowed): a small meteor crosses an outer arm; the stars right under its head are
  // lensed (magnified and pushed along its path for a moment) and settle back as it passes. It copies a small patch of the
  // already drawn frame onto itself, so no star, position, selection or hit test is modified.
  var lensCv = null, lensCv2 = null;
  function lens() {
    if (typeof FX !== 'object' || !FX.items.length) return;
    var c = ctx, now = performance.now();
    FX.items.forEach(function (o) {
      if (o.k !== 'graze') return; var p = (now - o.t0) / o.dur; if (p <= 0 || p >= 1) return;
      var fade = Math.sin(Math.PI * p), hx = o.x + (o.x1 - o.x) * p, hy = o.y + (o.y1 - o.y) * p, dx = o.x1 - o.x, dy = o.y1 - o.y, m = Math.sqrt(dx * dx + dy * dy) || 1;
      [[0, 1], [-.06, .55]].forEach(function (t) {   // at the head, and a weaker wake behind it
        var cx = hx + dx * t[0], cy = hy + dy * t[0], L = 22, k = .14 * fade * t[1], sh = 3.2 * fade * t[1], n = Math.ceil(2 * L * dpr), sx = Math.round((cx - L) * dpr), sy = Math.round((cy - L) * dpr);
        // the patch REPLACES the frame with a feathered mask (orig·(1−m) + lensed·m): never drawn on top, so the semi-transparent
        // background is not doubled and no disc outline can appear
        if (!lensCv) { lensCv = d.createElement('canvas'); lensCv2 = d.createElement('canvas'); }
        if (lensCv.width !== n) { lensCv.width = lensCv.height = lensCv2.width = lensCv2.height = n; }
        var a1 = lensCv.getContext('2d'), a2 = lensCv2.getContext('2d'), mid = n / 2, mg;
        a1.setTransform(1, 0, 0, 1, 0, 0); a1.clearRect(0, 0, n, n); a1.drawImage(cv, sx, sy, n, n, 0, 0, n, n);
        a2.setTransform(1, 0, 0, 1, 0, 0); a2.globalCompositeOperation = 'source-over'; a2.clearRect(0, 0, n, n);
        var zs = 1 + k, ox = (dx / m) * sh * dpr, oy = (dy / m) * sh * dpr;
        a2.drawImage(lensCv, mid - mid * zs + ox, mid - mid * zs + oy, n * zs, n * zs);
        mg = a2.createRadialGradient(mid, mid, 0, mid, mid, mid); mg.addColorStop(0, 'rgba(0,0,0,1)'); mg.addColorStop(.55, 'rgba(0,0,0,.85)'); mg.addColorStop(1, 'rgba(0,0,0,0)');
        a2.globalCompositeOperation = 'destination-in'; a2.fillStyle = mg; a2.fillRect(0, 0, n, n); a2.globalCompositeOperation = 'source-over';
        c.save(); c.setTransform(1, 0, 0, 1, 0, 0);
        mg = c.createRadialGradient(sx + mid, sy + mid, 0, sx + mid, sy + mid, mid); mg.addColorStop(0, 'rgba(0,0,0,1)'); mg.addColorStop(.55, 'rgba(0,0,0,.85)'); mg.addColorStop(1, 'rgba(0,0,0,0)');
        c.globalCompositeOperation = 'destination-out'; c.fillStyle = mg; c.fillRect(sx, sy, n, n);
        c.globalCompositeOperation = 'source-over'; c.drawImage(lensCv2, sx, sy); c.restore();
      });
      var tl = 46, tx = hx - dx / m * tl, ty = hy - dy / m * tl, g = c.createLinearGradient(hx, hy, tx, ty);
      g.addColorStop(0, 'rgba(255,236,210,' + (.75 * fade).toFixed(3) + ')'); g.addColorStop(1, 'rgba(255,236,210,0)');
      c.strokeStyle = g; c.lineWidth = 1.4; c.lineCap = 'round'; c.beginPath(); c.moveTo(hx, hy); c.lineTo(tx, ty); c.stroke(); c.lineCap = 'butt'; c.lineWidth = 1;
    });
  }
  function frame(t) {
    raf = 0;
    if (!visible || d.hidden || st.mode !== 'galaxy') return;
    if (t - lastT >= 33) { if (!over && !RM) rot += .0009 * Math.min(4, (t - lastT) / 16.7); lastT = t; drawGalaxy(); }
    if (!RM) raf = requestAnimationFrame(frame);
  }
  function kick() { if (!raf && st.mode === 'galaxy') { if (RM) drawGalaxy(); else raf = requestAnimationFrame(frame); } }
  // hit testing in canvas CSS px (xy() = the same transform the stars are drawn with: rotation, tilt, zoom, pan; the backing store
  // is W·dpr but every coordinate here is CSS px, like pos()). Radius 14 px with a mouse, 22 px with touch / pen: small, old
  // stars are as selectable as the large recent ones.
  var coarse = false;
  function near(ex, ey, rad) {
    var r2 = rad * rad, o = [];
    for (var i = 0; i < P.length; i++) { var q = xy(P[i]), dx = q[0] - ex, dy = q[1] - ey, dd = dx * dx + dy * dy; if (dd < r2) o.push([dd, P[i]]); }
    return o.sort(function (a, b) { return a[0] - b[0]; });
  }
  function nearest(ex, ey) { var o = near(ex, ey, coarse ? 22 : 14); return o.length ? o[0][1] : null; }
  // stars closer than this to the best one cannot be told apart by a pointer: offer a choice instead of guessing
  function ambiguous(ex, ey) {
    var o = near(ex, ey, coarse ? 22 : 14); if (o.length < 2) return o.length ? [o[0][1]] : [];
    var d0 = Math.sqrt(o[0][0]), tie = coarse ? 4 : 1.5;   // CSS px: stars whose distances differ by less cannot be told apart by this pointer
    return o.filter(function (x) { return Math.sqrt(x[0]) - d0 <= tie; }).slice(0, 10).map(function (x) { return x[1]; });
  }
  function pos(e, el) { var r = el.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
  function showTip(x, y, h) {
    var r = M.rows[M.rows.length - 1 - (M.tip - h)]; if (!r) { tip.hidden = true; return; }
    var age = M.tip - h;
    var pr = M.byAddr[r.m];
    tip.innerHTML = '<b>Block #' + fmt(h) + '</b> · ' + (age === 0 ? 'the tip' : fmt(age) + ' blocks ago') + '<br>' + new Date(r.t * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' +
      '<br>producer <span style="color:' + col(r.m, 66) + '">' + esc(short(r.m)) + '</span> · ' + fmt(pr ? pr.w[288] || 0 : 0) + ' of the last 288<br><span style="opacity:.7">click: inspect this producer and block</span>';
    tip.hidden = false; tip.style.left = Math.min(x + 14, cv.parentNode.clientWidth - 220) + 'px'; tip.style.top = (y + 14) + 'px';
  }
  var drag = null;
  cv.addEventListener('pointerdown', function (e) { coarse = e.pointerType === 'touch' || e.pointerType === 'pen'; hideChooser(); drag = { x: e.clientX, y: e.clientY, ox: st.ox, oy: st.oy, moved: false }; });
  addEventListener('pointerup', function () { setTimeout(function () { drag = null; }, 0); });
  cv.addEventListener('pointermove', function (e) {
    if (drag && (e.buttons & 1) && (st.z > 1 || e.pointerType === 'mouse')) { var dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
      if (drag.moved) { st.ox = drag.ox + dx; st.oy = drag.oy + dy; clampView(); tip.hidden = true; cv.style.cursor = 'grabbing'; drawGalaxy(); return; } }
    over = true; var p = pos(e, cv), n = nearest(p[0], p[1]);
    st.hover = n ? M.prod[n[2]].a : null; cv.style.cursor = n ? 'pointer' : 'default';
    if (n) showTip(p[0], p[1], n[4]); else tip.hidden = true;
    if (RM) drawGalaxy();
  });
  cv.addEventListener('pointerleave', function () { over = false; st.hover = null; tip.hidden = true; if (RM) drawGalaxy(); });
  cv.addEventListener('click', function (e) {
    if (drag && drag.moved) return; var p = pos(e, cv), c = ambiguous(p[0], p[1]);
    if (c.length > 1) { chooser(p[0], p[1], c); return; }
    pickBlock(c.length ? c[0][4] : null);
  });
  cv.style.touchAction = 'pan-y';
  function pickBlock(h) {   // a star = one block: select the block AND its producer
    hideChooser(); var r = h == null ? null : rowOf(h);
    if (!r) { st.blk = null; select(null); return; }
    st.pin = false; select(r.m, true, r.h); blockInfo(r.h);
  }
  // overlapping stars: a small list next to the pointer, one button per block (keyboard reachable), plus "zoom here"
  var ch = d.createElement('div'); ch.className = 'xs-obs-ch'; ch.hidden = true; ch.setAttribute('role', 'dialog'); ch.setAttribute('aria-label', 'Several blocks here'); cv.parentNode.appendChild(ch);
  function hideChooser() { if (!ch.hidden) ch.hidden = true; }
  function chooser(x, y, list) {
    tip.hidden = true;
    ch.innerHTML = '<p>' + list.length + ' blocks overlap here · choose one</p>' + list.map(function (q) { var r = rowOf(q[4]); return '<button type="button" data-h="' + q[4] + '"><i style="background:' + col(r.m, 60) + '"></i><b>#' + fmt(q[4]) + '</b> <span>' + esc(short(r.m)) + ' · ' + (M.tip - q[4] === 0 ? 'tip' : fmt(M.tip - q[4]) + ' ago') + '</span></button>'; }).join('') +
      '<button type="button" class="z" data-zx="' + x.toFixed(1) + '" data-zy="' + y.toFixed(1) + '">Zoom in here ×2</button>';
    ch.hidden = false; ch.style.left = Math.max(4, Math.min(x + 12, cv.parentNode.clientWidth - 250)) + 'px'; ch.style.top = Math.max(4, Math.min(y + 12, cv.clientHeight - ch.offsetHeight - 4)) + 'px';
    var f = ch.querySelector('button'); if (f) try { f.focus({ preventScroll: true }); } catch (e) {}
  }
  ch.addEventListener('click', function (e) { e.stopPropagation(); var b = e.target.closest('button'); if (!b) return;
    if (b.hasAttribute('data-zx')) { hideChooser(); zoomBy(2, +b.getAttribute('data-zx'), +b.getAttribute('data-zy')); return; }
    pickBlock(+b.getAttribute('data-h')); });
  ch.addEventListener('keydown', function (e) { if (e.key === 'Escape') { hideChooser(); cv.focus(); } });
  function clampView() { var m = (st.z - 1) * Math.max(W, H) / 2 + Math.max(W, H) * .3; st.ox = Math.max(-m, Math.min(m, st.ox)); st.oy = Math.max(-m, Math.min(m, st.oy)); }
  function zoomBy(f, cx, cy) { var z = Math.max(1, Math.min(8, st.z * f)), k = z / st.z; if (cx == null) { cx = W / 2; cy = H / 2; }
    st.ox = cx - W / 2 - (cx - W / 2 - st.ox) * k; st.oy = cy - H / 2 - (cy - H / 2 - st.oy) * k; st.z = z; clampView(); drawGalaxy(); var zl = $('#xsGalZl'); if (zl) zl.textContent = '×' + st.z.toFixed(1); }
  // zoom: buttons, Ctrl/⌘ + wheel or trackpad pinch (plain wheel keeps scrolling the page)
  cv.addEventListener('wheel', function (e) { if (!(e.ctrlKey || e.metaKey)) return; e.preventDefault(); var p = pos(e, cv); zoomBy(e.deltaY < 0 ? 1.18 : 1 / 1.18, p[0], p[1]); }, { passive: false });
  var zc = d.createElement('div'); zc.className = 'xs-obs-zoom'; zc.setAttribute('role', 'group'); zc.setAttribute('aria-label', 'Zoom');
  zc.innerHTML = '<button type="button" data-z="in" aria-label="Zoom in">+</button><button type="button" data-z="out" aria-label="Zoom out">−</button><button type="button" data-z="reset" aria-label="Reset view">Reset</button><span id="xsGalZl">×1.0</span>' +
    '<button type="button" data-fs aria-pressed="false" aria-label="Enter full screen">⛶ Full screen</button><button type="button" data-panel aria-pressed="true" aria-label="Show or hide the producer panel">Panel</button>' +
    '<button type="button" data-fx aria-label="Decorative effects: auto">FX: AUTO</button>';
  cv.parentNode.appendChild(zc);
  zc.addEventListener('click', function (e) { var b = e.target.closest('[data-z]'); if (!b) return; var k = b.getAttribute('data-z');
    hideChooser(); if (k === 'reset') { st.z = 1; st.ox = st.oy = 0; drawGalaxy(); $('#xsGalZl').textContent = '×1.0'; } else zoomBy(k === 'in' ? 1.5 : 1 / 1.5); });
  // keyboard: the canvas is focusable; arrows walk the blocks (older / newer), Enter opens the selected block
  cv.tabIndex = 0;
  cv.addEventListener('keydown', function (e) {
    if (!M.rows.length) return; var h = st.blk != null ? st.blk : M.tip;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') { e.preventDefault(); pickBlock(Math.max(M.rows[0].h, h - 1)); }
    else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') { e.preventDefault(); pickBlock(Math.min(M.tip, h + 1)); }
    else if (e.key === 'Home') { e.preventDefault(); pickBlock(M.tip); }
    else if (e.key === 'Enter' && st.blk != null) { e.preventDefault(); find(st.blk); }
  });

  // ---------------- MOSAIC (one canvas, one fill per producer) ----------------
  var mz = $('#xsMos'), mctx = mz.getContext('2d'), mCols = 60, mCell = 10;
  function drawMosaic() {
    var w = mz.parentNode.clientWidth || 600, N = M.rows.length; mCols = Math.max(w < 600 ? 30 : 60, Math.ceil(N / 240)); mCell = Math.max(1, Math.floor(w / mCols));   // full chain: more columns, height ≤ 240 rows
    var rowsN = Math.ceil(N / mCols), h = rowsN * mCell; mz.style.height = h + 'px'; mz.style.width = (mCell * mCols) + 'px';
    mz.width = Math.round(mCell * mCols * dpr); mz.height = Math.round(h * dpr);
    var c = mctx; c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h);
    var g = {}; M.rows.forEach(function (r, i) { (g[r.m] || (g[r.m] = [])).push(i); });
    Object.keys(g).forEach(function (a) {
      c.globalAlpha = !st.sel || st.sel === a ? 1 : .14; c.fillStyle = col(a, 54); c.beginPath();
      g[a].forEach(function (i) { c.rect((i % mCols) * mCell + .5, Math.floor(i / mCols) * mCell + .5, mCell - 1.5, mCell - 1.5); }); c.fill();
    });
    c.globalAlpha = 1;
    $('#xsMosNote').textContent = 'Oldest top-left → tip bottom-right · ' + mCols + ' blocks per row · ' + fmt(N) + ' blocks (#' + fmt(M.rows[0] && M.rows[0].h) + ' – #' + fmt(M.tip) + ')';
  }
  function mIdx(e) { var p = pos(e, mz), i = Math.floor(p[1] / mCell) * mCols + Math.floor(p[0] / mCell); return i >= 0 && i < M.rows.length && p[0] < mCols * mCell ? i : -1; }
  mz.addEventListener('pointermove', function (e) { var i = mIdx(e), mt = $('#xsMosTip'); if (i < 0) { mt.hidden = true; return; } var r = M.rows[i], p = pos(e, mz);
    mt.innerHTML = '<b>#' + fmt(r.h) + '</b> · ' + esc(short(r.m)) + ' · ' + fmt(M.tip - r.h) + ' blocks ago'; mt.hidden = false; mt.style.left = Math.min(p[0] + 12, mz.parentNode.clientWidth - 220) + 'px'; mt.style.top = (p[1] + 14) + 'px'; });
  mz.addEventListener('pointerleave', function () { $('#xsMosTip').hidden = true; });
  mz.addEventListener('click', function (e) { var i = mIdx(e); if (i >= 0) pickBlock(M.rows[i].h); });

  // ---------------- CHARTS (SVG bars: share of the chosen window) ----------------
  function TW() { return WIN.concat(M.recentN && M.recentN < M.rows.length ? [M.recentN] : []); }
  function winCount(p, w) { return w >= M.rows.length ? p.n : (p.w[w] || 0); }
  function charts() {
    var w = st.win, N = Math.min(w, M.rows.length), list = M.prod.map(function (p) { return [p, winCount(p, w)]; }).filter(function (x) { return x[1] > 0; }).sort(function (a, b) { return b[1] - a[1]; });
    var top = list.slice(0, 14), rest = list.slice(14), restN = rest.reduce(function (s, x) { return s + x[1]; }, 0), max = top.length ? top[0][1] : 1;
    var rowH = 26, Wd = 860, h = (top.length + (rest.length ? 1 : 0)) * rowH + 8, lab = 170;
    var svg = '<svg viewBox="0 0 ' + Wd + ' ' + h + '" role="img" aria-label="Blocks per producer address in the last ' + N + ' blocks" class="xs-obs-bars">';
    top.forEach(function (x, i) { var p = x[0], bw = (Wd - lab - 120) * x[1] / max, y = i * rowH + 4, on = !st.sel || st.sel === p.a;
      svg += '<g class="bar" data-a="' + esc(p.a) + '" opacity="' + (on ? 1 : .3) + '" style="cursor:pointer"><title>' + esc(p.a) + '</title><text x="0" y="' + (y + 15) + '">' + esc(short(p.a)) + '</text>' +
        '<rect x="' + lab + '" y="' + (y + 3) + '" width="' + Math.max(1, bw).toFixed(1) + '" height="16" rx="3" fill="' + col(p.a, 54) + '"/>' +
        '<text x="' + (lab + bw + 8).toFixed(1) + '" y="' + (y + 15) + '" class="v">' + fmt(x[1]) + ' · ' + pct(x[1], N) + '</text></g>'; });
    if (rest.length) { var y = top.length * rowH + 4; svg += '<text x="0" y="' + (y + 15) + '" class="dim">' + rest.length + ' other addresses</text><text x="' + lab + '" y="' + (y + 15) + '" class="v">' + fmt(restN) + ' · ' + pct(restN, N) + '</text>'; }
    svg += '</svg>';
    $('#xsCharts').innerHTML = (list.length ? svg : '<p class="dim">No blocks in this window.</p>') +
      '<p class="xs-obs-note">Blocks found by each address in the last ' + fmt(N) + ' blocks (#' + fmt(M.tip - N + 1) + ' – #' + fmt(M.tip) + '). Bar length = block count; label = count · share of the window. ' + list.length + ' distinct producer addresses.</p>';
  }
  $('#xsCharts').addEventListener('click', function (e) { var g = e.target.closest('g.bar'); if (g) select(g.getAttribute('data-a')); });

  // ---------------- TABLE (always available; sortable; filter) ----------------
  function earnOf(a) { var E = M.earn; if (!E || !E.addresses || !E.fields) return null; var r = E.addresses[a]; if (!r) return null; var o = {}; E.fields.forEach(function (f, i) { o[f] = r[i]; }); return o; }
  function table() {
    loadEarn();
    var f = st.filter.toLowerCase(), N = M.rows.length, key = st.sort[0], dir = st.sort[1];
    var val = function (p) { if (key === 'a') return p.a; if (key === 'last') return p.last; if (key === 'all') return p.n; if (key === 'mined') { var e = earnOf(p.a); return e ? e.mining_blocks : -1; } if (key === 's288') return p.w[288] || 0; return p.w[+key.slice(1)] || 0; };
    var list = M.prod.filter(function (p) { return !f || p.a.toLowerCase().indexOf(f) >= 0; }).sort(function (a, b) { var x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * dir || b.last - a.last; });
    var th = function (k, t, tl) { return '<th scope="col"><button type="button" data-sort="' + k + '"' + (tl ? ' title="' + esc(tl) + '"' : '') + '>' + t + (key === k ? (dir < 0 ? ' ▾' : ' ▴') : '') + '</button></th>'; };
    var h = '<table class="xs-obs-tbl"><thead><tr>' + th('a', 'Producer address') + TW().map(function (w) { return th('n' + w, fmt(w), 'Blocks in the last ' + w + ' blocks'); }).join('') + th('all', fmt(N), 'Blocks in all loaded blocks') +
      th('s288', 'Share 288') + th('last', 'Last block') + th('mined', 'Mined since genesis', 'Collector snapshot api/address_earnings.json: blocks and miner reward credited to this address since genesis') + '</tr></thead><tbody>';
    list.forEach(function (p) {
      var e = earnOf(p.a);
      h += '<tr' + (st.sel === p.a ? ' class="on"' : '') + '><td><button type="button" class="xs-a" data-a="' + esc(p.a) + '"><i style="background:' + col(p.a, 54) + '"></i>' + esc(p.a) + '</button></td>' +
        TW().map(function (w) { return '<td>' + fmt(p.w[w] || 0) + '</td>'; }).join('') + '<td>' + fmt(p.n) + '</td><td>' + pct(p.w[288] || 0, Math.min(288, N)) + '</td>' +
        '<td><a href="#" data-find="' + p.last + '">#' + fmt(p.last) + '</a></td><td>' + (e ? fmt(e.mining_blocks) + ' blk · ' + fmt(e.mining_sat / 1e8, 2) + ' SOST' : M.earn ? '—' : '…') + '</td></tr>';
    });
    h += '</tbody></table>';
    $('#xsTable').innerHTML = list.length ? h : '<p class="dim">No producer address matches “' + esc(st.filter) + '”.</p>';
  }
  $('#xsTable').addEventListener('click', function (e) {
    var b = e.target.closest('button[data-sort]'); if (b) { var k = b.getAttribute('data-sort'); st.sort = [k, st.sort[0] === k ? -st.sort[1] : (k === 'a' ? 1 : -1)]; table(); return; }
    var a = e.target.closest('button.xs-a'); if (a) { select(a.getAttribute('data-a')); return; }
  });

  // ---------------- detail card of the selected producer ----------------
  function detail() {
    var el = $('#xsObsDet'), a = st.sel, p = a && M.byAddr[a], N = M.rows.length;
    if (!p) {
      el.innerHTML = '<p class="xs-obs-k">Producer</p><p class="dim">Select a star, a mosaic cell, a bar or a table row to inspect one producer address.</p>' +
        '<p class="xs-obs-k">Loaded window' + (st.wk === 'genesis' && M.full ? ' <span class="pv verified">GENESIS</span>' : '') + '</p><p>' + fmt(N) + ' blocks · #' + fmt(M.rows[0] && M.rows[0].h) + ' – #' + fmt(M.tip) + ' · ' + M.prod.length + ' producer addresses' + (st.wk === 'genesis' && M.full ? ' · genesis block #0 (initial allocation, not mined) not counted' + (M.fullHash ? ' · series anchored to block #' + fmt(M.fullTip) + ' hash <code title="' + esc(M.fullHash) + '">' + esc(M.fullHash.slice(0, 16)) + '…</code>' + (M.fullCp ? ' + ' + M.fullCp + ' checkpoint hashes (every 1,000 blocks)' : '') : '') : '') + '</p>' +
        '<ol class="xs-obs-top">' + M.prod.slice(0, 8).map(function (q) { return '<li><button type="button" class="xs-a" data-a="' + esc(q.a) + '"><i style="background:' + col(q.a, 54) + '"></i>' + esc(short(q.a)) + '</button><span>' + fmt(q.w[288] || 0) + ' / 288</span></li>'; }).join('') + '</ol>';
      return;
    }
    loadEarn();
    var e = earnOf(a), hs = p.hs.slice(-10).reverse(), sb = st.blk != null && rowOf(st.blk) && rowOf(st.blk).m === a ? st.blk : null;
    var wN = Math.min(st.win, N);
    el.innerHTML = (sb != null ? blockCard(sb) : '') +
      '<p class="xs-obs-k">' + (sb != null ? 'Producer of block #' + fmt(sb) : 'Pinned address') + ' <span class="pv observed">OBSERVED</span></p>' +
      '<p class="xs-obs-addr"><i style="background:' + col(a, 54) + '"></i><code>' + esc(a) + '</code> <button type="button" class="copy" data-copy="' + esc(a) + '">Copy</button></p>' +
      '<div class="xs-obs-wins">' + WL().map(function (w) { var n = winCount(p, w), m = Math.min(w, N); return '<div' + (w === st.win ? ' class="on"' : '') + '><span>' + wlab(w) + cons(w) + '</span><b>' + fmt(n) + '</b><small>' + pct(n, m) + '</small></div>'; }).join('') + '</div>' +
      '<p class="xs-obs-k">Attributed blocks in the loaded window</p><p>' + fmt(p.n) + ' of ' + fmt(N) + ' · first #' + fmt(p.first) + ' · <b>last #' + fmt(p.last) + '</b> (' + (M.tip - p.last === 0 ? 'the tip' : fmt(M.tip - p.last) + ' blocks ago') + ')</p>' +
      '<p class="xs-obs-k">Latest blocks</p><p class="xs-obs-hs">' + hs.map(function (h) { return '<a href="#" data-find="' + h + '">#' + fmt(h) + '</a>'; }).join(' ') + '</p>' +
      '<p class="xs-obs-k">Observed rewards <span class="pv verified">COLLECTOR</span></p><p>' +
        (e ? fmt(e.mining_blocks) + ' blocks · ' + fmt(e.mining_sat / 1e8, 4) + ' SOST miner reward since genesis' + (e.dtd_normal_wins ? ' · DTD ' + fmt(e.dtd_normal_wins) + ' wins / ' + fmt(e.dtd_normal_sat / 1e8, 4) + ' SOST' : '') + (e.dtd_jackpot_wins ? ' · Jackpot ' + fmt(e.dtd_jackpot_wins) + ' / ' + fmt(e.dtd_jackpot_sat / 1e8, 4) + ' SOST' : '') +
          '<br><small class="dim">api/address_earnings.json, block by block up to #' + fmt(M.earn.tip) + '</small>'
         : M.earn ? '<span class="dim">Not verifiable from the snapshot for this address.</span>' : '<span class="dim">loading…</span>') + '</p>' +
      '<p class="xs-obs-k">Active interval</p><p>' + (wN === N && st.wk === 'genesis' ? 'full chain' : 'last') + ' ' + fmt(wN) + ' blocks · #' + fmt(M.tip - wN + 1) + ' – #' + fmt(M.tip) + ' · this address: <b>' + fmt(winCount(p, st.win)) + '</b> (' + pct(winCount(p, st.win), wN) + ')</p>' +
      '<p class="xs-obs-links"><a href="#xsObsInsp" data-insp="1"><b>Inspect address ↓</b> balance, UTXO, transactions, rewards, NODE_BIND</a><a href="sost-explorer.html?search=' + esc(a) + '" target="_blank" rel="noopener">Full address page ↗</a><a href="sost-explorer.html?search=' + p.last + '" data-find="' + p.last + '">Open last block #' + fmt(p.last) + ' →</a></p>';
  }
  // ---------------- ADDRESS INSPECTOR (under the galaxy, full width) ----------------
  var insp = d.getElementById('xsObsInsp'), inspFor = null;
  function permalink(a) { return location.origin + location.pathname + '#obs=' + a; }
  function inspector() {
    if (!insp) return; var a = st.sel, p = a && M.byAddr[a];
    if (!p) { insp.hidden = true; inspFor = null; return; }
    insp.hidden = false; if (inspFor === a) return; inspFor = a;
    var N = M.rows.length;
    var win = '<div class="xs-obs-wins">' + WL().map(function (w) { var n = winCount(p, w), m = Math.min(w, N); return '<div' + (w === st.win ? ' class="on"' : '') + '><span>' + wlab(w) + cons(w) + '</span><b>' + fmt(n) + '</b><small>' + pct(n, m) + '</small></div>'; }).join('') + '</div>' +
      '<p class="dim">Blocks attributed to this address in the loaded snapshot (#' + fmt(M.rows[0] && M.rows[0].h) + ' – #' + fmt(M.tip) + '): ' + fmt(p.n) + ' · last ' + '<a href="sost-explorer.html?search=' + p.last + '" data-find="' + p.last + '">#' + fmt(p.last) + '</a>. A window statistic, not a lifetime total.</p>';
    var body = insp.querySelector('.xs-insp-b');
    insp.querySelector('.xs-insp-h b').textContent = short(a);
    if (!U.addrInspector) { body.innerHTML = '<p class="dim">Loading the inspector…</p>'; var sc = d.createElement('script'); sc.src = 'universe/core/u-addr.js?v=obs2-20261104'; sc.onload = function () { inspFor = null; inspector(); }; sc.onerror = function () { body.innerHTML = '<p class="dim">The address inspector did not load. Use the full address page.</p>'; }; d.body.appendChild(sc); return; }
    U.addrInspector.render(body, a, { apiBase: 'api/', mode: 'public', windowHtml: win, permalink: permalink(a), fullHref: 'sost-explorer.html?search=' + a,
      link: function (k, v, t) { return '<a href="sost-explorer.html?search=' + esc(v) + '" data-find="' + esc(v) + '">' + esc(t) + '</a>'; } });
  }
  if (insp) insp.addEventListener('click', function (e) {
    var f = e.target.closest('[data-find]'); if (f) { e.preventDefault(); find(f.getAttribute('data-find')); return; }
    if (e.target.closest('[data-insp-close]')) { select(null); }
  });
  // ---------------- DECENTRALIZATION RADAR (observed production per window) ----------------
  function radar() {
    var el = d.getElementById('xsObsRadar'); if (!el) return; var N = M.rows.length; if (!N) { el.innerHTML = ''; return; }
    var cells = WL().map(function (w) {
      var m = Math.min(w, N), list = M.prod.map(function (p) { return [p, winCount(p, w)]; }).filter(function (x) { return x[1] > 0; }).sort(function (a, b) { return b[1] - a[1]; });
      var hhi = list.reduce(function (s2, x) { return s2 + Math.pow(x[1] / m, 2); }, 0), t1 = list[0], t3 = list.slice(0, 3).reduce(function (s2, x) { return s2 + x[1]; }, 0);
      return { w: w, m: m, n: list.length, t1: t1, s1: t1 ? t1[1] / m : 0, s3: t3 / m, eff: hhi ? 1 / hhi : 0 };
    });
    var cur = cells.filter(function (c) { return c.w === st.win; })[0] || cells[cells.length - 1], hi = cur.s1 >= .5;
    el.innerHTML = '<div class="xs-rad-h"><b>Decentralization radar</b><span>observed block production by address · not hashrate, not operators</span></div>' + srcStrip() +
      (hi ? '<p class="xs-rad-alert" role="status"><b>High observed concentration:</b> one address (<button type="button" class="xs-a" data-a="' + esc(cur.t1[0].a) + '"><i style="background:' + col(cur.t1[0].a, 54) + '"></i>' + esc(short(cur.t1[0].a)) + '</button>) produced ' + fmt(cur.t1[1]) + ' of the last ' + fmt(cur.m) + ' blocks (' + pct(cur.t1[1], cur.m) + '). This is a fact about found blocks; it does not by itself show an attack or who controls the address.</p>' : '') +
      '<div class="xs-rad-g">' + cells.map(function (c) {
        var k = c.w === N && st.wk === 'genesis' && N > M.recentN ? 'genesis' : c.w === N || c.w === M.recentN ? 'recent' : String(c.w);
        return '<div role="button" tabindex="0" data-wk="' + k + '" aria-pressed="' + (c === cur) + '" class="' + (c === cur ? 'on' : '') + (c.s1 >= .5 ? ' hi' : '') + (c.w === 288 ? ' cons' : '') + '"><span>' + wlab(c.w) + cons(c.w) + '</span><b>' + (100 * c.s1).toFixed(1) + ' %</b><small>top address</small>' +
          '<i class="bar"><i style="width:' + (100 * c.s1).toFixed(1) + '%;background:' + (c.t1 ? col(c.t1[0].a, 54) : '#555') + '"></i></i>' +
          '<small>top 3 · ' + (100 * c.s3).toFixed(1) + ' %</small><small>' + fmt(c.n) + ' address' + (c.n === 1 ? '' : 'es') + ' · effective ' + c.eff.toFixed(2) + '</small></div>';
      }).join('') + genCard() + '</div>' + (M.fullErr ? '<p class="xs-rad-n xs-gen-err" role="status">' + esc(M.fullErr) + '</p>' : '') + '<p class="xs-rad-n">Effective number = 1 / Σ share², the number of equal producers that would give the same concentration. One person can run several addresses, so the real number of independent operators can be lower.</p>';
  }
  // GENESIS card while the full chain is not active: load on demand, with progress
  function genCard() {
    if (st.wk === 'genesis' && M.full && M.rows.length > M.recentN) return '';
    var busy = M.fullBusy, kb = (M.fullProg / 1024).toFixed(0);
    return '<div role="button" tabindex="0" data-wk="genesis" aria-pressed="false" class="xs-gen' + (busy ? ' busy' : '') + '" aria-busy="' + busy + '"><span>genesis · full chain</span><b>' + (busy ? 'Loading…' : M.full ? fmt(M.full.length + 1) : '#0 → tip') + '</b>' +
      '<small>' + (busy ? 'Loading full-chain galaxy… ' + kb + ' KB' : M.full ? 'loaded · click to show' : 'all blocks since #0, on demand') + '</small><i class="bar"><i style="width:' + (busy ? Math.min(98, M.fullProg / 3600).toFixed(0) : 0) + '%;background:#22d3ee"></i></i><small>' + (M.full ? '' : 'heavier: loads only when clicked') + '</small></div>';
  }
  var rad = d.getElementById('xsObsRadar');
  if (rad) { rad.addEventListener('click', function (e) { var a = e.target.closest('button.xs-a'); if (a) { select(a.getAttribute('data-a'), true); return; } var c = e.target.closest('[data-wk]'); if (c && !M.fullBusy) setWk(c.getAttribute('data-wk')); });
    rad.addEventListener('keydown', function (e) { var c = e.target.closest('[data-wk]'); if (c && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); if (!M.fullBusy) setWk(c.getAttribute('data-wk')); } }); }
  host.addEventListener('click', function (e) {
    var f = e.target.closest('[data-find]'); if (f) { e.preventDefault(); find(f.getAttribute('data-find')); return; }
    var c = e.target.closest('button.copy[data-copy]'); if (c && !c.getAttribute('data-copy')) return; if (c) { try { var t0 = c.textContent; navigator.clipboard.writeText(c.getAttribute('data-copy')); c.textContent = 'Copied'; c.classList.add('ok'); setTimeout(function () { c.textContent = t0; c.classList.remove('ok'); }, 1400); } catch (er) {} return; }
    var a = e.target.closest('#xsObsDet button.xs-a'); if (a) { if (a.closest('.xs-obs-blk')) { if (insp) { inspector(); insp.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }); } } else select(a.getAttribute('data-a')); }
    var ip = e.target.closest('[data-insp]'); if (ip && insp) { e.preventDefault(); inspector(); insp.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }); }
    var ia = e.target.closest('[data-inspect]'); if (ia && insp) { e.preventDefault(); if (st.sel !== ia.getAttribute('data-inspect')) select(ia.getAttribute('data-inspect'), true); inspector(); insp.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }); }
  });

  // ---------------- modes, window, filter ----------------
  function select(a, keep, blk) {
    var prev = st.sel; st.sel = a && M.byAddr[a] ? (st.sel === a && !keep ? null : a) : null;
    if (blk !== undefined) { st.blk = blk; st.pin = false; }
    else if (!st.sel) { st.blk = null; st.pin = false; }
    else if (prev !== st.sel) { st.blk = null; st.pin = true; }   // chosen from a list / bar / row / filter: a pinned address, no block
    try { history.replaceState(null, '', st.blk != null && st.sel ? '#blk=' + st.blk : st.sel ? '#obs=' + st.sel : location.pathname + location.search + (location.hash === '#galaxy' ? '#galaxy' : '')); } catch (e) {}
    render();
  }
  function render() {
    host.querySelectorAll('[data-mode]').forEach(function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-mode') === st.mode)); });
    ['galaxy', 'mosaic', 'charts', 'table'].forEach(function (m) { $('#xsObs-' + m).hidden = m !== st.mode; });
    var ws = host.querySelector('.xs-obs-wsel');
    if (ws && !ws.querySelector('[data-win="genesis"]')) { var gb = d.createElement('button'); gb.type = 'button'; gb.setAttribute('data-win', 'genesis'); gb.title = 'Full chain from the genesis block (loads on demand)'; gb.textContent = 'Genesis'; ws.appendChild(gb);
      var b288 = ws.querySelector('[data-win="288"]'); if (b288) { b288.title = 'Last 288 blocks: the consensus reference window'; b288.setAttribute('aria-label', '288 blocks, consensus window'); } }
    host.querySelectorAll('[data-win]').forEach(function (b) { var v = b.getAttribute('data-win'), k = v === 'all' ? 'recent' : v; b.setAttribute('aria-pressed', String(k === st.wk)); if (v === 'genesis') { b.setAttribute('aria-busy', String(M.fullBusy)); b.textContent = M.fullBusy ? 'Loading…' : 'Genesis'; } });
    var all = host.querySelector('[data-win="all"]'); if (all) all.textContent = 'All ' + fmt(M.recentN || M.rows.length);
    $('#xsObsSrc').textContent = M.src ? netName(M.snap && M.snap.net) + ' · ' + M.src + ' · tip #' + fmt(M.tip) + (M.at ? ' · collected ' + new Date(M.at * 1000).toISOString().slice(0, 16).replace('T', ' ') + 'Z' : '') : 'snapshot unavailable';
    if (st.mode === 'galaxy') { size(); drawGalaxy(); kick(); }
    if (st.mode === 'mosaic') drawMosaic();
    if (st.mode === 'charts') charts();
    if (st.mode === 'table') table();
    detail(); radar(); inspector();
  }
  host.querySelector('.xs-obs-modes').addEventListener('click', function (e) { var b = e.target.closest('[data-mode]'); if (!b) return; st.mode = b.getAttribute('data-mode'); try { localStorage.setItem('sost_xs_obs_mode', st.mode); } catch (er) {} render(); });
  host.querySelector('.xs-obs-modes').addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return; var bs = [].slice.call(host.querySelectorAll('[data-mode]')), i = bs.indexOf(d.activeElement); if (i < 0) return;
    var n = bs[(i + (e.key === 'ArrowRight' ? 1 : bs.length - 1)) % bs.length]; n.focus(); n.click(); e.preventDefault();
  });
  host.querySelector('.xs-obs-wsel').addEventListener('click', function (e) { var b = e.target.closest('[data-win]'); if (!b) return; if (M.fullBusy) return; var v = b.getAttribute('data-win'); setWk(v === 'all' ? 'recent' : v); });
  var fi = $('#xsObsFilter');
  fi.addEventListener('input', function () {
    st.filter = fi.value.trim();
    var m = st.filter && M.prod.filter(function (p) { return p.a.toLowerCase().indexOf(st.filter.toLowerCase()) >= 0; });
    if (m && m.length === 1 && st.sel !== m[0].a) { st.sel = m[0].a; }
    if (st.mode === 'table') table(); else render();
  });
  d.addEventListener('keydown', function (e) { if (e.key === 'Escape' && st.sel && host.contains(d.activeElement)) select(null); });

  if ('IntersectionObserver' in root) new IntersectionObserver(function (es) { visible = es.some(function (x) { return x.isIntersecting; }); if (visible) kick(); }, { rootMargin: '60px 0px' }).observe(cv.parentNode);
  else visible = true;
  d.addEventListener('visibilitychange', function () { if (!d.hidden) kick(); });
  var rz = 0; addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(render, 150); }, { passive: true });

  host.classList.add('loading');
  load().catch(function () {}).then(function () {
    host.classList.remove('loading');
    var bm = /^#blk=(\d{1,9})$/.exec(location.hash); if (bm && rowOf(+bm[1])) { st.mode = 'galaxy'; pickBlock(+bm[1]); return; }
    var hm = /^#obs=(sost1[0-9a-f]{40})$/i.exec(location.hash);
    if (hm && M.byAddr[hm[1].toLowerCase()]) { st.sel = hm[1].toLowerCase(); render(); if (insp) setTimeout(function () { insp.scrollIntoView({ block: 'start' }); }, 80); }
    else if (hm) { render(); if (insp) { insp.hidden = false; insp.querySelector('.xs-insp-h b').textContent = short(hm[1]); var b = insp.querySelector('.xs-insp-b'); b.innerHTML = '<p class="dim">This address produced no block in the loaded window; its public data:</p><div></div>';
      var go = function () { U.addrInspector.render(b.lastChild, hm[1], { apiBase: 'api/', mode: 'public', permalink: permalink(hm[1].toLowerCase()), fullHref: 'sost-explorer.html?search=' + hm[1], link: function (k, v, t) { return '<a href="sost-explorer.html?search=' + esc(v) + '" data-find="' + esc(v) + '">' + esc(t) + '</a>'; } }); insp.scrollIntoView({ block: 'start' }); };
      if (U.addrInspector) go(); else { var sc = d.createElement('script'); sc.src = 'universe/core/u-addr.js?v=obs2-20261104'; sc.onload = go; d.body.appendChild(sc); } } }
    else render();
    if (st.wk === 'genesis') setWk('genesis');
  });
  // refresh with the collector cadence of the block series (5 min); a new tip re-lays out the galaxy
  setInterval(function () { if (!d.hidden) load().then(render).catch(function () {}); }, 300000);
  // ---- Full screen (Fullscreen API on the whole observatory: tabs, windows, Genesis card, zoom, panel and inspector come
  // along) with an immersive fallback (fixed, covering the viewport) where an element cannot go full screen (iPhone Safari)
  // or the request is refused. ESC leaves both (native: by the browser; immersive: handled here).
  var fsB = zc.querySelector('[data-fs]'), pnB = zc.querySelector('[data-panel]'), fxB = zc.querySelector('[data-fx]');
  function fsEl() { return d.fullscreenElement || d.webkitFullscreenElement || null; }
  function fsOn() { return host.classList.contains('xs-fs'); }
  function fsAfter() {
    var on = fsOn();
    fsB.textContent = on ? 'Exit full screen ✕' : '⛶ Full screen'; fsB.setAttribute('aria-pressed', String(on)); fsB.setAttribute('aria-label', on ? 'Exit full screen (Esc)' : 'Enter full screen');
    host.setAttribute('data-fs-kind', on ? (host.classList.contains('xs-imm') ? 'immersive' : 'native') : '');
    pnB.setAttribute('aria-pressed', String(!host.classList.contains('xs-fs-np')));
    clearTimeout(rz); rz = setTimeout(function () { render(); fxSchedule(); }, 80);
  }
  function immersive() { host.classList.add('xs-fs', 'xs-imm'); d.documentElement.classList.add('xs-fs-lock'); host.scrollTop = 0; fsAfter(); }
  function fsEnter() {
    if (root.innerWidth < 980) host.classList.add('xs-fs-np'); else host.classList.remove('xs-fs-np');   // phones: panel starts collapsed (bottom sheet)
    var req = host.requestFullscreen || host.webkitRequestFullscreen;
    if (!req) { immersive(); return; }
    try { var pr = req.call(host, { navigationUI: 'hide' }); if (pr && pr.then) pr.catch(immersive); } catch (e) { immersive(); }
  }
  function fsExit() {
    if (fsEl()) { var ex = d.exitFullscreen || d.webkitExitFullscreen; try { ex.call(d); } catch (e) { } return; }
    host.classList.remove('xs-fs', 'xs-imm'); d.documentElement.classList.remove('xs-fs-lock'); fsAfter(); cv.focus({ preventScroll: true });
  }
  function onFs() {
    if (fsEl() === host) { host.classList.add('xs-fs'); host.classList.remove('xs-imm'); host.scrollTop = 0; }
    else if (!host.classList.contains('xs-imm')) host.classList.remove('xs-fs');
    fsAfter();
  }
  d.addEventListener('fullscreenchange', onFs); d.addEventListener('webkitfullscreenchange', onFs);
  d.addEventListener('keydown', function (e) { if (e.key === 'Escape' && host.classList.contains('xs-imm')) fsExit(); });
  fsB.addEventListener('click', function () { if (fsOn()) fsExit(); else fsEnter(); });
  pnB.addEventListener('click', function () { host.classList.toggle('xs-fs-np'); fsAfter(); });

  // ---- Decorative FX: occasional shooting stars, comets and faint flashes. Purely decorative (never data): drawn on their
  // own canvas BEHIND the galaxy canvas (CSS z-index), so stars, rings, labels and markers always cover them; streaks and
  // tails, never dots, so they cannot be read as blocks. At most 2 at a time, one every ~9–23 s (~5–14 s in full screen),
  // 0.7–7 s each; the loop runs only while one is alive, at ≤ 30 fps. AUTO (default): off with prefers-reduced-motion,
  // on low-end devices (≤ 2 cores, ≤ 2 GB, Save-Data) and for the session once the page drops below 24 fps.
  // ON forces them (with reduced motion: faint flashes only, nothing moves). OFF removes them.
  var fxCv = d.createElement('canvas'); fxCv.className = 'xs-fx'; fxCv.setAttribute('aria-hidden', 'true'); cv.parentNode.insertBefore(fxCv, cv);
  var fxc = fxCv.getContext('2d'), FX = { mode: 'auto', slow: false, items: [], raf: 0, timer: 0, last: 0, prev: 0, dts: [] };
  try { var fxm = root.localStorage.getItem('sost_galaxy_fx'); if (/^(auto|on|off)$/.test(fxm || '')) FX.mode = fxm; } catch (e) { }
  var nav = root.navigator || {}, LOWEND = !!((nav.hardwareConcurrency && nav.hardwareConcurrency <= 2) || (nav.deviceMemory && nav.deviceMemory <= 2) || (nav.connection && nav.connection.saveData));
  function fxAllowed() { return FX.mode === 'on' || (FX.mode === 'auto' && !RM && !LOWEND && !FX.slow); }
  function fxWhy() { return FX.mode === 'off' ? 'off' : FX.mode === 'on' ? (RM ? 'on (reduced motion: flashes only)' : 'on') : RM ? 'auto: off (reduced motion)' : LOWEND ? 'auto: off (low-end device)' : FX.slow ? 'auto: off (page below 24 fps)' : 'auto: on'; }
  function fxLabel() { fxB.textContent = 'FX: ' + FX.mode.toUpperCase() + (FX.mode === 'auto' && !fxAllowed() ? ' · off' : ''); fxB.title = 'Decorative effects (comets, shooting stars, meteor grazes), not data — ' + fxWhy() + '. Click: AUTO → ON → OFF.'; fxB.setAttribute('aria-label', 'Decorative effects: ' + fxWhy()); fxB.setAttribute('data-fx-state', fxAllowed() ? 'on' : 'off'); }
  function fxSize() { if (fxCv.width !== cv.width || fxCv.height !== cv.height) { fxCv.width = cv.width; fxCv.height = cv.height; } }
  function fxClear() { FX.items = []; fxc.setTransform(1, 0, 0, 1, 0, 0); fxc.clearRect(0, 0, fxCv.width, fxCv.height); }
  function fxSchedule() {
    clearTimeout(FX.timer); FX.timer = 0; if (!fxAllowed()) { fxClear(); return; }
    var big = fsOn(); FX.timer = setTimeout(fxSpawn, (big ? 5000 : 9000) + Math.random() * (big ? 9000 : 14000));
  }
  function fxNew() {
    var now = performance.now(), r = Math.random();
    if (RM || r < .2) {   // faint cross glint, only OUTSIDE the galaxy disc (never where a star could be)
      for (var tr = 0; tr < 12; tr++) { var fx0 = Math.random() * W, fy0 = Math.random() * H, ex = (fx0 - W / 2 - st.ox) / (R * st.z * 1.08), ey = (fy0 - H / 2 - st.oy) / (R * TILT * st.z * 1.08);
        if (ex * ex + ey * ey > 1) return { k: 'flash', x: fx0, y: fy0, t0: now, dur: 1200 }; }
      return { k: 'flash', x: -99, y: -99, t0: now, dur: 1 };
    }
    if (r >= .62 && r < .8) {   // meteor graze across an outer arm (see lens()); drawn on the galaxy canvas, above the stars
      var a0 = Math.random() * Math.PI * 2, sw = (.5 + Math.random() * .45) * (Math.random() < .5 ? 1 : -1), rr0 = 1.12, rr1 = .78 + Math.random() * .18;
      var pt = function (ang, rad) { return [W / 2 + st.ox + Math.cos(ang) * rad * R * st.z, H / 2 + st.oy + Math.sin(ang) * rad * R * TILT * st.z]; };
      var s0 = pt(a0, rr0), s1 = pt(a0 + sw, rr1);
      return { k: 'graze', x: s0[0], y: s0[1], x1: s1[0] + (s1[0] - s0[0]) * .25, y1: s1[1] + (s1[1] - s0[1]) * .25, t0: now, dur: 1700 + Math.random() * 900 };
    }
    if (r < .75) {   // shooting star: a short fast streak through the upper band
      var left = Math.random() < .5, a = (left ? .42 : Math.PI - .42) + (Math.random() - .5) * .35, sp = (W + H) * (.0007 + Math.random() * .0004);
      return { k: 'shoot', x: left ? Math.random() * W * .45 : W * .55 + Math.random() * W * .45, y: Math.random() * H * .3, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp, t0: now, dur: 650 + Math.random() * 500, len: 55 + Math.random() * 55 };
    }
    var dur = 4500 + Math.random() * 2500, dir = Math.random() < .5 ? 1 : -1, top = Math.random() < .5;   // comet: slow, along the top or bottom edge band
    return { k: 'comet', x: dir > 0 ? -60 : W + 60, y: top ? H * (.05 + Math.random() * .12) : H * (.83 + Math.random() * .12), vx: dir * (W + 120) / dur, vy: (Math.random() - .5) * .006, t0: now, dur: dur, len: 70 + Math.random() * 50 };
  }
  function fxSpawn() {
    FX.timer = 0; if (!fxAllowed()) return;
    if (visible && !d.hidden && st.mode === 'galaxy' && FX.items.length < 2) { FX.items.push(fxNew()); if (!FX.raf) { FX.prev = 0; FX.raf = requestAnimationFrame(fxFrame); } }
    fxSchedule();
  }
  function fxDraw(now) {
    var c = fxc; c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, fxCv.width, fxCv.height); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    FX.items = FX.items.filter(function (o) { return now - o.t0 < o.dur; });
    FX.items.forEach(function (o) {
      var p = (now - o.t0) / o.dur, fade = Math.sin(Math.PI * Math.min(1, Math.max(0, p))), g;
      if (o.k === 'graze') return;
      if (o.k === 'flash') { c.strokeStyle = 'rgba(210,228,255,' + (.38 * fade).toFixed(3) + ')'; c.lineWidth = .8; c.beginPath(); c.moveTo(o.x - 7, o.y); c.lineTo(o.x + 7, o.y); c.moveTo(o.x, o.y - 7); c.lineTo(o.x, o.y + 7); c.stroke(); return; }
      var dt = now - o.t0, hx = o.x + o.vx * dt, hy = o.y + o.vy * dt, m = Math.sqrt(o.vx * o.vx + o.vy * o.vy) || 1, tx = hx - o.vx / m * o.len, ty = hy - o.vy / m * o.len;
      g = c.createLinearGradient(hx, hy, tx, ty);
      var rgb = o.k === 'comet' ? '170,215,255' : '255,255,255', a = (o.k === 'comet' ? .5 : .62) * fade;
      g.addColorStop(0, 'rgba(' + rgb + ',' + a.toFixed(3) + ')'); g.addColorStop(1, 'rgba(' + rgb + ',0)');
      c.strokeStyle = g; c.lineWidth = o.k === 'comet' ? 2.2 : 1.2; c.lineCap = 'round'; c.beginPath(); c.moveTo(hx, hy); c.lineTo(tx, ty); c.stroke();
      if (o.k === 'comet') { var gh = c.createRadialGradient(hx, hy, 0, hx, hy, 6); gh.addColorStop(0, 'rgba(225,240,255,' + (.6 * fade).toFixed(3) + ')'); gh.addColorStop(1, 'rgba(225,240,255,0)'); c.fillStyle = gh; c.fillRect(hx - 6, hy - 6, 12, 12); }
    });
  }
  function fxFrame(now) {
    FX.raf = 0;
    if (FX.prev) { FX.dts.push(now - FX.prev); if (FX.dts.length > 45) FX.dts.shift(); }
    FX.prev = now;
    if (FX.mode === 'auto' && FX.dts.length >= 45) { var avg = FX.dts.reduce(function (s, x) { return s + x; }, 0) / FX.dts.length;
      if (avg > 1000 / 24) { FX.slow = true; FX.dts = []; fxClear(); fxLabel(); clearTimeout(FX.timer); return; } }
    if (now - FX.last >= 33) { FX.last = now; fxDraw(now); }
    if (FX.items.length && fxAllowed() && st.mode === 'galaxy' && !d.hidden) FX.raf = requestAnimationFrame(fxFrame); else { fxClear(); FX.prev = 0; }
  }
  fxB.addEventListener('click', function () {
    FX.mode = FX.mode === 'auto' ? 'on' : FX.mode === 'on' ? 'off' : 'auto'; FX.slow = false; FX.dts = [];
    try { root.localStorage.setItem('sost_galaxy_fx', FX.mode); } catch (e) { }
    fxLabel(); fxSchedule(); if (FX.mode !== 'off') fxSpawn();
  });
  fxLabel(); fxSchedule();

  U.explorerGalaxy = { state: st, model: M, setWindow: setWk, select: function (a) { select(a, true); }, pickBlock: pickBlock, render: render, zoom: zoomBy, ambiguous: ambiguous,
    fx: function () { return { mode: FX.mode, allowed: fxAllowed(), why: fxWhy(), alive: FX.items.length, slow: FX.slow, spawn: fxSpawn, items: FX.items.map(function (o) { return { k: o.k, x: o.x, y: o.y, x1: o.x1, y1: o.y1, t0: o.t0, dur: o.dur }; }) }; },
    fullscreen: function () { return fsOn() ? (host.classList.contains('xs-imm') ? 'immersive' : 'native') : 'off'; },
    points: function () { return P.map(function (p) { var q = xy(p); return [p[4], +q[0].toFixed(2), +q[1].toFixed(2), p[3]]; }); } };   // read-only, for tests: [height, x, y, age bucket] in canvas CSS px
})(window);

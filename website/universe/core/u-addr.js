/* SOST — public ADDRESS INSPECTOR (owner orders 4 Nov 2026: Explorer P0 «consultas de direcciones» + Mining Observatory 2.0).
 * One renderer shared by the Mining Observatory of sost-explorer.html and by universe/explorer.html.
 * It shows, for one public sost1 address, three things that must never be mixed up:
 *   1. CURRENT STATE   — read now from the node: getaddressinfo (balance + UTXO set) and getaddressflows. 2 read-only calls,
 *                        cached 30 s per address. Labelled with its real source (public node / your node / fixture).
 *   2. HISTORICAL      — api/address_earnings.json (collector, block by block since genesis): mined blocks and miner reward,
 *                        DTD normal and Jackpot wins. Lifetime flow, NOT the balance.
 *   3. NODE IDENTITY   — api/node_participation.json: NODE_BIND and heartbeats (only addresses that bound a node, #30,000+).
 * A window statistic (blocks in the last N) is passed in by the caller and shown as such.
 * Nothing is invented: a source that does not answer is shown as NOT AVAILABLE with the reason and a Retry button.
 * A public address is not a wallet: no key, password or seed is ever asked for or touched. */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {}, d = document;
  var MATURITY = 1000, STOCKS = 1e8;
  var TYPE = { 0: 'transfer', 1: 'coinbase · miner', 2: 'coinbase · gold', 3: 'coinbase · popc', 4: 'coinbase · DTD', 16: 'bond-lock', 17: 'escrow-lock',
    18: 'htlc-lock (retired, H-01)', 19: 'htlc-claim (retired, H-01)', 32: 'burn', 48: 'node-protocol' };
  var esc = function (x) { return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var fmt = function (n, dd) { return n == null || isNaN(n) ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: dd || 0, maximumFractionDigits: dd || 0 }); };
  var sost = function (v) { return fmt(v, 8) + ' SOST'; };
  var short = function (h, n) { h = String(h || ''); n = n || 8; return h.length > 2 * n + 1 ? h.slice(0, n) + '…' + h.slice(-n) : h; };
  var utc = function (t) { return new Date(t).toISOString().slice(0, 19).replace('T', ' ') + ' UTC'; };
  var cache = {}, json = {};

  function css() {
    if (d.getElementById('uai-css')) return;
    var s = d.createElement('style'); s.id = 'uai-css';
    s.textContent = '.uai{font:13px/1.55 inherit;color:#d7dde8}.uai h4{margin:16px 0 6px;font:700 10.5px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.14em;text-transform:uppercase;color:#93a1b5;display:flex;gap:8px;align-items:center;flex-wrap:wrap}' +
      '.uai h4:first-child{margin-top:4px}.uai .src{font:600 9.5px ui-monospace,monospace;letter-spacing:.08em;padding:2px 7px;border-radius:99px;border:1px solid #ffffff30;color:#cbd5e1}' +
      '.uai .src.live{border-color:#22c55e88;color:#86efac}.uai .src.fx{border-color:#f59e0b88;color:#fcd34d}.uai .src.col{border-color:#38bdf888;color:#7dd3fc}.uai .src.na{border-color:#f8717188;color:#fca5a5}' +
      '.uai .kv{display:grid;grid-template-columns:minmax(120px,max-content) 1fr;gap:3px 14px}.uai .kv>span:nth-child(odd){color:#93a1b5}.uai .kv>span:nth-child(even){font-variant-numeric:tabular-nums;word-break:break-word}' +
      '.uai .big{font:700 20px/1.2 ui-monospace,monospace;color:#fff}.uai code{font:12px ui-monospace,monospace;color:#7dd3fc;word-break:break-all}.uai .dim{color:#8391a5;font-size:12px}' +
      '.uai .na{color:#fca5a5}.uai button.uai-b{all:unset;cursor:pointer;font:600 11px ui-monospace,monospace;padding:3px 10px;border-radius:7px;border:1px solid #ffffff38;color:#e2e8f0}.uai button.uai-b:hover{border-color:#22d3ee;color:#fff}' +
      '.uai button.uai-b:focus-visible{outline:2px solid #22d3ee;outline-offset:2px}.uai .tw{overflow-x:auto;max-height:280px;overflow-y:auto;border:1px solid #ffffff14;border-radius:8px}.uai table{border-collapse:collapse;width:100%;font:11.5px ui-monospace,monospace}' +
      '.uai th,.uai td{padding:5px 8px;border-bottom:1px solid #ffffff0f;text-align:left;white-space:nowrap}.uai th{color:#93a1b5;font-weight:600;position:sticky;top:0;background:#0b0f16}.uai td.r,.uai th.r{text-align:right}' +
      '.uai a{color:#7dd3fc}.uai .imm{color:#fbbf24}.uai .lck{color:#c4b5fd}.uai .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.uai .sk{height:14px;border-radius:5px;background:linear-gradient(90deg,#ffffff0d,#ffffff1f,#ffffff0d);background-size:200% 100%;animation:uaisk 1.2s linear infinite}' +
      '@keyframes uaisk{to{background-position:-200% 0}}@media (prefers-reduced-motion:reduce){.uai .sk{animation:none}}';
    d.head.appendChild(s);
  }
  function getJSON(u) {
    if (!json[u]) json[u] = fetch(u, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    json[u].catch(function () { delete json[u]; });
    return json[u];
  }
  function defaultRpc(m, p) {   // same-origin public endpoint; passes through the page's own transport (x-rpc.js limits)
    var ctl = root.AbortController ? new AbortController() : null, to = setTimeout(function () { if (ctl) ctl.abort(); }, 12000);
    return fetch('/rpc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: m, params: p || [] }), cache: 'no-store', credentials: 'omit', signal: ctl && ctl.signal })
      .then(function (r) { if (!r.ok) throw new Error('node HTTP ' + r.status); return r.json(); })
      .then(function (j) { clearTimeout(to); if (j.error) throw new Error(j.error.message || 'node error'); return j.result; },
        function (e) { clearTimeout(to); throw e.name === 'AbortError' ? new Error('the node did not answer within 12 s') : e; });
  }
  function nodeState(addr, o) {
    var c = cache[addr]; if (c && Date.now() - c.at < 30000) return c.p;
    var rpc = o.rpc || defaultRpc;
    var p = Promise.all([rpc('getaddressinfo', [addr]), rpc('getaddressflows', [addr]).catch(function () { return null; }),
      o.tip ? Promise.resolve(o.tip) : rpc('getblockcount', []).catch(function () { return null; })])
      .then(function (r) { return { info: r[0], flows: r[1], tip: r[2], at: Date.now() }; });
    cache[addr] = { at: Date.now(), p: p }; p.catch(function () { delete cache[addr]; });
    return p;
  }
  function reconcile(info, tip) {
    var u = (info && info.utxos) || [], sum = 0, imm = 0, locked = 0;
    u.forEach(function (x) { var a = Number(x.amount) || 0; sum += a; if (x.coinbase && tip && tip - x.height + 1 < MATURITY) imm += a; if (x.type === 16 || x.type === 17 || x.type === 18) locked += a; });
    var b = Number(info && info.balance); if (b > 1e6 && Number.isInteger(b) && sum < b / 1e4) b = b / STOCKS;
    var n8 = function (v) { return Math.round(v * 1e8); };
    return { balance: b, sum: sum, match: n8(sum) === n8(b), n: u.length, imm: imm, locked: locked, spend: b - imm - locked };
  }
  function srcTag(o) {
    var m = o.mode || 'public';
    return m === 'fixture' ? '<span class="src fx">FIXTURE · CAPTURED · NOT LIVE</span>' : m === 'own-node' ? '<span class="src live">YOUR NODE</span>' : '<span class="src live">LIVE · PUBLIC NODE</span>';
  }
  function na(why, retry) { return '<p class="na">Not available: ' + esc(why) + (retry ? ' <button type="button" class="uai-b" data-uai-retry>Retry</button>' : '') + '</p>'; }

  /** render(el, addr, opts) — opts: { rpc(method, params) → Promise, mode, tip, apiBase ('api/' | '../api/'),
   *  link(kind 'block'|'tx'|'address', value, label) → html, fullHref (string for the full address page), windowHtml, permalink } */
  function render(el, addr, o) {
    o = o || {}; css(); addr = String(addr || '').trim().toLowerCase();
    var L = o.link || function (k, v, t) { return '<a href="#search=' + esc(v) + '">' + esc(t) + '</a>'; }, api = o.apiBase || 'api/';
    if (!/^sost1[0-9a-f]{40}$/.test(addr)) { el.innerHTML = '<div class="uai">' + na('“' + addr + '” is not a sost1 address') + '</div>'; return; }
    var gen = (el.__uaiGen = (el.__uaiGen || 0) + 1);
    el.innerHTML = '<div class="uai" data-addr="' + esc(addr) + '">' +
      '<h4>Public address <span class="dim" style="letter-spacing:0;text-transform:none;font-family:inherit">not a wallet · no keys involved</span></h4>' +
      '<p class="row"><code>' + esc(addr) + '</code><button type="button" class="uai-b" data-uai-copy="' + esc(addr) + '">Copy</button>' +
        (o.permalink ? '<button type="button" class="uai-b" data-uai-copy="' + esc(o.permalink) + '" title="' + esc(o.permalink) + '">Copy link</button>' : '') +
        (o.fullHref ? '<a href="' + esc(o.fullHref) + '" target="_blank" rel="noopener">Full address page ↗</a>' : '') + '</p>' +
      '<section data-s="now"><h4>Current state ' + srcTag(o) + '</h4><div class="sk" style="width:60%"></div><div class="sk" style="width:40%;margin-top:6px"></div></section>' +
      '<section data-s="hist"><h4>Historical rewards <span class="src col">COLLECTOR · LIFETIME, NOT BALANCE</span></h4><div class="sk" style="width:55%"></div></section>' +
      '<section data-s="node"></section>' + (o.windowHtml ? '<section data-s="win"><h4>Window statistics <span class="src">OBSERVED BLOCKS</span></h4>' + o.windowHtml + '</section>' : '') + '<section data-s="utxo"></section></div>';
    var box = el.firstChild, sec = function (k) { return box.querySelector('[data-s="' + k + '"]'); };
    if (!el.__uaiWired) {
      el.__uaiWired = true;
      el.addEventListener('click', function (e) {
        var c = e.target.closest('[data-uai-copy]');
        if (c) { var v = c.getAttribute('data-uai-copy'), t = c.textContent; try { navigator.clipboard.writeText(v); c.textContent = 'Copied'; setTimeout(function () { c.textContent = t; }, 1300); } catch (er) {} return; }
        var r = e.target.closest('[data-uai-retry]'); if (r && el.__uaiLast) { delete cache[el.__uaiLast[0]]; render(el, el.__uaiLast[0], el.__uaiLast[1]); }
      });
    }
    el.__uaiLast = [addr, o];

    nodeState(addr, o).then(function (s) {
      if (gen !== el.__uaiGen) return;
      var tip = s.tip, rc = reconcile(s.info, tip), f = s.flows || {};
      sec('now').innerHTML = '<h4>Current state ' + srcTag(o) + '<span class="dim" style="letter-spacing:0;text-transform:none">read ' + utc(s.at) + (tip ? ' · tip #' + fmt(tip) : '') + '</span></h4>' +
        '<div class="kv"><span>Confirmed balance</span><span class="big">' + sost(rc.balance) + '</span>' +
        '<span>Spendable now</span><span>' + sost(rc.spend) + '</span>' +
        '<span>Immature coinbase</span><span class="imm">' + sost(rc.imm) + ' <span class="dim">(&lt; ' + fmt(MATURITY) + ' confirmations)</span></span>' +
        (rc.locked ? '<span>Locked</span><span class="lck">' + sost(rc.locked) + ' <span class="dim">(bond / escrow / retired HTLC)</span></span>' : '') +
        '<span>Unspent outputs</span><span>' + fmt(rc.n) + ' UTXO · Σ ' + sost(rc.sum) + (rc.match ? ' <span style="color:#86efac">✓ equals the balance</span>' : ' <span class="dim">≠ balance (node value shown)</span>') + '</span>' +
        '<span>Received, non-mining</span><span>' + (f.received_non_mining != null ? sost(f.received_non_mining / STOCKS) : '—') + '</span>' +
        '<span>Sent, non-mining</span><span>' + (f.sent_non_mining != null ? sost(f.sent_non_mining / STOCKS) : '—') + (f.scanned_height ? ' <span class="dim">(scanned to #' + fmt(f.scanned_height) + ')</span>' : '') + '</span></div>';
      var u = ((s.info && s.info.utxos) || []).slice().sort(function (a, b) { return b.height - a.height; }), txs = {}, shown = 0;
      u.forEach(function (x) { txs[x.txid] = (txs[x.txid] || 0) + 1; });
      function rows(n) {   // paged: a busy producer can hold thousands of outputs
        var h = u.slice(shown, shown + n).map(function (x) {
          var conf = tip ? tip - x.height + 1 : null, st = x.type === 16 || x.type === 17 || x.type === 18 ? '<span class="lck">locked</span>' : x.coinbase && conf != null && conf < MATURITY ? '<span class="imm">immature · ' + fmt(conf) + ' conf.</span>' : 'spendable' + (conf != null ? ' · ' + fmt(conf) + ' conf.' : '');
          return '<tr><td>' + L('tx', x.txid, short(x.txid, 8)) + ':' + x.vout + '</td><td class="r">' + fmt(x.amount, 8) + '</td><td>' + L('block', x.height, '#' + fmt(x.height)) + '</td><td>' + esc(TYPE[x.type] || 'type ' + x.type) + '</td><td>' + st + '</td></tr>';
        }).join(''); shown = Math.min(u.length, shown + n); return h;
      }
      sec('utxo').innerHTML = '<h4>Unspent outputs and their transactions <span class="src live">NODE</span><span class="dim" style="letter-spacing:0;text-transform:none">' + fmt(u.length) + ' UTXO in ' + fmt(Object.keys(txs).length) + ' transactions · newest first</span></h4>' +
        (u.length ? '<div class="tw"><table><thead><tr><th>Transaction</th><th class="r">Amount</th><th>Block</th><th>Type</th><th>Status</th></tr></thead><tbody>' + rows(50) + '</tbody></table></div>' +
          '<p class="row"><span class="dim" data-uai-n>' + fmt(shown) + ' of ' + fmt(u.length) + ' shown</span>' + (u.length > shown ? '<button type="button" class="uai-b" data-uai-more>Show 200 more</button>' : '') + '</p>' : '<p class="dim">No unspent outputs: the balance is zero.</p>') +
        '<p class="dim">The node keeps the unspent set; spent outputs and the complete history are on the full address page' + (o.fullHref ? ' (<a href="' + esc(o.fullHref) + '" target="_blank" rel="noopener">open ↗</a>)' : '') + '.</p>';
      var mb = sec('utxo').querySelector('[data-uai-more]');
      if (mb) mb.onclick = function () { sec('utxo').querySelector('tbody').insertAdjacentHTML('beforeend', rows(200)); sec('utxo').querySelector('[data-uai-n]').textContent = fmt(shown) + ' of ' + fmt(u.length) + ' shown'; if (shown >= u.length) mb.remove(); };
    }, function (e) {
      if (gen !== el.__uaiGen) return;
      sec('now').innerHTML = '<h4>Current state <span class="src na">NOT AVAILABLE</span></h4>' + na((e && e.message) || 'the node did not answer', true) +
        '<p class="dim">Balance and UTXO are read from the node only; nothing is shown from a stale copy.</p>';
    });

    getJSON(api + 'address_earnings.json').then(function (E) {
      if (gen !== el.__uaiGen) return;
      var r = E.addresses && E.addresses[addr], h = '<h4>Historical rewards <span class="src col">COLLECTOR · LIFETIME, NOT BALANCE</span><span class="dim" style="letter-spacing:0;text-transform:none">block by block to #' + fmt(E.tip) + '</span></h4>';
      if (!r) { sec('hist').innerHTML = h + '<p class="dim">This address has no mining, DTD or Jackpot reward up to #' + fmt(E.tip) + '.</p>'; return; }
      var v = {}; E.fields.forEach(function (k, i) { v[k] = r[i]; });
      var jw = (v.dtd_jackpot_wins || 0) + (v.dtd_jackpot_v1_wins || 0), js = (v.dtd_jackpot_sat || 0) + (v.dtd_jackpot_v1_sat || 0), tot = (v.mining_sat || 0) + (v.dtd_normal_sat || 0) + js;
      sec('hist').innerHTML = h + '<div class="kv"><span>Blocks mined</span><span>' + fmt(v.mining_blocks) + '</span><span>Miner reward</span><span>' + sost(v.mining_sat / STOCKS) + '</span>' +
        '<span>DTD normal</span><span>' + fmt(v.dtd_normal_wins) + ' wins · ' + sost(v.dtd_normal_sat / STOCKS) + '</span><span>DTD Jackpot</span><span>' + fmt(jw) + ' wins · ' + sost(js / STOCKS) + '</span>' +
        '<span>Total earned</span><span>' + sost(tot / STOCKS) + ' <span class="dim">(a flow since genesis: spending does not lower it)</span></span></div>';
    }, function (e) { if (gen === el.__uaiGen) sec('hist').innerHTML = '<h4>Historical rewards <span class="src na">NOT AVAILABLE</span></h4>' + na('api/address_earnings.json ' + ((e && e.message) || 'did not load'), true); });

    getJSON(api + 'node_participation.json').then(function (N) {
      if (gen !== el.__uaiGen) return;
      var n = (N.nodes || []).filter(function (x) { return x.miner === addr; })[0], h = '<h4>NODE_BIND and heartbeats <span class="src col">COLLECTOR · CHAIN FROM #' + fmt(N.activation_height) + '</span></h4>';
      sec('node').innerHTML = h + (n ? '<div class="kv"><span>Status</span><span>' + esc(n.status) + '</span><span>Node key</span><span><code>' + esc(short(n.node_key, 12)) + '</code></span>' +
          '<span>NODE_BIND</span><span>' + L('block', n.bind_height, '#' + fmt(n.bind_height)) + ' · tx ' + L('tx', n.bind_txid, short(n.bind_txid, 8)) + (n.binds_total > 1 ? ' · ' + fmt(n.binds_total) + ' binds' : '') + '</span>' +
          '<span>Heartbeats</span><span>' + fmt(n.heartbeats) + ' · epochs ' + fmt(n.epochs_covered) + ' / ' + fmt(n.epochs_expected) + ' · last ' + L('block', n.last_heartbeat_height, '#' + fmt(n.last_heartbeat_height)) + '</span>' +
          (n.next_jackpot ? '<span>Next Jackpot #' + fmt(n.next_jackpot.height) + '</span><span>' + (n.next_jackpot.node_condition_met ? 'node condition met' : 'node condition not met') + ' (' + fmt(n.next_jackpot.in_window) + ' of ' + fmt(n.next_jackpot.required) + ' heartbeats required in the window)</span>' : '') + '</div>' +
          '<p class="dim">' + esc(N.note || '') + '</p>'
        : '<p class="dim">No NODE_BIND on chain for this address (' + fmt((N.nodes || []).length) + ' bound identities to #' + fmt(N.tip) + ').</p>');
    }, function () { if (gen === el.__uaiGen) sec('node').innerHTML = '<h4>NODE_BIND and heartbeats <span class="src na">NOT AVAILABLE</span></h4>' + na('api/node_participation.json did not load', true); });
  }
  U.addrInspector = { render: render, reconcile: reconcile, TYPE: TYPE, _cache: cache };
})(window);

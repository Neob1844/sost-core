/* SOST Universe — Explorer 2.0 renderer (Phase 5). Shared by universe/explorer.html and the Explorer-only PWA.
 * Reads snapshots from SOSTU.data (no RPC) and asks SOSTU.query only for explicit lookups. Every value carries its scope
 * (LIVE / WINDOW / ARCHIVE · NOT CURRENT) and the page-wide provenance from the status bar. No "Gold Vault" wording:
 * getsupplyinfo.gold_vault_balance is shown as the legacy reserve address balance (historical 25 % share, ended #25,000).
 */
(function (root) {
  'use strict';
  var U = root.SOSTU, UI = U.ui, M = U.xmodel, Q = U.query, D = U.data, S = root.CRState;
  var $ = function (i) { return document.getElementById(i); };
  var esc = UI.esc, num = UI.num, last = null, win = 288, mosMode = 'time', prodN = 288, dwN = 288, dtdDoc = null, npDoc = null;
  var cfgBase = D.BASE, SPEC = ['#22d3ee', '#e879f9', '#a3e635', '#facc15', '#fb923c', '#8b5cf6', '#3b82f6', '#4ade80'];
  try { win = +(localStorage.getItem('sostx_win') || 288) || 288; mosMode = localStorage.getItem('sostx_mos') || 'time'; } catch (e) {}

  // ---------- scope labels (LIVE / WINDOW / ARCHIVE) adjusted by the snapshot status: nothing is called LIVE unless it is
  function tag(scope, n) {
    var s = last ? last.status : 'loading', nl = s !== 'live';
    if (scope === 'live') return '<span class="tag ' + (nl ? 'nl' : 'live') + '">' + (nl ? 'LAST KNOWN · ' + s.toUpperCase() : 'LIVE') + '</span>';
    if (scope === 'window') return '<span class="tag win">WINDOW · ' + n + (nl ? ' · ' + s.toUpperCase() : '') + '</span>';
    return '<span class="tag arc">ARCHIVE · NOT CURRENT</span>';
  }
  function src(m) { return m && m.source ? ' <span class="muted" title="' + esc('Source: ' + m.source) + '">ⓘ</span>' : ''; }
  function addr(a, full) { return a ? '<a class="bl addr" href="#search=' + esc(a) + '" title="' + esc(a) + '">' + esc(full ? a : UI.short(a)) + '</a>' : '—'; }
  function blk(h) { return '<a class="bl" href="#search=' + h + '">#' + num(h) + '</a>'; }
  function dur(s) { return s == null ? '—' : UI.dur(s); }
  function card(k, n, d) { return '<div class="c"><div class="k">' + k + '</div><div class="n">' + n + '</div><div class="d">' + (d || '') + '</div></div>'; }
  var ivColor = function (s) { return s == null ? '#333' : s < 300 ? '#22d3ee' : s <= 900 ? '#39ff14' : s <= 1800 ? '#fbbf24' : '#fb923c'; };      // CR ui.js:26 (red → orange: no alarm red)
  var profColor = function (i) { return i == null ? '#333' : i < 0 ? '#22d3ee' : i === 0 ? '#39ff14' : i <= 10 ? '#a3e635' : i <= 20 ? '#fbbf24' : i <= 28 ? '#f97316' : '#e879f9'; };
  function hue(a) { var h = 5381; for (var i = 0; i < (a || '').length; i++) h = ((h << 5) + h + a.charCodeAt(i)) >>> 0; return 'hsl(' + (h % 360) + ',66%,58%)'; }   // CRJ CR10 djb2
  function tw(rows, n) { return rows.slice(Math.max(1, rows.length - n)); }

  // ---------- SIMPLE: cards, mosaic, latest
  function renderCards(s) {
    var st = s.state, a = st.active, ch = a.chain, tm = a.timing, c = a.consensus, j = a.jackpot, d = a.dtd, sp = a.supply, n = a.network;
    var ws = S.windowStats(s.rows.map(function (r) { return { t: r.t }; }), win);
    $('cards').innerHTML =
      card('Height ' + tag('live'), '#' + num(ch.height.value), 'tip age ' + dur(ch.tipAge.value) + ' · latest interval ' + dur(ch.latestInterval.value)) +
      card('Avg block time ' + tag('window', win), dur(ws.avg), 'median ' + dur(ws.median) + ' · target 600 s · 24/72/288: ' + dur(tm.avg24.value) + ' / ' + dur(tm.avg72.value) + ' / ' + dur(tm.avg288.value)) +
      card('bitsQ ' + tag('live') + src(c.bitsQ), num(c.bitsQ.value), 'Q16.16 ' + num(c.bitsQ.q16, 4) + ' · next ' + num(c.bitsQ.next)) +
      card('Equalizer ' + tag('live') + src(c.equalizerNext), esc(c.equalizerNext.value || '—'), 'next block · schedule lag ' + num(c.equalizerNext.lag) + ' · latest declared ' + esc(c.equalizerTip.value || '—')) +
      card('Active miners ' + tag('window', 288) + src(a.miners.active288), num(a.miners.active288.value), 'node count (geteligibleminers.active_288) · distinct producer addresses in the series: ' + num(a.miners.active288Series.value) + ' · addresses are not people') +
      card('Normal DTD ' + tag('live'), num(d.eligibleNext.value) + ' eligible', 'for #' + num(d.nextHeight.value) + ' · payout ' + num(d.payout.value, 4) + ' SOST') +
      card('Next Jackpot ' + tag('live'), '#' + num(j.nextHeight.value), num(j.blocksRemaining.value) + ' blocks · ~' + dur(j.etaSeconds.value) + ' (estimate) · eligible ' + num(j.eligible.value) + '/' + num(j.candidates.value)) +
      card('Supply ' + tag('live') + src(sp.total), num(sp.total.value, 2), 'circulating ' + num(sp.circulating.value, 2) + ' SOST') +
      card('Peers ' + tag('live'), num(n.connectedPeers.value), 'of the public node · ' + num(n.syncedPeers.value) + ' within 1 block · not a network census');
  }
  function renderMosaic(s) {
    var rs = s.rows.slice(-144).reverse();
    $('mosTag').innerHTML = tag('window', 144);
    $('mos').innerHTML = rs.map(function (r) {
      var col = mosMode === 'miner' ? hue(r.miner) : mosMode === 'prof' ? profColor(r.prof) : ivColor(r.dt);
      return '<a href="#search=' + r.h + '" class="' + (M.isJackpot(r.h) ? 'j' : '') + '" style="background:' + col + '" aria-label="Block ' + r.h + ', ' + (r.dt == null ? '' : UI.dur(r.dt)) + ', ' + M.profName(r.prof) + '" title="#' + r.h + ' · ' + (r.dt == null ? '' : UI.dur(r.dt)) + ' · ' + M.profName(r.prof) + ' · ' + UI.short(r.miner) + '"></a>';
    }).join('');
    $('mosLeg').innerHTML = mosMode === 'time' ? [['< 5 min', '#22d3ee'], ['5–15 min', '#39ff14'], ['15–30 min', '#fbbf24'], ['> 30 min', '#fb923c']].map(function (x) { return '<span><i style="background:' + x[1] + '"></i>' + x[0] + '</span>'; }).join('')
      : mosMode === 'prof' ? [['E (relief)', '#22d3ee'], ['B0', '#39ff14'], ['H1–H10', '#a3e635'], ['H11–H20', '#fbbf24'], ['H21–H28', '#f97316'], ['H29–H35', '#e879f9']].map(function (x) { return '<span><i style="background:' + x[1] + '"></i>' + x[0] + '</span>'; }).join('')
      : '<span>one hue per producer address (djb2 hash)</span>';
  }
  function renderLatest(s) {
    $('latTag').innerHTML = tag('window', 20);
    var rs = s.rows.slice(-20).reverse();
    $('latest').innerHTML = '<table class="tbl"><thead><tr><th>Height</th><th>Time (UTC)</th><th class="r">Interval</th><th>Equalizer</th><th class="r">bitsQ</th><th>Producer</th></tr></thead><tbody>' +
      rs.map(function (r) { return '<tr><td>' + blk(r.h) + (M.isJackpot(r.h) ? ' <span class="tag win">JACKPOT</span>' : '') + '</td><td>' + UI.utc(r.t).slice(0, 19) + '</td><td class="r">' + dur(r.dt) + '</td><td>' + M.profName(r.prof) + '</td><td class="r">' + num(r.bq) + '</td><td>' + addr(r.miner) + '</td></tr>'; }).join('') + '</tbody></table>';
  }

  // ---------- ADVANCED: all CR rows grouped, with scope per group
  var GROUPS = [['chain', 'Chain', 'live'], ['timing', 'Block timing', 'window'], ['consensus', 'bitsQ', 'live'], ['eq', 'Equalizer', 'live'], ['miners', 'Active miners', 'window'],
    ['dtd', 'Normal DTD', 'live'], ['jp', 'DTD Jackpot', 'live'], ['net', 'Network', 'live'], ['supply', 'Supply', 'live'], ['ev', 'Events (since public-node boot)', 'live'], ['hist', 'Historical', 'archive']];
  function fmtRow(r) {
    var v = r.value;
    if (v == null) return '<span class="muted">n/a</span>';
    if (/^sost1/.test(v)) return addr(v);
    if (r.id === 'dtd.cooldown') return v ? v.split(',').map(function (x) { return addr(x); }).join(', ') : 'none';
    if (r.id === 'ev.boot') return UI.utc(v);
    if (r.id === 'hist.profiles') { var o = JSON.parse(v); return Object.keys(o).sort(function (a, b) { return a - b; }).map(function (k) { return M.profName(+k) + ' ' + o[k]; }).join(' · '); }
    if (/\(s\)$/.test(r.label)) return dur(v) + ' <span class="muted">(' + num(v) + ' s)</span>';
    if (typeof v === 'number') return num(v, Number.isInteger(v) ? 0 : 4);
    if (typeof v === 'boolean') return v ? 'yes' : 'no';
    return esc(v);
  }
  function renderCR(s) {
    var rows = M.crRows(s.state);
    $('crTag').innerHTML = '<span class="muted">' + rows.length + ' rows</span>';
    $('crRows').innerHTML = GROUPS.map(function (g) {
      var gr = rows.filter(function (r) { return r.id.split('.')[0] === g[0]; });
      return '<h3 style="font:600 12px var(--f-mono);letter-spacing:.14em;margin:14px 0 6px;text-transform:uppercase">' + g[1] + ' ' + tag(g[2], g[0] === 'timing' ? '24/72/288' : 288) + '</h3><div class="kv g">' +
        gr.map(function (r) { return '<div data-row="' + r.id + '"' + (/profiles|cooldown|Producer|projected/.test(r.id + r.label) ? ' class="wide"' : '') + '><span class="k">' + esc(r.label === 'Legacy reserve address (gold_vault_balance)' ? 'Legacy reserve address · historical 25 % share (ended #25,000)' : r.label) + '</span><span class="v">' + fmtRow(r) + '</span></div>'; }).join('') + '</div>';
    }).join('') + candidates(s.state);
  }
  function candidates(st) {
    var c = st.active.jackpot.candidateList;
    return '<details class="more" style="margin-top:10px"><summary>Jackpot V2 candidates (' + c.length + ')</summary><div class="tblw"><table class="tbl"><thead><tr><th>Candidate</th><th class="r">PoW blocks</th><th>NODE_BIND</th><th class="r">Heartbeats</th><th>Eligible</th></tr></thead><tbody>' +
      c.map(function (x) { return '<tr><td>' + addr(x.addr) + '</td><td class="r">' + num(x.powBlocks) + '</td><td>' + (x.bound ? 'bound' : 'not bound') + '</td><td class="r">' + num(x.heartbeats) + '/' + num(x.heartbeatsRequired) + '</td><td>' + (x.eligible ? 'yes' : 'no') + '</td></tr>'; }).join('') +
      '</tbody><caption>Not eligible does not mean penalised. Source: getjackpotv2audit for the next draw.</caption></table></div></details>';
  }

  // ---------- engine charts (SVG)
  function line(pts, W, H, col, lo, hi) {
    if (!pts.length) return ''; var r = hi - lo || 1;
    return '<polyline fill="none" stroke="' + col + '" stroke-width="1.4" points="' + pts.map(function (v, i) { return (i / Math.max(1, pts.length - 1) * W).toFixed(1) + ',' + (H - 4 - (v - lo) / r * (H - 12)).toFixed(1); }).join(' ') + '"/>';
  }
  function renderEngine(s) {
    var d = M.derive(M.engineRows(s.rows), 288), c = M.chips(d); if (!c) return;
    $('engTag').innerHTML = tag('window', d.length);
    var ch = function (l, v) { return '<span class="chip">' + l + '<b>' + v + '</b></span>'; };
    $('engChips').innerHTML = ch('TIP', '#' + num(c.tip)) + ch('SCHEDULE LAG', (c.lag > 0 ? '+' : '') + c.lag + ' blk') + ch('EQUALIZER', M.profName(c.equalizer)) + ch('bitsQ', c.bitsQ.toFixed(4)) +
      ch('AVG288 DEV', c.dev == null ? '—' : (c.dev > 0 ? '+' : '') + c.dev + ' s') + ch(c.inBand ? 'IN DEAD BAND' : 'bitsQ STEPPING', c.inBand ? 'bitsQ held ' + c.frozen + ' blk' : (c.dq > 0 ? '+' : '') + c.dq.toFixed(2) + '% · band ' + M.stepBand(c.dev) + '%') +
      ch('INTERVAL avg · median', UI.dur(c.avg) + ' · ' + UI.dur(c.median)) + ch('PRODUCERS', c.producers) + ch('EQUALIZER MODEL', c.known ? c.matched + '/' + c.known + (c.matched === c.known ? ' ✓' : '') : '—') +
      ch('BURST 72', c.burst == null ? '—' : c.burst.toFixed(1) + ' %') + ch('VOL 72', c.vol == null ? '—' : c.vol.toFixed(1) + ' %');
    var W = 860, n = d.length, bw = W / n;
    var cap = 14400, sq = function (v) { return Math.sqrt(Math.min(v, cap) / cap); };
    var bars = d.map(function (r, i) { var h = sq(Math.max(0, r.dt)) * 110; return '<rect x="' + (i * bw).toFixed(1) + '" y="' + (116 - h).toFixed(1) + '" width="' + Math.max(1, bw - .6).toFixed(1) + '" height="' + h.toFixed(1) + '" fill="' + ivColor(r.dt) + '"><title>#' + r.h + ' ' + UI.dur(r.dt) + '</title></rect>'; }).join('');
    var gl = [600, 1200, 3600].map(function (v) { var y = 116 - sq(v) * 110; return '<line x1="0" x2="' + W + '" y1="' + y + '" y2="' + y + '" stroke="#444" stroke-dasharray="3 3"/><text x="' + (W - 2) + '" y="' + (y - 2) + '" text-anchor="end">' + (v === 600 ? '600 s target' : v === 1200 ? '1200 s difficulty relief' : '3600 s anti-stall') + '</text>'; }).join('');
    var lags = d.map(function (r) { return r.lag; }), lmin = Math.min.apply(null, lags), lmax = Math.max.apply(null, lags);
    var rib = d.map(function (r, i) { return '<rect x="' + (i * bw).toFixed(1) + '" y="0" width="' + Math.max(1, bw).toFixed(1) + '" height="14" fill="' + profColor(r.p) + '"><title>#' + r.h + ' ' + M.profName(r.p) + ' · model ' + M.profName(r.model) + (r.match === false ? ' · differs' : '') + '</title></rect>'; }).join('');
    var devs = d.filter(function (r) { return r.dev != null; }).map(function (r) { return r.dev; }), dmax = Math.max(30, Math.max.apply(null, devs.map(Math.abs)));
    var bu = d.filter(function (r) { return r.burst != null; });
    $('engCharts').innerHTML =
      '<div class="k muted">Block times · sqrt scale, capped at 4 h</div><svg class="ch" viewBox="0 0 ' + W + ' 120" role="img" aria-label="Block intervals of the last ' + n + ' blocks">' + gl + bars + '</svg>' +
      '<div class="k muted">Schedule lag (blocks; + = ahead of the 600 s schedule) · ' + lmin + ' … ' + lmax + '</div><svg class="ch" viewBox="0 0 ' + W + ' 70" role="img" aria-label="Schedule lag">' + line(lags, W, 70, '#22d3ee', lmin, lmax) + '</svg>' +
      '<div class="k muted">Equalizer profile ribbon (recorded by the node)</div><svg class="ch" viewBox="0 0 ' + W + ' 14" role="img" aria-label="Equalizer profile per block">' + rib + '</svg>' +
      '<div class="k muted">AVG288 deviation (s) · dead band ±15 s shaded</div><svg class="ch" viewBox="0 0 ' + W + ' 70" role="img" aria-label="AVG288 deviation"><rect x="0" width="' + W + '" y="' + (66 - (15 + dmax) / (2 * dmax) * 58).toFixed(1) + '" height="' + (30 / (2 * dmax) * 58).toFixed(1) + '" fill="#39ff1422"/>' + line(devs, W, 70, '#facc15', -dmax, dmax) + '</svg>' +
      '<div class="k muted">Burst (cyan) and volatility (violet), rolling 72</div><svg class="ch" viewBox="0 0 ' + W + ' 70" role="img" aria-label="Burst and volatility">' + line(bu.map(function (r) { return r.burst; }), W, 70, '#22d3ee', 0, 100) + line(bu.map(function (r) { return r.vol; }), W, 70, '#8b5cf6', 0, Math.max(100, Math.max.apply(null, bu.map(function (r) { return r.vol; })))) + '</svg>';
  }
  function renderHistory(s) {
    var h = s.state.historical, peak = h.peakActive288InSeries.value, hist = h.profileHistogram, W = 860, bw = W / 43, mx = 1;
    Object.keys(hist).forEach(function (k) { mx = Math.max(mx, hist[k]); });
    var hb = ''; for (var i = -7; i <= 35; i++) { var cnt = hist[i] || 0, hh = cnt / mx * 70; hb += '<rect x="' + ((i + 7) * bw).toFixed(1) + '" y="' + (76 - hh).toFixed(1) + '" width="' + (bw - 2).toFixed(1) + '" height="' + hh.toFixed(1) + '" fill="' + profColor(i) + '"><title>' + M.profName(i) + ': ' + cnt + '</title></rect>'; }
    hb += '<text x="0" y="90">E7</text><text x="' + (7 * bw).toFixed(0) + '" y="90">B0</text><text x="' + (27 * bw).toFixed(0) + '" y="90">H20</text><text x="' + W + '" y="90" text-anchor="end">H35</text>';
    var bq = h.bitsQSeries.map(function (x) { return x[1]; }), bmin = Math.min.apply(null, bq), bmax = Math.max.apply(null, bq), rg = h.seriesRange ? '#' + num(h.seriesRange[0]) + '–#' + num(h.seriesRange[1]) : '—';
    $('histTag').innerHTML = tag('archive');
    $('hist').innerHTML = '<div class="kv g"><div><span class="k">Distinct producers (all time)</span><span class="v">' + num(h.uniqueProducersSinceGenesis.value) + '</span></div><div><span class="k">Since #' + num(h.producersSinceWindowStart.from) + '</span><span class="v">' + num(h.producersSinceWindowStart.value) + '</span></div>' +
      '<div><span class="k">Peak distinct producers in one 288 window</span><span class="v">' + (peak ? num(peak.n) + ' at #' + num(peak.at) : '—') + '</span></div><div><span class="k">Schedule since genesis</span><span class="v">' + (h.scheduleSinceGenesis.value >= 0 ? '+' : '') + num(h.scheduleSinceGenesis.value) + ' blocks</span></div></div>' +
      '<div class="k muted" style="margin-top:10px">Equalizer profiles mined (' + rg + ')</div><svg class="ch" viewBox="0 0 ' + W + ' 94" role="img" aria-label="Histogram of Equalizer profiles E7 to H35">' + hb + '</svg>' +
      '<div class="k muted">bitsQ evolution (' + rg + ') · ' + num(bmin) + ' … ' + num(bmax) + '</div><svg class="ch" viewBox="0 0 ' + W + ' 70" role="img" aria-label="bitsQ over the series">' + line(bq, W, 70, '#d9cbb0', bmin, bmax) + '</svg>' +
      '<details class="more"><summary>Protocol milestones (' + h.milestones.length + ')</summary><ul class="note">' + h.milestones.map(function (m) { return '<li>#' + num(m.h) + ' — ' + esc(m.label) + ' <span class="muted">· ' + esc(m.src) + '</span></li>'; }).join('') + '</ul></details>' +
      '<p class="ex">Range-bound: computed over the loaded series only; earlier history is not in it. The concentration history per 288-block window is on the <a class="bl" href="' + ((root.SOSTU_CONFIG && root.SOSTU_CONFIG.homeHref) || 'home.html') + '#concentration">home page</a>.</p>';
  }
  function periods(el, P, cur, avail, set) {
    $(el).innerHTML = P.map(function (p) { var ok = p[1] === Infinity || avail >= p[1]; return '<button type="button" data-n="' + p[1] + '" aria-pressed="' + (p[1] === cur) + '"' + (ok ? '' : ' disabled title="not enough data loaded"') + '>' + p[0] + '</button>'; }).join('');
    $(el).onclick = function (e) { var b = e.target.closest('button'); if (b && !b.disabled) set(+b.dataset.n || Infinity); };
  }
  function prodRows() { return dtdDoc ? dtdDoc.recent.map(function (r) { return { h: r.h, m: r.m }; }) : last.rows.map(function (r) { return { h: r.h, m: r.miner }; }); }
  function renderProducers() {
    var rs = prodRows(), p = M.producers(rs, prodN);
    periods('prodP', M.PD_PERIODS, prodN, rs.length, function (n) { prodN = n; renderProducers(); });
    $('prodTag').innerHTML = tag(prodN === Infinity ? 'archive' : 'window', p.n) + ' <span class="muted">' + (dtdDoc ? 'DTD history snapshot' : 'block series') + ' #' + num(p.from) + '–#' + num(p.to) + '</span>';
    $('prod').innerHTML = '<div class="kv g"><div><span class="k">Top 1</span><span class="v">' + (p.top1 == null ? '—' : p.top1.toFixed(1) + ' %') + '</span></div><div><span class="k">Top 3</span><span class="v">' + p.top3.toFixed(1) + ' %</span></div><div><span class="k">Distinct addresses</span><span class="v">' + p.unique + '</span></div><div><span class="k">Blocks</span><span class="v">' + num(p.n) + '</span></div></div>' +
      '<div class="tblw"><table class="tbl"><thead><tr><th>#</th><th>Producer address</th><th class="r">Blocks</th><th class="r">Share</th><th>Last block</th></tr></thead><tbody>' +
      p.list.slice(0, 20).map(function (x, i) { return '<tr><td>' + (i + 1) + '</td><td>' + addr(x.addr) + '</td><td class="r">' + num(x.blocks) + '</td><td class="r">' + x.share.toFixed(2) + ' %</td><td>' + blk(x.last) + '</td></tr>'; }).join('') + '</tbody></table></div>' +
      (dtdDoc ? '' : '<p class="note">Longer periods need the DTD history snapshot (Advanced › DTD › load).</p>');
  }
  function renderDTD(s) {
    var d = s.state.active.dtd, h = s.state.meta.height;
    $('dtdTag').innerHTML = tag('live');
    $('dtdNow').innerHTML = '<div class="kv g"><div><span class="k">Eligible for #' + num(d.nextHeight.value) + '</span><span class="v">' + num(d.eligibleNext.value) + '</span></div><div><span class="k">Cooldown window</span><span class="v">' + num(d.cooldownWindow.value) + ' blocks</span></div>' +
      '<div class="wide"><span class="k">In cooldown</span><span class="v">' + ((d.cooldownMiners.value || []).map(function (a) { return addr(a); }).join(', ') || 'none') + '</span></div><div><span class="k">Payout</span><span class="v">' + num(d.payout.value, 8) + ' SOST</span></div>' +
      '<div class="wide"><span class="k">Projected next winner (changes with the tip)</span><span class="v">' + addr(d.projectedWinner.value) + ' ' + UI.pv('projected') + '</span></div><div><span class="k">Era at the tip</span><span class="v">' + M.dtdEra(h) + '</span></div></div>' +
      '<p class="ex">Eligibility: an SbPoW-signed block in the last 288, 6-block cooldown (yields if it would empty the set), anti-dominance (≥ 10 % of 288) armed only with ≥ 11 distinct miners. Independent of the Jackpot: at a jackpot height both draws run in the same block.</p>';
    if (dtdDoc) renderDW();
  }
  function renderDW() {
    var tip = dtdDoc.scannedHeight, m = M.dtdWinners(dtdDoc.ph2.payouts, tip, dwN);
    periods('dtdP', M.DW_PERIODS, dwN, Infinity, function (n) { dwN = n; renderDW(); });
    $('dtdW').innerHTML = '<div class="k muted">' + tag(dwN === Infinity ? 'archive' : 'window', dwN === Infinity ? 'all' : dwN) + ' DTD payout history snapshot · scanned to #' + num(tip) + '</div><div class="kv g"><div><span class="k">Payouts</span><span class="v">' + num(m.payouts) + '</span></div><div><span class="k">Distinct winners</span><span class="v">' + m.unique + '</span></div><div><span class="k">Top 1 share of paid</span><span class="v">' + (m.top1 == null ? '—' : m.top1.toFixed(1) + ' %') + '</span></div><div><span class="k">Paid</span><span class="v">' + num(m.paid, 2) + ' SOST</span></div></div>' +
      '<div class="tblw"><table class="tbl"><thead><tr><th>#</th><th>Winner</th><th class="r">Wins</th><th class="r">SOST</th><th class="r">Share</th><th>Last</th></tr></thead><tbody>' + m.list.slice(0, 15).map(function (x, i) { return '<tr><td>' + (i + 1) + '</td><td>' + addr(x.addr) + '</td><td class="r">' + x.wins + '</td><td class="r">' + num(x.sost, 2) + '</td><td class="r">' + x.share.toFixed(1) + ' %</td><td>' + blk(x.last) + '</td></tr>'; }).join('') + '</tbody></table></div>';
    renderProducers();
  }
  function renderJackpot(s) {
    var j = s.state.active.jackpot, h = s.state.meta.height;
    $('jpTag').innerHTML = tag('live');
    $('jpNow').innerHTML = '<div class="kv g"><div><span class="k">Next draw</span><span class="v">' + blk(j.nextHeight.value) + '</span></div><div><span class="k">Blocks left · ETA (estimate)</span><span class="v">' + num(j.blocksRemaining.value) + ' · ~' + dur(j.etaSeconds.value) + '</span></div>' +
      '<div><span class="k">Eligible / candidates</span><span class="v">' + num(j.eligible.value) + ' / ' + num(j.candidates.value) + '</span></div><div><span class="k">Pot / reserve</span><span class="v">' + num(j.pot.value, 2) + ' / ' + num(j.reserve.value, 2) + ' SOST</span></div>' +
      '<div><span class="k">Rules</span><span class="v">≥ ' + num(j.minPowBlocks.value) + ' SbPoW blocks in ' + num(j.powWindow.value) + ' · heartbeats ' + num(j.heartbeatRequired.value) + ' · NODE_BIND</span></div><div><span class="k">If 0 eligible at the draw</span><span class="v">' + (j.rolloverIfNoneEligible.value ? 'rollover (currently 0 eligible)' : 'rollover') + '</span></div></div>' + candidates(s.state);
    var e = s.earnings, ja = s.doc && s.doc.bundle && s.doc.bundle.jackpotAudits;
    if (!e) { $('jpHist').innerHTML = '<p class="note">' + UI.pv('unavailable', 'JACKPOT HISTORY UNAVAILABLE') + ' address_earnings.json not loaded.</p>'; return; }
    var jp = M.jackpots(e.jackpots, Math.min(h, e.tip), ja);
    $('jpHist').innerHTML = '<div class="k muted">' + tag('archive') + ' Every scheduled draw #25,290 + 288·k up to #' + num(Math.min(h, e.tip)) + ' · confirmed payouts from the earnings index (canonical blocks)</div>' +
      '<div class="kv g"><div><span class="k">Draws</span><span class="v">' + jp.draws + '</span></div><div><span class="k">Paid</span><span class="v">' + jp.paid + '</span></div><div><span class="k">No payout (rollover)</span><span class="v">' + jp.noPayout + '</span></div><div><span class="k">Total paid</span><span class="v">' + num(jp.total, 2) + ' SOST</span></div></div>' +
      '<details class="more"><summary>All draws (' + jp.draws + ')</summary><div class="tblw"><table class="tbl"><thead><tr><th>Block</th><th>Rules</th><th>Winner</th><th class="r">SOST</th><th class="r">Eligible (audit)</th></tr></thead><tbody>' +
      jp.list.map(function (x) { return '<tr><td>' + blk(x.h) + '</td><td>' + (x.v2 ? 'V2' : 'V15') + '</td><td>' + (x.paid ? addr(x.addr) : '<span class="muted">no payout</span>') + '</td><td class="r">' + (x.paid ? num(x.sost, 2) : '0') + '</td><td class="r">' + (x.audit ? num(x.audit.eligible_count) : '<span class="muted">' + (x.v2 ? 'not collected' : '—') + '</span>') + '</td></tr>'; }).join('') +
      '</tbody><caption>Audit column from the collector\'s past getjackpotv2audit group when deployed; otherwise “not collected”, never invented.</caption></table></div></details>';
  }
  function renderNodes(s) {
    var n = s.state.active.network;
    $('nodesTag').innerHTML = tag('live');
    $('netNow').innerHTML = '<div class="kv g"><div><span class="k">Connected peers</span><span class="v">' + num(n.connectedPeers.value) + '</span></div><div><span class="k">Synced peers (≥ tip−1)</span><span class="v">' + num(n.syncedPeers.value) + '</span></div><div><span class="k">Unique active nodes seen</span><span class="v">' + num(n.uniqueActiveNodes.value) + '</span></div><div><span class="k">Public node</span><span class="v">' + esc(n.localStatus.value || '—') + '</span></div></div>' +
      '<div class="tblw"><table class="tbl"><thead><tr><th>Peer</th><th>Dir</th><th class="r">Height</th><th>Handshake</th></tr></thead><tbody>' + n.peers.map(function (p) { return '<tr><td>' + esc(p.addr) + '</td><td>' + esc(p.direction) + '</td><td class="r">' + num(p.height) + '</td><td>' + (p.acked ? 'acked' : 'pending') + '</td></tr>'; }).join('') + '</tbody><caption>Peers of the public node only — not a census of the SOST network.</caption></table></div>';
    if (npDoc) renderBound();
  }
  function renderBound() {
    var b = M.boundNodes(npDoc);
    $('bound').innerHTML = '<div class="k muted">' + tag('live') + ' NODE_BIND participation snapshot · epoch ' + b.epoch + ' · block ' + b.into + '/' + b.epochLen + ' · indexed to #' + num(b.tip) + '</div><div class="kv g">' +
      [['Bound identities', b.totals.bound_identities], ['Active', b.totals.active], ['Bind txs', b.totals.bind_txs], ['Heartbeat txs', b.totals.heartbeat_txs], ['Node-ready for #' + num(b.next.height), b.nodeReady]].map(function (x) { return '<div><span class="k">' + x[0] + '</span><span class="v">' + num(x[1]) + '</span></div>'; }).join('') + '</div>' +
      '<div class="tblw"><table class="tbl"><thead><tr><th>Miner identity</th><th>Bind</th><th class="r">Coverage</th><th class="r">Streak</th><th>Last heartbeat</th><th>Status</th><th>Next draw (node)</th></tr></thead><tbody>' +
      b.nodes.map(function (x) { return '<tr><td>' + addr(x.miner) + '</td><td>' + blk(x.bind_height) + ' v' + x.bind_version + '</td><td class="r">' + x.epochs_covered + '/' + x.epochs_expected + ' · ' + Math.round(100 * x.coverage) + ' %</td><td class="r">' + x.streak + '</td><td>' + blk(x.last_heartbeat_height) + (x.current_epoch_sent ? ' · this epoch ✓' : '') + '</td><td>' + esc(x.status) + '</td><td>' + (x.next_jackpot && x.next_jackpot.node_condition_met ? '✓ ' : '✗ ') + (x.next_jackpot ? x.next_jackpot.in_window + '/' + x.next_jackpot.required : '') + '</td></tr>'; }).join('') +
      '</tbody><caption>' + esc(b.note) + '</caption></table></div>';
  }
  function renderEvents(s) {
    var e = s.state.events, sb = e.submitblock.value || {};
    $('evTag').innerHTML = tag('live');
    var reasons = Object.keys(sb.reasons || {}).map(function (k) { return esc(k) + ' ' + sb.reasons[k]; }).join(', ') || 'none';
    var obs = e.observed.slice(-8).reverse().map(function (o) { return UI.utc(o.t).slice(11, 19) + ' ' + esc(o.kind) + ' — ' + esc(o.detail); }).join('<br>') || 'none observed since the collector started';
    $('ev').innerHTML = '<div class="kv g"><div><span class="k">Blocks submitted to the public node (accepted / received)</span><span class="v">' + num(sb.accepted) + ' / ' + num(sb.received) + '</span></div><div class="wide"><span class="k">Rejected (reasons)</span><span class="v">' + num(sb.rejected) + ' (' + reasons + ')</span></div>' +
      '<div><span class="k">Misbehavior events</span><span class="v">' + num(e.misbehavior.value) + '</span></div><div><span class="k">Public node uptime</span><span class="v">' + dur(e.nodeUptime.value) + ' · boot ' + UI.utc(e.nodeBoot.value) + '</span></div>' +
      '<div><span class="k">Reorgs</span><span class="v">n/a — not exposed by the public RPC (never shown as 0)' + (s.reorg ? ' · this tab observed #' + s.reorg.fromHeight + ' → #' + s.reorg.toHeight : '') + '</span></div><div><span class="k">Observed by the collector</span><span class="v">' + e.observed.length + '</span></div></div><p class="note">' + obs + '</p>' +
      '<div class="kv g" style="margin-top:8px">' + s.state.health.map(function (f) { return '<div><span class="k">' + esc(f.name) + ' <span class="muted">(' + esc(f.rule) + ')</span></span><span class="v">' + esc(f.value) + ' · ' + esc(f.state) + '</span></div>'; }).join('') + '</div>';
  }
  function renderEmission(s) {
    var h = s.state.meta.height, cur = Math.floor(h / M.EMI.EPOCH);
    $('em').innerHTML = '<div class="tblw"><table class="tbl"><thead><tr><th>Epoch</th><th>Blocks</th><th class="r">Reward / block</th><th class="r">Miner · DTD</th><th class="r">Cumulative</th><th class="r">% of max</th></tr></thead><tbody>' +
      M.epochs().map(function (e) { return '<tr' + (e.epoch === cur ? ' style="background:#22d3ee14"' : '') + '><td>' + e.epoch + (e.epoch === cur ? ' ← now' : '') + '</td><td>#' + num(e.from) + '–#' + num(e.to) + '</td><td class="r">' + num(e.reward / 1e8, 8) + '</td><td class="r">' + num(e.miner / 1e8, 4) + ' · ' + num(e.dtd / 1e8, 4) + '</td><td class="r">' + num(e.cumulative / 1e8, 0) + '</td><td class="r">' + e.pct.toFixed(3) + ' %</td></tr>'; }).join('') +
      '</tbody><caption>reward_e = ⌊785,100,863 · q^e⌋ stocks, q = e^−0.25, 131,553 blocks per epoch. 50 % miner / 50 % DTD since #25,000 (V15); the earlier 50/25/25 split is historical.</caption></table></div>';
  }

  // ---------- detail (on-demand)
  function kvs(o) { return '<div class="kv">' + o.map(function (x) { return '<span class="k">' + x[0] + '</span><span class="v">' + x[1] + '</span>'; }).join('') + '</div>'; }
  async function lookup(q) {
    var el = $('detail'); el.className = 'p show'; el.innerHTML = '<h2>Looking up ' + esc(q) + ' <span class="tag arc">' + Q.mode().toUpperCase() + '</span></h2><div class="skeleton" style="height:120px"></div>';
    try {
      // addresses: the shared ADDRESS INSPECTOR (core/u-addr.js) — current state from the node through Q (same limits, same cache,
      // same LIVE / FIXTURE label), historical rewards and NODE_BIND from the collector files. Owner P0, 4 Nov 2026.
      var cq = Q.classify(q);
      if (cq.kind === 'address' && U.addrInspector) {
        el.innerHTML = '<h2>Address <span class="tag live">' + (Q.mode() === 'fixture' ? 'FIXTURE · CAPTURED RPC · NOT LIVE' : Q.mode() === 'own-node' ? 'YOUR NODE' : 'PUBLIC NODE RPC') + '</span></h2><div id="uaiBox"></div>' +
          '<p class="note"><button class="btn small" type="button" id="dClose">close</button></p>';
        U.addrInspector.render($('uaiBox'), cq.v, { rpc: Q.call, mode: Q.mode(), tip: last && last.state && last.state.meta ? last.state.meta.height : null, apiBase: cfgBase,
          link: function (k, v, t) { return '<a class="bl" href="#search=' + esc(v) + '">' + esc(t) + '</a>'; },
          permalink: location.origin + location.pathname + '#search=' + cq.v, fullHref: '../sost-explorer.html?search=' + cq.v });
        $('dClose').onclick = function () { el.className = 'p'; history.replaceState(null, '', location.pathname + location.search); };
        el.focus({ preventScroll: true }); el.scrollIntoView({ block: 'start', behavior: UI.RM ? 'auto' : 'smooth' });
        setTimeout(function () { $('qStats').textContent = Q.stats.calls + ' RPC (' + Q.stats.perMinute() + ' in the last minute, limit ' + Q.LIMITS.perMinute + '/min)'; }, 3000);
        return;
      }
      var r = await Q.search(q), d = r.data, h = '';
      var vtag = '<span class="tag live">' + (Q.mode() === 'fixture' ? 'FIXTURE · CAPTURED RPC · NOT LIVE' : Q.mode() === 'own-node' ? 'YOUR NODE' : 'PUBLIC NODE RPC') + '</span>';
      if (r.kind === 'block') {
        var tip = last && last.state.meta.height, tx = d.txids || [];
        h = '<h2>Block #' + num(d.height) + ' ' + vtag + (M.isJackpot(d.height) ? ' <span class="tag win">JACKPOT HEIGHT</span>' : '') + '</h2>' + kvs([
          ['hash', '<code>' + esc(d.hash) + '</code>'], ['previous', d.previousblockhash ? '<a class="bl" href="#search=' + esc(d.previousblockhash) + '">' + esc(UI.short(d.previousblockhash, 12)) + '</a>' : '—'],
          ['time', UI.utc(d.time)], ['confirmations', tip ? num(tip - d.height + 1) : '—'], ['bitsQ', num(d.bits_q) + ' (' + (d.bits_q / 65536).toFixed(4) + ')'],
          ['Equalizer declared', esc(d.casert_mode || M.profName(d.casert_profile_index)) + ' · ceiling at height ' + M.profName(M.profileCeiling(d.height))],
          ['producer', addr(d.miner_address, true)], ['subsidy', d.subsidy != null ? num(d.subsidy / 1e8, 8) + ' SOST' : '—'],
          ['split', d.height >= 25000 ? '50 % miner · 50 % DTD (V15, since #25,000)' : d.height >= 7100 ? '50 % miner · 25 % legacy reserve · 25 % PoPC pool (historical, pre-V15); DTD by era ' + M.dtdEra(d.height) : '50 / 25 / 25 (historical)'],
          ['normal DTD', d.lottery_payout ? num(d.lottery_payout / 1e8, 8) + ' SOST → ' + addr(d.lottery_winner_address) : 'no payout in this block'],
          ['transactions', num(d.tx_count != null ? d.tx_count : tx.length) + (tx.length ? ' · ' + tx.slice(0, 6).map(function (t) { return '<a class="bl" href="#search=' + t + '">' + UI.short(t, 8) + '</a>'; }).join(', ') : '')],
          ['DTD era', M.dtdEra(d.height)]]);
      } else if (r.kind === 'tx') {
        h = '<h2>Transaction ' + vtag + '</h2>' + kvs([['txid', '<code>' + esc(d.txid) + '</code>'], ['block', d.block_height != null ? blk(d.block_height) : d.confirmed === false ? 'mempool' : '—'], ['size', d.size != null ? num(d.size) + ' bytes' : '—'],
          ['type', esc(d.tx_type != null ? d.tx_type : d.type || '—')], ['outputs', (d.outputs || d.vout || []).map(function (o) { return num((o.amount != null ? o.amount : o.value) / (o.amount > 1e6 ? 1e8 : 1), 8) + ' → ' + addr(o.address) + (o.type != null ? ' <span class="muted">' + esc(M.UTXO_TYPE[o.type] || o.type) + '</span>' : ''); }).join('<br>') || '—']]);
      } else {
        var info = d.info || {}, rc = M.reconcile(info, last ? last.state.meta.height : 0), fl = d.flows || {};
        h = '<h2>Address ' + vtag + '</h2>' + kvs([['address', '<code>' + esc(info.address) + '</code>'], ['balance (node)', num(rc.balance, 8) + ' SOST'], ['Σ UTXO', num(rc.sumUtxo, 8) + (rc.match ? ' <span class="warn-ok">✓ reconciles</span>' : ' <span class="muted">≠ (see node)</span>')],
          ['UTXOs', num(rc.utxos)], ['immature coinbase (< 1,000 conf.)', num(rc.immature, 8)], ['locked (bond / escrow / retired htlc)', num(rc.locked, 8)], ['spendable now', num(rc.spendable, 8)],
          ['received (non-mining)', fl.received_non_mining != null ? num(fl.received_non_mining / 1e8, 8) : '—'], ['sent (non-mining)', fl.sent_non_mining != null ? num(fl.sent_non_mining / 1e8, 8) : '—']]);
        var u = (info.utxos || []).slice().sort(function (a, b) { return b.height - a.height; }).slice(0, 25);
        if (u.length) h += '<details class="more"><summary>UTXOs (newest 25 of ' + num(rc.utxos) + ')</summary><div class="tblw"><table class="tbl"><thead><tr><th>Outpoint</th><th class="r">Amount</th><th>Height</th><th>Type</th></tr></thead><tbody>' + u.map(function (x) { return '<tr><td>' + UI.short(x.txid, 8) + ':' + x.vout + '</td><td class="r">' + num(x.amount, 8) + '</td><td>' + blk(x.height) + '</td><td>' + esc(M.UTXO_TYPE[x.type] || x.type) + '</td></tr>'; }).join('') + '</tbody></table></div></details>';
      }
      el.innerHTML = h + '<p class="note">' + r.calls + ' RPC call' + (r.calls === 1 ? '' : 's') + ' for this lookup · <button class="btn small" type="button" id="dClose">close</button></p>';
    } catch (e) {
      el.innerHTML = '<h2>' + esc(q) + ' ' + UI.pv('unavailable') + '</h2><p class="ex">' + esc(e.message) + '</p><p><button class="btn small" type="button" id="dClose">close</button></p>';
    }
    $('dClose').onclick = function () { el.className = 'p'; history.replaceState(null, '', location.pathname + location.search); };
    el.focus({ preventScroll: true }); el.scrollIntoView({ block: 'start', behavior: UI.RM ? 'auto' : 'smooth' });
    $('qStats').textContent = Q.stats.calls + ' RPC (' + Q.stats.perMinute() + ' in the last minute, limit ' + Q.LIMITS.perMinute + '/min)';
  }

  // ---------- lazy snapshots
  function getJSON(name) { return fetch(cfgBase + name, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(name + ' HTTP ' + r.status); return r.json(); }); }
  function loadDtd() { $('dtdW').innerHTML = '<div class="skeleton" style="height:120px"></div>'; return getJSON('dtd_history_acc.json').then(function (j) { dtdDoc = j; renderDW(); }, function (e) { $('dtdW').innerHTML = '<p class="note">' + UI.pv('unavailable') + ' ' + esc(e.message) + '</p>'; }); }
  function loadNP() { $('bound').innerHTML = '<div class="skeleton" style="height:120px"></div>'; return getJSON('node_participation.json').then(function (j) { npDoc = j; renderBound(); }, function (e) { $('bound').innerHTML = '<p class="note">' + UI.pv('unavailable') + ' ' + esc(e.message) + '</p>'; }); }

  // ---------- routing and controls
  function setView(adv, noHash) {
    document.body.classList.toggle('advanced', adv); $('vSimple').setAttribute('aria-pressed', !adv); $('vAdv').setAttribute('aria-pressed', adv);
    if (adv && last && last.state) renderAdvanced(last);
    if (!noHash) history.replaceState(null, '', adv ? '#view=advanced' : location.pathname + location.search);
  }
  function route() {
    var h = new URLSearchParams(location.hash.slice(1));
    if (h.get('search')) { $('q').value = h.get('search'); lookup(h.get('search')); }
    if (h.get('view') === 'advanced' || h.get('panel')) {
      setView(true, true); var p = h.get('panel'), t = p && $('panel-' + p);
      if (p === 'dtd' && !dtdDoc) loadDtd(); if (p === 'nodes' && !npDoc) loadNP();
      if (t) setTimeout(function () { t.scrollIntoView({ block: 'start' }); }, 30);
    }
  }
  function download(name, type, text) { var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: type })); a.download = name; document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
  function bind() {
    if (U.nav) U.nav.render($('nav'), 'explorer');
    $('mos').innerHTML = new Array(145).join('<a aria-hidden="true" tabindex="-1" style="background:#111"></a>');   // reserves the mosaic height (CLS)
    $('sform').addEventListener('submit', function (e) { e.preventDefault(); var v = $('q').value.trim(); if (v) location.hash = 'search=' + encodeURIComponent(v); });
    $('vSimple').onclick = function () { setView(false); }; $('vAdv').onclick = function () { setView(true); };
    [].forEach.call(document.querySelectorAll('#wSeg button'), function (b) { b.setAttribute('aria-pressed', +b.dataset.w === win); b.onclick = function () { win = +b.dataset.w; try { localStorage.setItem('sostx_win', win); } catch (e) {} [].forEach.call(document.querySelectorAll('#wSeg button'), function (x) { x.setAttribute('aria-pressed', x === b); }); if (last && last.state) renderCards(last); }; });
    [].forEach.call(document.querySelectorAll('[data-mm]'), function (b) { b.setAttribute('aria-pressed', b.dataset.mm === mosMode); b.onclick = function () { mosMode = b.dataset.mm; try { localStorage.setItem('sostx_mos', mosMode); } catch (e) {} [].forEach.call(document.querySelectorAll('[data-mm]'), function (x) { x.setAttribute('aria-pressed', x === b); }); if (last && last.state) renderMosaic(last); }; });
    $('dtdLoad').onclick = loadDtd; $('bLoad').onclick = loadNP;
    $('ownF').addEventListener('submit', function (e) { e.preventDefault(); var u = $('ownU').value.trim(); if (!/^https?:\/\//.test(u)) { $('ownMsg').textContent = 'Enter an http(s) URL.'; return; } Q.setNode(u, $('ownUs').value, $('ownPw').value); $('ownPw').value = ''; $('ownTag').textContent = 'ON · memory only'; $('ownMsg').textContent = 'Lookups now go to ' + u + '. Reload the page to forget it. (Your node must allow this origin via CORS.)'; });
    $('ownOff').onclick = function () { Q.setNode(''); $('ownU').value = $('ownUs').value = $('ownPw').value = ''; $('ownTag').textContent = 'OFF'; $('ownMsg').textContent = 'Own node off. Lookups use ' + (Q.mode() === 'fixture' ? 'captured fixtures' : 'the public node') + '.'; };
    $('xCsv').onclick = function () { if (!last) return; download('sost_series_' + last.state.meta.height + '.csv', 'text/csv', 'height,time,bits_q,profile,producer\n' + last.rows.map(function (r) { return [r.h, r.t, r.bq, r.prof, r.miner].join(','); }).join('\n')); };
    $('xJson').onclick = function () { if (!last) return; download('sost_state_' + last.state.meta.height + '.json', 'application/json', JSON.stringify({ provenance: last.provenance, status: last.status, collectedAt: last.collectedAt, state: last.state }, null, 1)); };
    addEventListener('hashchange', route);
  }
  function renderAdvanced(s) { renderCR(s); renderEngine(s); renderHistory(s); renderProducers(); renderDTD(s); renderJackpot(s); renderNodes(s); renderEvents(s); renderEmission(s); }
  function onSnap(s) {
    UI.bindStatus(s); last = s.state ? s : last; if (!s.state) return;
    renderCards(s); renderMosaic(s); renderLatest(s);
    if (document.body.classList.contains('advanced')) renderAdvanced(s);
  }
  U.explorer = { lookup: lookup, last: function () { return last; } };
  bind(); D.wantEarnings(); D.subscribe(onSnap); route();
})(window);

/* SOST Universe — Explorer 2.0 model (Phase 5). PURE functions, no DOM, no I/O: runs in the browser and in Node
 * (parity tests: audits/sost-universe/tools/parity_explorer.js).
 *
 * Every formula below is a port of the current production code, cited by file:line, so the parity test can compare
 * the two numerically on the same fixtures:
 *   CR  = website/control-room/ui.js + control-room/state.js   (Control Room V2)
 *   CRJ = website/js/control-room.js                           (Explorer "Convergence Control Room" card)
 *   EX  = website/sost-explorer.html                           (current Explorer)
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.SOSTU = root.SOSTU || {}).xmodel = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  var GENESIS = 1773597600, SPACING = 600, H_MAX = 35, E_MIN = -7, STOCKS = 1e8;   // CRJ:24, params.h
  var EMI = { EPOCH: 131553, R0: 785100863, Q: 0.7788007830714049, SUPPLY_MAX: 466920160910299, EPOCHS: 12 };   // EX:4647
  var JP_FIRST = 25290, JP_CAD = 288, JP_V2 = 30000, JP_V2_FIRST = 30186;                                      // EX:3763, ~10837

  function profName(i) { return i == null ? '—' : i < 0 ? 'E' + (-i) : i === 0 ? 'B0' : 'H' + i; }
  // EX:2193 ceiling by height
  function profileCeiling(h) { return h >= 12000 ? 35 : h >= 7350 ? 20 : h >= 5750 ? 13 : h >= 5635 ? 12 : h >= 5480 ? 11 : h >= 5075 ? 10 : 35; }

  /** CRJ:86-112 derive(), verbatim semantics. arr = contiguous ascending rows {h,t,d,p,m}. */
  function derive(arr, view) {
    view = view || 288;
    var n = arr.length, out = [];
    if (n < 3) return out;
    var pre = [0];
    for (var i = 1; i < n; i++) { var c = Math.min(Math.max(arr[i].t - arr[i - 1].t, 1), 86400); pre.push(pre[i - 1] + c); }
    for (var k = Math.max(1, n - view); k < n; k++) {
      var b = arr[k], pv = arr[k - 1], dt = b.t - pv.t;
      var lag = (b.h - 1) - Math.floor((pv.t - GENESIS) / SPACING);
      var base = lag <= 0 ? 0 : Math.min(lag, H_MAX), drop = 0;
      if (dt >= 540) { var nn = Math.min(1 + Math.floor((dt - 540) / 60), 7); drop = nn * (nn + 1) / 2; }
      var model = drop ? Math.max(E_MIN, base - drop) : base, dev = null;
      if (k >= 288) dev = Math.floor((pre[k - 1] - pre[k - 288]) / 287) - SPACING;
      var burst = null, vol = null;
      if (k >= 72) {
        var bc = 0, s1 = 0, s2 = 0;
        for (var j = k - 71; j <= k; j++) { var x = arr[j].t - arr[j - 1].t; if (x < 300) bc++; s1 += x; s2 += x * x; }
        var mean = s1 / 72; burst = bc / 72 * 100; vol = Math.sqrt(Math.max(0, s2 / 72 - mean * mean)) / SPACING * 100;
      }
      out.push({ h: b.h, t: b.t, d: b.d, p: b.p, m: b.m, dt: dt, lag: lag, base: base, drop: drop, model: model,
        match: b.p != null ? b.p === model : null, dev: dev, burst: burst, vol: vol, dq: pv.d ? (b.d - pv.d) / pv.d * 100 : 0 });
    }
    return out;
  }
  /** CRJ:412-432 chips(). */
  function chips(rows) {
    if (!rows.length) return null;
    var last = rows[rows.length - 1], n = rows.length, matched = 0, known = 0, frozen = 0;
    rows.forEach(function (r) { if (r.match != null) { known++; if (r.match) matched++; } });
    for (var i = rows.length - 1; i >= 0 && rows[i].dq === 0; i--) frozen++;
    var inBand = last.dev != null && Math.abs(last.dev) <= 15;
    var dts = rows.map(function (r) { return r.dt; }).sort(function (a, b) { return a - b; });
    var avg = rows.reduce(function (s, r) { return s + r.dt; }, 0) / n, sh = {};
    rows.forEach(function (r) { sh[r.m] = (sh[r.m] || 0) + 1; });
    return { tip: last.h, lag: last.lag, equalizer: last.p, bitsQ: last.d / 65536, dev: last.dev, inBand: inBand, frozen: frozen, dq: last.dq,
      avg: avg, median: dts[Math.floor(n / 2)], producers: Object.keys(sh).length, matched: matched, known: known,
      burst: last.burst, vol: last.vol };
  }
  /** CRJ:73-85 assemble() equivalent from u-data rows {h,t,bits_q,profile,miner}. */
  function engineRows(rows) { return rows.map(function (r) { return { h: r.h, t: r.t, d: 'bits_q' in r ? r.bits_q : r.bq, p: 'profile' in r ? r.profile : r.prof, m: r.miner || '' }; }); }
  // CRJ CR6 bitsQ step bands for |dev|: dead band ±15 s, then 0.5 / 1 / 2 / 3 %
  function stepBand(dev) { if (dev == null) return null; var a = Math.abs(dev); return a <= 15 ? 0 : a <= 60 ? 0.5 : a <= 120 ? 1 : a <= 240 ? 2 : 3; }

  /** EX:4649 getEpochData(). */
  function epochs(n) {
    var out = [], cum = 0;
    for (var e = 0; e < (n || EMI.EPOCHS + 1); e++) {   // EX:4649 loops e <= TOTAL_EPOCHS (13 rows: 0..12)
      var r = Math.floor(EMI.R0 * Math.pow(EMI.Q, e)), em = r * EMI.EPOCH; cum += em;
      out.push({ epoch: e, from: e * EMI.EPOCH, to: (e + 1) * EMI.EPOCH - 1, reward: r, emission: em, cumulative: cum, pct: cum / EMI.SUPPLY_MAX * 100, miner: r / 2, dtd: r / 2 });
    }
    return out;
  }
  /** DTD eras (EX:§0) and next-block type (EX:~3800 D2). */
  function dtdEra(h) { return h < 7100 ? 'none' : h < 12100 ? '2-of-3' : h < 25000 ? '1-of-3' : 'every block (50/50)'; }
  function isJackpot(h) { return h >= JP_FIRST && (h - JP_FIRST) % JP_CAD === 0; }
  function nextJackpot(tip) { return tip < JP_FIRST ? JP_FIRST : JP_FIRST + Math.ceil((tip + 1 - JP_FIRST) / JP_CAD) * JP_CAD; }
  function jpV2Next(tip) { return tip < JP_V2_FIRST ? JP_V2_FIRST : JP_V2_FIRST + Math.ceil((tip + 1 - JP_V2_FIRST) / JP_CAD) * JP_CAD; }   // EX:~10837

  /** EX:10161-10312 producer distribution; periods kept as in production (L1). rows = [{h,m}] ascending. */
  var PD_PERIODS = [['48h', 288], ['3D', 404], ['1W', 943], ['1M', 4039], ['3M', 12117], ['All', Infinity]];
  function producers(rows, n) {
    var w = n === Infinity ? rows : rows.slice(Math.max(0, rows.length - n)), c = {}, last = {};
    w.forEach(function (r) { c[r.m] = (c[r.m] || 0) + 1; last[r.m] = r.h; });
    var list = Object.keys(c).map(function (a) { return { addr: a, blocks: c[a], share: c[a] / w.length * 100, last: last[a] }; }).sort(function (a, b) { return b.blocks - a.blocks || b.last - a.last; });
    return { n: w.length, from: w.length ? w[0].h : null, to: w.length ? w[w.length - 1].h : null, unique: list.length,
      top1: list[0] ? list[0].share : null, top3: list.slice(0, 3).reduce(function (s, x) { return s + x.share; }, 0), list: list, enough: n === Infinity || rows.length >= n };
  }
  /** EX:1228-1314 DTD winners (dwz agg); periods kept as in production (M1, they differ from L1: parity note 7). */
  var DW_PERIODS = [['48h', 288], ['3D', 432], ['1W', 1008], ['1M', 4320], ['3M', 12960], ['All', Infinity]];
  function dtdWinners(payouts, tip, n) {
    var w = payouts.filter(function (p) { return n === Infinity || p.h > tip - n; }), c = {}, amt = {}, last = {}, total = 0;
    w.forEach(function (p) { c[p.addr] = (c[p.addr] || 0) + 1; amt[p.addr] = (amt[p.addr] || 0) + p.amt; last[p.addr] = Math.max(last[p.addr] || 0, p.h); total += p.amt; });
    var list = Object.keys(c).map(function (a) { return { addr: a, wins: c[a], sost: amt[a] / STOCKS, share: total ? amt[a] / total * 100 : 0, last: last[a] }; })
      .sort(function (a, b) { return b.wins - a.wins || b.sost - a.sost; });
    return { payouts: w.length, unique: list.length, top1: list[0] ? list[0].share : null, paid: total / STOCKS, list: list };
  }
  /** Confirmed jackpots (address_earnings.jackpots) + every scheduled draw height up to the tip: paid or no payout. */
  function jackpots(confirmed, tip, audits) {
    var byH = {}; (confirmed || []).forEach(function (j) { byH[j.h] = j; });
    var au = {}; if (audits && audits.rows) audits.rows.forEach(function (r) { var o = {}; audits.fields.forEach(function (f, i) { o[f] = r[i]; }); au[o.height] = o; });
    var out = [];
    for (var h = JP_FIRST; h <= tip; h += JP_CAD) {
      var j = byH[h];
      out.push({ h: h, v2: h >= JP_V2, paid: !!j, addr: j ? j.addr : null, sost: j ? j.sat / STOCKS : 0, txid: j ? j.txid : null, audit: au[h] || null });
    }
    var paid = out.filter(function (x) { return x.paid; });
    return { draws: out.length, paid: paid.length, noPayout: out.length - paid.length, total: paid.reduce(function (s, x) { return s + x.sost; }, 0), list: out.reverse() };
  }
  /** EX:11376-11425 bound nodes summary from api/node_participation.json. */
  function boundNodes(np) {
    if (!np) return null;
    var nr = (np.nodes || []).filter(function (x) { return x.next_jackpot && x.next_jackpot.node_condition_met; }).length;
    return { totals: np.totals, epoch: np.current_epoch, into: np.tip - np.current_epoch_start + 1, epochLen: np.epoch_length, tip: np.tip,
      next: np.next_jackpot, nodeReady: nr, nodes: np.nodes || [], note: np.note };
  }
  /** EX:11290-11310 Address Inspector reconciliation. info = getaddressinfo, tip = height. */
  function reconcile(info, tip) {
    var u = (info && info.utxos) || [], sumU = 0, imm = 0, locked = 0;
    u.forEach(function (x) {
      var a = Number(x.amount) || 0; sumU += a;
      if (x.coinbase && tip - x.height + 1 < 1000) imm += a;
      if (x.type === 16 || x.type === 17 || x.type === 18) locked += a;
    });
    var n8 = function (v) { return Math.round(v * 1e8) / 1e8; }, bal = Number(info && info.balance);
    // balance from the node may be in SOST (float) or stocks (int); getaddressinfo returns stocks: normalise to SOST
    var b = bal > 1e6 && Number.isInteger(bal) && sumU < bal / 1e4 ? bal / STOCKS : bal;
    return { balance: b, sumUtxo: sumU, match: Math.abs(n8(sumU) - n8(b)) < 1e-6, utxos: u.length, immature: imm, locked: locked, spendable: b - imm - locked };
  }
  var UTXO_TYPE = { 0: 'transfer', 1: 'coinbase · miner', 2: 'coinbase · gold', 3: 'coinbase · popc', 4: 'coinbase · lottery', 16: 'bond-lock', 17: 'escrow-lock',
    18: 'htlc-lock (retired, H-01)', 19: 'htlc-claim (retired, H-01)', 32: 'burn', 48: 'node-protocol' };

  /** Every Control Room row (CR ui.js renderActive / renderEvents / renderHistorical) as {id, label, value} from CRState. */
  function crRows(st) {
    var a = st.active, ch = a.chain, tm = a.timing, c = a.consensus, mi = a.miners, d = a.dtd, j = a.jackpot, nb = a.nodeBind, n = a.network, s = a.supply;
    var e = st.events, sb = e.submitblock.value || {}, h = st.historical, peak = h.peakActive288InSeries.value;
    var bq = h.bitsQSeries.map(function (x) { return x[1]; });
    var R = [
      ['chain.height', 'Height', ch.height.value], ['chain.tipAge', 'Tip age (s)', ch.tipAge.value], ['chain.latestInterval', 'Latest interval (s)', ch.latestInterval.value],
      ['chain.latestProducer', 'Latest producer', ch.latestProducer.value], ['chain.mempool', 'Mempool (tx)', ch.mempool.value],
      ['timing.target', 'Target (s)', 600], ['timing.avg24', 'Avg 24 (s)', tm.avg24.value], ['timing.avg72', 'Avg 72 (s)', tm.avg72.value], ['timing.avg288', 'Avg 288 (s)', tm.avg288.value],
      ['consensus.bitsQ', 'bitsQ', c.bitsQ.value], ['consensus.bitsQq16', 'bitsQ Q16.16', c.bitsQ.q16], ['consensus.bitsQnext', 'Next block bitsQ', c.bitsQ.next],
      ['eq.next', 'Equalizer (next block)', c.equalizerNext.value], ['eq.lag', 'Schedule lag (node, blocks)', c.equalizerNext.lag], ['eq.ceiling', 'Latest block ceiling', c.equalizerTip.base],
      ['eq.floor', 'Latest block floor', c.equalizerTip.floor], ['eq.declared', 'Latest block declared', c.equalizerTip.value],
      ['miners.active288', 'Active miners (288)', mi.active288.value], ['miners.active288Series', 'Active miners cross-check (series)', mi.active288Series.value],
      ['miners.top1share', 'Top producer share 288 (%)', mi.shares[0] ? mi.shares[0].share * 100 : null],
      ['dtd.eligible', 'DTD eligible next', d.eligibleNext.value], ['dtd.next', 'DTD next height', d.nextHeight.value], ['dtd.cooldownWindow', 'Cooldown window', d.cooldownWindow.value],
      ['dtd.cooldown', 'In cooldown', (d.cooldownMiners.value || []).join(',')], ['dtd.payout', 'DTD payout (SOST)', d.payout.value], ['dtd.projected', 'Projected next DTD winner', d.projectedWinner.value],
      ['net.peers', 'Connected peers', n.connectedPeers.value], ['net.synced', 'Synced peers (≥ tip−1)', n.syncedPeers.value], ['net.unique', 'Unique active nodes seen', n.uniqueActiveNodes.value],
      ['net.local', 'Public node', n.localStatus.value],
      ['jp.next', 'Jackpot next draw', j.nextHeight.value], ['jp.left', 'Jackpot blocks left', j.blocksRemaining.value], ['jp.eta', 'Jackpot ETA (s)', j.etaSeconds.value],
      ['jp.eligible', 'Jackpot eligible', j.eligible.value], ['jp.candidates', 'Jackpot candidates', j.candidates.value], ['jp.bound', 'NODE_BIND bound', nb.bound.value],
      ['jp.pot', 'Jackpot pot (SOST)', j.pot.value], ['jp.reserve', 'Jackpot reserve (SOST)', j.reserve.value], ['jp.minPow', 'Min PoW blocks', j.minPowBlocks.value],
      ['jp.powWindow', 'PoW window', j.powWindow.value], ['jp.hb', 'Heartbeats required', j.heartbeatRequired.value], ['jp.rollover', 'Rollover if 0 eligible', j.rolloverIfNoneEligible.value],
      ['supply.total', 'Supply total', s.total.value], ['supply.circ', 'Circulating', s.circulating.value], ['supply.circMining', 'Circulating (mining)', s.circulatingMining.value],
      ['supply.legacyReserve', 'Legacy reserve address (gold_vault_balance)', s.goldVault.value], ['supply.popc', 'PoPC pool', s.popcPool.value], ['supply.jpReserve', 'Jackpot reserve', s.jackpotReserve.value],
      ['ev.accepted', 'submitblock accepted', sb.accepted], ['ev.received', 'submitblock received', sb.received], ['ev.rejected', 'submitblock rejected', sb.rejected],
      ['ev.misbehavior', 'Misbehavior events', e.misbehavior.value], ['ev.uptime', 'Public node uptime (s)', e.nodeUptime.value], ['ev.boot', 'Public node boot', e.nodeBoot.value],
      ['ev.reorgs', 'Reorgs', 'n/a'], ['ev.observed', 'Observed by the collector', e.observed.length],
      ['hist.producersAll', 'Distinct producers (all time)', h.uniqueProducersSinceGenesis.value], ['hist.producersSince', 'Producers since window start', h.producersSinceWindowStart.value],
      ['hist.peak288', 'Peak distinct producers in a 288 window', peak ? peak.n : null], ['hist.peakAt', 'Peak reached at', peak ? peak.at : null],
      ['hist.schedule', 'Schedule since genesis (blocks)', h.scheduleSinceGenesis.value], ['hist.range', 'Series range', h.seriesRange ? h.seriesRange.join('-') : null],
      ['hist.bitsQmin', 'bitsQ min (series)', bq.length ? Math.min.apply(null, bq) : null], ['hist.bitsQmax', 'bitsQ max (series)', bq.length ? Math.max.apply(null, bq) : null],
      ['hist.profiles', 'Profile histogram', JSON.stringify(h.profileHistogram)], ['hist.milestones', 'Milestones', h.milestones.length]
    ];
    return R.map(function (r) { return { id: r[0], label: r[1], value: r[2] }; });
  }

  return { GENESIS: GENESIS, SPACING: SPACING, EMI: EMI, profName: profName, profileCeiling: profileCeiling, derive: derive, chips: chips, engineRows: engineRows, stepBand: stepBand,
    epochs: epochs, dtdEra: dtdEra, isJackpot: isJackpot, nextJackpot: nextJackpot, jpV2Next: jpV2Next, PD_PERIODS: PD_PERIODS, producers: producers,
    DW_PERIODS: DW_PERIODS, dtdWinners: dtdWinners, jackpots: jackpots, boundNodes: boundNodes, reconcile: reconcile, UTXO_TYPE: UTXO_TYPE, crRows: crRows };
});

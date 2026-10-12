/* SOST Control Room V2 — normalized state (pure functions, no I/O).
 *
 * normalize(bundle) turns the raw read-only RPC responses into ONE internal model, so the UI
 * never depends on RPC formats. Every metric carries:
 *   scope  : "live"       — value at the current tip / right now
 *            "window"     — computed over an explicit recent window (e.g. last 288 blocks)
 *            "historical" — cumulative / since genesis / archive
 *   source : the exact RPC field (or derivation) it came from
 * ACTIVE NOW = scope live|window. HISTORICAL = scope historical. They are never mixed.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.CRState = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const TARGET_SPACING = 600;           // params.h TARGET_SPACING
  const STOCKS = 1e8;
  const PROFILE_MIN = -7, PROFILE_MAX = 35; // params.h CASERT_H_MIN / CASERT_H_MAX (43 profiles, V8 #5,750+)

  // Protocol milestones — every height verified against sost-core include/sost/params.h / casert.cpp.
  const MILESTONES = [
    { h: 5270,  label: 'bitsQ avg288 dead band ±15 s, steps 0.5/1/2/3 %', src: 'casert.cpp:102-116' },
    { h: 5323,  label: 'Equalizer direct lag map', src: 'params.h CASERT_DIRECT_LAG_HEIGHT' },
    { h: 5750,  label: 'Equalizer V8: 43 profiles E7–H35', src: 'params.h CASERT_PROFILES' },
    { h: 7000,  label: 'V11: state-indexed dataset reads', src: 'params.h CASERT_V11_HEIGHT' },
    { h: 7100,  label: 'Phase 2 (SbPoW, DTD reward)', src: 'getlotterystate.phase2_height' },
    { h: 7350,  label: 'V12 (slingshot / cascade)', src: 'params.h V12_HEIGHT' },
    { h: 12000, label: 'V13', src: 'params.h V13_HEIGHT' },
    { h: 15000, label: 'V14 hardening', src: 'params.h V14_HEIGHT' },
    { h: 25000, label: 'V15: 50 % miner / 50 % DTD', src: 'params.h V15_HEIGHT' },
    { h: 25290, label: 'First DTD Jackpot', src: 'params.h jackpot first = V15 + 290' },
    { h: 30000, label: 'V30000: Jackpot V2 + NODE_BIND v2', src: 'params.h HIST_JACKPOT_V2_HEIGHT' },
  ];

  /** V12+ triangular cascade relief (casert.cpp:1010 compute_v11_cascade_drop_triangular_h, max 7 steps). */
  function cascadeDrop(elapsed) {
    if (elapsed == null || elapsed < 540) return 0;
    const n = Math.min(1 + Math.floor((elapsed - 540) / 60), 7);
    return (n * (n + 1)) / 2;
  }
  /** Floor = ceiling − cascade at the block's own elapsed time. Only below 3,600 s, where no other
   *  relief rule (anti-stall) applies; above that we do not reproduce consensus and return null. */
  function profileFloor(ceilingName, elapsed) {
    const c = profileIndex(ceilingName);
    if (c == null || elapsed == null || elapsed >= 3600) return null;
    return Math.max(PROFILE_MIN, c - cascadeDrop(elapsed));
  }

  function profileName(i) {
    if (i == null || isNaN(i)) return null;
    if (i < 0) return 'E' + (-i);
    if (i === 0) return 'B0';
    return 'H' + i;
  }
  function profileIndex(name) {
    if (typeof name !== 'string') return null;
    const m = /^([EHB])(\d+)$/.exec(name);
    if (!m) return null;
    return m[1] === 'E' ? -Number(m[2]) : Number(m[2]);
  }
  const shortAddr = (a) => (a && a.length > 18 ? a.slice(0, 10) + '…' + a.slice(-4) : a || '');
  const pkhToAddr = (pkh) => (pkh ? 'sost1' + pkh : null);
  const mean = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);
  const median = (xs) => {
    if (!xs.length) return null;
    const s = xs.slice().sort((a, b) => a - b), k = s.length >> 1;
    return s.length % 2 ? s[k] : (s[k - 1] + s[k]) / 2;
  };
  const m = (value, scope, source, extra) => Object.assign({ value, scope, source }, extra || {});

  /** Merge the static series (/api/block_series.json rows: [h, t, bits_q, profile, miner]) with
   *  delta blocks fetched by getblock, de-duplicated by height (delta wins). */
  function mergeSeries(series, deltaBlocks) {
    const byH = new Map();
    const f = (series && series.fields) || ['h', 't', 'bits_q', 'profile', 'miner'];
    const ix = (n) => f.indexOf(n);
    for (const r of (series && series.rows) || []) {
      byH.set(r[ix('h')], { h: r[ix('h')], t: r[ix('t')], bits_q: r[ix('bits_q')], profile: r[ix('profile')], miner: r[ix('miner')] });
    }
    for (const b of deltaBlocks || []) {
      if (!b || b.height == null) continue;
      byH.set(b.height, { h: b.height, t: b.time, bits_q: b.bits_q, profile: b.casert_profile_index, miner: b.miner_address,
        base: b.casert_base, mode: b.casert_mode, hash: b.hash });
    }
    return Array.from(byH.values()).sort((a, b) => a.h - b.h);
  }

  /** Contiguous tail ending at `tip` (no gaps), so window stats never silently skip blocks. */
  function contiguousTail(rows, tip) {
    const out = [];
    for (let i = rows.length - 1, want = tip; i >= 0; i--, want--) {
      if (rows[i].h !== want) break;
      out.push(rows[i]);
    }
    return out.reverse();
  }

  function windowStats(rows, n) {
    if (rows.length < n + 1) return { n, available: Math.max(0, rows.length - 1), avg: null, median: null };
    const w = rows.slice(rows.length - (n + 1));
    const iv = [];
    for (let i = 1; i < w.length; i++) iv.push(w[i].t - w[i - 1].t);
    return { n, available: n, avg: mean(iv), median: median(iv) };
  }

  function producersInWindow(rows, n) {
    const w = rows.slice(Math.max(0, rows.length - n));
    const c = new Map();
    for (const r of w) c.set(r.miner, (c.get(r.miner) || 0) + 1);
    return Array.from(c.entries()).map(([addr, blocks]) => ({ addr, blocks, share: blocks / w.length }))
      .sort((a, b) => b.blocks - a.blocks);
  }

  /** Max distinct producers in any 288-block window inside the available series (archive stat). */
  function peakActive288(rows) {
    if (rows.length < 288) return null;
    const c = new Map();
    let best = { n: 0, at: null };
    for (let i = 0; i < rows.length; i++) {
      c.set(rows[i].miner, (c.get(rows[i].miner) || 0) + 1);
      if (i >= 288) {
        const old = rows[i - 288].miner, v = c.get(old) - 1;
        if (v === 0) c.delete(old); else c.set(old, v);
      }
      if (i >= 287 && c.size > best.n) best = { n: c.size, at: rows[i].h };
    }
    return best;
  }

  function normalize(b) {
    const info = b.info || {}, sup = b.supply || {}, lot = b.lottery || {}, elig = b.eligible || {};
    const hj = b.hjack || {}, jv2 = b.jv2 || {}, mp = b.mempool || {}, ns = b.netsum || {}, ms = b.minerstats || {};
    const now = b.now || Math.floor(Date.now() / 1000);
    const height = info.blocks != null ? info.blocks : (sup.block_height != null ? sup.block_height : null);
    const rows = contiguousTail(mergeSeries(b.series, b.deltaBlocks), height);
    const tip = rows.length ? rows[rows.length - 1] : null;
    const prev = rows.length > 1 ? rows[rows.length - 2] : null;
    const tipBlock = (b.deltaBlocks || []).find((x) => x && x.height === height) || null;
    const genesisTime = b.series && b.series.genesis_time;

    const w288 = producersInWindow(rows, 288);
    const cooldown = Array.isArray(lot.previous_cooldown_block_winners) ? lot.previous_cooldown_block_winners : [];
    const v2c = Array.isArray(jv2.candidates) ? jv2.candidates : [];
    const peers = Array.isArray(b.peers) ? b.peers : [];

    const active = {
      chain: {
        height: m(height, 'live', 'getinfo.blocks'),
        tipHash: m(b.bestblockhash || (tipBlock && tipBlock.hash) || null, 'live', 'getbestblockhash'),
        tipAge: m(tip ? Math.max(0, now - tip.t) : null, 'live', 'now − tip block time'),
        latestInterval: m(tip && prev ? tip.t - prev.t : null, 'live', 'tip.time − (tip−1).time'),
        latestProducer: m(tip ? tip.miner : null, 'live', 'getblock(tip).miner_address'),
        mempool: m(mp.size != null ? mp.size : info.mempool_size, 'live', 'getmempoolinfo.size'),
      },
      timing: {
        target: m(TARGET_SPACING, 'live', 'params.h TARGET_SPACING'),
        avg24: m(windowStats(rows, 24).avg, 'window', 'mean interval, last 24 blocks', { stats: windowStats(rows, 24) }),
        avg72: m(windowStats(rows, 72).avg, 'window', 'mean interval, last 72 blocks', { stats: windowStats(rows, 72) }),
        avg288: m(windowStats(rows, 288).avg, 'window', 'mean interval, last 288 blocks', { stats: windowStats(rows, 288) }),
        nodeAvg: m(info.avg_block_time_s != null ? info.avg_block_time_s : null, 'window', 'getinfo.avg_block_time_s (node window)'),
        intervals: rows.slice(-289).map((r, i, a) => (i ? r.t - a[i - 1].t : null)).slice(1),  // last 288 intervals
      },
      consensus: {
        bitsQ: m(info.difficulty != null ? info.difficulty : (tip && tip.bits_q), 'live', 'getinfo.difficulty (bitsQ, Q16.16)',
          { q16: info.difficulty != null ? info.difficulty / 65536 : null, next: info.next_difficulty }),
        equalizerNext: m(info.casert_profile || profileName(info.casert_profile_index), 'live', 'getinfo.casert_profile (next block)',
          { index: info.casert_profile_index, lag: info.casert_lag }),
        equalizerTip: m(tipBlock ? (tipBlock.casert_mode || null) : profileName(tip && tip.profile), 'live',
          'getblock(tip).casert_mode (declared profile, verified by every node)', { base: tipBlock ? tipBlock.casert_base : null, signal: tipBlock ? tipBlock.casert_signal : null,
            floor: tipBlock && tip && prev ? profileName(profileFloor(tipBlock.casert_base, tip.t - prev.t)) : null,
            elapsed: tip && prev ? tip.t - prev.t : null }),
      },
      miners: {
        active288: m(elig.active_288 != null ? elig.active_288 : null, 'window', 'geteligibleminers.active_288 (288-block window)'),
        active288Series: m(w288.length || null, 'window', 'distinct producers in the last 288 blocks of the series (cross-check)'),
        shares: w288,
      },
      recent: m(rows.slice(-144).map((r, i, a) => ({ h: r.h, t: r.t, miner: r.miner, profile: r.profile,
        interval: i ? r.t - a[i - 1].t : (rows.length > 144 ? r.t - rows[rows.length - 145].t : null) })),
        'window', 'last 144 blocks (block series + getblock)'),
      dtd: {
        nextHeight: m(lot.height_next != null ? lot.height_next : null, 'live', 'getlotterystate.height_next'),
        eligibleNext: m(lot.eligible_count != null ? lot.eligible_count : null, 'live', 'getlotterystate.eligible_count (next block, V30000 rules)'),
        cooldownWindow: m(lot.cooldown_window != null ? lot.cooldown_window : null, 'live', 'getlotterystate.cooldown_window'),
        cooldownMiners: m(Array.from(new Set(cooldown)).map(pkhToAddr), 'live', 'getlotterystate.previous_cooldown_block_winners'),
        projectedWinner: m(pkhToAddr(lot.lottery_winner_pkh), 'live', 'getlotterystate.lottery_winner_pkh — PROJECTED for the next block at the current tip'),
        payout: m(lot.lottery_payout != null ? lot.lottery_payout / STOCKS : null, 'live', 'getlotterystate.lottery_payout'),
        triggered: m(!!lot.lottery_triggered, 'live', 'getlotterystate.lottery_triggered'),
      },
      jackpot: {
        nextHeight: m(hj.next_jackpot_height != null ? hj.next_jackpot_height : jv2.height, 'live', 'gethistoricaljackpotstatus.next_jackpot_height'),
        blocksRemaining: m(hj.blocks_remaining != null ? hj.blocks_remaining : null, 'live', 'gethistoricaljackpotstatus.blocks_remaining'),
        etaSeconds: m(hj.blocks_remaining != null ? hj.blocks_remaining * TARGET_SPACING : null, 'live', 'blocks_remaining × 600 s (estimate)'),
        isV2: m(!!jv2.is_v2_jackpot, 'live', 'getjackpotv2audit.is_v2_jackpot'),
        eligible: m(jv2.eligible_count != null ? jv2.eligible_count : null, 'live', 'getjackpotv2audit.eligible_count'),
        candidates: m(v2c.length, 'live', 'getjackpotv2audit.candidates'),
        candidateList: v2c.map((c) => ({ addr: c.address, powBlocks: c.pow_blocks, bound: !!c.node_bound,
          heartbeats: c.heartbeats, heartbeatsRequired: c.heartbeats_required, eligible: !!c.eligible, weight: c.weight })),
        heartbeatRequired: m(jv2.heartbeat_required != null ? jv2.heartbeat_required : null, 'live', 'getjackpotv2audit.heartbeat_required'),
        minPowBlocks: m(jv2.min_pow_blocks != null ? jv2.min_pow_blocks : null, 'live', 'getjackpotv2audit.min_pow_blocks'),
        powWindow: m(jv2.pow_window != null ? jv2.pow_window : null, 'live', 'getjackpotv2audit.pow_window'),
        reserve: m(jv2.reserve_stocks != null ? jv2.reserve_stocks / STOCKS : (hj.reserve != null ? hj.reserve : null), 'live', 'getjackpotv2audit.reserve_stocks'),
        pot: m(jv2.current_pot_stocks != null ? jv2.current_pot_stocks / STOCKS : null, 'live', 'getjackpotv2audit.current_pot_stocks'),
        rolloverIfNoneEligible: m(jv2.eligible_count === 0, 'live', 'eligible_count = 0 → rollover at the draw'),
      },
      nodeBind: {
        bound: m(v2c.filter((c) => c.node_bound).length, 'live', 'getjackpotv2audit.candidates[].node_bound'),
        of: m(v2c.length, 'live', 'getjackpotv2audit.candidates'),
      },
      network: {
        connectedPeers: m(peers.length || (ns.connections != null ? ns.connections : null), 'live', 'getpeerinfo (connected peers of the public node)'),
        peers: peers.map((p) => ({ addr: p.addr, direction: p.direction, height: p.height, acked: !!p.version_acked })),
        syncedPeers: m(peers.filter((p) => height != null && p.height >= height - 1).length, 'live', 'getpeerinfo[].height ≥ tip − 1'),
        uniqueActiveNodes: m(ns.unique_active_nodes != null ? ns.unique_active_nodes : null, 'live',
          'getnetworksummary.unique_active_nodes — observed by the public node, NOT a census of the network'),
        localStatus: m(ns.local_node ? ns.local_node.status : null, 'live', 'getnetworksummary.local_node.status'),
        localReasons: (ns.local_node && ns.local_node.reasons) || [],
        tipStaleAfter: m(ns.tip_stale_after_s != null ? ns.tip_stale_after_s : null, 'live', 'getnetworksummary.tip_stale_after_s'),
      },
      supply: {
        total: m(sup.total_supply, 'live', 'getsupplyinfo.total_supply'),
        circulating: m(sup.circulating_supply, 'live', 'getsupplyinfo.circulating_supply'),
        circulatingMining: m(sup.circulating_mining, 'live', 'getsupplyinfo.circulating_mining'),
        goldVault: m(sup.gold_vault_balance, 'live', 'getsupplyinfo.gold_vault_balance'),
        popcPool: m(sup.popc_pool_balance, 'live', 'getsupplyinfo.popc_pool_balance'),
        dtdDistributed: m(sup.dtd_lottery_distributed, 'historical', 'getsupplyinfo.dtd_lottery_distributed (cumulative since #7,100)'),
        jackpotReserve: m(jv2.reserve_stocks != null ? jv2.reserve_stocks / STOCKS : (hj.reserve != null ? hj.reserve : null), 'live', 'getjackpotv2audit.reserve_stocks'),
      },
    };

    const lt = ms.lifetime || {};
    const events = {
      submitblock: m({ received: lt.submitblock_received, accepted: lt.submitblock_accepted, rejected: lt.submitblock_rejected,
        reasons: ms.rejected_reasons || {} }, 'live', 'getminerstats.lifetime (since node boot; blocks submitted to THIS node only)'),
      misbehavior: m(lt.misbehavior_events != null ? lt.misbehavior_events : null, 'live', 'getminerstats.lifetime.misbehavior_events'),
      nodeBoot: m(ms.boot_time_unix || null, 'live', 'getminerstats.boot_time_unix'),
      nodeUptime: m(ms.uptime_seconds != null ? ms.uptime_seconds : (ns.local_node ? ns.local_node.uptime_s : null), 'live', 'getminerstats.uptime_seconds'),
      reorgs: m(null, 'live', 'not exposed by the public RPC', { available: false }),
      observed: (b.session && b.session.observed) || [],
    };

    const historical = {
      uniqueProducersSinceGenesis: m(elig.producers_since_genesis != null ? elig.producers_since_genesis : null, 'historical',
        'geteligibleminers.producers_since_genesis — distinct addresses that ever produced a block'),
      producersSinceWindowStart: m(elig.producers_total != null ? elig.producers_total : null, 'historical',
        'geteligibleminers.producers_total', { from: elig.window_start }),
      peakActive288InSeries: m(peakActive288(rows), 'historical', 'max distinct producers in any 288-block window of the loaded series',
        { range: rows.length ? [rows[0].h, rows[rows.length - 1].h] : null }),
      seriesRange: rows.length ? [rows[0].h, rows[rows.length - 1].h] : null,
      profileHistogram: (() => {
        const hst = {};
        for (const r of rows) if (r.profile != null) hst[r.profile] = (hst[r.profile] || 0) + 1;
        return hst;
      })(),
      bitsQSeries: rows.map((r) => [r.h, r.bits_q]),
      profileSeries: rows.map((r) => [r.h, r.profile]),
      scheduleSinceGenesis: m(genesisTime && height != null ? height - Math.floor((now - genesisTime) / TARGET_SPACING) : null,
        'historical', 'height − (now − genesis_time)/600 (blocks ahead of schedule since genesis)'),
      milestones: MILESTONES.filter((x) => height == null || x.h <= height),
    };

    // HEALTH — facts with the rule that classifies them; no aggregate score.
    const facts = [];
    const tipAge = active.chain.tipAge.value, stale = active.network.tipStaleAfter.value;
    if (tipAge != null) facts.push({ name: 'Tip age', value: tipAge + ' s', state: stale && tipAge > stale ? 'attention' : 'normal',
      rule: stale ? 'attention above ' + stale + ' s (node tip_stale_after_s)' : 'no threshold from node' });
    if (active.timing.avg288.value != null) facts.push({ name: 'Avg interval (288)', value: Math.round(active.timing.avg288.value) + ' s',
      state: Math.abs(active.timing.avg288.value - TARGET_SPACING) <= 15 ? 'normal' : 'info', rule: 'inside the ±15 s bitsQ dead band = no bitsQ change' });
    facts.push({ name: 'Synced peers', value: String(active.network.syncedPeers.value), state: active.network.syncedPeers.value > 0 ? 'normal' : 'attention',
      rule: 'attention when no connected peer is within 1 block of the tip' });
    const rej = (events.submitblock.value || {}).rejected;
    if (rej != null) facts.push({ name: 'submitblock rejected (since boot)', value: String(rej), state: rej > 0 ? 'info' : 'normal',
      rule: 'blocks rejected by this node since boot; see reasons' });
    facts.push({ name: 'Reorgs', value: 'not exposed', state: 'unknown', rule: 'the public RPC has no reorg counter' });
    if (active.network.localStatus.value) facts.push({ name: 'Public node', value: active.network.localStatus.value,
      state: active.network.localStatus.value === 'ONLINE' ? 'normal' : 'attention', rule: 'getnetworksummary.local_node.status' });

    return { version: 2, meta: { height, fetchedAt: now, source: b.source || 'live', recordedAt: b.recordedAt || null },
      active, events, historical, health: facts, constants: { TARGET_SPACING, PROFILE_MIN, PROFILE_MAX } };
  }

  return { normalize, cascadeDrop, profileFloor, mergeSeries, contiguousTail, windowStats, producersInWindow, peakActive288, profileName, profileIndex,
    shortAddr, pkhToAddr, MILESTONES, TARGET_SPACING };
});

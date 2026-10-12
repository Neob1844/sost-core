/* SOST Control Room V2 — renderer. Reads only the normalized state from CRState.normalize(). */
(function () {
  'use strict';
  const S = window.CRState;
  const $ = (id) => document.getElementById(id);
  const esc = (x) => String(x == null ? '' : x).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (v, d = 0) => (v == null || isNaN(v) ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const dur = (s) => {
    if (s == null || isNaN(s)) return '—';
    s = Math.round(s);
    const sign = s < 0 ? '−' : '';
    s = Math.abs(s);
    if (s < 60) return sign + s + 's';
    if (s < 3600) return sign + Math.floor(s / 60) + 'm ' + (s % 60) + 's';
    return sign + Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm';
  };
  const hms = (s) => { s = Math.floor(s); return s < 3600 ? dur(s) : Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm ' + (s % 60) + 's'; };
  // Values that depend only on the clock carry their reference time and are advanced locally every
  // second by tick(), without any request: tip age, countdowns, uptime.
  const tk = (t, kind, text) => t == null ? text : `<span class="tk" data-t="${t}" data-k="${kind}">${text}</span>`;
  const src = (metric) => metric && metric.source ? `<span class="src" title="${esc('Source: ' + metric.source)}" aria-label="${esc('Source: ' + metric.source)}">i</span>` : '';
  const addr = (a) => a ? `<span class="addr" title="${esc(a)}">${esc(S.shortAddr(a))}</span>` : '—';
  const tag = (scope) => scope === 'window' ? '<span class="tag win">WINDOW</span>' : '<span class="tag live">LIVE</span>';
  const profColor = (i) => i == null ? '#333' : i < 0 ? '#22d3ee' : i === 0 ? '#39ff14' : i <= 10 ? '#a3e635' : i <= 20 ? '#fbbf24' : i <= 28 ? '#f97316' : '#fb010d';
  const ivColor = (s) => s == null ? '#333' : s < 300 ? '#22d3ee' : s <= 900 ? '#39ff14' : s <= 1800 ? '#fbbf24' : '#fb010d';

  function intervalsChart(st) {
    const iv = st.active.timing.intervals.filter((x) => x != null);
    const prof = st.historical.profileSeries.slice(-iv.length).map((p) => p[1]);
    if (!iv.length) return '<div class="sub">No interval data.</div>';
    const W = 860, H = 150, PH = 14, cap = 1800, bw = W / iv.length;
    const y = (s) => H - Math.min(s, cap) / cap * (H - 8);
    let bars = '';
    iv.forEach((s, i) => { bars += `<rect x="${(i * bw).toFixed(2)}" y="${y(s).toFixed(1)}" width="${Math.max(bw - .6, .6).toFixed(2)}" height="${(H - y(s)).toFixed(1)}" fill="${ivColor(s)}" opacity=".85"><title>${esc(dur(s))}</title></rect>`; });
    let strip = '';
    prof.forEach((p, i) => { strip += `<rect x="${(i * bw).toFixed(2)}" y="${H + 6}" width="${Math.max(bw - .6, .6).toFixed(2)}" height="${PH}" fill="${profColor(p)}"><title>${esc(S.profileName(p))}</title></rect>`; });
    const t = y(600);
    return `<svg class="chart" viewBox="0 0 ${W} ${H + PH + 22}" role="img" aria-label="Last ${iv.length} block intervals with the Equalizer profile of each block">
      ${bars}<line x1="0" x2="${W}" y1="${t}" y2="${t}" stroke="#e6edf3" stroke-dasharray="4 4" stroke-width="1"/>
      <text x="4" y="${t - 4}">target 600 s</text><text x="${W - 4}" y="12" text-anchor="end">cap 30 m</text>
      ${strip}<text x="4" y="${H + PH + 18}">Equalizer profile of each block (same x axis)</text></svg>
      <div class="legend"><span><i style="background:#22d3ee"></i>&lt; 5 m</span><span><i style="background:#39ff14"></i>5–15 m</span><span><i style="background:#fbbf24"></i>15–30 m</span><span><i style="background:#fb010d"></i>&gt; 30 m</span></div>`;
  }

  function eqScale(st) {
    const c = st.active.consensus;
    const pos = (i) => ((i + 7) / 42 * 100).toFixed(2);  // E7 (-7) .. H35 (+35)
    const nIdx = c.equalizerNext.index != null ? c.equalizerNext.index : S.profileIndex(c.equalizerNext.value);
    const tIdx = S.profileIndex(c.equalizerTip.value), bIdx = S.profileIndex(c.equalizerTip.base);
    const mk = (i, cls, label) => i == null ? '' : `<span class="mk ${cls}" style="left:${pos(i)}%" title="${esc(label + ': ' + S.profileName(i))}"></span>`;
    return `<div class="eqscale" role="img" aria-label="Equalizer scale E7 to H35">${mk(bIdx, 'base', 'Latest block ceiling (schedule lag, no time relief)')}${mk(tIdx, 'tip', 'Latest block declared and verified')}${mk(nIdx, 'next', 'Next block: lowest valid profile if stamped now')}</div>
      <div class="eqticks"><span>E7</span><span>B0</span><span>H10</span><span>H20</span><span>H35</span></div>
      <div class="legend"><span><i style="background:#39ff14"></i>next block, lowest valid if stamped now: ${esc(S.profileName(nIdx) || '—')}</span><span><i style="background:#a78bfa"></i>latest block ceiling: ${esc(c.equalizerTip.base || '—')}</span><span><i style="background:#fbbf24"></i>latest block declared &amp; verified: ${esc(c.equalizerTip.value || '—')}</span></div>`;
  }

  function supplyBar(st) {
    const s = st.active.supply, T = s.total.value || 0;
    if (!T) return '';
    const parts = [['Circulating', s.circulating.value, '#22d3ee'], ['Gold Vault', s.goldVault.value, '#fbbf24'], ['PoPC Pool', s.popcPool.value, '#a78bfa']];
    const sum = parts.reduce((a, p) => a + (p[1] || 0), 0);
    return `<div class="sbar" role="img" aria-label="Supply composition">${parts.map((p) => `<span style="width:${(p[1] / T * 100).toFixed(3)}%;background:${p[2]}" title="${esc(p[0] + ': ' + num(p[1], 4) + ' SOST')}"></span>`).join('')}</div>
      <div class="legend">${parts.map((p) => `<span><i style="background:${p[2]}"></i>${esc(p[0])} ${num(p[1] / T * 100, 1)}%</span>`).join('')}</div>
      <div class="sub">Check: circulating + vault + pool = ${num(sum, 4)} ${Math.abs(sum - T) < 1e-4 ? '<span class="pill yes">= total</span>' : '<span class="pill warn">≠ total</span>'}</div>`;
  }

  function renderActive(st) {
    const a = st.active;
    const ch = a.chain, tm = a.timing, c = a.consensus, mi = a.miners, d = a.dtd, j = a.jackpot, nb = a.nodeBind, n = a.network, s = a.supply;
    const tile = (cls, l, m, extra) => `<div class="tile ${cls}"><div class="l">${esc(l)}</div><div class="n">${m}</div><div class="d">${extra || ''}</div></div>`;
    const html = [];
    html.push(`<div class="p" id="pChain"><h3>Chain ${tag('live')}${src(ch.height)}</h3>
      <div class="big">#${num(ch.height.value)}</div>
      <div class="kv"><span class="k">Tip age</span><span class="v">${tk(st.tipTime, 'ago', dur(ch.tipAge.value))}</span>
      <span class="k">Latest interval</span><span class="v">${dur(ch.latestInterval.value)}</span>
      <span class="k">Latest producer</span><span class="v">${addr(ch.latestProducer.value)}</span>
      <span class="k">Mempool</span><span class="v">${num(ch.mempool.value)} tx</span></div></div>`);

    html.push(`<div class="p w8"><h3>Block timing ${src(tm.avg288)}</h3>
      <div class="tiles">
        ${tile('target', 'Target', '600 s', 'consensus')}
        ${tile('instant', 'Latest', dur(ch.latestInterval.value), 'instant · 1 block')}
        ${tile('window', 'Avg 24', dur(tm.avg24.value), 'window · last 24')}
        ${tile('window', 'Avg 72', dur(tm.avg72.value), 'window · last 72')}
        ${tile('window', 'Avg 288', dur(tm.avg288.value), 'window · last 288 (bitsQ input)')}
      </div>${intervalsChart(st)}</div>`);

    html.push(`<div class="p"><h3>bitsQ ${tag('live')}${src(c.bitsQ)}</h3>
      <div class="big">${num(c.bitsQ.value)}</div>
      <div class="sub">Numeric target difficulty · Q16.16 = ${num(c.bitsQ.q16, 4)}</div>
      <div class="kv"><span class="k">Next block bitsQ</span><span class="v">${num(c.bitsQ.next)}</span>
      <span class="k">Change rule</span><span class="v">avg288 vs 600 s</span></div>
      <div class="sub">bitsQ only sets how low the commit must be. It does not describe the structural work.</div></div>`);

    html.push(`<div class="p w8"><h3>Equalizer ${tag('live')}${src(c.equalizerNext)}</h3>
      <div class="big">${esc(c.equalizerNext.value || '—')} <small>next block · lowest valid profile if stamped now</small></div>
      ${eqScale(st)}
      <div class="kv"><span class="k">Schedule lag (node)</span><span class="v">${num(c.equalizerNext.lag)} blocks</span>
      <span class="k">Latest block ceiling (no time relief)</span><span class="v">${esc(c.equalizerTip.base || '—')}</span>
      <span class="k">Latest block floor at its timestamp</span><span class="v">${c.equalizerTip.floor ? esc(c.equalizerTip.floor) + ' <span class="dim">(' + esc(dur(c.equalizerTip.elapsed)) + ' → cascade −' + S.cascadeDrop(c.equalizerTip.elapsed) + ')</span>' : 'n/a'}</span>
      <span class="k">Latest block declared &amp; verified</span><span class="v">${esc(c.equalizerTip.value || '—')} ${c.equalizerTip.floor && S.profileIndex(c.equalizerTip.value) >= S.profileIndex(c.equalizerTip.floor) && S.profileIndex(c.equalizerTip.value) <= S.profileIndex(c.equalizerTip.base) ? '<span class="pill yes">within floor…ceiling</span>' : ''}</span></div>
      <div class="rule"><b>Consensus rule.</b> A block is valid only if <code>floor ≤ declared ≤ ceiling</code>. The <b>ceiling</b> comes from the schedule lag. The <b>floor</b> is the same computation with time relief applied at the block's own timestamp: the longer a block takes, the lower the floor (cascade relief from 540 s, anti-stall). Every node checks both bounds and then verifies the proof with the parameters of the <b>declared</b> profile, so a declared profile below the ceiling is a legitimate eased block, never a weaker-than-required one. The floor shown here is recomputed from the published rule for blocks under 3,600 s (casert.cpp:1010); above that it is shown as n/a.</div>
      <div class="sub">The Equalizer (43 profiles E7–H35) sets the stability probes and refinement steps a valid proof must survive. It is separate from bitsQ.</div></div>`);

    const shares = mi.shares.slice(0, 8).map((x) => `<tr><td>${addr(x.addr)}</td><td>${num(x.blocks)}</td><td>${num(x.share * 100, 1)}%</td><td><div class="sharebar"><span style="width:${(x.share * 100).toFixed(1)}%"></span></div></td></tr>`).join('');
    html.push(`<div class="p"><h3>Active miners ${tag('window')}${src(mi.active288)}</h3>
      <div class="big">${num(mi.active288.value)} <small>in the last 288 blocks</small></div>
      <div class="sub">Cross-check from the block series: ${num(mi.active288Series.value)}</div>
      <div class="tbl-wrap"><table><thead><tr><th>Producer</th><th>Blocks</th><th>Share</th><th></th></tr></thead><tbody>${shares}</tbody></table></div></div>`);

    html.push(`<div class="p"><h3>Normal DTD — every block ${tag('live')}${src(d.eligibleNext)}</h3>
      <div class="big">${num(d.eligibleNext.value)} <small>eligible for #${num(d.nextHeight.value)}</small></div>
      <div class="kv"><span class="k">Cooldown window</span><span class="v">${num(d.cooldownWindow.value)} blocks</span>
      <span class="k">In cooldown</span><span class="v">${(d.cooldownMiners.value || []).map(addr).join(', ') || 'none'}</span>
      <span class="k">Payout</span><span class="v">${num(d.payout.value, 8)} SOST</span></div>
      <div class="proj"><div class="lbl">PROJECTED NEXT DTD WINNER — CURRENT TIP</div>${addr(d.projectedWinner.value)}
      <div class="sub">Projection for #${num(d.nextHeight.value)} if mined on the current tip. <b>The projection changes when the chain tip changes</b>; it is not a confirmed winner until block #${num(d.nextHeight.value)} exists.</div></div>
      <div class="sub">Independent of the DTD Jackpot: at a jackpot height both draws run in the same block, each with its own rules and its own winner (or none).</div></div>`);

    const prs = n.peers.map((p) => `<tr><td>${esc(p.addr)}</td><td>${esc(p.direction)}</td><td>${num(p.height)}</td><td>${p.acked ? '✔' : '…'}</td></tr>`).join('');
    html.push(`<div class="p"><h3>Network ${tag('live')}${src(n.uniqueActiveNodes)}</h3>
      <div class="big">${num(n.connectedPeers.value)} <small>connected peers</small></div>
      <div class="sub">Peers of the public node only — <b>not a census of the SOST network</b>.</div>
      <div class="kv"><span class="k">Synced peers (≥ tip−1)</span><span class="v">${num(n.syncedPeers.value)}</span>
      <span class="k">Unique active nodes seen</span><span class="v">${num(n.uniqueActiveNodes.value)}</span>
      <span class="k">Public node</span><span class="v">${esc(n.localStatus.value || '—')}</span></div>
      <div class="tbl-wrap"><table><thead><tr><th>Peer</th><th>Dir</th><th>Height</th><th>Ack</th></tr></thead><tbody>${prs}</tbody></table></div></div>`);

    const cand = j.candidateList.map((x) => `<tr><td>${addr(x.addr)}</td><td>${num(x.powBlocks)}</td><td>${x.bound ? '<span class="pill yes">✔ bound</span>' : '<span class="pill no">✘ not bound</span>'}</td><td>${num(x.heartbeats)}/${num(x.heartbeatsRequired)}</td><td>${x.eligible ? '<span class="pill yes">YES</span>' : '<span class="pill no">NO</span>'}</td></tr>`).join('');
    html.push(`<div class="p w6"><h3>DTD Jackpot ${j.isV2.value ? 'V2' : ''} ${tag('live')}${src(j.eligible)}</h3>
      <div class="tiles">
        ${tile('target', 'Next draw', '#' + num(j.nextHeight.value), '')}
        ${tile('instant', 'Blocks left', num(j.blocksRemaining.value), '')}
        ${tile('instant', 'ETA', '~' + tk(st.tipTime != null && j.etaSeconds.value != null ? st.tipTime + j.etaSeconds.value : null, 'until', dur(j.etaSeconds.value)), '600 s per block from the tip time (estimate)')}
        ${tile('instant', 'Eligible', num(j.eligible.value) + ' / ' + num(j.candidates.value), 'getjackpotv2audit')}
        ${tile('instant', 'NODE_BIND', num(nb.bound.value) + ' / ' + num(nb.of.value), 'candidates bound')}
      </div>
      ${j.rolloverIfNoneEligible.value ? '<div class="sub" style="margin-top:8px"><span class="pill warn">ROLLOVER if still 0 eligible at the draw</span></div>' : ''}
      <div class="kv"><span class="k">Pot / reserve</span><span class="v">${num(j.pot.value, 2)} / ${num(j.reserve.value, 2)} SOST</span>
      <span class="k">Rules</span><span class="v">≥ ${num(j.minPowBlocks.value)} PoW blocks in ${num(j.powWindow.value)} · heartbeats ${num(j.heartbeatRequired.value)}</span></div>
      <div class="sub">A separate draw from the normal DTD: NODE_BIND + heartbeats + SbPoW blocks, weighted by PoW, no cooldown and no anti-dominance. The normal DTD winner of a jackpot block is <b>not</b> the jackpot winner.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Candidate</th><th>PoW blocks</th><th>NODE_BIND</th><th>Heartbeats</th><th>Eligible</th></tr></thead><tbody>${cand}</tbody></table></div></div>`);

    html.push(`<div class="p w6"><h3>Supply ${tag('live')}${src(s.total)}</h3>
      <div class="big">${num(s.total.value, 4)} <small>SOST total</small></div>${supplyBar(st)}
      <div class="kv"><span class="k">Circulating</span><span class="v">${num(s.circulating.value, 4)}</span>
      <span class="k">Circulating (mining)</span><span class="v">${num(s.circulatingMining.value, 4)}</span>
      <span class="k">Gold Vault</span><span class="v">${num(s.goldVault.value, 4)}</span>
      <span class="k">PoPC Pool</span><span class="v">${num(s.popcPool.value, 4)}</span>
      <span class="k">Jackpot reserve (= Vault + Pool)</span><span class="v">${num(s.jackpotReserve.value, 4)}</span></div></div>`);
    $('activeGrid').innerHTML = html.join('');
  }

  function renderEvents(st) {
    const e = st.events, sb = e.submitblock.value || {};
    const reasons = Object.entries(sb.reasons || {}).map(([k, v]) => esc(k) + ' ' + v).join(', ') || 'none';
    const obs = e.observed.slice(-6).reverse().map((o) => `${new Date(o.t * 1000).toISOString().slice(11, 19)}Z ${esc(o.kind)} — ${esc(o.detail)}`).join('<br>') || 'none observed since the collector started';
    $('eventGrid').innerHTML = `
      <div class="evi"><div class="t">Blocks submitted to node (since boot)</div><div class="n">${num(sb.accepted)} / ${num(sb.received)}</div><div class="d">accepted / received · rejected ${num(sb.rejected)} (${reasons})</div></div>
      <div class="evi"><div class="t">Misbehavior events (since boot)</div><div class="n">${num(e.misbehavior.value)}</div><div class="d">getminerstats</div></div>
      <div class="evi"><div class="t">Public node uptime</div><div class="n">${tk(e.nodeBoot.value, 'ago', dur(e.nodeUptime.value))}</div><div class="d">boot ${e.nodeBoot.value ? new Date(e.nodeBoot.value * 1000).toISOString().slice(0, 16).replace('T', ' ') + 'Z' : '—'}</div></div>
      <div class="evi"><div class="t">Reorgs</div><div class="n">n/a</div><div class="d">not exposed by the public RPC — shown as unknown, never as 0</div></div>
      <div class="evi"><div class="t">Observed by the collector</div><div class="n">${num(e.observed.length)}</div><div class="d">${obs}</div></div>`;
  }

  function renderHistorical(st) {
    const h = st.historical;
    const peak = h.peakActive288InSeries.value;
    const hist = h.profileHistogram, maxc = Math.max(1, ...Object.values(hist));
    const W = 860, H = 90, bw = W / 43;
    let hb = '';
    for (let i = -7; i <= 35; i++) {
      const cnt = hist[i] || 0, hh = cnt / maxc * (H - 14);
      hb += `<rect x="${((i + 7) * bw).toFixed(1)}" y="${(H - 14 - hh).toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${hh.toFixed(1)}" fill="${profColor(i)}" opacity=".8"><title>${esc(S.profileName(i) + ': ' + cnt + ' blocks')}</title></rect>`;
    }
    hb += `<text x="0" y="${H}">E7</text><text x="${(7 * bw).toFixed(0)}" y="${H}">B0</text><text x="${(27 * bw).toFixed(0)}" y="${H}">H20</text><text x="${W}" y="${H}" text-anchor="end">H35</text>`;
    const bq = h.bitsQSeries, bmin = Math.min(...bq.map((x) => x[1])), bmax = Math.max(...bq.map((x) => x[1]));
    const pts = bq.map((x, i) => `${(i / Math.max(1, bq.length - 1) * W).toFixed(1)},${(70 - (bmax === bmin ? 35 : (x[1] - bmin) / (bmax - bmin) * 60)).toFixed(1)}`).join(' ');
    const range = h.seriesRange ? '#' + num(h.seriesRange[0]) + '–#' + num(h.seriesRange[1]) : '—';
    $('histGrid').innerHTML = `
      <div class="p"><h3>Distinct block producers (all time) ${src(h.uniqueProducersSinceGenesis)}</h3>
        <div class="big">${num(h.uniqueProducersSinceGenesis.value)}</div>
        <div class="sub">${num(h.uniqueProducersSinceGenesis.value)} distinct addresses have produced at least one block historically. A cumulative count — <b>not</b> a number of miners, and <b>not</b> miners active now (see Active miners above).</div>
        <div class="kv"><span class="k">Since #${num(h.producersSinceWindowStart.from)}</span><span class="v">${num(h.producersSinceWindowStart.value)}</span></div></div>
      <div class="p"><h3>Most distinct producers in one 288-block window ${src(h.peakActive288InSeries)}</h3>
        <div class="big">${peak ? num(peak.n) : '—'}</div>
        <div class="sub">Highest distinct-producer count in any 288-block window of the loaded series (${esc(range)}), reached at #${peak ? num(peak.at) : '—'}. Earlier history is not in this series.</div></div>
      <div class="p"><h3>Schedule since genesis ${src(h.scheduleSinceGenesis)}</h3>
        <div class="big">${h.scheduleSinceGenesis.value == null ? '—' : (h.scheduleSinceGenesis.value >= 0 ? '+' : '') + num(h.scheduleSinceGenesis.value)} <small>blocks vs 600 s schedule</small></div>
        <div class="sub">Lifetime aggregate since genesis. Different window from avg 24/72/288 above — not comparable to them.</div></div>
      <div class="p w6"><h3>Equalizer profiles mined (${esc(range)})</h3>
        <svg class="chart" viewBox="0 0 ${W} ${H + 4}" role="img" aria-label="Histogram of Equalizer profiles">${hb}</svg></div>
      <div class="p w6"><h3>bitsQ evolution (${esc(range)})</h3>
        <svg class="chart" viewBox="0 0 ${W} 80" role="img" aria-label="bitsQ over the series"><polyline points="${pts}" fill="none" stroke="#d9cbb0" stroke-width="1.5"/>
        <text x="0" y="78">${num(bmin)}</text><text x="${W}" y="10" text-anchor="end">${num(bmax)}</text></svg>
        ${bmin === bmax ? '<div class="sub">bitsQ was unchanged (' + num(bmin) + ') across the whole loaded series.</div>' : ''}</div>
      <div class="p w12"><h3>Protocol milestones (verified in sost-core)</h3>
        <ul class="miles">${h.milestones.map((m) => `<li><span class="hh">#${num(m.h)}</span><span>${esc(m.label)} <span class="s">· ${esc(m.src)}</span></span></li>`).join('')}</ul></div>`;
  }

  const PALETTE = ['#fb010d', '#22d3ee', '#39ff14', '#fbbf24', '#a78bfa', '#f472b6', '#60a5fa', '#f97316'];
  let lastMosaicTip = null;
  function renderMosaic(st) {
    const rec = st.active.recent.value || [];
    const rank = st.active.miners.shares.map((x) => x.addr);
    const color = (a) => { const i = rank.indexOf(a); return i >= 0 && i < PALETTE.length ? PALETTE[i] : '#6b7280'; };
    const n = rec.length;
    const tipH = n ? rec[n - 1].h : null;
    $('mosaic').innerHTML = rec.map((b, i) => {
      const age = n - 1 - i, op = age < 6 ? 1 : Math.max(.38, 1 - age / 160);
      const fresh = lastMosaicTip != null && b.h > lastMosaicTip ? ' fresh' : '';
      return `<div class="b${fresh}" data-m="${esc(b.miner)}" style="background:${color(b.miner)};opacity:${op.toFixed(2)};border-bottom-color:${ivColor(b.interval)}" title="${esc('#' + num(b.h) + ' · ' + S.shortAddr(b.miner) + ' · ' + dur(b.interval) + ' · ' + (S.profileName(b.profile) || ''))}"></div>`;
    }).join('');
    lastMosaicTip = tipH;
    const counts = {};
    rec.forEach((b) => { counts[b.miner] = (counts[b.miner] || 0) + 1; });
    $('mosaicLegend').innerHTML = Object.keys(counts).sort((a, b) => counts[b] - counts[a]).map((a) =>
      `<span class="lg" tabindex="0" data-m="${esc(a)}"><i style="background:${color(a)}"></i>${esc(S.shortAddr(a))} · ${counts[a]}</span>`).join('') +
      '<span><i style="background:#22d3ee"></i>bar &lt;5m</span><span><i style="background:#39ff14"></i>5–15m</span><span><i style="background:#fbbf24"></i>15–30m</span><span><i style="background:#fb010d"></i>&gt;30m</span>';
    const mz = $('mosaic');
    $('mosaicLegend').querySelectorAll('.lg').forEach((el) => {
      const on = () => { mz.classList.add('iso'); mz.querySelectorAll('.b').forEach((b) => b.classList.toggle('on', b.dataset.m === el.dataset.m)); };
      const off = () => mz.classList.remove('iso');
      el.addEventListener('mouseenter', on); el.addEventListener('focus', on);
      el.addEventListener('mouseleave', off); el.addEventListener('blur', off);
    });
  }

  function renderHero(st) {
    const a = st.active, j = a.jackpot;
    const chip = (l, n2, s2) => `<div class="chip"><div class="l">${esc(l)}</div><div class="n">${n2}</div><div class="s">${s2}</div></div>`;
    $('hero').innerHTML = `<div><div class="cap"><span class="dot"></span>Block height · live</div><div class="hh">#${num(a.chain.height.value)}</div>
        <div class="sub">tip ${tk(st.tipTime, 'ago', dur(a.chain.tipAge.value))} ago · by ${addr(a.chain.latestProducer.value)}</div></div>
      <div class="chips">
        ${chip('Avg block time · 288', dur(a.timing.avg288.value), 'target 600 s')}
        ${chip('bitsQ', num(a.consensus.bitsQ.value), 'numeric target')}
        ${chip('Equalizer', esc(a.consensus.equalizerNext.value || '—'), 'structural profile, next block')}
        ${chip('Active miners · 288', num(a.miners.active288.value), 'last 288 blocks')}
        ${chip('Next jackpot', '#' + num(j.nextHeight.value), num(j.blocksRemaining.value) + ' blocks · ~' + tk(st.tipTime != null && j.etaSeconds.value != null ? st.tipTime + j.etaSeconds.value : null, 'until', dur(j.etaSeconds.value)))}
        ${chip('Supply', num(a.supply.total.value, 2), 'SOST')}
      </div>`;
  }

  function renderHealth(st) {
    $('health').innerHTML = st.health.map((f) => `<span class="fact ${esc(f.state)}" title="${esc('Rule: ' + f.rule)}"><span class="k">${esc(f.name)}</span><span class="v">${esc(f.value)}</span></span>`).join('');
  }

  let lastHeight = null;
  function render(st) {
    renderHero(st); renderHealth(st); renderMosaic(st); renderActive(st); renderEvents(st); renderHistorical(st);
    $('topHeight').textContent = '#' + num(st.meta.height);
    $('updated').textContent = 'updated ' + new Date(st.meta.fetchedAt * 1000).toISOString().slice(11, 19) + 'Z';
    if (lastHeight != null && st.meta.height > lastHeight) {
      const el = $('pChain');
      if (el) { el.classList.remove('pulse'); void el.offsetWidth; el.classList.add('pulse'); }
    }
    lastHeight = st.meta.height;
  }

  // ---- driver: revalidate the collector document every second (HTTP 304 when unchanged, so an
  // unchanged second costs a header, not a download); render only when it changed. Clock-only values
  // advance locally every second with no request at all. Paused while the tab is hidden.
  const POLL_MS = 1000;
  const source = new window.CRSource();
  let lastCollected = null, lastDoc = null, busy = false;
  window.__crLatency = [];   // per new tip: collector saw it → this browser drew it (server clock, ms)
  function tick() {
    const now = source.now();
    document.querySelectorAll('.tk').forEach((el) => {
      const t = Number(el.dataset.t);
      el.textContent = el.dataset.k === 'until' ? (t - now > 0 ? hms(t - now) : 'due') : hms(Math.max(0, now - t));
    });
    if (lastDoc && !lastDoc.replay) {
      const age = Math.max(0, Math.floor(now - lastDoc.collected_at));
      const stale = age > 45;   // the collector rewrites at least every 15 s
      $('srcBadge').textContent = stale ? 'DATA STALE · collector ' + age + ' s ago' : 'LIVE · read-only snapshot';
      $('srcBadge').className = 'badge ' + (stale ? 'err' : 'live');
    }
  }
  async function refresh() {
    if (busy || document.hidden) return; busy = true;
    try {
      const { doc, bundle } = await source.load();
      if (doc.collected_at !== lastCollected) {
        const st = S.normalize(bundle);
        st.tipTime = st.active.chain.tipAge.value != null ? st.meta.fetchedAt - st.active.chain.tipAge.value : null;
        const newTip = lastHeight != null && st.meta.height > lastHeight;
        window.__crState = st; window.__crDoc = doc; window.__crDownloads = source.downloads;
        render(st);
        if (newTip && doc.tip_changed_at) {
          window.__crLatency.push({ height: st.meta.height, ms: Math.round((source.now() - doc.tip_changed_at) * 1000) });
          window.__crLatency = window.__crLatency.slice(-20);
        }
        lastCollected = doc.collected_at;
      }
      lastDoc = doc;
      if (doc.replay) {
        $('srcBadge').textContent = 'REPLAY · snapshot ' + new Date(doc.collected_at * 1000).toISOString().slice(0, 16).replace('T', ' ') + 'Z';
        $('srcBadge').className = 'badge replay';
      }
      $('updated').textContent = 'collected ' + new Date(doc.collected_at * 1000).toISOString().slice(11, 19) + 'Z';
      tick();
    } catch (e) {
      $('srcBadge').textContent = 'DATA UNAVAILABLE — ' + e.message.slice(0, 60);
      $('srcBadge').className = 'badge err';
    } finally { busy = false; }
  }
  refresh();
  setInterval(refresh, POLL_MS);
  (function second() { tick(); setTimeout(second, 1000 - ((source.now() * 1000) % 1000) + 5); })();   // on the second boundary
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });

  // HIDE NAV / SHOW NAV — hides the sticky top bar; the choice is remembered on this browser only.
  const navHide = $('navHide'), navShow = $('navShow');
  function setNav(hidden) {
    document.body.classList.toggle('cr-nav-hidden', hidden);
    if (navShow) navShow.hidden = !hidden;
    if (navHide) navHide.setAttribute('aria-expanded', String(!hidden));
    try { localStorage.setItem('sost_cr_nav_hidden', hidden ? '1' : '0'); } catch (e) {}
  }
  if (navHide && navShow) {
    navHide.addEventListener('click', () => { setNav(true); navShow.focus(); });
    navShow.addEventListener('click', () => { setNav(false); navHide.focus(); });
    let saved = null;
    try { saved = localStorage.getItem('sost_cr_nav_hidden'); } catch (e) {}
    if (saved === '1') setNav(true);
  }
})();

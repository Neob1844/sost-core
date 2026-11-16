/* SOST Convergence Universe — demo data layer.
   Reads the same static snapshots the production Control Room uses
   (api/block_series.json, api/control_room.json), here as local copies
   captured from sostcore.com (see data/CAPTURED_AT.txt). No RPC, no polling.
   In integration this module is replaced by the shared, same-origin source
   (control-room/adapter.js) so no second refresh loop is ever created. */
(function (root) {
  'use strict';
  // Producer palette: official spectrum colours, assigned by producer rank in the window.
  // Red is reserved for the SOST brand and is never used for a producer.
  var PALETTE = ['#22d3ee', '#e879f9', '#a3e635', '#facc15', '#fb923c', '#8b5cf6', '#3b82f6', '#4ade80'];
  var SHAPES = ['circle', 'square', 'triangle', 'diamond', 'ring', 'cross', 'hex', 'bar'];
  function short(a) { return a ? a.slice(0, 9) + '…' + a.slice(-4) : '—'; }
  function profileName(i) { return i < 0 ? 'E' + (-i) : i === 0 ? 'B0' : 'H' + i; }
  async function load() {
    var out = { mode: 'snapshot', capturedAt: null, rows: [], tip: 0, cr: null, producers: [] };
    try { out.capturedAt = (await (await fetch('data/CAPTURED_AT.txt')).text()).trim(); } catch (e) {}
    try {
      var s = await (await fetch('data/block_series.json')).json();
      // rows: [height, unix time, bits_q, casert_profile_index, miner_address]
      out.rows = s.rows.map(function (r, i, a) {
        return { h: r[0], t: r[1], bq: r[2], prof: r[3], miner: r[4], dt: i ? r[1] - a[i - 1][1] : null };
      });
      out.tip = s.tip; out.spacing = s.target_spacing || 600;
    } catch (e) { out.error = 'series unavailable'; }
    try { out.cr = await (await fetch('data/control_room.json')).json(); } catch (e) {}
    var counts = {};
    out.rows.forEach(function (r) { counts[r.miner] = (counts[r.miner] || 0) + 1; });
    out.producers = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; }).map(function (m, i) {
      return { miner: m, n: counts[m], pct: 100 * counts[m] / out.rows.length, color: i < PALETTE.length ? PALETTE[i] : '#64748b', shape: SHAPES[Math.min(i, SHAPES.length - 1)], rank: i };
    });
    var byMiner = {}; out.producers.forEach(function (p) { byMiner[p.miner] = p; });
    out.producerOf = function (m) { return byMiner[m] || { color: '#64748b', shape: 'bar', rank: 99 }; };
    return out;
  }
  function hexToRgb(h) { var n = parseInt(h.slice(1), 16); return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255]; }
  root.SOSTData = { load: load, short: short, profileName: profileName, hexToRgb: hexToRgb, PALETTE: PALETTE };
})(window);

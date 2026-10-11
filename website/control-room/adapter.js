/* SOST Control Room V2 — data source (browser).
 * The browser NEVER talks RPC: it downloads the static document written by the single server-side
 * collector (/api/control_room.json) plus the static block series. Node load is independent of the
 * number of visitors.
 */
(function (root) {
  'use strict';
  function Source(opts) {
    this.docUrl = (opts && opts.docUrl) || 'api/control_room.json';
    this.seriesUrl = (opts && opts.seriesUrl) || 'api/block_series.json';
    this.series = null;
    this.seriesAt = 0;
    this.downloads = 0;
  }
  Source.prototype.getJSON = async function (url) {
    this.downloads++;
    // 'no-cache' = revalidate with the server (ETag/Last-Modified): an unchanged file costs a 304, not a download
    const r = await fetch(url, { cache: 'no-cache' });
    if (!r.ok) throw new Error(url + ' HTTP ' + r.status);
    return r.json();
  };
  /** Returns { doc, bundle } ready for CRState.normalize(bundle). */
  Source.prototype.load = async function () {
    const doc = await this.getJSON(this.docUrl);
    if (!this.series || Date.now() - this.seriesAt > 300000) {   // series: refresh every 5 min
      try { this.series = await this.getJSON(this.seriesUrl); this.seriesAt = Date.now(); } catch (e) { if (!this.series) this.series = { rows: [] }; }
    }
    const b = Object.assign({}, doc.bundle, { series: this.series });
    const db = doc.bundle.deltaBlocks;
    if (db && db.fields) {   // schema 2: compact rows -> objects
      b.deltaBlocks = db.rows.map((r) => { const o = {}; db.fields.forEach((f, i) => { o[f] = r[i]; }); return o; });
      if (b.deltaBlocks.length) b.deltaBlocks[b.deltaBlocks.length - 1].hash = db.tip_hash;
    }
    b.now = doc.replay ? doc.collected_at : Math.floor(Date.now() / 1000);
    b.source = doc.replay ? 'replay' : 'live';
    b.recordedAt = doc.collected_at;
    return { doc, bundle: b };
  };
  root.CRSource = Source;
})(typeof self !== 'undefined' ? self : this);

/* sost-gold-reference.js — SINGLE shared source for the SOST gold reference.
 * 1 SOST is VOLUNTARILY DENOMINATED as 1/1000 of the gold content of the Bretton
 * Woods dollar (official parity 35 USD per troy ounce): 0.8886707657142857 mg of
 * gold. This is a MONETARY REFERENCE and a project denomination choice, not a
 * market price, not a peg, not collateral, not redeemable. Every public page must
 * consume the constants + formula from here — never re-implement them inline.
 */
(function (root) {
  "use strict";
  // Exact, single source of truth: 1/1000 of the Bretton Woods dollar gold content.
  // (troy_oz_grams / 35 USD-per-oz) grams-per-dollar == mg-per-SOST after the /1000
  // denomination and the g->mg factor cancel. = 0.8886707657142857 mg.
  var WEIGHT_MG = 31.1034768 / 35;  // 0.8886707657142857 mg (Bretton Woods reference)
  var MG_PER_TROY_OZ = 31103.4768; // milligrams per troy ounce
  var GOLD_URL = 'https://api.coingecko.com/api/v3/simple/price?ids=tether-gold,pax-gold&vs_currencies=usd';

  // Canonical conversions (pure — the ONLY place these live).
  function sostFromOz(goldUsdPerOz) { return (Number(goldUsdPerOz) || 0) * WEIGHT_MG / MG_PER_TROY_OZ; }
  function sostFromGram(goldUsdPerGram) { return (Number(goldUsdPerGram) || 0) * (WEIGHT_MG / 1000); } // = *0.0008886707657142857
  function gramFromOz(oz) { return (Number(oz) || 0) / 31.1034768; }
  function mgFromOz(oz) { return (Number(oz) || 0) / MG_PER_TROY_OZ; } // USD per mg of gold from an oz price

  var _state = { goldUsdPerOz: 0, goldUsdPerGram: 0, goldUsdPerMg: 0, sostReferenceUsd: 0, ts: '', ok: false };
  function _apply(oz) {
    _state.goldUsdPerOz = oz;
    _state.goldUsdPerGram = gramFromOz(oz);
    _state.goldUsdPerMg = _state.goldUsdPerGram / 1000;
    _state.sostReferenceUsd = sostFromOz(oz);
    _state.ok = oz > 0;
    return _state;
  }

  var _cache = null, _pending = null;
  // load() -> Promise<state>. Single fetch + single fallback for the whole site.
  function load() {
    if (_cache && (new Date().getTime() - _cache._t) < 60000) return Promise.resolve(_cache);
    if (_pending) return _pending;
    _pending = fetch(GOLD_URL).then(function (r) { return r.json(); }).then(function (d) {
      var xaut = (d['tether-gold'] && d['tether-gold'].usd) || 0;
      var paxg = (d['pax-gold'] && d['pax-gold'].usd) || 0;
      var oz = (xaut && paxg) ? (xaut + paxg) / 2 : (xaut || paxg || 0);
      _apply(oz); _state.ts = new Date().toISOString();
      _cache = {}; for (var k in _state) _cache[k] = _state[k]; _cache._t = new Date().getTime();
      _pending = null; return _cache;
    }).catch(function () { _pending = null; return _state; });
    return _pending;
  }

  root.SOSTGold = {
    WEIGHT_MG: WEIGHT_MG,
    MG_PER_TROY_OZ: MG_PER_TROY_OZ,
    GOLD_URL: GOLD_URL,
    sostFromOz: sostFromOz,
    sostFromGram: sostFromGram,
    gramFromOz: gramFromOz,
    mgFromOz: mgFromOz,
    load: load,
    get: function () { return _state; },
    // convenience label used across surfaces
    label: '1 SOST ≡ 1.14 mg gold · reference, not a market price'
  };
})(window);

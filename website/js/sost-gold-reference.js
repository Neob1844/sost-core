/* sost-gold-reference.js — SINGLE shared source for the SOST gold reference.
 *
 * CURRENT REFERENCE:  1 SOST = 0.8886707657 mg of fine gold.
 * This is one-thousandth of the gold content of one 1944 Bretton Woods dollar:
 *   Bretton Woods parity      = 35 USD per troy ounce
 *   1 troy ounce              = 31.1034768 g
 *   gold per dollar           = 31.1034768 / 35 = 0.8886707657… g  (888.6707657 mg)
 *   1 SOST reference (1/1000) = 0.8886707657 mg
 *
 * It is a MONETARY / MATHEMATICAL REFERENCE ONLY — NOT a market price, NOT a peg,
 * NOT collateral, NOT redeemable for gold, and NOT a guaranteed floor. SOST is not
 * gold-backed. The real traded price is set by the market and can diverge completely.
 * The reference changes NOTHING about SOST supply, consensus, ConvergenceX, DTD,
 * Jackpot or the Gold Vault. Every public page must consume the constants + formula
 * from here — never re-implement them inline.
 *
 * (The previous 1.14 mg figure is HISTORICAL only — see HISTORICAL_WEIGHT_MG — and is
 *  never used in any live calculation.)
 */
(function (root) {
  "use strict";

  // ---- Bretton Woods derivation (the single origin of the constant) ----
  var BW_USD_PER_TROY_OZ = 35;          // 1944 official parity
  var TROY_OZ_G = 31.1034768;           // grams per troy ounce (exact)
  var MG_PER_TROY_OZ = TROY_OZ_G * 1000; // 31103.4768 mg
  // gold content of one Bretton Woods dollar, in mg, then one-thousandth of it:
  var WEIGHT_MG = (TROY_OZ_G / BW_USD_PER_TROY_OZ) * 1000 / 1000; // = 0.8886707657 mg
  var WEIGHT_G = WEIGHT_MG / 1000;      // = 0.0008886707657 g  (the USD/SOST multiplier)

  var HISTORICAL_WEIGHT_MG = 1.14;      // superseded reference — historical/context ONLY

  var GOLD_URL = 'https://api.coingecko.com/api/v3/simple/price?ids=tether-gold,pax-gold&vs_currencies=usd';

  // Canonical conversions (pure — the ONLY place these live).
  // USD/SOST = gold_USD_per_gram × 0.0008886707657
  function sostFromGram(goldUsdPerGram) { return (Number(goldUsdPerGram) || 0) * WEIGHT_G; }
  function sostFromOz(goldUsdPerOz) { return (Number(goldUsdPerOz) || 0) * WEIGHT_MG / MG_PER_TROY_OZ; }
  function gramFromOz(oz) { return (Number(oz) || 0) / TROY_OZ_G; }
  function mgFromOz(oz) { return (Number(oz) || 0) / MG_PER_TROY_OZ; } // USD per mg of gold from an oz price

  var _state = { goldUsdPerOz: 0, goldUsdPerGram: 0, goldUsdPerMg: 0, sostReferenceUsd: 0, ts: '', ok: false, source: 'coingecko:tether-gold,pax-gold' };
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
  // On provider failure `ok:false` — callers MUST show "reference temporarily
  // unavailable" and NEVER present a stale/static number as a live quote.
  function load() {
    if (_cache && (new Date().getTime() - _cache._t) < 60000) return Promise.resolve(_cache);
    if (_pending) return _pending;
    _pending = fetch(GOLD_URL).then(function (r) { return r.json(); }).then(function (d) {
      var xaut = (d['tether-gold'] && d['tether-gold'].usd) || 0;
      var paxg = (d['pax-gold'] && d['pax-gold'].usd) || 0;
      var oz = (xaut && paxg) ? (xaut + paxg) / 2 : (xaut || paxg || 0);
      _apply(oz); _state.ts = new Date().toISOString(); // UTC snapshot of the quote
      _cache = {}; for (var k in _state) _cache[k] = _state[k]; _cache._t = new Date().getTime();
      _pending = null; return _cache;
    }).catch(function () { _state.ok = false; _pending = null; return _state; });
    return _pending;
  }

  root.SOSTGold = {
    // canonical constants
    WEIGHT_MG: WEIGHT_MG,              // 0.8886707657
    WEIGHT_G: WEIGHT_G,               // 0.0008886707657 (USD/SOST multiplier vs gold USD/g)
    MG_PER_TROY_OZ: MG_PER_TROY_OZ,
    TROY_OZ_G: TROY_OZ_G,
    BW_USD_PER_TROY_OZ: BW_USD_PER_TROY_OZ,
    HISTORICAL_WEIGHT_MG: HISTORICAL_WEIGHT_MG,
    GOLD_URL: GOLD_URL,
    // conversions
    sostFromOz: sostFromOz,
    sostFromGram: sostFromGram,
    gramFromOz: gramFromOz,
    mgFromOz: mgFromOz,
    load: load,
    get: function () { return _state; },
    // convenience label used across surfaces
    label: '1 SOST ≡ 0.8886707657 mg gold · reference, not a market price'
  };
})(window);

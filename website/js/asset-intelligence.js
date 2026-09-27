/* SOST Asset Intelligence (lab) — modular, fully-traceable valuation engine.
 *
 * NOT financial advice, NOT an appraisal, NOT opaque AI/ML. Every output number
 * is produced by an explicit rule over declared inputs and is accompanied by a
 * trace entry {rule, inputs, formula, out}. A missing input LOWERS confidence and
 * WIDENS the range — it never invents a value.
 *
 * Pipeline: classify -> evidenceQuality -> model -> recoverability -> haircuts
 *           -> confidence -> financing.  value(asset) runs all stages.
 */
(function (root) {
  "use strict";

  // ---- per-category parameters (all explicit, all auditable) -------------
  // recovery = fraction of base market value realizable in an orderly forced sale
  // liqCostPct = cost of running that sale, as a fraction of the recovered amount
  // baseSpread = intrinsic price uncertainty even with perfect evidence
  // volatility = extra spread multiplier for thin/volatile markets
  // ltvCeiling = the MOST we would ever suggest lending, regardless of evidence
  // required = evidence keys that must be present for a full-confidence valuation
  var CATS = {
    precious_metal:    { recovery: 0.97, liqCostPct: 0.010, baseSpread: 0.02, volatility: 0.6, ltvCeiling: 0.85, required: ["assay", "weight", "spot_reference"] },
    commodity_lot:     { recovery: 0.85, liqCostPct: 0.030, baseSpread: 0.05, volatility: 1.0, ltvCeiling: 0.70, required: ["assay_or_grade", "quantity", "warehouse_receipt", "price_reference"] },
    real_estate:       { recovery: 0.80, liqCostPct: 0.060, baseSpread: 0.08, volatility: 1.0, ltvCeiling: 0.70, required: ["title", "appraisal", "comparables"] },
    machinery:         { recovery: 0.60, liqCostPct: 0.120, baseSpread: 0.10, volatility: 1.2, ltvCeiling: 0.50, required: ["invoice", "serial", "inspection"] },
    vehicle:           { recovery: 0.70, liqCostPct: 0.080, baseSpread: 0.08, volatility: 1.0, ltvCeiling: 0.55, required: ["title", "vin", "inspection", "mileage"] },
    contractual_right: { recovery: 0.90, liqCostPct: 0.050, baseSpread: 0.06, volatility: 1.1, ltvCeiling: 0.60, required: ["contract", "payment_history", "counterparty_rating"] },
    company:           { recovery: 0.40, liqCostPct: 0.100, baseSpread: 0.20, volatility: 1.5, ltvCeiling: 0.35, required: ["audited_financials", "cap_table", "ebitda"] },
    art:               { recovery: 0.50, liqCostPct: 0.150, baseSpread: 0.25, volatility: 1.8, ltvCeiling: 0.30, required: ["provenance", "authentication", "appraisal", "comparables"] },
    digital_asset:     { recovery: 0.75, liqCostPct: 0.030, baseSpread: 0.15, volatility: 2.0, ltvCeiling: 0.40, required: ["market_reference", "custody_proof"] }
  };

  function round2(x) { return Math.round(x * 100) / 100; }
  function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }

  // ---- Stage 1: classification ------------------------------------------
  function classify(asset) {
    var p = CATS[asset.category];
    var trace = [{ rule: "classify", inputs: { category: asset.category }, formula: "lookup category parameter set", out: p ? "known" : "UNKNOWN" }];
    if (!p) throw new Error("unknown category: " + asset.category);
    return { params: p, trace: trace };
  }

  // ---- Stage 2: evidence quality ----------------------------------------
  // quality in [0,1] = present required items / total required; also returns the gaps.
  function evidenceQuality(asset, params) {
    var present = asset.evidence || {};
    var have = params.required.filter(function (k) { return present[k] === true || (present[k] != null && present[k] !== false); });
    var missing = params.required.filter(function (k) { return !(present[k] === true || (present[k] != null && present[k] !== false)); });
    var q = params.required.length ? have.length / params.required.length : 1;
    // independent third-party attestation nudges quality up but can never reach 1 alone
    var attest = (asset.attestations || []).filter(function (a) { return a && !a.revoked; }).length;
    var qAdj = clamp(q + Math.min(attest, 2) * 0.05, 0, 0.98 + (q >= 1 ? 0.02 : 0));
    return {
      quality: round2(qAdj),
      missing_evidence: missing,
      trace: [{ rule: "evidence_quality", inputs: { have: have.length, required: params.required.length, attestations: attest }, formula: "have/required + 0.05*min(attest,2)", out: round2(qAdj) }]
    };
  }

  // ---- Stage 3: per-category valuation models ---------------------------
  // Each returns a single base market value + a trace. No model guesses missing
  // numbers; if a required numeric input is absent it throws (caller supplies 0-safe
  // inputs) — the RANGE/confidence is where uncertainty is expressed, not the base.
  var MODELS = {
    precious_metal: function (a) {
      var v = a.weight_g * a.purity * a.spot_per_g;
      return { base: v, trace: { rule: "model:precious_metal", inputs: { weight_g: a.weight_g, purity: a.purity, spot_per_g: a.spot_per_g }, formula: "weight_g*purity*spot_per_g", out: round2(v) } };
    },
    commodity_lot: function (a) {
      var v = a.quantity * a.grade * a.price_per_unit;
      return { base: v, trace: { rule: "model:commodity_lot", inputs: { quantity: a.quantity, grade: a.grade, price_per_unit: a.price_per_unit }, formula: "quantity*grade*price_per_unit", out: round2(v) } };
    },
    real_estate: function (a) {
      var v = a.area_m2 * a.price_per_m2;
      return { base: v, trace: { rule: "model:real_estate", inputs: { area_m2: a.area_m2, price_per_m2: a.price_per_m2 }, formula: "area_m2*price_per_m2 (comparables)", out: round2(v) } };
    },
    machinery: function (a) {
      var dep = clamp(1 - (a.age_years / a.useful_life_years), 0.1, 1);
      var v = a.replacement_cost * dep * a.condition_factor;
      return { base: v, trace: { rule: "model:machinery", inputs: { replacement_cost: a.replacement_cost, age_years: a.age_years, useful_life_years: a.useful_life_years, condition_factor: a.condition_factor, straight_line_dep: round2(dep) }, formula: "replacement_cost*max(0.1,1-age/life)*condition", out: round2(v) } };
    },
    vehicle: function (a) {
      var dep = clamp(1 - (a.age_years / a.useful_life_years), 0.1, 1);
      var v = a.replacement_cost * dep * a.condition_factor;
      return { base: v, trace: { rule: "model:vehicle", inputs: { replacement_cost: a.replacement_cost, age_years: a.age_years, useful_life_years: a.useful_life_years, condition_factor: a.condition_factor }, formula: "replacement_cost*max(0.1,1-age/life)*condition", out: round2(v) } };
    },
    contractual_right: function (a) {
      // present value of the receivable, net of default probability
      var pv = a.principal / Math.pow(1 + a.discount_rate, a.term_years);
      var v = pv * (1 - a.default_prob);
      return { base: v, trace: { rule: "model:contractual_right", inputs: { principal: a.principal, discount_rate: a.discount_rate, term_years: a.term_years, default_prob: a.default_prob, pv: round2(pv) }, formula: "principal/(1+r)^t * (1-default_prob)", out: round2(v) } };
    },
    company: function (a) {
      var v = a.ebitda * a.multiple;
      return { base: v, trace: { rule: "model:company", inputs: { ebitda: a.ebitda, multiple: a.multiple }, formula: "ebitda*multiple", out: round2(v) } };
    },
    art: function (a) {
      // median of comparable sales; the wide range comes from spread/volatility later
      var comps = (a.comparable_sales || []).slice().sort(function (x, y) { return x - y; });
      if (!comps.length) throw new Error("art model requires comparable_sales");
      var mid = comps.length % 2 ? comps[(comps.length - 1) / 2] : (comps[comps.length / 2 - 1] + comps[comps.length / 2]) / 2;
      return { base: mid, trace: { rule: "model:art", inputs: { comparable_sales: comps }, formula: "median(comparable_sales)", out: round2(mid) } };
    },
    digital_asset: function (a) {
      var v = a.units * a.market_reference_price;
      return { base: v, trace: { rule: "model:digital_asset", inputs: { units: a.units, market_reference_price: a.market_reference_price }, formula: "units*market_reference_price", out: round2(v) } };
    }
  };

  // ---- Stage 4/5: range, recoverability, haircuts -----------------------
  function value(asset, opts) {
    opts = opts || {};
    var c = classify(asset);
    var params = c.params;
    var eq = evidenceQuality(asset, params);
    var model = MODELS[asset.category];
    if (!model) throw new Error("no model for category: " + asset.category);
    var m = model(asset);
    var base = m.base;

    var trace = c.trace.concat(eq.trace, [m.trace]);
    var risk_factors = [];

    // range widens as evidence quality falls and with category volatility
    var evidenceGap = 1 - eq.quality;
    var spread = params.baseSpread + evidenceGap * params.baseSpread * params.volatility * 3;
    spread = clamp(spread, params.baseSpread, 0.9);
    var low = base * (1 - spread), high = base * (1 + spread);
    trace.push({ rule: "range", inputs: { baseSpread: params.baseSpread, evidenceGap: round2(evidenceGap), volatility: params.volatility }, formula: "spread=baseSpread+evidenceGap*baseSpread*vol*3 (cap .9)", out: { spread: round2(spread), low: round2(low), high: round2(high) } });

    // declared risk flags -> haircut penalties (each traceable)
    var haircut = 0;
    (asset.risk_flags || []).forEach(function (f) {
      var pen = { title_defect: 0.15, single_comparable: 0.08, concentration: 0.05, jurisdiction_risk: 0.07, unverified_custody: 0.10, expired_attestation: 0.06 }[f] || 0.05;
      haircut += pen; risk_factors.push(f + " (-" + Math.round(pen * 100) + "%)");
      trace.push({ rule: "risk_flag", inputs: { flag: f }, formula: "haircut += penalty", out: pen });
    });
    // evidence gap itself is a haircut on recoverable value
    var evidenceHaircut = evidenceGap * 0.25;
    haircut = clamp(haircut + evidenceHaircut, 0, 0.9);
    if (eq.missing_evidence.length) risk_factors.push("missing evidence: " + eq.missing_evidence.join(", "));
    trace.push({ rule: "haircut", inputs: { risk_haircut: round2(haircut - evidenceHaircut), evidence_haircut: round2(evidenceHaircut) }, formula: "sum(risk penalties)+evidenceGap*0.25 (cap .9)", out: round2(haircut) });

    // recoverable value: orderly-forced-sale recovery, then haircut, then sale costs
    var recovery = base * params.recovery;
    var afterHaircut = recovery * (1 - haircut);
    var liqCost = afterHaircut * params.liqCostPct;
    var net = afterHaircut - liqCost;
    trace.push({ rule: "recoverable", inputs: { recovery_rate: params.recovery, haircut: round2(haircut), liqCostPct: params.liqCostPct }, formula: "base*recovery*(1-haircut) - liqCost", out: { recovery: round2(recovery), net: round2(net), liqCost: round2(liqCost) } });

    // ---- Stage 6: confidence ----
    var modelSpreadPenalty = clamp(spread, 0, 0.9);
    var confidence = clamp(eq.quality * (1 - modelSpreadPenalty) * (1 - clamp(haircut, 0, 0.9)), 0, 1);
    trace.push({ rule: "confidence", inputs: { evidence_quality: eq.quality, spread: round2(spread), haircut: round2(haircut) }, formula: "quality*(1-spread)*(1-haircut)", out: round2(confidence) });

    // ---- Stage 7: financing (suggested LTV) ----
    // never exceed category ceiling; scale by confidence and net recoverability
    var netRecoverabilityRatio = base > 0 ? net / base : 0;
    var suggestedLtv = clamp(params.ltvCeiling * confidence * netRecoverabilityRatio, 0, params.ltvCeiling);
    var maxLoan = base * suggestedLtv;
    trace.push({ rule: "financing", inputs: { ltvCeiling: params.ltvCeiling, confidence: round2(confidence), net_recoverability: round2(netRecoverabilityRatio) }, formula: "min(ceiling, ceiling*confidence*net/base)", out: { suggested_LTV: round2(suggestedLtv), max_loan: round2(maxLoan) } });

    return {
      category: asset.category,
      market_value_low: round2(low),
      market_value_base: round2(base),
      market_value_high: round2(high),
      recoverable_value: round2(net),
      estimated_liquidation_cost: round2(liqCost),
      confidence: round2(confidence),
      suggested_LTV: round2(suggestedLtv),
      suggested_max_loan: round2(maxLoan),
      missing_evidence: eq.missing_evidence,
      risk_factors: risk_factors,
      disclaimer: "Deterministic estimate from declared inputs. NOT an appraisal, NOT investment advice. A token is not enforceable physical collateral.",
      trace: opts.trace === false ? undefined : trace
    };
  }

  var API = { CATS: CATS, classify: classify, evidenceQuality: evidenceQuality, MODELS: MODELS, value: value };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.SOSTAssetIntelligence = API;
})(typeof window !== "undefined" ? window : this);

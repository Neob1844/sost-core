/* Tests for the Asset Intelligence engine. Deterministic; asserts traceability. */
var AI = require("./asset-intelligence.js");
var pass = 0, fail = 0;
function ok(name, cond) { if (cond) { pass++; } else { fail++; console.log("  FAIL:", name); } }
function approx(a, b, eps) { return Math.abs(a - b) <= (eps || 0.5); }

// 1. precious metal: 1000 g, 0.999 purity, 60/g -> 59940 base
var pm = AI.value({ category: "precious_metal", weight_g: 1000, purity: 0.999, spot_per_g: 60,
  evidence: { assay: true, weight: true, spot_reference: true } });
ok("pm base", approx(pm.market_value_base, 59940));
ok("pm full evidence -> high confidence", pm.confidence > 0.8);
ok("pm no missing evidence", pm.missing_evidence.length === 0);
ok("pm liquid -> LTV near ceiling", pm.suggested_LTV > 0.7 && pm.suggested_LTV <= 0.85);
ok("pm low<base<high", pm.market_value_low < pm.market_value_base && pm.market_value_base < pm.market_value_high);

// 2. missing evidence widens range + lowers confidence + adds to missing_evidence
var pmWeak = AI.value({ category: "precious_metal", weight_g: 1000, purity: 0.999, spot_per_g: 60, evidence: {} });
ok("weak evidence lists gaps", pmWeak.missing_evidence.length === 3);
ok("weak evidence -> lower confidence", pmWeak.confidence < pm.confidence);
ok("weak evidence -> wider range", (pmWeak.market_value_high - pmWeak.market_value_low) > (pm.market_value_high - pm.market_value_low));
ok("weak evidence -> lower LTV", pmWeak.suggested_LTV < pm.suggested_LTV);
ok("base unchanged by evidence (uncertainty is in range/conf, not base)", pmWeak.market_value_base === pm.market_value_base);

// 3. machinery depreciation
var mach = AI.value({ category: "machinery", replacement_cost: 100000, age_years: 5, useful_life_years: 10, condition_factor: 0.9,
  evidence: { invoice: true, serial: true, inspection: true } });
ok("machinery dep base = 100000*0.5*0.9 = 45000", approx(mach.market_value_base, 45000));
ok("machinery recovery lower than precious metal", mach.recoverable_value / mach.market_value_base < pm.recoverable_value / pm.market_value_base);

// 4. contractual right PV + default
var debt = AI.value({ category: "contractual_right", principal: 100000, discount_rate: 0.1, term_years: 2, default_prob: 0.2,
  evidence: { contract: true, payment_history: true, counterparty_rating: true } });
// pv = 100000/1.21 = 82644.6; *0.8 = 66115.7
ok("debt PV*(1-default)", approx(debt.market_value_base, 66115.7, 5));

// 5. risk flags apply traceable haircuts
var re = AI.value({ category: "real_estate", area_m2: 100, price_per_m2: 3000,
  evidence: { title: true, appraisal: true, comparables: true }, risk_flags: ["title_defect"] });
var reClean = AI.value({ category: "real_estate", area_m2: 100, price_per_m2: 3000,
  evidence: { title: true, appraisal: true, comparables: true } });
ok("title_defect lowers recoverable", re.recoverable_value < reClean.recoverable_value);
ok("risk factor reported", re.risk_factors.some(function (r) { return /title_defect/.test(r); }));

// 6. every output number is traceable
var traced = AI.value({ category: "precious_metal", weight_g: 10, purity: 1, spot_per_g: 60,
  evidence: { assay: true, weight: true, spot_reference: true } });
var rules = traced.trace.map(function (t) { return t.rule; });
["classify", "evidence_quality", "range", "haircut", "recoverable", "confidence", "financing"].forEach(function (r) {
  ok("trace has " + r, rules.indexOf(r) >= 0 || rules.some(function (x) { return x.indexOf(r) === 0; }));
});
ok("model trace present", rules.some(function (r) { return r.indexOf("model:") === 0; }));

// 7. LTV never exceeds category ceiling even at max confidence
ok("LTV <= ceiling", pm.suggested_LTV <= AI.CATS.precious_metal.ltvCeiling + 1e-9);

// 8. company + art models
var co = AI.value({ category: "company", ebitda: 200000, multiple: 5,
  evidence: { audited_financials: true, cap_table: true, ebitda: true } });
ok("company ebitda*multiple", approx(co.market_value_base, 1000000));
ok("company illiquid -> low LTV ceiling respected", co.suggested_LTV <= 0.35 + 1e-9);
var art = AI.value({ category: "art", comparable_sales: [80000, 120000, 100000],
  evidence: { provenance: true, authentication: true, appraisal: true, comparables: true } });
ok("art median", approx(art.market_value_base, 100000));
ok("art very wide range", (art.market_value_high - art.market_value_low) / art.market_value_base > 0.2);

// 9. unknown category throws
var threw = false; try { AI.value({ category: "unicorn" }); } catch (e) { threw = true; }
ok("unknown category throws", threw);

// 10. disclaimer always present
ok("disclaimer present", /NOT an appraisal/.test(pm.disclaimer));

console.log("ASSET-INTELLIGENCE TESTS: PASS=" + pass + " FAIL=" + fail);
process.exit(fail ? 1 : 0);

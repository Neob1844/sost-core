/* Tests for the SOST gold reference single-source (Bretton Woods derivation).
 * Runs the browser file in a fake root; asserts the constant, the formula, the
 * historical value is inert, and that all consumers computing from this source agree. */
var fs = require("fs");
var pass = 0, fail = 0;
function ok(n, c) { if (c) pass++; else { fail++; console.log("  FAIL:", n); } }
function approx(a, b, eps) { return Math.abs(a - b) <= (eps == null ? 1e-9 : eps); }

// load the browser module into a fake window
var root = {};
globalThis.fetch = function () { return Promise.reject(new Error("no-net")); };
var code = fs.readFileSync(__dirname + "/sost-gold-reference.js", "utf8").replace("(window)", "(globalThis.__root)");
globalThis.__root = root;
eval(code);
var G = root.SOSTGold;

// 1. constant is the Bretton Woods 1/1000-dollar gold content
var expectedMg = (31.1034768 / 35) * 1000 / 1000; // 0.8886707657142857
ok("WEIGHT_MG = 1/1000 dollar gold content", approx(G.WEIGHT_MG, expectedMg));
ok("WEIGHT_MG ~ 0.8886707657", approx(G.WEIGHT_MG, 0.8886707657, 1e-9));
ok("WEIGHT_G = WEIGHT_MG/1000", approx(G.WEIGHT_G, G.WEIGHT_MG / 1000));
ok("WEIGHT_G ~ 0.0008886707657", approx(G.WEIGHT_G, 0.0008886707657, 1e-12));

// 2. derivation constants
ok("BW parity 35 USD/oz", G.BW_USD_PER_TROY_OZ === 35);
ok("troy oz = 31.1034768 g", approx(G.TROY_OZ_G, 31.1034768));
ok("mg per troy oz = 31103.4768", approx(G.MG_PER_TROY_OZ, 31103.4768, 1e-6));
// one Bretton Woods dollar holds 888.6707657 mg of gold; SOST is 1/1000 of that
ok("dollar gold content = 1000 x WEIGHT_MG", approx((G.TROY_OZ_G / 35) * 1000, G.WEIGHT_MG * 1000));

// 3. formula: USD/SOST = gold_USD_per_gram × 0.0008886707657
[0, 50, 137.93, 200, 4290 / 31.1034768].forEach(function (perG) {
  ok("sostFromGram(" + perG.toFixed(3) + ") = perG*WEIGHT_G", approx(G.sostFromGram(perG), perG * G.WEIGHT_G));
});
// illustrative: gold 137.93 USD/g -> ~0.12257 USD/SOST
ok("illustrative 137.93 USD/g -> ~0.1226", approx(G.sostFromGram(137.93), 0.12257, 1e-3));

// 4. oz and gram paths agree (internal consistency of the source)
var oz = 4290;
ok("sostFromOz == sostFromGram(gramFromOz)", approx(G.sostFromOz(oz), G.sostFromGram(G.gramFromOz(oz)), 1e-12));

// 5. historical 1.14 present but INERT (never used by the formula)
ok("HISTORICAL_WEIGHT_MG kept = 1.14", G.HISTORICAL_WEIGHT_MG === 1.14);
ok("formula does NOT use 1.14", !approx(G.sostFromGram(1000), 1000 * (1.14 / 1000)) && approx(G.sostFromGram(1000), 1000 * G.WEIGHT_G));

// 6. label reflects the new reference, not the old
ok("label says 0.8886707657", /0\.8886707657/.test(G.label));
ok("label does NOT say 1.14", !/1\.14/.test(G.label));

// 7. CONSISTENCY across consumers: reference page, Explorer, markets all derive from
//    the SAME source, so for any gold input their SOST reference figures are identical.
function referencePageValue(oz) { return root.SOSTGold.sostFromOz(oz); }           // sost-reference.html path
function explorerValue(oz) { return root.SOSTGold.sostFromGram(root.SOSTGold.gramFromOz(oz)); } // explorer path
function marketsValue(perG) { return root.SOSTGold.sostFromGram(perG); }           // markets path
[3000, 4290, 5000].forEach(function (oz) {
  var perG = oz / G.TROY_OZ_G;
  ok("consumers agree @oz=" + oz, approx(referencePageValue(oz), explorerValue(oz), 1e-12) &&
     approx(referencePageValue(oz), marketsValue(perG), 1e-12));
});

// 8. provider-failure surfaces ok:false (callers must show "unavailable", not a static live quote)
G.load().then(function (st) {
  ok("provider failure -> ok:false", st.ok === false);
  console.log("SOST-GOLD-REFERENCE TESTS: PASS=" + pass + " FAIL=" + fail);
  process.exit(fail ? 1 : 0);
});

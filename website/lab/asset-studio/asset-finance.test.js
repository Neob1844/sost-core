var F = require("./asset-finance.js");
var pass = 0, fail = 0;
function ok(n, c) { if (c) pass++; else { fail++; console.log("  FAIL:", n); } }
function approx(a, b, e) { return Math.abs(a - b) <= (e || 1); }

var collat = { recoverable_value: 40000, suggested_max_loan: 30000 };

// 1. bilateral amortizing, no default: lender gets principal + interest, positive PnL
var b = F.simulateLoan({ principal: 30000, annual_rate: 0.1, term_months: 12, payment_structure: "amortizing",
  structure_type: "bilateral", currency: "SOST", collateral: collat, lenders: [{ id: "L1", amount: 30000 }] });
ok("bilateral ok", b.ok);
ok("no default", !b.defaulted);
ok("lender PnL positive (interest earned)", b.lenders[0].pnl > 0);
ok("conservation holds (no mint)", b.invariants.no_mint);
ok("to_lenders == borrower_paid (no default)", approx(b.total_to_lenders, b.total_borrower_paid));

// 2. multi-lender pool, pro-rata shares
var m = F.simulateLoan({ principal: 30000, annual_rate: 0.12, term_months: 12, payment_structure: "interest_only",
  structure_type: "multi_lender", collateral: collat, lenders: [{ id: "A", amount: 20000 }, { id: "B", amount: 10000 }] });
ok("multi ok", m.ok);
ok("shares pro-rata", approx(m.lenders[0].share, 0.6667, 0.01) && approx(m.lenders[1].share, 0.3333, 0.01));
ok("A earns ~2x B", approx(m.lenders[0].pnl, m.lenders[1].pnl * 2, 5));
ok("multi conservation", m.invariants.no_mint);

// 3. default, collateral covers outstanding -> no loss to lenders
var d1 = F.simulateLoan({ principal: 30000, annual_rate: 0.1, term_months: 12, payment_structure: "interest_only",
  structure_type: "bilateral", collateral: { recoverable_value: 40000, suggested_max_loan: 30000 }, lenders: [{ id: "L1", amount: 30000 }], default_at_month: 6 });
ok("default flagged", d1.defaulted);
ok("collateral covers -> zero loss", d1.total_lender_loss === 0);
ok("default conservation", d1.invariants.no_mint);

// 4. default, collateral SHORT -> lenders take a loss, still no mint
var d2 = F.simulateLoan({ principal: 30000, annual_rate: 0.1, term_months: 12, payment_structure: "interest_only",
  structure_type: "multi_lender", collateral: { recoverable_value: 12000, suggested_max_loan: 30000 },
  lenders: [{ id: "A", amount: 15000 }, { id: "B", amount: 15000 }], default_at_month: 3 });
ok("shortfall -> loss > 0", d2.total_lender_loss > 0);
ok("loss shared equally", approx(d2.lenders[0].loss, d2.lenders[1].loss, 1));
ok("shortfall conservation (no mint even on loss)", d2.invariants.no_mint);
ok("collateral applied capped at outstanding", d2.events.slice(-1)[0].collateral_applied <= d2.events.slice(-1)[0].outstanding + 1);

// 5. over-leverage rejected (principal > suggested_max_loan)
var over = F.simulateLoan({ principal: 50000, annual_rate: 0.1, term_months: 12, structure_type: "bilateral",
  collateral: { recoverable_value: 40000, suggested_max_loan: 30000 }, lenders: [{ id: "L1", amount: 50000 }] });
ok("over-leverage rejected", !over.ok && over.errors.some(function (e) { return /over-leveraged/.test(e); }));

// 6. commitments must equal principal
var mism = F.simulateLoan({ principal: 30000, annual_rate: 0.1, term_months: 12, structure_type: "bilateral",
  collateral: collat, lenders: [{ id: "L1", amount: 25000 }] });
ok("commitment mismatch rejected", !mism.ok);

// 7. bilateral requires exactly one lender
var badBi = F.simulateLoan({ principal: 30000, annual_rate: 0.1, term_months: 12, structure_type: "bilateral",
  collateral: collat, lenders: [{ id: "A", amount: 15000 }, { id: "B", amount: 15000 }] });
ok("bilateral w/ 2 lenders rejected", !badBi.ok);

// 8. "miner" lender is just a label; commitments still conserve, no reward pool touched
var miner = F.simulateLoan({ principal: 30000, annual_rate: 0.08, term_months: 6, payment_structure: "interest_only",
  structure_type: "pool", collateral: collat, lenders: [{ id: "M1", type: "miner", amount: 30000 }] });
ok("miner-labelled lender ok", miner.ok);
ok("engine reports uses_no_rewards", miner.invariants.uses_no_rewards === true && miner.invariants.uses_no_reserves === true);

// 9. EUR currency with SOST settlement label preserved
var eur = F.simulateLoan({ principal: 30000, annual_rate: 0.1, term_months: 12, structure_type: "bilateral",
  currency: "EUR", collateral: collat, lenders: [{ id: "L1", amount: 30000 }] });
ok("currency preserved", eur.currency === "EUR");

// 10. disclaimer present + no-mint invariant on every path
[b, m, d1, d2, miner, eur].forEach(function (res, i) {
  ok("disclaimer " + i, /SIMULATION ONLY/.test(res.disclaimer) && res.invariants.no_mint);
});

console.log("ASSET-FINANCE TESTS: PASS=" + pass + " FAIL=" + fail);
process.exit(fail ? 1 : 0);

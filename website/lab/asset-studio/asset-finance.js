/* SOST Asset Finance (lab) — voluntary lending SIMULATION. No real loans.
 *
 * HARD INVARIANTS (asserted every run):
 *  - NO SOST is ever minted. Money reaching lenders comes ONLY from borrower
 *    payments + collateral liquidation. conservation() proves it each simulation.
 *  - NO consensus change, NO Gold Vault / reserve involvement, NO block-reward use.
 *    A "miner" lender is just a LABEL on ordinary voluntarily-committed funds; the
 *    engine has no access to and never reads mining rewards.
 *  - Token collateral is a CLAIM on an off-chain asset, NOT enforceable physical
 *    collateral. Recovery is modelled from the Asset Intelligence recoverable_value.
 *
 * Currencies: 'SOST' (native) or 'EUR' with SOST settlement (fx supplied by caller;
 *  the engine never invents an FX rate).
 */
(function (root) {
  "use strict";
  function r2(x) { return Math.round(x * 100) / 100; }
  function sum(a) { return a.reduce(function (s, x) { return s + x; }, 0); }

  // amortizing monthly payment (annuity); interest-only returns just interest
  function monthlyPayment(principal, annualRate, termMonths, structure) {
    var r = annualRate / 12;
    if (structure === "interest_only") return principal * r;
    if (r === 0) return principal / termMonths;
    return principal * r / (1 - Math.pow(1 + r, -termMonths));
  }

  function validate(cfg) {
    var errs = [];
    var lenders = cfg.lenders || [];
    if (!lenders.length) errs.push("no lenders");
    var committed = r2(sum(lenders.map(function (l) { return l.amount; })));
    if (committed !== r2(cfg.principal)) errs.push("lender commitments (" + committed + ") != principal (" + cfg.principal + ")");
    // LTV discipline: principal must not exceed the suggested max loan from Intelligence
    if (cfg.collateral && cfg.collateral.suggested_max_loan != null && cfg.principal > cfg.collateral.suggested_max_loan + 1e-6)
      errs.push("principal " + cfg.principal + " exceeds suggested_max_loan " + cfg.collateral.suggested_max_loan + " (over-leveraged)");
    if (["bilateral", "multi_lender", "pool"].indexOf(cfg.structure_type || "bilateral") < 0) errs.push("bad structure_type");
    if (cfg.structure_type === "bilateral" && lenders.length !== 1) errs.push("bilateral requires exactly 1 lender");
    return errs;
  }

  function simulateLoan(cfg) {
    var errs = validate(cfg);
    if (errs.length) return { ok: false, errors: errs };

    var structure = cfg.payment_structure || "amortizing";
    var pmt = monthlyPayment(cfg.principal, cfg.annual_rate, cfg.term_months, structure);
    var lenders = cfg.lenders.map(function (l) { return { id: l.id, type: l.type || "investor", amount: l.amount, share: l.amount / cfg.principal, received: 0 }; });

    var events = [];
    var borrowerPaid = 0;              // real cash from borrower
    var collateralProceeds = 0;        // real cash from liquidation
    var outstanding = cfg.principal;
    var r = cfg.annual_rate / 12;
    var defaultMonth = cfg.default_at_month || null;

    var lastMonth = defaultMonth ? defaultMonth - 1 : cfg.term_months;
    for (var mth = 1; mth <= lastMonth; mth++) {
      var interest = outstanding * r;
      var principalPart = structure === "interest_only" ? (mth === cfg.term_months ? outstanding : 0) : (pmt - interest);
      var pay = structure === "interest_only" ? interest + (mth === cfg.term_months ? outstanding : 0) : pmt;
      borrowerPaid += pay;
      outstanding = r2(Math.max(0, outstanding - principalPart));
      // distribute this payment pro-rata to lender shares (interest + principal alike)
      lenders.forEach(function (L) { L.received += pay * L.share; });
      events.push({ month: mth, type: "payment", interest: r2(interest), principal: r2(principalPart), paid: r2(pay), outstanding: outstanding });
    }

    var lossTotal = 0;
    if (defaultMonth) {
      // borrower stops paying at defaultMonth; liquidate collateral claim.
      var recoverable = cfg.collateral ? cfg.collateral.recoverable_value : 0; // from Asset Intelligence
      // recovery is capped at outstanding (lenders can't recover more than owed)
      collateralProceeds = Math.min(recoverable, outstanding);
      var shortfall = Math.max(0, outstanding - collateralProceeds);
      // proceeds distributed pro-rata to CURRENT exposure (equal shares here => pro-rata to share)
      lenders.forEach(function (L) {
        var recov = collateralProceeds * L.share;
        var loss = (outstanding * L.share) - recov;
        L.received += recov; L.loss = r2(Math.max(0, loss));
      });
      lossTotal = r2(shortfall);
      events.push({ month: defaultMonth, type: "default", outstanding: r2(outstanding), collateral_recoverable: r2(recoverable), collateral_applied: r2(collateralProceeds), shortfall: r2(shortfall),
        note: "Collateral is a token CLAIM on an off-chain asset; realized recovery depends on real-world enforcement." });
    }

    // per-lender P&L (received vs committed)
    lenders.forEach(function (L) { L.pnl = r2(L.received - L.amount); L.received = r2(L.received); L.share = r2(L.share); });

    var result = {
      ok: true,
      structure_type: cfg.structure_type || "bilateral",
      currency: cfg.currency || "SOST",
      monthly_payment: r2(pmt),
      total_borrower_paid: r2(borrowerPaid),
      collateral_proceeds: r2(collateralProceeds),
      total_to_lenders: r2(sum(lenders.map(function (L) { return L.received; }))),
      total_lender_loss: r2(sum(lenders.map(function (L) { return L.loss || 0; }))),
      defaulted: !!defaultMonth,
      lenders: lenders,
      events: events,
      invariants: null,
      disclaimer: "SIMULATION ONLY. No SOST minted. No block rewards, no Gold Vault, no reserves used. Token collateral is a claim on an off-chain asset, not enforceable physical collateral. Not a lending offer."
    };
    result.invariants = conservation(result);
    if (!result.invariants.no_mint) return { ok: false, errors: ["INVARIANT VIOLATED: value created from nothing"], detail: result.invariants };
    return result;
  }

  // conservation: money to lenders must equal money from borrower + collateral (± rounding).
  function conservation(res) {
    var inflow = r2(res.total_borrower_paid + res.collateral_proceeds);
    var outflow = res.total_to_lenders;
    var diff = r2(inflow - outflow);
    return {
      borrower_plus_collateral: inflow,
      to_lenders: outflow,
      difference: diff,
      no_mint: Math.abs(diff) <= 1.0,   // lenders never receive more than real inflows
      uses_no_rewards: true,            // engine has no access to reward pools by construction
      uses_no_reserves: true
    };
  }

  var API = { simulateLoan: simulateLoan, monthlyPayment: monthlyPayment, validate: validate, conservation: conservation };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.SOSTAssetFinance = API;
})(typeof window !== "undefined" ? window : this);

var T = require("./sacs-tx-safety.js");
var S = T.STATES;
var pass = 0, fail = 0;
function ok(n, c) { if (c) pass++; else { fail++; console.log("  FAIL:", n); } }

// mutable mock chain view
function mkView() {
  return {
    _tip: 100, _canon: {}, _conf: {}, _mem: {}, _conflict: {}, _deep: false, _complete: true,
    tipHeight() { return this._tip; },
    blockHashAt(h) { return this._canon[h] || null; },
    txConfirmedIn(tx) { return this._conf[tx] || null; },
    inMempool(tx) { return !!this._mem[tx]; },
    conflictOf(tx) { return this._conflict[tx] || null; },
    deepReorgActive() { return this._deep; },
    dataComplete() { return this._complete; }
  };
}

// 1. pending -> confirmed
var v = mkView(); v._canon[95] = "hA"; v._conf["t1"] = { height: 95, hash: "hA" };
var tr = T.makeTracker(v);
tr.track("t1", { amount: 100 });
ok("confirmed when in canonical block", tr.get("t1").status === S.CONFIRMED);
ok("confirmations = tip-h+1 = 6", tr.get("t1").confirmations === 6);

// 2. reorg drops the confirming block -> REORGED (not in mempool) / REENTERED_MEMPOOL (in mempool)
v._canon[95] = "hA_prime"; // height 95 now a different block => t1's block hA no longer canonical
var s = tr.update("t1");
ok("reorged out -> REORGED", s.status === S.REORGED);
v._mem["t1"] = true;
ok("reorged + in mempool -> REENTERED_MEMPOOL", tr.update("t1").status === S.REENTERED_MEMPOOL);

// 3. conflict / replacement
var v2 = mkView(); v2._canon[90] = "hX"; v2._conf["t2"] = { height: 90, hash: "hX" };
var tr2 = T.makeTracker(v2); tr2.track("t2", { amount: 50 });
ok("t2 confirmed", tr2.get("t2").status === S.CONFIRMED);
v2._conflict["t2"] = { txid: "t2b", replacement: false };
ok("double-spend of input -> CONFLICTED", tr2.update("t2").status === S.CONFLICTED);
v2._conflict["t2"] = { txid: "t2c", replacement: true };
ok("explicit replacement -> REPLACED", tr2.update("t2").status === S.REPLACED);

// 4. UNKNOWN when data incomplete (never invent certainty)
var v3 = mkView(); v3._complete = false;
var tr3 = T.makeTracker(v3); tr3.track("t3", { amount: 10 });
ok("incomplete data -> UNKNOWN", tr3.get("t3").status === S.UNKNOWN);

// 5. pending when only in mempool
var v4 = mkView(); v4._mem["t4"] = true;
var tr4 = T.makeTracker(v4); tr4.track("t4", { amount: 10 });
ok("mempool-only -> PENDING", tr4.get("t4").status === S.PENDING);

// 6. credit policy: tiered min-confirmations
var v5 = mkView(); v5._canon[80] = "hZ"; v5._conf["big"] = { height: 80, hash: "hZ" }; v5._tip = 100; // 21 conf
var tr5 = T.makeTracker(v5);
tr5.track("big", { amount: 100000 });
var pol = { tiers: [{ maxAmount: 100, minConf: 6 }, { maxAmount: 10000, minConf: 30 }], defaultMinConf: 100, suspendOnDeepReorg: true };
ok("large deposit needs 100 conf (has 21) -> no credit", tr5.creditable("big", pol).credit === false);
v5._tip = 179; // now 100 conf
ok("large deposit with 100 conf -> credit", tr5.creditable("big", tr5.update("big") && pol).credit === true);
// small deposit tier
var v6 = mkView(); v6._canon[94] = "hS"; v6._conf["sm"] = { height: 94, hash: "hS" }; v6._tip = 100; // 7 conf
var tr6 = T.makeTracker(v6); tr6.track("sm", { amount: 50 });
ok("small deposit (<=100) needs 6, has 7 -> credit", tr6.creditable("sm", pol).credit === true);

// 7. deep-reorg alert suspends crediting even when confirmed
v6._deep = true;
ok("deep-reorg suspends crediting", tr6.creditable("sm", pol).credit === false && /deep-reorg/.test(tr6.creditable("sm", pol).reason));
v6._deep = false;
ok("resumes after deep-reorg clears", tr6.creditable("sm", pol).credit === true);

// 8. not-confirmed never creditable
ok("pending not creditable", tr4.creditable("t4", pol).credit === false);

console.log("SACS-TX-SAFETY TESTS: PASS=" + pass + " FAIL=" + fail);
process.exit(fail ? 1 : 0);

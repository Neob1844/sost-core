var M = require("./peer-addrman.js");
var pass = 0, fail = 0;
function ok(n, c) { if (c) pass++; else { fail++; console.log("  FAIL:", n); } }

// 1. group extraction (/16)
ok("group /16", M.groupOf("203.0.113.5") === "203.0");
ok("group ipv6-ish", M.groupOf("2001:db8::1").indexOf("2001") === 0);

// 2. per-source share cap: one hostile source cannot flood NEW
var am = M.makeAddrMan({ newCap: 100, maxSharePerSource: 0.10, addrPerInterval: 100000 });
var accepted = 0;
for (var i = 0; i < 500; i++) {
  var r = am.addAddr("10.0." + (i >> 8) + "." + (i & 255), "attacker", i);
  if (r.accepted) accepted++;
}
ok("hostile source capped at 10% of NEW", accepted === 10, accepted);
ok("stats reflect source cap", am.stats().new_by_source.attacker === 10);

// 3. many honest sources fill the rest -> table not monopolized
for (var s = 0; s < 20; s++) for (var j = 0; j < 10; j++) am.addAddr("192." + s + "." + j + ".1", "honest" + s, 1000 + s);
ok("no single source dominates", Object.keys(am.stats().new_by_source).every(function (k) { return am.stats().new_by_source[k] <= am.stats().source_cap; }));

// 4. ADDR rate-limit per source per interval
var am2 = M.makeAddrMan({ newCap: 100000, addrPerInterval: 5 });
var acc2 = 0;
for (var t = 0; t < 20; t++) if (am2.addAddr("172.16." + t + ".1", "spammer", t).accepted) acc2++;
ok("ADDR rate-limited to 5/interval", acc2 === 5, acc2);
am2.resetInterval();
ok("interval reset allows more", am2.addAddr("172.16.99.1", "spammer", 99).accepted === true);

// 5. tried preferred + only-connected become tried
var am3 = M.makeAddrMan({});
am3.addAddr("8.8.8.8", "dns", 1);
am3.addAddr("9.9.9.9", "dns", 1);
ok("in new not tried", am3.stats().tried === 0 && am3.stats().new === 2);
am3.markGood("8.8.8.8", 2);
ok("markGood promotes to tried", am3.stats().tried === 1);
ok("promoted removed from new", am3.stats().new === 1);

// 6. outbound selection is group-diverse (no two from same /16 in first pass)
var am4 = M.makeAddrMan({});
["1.1.0.1", "1.1.0.2", "1.1.0.3", "2.2.0.1", "3.3.0.1"].forEach(function (a, i) { am4.addAddr(a, "s" + i, i); am4.markGood(a, i); });
var sel = am4.selectOutbound(3);
var groups = sel.map(M.groupOf);
ok("outbound group-diverse", new Set(groups).size === groups.length, JSON.stringify(sel));
ok("prefers distinct groups over same-subnet flood", groups.indexOf("1.1") >= 0 && groups.filter(function (g) { return g === "1.1"; }).length === 1);

// 7. eclipse resistance: attacker owns one /16, cannot win all 3 outbound
var am5 = M.makeAddrMan({});
for (var e = 0; e < 50; e++) { var a = "66.66." + e + ".1"; am5.addAddr(a, "eclipser", e); am5.markGood(a, e); }
["77.77.1.1", "88.88.1.1"].forEach(function (a, i) { am5.addAddr(a, "good" + i, 100 + i); am5.markGood(a, 100 + i); });
var sel5 = am5.selectOutbound(3);
var attackerCount = sel5.map(M.groupOf).filter(function (g) { return g === "66.66"; }).length;
ok("attacker /16 gets at most 1 of 3 outbound (first pass)", attackerCount <= 1, JSON.stringify(sel5));

// 8. repeated failure demotes a tried peer (no permanent trust)
var am6 = M.makeAddrMan({ demoteAfter: 3 });
am6.addAddr("5.5.5.5", "dns", 1); am6.markGood("5.5.5.5", 2);
ok("is tried", am6.stats().tried === 1);
am6.markFail("5.5.5.5", 3); am6.markFail("5.5.5.5", 4); am6.markFail("5.5.5.5", 5);
ok("demoted after 3 failures", am6.stats().tried === 0);

// 9. bounded eviction never drops below/over capacity
var am7 = M.makeAddrMan({ newCap: 10, maxSharePerSource: 1.0, addrPerInterval: 100000 });
for (var q = 0; q < 100; q++) am7.addAddr("100.0." + (q >> 8) + "." + (q & 255), "src", q);
ok("NEW capacity bounded", am7.stats().new <= 10);

// 10. known address not double-counted
var am8 = M.makeAddrMan({});
am8.addAddr("4.4.4.4", "a", 1);
ok("dup rejected", am8.addAddr("4.4.4.4", "b", 2).reason === "known");

console.log("PEER-ADDRMAN TESTS: PASS=" + pass + " FAIL=" + fail);
process.exit(fail ? 1 : 0);

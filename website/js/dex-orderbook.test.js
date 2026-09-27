var OB = require("./dex-orderbook.js");
var pass = 0, fail = 0;
function ok(n, c) { if (c) pass++; else { fail++; console.log("  FAIL:", n); } }

var T = 1000000;
function clock() { return T; }
// permissive verifier for happy-path tests; sig must be present and truthy
function verifyOk(o) { return !!o.signature; }

function ord(maker, side, amount, price, nonce, sig) {
  return { maker: maker, pair: "SOST/USDC", side: side, amount: amount, limit_price: price,
           nonce: nonce, expiry: T + 100000, network: "sost", signature: sig || "sig" };
}

// 1. FAIL-CLOSED: no verifier -> everything rejected
var fc = OB.makeBook({ now: clock });
ok("no verifier rejects submit", fc.submit(ord("a", "buy", 10, 100, "n1")).reason === "no_verifier_fail_closed");
ok("no verifier rejects cancel", fc.cancel({ maker: "a", order_id: "o1" }).reason === "no_verifier_fail_closed");

// 2. bad signature rejected
var b = OB.makeBook({ verify: verifyOk, now: clock });
ok("missing sig rejected", b.submit({ maker: "a", pair: "SOST/USDC", side: "buy", amount: 10, limit_price: 100, nonce: "x", expiry: T + 100, network: "sost" }).reason === "bad_signature");

// 3. resting limit + crossing match with partial fill
var b3 = OB.makeBook({ verify: verifyOk, now: clock });
var r1 = b3.submit(ord("maker", "sell", 10, 100, "s1"));   // ask 10 @100
ok("sell rests", r1.ok && r1.rested && r1.filled === 0);
var r2 = b3.submit(ord("taker", "buy", 4, 100, "b1"));     // buy 4 @100 -> fills 4
ok("buy fills 4", r2.ok && r2.filled === 4 && r2.remaining === 0);
ok("resting ask now has 6 left", b3.get(r1.order_id).remaining === 6);
var r3 = b3.submit(ord("taker2", "buy", 10, 100, "b2"));   // buy 10 -> fills remaining 6, rests 4
ok("buy fills 6 then rests 4", r3.filled === 6 && r3.remaining === 4 && r3.rested);

// 4. price-time priority + no cross => no fill
var b4 = OB.makeBook({ verify: verifyOk, now: clock });
b4.submit(ord("m1", "sell", 5, 105, "s1"));
b4.submit(ord("m2", "sell", 5, 101, "s2"));  // best ask 101
var buyLow = b4.submit(ord("t", "buy", 5, 100, "b1")); // 100 < 101 -> no cross
ok("non-crossing buy rests, no fill", buyLow.filled === 0 && buyLow.rested);
var buyCross = b4.submit(ord("t2", "buy", 5, 101, "b2"));
ok("crossing buy hits best (101) first", buyCross.filled === 5 && buyCross.fills[0].price === 101);

// 5. market order fills best available, unfilled remainder NOT rested
var b5 = OB.makeBook({ verify: verifyOk, now: clock });
b5.submit(ord("m", "sell", 3, 100, "s1"));
var mkt = b5.submit(ord("t", "buy", 10, null, "b1")); // market buy 10, only 3 available
ok("market fills 3", mkt.filled === 3);
ok("market remainder cancelled not rested", mkt.remaining === 7 && !mkt.rested && mkt.status === "partial_cancelled");

// 6. replay (reused nonce) rejected
var b6 = OB.makeBook({ verify: verifyOk, now: clock });
b6.submit(ord("a", "buy", 1, 100, "dup"));
ok("reused nonce rejected", b6.submit(ord("a", "buy", 1, 100, "dup")).reason === "replay");

// 7. replay AFTER RESTART rejected (persisted nonce ledger)
var saved = null;
var store = { load: function () { return saved; }, save: function (s) { saved = JSON.parse(JSON.stringify(s)); } };
var pre = OB.makeBook({ verify: verifyOk, now: clock, store: store });
pre.submit(ord("a", "buy", 1, 100, "persist-nonce"));
ok("store persisted", saved && saved.seenNonce["a:persist-nonce"]);
var post = OB.makeBook({ verify: verifyOk, now: clock, store: store }); // "restart"
ok("replay after restart rejected", post.submit(ord("a", "buy", 1, 100, "persist-nonce")).reason === "replay");
ok("durable() reports durable", post.durable().durable === true);

// 8. concurrent double-accept / double-fill guard: stale snapshot cannot overfill
var b8 = OB.makeBook({ verify: verifyOk, now: clock });
var rest = b8.submit(ord("m", "sell", 5, 100, "s1"));
var restingOrder = b8.get(rest.order_id);
var before = restingOrder.remaining;
// first taker fills all 5
var t1 = b8.submit(ord("t1", "buy", 5, 100, "b1"));
ok("first taker fills all 5", t1.filled === 5);
ok("resting fully filled", b8.get(rest.order_id).remaining === 0);
// second taker arrives with the same intent against the (now empty) resting order
var t2 = b8.submit(ord("t2", "buy", 5, 100, "b2"));
ok("second taker cannot fill the exhausted order", t2.filled === 0 && before === 5);

// 9. signed cancel: only owner, only cancellable states
var b9 = OB.makeBook({ verify: verifyOk, now: clock });
var c = b9.submit(ord("owner", "sell", 5, 100, "s1"));
ok("wrong owner cannot cancel", b9.cancel({ maker: "attacker", order_id: c.order_id, signature: "sig" }).reason === "not_owner");
ok("owner cancels", b9.cancel({ maker: "owner", order_id: c.order_id, signature: "sig" }).ok);
ok("cancelled leaves book", b9.depth("SOST/USDC").asks.length === 0);
ok("cannot cancel twice", b9.cancel({ maker: "owner", order_id: c.order_id, signature: "sig" }).reason === "not_cancellable");

// 10. expiry sweep
var tt = T;
var b10 = OB.makeBook({ verify: verifyOk, now: function () { return tt; } });
b10.submit({ maker: "m", pair: "SOST/USDC", side: "sell", amount: 5, limit_price: 100, nonce: "s1", expiry: T + 50, network: "sost", signature: "sig" });
ok("order resting before expiry", b10.depth("SOST/USDC").asks.length === 1);
tt = T + 100; // advance past expiry
ok("sweep removes expired", b10.sweepExpired() === 1 && b10.depth("SOST/USDC").asks.length === 0);

// 11. history + depth reflect fills
var b11 = OB.makeBook({ verify: verifyOk, now: clock });
b11.submit(ord("m", "sell", 5, 100, "s1"));
b11.submit(ord("t", "buy", 2, 100, "b1"));
ok("history records the trade", b11.history("SOST/USDC").length === 1 && b11.history("SOST/USDC")[0].amount === 2);
ok("depth shows remaining 3", b11.depth("SOST/USDC").asks[0].remaining === 3);

console.log("DEX-ORDERBOOK TESTS: PASS=" + pass + " FAIL=" + fail);
process.exit(fail ? 1 : 0);

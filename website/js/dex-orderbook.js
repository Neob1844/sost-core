/* SOST DEX — signed-order matching book (lab, HARDENED, FAIL-CLOSED).
 *
 * Limit + market orders with price-time priority, partial fills, signed cancels, expiry
 * sweep, injectable durable store for restart recovery. Holds NO custody and moves NO funds
 * — a matched trade is an intent that must still be settled on-chain / via atomic swap.
 *
 * FAIL-CLOSED: with no signature verifier configured, EVERY order and cancel is rejected.
 * Replay (reused nonce) and double-accept are blocked, and the nonce ledger is persisted so a
 * replay AFTER RESTART is still rejected. Fills are applied atomically against the resting
 * order's remaining amount, so a stale snapshot can never overfill (concurrent double-accept).
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = m;
  if (root) root.SOSTOrderBook = m;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function makeBook(opts) {
    opts = opts || {};
    var verify = (typeof opts.verify === "function") ? opts.verify : null; // FAIL-CLOSED
    var store = opts.store || null;
    var now = opts.now || function () { return Date.now(); };

    // state
    var bids = [];   // resting buy limit orders (highest price first)
    var asks = [];   // resting sell limit orders (lowest price first)
    var seenNonce = Object.create(null); // maker+nonce -> true (replay guard, persisted)
    var byId = Object.create(null);      // orderId -> resting order
    var trades = [];                     // fill history
    var seq = 0;

    if (store && store.load) {
      var s = store.load() || {};
      bids = s.bids || []; asks = s.asks || []; seenNonce = s.seenNonce || Object.create(null);
      trades = s.trades || []; seq = s.seq || 0;
      (bids.concat(asks)).forEach(function (o) { byId[o.id] = o; });
    }
    function persist() { if (store && store.save) store.save({ bids: bids, asks: asks, seenNonce: seenNonce, trades: trades, seq: seq }); }

    function nonceKey(o) { return String(o.maker) + ":" + String(o.nonce); }
    function reject(reason) { return { ok: false, reason: reason }; }

    function validate(o) {
      if (!verify) return reject("no_verifier_fail_closed");
      if (!o || !o.maker || !o.pair || !o.side || o.amount == null || o.nonce == null || o.expiry == null || !o.network) return reject("malformed");
      if (o.side !== "buy" && o.side !== "sell") return reject("bad_side");
      if (!(o.amount > 0)) return reject("bad_amount");
      if (o.limit_price != null && !(o.limit_price > 0)) return reject("bad_price");
      if (o.expiry <= now()) return reject("expired");
      if (seenNonce[nonceKey(o)]) return reject("replay");     // also blocks replay-after-restart
      if (!verify(o)) return reject("bad_signature");
      return { ok: true };
    }

    function crosses(order, resting) {
      // order buys: fills against asks priced <= order.limit_price (or any if market)
      if (order.side === "buy") return order.limit_price == null || resting.price <= order.limit_price;
      return order.limit_price == null || resting.price >= order.limit_price; // sell fills bids >= limit
    }

    function bookFor(side) { return side === "buy" ? asks : bids; } // buy matches asks
    function sortBooks() {
      asks.sort(function (a, b) { return a.price - b.price || a.ts - b.ts; });   // best ask = lowest
      bids.sort(function (a, b) { return b.price - a.price || a.ts - b.ts; });   // best bid = highest
    }

    // Atomically fill `take` units against resting order `r`. Returns filled amount.
    function fillResting(r, take) {
      var avail = r.remaining;               // snapshot-safe: read-modify-write in one synchronous step
      if (avail <= 0) return 0;
      var filled = Math.min(avail, take);
      r.remaining = avail - filled;          // atomic decrement
      if (r.remaining <= 0) { r.status = "filled"; removeResting(r); }
      return filled;
    }

    function removeResting(r) {
      var arr = r.side === "buy" ? bids : asks;
      var i = arr.indexOf(r); if (i >= 0) arr.splice(i, 1);
      // keep in byId as filled/cancelled record
    }

    function submit(order) {
      var v = validate(order); if (!v.ok) return v;
      seenNonce[nonceKey(order)] = true;     // record BEFORE matching so a mid-flight resubmit can't replay
      var id = "o" + (++seq);
      var o = { id: id, maker: order.maker, pair: order.pair, side: order.side,
                amount: order.amount, remaining: order.amount, limit_price: order.limit_price != null ? order.limit_price : null,
                nonce: order.nonce, expiry: order.expiry, network: order.network, ts: now(), status: "open" };
      byId[id] = o;

      var fills = [];
      var opp = bookFor(o.side).filter(function (r) { return r.pair === o.pair && r.remaining > 0 && r.expiry > now(); });
      // price-time priority: opposite book is already sorted best-first
      for (var i = 0; i < opp.length && o.remaining > 0; i++) {
        var r = opp[i];
        if (!crosses(o, r)) break;           // sorted: once it doesn't cross, none after will
        var take = fillResting(r, o.remaining);
        if (take > 0) {
          o.remaining -= take;
          var price = r.price;               // resting order sets the price (maker price)
          var trade = { buy_id: o.side === "buy" ? o.id : r.id, sell_id: o.side === "sell" ? o.id : r.id,
                        price: price, amount: take, ts: now() };
          trades.push(trade); fills.push(trade);
        }
      }

      var rested = false;
      if (o.remaining > 0) {
        if (o.limit_price == null) { o.status = "partial_cancelled"; } // market remainder is NOT rested
        else { o.status = o.remaining < o.amount ? "partially_filled_resting" : "open"; o.price = o.limit_price; (o.side === "buy" ? bids : asks).push(o); rested = true; }
      } else { o.status = "filled"; }
      sortBooks(); persist();
      return { ok: true, order_id: id, filled: o.amount - o.remaining, remaining: o.remaining, status: o.status, rested: rested, fills: fills };
    }

    function cancel(cancelMsg) {
      // cancelMsg: {maker, order_id, nonce, expiry, signature}
      if (!verify) return reject("no_verifier_fail_closed");
      if (!cancelMsg || !cancelMsg.order_id || !cancelMsg.maker) return reject("malformed");
      var o = byId[cancelMsg.order_id];
      if (!o) return reject("unknown_order");
      if (o.maker !== cancelMsg.maker) return reject("not_owner");
      if (!verify(cancelMsg)) return reject("bad_signature");
      if (o.status === "filled" || o.status === "cancelled") return reject("not_cancellable");
      removeResting(o); o.status = "cancelled"; sortBooks(); persist();
      return { ok: true, order_id: o.id, cancelled_remaining: o.remaining };
    }

    function sweepExpired() {
      var t = now(), removed = 0;
      [bids, asks].forEach(function (arr) {
        for (var i = arr.length - 1; i >= 0; i--) if (arr[i].expiry <= t) { arr[i].status = "expired"; arr.splice(i, 1); removed++; }
      });
      if (removed) persist();
      return removed;
    }

    function depth(pair) {
      return { bids: bids.filter(function (o) { return o.pair === pair; }).map(snap),
               asks: asks.filter(function (o) { return o.pair === pair; }).map(snap) };
    }
    function snap(o) { return { id: o.id, price: o.price, remaining: o.remaining, side: o.side, maker: o.maker }; }
    function history(pair) { return pair ? trades.filter(function (t) { return byId[t.buy_id] && byId[t.buy_id].pair === pair; }) : trades.slice(); }
    function get(id) { return byId[id] || null; }
    function durable() { return { durable: !!(store && store.load && store.save), note: store ? "restart recovery via injected store" : "in-memory lab prototype only" }; }

    return { submit: submit, cancel: cancel, sweepExpired: sweepExpired, depth: depth, history: history, get: get, durable: durable };
  }

  return { makeBook: makeBook };
});

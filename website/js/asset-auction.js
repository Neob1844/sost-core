/*
 * SOST Asset Auction — Option 2 engine (FUTURE / LIVE DEMO / LAB VERIFIED).
 * ---------------------------------------------------------------------------
 * Highest valid signed bid wins (ties -> earliest valid bid; NO chance). An
 * asset (Asset Passport) is offered; bidders post domain-separated signed bids
 * backed by a refundable escrow (a REFERENCE value converted to a SOST quote,
 * never custodied fiat/USDC). Losers' escrows are refundable; the winner's may
 * apply to settlement. Real funds are DISABLED — engine + demo + tests only.
 * Application layer: no consensus / node / STRATO / DTD change.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTAssetAuction = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var DOMAIN = 'SOST_ASSET_AUCTION_V1';
  var STATES = ['DRAFT', 'READY', 'OPEN', 'CLOSING', 'CLOSED', 'RESERVE_NOT_MET', 'WINNER_SELECTED',
    'SETTLEMENT_PENDING', 'SETTLED', 'FAILED', 'CANCELLED', 'REFUNDING', 'REFUNDED', 'COMPLETE'];
  function assert(c, m) { if (!c) throw new Error(m); }

  async function sha256Hex(s) {
    if (typeof s !== 'string') s = JSON.stringify(s);
    var bytes = (typeof TextEncoder !== 'undefined') ? new TextEncoder().encode(s) : Buffer.from(s, 'utf8');
    if (typeof crypto !== 'undefined' && crypto.subtle) {
      var buf = await crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
    }
    return require('crypto').createHash('sha256').update(Buffer.from(bytes)).digest('hex');
  }
  function canon(o) {
    if (o === null || typeof o !== 'object') { if (typeof o === 'number' && !Number.isInteger(o)) throw new Error('non-integers as strings'); return JSON.stringify(o); }
    if (Array.isArray(o)) return '[' + o.map(canon).join(',') + ']';
    return '{' + Object.keys(o).sort().map(function (k) { return JSON.stringify(k) + ':' + canon(o[k]); }).join(',') + '}';
  }

  // amounts are integer minor units (e.g. cents) as strings; reference value only.
  function newAuction(o) {
    assert(o.passportId, 'passportId required (register/verify the asset first)');
    assert(o.seller, 'seller required');
    var starting = BigInt(o.startingPrice || '0');
    var reserve = o.reservePrice != null ? BigInt(o.reservePrice) : null; // null => NO RESERVE
    assert(starting >= 0n, 'startingPrice invalid');
    if (reserve != null) assert(reserve >= starting, 'reserve must be >= starting');
    return {
      auctionId: o.auctionId || null, passportId: o.passportId, seller: o.seller,
      currency: o.currency || 'EUR', network: o.network || 'devnet',
      startingPrice: starting.toString(), reservePrice: reserve != null ? reserve.toString() : null,
      minimumIncrement: (BigInt(o.minimumIncrement || '1')).toString(),
      openingTime: o.openingTime | 0, closingTime: o.closingTime | 0,
      antiSnipeSecs: o.antiSnipeSecs | 0, antiSnipeMaxExtends: o.antiSnipeMaxExtends != null ? (o.antiSnipeMaxExtends | 0) : 10, extends: 0,
      escrowRequired: o.escrowRequired !== false, escrowReferenceAmount: String(o.escrowReferenceAmount || '0'),
      settlementDeadline: o.settlementDeadline | 0,
      state: 'DRAFT', bids: [], nonces: {}, escrows: {}, highest: null, winner: null,
      settlement: null, events: [{ e: 'AUCTION_CREATED', t: o.openingTime | 0 }]
    };
  }

  function log(a, e, t) { a.events.push({ e: e, t: t | 0 }); }
  function ready(a) { assert(a.state === 'DRAFT', 'not draft'); a.state = 'READY'; return a; }
  function cancelBeforeOpen(a) { assert(a.state === 'DRAFT' || a.state === 'READY', 'cannot cancel after open'); a.state = 'CANCELLED'; log(a, 'CANCELLED'); return a; }
  function open(a, now) {
    assert(a.state === 'DRAFT' || a.state === 'READY', 'not openable');
    assert((now | 0) >= a.openingTime, 'before opening time');
    a.state = 'OPEN'; log(a, 'OPENED', now); return a;
  }

  // canonical bid the bidder signs. `signature` is opaque (real ECDSA = wallet side).
  function canonicalBid(b) {
    return { domain: DOMAIN, auctionId: b.auctionId, network: b.network, bidder: b.bidder,
      amount: String(b.amount), currency: b.currency, nonce: String(b.nonce), expiry: b.expiry | 0 };
  }
  async function bidDigest(b) { return sha256Hex(canon(canonicalBid(b))); }

  // register a bidder's refundable escrow (reference value -> SOST quote recorded; no custody here).
  function lockEscrow(a, bidder, quote) {
    assert(a.escrowRequired, 'no escrow required');
    a.escrows[bidder] = { status: 'ESCROW_LOCKED', reference: a.escrowReferenceAmount, currency: a.currency,
      quote_sost: quote && quote.sost != null ? String(quote.sost) : null,
      quote_price: quote && quote.price != null ? String(quote.price) : null,
      quote_source: quote && quote.source || null, quote_ts: quote && quote.ts != null ? (quote.ts | 0) : null };
    return a.escrows[bidder];
  }

  async function placeBid(a, b, now, opts) {
    opts = opts || {};
    assert(a.state === 'OPEN', 'auction not open');
    assert((now | 0) < a.closingTime, 'auction closing time passed');
    assert(b.network === a.network, 'network mismatch');
    assert(b.auctionId === a.auctionId, 'auctionId mismatch');
    assert(b.signature && String(b.signature).length >= 8, 'missing signature');
    assert(!(b.expiry && (now | 0) > (b.expiry | 0)), 'bid expired');
    var key = b.bidder + '|' + String(b.nonce);
    assert(!a.nonces[key], 'nonce reuse / duplicate bid');
    if (a.escrowRequired) assert(a.escrows[b.bidder] && a.escrows[b.bidder].status === 'ESCROW_LOCKED', 'escrow not locked (bidder not eligible)');
    var amt = BigInt(b.amount);
    var floor = a.highest ? (BigInt(a.highest.amount) + BigInt(a.minimumIncrement)) : BigInt(a.startingPrice);
    assert(amt >= floor, 'amount below minimum (' + floor.toString() + ')');
    if (opts.digest != null) { var d = await bidDigest(b); assert(d === opts.digest, 'bid digest mismatch'); }
    a.nonces[key] = 1;
    var rec = { bidder: b.bidder, amount: amt.toString(), currency: b.currency, nonce: String(b.nonce), t: now | 0, seq: a.bids.length, signature: b.signature };
    a.bids.push(rec);
    a.highest = rec; // strictly increasing floor => highest is always the latest accepted
    log(a, 'BID_PLACED', now);
    // anti-sniping: a valid bid within the window extends the close, bounded.
    if (a.antiSnipeSecs > 0 && (a.closingTime - (now | 0)) <= a.antiSnipeSecs && a.extends < a.antiSnipeMaxExtends) {
      a.closingTime += a.antiSnipeSecs; a.extends += 1; log(a, 'ANTISNIPE_EXTENDED', now);
    }
    return rec;
  }

  function close(a, now) {
    assert(a.state === 'OPEN', 'not open');
    assert((now | 0) >= a.closingTime, 'closing time not reached');
    a.state = 'CLOSED'; log(a, 'CLOSED', now);
    if (!a.highest) { a.state = 'FAILED'; log(a, 'FAILED_NO_BIDS', now); return a; }
    if (a.reservePrice != null && BigInt(a.highest.amount) < BigInt(a.reservePrice)) {
      a.state = 'RESERVE_NOT_MET'; log(a, 'RESERVE_NOT_MET', now);
      a.state = 'FAILED'; return a;   // reserve not met -> failed, escrows refundable
    }
    a.winner = a.highest; a.state = 'WINNER_SELECTED'; log(a, 'WINNER_SELECTED', now);
    a.state = 'SETTLEMENT_PENDING';
    return a;
  }

  // AUCTION RESULT vs PAYMENT SETTLEMENT are separate. Settlement rail: SOST | EXTERNAL_DOCUMENTED | FUTURE.
  function settle(a, o) {
    assert(a.state === 'SETTLEMENT_PENDING', 'no winner pending settlement');
    o = o || {};
    a.settlement = { rail: o.rail || 'SOST', reference: o.reference || null, applied_escrow: !!o.applyEscrow,
      amount: a.winner.amount, currency: a.currency, note: 'SOST DOES NOT CUSTODY EXTERNAL FUNDS' };
    a.state = 'SETTLED'; log(a, 'SETTLEMENT_RECORDED');
    a.state = 'COMPLETE'; return a.settlement;
  }
  // winner fails to settle by deadline -> optionally offer to next-highest, else FAILED.
  function winnerFailed(a, now, offerToNext) {
    assert(a.state === 'SETTLEMENT_PENDING', 'not pending settlement');
    if (offerToNext) {
      var others = a.bids.filter(function (x) { return x.bidder !== a.winner.bidder; })
        .sort(function (x, y) { var d = BigInt(y.amount) - BigInt(x.amount); return d > 0n ? 1 : d < 0n ? -1 : (x.seq - y.seq); });
      if (others.length && (a.reservePrice == null || BigInt(others[0].amount) >= BigInt(a.reservePrice))) {
        a.winner = others[0]; log(a, 'WINNER_REASSIGNED', now); return a.winner;
      }
    }
    a.state = 'FAILED'; log(a, 'WINNER_FAILED', now); return null;
  }

  // refundable escrows: every escrow except a winner whose escrow was applied to settlement.
  function refundable(a) {
    return Object.keys(a.escrows).filter(function (bidder) {
      if (a.state === 'COMPLETE' && a.settlement && a.settlement.applied_escrow && a.winner && bidder === a.winner.bidder) return false;
      return a.escrows[bidder].status === 'ESCROW_LOCKED';
    });
  }
  function markRefunded(a, bidder) { if (a.escrows[bidder]) a.escrows[bidder].status = 'REFUNDED'; log(a, 'REFUND_RECORDED'); return true; }

  // persistence
  var KEY = 'sost.auctions.v1';
  function _ls() { try { return (typeof localStorage !== 'undefined') ? localStorage : null; } catch (e) { return null; } }
  function loadAll() { var ls = _ls(); if (!ls) return {}; try { return JSON.parse(ls.getItem(KEY) || '{}'); } catch (e) { return {}; } }
  function save(a) { assert(a.auctionId, 'auctionId required'); var ls = _ls(); if (!ls) return false; var m = loadAll(); m[a.auctionId] = a; try { ls.setItem(KEY, JSON.stringify(m)); return true; } catch (e) { return false; } }
  function resumable() { var m = loadAll(); return Object.keys(m).map(function (k) { return m[k]; }).filter(function (a) { return ['OPEN', 'SETTLEMENT_PENDING', 'WINNER_SELECTED'].indexOf(a.state) >= 0; }); }

  return {
    DOMAIN: DOMAIN, STATES: STATES, sha256Hex: sha256Hex, canon: canon,
    newAuction: newAuction, ready: ready, cancelBeforeOpen: cancelBeforeOpen, open: open,
    canonicalBid: canonicalBid, bidDigest: bidDigest, lockEscrow: lockEscrow, placeBid: placeBid,
    close: close, settle: settle, winnerFailed: winnerFailed, refundable: refundable, markRefunded: markRefunded,
    loadAll: loadAll, save: save, resumable: resumable
  };
});

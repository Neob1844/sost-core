/*
 * SOST DEX — QUOTE / RFQ POLICY (price-lock + expiry + cancellation).
 * ===========================================================================
 * Pure, dependency-free logic shared by the DEX dashboard + the DEVNET admin
 * E2E flow. It defines:
 *   - a FIRM QUOTE object (pair/side/amount/price/minimumReceived/counterparty/
 *     nonce/created_at/expires_at) with a default 90s lifetime and a live
 *     countdown + hard EXPIRY (an expired quote is NOT executable),
 *   - a QUOTE INTEGRITY digest (sha256 over the binding fields + nonce) so a
 *     MODIFIED quote (amount/price/expiry/counterparty tampered) is REJECTED
 *     before execution, and a reservation that PRICE-LOCKS the quote so no
 *     price change can slip through after it is reserved,
 *   - the CANCELLATION state machine: an order is cancelable while OPEN /
 *     SIGNED_OFFER / QUOTE_RESERVED (no HTLC funded yet); ONCE THE FIRST HTLC
 *     IS FUNDED there is NO simple cancel — only SETTLE, or TIMEOUT -> REFUND.
 *   - LIMIT orders with selectable expiry (15m / 1h / 24h / 7d / GTC).
 *
 * This module never fabricates a market price. A market/RFQ quote must come
 * from a real quote source (requestFirmQuote); with no source it fails closed.
 * No consensus/node/STRATO change; web/lab only. HTLC timelock VALUES live in
 * the swap flow and are NOT set here.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTDexQuotePolicy = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var QUOTE_DOMAIN = 'SOST-DEX-QUOTE';
  var QUOTE_VERSION = 1;
  var DEFAULT_LIFETIME_SECS = 90;              // firm quote default lifetime

  // Limit-order expiry presets (seconds). GTC = Good-Till-Cancelled (no expiry).
  var EXPIRY_PRESETS = { '15m': 900, '1h': 3600, '24h': 86400, '7d': 604800, 'GTC': null };
  var EXPIRY_LABEL = { '15m': '15 minutes', '1h': '1 hour', '24h': '24 hours', '7d': '7 days', 'GTC': 'Good-Till-Cancelled' };

  // Order / swap lifecycle states (the cancellation state machine).
  //   OPEN           : drafted, unsigned           -> cancelable
  //   SIGNED_OFFER   : signed offer, not funded     -> cancelable
  //   QUOTE_RESERVED : quote locked, no HTLC yet     -> cancelable (until funding begins)
  //   FUNDED         : first HTLC funded             -> NO cancel (SETTLE or TIMEOUT->REFUND)
  //   SETTLED/REFUNDED/CANCELLED/EXPIRED : terminal
  var ORDER_STATES = ['OPEN', 'SIGNED_OFFER', 'QUOTE_RESERVED', 'FUNDED', 'SETTLED', 'REFUNDED', 'CANCELLED', 'EXPIRED'];
  var CANCELABLE = { OPEN: 1, UNSIGNED: 1, SIGNED_OFFER: 1, QUOTE_RESERVED: 1 };
  var CANCEL_REFUSED_MSG =
    'Cannot cancel — the first HTLC is funded. From here the swap can only SETTLE, ' +
    'or TIMEOUT → REFUND. A confirmed on-chain HTLC is never reverted by a cancel.';

  function assert(c, m) { if (!c) throw new Error(m); }
  function nowSecs(nowMs) { return Math.floor((nowMs == null ? Date.now() : nowMs) / 1000); }

  // ---- self-contained sha256 (hex) so integrity works in node + browser ------
  function sha256hex(str) {
    function rotr(n, x) { return (x >>> n) | (x << (32 - n)); }
    var K = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    // UTF-8 encode
    var bytes = [];
    for (var i = 0; i < str.length; i++) {
      var c = str.charCodeAt(i);
      if (c < 0x80) bytes.push(c);
      else if (c < 0x800) { bytes.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f)); }
      else if (c < 0xd800 || c >= 0xe000) { bytes.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f)); }
      else { // surrogate pair
        i++; var c2 = 0x10000 + (((c & 0x3ff) << 10) | (str.charCodeAt(i) & 0x3ff));
        bytes.push(0xf0 | (c2 >> 18), 0x80 | ((c2 >> 12) & 0x3f), 0x80 | ((c2 >> 6) & 0x3f), 0x80 | (c2 & 0x3f));
      }
    }
    var l = bytes.length, bitLen = l * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    // 64-bit length (high 32 bits are 0 for our short inputs)
    for (var k = 7; k >= 0; k--) bytes.push((k < 4) ? ((bitLen >>> (k * 8)) & 0xff) : 0);
    var w = new Array(64);
    for (var off = 0; off < bytes.length; off += 64) {
      for (var t = 0; t < 16; t++) {
        w[t] = (bytes[off + t * 4] << 24) | (bytes[off + t * 4 + 1] << 16) | (bytes[off + t * 4 + 2] << 8) | (bytes[off + t * 4 + 3]);
      }
      for (var t2 = 16; t2 < 64; t2++) {
        var s0 = rotr(7, w[t2 - 15]) ^ rotr(18, w[t2 - 15]) ^ (w[t2 - 15] >>> 3);
        var s1 = rotr(17, w[t2 - 2]) ^ rotr(19, w[t2 - 2]) ^ (w[t2 - 2] >>> 10);
        w[t2] = (w[t2 - 16] + s0 + w[t2 - 7] + s1) | 0;
      }
      var a = H[0], b = H[1], c3 = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (var t3 = 0; t3 < 64; t3++) {
        var S1 = rotr(6, e) ^ rotr(11, e) ^ rotr(25, e);
        var ch = (e & f) ^ (~e & g);
        var temp1 = (h + S1 + ch + K[t3] + w[t3]) | 0;
        var S0 = rotr(2, a) ^ rotr(13, a) ^ rotr(22, a);
        var maj = (a & b) ^ (a & c3) ^ (b & c3);
        var temp2 = (S0 + maj) | 0;
        h = g; g = f; f = e; e = (d + temp1) | 0; d = c3; c3 = b; b = a; a = (temp1 + temp2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c3) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    var out = '';
    for (var j = 0; j < 8; j++) out += ('00000000' + (H[j] >>> 0).toString(16)).slice(-8);
    return out;
  }

  // ---- quote integrity digest -----------------------------------------------
  // The EXACT binding fields a maker signs. Tampering with any of them changes
  // the digest, so a modified quote (amount/price/expiry/counterparty/nonce/
  // side/pair) is rejected by verifyQuote before anything is funded.
  function bindingFields(q) {
    return {
      domain: QUOTE_DOMAIN, version: QUOTE_VERSION,
      pair: String(q.pair), side: String(q.side),
      amount: String(q.amount), price: String(q.price),
      minimumReceived: String(q.minimumReceived),
      counterparty: String(q.counterparty || ''),
      nonce: String(q.nonce),
      created_at: q.created_at | 0, expires_at: q.expires_at | 0
    };
  }
  function canon(o) {
    if (o === null || typeof o !== 'object') return JSON.stringify(o);
    if (Array.isArray(o)) return '[' + o.map(canon).join(',') + ']';
    return '{' + Object.keys(o).sort().map(function (k) { return JSON.stringify(k) + ':' + canon(o[k]); }).join(',') + '}';
  }
  function quoteDigest(q) { return sha256hex(canon(bindingFields(q))); }

  function randNonce() {
    try {
      var c = (typeof self !== 'undefined' && (self.crypto || self.msCrypto)) || (typeof crypto !== 'undefined' ? crypto : null);
      if (c && c.getRandomValues) { var b = new Uint8Array(16); c.getRandomValues(b); return Array.from(b).map(function (x) { return ('0' + x.toString(16)).slice(-2); }).join(''); }
    } catch (e) {}
    return String(Date.now()) + '-' + Math.floor(Math.random() * 1e9).toString(36);
  }

  // ---- firm quote ------------------------------------------------------------
  // params: {pair, side, amount, price, minimumReceived?, counterparty?, nonce?, signature?}
  // amounts/prices are STRINGS (base units / human). minimumReceived defaults to amount.
  function makeQuote(params, nowMs, lifetimeSecs) {
    params = params || {};
    assert(params.pair, 'quote.pair required');
    assert(params.side === 'buy' || params.side === 'sell', 'quote.side must be buy|sell');
    assert(params.amount != null && String(params.amount) !== '', 'quote.amount required');
    assert(params.price != null && String(params.price) !== '', 'quote.price required');
    var created = nowSecs(nowMs);
    var life = (lifetimeSecs == null) ? DEFAULT_LIFETIME_SECS : (lifetimeSecs | 0);
    assert(life > 0, 'lifetime must be > 0');
    var q = {
      domain: QUOTE_DOMAIN, version: QUOTE_VERSION,
      pair: String(params.pair), side: String(params.side),
      amount: String(params.amount), price: String(params.price),
      minimumReceived: String(params.minimumReceived != null ? params.minimumReceived : params.amount),
      counterparty: String(params.counterparty || ''),
      nonce: String(params.nonce != null ? params.nonce : randNonce()),
      created_at: created, expires_at: created + life,
      state: 'FIRM', reserved: false
    };
    q.digest = quoteDigest(q);
    if (params.signature != null) q.signature = String(params.signature);
    return q;
  }

  function isExpired(q, nowMs) { return nowSecs(nowMs) >= (q.expires_at | 0); }
  function remainingSecs(q, nowMs) { var r = (q.expires_at | 0) - nowSecs(nowMs); return r > 0 ? r : 0; }
  function formatCountdown(secs) {
    secs = Math.max(0, secs | 0);
    var m = Math.floor(secs / 60), s = secs % 60;
    return ('0' + m).slice(-2) + ':' + ('0' + s).slice(-2);
  }
  // Flip FIRM -> EXPIRED when the clock passes expires_at (idempotent, never un-expires).
  function refreshState(q, nowMs) {
    if (!q) return q;
    if (q.state === 'FIRM' && isExpired(q, nowMs)) q.state = 'EXPIRED';
    return q;
  }
  // A quote is executable ONLY while FIRM and now < expires_at.
  function isExecutable(q, nowMs) { return !!q && q.state === 'FIRM' && !isExpired(q, nowMs); }

  // verifyQuote: reject a MODIFIED quote (digest mismatch) or a STALE one (expired).
  // Returns {ok:boolean, reason:string}.
  function verifyQuote(q, nowMs) {
    if (!q) return { ok: false, reason: 'no quote' };
    if (!q.digest) return { ok: false, reason: 'quote has no integrity digest' };
    if (q.digest !== quoteDigest(q)) return { ok: false, reason: 'quote integrity check FAILED — amount/price/expiry/counterparty was modified (rejected)' };
    if (isExpired(q, nowMs)) return { ok: false, reason: 'quote is stale (expired) — request a new quote' };
    if (q.state !== 'FIRM') return { ok: false, reason: 'quote is not FIRM (state=' + q.state + ')' };
    return { ok: true, reason: '' };
  }

  // ---- reservation = PRICE LOCK ----------------------------------------------
  // After a quote is reserved, the price is pinned. assertUnchanged() rejects ANY
  // later price/digest drift, so no price change can slip through post-reservation.
  function reserveQuote(q, nowMs) {
    var v = verifyQuote(q, nowMs);
    assert(v.ok, v.reason);
    q.reserved = true; q.reserved_at = nowSecs(nowMs);
    return {
      digest: q.digest, nonce: q.nonce, pair: q.pair, side: q.side,
      price: q.price, amount: q.amount, minimumReceived: q.minimumReceived,
      expires_at: q.expires_at
    };
  }
  function assertUnchanged(reservation, q) {
    assert(reservation && q, 'reservation + quote required');
    if (q.digest !== reservation.digest || String(q.price) !== String(reservation.price) || String(q.amount) !== String(reservation.amount)) {
      throw new Error('price/terms changed after reservation — refusing (quote is price-locked)');
    }
    return true;
  }

  // ---- cancellation state machine --------------------------------------------
  function canCancel(state) { return !!CANCELABLE[state]; }
  // Refuse to cancel once funded; never touch a confirmed on-chain tx.
  function cancelOrder(order) {
    assert(order, 'order required');
    if (!canCancel(order.orderState)) throw new Error(CANCEL_REFUSED_MSG);
    order.orderState = 'CANCELLED';
    return order;
  }
  // The actions available for an order state (drives the UI buttons).
  function availableActions(state) {
    if (canCancel(state)) return ['CANCEL'];
    if (state === 'FUNDED') return ['SETTLE', 'REFUND'];   // only after timeout for REFUND
    return [];                                              // terminal
  }

  // ---- limit orders ----------------------------------------------------------
  // params: {side, amount, price, quoteAsset, expiry} expiry in EXPIRY_PRESETS.
  function newLimitOrder(params, nowMs) {
    params = params || {};
    assert(params.side === 'buy' || params.side === 'sell', 'limit side must be buy|sell');
    assert(params.amount != null && String(params.amount) !== '', 'limit amount required');
    assert(params.price != null && String(params.price) !== '', 'limit price required');
    var key = params.expiry || 'GTC';
    assert(Object.prototype.hasOwnProperty.call(EXPIRY_PRESETS, key), 'invalid expiry preset: ' + key);
    var created = nowSecs(nowMs);
    var secs = EXPIRY_PRESETS[key];
    return {
      type: 'limit', side: String(params.side),
      amount: String(params.amount), price: String(params.price),
      quoteAsset: String(params.quoteAsset || ''),
      expiryKey: key, created_at: created,
      expires_at: (secs == null) ? null : created + secs,
      nonce: String(params.nonce != null ? params.nonce : randNonce()),
      orderState: 'SIGNED_OFFER'   // a placed, signed limit order (not funded) -> cancelable
    };
  }
  function limitExpired(order, nowMs) { return order.expires_at != null && nowSecs(nowMs) >= order.expires_at; }
  function limitStatus(order, nowMs) {
    if (['CANCELLED', 'SETTLED', 'REFUNDED', 'EXPIRED'].indexOf(order.orderState) >= 0) return order.orderState;
    if (limitExpired(order, nowMs)) return 'EXPIRED';
    return order.orderState;
  }
  // Human-readable intent: "Sell X SOST at >= Y <quote>" / "Buy X SOST at <= Y <quote>".
  function limitLabel(order) {
    var cmp = order.side === 'sell' ? '≥' : '≤';
    var verb = order.side === 'sell' ? 'Sell' : 'Buy';
    return verb + ' ' + order.amount + ' SOST at ' + cmp + ' ' + order.price + (order.quoteAsset ? (' ' + order.quoteAsset) : '');
  }

  // ---- market / RFQ ----------------------------------------------------------
  // A market order MUST consume a FIRM quote from a real quote source — never a
  // fabricated price. `source` is a function(params)->{price,minimumReceived?,
  // counterparty?} (may be async). With no source we fail closed.
  function requestFirmQuote(source, params, nowMs, lifetimeSecs) {
    if (typeof source !== 'function') {
      return Promise.reject(new Error('no maker / quote source connected — fail-closed (no fabricated market price)'));
    }
    return Promise.resolve(source(params)).then(function (rate) {
      if (!rate || rate.price == null) throw new Error('quote source returned no firm price — fail-closed (nothing to lock)');
      return makeQuote({
        pair: params.pair, side: params.side, amount: params.amount,
        price: rate.price, minimumReceived: rate.minimumReceived, counterparty: rate.counterparty,
        signature: rate.signature
      }, nowMs, lifetimeSecs);
    });
  }

  return {
    QUOTE_DOMAIN: QUOTE_DOMAIN, QUOTE_VERSION: QUOTE_VERSION,
    DEFAULT_LIFETIME_SECS: DEFAULT_LIFETIME_SECS,
    EXPIRY_PRESETS: EXPIRY_PRESETS, EXPIRY_LABEL: EXPIRY_LABEL,
    ORDER_STATES: ORDER_STATES, CANCELABLE: CANCELABLE, CANCEL_REFUSED_MSG: CANCEL_REFUSED_MSG,
    sha256hex: sha256hex, quoteDigest: quoteDigest,
    makeQuote: makeQuote, isExpired: isExpired, remainingSecs: remainingSecs,
    formatCountdown: formatCountdown, refreshState: refreshState, isExecutable: isExecutable,
    verifyQuote: verifyQuote, reserveQuote: reserveQuote, assertUnchanged: assertUnchanged,
    canCancel: canCancel, cancelOrder: cancelOrder, availableActions: availableActions,
    newLimitOrder: newLimitOrder, limitExpired: limitExpired, limitStatus: limitStatus, limitLabel: limitLabel,
    requestFirmQuote: requestFirmQuote
  };
});

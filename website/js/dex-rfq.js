/*
 * SOST DEX — signed-RFQ / manual-offer core + atomic-swap state machine.
 * ---------------------------------------------------------------------------
 * Non-custodial. This module NEVER holds a seed, a private key, or a preimage
 * before it is revealed on-chain. It builds and validates a canonical, replay-
 * and expiry-protected OFFER (the executable quote), computes its integrity
 * digest, drives the frozen swap state machine, and reconciles persisted state
 * against on-chain truth (blockchain truth always wins). Real ECDSA signing and
 * verification are the wallet's job (browser) — this module only defines what is
 * signed and enforces the binding rules; signature bytes are opaque here.
 *
 * Pure web/lab. No consensus/node/STRATO change.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTDexRFQ = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var OFFER_DOMAIN = 'SOST-DEX-OFFER';
  var OFFER_VERSION = 1;

  // frozen atomic-swap state machine
  var STATES = ['DRAFT', 'OFFERED', 'ACCEPTED', 'INITIATOR_LOCKING', 'INITIATOR_LOCKED',
    'COUNTERPARTY_LOCKING', 'COUNTERPARTY_LOCKED', 'CLAIMABLE', 'CLAIMING', 'COMPLETE',
    'CANCELLED', 'EXPIRED', 'FAILED', 'REFUND_AVAILABLE', 'REFUNDING', 'REFUNDED'];
  var ALLOWED = {
    DRAFT: ['OFFERED', 'CANCELLED'],
    OFFERED: ['ACCEPTED', 'CANCELLED', 'EXPIRED'],
    ACCEPTED: ['INITIATOR_LOCKING', 'CANCELLED', 'EXPIRED', 'FAILED'],
    INITIATOR_LOCKING: ['INITIATOR_LOCKED', 'FAILED'],
    INITIATOR_LOCKED: ['COUNTERPARTY_LOCKING', 'REFUND_AVAILABLE', 'FAILED'],
    COUNTERPARTY_LOCKING: ['COUNTERPARTY_LOCKED', 'REFUND_AVAILABLE', 'FAILED'],
    COUNTERPARTY_LOCKED: ['CLAIMABLE', 'REFUND_AVAILABLE', 'FAILED'],
    CLAIMABLE: ['CLAIMING', 'REFUND_AVAILABLE'],
    CLAIMING: ['COMPLETE', 'REFUND_AVAILABLE', 'FAILED'],
    COMPLETE: [],
    CANCELLED: [], EXPIRED: [], FAILED: [],
    REFUND_AVAILABLE: ['REFUNDING'],
    REFUNDING: ['REFUNDED', 'REFUND_AVAILABLE'],
    REFUNDED: []
  };
  var TERMINAL = { COMPLETE: 1, CANCELLED: 1, EXPIRED: 1, FAILED: 1, REFUNDED: 1 };

  function assert(c, m) { if (!c) throw new Error(m); }

  async function sha256Hex(bytes) {
    if (typeof bytes === 'string') bytes = (typeof TextEncoder !== 'undefined') ? new TextEncoder().encode(bytes) : Buffer.from(bytes, 'utf8');
    if (typeof crypto !== 'undefined' && crypto.subtle) {
      var buf = await crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
    }
    return require('crypto').createHash('sha256').update(Buffer.from(bytes)).digest('hex');
  }

  // canonical JSON: sorted keys, integers/strings only (amounts are STRINGS, base units)
  function canon(o) {
    if (o === null || typeof o !== 'object') {
      if (typeof o === 'number' && !Number.isInteger(o)) throw new Error('amounts/values must be strings, not floats');
      return JSON.stringify(o);
    }
    if (Array.isArray(o)) return '[' + o.map(canon).join(',') + ']';
    return '{' + Object.keys(o).sort().map(function (k) { return JSON.stringify(k) + ':' + canon(o[k]); }).join(',') + '}';
  }

  // The exact object a maker signs. Binding fields prevent replay/cross-use.
  function canonicalOffer(o) {
    return {
      domain: OFFER_DOMAIN, version: OFFER_VERSION,
      maker: o.maker,                       // maker identifier (e.g. address)
      pay_chain: o.pay_chain, pay_asset: o.pay_asset, pay_amount: String(o.pay_amount),
      recv_chain: o.recv_chain, recv_asset: o.recv_asset, recv_amount: String(o.recv_amount),
      maker_receive_address: o.maker_receive_address,
      min_confirmations: o.min_confirmations | 0,
      refund_timeout: o.refund_timeout | 0, // blocks/seconds per chain adapter
      expiry: o.expiry | 0,                 // unix seconds; hard offer expiry
      nonce: String(o.nonce),               // unique per maker
      network: o.network                    // "mainnet" | "testnet" | "regtest" | "devnet"
    };
  }

  async function offerDigest(o) { return sha256Hex(canon(canonicalOffer(o))); }

  var CHAINS = { SOST: 1, BTC: 1, ETH: 1, EVM: 1 };
  function validateOffer(o, opts) {
    opts = opts || {};
    var c = canonicalOffer(o);
    assert(c.maker, 'offer.maker required');
    assert(CHAINS[c.pay_chain] && CHAINS[c.recv_chain], 'offer chains must be SOST/BTC/ETH/EVM');
    assert(c.pay_chain !== c.recv_chain, 'pay and receive chains must differ (cross-chain swap)');
    assert(/^[0-9]+$/.test(c.pay_amount) && c.pay_amount !== '0', 'pay_amount must be a positive integer string (base units)');
    assert(/^[0-9]+$/.test(c.recv_amount) && c.recv_amount !== '0', 'recv_amount must be a positive integer string (base units)');
    assert(c.min_confirmations >= 1, 'min_confirmations >= 1 (no 0-conf finality)');
    assert(c.refund_timeout > 0, 'refund_timeout required');
    assert(c.nonce && c.nonce !== '0', 'nonce required');
    assert(['mainnet', 'testnet', 'regtest', 'devnet'].indexOf(c.network) >= 0, 'invalid network');
    assert(c.expiry > 0, 'expiry required');
    if (opts.now != null) assert(c.expiry > opts.now, 'offer already expired');
    return true;
  }

  function isExpired(o, nowSecs) { return (canonicalOffer(o).expiry | 0) <= (nowSecs | 0); }

  // replay/duplicate guard: a (maker,nonce) may be accepted at most once
  function makeSeenSet() {
    var seen = {};
    return {
      key: function (o) { var c = canonicalOffer(o); return c.maker + '|' + c.nonce; },
      accept: function (o) { var k = this.key(o); if (seen[k]) return false; seen[k] = 1; return true; }
    };
  }

  // hashlock from a client-side preimage (preimage NEVER leaves the client until claim reveals it on-chain)
  async function hashlock(preimageHex) {
    assert(/^[0-9a-fA-F]{64}$/.test(preimageHex), 'preimage must be 32 bytes hex');
    var bytes = new Uint8Array(preimageHex.match(/../g).map(function (h) { return parseInt(h, 16); }));
    return sha256Hex(bytes);
  }

  // ---- state machine ----
  function canTransition(from, to) { return (ALLOWED[from] || []).indexOf(to) >= 0; }
  function applyTransition(swap, to) {
    assert(STATES.indexOf(to) >= 0, 'unknown state: ' + to);
    if (swap.state === to) return swap;                 // idempotent
    assert(canTransition(swap.state, to), 'illegal transition ' + swap.state + ' -> ' + to);
    swap.state = to;
    swap.history = (swap.history || []).concat([to]);
    return swap;
  }
  function isTerminal(state) { return !!TERMINAL[state]; }

  // ---- reconcile: on-chain truth beats local/relay ----
  // chain = { initiatorLocked, counterpartyLocked, claimed, refunded, expiredByTimeout }
  function reconcile(swap, chain) {
    chain = chain || {};
    if (chain.claimed) return forceTo(swap, 'COMPLETE');
    if (chain.refunded) return forceTo(swap, 'REFUNDED');
    if (chain.counterpartyLocked && !isTerminal(swap.state)) return forceTo(swap, 'CLAIMABLE');
    if (chain.initiatorLocked && !isTerminal(swap.state) && rank(swap.state) < rank('INITIATOR_LOCKED')) return forceTo(swap, 'INITIATOR_LOCKED');
    if (chain.expiredByTimeout && !isTerminal(swap.state)) return forceTo(swap, 'REFUND_AVAILABLE');
    return swap;
  }
  function forceTo(swap, to) { swap.state = to; swap.reconciled = true; swap.history = (swap.history || []).concat(['~' + to]); return swap; }
  function rank(s) { return STATES.indexOf(s); }

  // ---- persistence (localStorage-backed; safe no-op off-browser) ----
  var KEY = 'sost.dex.swaps.v1';
  function _ls() { try { return (typeof localStorage !== 'undefined') ? localStorage : null; } catch (e) { return null; } }
  function loadAll() { var ls = _ls(); if (!ls) return {}; try { return JSON.parse(ls.getItem(KEY) || '{}'); } catch (e) { return {}; } }
  function saveAll(map) { var ls = _ls(); if (!ls) return false; try { ls.setItem(KEY, JSON.stringify(map)); return true; } catch (e) { return false; } }
  function saveSwap(swap) { assert(swap && swap.id, 'swap.id required'); var m = loadAll(); m[swap.id] = swap; saveAll(m); return swap; }
  function resumable() { var m = loadAll(); return Object.keys(m).map(function (k) { return m[k]; }).filter(function (s) { return !isTerminal(s.state); }); }

  function newSwap(id, offer) { return { id: id, offer: canonicalOffer(offer), state: 'DRAFT', history: ['DRAFT'], created: null }; }

  return {
    OFFER_DOMAIN: OFFER_DOMAIN, OFFER_VERSION: OFFER_VERSION, STATES: STATES, ALLOWED: ALLOWED,
    sha256Hex: sha256Hex, canon: canon, canonicalOffer: canonicalOffer, offerDigest: offerDigest,
    validateOffer: validateOffer, isExpired: isExpired, makeSeenSet: makeSeenSet, hashlock: hashlock,
    canTransition: canTransition, applyTransition: applyTransition, isTerminal: isTerminal, reconcile: reconcile,
    loadAll: loadAll, saveSwap: saveSwap, resumable: resumable, newSwap: newSwap
  };
});

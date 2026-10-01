/*
 * SOST DEX — order relay (signed-offer store) + private-beta gate.
 * ---------------------------------------------------------------------------
 * The relay stores ONLY public data: signed offers, their status, hashlocks,
 * public tx references, timestamps. It NEVER stores a seed, a private key, or a
 * preimage before it is revealed on-chain. Storage is injected (a durable
 * backend in production — e.g. SQLite/HTTP; an in-memory Map in tests) so the
 * lifecycle logic is unit-testable. Guards: signature-shape, digest match,
 * expiry, network binding, and single-acceptance (no replay / double-fill).
 * No consensus/node/STRATO change.
 */
(function (root, factory) {
  var m = factory(function () {
    if (typeof module !== 'undefined' && module.exports) return require('./dex-rfq.js');
    return (typeof self !== 'undefined' ? self : this).SOSTDexRFQ;
  });
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTDexRelay = m;
})(typeof self !== 'undefined' ? self : this, function (getRFQ) {
  'use strict';
  var RFQ = getRFQ();

  function memoryStore() {
    var offers = {}, swaps = {};
    return {
      putOffer: function (id, rec) { offers[id] = rec; },
      getOffer: function (id) { return offers[id] || null; },
      listOffers: function () { return Object.keys(offers).map(function (k) { return offers[k]; }); },
      putSwap: function (id, rec) { swaps[id] = rec; },
      getSwap: function (id) { return swaps[id] || null; },
      listSwaps: function () { return Object.keys(swaps).map(function (k) { return swaps[k]; }); }
    };
  }

  // relay over an injected store. `now()` injectable for deterministic tests.
  function relay(store, now) {
    store = store || memoryStore();
    now = now || function () { return Math.floor(Date.now() / 1000); };
    var seen = RFQ.makeSeenSet();

    return {
      store: store,
      // POST a signed offer. sig is the opaque wallet signature over offerDigest.
      async post(offer, sig) {
        RFQ.validateOffer(offer, { now: now() });
        if (!sig || typeof sig !== 'string' || sig.length < 8) throw new Error('MISSING_SIGNATURE');
        var digest = await RFQ.offerDigest(offer);
        var c = RFQ.canonicalOffer(offer);
        var id = digest.slice(0, 32);
        if (store.getOffer(id)) throw new Error('DUPLICATE_OFFER');
        store.putOffer(id, { id: id, offer: c, sig: sig, digest: digest, status: 'OFFERED', posted: now() });
        return id;
      },
      list(filter) {
        var t = now();
        return store.listOffers().filter(function (r) {
          if (r.status !== 'OFFERED') return false;
          if (r.offer.expiry <= t) return false;                    // hide expired
          if (filter && filter.network && r.offer.network !== filter.network) return false;
          if (filter && filter.pay_asset && r.offer.pay_asset !== filter.pay_asset) return false;
          if (filter && filter.recv_asset && r.offer.recv_asset !== filter.recv_asset) return false;
          return true;
        });
      },
      get(id) { return store.getOffer(id); },
      // ACCEPT binds a taker; single-acceptance enforced (no double-fill / replay).
      async accept(id, taker, network) {
        var rec = store.getOffer(id);
        if (!rec) throw new Error('NO_SUCH_OFFER');
        if (rec.status !== 'OFFERED') throw new Error('OFFER_NOT_OPEN');
        if (rec.offer.expiry <= now()) { rec.status = 'EXPIRED'; store.putOffer(id, rec); throw new Error('OFFER_EXPIRED'); }
        if (network && network !== rec.offer.network) throw new Error('NETWORK_MISMATCH');
        if (!seen.accept(rec.offer)) throw new Error('ALREADY_ACCEPTED');     // replay / double accept
        rec.status = 'ACCEPTED'; rec.taker = taker || null; rec.accepted = now(); store.putOffer(id, rec);
        var swapId = rec.digest.slice(0, 40);
        store.putSwap(swapId, { id: swapId, offerId: id, state: 'ACCEPTED', hashlock: null, txrefs: {}, updated: now() });
        return swapId;
      },
      // CANCEL only before any lock exists.
      cancelBeforeLock(id) {
        var rec = store.getOffer(id);
        if (!rec) throw new Error('NO_SUCH_OFFER');
        if (rec.status !== 'OFFERED') throw new Error('CANNOT_CANCEL_AFTER_ACCEPT');
        rec.status = 'CANCELLED'; store.putOffer(id, rec); return true;
      },
      // sweep expired open offers.
      expireSweep() {
        var t = now(), n = 0;
        store.listOffers().forEach(function (r) { if (r.status === 'OFFERED' && r.offer.expiry <= t) { r.status = 'EXPIRED'; store.putOffer(r.id, r); n++; } });
        return n;
      },
      // record public swap progress (hashlock once known, tx references). Never a preimage pre-reveal.
      updateSwap(swapId, patch) {
        var s = store.getSwap(swapId); if (!s) throw new Error('NO_SUCH_SWAP');
        if (patch && patch.preimage) throw new Error('RELAY_MUST_NOT_STORE_PREIMAGE');
        Object.assign(s, patch || {}, { updated: now() }); store.putSwap(swapId, s); return s;
      },
      swapStatus(swapId) { return store.getSwap(swapId); }
    };
  }

  // ---- private-beta gate (server-side allowlist; no secrets) ---------------
  function gate(config) {
    // config.allowlist = { sost:[], evm:[], btc:[] } (addresses, lowercased). Empty/absent => execution disabled.
    var cfg = config || {};
    function norm(a) { return (a || '').toString().trim().toLowerCase(); }
    var lists = cfg.allowlist || {};
    var any = ['sost', 'evm', 'btc'].some(function (k) { return (lists[k] || []).length > 0; });
    return {
      configured: any,
      executionEnabled: function () { return any; },   // no allowlist configured => DISABLED
      isAllowed: function (chainKey, addr) {
        if (!any) return false;
        var l = (lists[chainKey] || []).map(norm);
        return l.indexOf(norm(addr)) >= 0;
      },
      banner: any ? 'PRIVATE BETA · OWNER TESTING ONLY' : 'PRIVATE BETA · EXECUTION DISABLED (no allowlist configured)'
    };
  }

  return { memoryStore: memoryStore, relay: relay, gate: gate };
});

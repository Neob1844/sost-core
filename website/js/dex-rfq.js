/* SOST DEX — RFQ signed-quote engine (lab, HARDENED). Request-for-quote to INDEPENDENT liquidity
 * providers. A firm quote is a signed offer with reserved inventory, a nonce and an expiry. This
 * module holds NO custody and builds NO HTLCs — it manages quote validity, signature verification,
 * replay/double-accept protection, and an atomic confirmed/committed/available inventory model.
 *
 * FAIL-CLOSED: with no signature verifier configured, EVERY quote is rejected. There is no
 * accept-any default. A durable store may be injected for restart recovery; without it state is
 * in-memory (lab prototype) and that limitation is reported by `durable()`.
 */
(function (root, factory){ var m=factory(); if(typeof module!=='undefined'&&module.exports){module.exports=m;} if(root){root.SOSTRfq=m;} })(typeof self!=='undefined'?self:this, function(){
  'use strict';

  function makeBook(opts){
    opts = opts || {};
    // FAIL-CLOSED: verifier must be an explicit function. No permissive default.
    var verify = (typeof opts.verify === 'function') ? opts.verify : null;
    // optional durable store: { load():{accepted,committed}, save(state) }
    var store = opts.store || null;

    var accepted = Object.create(null);   // nonceKey -> {maker,amount}  (replay / double-accept guard)
    var committed = Object.create(null);  // maker -> committed amount (reserved against confirmed)

    if (store && typeof store.load === 'function') {
      try {
        var st = store.load() || {};
        if (st.accepted) accepted = Object.assign(Object.create(null), st.accepted);
        if (st.committed) committed = Object.assign(Object.create(null), st.committed);
      } catch (e) { /* start empty on a corrupt store */ }
    }
    function persist(){ if (store && typeof store.save === 'function') { try { store.save({accepted:accepted, committed:committed}); } catch(e){} } }
    function nkey(q){ return q.maker + ':' + q.nonce; }
    function committedFor(m){ return committed[m] || 0; }

    var api = {
      durable: function(){ return !!store; },   // false = in-memory lab prototype (not a real engine)
      committedFor: committedFor,
      availableFor: function(q){ return (Number(q.confirmedInventory)||0) - committedFor(q.maker); },

      // Validate a maker quote WITHOUT reserving. Fail-closed on missing verifier.
      validate: function(q, nowMs){
        if (!verify) return {ok:false, error:'no signature verifier configured (fail-closed)'};
        if (!q || !q.maker || q.nonce==null) return {ok:false, error:'malformed quote'};
        if (typeof q.amount!=='number' || q.amount<=0) return {ok:false, error:'bad amount'};
        if (typeof q.price!=='number' || q.price<=0) return {ok:false, error:'bad price'};
        if (!q.expiry || nowMs > q.expiry) return {ok:false, error:'quote expired'};
        // confirmed / committed / available: never trust a bare "reservedInventory" number.
        var confirmed = Number(q.confirmedInventory);
        if (!(confirmed >= 0)) return {ok:false, error:'missing confirmedInventory'};
        var available = confirmed - committedFor(q.maker);
        if (q.amount > available) return {ok:false, error:'insufficient available inventory ('+available+' < '+q.amount+')'};
        if (accepted[nkey(q)]) return {ok:false, error:'already accepted (replay)'};
        if (!verify(q)) return {ok:false, error:'bad maker signature'};
        return {ok:true, available:available};
      },

      // Atomically validate + reserve (commit) inventory + mark the nonce. JS is single-threaded, so
      // this check-then-commit cannot interleave; two accepts of the same nonce or of overlapping
      // inventory are serialized and the second is rejected.
      accept: function(q, nowMs){
        var v = this.validate(q, nowMs); if(!v.ok) return v;
        var id = nkey(q);
        // re-check inside the atomic section (defensive; validate already checked)
        if (accepted[id]) return {ok:false, error:'double-accept blocked'};
        if (q.amount > (Number(q.confirmedInventory)||0) - committedFor(q.maker)) return {ok:false, error:'inventory raced out'};
        accepted[id] = {maker:q.maker, amount:q.amount};
        committed[q.maker] = committedFor(q.maker) + q.amount;
        persist();
        return {ok:true, quoteId:id, committed:committed[q.maker]};
      },

      // Release a commitment (e.g. the swap failed / refunded) — frees the reserved inventory.
      release: function(q){
        var id = nkey(q); var rec = accepted[id];
        if (!rec) return {ok:false, error:'unknown quote'};
        committed[rec.maker] = Math.max(0, committedFor(rec.maker) - rec.amount);
        delete accepted[id];
        persist();
        return {ok:true, committed:committedFor(rec.maker)};
      },

      isAccepted: function(q){ return !!accepted[nkey(q)]; }
    };
    return api;
  }
  return { makeBook: makeBook };
});

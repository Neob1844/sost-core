/* SOST DEX — RFQ signed-quote engine (lab). Request-for-quote to INDEPENDENT liquidity providers.
 * A firm quote is a signed offer with reserved inventory, a nonce and an expiry. This module does
 * NOT hold custody and does NOT build HTLCs — it only manages quote validity + double-accept /
 * replay protection. Real signature verification is delegated to a wallet-adapter verifier.
 */
(function (root, factory){ var m=factory(); if(typeof module!=='undefined'&&module.exports){module.exports=m;} if(root){root.SOSTRfq=m;} })(typeof self!=='undefined'?self:this, function(){
  'use strict';
  function makeBook(opts){
    opts = opts || {};
    var verify = opts.verify || function(){ return true; };  // (quote)->bool signature check (injected)
    var accepted = Object.create(null);   // nonce -> true  (double-accept / replay guard)
    var reserved = Object.create(null);   // quoteId -> amount reserved
    function quoteId(q){ return q.maker + ':' + q.nonce; }
    return {
      // validate a maker quote before showing it as executable
      validate: function(q, nowMs){
        if(!q || !q.maker || q.nonce==null) return {ok:false, error:'malformed quote'};
        if(typeof q.amount!=='number' || q.amount<=0) return {ok:false, error:'bad amount'};
        if(typeof q.price!=='number' || q.price<=0) return {ok:false, error:'bad price'};
        if(!q.expiry || nowMs > q.expiry) return {ok:false, error:'quote expired'};
        if(!(q.reservedInventory>=q.amount)) return {ok:false, error:'insufficient reserved inventory'};
        if(accepted[quoteId(q)]) return {ok:false, error:'already accepted (replay)'};
        if(!verify(q)) return {ok:false, error:'bad maker signature'};
        return {ok:true};
      },
      // accept exactly once; returns false on any double-accept of the same nonce
      accept: function(q, nowMs){
        var v = this.validate(q, nowMs); if(!v.ok) return v;
        var id = quoteId(q);
        if(accepted[id]) return {ok:false, error:'double-accept blocked'};
        accepted[id] = true; reserved[id] = q.amount;
        return {ok:true, quoteId:id};
      },
      isAccepted: function(q){ return !!accepted[quoteId(q)]; },
      reservedFor: function(q){ return reserved[quoteId(q)]||0; }
    };
  }
  return { makeBook: makeBook };
});

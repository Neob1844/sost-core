/* SOST DEX — Price Reference Adapter (lab). DECOUPLED from the DEX engine.
 *
 * Purpose: when SOST is listed on a CEX (first target SOST/USDT or SOST/USDC), this adapter will
 * query bid/ask/depth/volume/last/age/market-status/fees via that venue's API. Until then it
 * returns a clearly-labelled SIMULATED reference and ALWAYS reports executable:false.
 *
 * HARD RULES:
 *  - A reference price is NOT executable liquidity and NOT a promise.
 *  - NEVER use the protocol's gold reference (1.14 mg/SOST) as a market price. See
 *    docs/dex/GOLD_REFERENCE_RECONCILIATION.md. The gold figure is informational only.
 */
(function (root, factory){ var m=factory(); if(typeof module!=='undefined'&&module.exports){module.exports=m;} if(root){root.SOSTPriceAdapter=m;} })(typeof self!=='undefined'?self:this, function(){
  'use strict';
  // A CEX source, once configured, must implement fetchTicker() -> {bid,ask,last,depth,volume24h,tsMs,status,fees}
  function makeAdapter(opts){
    opts = opts || {};
    var source = opts.source || null;          // null in the lab
    var maxAgeMs = opts.maxAgeMs || 30000;     // a quote older than this is stale
    return {
      // returns a normalized reference; executable is true ONLY with a live, fresh CEX source
      async getReference(pair, nowMs){
        if(!source){
          return { pair:pair, executable:false, simulated:true, reason:'no CEX market connected',
                   bid:null, ask:null, last:null, depthForAmount:null, volume24h:null,
                   ageMs:null, status:'lab', fees:null };
        }
        var t = await source.fetchTicker(pair);
        var age = (nowMs||0) - (t.tsMs||0);
        var fresh = age >= 0 && age <= maxAgeMs && t.status === 'trading';
        return { pair:pair, executable:false /* reference != executable; RFQ provides executable */,
                 simulated:false, reason: fresh?'reference only':'stale/closed',
                 bid:t.bid, ask:t.ask, last:t.last, depthForAmount:t.depth||null,
                 volume24h:t.volume24h||null, ageMs:age, status:t.status, fees:t.fees||null, fresh:fresh };
      }
    };
  }
  return { makeAdapter: makeAdapter };
});

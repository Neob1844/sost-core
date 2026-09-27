/* SOST DEX — initial-liquidity SIMULATOR (lab). NOT an investment and NOT real funds.
 * Models an INDEPENDENT provider seeding one experimental market (SOST/USDC) with a small
 * hypothetical budget (default $2,000 split USDC/SOST). It reserves inventory per active quote,
 * recomputes capacity on fills, suspends on insufficient funds or a stale reference, and tracks
 * exposure, fees and realized PnL. The owner is NOT assumed to self-trade.
 */
(function (root, factory){ var m=factory(); if(typeof module!=='undefined'&&module.exports){module.exports=m;} if(root){root.SOSTLiquiditySim=m;} })(typeof self!=='undefined'?self:this, function(){
  'use strict';
  function makeSim(cfg){
    cfg = cfg || {};
    var S = {
      usdc: cfg.usdc!=null?cfg.usdc:1000,      // USDC reserve
      sost: cfg.sost!=null?cfg.sost:1000/(cfg.refPrice||0.15), // SOST reserve (~$1000 at ref)
      refPrice: cfg.refPrice||0.15,            // informational reference $/SOST (NOT a promise)
      spreadBps: cfg.spreadBps!=null?cfg.spreadBps:150, // 1.5% each side
      maxQuoteUsd: cfg.maxQuoteUsd||100,       // cap per quote
      feeBps: cfg.feeBps!=null?cfg.feeBps:30,  // protocol/maker fee
      reserved: {usdc:0, sost:0},
      realizedPnlUsd: 0, feesUsd: 0, suspended:false, suspendReason:''
    };
    function price(side){ // maker quotes around the reference with a spread
      var s = S.spreadBps/10000;
      return side==='buy'  ? S.refPrice*(1+s)   // taker buys SOST -> maker sells higher
                           : S.refPrice*(1-s);  // taker sells SOST -> maker buys lower
    }
    function availUsd(){ return S.usdc - S.reserved.usdc; }
    function availSost(){ return S.sost - S.reserved.sost; }
    return {
      state: function(){ return JSON.parse(JSON.stringify(S)); },
      setReference: function(p, stale){ // feed a fresh reference; suspend if stale
        if(stale){ S.suspended=true; S.suspendReason='stale reference'; return; }
        S.refPrice=p; if(S.suspendReason==='stale reference'){S.suspended=false;S.suspendReason='';}
      },
      // produce a firm quote for a taker order of `amountSost` on `side`, or a refusal
      quote: function(side, amountSost, nowMs){
        if(S.suspended) return {ok:false, error:'suspended: '+S.suspendReason};
        var px = price(side), usd = amountSost*px;
        if(usd > S.maxQuoteUsd) return {ok:false, error:'exceeds max quote size'};
        if(side==='buy'){ if(amountSost > availSost()) return {ok:false, error:'insufficient SOST inventory'}; }
        else            { if(usd > availUsd())        return {ok:false, error:'insufficient USDC inventory'}; }
        // reserve inventory for this offer
        if(side==='buy') S.reserved.sost += amountSost; else S.reserved.usdc += usd;
        return {ok:true, side:side, amountSost:amountSost, price:px, usd:usd,
                nonce:(nowMs||0)+'-'+Math.floor(usd*100), expiry:(nowMs||0)+15000,
                reservedInventory:amountSost};
      },
      // settle a previously-quoted offer (a real cross-chain fill); updates reserves + PnL + fees
      fill: function(q){
        var fee = q.usd*(S.feeBps/10000); S.feesUsd += fee;
        if(q.side==='buy'){ // maker sold SOST, received USDC
          S.reserved.sost -= q.amountSost; S.sost -= q.amountSost; S.usdc += q.usd - fee;
          S.realizedPnlUsd += (q.price - S.refPrice)*q.amountSost - fee;
        } else {            // maker bought SOST, paid USDC
          S.reserved.usdc -= q.usd; S.usdc -= q.usd; S.sost += q.amountSost; S.usdc += 0;
          S.realizedPnlUsd += (S.refPrice - q.price)*q.amountSost - fee;
        }
        // suspend if either reserve is effectively empty
        if(availUsd() < 1 || availSost() < 1){ S.suspended=true; S.suspendReason='inventory depleted'; }
        return this.state();
      },
      cancel: function(q){ // release reservation without a fill
        if(q.side==='buy') S.reserved.sost -= q.amountSost; else S.reserved.usdc -= q.usd;
      },
      exposureUsd: function(){ return S.sost*S.refPrice + S.usdc; }, // mark-to-reference
      // model an adverse CEX move: reference drops p% -> unrealized mark change
      shockReference: function(pct){ S.refPrice = S.refPrice*(1+pct/100); return this.exposureUsd(); }
    };
  }
  return { makeSim: makeSim };
});

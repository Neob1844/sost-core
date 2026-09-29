/* SOST Offering Dashboards — shared, professional dashboards over the tested
 * offering engines (Auction here; Draw / Project Funding reuse .od-* + helpers).
 * Real-money execution is DISABLED (client mirror of the server-side regulatory
 * gate). Engine logic, validation, state transitions, verification and readback
 * all run; only BROADCAST / real fund movement is blocked. No consensus change. */
(function(){
  'use strict';
  var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});};
  // Client mirror of the authoritative server-side gate (slice F). Execution OFF.
  var GATE={AUCTION_EXECUTION:false,DRAW_EXECUTION:false,PROJECT_FUNDING_EXECUTION:false,TOKENIZE_REGULATED_EXECUTION:false};
  window.SOST_OFFERING_GATE=GATE;

  function badge(state){
    var m={DRAFT:'d',READY:'d',OPEN:'o',CLOSING:'o',CLOSED:'o',WINNER_SELECTED:'o',SETTLEMENT_PENDING:'o',
      RESERVE_NOT_MET:'w',FAILED:'w',CANCELLED:'w',REFUNDING:'o',REFUNDED:'g',SETTLED:'g',COMPLETE:'g'};
    return '<span class="od-state '+(m[state]||'d')+'">'+esc(state)+'</span>';
  }
  function stepper(steps,active){
    return '<div class="od-steps">'+steps.map(function(s,i){
      var cls=i<active?'done':(i===active?'now':''); return '<span class="od-step '+cls+'">'+esc(s)+'</span>';
    }).join('<i>→</i>')+'</div>';
  }
  function metric(l,v,sub){ return '<div class="od-metric"><div class="od-ml">'+esc(l)+'</div><div class="od-mv">'+v+'</div>'+(sub?'<div class="od-ms">'+esc(sub)+'</div>':'')+'</div>'; }
  function fmtMoney(v,cur){ if(v==null)return '—'; return Number(v).toLocaleString('en-US')+' '+esc(cur||''); }

  // ---------------- AUCTION ----------------
  var A=window.SOSTAssetAuction;
  function ex(){ return {asset:'Gold bar (1 kg, LBMA)',passportId:'ap_demo_goldbar',seller:'sost1seller_demo',
    currency:'EUR',startingPrice:'15000',reservePrice:'18000',minimumIncrement:'100',escrowReferenceAmount:'100',
    bids:[['sost1bidder_a','16000'],['sost1bidder_b','17500'],['sost1bidder_c','18200'],['sost1bidder_d','18900']]}; }

  async function runAuction(cfg){
    var a=A.newAuction({auctionId:'auc_'+cfg.passportId, passportId:cfg.passportId, seller:cfg.seller,
      currency:cfg.currency, network:'devnet', startingPrice:cfg.startingPrice, reservePrice:cfg.reservePrice||null,
      minimumIncrement:cfg.minimumIncrement, openingTime:0, closingTime:100000,
      antiSnipeSecs:30, escrowRequired:true, escrowReferenceAmount:cfg.escrowReferenceAmount, settlementDeadline:200000});
    A.ready(a); A.open(a, 0);
    var t=10, digests=[];
    for(var i=0;i<cfg.bids.length;i++){
      var bidder=cfg.bids[i][0], amount=cfg.bids[i][1];
      A.lockEscrow(a, bidder, {sost:'~', price:cfg.escrowReferenceAmount, source:'reference (CryptoCompare) — quote only', ts:t});
      var bid={auctionId:a.auctionId, network:'devnet', bidder:bidder, amount:amount, currency:cfg.currency, nonce:'n'+i, expiry:0};
      var digest=await A.bidDigest(bid); bid.signature='demo-sig-'+digest.slice(0,16); // real ECDSA = wallet-side (local only)
      digests.push({bidder:bidder,amount:amount,digest:digest});
      await A.placeBid(a, bid, t, {digest:digest}); // digest check exercises signature/canonical path
      t+=10;
    }
    A.close(a, 100000);
    var settlement=null;
    if(a.state==='SETTLEMENT_PENDING'){ settlement=A.settle(a,{rail:'SOST', applyEscrow:false}); }
    var refunds=A.refundable(a); refunds.forEach(function(b){ A.markRefunded(a,b); });
    a._digests=digests; return a;
  }

  function renderAuction(root, a, cfg){
    var STEPS=['Passport','Configure','Open','Bids','Close','Winner','Settlement','Refunds','Complete'];
    var active=({DRAFT:1,READY:1,OPEN:2,CLOSED:4,RESERVE_NOT_MET:4,FAILED:4,WINNER_SELECTED:5,SETTLEMENT_PENDING:6,SETTLED:7,COMPLETE:8})[a.state]||0;
    var reserveMet = a.reservePrice==null || (a.highest && BigInt(a.highest.amount)>=BigInt(a.reservePrice));
    var participants=Object.keys(a.escrows).length;
    var h='';
    h+='<div class="od-head"><div class="od-title">Auction dashboard '+badge(a.state)+'</div>'
      +'<div class="od-sub">Highest valid signed bid wins · ties → earliest · refundable escrow · <b>real funds disabled</b></div></div>';
    h+=stepper(STEPS,active);
    // metrics
    h+='<div class="od-metrics">'
      + metric('Asset', esc(cfg.asset))
      + metric('Starting', fmtMoney(a.startingPrice,a.currency))
      + metric('Reserve', a.reservePrice==null?'none':fmtMoney(a.reservePrice,a.currency), reserveMet?'met':'not met')
      + metric('Min. increment', fmtMoney(a.minimumIncrement,a.currency))
      + metric('Participants', participants)
      + metric('Highest bid', a.highest?fmtMoney(a.highest.amount,a.currency):'—', a.highest?esc(a.highest.bidder):'')
      + metric('Winner', a.winner?esc(a.winner.bidder):'—', a.winner?fmtMoney(a.winner.amount,a.currency):'')
      + metric('Settlement', a.settlement?('rail '+esc(a.settlement.rail)):'—', a.settlement?'no custody':'')
      +'</div>';
    // bids table
    h+='<div class="od-block od-adv-only"><h4>Signed bids <span class="od-mini">(digest = SHA-256 of canonical bid; ECDSA is wallet-side, local only)</span></h4><div class="od-scroll"><table class="od-tbl"><thead><tr><th>#</th><th>Bidder</th><th>Amount</th><th>Nonce</th><th>Digest</th></tr></thead><tbody>';
    a.bids.forEach(function(b,i){ var dg=(a._digests&&a._digests[i])?a._digests[i].digest:''; h+='<tr><td>'+(i+1)+'</td><td>'+esc(b.bidder)+'</td><td>'+fmtMoney(b.amount,a.currency)+'</td><td>'+esc(b.nonce)+'</td><td class="od-hash">'+esc(dg.slice(0,20))+'…</td></tr>'; });
    h+='</tbody></table></div></div>';
    // escrow / refunds
    h+='<div class="od-block"><h4>Escrows &amp; refunds</h4><div class="od-scroll"><table class="od-tbl"><thead><tr><th>Bidder</th><th>Reference</th><th>Status</th></tr></thead><tbody>';
    Object.keys(a.escrows).forEach(function(b){ var e=a.escrows[b]; h+='<tr><td>'+esc(b)+'</td><td>'+fmtMoney(e.reference,e.currency)+'</td><td>'+badge(e.status)+'</td></tr>'; });
    h+='</tbody></table></div></div>';
    // event log
    h+='<div class="od-block"><h4>Event log</h4><div class="od-events">'+a.events.map(function(ev){return '<span class="od-ev">'+esc(ev.e)+(ev.t?'<i>@'+ev.t+'</i>':'')+'</span>';}).join('')+'</div></div>';
    // legal readiness + gate
    h+='<div class="od-two"><div class="od-legal"><h4>Legal readiness</h4><ul>'
      +'<li>Legal classification: <b>NOT DETERMINED BY SOST</b></li>'
      +'<li>SOST never custodies external funds — settlement is a recorded reference</li>'
      +'<li>Asset transfer / AML / tax rules apply off-chain</li></ul></div>';
    h+='<div class="od-gate"><h4>Mainnet execution</h4>'
      +'<div class="od-gaterow"><span class="od-glabel">AUCTION_EXECUTION</span><span class="od-gval off">DISABLED · REGULATORY GATE</span></div>'
      +'<div class="od-mini">Engine, validation, state machine, verification and readback run in full. <b>Broadcast / real fund movement is blocked</b> until the server-side gate + transaction-path E2E are proven, then legal authorization. Server-side gate: pending (slice F).</div></div></div>';
    // advanced raw
    h+='<div class="od-block od-adv-only"><h4>Raw state</h4><pre class="od-raw">'+esc(JSON.stringify(a,function(k,v){return k==='_digests'?undefined:v;},1))+'</pre></div>';
    root.querySelector('.od-body').innerHTML=h;
  }

  function mountAuction(){
    var root=document.getElementById('auction-dash'); if(!root||!A) return;
    root.innerHTML='<div class="od-toolbar">'
      +'<button class="od-run" id="aucd-run">Run full lifecycle (example)</button>'
      +'<label class="od-modes"><input type="checkbox" id="aucd-adv"> Advanced mode</label>'
      +'<span class="od-gatepill">Real-money execution: DISABLED</span></div>'
      +'<div class="od-body"><div class="od-empty">Press <b>Run full lifecycle</b> to drive a real Asset Passport through Configure → Open → signed Bids → Close → Winner → Settlement → Refunds → Complete, using the lab-verified auction engine. No funds move.</div></div>';
    var advCb=document.getElementById('aucd-adv');
    advCb.addEventListener('change',function(){ root.classList.toggle('od-advanced', advCb.checked); });
    document.getElementById('aucd-run').addEventListener('click',function(){
      var btn=this; btn.disabled=true; btn.textContent='Running…';
      runAuction(ex()).then(function(a){ renderAuction(root,a,ex()); btn.disabled=false; btn.textContent='Re-run lifecycle';
        try{ A.save(a); }catch(e){} })
      .catch(function(e){ root.querySelector('.od-body').innerHTML='<div class="od-empty">Error: '+esc(e.message)+'</div>'; btn.disabled=false; btn.textContent='Run full lifecycle (example)'; });
    });
  }
  if(document.readyState!=='loading') mountAuction(); else document.addEventListener('DOMContentLoaded',mountAuction);
  window.SOSTOfferDash={mountAuction:mountAuction, _runAuction:runAuction};
})();

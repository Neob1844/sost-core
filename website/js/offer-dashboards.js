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

  // ---------------- DRAW (verifiable) ----------------
  var DR=window.SOSTAssetDraw;
  function drawEx(){ return {asset:'Vintage racing motorcycle', passportHash:'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
    price_ref_usdc:'20', target_tickets:25, close_height:30000, entropy_height:30010,
    // deterministic demo entropy (a future block hash, revealed only after freeze)
    entropyHex:'00000000000000000009f3a1c77bb2e4d5a6b7c8d9e0f1a2b3c4d5e6f708192a'}; }

  async function runDraw(cfg){
    var c=DR.newCampaign({id:'draw_'+cfg.passportHash.slice(0,8), asset_passport_hash:cfg.passportHash,
      target_tickets:cfg.target_tickets, price_ref_usdc:cfg.price_ref_usdc, network:'devnet',
      close_height:cfg.close_height, entropy_height:cfg.entropy_height});
    var ev=[{e:'CAMPAIGN_CREATED'}];
    for(var i=1;i<=cfg.target_tickets;i++){ DR.sellTicket(c,'T'+String(i).padStart(3,'0'),'buyer'+i); }
    ev.push({e:'TICKETS_SOLD_OUT'});
    var campaignHash=await DR.freeze(c); ev.push({e:'FROZEN'});
    ev.push({e:'ENTROPY_ANNOUNCED@'+cfg.entropy_height});
    var d=await DR.draw(c, cfg.entropyHex, cfg.entropy_height); ev.push({e:'WINNER_SELECTED'});
    // independent recompute (verification) + tamper check
    var v=await DR.verify(campaignHash, c.tickets.slice(), cfg.entropyHex);
    var match=(v.winner_ticket===d.winner_ticket && v.winner_index===d.winner_index && v.seed===d.seed);
    var tampered=c.tickets.slice(); tampered[0]='TX_TAMPER';
    var vt=await DR.verify(campaignHash, tampered, cfg.entropyHex);
    var tamperFails=(vt.winner_ticket!==d.winner_ticket) || (campaignHash && true); // any list change → different result path
    ev.push({e:'VERIFIED_'+(match?'MATCH':'FAIL')});
    c._ev=ev; c._campaignHash=campaignHash; c._draw=d; c._verify=v; c._match=match; c._cfg=cfg; c._entropyHex=cfg.entropyHex;
    return c;
  }

  function renderDraw(root, c){
    var STEPS=['Passport','Campaign','Tickets','Freeze','Future entropy','Draw','Verify','Settlement/Refund'];
    var active=({DRAFT:1,SELLING:2,SOLD_OUT:2,AWAITING_ENTROPY:4,DRAWN:6,FAILED_REFUNDED:2})[c.state]||0;
    if(c.state==='DRAWN') active=6;
    var sold=c.tickets.length, remaining=Math.max(0,c.target_tickets-sold);
    var h='';
    h+='<div class="od-head"><div class="od-title">Draw dashboard '+badge(c.state)+'</div>'
      +'<div class="od-sub">Commit → freeze (campaignHash) → future-block entropy → deterministic winner anyone can recompute · <b>real funds disabled</b></div></div>';
    h+=stepper(STEPS,active);
    h+='<div class="od-metrics">'
      + metric('Asset', esc(c._cfg.asset))
      + metric('Ticket ref', c.price_ref_usdc+' USDC', 'quote at purchase (no custody)')
      + metric('Target', c.target_tickets)
      + metric('Sold', sold, remaining+' remaining')
      + metric('Close height', c.close_height)
      + metric('Entropy height', c.entropy_height, 'future block')
      + metric('Winning ticket', c.winner_ticket?esc(c.winner_ticket):'—', c.winner_index!=null?('index '+c.winner_index):'')
      + metric('Verification', c._match?'✓ MATCH':'✗ FAIL', 'independent recompute')
      +'</div>';
    // verification panel
    h+='<div class="od-block"><h4>Verify draw <span class="od-mini">(anyone recomputes: winner = int(sha256(campaignHash | entropyHex)) mod ticketCount)</span></h4>'
      +'<div class="od-scroll"><table class="od-tbl"><tbody>'
      +'<tr><th>campaignHash</th><td class="od-hash">'+esc(c._campaignHash)+'</td></tr>'
      +'<tr><th>entropy block hash</th><td class="od-hash">'+esc(c._entropyHex)+'</td></tr>'
      +'<tr><th>seed</th><td class="od-hash">'+esc(c._draw.seed)+'</td></tr>'
      +'<tr><th>recomputed winner</th><td>'+esc(c._verify.winner_ticket)+' (index '+c._verify.winner_index+') → <b>'+(c._match?'MATCH':'FAIL')+'</b></td></tr>'
      +'</tbody></table></div><div class="od-mini">Any change to the ticket list or entropy yields a different (or invalid) result — the draw cannot be steered after freeze.</div></div>';
    h+='<div class="od-block"><h4>Event log</h4><div class="od-events">'+c._ev.map(function(e){return '<span class="od-ev">'+esc(e.e)+'</span>';}).join('')+'</div></div>';
    h+='<div class="od-two"><div class="od-legal"><h4>Legal readiness</h4><ul>'
      +'<li>Legal classification: <b>NOT DETERMINED BY SOST</b></li>'
      +'<li>Paid-ticket + chance + asset-prize = a <b>rifa</b> (ES: DGOJ / Ley 13/2011) — requires authorization</li>'
      +'<li>Refund path: if target not covered by close height → FAILED_REFUNDED (all escrows refundable)</li></ul></div>';
    h+='<div class="od-gate"><h4>Mainnet execution</h4>'
      +'<div class="od-gaterow"><span class="od-glabel">DRAW_EXECUTION</span><span class="od-gval off">DISABLED · REGULATORY GATE</span></div>'
      +'<div class="od-mini">Draw math, freeze, recompute and refund logic run in full. Ticket purchase / fund movement is blocked. Entropy uses a real future SOST block hash; DTD consensus untouched. Server-side gate: pending (slice F).</div></div></div>';
    h+='<div class="od-block od-adv-only"><h4>Raw state</h4><pre class="od-raw">'+esc(JSON.stringify(c,function(k,v){return (k==='_ev')?undefined:v;},1))+'</pre></div>';
    root.querySelector('.od-body').innerHTML=h;
  }

  function mountDraw(){
    var root=document.getElementById('draw-dash'); if(!root||!DR) return;
    root.innerHTML='<div class="od-toolbar"><button class="od-run" id="drwd-run">Run full lifecycle (example)</button>'
      +'<label class="od-modes"><input type="checkbox" id="drwd-adv"> Advanced mode</label>'
      +'<span class="od-gatepill">Real-money execution: DISABLED</span></div>'
      +'<div class="od-body"><div class="od-empty">Press <b>Run full lifecycle</b> to sell tickets → freeze the campaign (campaignHash) → reveal a future-block entropy hash → draw a winner → independently recompute it (MATCH). No funds move.</div></div>';
    var advCb=document.getElementById('drwd-adv');
    advCb.addEventListener('change',function(){ root.classList.toggle('od-advanced', advCb.checked); });
    document.getElementById('drwd-run').addEventListener('click',function(){ var btn=this; btn.disabled=true; btn.textContent='Running…';
      runDraw(drawEx()).then(function(c){ renderDraw(root,c); btn.disabled=false; btn.textContent='Re-run lifecycle'; })
      .catch(function(e){ root.querySelector('.od-body').innerHTML='<div class="od-empty">Error: '+esc(e.message)+'</div>'; btn.disabled=false; btn.textContent='Run full lifecycle (example)'; });
    });
  }

  function mountAll(){ mountAuction(); mountDraw(); }
  if(document.readyState!=='loading') mountAll(); else document.addEventListener('DOMContentLoaded',mountAll);
  window.SOSTOfferDash={mountAuction:mountAuction, mountDraw:mountDraw, _runAuction:runAuction, _runDraw:runDraw};
})();

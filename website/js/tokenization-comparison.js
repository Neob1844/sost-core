/* SOST — Tokenization Industry Comparison renderer. Data-driven, honest, sourced. */
(function(){
  var D = window.SOST_TOKCMP; if(!D) return;
  var root = document.getElementById('tokcmp-root'); if(!root) return;
  var P = D.order, PL = {}; D.platforms.forEach(function(p){ PL[p.key]=p; });
  var CAT = D.categories;
  // curated 12-row executive overview (balanced: SOST strengths AND gaps)
  var OVERVIEW = ["Asset Passport / digital twin","Per-claim provenance","Legal enforceability layer",
    "Regulated issuance support","On-chain identity","Native on-chain asset issuance","Secondary trading",
    "Own Layer 1","Public verification","Custody integration","Auction (highest bidder)","Fiat / stablecoin settlement"];
  var STLABEL = {C:"CURRENT",G:"GATED / READY",F:"FUTURE"};
  var esc = function(s){ return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); };

  function stars(n){
    if(n===-1) return '<span class="tc-na" title="Not applicable to this platform’s model">N/A</span>';
    if(n===0)  return '<span class="tc-none" title="Not currently offered">○</span>';
    var s=''; for(var i=0;i<5;i++) s+= '<span class="tc-st'+(i<n?' on':'')+'">★</span>';
    return '<span class="tc-stars" aria-label="'+n+' of 5">'+s+'</span>';
  }
  function dot(b){ if(!b) return ''; var c={C:'c',G:'g',F:'f'}[b]||''; return '<span class="tc-dot '+c+'" title="'+STLABEL[b]+'"></span>'; }

  function dimsFor(cat){
    if(cat==='overview') return OVERVIEW.map(function(l){ return D.dimensions.find(function(x){return x.label===l;}); }).filter(Boolean);
    return D.dimensions.filter(function(x){ return x.cat===cat; });
  }

  function buildCards(){
    var h='<div class="tc-cards">';
    P.forEach(function(k){ var p=PL[k];
      h+='<div class="tc-card'+(k==='sost'?' sost':'')+'">'
        +'<div class="tc-cn">'+esc(p.name)+'</div>'
        +'<div class="tc-cf">'+esc(p.focus)+'</div>'
        +'<div class="tc-cm">'+esc(p.model)+'</div>'
        +'<div class="tc-cd">'+esc(p.diff)+'</div>'
        +'<div class="tc-cmat">'+esc(p.maturity)+'</div></div>';
    });
    return h+'</div>';
  }

  function buildTable(cat){
    var dims=dimsFor(cat);
    var h='<div class="tc-scroll"><table class="tc-tbl"><thead><tr><th class="tc-dimh">Dimension</th>';
    P.forEach(function(k){ h+='<th data-pk="'+k+'" class="'+(k==='sost'?'sost':'')+'">'+esc(PL[k].name)+'</th>'; });
    h+='</tr></thead><tbody>';
    dims.forEach(function(dm){
      h+='<tr><td class="tc-dim">'+esc(dm.label)+'</td>';
      P.forEach(function(k){ var c=dm.cells[k];
        h+='<td data-pk="'+k+'" class="tc-cell'+(k==='sost'?' sost':'')+'" tabindex="0" role="button" '
          +'data-p="'+k+'" data-d="'+esc(dm.label)+'" title="'+esc(PL[k].name+' — '+dm.label+': '+c[2])+'">'
          +stars(c[0])+dot(c[1])+'</td>';
      });
      h+='</tr>';
    });
    return h+'</tbody></table></div>';
  }

  function detail(pk,label){
    var dm=D.dimensions.find(function(x){return x.label===label;}); if(!dm)return;
    var c=dm.cells[pk], p=PL[pk];
    var srcs=p.sources.map(function(s){return '<a href="'+s[1]+'" target="_blank" rel="noopener">'+esc(s[0])+'</a>';}).join(' · ');
    var box=document.getElementById('tc-detail');
    box.innerHTML='<div class="tc-dh"><b>'+esc(p.name)+'</b> — '+esc(dm.label)+'</div>'
      +'<div class="tc-dscore">'+stars(c[0])+(c[1]?'<span class="tc-badge '+({C:'c',G:'g',F:'f'}[c[1]])+'">'+STLABEL[c[1]]+'</span>':'')+'</div>'
      +'<div class="tc-dwhy">'+esc(c[2])+'</div>'
      +'<div class="tc-dsrc"><span>Source:</span> '+srcs+'</div>'
      +'<div class="tc-dver">Capability coverage per documented rubric · last verified '+esc(D.verifiedAt)+'</div>';
    box.classList.add('open');
  }

  function applyFilter(sel){
    // sel = 'all' or a competitor key. SOST always shown.
    root.querySelectorAll('.tc-tbl [data-pk]').forEach(function(el){
      var k=el.getAttribute('data-pk');
      var show = (sel==='all') || (k==='sost') || (k===sel);
      el.style.display = show ? '' : 'none';
    });
  }

  function render(){
    var tabs=[['overview','Overview']].concat(CAT.filter(function(c){return c[0]!=='overview';}));
    var h='';
    h+='<div class="tc-head"><div class="tc-eyebrow">Tokenization Industry Landscape</div>';
    h+='<h2>Seven architectures. <span class="g">Different problems.</span> One detailed comparison.</h2>';
    h+='<div class="tc-plat">'+P.map(function(k){return '<span'+(k==='sost'?' class="sost"':'')+'>'+esc(PL[k].name.toUpperCase())+'</span>';}).join('<i>·</i>')+'</div>';
    h+='<div class="tc-note">Stars = documented capability coverage &amp; maturity per our rubric — <b>not</b> investment quality, company quality or regulatory approval. No total score and no “winner”: these platforms solve different problems. Click any cell for the reason and source.</div></div>';
    // cards
    h+=buildCards();
    // controls
    h+='<div class="tc-controls"><div class="tc-tabs" role="tablist">'
      +tabs.map(function(t,i){return '<button class="tc-tab'+(i===0?' active':'')+'" data-cat="'+t[0]+'" role="tab">'+esc(t[1])+'</button>';}).join('')
      +'</div><label class="tc-filter">Compare SOST with <select id="tc-sel"><option value="all">All platforms</option>'
      +P.filter(function(k){return k!=='sost';}).map(function(k){return '<option value="'+k+'">'+esc(PL[k].name)+'</option>';}).join('')
      +'</select></label></div>';
    // legend
    h+='<div class="tc-legend"><span class="tc-stars"><span class="tc-st on">★</span></span> supported (1–5) · <span class="tc-none">○</span> not offered · <span class="tc-na">N/A</span> not applicable &nbsp; | &nbsp; <span class="tc-dot c"></span> current · <span class="tc-dot g"></span> gated/ready · <span class="tc-dot f"></span> future</div>';
    // table mount
    h+='<div id="tc-table">'+buildTable('overview')+'</div>';
    h+='<div id="tc-detail" class="tc-detail">Select any cell above to see <b>why</b> a platform scores what it does, with its source.</div>';
    // how they do it
    h+='<div class="tc-block"><h3>How each platform approaches tokenization</h3><div class="tc-how">';
    var HOW={sost:"Asset → Claims → Provenance → Rights → Passport → Offering → SOST verification / settlement",
      securitize:"Issuer → regulated onboarding → security token → transfer-agent register → ATS trading → custody & settlement",
      tokeny:"Issuer → ONCHAINID identity → ERC-3643 token → on-chain compliance rules → controlled transfers",
      centrifuge:"Originator → pool → tokenized fund/credit → DeFi lenders → on-chain NAV & distribution",
      polymesh:"Verified identity → native regulated asset → protocol compliance → on-chain settlement",
      mattereum:"Physical asset → expert certification + legal warranties → Asset Passport → rwaNFT → arbitration-backed transfer",
      inx:"Issuer → regulated onboarding → security token → INX ATS → 24/7 secondary trading"};
    P.forEach(function(k){ h+='<div class="tc-howrow'+(k==='sost'?' sost':'')+'"><span class="tc-hn">'+esc(PL[k].name)+'</span><span class="tc-hf">'+esc(HOW[k])+'</span></div>'; });
    h+='</div></div>';
    // where SOST differs / where others ahead
    h+='<div class="tc-two"><div class="tc-block half"><h3>Where SOST takes a different approach</h3><ul class="tc-ul">'
      +['Typed claims recorded <b>before</b> any token exists','Per-claim provenance — who says each fact and whether it was independently verified','Deterministic Passport hash anyone can recompute (MATCH/FAIL)','A <b>Project</b> Passport can exist before the asset is built, then become an Asset Passport','Four offering engines (Tokenize · Auction · Draw · Project Funding) from one Passport','Its own PoW Layer 1, with network supply independent of any asset unit'].map(function(x){return '<li>'+x+'</li>';}).join('')
      +'</ul><div class="tc-mini">“Different”, not “better” — several of these also appear, in other forms, elsewhere.</div></div>';
    h+='<div class="tc-block half"><h3>Where established platforms are ahead today</h3><ul class="tc-ul warn">'
      +['Regulated issuance under real licences (Securitize, INX/Republic, Polymesh ecosystem)','KYC/AML &amp; on-chain investor identity (Tokeny ONCHAINID, Polymesh, Securitize)','Programmable transfer restrictions &amp; forced-transfer/recovery (Tokeny ERC-3643, Polymesh)','Regulated secondary trading &amp; order books (Securitize Markets, INX ATS)','Custody of tokenized securities (Securitize — FINRA-approved) & settlement vs stablecoins','Established liquidity &amp; institutional integrations (Centrifuge private credit, Securitize)'].map(function(x){return '<li>'+x+'</li>';}).join('')
      +'</ul><div class="tc-mini">SOST does not claim parity here — these are gated or future for SOST.</div></div></div>';
    // methodology & sources
    h+='<details class="tc-method"><summary>Methodology &amp; sources</summary><div class="tc-mbody">';
    h+='<p><b>Rubric.</b> ★★★★★ mature / strongly supported · ★★★★ strong · ★★★ meaningful / partial · ★★ limited · ★ minimal · ○ not currently offered · N/A not applicable to that platform’s model. Scores reflect <i>documented capability coverage</i>, verified against official sources on '+esc(D.verifiedAt)+'. SOST is scored on what is <b>implemented today</b>: roadmap items score ○/low and carry a FUTURE or GATED badge. No capability is penalised as “missing” when it is simply outside a platform’s purpose (marked N/A).</p>';
    h+='<div class="tc-srcs">'+P.map(function(k){var p=PL[k];
      return '<div class="tc-srcrow"><b>'+esc(p.name)+'</b> — '+p.sources.map(function(s){return '<a href="'+s[1]+'" target="_blank" rel="noopener">'+esc(s[0])+'</a>';}).join(' · ')+'</div>';
    }).join('')+'</div><div class="tc-mini">Last verified '+esc(D.verifiedAt)+'. Competitor capabilities evolve — verify current status with each vendor.</div></div></details>';
    root.innerHTML=h;

    // wiring
    root.querySelectorAll('.tc-tab').forEach(function(b){ b.addEventListener('click',function(){
      root.querySelectorAll('.tc-tab').forEach(function(x){x.classList.remove('active');}); b.classList.add('active');
      document.getElementById('tc-table').innerHTML=buildTable(b.getAttribute('data-cat'));
      applyFilter(document.getElementById('tc-sel').value); wireCells();
    }); });
    document.getElementById('tc-sel').addEventListener('change',function(){ applyFilter(this.value); });
    wireCells();
    // mobile default: focus SOST vs Securitize
    if(window.innerWidth<=760){ var s=document.getElementById('tc-sel'); s.value='securitize'; applyFilter('securitize'); }
  }
  function wireCells(){
    root.querySelectorAll('.tc-cell').forEach(function(c){
      var f=function(){ detail(c.getAttribute('data-p'), c.getAttribute('data-d')); };
      c.addEventListener('click',f);
      c.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){e.preventDefault();f();} });
    });
  }
  render();
})();

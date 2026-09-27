const PA = require(process.env.ROOT+'/js/dex-price-adapter.js');
const RFQ = require(process.env.ROOT+'/js/dex-rfq.js');
const SIM = require(process.env.ROOT+'/js/dex-liquidity-sim.js');
let P=0,F=0; function chk(c,m){ if(c){P++;} else {F++; console.log('  [FAIL] '+m);} }

(async ()=>{
  // --- Price adapter: lab returns non-executable simulated reference ---
  const a = PA.makeAdapter({source:null});
  const r = await a.getReference('SOST/USDC', 1000);
  chk(r.executable===false, 'adapter: lab reference is NOT executable');
  chk(r.simulated===true && r.status==='lab', 'adapter: labelled simulated/lab');
  // with a fresh CEX source, reference present but still not "executable" (RFQ provides executable)
  const src={fetchTicker:async()=>({bid:0.149,ask:0.151,last:0.15,depth:5000,volume24h:1e5,tsMs:1000,status:'trading',fees:{taker:10}})};
  const a2 = PA.makeAdapter({source:src, maxAgeMs:30000});
  const r2 = await a2.getReference('SOST/USDC', 1000);
  chk(r2.fresh===true && r2.bid===0.149 && r2.executable===false, 'adapter: fresh CEX reference, still not executable');
  const r3 = await a2.getReference('SOST/USDC', 999999); // stale
  chk(r3.fresh===false, 'adapter: stale reference flagged');

  // --- RFQ: validation, expiry, replay, double-accept ---
  const book = RFQ.makeBook({verify:()=>true});
  const q = {maker:'0xabc', nonce:1, amount:100, price:0.15, reservedInventory:100, expiry:2000};
  chk(book.validate(q,1000).ok, 'rfq: valid quote passes');
  chk(!book.validate({...q,expiry:500},1000).ok, 'rfq: expired quote rejected');
  chk(!book.validate({...q,reservedInventory:50},1000).ok, 'rfq: under-reserved rejected');
  chk(!RFQ.makeBook({verify:()=>false}).validate(q,1000).ok, 'rfq: bad signature rejected');
  chk(book.accept(q,1000).ok, 'rfq: first accept ok');
  chk(!book.accept(q,1000).ok, 'rfq: double-accept (replay) blocked');
  chk(!book.validate(q,1000).ok, 'rfq: re-validate after accept -> replay');

  // --- Liquidity simulator ---
  const sim = SIM.makeSim({usdc:1000, refPrice:0.15, spreadBps:150, maxQuoteUsd:100, feeBps:30});
  const st0 = sim.state();
  chk(Math.abs(st0.sost - 1000/0.15) < 1, 'sim: SOST reserve ~ $1000 at ref');
  chk(Math.abs(sim.exposureUsd() - 2000) < 5, 'sim: total exposure ~ $2000');
  // quote too big rejected
  chk(!sim.quote('buy', 10000, 0).ok, 'sim: over-max quote rejected');
  // a valid buy quote reserves SOST
  const bq = sim.quote('buy', 100, 0); // taker buys 100 SOST
  chk(bq.ok && bq.price>0.15, 'sim: buy quote priced above ref (spread)');
  chk(sim.state().reserved.sost>=100, 'sim: buy quote reserves SOST inventory');
  // fill reduces SOST, adds USDC, books fee
  sim.fill(bq);
  chk(sim.state().sost < st0.sost, 'sim: fill reduced SOST inventory');
  chk(sim.state().feesUsd > 0, 'sim: fee booked on fill');
  chk(sim.state().reserved.sost < 1, 'sim: reservation released on fill');
  // stale reference suspends
  sim.setReference(0.15, true); chk(!sim.quote('buy',10,0).ok, 'sim: suspended on stale reference');
  sim.setReference(0.15, false); chk(sim.quote('buy',10,0).ok, 'sim: resumes when reference fresh');
  // adverse shock changes exposure
  const e0=sim.exposureUsd(); sim.shockReference(-20); chk(sim.exposureUsd()<e0, 'sim: adverse -20% shock lowers exposure');
  // depletion suspends
  const sim2 = SIM.makeSim({usdc:120, refPrice:0.15, spreadBps:0, maxQuoteUsd:1000, feeBps:0});
  const sq=sim2.quote('sell', 800, 0); if(sq.ok) sim2.fill(sq); // spend most USDC buying SOST
  chk(sim2.state().suspended===true, 'sim: suspends when inventory depleted');

  console.log('DEX PHASE-4 TESTS: PASS='+P+' FAIL='+F);
  process.exit(F?1:0);
})();

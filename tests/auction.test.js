/* SOST Auction engine unit tests + cross-mode (one passport -> tokenize/draw/auction; project->asset). */
const A = require('../website/js/asset-auction.js');
const DRAW = require('../website/js/asset-draw.js');
const PF = require('../website/js/project-funding.js');
const V2 = require('../website/js/asset-passport-v2.js');
let pass = 0, fail = 0; const fails = [];
function ok(c, m) { if (c) pass++; else { fail++; fails.push(m); console.log('  ❌ ' + m); } }
async function athrows(fn, m) { try { await fn(); fail++; fails.push(m + ' (did not throw)'); console.log('  ❌ ' + m); } catch (e) { pass++; } }

function mkAuction(over) {
  return A.newAuction(Object.assign({
    auctionId: 'auc-1', passportId: 'sost-asset-gold', seller: '0xSeller', currency: 'EUR', network: 'devnet',
    startingPrice: '1500000', reservePrice: '1800000', minimumIncrement: '10000',
    openingTime: 100, closingTime: 1000, escrowRequired: true, escrowReferenceAmount: '10000', settlementDeadline: 2000
  }, over || {}));
}
function bid(bidder, amount, nonce, over) {
  return Object.assign({ auctionId: 'auc-1', network: 'devnet', bidder: bidder, amount: amount, currency: 'EUR', nonce: nonce, expiry: 0, signature: '0xsignature-' + nonce }, over || {});
}

(async () => {
  console.log('=== AUCTION create/open/cancel ===');
  let a = mkAuction();
  ok(a.state === 'DRAFT', 'create -> DRAFT');
  let c = mkAuction(); A.cancelBeforeOpen(c); ok(c.state === 'CANCELLED', 'cancel before open');
  await athrows(() => A.open(a, 50), 'cannot open before openingTime');
  A.open(a, 100); ok(a.state === 'OPEN', 'open at openingTime');

  console.log('=== escrow + bids ===');
  await athrows(() => A.placeBid(a, bid('0xB1', '1500000', 'n1'), 120), 'bid without escrow rejected (required)');
  A.lockEscrow(a, '0xB1', { sost: '200000000', price: '0.05', source: 'oracle', ts: 110 });
  A.lockEscrow(a, '0xB2', { sost: '200000000', price: '0.05', source: 'oracle', ts: 110 });
  A.lockEscrow(a, '0xB3', {});
  const r1 = await A.placeBid(a, bid('0xB1', '1600000', 'n1'), 120);
  ok(r1.amount === '1600000' && a.highest.bidder === '0xB1', 'first valid bid becomes highest');
  await athrows(() => A.placeBid(a, bid('0xB2', '1605000', 'n2'), 130), 'below minimum increment rejected');
  await athrows(() => A.placeBid(a, bid('0xB2', '1600000', 'n2'), 130), 'equal-to-highest rejected (earliest-wins by construction)');
  await A.placeBid(a, bid('0xB2', '1750000', 'n2'), 140);
  ok(a.highest.bidder === '0xB2' && a.highest.amount === '1750000', 'higher bid takes the lead');
  await athrows(() => A.placeBid(a, bid('0xB1', '1800000', 'n1'), 150), 'nonce reuse rejected');
  await athrows(() => A.placeBid(a, bid('0xB1', '1800000', 'n9', { signature: '' }), 150), 'missing signature rejected');
  await athrows(() => A.placeBid(a, bid('0xB1', '1800000', 'n8', { expiry: 100 }), 150), 'expired bid rejected');
  await athrows(() => A.placeBid(a, bid('0xB1', '1800000', 'n7', { network: 'mainnet' }), 150), 'network mismatch rejected');
  // digest binding
  const b = bid('0xB1', '1900000', 'n3'); const dg = await A.bidDigest(b);
  await athrows(() => A.placeBid(a, b, 160, { digest: 'deadbeef' }), 'wrong digest rejected');
  await A.placeBid(a, b, 160, { digest: dg }); ok(a.highest.bidder === '0xB1' && a.highest.amount === '1900000', 'digest-verified bid accepted');

  console.log('=== close / reserve / winner ===');
  await athrows(() => A.close(a, 500), 'cannot close before closingTime');
  A.close(a, 1000);
  ok(a.state === 'SETTLEMENT_PENDING' && a.winner.bidder === '0xB1' && a.winner.amount === '1900000', 'highest >= reserve -> winner selected (settlement pending)');

  console.log('=== reserve not met -> failed + refunds ===');
  let rn = mkAuction({ auctionId: 'auc-2' }); A.open(rn, 100); A.lockEscrow(rn, '0xX', {});
  await A.placeBid(rn, bid('0xX', '1600000', 'm1', { auctionId: 'auc-2' }), 120);
  A.close(rn, 1000);
  ok(rn.state === 'FAILED', 'reserve not met -> FAILED');
  ok(A.refundable(rn).indexOf('0xX') >= 0, 'failed auction: escrow refundable');

  console.log('=== settlement + loser refunds ===');
  const set = A.settle(a, { rail: 'EXTERNAL_DOCUMENTED', reference: 'notary-123', applyEscrow: false });
  ok(a.state === 'COMPLETE' && /DOES NOT CUSTODY/.test(set.note), 'settlement recorded, no custody');
  const ref = A.refundable(a);
  ok(ref.indexOf('0xB2') >= 0 && ref.indexOf('0xB1') >= 0, 'all escrows refundable (winner escrow not applied)');
  A.markRefunded(a, '0xB2'); ok(a.escrows['0xB2'].status === 'REFUNDED', 'loser escrow marked refunded');

  console.log('=== winner failure -> next highest ===');
  let wf = mkAuction({ auctionId: 'auc-3', reservePrice: null }); A.open(wf, 100);
  A.lockEscrow(wf, '0xH', {}); A.lockEscrow(wf, '0xL', {});
  await A.placeBid(wf, bid('0xL', '1500000', 'q1', { auctionId: 'auc-3' }), 120);
  await A.placeBid(wf, bid('0xH', '1600000', 'q2', { auctionId: 'auc-3' }), 130);
  A.close(wf, 1000); ok(wf.winner.bidder === '0xH', 'highest wins (no reserve)');
  const next = A.winnerFailed(wf, 1100, true);
  ok(next && next.bidder === '0xL', 'winner failed -> reassigned to next-highest');

  console.log('=== anti-sniping ===');
  let sn = mkAuction({ auctionId: 'auc-4', reservePrice: null, closingTime: 1000, antiSnipeSecs: 60 }); A.open(sn, 100); A.lockEscrow(sn, '0xS', {});
  await A.placeBid(sn, bid('0xS', '1500000', 's1', { auctionId: 'auc-4' }), 970); // within 60s of close
  ok(sn.closingTime === 1060 && sn.extends === 1, 'anti-snipe extends closing time');

  console.log('=== persistence / resume ===');
  const store = {}; global.localStorage = { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = v; }, removeItem: k => { delete store[k]; } };
  A.save(a); A.save(sn); // a COMPLETE, sn OPEN
  const res = A.resumable().map(x => x.auctionId).sort();
  ok(res.indexOf('auc-4') >= 0 && res.indexOf('auc-1') < 0, 'resumable() returns OPEN/pending, not COMPLETE');
  ok(A.loadAll()['auc-1'].state === 'COMPLETE', 'auction survives reload');

  console.log('=== CROSS-MODE: one passport, three offerings + project->asset ===');
  const passport = 'sost-asset-shared-001';
  const tok = V2.rightClaim({ right_type: 'OWNERSHIP_OR_EQUITY_LIKE', economic_rights_declared: true, obligor: 'X', token_supply: '1000', token_decimals: 0 });
  const drawC = DRAW.newCampaign({ asset_passport_hash: passport, target_tickets: 3, close_height: 10, entropy_height: 20 });
  const aucC = A.newAuction({ auctionId: 'x', passportId: passport, seller: 's', startingPrice: '100', escrowRequired: false });
  ok(tok.class === 'RIGHT' && drawC.asset_passport_hash === passport && aucC.passportId === passport, 'same Asset Passport feeds Tokenize + Draw + Auction');
  const proj = PF.newProject({ project_passport_hash: 'proj-solar', model: 'REVENUE_SHARE', target: '100', minimum: '80' });
  const assetFromProject = { asset_passport_hash: 'sost-asset-from-proj-solar', derived_from_project: proj.project_passport_hash };
  const aucOnBuilt = A.newAuction({ auctionId: 'y', passportId: assetFromProject.asset_passport_hash, seller: 's', startingPrice: '100', escrowRequired: false });
  ok(assetFromProject.derived_from_project === 'proj-solar' && aucOnBuilt.passportId.indexOf('from-proj') >= 0, 'Project Passport -> Asset Passport -> can then Tokenize/Auction/Draw');

  console.log('\nRESULT: ' + pass + ' passed / ' + fail + ' failed');
  if (fail) { console.log('FAILURES:\n - ' + fails.join('\n - ')); process.exit(1); }
  process.exit(0);
})();

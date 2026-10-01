/* SOST offering models — verifiable Draw engine + Project Funding engine unit tests. */
const DRAW = require('../website/js/asset-draw.js');
const PF = require('../website/js/project-funding.js');
let pass = 0, fail = 0; const fails = [];
function ok(c, m) { if (c) pass++; else { fail++; fails.push(m); console.log('  ❌ ' + m); } }
async function athrows(fn, m) { try { await fn(); fail++; fails.push(m + ' (did not throw)'); console.log('  ❌ ' + m); } catch (e) { pass++; } }

(async () => {
  console.log('=== ASSET DRAW (verifiable) ===');
  let c = DRAW.newCampaign({ asset_passport_hash: 'sost-asset-abc', target_tickets: 5, price_ref_usdc: '20', network: 'devnet', close_height: 1000, entropy_height: 1010 });
  ok(c.state === 'DRAFT', 'draw draft');
  for (let i = 1; i <= 4; i++) DRAW.sellTicket(c, 'GOLD-' + i, 'buyer' + i);
  ok(c.state === 'SELLING' && c.tickets.length === 4, 'selling, 4 tickets');
  await athrows(() => DRAW.freeze(c), 'cannot freeze before target covered');
  DRAW.sellTicket(c, 'GOLD-5', 'buyer5');
  ok(c.state === 'SOLD_OUT', 'sold out at target (5/5)');
  await athrows(() => DRAW.sellTicket(c, 'GOLD-5', 'x'), 'duplicate ticket rejected');
  const h1 = await DRAW.freeze(c);
  ok(/^[0-9a-f]{64}$/.test(h1) && c.state === 'AWAITING_ENTROPY', 'freeze -> campaignHash + AWAITING_ENTROPY');
  // entropy must come from a block AT/AFTER the announced height
  await athrows(() => DRAW.draw(c, 'deadbeefdeadbeef', 1009), 'draw rejects entropy before announced height');
  const res = await DRAW.draw(c, 'a'.repeat(64), 1010);
  ok(c.state === 'DRAWN' && res.winner_index >= 0 && res.winner_index < 5, 'draw picks a valid winner index');
  const v = await DRAW.verify(h1, c.tickets, 'a'.repeat(64));
  ok(v.winner_index === res.winner_index && v.winner_ticket === res.winner_ticket, 'ANYONE recomputes the same winner (verifiable)');
  const v2 = await DRAW.verify(h1, c.tickets, 'b'.repeat(64));
  ok(v2.winner_index !== undefined, 'different entropy -> recomputable (independent seed)');
  // freeze determinism
  let c2 = DRAW.newCampaign({ asset_passport_hash: 'sost-asset-abc', target_tickets: 5, close_height: 1000, entropy_height: 1010 });
  ['GOLD-1', 'GOLD-2', 'GOLD-3', 'GOLD-4', 'GOLD-5'].forEach((t, i) => DRAW.sellTicket(c2, t, 'b' + i));
  ok((await DRAW.freeze(c2)) === h1, 'campaignHash deterministic (same tickets/params -> same hash)');
  // refund if unsold by deadline
  let c3 = DRAW.newCampaign({ asset_passport_hash: 'x', target_tickets: 10, close_height: 500, entropy_height: 520 });
  DRAW.sellTicket(c3, 'T1', 'a');
  ok(DRAW.failIfUnsold(c3, 500) === true && c3.state === 'FAILED_REFUNDED', 'undersold by deadline -> FAILED_REFUNDED (all refund)');

  console.log('=== PROJECT FUNDING ===');
  await athrows(async () => PF.newProject({ project_passport_hash: 'p', model: 'BOGUS', target: '100' }), 'invalid model rejected');
  await athrows(async () => PF.newProject({ project_passport_hash: 'p', model: 'DEBT', target: '100', minimum: '200' }), 'minimum > target rejected');
  await athrows(async () => PF.newProject({ project_passport_hash: 'p', model: 'DEBT', target: '100', milestones: [{ pct: 40 }, { pct: 40 }] }), 'milestones not summing 100 rejected');
  let p = PF.newProject({ project_passport_hash: 'proj-solar', model: 'REVENUE_SHARE', right_desc: '8% revenue / 10y', target: '200000000', minimum: '150000000', currency: 'EUR', settlement_rail: 'SOST', token_symbol: 'SOLAR-X', token_supply: '200000', deadline: 1000, milestones: [{ pct: 15, desc: 'permits' }, { pct: 25, desc: 'construction start' }, { pct: 35, desc: 'equipment' }, { pct: 20, desc: 'commissioning' }, { pct: 5, desc: 'operation' }] });
  ok(p.state === 'DRAFT' && p.milestones.length === 5, 'project created, 5 milestones');
  PF.commit(p, '120000000'); PF.commit(p, '40000000');
  ok(p.committed === '160000000' && p.funders === 2, 'commits accumulate + funder count');
  ok(Math.abs(PF.pct(p) - 80) < 0.001, 'pct funded = 80%');
  // all-or-nothing success (>= minimum 150M)
  ok(PF.closeWindow(p, 1000) === 'FUNDED', 'closeWindow >= minimum -> FUNDED');
  PF.activate(p);
  await athrows(async () => PF.release(p, 0), 'cannot release an unverified milestone');
  PF.verifyMilestone(p, 0); const r0 = PF.release(p, 0);
  ok(r0.tranche === '30000000' && p.released === '30000000', 'milestone 0 (15% of 200M) releases 30M');
  await athrows(async () => { PF.verifyMilestone(p, 2); PF.release(p, 2); }, 'out-of-order release rejected (prev not released)');
  const acc = PF.accounting(p);
  ok(acc.escrowed === '130000000' && acc.released === '30000000', 'accounting: funded 160M - released 30M = escrowed 130M');
  ok(/SOST price risk/.test(acc.note), 'SOST-denominated risk noted (no fake stability)');
  // failure path
  let pf = PF.newProject({ project_passport_hash: 'p2', model: 'DEBT', target: '100000', minimum: '80000', deadline: 500 });
  PF.commit(pf, '50000');
  ok(PF.closeWindow(pf, 500) === 'FAILED_REFUND', 'under minimum by deadline -> FAILED_REFUND');

  console.log('\nRESULT: ' + pass + ' passed / ' + fail + ' failed');
  if (fail) { console.log('FAILURES:\n - ' + fails.join('\n - ')); process.exit(1); }
  process.exit(0);
})();

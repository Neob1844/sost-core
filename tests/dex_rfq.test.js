/* SOST DEX RFQ core — unit tests (offer digest, binding/replay/expiry, state machine, reconcile, persistence). */
const D = require('../website/js/dex-rfq.js');
let pass = 0, fail = 0; const fails = [];
function ok(c, m) { if (c) pass++; else { fail++; fails.push(m); console.log('  ❌ ' + m); } }
function throws(fn, m) { try { fn(); fail++; fails.push(m + ' (did not throw)'); console.log('  ❌ ' + m); } catch (e) { pass++; } }

const baseOffer = {
  maker: '0xMaker', pay_chain: 'SOST', pay_asset: 'SOST', pay_amount: '100000000',
  recv_chain: 'EVM', recv_asset: 'USDC', recv_amount: '250000000',
  maker_receive_address: '0xMakerRecv', min_confirmations: 3, refund_timeout: 144,
  expiry: 2000000000, nonce: '1', network: 'mainnet'
};

(async () => {
  console.log('=== 1. CANONICAL OFFER + DIGEST ===');
  const d1 = await D.offerDigest(baseOffer);
  const d2 = await D.offerDigest(JSON.parse(JSON.stringify(baseOffer)));
  ok(/^[0-9a-f]{64}$/.test(d1), 'digest is sha256 hex');
  ok(d1 === d2, 'digest deterministic (same offer -> same digest)');
  const changed = Object.assign({}, baseOffer, { recv_amount: '250000001' });
  ok((await D.offerDigest(changed)) !== d1, 'one-unit change -> different digest (tamper-evident)');
  // amount as float must be rejected by canon
  throws(() => D.canon({ a: 1.5 }), 'canon rejects float');

  console.log('=== 2. VALIDATION / BINDING ===');
  ok(D.validateOffer(baseOffer, { now: 1000 }), 'valid offer passes');
  throws(() => D.validateOffer(Object.assign({}, baseOffer, { pay_chain: 'EVM', recv_chain: 'EVM' })), 'same-chain rejected');
  throws(() => D.validateOffer(Object.assign({}, baseOffer, { pay_amount: '0' })), 'zero pay amount rejected');
  throws(() => D.validateOffer(Object.assign({}, baseOffer, { min_confirmations: 0 })), '0-conf rejected');
  throws(() => D.validateOffer(Object.assign({}, baseOffer, { network: 'bogus' })), 'bad network rejected');
  throws(() => D.validateOffer(baseOffer, { now: 2000000001 }), 'expired offer rejected at now');
  ok(D.isExpired(baseOffer, 2000000001) === true && D.isExpired(baseOffer, 1) === false, 'isExpired boundary');

  console.log('=== 3. REPLAY / DUPLICATE ACCEPTANCE ===');
  const seen = D.makeSeenSet();
  ok(seen.accept(baseOffer) === true, 'first acceptance ok');
  ok(seen.accept(baseOffer) === false, 'same (maker,nonce) rejected (replay/double-accept)');
  ok(seen.accept(Object.assign({}, baseOffer, { nonce: '2' })) === true, 'new nonce accepted');

  console.log('=== 4. HASHLOCK (sha256 of client preimage) ===');
  const pre = 'ab'.repeat(32);
  const hl = await D.hashlock(pre);
  ok(/^[0-9a-f]{64}$/.test(hl), 'hashlock is sha256 hex');
  ok(hl === (await D.sha256Hex(new Uint8Array(pre.match(/../g).map(h => parseInt(h, 16))))), 'hashlock == sha256(preimage bytes)');
  let hlThrew=false; try { await D.hashlock('xyz'); } catch(e){ hlThrew=true; } ok(hlThrew, 'bad preimage rejected');

  console.log('=== 5. STATE MACHINE ===');
  let s = D.newSwap('swap1', baseOffer);
  ok(s.state === 'DRAFT', 'new swap is DRAFT');
  D.applyTransition(s, 'OFFERED'); D.applyTransition(s, 'ACCEPTED'); D.applyTransition(s, 'INITIATOR_LOCKING'); D.applyTransition(s, 'INITIATOR_LOCKED');
  ok(s.state === 'INITIATOR_LOCKED', 'legal path DRAFT->...->INITIATOR_LOCKED');
  ok(D.applyTransition(s, 'INITIATOR_LOCKED').state === 'INITIATOR_LOCKED', 'transition idempotent (no-op to same state)');
  throws(() => D.applyTransition(s, 'COMPLETE'), 'illegal jump INITIATOR_LOCKED->COMPLETE rejected');
  D.applyTransition(s, 'COUNTERPARTY_LOCKING'); D.applyTransition(s, 'COUNTERPARTY_LOCKED'); D.applyTransition(s, 'CLAIMABLE'); D.applyTransition(s, 'CLAIMING'); D.applyTransition(s, 'COMPLETE');
  ok(s.state === 'COMPLETE' && D.isTerminal('COMPLETE'), 'reaches COMPLETE (terminal)');
  throws(() => D.applyTransition(s, 'REFUND_AVAILABLE'), 'no transition out of terminal COMPLETE');

  console.log('=== 6. RECONCILE (on-chain truth wins) ===');
  let r = D.newSwap('swap2', baseOffer); D.applyTransition(r, 'OFFERED'); D.applyTransition(r, 'ACCEPTED');
  D.reconcile(r, { initiatorLocked: true });
  ok(r.state === 'INITIATOR_LOCKED' && r.reconciled, 'reconcile advances to on-chain INITIATOR_LOCKED');
  D.reconcile(r, { counterpartyLocked: true });
  ok(r.state === 'CLAIMABLE', 'reconcile -> CLAIMABLE when counterparty locked');
  D.reconcile(r, { claimed: true });
  ok(r.state === 'COMPLETE', 'reconcile -> COMPLETE when chain shows claimed (truth beats local)');
  let rf = D.newSwap('swap3', baseOffer); D.applyTransition(rf, 'OFFERED'); D.applyTransition(rf, 'ACCEPTED'); D.applyTransition(rf, 'INITIATOR_LOCKING'); D.applyTransition(rf, 'INITIATOR_LOCKED');
  D.reconcile(rf, { expiredByTimeout: true });
  ok(rf.state === 'REFUND_AVAILABLE', 'reconcile -> REFUND_AVAILABLE on timeout');
  D.reconcile(rf, { refunded: true });
  ok(rf.state === 'REFUNDED', 'reconcile -> REFUNDED when chain shows refunded');

  console.log('=== 7. PERSISTENCE / RESUME (localStorage shim) ===');
  const store = {}; global.localStorage = { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = v; }, removeItem: k => { delete store[k]; } };
  let a = D.newSwap('A', baseOffer); D.applyTransition(a, 'OFFERED'); D.saveSwap(a);
  let b = D.newSwap('B', baseOffer); D.applyTransition(b, 'OFFERED'); D.applyTransition(b, 'ACCEPTED'); D.applyTransition(b, 'INITIATOR_LOCKING'); D.applyTransition(b, 'INITIATOR_LOCKED'); D.saveSwap(b);
  let done = D.newSwap('C', baseOffer); done.state = 'COMPLETE'; D.saveSwap(done);
  const res = D.resumable().map(s => s.id).sort();
  ok(JSON.stringify(res) === JSON.stringify(['A', 'B']), 'resumable() returns only non-terminal swaps (A,B not C)');
  ok(D.loadAll()['B'].state === 'INITIATOR_LOCKED', 'swap survives reload (persisted state)');

  console.log('\nRESULT: ' + pass + ' passed / ' + fail + ' failed');
  if (fail) { console.log('FAILURES:\n - ' + fails.join('\n - ')); process.exit(1); }
  process.exit(0);
})();

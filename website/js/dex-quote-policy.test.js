/* Headless tests for the DEX quote/RFQ policy (pure logic).
 * Covers: quote expiry (state flips, not executable), cancel-before-funding
 * allowed, cancel-after-funding REJECTED, stale-quote rejected, price locked
 * through reservation, modified-quote (digest/nonce) rejected, plus the sha256
 * sanity vector and limit-order expiry presets.
 *
 * NOTE: timeout / refund / counterparty-disappears / page-reload are covered by
 * scripts/e2e_sost_eth_devnet.sh + the devnet-flow resume/reconcile logic — not
 * duplicated here (this file is the PURE policy layer only).
 *
 * Run: node website/js/dex-quote-policy.test.js
 */
var P = require('./dex-quote-policy.js');
var pass = 0, fail = 0;
function ok(n, c) { if (c) { pass++; } else { fail++; console.log('  FAIL:', n); } }
function throws(fn) { try { fn(); return false; } catch (e) { return true; } }

var T0 = 1700000000000; // fixed "now" (ms) for deterministic expiry math

// --- sha256 sanity vector (proves the integrity hash is a real SHA-256) ------
ok('sha256("abc") vector', P.sha256hex('abc') === 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
ok('sha256("") vector', P.sha256hex('') === 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');

// --- a firm quote carries every required field + a 90s default lifetime ------
var q = P.makeQuote({ pair: 'SOST/ETH', side: 'sell', amount: '1000', price: '1', counterparty: 'anvil0' }, T0);
['pair', 'side', 'amount', 'price', 'minimumReceived', 'counterparty', 'nonce', 'created_at', 'expires_at'].forEach(function (k) {
  ok('quote has field ' + k, q[k] != null);
});
ok('default lifetime is 90s', (q.expires_at - q.created_at) === 90);
ok('quote starts FIRM', q.state === 'FIRM');
ok('minimumReceived defaults to amount', q.minimumReceived === '1000');

// --- quote EXPIRES: state flips and it is no longer executable ---------------
ok('executable at t=0', P.isExecutable(q, T0));
ok('executable at t=89s', P.isExecutable(q, T0 + 89 * 1000));
ok('countdown shows 01:30 at t=0', P.formatCountdown(P.remainingSecs(q, T0)) === '01:30');
ok('countdown shows 00:00 at expiry', P.formatCountdown(P.remainingSecs(q, T0 + 90 * 1000)) === '00:00');
P.refreshState(q, T0 + 90 * 1000);
ok('state flips to EXPIRED at expires_at', q.state === 'EXPIRED');
ok('NOT executable once expired', !P.isExecutable(q, T0 + 90 * 1000));
ok('refreshState never un-expires', (P.refreshState(q, T0), q.state === 'EXPIRED'));

// --- STALE quote is rejected by verifyQuote ----------------------------------
var qs = P.makeQuote({ pair: 'SOST/ETH', side: 'sell', amount: '5', price: '1' }, T0);
ok('fresh quote verifies', P.verifyQuote(qs, T0).ok);
var vStale = P.verifyQuote(qs, T0 + 91 * 1000);
ok('stale quote rejected', !vStale.ok && /stale|expired/i.test(vStale.reason));

// --- MODIFIED quote (price/amount/expiry/nonce tamper) is rejected -----------
function tamper(mut) { var c = JSON.parse(JSON.stringify(q2)); mut(c); return c; }
var q2 = P.makeQuote({ pair: 'SOST/ETH', side: 'sell', amount: '1000', price: '2', counterparty: 'anvil0' }, T0);
ok('untampered quote verifies', P.verifyQuote(q2, T0).ok);
ok('price tamper rejected', !P.verifyQuote(tamper(function (c) { c.price = '999'; }), T0).ok);
ok('amount tamper rejected', !P.verifyQuote(tamper(function (c) { c.amount = '1'; }), T0).ok);
ok('expiry tamper rejected', !P.verifyQuote(tamper(function (c) { c.expires_at = c.expires_at + 86400; }), T0).ok);
ok('nonce tamper rejected', !P.verifyQuote(tamper(function (c) { c.nonce = 'forged'; }), T0).ok);
ok('counterparty tamper rejected', !P.verifyQuote(tamper(function (c) { c.counterparty = 'evil'; }), T0).ok);
ok('missing-digest quote rejected', !P.verifyQuote(tamper(function (c) { delete c.digest; }), T0).ok);

// --- PRICE LOCKED THROUGH RESERVATION: no price change slips through ---------
var q3 = P.makeQuote({ pair: 'SOST/ETH', side: 'sell', amount: '1000', price: '3' }, T0);
var reservation = P.reserveQuote(q3, T0);
ok('reserve marks quote reserved', q3.reserved === true);
ok('reservation pins the price', reservation.price === '3');
ok('reserved quote still matches reservation', P.assertUnchanged(reservation, q3));
ok('repriced quote rejected post-reservation', throws(function () {
  var repriced = P.makeQuote({ pair: 'SOST/ETH', side: 'sell', amount: '1000', price: '7' }, T0); // different price => different digest
  P.assertUnchanged(reservation, repriced);
}));
ok('reserving a stale quote throws', throws(function () { var old = P.makeQuote({ pair: 'SOST/ETH', side: 'sell', amount: '1', price: '1' }, T0); P.reserveQuote(old, T0 + 100 * 1000); }));

// --- CANCELLATION state machine ----------------------------------------------
ok('OPEN cancelable', P.canCancel('OPEN'));
ok('SIGNED_OFFER cancelable', P.canCancel('SIGNED_OFFER'));
ok('QUOTE_RESERVED cancelable', P.canCancel('QUOTE_RESERVED'));
ok('FUNDED NOT cancelable', !P.canCancel('FUNDED'));

var o1 = { orderState: 'QUOTE_RESERVED' };
P.cancelOrder(o1);
ok('cancel-before-funding allowed (-> CANCELLED)', o1.orderState === 'CANCELLED');

var o2 = { orderState: 'FUNDED' };
var refused = false, msg = '';
try { P.cancelOrder(o2); } catch (e) { refused = true; msg = e.message; }
ok('cancel-after-funding REJECTED', refused && o2.orderState === 'FUNDED');
ok('rejection message is clear (SETTLE/REFUND)', /SETTLE|REFUND|funded/i.test(msg));
ok('availableActions(FUNDED) = SETTLE/REFUND', P.availableActions('FUNDED').join(',') === 'SETTLE,REFUND');
ok('availableActions(OPEN) = CANCEL', P.availableActions('OPEN').join(',') === 'CANCEL');

// --- LIMIT orders: selectable expiry presets + cancelable while not funded ---
ok('presets are 15m/1h/24h/7d/GTC', Object.keys(P.EXPIRY_PRESETS).join(',') === '15m,1h,24h,7d,GTC');
var lo = P.newLimitOrder({ side: 'sell', amount: '100', price: '5', quoteAsset: 'USDC', expiry: '15m' }, T0);
ok('limit order expires_at = +15m', lo.expires_at === lo.created_at + 900);
ok('limit label reads Sell ... at >=', /Sell 100 SOST at ≥ 5 USDC/.test(P.limitLabel(lo)));
ok('limit order cancelable while not funded', P.canCancel(lo.orderState));
ok('limit status EXPIRED after window', P.limitStatus(lo, T0 + 16 * 60 * 1000) === 'EXPIRED');
var gtc = P.newLimitOrder({ side: 'buy', amount: '10', price: '4', expiry: 'GTC' }, T0);
ok('GTC never expires', gtc.expires_at === null && P.limitStatus(gtc, T0 + 3650 * 86400 * 1000) === 'SIGNED_OFFER');
ok('invalid expiry preset throws', throws(function () { P.newLimitOrder({ side: 'buy', amount: '1', price: '1', expiry: '99y' }, T0); }));

// --- market/RFQ fails closed with no quote source ----------------------------
P.requestFirmQuote(null, { pair: 'SOST/ETH', side: 'sell', amount: '1' }, T0)
  .then(function () { ok('no-source market order fails closed', false); finish(); })
  .catch(function (e) { ok('no-source market order fails closed', /fail-closed|no maker|quote source/i.test(e.message)); finish(); });

function finish() {
  console.log('DEX-QUOTE-POLICY TESTS: PASS=' + pass + ' FAIL=' + fail);
  process.exit(fail ? 1 : 0);
}

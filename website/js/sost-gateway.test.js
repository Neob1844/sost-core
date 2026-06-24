/* Dependency-free unit tests for the SOST Gateway skeleton.
 * Run: node website/js/sost-gateway.test.js
 *
 * Covers: flag OFF hides everything; dev flag reveals UI; no funds sent; no real network;
 * no secret stored; address/amount/reference validation; module risk-separation.
 */
'use strict';
var G = require('./sost-gateway.js');
var assert = require('assert');
var n = 0;
function t(name, fn) { fn(); n++; }

var ADDR1 = 'sost1' + '0'.repeat(40);
var ADDR2 = 'sost1' + 'a'.repeat(40);
var ADDR3 = 'sost1' + 'b'.repeat(40);
var P2SH  = 'sost3' + 'c'.repeat(40);

function resetFlags() {
  G._setFlags({ SOST_GATEWAY_ENABLED: false, SOST_GATEWAY_HOLD_ENABLED: false,
    SOST_GATEWAY_PAY_ENABLED: false, SOST_GATEWAY_ESCROW_ENABLED: false,
    SOST_GATEWAY_ATOMIC_SWAP_ENABLED: false, SOST_GATEWAY_POPC_BOND_ENABLED: false });
}

// ---- 1. Flags default OFF: nothing visible, nothing enabled --------------------
t('all flags default to false', function () {
  resetFlags();
  var f = G.flags();
  Object.keys(f).forEach(function (k) { assert.strictEqual(f[k], false, k + ' must default false'); });
});

t('flag OFF hides the whole gateway and every module', function () {
  resetFlags();
  assert.strictEqual(G.gatewayVisible(), false);
  assert.deepStrictEqual(G.visibleModules(), []);
  assert.strictEqual(G.Hold.isEnabled(), false);
  assert.strictEqual(G.Pay.isEnabled(), false);
  assert.strictEqual(G.Escrow.isEnabled(), false);
  assert.strictEqual(G.Swap.isEnabled(), false);
  assert.strictEqual(G.PopcBond.isEnabled(), false);
});

t('module flag ON but master OFF still hides everything', function () {
  resetFlags();
  G._setFlags({ SOST_GATEWAY_PAY_ENABLED: true });   // master still false
  assert.strictEqual(G.Pay.isEnabled(), false);
  assert.deepStrictEqual(G.visibleModules(), []);
});

// ---- 2. Dev/owner flag reveals UI ---------------------------------------------
t('master + module flags reveal the right sub-tabs in order', function () {
  resetFlags();
  G._setFlags({ SOST_GATEWAY_ENABLED: true, SOST_GATEWAY_HOLD_ENABLED: true,
    SOST_GATEWAY_PAY_ENABLED: true, SOST_GATEWAY_POPC_BOND_ENABLED: true });
  assert.strictEqual(G.gatewayVisible(), true);
  assert.deepStrictEqual(G.visibleModules(), ['hold', 'pay', 'popc_bond']);
  assert.strictEqual(G.Hold.isEnabled(), true);
  assert.strictEqual(G.Escrow.isEnabled(), false);   // not flipped
  resetFlags();
});

// ---- 3. Address validation -----------------------------------------------------
t('validateAddress accepts sost1/sost3 + 40 hex, rejects garbage', function () {
  assert.strictEqual(G.validateAddress(ADDR1).ok, true);
  assert.strictEqual(G.validateAddress(P2SH).ok, true);
  assert.strictEqual(G.validateAddress('sost1abc').ok, false);            // too short
  assert.strictEqual(G.validateAddress('sost2' + '0'.repeat(40)).ok, false); // wrong prefix
  assert.strictEqual(G.validateAddress('sost1' + 'g'.repeat(40)).ok, false);  // non-hex
  assert.strictEqual(G.validateAddress(123).ok, false);
  assert.strictEqual(G.validateAddress('').ok, false);
});

// ---- 4. Amount validation (integer stocks, 8 decimals, no float drift) ---------
t('validateAmount parses to integer stocks and rejects bad values', function () {
  assert.strictEqual(G.validateAmount('1').stocks, 100000000);
  assert.strictEqual(G.validateAmount('0.00000001').stocks, 1);
  assert.strictEqual(G.validateAmount('7.85100863').stocks, 785100863);
  assert.strictEqual(G.validateAmount('0').ok, false);          // not > 0
  assert.strictEqual(G.validateAmount('-1').ok, false);
  assert.strictEqual(G.validateAmount('1.123456789').ok, false); // 9 decimals
  assert.strictEqual(G.validateAmount('abc').ok, false);
  assert.strictEqual(G.validateAmount('').ok, false);
});

// ---- 5. Reference validation ---------------------------------------------------
t('validateReference allows short printable ASCII, rejects long/control', function () {
  assert.strictEqual(G.validateReference('order-42').ok, true);
  assert.strictEqual(G.validateReference('').reference, '');
  assert.strictEqual(G.validateReference(null).ok, true);
  assert.strictEqual(G.validateReference('x'.repeat(65)).ok, false);
  assert.strictEqual(G.validateReference('bad\nnewline').ok, false);
});

// ---- 6. PAY builds dummy intents, never real, validates inputs ------------------
t('Pay.createDummyIntent returns kind=dummy and validates', function () {
  var it = G.Pay.createDummyIntent({ destination: ADDR1, amount_sost: '25', concept: 'mine report' });
  assert.strictEqual(it.kind, 'dummy');
  assert.strictEqual(it.amount_stocks, 25 * 100000000);
  assert.strictEqual(it.state, 'draft');
  assert.strictEqual(it.required_confirmations, 3);
  assert.throws(function () { G.Pay.createDummyIntent({ destination: 'bad', amount_sost: '1' }); });
  assert.throws(function () { G.Pay.createDummyIntent({ destination: ADDR1, amount_sost: '0' }); });
  assert.throws(function () { G.Pay.createDummyIntent({ destination: ADDR1, amount_sost: '1', required_confirmations: 0 }); });
});

t('Pay.evaluateLocal mirrors destination+amount+confirmation states', function () {
  var it = G.Pay.createDummyIntent({ destination: ADDR1, amount_sost: '10', required_confirmations: 3, expires_at: 1000 });
  var ok = { confirmations: 6, outputs: [{ address: ADDR1, amount_stocks: 10 * 1e8 }] };
  assert.strictEqual(G.Pay.evaluateLocal(it, ok, 100), 'paid');
  assert.strictEqual(G.Pay.evaluateLocal(it, { confirmations: 6, outputs: [{ address: ADDR1, amount_stocks: 9 * 1e8 }] }, 100), 'underpaid');
  assert.strictEqual(G.Pay.evaluateLocal(it, { confirmations: 6, outputs: [{ address: ADDR2, amount_stocks: 10 * 1e8 }] }, 100), 'wrong_destination');
  assert.strictEqual(G.Pay.evaluateLocal(it, { confirmations: 1, outputs: [{ address: ADDR1, amount_stocks: 10 * 1e8 }] }, 100), 'insufficient_confirmations');
  assert.strictEqual(G.Pay.evaluateLocal(it, ok, 99999), 'expired');
});

// ---- 7. ESCROW spec only (no script, separate from PAY) ------------------------
t('Escrow.createSpec validates and stays a spec (no funds, no script)', function () {
  var s = G.Escrow.createSpec({ template: 'multisig_2of3_cltv', payer: ADDR1, beneficiary: ADDR2,
    arbiter: ADDR3, amount_sost: '500', expiry_height: 30000, purpose: 'data room' });
  assert.strictEqual(s.kind, 'spec');
  assert.strictEqual(s.status, 'draft');
  assert.strictEqual(s.amount_stocks, 500 * 1e8);
  assert.throws(function () { G.Escrow.createSpec({ template: 'multisig_2of3_cltv', payer: ADDR1, beneficiary: ADDR2, amount_sost: '1', expiry_height: 1 }); }, /arbiter/);
  assert.throws(function () { G.Escrow.createSpec({ template: 'nope', payer: ADDR1, beneficiary: ADDR2, amount_sost: '1', expiry_height: 1 }); });
  assert.throws(function () { G.Escrow.createSpec({ template: 'hashlock_timelock', payer: ADDR1, beneficiary: ADDR2, amount_sost: '1', expiry_height: 0 }); }, /expiry_height/);
});

// ---- 8. SWAP is link/embed only; PoPC bond is explanation only -----------------
t('Swap exposes pairs + console link, no integration', function () {
  assert.ok(G.Swap.PAIRS.indexOf('SOST/ETH') !== -1);
  assert.strictEqual(typeof G.Swap.consoleUrl(), 'string');
  assert.ok(/V15/.test(G.Swap.note()));
});
t('PopcBond recommends Model B first', function () {
  assert.ok(/Model B/.test(G.PopcBond.recommendation()));
  assert.ok(G.PopcBond.MODELS.A && G.PopcBond.MODELS.B);
});

// ---- 9. SECURITY invariants: no funds, no network, no secrets ------------------
t('no module exposes signing / broadcasting / key material', function () {
  var leak = /priv|seed|mnemonic|secret|sign\b|broadcast|fetch|xhr|http/i;
  ['Hold', 'Pay', 'Escrow', 'Swap', 'PopcBond'].forEach(function (modName) {
    var mod = G[modName];
    Object.keys(mod).forEach(function (key) {
      assert.ok(!leak.test(key), modName + '.' + key + ' looks like a fund/key/network surface');
    });
  });
});

t('HOLD proof shape carries no private key / seed', function () {
  var shape = G.Hold.proofShape();
  shape.forEach(function (field) {
    assert.ok(!/priv|seed|mnemonic|secret/i.test(field), 'proof field leaks secret: ' + field);
  });
  assert.ok(shape.indexOf('signature_der') !== -1);   // signature is fine; the key is not
});

t('dummy intent never contains a key/secret field', function () {
  var it = G.Pay.createDummyIntent({ destination: ADDR1, amount_sost: '1' });
  Object.keys(it).forEach(function (k) {
    assert.ok(!/priv|seed|mnemonic|secret/i.test(k), 'intent leaks: ' + k);
  });
});

// ---- 10. Config override (window.SOST_GATEWAY_CONFIG) without editing the lib ----
t('applyConfig maps friendly keys to internal flags', function () {
  resetFlags();
  G.applyConfig({ enabled: true, hold: true, pay: true, escrow: false, swap: true, popcBond: true });
  assert.strictEqual(G.gatewayVisible(), true);
  assert.deepStrictEqual(G.visibleModules(), ['hold', 'pay', 'swap', 'popc_bond']); // escrow stays off
  resetFlags();
});

t('applyConfig with no/empty config leaves everything OFF', function () {
  resetFlags();
  G.applyConfig(undefined); G.applyConfig(null); G.applyConfig({});
  assert.strictEqual(G.gatewayVisible(), false);
  assert.deepStrictEqual(G.visibleModules(), []);
});

t('applyConfig ignores unknown keys (no accidental enable)', function () {
  resetFlags();
  G.applyConfig({ bogus: true, hold: true });   // master not set → still hidden
  assert.strictEqual(G.gatewayVisible(), false);
  assert.deepStrictEqual(G.visibleModules(), []);
  resetFlags();
});

resetFlags();
console.log('ok - ' + n + ' SOST Gateway skeleton tests passed');

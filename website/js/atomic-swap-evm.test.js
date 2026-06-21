/* Dependency-free unit tests for the EVM codec. Run: node website/js/atomic-swap-evm.test.js
 * Validates selectors, calldata encoding, getSwap decoding, decimals math (no float), and config.
 */
'use strict';
var A = require('./atomic-swap-evm.js');
var assert = require('assert');
var n = 0;
function t(name, fn) { fn(); n++; }

var B32a = '0x' + '11'.repeat(32);
var B32b = '0x' + '22'.repeat(32);
var ADDR = '0x' + 'ab'.repeat(20);

t('selectors are the exact contract selectors', function () {
  assert.strictEqual(A.SEL.lockNative, '0xbef939c1');
  assert.strictEqual(A.SEL.lockERC20, '0x9cbaca50');
  assert.strictEqual(A.SEL.claim, '0x84cc9dfb');
  assert.strictEqual(A.SEL.refund, '0x7249fbb6');
  assert.strictEqual(A.SEL.getSwap, '0x3da0e66e');
  assert.strictEqual(A.SEL.approve, '0x095ea7b3');
  assert.strictEqual(A.SEL.decimals, '0x313ce567');
});

t('claim calldata = selector + 2 words (matches cast calldata)', function () {
  var d = A.dataClaim(B32a, B32b);
  // cast calldata "claim(bytes32,bytes32)" 0x11..11 0x22..22
  assert.strictEqual(d, '0x84cc9dfb' + '11'.repeat(32) + '22'.repeat(32));
  assert.strictEqual(d.length, 2 + 8 + 64 * 2);
});

t('refund calldata = selector + 1 word', function () {
  assert.strictEqual(A.dataRefund(B32a), '0x7249fbb6' + '11'.repeat(32));
});

t('lockNative calldata length = selector + 5 words; address left-padded', function () {
  var d = A.dataRefund; // touch
  var c = A.dataLockNative(B32a, B32b, 19000, ADDR, ADDR);
  assert.strictEqual(c.slice(0, 10), '0xbef939c1');
  assert.strictEqual(c.length, 2 + 8 + 64 * 5);
  // refundTime 19000 = 0x4a38 in the 3rd word
  assert.strictEqual(c.slice(10 + 64 * 2, 10 + 64 * 3), '4a38'.padStart(64, '0'));
  // address word is left-padded with 24 zero-bytes
  assert.strictEqual(c.slice(10 + 64 * 3, 10 + 64 * 3 + 24), '0'.repeat(24));
});

t('lockERC20 calldata = selector + 7 words', function () {
  var c = A.dataLockERC20(B32a, ADDR, '1000000', B32b, 19000, ADDR, ADDR);
  assert.strictEqual(c.slice(0, 10), '0x9cbaca50');
  assert.strictEqual(c.length, 2 + 8 + 64 * 7);
});

t('approve/allowance/balanceOf encode correctly', function () {
  assert.strictEqual(A.dataApprove(ADDR, '5').slice(0, 10), '0x095ea7b3');
  assert.strictEqual(A.dataAllowance(ADDR, ADDR).length, 2 + 8 + 64 * 2);
  assert.strictEqual(A.dataBalanceOf(ADDR).length, 2 + 8 + 64);
});

t('bad inputs are rejected (no silent corruption)', function () {
  assert.throws(function () { A.dataClaim('0x12', B32b); });        // short bytes32
  assert.throws(function () { A.dataLockNative(B32a, B32b, 1, '0xzz', ADDR); }); // bad address
  assert.throws(function () { A.toBaseUnits('1.2.3', 6); });
});

t('toBaseUnits/fromBaseUnits are exact (no float) and honour decimals', function () {
  assert.strictEqual(A.toBaseUnits('1', 6).toString(), '1000000');         // USDT 6dp
  assert.strictEqual(A.toBaseUnits('0.000001', 6).toString(), '1');
  assert.strictEqual(A.toBaseUnits('1.5', 18).toString(), '1500000000000000000'); // 18dp
  assert.strictEqual(A.toBaseUnits('0.1', 8).toString(), '10000000');      // SOST-like 8dp
  assert.throws(function () { A.toBaseUnits('0.0000001', 6); });           // too many decimals
  assert.strictEqual(A.fromBaseUnits('1000000', 6), '1');
  assert.strictEqual(A.fromBaseUnits('1500000000000000000', 18), '1.5');
  assert.strictEqual(A.fromBaseUnits('1', 6), '0.000001');
});

t('decodeGetSwap parses the static tuple', function () {
  // state=1 LOCKED, token=0, amount=1000, hashlock=B32a, refundTime=19000, claimer=ADDR, refunder=ADDR
  var w = function (h) { return h.padStart(64, '0'); };
  var ret = '0x' + w('1') + w('0') + w(BigInt(1000).toString(16)) + '11'.repeat(32) +
    w(BigInt(19000).toString(16)) + 'ab'.repeat(20).padStart(64, '0') + 'ab'.repeat(20).padStart(64, '0');
  var s = A.decodeGetSwap(ret);
  assert.strictEqual(s.state, 'LOCKED');
  assert.strictEqual(s.amountBase, '1000');
  assert.strictEqual(s.refundTime, '19000');
  assert.strictEqual(s.hashlock, B32a);
  assert.strictEqual(s.token, '0x' + '00'.repeat(20));
});

t('classifySwap: locked before/after refundTime', function () {
  assert.strictEqual(A.classifySwap({ stateIndex: 1, refundTime: '100' }, 50), 'CLAIMABLE');
  assert.strictEqual(A.classifySwap({ stateIndex: 1, refundTime: '100' }, 150), 'REFUNDABLE');
  assert.strictEqual(A.classifySwap({ stateIndex: 2, refundTime: '100' }, 50), 'CLAIMED');
  assert.strictEqual(A.classifySwap({ stateIndex: 3, refundTime: '100' }, 50), 'REFUNDED');
  assert.strictEqual(A.classifySwap({ stateIndex: 0 }, 1), 'NONE');
});

t('config: networks present, htlc null (not deployed), tokens have addresses', function () {
  assert.ok(A.NETWORKS['0x1'] && A.NETWORKS['0x38']);
  assert.strictEqual(A.NETWORKS['0x1'].htlc, null);        // not deployed by default
  assert.strictEqual(A.NETWORKS['0x38'].htlc, null);
  assert.ok(A.isAddress(A.NETWORKS['0x1'].tokens.USDT.address));
  assert.deepStrictEqual(A.FREEZE_RISK.sort(), ['PAXG', 'USDC', 'USDT', 'XAUT']);
});

t('native-first policy + fee-on-transfer blacklist', function () {
  assert.strictEqual(A.ERC20_ENABLED, false);              // ERC20 off by default
  assert.ok(A.FEE_ON_TRANSFER.indexOf('PAXG') >= 0);       // PAXG hard-blocked (fee-on-transfer)
});

t('testnets present (native-only), mainnets present', function () {
  assert.ok(A.NETWORKS['0xaa36a7'] && A.NETWORKS['0x61']); // Sepolia + BNB testnet
  assert.deepStrictEqual(A.NETWORKS['0xaa36a7'].tokens, {});
  assert.strictEqual(A.NETWORKS['0xaa36a7'].htlc, null);
});

t('verifyCode classifies empty / exact / differs', function () {
  assert.strictEqual(A.verifyCode('0x', '0xabcd'), 'EMPTY');
  assert.strictEqual(A.verifyCode('0x0', '0xabcd'), 'EMPTY');
  assert.strictEqual(A.verifyCode('0xABcd', '0xabcd'), 'EXACT');   // case-insensitive
  assert.strictEqual(A.verifyCode('0xdead', '0xabcd'), 'DIFFERS');
  assert.strictEqual(A.verifyCode('0xab', null), 'UNKNOWN');
});

t('vendored runtime bytecode matches the forge artifact', function () {
  var fs = require('fs'), path = require('path');
  var runtime = require('./atomic-swap-htlc-runtime.js');
  var art = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../../contracts/atomic-swap/out/AtomicSwapHTLC.sol/AtomicSwapHTLC.json'), 'utf8'));
  assert.strictEqual(runtime.toLowerCase(), art.deployedBytecode.object.toLowerCase());
  assert.strictEqual(A.verifyCode(art.deployedBytecode.object, runtime), 'EXACT');
});

console.log('ASWEVM codec: ' + n + ' tests passed');

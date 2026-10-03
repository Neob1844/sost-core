/* Headless DEX security/policy test suite (section 15 — DEX part).
 * ---------------------------------------------------------------------------
 * Covers the devnet security/policy bundle across the three pure modules:
 *   - dex-quote-policy.js   : anti-replay domain binding, expired/modified quote,
 *                             wrong chainId/contract, lifecycle cancel pre/post fund
 *   - dex-token-allowlist.js: fake token (right symbol/wrong contract), wrong
 *                             decimals, disabled tokens
 *   - dex-swap-policy.js    : timelock validation PASS, reversed REJECT, gap REJECT,
 *                             contract pinning mismatch/unpinned CRITICAL, signing summary
 *   - dex-rfq.js            : duplicate (maker,nonce) replay guard
 *
 * The timeout / refund / page-reload chain behaviour is covered by
 * scripts/e2e_sost_eth_devnet.sh + the devnet-flow resume/reconcile logic and is
 * referenced here, NOT duplicated (this file is the pure security layer).
 *
 * Run: node website/js/dex-security.test.js
 */
var QP = require('./dex-quote-policy.js');
var AL = require('./dex-token-allowlist.js');
var SW = require('./dex-swap-policy.js');
var RFQ = require('./dex-rfq.js');

var pass = 0, fail = 0;
function ok(n, c) { if (c) { pass++; } else { fail++; console.log('  FAIL:', n); } }
function throws(fn, re) { try { fn(); return false; } catch (e) { return re ? re.test(e.message) : true; } }

var T0 = 1700000000000;            // fixed now (ms)
var NOW = T0 + 10 * 1000;          // 10s later, still inside the 90s quote lifetime
var CONTRACT = '0x5fbdb2315678afecb367f032d93f642f64180aa3'; // devnet HTLC (config)
var OTHER_CONTRACT = '0x000000000000000000000000000000000000dead';

// A firm quote bound to the SOST/ETH DEVNET context (chainIdB=31337, this contract).
function baseQuote() {
  return QP.makeQuote({
    pair: 'SOST/ETH', side: 'sell', amount: '1000', price: '1',
    environment: 'devnet', chainIdA: 'sost:devnet', chainIdB: '31337',
    htlcContract: CONTRACT, maker: 'sost1aaa', taker: '0xbbb'
  }, T0);
}
var CTX = { environment: 'devnet', chainIdA: 'sost:devnet', chainIdB: '31337', pair: 'SOST/ETH', side: 'sell', htlcContract: CONTRACT };

// ============================ ANTI-REPLAY (section 4) ========================
var q = baseQuote();
ok('[replay] base quote verifies in its own context', QP.verifyQuoteFor(q, CTX, NOW).ok);
ok('[replay] SAME quote REJECTED for mainnet',
  !QP.verifyQuoteFor(q, Object.assign({}, CTX, { environment: 'mainnet' }), NOW).ok);
ok('[replay] SAME quote REJECTED for SOST/USDC',
  !QP.verifyQuoteFor(q, Object.assign({}, CTX, { pair: 'SOST/USDC' }), NOW).ok);
ok('[replay] SAME quote REJECTED for another HTLC contract',
  !QP.verifyQuoteFor(q, Object.assign({}, CTX, { htlcContract: OTHER_CONTRACT }), NOW).ok);
ok('[replay] SAME quote REJECTED for another chainId',
  !QP.verifyQuoteFor(q, Object.assign({}, CTX, { chainIdB: '1' }), NOW).ok);
ok('[replay] SAME quote REJECTED for opposite side',
  !QP.verifyQuoteFor(q, Object.assign({}, CTX, { side: 'buy' }), NOW).ok);
// digest binds amount + expiry: tampering either breaks verification (amount/expiry replay)
function tamper(mut) { var c = JSON.parse(JSON.stringify(q)); mut(c); return c; }
ok('[replay] another AMOUNT rejected (digest)', !QP.verifyQuote(tamper(function (c) { c.amount = '9'; }), NOW).ok);
ok('[replay] another EXPIRY rejected (digest)', !QP.verifyQuote(tamper(function (c) { c.expires_at += 86400; }), NOW).ok);
ok('[replay] another CONTRACT in-body rejected (digest)', !QP.verifyQuote(tamper(function (c) { c.htlcContract = OTHER_CONTRACT; }), NOW).ok);
ok('[replay] another chainId in-body rejected (digest)', !QP.verifyQuote(tamper(function (c) { c.chainIdB = '1'; }), NOW).ok);

// ============================ EXPIRED QUOTE ==================================
ok('[expired] fresh quote executable', QP.isExecutable(q, NOW));
QP.refreshState(q, T0 + 91 * 1000);
ok('[expired] state flips to EXPIRED', q.state === 'EXPIRED');
ok('[expired] NOT executable once expired', !QP.isExecutable(q, T0 + 91 * 1000));
ok('[expired] verifyQuoteFor rejects expired', !QP.verifyQuoteFor(q, CTX, T0 + 91 * 1000).ok);

// ============================ MODIFIED QUOTE =================================
var qm = baseQuote();
ok('[modified] price tamper rejected', !QP.verifyQuote(tamperOf(qm, function (c) { c.price = '999'; }), NOW).ok);
ok('[modified] minimumReceived tamper rejected', !QP.verifyQuote(tamperOf(qm, function (c) { c.minimumReceived = '1'; }), NOW).ok);
ok('[modified] nonce tamper rejected', !QP.verifyQuote(tamperOf(qm, function (c) { c.nonce = 'forged'; }), NOW).ok);
ok('[modified] maker tamper rejected', !QP.verifyQuote(tamperOf(qm, function (c) { c.maker = 'sost1evil'; }), NOW).ok);
function tamperOf(src, mut) { var c = JSON.parse(JSON.stringify(src)); mut(c); return c; }

// ============================ TOKEN ALLOWLIST (section 7) ====================
AL.registerFromConfig({ evm_chain_id: 31337, usdc_token: '0x1111111111111111111111111111111111111111' });
ok('[token] ETH native (31337) SUPPORTED', AL.checkToken(31337, 'ETH', null, 18).ok);
ok('[token] authorized USDC (31337) ok', AL.checkToken(31337, 'USDC', '0x1111111111111111111111111111111111111111', 6).ok);
var fake = AL.checkToken(31337, 'USDC', '0x2222222222222222222222222222222222222222', 6);
ok('[token] FAKE token (USDC symbol / wrong contract) REJECTED', !fake.ok && fake.status === 'FAKE_TOKEN');
var wrongDec = AL.checkToken(31337, 'USDC', '0x1111111111111111111111111111111111111111', 18);
ok('[token] WRONG decimals REJECTED', !wrongDec.ok && wrongDec.status === 'DECIMALS_MISMATCH');
ok('[token] USDT DISABLED', AL.checkToken(1, 'USDT', '0xanything', 6).status === 'DISABLED');
ok('[token] PAXG DISABLED', AL.checkToken(1, 'PAXG', null, 18).status === 'DISABLED');
ok('[token] XAUT DISABLED', AL.checkToken(1, 'XAUT', null, 6).status === 'DISABLED');
ok('[token] unknown ERC20 on chain REJECTED', !AL.checkToken(31337, 'FOO', '0x3333333333333333333333333333333333333333', 18).ok);
ok('[token] mainnet USDC pinned to Circle contract', AL.checkToken(1, 'USDC', '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', 6).ok);
ok('[token] mainnet USDC FAKE contract REJECTED', AL.checkToken(1, 'USDC', '0x2222222222222222222222222222222222222222', 6).status === 'FAKE_TOKEN');

// ============================ DUPLICATE NONCE (replay guard) =================
var seen = RFQ.makeSeenSet();
var offer = { maker: 'sost1aaa', pay_chain: 'SOST', pay_asset: 'SOST', pay_amount: '1000', recv_chain: 'ETH', recv_asset: 'ETH', recv_amount: '1000', maker_receive_address: 'sost1aaa', min_confirmations: 1, refund_timeout: 288, expiry: 2000000000, nonce: 'n-123', network: 'devnet' };
ok('[nonce] first (maker,nonce) accepted', seen.accept(offer) === true);
ok('[nonce] duplicate (maker,nonce) REJECTED', seen.accept(offer) === false);

// ============================ CANCELLATION LIFECYCLE (section 5) =============
var preFund = { lifecycle: 'RESERVED' };
QP.lifecycleTransition(preFund, 'CANCELLED');
ok('[cancel] pre-funding (RESERVED) cancel ALLOWED', preFund.lifecycle === 'CANCELLED');
ok('[cancel] OPEN cancelable', QP.lifecycleCanCancel('OPEN'));
ok('[cancel] QUOTED cancelable', QP.lifecycleCanCancel('QUOTED'));
ok('[cancel] FUNDED NOT cancelable', !QP.lifecycleCanCancel('FUNDED'));
var postFund = { lifecycle: 'FUNDED' };
ok('[cancel] post-funding (FUNDED) cancel REJECTED', throws(function () { QP.lifecycleTransition(postFund, 'CANCELLED'); }, /funded|SETTLE|REFUND/i) && postFund.lifecycle === 'FUNDED');
ok('[cancel] FUNDED -> SETTLING allowed', (QP.lifecycleTransition({ lifecycle: 'FUNDED' }, 'SETTLING').lifecycle === 'SETTLING'));
ok('[cancel] FUNDED -> REFUND_AVAILABLE allowed', (QP.lifecycleTransition({ lifecycle: 'FUNDED' }, 'REFUND_AVAILABLE').lifecycle === 'REFUND_AVAILABLE'));
ok('[cancel] lifecycle states include SETTLING/COMPLETE/FAILED', ['SETTLING', 'COMPLETE', 'FAILED'].every(function (s) { return QP.LIFECYCLE_STATES.indexOf(s) >= 0; }));

// ============================ TIMELOCK VALIDATION (section 6) ================
var tlEth = SW.computeTimelocks('SOST/ETH', { env: 'mainnet', sostTip: 1000, evmHead: 5000 });
var vEth = SW.validateTimelocks(tlEth);
ok('[timelock] SOST/ETH PASS (long>short, gap>=24h)', vEth.ok && vEth.gapSecs === 86400);
ok('[timelock] SOST long = 288 blocks / 48h', tlEth.long.refundBlocks === 288 && tlEth.long.timeoutSecs === 172800);
ok('[timelock] EVM short = 7200 blocks / 24h', tlEth.short.refundBlocks === 7200 && tlEth.short.timeoutSecs === 86400);
ok('[timelock] SOST is the LONG leg', tlEth.long.chain === 'SOST' && tlEth.long.timeoutSecs > tlEth.short.timeoutSecs);
var tlBtc = SW.computeTimelocks('SOST/BTC', { env: 'mainnet', sostTip: 1000, btcTip: 800 });
ok('[timelock] SOST/BTC PASS', SW.validateTimelocks(tlBtc).ok);
ok('[timelock] BTC short = 144 blocks / 24h (CLTV)', tlBtc.short.refundBlocks === 144 && tlBtc.short.timeoutSecs === 86400 && tlBtc.short.chain === 'BTC');
var tlUsdc = SW.computeTimelocks('SOST/USDC', { env: 'mainnet', sostTip: 1, evmHead: 1 });
ok('[timelock] SOST/USDC short leg is EVM', tlUsdc.short.chain === 'EVM' && SW.validateTimelocks(tlUsdc).ok);
// devnet scaling: staggered + still valid policy durations, scaled heights
var tlDev = SW.computeTimelocks('SOST/ETH', { env: 'devnet', sostTip: 10, evmHead: 10 });
ok('[timelock] devnet scaled heights (SOST+500 long / EVM+200 short)', tlDev.long.refundBlocks === 500 && tlDev.short.refundBlocks === 200 && tlDev.devnetScaled === true);
ok('[timelock] devnet still validates (mainnet-policy durations)', SW.validateTimelocks(tlDev).ok);

// REVERSED timelock REJECTED (short outlives long)
ok('[timelock] REVERSED timelock REJECTED', throws(function () {
  SW.validateTimelocks({ short: { timeoutSecs: 172800 }, long: { timeoutSecs: 86400 } });
}, /REVERSED/i));
// INSUFFICIENT GAP REJECTED (long only 100s beyond short)
ok('[timelock] INSUFFICIENT GAP REJECTED', throws(function () {
  SW.validateTimelocks({ short: { timeoutSecs: 86400 }, long: { timeoutSecs: 86400 + 100 } });
}, /INSUFFICIENT SAFETY GAP/i));
// equal legs rejected as reversed (not strictly greater)
ok('[timelock] EQUAL legs REJECTED', throws(function () {
  SW.validateTimelocks({ short: { timeoutSecs: 86400 }, long: { timeoutSecs: 86400 } });
}, /REVERSED/i));

// ============================ CONTRACT PINNING (section 8) ===================
SW.registerPin('devnet', 31337, 'v2', CONTRACT);
ok('[pin] correct contract passes', SW.assertPinnedContract(CONTRACT, { env: 'devnet', chainId: 31337, version: 'v2' }).ok);
ok('[pin] MISMATCH contract CRITICAL (no sign)', throws(function () {
  SW.assertPinnedContract(OTHER_CONTRACT, { env: 'devnet', chainId: 31337, version: 'v2' });
}, /CRITICAL.*MISMATCH/i));
ok('[pin] UNPINNED (mainnet, null) CRITICAL (no sign)', throws(function () {
  SW.assertPinnedContract(CONTRACT, { env: 'mainnet', chainId: 1, version: 'v2' });
}, /CRITICAL.*no PINNED/i));
ok('[pin] resolves devnet address from local config', SW.resolveExpectedHtlc('devnet', 31337, 'v2', { htlc_v2: CONTRACT }) === CONTRACT);

// ============================ HUMAN-READABLE SIGNING (section 3) =============
var sfull = SW.buildSigningSummary({
  youPay: '1000 SOST', youReceive: '1000 ETH', pair: 'SOST/ETH', side: 'sell',
  rate: '1 ETH/SOST', minimumReceived: '1000 ETH', fees: 'gas only', counterparty: 'devnet',
  networkA: 'SOST sost:devnet', networkB: 'EVM chainId 31337', htlcContract: CONTRACT,
  quoteExpiry: 't=... (90s)', htlcTimelock: 'short ~24h / long ~48h', refundAvailableAt: 'SOST height 1288', nonce: 'n-1'
});
ok('[sign] summary carries all 15 required fields', SW.summaryComplete(sfull));
ok('[sign] field set = required canonical signing fields',
  SW.SUMMARY_FIELDS.map(function (f) { return f[0]; }).join(',') ===
  'youPay,youReceive,pair,side,rate,minimumReceived,fees,counterparty,networkA,networkB,htlcContract,quoteExpiry,htlcTimelock,refundAvailableAt,nonce');
ok('[sign] incomplete summary (missing field) NOT complete',
  !SW.summaryComplete(SW.buildSigningSummary({ youPay: '1000 SOST' })));
ok('[sign] text render names every field', /YOU PAY:.*NONCE:/s.test(SW.formatSigningSummaryText(sfull)));

// ============================ RESUME: EXACT DEADLINES =======================
// Deadlines persist as explicit refund heights and reconcile against chain tips
// on reload (the stored heights are NEVER re-derived — exact resume).
var tlFunded = SW.computeTimelocks('SOST/ETH', { env: 'devnet', sostTip: 100, evmHead: 200 });
tlFunded.long.refundHeight = 100 + tlFunded.long.refundBlocks;  // 600
tlFunded.short.refundHeight = 200 + tlFunded.short.refundBlocks; // 400
var rec = SW.deadlineRecord(tlFunded);
var roundtrip = JSON.parse(JSON.stringify(rec)); // survive localStorage JSON
ok('[resume] deadline record persists exact refund heights', roundtrip.longRefundHeight === 600 && roundtrip.shortRefundHeight === 400);
var rc = SW.reconcileDeadlines(roundtrip, { sostTip: 550, evmHead: 350 });
ok('[resume] reconcile keeps the SAME deadlines (no re-derive)', rc.longRefundHeight === 600 && rc.shortRefundHeight === 400);
ok('[resume] reconcile computes blocks-remaining from chain tips', rc.longBlocksRemaining === 50 && rc.shortBlocksRemaining === 50);
ok('[resume] short refund not yet open', rc.shortRefundOpen === false);
var rcOpen = SW.reconcileDeadlines(roundtrip, { sostTip: 700, evmHead: 500 });
ok('[resume] refunds open once tips pass the stored heights', rcOpen.longRefundOpen === true && rcOpen.shortRefundOpen === true);

console.log('DEX-SECURITY TESTS: PASS=' + pass + ' FAIL=' + fail);
process.exit(fail ? 1 : 0);

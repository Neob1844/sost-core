/*
 * Headless tests for sost-wallet-bridge.js — run with: node sost-wallet-bridge.test.js
 * Exercises the message-handling + security logic WITHOUT a browser. The signer /
 * builder / address callbacks are mocked; the real crypto lives in sost-wallet.html.
 *
 * Verifies:
 *   - correct reqId round-trip (address)
 *   - wrong-origin message is dropped with NO response
 *   - malformed payload -> bad_request
 *   - unknown type -> dropped (not a bridge request) with bad_request to allowed origin
 *   - user-reject (authorizeSign -> false) -> { error:'user_reject' }, NOT signed
 *   - build path round-trip
 *   - sign path (authorized) round-trip
 *   - NO private-key / seed field EVER appears in ANY response (incl. when a buggy
 *     callback tries to leak one)
 */
'use strict';

var B = require('./sost-wallet-bridge.js');

var passed = 0, failed = 0;
function ok(name, cond) {
  if (cond) { passed++; console.log('  PASS ' + name); }
  else { failed++; console.log('  FAIL ' + name); }
}

// --- a capturing responder with mock deps ---------------------------------
function makeHarness(opts) {
  opts = opts || {};
  var sent = [];                       // every message posted to the "opener"
  var signCalls = 0, buildCalls = 0;
  var responder = B.createResponder({
    allowlist: ['http://127.0.0.1:8899'],
    selfOrigin: 'http://127.0.0.1:8899',
    getAddress: async function () {
      // A buggy wallet might try to attach a secret — the bridge must scrub it.
      return { address: 'sost1' + 'ab'.repeat(20), balanceStocks: 1234,
               privKey: 'DEADBEEF'.repeat(8), seedPhrase: 'abandon abandon ...' };
    },
    buildHtlc: async function (payload) {
      buildCalls++;
      return {
        rawUnsignedHex: '0100' + '00'.repeat(60),
        summary: { kind: payload.kind, amount: payload.amount || null },
        spend: [{ amount: payload.amount || 0, type: 0 }],
        mnemonic: 'should be scrubbed'   // buggy leak attempt
      };
    },
    signTx: async function () {
      signCalls++;
      return { signedHex: '0100' + 'ff'.repeat(80), txid: 'cc'.repeat(32), vout: 0,
               privKey: 'leak-me-if-you-can' };  // buggy leak attempt
    },
    authorizeSign: async function () {
      return opts.approve !== false;   // default approve; set approve:false to reject
    },
    post: function (target, origin, msg) { sent.push({ origin: origin, msg: msg }); },
    log: function () {}
  });
  return { responder: responder, sent: sent,
           signCount: function () { return signCalls; },
           buildCount: function () { return buildCalls; } };
}

function evt(origin, data) { return { origin: origin, data: data, source: {} }; }

// Recursively assert no secret-looking key appears anywhere in an object.
function hasSecretKey(obj, _seen) {
  _seen = _seen || [];
  if (obj == null || typeof obj !== 'object') return false;
  if (_seen.indexOf(obj) >= 0) return false;
  _seen.push(obj);
  var keys = Object.keys(obj);
  for (var i = 0; i < keys.length; i++) {
    if (B.SECRET_KEY_RE.test(keys[i])) return true;
    if (hasSecretKey(obj[keys[i]], _seen)) return true;
  }
  return false;
}

(async function run() {
  console.log('sost-wallet-bridge headless tests');

  // 1) address round-trip with matching reqId
  {
    var h = makeHarness();
    await h.responder.handleMessage(evt('http://127.0.0.1:8899',
      { reqId: 'req-address-1', type: 'sost:address' }));
    var r = h.sent[0] && h.sent[0].msg;
    ok('address returns matching reqId', r && r.reqId === 'req-address-1');
    ok('address type is sost:address', r && r.type === 'sost:address');
    ok('address carries an address', r && typeof r.address === 'string' && r.address.indexOf('sost1') === 0);
  }

  // 2) wrong origin -> dropped, no response
  {
    var h = makeHarness();
    var res = await h.responder.handleMessage(evt('https://evil.example',
      { reqId: 'req-address-2', type: 'sost:address' }));
    ok('wrong origin reported dropped', res && res.dropped === true && res.reason === 'bad_origin');
    ok('wrong origin produced NO response', h.sent.length === 0);
  }

  // 3) malformed payload (build with bad fields) -> bad_request
  {
    var h = makeHarness();
    await h.responder.handleMessage(evt('http://127.0.0.1:8899',
      { reqId: 'req-build-bad', type: 'sost:build', kind: 'htlc_lock', amount: -5, hashlock: 'xyz' }));
    var r = h.sent[0] && h.sent[0].msg;
    ok('malformed build -> error bad_request', r && r.error === 'bad_request' && r.reqId === 'req-build-bad');
    ok('malformed build did NOT build', h.buildCount() === 0);
  }

  // 4) unknown type -> bad_request (normalizeRequest rejects it, allowed origin)
  {
    var h = makeHarness();
    await h.responder.handleMessage(evt('http://127.0.0.1:8899',
      { reqId: 'req-weird', type: 'sost:destroyEverything' }));
    var r = h.sent[0] && h.sent[0].msg;
    ok('unknown type -> bad_request', r && r.error === 'bad_request');
  }

  // 5) user reject -> error user_reject, signTx NOT called
  {
    var h = makeHarness({ approve: false });
    await h.responder.handleMessage(evt('http://127.0.0.1:8899',
      { reqId: 'req-sign-rej', type: 'sost:sign',
        tx: { rawUnsignedHex: '0100' + '00'.repeat(40), spend: [{ amount: 10, type: 18 }] } }));
    var r = h.sent[0] && h.sent[0].msg;
    ok('user reject -> error user_reject', r && r.error === 'user_reject' && r.reqId === 'req-sign-rej');
    ok('user reject did NOT sign', h.signCount() === 0);
  }

  // 6) build round-trip
  {
    var h = makeHarness();
    await h.responder.handleMessage(evt('http://127.0.0.1:8899',
      { reqId: 'req-build-ok', type: 'sost:build',
        kind: 'htlc_lock', amount: 500000000, hashlock: 'aa'.repeat(32), refund_height: 30000,
        claim_address: 'sost1' + 'bb'.repeat(20), refund_address: 'sost1' + 'cc'.repeat(20) }));
    var r = h.sent[0] && h.sent[0].msg;
    ok('build -> type sost:build', r && r.type === 'sost:build' && r.reqId === 'req-build-ok');
    ok('build -> rawUnsignedHex present', r && typeof r.rawUnsignedHex === 'string');
    ok('build -> spend metadata present', r && Array.isArray(r.spend));
    ok('build actually built', h.buildCount() === 1);
  }

  // 7) sign round-trip (authorized)
  {
    var h = makeHarness();
    await h.responder.handleMessage(evt('http://127.0.0.1:8899',
      { reqId: 'req-sign-ok', type: 'sost:sign',
        tx: { rawUnsignedHex: '0100' + '00'.repeat(40), spend: [{ amount: 10, type: 18 }] } }));
    var r = h.sent[0] && h.sent[0].msg;
    ok('sign -> type sost:sign', r && r.type === 'sost:sign' && r.reqId === 'req-sign-ok');
    ok('sign -> signedHex present', r && typeof r.signedHex === 'string');
    ok('sign -> hex alias present (dex broadcast reads .hex)', r && r.hex === r.signedHex);
    ok('sign actually signed', h.signCount() === 1);
  }

  // 8) hash bootstrap: #address auto-responds to opener
  {
    var h = makeHarness();
    var opener = {};
    await h.responder.handleHash('#address=req-hash-1', opener, 'http://127.0.0.1:8899');
    var r = h.sent[0] && h.sent[0].msg;
    ok('hash #address auto-responds', r && r.type === 'sost:address' && r.reqId === 'req-hash-1');
  }
  {
    var h = makeHarness();
    var res = await h.responder.handleHash('#build=req-hash-2', {}, 'http://127.0.0.1:8899');
    ok('hash #build is pending (awaits payload msg)', res && res.pending === true && res.reqId === 'req-hash-2');
    ok('hash #build sent nothing yet', h.sent.length === 0);
  }

  // 8b) unrelated same-origin chatter (no reqId, non-sost type) is ignored silently
  {
    var h = makeHarness();
    var res = await h.responder.handleMessage(evt('http://127.0.0.1:8899',
      { foo: 'bar', type: 'webpack/hot-update' }));
    ok('unrelated same-origin message ignored', res && res.ignored === true);
    ok('unrelated message produced NO response', h.sent.length === 0);
  }

  // 9) NO secret field in ANY response across all the above interactions
  {
    var h = makeHarness();
    // exercise every path, including the leaky mock callbacks
    await h.responder.handleMessage(evt('http://127.0.0.1:8899', { reqId: 'a', type: 'sost:address' }));
    await h.responder.handleMessage(evt('http://127.0.0.1:8899', { reqId: 'c', type: 'sost:connect' }));
    await h.responder.handleMessage(evt('http://127.0.0.1:8899',
      { reqId: 'b', type: 'sost:build', kind: 'htlc_lock', amount: 1, hashlock: 'aa'.repeat(32),
        refund_height: 1, claim_address: 'sost1' + 'bb'.repeat(20), refund_address: 'sost1' + 'cc'.repeat(20) }));
    await h.responder.handleMessage(evt('http://127.0.0.1:8899',
      { reqId: 's', type: 'sost:sign', tx: { rawUnsignedHex: '0100' + '00'.repeat(40) } }));
    var anyLeak = h.sent.some(function (e) { return hasSecretKey(e.msg); });
    ok('NO private-key/seed field in any response (leaky callbacks scrubbed)', anyLeak === false);
  }

  console.log('\n' + passed + ' passed, ' + failed + ' failed');
  process.exit(failed === 0 ? 0 : 1);
})();

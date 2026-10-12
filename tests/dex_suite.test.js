/* SOST DEX unified suite — RFQ core + connectors (mock providers) + relay lifecycle + private-beta gate. */
const RFQ = require('../website/js/dex-rfq.js');
const C = require('../website/js/dex-connectors.js');
const R = require('../website/js/dex-relay.js');
let pass = 0, fail = 0; const fails = [];
function ok(c, m) { if (c) pass++; else { fail++; fails.push(m); console.log('  ❌ ' + m); } }
async function athrows(fn, m) { try { await fn(); fail++; fails.push(m + ' (did not throw)'); console.log('  ❌ ' + m); } catch (e) { pass++; } }

const offer = {
  maker: '0xMaker', pay_chain: 'SOST', pay_asset: 'SOST', pay_amount: '100000000',
  recv_chain: 'EVM', recv_asset: 'USDC', recv_amount: '250000000',
  maker_receive_address: '0xRecv', min_confirmations: 3, refund_timeout: 144,
  expiry: 2000000000, nonce: '1', network: 'mainnet'
};

(async () => {
  console.log('=== CONNECTORS: EVM (mock EIP-1193) ===');
  const calls = [];
  const mockEvm = { request: async ({ method }) => { calls.push(method); if (method === 'eth_requestAccounts') return ['0xabc']; if (method === 'eth_chainId') return '0x1'; return '0x0'; }, on: () => {} };
  const e = C.evm(mockEvm);
  ok(e.status === C.STATUS.DETECTED, 'evm detected');
  const acc = await e.connect();
  ok(acc === '0xabc' && e.status === C.STATUS.CONNECTED, 'evm connect -> account + CONNECTED');
  await e.switchNetwork('0xaa36a7'); await e.approve('0xToken', '0xSpender', '0x64'); await e.send({ to: '0xX', data: '0x' });
  ok(calls.includes('wallet_switchEthereumChain') && calls.includes('eth_sendTransaction'), 'evm switch/approve/send call right methods');
  ok(C.evm({}).status === C.STATUS.NOT_DETECTED, 'evm bad provider -> NOT_DETECTED');
  ok(C.discoverEip6963([{ info: { name: 'MetaMask' }, provider: mockEvm }]).length === 1, 'eip6963 discovery (array injection)');

  console.log('=== CONNECTORS: BTC PSBT capability ===');
  const btcOk = C.btc({ signPsbt: async () => 'signed', getAddresses: async () => ['bc1q'] });
  ok(btcOk.status === C.STATUS.SUPPORTED, 'btc with signPsbt -> SUPPORTED');
  ok((await btcOk.signPsbt('cHNidAA=')) === 'signed', 'btc signPsbt delegates');
  const btcNo = C.btc({ sendBitcoin: async () => {} });
  ok(btcNo.status === C.STATUS.INCOMPATIBLE, 'btc without PSBT -> INCOMPATIBLE');
  await athrows(() => btcNo.signPsbt('x'), 'btc incompatible signPsbt throws');

  console.log('=== CONNECTORS: SOST bridge (no key exposure) ===');
  const bcalls = [];
  const bridge = { getAddress: async () => 'sost1x', getBalance: async () => '5', buildTx: async (o) => ({ unsigned: o.kind }), sign: async (t) => { bcalls.push('sign'); return { signed: t.unsigned }; }, broadcast: async (t) => { bcalls.push('broadcast'); return 'txid'; } };
  const sb = C.sost(bridge);
  const lock = await sb.buildLock({ amount: '1' });
  ok(lock.unsigned === 'htlc_lock', 'sost buildLock -> unsigned tx template');
  const signed = await sb.sign(lock); const tx = await sb.broadcast(signed);
  ok(tx === 'txid' && bcalls.join(',') === 'sign,broadcast', 'sost sign then broadcast (key stays in wallet)');
  ok(typeof sb.bridge.privateKey === 'undefined', 'sost bridge exposes no private key');

  console.log('=== RELAY lifecycle ===');
  let t = 1000; const rl = R.relay(R.memoryStore(), () => t);
  await athrows(() => rl.post(offer, ''), 'relay rejects missing signature');
  const id = await rl.post(offer, '0xsignature-opaque');
  ok(!!id, 'relay post signed offer -> id');
  await athrows(() => rl.post(offer, '0xsignature-opaque'), 'relay rejects duplicate offer');
  ok(rl.list({ network: 'mainnet' }).length === 1, 'relay list shows open offer');
  ok(rl.list({ network: 'testnet' }).length === 0, 'relay list hides other-network offer');
  await athrows(() => rl.accept(id, '0xtaker', 'testnet'), 'relay accept rejects network mismatch');
  const swapId = await rl.accept(id, '0xtaker', 'mainnet');
  ok(!!swapId && rl.swapStatus(swapId).state === 'ACCEPTED', 'relay accept -> swap ACCEPTED');
  await athrows(() => rl.accept(id, '0xother', 'mainnet'), 'relay single-acceptance (no double-fill)');
  await athrows(() => rl.updateSwap(swapId, { preimage: 'deadbeef' }), 'relay refuses to store a preimage');
  ok(rl.updateSwap(swapId, { hashlock: 'abc', txrefs: { initiatorLock: '0xtx' } }).hashlock === 'abc', 'relay records public swap progress');

  console.log('=== RELAY expiry + cancel ===');
  let t2 = 1000; const rl2 = R.relay(R.memoryStore(), () => t2);
  const shortOffer = Object.assign({}, offer, { nonce: '9', expiry: 1500 });
  const id2 = await rl2.post(shortOffer, '0xsignature-2');
  ok(rl2.cancelBeforeLock(id2) === true, 'cancel before lock ok');
  await athrows(() => rl2.cancelBeforeLock(id2), 'cannot cancel a cancelled offer');
  const id3 = await rl2.post(Object.assign({}, offer, { nonce: '10', expiry: 1500 }), '0xsignature-3');
  t2 = 2000; // now past expiry
  ok(rl2.expireSweep() >= 1 && rl2.list().length === 0, 'expireSweep marks expired offers, list empty');
  await athrows(() => rl2.accept(id3, '0xt', 'mainnet'), 'cannot accept an expired offer');

  console.log('=== PRIVATE-BETA GATE ===');
  const gOff = R.gate({});
  ok(gOff.executionEnabled() === false && /DISABLED/.test(gOff.banner), 'no allowlist -> execution DISABLED');
  const gOn = R.gate({ allowlist: { evm: ['0xOWNER'], sost: ['sost1owner'] } });
  ok(gOn.executionEnabled() === true && /OWNER TESTING ONLY/.test(gOn.banner), 'allowlist -> enabled + owner banner');
  ok(gOn.isAllowed('evm', '0xowner') === true, 'gate allows listed address (case-insensitive)');
  ok(gOn.isAllowed('evm', '0xstranger') === false, 'gate blocks unlisted address');

  console.log('\nRESULT: ' + pass + ' passed / ' + fail + ' failed');
  if (fail) { console.log('FAILURES:\n - ' + fails.join('\n - ')); process.exit(1); }
  process.exit(0);
})();

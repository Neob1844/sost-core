/* SOST Sentinel — link policy tests (exact-host allowlist, https only).
 *
 * Usage: node tests/sentinel_link_policy.test.js [repo_root]
 *
 * 1. Adversarial vectors: every one must be NOT official (a false negative is
 *    a phishing link that would be treated as official).
 * 2. Legitimate official links: every one must be official (false positive).
 * 3. Crawl of website/: every https link the site itself points at on
 *    sostcore.com / www.sostcore.com / github.com/Neob1844 must stay official;
 *    every other absolute link must not be official.
 * 4. analyze() end-to-end: flags produced for messages.
 */
'use strict';
const fs = require('fs');
const path = require('path');

const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const S = require(path.join(root, 'website/js/sost-sentinel.js'));

let fneg = 0, fpos = 0, pass = 0;
const failures = [];
function expectUnsafe(u, why) {
  if (S.isOfficialUrl(u)) { fneg++; failures.push('FALSE_NEGATIVE ' + JSON.stringify(u) + ' (' + why + ')'); }
  else pass++;
}
function expectOfficial(u, why) {
  if (!S.isOfficialUrl(u)) { fpos++; failures.push('FALSE_POSITIVE ' + JSON.stringify(u) + ' (' + why + ')'); }
  else pass++;
}

// ── 1. adversarial vectors ────────────────────────────────────────────
const VECTORS = [
  ['https://evil.example/sostcore.com', 'official name in path'],
  ['https://evil.example/?u=https://sostcore.com', 'official URL in query'],
  ['https://evil.example/#sostcore.com', 'official name in fragment'],
  ['https://evil.example/github.com/neob1844', 'github path on other host'],
  ['https://sostcore.com.evil.example/', 'official as subdomain of attacker'],
  ['https://www.sostcore.com.evil.example/', 'www official as subdomain'],
  ['https://evil-sostcore.com/', 'prefix lookalike'],
  ['https://evilsostcore.com/', 'glued prefix'],
  ['https://sostcore.co/', 'TLD typo'],
  ['https://sostcore.com.co/', 'extra TLD'],
  ['https://sost-core.com/', 'hyphen lookalike'],
  ['https://s0stcore.com/', 'digit lookalike'],
  ['https://sostcore.org/', 'other TLD'],
  ['https://sub.sostcore.com/', 'unlisted subdomain'],
  ['https://wallet.sostcore.com/', 'unlisted subdomain (not allowlisted)'],
  ['https://evil.sostcore.com.attacker.example/', 'subdomain-shaped attacker host'],
  ['https://sostprotocol.com/', 'retired domain'],
  ['https://www.sostprotocol.com/', 'retired domain www'],
  ['https://sostprotocol.org/whitepaper', 'unregistered lookalike'],
  ['https://user@sostcore.com.evil.example/', 'userinfo + attacker host'],
  ['https://sostcore.com@evil.example/', 'official as userinfo'],
  ['https://sostcore.com:pass@evil.example/', 'official as user:pass'],
  ['https://user@sostcore.com/', 'userinfo on official host'],
  ['https://:@sostcore.com/', 'empty userinfo'],
  ['https://sostcore.com%40evil.example/', 'encoded @'],
  ['https://sostcore.com%2eevil.example/', 'encoded dot'],
  ['https://sostcore.com%2F@evil.example/', 'encoded slash + userinfo'],
  ['http://sostcore.com/', 'http (https-only policy)'],
  ['http://www.sostcore.com/', 'http www'],
  ['http://github.com/Neob1844', 'http github'],
  ['https://sostcore.com:8443/', 'explicit non-default port'],
  ['https://sostcore.com:80/', 'port 80 on https'],
  ['https://sostcore.com./', 'trailing-dot host (policy: not official)'],
  ['https://SOSTCORE.COM./', 'trailing-dot upper'],
  ['https://sostcore.com../', 'double trailing dot'],
  ['javascript:alert(1)', 'javascript scheme'],
  ['JavaScript:alert(document.domain)//https://sostcore.com', 'javascript with official tail'],
  ['javascript://sostcore.com/%0aalert(1)', 'javascript disguised as authority'],
  ['data:text/html,<a href=https://sostcore.com>x</a>', 'data URL'],
  ['data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==', 'data base64'],
  ['blob:https://sostcore.com/550e8400-e29b-41d4-a716-446655440000', 'blob of official origin'],
  ['file:///etc/passwd', 'file scheme'],
  ['file://sostcore.com/x', 'file with official host'],
  ['vbscript:msgbox(1)', 'vbscript'],
  ['ftp://sostcore.com/', 'ftp scheme'],
  ['wss://sostcore.com/', 'websocket scheme'],
  ['//sostcore.com/', 'protocol-relative'],
  ['//evil.example/', 'protocol-relative attacker'],
  ['///sostcore.com/', 'triple slash'],
  ['https:/sostcore.com/', 'single slash scheme'],
  ['https:sostcore.com', 'no slash scheme'],
  ['https:\\\\sostcore.com', 'backslash authority'],
  ['https://evil.example\\@sostcore.com/', 'backslash userinfo split'],
  ['https://sostcore.com\\.evil.example/', 'backslash in host'],
  ['https://evil.example\\sostcore.com', 'backslash path'],
  [' https://sostcore.com.evil.example', 'leading space'],
  ['https://sostcore.com\t.evil.example/', 'tab inside'],
  ['https://sostcore.com\n.evil.example/', 'newline inside'],
  ['https://sostcore.com\u0000.evil.example/', 'NUL inside'],
  ['https://ѕostcore.com/', 'Cyrillic s (IDN homograph)'],
  ['https://sostcоre.com/', 'Cyrillic o (IDN homograph)'],
  ['https://xn--ostcore-6ig.com/', 'punycode homograph'],
  ['https://sostcore．com/', 'fullwidth dot'],
  ['https://sostcore。com/', 'ideographic dot'],
  ['https://ｓｏｓｔｃｏｒｅ.com/', 'fullwidth letters'],
  ['https://sostcore.com​.evil.example/', 'zero-width space'],
  ['https://sostcore.com‮/moc.live', 'RTL override'],
  ['https://212.132.108.244/', 'raw IP'],
  ['https://[::1]/', 'IPv6 literal'],
  ['https://0xd4.0x84.0x6c.0xf4/', 'hex IP'],
  ['https://github.com/neob1844x', 'owner segment suffix'],
  ['https://github.com/neob1844-evil/repo', 'owner hyphen suffix'],
  ['https://github.com/xneob1844', 'owner prefix'],
  ['https://github.com/evil/neob1844', 'owner as second segment'],
  ['https://github.com/', 'github root'],
  ['https://github.com/neob%31844', 'percent-encoded owner'],
  ['https://github.com.evil.example/Neob1844', 'github as attacker subdomain'],
  ['https://gist.github.com/Neob1844', 'unlisted github subdomain'],
  ['https://raw.githubusercontent.com/Neob1844/sost-core/main/x', 'githubusercontent'],
  ['https://evil.example/redirect?to=github.com/neob1844', 'github in query'],
  ['https://github.com@evil.example/Neob1844', 'github userinfo'],
  ['https://sostcore.com.', 'trailing dot no slash'],
  ['', 'empty'],
  ['sostcore.com', 'bare host (no scheme)'],
  ['https://', 'scheme only'],
  [null, 'null'],
  [undefined, 'undefined'],
  [{ toString() { return 'https://sostcore.com/'; } }, 'object with toString'],
  ['https://' + 'a'.repeat(3000) + '.sostcore.com/', 'oversized'],
];
for (const [u, why] of VECTORS) expectUnsafe(u, why);

// ── 2. legitimate official links ───────────────────────────────────────
const LEGIT = [
  'https://sostcore.com', 'https://sostcore.com/', 'https://sostcore.com/sost-wallet.html',
  'https://sostcore.com/sost-explorer.html?h=30000#tx', 'https://SOSTCORE.COM/index.html',
  'https://www.sostcore.com/', 'https://sostcore.com:443/', 'https://sostcore.com/sost-markets.html?from=app',
  'https://github.com/Neob1844', 'https://github.com/Neob1844/', 'https://github.com/neob1844/sost-core',
  'https://github.com/Neob1844/sost-core/releases/tag/v30000-final.1', 'https://GitHub.com/NEOB1844/sost-core',
];
for (const u of LEGIT) expectOfficial(u, 'legit');
const vectorsTested = VECTORS.length;

// ── 3. crawl website/ outbound links ───────────────────────────────────
const webRoot = path.join(root, 'website');
const files = [];
(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    if (e.name === 'node_modules' || e.name.startsWith('.')) continue;
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(html|js)$/.test(e.name) && !/\.bak/.test(e.name)) files.push(p);
  }
})(webRoot);
const URL_RE = /https?:\/\/[A-Za-z0-9.\-]+(?::\d+)?(?:\/[^\s"'<>`)\\]*)?/g;
let crawlOfficial = 0, crawlOther = 0, crawlOtherUnsafe = 0;
const seen = new Set();
for (const f of files) {
  const txt = fs.readFileSync(f, 'utf8');
  for (const m of txt.match(URL_RE) || []) {
    const u = m.replace(/[.,;:!?]+$/, '');
    if (seen.has(u)) continue; seen.add(u);
    let host = '';
    try { host = new URL(u).hostname.toLowerCase(); } catch (e) { continue; }
    let seg = '';
    try { seg = (new URL(u).pathname.split('/')[1] || '').toLowerCase(); } catch (e) {}
    const shouldBeOfficial = /^https:/i.test(u) &&
      (host === 'sostcore.com' || host === 'www.sostcore.com' || (host === 'github.com' && seg === 'neob1844'));
    if (shouldBeOfficial) {
      crawlOfficial++;
      if (!S.isOfficialUrl(u)) { fpos++; failures.push('FALSE_POSITIVE (site link) ' + u + ' in ' + path.relative(root, f)); }
      else pass++;
    } else {
      crawlOther++;
      if (S.isOfficialUrl(u)) { fneg++; failures.push('FALSE_NEGATIVE (site link) ' + u + ' in ' + path.relative(root, f)); }
      else pass++;
      if (S.linkVerdict(u) === 'UNSAFE') crawlOtherUnsafe++;
    }
  }
}

// ── 4. analyze() end-to-end ────────────────────────────────────────────
let e2eFail = 0;
function flagsOf(msg, uid) { return S.analyze(msg, uid, 'tester').flags.map(f => f.type + ':' + (f.url || '')); }
function e2e(cond, label) { if (cond) pass++; else { e2eFail++; failures.push('ANALYZE ' + label); } }
let uid = 0;
const nextId = () => 'u' + (++uid);
e2e(flagsOf('Read https://sostcore.com/sost-wallet.html, then https://github.com/Neob1844/sost-core.', nextId()).length === 0, 'official links -> no flags');
e2e(flagsOf('Get it at (https://www.sostcore.com/sost-explorer.html).', nextId()).length === 0, 'bracketed official link -> no flags');
e2e(flagsOf('claim at https://evil.example/sostcore.com now', nextId()).join() === 'EXTERNAL_LINK:https://evil.example/sostcore.com', 'path trick -> EXTERNAL flag');
e2e(flagsOf('go https://sostcore.com.evil.example/ please', nextId()).join() === 'UNSAFE_LINK:https://sostcore.com.evil.example/', 'lookalike host -> UNSAFE');
e2e(flagsOf('open https://sostcore.com@evil.example/ please', nextId()).join() === 'UNSAFE_LINK:https://sostcore.com@evil.example/', 'userinfo -> UNSAFE');
e2e(flagsOf('click javascript:alert(1) here', nextId())[0].indexOf('UNSAFE_LINK:javascript:') === 0, 'javascript: -> UNSAFE');
e2e(flagsOf('see [docs](https://sostprotocol.com/x)', nextId()).join() === 'UNSAFE_LINK:https://sostprotocol.com/x', 'retired domain in markdown -> UNSAFE');
e2e(flagsOf('mirror //evil.example/wallet', nextId()).join() === 'UNSAFE_LINK://evil.example/wallet', 'protocol-relative -> UNSAFE');
e2e(flagsOf('docs at https://bitcointalk.org/index.php?topic=1', nextId()).join() === 'EXTERNAL_LINK:https://bitcointalk.org/index.php?topic=1', 'ordinary third party -> EXTERNAL INFO');
e2e(flagsOf('relay at https://relay.sostcore.com/x', nextId()).join() === 'EXTERNAL_LINK:https://relay.sostcore.com/x', 'own subdomain -> EXTERNAL, not UNSAFE');
e2e(flagsOf('plain http://sostcore.com/x', nextId()).join() === 'UNSAFE_LINK:http://sostcore.com/x', 'http official -> UNSAFE');
e2e(flagsOf('the metadata: field and the node file: config are fine', nextId()).length === 0, 'prose with "data:"/"file:" words -> no flags');

const ok = fneg === 0 && fpos === 0 && e2eFail === 0;
console.log('SENTINEL_HOST_VALIDATION=' + (ok ? 'PASS' : 'FAIL'));
console.log('PHISHING_VECTORS_TESTED=' + vectorsTested);
console.log('LEGIT_OFFICIAL_LINKS_TESTED=' + LEGIT.length);
console.log('SITE_LINKS_CRAWLED=' + (crawlOfficial + crawlOther) + ' (official=' + crawlOfficial + ', other=' + crawlOther + ', other_flagged_unsafe=' + crawlOtherUnsafe + ') from ' + files.length + ' files');
console.log('ANALYZE_E2E_FAILURES=' + e2eFail);
console.log('FALSE_POSITIVES=' + fpos);
console.log('FALSE_NEGATIVES=' + fneg);
console.log('CHECKS_PASSED=' + pass);
if (failures.length) { console.log(failures.slice(0, 50).join('\n')); }
process.exit(ok ? 0 : 1);

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
const { VECTORS, LEGIT } = require('./fixtures/sentinel_link_vectors.js');
for (const [u, why] of VECTORS) expectUnsafe(u, why);

// ── 2. legitimate official links ───────────────────────────────────────

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

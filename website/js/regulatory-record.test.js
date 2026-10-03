/* SOST Asset Registry — REGULATORY RECORD + PASSPORT VERSIONING security tests.
 * Run: node website/js/regulatory-record.test.js
 * Pure web/lab. No consensus / node / miner / RC change. NEVER fabricates results.
 */
'use strict';
var assert = require('assert');
var AP2 = require('./asset-passport-v2.js');
var REG = require('./regulatory-record.js');
var VER = require('./passport-versioning.js');

var pass = 0, fail = 0;
function ok(name) { pass++; console.log('PASS - ' + name); }
function bad(name, e) { fail++; console.log('FAIL - ' + name + ' :: ' + (e && e.stack || e)); }
async function test(name, fn) { try { await fn(); ok(name); } catch (e) { bad(name, e); } }

// a base regulatory input (deterministic: fixed timestamps so hashes are reproducible)
function baseDocs(valueDoc) {
  return [
    { document_type: 'PROOF_OF_TITLE_OWNERSHIP', filename: 'title.pdf', text: 'TITLE DEED v1', provenance: { source_type: 'LEGAL_DOCUMENT' }, verification_status: 'DOCUMENT PROVIDED', timestamp: '2026-10-03T00:00:00Z' },
    { document_type: 'INDEPENDENT_VALUATION', filename: 'valuation.pdf', text: (valueDoc || 'VALUATION 10,000,000 EUR'), provenance: { source_type: 'INDEPENDENT_EXPERT' }, verification_status: 'DECLARED', timestamp: '2026-10-03T00:00:00Z' }
  ];
}
function baseInput(over) {
  var f = {
    jurisdiction: 'Spain', asset_class: 'Mining asset', offering_model: 'REVENUE_PARTICIPATION',
    applicant: 'Example Mining S.L.', reviewer_id: 'admin:sost1993a8',
    documents: baseDocs(), applicant_declaration: 'Docs provided and reviewed.',
    acknowledgement_timestamp: '2026-10-03T12:00:00Z',
    checklist_reviewed_at: '2026-10-03T11:00:00Z', now: '2026-10-03T11:00:00Z'
  };
  if (over) Object.keys(over).forEach(function (k) { f[k] = over[k]; });
  return f;
}

(async function () {
  console.log('=== REGULATORY RECORD + PASSPORT VERSIONING — SECURITY TESTS ===');

  // 1) missing regulatory record -> EXECUTE refused
  await test('1. missing regulatory record -> EXECUTE refused', async function () {
    var threw = false;
    try { await REG.assertCanGenerate({ recordResult: null, acknowledgement_timestamp: 'x' }); }
    catch (e) { threw = /REGULATORY RECORD MISSING/.test(e.message); }
    assert(threw, 'assertCanGenerate must throw REGULATORY RECORD MISSING when no record');
  });

  // 2) tampered document -> detected (record hash no longer matches content)
  await test('2. tampered record/document -> detected + EXECUTE refused', async function () {
    var rr = await REG.buildRegulatoryRecord(baseInput());
    var v0 = await REG.verifyRecord(rr);
    assert(v0.recordMatches, 'fresh record must verify');
    // tamper: mutate a stored document hash inside the record (forge evidence)
    rr.record.documents[0].sha256 = 'deadbeef'.repeat(8);
    var v1 = await REG.verifyRecord(rr);
    assert(!v1.recordMatches, 'tampered record must NOT verify');
    var threw = false;
    try { await REG.assertCanGenerate({ recordResult: rr, acknowledgement_timestamp: rr.record.acknowledgement_timestamp }); }
    catch (e) { threw = /TAMPERING DETECTED/.test(e.message); }
    assert(threw, 'assertCanGenerate must refuse a tampered record');
  });

  // 3) changed document hash -> new version created, previous preserved
  await test('3. changed document -> new version (v2), previous (v1) preserved', async function () {
    var v1 = await REG.buildRegulatoryRecord(baseInput());
    assert(v1.record.record_version === 1, 'first version is 1');
    // same applicant, one document changed
    var v2 = await REG.nextVersion(v1, baseInput({ documents: baseDocs('VALUATION 12,500,000 EUR (revised)') }));
    assert(v2.record.record_version === 2, 'second version is 2');
    assert(v2.record.previous_record_hash === v1.record_hash, 'v2 keeps v1 hash as previous_record_hash');
    assert(v2.record_hash !== v1.record_hash, 'v2 hash differs from v1');
    assert(v2.changed === true, 'change detected');
    var changed = v2.changes.filter(function (c) { return c.change === 'CHANGED'; });
    assert(changed.length === 1 && changed[0].document_type === 'INDEPENDENT_VALUATION', 'exactly the valuation doc changed');
    // v1 result object must be untouched (not overwritten)
    assert(v1.record.record_version === 1 && v1.record.previous_record_hash == null, 'v1 preserved intact');
  });

  // 4) previous-version preservation across a non-overwriting history (versioning engine)
  await test('4. passport evidence history is non-overwriting (prev preserved)', async function () {
    var L = VER.newLedger();
    var a = await VER.putEvidence(L, { evidence_class: 'VALUATION', content: 'EUR 10,000,000', reason: 'initial appraisal', provenance: { source_type: 'INDEPENDENT_EXPERT' }, verification_status: 'DECLARED', retain: true, timestamp: 't1' });
    var b = await VER.putEvidence(L, { evidence_class: 'VALUATION', content: 'EUR 12,500,000', reason: 'revised appraisal', provenance: { source_type: 'INDEPENDENT_EXPERT' }, verification_status: 'INDEPENDENTLY VERIFIED', retain: true, timestamp: 't2' });
    assert(a.changed && b.changed, 'both writes created versions');
    var hist = VER.history(L, 'VALUATION');
    assert(hist.length === 2, 'history has 2 versions');
    assert(hist[0].version === 1 && hist[1].version === 2, 'sequential versions');
    assert(hist[1].previous_hash === hist[0].hash, 'v2 links to v1 hash');
    assert(VER.current(L, 'VALUATION').version === 2, 'current is v2');
    // identical content must NOT create a new version (no silent overwrite, no churn)
    var c = await VER.putEvidence(L, { evidence_class: 'VALUATION', content: 'EUR 12,500,000' });
    assert(c.changed === false && VER.versionCount(L, 'VALUATION') === 2, 'unchanged content => no new version');
    var vh = await VER.verifyHistory(L);
    assert(vh.ok === true, 'whole history verifies');
  });

  // 4b) tampering a retained history version is caught by verifyHistory
  await test('4b. tampered history version -> verifyHistory fails', async function () {
    var L = VER.newLedger();
    await VER.putEvidence(L, { evidence_class: 'TITLE_OWNERSHIP', content: 'DEED A', retain: true, timestamp: 't1' });
    await VER.putEvidence(L, { evidence_class: 'TITLE_OWNERSHIP', content: 'DEED B', retain: true, timestamp: 't2' });
    L.entries.TITLE_OWNERSHIP[0].content = 'FORGED DEED'; // tamper retained content, keep old hash
    var vh = await VER.verifyHistory(L);
    assert(vh.ok === false, 'tampered retained content must fail verifyHistory');
  });

  // 5) acknowledgement missing -> EXECUTE refused
  await test('5. acknowledgement missing -> EXECUTE refused', async function () {
    var rr = await REG.buildRegulatoryRecord(baseInput({ acknowledgement_timestamp: null }));
    var threw = false;
    try { await REG.assertCanGenerate({ recordResult: rr }); }
    catch (e) { threw = /ACKNOWLEDGEMENT MISSING/.test(e.message); }
    assert(threw, 'assertCanGenerate must refuse when acknowledgement missing');
  });

  // 5b) documents changed AFTER review -> EXECUTE refused (presented != reviewed)
  await test('5b. documents changed after acknowledgement -> EXECUTE refused', async function () {
    var rr = await REG.buildRegulatoryRecord(baseInput());
    // present a DIFFERENT valuation document than the one reviewed/acknowledged
    var presented = [
      { document_type: 'PROOF_OF_TITLE_OWNERSHIP', filename: 'title.pdf', text: 'TITLE DEED v1' },
      { document_type: 'INDEPENDENT_VALUATION', filename: 'valuation.pdf', text: 'VALUATION 99,000,000 EUR (swapped)' }
    ];
    var threw = false;
    try { await REG.assertCanGenerate({ recordResult: rr, acknowledgement_timestamp: rr.record.acknowledgement_timestamp, presentedDocuments: presented }); }
    catch (e) { threw = /DOCUMENT HASH MISMATCH/.test(e.message); }
    assert(threw, 'assertCanGenerate must refuse when presented docs differ from reviewed state');
    // control: presenting the SAME documents passes
    var samePresented = [
      { document_type: 'PROOF_OF_TITLE_OWNERSHIP', filename: 'title.pdf', text: 'TITLE DEED v1' },
      { document_type: 'INDEPENDENT_VALUATION', filename: 'valuation.pdf', text: 'VALUATION 10,000,000 EUR' }
    ];
    var r = await REG.assertCanGenerate({ recordResult: rr, acknowledgement_timestamp: rr.record.acknowledgement_timestamp, presentedDocuments: samePresented });
    assert(r.ok === true, 'matching presented docs must pass the gate');
  });

  // 6) manifestHash changes correctly when the regulatory record changes
  await test('6. manifestHash incorporates + changes with the regulatory record', async function () {
    var baseClaims = [
      AP2.valuationClaim({ amount: '10000000', currency: 'EUR', provenance: { source_type: 'DECLARING_PARTY' }, verification: 'DECLARED' }),
      AP2.rightClaim({ right_type: 'REVENUE_PARTICIPATION', economic_rights_declared: true, obligor: 'Example Mining S.L.', provenance: { source_type: 'DECLARING_PARTY' }, verification: 'DECLARED' })
    ];
    var fields = { issuer: 'sost1issuer', nonce: '0', category: 'Mining asset', locator: '', claims: baseClaims };

    // passport WITHOUT regulatory record
    var pPlain = await AP2.buildPassport({ issuer: fields.issuer, nonce: '0', category: fields.category, locator: '', claims: baseClaims.slice() });
    // passport WITH regulatory record v1
    var rr1 = await REG.buildRegulatoryRecord(baseInput());
    var p1 = await REG.buildPassportWithRegulatory(fields, rr1);
    assert(p1.manifestHash !== pPlain.manifestHash, 'adding the regulatory record must change manifestHash');
    assert(p1.regulatoryRecordHash === rr1.record_hash, 'passport carries the regulatory record hash');
    // the record is incorporated as a claim
    var hasRegClaim = p1.manifest.claims.some(function (c) { return c.id === 'regulatory-record' && c.value && c.value.regulatory_record_hash === rr1.record_hash; });
    assert(hasRegClaim, 'regulatory-record claim present in the manifest');

    // passport WITH regulatory record v2 (changed document) -> different manifestHash
    var rr2 = await REG.nextVersion(rr1, baseInput({ documents: baseDocs('VALUATION 12,500,000 EUR (revised)') }));
    var p2 = await REG.buildPassportWithRegulatory(fields, rr2);
    assert(p2.manifestHash !== p1.manifestHash, 'changing the regulatory record must change manifestHash');

    // rebuilding with the SAME record is deterministic (same manifestHash)
    var p1again = await REG.buildPassportWithRegulatory(fields, rr1);
    assert(p1again.manifestHash === p1.manifestHash, 'same record => same manifestHash (deterministic)');

    // v2 passport still verifies under the engine
    var vr = await AP2.verify(p2);
    assert(vr.manifestMatches === true, 'v2 passport manifest verifies');
  });

  // 7) forbidden auto-states are rejected + legal classification preserved
  await test('7. forbidden auto-states rejected; LEGAL CLASSIFICATION preserved', async function () {
    var threw = false;
    try { await REG.hashDocument({ document_type: 'X', text: 'y', verification_status: 'COMPLIANT' }); }
    catch (e) { threw = /FORBIDDEN|invalid verification_status/.test(e.message); }
    assert(threw, 'COMPLIANT must be rejected');
    var threw2 = false;
    try { await REG.hashDocument({ document_type: 'X', text: 'y', verification_status: 'AUTHORIZED' }); }
    catch (e) { threw2 = /FORBIDDEN|invalid verification_status/.test(e.message); }
    assert(threw2, 'AUTHORIZED must be rejected');
    var rr = await REG.buildRegulatoryRecord(baseInput());
    assert(rr.record.legal_classification === 'NOT DETERMINED BY SOST', 'record carries NOT DETERMINED BY SOST');
    rr.record.documents.forEach(function (d) {
      assert(REG.ALLOWED_DOC_STATES.indexOf(d.verification_status) >= 0, 'only allowed doc states present');
    });
    // versioning engine rejects forbidden states too
    var L = VER.newLedger(), threw3 = false;
    try { await VER.putEvidence(L, { evidence_class: 'AUDIT', content: 'x', verification_status: 'LEGAL' }); }
    catch (e) { threw3 = /FORBIDDEN|invalid verification_status/.test(e.message); }
    assert(threw3, 'versioning engine rejects LEGAL state');
  });

  // 8) checklist is derived deterministically from jurisdiction + asset_class
  await test('8. checklist derived deterministically from jurisdiction + asset_class', async function () {
    var c1 = REG.deriveChecklist('Spain', 'Mining asset', 'REVENUE_PARTICIPATION');
    var c2 = REG.deriveChecklist('Spain', 'Mining asset', 'REVENUE_PARTICIPATION');
    assert(JSON.stringify(c1) === JSON.stringify(c2), 'checklist is deterministic');
    assert(c1.required_documents.indexOf('CONCESSION_TITLE') >= 0, 'mining requires a concession title');
    assert(c1.required_documents.indexOf('REGULATORY_AUTHORIZATION') >= 0, 'economic offer requires regulatory authorization doc');
    var re = REG.deriveChecklist('Spain', 'Real estate', 'CERTIFICATE');
    assert(re.required_documents.indexOf('CADASTRAL_REFERENCE') >= 0, 'real estate requires a cadastral reference');
    assert(JSON.stringify(c1.required_documents) !== JSON.stringify(re.required_documents), 'different asset classes derive different checklists');
  });

  console.log('\n=== RESULT: ' + pass + ' passed, ' + fail + ' failed ===');
  process.exit(fail === 0 ? 0 : 1);
})().catch(function (e) { console.log('FATAL', e && e.stack || e); process.exit(1); });

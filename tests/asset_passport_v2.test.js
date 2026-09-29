/* SOST Asset Passport v2 test suite — schema, canonicalization, v1 compat, v2, engines, anchor. */
const V1 = require('../website/js/asset-passport.js');
const V2 = require('../website/js/asset-passport-v2.js');
let pass = 0, fail = 0; const fails = [];
function ok(c, m){ if(c){pass++;} else {fail++; fails.push(m); console.log('  ❌ '+m);} }
function throws(fn, m){ try{ fn(); fail++; fails.push(m+' (did not throw)'); console.log('  ❌ '+m+' (did not throw)'); }catch(e){ pass++; } }

(async () => {
  console.log('=== 1. CANONICALIZATION ===');
  ok(V2.canon({b:1,a:2}) === V2.canon({a:2,b:1}), 'canon key-order independent');
  ok(V2.canon({a:[3,1,2]}) === '{"a":[3,1,2]}', 'canon preserves array order');
  ok(V2.canon('áé😀') === JSON.stringify('áé😀'), 'canon unicode string');
  ok(V2.canon({n:42}) === '{"n":42}', 'canon integer ok');
  throws(() => V2.canon({n:1.5}), 'canon rejects non-integer number');
  ok(V2.canon(null) === 'null' && V2.canon(true) === 'true', 'canon null/bool');

  console.log('=== 2. SCHEMA VALIDATION ===');
  ok(V2.validateClaim({id:'c1',class:'FACT',verification:{status:'DECLARED'}}), 'valid FACT claim');
  throws(() => V2.validateClaim({id:'x',class:'NOPE'}), 'invalid class rejected');
  throws(() => V2.validateClaim({id:'x',class:'RIGHT',value:{right_type:'BOGUS'}}), 'invalid right subtype rejected');
  throws(() => V2.validateClaim({id:'x',class:'FACT',provenance:{source_type:'BOGUS'}}), 'invalid provenance type rejected');
  throws(() => V2.validateClaim({id:'x',class:'FACT',confidence:150}), 'confidence>100 rejected');
  throws(() => V2.validateClaim({class:'FACT'}), 'missing id rejected');

  console.log('=== 3. V1 COMPATIBILITY (hash unchanged, verify, normalize) ===');
  const v1inputs = { category:'machinery', issuer:'sost1issuerX', nonce:'0',
    ownerDeclaration:'I hold the asset', jurisdiction:'ES', rights:'bearer claim',
    documents:[{name:'invoice.pdf', text:'CAT 390F'}], locator:'ipfs://Qm-v1' };
  const v1a = await V1.buildPassport(v1inputs);
  const v1b = await V1.buildPassport(v1inputs);
  ok(v1a.manifestHash === v1b.manifestHash, 'v1 build deterministic');
  const V1_HASH = v1a.manifestHash;
  const vr1 = await V2.verify(v1a);
  ok(vr1.version === 1, 'v2.verify detects v1');
  ok(vr1.manifestMatches === true, 'v2.verify reproduces v1 hash byte-exact');
  ok(vr1.recomputed === V1_HASH, 'v1 recomputed == original v1 hash');
  const norm = V2.normalizeV1ToClaims(v1a);
  ok(norm.raw_hash === V1_HASH, 'normalized view keeps raw v1 hash');
  ok(norm.version === 1 && norm.claims.length >= 4, 'v1 normalized to claims (read-only)');
  ok(JSON.stringify(v1a.manifest) === JSON.stringify(v1b.manifest), 'v1 manifest not mutated by v2');
  console.log('  V1_FIXTURE_HASH=' + V1_HASH);

  console.log('=== 4. V2 CREATE / RELOAD / TAMPER ===');
  const v2inputs = { issuer:'sost1issuerX', nonce:'7', category:'machinery', locator:'ipfs://Qm-v2',
    claims:[
      V2.valuationClaim({ amount:'100000', currency:'EUR', range_low:'92000', range_high:'108000', recoverable:'80000', methodology:'comparables+income', confidence:78, provenance:{source_type:'INDEPENDENT_EXPERT', source_name:'Appraiser AB', reference:'report-123'}, verification:'ATTESTED' }),
      V2.rightClaim({ right_type:'REVENUE_PARTICIPATION', description:'5% of net rental revenue', economic_rights_declared:true, obligor:'Empresa X S.L.', agreement_reference:'contract-9', agreement_hash:'ab73ffee', distribution_mechanism:'quarterly bank transfer', token_supply:'100000', token_decimals:6, verification:'DECLARED' }),
      { id:'owner', class:'OWNERSHIP_DECLARATION', value:{declaration:'Empresa X declares title'}, provenance:{source_type:'DECLARING_PARTY'}, verification:{status:'DECLARED'} }
    ]};
  const p2a = await V2.buildPassport(v2inputs);
  const p2b = await V2.buildPassport(v2inputs);
  ok(p2a.manifestHash === p2b.manifestHash, 'v2 build deterministic (same inputs -> same hash)');
  const V2_HASH = p2a.manifestHash;
  const vr2 = await V2.verify(p2a);
  ok(vr2.version === 2 && vr2.manifestMatches === true, 'v2.verify reproduces v2 hash');
  ok(vr2.claimsValid === true, 'v2 claims valid');
  // reload (simulate persistence roundtrip)
  const reloaded = JSON.parse(JSON.stringify(p2a));
  const vr2r = await V2.verify(reloaded);
  ok(vr2r.manifestMatches === true, 'v2 verifies after JSON reload');
  // tamper: change one byte of a claim value
  const tampered = JSON.parse(JSON.stringify(p2a));
  tampered.manifest.claims.find(c=>c.class==='VALUATION').value.amount = '150000';
  const vt = await V2.verify(tampered);
  ok(vt.manifestMatches === false, 'TAMPER DETECTED (changed valuation -> hash mismatch)');
  ok(V2_HASH !== V1_HASH, 'v1 and v2 never produce the same hash');
  console.log('  V2_TEST_VECTOR_HASH=' + V2_HASH);

  console.log('=== 5. ROLL-UP / ENGINES ===');
  ok(vr2.rollup.economic_rights_declared === true, 'rollup: economic_rights_declared');
  ok(vr2.rollup.obligor_identified === true, 'rollup: obligor_identified');
  ok(vr2.rollup.agreement_attached === true, 'rollup: agreement_attached');
  ok(vr2.rollup.legal_title_verified === false, 'rollup: legal_title_verified NO (only declared)');
  ok(vr2.rollup.legal_classification === 'NOT DETERMINED BY SOST', 'rollup: legal classification not determined by SOST');
  ok(vr2.rollup.by_status.ATTESTED === 1 && vr2.rollup.by_status.DECLARED === 2, 'rollup per-claim status counts');

  console.log('=== 6. ANCHOR (capsule doc_ref) ===');
  const cap = V2.capsuleDocRef(p2a);
  ok(cap.ok === true && cap.bytes <= 243, 'v2 doc_ref within 243B body limit');
  ok(cap.body.h === V2_HASH, 'anchor body.h == v2 manifestHash');

  console.log('\nRESULT: ' + pass + ' passed / ' + fail + ' failed');
  if (fail) { console.log('FAILURES:\n - ' + fails.join('\n - ')); process.exit(1); }
  process.exit(0);
})();

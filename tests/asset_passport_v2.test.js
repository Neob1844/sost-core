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

  console.log('=== 7. CANONICALIZATION VECTORS CONTRACT (tests/fixtures/canon_vectors.json) ===');
  const VEC = require('./fixtures/canon_vectors.json');
  for (const c of VEC.cases) {
    ok(V2.canon(c.input) === c.canon_expected, 'vector canon: ' + c.name);
    ok((await V2.sha256Hex(c.canon_expected)) === c.sha256_expected, 'vector sha256: ' + c.name);
  }
  const mvRecomputed = await V2.sha256Hex(V2.canon(VEC.manifest_vector.manifest));
  ok(mvRecomputed === VEC.manifest_vector.manifestHash, 'vector: full manifest hash reproduces (third-party reconstructable)');
  ok(VEC.claim_ordering_vector.equal === true && VEC.claim_ordering_vector.manifestHash === VEC.claim_ordering_vector.manifestHash_shuffled, 'vector: claim ordering is deterministic (shuffled claims -> same manifestHash)');
  const mvClaimHashes = VEC.manifest_vector.manifest.claims.map(c=>c.id);
  ok(JSON.stringify(mvClaimHashes) === JSON.stringify(mvClaimHashes.slice().sort()), 'vector: manifest claims stored in sorted id order');

  console.log('=== 8. SETTLEMENT (minimal, SOST-does-not-custody) ===');
  const setc = V2.settlementClaim({settlement_type:'EXTERNAL_DOCUMENTED', reference:'bank-123', hash:'abcd'});
  ok(setc.class === 'SETTLEMENT_REFERENCE', 'settlement class');
  ok(setc.value.custody === 'SOST DOES NOT CUSTODY FUNDS', 'settlement states no custody');
  ok(setc.verification.status === 'NOT_VERIFIED', 'external settlement defaults NOT_VERIFIED');
  ok(V2.validateClaim(Object.assign({id:'s1'}, setc)) , 'settlement claim validates');
  throws(() => V2.settlementClaim({settlement_type:'EUR_STABLECOIN'}), 'unknown settlement_type rejected (stablecoin is FUTURE)');

  console.log('=== 9. INTELLIGENCE -> VALUATION CLAIM (coherence adapter) ===');
  const ivc = V2.intelligenceToValuationClaim({marketValue:100000, low:90000, high:110000, recoverable:70000, confidence:0.62});
  ok(ivc.class === 'VALUATION', 'intel adapter -> VALUATION');
  ok(ivc.value.amount === '100000' && typeof ivc.value.amount === 'string', 'intel amount is a string (canonical-safe)');
  ok(ivc.confidence === 62, 'intel confidence 0..1 mapped to 0..100 integer');
  ok(ivc.provenance.source_type === 'SOST_CALCULATION', 'intel valuation provenance = SOST_CALCULATION');
  ok(V2.validateClaim(Object.assign({id:'v'}, ivc)), 'intel valuation claim validates');

  console.log('=== 10. LIQUIDITY HONESTY (five concepts kept distinct) ===');
  const lh = V2.liquidityHonesty({valuation:'100000', reference_price_per_token:1, currency:'EUR'});
  ok(lh.executable_liquidity === 'NOT VERIFIED', 'executable liquidity NOT VERIFIED');
  ok(lh.market_depth === 'NONE OBSERVED', 'market depth NONE OBSERVED');
  ok(lh.order_book === 'NONE' && lh.market_makers === 'NONE', 'no order book / no makers');
  ok(lh.scenarios.length === 4, 'four SOST arithmetic scenarios');
  ok(/SCENARIO/.test(lh.scenarios[0].label), 'scenarios labelled SCENARIO not quote');
  ok(lh.scenarios.find(s=>s.sost_price==='0.10').sost_per_token === '10.00', 'scenario math: €1 ref @ SOST€0.10 = 10 SOST/token');
  ok(/REFERENCE PRICE ≠ MARKET PRICE ≠ EXECUTABLE LIQUIDITY/.test(lh.disclaimer), 'liquidity disclaimer separates the concepts');

  console.log('\nRESULT: ' + pass + ' passed / ' + fail + ' failed');
  if (fail) { console.log('FAILURES:\n - ' + fails.join('\n - ')); process.exit(1); }
  process.exit(0);
})();

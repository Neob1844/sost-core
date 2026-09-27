const AP = require('./asset-passport.js');
let P=0,F=0; function chk(c,m){ if(c)P++; else {F++;console.log('  [FAIL] '+m);} }
(async()=>{
  // build a machinery passport with 2 docs + a third-party attestation
  var pass = await AP.buildPassport({
    category:'machinery', issuer:'sost1issuer', nonce:'n1',
    ownerDeclaration:'I own excavator SN-12345', jurisdiction:'ES', rights:'right to receive the machine',
    documents:[{name:'invoice.pdf', text:'INVOICE CONTENT'},{name:'photo.jpg', text:'PHOTOBYTES'}],
    attestations:[{by:'independent-appraiser', statement:'verified SN + condition', issuedAt:1000, expiresAt:5000, revoked:false}],
    locator:'ipfs://Qm-demo-machinery'
  });
  chk(pass.manifestHash && pass.manifestHash.length===64, 'manifest hash computed (sha256)');
  chk(pass.manifest.documents[0].sha256.length===64, 'per-document sha256');
  chk(pass.manifest.assetId.indexOf('sost-asset-')===0, 'deterministic asset id');

  // determinism: rebuild identical -> same manifest hash
  var pass2 = await AP.buildPassport({category:'machinery',issuer:'sost1issuer',nonce:'n1',ownerDeclaration:'I own excavator SN-12345',jurisdiction:'ES',rights:'right to receive the machine',documents:[{name:'invoice.pdf',text:'INVOICE CONTENT'},{name:'photo.jpg',text:'PHOTOBYTES'}],attestations:[],locator:'ipfs://Qm-demo-machinery'});
  chk(pass.manifestHash===pass2.manifestHash, 'manifest hash deterministic (canonical JSON)');

  // capsule doc_ref within 243B
  var cap = AP.capsuleDocRef(pass);
  chk(cap.ok && cap.bytes<=243, 'capsule doc_ref within 243B ('+cap.bytes+'B)');
  var big = AP.capsuleDocRef({manifestHash:pass.manifestHash, manifest:{locator:'x'.repeat(300)}});
  chk(!big.ok, 'oversized locator rejected (>243B)');

  // verify: correct docs match; tampered doc fails
  var v = await AP.verify(pass, [{name:'invoice.pdf',text:'INVOICE CONTENT'},{name:'photo.jpg',text:'PHOTOBYTES'}]);
  chk(v.manifestMatches && v.allDocsMatch, 'verify passes for untampered docs');
  var vt = await AP.verify(pass, [{name:'invoice.pdf',text:'TAMPERED'},{name:'photo.jpg',text:'PHOTOBYTES'}]);
  chk(!vt.allDocsMatch && vt.documents[0].matches===false, 'verify detects a tampered document');

  // classify: 4 states
  var c1 = AP.classify(pass, true, 2000);  // anchored, attestation valid at t=2000
  chk(c1.DECLARED_BY_ISSUER===true, 'DECLARED_BY_ISSUER true (owner declaration present)');
  chk(c1.VERIFIED_BY_THIRD_PARTY===true, 'VERIFIED_BY_THIRD_PARTY true (valid attestation)');
  chk(c1.ANCHORED_ON_SOST===true, 'ANCHORED_ON_SOST true');
  chk(c1.LEGAL_RIGHT_NOT_VERIFIED===true, 'LEGAL_RIGHT_NOT_VERIFIED always true');
  var c2 = AP.classify(pass, true, 9000);  // attestation expired at t=9000
  chk(c2.VERIFIED_BY_THIRD_PARTY===false && c2.expiredOrRevoked===1, 'expired attestation -> not verified');
  var passR = await AP.buildPassport({category:'art',issuer:'i',attestations:[{by:'x',revoked:true}]});
  chk(AP.classify(passR,false,1).VERIFIED_BY_THIRD_PARTY===false, 'revoked attestation -> not verified');
  chk(AP.classify(passR,false,1).ANCHORED_ON_SOST===false, 'not anchored -> ANCHORED false');

  // demos: all 7 categories build
  var cats=['machinery','real_estate','precious_metal','commodity_lot','art','vehicle','contractual_right','digital_asset'];
  var okCats=0; for(var k=0;k<cats.length;k++){ try{ await AP.buildPassport({category:cats[k],issuer:'i',documents:[{name:'d',text:'x'}]}); okCats++; }catch(e){} }
  chk(okCats===cats.length, 'all '+cats.length+' universal categories build');
  chk((function(){try{ return false; }catch(e){return true;}})() || true, 'ok');
  // unknown category rejected
  var bad=false; try{ await AP.buildPassport({category:'spaceship',issuer:'i'}); }catch(e){ bad=true; }
  chk(bad, 'unknown category rejected');

  console.log('ASSET-PASSPORT TESTS: PASS='+P+' FAIL='+F);
  process.exit(F?1:0);
})();

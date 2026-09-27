/* SOST Asset Studio — Asset Passport core (lab, NO consensus change).
 * Builds a universal asset passport, hashes documents (SHA-256), computes a manifest hash, and
 * shapes the on-chain anchor as a SOST Capsule doc_ref (verified live on mainnet since block 7350;
 * body <=243B, so only the 32-byte manifest hash + an off-chain locator are anchored — never the
 * documents themselves). Verification re-hashes documents and checks attestation validity.
 *
 * FOUR STATES, never conflated (the chain proves NONE of the legal facts):
 *   DECLARED_BY_ISSUER   — the issuer asserted it (self-declaration).
 *   VERIFIED_BY_THIRD_PARTY — a non-expired, non-revoked attestation from a third party exists.
 *   ANCHORED_ON_SOST     — the manifest hash is committed on-chain (proves existence-at-time only).
 *   LEGAL_RIGHT_NOT_VERIFIED — ALWAYS true here: on-chain anchoring is NOT proof of ownership,
 *                              authenticity, or any enforceable legal right.
 */
(function (root, factory){ var m=factory(); if(typeof module!=='undefined'&&module.exports){module.exports=m;} if(root){root.SOSTAssetPassport=m;} })(typeof self!=='undefined'?self:this, function(){
  'use strict';
  var CAPSULE_MAX_BODY = 243; // verified: include/sost/capsule.h

  // async SHA-256 -> hex, works in browser (crypto.subtle) and node (crypto)
  async function sha256Hex(bytes){
    if(typeof bytes === 'string'){ bytes = new TextEncoder ? new TextEncoder().encode(bytes) : Buffer.from(bytes,'utf8'); }
    if(typeof crypto!=='undefined' && crypto.subtle){
      var buf = await crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,'0');}).join('');
    }
    var nc = require('crypto'); return nc.createHash('sha256').update(Buffer.from(bytes)).digest('hex');
  }

  // canonical JSON (sorted keys) so the manifest hash is deterministic
  function canon(o){
    if(o===null||typeof o!=='object') return JSON.stringify(o);
    if(Array.isArray(o)) return '['+o.map(canon).join(',')+']';
    return '{'+Object.keys(o).sort().map(function(k){return JSON.stringify(k)+':'+canon(o[k]);}).join(',')+'}';
  }

  var CATEGORIES = ['machinery','real_estate','precious_metal','commodity_lot','art','vehicle','contractual_right','digital_asset'];

  // deterministic asset id from issuer + nonce + category (collision-resistant; no supply link to SOST)
  async function assetId(issuer, nonce, category){
    return 'sost-asset-' + (await sha256Hex(issuer+'|'+nonce+'|'+category)).slice(0,40);
  }

  // build a passport. docs: [{name, bytes|text}]; attestations: [{by, statement, issuedAt, expiresAt, revoked}]
  async function buildPassport(f){
    if(CATEGORIES.indexOf(f.category)<0) throw new Error('unknown category: '+f.category);
    if(!f.issuer) throw new Error('issuer required');
    var docs = [];
    for(var i=0;i<(f.documents||[]).length;i++){
      var d=f.documents[i]; docs.push({name:d.name, sha256: await sha256Hex(d.bytes!=null?d.bytes:(d.text||'')), bytes: (d.bytes!=null?d.bytes.length:(d.text||'').length)});
    }
    var id = f.assetId || await assetId(f.issuer, f.nonce||'0', f.category);
    var manifestFields = {
      assetId:id, category:f.category, issuer:f.issuer,
      ownerDeclaration:f.ownerDeclaration||null, jurisdiction:f.jurisdiction||null,
      rights:f.rights||null, encumbrances:f.encumbrances||[], disputes:f.disputes||[],
      documents:docs, locator:f.locator||null, version:f.version||1
    };
    var manifestHash = await sha256Hex(canon(manifestFields));
    return {
      manifest:manifestFields, manifestHash:manifestHash,
      attestations:(f.attestations||[]),
      privacy:{ note:'documents & personal data stay OFF-CHAIN; only hashes + a locator are anchored' }
    };
  }

  // the on-chain anchor payload for a SOST Capsule doc_ref (validated against the 243B body limit)
  function capsuleDocRef(passport){
    var body = { m:'doc_ref', h:passport.manifestHash, loc:(passport.manifest.locator||'') };
    var enc = canon(body);
    var bytes = (typeof TextEncoder!=='undefined') ? new TextEncoder().encode(enc).length : Buffer.byteLength(enc,'utf8');
    return { ok: bytes<=CAPSULE_MAX_BODY, bytes:bytes, max:CAPSULE_MAX_BODY, body:body, encoded:enc,
             error: bytes<=CAPSULE_MAX_BODY?null:('locator too long: '+bytes+'B > '+CAPSULE_MAX_BODY+'B — shorten the off-chain locator') };
  }

  // classify each rights/claim into the four states (nowMs for attestation expiry)
  function classify(passport, anchored, nowMs){
    var valid = passport.attestations.filter(function(a){ return !a.revoked && (!a.expiresAt || nowMs<=a.expiresAt); });
    return {
      DECLARED_BY_ISSUER: !!(passport.manifest.ownerDeclaration || passport.manifest.rights),
      VERIFIED_BY_THIRD_PARTY: valid.length>0,
      validAttestations: valid.length,
      expiredOrRevoked: passport.attestations.length - valid.length,
      ANCHORED_ON_SOST: !!anchored,
      LEGAL_RIGHT_NOT_VERIFIED: true  // ALWAYS — the chain never proves a legal right
    };
  }

  // verify: re-hash the presented documents against the passport; recompute the manifest hash
  async function verify(passport, presentedDocs){
    var byName={}; (presentedDocs||[]).forEach(function(d){ byName[d.name]=d; });
    var docResults=[];
    for(var i=0;i<passport.manifest.documents.length;i++){
      var pd=passport.manifest.documents[i], got=byName[pd.name];
      var ok=false, h=null;
      if(got){ h=await sha256Hex(got.bytes!=null?got.bytes:(got.text||'')); ok=(h===pd.sha256); }
      docResults.push({name:pd.name, present:!!got, matches:ok, expected:pd.sha256, got:h});
    }
    var recomputed = await sha256Hex(canon(passport.manifest));
    return { manifestMatches: recomputed===passport.manifestHash, recomputed:recomputed,
             documents:docResults, allDocsMatch: docResults.every(function(r){return r.matches;}) };
  }

  return { CATEGORIES:CATEGORIES, sha256Hex:sha256Hex, canon:canon, assetId:assetId,
           buildPassport:buildPassport, capsuleDocRef:capsuleDocRef, classify:classify, verify:verify,
           CAPSULE_MAX_BODY:CAPSULE_MAX_BODY };
});

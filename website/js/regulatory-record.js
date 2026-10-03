/* SOST Asset Registry — REGULATORY RECORD (integrated into the Asset Passport).
 * ---------------------------------------------------------------------------
 * This is an INTEGRITY / DOCUMENTATION layer, NOT an automatic legal validation.
 * It records, hashes and versions the regulatory documentation an applicant
 * declares for a tokenization, incorporates that record into the Asset Passport
 * and its manifestHash, and refuses passport generation at the registry integrity
 * layer (not only a UI checkbox) when the record is missing, the acknowledgement
 * is missing, or the reviewed document hashes no longer match.
 *
 * HARD RULES (enforced in code):
 *   - A document's verification_status may ONLY be one of:
 *        DECLARED · DOCUMENT PROVIDED · INDEPENDENTLY VERIFIED
 *   - It NEVER auto-generates LEGAL / COMPLIANT / REGULATORY APPROVED / AUTHORIZED.
 *   - Every record carries  legal_classification: 'NOT DETERMINED BY SOST'.
 *
 * No consensus / node / miner / RC change. Pure web/lab. Reuses the real
 * canonicalization + SHA-256 from SOSTAssetPassportV2 so hashes match the passport.
 */
(function (root, factory) {
  var dep = (typeof module !== 'undefined' && module.exports)
    ? require('./asset-passport-v2.js')
    : (root && root.SOSTAssetPassportV2);
  var m = factory(dep);
  if (typeof module !== 'undefined' && module.exports) { module.exports = m; }
  if (root) { root.SOSTRegulatoryRecord = m; }
})(typeof self !== 'undefined' ? self : this, function (AP2) {
  'use strict';
  if (!AP2) { throw new Error('SOSTRegulatoryRecord requires SOSTAssetPassportV2 (canon + sha256Hex)'); }

  var sha256Hex = AP2.sha256Hex, canon = AP2.canon, strip = AP2.strip;

  var RECORD_VERSION_SCHEMA = 1;
  var CHECKLIST_VERSION = '2026-10-reg-v1';

  // The ONLY allowed document verification states. Nothing else may ever be stored.
  var ALLOWED_DOC_STATES = ['DECLARED', 'DOCUMENT PROVIDED', 'INDEPENDENTLY VERIFIED'];
  // States a record must NEVER auto-assert (defensive guard; also blocked by the allow-list).
  var FORBIDDEN_STATES = ['LEGAL', 'COMPLIANT', 'REGULATORY APPROVED', 'APPROVED', 'AUTHORIZED', 'AUTHORISED'];
  var LEGAL_CLASSIFICATION = 'NOT DETERMINED BY SOST';

  function assert(cond, msg) { if (!cond) throw new Error(msg); }

  function assertDocState(s) {
    var up = String(s == null ? '' : s).toUpperCase();
    if (FORBIDDEN_STATES.indexOf(up) >= 0) {
      throw new Error('FORBIDDEN verification_status "' + s + '": SOST never auto-asserts LEGAL / COMPLIANT / REGULATORY APPROVED / AUTHORIZED. Allowed: ' + ALLOWED_DOC_STATES.join(' / '));
    }
    assert(ALLOWED_DOC_STATES.indexOf(s) >= 0,
      'invalid verification_status "' + s + '" — allowed only: ' + ALLOWED_DOC_STATES.join(' / '));
    return s;
  }

  // ---- checklist derivation (deterministic) --------------------------------
  // DOCUMENTATION derivation from jurisdiction + asset_class + offering_model.
  // This is orientation only — it is NOT a legal determination of what the law
  // requires. The output is stable so the record hash is reproducible.
  function norm(s) { return String(s == null ? '' : s).toLowerCase(); }

  function deriveChecklist(jurisdiction, asset_class, offering_model) {
    var ac = norm(asset_class), om = norm(offering_model), ju = norm(jurisdiction);
    var items = {}; // document_type -> true (set, de-duplicated, then sorted)
    function need(t) { items[t] = true; }

    // universal baseline
    need('PROOF_OF_TITLE_OWNERSHIP');
    need('INDEPENDENT_VALUATION');
    need('LEGAL_MEMORANDUM');

    // asset-class specific
    if (ac.indexOf('real estate') >= 0 || ac.indexOf('land') >= 0 || ac.indexOf('building') >= 0) {
      need('CADASTRAL_REFERENCE'); need('CUSTODY_EVIDENCE');
    }
    if (ac.indexOf('mining') >= 0) {
      need('CONCESSION_TITLE'); need('TECHNICAL_REPORT'); need('ENVIRONMENTAL_PERMIT');
    }
    if (ac.indexOf('machinery') >= 0 || ac.indexOf('vehicle') >= 0 || ac.indexOf('art') >= 0 ||
        ac.indexOf('metal') >= 0 || ac.indexOf('commodit') >= 0 || ac.indexOf('inventory') >= 0 ||
        ac.indexOf('physical') >= 0) {
      need('CUSTODY_EVIDENCE');
    }
    if (ac.indexOf('debt') >= 0 || ac.indexOf('loan') >= 0 || ac.indexOf('receivable') >= 0 ||
        ac.indexOf('bond') >= 0 || ac.indexOf('note') >= 0) {
      need('OFFERING_DOCUMENT'); need('AUDIT_EVIDENCE');
    }
    if (ac.indexOf('equity') >= 0 || ac.indexOf('share') >= 0 || ac.indexOf('ownership') >= 0 ||
        ac.indexOf('fund') >= 0) {
      need('OFFERING_DOCUMENT'); need('AUDIT_EVIDENCE'); need('CORPORATE_RESOLUTION');
    }
    if (ac.indexOf('royalt') >= 0 || ac.indexOf('ip') >= 0 || ac.indexOf('intellectual') >= 0 ||
        ac.indexOf('licen') >= 0) {
      need('IP_REGISTRATION'); need('LICENSE_AGREEMENT');
    }

    // offering-model specific (economic offers)
    if (om.indexOf('revenue') >= 0 || om.indexOf('debt') >= 0 || om.indexOf('equity') >= 0 ||
        om.indexOf('ownership') >= 0 || om.indexOf('proceeds') >= 0 || om.indexOf('royalt') >= 0) {
      need('OFFERING_DOCUMENT'); need('REGULATORY_AUTHORIZATION');
    }

    // jurisdiction (orientation only)
    if (ju.indexOf('spain') >= 0 || ju === 'es' || ju.indexOf('eu') >= 0 || ju.indexOf('europe') >= 0) {
      need('REGULATORY_AUTHORIZATION');
    } else {
      need('REGULATORY_AUTHORIZATION');
    }

    var required = Object.keys(items).sort();
    return {
      checklist_version: CHECKLIST_VERSION,
      jurisdiction: jurisdiction || null,
      asset_class: asset_class || null,
      offering_model: offering_model || null,
      required_documents: required,
      note: 'DOCUMENTATION CHECKLIST derived deterministically from jurisdiction + asset class + offering model. Orientation only — NOT a legal determination. LEGAL CLASSIFICATION: ' + LEGAL_CLASSIFICATION
    };
  }

  // ---- document hashing ----------------------------------------------------
  // doc input: { document_type, filename|reference, bytes|text, provenance, source,
  //              verification_status?, version?, timestamp? }
  async function hashDocument(doc) {
    assert(doc && typeof doc === 'object', 'document must be an object');
    assert(doc.document_type, 'document.document_type required');
    var content = (doc.bytes != null) ? doc.bytes : (doc.text != null ? doc.text : (doc.content != null ? doc.content : ''));
    var sha = await sha256Hex(content);
    var status = assertDocState(doc.verification_status || 'DECLARED');
    return strip({
      document_type: doc.document_type,
      filename: doc.filename || doc.reference || null,
      reference: doc.reference || null,
      sha256: sha,
      provenance: doc.provenance || doc.source || null,
      verification_status: status,
      version: (doc.version != null ? doc.version : 1),
      timestamp: doc.timestamp || null
    });
  }

  async function hashDocuments(docs) {
    var out = [];
    for (var i = 0; i < (docs || []).length; i++) { out.push(await hashDocument(docs[i])); }
    return out;
  }

  // ---- canonical record hash (over the record, record_hash excluded) -------
  async function recordHash(record) {
    return await sha256Hex(canon(strip(record)));
  }

  // ---- build a regulatory record (v1, or a later version if previous given) -
  // f: { jurisdiction, asset_class, offering_model, applicant, reviewer_id?,
  //      documents:[...], applicant_declaration, acknowledgement_timestamp?,
  //      checklist_reviewed_at?, previous_record_hash?, record_version?, now? }
  async function buildRegulatoryRecord(f) {
    assert(f && typeof f === 'object', 'regulatory record fields required');
    assert(f.applicant, 'applicant (declaring party) required');
    var now = f.now || new Date().toISOString();
    var checklist = deriveChecklist(f.jurisdiction, f.asset_class, f.offering_model);
    var documents = await hashDocuments(f.documents || []);

    var record = strip({
      record_schema: RECORD_VERSION_SCHEMA,
      record_version: (f.record_version != null ? f.record_version : 1),
      jurisdiction: f.jurisdiction || null,
      asset_class: f.asset_class || null,
      offering_model: f.offering_model || null,
      checklist_version: checklist.checklist_version,
      checklist_reviewed_at: f.checklist_reviewed_at || now,
      checklist: checklist,
      applicant: f.applicant,
      reviewer_id: f.reviewer_id || null,
      documents: documents,
      applicant_declaration: f.applicant_declaration ||
        'The applicant declares that the documentation above has been provided and reviewed. SOST records this declaration as a FACT; it makes no legal determination.',
      acknowledgement_timestamp: f.acknowledgement_timestamp || null,
      previous_record_hash: f.previous_record_hash || null,
      legal_classification: LEGAL_CLASSIFICATION
    });

    var hash = await recordHash(record);
    // completeness: which required documents are still missing (FACT, not a verdict)
    var provided = {};
    documents.forEach(function (d) { provided[d.document_type] = true; });
    var missing = checklist.required_documents.filter(function (t) { return !provided[t]; });

    return {
      record: record,
      record_hash: hash,
      required_documents: checklist.required_documents,
      missing_documents: missing,
      complete: missing.length === 0
    };
  }

  // ---- document change detection + non-overwriting versioning --------------
  function docKey(d) { return (d.document_type || '') + '|' + (d.filename || d.reference || ''); }

  function diffDocuments(prevDocs, newDocs) {
    var prev = {}, next = {}, changes = [];
    (prevDocs || []).forEach(function (d) { prev[docKey(d)] = d; });
    (newDocs || []).forEach(function (d) { next[docKey(d)] = d; });
    Object.keys(next).forEach(function (k) {
      var n = next[k], p = prev[k];
      if (!p) changes.push({ key: k, document_type: n.document_type, change: 'ADDED', old_sha256: null, new_sha256: n.sha256 });
      else if (p.sha256 !== n.sha256) changes.push({ key: k, document_type: n.document_type, change: 'CHANGED', old_sha256: p.sha256, new_sha256: n.sha256 });
      else changes.push({ key: k, document_type: n.document_type, change: 'UNCHANGED', old_sha256: p.sha256, new_sha256: n.sha256 });
    });
    Object.keys(prev).forEach(function (k) {
      if (!next[k]) changes.push({ key: k, document_type: prev[k].document_type, change: 'REMOVED', old_sha256: prev[k].sha256, new_sha256: null });
    });
    return changes;
  }

  // Create the NEXT version of a record, keeping the previous hash. Never mutates
  // the previous result. Returns the new result + the per-document change set.
  async function nextVersion(previousResult, f) {
    assert(previousResult && previousResult.record, 'previousResult with .record required');
    var fields = {};
    Object.keys(f || {}).forEach(function (k) { fields[k] = f[k]; });
    fields.record_version = (previousResult.record.record_version || 1) + 1;
    fields.previous_record_hash = previousResult.record_hash;
    var res = await buildRegulatoryRecord(fields);
    res.changes = diffDocuments(previousResult.record.documents, res.record.documents);
    res.changed = res.changes.some(function (c) { return c.change !== 'UNCHANGED'; });
    return res;
  }

  // ---- verification / tamper detection -------------------------------------
  // Recomputes the record hash (detects record tampering) and, if presented
  // documents are given, re-hashes them against the reviewed record (detects a
  // changed/forged document).
  async function verifyRecord(recordResult, presentedDocuments) {
    assert(recordResult && recordResult.record, 'recordResult with .record required');
    var recomputed = await recordHash(recordResult.record);
    var recordMatches = (recomputed === recordResult.record_hash);
    var docResults = [], allDocsMatch = true;
    if (presentedDocuments) {
      var byKey = {};
      (recordResult.record.documents || []).forEach(function (d) { byKey[docKey(d)] = d; });
      for (var i = 0; i < presentedDocuments.length; i++) {
        var pd = presentedDocuments[i];
        var content = (pd.bytes != null) ? pd.bytes : (pd.text != null ? pd.text : (pd.content != null ? pd.content : ''));
        var h = await sha256Hex(content);
        var rec = byKey[docKey({ document_type: pd.document_type, filename: pd.filename, reference: pd.reference })];
        var matches = !!(rec && rec.sha256 === h);
        if (!matches) allDocsMatch = false;
        docResults.push({ document_type: pd.document_type, present: !!rec, matches: matches, expected: rec ? rec.sha256 : null, got: h });
      }
    }
    return { recordMatches: recordMatches, recomputed: recomputed, documents: docResults, allDocsMatch: allDocsMatch };
  }

  // ---- REGISTRY INTEGRITY GATE (refuses EXECUTE / GENERATE) -----------------
  // Refuses — at the registry integrity layer, NOT only a UI checkbox — if:
  //   (a) a required regulatory record is missing,
  //   (b) the acknowledgement is missing, or
  //   (c) the reviewed document hashes no longer match (tampering / post-review edit).
  // This is an INTEGRITY check, NOT a legal validation.
  async function assertCanGenerate(opts) {
    opts = opts || {};
    var rr = opts.recordResult || (opts.record ? { record: opts.record, record_hash: opts.record_hash } : null);
    if (!rr || !rr.record || !rr.record_hash) {
      throw new Error('EXECUTE REFUSED — REGULATORY RECORD MISSING: a regulatory record must be prepared before an Asset Passport can be generated. (Registry integrity check, not a legal validation.)');
    }
    var ack = opts.acknowledgement_timestamp != null ? opts.acknowledgement_timestamp : rr.record.acknowledgement_timestamp;
    if (!ack) {
      throw new Error('EXECUTE REFUSED — ACKNOWLEDGEMENT MISSING: the applicant acknowledgement of the regulatory documentation has not been recorded. (Registry integrity check, not a legal validation.)');
    }
    var v = await verifyRecord(rr, opts.presentedDocuments);
    if (!v.recordMatches) {
      throw new Error('EXECUTE REFUSED — TAMPERING DETECTED: the regulatory record hash does not match its recorded content. (Registry integrity check, not a legal validation.)');
    }
    if (opts.presentedDocuments && !v.allDocsMatch) {
      throw new Error('EXECUTE REFUSED — DOCUMENT HASH MISMATCH: one or more documents no longer match the reviewed/acknowledged state. Re-review before generating. (Registry integrity check, not a legal validation.)');
    }
    return { ok: true, verification: v };
  }

  // ---- incorporate the record into the Asset Passport (and its manifestHash) -
  // A REGULATORY_RECORD claim (class OTHER) carries the record hash, so building
  // the passport folds it into the canonical manifest and the manifestHash.
  function regulatoryClaim(recordResult) {
    assert(recordResult && recordResult.record && recordResult.record_hash, 'recordResult required');
    var r = recordResult.record;
    return {
      id: 'regulatory-record',
      class: 'OTHER',
      value: {
        kind: 'REGULATORY_RECORD',
        record_version: r.record_version,
        jurisdiction: r.jurisdiction || null,
        asset_class: r.asset_class || null,
        offering_model: r.offering_model || null,
        checklist_version: r.checklist_version,
        regulatory_record_hash: recordResult.record_hash,
        previous_record_hash: r.previous_record_hash || null,
        acknowledgement_timestamp: r.acknowledgement_timestamp || null,
        documents: (r.documents || []).map(function (d) {
          return { document_type: d.document_type, sha256: d.sha256, verification_status: d.verification_status, version: d.version };
        }),
        legal_classification: LEGAL_CLASSIFICATION
      },
      provenance: { source_type: 'DECLARING_PARTY', source_name: r.applicant },
      verification: { status: 'DECLARED' }
    };
  }

  // Convenience: append the regulatory claim and build a v2 passport that carries
  // the full record. manifestHash changes whenever the regulatory record changes.
  async function buildPassportWithRegulatory(fields, recordResult) {
    assert(recordResult && recordResult.record, 'recordResult required');
    var claims = (fields.claims || []).slice();
    // replace any existing regulatory-record claim, then append the current one
    claims = claims.filter(function (c) { return c.id !== 'regulatory-record'; });
    claims.push(regulatoryClaim(recordResult));
    var f = {}; Object.keys(fields).forEach(function (k) { f[k] = fields[k]; });
    f.claims = claims;
    var p = await AP2.buildPassport(f);
    p.regulatoryRecord = recordResult.record;
    p.regulatoryRecordHash = recordResult.record_hash;
    return p;
  }

  return {
    RECORD_VERSION_SCHEMA: RECORD_VERSION_SCHEMA,
    CHECKLIST_VERSION: CHECKLIST_VERSION,
    ALLOWED_DOC_STATES: ALLOWED_DOC_STATES,
    FORBIDDEN_STATES: FORBIDDEN_STATES,
    LEGAL_CLASSIFICATION: LEGAL_CLASSIFICATION,
    assertDocState: assertDocState,
    deriveChecklist: deriveChecklist,
    hashDocument: hashDocument, hashDocuments: hashDocuments,
    recordHash: recordHash,
    buildRegulatoryRecord: buildRegulatoryRecord,
    diffDocuments: diffDocuments, nextVersion: nextVersion,
    verifyRecord: verifyRecord, assertCanGenerate: assertCanGenerate,
    regulatoryClaim: regulatoryClaim, buildPassportWithRegulatory: buildPassportWithRegulatory
  };
});

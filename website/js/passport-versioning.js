/* SOST Asset Registry — PASSPORT (sensitive evidence) VERSIONING.
 * ---------------------------------------------------------------------------
 * Sensitive evidence attached to an Asset Passport is NEVER silently overwritten.
 * When a piece of evidence changes, a NEW version is appended that keeps:
 *   previous_hash + new hash + timestamp + reason/reference + provenance +
 *   verification_status.  The ledger exposes CURRENT VERSION + full HISTORY and
 *   can VERIFY the whole history (hash chain + optional content re-hash).
 *
 * Evidence classes that must be versioned (never overwritten):
 *   VALUATION · TITLE_OWNERSHIP · AUDIT · LEGAL_MEMORANDUM · OFFERING_DOCUMENT ·
 *   CUSTODY_EVIDENCE · REGULATORY_AUTHORIZATION · TECHNICAL_REPORT
 *
 * INTEGRITY feature, NOT a legal validation. verification_status is limited to
 *   DECLARED · DOCUMENT PROVIDED · INDEPENDENTLY VERIFIED  and never asserts
 *   LEGAL / COMPLIANT / REGULATORY APPROVED / AUTHORIZED.
 * No consensus / node / miner / RC change. Reuses SOSTAssetPassportV2 SHA-256.
 */
(function (root, factory) {
  var dep = (typeof module !== 'undefined' && module.exports)
    ? require('./asset-passport-v2.js')
    : (root && root.SOSTAssetPassportV2);
  var m = factory(dep);
  if (typeof module !== 'undefined' && module.exports) { module.exports = m; }
  if (root) { root.SOSTPassportVersioning = m; }
})(typeof self !== 'undefined' ? self : this, function (AP2) {
  'use strict';
  if (!AP2) { throw new Error('SOSTPassportVersioning requires SOSTAssetPassportV2 (sha256Hex)'); }
  var sha256Hex = AP2.sha256Hex;

  var SENSITIVE_CLASSES = ['VALUATION', 'TITLE_OWNERSHIP', 'AUDIT', 'LEGAL_MEMORANDUM',
    'OFFERING_DOCUMENT', 'CUSTODY_EVIDENCE', 'REGULATORY_AUTHORIZATION', 'TECHNICAL_REPORT'];
  var ALLOWED_STATES = ['DECLARED', 'DOCUMENT PROVIDED', 'INDEPENDENTLY VERIFIED'];
  var FORBIDDEN_STATES = ['LEGAL', 'COMPLIANT', 'REGULATORY APPROVED', 'APPROVED', 'AUTHORIZED', 'AUTHORISED'];

  function assert(cond, msg) { if (!cond) throw new Error(msg); }
  function assertState(s) {
    var up = String(s == null ? '' : s).toUpperCase();
    if (FORBIDDEN_STATES.indexOf(up) >= 0) throw new Error('FORBIDDEN verification_status "' + s + '" — SOST never asserts LEGAL / COMPLIANT / REGULATORY APPROVED / AUTHORIZED');
    assert(ALLOWED_STATES.indexOf(s) >= 0, 'invalid verification_status "' + s + '" — allowed only: ' + ALLOWED_STATES.join(' / '));
    return s;
  }

  function newLedger() { return { entries: {} }; }

  // Append (or no-op if unchanged) a piece of evidence. Never overwrites.
  // e: { evidence_class, content|hash, reason, reference, provenance,
  //      verification_status?, timestamp?, retain? }
  async function putEvidence(ledger, e) {
    assert(ledger && ledger.entries, 'ledger required (use newLedger())');
    assert(e && e.evidence_class, 'evidence_class required');
    assert(SENSITIVE_CLASSES.indexOf(e.evidence_class) >= 0,
      'evidence_class must be one of: ' + SENSITIVE_CLASSES.join(', '));
    var status = assertState(e.verification_status || 'DECLARED');
    var hash = e.hash;
    if (hash == null) {
      var content = (e.content != null) ? e.content : (e.text != null ? e.text : '');
      hash = await sha256Hex(content);
    }
    var list = ledger.entries[e.evidence_class] || (ledger.entries[e.evidence_class] = []);
    var cur = list.length ? list[list.length - 1] : null;
    if (cur && cur.hash === hash) {
      // unchanged — do NOT create a new version, do NOT overwrite
      return { changed: false, version: cur.version, current: cur };
    }
    var ver = {
      version: list.length + 1,
      hash: hash,
      previous_hash: cur ? cur.hash : null,
      timestamp: e.timestamp || new Date().toISOString(),
      reason: e.reason || (cur ? 'evidence updated' : 'initial version'),
      reference: e.reference || null,
      provenance: e.provenance || null,
      verification_status: status
    };
    if (e.retain && e.content != null) ver.content = e.content; // optional, for full re-hash on verify
    list.push(ver);
    return { changed: true, version: ver.version, current: ver, previous: cur };
  }

  function current(ledger, evidence_class) {
    var l = ledger.entries[evidence_class]; return l && l.length ? l[l.length - 1] : null;
  }
  function history(ledger, evidence_class) {
    if (evidence_class) return (ledger.entries[evidence_class] || []).slice();
    var out = {}; Object.keys(ledger.entries).forEach(function (k) { out[k] = ledger.entries[k].slice(); }); return out;
  }
  function versionCount(ledger, evidence_class) {
    if (evidence_class) return (ledger.entries[evidence_class] || []).length;
    return Object.keys(ledger.entries).reduce(function (a, k) { return a + ledger.entries[k].length; }, 0);
  }

  // Verify the whole history: (1) each version's previous_hash links to the prior
  // version's hash (non-overwriting chain), (2) version numbers are sequential,
  // (3) if content was retained, its re-hash still matches. Returns per-class + overall.
  async function verifyHistory(ledger) {
    var classes = {}, ok = true;
    var keys = Object.keys(ledger.entries);
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i], list = ledger.entries[k], cok = true, problems = [];
      for (var j = 0; j < list.length; j++) {
        var v = list[j], prev = j ? list[j - 1] : null;
        if (v.version !== j + 1) { cok = false; problems.push('version ' + v.version + ' out of sequence at index ' + j); }
        var expectedPrev = prev ? prev.hash : null;
        if ((v.previous_hash || null) !== expectedPrev) { cok = false; problems.push('version ' + v.version + ' previous_hash does not link to prior hash'); }
        if (v.content != null) {
          var rh = await sha256Hex(v.content);
          if (rh !== v.hash) { cok = false; problems.push('version ' + v.version + ' content re-hash mismatch (tampered)'); }
        }
      }
      classes[k] = { ok: cok, versions: list.length, problems: problems };
      if (!cok) ok = false;
    }
    return { ok: ok, classes: classes };
  }

  return {
    SENSITIVE_CLASSES: SENSITIVE_CLASSES, ALLOWED_STATES: ALLOWED_STATES, FORBIDDEN_STATES: FORBIDDEN_STATES,
    newLedger: newLedger, putEvidence: putEvidence, current: current, history: history,
    versionCount: versionCount, verifyHistory: verifyHistory
  };
});

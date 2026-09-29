/*
 * SOST Asset Passport v2 — unified CLAIMS + PROVENANCE model.
 * ---------------------------------------------------------------------------
 * Every material assertion about an asset is a typed CLAIM that answers:
 *   WHAT (class/value) · WHO SAYS IT (provenance.issuer/source) · SOURCE/EVIDENCE
 *   (provenance) · VERIFICATION STATUS · WHEN (timestamp) · CONFIDENCE · and —
 *   because the whole manifest is canonicalized + hashed + anchored — WHETHER
 *   THE RECORD CHANGED (tamper detection).
 *
 * SOST proves integrity + existence-at-time + anchored content. It NEVER asserts
 * the underlying claim is legally true, nor classifies a token as an investment /
 * security / ownership. It only records FACTS ("rights declared: yes", "independent
 * verification: no"). LEGAL CLASSIFICATION: NOT DETERMINED BY SOST.
 *
 * Backward compatible with v1: v1 passports are NEVER rewritten, their manifestHash
 * NEVER changes; verify() branches on version and v1 is exposed through a read-only
 * normalized-claims view. See docs/ASSET_REGISTRY_V2.md.
 *
 * Pure web/lab. No consensus / node / monetary changes. SOST stays 8 decimals.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) { module.exports = m; }
  if (root) { root.SOSTAssetPassportV2 = m; }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var SCHEMA_VERSION = 2;
  var CAPSULE_MAX_BODY = 243; // matches v1 / node capsule doc_ref body limit

  // ---- taxonomy ------------------------------------------------------------
  var CLAIM_CLASSES = ['FACT', 'IDENTITY', 'OWNERSHIP_DECLARATION', 'VALUATION',
    'RIGHT', 'ENCUMBRANCE', 'DISPUTE', 'DOCUMENT', 'LOCATION',
    'SETTLEMENT_REFERENCE', 'OTHER'];
  var RIGHT_SUBTYPES = ['CERTIFICATE', 'USAGE_RIGHT', 'REVENUE_PARTICIPATION',
    'SALE_PROCEEDS_PARTICIPATION', 'OWNERSHIP_OR_EQUITY_LIKE', 'CUSTOM'];
  var PROVENANCE_TYPES = ['DECLARING_PARTY', 'PUBLIC_REGISTRY', 'PUBLIC_DATASET',
    'GEASPIRIT_ANALYSIS', 'INDEPENDENT_EXPERT', 'LABORATORY', 'LEGAL_DOCUMENT',
    'TECHNICAL_DOCUMENT', 'THIRD_PARTY_API', 'SOST_CALCULATION', 'OTHER'];
  var VERIFICATION_STATES = ['DECLARED', 'ATTESTED', 'INDEPENDENTLY_VERIFIED',
    'NOT_VERIFIED', 'REJECTED', 'CONFLICTING'];

  // ---- crypto (browser SubtleCrypto or Node crypto) ------------------------
  async function sha256Hex(bytes) {
    if (typeof bytes === 'string') {
      bytes = (typeof TextEncoder !== 'undefined') ? new TextEncoder().encode(bytes) : Buffer.from(bytes, 'utf8');
    }
    if (typeof crypto !== 'undefined' && crypto.subtle) {
      var buf = await crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
    }
    var nc = require('crypto');
    return nc.createHash('sha256').update(Buffer.from(bytes)).digest('hex');
  }

  // ---- CANONICALIZATION (RFC-8785-lite; MUST match v1 for v1 compat) --------
  // Rules (documented in docs/ASSET_REGISTRY_V2.md):
  //  - objects: keys sorted by JS string (UTF-16 code unit) order, ascending.
  //  - null/undefined optional fields are STRIPPED before canon (absent == null).
  //  - strings: JSON.stringify (canonical JSON escaping; Unicode preserved as UTF-8 on hash).
  //  - booleans: true/false. numbers: MUST be integers (String via JSON.stringify);
  //    non-integer numbers throw — money/decimals MUST be passed as strings.
  //  - arrays: preserved IN ORDER (caller controls order; claims[] is pre-sorted by id).
  function canon(o) {
    if (o === null || typeof o !== 'object') {
      if (typeof o === 'number' && !Number.isInteger(o)) {
        throw new Error('non-integer number must be a string for canonical hashing: ' + o);
      }
      return JSON.stringify(o);
    }
    if (Array.isArray(o)) return '[' + o.map(canon).join(',') + ']';
    return '{' + Object.keys(o).sort().map(function (k) {
      return JSON.stringify(k) + ':' + canon(o[k]);
    }).join(',') + '}';
  }

  // strip null/undefined recursively (absent === null canonically). Empty arrays kept.
  function strip(o) {
    if (o === null || o === undefined) return undefined;
    if (Array.isArray(o)) return o.map(strip).filter(function (x) { return x !== undefined; });
    if (typeof o !== 'object') return o;
    var out = {};
    Object.keys(o).forEach(function (k) {
      var v = strip(o[k]);
      if (v !== undefined) out[k] = v;
    });
    return out;
  }

  function assert(cond, msg) { if (!cond) throw new Error(msg); }

  async function assetId(issuer, nonce, category) {
    return 'sost-asset-' + (await sha256Hex(issuer + '|' + nonce + '|' + category)).slice(0, 40);
  }

  // ---- claim validation ----------------------------------------------------
  function validateClaim(c, idx) {
    var where = 'claim[' + (idx != null ? idx : '?') + ']';
    assert(c && typeof c === 'object', where + ' must be an object');
    assert(typeof c.id === 'string' && c.id.length > 0, where + ' missing id');
    assert(CLAIM_CLASSES.indexOf(c.class) >= 0, where + ' invalid class: ' + c.class);
    if (c.class === 'RIGHT') {
      assert(RIGHT_SUBTYPES.indexOf((c.value && c.value.right_type) || c.subtype) >= 0,
        where + ' RIGHT needs a valid right_type/subtype');
    }
    if (c.provenance) {
      assert(typeof c.provenance === 'object', where + ' provenance must be an object');
      if (c.provenance.source_type != null) {
        assert(PROVENANCE_TYPES.indexOf(c.provenance.source_type) >= 0,
          where + ' invalid provenance.source_type: ' + c.provenance.source_type);
      }
    }
    var vs = (c.verification && c.verification.status) || 'NOT_VERIFIED';
    assert(VERIFICATION_STATES.indexOf(vs) >= 0, where + ' invalid verification.status: ' + vs);
    if (c.confidence != null) {
      assert(Number.isInteger(c.confidence) && c.confidence >= 0 && c.confidence <= 100,
        where + ' confidence must be an integer 0..100');
    }
    return true;
  }

  // normalize one claim into canonical shape (defaults + strip)
  function normalizeClaim(c, i) {
    var out = {
      id: c.id || ('c' + (i + 1)),
      class: c.class,
      value: c.value != null ? c.value : null,
      provenance: c.provenance || null,
      verification: {
        status: (c.verification && c.verification.status) || 'NOT_VERIFIED',
        verifier: (c.verification && c.verification.verifier) || null,
        date: (c.verification && c.verification.date) || null
      },
      confidence: (c.confidence != null ? c.confidence : null),
      timestamp: c.timestamp || null
    };
    if (c.subtype) out.subtype = c.subtype;
    return strip(out);
  }

  // ---- build a v2 passport -------------------------------------------------
  // f: { assetId?, issuer, nonce?, category, locator?, claims:[...] }
  async function buildPassport(f) {
    assert(f && f.issuer, 'issuer required');
    assert(Array.isArray(f.claims), 'claims[] required');
    f.claims.forEach(validateClaim);
    var id = f.assetId || await assetId(f.issuer, f.nonce || '0', f.category || 'other');
    // normalize + deterministic ordering by id
    var claims = f.claims.map(normalizeClaim).sort(function (a, b) {
      return a.id < b.id ? -1 : (a.id > b.id ? 1 : 0);
    });
    var manifest = strip({
      schema_version: SCHEMA_VERSION,
      assetId: id,
      issuer: f.issuer,
      category: f.category || null,
      locator: f.locator || null,
      claims: claims
    });
    var manifestHash = await sha256Hex(canon(manifest));
    return { manifest: manifest, manifestHash: manifestHash, rollup: rollup(claims) };
  }

  // ---- roll-up (derives a summary; NEVER hides individual claim state) -----
  function rollup(claims) {
    var byStatus = {}, byClass = {};
    VERIFICATION_STATES.forEach(function (s) { byStatus[s] = 0; });
    claims.forEach(function (c) {
      var s = (c.verification && c.verification.status) || 'NOT_VERIFIED';
      byStatus[s] = (byStatus[s] || 0) + 1;
      byClass[c.class] = (byClass[c.class] || 0) + 1;
    });
    var rights = claims.filter(function (c) { return c.class === 'RIGHT'; });
    var anyRight = rights.length > 0;
    var econ = rights.some(function (c) { return c.value && c.value.economic_rights_declared === true; });
    var obligor = rights.some(function (c) { return c.value && c.value.obligor; });
    var agreement = rights.some(function (c) { return c.value && (c.value.agreement_hash || c.value.agreement_reference); });
    var ownership = claims.filter(function (c) { return c.class === 'OWNERSHIP_DECLARATION' || (c.class === 'RIGHT' && c.subtype === 'OWNERSHIP_OR_EQUITY_LIKE'); });
    var legalTitleVerified = ownership.some(function (c) { return c.verification && c.verification.status === 'INDEPENDENTLY_VERIFIED'; });
    return {
      total: claims.length,
      by_status: byStatus,
      by_class: byClass,
      economic_rights_declared: !!(anyRight && econ),
      obligor_identified: !!obligor,
      agreement_attached: !!agreement,
      independent_verification_count: byStatus.INDEPENDENTLY_VERIFIED || 0,
      legal_title_verified: !!legalTitleVerified,
      legal_classification: 'NOT DETERMINED BY SOST'
    };
  }

  // ---- verify (v1 OR v2). Recomputes hash + per-claim + roll-up ------------
  async function verify(passport) {
    var m = passport.manifest;
    var version = (m && (m.schema_version || m.version)) || 1;
    if (version === 2) {
      var recomputed = await sha256Hex(canon(m));
      var claimsOk = true;
      try { (m.claims || []).forEach(validateClaim); } catch (e) { claimsOk = false; }
      return {
        version: 2, manifestMatches: recomputed === passport.manifestHash,
        recomputed: recomputed, claimsValid: claimsOk, rollup: rollup(m.claims || [])
      };
    }
    // v1: reuse the EXACT v1 canon (identical algorithm) over the raw v1 manifest
    var rec1 = await sha256Hex(canon(m));
    return { version: 1, manifestMatches: rec1 === passport.manifestHash, recomputed: rec1 };
  }

  // ---- v1 -> normalized claims (READ-ONLY view; does NOT change v1 hash) ---
  function normalizeV1ToClaims(v1passport) {
    var m = v1passport.manifest, claims = [], n = 0;
    function add(cls, value, prov, subtype) {
      var c = { id: 'v1-' + (++n), class: cls, value: value,
        provenance: prov || { source_type: 'DECLARING_PARTY' },
        verification: { status: 'DECLARED' } };
      if (subtype) c.subtype = subtype;
      claims.push(strip(c));
    }
    add('IDENTITY', { assetId: m.assetId, category: m.category, issuer: m.issuer });
    if (m.ownerDeclaration) add('OWNERSHIP_DECLARATION', { declaration: m.ownerDeclaration, jurisdiction: m.jurisdiction || null });
    if (m.rights) add('RIGHT', { right_type: 'CUSTOM', description: m.rights, economic_rights_declared: null }, null, 'CUSTOM');
    (m.encumbrances || []).forEach(function (e) { add('ENCUMBRANCE', { description: e }); });
    (m.disputes || []).forEach(function (d) { add('DISPUTE', { description: d }); });
    (m.documents || []).forEach(function (d) { add('DOCUMENT', { name: d.name, bytes: d.bytes }, { source_type: 'TECHNICAL_DOCUMENT', hash: d.sha256 }); });
    return {
      version: 1, raw_manifest: m, raw_hash: v1passport.manifestHash,
      claims: claims, rollup: rollup(claims),
      note: 'READ-ONLY normalized view of a v1 passport. The v1 manifest and its hash are unchanged.'
    };
  }

  // ---- engine adapters (produce claims) ------------------------------------
  function valuationClaim(o) {
    // amounts as STRINGS (canonical hashing forbids non-integer numbers)
    return {
      id: o.id || 'valuation', class: 'VALUATION',
      value: {
        amount: String(o.amount), currency: o.currency || 'EUR',
        range_low: o.range_low != null ? String(o.range_low) : null,
        range_high: o.range_high != null ? String(o.range_high) : null,
        recoverable: o.recoverable != null ? String(o.recoverable) : null,
        methodology: o.methodology || null, assumptions: o.assumptions || null
      },
      provenance: o.provenance || { source_type: 'SOST_CALCULATION' },
      verification: { status: o.verification || 'DECLARED' },
      confidence: (o.confidence != null ? o.confidence : null),
      timestamp: o.timestamp || null
    };
  }
  function rightClaim(o) {
    assert(RIGHT_SUBTYPES.indexOf(o.right_type) >= 0, 'invalid right_type: ' + o.right_type);
    return {
      id: o.id || 'right', class: 'RIGHT', subtype: o.right_type,
      value: {
        right_type: o.right_type, description: o.description || null,
        economic_rights_declared: (o.economic_rights_declared === true),
        obligor: o.obligor || null,
        agreement_reference: o.agreement_reference || null, agreement_hash: o.agreement_hash || null,
        distribution_mechanism: o.distribution_mechanism || null, distribution_frequency: o.distribution_frequency || null,
        exit_mechanism: o.exit_mechanism || null, transferability: o.transferability || null,
        jurisdiction: o.jurisdiction || null, token_supply: (o.token_supply != null ? String(o.token_supply) : null),
        token_decimals: (o.token_decimals != null ? o.token_decimals : null)
      },
      provenance: o.provenance || { source_type: 'DECLARING_PARTY' },
      verification: { status: o.verification || 'DECLARED' },
      timestamp: o.timestamp || null
    };
  }

  // ---- on-chain anchor payload (same body shape / limit as v1) -------------
  function capsuleDocRef(passport) {
    var body = { m: 'doc_ref', h: passport.manifestHash, loc: (passport.manifest.locator || '') };
    var enc = canon(body);
    var bytes = (typeof TextEncoder !== 'undefined') ? new TextEncoder().encode(enc).length : Buffer.byteLength(enc, 'utf8');
    return { ok: bytes <= CAPSULE_MAX_BODY, bytes: bytes, max: CAPSULE_MAX_BODY, body: body, encoded: enc,
      error: bytes <= CAPSULE_MAX_BODY ? null : ('locator too long: ' + bytes + 'B > ' + CAPSULE_MAX_BODY + 'B') };
  }

  return {
    SCHEMA_VERSION: SCHEMA_VERSION, CLAIM_CLASSES: CLAIM_CLASSES, RIGHT_SUBTYPES: RIGHT_SUBTYPES,
    PROVENANCE_TYPES: PROVENANCE_TYPES, VERIFICATION_STATES: VERIFICATION_STATES,
    sha256Hex: sha256Hex, canon: canon, strip: strip, assetId: assetId,
    validateClaim: validateClaim, buildPassport: buildPassport, rollup: rollup, verify: verify,
    normalizeV1ToClaims: normalizeV1ToClaims, valuationClaim: valuationClaim, rightClaim: rightClaim,
    capsuleDocRef: capsuleDocRef
  };
});

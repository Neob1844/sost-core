# SOST Asset Registry — Asset Passport v2 (Claims + Provenance)

Web/lab only. NO consensus / node / miner / P2P / monetary / STOCKS_PER_SOST / STRATO change.
SOST stays 8 decimals. Anchoring reuses the already-proven Capsule `doc_ref` round-trip.

## Architecture BEFORE
Three disconnected islands: (1) `asset-passport.js` v1 — a FLAT manifest where `rights` is
FREE TEXT, no per-datum provenance, states via a hardcoded `classify()`; (2) `asset-intelligence.js`
— deterministic valuation with a trace but boolean evidence flags (no source objects); (3) the
Tokenization Studio (`tk*`) — a client-side calculator NOT connected to the Passport (`manifestHash`
used 0×). Rights, provenance and status were three parallel metadata systems.

## Architecture AFTER
One model: the Passport is a set of typed CLAIMS. Every material assertion (identity, valuation,
right, ownership, encumbrance, document, location, settlement reference) is a claim with the SAME
envelope, so the UI answers WHAT / WHO SAYS IT / SOURCE·EVIDENCE / VERIFICATION / WHEN / CONFIDENCE /
CHANGED uniformly. The three "engines" become views/producers over claims. Status is a deterministic
ROLL-UP of per-claim verification (not a hardcoded classify). Everything is canonicalized → hashed →
anchored (tamper-evident). Module: `website/js/asset-passport-v2.js`.

## Schema v2 (canonical manifest)
```
manifest = {
  schema_version: 2,
  assetId,                      // sost-asset-<40hex> = sha256(issuer|nonce|category)[:40] (no SOST-supply link)
  issuer,
  category,                     // optional
  locator,                      // optional off-chain reference
  claims: [ claim, ... ]        // normalized + sorted by id
}
claim = {
  id,                           // stable within the passport
  class,                        // see CLAIM CLASSES
  subtype?,                     // for RIGHT
  value,                        // class-specific (money as STRINGS)
  provenance: { source_type, source_name?, reference?, issuer?, date?, hash?, notes? },
  verification: { status, verifier?, date? },
  confidence?,                  // integer 0..100
  timestamp?
}
```

### CLAIM CLASSES
`FACT · IDENTITY · OWNERSHIP_DECLARATION · VALUATION · RIGHT · ENCUMBRANCE · DISPUTE · DOCUMENT · LOCATION · SETTLEMENT_REFERENCE · OTHER`

### RIGHT SUBTYPES
`CERTIFICATE · USAGE_RIGHT · REVENUE_PARTICIPATION · SALE_PROCEEDS_PARTICIPATION · OWNERSHIP_OR_EQUITY_LIKE · CUSTOM`
RIGHT value fields (when applicable): right_type, description, economic_rights_declared(bool), obligor,
agreement_reference, agreement_hash, distribution_mechanism, distribution_frequency, exit_mechanism,
transferability, jurisdiction, token_supply(string), token_decimals(int). **SOST records these as FACTS
and NEVER classifies the token as investment/security/ownership.**

### PROVENANCE MODEL
source_type ∈ `DECLARING_PARTY · PUBLIC_REGISTRY · PUBLIC_DATASET · GEASPIRIT_ANALYSIS · INDEPENDENT_EXPERT ·
LABORATORY · LEGAL_DOCUMENT · TECHNICAL_DOCUMENT · THIRD_PARTY_API · SOST_CALCULATION · OTHER`; plus
source_name, reference, issuer, date, hash, notes (all optional).

### VERIFICATION MODEL
Per-claim status ∈ `DECLARED · ATTESTED · INDEPENDENTLY_VERIFIED · NOT_VERIFIED · REJECTED · CONFLICTING`.
The Passport ROLL-UP derives: per-status/per-class counts, economic_rights_declared, obligor_identified,
agreement_attached, independent_verification_count, legal_title_verified, and a constant
`legal_classification: "NOT DETERMINED BY SOST"`. The roll-up NEVER hides individual claim state.

### CANONICALIZATION RULES (RFC-8785-lite; identical algorithm to v1)
- objects: keys sorted by UTF-16 code-unit ascending; `{"k":v,...}`.
- null/undefined optional fields are STRIPPED before hashing (absent === null).
- strings: JSON.stringify escaping; Unicode preserved.
- numbers: integers only (String); **non-integer numbers THROW** — money/decimals MUST be strings.
- booleans: true/false. arrays: preserved IN ORDER (claims[] pre-sorted by id).
- `manifestHash = sha256(canon(manifest))`. Reproducible by any third party from the canonical bytes.

## V1 COMPATIBILITY METHOD
v1 passports are NEVER rewritten and their `manifestHash` NEVER changes. `verify()` branches on
`schema_version||version`: v1 → recompute with the identical canon over the raw v1 manifest (byte-exact);
v2 → recompute + validate claims + roll-up. `normalizeV1ToClaims()` gives a READ-ONLY claims view of a v1
passport (keeps raw manifest + raw hash + version:1). v1 and v2 never produce the same hash. Proven by
test: V1 fixture hash `c11e5e59…` reproduced unchanged; v1 manifest not mutated.

## CURRENT (SOST Asset Registry) vs FUTURE (SOST Asset Marketplace)
CURRENT: claims, provenance, evidence, valuation, rights declarations, Asset Passport, document hashing,
on-chain anchoring, read-back, verification, tamper detection. FUTURE (NOT built, NOT simulated):
financial marketplace, asset order book, real yield distribution, custody, secondary trading of rights,
real stablecoin/fiat settlement, native UTXO asset layer.

## SETTLEMENT (minimal, honest)
Rails: `SOST` (when there is real liquidity/counterparty) and `EXTERNAL_DOCUMENTED` (SOST records a
reference/evidence/hash of an off-chain settlement — **SOST does NOT custody funds**). Stablecoin/EUR =
FUTURE/NOT IMPLEMENTED. Liquidity honesty: VALUATION ≠ REFERENCE PRICE ≠ LIQUIDITY ≠ MARKET DEPTH ≠
EXECUTABILITY; SOST-price scenarios (€0.001/0.01/0.10/1.00) are MATHEMATICAL EQUIVALENCE, never a market
quote; with no real depth → `EXECUTABLE LIQUIDITY: NOT VERIFIED`, `MARKET DEPTH: UNKNOWN`.

## LEGAL GUARDRAILS (precise, non-alarmist)
DECLARATION ≠ LEGAL TITLE · ON-CHAIN ≠ TRUTH OF THE CLAIM · TOKEN ≠ OWNERSHIP UNLESS LEGALLY CONSTITUTED ·
VALUATION ≠ MARKET PRICE · REFERENCE PRICE ≠ LIQUIDITY · TOKENIZATION ≠ INVESTMENT OFFER ·
SOST DOES NOT DETERMINE LEGAL OR REGULATORY CLASSIFICATION. Where a declared right may fall under MiCA/
MiFID II/securities law, note it prudently; do not resolve the classification automatically.

## GeaSpirit hand-off (decoupled; schema only — see geaspirit-sost-handoff.schema.json)
GeaSpirit (discovery/intelligence) → deep-link/JSON hand-off → SOST Asset Registry. Data crossing the
boundary becomes claims with `provenance.source_type = GEASPIRIT_ANALYSIS`. NO GeaSpirit code imported
into SOST or vice-versa; NO runtime dependency; NO custody/tokenization inside GeaSpirit.

# PQ Pre-Activation Audit Checklist — V3 (RESEARCH / DOCS ONLY)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> **No audit has been performed yet.** Every box below is **UNCHECKED**. This checklist must be
> fully satisfied (Phase C of `docs/PQ_WALLET_MIGRATION_V3.md`) and independently reviewed before
> any PQ activation is even scheduled. `PQ_ACTIVATION_HEIGHT = INT64_MAX` ("never") until then.
> Supersedes the audit notes in `docs/PQ_MIGRATION_V2.md` (PR #37).

---

## 1. Crypto-agility registry correctness
- [ ] 1-byte `alg_id` registry values match the V3 spec (0x00 LEGACY, 0x01 ML-DSA-44,
      0x02 HYBRID, 0x03 ML-DSA-65 rsv., 0x04 ML-DSA-87 rsv., 0x10 SLH-DSA rsv., 0xFF INVALID).
- [ ] V3 reassignment vs V2 is documented; no live conflict (PQ height = INT64_MAX, unused).
- [ ] Every unknown / unassigned `alg_id` is **deterministically REJECTED**, never ignored.
- [ ] Reserved ids (0x03/0x04/0x10) are rejected as not-yet-valid, not silently accepted.
- [ ] Registry is a single source of truth; no divergent copies between wallet / node / explorer.

## 2. Witness parser safety
- [ ] Rejects **unknown alg_id**.
- [ ] Rejects **truncated** witnesses (length prefix exceeds remaining bytes).
- [ ] Rejects **oversized** witnesses (exceeds the per-class expected size / declared bound).
- [ ] Rejects **duplicate** witness components.
- [ ] Rejects **mis-ordered** components (fixed, documented field order).
- [ ] Every component length is encoded as **exactly one unsigned 16-bit big-endian value**; no
      `CompactSize`, varint, short form or alternative form is accepted.
- [ ] The length prefix is **exactly two bytes**; a one-byte prefix is rejected.
- [ ] A `CompactSize`-style `0xfd` lead is treated as the high byte of a BE16 length, never as a
      varint marker (no varint interpretation exists).
- [ ] Truncation after only the first length-prefix byte is rejected (two prefix bytes required).
- [ ] The exact expected component size is checked **before any allocation** driven by the length.
- [ ] BE16 length decoding has **identical semantics on all architectures** (byte order is fixed,
      not host-endian).
- [ ] Signature/pubkey lengths must exactly match the class's fixed FIPS 204 sizes.
- [ ] No unbounded allocation driven by attacker-supplied length fields.

## 3. Deterministic canonical encoding
- [ ] Exactly one valid byte encoding per witness (round-trip serialize/deserialize is identity).
- [ ] No optional/omittable fields that create two encodings of the same meaning.
- [ ] Encoding is versioned under tx version 2 and legacy tx version 1 is untouched.

## 4. Domain separation
- [ ] PQ signing/verification uses a distinct domain-separation tag from ECDSA and from Schnorr.
- [ ] Hybrid sub-signatures are domain-separated from their standalone equivalents.
- [ ] No cross-protocol message reuse between spend, SbPoW Schnorr, and PQ.

## 5. Adversarial resistance
- [ ] **Downgrade** resistance: an attacker cannot force a HYBRID output to be accepted on the
      ECDSA-only leg.
- [ ] **Algorithm-confusion** resistance: a signature/key of one alg cannot validate under another.
- [ ] **Signature-substitution** resistance: witness bound to the exact spend it authorises.
- [ ] **Malleability** resistance: canonical form enforced; no third-party mutation of txid/witness.
- [ ] **Replay** resistance: no cross-tx / cross-chain replay of a PQ witness.

## 6. DoS bounds
- [ ] Maximum signature/pubkey/witness size bounded per class before any heavy work.
- [ ] Per-input and per-tx verify cost bounded; block-level aggregate verify cost bounded.
- [ ] Memory per verification bounded and measured (no timing yet — RESULTS_PENDING_COMPUTE_ENV).
- [ ] Size/weight review complete; **no unjustified weight discount for PQ**
      (see `docs/PQ_PERFORMANCE_MODEL_V3.md`).

## 7. Hybrid AND semantics
- [ ] HYBRID (0x02) requires **BOTH** ECDSA **AND** ML-DSA-44 to verify (conjunctive).
- [ ] OR-hybrid is impossible to express or is rejected (breaking either scheme must not suffice).
- [ ] Partial hybrid (one leg valid, one missing/invalid) is rejected.

## 8. Library review
- [ ] License compatible with SOST (MIT) and documented.
- [ ] Maintenance status / release cadence acceptable.
- [ ] Independent audit history of the library reviewed.
- [ ] Exact version/commit pinned and recorded.
- [ ] Side-channel posture reviewed (constant-time claims, known leaks).
- [ ] Supply-chain integrity (checksums / signed releases / vendoring policy).
- [ ] Reproducible build of the library achievable.
- [ ] Target platforms all supported (build + run verified).
- [ ] Library isolated behind the abstract crypto interface (swappable, no leakage into consensus).

## 9. Entropy / RNG
- [ ] PQ keygen uses a vetted CSPRNG; source documented.
- [ ] No reuse of nonces/randomness where the scheme requires freshness.
- [ ] Deterministic-signing modes (if used) reviewed for the scheme's requirements.

## 10. Side channels (implementation)
- [ ] Signing path timing/cache behaviour reviewed on target platforms.
- [ ] No secret-dependent branches/memory access in the integrated signing path.

## 11. Test vectors
- [ ] Official FIPS 204 known-answer / test vectors pass.
- [ ] **Valid** vectors accepted.
- [ ] **Invalid** vectors (bad sig, wrong key, tampered message) rejected.
- [ ] Hybrid valid/invalid combination vectors covered.

## 12. Fuzzing
- [ ] Witness parser fuzzed (structure-aware) with no crashes/UB/OOM.
- [ ] Verification path fuzzed against malformed sig/pubkey inputs.
- [ ] Differential fuzzing vs the reference implementation where feasible.

## 13. Activation / governance gating
- [ ] `PQ_ACTIVATION_HEIGHT = INT64_MAX` ("never") until governance schedules otherwise.
- [ ] Activation mechanism reviewed; cannot activate accidentally or via default config.
- [ ] `include/sost/proposals.h:44` placeholder (id 8) remains INERT; eventual reword to ML-DSA
      changes no behaviour.

## 14. Wallet migration correctness
- [ ] Opt-in only; no auto-migration of user funds.
- [ ] PQ key derivation scheme finalised and documented (ECDSA seed does **not** yield an ML-DSA key).
- [ ] Backup / restore / descriptor / export cover all classes and label `alg_id`.
- [ ] Wallet refuses to create outputs the network cannot yet validate.
- [ ] Wallet refuses to send to a class the recipient/old client cannot spend.

## 15. Explorer / RPC labelling
- [ ] Every input's spend type shown by `alg_id` label (LEGACY / PQ ML-DSA-44 / HYBRID …).
- [ ] Unknown/reserved `alg_id` rendered as INVALID, never as a known-good class.

## 16. Node-upgrade split handling
- [ ] Behaviour of upgraded vs non-upgraded nodes analysed (no accidental chain split on mainnet
      while PQ is inert).
- [ ] Testnet-only activation confirmed unreachable from mainnet code paths.
- [ ] Rollback / disable path exists if a defect is found post-testnet.

---

## Sign-off (blank until a real audit occurs)

```
Auditor(s):         <none — no audit performed>
Scope / commit:     <none>
Date:               <none>
Findings resolved:  <none>
Verdict:            NOT AUDITED
```

---

*Author: NeoB. No audit has been performed. All items UNCHECKED. Activates nothing.*

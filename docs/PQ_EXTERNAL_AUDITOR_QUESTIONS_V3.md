# SOST Post-Quantum Migration — External Auditor Questions (V3)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> These are the **specific** questions the external cryptographer / code auditor is asked to answer,
> grounded in the V3 design and prototype. Read `docs/PQ_EXTERNAL_AUDIT_BRIEF_V3.md` first; the
> authoritative design lives in `docs/PQ_MIGRATION_V3.md` and its siblings; the reproducibility
> package is `docs/PQ_EXTERNAL_AUDIT_MANIFEST_V3.md`. For each question, please give a verdict
> (OK / CONCERN / BLOCKER), the reasoning, and any concrete change required.

---

## A. Hybrid construction

- **A1 — AND sufficiency.** HYBRID `0x02` is defined as ECDSA **AND** ML-DSA-44 over the same
  domain-separated sighash (`prototype/pq/pq_validate.h`, ADR-002). Is verifying two independent
  signatures over one shared `H(tag || 0x00 || sighash)` a sound hybrid, or is a formal
  combiner / dual-signature construction (e.g. binding both public keys into the signed message)
  required to prevent a mix-and-match forgery where each leg was produced in a different context?
- **A2 — Weakest-leg accounting.** Confirm that under this AND, security is `max` of the two legs
  (not `min`), including the case where ML-DSA-44 later proves weak but ECDSA is not yet
  Shor-broken, and vice-versa. Any scenario where the hybrid is weaker than either standalone leg?
- **A3 — Partial-hybrid rejection.** Verify that a hybrid witness with one valid and one
  missing/invalid/duplicated leg is rejected in **both** orderings (the tests claim both directions —
  `tests/pq_vectors/test_pq_witness.cpp`). Any parse/verify path that could accept a one-leg hybrid?

## B. Downgrade, confusion, substitution

- **B1 — Downgrade binding.** The design says a PQ/hybrid-locked output must not be spendable by a
  bare `0x00` legacy witness (`docs/PQ_THREAT_MODEL_V3.md §4.1`). But the prototype only checks a
  witness in isolation — the **output → required-alg binding** is not implemented. Specify exactly
  how the spent output must commit to its required `alg_id` (e.g. in the address/scriptPubKey) so
  that downgrade is impossible, and confirm the current design is adequate or under-specified.
- **B2 — Algorithm confusion.** Is the 1-byte `alg_id` authenticated strongly enough? It selects the
  verifier and is fed into the domain tag, but is it *inside* the signed message such that flipping
  `alg_id` invalidates the signature, or only *alongside* it? Can a valid ML-DSA signature be
  re-presented under `alg_id = 0x00`/`0x02` (or vice-versa) and pass?
- **B3 — Substitution.** Can either leg of a hybrid, or a whole witness, be lifted from one input and
  attached to another input/tx that shares a sighash collision or a weak binding?

## C. Encoding, malleability, binding

- **C1 — Canonical length encoding (single, provisional).** V3 uses **one** length encoding
  everywhere: an **unsigned 16-bit big-endian value in exactly 2 bytes** (`len_be16`). The wire spec
  (`docs/PQ_TX_FORMAT_V3.md §5`), performance model (`docs/PQ_PERFORMANCE_MODEL_V3.md §3`), checklist
  (`docs/PQ_AUDIT_CHECKLIST_V3.md §2`) and prototype (`prototype/pq/pq_witness.h`) now all agree;
  `CompactSize`/varint is **not** part of the proposal. This is **provisional** (pending this review),
  not audited or production-final. Please assess: is BE16 sufficient? Are explicit per-component
  lengths worth keeping when `alg_id` already fixes every exact size (an alternative is length-free,
  size-by-`alg_id` parsing)? Is there parser-differential risk across implementations? Is a separate
  global witness-size limit needed? Confirm the encoding is single-valued (exactly one byte-string per
  logical witness) and that non-canonical encodings are rejected. Note: any future component larger
  than 65535 bytes would require a **new witness version**, never a re-interpretation of the V3 length
  field.
- **C2 — Malleability / txid stability.** With exact-length + no-trailing-bytes + fixed field order,
  is there any third-party mutation that yields a different accepted witness (hence a different txid)
  for the same authorised spend? Consider ML-DSA's own signature-encoding malleability, if any.
- **C3 — Full-context binding.** Does the signed message bind `alg_id`, the specific public key(s),
  the signature's position, the exact input (outpoint), the amounts, the whole transaction, and the
  network/genesis domain? Identify any of these NOT bound.
- **C4 — Duplicate-key ambiguity.** For hybrid (two keys) and for any multi-key/multisig extension,
  can two different `(key, sig)` assignments satisfy the same witness, or can a duplicated key make
  the AND collapse to a single-leg check?

## D. Registry and unknown algorithms

- **D1 — Algorithm substitution via registry.** Given the V2→V3 `alg_id` reassignment, is there any
  cross-iteration replay risk if a V2-era prototype signature/witness were presented to a V3 verifier
  (both inert today, but confirm the domain tags prevent it regardless)?
- **D2 — Unknown / reserved handling.** Confirm every unlisted byte, every RESERVED id
  (`0x03/0x04/0x10`), and `0xFF` are **rejected with a deterministic, distinct outcome**, never
  ignored or best-effort-parsed, and that reserved ids are parsed only far enough to reject
  (`prototype/pq/pq_witness.h`). Any id value that reaches verification unexpectedly?

## E. Replay

- **E1 — Mainnet ↔ testnet replay.** The isolated testnet is to use distinct network magic
  (`docs/PQ_TESTNET_PLAN_V3.md`). Confirm the domain separation actually enters the signed message so
  a testnet witness cannot be replayed on mainnet (or any future PQ testnet) and vice-versa.
- **E2 — Cross-class replay.** Can a signature valid for LEGACY be replayed inside a PQ or HYBRID
  witness (or a hybrid's ECDSA leg be replayed as a standalone LEGACY spend of the same input)?
- **E3 — Cross-input / cross-tx replay.** Any way a witness authorising one input authorises another?

## F. Limits and DoS

- **F1 — Witness size limits.** Are exact per-alg size bounds (rejecting before any allocation or
  verify) sufficient, given `MAX_TX_BYTES_CONSENSUS = 100000`, `MAX_INPUTS_CONSENSUS = 256`, and the
  ~28–40× per-input growth (`docs/PQ_PERFORMANCE_MODEL_V3.md §3-4`)? Should standardness
  (`MAX_TX_BYTES_STANDARD = 16000`) change?
- **F2 — Verify-work accounting.** Evaluate the candidate per-tx **verify-work budget**
  (`docs/PQ_PERFORMANCE_MODEL_V3.md §4.4`): is a weighted pre-verify budget the right mechanism, what
  should the ECDSA-relative weights be once timings are authoritative, and does checking it "before
  any verify" actually bound the worst case?
- **F3 — Invalid-signature flooding.** ML-DSA verify-invalid ≈ verify-valid cost in the indicative
  run (no early-out). Does this enable a cheap-to-produce / expensive-to-reject flood, and is
  "cheap checks first" plus the budget enough?
- **F4 — Batch verification.** Should ML-DSA batch verification be used at block validation, and does
  any batch technique introduce a soundness or DoS risk (e.g. a batch that passes while an individual
  signature is invalid)?

## G. Implementation-level cryptography

- **G1 — Side channels.** For a chosen production ML-DSA implementation, are signing (and hot-verify)
  paths constant-time, including ML-DSA's rejection-sampling timing? What is the required posture for
  hardware wallets and custodians (`docs/PQ_THREAT_MODEL_V3.md §8.2`)?
- **G2 — Key generation & entropy.** What CSPRNG/entropy requirements must SOST document for ML-DSA
  keygen and hedged signing, and how should failure modes (weak entropy) be prevented
  (`docs/PQ_SECURITY_ASSUMPTIONS_V3.md §8`... `docs/PQ_THREAT_MODEL_V3.md §8.3`)?
- **G3 — Secret storage.** Requirements for storing larger ML-DSA private keys (1312 B+ public,
  larger secret) safely, including on constrained secure elements.

## H. Wallet, backup, migration

- **H1 — Backup / recovery.** Since an ECDSA seed does not yield an ML-DSA key
  (`docs/PQ_WALLET_MIGRATION_V3.md §3`), what is a safe, standardisable PQ key-derivation KDF/branch
  so a single seed can regenerate both trees, and what must a backup/export/descriptor carry
  (the `alg_id`, class labels)?
- **H2 — Never-moved funds.** For dormant/never-spent outputs (only the hash is exposed), what is the
  safest single-spend migration flow given the mempool front-running window at reveal
  (`docs/PQ_THREAT_MODEL_V3.md §3.1-3.2`)? Is a commit-reveal spend worth specifying?
- **H3 — Prior public-key exposure.** For already-revealed/reused keys, is there anything beyond
  "migrate first" that helps, and how should wallets prioritise/warn?

## I. Parameters and libraries

- **I1 — ML-DSA-44 vs -65.** Is NIST L2 (ML-DSA-44) an acceptable default for a monetary chain, or
  should L3 (ML-DSA-65) be the default given the modest size delta (~3773 vs ~5302 B/input)?
- **I2 — ML-DSA-87 utility.** Is there any real utility to ML-DSA-87 (L5) for spend authorisation, or
  should it stay reserved-only?
- **I3 — SLH-DSA reserve.** Is holding SLH-DSA (FIPS 205, hash-based) purely as a reserve the right
  hedge against a lattice break, and which parameter set (size/perf trade-off) would be the reserve?
- **I4 — Library maturity & liboqs risk.** `liboqs` was used only for research measurement, not
  proposed for production (ADR-004). What are the concrete risks of ever shipping liboqs prototypes,
  and what selection criteria (audit history, constant-time, maintenance, license MIT-compat,
  reproducible build, pinned version) should gate a production library
  (`docs/PQ_AUDIT_CHECKLIST_V3.md §8`)?

## J. Hardware wallets and activation

- **J1 — Hardware-wallet requirements.** Minimum flash/RAM/throughput and firmware requirements for
  on-device ML-DSA and for hybrid (both legs) signing; is on-device ML-DSA realistic for current
  secure elements (`docs/PQ_WALLET_MIGRATION_V3.md §4.1`)?
- **J2 — Activation & rollback criteria.** Are the phased, condition-gated activation and the
  suspend-on-vulnerability / rollback plan (`docs/PQ_ACTIVATION_PLAN_V3.md`) sufficient to avoid a
  node-upgrade chain split, and what version-signalling threshold / minimum-node-version policy would
  you require before any height is ever set?

---

*Author: NeoB. Research/architecture only — activates nothing. No audit has been performed.*

# SOST Post-Quantum Security Assumptions (V3)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> V3 supersedes `docs/PQ_MIGRATION_V2.md` (PR #37). SOST is **not** claimed to be quantum-safe or
> post-quantum secure. **No audit of any kind has been performed on the PQ prototype, its
> assumptions, or its integration.** Every assumption below marked *unverified* or *pending audit*
> must be independently reviewed before any activation is even proposed.

---

## 1. Purpose

This document states, as explicitly as possible, the cryptographic and system assumptions that the
V3 PQ migration research relies on. It separates:

- **(A) Assumptions holding today** — what protects mainnet right now.
- **(B) Assumptions for the PQ prototype** — what would need to hold if PQ were ever activated.
- **(C) System / protocol assumptions** — encoding, domain separation, parsing, hybrid semantics.

Each assumption is tagged **[HOLDS TODAY]**, **[STANDARD-BACKED]**, **[UNVERIFIED / PENDING
AUDIT]**, or **[OPEN / RESEARCH]**.

---

## 2. Classical cryptographic assumptions (today)

### A1. ECDSA / secp256k1 discrete-log hardness (classical) — [HOLDS TODAY]

SOST spend authorisation is ECDSA over secp256k1, compact 64-byte `r||s`, canonical LOW-S
(`README.md:196`; `src/tx_signer.cpp:8,19`; `IsLowS` `:210`; `EnforceLowS` `:223`;
`secp256k1_ecdsa_verify` `:374`; `VerifyTransactionInput` `:551`). We assume the elliptic-curve
discrete-log problem on secp256k1 is hard **against classical adversaries**. This assumption holds
today and is the basis of mainnet security.

**Explicitly does NOT hold against a CRQC:** Shor's algorithm recovers the private key from the
public key. This is precisely the reason for the migration research and is treated as a *known
future break*, not an open question.

### A2. BIP-340 Schnorr (block-identity only) — [HOLDS TODAY, out of spend scope]

BIP-340 Schnorr is used **only** for SbPoW miner block-identity binding, gated by
`SOST_HAVE_SCHNORRSIG` in a private, separate secp256k1 context (`src/sbpow.cpp:37-80`, sign
`:249-270`, verify `:304-318`; public wording `website/index.html:1413`). It is not used for
spending and shares secp256k1's classical-only assumption. A CRQC affects it too, but it is a
separate migration surface and out of scope for spend-signature assumptions here.

---

## 3. Post-quantum primitive assumptions (prototype)

### A3. ML-DSA (FIPS 204) — Module-LWE / Module-SIS hardness — [STANDARD-BACKED, UNVERIFIED in SOST]

The prototype primary PQ signature is **ML-DSA (FIPS 204)**, standardised by NIST from
CRYSTALS-Dilithium. Its unforgeability rests on the hardness of **Module Learning-With-Errors
(Module-LWE)** and **Module Short-Integer-Solution (Module-SIS)** lattice problems, assumed hard
against both classical and quantum adversaries. We assume:

- The Module-LWE / Module-SIS parameters chosen by FIPS 204 for ML-DSA-44 (NIST security level 2),
  ML-DSA-65 (level 3), and ML-DSA-87 (level 5) provide their claimed security levels.
- The fixed FIPS 204 object sizes are exact and are not altered by SOST (public key / signature):
  ML-DSA-44 = 1312 / 2420; ML-DSA-65 = 1952 / 3309; ML-DSA-87 = 2592 / 4627 bytes.

**[UNVERIFIED / PENDING AUDIT]** — SOST has not audited any ML-DSA implementation, its constant-time
properties, its parameter handling, or its integration. Lattice assumptions are younger than the
discrete-log assumption and carry more model risk. The prototype defaults to ML-DSA-44 (`0x01`) with
ML-DSA-65 (`0x03`) and ML-DSA-87 (`0x04`) **reserved**.

### A4. SLH-DSA (FIPS 205) — hash-based conservative backup — [STANDARD-BACKED, RESERVED]

**SLH-DSA (FIPS 205)** is retained as a **conservative backup**, not an automatic replacement. Its
security reduces (essentially) to the security of its underlying hash function, a much older and
better-understood assumption than lattices — so it hedges the risk that a lattice assumption is later
weakened. Trade-off: SLH-DSA signatures are large and parameter-set dependent (e.g.
SLH-DSA-SHA2-128s: public key 32 B, signature 7856 B — sizes are **parameter-set dependent** and not
pinned to a single number unless the exact set is named). We assume the chosen hash function retains
its required (second-)preimage / collision properties even under quantum attack (see A5). SLH-DSA is
`0x10 SLH_DSA_RESERVED` in the registry — **reserved, not active.**

---

## 4. Hash-function assumptions

### A5. SHA-256 resistance under Grover — [STANDARD-BACKED, HOLDS with 256-bit output]

SOST relies on SHA-256 for hashing (including address hashes protecting *unrevealed* public keys).
Grover's algorithm gives only a **quadratic** speedup for preimage search, effectively halving the
brute-force exponent: a 256-bit preimage search drops to ~2^128 quantum work, which remains
infeasible. We assume:

- SHA-256 remains **second-preimage** and **collision** resistant, with only Grover's quadratic
  speedup applying to preimage/second-preimage search — so 256-bit output stays safe.
- Address-hash protection of unrevealed public keys therefore remains meaningful post-quantum (the
  hash is not the weak link; the revealed public key is — see the threat model, §2.3).

This is a mainstream, standard-backed assumption. It is not SOST-specific and is treated as holding.

---

## 5. System / protocol assumptions (prototype)

### A6. Domain separation — [OPEN / MUST-HOLD, UNVERIFIED]

We assume every signed message is **domain-separated**: distinct contexts (spend vs SbPoW
block-identity; mainnet vs isolated testnet; per-input context) produce distinct signed messages so
a signature is never valid across contexts (anti-replay, §A9). The isolated PQ testnet uses distinct
network magic (see `docs/PQ_TESTNET_PLAN_V3.md`). **[UNVERIFIED / PENDING AUDIT]** — the exact
domain-separation tags for the PQ witness are prototype-level and unaudited.

### A7. Deterministic canonical encoding — [OPEN / MUST-HOLD, UNVERIFIED]

We assume the versioned PQ witness has a **single canonical byte encoding**: one valid serialization
per logical witness, with strict length-prefixed, bounds-checked, single-pass parsing. This is the
PQ analogue of ECDSA's canonical LOW-S (`IsLowS` `src/tx_signer.cpp:210`; `E5` at `:247`/`:277`) and
is required for txid stability and malleability resistance. Contrast today's fixed, no-length-prefix
64+33 layout (`include/sost/transaction.h:72-73`; `src/transaction.cpp:210-225`), which is
inflexible but unambiguous. **[UNVERIFIED / PENDING AUDIT].**

### A8. Unknown alg-ids are rejected — [MUST-HOLD by construction]

We assume every node **deterministically REJECTS** any `alg_id` not explicitly active in the
registry — including `RESERVED` entries and `0xFF INVALID`, and any unlisted byte value — rather than
ignoring or best-effort-accepting it. The V3 PROVISIONAL registry (1-byte `alg_id`): `0x00`
LEGACY_ECDSA_SECP256K1; `0x01` PQ_ML_DSA_44; `0x02` HYBRID_ECDSA_ML_DSA_44 (AND); `0x03`
ML_DSA_65_RESERVED; `0x04` ML_DSA_87_RESERVED; `0x10` SLH_DSA_RESERVED; `0xFF` INVALID; anything else
= REJECT. This reject-by-default rule is a *precondition* for avoiding consensus splits, not an
optional optimisation. (Note: V3 reassigns ids relative to V2; no protocol conflict because
`PQ_ACTIVATION_HEIGHT = INT64_MAX`, i.e. unused.)

### A9. Replay resistance — [DEPENDS ON A6]

We assume a valid signature/witness cannot be replayed across inputs, transactions, or networks,
because the signed message commits to the full spend context plus network domain separation (A6).

### A10. Hybrid AND requires breaking BOTH schemes — [MUST-HOLD by construction]

We assume HYBRID (`0x02`) is **conjunctive AND**: a spend authorises **only if both** the ECDSA
**and** the ML-DSA-44 signatures verify over the same canonical message. Therefore forging a hybrid
spend requires breaking **both** ECDSA **and** ML-DSA-44. **OR-hybrid is explicitly excluded** — an
OR would be only as strong as the *weaker* scheme, since breaking either suffices to forge. AND is
the conservative transition choice and must be enforced as an AND at the verifier, not a
best-effort/either-path check.

---

## 6. Explicit non-assumptions (things we do NOT assume)

- We do **not** assume SOST is quantum-safe or post-quantum secure today. It is not.
- We do **not** assume ML-DSA is active on mainnet. It is not; `PQ_ACTIVATION_HEIGHT = INT64_MAX`.
- We do **not** assume any implementation (ML-DSA, SLH-DSA, the witness parser, the hybrid verifier)
  is correct, constant-time, or side-channel-free. **No audit has been performed.**
- We do **not** assume ML-KEM (FIPS 203) is involved — it is a KEM, not a signature, and is not used
  for SOST spends. The signature threat is "collect public keys now, forge later," not "harvest now,
  decrypt later."
- We do **not** assume dormant/lost coins can be protected; their owners cannot migrate them.
- We do **not** assume any performance characteristic — no timings are stated or relied upon
  anywhere in V3.

---

## 7. Assumptions status summary

| ID | Assumption | Tag | Verified? |
|---|---|---|---|
| A1 | secp256k1 discrete-log hard (classical) | HOLDS TODAY | Standard; breaks under Shor (known) |
| A2 | BIP-340 Schnorr (block-identity only) | HOLDS TODAY | Out of spend scope |
| A3 | ML-DSA Module-LWE/SIS hardness | STANDARD-BACKED | UNVERIFIED in SOST / pending audit |
| A4 | SLH-DSA hash-based backup | STANDARD-BACKED | RESERVED, not active |
| A5 | SHA-256 resistant under Grover (256-bit) | STANDARD-BACKED | Holds (quadratic only) |
| A6 | Domain separation | MUST-HOLD | UNVERIFIED / pending audit |
| A7 | Deterministic canonical encoding | MUST-HOLD | UNVERIFIED / pending audit |
| A8 | Unknown alg-ids rejected | MUST-HOLD | By construction; needs test/audit |
| A9 | Replay resistance | DEPENDS ON A6 | UNVERIFIED / pending audit |
| A10 | Hybrid = AND (break BOTH) | MUST-HOLD | By construction; needs test/audit |

---

## 8. Status

The lattice-based (A3) and system-level (A6–A10) assumptions are **unverified and pending external
audit**. **No audit has been performed.** These assumptions describe what *would need to hold* if PQ
were ever activated; they do not assert that SOST is secure against quantum adversaries today.
Post-quantum transaction validation is not active on mainnet. This document changes no consensus rule
and activates nothing.

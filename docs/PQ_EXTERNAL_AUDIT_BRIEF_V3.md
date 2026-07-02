# SOST Post-Quantum Migration — External Cryptographic Audit Brief (V3)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> **Purpose.** This brief is a **self-contained entry point for an external cryptographer / code
> auditor**. It can be read without rebuilding the SOST project history. It summarises the design and
> then points to the authoritative V3 documents (the single source of truth) for full detail — it
> does **not** duplicate their content. Where a constant is load-bearing for review (object sizes,
> algorithm ids, consensus limits, measured medians) it is restated here with a citation to its
> source document.
>
> **No audit has been performed.** **No** post-quantum transaction validation is active on mainnet;
> `PQ_ACTIVATION_HEIGHT = INT64_MAX` ("never"). This is a research/architecture package only.

Companion documents in this hand-off package:
- `docs/PQ_EXTERNAL_AUDITOR_QUESTIONS_V3.md` — the specific questions the auditor must answer.
- `docs/PQ_EXTERNAL_AUDIT_MANIFEST_V3.md` — file inventory, SHA-256 hashes, exact reproduce commands.

---

## 1. Executive summary

SOST today authorises spends with **ECDSA over secp256k1** (compact 64-byte `r||s`, canonical
LOW-S). A cryptographically-relevant quantum computer (CRQC) running Shor's algorithm would recover
the private key from any **revealed** public key, breaking spend unforgeability. This package is a
**research prototype and architecture** for migrating spend authorisation to a post-quantum
signature (ML-DSA, FIPS 204) via a **versioned, variable-length witness** carrying a 1-byte
crypto-agility `alg_id`, with three spend types — **LEGACY** (ECDSA), **PQ** (ML-DSA-44), and
**HYBRID** (ECDSA **AND** ML-DSA-44, conjunctive). Nothing is activated: the prototype is not
compiled into the node, adds no dependency, sets no height, and changes no consensus rule. The ask
is an independent cryptographic and code review of the *design* and the *prototype* before any
experimental testnet is even stood up. Full index: `docs/PQ_MIGRATION_V3.md`.

## 2. Exact audit scope

In scope for this review:
- The **witness format and canonical serialization** (`docs/PQ_TX_FORMAT_V3.md`; prototype
  `prototype/pq/pq_witness.h`).
- The **crypto-agility registry** and unknown/reserved-id handling (`prototype/pq/pq_alg_registry.h`).
- The **hybrid AND semantics** and per-scheme **domain separation** (`prototype/pq/pq_validate.h`,
  ADR-002, `docs/PQ_TX_FORMAT_V3.md §6-7`).
- The **threat model** and **security assumptions** (`docs/PQ_THREAT_MODEL_V3.md`,
  `docs/PQ_SECURITY_ASSUMPTIONS_V3.md`).
- The **size / DoS / verify-work model** (`docs/PQ_PERFORMANCE_MODEL_V3.md`, incl. §4.4).
- The **wallet / fund-migration** strategy (`docs/PQ_WALLET_MIGRATION_V3.md`).
- The **prototype tests and fuzz target** (`tests/pq_vectors/`).
- The **benchmark methodology and provenance** (`docs/PQ_BENCHMARK_RESULTS_V3.md`,
  `scripts/pq_bench/`).
- The **pre-activation audit checklist** as the gating instrument (`docs/PQ_AUDIT_CHECKLIST_V3.md`).

## 3. Explicit out-of-scope

- **Any mainnet consensus code.** `git diff origin/main` over `src/`, `include/`,
  `genesis_block.json`, `CMakeLists.txt`, `cmake/`, `config/` is **empty**; there is nothing to audit
  there for PQ.
- **Selecting a production ML-DSA implementation.** `liboqs` was used only for research measurement
  in an isolated venv; it is explicitly *not* a proposed production dependency (ADR-004).
- **The transport-channel (P2P KEM) track** (`docs/PQ_THREAT_MODEL_V3.md §12`) — a *secondary*,
  signature-unrelated concern (ML-KEM-768 / FIPS 203). It may be commented on but is not the
  signature-migration review being commissioned.
- **The SbPoW BIP-340 Schnorr block-identity binding** — a separate migration surface, not spend
  authorisation (§4 below).
- **Setting any activation height, date, weight constant, or standardness limit** — all are future,
  separate consensus proposals.

## 4. Current active cryptography (mainnet, verified)

- **Spend authorisation = ECDSA over secp256k1**, compact 64-byte `r||s` big-endian, canonical
  **LOW-S** enforced. `README.md:196`; `src/tx_signer.cpp:8,19`; `IsLowS` `:210`; `EnforceLowS`
  `:223`; LOW-S check `:277`; `secp256k1_ecdsa_verify` `:374`; `VerifyTransactionInput` `:551`.
- **Input layout is fixed-width, no length prefix:** `TxInput.signature = std::array<Byte,64>`,
  `TxInput.pubkey = std::array<Byte,33>` (`include/sost/transaction.h:72-73`), serialized raw
  (`src/transaction.cpp:210-217` / `:220-225`); per-input on-chain size **133 bytes**
  (`src/tx_validation.cpp:77`). This fixed layout is exactly why PQ needs a *new* witness.
- **BIP-340 Schnorr is used ONLY for SbPoW miner block-identity binding**, in a separate secp256k1
  context gated by `SOST_HAVE_SCHNORRSIG` (`src/sbpow.cpp:37-80`, sign `:249-270`, verify
  `:304-318`). It is **not** the spend scheme and is out of scope for spend-signature review.
- **SHA-256** hashing is only quadratically weakened by Grover; 256-bit output remains adequate
  (`docs/PQ_SECURITY_ASSUMPTIONS_V3.md §A5`).

## 5. Proposed model — LEGACY / ML-DSA / HYBRID

Three spend types selected by the 1-byte `alg_id` (`docs/PQ_TX_FORMAT_V3.md §3`, ADR-002):
- **LEGACY (`0x00`)** — ECDSA secp256k1, today's behaviour re-expressed in the witness; compatibility
  only.
- **PQ (`0x01`)** — ML-DSA-44 (FIPS 204, NIST L2); prototype/testnet only.
- **HYBRID (`0x02`)** — **ECDSA AND ML-DSA-44** (conjunctive; both must verify over the same
  domain-separated sighash). **OR-hybrid is refused**: an OR-hybrid is only as strong as the weaker
  leg. Forging a hybrid requires breaking **both** ECDSA and ML-DSA-44 (`docs/PQ_THREAT_MODEL_V3.md
  §5`, `docs/PQ_SECURITY_ASSUMPTIONS_V3.md §A10`).

## 6. Security assumptions

Fully enumerated and tagged (HOLDS TODAY / STANDARD-BACKED / MUST-HOLD / OPEN) in
`docs/PQ_SECURITY_ASSUMPTIONS_V3.md`. Key points: A1 secp256k1 discrete-log (classical) holds today
but breaks under Shor (known); A3 ML-DSA Module-LWE/SIS hardness is STANDARD-BACKED but **UNVERIFIED
in SOST**; A5 SHA-256 holds under Grover with 256-bit output; A6–A10 (domain separation, canonical
encoding, unknown-id rejection, replay resistance, hybrid=AND) are **MUST-HOLD, UNVERIFIED / pending
audit**. Explicit non-assumptions: SOST is **not** claimed quantum-safe; no implementation is assumed
correct/constant-time; no performance is assumed.

## 7. Domain separation

Every scheme signs over a domain-separated message `H(domain_tag || 0x00 || sighash)` with distinct
per-scheme tags (`prototype/pq/pq_alg_registry.h`; `docs/PQ_TX_FORMAT_V3.md §6`):
`SOST/pq-v3/ecdsa-secp256k1`, `SOST/pq-v3/ml-dsa-44`, `SOST/pq-v3/hybrid-ecdsa+ml-dsa-44` (all
**PROVISIONAL** strings). The intent is to prevent algorithm-confusion, downgrade,
signature-substitution, and cross-context replay. `sighash` is the existing SOST version-1 sighash
(`src/tx_signer.cpp`); the witness does not change how it is computed.

## 8. Provisional algorithm registry

1-byte `alg_id` (PROVISIONAL — `prototype/pq/pq_alg_registry.h`, ADR-001, `docs/PQ_DECISION_LOG_V3.md
D1`): `0x00` LEGACY_ECDSA_SECP256K1; `0x01` PQ_ML_DSA_44; `0x02` HYBRID_ECDSA_ML_DSA_44 (AND); `0x03`
ML_DSA_65_RESERVED; `0x04` ML_DSA_87_RESERVED; `0x10` SLH_DSA_RESERVED; `0xFF` INVALID; **any other
value = deterministically REJECTED**. This map **reassigns** ids relative to V2 (which used `0x02` =
ML-DSA-65 and `0x10` = hybrid); the reassignment is safe because `PQ_ACTIVATION_HEIGHT = INT64_MAX`,
so no id is consensus-live in either iteration.

## 9. Variable-length witness

The PQ witness rides a **new tx version 2** (`PQ_WITNESS_TX_VERSION = 2`, PROVISIONAL); mainnet tx
version is 1 (`include/sost/transaction.h:109`), so old clients reject a v2 tx by the version check
rather than mis-parsing an unknown witness (ADR-003, `docs/PQ_TX_FORMAT_V3.md §2`). Wire format
(prototype, `docs/PQ_TX_FORMAT_V3.md §5`): `witness := alg_id(1) || component*`, each component
`len(2 bytes, big-endian) || bytes[len]`, no trailing bytes. Exact component sizes (FIPS 204):
ML-DSA-44 sig 2420 / pk 1312; ML-DSA-65 3309 / 1952; ML-DSA-87 4627 / 2592; ECDSA 64 / 33.

## 10. Canonical serialization

Design goal: exactly one valid byte encoding per logical witness (the PQ analogue of ECDSA LOW-S),
for txid stability and malleability resistance. The prototype (`prototype/pq/pq_witness.h`,
`parse_witness`) enforces fixed 2-byte big-endian length prefixes, **exact-length** equality per
`alg_id`, single-pass bounds-checked parsing, and **no trailing bytes**, returning deterministic
codes (`OK`, `ERR_EMPTY`, `ERR_UNKNOWN_ALGID`, `ERR_RESERVED_ALGID`, `ERR_INVALID_ALGID`,
`ERR_TRUNCATED`, `ERR_BAD_LENGTH_PREFIX`, `ERR_WRONG_COMPONENT_LEN`, `ERR_TRAILING_BYTES`,
`ERR_DUP_OR_MISORDERED`). **Auditor note / known doc inconsistency:** the wire spec
(`docs/PQ_TX_FORMAT_V3.md §5`) and the prototype use a **fixed 2-byte big-endian** length prefix,
whereas `docs/PQ_PERFORMANCE_MODEL_V3.md §3` models overhead as `CompactSize` and
`docs/PQ_AUDIT_CHECKLIST_V3.md §2` still says "shortest-form CompactSize"; the canonical length
encoding must be reconciled to a single normative choice (see the auditor questions, canonical
encoding).

## 11. Unknown-id rejection

Reject-by-default is a **precondition** for avoiding consensus splits, not an optimisation: any
`alg_id` not explicitly ACTIVE — including RESERVED entries, `0xFF`, and any unlisted byte — must be
**deterministically REJECTED, never ignored** (`docs/PQ_THREAT_MODEL_V3.md §4.7`,
`docs/PQ_SECURITY_ASSUMPTIONS_V3.md §A8`). The prototype distinguishes unknown vs reserved vs invalid
with distinct error codes and is exercised by negative vectors (`tests/pq_vectors/`).

## 12. Size limits

Consensus limits any witness must honour (`include/sost/consensus_constants.h`): `MAX_TX_BYTES_CONSENSUS
= 100000` (:15), `MAX_BLOCK_BYTES_CONSENSUS = 1000000` (:16), `MAX_INPUTS_CONSENSUS = 256` (:17),
`MAX_OUTPUTS_CONSENSUS = 256` (:18); plus `MAX_TX_BYTES_STANDARD = 16000` (`include/sost/tx_validation.h:26`),
`MAX_BLOCK_TXS_CONSENSUS = 65536` (`include/sost/block_validation.h:37`), `MAX_BLOCK_TX_COUNT = 4096`
(`include/sost/mempool.h:22`). Modelled per-input size: legacy 133 B → ML-DSA-44 ~3775 B (~28×),
ML-DSA-65 ~5304 B (~40×), HYBRID ~3874 B (~29×) (`docs/PQ_PERFORMANCE_MODEL_V3.md §3`). No weight
discount is proposed for PQ. The full migration surface (every fixed-size key/sig/hash field) is
inventoried in `docs/PQ_MIGRATION_V3.md §1.1`.

## 13. Verify-work budget

Byte limits do not bound verify **CPU**. A **candidate per-transaction verify-work budget** (weighted
sum of per-input verify costs, ECDSA weight 1, each PQ/hybrid `alg_id` weight `> 1`, checked **before**
any signature is verified) is documented in `docs/PQ_PERFORMANCE_MODEL_V3.md §4.4` (carried over from
V2), complementary to "cheapest checks first" (`docs/PQ_THREAT_MODEL_V3.md §6.2`). The per-`alg_id`
weights are **not asserted** — they must be calibrated from measured verify timings (still pending an
authoritative run). Any actual budget constant is itself a consensus change and out of scope here.

## 14. DoS risks

Four classes (`docs/PQ_THREAT_MODEL_V3.md §6`): (6.1) giant-signature block/mempool bloat (mitigate
with exact per-alg size bounds, reject before verify); (6.2) costly-verify CPU (cheap checks first +
the verify-work budget above); (6.3) memory exhaustion (never allocate on an unvalidated length;
single-pass bounds-checked parse); (6.4) unknown-alg split (deterministic reject). All are
research-level and **unaudited**.

## 15. Malleability risks

ECDSA already enforces canonical LOW-S. A PQ witness must define a single canonical encoding so a
third party cannot mutate an accepted witness into another accepted-but-different one (which would
change the txid) — `docs/PQ_THREAT_MODEL_V3.md §4.4`, `docs/PQ_SECURITY_ASSUMPTIONS_V3.md §A7`. The
prototype's exact-length, no-trailing-bytes, fixed-order rules are the intended mitigation; see the
canonical-encoding inconsistency flagged in §10.

## 16. Wallet migration

Opt-in, never auto (`docs/PQ_WALLET_MIGRATION_V3.md`, ADR-007, `docs/PQ_DECISION_LOG_V3.md D7`). Three
coexisting address classes bound to `alg_id`; a **new address prefix** is *reserved* but `sost2…` is a
**provisional placeholder only** (not final). A wallet must refuse to send to a class the network
cannot yet validate or the recipient cannot spend. Migration priority follows exposure:
reused/revealed addresses first, then dormant never-spent addresses before their single safe spend.

## 17. Backup / import / recovery

**An ECDSA seed does not yield an ML-DSA key** (`docs/PQ_WALLET_MIGRATION_V3.md §3`). PQ keys need a
dedicated derivation branch; the exact KDF/derivation is **intentionally unspecified / open**. Until
fixed, treat PQ keys as independently-backed; a pre-PQ backup contains no PQ keys. Descriptors /
watch-only / private-key export must carry the `alg_id` and default to LEGACY, never silently
upgrade. Hardware wallets / custodians / multisig face large-key and mixed-class hazards (documented,
not solved by protocol alone).

## 18. Harvest-now-decrypt-later (where applicable)

For **signatures**, the correct framing is **NOT** harvest-now-decrypt-later; it is **"collect public
keys now, forge later"** — Shor recovers the private key from a revealed public key
(`docs/PQ_THREAT_MODEL_V3.md §2.2`). Harvest-now-decrypt-later applies **only** to the encrypted P2P
**transport channel** (a KEM concern), which is a separate, secondary, out-of-scope track
(`docs/PQ_THREAT_MODEL_V3.md §12`). The two must not be conflated.

## 19. ML-DSA (signature) vs ML-KEM (transport) distinction

**ML-DSA (FIPS 204)** is a *signature* scheme and is the subject of this migration. **ML-KEM (FIPS
203)** is a *key-encapsulation mechanism*, **never used for SOST spends**; it appears only in the
secondary transport-channel track (`docs/PQ_MIGRATION_V3.md §1.2`, `docs/PQ_THREAT_MODEL_V3.md §12`).
**SLH-DSA (FIPS 205)** is a hash-based *signature* reserve (`0x10`), not part of the current
selection.

## 20. Benchmark results with provenance

Two kinds of numbers (`docs/PQ_BENCHMARK_RESULTS_V3.md`, `docs/PQ_PERFORMANCE_MODEL_V3.md`):
- **Sizes — KNOWN** from FIPS 204 + current serialization (exact; not measured).
- **Timings — INDICATIVE only.** `liboqs 0.15.0` + `liboqs-python 0.15.0` in an **isolated venv**
  (not in the node build), **2026-07-02**, Intel i9-10885H, Linux 5.15 WSL2, CPython 3.10.12,
  **10,000 iters/op**, ML-DSA-44/65/87 keygen/sign/verify-valid/verify-invalid. Median verify (µs):
  ML-DSA-44 ~24.7, ML-DSA-65 ~40.2, ML-DSA-87 ~62.8. Raw JSON
  `scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json` (schema-validated). **Turbo /
  clock NOT pinned → order-of-magnitude only.** ECDSA baseline, full HYBRID cost, peak memory, and
  p99 are **`RESULTS_PENDING_COMPUTE_ENV`**; a clock-pinned bare-metal authoritative run is required
  before the verify-work-budget weights (§13) may be set.

## 21. Test + fuzz results

`tests/pq_vectors/` (std-lib only, off-ctest): **21/21 PASS** — LEGACY/PQ/HYBRID round-trips plus
negatives (empty, unknown id, reserved ids, `0xFF`, truncated prefix, wrong length, oversized length,
trailing bytes, mis-ordered/duplicated hybrid halves, hybrid AND both directions, per-scheme domain
tags). Fuzz smoke (`fuzz_pq_witness.cpp`, libFuzzer + ASan/UBSan): **~11M execs, 0 crashes / 0 leaks
/ 0 UB** in a short run (extended, coverage-guided fuzzing and FIPS 204 ACVP known-answer vectors are
**not** yet run). Exact reproduce commands: `docs/PQ_EXTERNAL_AUDIT_MANIFEST_V3.md`.

## 22. Provisional decisions

Recorded in `docs/PQ_DECISION_LOG_V3.md`: D1 1-byte `alg_id` registry (PROVISIONAL); D2 hybrid = AND
(ACCEPTED principle); D3 variable-length versioned witness under tx v2 (PROVISIONAL); D4 library
isolation behind an interface (PROVISIONAL); D5 no mainnet activation / INT64_MAX (DEFERRED); D6
whitepaper-as-code (ACCEPTED process); D7 opt-in wallet migration (ACCEPTED recommendation).
Provisional algorithm recommendation (**not final**): **HYBRID_ECDSA_ML_DSA_44** as the conservative
transition default, ML-DSA-65 reserved for high-value outputs, SLH-DSA as reserve only — pending
measured verify timings and this review (`docs/PQ_V3_CONSOLIDATION_REVIEW.md §15`).

## 23. Still-open decisions

`docs/PQ_DECISION_LOG_V3.md` "DECISIONS PENDING": final `alg_id` assignment; exact size limits /
weights; activation height (remains INT64_MAX); external audit scope/auditor/sign-off; isolated
testnet parameters; final address prefix (`sost2…` is placeholder); PQ key-derivation KDF. Plus the
canonical length-encoding reconciliation flagged in §10.

## 24. Concrete questions the auditor must answer

Enumerated, specific, and non-generic in `docs/PQ_EXTERNAL_AUDITOR_QUESTIONS_V3.md` (AND-hybrid
sufficiency; downgrade / cross-algorithm / substitution attacks; algorithm↔key↔signature↔input↔tx↔
network binding; canonical encoding; malleability; duplicate-key ambiguity; unknown-alg handling;
replay across networks and spend classes; witness/verify-work limits; invalid-signature flooding;
batch verification; side channels; entropy; secret storage; backup/recovery; never-moved-fund
migration; prior key exposure; ML-DSA-44 vs -65 vs -87; SLH-DSA reserve; library maturity / liboqs
prototype risk; production-library selection; hardware-wallet requirements; activation & rollback
criteria).

## 25. Minimum conditions to recommend an experimental testnet

The auditor should state whether, at minimum: the witness parser is memory-safe and unambiguous under
fuzzing + review; unknown/reserved/invalid ids are provably reject-by-default; the canonical encoding
is single-valued (§10 reconciled); hybrid is provably AND (both legs, both directions); domain
separation binds algorithm/key/context so no signature crosses schemes or networks; per-alg size
bounds and a (calibrated) verify-work bound exist; and the testnet is confirmed unreachable from
mainnet code paths (`SOST_EXPERIMENTAL_PQ_TESTNET_ONLY`, distinct network magic — see
`docs/PQ_TESTNET_PLAN_V3.md`). A testnet recommendation does **not** imply any mainnet activation.

## 26. Minimum conditions to reject the design

The auditor should reject (send back to design) if, e.g.: the encoding admits two readings of one
byte-string or a malleable/ambiguous witness; OR-hybrid is expressible or a hybrid can pass on one
leg; an unknown/reserved id can be accepted or "ignored"; downgrade lets a PQ/hybrid output be spent
by a bare legacy witness; a signature is replayable across inputs/txs/networks or across LEGACY/PQ/
HYBRID; the parser can be driven to unbounded allocation or over/under-read; or a chosen production
library/parameter set has disqualifying side-channel/maturity problems.

## 27. Confirmation: NO mainnet activation

`PQ_ACTIVATION_HEIGHT = INT64_MAX` ("never"). `git diff origin/main` over `src/`, `include/`,
`genesis_block.json`, `CMakeLists.txt`, `cmake/`, `config/` is **empty**. The prototype is not in any
CMake list and is `#include`d by no consensus/wallet/mempool/block unit; the mainnet build is
byte-identical with or without it. No dependency (`liboqs`/`oqs`) is added to the node. No activation
height, no date, no deploy, no merge. Any activation of post-quantum transaction validation is a
separate, future, reviewed, audited, announced consensus proposal — not this package.

---

*Author: NeoB. Research/architecture only — activates nothing. No audit has been performed.*

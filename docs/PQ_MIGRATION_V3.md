# SOST Post-Quantum Migration — V3 (RESEARCH / ARCHITECTURE / PROTOTYPE)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

This is the master index for the SOST post-quantum (PQ) migration research effort,
iteration **V3**. It **supersedes** V2 (branch `draft/pq-migration-v2`, PR #37),
which is left intact for history. Nothing here activates PQ on mainnet and
nothing here changes consensus; this research does **not** claim SOST is
quantum-safe.

## 1. Where SOST cryptography stands today (verified)

- **Spend authorisation** = ECDSA over secp256k1, compact 64-byte (`r||s`
  big-endian), canonical **LOW-S**. `README.md:196`;
  `src/tx_signer.cpp:8,19`; LOW-S at `src/tx_signer.cpp:210` (`IsLowS`), `:223`
  (`EnforceLowS`), `:277` (LOW-S check), verify at `:374`
  (`secp256k1_ecdsa_verify`).
- **Input layout** = fixed `signature[64]` + `pubkey[33]`
  (`include/sost/transaction.h:72-73`), serialized raw with no length prefix
  (`src/transaction.cpp:210-217`); 133 bytes/input (`src/tx_validation.cpp:77`).
- **BIP-340 Schnorr** is used **only** for SbPoW miner block-identity binding, in
  a separate secp256k1 context gated by `SOST_HAVE_SCHNORRSIG`
  (`src/sbpow.cpp:37-80`, sign `:249-270`, verify `:304-318`). It is **not** the
  spend scheme. Public copy already states this (`website/index.html:1413`).
- **SHA-256** hashing is unaffected by Shor and only quadratically weakened by
  Grover; 256-bit output remains adequate.
- SOST is **not** post-quantum today. PQ is under research. The inert placeholder
  proposal at `include/sost/proposals.h:44` (id 8, status `DEFINED`, heights
  `-1`) still uses the legacy label "SPHINCS+/Dilithium"; it changes no behaviour
  and should eventually be reworded to ML-DSA.

## 2. The threat, framed correctly

The signature risk is **not** "harvest now, decrypt later" (that is the
encryption/KEM risk). For signatures the correct framing is: an adversary can
**collect public keys now** (from revealed pubkeys on-chain) and **forge
signatures later** once a cryptographically-relevant quantum computer runs Shor's
algorithm to recover a private key from its public key.

- Funds at **revealed** pubkeys (already-spent-from or reused addresses) are
  exposed the moment such a machine exists.
- Funds at **unrevealed** pubkeys (hash-locked, never spent) expose only the
  hash until spend time; the spend then reveals the pubkey and opens a
  mempool/front-running window.
- **Dormant / lost** coins cannot be migrated by their owners — an intrinsic,
  unsolved problem discussed in `docs/PQ_THREAT_MODEL_V3.md`.

Full analysis: `docs/PQ_THREAT_MODEL_V3.md`, assumptions in
`docs/PQ_SECURITY_ASSUMPTIONS_V3.md`.

## 3. Architecture summary

- **Crypto-agility registry** (1-byte `alg_id`, PROVISIONAL): `0x00` legacy
  ECDSA, `0x01` ML-DSA-44, `0x02` hybrid, `0x03/0x04/0x10` reserved, `0xFF`
  invalid. Unknown ⇒ deterministic reject. (ADR-001, `docs/PQ_TX_FORMAT_V3.md`.)
- **Versioned variable-length witness** under a new tx version 2, because the
  fixed 64/33 slot cannot hold a 2420-byte signature. (ADR-003.)
- **Three spend types**: LEGACY (ECDSA, compatibility only), PQ (ML-DSA,
  prototype/testnet only), HYBRID (ECDSA **AND** ML-DSA — conjunctive; OR-hybrid
  refused). (ADR-002.)
- **Domain separation** per scheme; exact-size enforcement; no trailing bytes;
  no weight discount for PQ.
- **Library isolation** behind a replaceable interface (prefer NIST reference +
  liboqs for experimentation); no crypto dependency added to the build.
  (ADR-004.)
- **No mainnet activation**: `PQ_ACTIVATION_HEIGHT = INT64_MAX`; prototype not
  compiled; any experimental wiring sits behind `SOST_EXPERIMENTAL_PQ_TESTNET_ONLY`
  (default OFF, insufficient alone to change consensus). (ADR-005.)

## 4. Document map

| Area | Document |
|------|----------|
| Transaction / witness format | `docs/PQ_TX_FORMAT_V3.md` |
| Threat model | `docs/PQ_THREAT_MODEL_V3.md` |
| Security assumptions | `docs/PQ_SECURITY_ASSUMPTIONS_V3.md` |
| Wallet / fund migration | `docs/PQ_WALLET_MIGRATION_V3.md` |
| Activation & governance | `docs/PQ_ACTIVATION_PLAN_V3.md` |
| Performance & size model | `docs/PQ_PERFORMANCE_MODEL_V3.md` |
| Benchmark results (pending) | `docs/PQ_BENCHMARK_RESULTS_V3.md` |
| Testnet plan | `docs/PQ_TESTNET_PLAN_V3.md` |
| Pre-activation audit checklist | `docs/PQ_AUDIT_CHECKLIST_V3.md` |
| Decision log | `docs/PQ_DECISION_LOG_V3.md` |
| ADRs | `docs/ADR/ADR-001..007` |
| Canonical whitepaper tree | `docs/whitepaper/00..12` + `docs/WHITEPAPER_MANIFEST.md` |
| Prototype (not compiled) | `prototype/pq/`, tests `tests/pq_vectors/` |
| Benchmark harness | `scripts/pq_bench/` |
| Sync / claim tooling | `scripts/check_whitepaper_sync.py`, `scripts/check_crypto_claims.py` |

## 5. Prior art in this repo

`docs/QUANTUM_RESISTANCE_RESEARCH.md` (2026-04) is an earlier research note; V3
does not delete it and remains consistent with its threat framing. V2
(`docs/PQ_MIGRATION_V2.md` on PR #37's branch) is the immediate predecessor; V3
reassigns the provisional `alg_id` map and adds the safe parser, hybrid AND
semantics in the prototype, the whitepaper-as-code tooling, and the full
document set.

## 6. What V3 explicitly does NOT claim or do

- Does not claim SOST is quantum-safe / post-quantum secure / that ML-DSA is
  active.
- Sets no activation height and no date.
- Changes no PoW / ConvergenceX / SbPoW / DTD / supply / genesis / block-time /
  monetary parameter, no active tx or block format, no default wallet, no
  current address.
- Adds no dependency to and compiles nothing into the node/miner.
- Is not a consensus change and must not be merged as one. Any activation of
  post-quantum transaction validation is a separate, reviewed, audited, announced
  consensus upgrade (`docs/PQ_ACTIVATION_PLAN_V3.md`).

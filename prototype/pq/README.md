# SOST Post-Quantum Migration V3 — isolated prototype

**RESEARCH / PROTOTYPE ONLY. NOT COMPILED INTO THE MAINNET NODE OR MINER.**

This directory contains a self-contained, header-only reference implementation of
the proposed SOST post-quantum signature-witness format (`docs/PQ_TX_FORMAT_V3.md`).
It exists so reviewers can read and *run* the concrete design rather than only
prose. It:

- is **not** listed in `CMakeLists.txt` (the SOST build enumerates sources
  explicitly and never globs, so nothing here is picked up automatically);
- is **not** `#include`d by any consensus, wallet, mempool, block, or RPC unit;
- depends only on the C++17 standard library (no secp256k1, no liboqs);
- defines **no** consensus rule, registers **no** spend type, and sets **no**
  activation height (`PQ_ACTIVATION_HEIGHT == INT64_MAX`, the codebase's
  "never active" sentinel).

The mainnet build is byte-identical whether or not this directory is present.

## Files

| File | Purpose |
|------|---------|
| `pq_alg_registry.h` | 1-byte `alg_id` registry (PROVISIONAL), exact FIPS 204 sizes, domain-separation tags, activation sentinel. |
| `pq_witness.h`      | Witness structs, deterministic canonical serializer, and the **safe parser** (rejects unknown/reserved/invalid ids, truncation, wrong/oversized lengths, trailing bytes, mis-ordered hybrid halves). |
| `pq_validate.h`     | Conceptual per-scheme verification with domain separation and the **hybrid = AND** rule. Cryptographic verify calls are injected hooks (no crypto lib linked). |

## Wire format (proposed, provisional)

Rides a **new tx version 2** so today's version-1 mainnet clients reject it by
version check instead of mis-parsing it.

```
alg_id (1 byte)
  then, per component:  len (2 bytes, big-endian)  ||  bytes[len]
  0x00 LEGACY : sig(64)  pk(33)
  0x01 ML-DSA : sig(2420) pk(1312)
  0x02 HYBRID : ecdsa_sig(64) ecdsa_pk(33) mldsa_sig(2420) mldsa_pk(1312)
  0x03/0x04/0x10 : RESERVED — rejected
  0xFF : INVALID — rejected
No trailing bytes are tolerated. Each length prefix must equal the EXACT size
for its alg_id (no ranges), which also bounds memory and removes length
malleability.
```

## Build & run the tests

```
c++ -std=c++17 -Wall -Wextra -I prototype/pq \
    tests/pq_vectors/test_pq_witness.cpp -o /tmp/test_pq_witness
/tmp/test_pq_witness      # expect: pass=21 fail=0, exit 0
```

Optional fuzzing and the JSON vectors are described in `tests/pq_vectors/README.md`.

## Experimental flag (documentation only)

Any future experimental wiring must sit behind `SOST_EXPERIMENTAL_PQ_TESTNET_ONLY`
(default **OFF**), which must: block accidental mainnet compilation, require
explicit configuration, print visible warnings, and be **insufficient on its own**
to change consensus. That flag is documented in `docs/PQ_TESTNET_PLAN_V3.md`; it
is **not** defined or referenced by the production build in this PR.

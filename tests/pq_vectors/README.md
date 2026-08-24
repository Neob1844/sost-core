# SOST PQ V3 — prototype test vectors (STANDALONE, off-consensus)

These tests exercise the header-only post-quantum witness prototype in
`prototype/pq/`. They are **not** registered in the project CMake/ctest and are
**not** part of the SOST node or miner build. They depend only on the C++17
standard library, so they can never affect mainnet consensus.

## Build & run the unit/negative tests

```
c++ -std=c++17 -Wall -Wextra -I prototype/pq \
    tests/pq_vectors/test_pq_witness.cpp -o /tmp/test_pq_witness
/tmp/test_pq_witness
```

Expected output (exit code 0):

```
== SOST PQ V3 prototype witness tests ==
== pass=21 fail=0 ==
```

## What is covered

Valid vectors (serialize -> parse round-trip, fields preserved):
- LEGACY ECDSA (0x00), PQ ML-DSA-44 (0x01), HYBRID (0x02).

Negative vectors (each must be rejected with a specific, deterministic code):
- empty input
- unknown alg_id (0x7E)
- reserved alg_ids (0x03, 0x04, 0x10) — rejected distinctly, not "ignored"
- 0xFF INVALID sentinel
- truncated length prefix
- wrong declared component length (63 != 64)
- oversized declared length (0xFFFF) rejected before any allocation
- trailing bytes after a complete witness
- mis-ordered / duplicated hybrid halves

Verification semantics:
- LEGACY verifies via the injected ECDSA hook
- HYBRID is **AND**: rejects if either half fails (both directions tested)
- domain-separation tags differ per scheme

## Optional fuzzing

`fuzz_pq_witness.cpp` is a libFuzzer target for the parser (must never crash /
over-read / allocate unboundedly). Requires clang + libFuzzer:

```
clang++ -std=c++17 -g -O1 -fsanitize=fuzzer,address,undefined \
    -I prototype/pq tests/pq_vectors/fuzz_pq_witness.cpp -o /tmp/fuzz_pq
/tmp/fuzz_pq -max_total_time=60
```

If clang/libFuzzer is unavailable the fuzz target is simply not built. Status in
this environment: **fuzzer NOT_RUN (toolchain not verified present)**.

## JSON vectors

Machine-readable valid/invalid vectors are in `docs/examples/pq/`.

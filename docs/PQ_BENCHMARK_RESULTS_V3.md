# PQ Benchmark Results — V3 (SKELETON / NO MEASURED TIMINGS YET)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> **No measured timings exist yet.** `liboqs` / `python-oqs` is **NOT installed** in the build
> environment (verified **2026-07-02**). Every timing / CPU / memory cell below is
> **`RESULTS_PENDING_COMPUTE_ENV`**. **Never fabricate a timing.** The **size** math *is* known
> (from FIPS 204 + current serialization) and is filled in. Supersedes benchmark placeholders in
> `docs/PQ_MIGRATION_V2.md` (PR #37).

---

## 1. Required methodology (all fields mandatory before ANY number is published)

A performance number may be published in this file **only** when accompanied by every field below.
A row missing any field stays `RESULTS_PENDING_COMPUTE_ENV`.

| Field                | Requirement                                                              |
|----------------------|--------------------------------------------------------------------------|
| Hardware             | CPU model, core count, clock/turbo state (fixed), RAM                     |
| OS / kernel          | OS name + version, kernel version                                         |
| Compiler + version   | Exact compiler and version                                               |
| Build flags          | `-O2`/`-O3`, arch flags actually used (e.g. AVX2 on/off), ct vs optimised |
| Library + version    | `liboqs` release/commit and/or NIST reference source + commit             |
| Parameter sets       | Which ML-DSA (and SLH-DSA, if any) parameter sets were built/measured     |
| Iterations           | Count per operation (e.g. ≥ 10,000), plus warm-up runs                    |
| Statistics           | mean, median, p95, p99, stddev per operation                             |
| Date                 | Date of run                                                              |
| Commit               | Exact repo commit hash under test                                        |

Operations to measure per scheme: **keygen**, **sign**, **verify**.
Schemes: **ECDSA secp256k1** (baseline), **ML-DSA-44**, **ML-DSA-65**, **HYBRID** (ECDSA +
ML-DSA-44, AND). **SLH-DSA** only if the environment is valid — otherwise **N/A**.

---

## 2. Run provenance (to be filled on a real run)

```
Hardware:           <RESULTS_PENDING_COMPUTE_ENV>
OS / kernel:        <RESULTS_PENDING_COMPUTE_ENV>
Compiler + version: <RESULTS_PENDING_COMPUTE_ENV>
Build flags:        <RESULTS_PENDING_COMPUTE_ENV>
Library + version:  <RESULTS_PENDING_COMPUTE_ENV>   (liboqs / python-oqs NOT installed 2026-07-02)
Parameter sets:     <RESULTS_PENDING_COMPUTE_ENV>
Iterations / warmup:<RESULTS_PENDING_COMPUTE_ENV>
Date of run:        <RESULTS_PENDING_COMPUTE_ENV>
Commit under test:  <RESULTS_PENDING_COMPUTE_ENV>
```

---

## 3. Timing results template (all cells pending)

### 3.1 keygen (µs)
| Scheme            | mean | median | p95 | p99 | stddev |
|-------------------|------|--------|-----|-----|--------|
| ECDSA secp256k1   | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-44         | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-65         | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| HYBRID (ECDSA+44) | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| SLH-DSA           | N/A (env not valid) | N/A | N/A | N/A | N/A |

### 3.2 sign (µs)
| Scheme            | mean | median | p95 | p99 | stddev |
|-------------------|------|--------|-----|-----|--------|
| ECDSA secp256k1   | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-44         | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-65         | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| HYBRID (ECDSA+44) | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| SLH-DSA           | N/A (env not valid) | N/A | N/A | N/A | N/A |

### 3.3 verify (µs)
| Scheme            | mean | median | p95 | p99 | stddev |
|-------------------|------|--------|-----|-----|--------|
| ECDSA secp256k1   | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-44         | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-65         | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| HYBRID (ECDSA+44) | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| SLH-DSA           | N/A (env not valid) | N/A | N/A | N/A | N/A |

### 3.4 peak memory per verify (KiB)
| Scheme            | value |
|-------------------|-------|
| ECDSA secp256k1   | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-44         | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-65         | RESULTS_PENDING_COMPUTE_ENV |
| HYBRID (ECDSA+44) | RESULTS_PENDING_COMPUTE_ENV |
| SLH-DSA           | N/A (env not valid) |

---

## 4. Size math (KNOWN — from FIPS 204 + current serialization)

Signature / public-key sizes (FIPS 204; ECDSA from current SOST):

| Scheme            | Signature (B) | Public key (B) |
|-------------------|---------------|----------------|
| ECDSA secp256k1   | 64            | 33             |
| ML-DSA-44         | 2420          | 1312           |
| ML-DSA-65         | 3309          | 1952           |
| ML-DSA-87 (rsv.)  | 4627          | 2592           |
| SLH-DSA           | parameter-set dependent | parameter-set dependent |

Modelled per-input serialized size (outpoint 36 + alg_id 1 + length-prefixed fields; current legacy
= 133 B at `src/tx_validation.cpp:77`; fixed 64/33 layout at `include/sost/transaction.h:72-73`):

| Class             | Per-input (B) | vs legacy 133 |
|-------------------|---------------|---------------|
| LEGACY (today)    | 133           | 1.0×          |
| ML-DSA-44         | 3775          | ~28×          |
| ML-DSA-65         | 5304          | ~40×          |
| HYBRID (ECDSA+44) | 3874          | ~29×          |

See `docs/PQ_PERFORMANCE_MODEL_V3.md` for the full arithmetic and the impact against
`MAX_TX_BYTES_CONSENSUS = 100000` (`include/sost/consensus_constants.h:15`) and
`MAX_BLOCK_BYTES_CONSENSUS = 1000000` (`:16`).

---

## 5. How to fill this file

Run the benchmarks per `scripts/pq_bench/` in a valid compute environment, record every field in
§1–§2, then replace the `RESULTS_PENDING_COMPUTE_ENV` cells in §3. Do not publish a single timing
until its full provenance row is complete. SLH-DSA rows stay **N/A** until an environment with a
validated SLH-DSA implementation is available.

---

*Author: NeoB. No timings measured (liboqs/python-oqs absent, verified 2026-07-02). Sizes known
from FIPS 204. Activates nothing.*

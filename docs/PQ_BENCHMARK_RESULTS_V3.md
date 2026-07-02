# PQ Benchmark Results — V3 (SKELETON / NO MEASURED TIMINGS YET)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> **Indicative measured timings now exist (ML-DSA only), with caveats.** The node/miner **build**
> environment still ships **no** PQ library. For research measurement only, `liboqs 0.15.0` +
> `liboqs-python` were installed in an **isolated python venv** (never global, not in the build) on
> **2026-07-02**, and `scripts/pq_bench/pq_bench_v3.py --iters 10000` was run. Those numbers appear
> in §2–§3 and in `scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json`. **They are
> INDICATIVE, not authoritative:** the host is WSL2 with **turbo/clock NOT pinned**, so §1's
> "fixed clock" requirement is **not** met — treat medians as order-of-magnitude, not final. ECDSA
> baseline and SLH-DSA remain **unmeasured** (`RESULTS_PENDING_COMPUTE_ENV` / N/A). **Never fabricate
> a timing.** The **size** math *is* known (from FIPS 204 + current serialization). Supersedes
> benchmark placeholders in `docs/PQ_MIGRATION_V2.md` (PR #37).

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

## 2. Run provenance

### 2.1 Indicative research run (ML-DSA only — turbo NOT pinned, treat as order-of-magnitude)

```
Hardware:           Intel Core i9-10885H @ 2.40 GHz base, 14 logical cores, 23 GiB RAM
                    (turbo / clock NOT fixed — §1 "fixed clock" NOT met; numbers indicative)
OS / kernel:        Linux 5.15.167.4-microsoft-standard-WSL2 (glibc 2.35), WSL2 on Windows host
Interpreter:        CPython 3.10.12
Build flags:        liboqs default build (BUILD_SHARED_LIBS=ON), arch-native as auto-selected by
                    liboqs cmake; ct-vs-optimised path NOT separately controlled
Library + version:  liboqs 0.15.0 + liboqs-python 0.15.0, in an ISOLATED venv (not in node build)
Parameter sets:     ML-DSA-44, ML-DSA-65, ML-DSA-87 (final FIPS 204 names; "Dilithium*" NOT enabled)
Iterations / warmup:10000 per operation; no explicit warm-up loop (first iters included → higher p95)
Date of run:        2026-07-02 (UTC)
Commit under test:  831a662c (+ consolidation doc/harness edits on branch)
Raw JSON:           scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json
```

### 2.2 Authoritative run (still required — pinned clocks, ECDSA baseline, SLH-DSA)

```
Everything in 2.1 EXCEPT: fixed CPU clock / disabled turbo; a warm-up loop; ECDSA secp256k1
baseline measured on the same host; p99 captured; and, if a validated impl exists, SLH-DSA.
Status:             RESULTS_PENDING_COMPUTE_ENV (bare-metal, clock-pinned host)
```

---

## 3. Timing results

ML-DSA rows below are from the **indicative** run in §2.1 (WSL2, turbo NOT pinned, n=10000). `p99`
was **not captured** by the harness (it reports mean/median/p95/min/max/stddev). ECDSA baseline and
HYBRID (= one ECDSA verify + one ML-DSA-44 verify) were **not** measured in this run; SLH-DSA is out
of scope for the selection. All cells not yet measured stay `RESULTS_PENDING_COMPUTE_ENV` / N/A.

### 3.1 keygen (µs)
| Scheme            | mean | median | p95 | p99 | stddev |
|-------------------|------|--------|-----|-----|--------|
| ECDSA secp256k1   | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-44         | 28.2 | 26.7 | 33.9 | not captured | 13.8 |
| ML-DSA-65         | 47.4 | 43.2 | 62.8 | not captured | 114.5 |
| ML-DSA-87         | 69.0 | 67.0 | 84.0 | not captured | 9.0 |
| HYBRID (ECDSA+44) | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| SLH-DSA           | N/A (out of selection) | N/A | N/A | N/A | N/A |

### 3.2 sign (µs)
| Scheme            | mean | median | p95 | p99 | stddev |
|-------------------|------|--------|-----|-----|--------|
| ECDSA secp256k1   | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-44         | 64.4 | 53.2 | 130.9 | not captured | 34.1 |
| ML-DSA-65         | 105.6 | 86.5 | 224.5 | not captured | 70.7 |
| ML-DSA-87         | 128.9 | 111.5 | 242.4 | not captured | 57.3 |
| HYBRID (ECDSA+44) | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| SLH-DSA           | N/A (out of selection) | N/A | N/A | N/A | N/A |

### 3.3 verify (µs) — valid signatures
| Scheme            | mean | median | p95 | p99 | stddev |
|-------------------|------|--------|-----|-----|--------|
| ECDSA secp256k1   | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-44         | 25.9 | 24.7 | 30.1 | not captured | 5.1 |
| ML-DSA-65         | 43.2 | 40.2 | 58.4 | not captured | 30.4 |
| ML-DSA-87         | 64.7 | 62.8 | 79.4 | not captured | 8.6 |
| HYBRID (ECDSA+44) | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV | RESULTS_PENDING_COMPUTE_ENV |
| SLH-DSA           | N/A (out of selection) | N/A | N/A | N/A | N/A |

### 3.3b verify (µs) — INVALID signatures (bit-flipped; all correctly rejected)
| Scheme            | mean | median | p95 | stddev | correctness |
|-------------------|------|--------|-----|--------|-------------|
| ML-DSA-44         | 25.1 | 24.0 | 29.5 | 5.5 | forged sig rejected (asserted) |
| ML-DSA-65         | 42.4 | 39.2 | 58.0 | 40.3 | forged sig rejected (asserted) |
| ML-DSA-87         | 63.9 | 61.4 | 78.9 | 9.3 | forged sig rejected (asserted) |

Note: verify-invalid ≈ verify-valid cost (no obvious early-out timing gap in this run), consistent
with ML-DSA verifying the full object before deciding. Side-channel analysis is audit-scope, not
inferable from this coarse timing.

### 3.4 peak memory per verify (KiB)
| Scheme            | value |
|-------------------|-------|
| ECDSA secp256k1   | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-44         | RESULTS_PENDING_COMPUTE_ENV (not instrumented this run) |
| ML-DSA-65         | RESULTS_PENDING_COMPUTE_ENV |
| ML-DSA-87         | RESULTS_PENDING_COMPUTE_ENV |
| HYBRID (ECDSA+44) | RESULTS_PENDING_COMPUTE_ENV |
| SLH-DSA           | N/A (out of selection) |

### 3.5 throughput (derived from §3.3 medians, single-thread, indicative)
| Scheme    | verifies/s (≈ 1e6 / median_us) | signs/s (≈ 1e6 / median_us) |
|-----------|--------------------------------|-----------------------------|
| ML-DSA-44 | ~40,500 | ~18,800 |
| ML-DSA-65 | ~24,900 | ~11,600 |
| ML-DSA-87 | ~15,900 | ~9,000  |

Derived arithmetic only (from the indicative medians); not an independent measurement.

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

*Author: NeoB. Indicative ML-DSA timings measured 2026-07-02 in an isolated venv (liboqs 0.15.0,
WSL2, turbo unpinned — order-of-magnitude only); ECDSA baseline, HYBRID, memory, p99 and a
clock-pinned authoritative run remain pending. Sizes known from FIPS 204. Activates nothing.*

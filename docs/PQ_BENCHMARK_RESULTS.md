# SOST PQ Benchmark Results

Status: **DRAFT / RESEARCH.** No consensus change. Harness:
`scripts/pq_bench/pq_bench.py` (not part of the node/miner build).

Author: NeoB.

---

## 0. Environment used for this run

| Item | Value |
|---|---|
| Python | 3.10.12 |
| PQ library (`import oqs`) | **NOT available** in this environment |
| System liboqs (`ldconfig`) | not present |
| Consequence | **Size math = real** (FIPS 204 fixed sizes). **Timings = `RESULTS_PENDING_COMPUTE_ENV`** (not fabricated). |

Timings are honestly withheld because there is no PQ implementation to measure.
§4 gives exact commands to produce them on a real VPS + desktop.

---

## 1. FIPS parameter sizes (bytes — from the standard, not measured)

| Set | Standard | NIST level | public key | secret key | signature |
|---|---|---|---|---|---|
| ML-DSA-44 | FIPS 204 | 2 | 1,312 | 2,560 | 2,420 |
| ML-DSA-65 | FIPS 204 | 3 | 1,952 | 4,032 | 3,309 |
| ML-DSA-87 | FIPS 204 | 5 | 2,592 | 4,896 | 4,627 |
| ML-KEM-768 | FIPS 203 | 3 | pk 1,184 | sk 2,400 | ct 1,088 (ss 32) |

Compare: ECDSA secp256k1 today = 33-byte pubkey + 64-byte signature
(`include/sost/transaction.h:72-73`).

---

## 2. Transaction-size impact (REAL — computed by the harness)

Witness framing = `alg_id[1] + sig_len + pk_len` length-prefixed (see
`PQ_TX_FORMAT_PROPOSAL.md §2`). Non-witness per input = 36 B
(`prev_txid`+`prev_index`), per output = 31 B.

| scheme | witness/input | 1-input tx | 2-input tx | 10-input tx | tx / 1 MB block (2-in) | 10-in ≤ MAX_TX (100 kB) |
|---|---|---|---|---|---|---|
| legacy ECDSA | 97 B | 202 B | 335 B | 1,399 B | 2,985 | yes |
| PQ ML-DSA-44 | 3,737 B | 3,842 B | 7,615 B | 37,799 B | 131 | yes |
| PQ ML-DSA-65 | 5,266 B | 5,371 B | 10,673 B | 53,089 B | 93 | yes |
| hybrid ML-DSA-44 | 3,834 B | 3,939 B | 7,809 B | 38,769 B | 128 | yes |
| hybrid ML-DSA-65 | 5,363 B | 5,468 B | 10,867 B | 54,059 B | 92 | yes |

Observations:
- ML-DSA-44 input is ~38× the legacy 97-byte witness; hybrid adds only ~97 B
  (the ECDSA half) on top of the PQ witness.
- Throughput at 1 MB blocks drops ~23× (2,985 → ~128 two-input tx) for hybrid
  ML-DSA-44 — the dominant cost is block space, not (per §3) verify time.
- Even a 256-inputs-worth workload stays bounded because a single tx is capped at
  100 kB (`MAX_TX_BYTES_CONSENSUS`, `consensus_constants.h:15`); a 10-input hybrid
  tx (~38.8 kB) is the practical large case.

---

## 3. Timings — RESULTS_PENDING_COMPUTE_ENV

| Metric | ML-DSA-44 | ML-DSA-65 | Hybrid overhead |
|---|---|---|---|
| Keygen (µs) | PENDING | PENDING | + ECDSA keygen (~µs) |
| Sign (µs) | PENDING | PENDING | + one ECDSA sign |
| Verify (µs) | PENDING | PENDING | + one ECDSA verify (~50–100 µs) |
| Verify on low-end VPS (µs) | PENDING | PENDING | — |
| Verify on desktop (µs) | PENDING | PENDING | — |

`PENDING` = `RESULTS_PENDING_COMPUTE_ENV`. These are **not** guessed. Published
literature suggests ML-DSA verify is on the order of ECDSA verify (tens–low
hundreds of µs) and sign somewhat higher, but SOST will publish **only measured**
numbers from §4 before recommending verify-work weights or a candidate set.

---

## 4. How to fill the timing cells (exact commands)

On both a low-end VPS and a normal desktop:

```bash
# 1. Build liboqs (research library — NOT audited for production)
git clone --depth 1 https://github.com/open-quantum-safe/liboqs
cmake -S liboqs -B liboqs/build -DBUILD_SHARED_LIBS=ON \
      -DOQS_MINIMAL_BUILD="SIG_ml_dsa_44;SIG_ml_dsa_65;KEM_ml_kem_768"
cmake --build liboqs/build --parallel
sudo cmake --install liboqs/build && sudo ldconfig

# 2. Python bindings
python3 -m pip install liboqs-python     # provides `import oqs`

# 3. Measure (median + p95 over 200 iters)
python3 scripts/pq_bench/pq_bench.py --iters 200
python3 scripts/pq_bench/pq_bench.py --iters 200 --json > pq_bench_$(hostname).json
```

The harness auto-detects `oqs`; the `RESULTS_PENDING_COMPUTE_ENV` cells become
measured `sign_us_median` / `verify_us_median` / p95 for `ML-DSA-44` and
`ML-DSA-65` on the machine it runs on. Record both machines' JSON here.

---

## 5. Candidate recommendation

**Deferred until §3/§4 timings are measured** (per task: recommend a candidate
*only* after measured results). Size-only, the leading candidate is
**HYBRID_ECDSA_ML_DSA_44** (`alg_id 0x10`): NIST L2, smallest PQ witness
(3.83 kB/input), defence-in-depth during transition, all tx sizes well under the
100 kB tx cap. Final selection also weighs measured verify time (DoS budget) and
whether L3 (ML-DSA-65) is warranted for high-value outputs. No selection is
binding and none activates anything.

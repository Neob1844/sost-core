# SOST PQ V3 — benchmark harness (research only, off-consensus)

`pq_bench_v3.py` measures the cost and transaction-size impact of post-quantum
signatures for the SOST PQ migration research. It is **not** part of the node or
miner build, touches no consensus code, no keys, and no chain state.

Two kinds of output:

1. **Transaction size impact** — always emitted. Computed exactly from the
   published FIPS 204 parameter sets and the current SOST consensus limits
   (`MAX_TX_BYTES_CONSENSUS = 100000`, `MAX_BLOCK_BYTES_CONSENSUS = 1000000`,
   `MAX_INPUTS_CONSENSUS = 256` — `include/sost/consensus_constants.h:15-17`).
2. **Timings** (keygen / sign / verify) — measured **only** if the python `oqs`
   binding to liboqs is installed on the machine running the script. If absent,
   every timing cell is the literal `RESULTS_PENDING_COMPUTE_ENV`. The harness
   **never fabricates a timing.**

## Environment status (verified 2026-07-02)

The node/miner **build** environment ships **no** PQ library. For research only,
an **indicative** run was produced in an **isolated venv** (`liboqs 0.15.0` +
`liboqs-python`, never global, not in the build) —
`results/measured_2026-07-02_i9-10885H_wsl2.json`. Those ML-DSA timings are
**order-of-magnitude only** (WSL2, turbo NOT pinned); ECDSA baseline / SLH-DSA
stay `RESULTS_PENDING_COMPUTE_ENV` / N/A. The size math is complete regardless.

Note: the harness resolves mechanism names by alias (final FIPS name first, e.g.
`ML-DSA-44`, then the legacy `Dilithium2`) — modern liboqs (≥ 0.10) enables the
final names only, so the legacy-only lookup used previously would have missed a
valid install.

## Run

```
python3 scripts/pq_bench/pq_bench_v3.py                                  # print
python3 scripts/pq_bench/pq_bench_v3.py --iters 200                      # more iters
python3 scripts/pq_bench/pq_bench_v3.py --json scripts/pq_bench/results/run.json
```

Output validates against `scripts/pq_bench/results/schema.json`.
A sample (timings pending) is at `scripts/pq_bench/results/sample_run.json`.

## To obtain measured timings

```
git clone --depth 1 https://github.com/open-quantum-safe/liboqs
cmake -S liboqs -B liboqs/build -DBUILD_SHARED_LIBS=ON
cmake --build liboqs/build --parallel
pip install liboqs-python
python3 scripts/pq_bench/pq_bench_v3.py --iters 500 --json results/measured.json
```

## Provenance requirement

No timing number may be published anywhere (docs, whitepaper, marketing) without
**all** of: hardware/OS, compiler/interpreter, CPU model, library + version,
iteration count, mean/median/p95/stddev, date, and git commit. The JSON schema
enforces the presence of the provenance block; reviewers must reject any timing
lacking it. See `docs/PQ_BENCHMARK_RESULTS_V3.md`.

## Size-impact summary (exact, from FIPS 204)

| config | per-input bytes | max inputs/tx (bytes / effective) | single-input txs/block |
|--------|-----------------|-----------------------------------|------------------------|
| LEGACY ECDSA | 138 | 724 / 256 | 7246 |
| ML-DSA-44 | 3773 | 26 / 26 | 265 |
| ML-DSA-65 | 5302 | 18 / 18 | 188 |
| HYBRID ECDSA+ML-DSA-44 | 3874 | 25 / 25 | 258 |

(Per-input bytes here include the prototype witness envelope: 36-byte outpoint +
1-byte alg_id + 2-byte length prefixes. The current mainnet fixed layout is 133
bytes/input at `src/tx_validation.cpp:77`. PQ inputs are ~27x larger — no weight
discount is assumed; see `docs/PQ_PERFORMANCE_MODEL_V3.md`.)

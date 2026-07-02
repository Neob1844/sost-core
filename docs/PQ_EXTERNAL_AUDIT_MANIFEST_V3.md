# SOST Post-Quantum Migration — External Audit Manifest (V3)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> Reproducibility and integrity manifest for the V3 external-audit hand-off. It lists every relevant
> artefact with its SHA-256, the exact commit baselines, and the exact commands to reproduce the
> tests and benchmarks. It **links** to the source documents (single source of truth) and does not
> duplicate their content. Read `docs/PQ_EXTERNAL_AUDIT_BRIEF_V3.md` first and
> `docs/PQ_EXTERNAL_AUDITOR_QUESTIONS_V3.md` for the questions.

---

## 1. Commit baselines

| Ref | SHA | Meaning |
|-----|-----|---------|
| `origin/main` (baseline) | `682fd82092df1b22e89c5b204fcc8475702e8a74` | Mainnet baseline; **no PQ code**. |
| PR #38 branch tip before hand-off | `a5186643e439ba1dd4af5a1d27c478aaeb7eb733` | V2→V3 consolidation commit; the SHA-256 table in §7 was computed against this tree. |
| PR #38 hand-off commit | *(this docs-only commit)* | Adds `PQ_EXTERNAL_AUDIT_BRIEF_V3.md`, `PQ_EXTERNAL_AUDITOR_QUESTIONS_V3.md`, `PQ_EXTERNAL_AUDIT_MANIFEST_V3.md` on top of `a5186643`; changes nothing else. |
| PR #37 (superseded) | `3d214355a02c25436ae885a5e5b16c31448b2900` | V2, **CLOSED not merged**, branch `draft/pq-migration-v2` preserved. |

Branch: `draft/pq-migration-v3-docsync` (PR #38, **DRAFT**). `PQ_ACTIVATION_HEIGHT = INT64_MAX`.

## 2. Relevant documents (single source of truth)

- Master index: `docs/PQ_MIGRATION_V3.md`
- Witness / tx format: `docs/PQ_TX_FORMAT_V3.md`
- Threat model: `docs/PQ_THREAT_MODEL_V3.md`
- Security assumptions: `docs/PQ_SECURITY_ASSUMPTIONS_V3.md`
- Wallet / fund migration: `docs/PQ_WALLET_MIGRATION_V3.md`
- Activation & governance: `docs/PQ_ACTIVATION_PLAN_V3.md`
- Performance & size / verify-work model: `docs/PQ_PERFORMANCE_MODEL_V3.md`
- Benchmark results: `docs/PQ_BENCHMARK_RESULTS_V3.md`
- Testnet plan: `docs/PQ_TESTNET_PLAN_V3.md`
- Pre-activation audit checklist: `docs/PQ_AUDIT_CHECKLIST_V3.md`
- Decision log: `docs/PQ_DECISION_LOG_V3.md`
- V2→V3 consolidation review: `docs/PQ_V3_CONSOLIDATION_REVIEW.md`
- Prior research note (2026-04): `docs/QUANTUM_RESISTANCE_RESEARCH.md`
- This hand-off: `docs/PQ_EXTERNAL_AUDIT_BRIEF_V3.md`, `docs/PQ_EXTERNAL_AUDITOR_QUESTIONS_V3.md`,
  `docs/PQ_EXTERNAL_AUDIT_MANIFEST_V3.md`
- Whitepaper-as-code tree: `docs/whitepaper/00..12` + `docs/WHITEPAPER_MANIFEST.md`

## 3. ADRs

`docs/ADR/ADR-001-crypto-agility.md`, `ADR-002-hybrid-not-or.md`,
`ADR-003-variable-length-witness.md`, `ADR-004-pq-library-isolation.md`,
`ADR-005-no-mainnet-activation-yet.md`, `ADR-006-whitepaper-as-code.md`,
`ADR-007-wallet-migration-strategy.md`.

## 4. Prototype (NOT compiled, not in CMake, `#include`d by no consensus unit)

- `prototype/pq/pq_alg_registry.h` — 1-byte `alg_id` registry, exact sizes, domain tags, sentinel.
- `prototype/pq/pq_witness.h` — deterministic single-pass witness parser/serializer.
- `prototype/pq/pq_validate.h` — conceptual LEGACY/PQ/HYBRID verify (hybrid AND).
- `prototype/pq/README.md`.

## 5. Test vectors, fuzz target, benchmark scripts, raw results

- Unit + negative vectors: `tests/pq_vectors/test_pq_witness.cpp` (21 checks).
- Fuzz target (libFuzzer): `tests/pq_vectors/fuzz_pq_witness.cpp`.
- Test README: `tests/pq_vectors/README.md`.
- Machine-readable witness vectors: `docs/examples/pq/witness_vectors.json`.
- Benchmark harness: `scripts/pq_bench/pq_bench_v3.py`, `scripts/pq_bench/README.md`.
- Result schema: `scripts/pq_bench/results/schema.json`.
- Sample (illustrative) result: `scripts/pq_bench/results/sample_run.json`.
- **Raw measured result (indicative):** `scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json`.
- Anti-false-claim / sync tooling: `scripts/check_crypto_claims.py`, `scripts/check_whitepaper_sync.py`.

## 6. Internal package-audit results (this hand-off)

| Check | Result |
|-------|--------|
| `tests/pq_vectors/test_pq_witness.cpp` | **21/21 PASS** (exit 0) |
| `fuzz_pq_witness.cpp` smoke (clang libFuzzer + ASan/UBSan, ~25 s) | **~11.06M execs, 0 crashes / 0 leaks / 0 UB** |
| `scripts/check_crypto_claims.py` | **OK** (no dangerous crypto claims) |
| `scripts/check_whitepaper_sync.py --base origin/main` | **OK** |
| `docs/examples/pq/witness_vectors.json` | valid JSON |
| `measured_*.json` + `sample_run.json` vs `schema.json` (jsonschema) | **SCHEMA-OK** (both) |
| Internal-link validation (PQ docs/ADRs/whitepaper) | **0 broken same-branch links** (references to `docs/PQ_MIGRATION_V2.md` and other V2-only files resolve on PR #37's branch by design) |
| Duplicate-doc check (byte-identical bodies) | **none** |
| `pq_bench_v3.py` size math | reproduced published size table |
| Live ML-DSA timing re-run | **NOT_RUN** in this session (no `oqs` venv present); committed `measured_*.json` is the 2026-07-02 indicative run |
| FIPS 204 ACVP known-answer vectors | **NOT_RUN** (not available in-repo; audit-scope) |
| Authoritative clock-pinned timings / ECDSA baseline / HYBRID / memory / p99 | **RESULTS_PENDING_COMPUTE_ENV** |

## 7. SHA-256 of critical files (computed at tree `a5186643`)

```
6da8e3f48441fa92c074a29d05b8ab1b5b91ade411af98d3ee748f44b1313b44  docs/PQ_MIGRATION_V3.md
a5804b66914a6b5c905b772a1db6983718f329d75f43920c8d70f84e777f6705  docs/PQ_TX_FORMAT_V3.md
21d8a367434ac050d810ef42e0065648733866f71455549bb937a4a210fa05fa  docs/PQ_THREAT_MODEL_V3.md
3d067cab74216eb57b393e36e9ab9467c87fcf3d939c130a3278e792da6e0298  docs/PQ_SECURITY_ASSUMPTIONS_V3.md
808e64919c45a2ee21e64bbba56a6f113ff91a8a57f7cf27c4959fa80a1df1fe  docs/PQ_WALLET_MIGRATION_V3.md
28823cc80c2979365307de108d0283fe46dd864ec72f9d617ce69f3cf727d3ac  docs/PQ_ACTIVATION_PLAN_V3.md
68df70d7cadb23eccfc49363907a3c3e1bc26eb268e2b75f6bef47f44c73383f  docs/PQ_PERFORMANCE_MODEL_V3.md
b336eb9369ba48ef415093aea8227507d1bb7ab13daf30069b3650a2a09b4ff0  docs/PQ_BENCHMARK_RESULTS_V3.md
d441d78af14f95bb826416182fb43f68bb9090bb1a301e29ae51763f45836698  docs/PQ_TESTNET_PLAN_V3.md
b3eacf42713a73fcfdf43302fbb68b87e084d122e2ddd305e42f508a928d506f  docs/PQ_AUDIT_CHECKLIST_V3.md
e601dfc4cef42d80e730a861d7af4dcd550fded131212bdac51a60390c8e9939  docs/PQ_DECISION_LOG_V3.md
aa54729059b52bd9836cbeeb99e524a0f4a8352c369cce23babc20e1a31c0aff  docs/PQ_V3_CONSOLIDATION_REVIEW.md
842628b5448aa9f052e00497bd06f8a537d2dce2459d2993940606977a9d1e51  docs/PQ_EXTERNAL_AUDIT_BRIEF_V3.md
3d3266a069a1a922c5a0522b690b3a836bb36365a5a31512f00f69a9fed8567e  docs/PQ_EXTERNAL_AUDITOR_QUESTIONS_V3.md
2ef73277ec2f1d7fc1219af950be1a3efb84b50ec43cb258888c2d0ba79cc448  docs/ADR/ADR-001-crypto-agility.md
66717ef6983452955bbdefbd9b4fc22f22560d29a2b6a49bda69db4a8c527129  docs/ADR/ADR-002-hybrid-not-or.md
2ea8cfe483b212d3c89910479eead70bb4fb93414557146a57ea7b6d61fcb3ff  docs/ADR/ADR-003-variable-length-witness.md
bf601982be6f91ef48dc986f2f92414cad09b0e287ca76c7de5f0e6b7705b619  docs/ADR/ADR-004-pq-library-isolation.md
439fce757c9a750ff09f2357e01e9b4b2f90d8d2b010c8502731c05c899af136  docs/ADR/ADR-005-no-mainnet-activation-yet.md
5020dc985f84136c62528b6b01cebc5c0b969fa243c14c190d5f9ace32050ae1  docs/ADR/ADR-006-whitepaper-as-code.md
c3d8fc9260c96f4c445e2f4a39ecdf8088070dd2a19c0b61264832df2f9cf10a  docs/ADR/ADR-007-wallet-migration-strategy.md
e1aeee52d7a1f433b583d97e5a68b4b214247bce3125a3678c995f64f50c3314  prototype/pq/pq_alg_registry.h
5430161684157dd1634d18da427a12cfb81dc6be04fd3608610dc84ba3376c3c  prototype/pq/pq_witness.h
1ae15c06a243ceae43d8d503f92cebff26496c2f2cf62c5427f125162c8a80aa  prototype/pq/pq_validate.h
51774ec23b54e132f567e77a1bc219c77610a7981154029a42f315c7f1971603  prototype/pq/README.md
3af0b65f0f6c16f7a3d141a4326d977aaab5de584e9f46886735e8afa546fd70  tests/pq_vectors/test_pq_witness.cpp
f49af5eafbe7877a0fb39a1101d68d608df4074e5c7d290384e78de7834597ab  tests/pq_vectors/fuzz_pq_witness.cpp
75117923c3c6bfa1b97c45ae73dd9fdb75273352301afbcaf3c1ea4f7525b890  tests/pq_vectors/README.md
566dab6ab0ac740f9b838e4c5f99191d55c450358d4dd805b4580ff35654b8ff  docs/examples/pq/witness_vectors.json
b52c343e5f708690f216845f1dd33026dfe22c93bdebeddf1bc99274ecabbb71  scripts/pq_bench/pq_bench_v3.py
e873c40d505f6a4f25f2bbc91d9fb497bcc3fd068d8cbfd04653712b298a58ad  scripts/pq_bench/README.md
13e13d770e7429e4c9e59d54b5754f8b5edfde0b5731e8b53391a96beafbb036  scripts/pq_bench/results/schema.json
f662e860e739384d55b3686ce30497399720d00f54d4600b277b0f09c900763c  scripts/pq_bench/results/sample_run.json
7565169de35aa01f336ea2ea3ba79d270f1998e6a64c34240135916af4757598  scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json
1f80a4568ff74a7910fdbe981193f2ac7154e34c50c7be026ecde71e31c040b0  scripts/check_crypto_claims.py
5c8b700c406972154da8ec8f83db348832ebf621c4413ddb70765bec304e485c  scripts/check_whitepaper_sync.py
```

To re-verify after checkout of the branch tip `a5186643`:
```
git fetch origin
git checkout a5186643e439ba1dd4af5a1d27c478aaeb7eb733
sha256sum -c <(sed -n '/^```$/,/^```$/p' docs/PQ_EXTERNAL_AUDIT_MANIFEST_V3.md | grep -E '^[0-9a-f]{64}  ')
```
(The hand-off commit adds only the three `PQ_EXTERNAL_AUDIT_*_V3.md` docs on top of `a5186643`; all
hashes above remain valid at the hand-off commit.)

## 8. Reproduce the tests

Prototype unit + negative vectors (std-lib only; not in CMake/ctest):
```
c++ -std=c++17 -Wall -Wextra -I prototype/pq tests/pq_vectors/test_pq_witness.cpp -o /tmp/test_pq_witness
/tmp/test_pq_witness            # expect: pass=21 fail=0 ; exit 0
```

Fuzz smoke (requires clang + libFuzzer; skip if unavailable):
```
clang++ -std=c++17 -g -O1 -fsanitize=fuzzer,address,undefined \
    -I prototype/pq tests/pq_vectors/fuzz_pq_witness.cpp -o /tmp/fuzz_pq
/tmp/fuzz_pq -max_total_time=25   # expect: 0 crashes / 0 leaks / 0 UB
```

Anti-claim + whitepaper sync + JSON validation:
```
python3 scripts/check_crypto_claims.py
python3 scripts/check_whitepaper_sync.py --base origin/main
python3 -c "import json; json.load(open('docs/examples/pq/witness_vectors.json'))"
python3 - <<'PY'
import json, jsonschema
s = json.load(open('scripts/pq_bench/results/schema.json'))
for f in ('scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json',
          'scripts/pq_bench/results/sample_run.json'):
    jsonschema.validate(json.load(open(f)), s)
print("SCHEMA-OK")
PY
```

## 9. Reproduce the benchmarks

Size math (no PQ library needed; exact from FIPS 204 + current serialization):
```
python3 scripts/pq_bench/pq_bench_v3.py --iters 5      # prints the size-impact table
```

Indicative ML-DSA timings (research only — **isolated venv**, never global, never in the node build):
```
python3 -m venv /tmp/pqvenv && . /tmp/pqvenv/bin/activate
pip install liboqs-python==0.15.0            # builds liboqs 0.15.0 under ~/_oqs on first import
python3 scripts/pq_bench/pq_bench_v3.py --iters 10000 --json /tmp/pqrun.json
deactivate
```
Record every provenance field required by `docs/PQ_BENCHMARK_RESULTS_V3.md §1` before publishing any
number. The committed indicative run is `scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json`
(turbo/clock NOT pinned → order-of-magnitude only). An **authoritative** run additionally requires a
**clock-pinned bare-metal** host, a warm-up loop, an **ECDSA secp256k1 baseline**, the full **HYBRID**
cost, **peak memory**, and **p99** — all currently `RESULTS_PENDING_COMPUTE_ENV`.

## 10. Paths explicitly EXCLUDED from the build (must remain unbuilt)

The following are **research artefacts** and are deliberately **not** in any `CMakeLists.txt` / `cmake/`
target, and are `#include`d by no consensus/wallet/mempool/block translation unit. The mainnet
node/miner build is byte-identical with or without them:

- `prototype/pq/**`
- `tests/pq_vectors/**`
- `scripts/pq_bench/**`
- `scripts/check_crypto_claims.py`, `scripts/check_whitepaper_sync.py`
- `docs/**` (all PQ docs, ADRs, whitepaper, examples)

Protected mainnet paths with **empty** diff vs `origin/main` (verified): `src/`, `include/`,
`genesis_block.json`, `CMakeLists.txt`, `cmake/`, `config/`. No `liboqs`/`oqs` dependency is added to
the node. `PQ_ACTIVATION_HEIGHT = INT64_MAX`.

---

*Author: NeoB. Research/architecture only — activates nothing. No audit has been performed.*

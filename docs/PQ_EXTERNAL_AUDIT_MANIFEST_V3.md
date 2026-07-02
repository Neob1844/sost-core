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

- Research archive entry point (master index): `docs/PQ_RESEARCH_INDEX_V3.md`
- Architecture master document: `docs/PQ_MIGRATION_V3.md`
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
- Prior research note (pre-V3, historical): `docs/QUANTUM_RESISTANCE_RESEARCH.md`

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

- Unit + negative vectors: `tests/pq_vectors/test_pq_witness.cpp` (33 checks).
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
| `tests/pq_vectors/test_pq_witness.cpp` | **33/33 PASS** (exit 0) |
| `fuzz_pq_witness.cpp` smoke (clang libFuzzer + ASan/UBSan, ~20 s) | **~8.8M execs, 0 crashes / 0 leaks / 0 UB** |
| `scripts/check_crypto_claims.py` | **OK** (no dangerous crypto claims) |
| `scripts/check_whitepaper_sync.py` | **OK** |
| `docs/examples/pq/witness_vectors.json` | valid JSON |
| `measured_*.json` + `sample_run.json` + `schema.json` (json parse) | valid (all) |
| Internal-link validation (PQ docs/ADRs/whitepaper, 40 md files) | **0 broken same-branch links** (references to `docs/PQ_MIGRATION_V2.md` and other V2-only files resolve on PR #37's branch by design) |
| Duplicate-doc check (byte-identical bodies) | **none** |
| Duplicate-ADR check (repeated ADR number) | **none** |
| Manifest SHA-256 table (`sha256sum -c`, 52 files) | **all OK** |
| `pq_bench_v3.py` size math | reproduced published size table |
| Live ML-DSA timing re-run | **NOT_RUN** in this session (no `oqs` venv present); committed `measured_*.json` is the 2026-07-02 indicative run |
| FIPS 204 ACVP known-answer vectors | **NOT_RUN** (not available in-repo; audit-scope) |
| Authoritative clock-pinned timings / ECDSA baseline / HYBRID / memory / p99 | **RESULTS_PENDING_COMPUTE_ENV** |

## 7. Complete PQ file inventory (every PQ file on the branch)

Classification: `normative` = proposed spec/decision text; `informative` = context /
status / index; `prototype` = non-compiled prototype, tests, harness; `result` =
data/vectors/schema. `In-build` = referenced by any `CMakeLists.txt`/`cmake/`
target or `#include`d by a node/miner translation unit (all **no**). This manifest
file itself (`docs/PQ_EXTERNAL_AUDIT_MANIFEST_V3.md`) is informative / not-in-build
and cannot list its own hash; every other PQ file is below.

| # | Path | Purpose | Classification | In-build | SHA-256 |
|---|------|---------|----------------|----------|---------|
| 1 | `docs/PQ_RESEARCH_INDEX_V3.md` | Master index / single entry point | informative | no | `efe0b9cee489fe9057fda754dd49d22c059d1e4113d559e46c7c6b28aba0ac72` |
| 2 | `docs/PQ_MIGRATION_V3.md` | Top-level architecture + migration surface | normative | no | `6da8e3f48441fa92c074a29d05b8ab1b5b91ade411af98d3ee748f44b1313b44` |
| 3 | `docs/PQ_TX_FORMAT_V3.md` | Witness / tx wire format (BE16) | normative | no | `803e8ae25467471a0a8c2fdc1d3c056b1af4308dcf783a4dcc56163ec7bdc2a0` |
| 4 | `docs/PQ_THREAT_MODEL_V3.md` | Threat model | informative | no | `21d8a367434ac050d810ef42e0065648733866f71455549bb937a4a210fa05fa` |
| 5 | `docs/PQ_SECURITY_ASSUMPTIONS_V3.md` | Security assumptions | informative | no | `3d067cab74216eb57b393e36e9ab9467c87fcf3d939c130a3278e792da6e0298` |
| 6 | `docs/PQ_PERFORMANCE_MODEL_V3.md` | Size / weight / verify-work model | informative | no | `5ce77f1ef3a469ec14dbb5aa79f26b7f79859659cd6b8d6ae81e73d7ec6f0446` |
| 7 | `docs/PQ_DECISION_LOG_V3.md` | Decision log D1-D8 | informative | no | `613c5e4c2d5c76d719ee6e760b05179f5e3fc512f52198857987f9ec1432f301` |
| 8 | `docs/PQ_V3_CONSOLIDATION_REVIEW.md` | V2->V3 consolidation review | informative | no | `aa54729059b52bd9836cbeeb99e524a0f4a8352c369cce23babc20e1a31c0aff` |
| 9 | `docs/PQ_WALLET_MIGRATION_V3.md` | Wallet / fund migration (opt-in) | normative | no | `808e64919c45a2ee21e64bbba56a6f113ff91a8a57f7cf27c4959fa80a1df1fe` |
| 10 | `docs/PQ_ACTIVATION_PLAN_V3.md` | Conditional phases A-H (no dates/heights) | normative | no | `28823cc80c2979365307de108d0283fe46dd864ec72f9d617ce69f3cf727d3ac` |
| 11 | `docs/PQ_TESTNET_PLAN_V3.md` | Private-testnet plan (OFF by default) | informative | no | `d441d78af14f95bb826416182fb43f68bb9090bb1a301e29ae51763f45836698` |
| 12 | `docs/PQ_AUDIT_CHECKLIST_V3.md` | Pre-activation audit checklist | informative | no | `01272ac1fd172b4ead486a5c0d14e29512843bfa6bb801424307e8fedda06d04` |
| 13 | `docs/PQ_EXTERNAL_AUDIT_BRIEF_V3.md` | External-audit brief (no audit exists) | informative | no | `7869f7c7d4d4c2535ba618695e506ce74e29fa5a430b96b8e830aa95755f75cc` |
| 14 | `docs/PQ_EXTERNAL_AUDITOR_QUESTIONS_V3.md` | Questions for reviewers | informative | no | `c828c2f478558987e5eafd364e7b4d8ff28bdf54be0a7f7abaea2aaef21b6d46` |
| 15 | `docs/PQ_BENCHMARK_RESULTS_V3.md` | Benchmark results + provenance rules | informative | no | `fc2b6f8e901b3dc6b5b1a13100bc81fe79c1ab62256e4993a93ca03bedd87aad` |
| 16 | `docs/QUANTUM_RESISTANCE_RESEARCH.md` | Pre-V3 research note (historical; also on main) | informative | no | `c54d0e850a39454ce77a6eb647e7fc4e37ea5b13229fbd9c72a0c982b62cdbf9` |
| 17 | `docs/WHITEPAPER_MANIFEST.md` | Whitepaper-as-code manifest | informative | no | `3db55977625f804488e50f025af6eb065cd76759252c7d3ee4fbb977295b3f02` |
| 18 | `docs/whitepaper/00-status.md` | Internal whitepaper: status | informative | no | `64952011791a660b994c1b8f5a696c447c4eca13f9637c94132b96e6a3204ede` |
| 19 | `docs/whitepaper/01-protocol-overview.md` | Internal whitepaper: overview | informative | no | `353f01df0d14b4cc2808b53890d64e585eb35309abe37a9ba2defc4245180316` |
| 20 | `docs/whitepaper/02-consensus.md` | Internal whitepaper: consensus | informative | no | `cc0a65ceaf70f0652b97e79db1cad7254c6bcd89352be8e493aeef78f8973c2c` |
| 21 | `docs/whitepaper/03-transactions-and-signatures.md` | Internal whitepaper: tx & signatures | informative | no | `58f95899ebeac08437e01f8345f027e8ca1eb415e4f25fb48ea3118ab37def4b` |
| 22 | `docs/whitepaper/04-sbpow.md` | Internal whitepaper: SbPoW | informative | no | `faaea180fc6d8af543bfda6b28bc11a07ac0de9213b5400329953c762c512545` |
| 23 | `docs/whitepaper/05-security-model.md` | Internal whitepaper: security model | informative | no | `1333d44354532c3f3b1da26c37c6c7e6f4a25567d567518847873ef08df02488` |
| 24 | `docs/whitepaper/06-post-quantum-roadmap.md` | Internal whitepaper: PQ roadmap | informative | no | `02397fc22b6709761c28f2e853317ef1662ae294dad3b7a11f18d10c1bed89a6` |
| 25 | `docs/whitepaper/07-wallet-migration.md` | Internal whitepaper: wallet migration | informative | no | `17196c28eaae73a56ba63a2dfe68da506da34ae8fe7938ad1814c84090029350` |
| 26 | `docs/whitepaper/08-activation-and-governance.md` | Internal whitepaper: activation & governance | informative | no | `78f62bb153e367dfb053dd5108e5f0dafc7019d7b6c7229c0ef33af580fc449e` |
| 27 | `docs/whitepaper/09-performance-and-limits.md` | Internal whitepaper: performance & limits | informative | no | `3889410c5f108896fd45c4f99aa4cfe5164d1fb45d8d0fe933f413d1faca7a73` |
| 28 | `docs/whitepaper/10-known-limitations.md` | Internal whitepaper: known limitations | informative | no | `bd20bd7114af58ae7c72d365d5846774847d300c20cac7fab4522f21c2a190bc` |
| 29 | `docs/whitepaper/11-glossary.md` | Internal whitepaper: glossary | informative | no | `02e0229683478a17da8a42b24030f09af1f37212dacf3115ea34e1e1d84feba9` |
| 30 | `docs/whitepaper/12-changelog.md` | Internal whitepaper: changelog | informative | no | `82455b9ea75a2df9393b852f2d1537bd768b4eeb68768a46506146ee8e1e897d` |
| 31 | `docs/ADR/ADR-001-crypto-agility.md` | ADR: crypto-agility | normative | no | `2ef73277ec2f1d7fc1219af950be1a3efb84b50ec43cb258888c2d0ba79cc448` |
| 32 | `docs/ADR/ADR-002-hybrid-not-or.md` | ADR: hybrid = AND | normative | no | `66717ef6983452955bbdefbd9b4fc22f22560d29a2b6a49bda69db4a8c527129` |
| 33 | `docs/ADR/ADR-003-variable-length-witness.md` | ADR: variable-length witness (BE16) | normative | no | `2bb58ed1e3350990b6619cf8f2b983b7381fafd4f0c60dc42bfb03a002428293` |
| 34 | `docs/ADR/ADR-004-pq-library-isolation.md` | ADR: PQ library isolation | normative | no | `bf601982be6f91ef48dc986f2f92414cad09b0e287ca76c7de5f0e6b7705b619` |
| 35 | `docs/ADR/ADR-005-no-mainnet-activation-yet.md` | ADR: no mainnet activation yet | normative | no | `439fce757c9a750ff09f2357e01e9b4b2f90d8d2b010c8502731c05c899af136` |
| 36 | `docs/ADR/ADR-006-whitepaper-as-code.md` | ADR: whitepaper-as-code | normative | no | `5020dc985f84136c62528b6b01cebc5c0b969fa243c14c190d5f9ace32050ae1` |
| 37 | `docs/ADR/ADR-007-wallet-migration-strategy.md` | ADR: wallet migration strategy | normative | no | `c3d8fc9260c96f4c445e2f4a39ecdf8088070dd2a19c0b61264832df2f9cf10a` |
| 38 | `prototype/pq/pq_alg_registry.h` | Prototype: alg_id registry | prototype | no | `e1aeee52d7a1f433b583d97e5a68b4b214247bce3125a3678c995f64f50c3314` |
| 39 | `prototype/pq/pq_witness.h` | Prototype: witness parser/serializer | prototype | no | `5430161684157dd1634d18da427a12cfb81dc6be04fd3608610dc84ba3376c3c` |
| 40 | `prototype/pq/pq_validate.h` | Prototype: LEGACY/PQ/HYBRID verify (AND) | prototype | no | `1ae15c06a243ceae43d8d503f92cebff26496c2f2cf62c5427f125162c8a80aa` |
| 41 | `prototype/pq/README.md` | Prototype: README | prototype | no | `51774ec23b54e132f567e77a1bc219c77610a7981154029a42f315c7f1971603` |
| 42 | `tests/pq_vectors/test_pq_witness.cpp` | Standalone unit + negative tests | prototype | no | `85f53ad6f79e639fa14ce7b1cf2de7eae78d81a23436a11f5ebc6902971612fc` |
| 43 | `tests/pq_vectors/fuzz_pq_witness.cpp` | libFuzzer parser target | prototype | no | `f49af5eafbe7877a0fb39a1101d68d608df4074e5c7d290384e78de7834597ab` |
| 44 | `tests/pq_vectors/README.md` | Tests README | prototype | no | `75117923c3c6bfa1b97c45ae73dd9fdb75273352301afbcaf3c1ea4f7525b890` |
| 45 | `docs/examples/pq/witness_vectors.json` | Machine-readable valid/invalid vectors | result | no | `3269deebbdc94868924d00970b0404945b6c62193ee3cc3d266ae0fccc75b272` |
| 46 | `scripts/pq_bench/pq_bench_v3.py` | Benchmark harness (size math + timings) | prototype | no | `b52c343e5f708690f216845f1dd33026dfe22c93bdebeddf1bc99274ecabbb71` |
| 47 | `scripts/pq_bench/README.md` | Benchmark README | prototype | no | `e873c40d505f6a4f25f2bbc91d9fb497bcc3fd068d8cbfd04653712b298a58ad` |
| 48 | `scripts/pq_bench/results/schema.json` | Benchmark result schema | result | no | `13e13d770e7429e4c9e59d54b5754f8b5edfde0b5731e8b53391a96beafbb036` |
| 49 | `scripts/pq_bench/results/sample_run.json` | Sample result (timings pending) | result | no | `f662e860e739384d55b3686ce30497399720d00f54d4600b277b0f09c900763c` |
| 50 | `scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json` | Indicative measured run | result | no | `7565169de35aa01f336ea2ea3ba79d270f1998e6a64c34240135916af4757598` |
| 51 | `scripts/check_crypto_claims.py` | Anti-false-claim linter | prototype | no | `1f80a4568ff74a7910fdbe981193f2ac7154e34c50c7be026ecde71e31c040b0` |
| 52 | `scripts/check_whitepaper_sync.py` | Whitepaper-sync linter | prototype | no | `5c8b700c406972154da8ec8f83db348832ebf621c4413ddb70765bec304e485c` |

### 7.1 Canonical `sha256sum -c` integrity list

The same 52 hashes as `<sha256>  <path>` lines for machine verification:

```
efe0b9cee489fe9057fda754dd49d22c059d1e4113d559e46c7c6b28aba0ac72  docs/PQ_RESEARCH_INDEX_V3.md
6da8e3f48441fa92c074a29d05b8ab1b5b91ade411af98d3ee748f44b1313b44  docs/PQ_MIGRATION_V3.md
803e8ae25467471a0a8c2fdc1d3c056b1af4308dcf783a4dcc56163ec7bdc2a0  docs/PQ_TX_FORMAT_V3.md
21d8a367434ac050d810ef42e0065648733866f71455549bb937a4a210fa05fa  docs/PQ_THREAT_MODEL_V3.md
3d067cab74216eb57b393e36e9ab9467c87fcf3d939c130a3278e792da6e0298  docs/PQ_SECURITY_ASSUMPTIONS_V3.md
5ce77f1ef3a469ec14dbb5aa79f26b7f79859659cd6b8d6ae81e73d7ec6f0446  docs/PQ_PERFORMANCE_MODEL_V3.md
613c5e4c2d5c76d719ee6e760b05179f5e3fc512f52198857987f9ec1432f301  docs/PQ_DECISION_LOG_V3.md
aa54729059b52bd9836cbeeb99e524a0f4a8352c369cce23babc20e1a31c0aff  docs/PQ_V3_CONSOLIDATION_REVIEW.md
808e64919c45a2ee21e64bbba56a6f113ff91a8a57f7cf27c4959fa80a1df1fe  docs/PQ_WALLET_MIGRATION_V3.md
28823cc80c2979365307de108d0283fe46dd864ec72f9d617ce69f3cf727d3ac  docs/PQ_ACTIVATION_PLAN_V3.md
d441d78af14f95bb826416182fb43f68bb9090bb1a301e29ae51763f45836698  docs/PQ_TESTNET_PLAN_V3.md
01272ac1fd172b4ead486a5c0d14e29512843bfa6bb801424307e8fedda06d04  docs/PQ_AUDIT_CHECKLIST_V3.md
7869f7c7d4d4c2535ba618695e506ce74e29fa5a430b96b8e830aa95755f75cc  docs/PQ_EXTERNAL_AUDIT_BRIEF_V3.md
c828c2f478558987e5eafd364e7b4d8ff28bdf54be0a7f7abaea2aaef21b6d46  docs/PQ_EXTERNAL_AUDITOR_QUESTIONS_V3.md
fc2b6f8e901b3dc6b5b1a13100bc81fe79c1ab62256e4993a93ca03bedd87aad  docs/PQ_BENCHMARK_RESULTS_V3.md
c54d0e850a39454ce77a6eb647e7fc4e37ea5b13229fbd9c72a0c982b62cdbf9  docs/QUANTUM_RESISTANCE_RESEARCH.md
3db55977625f804488e50f025af6eb065cd76759252c7d3ee4fbb977295b3f02  docs/WHITEPAPER_MANIFEST.md
64952011791a660b994c1b8f5a696c447c4eca13f9637c94132b96e6a3204ede  docs/whitepaper/00-status.md
353f01df0d14b4cc2808b53890d64e585eb35309abe37a9ba2defc4245180316  docs/whitepaper/01-protocol-overview.md
cc0a65ceaf70f0652b97e79db1cad7254c6bcd89352be8e493aeef78f8973c2c  docs/whitepaper/02-consensus.md
58f95899ebeac08437e01f8345f027e8ca1eb415e4f25fb48ea3118ab37def4b  docs/whitepaper/03-transactions-and-signatures.md
faaea180fc6d8af543bfda6b28bc11a07ac0de9213b5400329953c762c512545  docs/whitepaper/04-sbpow.md
1333d44354532c3f3b1da26c37c6c7e6f4a25567d567518847873ef08df02488  docs/whitepaper/05-security-model.md
02397fc22b6709761c28f2e853317ef1662ae294dad3b7a11f18d10c1bed89a6  docs/whitepaper/06-post-quantum-roadmap.md
17196c28eaae73a56ba63a2dfe68da506da34ae8fe7938ad1814c84090029350  docs/whitepaper/07-wallet-migration.md
78f62bb153e367dfb053dd5108e5f0dafc7019d7b6c7229c0ef33af580fc449e  docs/whitepaper/08-activation-and-governance.md
3889410c5f108896fd45c4f99aa4cfe5164d1fb45d8d0fe933f413d1faca7a73  docs/whitepaper/09-performance-and-limits.md
bd20bd7114af58ae7c72d365d5846774847d300c20cac7fab4522f21c2a190bc  docs/whitepaper/10-known-limitations.md
02e0229683478a17da8a42b24030f09af1f37212dacf3115ea34e1e1d84feba9  docs/whitepaper/11-glossary.md
82455b9ea75a2df9393b852f2d1537bd768b4eeb68768a46506146ee8e1e897d  docs/whitepaper/12-changelog.md
2ef73277ec2f1d7fc1219af950be1a3efb84b50ec43cb258888c2d0ba79cc448  docs/ADR/ADR-001-crypto-agility.md
66717ef6983452955bbdefbd9b4fc22f22560d29a2b6a49bda69db4a8c527129  docs/ADR/ADR-002-hybrid-not-or.md
2bb58ed1e3350990b6619cf8f2b983b7381fafd4f0c60dc42bfb03a002428293  docs/ADR/ADR-003-variable-length-witness.md
bf601982be6f91ef48dc986f2f92414cad09b0e287ca76c7de5f0e6b7705b619  docs/ADR/ADR-004-pq-library-isolation.md
439fce757c9a750ff09f2357e01e9b4b2f90d8d2b010c8502731c05c899af136  docs/ADR/ADR-005-no-mainnet-activation-yet.md
5020dc985f84136c62528b6b01cebc5c0b969fa243c14c190d5f9ace32050ae1  docs/ADR/ADR-006-whitepaper-as-code.md
c3d8fc9260c96f4c445e2f4a39ecdf8088070dd2a19c0b61264832df2f9cf10a  docs/ADR/ADR-007-wallet-migration-strategy.md
e1aeee52d7a1f433b583d97e5a68b4b214247bce3125a3678c995f64f50c3314  prototype/pq/pq_alg_registry.h
5430161684157dd1634d18da427a12cfb81dc6be04fd3608610dc84ba3376c3c  prototype/pq/pq_witness.h
1ae15c06a243ceae43d8d503f92cebff26496c2f2cf62c5427f125162c8a80aa  prototype/pq/pq_validate.h
51774ec23b54e132f567e77a1bc219c77610a7981154029a42f315c7f1971603  prototype/pq/README.md
85f53ad6f79e639fa14ce7b1cf2de7eae78d81a23436a11f5ebc6902971612fc  tests/pq_vectors/test_pq_witness.cpp
f49af5eafbe7877a0fb39a1101d68d608df4074e5c7d290384e78de7834597ab  tests/pq_vectors/fuzz_pq_witness.cpp
75117923c3c6bfa1b97c45ae73dd9fdb75273352301afbcaf3c1ea4f7525b890  tests/pq_vectors/README.md
3269deebbdc94868924d00970b0404945b6c62193ee3cc3d266ae0fccc75b272  docs/examples/pq/witness_vectors.json
b52c343e5f708690f216845f1dd33026dfe22c93bdebeddf1bc99274ecabbb71  scripts/pq_bench/pq_bench_v3.py
e873c40d505f6a4f25f2bbc91d9fb497bcc3fd068d8cbfd04653712b298a58ad  scripts/pq_bench/README.md
13e13d770e7429e4c9e59d54b5754f8b5edfde0b5731e8b53391a96beafbb036  scripts/pq_bench/results/schema.json
f662e860e739384d55b3686ce30497399720d00f54d4600b277b0f09c900763c  scripts/pq_bench/results/sample_run.json
7565169de35aa01f336ea2ea3ba79d270f1998e6a64c34240135916af4757598  scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json
1f80a4568ff74a7910fdbe981193f2ac7154e34c50c7be026ecde71e31c040b0  scripts/check_crypto_claims.py
5c8b700c406972154da8ec8f83db348832ebf621c4413ddb70765bec304e485c  scripts/check_whitepaper_sync.py
```

To re-verify after checkout of the branch tip:
```
git fetch origin
git checkout draft/pq-migration-v3-docsync
sha256sum -c <(sed -n '/^```$/,/^```$/p' docs/PQ_EXTERNAL_AUDIT_MANIFEST_V3.md | grep -E '^[0-9a-f]{64}  ')
```
(Hashes cover every PQ file on the branch except this manifest itself. Changing any listed
file changes its hash here; the list is docs/prototype/tests/scripts/vectors only and touches
no `src/`, `include/`, build, or consensus file.)

## 8. Reproduce the tests

Prototype unit + negative vectors (std-lib only; not in CMake/ctest):
```
c++ -std=c++17 -Wall -Wextra -I prototype/pq tests/pq_vectors/test_pq_witness.cpp -o /tmp/test_pq_witness
/tmp/test_pq_witness            # expect: pass=33 fail=0 ; exit 0
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
- `docs/**` (all PQ docs, ADRs, whitepaper, examples, master index)

Protected mainnet paths with **empty** diff vs `origin/main` (verified): `src/`, `include/`,
`genesis_block.json`, `CMakeLists.txt`, `cmake/`, `config/`. No `liboqs`/`oqs` dependency is added to
the node. `PQ_ACTIVATION_HEIGHT = INT64_MAX`.

---

*Author: NeoB. Research/architecture only — activates nothing. No audit has been performed.*

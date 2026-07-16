# PQ Migration — V3 Consolidation Review (PR #38 vs PR #37)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

This review consolidates the SOST post-quantum research into **V3** (PR #38,
branch `draft/pq-migration-v3-docsync`) and records how it relates to **V2**
(PR #37, branch `draft/pq-migration-v2`). No new PR was created; V2 is left
intact for history. Nothing here activates PQ, merges, deploys, or changes
consensus. Author: NeoB.

---

## 1. Initial state (verified at consolidation time)

- `origin/main` = `682fd820` (clean).
- PR #38 = `draft/pq-migration-v3-docsync` @ `831a662c` — OPEN, **draft**.
- PR #37 = `draft/pq-migration-v2` @ `3d214355` — OPEN, **draft**.
- Two pre-existing stashes (`pq-migration-v2` WIP, `popc-bond-dashboard` WIP) —
  left untouched.
- Work was done in an **isolated git worktree** off the PR #38 branch; the main
  checkout was not edited.
- Protected paths (`src/`, `include/`, `genesis_block.json`, `CMakeLists.txt`,
  `cmake/`, `config/`) had **0** diff vs `origin/main` before and after this work.

## 2. Full #37 (V2) vs #38 (V3) comparison matrix

Legend: **=** equivalent · **V3+** better in V3 · **V2+** better/only in V2 (port
candidate) · **conflict** resolved.

| Content / decision | In #37 (V2) | In #38 (V3) | Verdict | Action |
|---|---|---|---|---|
| Threat model | 1 doc, 4 adversaries | 1 doc, 22 numbered threats + table | V3+ | keep V3 |
| Tx / witness format | prose + compactsize varint framing | prose + prototype + fixed 2-byte length prefix, "no trailing bytes" | V3+ | keep V3 |
| Algorithm registry | `0x00/01/02/10/11` | reassigned `0x00/01/02` + `0x03/04/10` reserved + `0xFF` | conflict → V3 documents reassignment; safe (INT64_MAX) | keep V3 |
| Canonical serialization | compactsize | fixed 2-byte BE, exact-length, single-pass | V3+ | keep V3 |
| Domain separation | `SHA256d(tag‖alg_id‖preimage)` | per-scheme string tags `SOST/pq-v3/…` in prototype | V3+ | keep V3 |
| LEGACY / PQ_ML_DSA / HYBRID | yes | yes | = | — |
| HYBRID = ECDSA **AND** ML-DSA | yes (conjunctive) | yes (conjunctive, ADR-002, enforced+tested) | V3+ | keep V3 |
| Unknown-alg rejection | deterministic reject | deterministic reject + reserved/INVALID classes | V3+ | keep V3 |
| Max sizes | FIPS-exact | FIPS-exact + full limit inventory | V3+ | keep V3 |
| Verify-work budget | **explicit per-tx budget mechanism** | mentioned as "cheap checks first" only | V2+ | **PORTED → `PQ_PERFORMANCE_MODEL_V3.md §4.4`** |
| DoS protection | oversize + verify flood | 4 DoS classes (bloat/CPU/memory/split) | V3+ (plus port above) | keep V3 |
| Wallet migration | §6 (sost2/sost2h, HD domain sep, no PQ key in localStorage) | full `PQ_WALLET_MIGRATION_V3.md` + ADR-007 | V3+ | keep V3 |
| Backup / recovery | §6 | dedicated doc §3/§6/§9 | V3+ | keep V3 |
| Testnet | mentions | full `PQ_TESTNET_PLAN_V3.md` + build flag | V3+ | keep V3 |
| Activation plan | light | `PQ_ACTIVATION_PLAN_V3.md` + phases A–J | V3+ | keep V3 |
| Benchmarks | `pq_bench.py`, results doc | `pq_bench_v3.py` + schema + sample + results skeleton | V3+ | keep V3 |
| Test vectors | design matrix only | `tests/pq_vectors/` (21 tests) + JSON vectors | V3+ | keep V3 |
| Fuzzing | mentioned | `fuzz_pq_witness.cpp` libFuzzer target | V3+ | keep V3 |
| Whitepaper docs | none | `docs/whitepaper/00..12` + manifest | V3+ | keep V3 |
| Anti-false-claim scripts | none | `check_crypto_claims.py` + `check_whitepaper_sync.py` | V3+ | keep V3 |
| Migration-surface inventory | **§1.1 full field table (multisig/RPC/wallet/address/SbPoW)** | only primary sites cited | V2+ | **PORTED → `PQ_MIGRATION_V3.md §1.1`** |
| Transport / P2P KEM (ML-KEM-768) | **§5/§6/§7, A1 adversary** | out of scope (signatures only) | V2+ | **PORTED (scoped) → `PQ_THREAT_MODEL_V3.md §12`, index `PQ_MIGRATION_V3.md §1.2`** |
| Terminology map (Dilithium→ML-DSA …) | §7 table | glossary entries (`whitepaper/11`) | = | keep V3 (glossary already covers) |
| POPC on-chain-collateral doc | present on V2 branch | absent | off-topic (not PQ) | **discarded — not PQ content** |

## 3. Content ported from #37 into #38

1. **Full migration-surface inventory** → `docs/PQ_MIGRATION_V3.md §1.1`. Every
   fixed-size key/signature/hash field (TxInput sig/pubkey, TxOutput pkh, type
   aliases, multisig `PubKey`/`Sig64`, wallet key material, RPC pubkey/address
   fields, `sost1` address, SbPoW `MinerPubkey`) with **re-verified** current
   `file:line` citations and the consensus size limits that bound any witness.
2. **Verify-work budget** (candidate per-tx weighted verify-cost DoS bound,
   calibrated from measured timings, checked before verification) →
   `docs/PQ_PERFORMANCE_MODEL_V3.md §4.4`, cross-referenced from
   `docs/PQ_THREAT_MODEL_V3.md §6.2`.
3. **Transport-channel (KEM) track** (A1 harvest-now-decrypt-later on the P2P
   channel; hybrid X25519 + ML-KEM-768 direction with transcript-bound downgrade
   protection) → `docs/PQ_THREAT_MODEL_V3.md §12`, indexed at
   `docs/PQ_MIGRATION_V3.md §1.2`, explicitly marked **secondary / out of the
   signature-activation scope**, single source of truth (no duplication).

4. **Benchmark-harness mechanism-name alias fallback** (from V2's `pq_bench.py`
   `OQS_ALIASES`) → `scripts/pq_bench/pq_bench_v3.py`. Without it, `pq_bench_v3.py`
   found no mechanism on liboqs 0.15.0 (final `ML-DSA-*` names only) and reported
   `MECH_NOT_ENABLED`; the V2 harness would have measured. Also added
   verify-invalid timing + a correctness assertion (forged sig must be rejected)
   and min/max stats. Schema (`results/schema.json`) updated to match.

Each port was adapted to the V3 architecture (V3 alg-id map, V3 doc structure)
and placed once. No V2 file was copied wholesale into V3.

## 4. Content discarded (and why)

- **V2 alg-id numbering** (`0x02`=ML-DSA-65, `0x10/0x11`=hybrids): superseded by
  the V3 reassignment; keeping both would be a conflict. Safe because
  `PQ_ACTIVATION_HEIGHT == INT64_MAX` in both — no id is used by consensus.
- **`docs/POPC_BOND_V2_ONCHAIN_COLLATERAL.md` / `POPC_IMPLEMENTATION_STATUS.md`**
  (present on the V2 branch): not post-quantum content; out of scope for this
  consolidation. Left where they belong (their own workstream), not imported.
- **V2 duplicate size tables / benchmark prose**: superseded by
  `PQ_PERFORMANCE_MODEL_V3.md` + `PQ_BENCHMARK_RESULTS_V3.md`; not re-imported to
  avoid two sources of truth.

## 5. Benchmark environment

- OS/kernel: `Linux 5.15.167.4-microsoft-standard-WSL2 x86_64` (glibc 2.35).
- Python: `3.10.12`. Compilers present: `clang 14.0.0`, `gcc`, `cmake`.
- Tested branch SHA at run: `831a662c` (+ the doc edits in this consolidation).
- CPU: Intel Core i9-10885H @ 2.40 GHz, 14 logical cores, 23 GiB RAM — **turbo /
  clock NOT pinned** (WSL2), so timings are indicative, not authoritative.
- Date (UTC): 2026-07-02.
- PQ library: `liboqs 0.15.0` + `liboqs-python 0.15.0` installed in an **isolated
  venv** (`/tmp/claude-1001/pqvenv`, never global, not in the node build). Import
  builds liboqs to `~/_oqs`; ML-DSA-44/65/87 enabled under **final FIPS names**
  ("Dilithium*" not enabled).

## 6. Benchmarks run

- **Size math (exact, from FIPS 204):** `scripts/pq_bench/pq_bench_v3.py --iters 50`
  ran successfully and reproduced the published size table (see §7). This is
  computed-from-constants, not measured timing.
- **Timing (ML-DSA, indicative):** `pq_bench_v3.py --iters 10000 --json` ran with
  a working `oqs` in the isolated venv, measuring ML-DSA-44/65/87 keygen / sign /
  verify-valid / verify-invalid (§7). During the harness fix (below) it also
  **asserted correctness**: every valid signature verified and every bit-flipped
  signature was rejected. Numbers are **order-of-magnitude only** (turbo unpinned).
- **Harness fix (ported from V2):** `pq_bench_v3.py` previously looked up only the
  legacy `Dilithium2/3/5` mechanism names and returned `MECH_NOT_ENABLED` on
  liboqs 0.15.0 (which enables `ML-DSA-44/65/87`). Added V2's alias fallback
  (final name → legacy) plus verify-invalid measurement and min/max stats.

## 7. Raw results (size math — reproduced this run)

```
config                      per_input_B  in/tx(bytes)  in/tx(eff)  1in-tx/block
LEGACY_ECDSA                        138           724         256          7246
PQ_ML_DSA_44                       3773            26          26           265
PQ_ML_DSA_65                       5302            18          18           188
HYBRID_ECDSA_ML_DSA_44             3874            25          25           258
```

(`in/tx(eff)` = `min(byte-budget, MAX_INPUTS_CONSENSUS=256)`; block figures by
byte budget, also capped by `MAX_BLOCK_TX_COUNT=4096`.) These match
`docs/PQ_PERFORMANCE_MODEL_V3.md §3` and `docs/PQ_BENCHMARK_RESULTS_V3.md §4`.

Indicative measured timings (µs, median; WSL2 turbo-unpinned; n=10000;
liboqs 0.15.0; raw JSON `scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json`):

| scheme | keygen | sign | verify-valid | verify-invalid |
|---|---|---|---|---|
| ML-DSA-44 | 26.7 | 53.2 | 24.7 | 24.0 |
| ML-DSA-65 | 43.2 | 86.5 | 40.2 | 39.2 |
| ML-DSA-87 | 67.0 | 111.5 | 62.8 | 61.4 |

Derived (median-based, single-thread): ML-DSA-44 ≈ 40.5k verifies/s, 18.8k
signs/s. Full mean/p95/stddev in `docs/PQ_BENCHMARK_RESULTS_V3.md §3`.

## 8. Pending results

- **Authoritative** timings on a **clock-pinned** host (turbo disabled, warm-up);
  ECDSA secp256k1 **baseline**; HYBRID (ECDSA + ML-DSA-44) combined cost; **peak
  memory** per verify; **p99**: all `RESULTS_PENDING_COMPUTE_ENV`. The §7 numbers
  are indicative only and must not be used to set the verify-work-budget weights
  (`docs/PQ_PERFORMANCE_MODEL_V3.md §4.4`).
- SLH-DSA timings: **N/A** until a validated SLH-DSA implementation is available
  (reserve option only, not part of the selection).

## 9. Tests run

- Prototype unit + negative vectors: `tests/pq_vectors/test_pq_witness.cpp`
  compiled with `c++ -std=c++17` → **21/21 PASS** (round-trip for
  LEGACY/PQ/HYBRID; negatives: empty, unknown alg-id, reserved ids, `0xFF`,
  truncated prefix, wrong length, oversized length, trailing bytes, mis-ordered/
  duplicated hybrid halves; hybrid AND both-directions; per-scheme domain tags).
- Fuzz smoke: `fuzz_pq_witness.cpp` built with
  `clang++ -fsanitize=fuzzer,address,undefined` → **~12.36M execs in 31 s, 0
  crashes / 0 leaks / 0 UB**.
- `scripts/check_crypto_claims.py` → **OK** (no dangerous crypto claims).
- `scripts/check_whitepaper_sync.py --base origin/main` → **OK**.
- JSON vectors `docs/examples/pq/witness_vectors.json` → valid JSON, parsed.
- `scripts/pq_bench/pq_bench_v3.py` → ran (size math §7; ML-DSA timings §7/§8).
- Benchmark result JSON validated against `scripts/pq_bench/results/schema.json`
  (both the measured run and `sample_run.json`) with `jsonschema`.
- ML-DSA correctness (via harness asserts): valid signatures verified, bit-flipped
  signatures rejected, for ML-DSA-44/65/87 across 10000 iters each.

## 10. Tests not run

- **Authoritative** (clock-pinned) timings, ECDSA baseline, HYBRID cost, memory,
  p99 — `RESULTS_PENDING_COMPUTE_ENV` (the §7 run is indicative only).
- FIPS ACVP known-answer vectors for ML-DSA — not run (self-consistency
  verify-valid/verify-invalid only was checked).
- Project C++ ctest suite — **not applicable** to this docs/prototype PR (no
  consensus code changed; prototype is not in CMake). Not run here.
- Extended (multi-hour) fuzzing / coverage-guided corpus growth — only a 31 s
  smoke run was performed.

## 11. Estimated tx / block impact (computed from real constants)

Per-input size grows from **133 B** (legacy) to ~**3773 B** (ML-DSA-44, ~28×),
~**5302 B** (ML-DSA-65, ~40×), ~**3874 B** (hybrid, ~29×). Under
`MAX_TX_BYTES_CONSENSUS=100000`: ~26 / ~18 / ~25 inputs respectively (vs the 256
input cap binding first for legacy). Under `MAX_BLOCK_BYTES_CONSENSUS=1000000`:
~265 / ~188 / ~258 single-input PQ txs per block (vs the 4096 tx-count cap for
legacy). **These are computed from FIPS sizes + current serialization, not
measured.** Verify CPU cost per block is `RESULTS_PENDING_COMPUTE_ENV`.

## 12. Security risks (research-level, no activation)

- New variable-length witness = new parser attack surface (ambiguous parse,
  over/under-read, unknown-id split) — mitigated in the prototype (strict
  single-pass, exact-length, reject-by-default) and fuzz-smoked, but **not
  audited**.
- Hybrid must be **AND** (both verify); OR would be only as strong as the weaker
  half.
- ML-DSA/SLH-DSA library immaturity, side channels, RNG dependence — all **open,
  audit-scope** (`PQ_THREAT_MODEL_V3.md §8`, `PQ_AUDIT_CHECKLIST_V3.md`).
- A mis-compiled verifier can split the network (the `-DSOST_ENABLE_PHASE2_SBPOW`
  precedent) — PQ ships gated OFF, behind a build flag, KAT- and audit-gated
  before any height.

## 13. Performance risks

- ~28–40× per-input bloat cuts effective spend throughput per block; no witness
  weight discount is proposed (bytes count at true size).
- ML-DSA verify CPU cost is higher than ECDSA (magnitude **pending measurement**);
  the candidate verify-work budget (§4.4 of the perf model) is the intended bound
  but its weights are un-calibrated until timings exist.
- Memory: variable-length parsing must never allocate on an unvalidated length
  (enforced in the prototype).

## 14. Wallet / recovery risks

- An ECDSA seed does **not** yield an ML-DSA key; PQ keys need a separate
  derivation path (KDF **unspecified / open** — `PQ_WALLET_MIGRATION_V3.md §3`).
  Until fixed, treat PQ keys as independently-backed; a pre-PQ backup contains no
  PQ keys.
- Migration is **opt-in**, never auto (a migration spend reveals the pubkey and
  opens a front-running window).
- Hardware wallets / custodians / multisig face large-key constraints and
  mixed-class hazards; all documented, none solved by protocol alone.
- `sost2` prefix is **provisional placeholder only**, not final.

## 15. Provisional algorithm recommendation (NOT a final choice)

Provisional, size/compat-driven, **pending measured verify timings**:
**HYBRID_ECDSA_ML_DSA_44 (`0x02`)** as the conservative transition default —
NIST L2, smallest PQ witness (~3874 B/input), defence-in-depth (must break both
ECDSA and ML-DSA), all sizes well under the 100 kB tx cap; with **ML-DSA-65**
reserved for high-value outputs. SLH-DSA is held only as a hash-based **reserve**,
not part of the selection. Final selection requires measured verify time (DoS
budget) and external review. No selection is binding and none activates anything.

## 16. Decisions needing an external auditor

- Constant-time, audited ML-DSA (and reserve SLH-DSA) implementation choice.
- Final alg-id assignment, witness canonicalisation, and domain-tag scheme.
- Verify-work-budget weights + any standardness/limit changes (consensus).
- PQ key-derivation KDF and unified backup scheme.
- Downgrade-binding of output-class → required spend scheme.
- Activation mechanism / version-signalling / minimum-node-version policy.
No audit has been performed at V3.

## 17. Consensus-intact confirmation

`git diff origin/main` over `src/`, `include/`, `genesis_block.json`,
`CMakeLists.txt`, `cmake/`, `config/` = **EMPTY**. No change to consensus,
active validation/serialization, params, heights, PoW / ConvergenceX / SbPoW /
DTD / supply / genesis. `prototype/pq/` and `scripts/pq_bench/` are **not** in any
CMake list; no `liboqs`/`oqs` dependency in the build. `PQ_ACTIVATION_HEIGHT =
INT64_MAX` (never active).

## 18. No-merge / no-deploy confirmation

No merge, no deploy, no mainnet action, no new PR, no V4, no PQ activation, no new
activation height. PR #38 stays **draft**; PR #37 is **not** modified or closed.

## 19. Exact next steps

1. Keep PR #38 draft; do not merge.
2. On a **clock-pinned bare-metal** host (turbo disabled, warm-up), re-run
   `python scripts/pq_bench/pq_bench_v3.py --iters 10000 --json results/<host>.json`
   plus an ECDSA baseline + HYBRID + memory instrumentation, and replace the §7
   *indicative* numbers in `docs/PQ_BENCHMARK_RESULTS_V3.md §2.2/§3` with
   authoritative ones (full provenance row). The indicative WSL2 run is already in
   `results/measured_2026-07-02_i9-10885H_wsl2.json`.
3. Commission an **external cryptographic + code review** against
   `docs/PQ_AUDIT_CHECKLIST_V3.md`.
4. Stand up the **isolated experimental testnet** (`docs/PQ_TESTNET_PLAN_V3.md`,
   `SOST_EXPERIMENTAL_PQ_TESTNET_ONLY`, default OFF) — **not mainnet**.
5. Separately (comment-only, not this PR): reword the inert
   `include/sost/proposals.h:44` "SPHINCS+/Dilithium" placeholder to ML-DSA.
6. Post the "superseded by #38" note on PR #37; close it only on explicit
   operator authorisation (no information is lost — everything useful is ported).

*Author: NeoB. Research/architecture only — activates nothing.*

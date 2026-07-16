# PQ Performance & Size / Cost Model — V3 (RESEARCH / DOCS ONLY)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> **Two kinds of numbers.** Sizes below are **known** from FIPS 204 and from the current SOST
> serialization, and are computed honestly. All **timing / CPU / memory** numbers are
> **`RESULTS_PENDING_COMPUTE_ENV`** — `liboqs`/`python-oqs` is **not available** in this build
> environment (verified), so no measured performance figure is stated. See §5 for how to obtain
> them and `docs/PQ_BENCHMARK_RESULTS_V3.md` for the results skeleton. Supersedes the sizing
> discussion in `docs/PQ_MIGRATION_V2.md` (PR #37).

---

## 1. Known cryptographic sizes (bytes)

From published FIPS 204 (ML-DSA); ECDSA from current SOST:

| Scheme                         | NIST level | Signature | Public key |
|--------------------------------|------------|-----------|------------|
| ECDSA secp256k1 (today)        | —          | 64        | 33         |
| ML-DSA-44                      | L2         | 2420      | 1312       |
| ML-DSA-65                      | L3         | 3309      | 1952       |
| ML-DSA-87 (reserved)           | L5         | 4627      | 2592       |
| SLH-DSA (FIPS 205)             | varies     | parameter-set dependent | parameter-set dependent |

SLH-DSA sizes are parameter-set dependent (e.g. SLH-DSA-SHA2-128s: public key 32, signature 7856)
and are **not** pinned to a single number here.

---

## 2. Current per-input size (verified)

Today's serialized per-input size is **133 bytes** (`src/tx_validation.cpp:77`):

```
prev_txid(32) + prev_index(4) + signature(64) + pubkey(33) = 133
```

The 64-byte signature and 33-byte pubkey are a **fixed** layout with **no length prefix**
(`include/sost/transaction.h:72-73`; `src/transaction.cpp:210-225`). PQ therefore requires a
**new versioned, variable-length witness** (tx version 2, **PROVISIONAL** —
`include/sost/transaction.h:109`).

---

## 3. Modelled per-input size under the versioned PQ witness

The outpoint (`prev_txid 32 + prev_index 4 = 36`) is unchanged. The variable witness carries a
1-byte `alg_id`, then each signature and public key component is emitted as a **fixed 2-byte
big-endian (BE16) length prefix** followed by the component bytes. Every length occupies **exactly
2 bytes** — there is **no `CompactSize`, no varint, and no short/long form**. This is the canonical
encoding fixed in `docs/PQ_TX_FORMAT_V3.md` and `prototype/pq/pq_witness.h`. **These envelope/overhead
bytes model a proposed format, not a shipped wire format.**

| Class (alg_id)              | Outpoint | alg_id | sig len+sig            | pk len+pk             | **Per-input** |
|-----------------------------|----------|--------|------------------------|-----------------------|---------------|
| LEGACY (0x00) — today, no envelope | 36 | —      | 64 (fixed)             | 33 (fixed)            | **133**       |
| LEGACY under envelope (0x00)| 36       | 1      | 2 + 64                 | 2 + 33                | **138**       |
| ML-DSA-44 (0x01)            | 36       | 1      | 2 + 2420               | 2 + 1312              | **3773**      |
| ML-DSA-65 (0x03 rsv.)       | 36       | 1      | 2 + 3309               | 2 + 1952              | **5302**      |
| ML-DSA-87 (0x04 rsv.)       | 36       | 1      | 2 + 4627               | 2 + 2592              | **7260**      |
| HYBRID (0x02)               | 36       | 1      | (2+64) + (2+2420)      | (2+33) + (2+1312)     | **3874**      |

HYBRID = ECDSA **AND** ML-DSA-44 (AND semantics): it carries **both** key/sig pairs. Explicit
arithmetic: `36 + 1 + [2+64] + [2+33] + [2+2420] + [2+1312] = 3874 bytes` (ECDSA sig 64 + pk 33,
ML-DSA-44 sig 2420 + pk 1312, each with a 2-byte BE length prefix).

**Takeaway:** a PQ input is roughly **28×** a legacy input (ML-DSA-44), ML-DSA-65 roughly **40×**,
ML-DSA-87 roughly **55×**, and HYBRID roughly **29×**. A PQ transaction of the *same input count* is
far larger than its legacy equivalent.

---

## 4. Impact against consensus limits

Consensus limits (verified):
- `MAX_TX_BYTES_CONSENSUS = 100000` (`include/sost/consensus_constants.h:15`)
- `MAX_BLOCK_BYTES_CONSENSUS = 1000000` (`include/sost/consensus_constants.h:16`)
- `MAX_INPUTS_CONSENSUS = 256` (`include/sost/consensus_constants.h:17`)
- `MAX_TX_BYTES_STANDARD = 16000` (`include/sost/tx_validation.h:26`)
- `MAX_BLOCK_TXS_CONSENSUS = 65536` (`include/sost/block_validation.h:37`)
- `MAX_BLOCK_TX_COUNT = 4096` (`include/sost/mempool.h:22`)

### 4.1 Inputs that fit in one transaction (`MAX_TX_BYTES_CONSENSUS = 100000`)
Theoretical maxima **by byte budget only** (integer division of the budget by per-input size).
These **exclude** the tx header, outputs and all other fields, which reduce the count further; the
`MAX_INPUTS_CONSENSUS = 256` cap and per-tx limits may bind earlier. **These are not proposed
consensus parameters.** Per-input sizes use the envelope model of §3 (LEGACY-under-envelope = 138).

| Class        | ~Inputs by byte budget (100000 / per-input) | Also capped by MAX_INPUTS_CONSENSUS |
|--------------|---------------------------------------------|-------------------------------------|
| LEGACY 138   | 724                                         | **256** (input cap binds first)     |
| ML-DSA-44    | 26                                          | 26 (byte budget binds first)        |
| ML-DSA-65    | 18                                          | 18 (byte budget binds first)        |
| ML-DSA-87    | 13                                          | 13 (byte budget binds first)        |
| HYBRID       | 25                                          | 25 (byte budget binds first)        |

For a **standard** tx (`MAX_TX_BYTES_STANDARD = 16000`, byte budget only): LEGACY ≈ 115 inputs;
ML-DSA-44 ≈ 4; ML-DSA-65 ≈ 3; ML-DSA-87 ≈ 2; HYBRID ≈ 4. PQ transactions hit the standard limit
very quickly.

### 4.2 Single-input transactions that fit in one block (`MAX_BLOCK_BYTES_CONSENSUS = 1000000`)
Theoretical single-input-tx equivalents **by byte budget only** (integer division; excludes headers,
outputs and other fields); also bounded by `MAX_BLOCK_TX_COUNT = 4096`. **Not proposed consensus
parameters.** Per-input sizes use the envelope model of §3 (LEGACY-under-envelope = 138).

| Class        | ~Single-input txs by byte budget (1000000 / per-input) |
|--------------|--------------------------------------------------------|
| LEGACY 138   | 7246 (block tx-count cap 4096 binds first)             |
| ML-DSA-44    | 265                                                    |
| ML-DSA-65    | 188                                                    |
| ML-DSA-87    | 137                                                    |
| HYBRID       | 258                                                    |

**Interpretation:** the same block that holds thousands of legacy single-input spends holds only a
few hundred PQ ones. Byte-for-byte, PQ meaningfully reduces effective per-block spend throughput.

### 4.3 Weight / limit position (explicit)
- A PQ transaction of the same input count is **far larger** and would require a deliberate
  **weight/limit review** before activation (Phase D in the migration plan).
- **There is NO unjustified weight discount for PQ.** PQ witness bytes are large because the
  cryptography is large; they must be counted at their true size unless a rigorously-justified,
  separately-audited weighting is adopted. This document proposes none.

---

### 4.4 Verify-work budget (candidate DoS bound — carried over from V2)

Byte-size limits alone do not bound **verification CPU**: ML-DSA verify is more
expensive than ECDSA verify, and a transaction can pack many inputs. The V2
iteration (PR #37) proposed an explicit **per-transaction verify-work budget** —
a weighted sum of per-input verification costs (ECDSA = weight 1; each PQ / hybrid
`alg_id` a weight `> 1`) checked **before any signature is verified**, so an
attacker cannot force a node to run hundreds of maximum-cost verifications by
submitting a single oversized transaction. V3 records this as a **candidate**
consensus-level DoS bound, complementary to the "cheapest checks first" ordering
in `docs/PQ_THREAT_MODEL_V3.md §6.2`:

- The per-`alg_id` weights are **not asserted** here — they must be **calibrated
  from measured verify timings** (§5 / `docs/PQ_BENCHMARK_RESULTS_V3.md`), which
  are `RESULTS_PENDING_COMPUTE_ENV`. No weight is invented.
- Any actual budget constant is itself a **consensus change** and is therefore
  **out of scope for this research PR**; it would be set only by a future,
  separately-audited activation proposal (`docs/PQ_ACTIVATION_PLAN_V3.md`).
- Ordering: reject on `alg_id` / size / encoding (cheap) first; only then spend
  verify budget. This bounds the worst case to the budget, not to `MAX_INPUTS`.

## 5. Timing / CPU / memory

No timing figure is published **in this model doc**. **Indicative** ML-DSA-44/65/87 keygen/sign/
verify medians (WSL2, turbo NOT pinned, n=10000, liboqs 0.15.0 in an isolated venv) now exist in
`docs/PQ_BENCHMARK_RESULTS_V3.md §3` and `scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json`
— they are order-of-magnitude only. The **authoritative** figures needed to size the §4.4
verify-work budget (clock-pinned host, ECDSA baseline, HYBRID, memory, p99) remain
**`RESULTS_PENDING_COMPUTE_ENV`**. No performance number is used to set any consensus value in this PR.

### 5.1 Reproducible instructions to obtain the numbers
Run in a valid compute environment (see `scripts/pq_bench/` and record every field into
`docs/PQ_BENCHMARK_RESULTS_V3.md`):

1. **Library + version:** `liboqs` (record exact release/commit) and/or NIST reference
   implementation (record source + commit). Note the ML-DSA parameter sets built.
2. **Compiler + flags:** exact compiler and version (e.g. the project toolchain), optimisation
   flags (`-O2`/`-O3`), architecture flags actually used (e.g. AVX2 on/off), and whether the
   constant-time reference or an optimised path is measured.
3. **Hardware + OS:** CPU model, core count, fixed clock / turbo state, RAM, OS + kernel version.
4. **Measurement:** iterations (e.g. ≥ 10,000 per operation), warm-up runs, and report
   **mean, median, p95/p99, and stddev** for `keygen`, `sign`, `verify` per scheme
   (ECDSA baseline, ML-DSA-44, ML-DSA-65, HYBRID = ECDSA+ML-DSA-44). SLH-DSA only if the env is
   valid, else mark **N/A**.
5. **Provenance:** date of run and the exact repo commit hash.

Until every field above is filled from a real run, tables in `docs/PQ_BENCHMARK_RESULTS_V3.md`
remain `RESULTS_PENDING_COMPUTE_ENV`.

---

*Author: NeoB. Sizes are computed from FIPS 204 + current serialization; all timings pending a
valid compute environment. Activates nothing.*

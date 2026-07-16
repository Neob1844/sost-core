# 09 — Performance and Consensus Limits

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

Detailed modelling lives in `docs/PQ_PERFORMANCE_MODEL_V3.md`.

## Current consensus size limits (with file:line)

| Limit | Value | Source |
| --- | --- | --- |
| `MAX_TX_BYTES_CONSENSUS` | 100,000 | `include/sost/consensus_constants.h:15` |
| `MAX_BLOCK_BYTES_CONSENSUS` | 1,000,000 | `include/sost/consensus_constants.h:16` |
| `MAX_TX_BYTES_STANDARD` | 16,000 | `include/sost/tx_validation.h:26` |
| `MAX_BLOCK_TXS_CONSENSUS` | 65,536 | `include/sost/block_validation.h:37` |
| `MAX_BLOCK_TX_COUNT` | 4,096 | `include/sost/mempool.h:22` |
| Per-input serialized size (today) | 133 bytes | `src/tx_validation.cpp:77` |

Today's 133-byte input = `prev_txid(32) + prev_index(4) + signature(64) + pubkey(33)`.

## Signature/key sizes (FIPS 204 — do not alter)

| Scheme | Signature (bytes) | Public key (bytes) |
| --- | --- | --- |
| ECDSA secp256k1 (today) | 64 | 33 (compressed) |
| ML-DSA-44 (NIST L2) | 2,420 | 1,312 |
| ML-DSA-65 (NIST L3) | 3,309 | 1,952 |
| ML-DSA-87 (NIST L5) | 4,627 | 2,592 |
| SLH-DSA (FIPS 205) | parameter-set dependent | parameter-set dependent |

SLH-DSA sizes vary widely by parameter set (e.g. SLH-DSA-SHA2-128s: 32-byte public key, 7,856-byte
signature); do not pin a single number without naming the exact parameter set.

## Tx-size impact of ML-DSA (arithmetic on published sizes only)

A single ML-DSA-44 witness contributes roughly `2420 + 1312 = 3,732` bytes of signature+key material
per input, versus `64 + 33 = 97` bytes today — about a **38x** increase in the signature/key portion
of an input. A HYBRID (`0x02`) input carries **both** an ECDSA and an ML-DSA-44 witness, so it is
larger still (roughly `97 + 3732` bytes of signature/key material). These figures are direct
arithmetic on the FIPS 204 sizes above; they are **not** measured serialized transaction sizes and
do not account for envelope framing in the provisional versioned witness.

Implication: even a modest number of ML-DSA inputs consumes the current per-transaction budgets far
faster than ECDSA inputs. Whether limits would need revisiting is an open modelling question for
`docs/PQ_PERFORMANCE_MODEL_V3.md`; nothing here changes any limit.

## Timings

**RESULTS_PENDING_COMPUTE_ENV.** No verification/signing benchmarks are reported here because they
have not been measured in a trusted environment. Do not infer timings from the size figures above.

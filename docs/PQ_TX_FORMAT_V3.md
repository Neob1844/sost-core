# SOST Post-Quantum Transaction / Witness Format — V3 (PROPOSAL)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

This document specifies the **proposed** post-quantum signature-witness format
for SOST. It is a design under research; it defines no consensus rule. The
reference implementation is the header-only, non-compiled prototype in
`prototype/pq/` (`pq_alg_registry.h`, `pq_witness.h`, `pq_validate.h`), exercised
by `tests/pq_vectors/`. V3 supersedes the V2 proposal (branch
`draft/pq-migration-v2`, PR #37), which is left intact for history.

## 1. Why a new format is required

Today's transaction input carries a **fixed** signature/pubkey layout:

- `TxInput.signature` = `std::array<Byte,64>` — compact ECDSA `r||s`
  (`include/sost/transaction.h:72`);
- `TxInput.pubkey` = `std::array<Byte,33>` — compressed secp256k1 point
  (`include/sost/transaction.h:73`);
- serialized as exactly `64 + 33` raw bytes with **no length prefix**
  (`src/transaction.cpp:210-217` / deserialize `:220-225`); per-input on-chain
  size is 133 bytes (`src/tx_validation.cpp:77`).

A fixed 64/33 slot cannot hold an ML-DSA-44 signature (2420 bytes) or public key
(1312 bytes). Post-quantum support therefore needs a **new, versioned,
variable-length witness**, not a tweak to the version-1 layout. The version-1
serialization is unchanged by this proposal.

## 2. Version gating

The PQ witness rides a **new transaction version 2**
(`prototype/pq/pq_alg_registry.h`, `PQ_WITNESS_TX_VERSION = 2`; PROVISIONAL).
Today's mainnet tx version is 1 (`include/sost/transaction.h:109`). Because
old clients accept only version 1, they reject a version-2 transaction by the
version check rather than mis-parsing an unknown witness — a clean
forward-incompatibility boundary (see also `docs/PQ_ACTIVATION_PLAN_V3.md`).

## 3. Cryptographic-agility registry (PROVISIONAL)

A single 1-byte `alg_id` selects the signature scheme. This lets future schemes
be added by assignment rather than by re-architecting the format each time
(ADR-001).

| alg_id | name | meaning | status |
|-------:|------|---------|--------|
| `0x00` | `LEGACY_ECDSA_SECP256K1` | today's 64/33 layout, re-expressed in the witness | active-in-proposal |
| `0x01` | `PQ_ML_DSA_44` | ML-DSA (FIPS 204), NIST level 2 | prototype/testnet only |
| `0x02` | `HYBRID_ECDSA_ML_DSA_44` | ECDSA **AND** ML-DSA-44 (both must verify) | prototype/testnet only |
| `0x03` | `ML_DSA_65_RESERVED` | FIPS 204 level 3 | reserved, rejected |
| `0x04` | `ML_DSA_87_RESERVED` | FIPS 204 level 5 | reserved, rejected |
| `0x10` | `SLH_DSA_RESERVED` | FIPS 205 hash-based backup | reserved, rejected |
| `0xFF` | `INVALID` | sentinel | always rejected |

Any value not explicitly active is **deterministically rejected** — there is no
"unknown id ⇒ ignore" path. This id map **reassigns** ids relative to V2 (V2 used
`0x02`=ML-DSA-65, `0x10`=hybrid); the reassignment is safe because
`PQ_ACTIVATION_HEIGHT == INT64_MAX` means no id is used by consensus in either
iteration. All ids are PROVISIONAL until a separate, audited proposal.

## 4. Component sizes (exact, from FIPS 204)

Enforced as **exact equalities**, never ranges — this removes length
malleability and bounds memory/DoS.

| scheme | signature (bytes) | public key (bytes) | NIST level |
|--------|------------------:|-------------------:|-----------|
| ECDSA secp256k1 | 64 | 33 | classical |
| ML-DSA-44 | 2420 | 1312 | 2 |
| ML-DSA-65 | 3309 | 1952 | 3 (reserved) |
| ML-DSA-87 | 4627 | 2592 | 5 (reserved) |

SLH-DSA (FIPS 205) sizes are parameter-set dependent and are not pinned here.

## 5. Wire format (prototype)

```
witness   := alg_id(1 byte) || component*      (no trailing bytes allowed)
component := len_be16 || component_bytes
len_be16  := unsigned 16-bit integer, big-endian (network byte order)

alg_id 0x00 LEGACY : sig(64)      pk(33)
alg_id 0x01 ML-DSA : sig(2420)    pk(1312)
alg_id 0x02 HYBRID : ec_sig(64)   ec_pk(33)   ml_sig(2420)   ml_pk(1312)
alg_id 0x03/0x04/0x10 RESERVED : rejected
alg_id 0xFF INVALID  : rejected
```

**Length encoding — single canonical rule (normative for V3).** Every component
length is encoded as `len_be16`: an **unsigned 16-bit integer, big-endian
(network byte order), occupying exactly 2 bytes**. There is exactly one length
encoding in V3:

- Exactly **2 length bytes** per component — never 1, never 3.
- **Unsigned big-endian**, always network byte order, identical on every
  architecture.
- **No `CompactSize`, no varint, no short form, no long form, no alternative
  prefix.** A `0xfd`/`0xfe`/`0xff` lead byte is just the high byte of a 16-bit
  length, never a varint marker.
- Each decoded `len_be16` **must equal the exact expected size** for the
  component's algorithm **and position**; any other value — including a
  correctly-formed length that names the wrong size — is rejected.

Rejection is deterministic for: truncation (fewer than 2 length bytes, or fewer
than `len_be16` component bytes), a wrong length, an over- or under-sized
component, wrong component order, duplication, and trailing bytes after a
complete witness. The parser performs **no allocation before the exact expected
length has been checked**. This format is **PROVISIONAL**; it is not active on
mainnet. An external auditor may question whether explicit per-component lengths
are needed at all (the `alg_id` already fixes every exact size), but must never
be presented with two incompatible encodings for the same witness version.

Design choices:

- **Fixed 2-byte big-endian length prefix.** Exactly one encoding of each length
  (no non-canonical varint attack surface). The largest reserved component
  (ML-DSA-87, 4627 bytes) fits in 16 bits.
- **Exact-length enforcement.** Each declared length must equal the exact size
  for its `alg_id`; a mismatch is rejected *before* any allocation, bounding
  memory. This same rule catches duplicated / mis-ordered hybrid halves (a
  swapped half presents the wrong length for its position).
- **No trailing bytes.** A witness must consume its input exactly.

> **Decision note (V3 research prototype).** Fixed-width BE16 was selected for the
> V3 research prototype because all currently proposed component sizes are below
> 65536 bytes, every length has exactly one representation, and the parser avoids
> CompactSize/varint canonicalisation rules. This remains provisional until
> external review and a separate consensus proposal.
>
> A component larger than 65535 bytes (none is currently proposed) could not be
> expressed under this encoding and would require a **new witness version**, never
> an alternative interpretation of the V3 length field.

The prototype parser (`prototype/pq/pq_witness.h`, `parse_witness`) returns one
of these deterministic codes: `OK`, `ERR_EMPTY`, `ERR_UNKNOWN_ALGID`,
`ERR_RESERVED_ALGID`, `ERR_INVALID_ALGID`, `ERR_TRUNCATED`,
`ERR_BAD_LENGTH_PREFIX`, `ERR_WRONG_COMPONENT_LEN`, `ERR_TRAILING_BYTES`,
`ERR_DUP_OR_MISORDERED`.

## 6. Signing and domain separation

Every scheme signs over a **domain-separated** message
`H(domain_tag || 0x00 || sighash)`, with distinct tags per scheme
(`prototype/pq/pq_alg_registry.h`):

- `SOST/pq-v3/ecdsa-secp256k1`
- `SOST/pq-v3/ml-dsa-44`
- `SOST/pq-v3/hybrid-ecdsa+ml-dsa-44`

Domain separation prevents algorithm-confusion, downgrade, signature-substitution
and cross-context replay: a signature valid under one tag is not valid under
another. `sighash` is the existing SOST sighash produced by the version-1 signer
(`src/tx_signer.cpp`); the witness format does not change how the sighash is
computed for a given input.

## 7. Hybrid = AND (never OR)

`HYBRID` (`0x02`) requires **both** the ECDSA and the ML-DSA-44 signature to
verify over the hybrid-tagged sighash. If either fails, the input is rejected.
OR-hybrid is explicitly refused: under OR an attacker who breaks *either* scheme
can forge, whereas AND requires breaking *both* (ADR-002). The prototype
enforces this in `prototype/pq/pq_validate.h` (`verify_parsed`, `HYBRID` arm),
and the negative tests confirm rejection when either half fails
(`tests/pq_vectors/test_pq_witness.cpp`).

## 8. Weight / cost

A PQ input is ~28x the size of a legacy input (ML-DSA-44); a hybrid input
slightly larger still (~29x). **No weight discount is assumed for PQ.** Size, per-input and per-tx
validation cost, and the interaction with `MAX_TX_BYTES_CONSENSUS = 100000`
(`include/sost/consensus_constants.h:15`), `MAX_BLOCK_BYTES_CONSENSUS = 1000000`
(`:16`) and `MAX_INPUTS_CONSENSUS = 256` (`:17`) are analysed in
`docs/PQ_PERFORMANCE_MODEL_V3.md`. CPU/memory timings are
`RESULTS_PENDING_COMPUTE_ENV` (`scripts/pq_bench/`).

## 9. Rejection rules a validator MUST apply (once activated — not now)

1. Reject any tx version 2 while `height < PQ_ACTIVATION_HEIGHT` (i.e. always,
   today, because the height is `INT64_MAX`).
2. Reject unknown / reserved / `0xFF` `alg_id`.
3. Reject a component whose declared length ≠ the exact expected size.
4. Reject truncated input and any trailing bytes.
5. Reject a hybrid whose halves are missing, duplicated, or mis-ordered.
6. Reject a witness whose signature(s) do not verify under the correct
   domain-separated sighash (both, for hybrid).
7. Enforce ECDSA LOW-S on the ECDSA half exactly as today
   (`src/tx_signer.cpp:210` `IsLowS`, `:277` LOW-S check).

## 10. What this document does NOT do

- It sets no activation height or date.
- It changes no version-1 serialization, sighash, txid, wallet, or explorer
  behaviour.
- It adds no dependency to the build and compiles nothing into the node.
- It is not a consensus change and must not be merged as one. Any activation is a
  separate, reviewed, audited, announced upgrade
  (`docs/PQ_ACTIVATION_PLAN_V3.md`).

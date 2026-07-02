# SOST PQ Transaction Format Proposal

Status: **DRAFT / RESEARCH.** No consensus change. All new types are height-gated
OFF (sentinel `INT64_MAX`). Mainnet serialization is byte-identical.

Author: NeoB. Companion to `PQ_MIGRATION_V2.md` and `PQ_THREAT_MODEL_V2.md`.

---

## 1. Baseline being preserved (do not change)

Legacy input, exactly as shipped (`src/transaction.cpp:207-227`,
`include/sost/transaction.h:69-82`):

```
input_v1 := prev_txid[32] || prev_index[4 LE] || signature[64] || pubkey[33]   // 133 B fixed
```

Legacy output (`src/transaction.cpp:233-286`):

```
output := amount[8 LE] || type[1] || pubkey_hash[20] || payload_len[2 LE] || payload[N]
```

Transaction (`src/transaction.cpp:290-333`):

```
tx := version[4 LE] || tx_type[1] || compactsize(n_in) || inputs[] || compactsize(n_out) || outputs[]
```

A transaction with `version == 1` MUST serialize and validate exactly as today.
This is the byte-identical guarantee.

---

## 2. Versioned witness (tx `version == 2`, gated OFF)

```
input_v2 := prev_txid[32] || prev_index[4 LE] || witness
witness  := alg_id[1] || compactsize(sig_len) || sig[sig_len] || compactsize(pk_len) || pk[pk_len]
```

Rules:
- `version == 2` is **rejected** unless `pq_active_at(height)` is reached
  (sentinel `INT64_MAX` today → always rejected → mainnet no-op, same pattern as
  `atomic_swap_htlc_active_at`, `include/sost/transaction.h:28-30`).
- For `alg_id == 0x00` (legacy inside v2), `sig_len == 64` and `pk_len == 33`
  are **mandatory exact values** (canonical), so a v2-legacy input carries the
  same signature bytes as v1.
- For every other `alg_id`, `sig_len` and `pk_len` MUST equal the registry's
  exact FIPS sizes (§3). Any other length ⇒ reject (malleability + DoS defence).

---

## 3. Algorithm registry (`alg_id`)

| `alg_id` | Name | sig_len | pk_len | verify-work weight (ECDSA=1) |
|---|---|---|---|---|
| `0x00` | LEGACY_ECDSA_SECP256K1 | 64 | 33 | 1 |
| `0x01` | PQ_ML_DSA_44 (FIPS 204) | 2420 | 1312 | TBD from §5 timings |
| `0x02` | PQ_ML_DSA_65 (FIPS 204) | 3309 | 1952 | TBD from §5 timings |
| `0x10` | HYBRID_ECDSA_ML_DSA_44 | 64+2420 | 33+1312 | 1 + w(0x01) |
| `0x11` | HYBRID_ECDSA_ML_DSA_65 | 64+3309 | 33+1952 | 1 + w(0x02) |
| any other | — | — | — | **REJECT (consensus)** |

Hybrid witness lays ECDSA first, then ML-DSA, each length-prefixed:

```
hybrid_witness := 0x10 || cs(64) || ecdsa_sig[64] || cs(33) || ecdsa_pub[33]
                        || cs(2420) || mldsa_sig[2420] || cs(1312) || mldsa_pub[1312]
```

Validation for `0x10`/`0x11`: compute the (domain-tagged) sighash, run
`VerifySighash` (existing `src/tx_signer.cpp:334`) over the ECDSA half **and**
ML-DSA verify over the same sighash; input is valid iff **both** pass.

---

## 4. Sighash (domain separation)

Reuse the existing preimage (`src/tx_signer.cpp:151-199`,
`hashPrevouts || … || hashOutputs || genesis_hash`) with a new leading
**domain tag byte** per spend type so an ECDSA signature can never be replayed as
a PQ or hybrid signature:

```
sighash_v2 := SHA256d( domain_tag[1] || alg_id[1] || <existing v1.2a preimage> )
```

`domain_tag` distinguishes legacy/PQ/hybrid. The legacy v1 sighash is untouched
(no tag) so old signatures remain valid.

---

## 5. Size & weight (measured size math; timings pending)

Per-input witness bytes (from `scripts/pq_bench/pq_bench.py`, real output):

| scheme | witness/input | 1-in tx | 2-in tx | 10-in tx | tx / 1 MB block (2-in) |
|---|---|---|---|---|---|
| legacy | 97 B | 202 B | 335 B | 1,399 B | 2,985 |
| pq / ML-DSA-44 | 3,737 B | 3,842 B | 7,615 B | 37,799 B | 131 |
| pq / ML-DSA-65 | 5,266 B | 5,371 B | 10,673 B | 53,089 B | 93 |
| hybrid / ML-DSA-44 | 3,834 B | 3,939 B | 7,809 B | 38,769 B | 128 |
| hybrid / ML-DSA-65 | 5,363 B | 5,468 B | 10,867 B | 54,059 B | 92 |

All fit under `MAX_TX_BYTES_CONSENSUS` = 100,000 even at 10 inputs. No witness fee
discount: PQ bytes weigh full rate under `MAX_BLOCK_BYTES_CONSENSUS` so fee cost
tracks DoS cost. Verify-work weights (`w`) filled from §5 of
`PQ_BENCHMARK_RESULTS.md` once timings are measured.

---

## 6. Wallet migration design

- `sost1` = legacy ECDSA (unchanged, `src/address.cpp:17`).
- `sost2` = PQ address type, HRP-distinct, commits to `HASH160(ml_dsa_pubkey)`.
- A distinct hybrid address/output type (e.g. `sost2h`) commits to both keys.
- **Deterministic derivation with domain separation**: extend the existing
  seed→key path (`src/hd_wallet.cpp:191-219`) with a PQ branch under a separate
  derivation domain (distinct salt/label) so ECDSA and ML-DSA keys never derive
  from the same expanded secret.
- Backup/import/export and an explicit **migration transaction** (legacy input →
  PQ/hybrid output) sweep funds forward; nothing is migrated in place.
- **PQ secret keys are never written to browser `localStorage`.** Web wallet
  already keeps the ECDSA private key out of storage/logs
  (`website/sost-wallet.html:6564` "no fetch, no localStorage, private key never
  logged"); the far larger PQ secret (2.5–4 kB) stays in memory only or in the
  encrypted export blob, never plaintext-persisted.

---

## 7. P2P handshake (testnet-only research)

- Keep X25519 + ChaCha20-Poly1305 (`src/sost-node.cpp:266-320`).
- Add optional hybrid KEM: X25519 shared-secret concatenated with ML-KEM-768
  (FIPS 203, pk 1184 / ct 1088) shared-secret, KDF'd to the ChaCha20-Poly1305
  key. Both halves must succeed.
- Capability negotiation bits bound into the transcript hash → downgrade attempts
  change the derived key and break the AEAD (downgrade protection).
- Off by default; testnet flag only; no mainnet activation.

---

## 8. Testing matrix (design; none run on mainnet)

| Category | Test |
|---|---|
| FIPS KAT | ML-DSA-44/65 and ML-KEM-768 known-answer vectors (NIST ACVP) |
| Round-trip | serialize→deserialize equality for every `alg_id`; v1 unchanged |
| Invalid length | wrong `sig_len`/`pk_len` for an `alg_id` ⇒ reject |
| Unknown alg | `alg_id` not in registry ⇒ deterministic reject |
| Malleability | any bit-flip in witness ⇒ verify fail; no alternate valid encoding |
| Fuzzing | libFuzzer over the v2 witness parser (bounded sizes) |
| Reorg / mempool | v2 tx across reorg, RBF, eviction; no crash, no accept while gated |
| Legacy regression | entire existing ctest suite passes unchanged (byte-identical v1) |
| DoS | max-input oversized-sig tx rejected by size + verify-work budget |

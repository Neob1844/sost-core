# SOST Post-Quantum Migration V2 — Architecture & Prototype Review

Status: **DRAFT / RESEARCH ONLY.** Nothing in this document activates on mainnet.
No consensus rule, activation height, ConvergenceX PoW parameter, or serialized
byte is changed by this work. SOST is **not** post-quantum secure today and this
document does not claim it is; it is a migration *design* plus a benchmark
harness.

Author: NeoB. Supersedes the aspirational notes in
`docs/QUANTUM_RESISTANCE_RESEARCH.md` (which still uses pre-final algorithm
names — see §7).

---

## 1. Cryptographic source of truth (audited)

The SOST spend/account scheme is **ECDSA over secp256k1**, compact 64-byte
signature `(r[32] || s[32])`, canonical **LOW-S** enforced, compressed 33-byte
public keys. This is confirmed at the following load-bearing sites:

| Concern | Evidence (file:line) |
|---|---|
| Signature scheme statement | `README.md:196` — "ECDSA secp256k1 (libsecp256k1) with LOW-S" |
| Key/sig type aliases | `include/sost/tx_signer.h:23-26` — `PrivKey[32]`, `PubKey[33]`, `Sig64[64]`, `PubKeyHash[20]` |
| Sign (LOW-S) | `src/tx_signer.cpp:289-328` (`SignSighash`, `secp256k1_ecdsa_sign` + `normalize`) |
| Verify (LOW-S) | `src/tx_signer.cpp:334-374` (`VerifySighash`) |
| LOW-S rule | `src/tx_signer.cpp:223-241` (`EnforceLowS`), `:247-283` (`ValidateRSRange`, "s > curve_order/2 … E5") |
| Sighash domain sep. | `src/tx_signer.cpp:151-199` — preimage ends with `genesis_hash(32)` (`:179`) |

**BIP-340 Schnorr is NOT the spend scheme.** Schnorr is used only for the SbPoW
miner-identity signature over the PoW commitment (miner block-identity binding),
gated at V11 Phase 2: `website/index.html:1402`, `docs/V11_PHASE2_RELEASE_NOTES.md:22,139`,
and the SbPoW path in `src/lottery.cpp` / `src/sbpow.cpp`. The two schemes must
never be conflated.

### 1.1 Every fixed-size public-key / signature field (the migration surface)

| Field | Size | Where declared | Where serialized | Where deserialized |
|---|---|---|---|---|
| `TxInput.signature` | 64 B fixed | `include/sost/transaction.h:72` | `src/transaction.cpp:216` (`WriteBytes(...,64)`) | `src/transaction.cpp:224` (`ReadBytes(...,64)`) |
| `TxInput.pubkey` | 33 B fixed | `include/sost/transaction.h:73` | `src/transaction.cpp:217` (`WriteBytes(...,33)`) | `src/transaction.cpp:225` (`ReadBytes(...,33)`) |
| `TxOutput.pubkey_hash` | 20 B fixed | `include/sost/transaction.h:91` | `src/transaction.cpp:249` | `src/transaction.cpp:264` |
| Per-input fixed layout | 133 B/input | comment `src/transaction.cpp:207-211` | — | size math `src/tx_validation.cpp:85` |
| `Sig64` / `PubKey` (script/multisig) | 64 / 33 | `include/sost/tx_signer.h:25,24` | `include/sost/script.h:53,56` (`make_multisig_*`) | `src/script.cpp` (eval) |
| Address (sost1) | `sost1` + 40 hex (20-B pkh) | `src/address.cpp:17,28`; `include/sost/address.h:8-11` | — | — |
| Wallet key material | `PubKey[33]`, `PrivKey[32]` | `src/hd_wallet.cpp:194-197` | `wallet.json` | `src/hd_wallet.cpp:213-219` |
| RPC pubkey field | `to_hex(...,33)` | `src/sost-rpc.cpp:167` | JSON out | — |
| RPC address field | `address_encode(pubkey_hash)` | `src/sost-rpc.cpp:187,232` | JSON out | — |
| SbPoW miner identity (Schnorr, **not** spend) | 32-B X-only pk | `include/sost/sbpow.h:219` | `src/sbpow.cpp` | — |

Explorer surfaces only txids / addresses / pubkey_hash, so it inherits whatever
the tx format encodes (`website/sost-explorer.html`). The explorer "ED25519 /
X25519 EKEY" lines (`explorer.html:331,497,533`) describe the **deal-channel P2P
relay**, not tx signatures.

### 1.2 Consensus size limits that bound the design (must be honoured)

| Constant | Value | file:line |
|---|---|---|
| `MAX_TX_BYTES_CONSENSUS` | 100,000 | `include/sost/consensus_constants.h:15` |
| `MAX_BLOCK_BYTES_CONSENSUS` | 1,000,000 | `include/sost/consensus_constants.h:16` |
| `MAX_INPUTS_CONSENSUS` | 256 | `include/sost/consensus_constants.h:17` |
| `MAX_OUTPUTS_CONSENSUS` | 256 | `include/sost/consensus_constants.h:18` |
| Tx size gate (R9) | `est_size > MAX_TX_BYTES` reject | `src/tx_validation.cpp:311-316` |
| Per-input size in estimate | `inputs.size()*133` | `src/tx_validation.cpp:85` |

### 1.3 Incorrect "Schnorr = spend scheme" statements (report only — not touched here)

- `website/index.html:1413` — **already corrected** by the operator (now
  correctly says the BIP-340 Schnorr signature is only the SbPoW block-identity
  binding, not the spend scheme). Do not touch.
- `website/sost-whitepaper.html:1417` — **still wrong**: "the current scheme uses
  secp256k1 + BIP-340 Schnorr". Recommend the same correction as index.html.
- Stale algorithm naming (see §7) in `website/sost-security.html:623,633`,
  `website/whitepaper-reader.html:3472`, `website/sost-technology.html:1526`.

These are website copy, not consensus. They are **reported, not modified** in
this draft (scope = `docs/` + off-consensus prototype only).

---

## 2. Non-negotiable constraints

1. Mainnet stays **byte-identical**. Legacy `sost1` addresses, existing UTXOs,
   the 133-byte input layout, sighash preimage, and ConvergenceX PoW are
   unchanged.
2. Every new spend type is **height-gated OFF** (sentinel `INT64_MAX`, the same
   pattern as `atomic_swap_htlc_active_at()` in `include/sost/transaction.h:28-30`
   and `POPC_V15_ACTIVATION_HEIGHT`). With the gate closed the validator rejects
   the new algorithm IDs, so replay of historical chain is bit-for-bit identical.
3. No merge, no deploy, no activation. This is a reviewable draft.
4. SOST is described as **ECDSA-secured today, PQ-migration under research** —
   never as "post-quantum secure".

---

## 3. Cryptographic agility design

The current input is a *fixed* `signature[64] || pubkey[33]`. PQ signatures are
1–5 kB and variable across parameter sets, so agility requires a versioned,
length-prefixed **witness** that carries an explicit algorithm identifier. The
legacy path is preserved unchanged so old transactions never re-serialize
differently.

### 3.1 Algorithm identifier registry (1-byte `alg_id`)

| `alg_id` | Name | Scheme | Sig / Pub sizes | Status |
|---|---|---|---|---|
| `0x00` | `LEGACY_ECDSA_SECP256K1` | ECDSA secp256k1 LOW-S | 64 / 33 | ACTIVE (implicit; today's format) |
| `0x01` | `PQ_ML_DSA_44` | ML-DSA-44 (FIPS 204, NIST L2) | 2420 / 1312 | gated OFF |
| `0x02` | `PQ_ML_DSA_65` | ML-DSA-65 (FIPS 204, NIST L3) | 3309 / 1952 | gated OFF |
| `0x10` | `HYBRID_ECDSA_ML_DSA_44` | ECDSA **AND** ML-DSA-44 | 64+2420 / 33+1312 | gated OFF |
| `0x11` | `HYBRID_ECDSA_ML_DSA_65` | ECDSA **AND** ML-DSA-65 | 64+3309 / 33+1952 | gated OFF |
| others | — | — | — | **deterministically REJECTED** |

Unknown `alg_id` is a hard consensus reject (not "ignore"), mirroring how
`OUT_HTLC_LOCK` is rejected while its gate is closed (`src/tx_validation.cpp`
R11 path). This prevents "unknown = valid" soft-fork ambiguity.

### 3.2 Versioned witness encoding

The legacy input (tx `version == 1`) is untouched. PQ witnesses ride a new tx
`version == 2` (or a per-input marker) so a v1 tx is byte-identical forever. The
v2 input witness is:

```
input_v2 := prev_txid[32] || prev_index[4] || witness
witness  := alg_id[1] || sig_len[varint] || sig[sig_len] || pk_len[varint] || pk[pk_len]
```

- `alg_id == 0x00` MUST use the exact legacy fixed sizes (64/33) — canonical,
  no length flexibility — so a v1 and a v2-legacy input hash the same payload.
- Consensus-safe max sizes: per `alg_id`, `sig_len` and `pk_len` MUST equal the
  registry's exact FIPS sizes (no ranges) → malleability-free, DoS-bounded.
- Verification-cost limit: a per-tx **verify-work budget** (weighted sum of
  per-input verify costs, ML-DSA weighted vs ECDSA baseline) checked before any
  signature is verified, so an attacker cannot pack 256 max-cost inputs to stall
  a node. Budget is a consensus constant tuned from §5 measurements.
- Fee/weight: PQ witnesses are large; to avoid subsidising them, weight
  `sig+pk` bytes at full rate under `MAX_TX_BYTES_CONSENSUS` (they already count
  fully in `EstimateSerializedSize`, `src/tx_validation.cpp:84-90`). No witness
  discount (unlike segwit) so DoS surface = fee surface.

### 3.3 Preserving existing addresses and UTXOs

- `sost1` addresses hash a 33-byte ECDSA pubkey → 20-byte pkh. Unchanged.
- A PQ output commits to `HASH160(pq_pubkey)` under a **new address type**
  (`sost2`, §6 of `PQ_TX_FORMAT_PROPOSAL.md`) so PQ pubkeys never collide with
  legacy pkh space and old UTXOs remain spendable by ECDSA only.
- No UTXO is rewritten or migrated in place; migration is an explicit
  user-signed transaction (legacy-in → PQ-out).

---

## 4. Three spend types

| Type | Unlock condition | Purpose |
|---|---|---|
| `LEGACY_ECDSA_SECP256K1` | ECDSA verify passes (today's rule) | Backward compat; all current UTXOs |
| `PQ_ML_DSA` | ML-DSA verify passes | Full PQ signatures for new funds |
| `HYBRID_ECDSA_ML_DSA` | **ECDSA verify passes AND ML-DSA verify passes** | Defence-in-depth during transition |

Hybrid is explicitly **conjunctive**: *both* signatures must validate over the
same sighash. "ECDSA **or** ML-DSA" is rejected as a design — an OR-hybrid is no
stronger than its weakest half against a quantum adversary. The validator for
hybrid runs ECDSA `VerifySighash` (existing `src/tx_signer.cpp:334`) and the
ML-DSA verify, and fails the input if either fails.

---

## 5. Benchmark status

See `docs/PQ_BENCHMARK_RESULTS.md`. **Size math is real** (derived from FIPS 204
fixed sizes by `scripts/pq_bench/pq_bench.py`, run on this repo). **Timing is
`RESULTS_PENDING_COMPUTE_ENV`** because no PQ library (liboqs / python-oqs) is
installed in this environment — timings are *not* fabricated. The doc contains
exact install + run instructions to fill the timing cells on a real VPS and
desktop, after which a candidate parameter set is recommended.

Preliminary size-only guidance (candidate NOT finalised until timings land):
ML-DSA-44 hybrid input ≈ 3.83 kB vs 97 B legacy; a 10-input hybrid tx ≈ 38.8 kB
(< 100 kB `MAX_TX_BYTES`); ~128 two-input hybrid tx per 1 MB block vs ~2985
legacy.

---

## 6. P2P handshake (research, testnet-only)

Current P2P encryption is already X25519 + ChaCha20-Poly1305
(`src/sost-node.cpp:91,266-320,4432-4483,6556-6570`). Proposed research: an
**optional testnet** handshake that adds ML-KEM-768 (FIPS 203) alongside X25519
(hybrid KEM), keeping ChaCha20-Poly1305 as the symmetric cipher. Downgrade
protection: both peers' capability bits are bound into the transcript hash that
keys the AEAD, so a MITM cannot silently strip ML-KEM. No default, no mainnet
activation. Detail in `PQ_TX_FORMAT_PROPOSAL.md §7`.

---

## 7. Terminology update (FIPS-final names)

This work standardises on the final NIST names. `docs/QUANTUM_RESISTANCE_RESEARCH.md`
and the website copy predate them:

| Old name (in repo) | Final name | Standard |
|---|---|---|
| CRYSTALS-Dilithium | **ML-DSA** | FIPS 204 |
| CRYSTALS-Kyber | **ML-KEM** | FIPS 203 |
| SPHINCS+ | **SLH-DSA** | FIPS 205 |

`liboqs` (Open Quantum Safe) is a **research** library and is **not presented as
production-audited** anywhere in this proposal. Any mainnet path would require an
independently audited, constant-time implementation.

---

## 8. Testing plan

Full matrix in `PQ_TX_FORMAT_PROPOSAL.md §8` and `PQ_THREAT_MODEL_V2.md`:
FIPS known-answer tests, serialization round-trip, invalid-length /
unknown-`alg_id` rejection, malleability, fuzzing, reorg/mempool compatibility,
legacy regression (every existing test must pass unchanged), and DoS
(oversized signatures + excessive verification work). None run against mainnet.

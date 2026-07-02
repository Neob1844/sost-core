# SOST Post-Quantum Threat Model V2

Status: **DRAFT / RESEARCH.** No mainnet impact. SOST is ECDSA-secured today and
is **not** post-quantum secure. This document scopes the quantum threat and the
non-quantum risks introduced by any PQ migration.

Author: NeoB.

---

## 1. Adversary model

| Adversary | Capability | In scope |
|---|---|---|
| A0 — classical | Today's attackers; no CRQC | Baseline (secp256k1 already resists) |
| A1 — harvest-now-decrypt-later | Records P2P traffic now, decrypts with a future CRQC | Yes (P2P KEM, §5) |
| A2 — CRQC signature forger | Runs Shor against secp256k1 to recover a private key from an **exposed public key** | Yes (spend scheme, §3) |
| A3 — protocol/DoS | Classical attacker abusing the *new* PQ code paths (oversized sigs, verify-work floods, malleability, downgrade) | Yes (§4) — the near-term real risk |

A cryptographically relevant quantum computer (CRQC) does not exist as of the
knowledge cutoff. A3 is the **immediate** risk that any PQ prototype must not
introduce.

---

## 2. What is and isn't exposed under secp256k1

- Shor's algorithm recovers a private key **only once the public key is known**.
- SOST outputs commit to `HASH160(pubkey)` (`src/tx_signer.cpp` /
  `include/sost/tx_signer.h:26`), so the pubkey is revealed **only when the UTXO
  is spent**. Unspent, address-reused-once funds behind a hash have SHA256+
  RIPEMD160 preimage resistance, which Grover only halves (still ~2^80 / 2^128).
- Therefore the acute A2 exposure is: (a) funds whose pubkey is already on-chain
  (spent-from / reused addresses), and (b) the window between broadcast and
  confirmation. This is the same exposure profile as Bitcoin.

**SHA-256 / RIPEMD-160 / ConvergenceX PoW are not Shor-broken**; Grover gives at
most a quadratic speedup, mitigated by existing widths. PoW and hashing are out
of scope for migration and are **not changed**.

---

## 3. Spend-scheme threat (A2) and the migration answer

- Legacy `LEGACY_ECDSA_SECP256K1`: vulnerable to A2 once pubkey exposed.
- `PQ_ML_DSA`: ML-DSA (FIPS 204) lattice signatures, believed CRQC-resistant.
- `HYBRID_ECDSA_ML_DSA`: **both** must verify. A forger needs to break ECDSA
  (quantum) *and* ML-DSA (no known attack) simultaneously → strictly stronger
  than either alone, and immune to a single-algorithm break in *either*
  direction during the transition. An OR-hybrid is explicitly rejected: it is
  only as strong as its weakest branch.

Residual: users must actively migrate funds to `sost2` PQ outputs; funds left in
`sost1` after a CRQC exists remain A2-exposed. Migration UX (a one-click legacy→PQ
sweep) is a wallet responsibility (`PQ_TX_FORMAT_PROPOSAL.md §6`).

---

## 4. Non-quantum risks introduced by the PQ code (A3 — the near-term danger)

| Risk | Mitigation in the design |
|---|---|
| **Oversized-signature DoS** — PQ sigs are 40–55× larger | Exact fixed sizes per `alg_id` (no ranges); witnesses count fully toward `MAX_TX_BYTES_CONSENSUS` (`consensus_constants.h:15`); no witness fee discount |
| **Verify-work flood** — ML-DSA verify ≫ ECDSA; 256 inputs | Per-tx verify-work budget checked *before* any verify; budget calibrated from §5 timings of `PQ_BENCHMARK_RESULTS.md` |
| **Unknown-`alg_id` soft-fork ambiguity** | Unknown IDs **deterministically rejected**, never "ignored" |
| **Signature malleability** | ML-DSA is deterministic; witness sizes are exact; ECDSA half already LOW-S (`tx_signer.cpp:223-283`); sighash unchanged (domain-separated by `genesis_hash`, `tx_signer.cpp:179`) |
| **Downgrade (hybrid → single)** | Output's `alg_id`/address type fixes the required scheme; a spender cannot present a weaker witness than the output demands |
| **Cross-protocol signature reuse** | New sighash domain tag per spend type + existing `genesis_hash` binding |
| **Library immaturity** | liboqs is research-grade; NOT presented as audited; any mainnet path needs an audited constant-time impl |
| **Consensus split from a verifier bug** | The `-DSOST_ENABLE_PHASE2_SBPOW` incident (`website/news.html:854`) shows a mis-compiled verifier can split the net; PQ paths ship height-gated OFF and behind an explicit build flag, KAT-tested, before any height is set |

---

## 5. P2P / KEM threat (A1)

- Harvest-now-decrypt-later on the encrypted P2P channel (currently X25519 +
  ChaCha20-Poly1305, `src/sost-node.cpp:91`). Impact is limited: SOST P2P carries
  public blocks/txs, not secrets; the main value is metadata / deal-channel
  content.
- Mitigation (testnet research only): hybrid X25519 + ML-KEM-768 handshake with
  the capability bits bound into the transcript to block downgrade. Symmetric
  layer (ChaCha20-Poly1305, 256-bit) is already Grover-adequate.

---

## 6. Explicit non-goals / untouched surfaces

- ConvergenceX PoW, cASERT, SbPoW Schnorr miner-identity binding — **unchanged**.
- No activation height set. No mainnet consensus edit. No change to the 133-byte
  legacy input, sighash preimage, address format, or supply.
- No claim of post-quantum security is made anywhere.

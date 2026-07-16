# SOST Post-Quantum Threat Model (V3)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> V3 supersedes the prior iteration `docs/PQ_MIGRATION_V2.md` (PR #37). Where V3 changes V2
> assumptions (notably the alg-id registry reassignment) this is noted explicitly. V3 does not
> delete or silently contradict V2.
>
> SOST is **not** claimed to be quantum-safe or post-quantum secure. Post-quantum transaction
> validation is not active on mainnet; there is no activation height and no date. This is a
> research/architecture document only.

---

## 1. Scope and framing

This document enumerates the threats that motivate (and constrain) a post-quantum (PQ) signature
migration for SOST spend authorisation. It covers both the underlying cryptographic exposure and
the protocol-engineering attack surface that a versioned, variable-length PQ witness introduces.

Today, SOST spend signatures are **ECDSA over secp256k1**, compact 64-byte (`r||s` big-endian),
canonical **LOW-S** enforced:

- `README.md:196` — "Signature | ECDSA secp256k1 (libsecp256k1) with LOW-S".
- `src/tx_signer.cpp:8,19` (header comment); `IsLowS` at `src/tx_signer.cpp:210`;
  `EnforceLowS` at `src/tx_signer.cpp:223`; `ValidateRSRange` (LOW-S violation = `E5`) at
  `src/tx_signer.cpp:247` / `:277`; `secp256k1_ecdsa_verify` at `src/tx_signer.cpp:374`;
  `VerifyTransactionInput` at `src/tx_signer.cpp:551`.

The on-chain input layout is **fixed-width, no length prefix**:

- `signature = std::array<Byte,64>` (`include/sost/transaction.h:72`); `pubkey =
  std::array<Byte,33>` compressed 02/03 (`include/sost/transaction.h:73`).
- Serialized as a FIXED 64 + 33 bytes with no length prefix
  (`src/transaction.cpp:210-217` `SerializeTo` / `:220-225` `DeserializeFrom`).
- Per-input serialized size today = 133 bytes (`src/tx_validation.cpp:77`).

This fixed layout is exactly why PQ requires a **new versioned, variable-length witness** rather
than an in-place field swap: ML-DSA signatures and public keys are far larger than 64/33 bytes and
cannot fit the current array types.

---

## 2. Core cryptographic threat: quantum vs ECDSA

### 2.1 Shor recovers the private key from the public key

A cryptographically-relevant quantum computer (CRQC) running **Shor's algorithm** solves the
elliptic-curve discrete-logarithm problem efficiently. For secp256k1 this means: **given a public
key, the corresponding private key can be recovered.** ECDSA signature unforgeability rests entirely
on that discrete-log being hard; Shor removes that hardness. This is a *signature-forgery* threat,
not a decryption threat.

### 2.2 Correct signature threat framing — "collect public keys now, forge later"

The relevant model for signatures is **NOT** "harvest now, decrypt later" (that is the
KEM/encryption model — see ML-KEM / FIPS 203, which SOST does not use for spends). The correct
framing is:

> An adversary can **collect public keys now** (every revealed on-chain public key) and **forge
> signatures later**, once a CRQC exists. Shor's algorithm recovers the private key from the
> collected public key.

Any public key that has ever been revealed on-chain is therefore a standing liability the moment a
CRQC appears, independent of when it was revealed.

### 2.3 Funds at REVEALED vs UNREVEALED public keys

- **REVEALED public keys** — funds sitting at addresses whose public key is already visible
  on-chain (any address that has been spent from, and any reused address). These are directly
  exposed: an adversary with a CRQC can recover the private key and spend the funds. **Highest
  risk class.**
- **UNREVEALED public keys** — funds at addresses where only a *hash* of the public key has been
  published and the output has never been spent. The public key itself is not yet on-chain, so the
  adversary has only the hash (protected by hash preimage resistance, which Grover only weakens
  quadratically — see §2.4 and the assumptions doc). These have a **smaller exposure window** — but
  that window is not zero (see §3.1, mempool front-running).

### 2.4 Address reuse

Address reuse converts an unrevealed key into a revealed key permanently and needlessly. Every reuse
after a first spend leaves the public key on-chain for future forgery. **Exposed:** any user or
service that reuses addresses. **V3 mitigation:** documentation/wallet guidance to avoid reuse;
long-term, migrate value to PQ or hybrid outputs whose forgery requires breaking ML-DSA (or both
schemes). This is guidance-level, not a consensus rule.

---

## 3. Protocol / operational threats around a quantum window

### 3.1 Mempool exposure and front-running during a quantum window

Even for an unrevealed key, spending **reveals the public key** in the spending transaction. If a
CRQC exists at that time, an adversary who sees the transaction in the mempool (or in any
unconfirmed state) can, within the confirmation window:

1. Read the newly revealed public key,
2. Recover the private key (Shor),
3. **Forge a competing/replacement transaction** that pays the adversary, and
4. Get it confirmed before or instead of the honest spend.

**Exposed:** anyone spending a pre-quantum-era output after a CRQC exists; the confirmation latency
*is* the attack window. **V3 mitigation:** PQ or hybrid spend types whose authorisation is not
ECDSA-forgeable; note that this threat is the strongest argument for migrating *before* a CRQC, not
after. Open research: reducing reveal-to-confirm latency and commit/reveal spend schemes.

### 3.2 Dormant / lost coins

Coins whose owners are unreachable or whose keys are lost **cannot be migrated by their owners.**
Their public keys, once revealed, remain forgeable forever after a CRQC. **Exposed:** the network as
a whole (supply/economic integrity), not one user. **V3 mitigation:** *open / research / social* —
this is a governance and economics question, not something V3 solves cryptographically. V3 does not
propose confiscation or forced migration.

### 3.3 Non-migrating exchanges, custodians, and services

Exchanges and custodians that do not upgrade continue to hold value at ECDSA keys and may sign in
old formats. **Exposed:** custodial customer balances; also a downgrade vector (§4.1) if such
services keep old-format acceptance alive. **V3 mitigation:** *open / adoption* — activation plan
requires minimum node versions and adoption metrics (see `docs/PQ_ACTIVATION_PLAN_V3.md`); V3 cannot
force third parties.

### 3.4 Hardware wallets

ML-DSA public keys and signatures are large (see §7). Hardware wallets face: firmware that must add
ML-DSA; constrained RAM/flash for larger keys and signatures; longer signing time; and secure key
storage for larger secrets. **Exposed:** hardware-wallet users if firmware lags. **V3 mitigation:**
*open / vendor-dependent* — V3 documents the size and format requirements so vendors can plan; it
does not ship firmware.

---

## 4. Witness / consensus-engineering attack surface (introduced by a PQ witness)

Introducing a versioned, variable-length witness with a crypto-agility registry creates its own
attack surface. The V3 **PROVISIONAL** alg-id registry (a 1-byte `alg_id` in the versioned witness;
supersedes V2, which used different ids — no protocol conflict because
`PQ_ACTIVATION_HEIGHT = INT64_MAX`, i.e. unused):

- `0x00` LEGACY_ECDSA_SECP256K1 (today's 64/33 fixed layout)
- `0x01` PQ_ML_DSA_44 (FIPS 204, NIST L2)
- `0x02` HYBRID_ECDSA_ML_DSA_44 (BOTH ECDSA AND ML-DSA-44 must verify — AND semantics)
- `0x03` ML_DSA_65_RESERVED
- `0x04` ML_DSA_87_RESERVED
- `0x10` SLH_DSA_RESERVED
- `0xFF` INVALID
- any other value = deterministically REJECTED (never "ignore")

### 4.1 Downgrade attacks

An attacker tries to force validation to fall back to the weaker (ECDSA) path for an output the owner
intended to protect with PQ/hybrid. **V3 mitigation:** the spend type is bound to the output being
spent; a PQ- or hybrid-locked output must not be spendable via a bare `0x00` legacy witness.
Acceptance of `0x00` is compatibility-only and must never override a stronger commitment.

### 4.2 Algorithm-confusion attacks

Attacker supplies a witness whose declared `alg_id` does not match the key material or the verifier
selected. **V3 mitigation:** `alg_id` is authenticated as part of the signed message / witness
envelope and drives verifier selection deterministically; a mismatch is a hard reject, not a
best-effort parse.

### 4.3 Signature-substitution attacks

Attacker replaces the signature (or, for hybrid, one of the two signatures) with a different valid-
looking blob. **V3 mitigation:** for HYBRID `0x02`, **both** ECDSA **and** ML-DSA-44 must verify
over the same canonical message (AND semantics — see §5); substituting either alone fails.

### 4.4 Malleability

ECDSA already enforces canonical LOW-S (`IsLowS` `src/tx_signer.cpp:210`; `EnforceLowS` `:223`;
`E5` at `:247`/`:277`). A PQ witness must likewise define a single canonical encoding so a third
party cannot mutate an accepted witness into another accepted-but-different witness (which would
change the txid). **V3 mitigation:** deterministic canonical encoding of the witness; non-canonical
encodings are rejected.

### 4.5 Replay attacks

A signature/witness valid in one context is replayed in another (cross-input, cross-tx, or
cross-network). **V3 mitigation:** the signed message must commit to the full spend context (input,
amounts, and network/genesis domain separation); the isolated testnet uses distinct network magic
(see `docs/PQ_TESTNET_PLAN_V3.md`).

### 4.6 Ambiguous-parsing attacks

A variable-length witness with multiple length fields can be crafted to parse two ways ("two
readings, one bytes"), or to over-read/under-read. **V3 mitigation:** strict length-prefixed,
bounds-checked, single-pass parsing; any trailing bytes, inconsistent lengths, or truncation is a
deterministic reject. Contrast today's safe-but-inflexible fixed 64+33 layout
(`src/transaction.cpp:210-225`).

### 4.7 Unknown / reserved alg-ids

An unrecognised `alg_id` (or a `RESERVED`/`0xFF INVALID` value) must be **deterministically
REJECTED, never ignored or treated as valid.** Ignoring would create a consensus split between nodes
that "skip" vs nodes that reject. **V3 mitigation:** the registry defines reject-by-default; only
explicitly-listed active ids validate.

---

## 5. Hybrid rationale (why AND, not OR)

The three spend types:

- **LEGACY (`0x00`)** — ECDSA; compatibility only, today's mainnet behaviour.
- **PQ (`0x01`)** — ML-DSA; prototype/testnet only.
- **HYBRID (`0x02`)** — ECDSA **AND** ML-DSA both valid (conjunctive AND).

**OR-hybrid is REJECTED.** With OR-semantics, an attacker who breaks *either* scheme can forge — so
an OR-hybrid is only as strong as the *weaker* of the two. **AND-hybrid** requires breaking **both**
ECDSA **and** ML-DSA-44 to forge, so it is at least as strong as the stronger scheme and hedges the
risk that a newly-standardised PQ scheme has an undiscovered weakness. This is the conservative
choice during a transition when neither classical-only nor PQ-only is fully satisfactory.

---

## 6. Availability / DoS threats

Large PQ objects interact badly with size and cost limits. Relevant consensus limits today:

- `MAX_TX_BYTES_CONSENSUS = 100000` (`include/sost/consensus_constants.h:15`)
- `MAX_BLOCK_BYTES_CONSENSUS = 1000000` (`include/sost/consensus_constants.h:16`)
- `MAX_TX_BYTES_STANDARD = 16000` (`include/sost/tx_validation.h:26`)
- `MAX_BLOCK_TXS_CONSENSUS = 65536` (`include/sost/block_validation.h:37`)
- `MAX_BLOCK_TX_COUNT = 4096` (`include/sost/mempool.h:22`)
- Per-input serialized size today = 133 bytes (`src/tx_validation.cpp:77`)

### 6.1 Giant-signature / block-and-mempool bloat DoS

An ML-DSA-44 signature (2420 B) + public key (1312 B) is ~3.7 KB per input versus 133 B today —
roughly a 28x per-input expansion; hybrid is larger still (ECDSA + ML-DSA). Unbounded, this lets an
attacker fill blocks/mempool cheaply relative to verification value. **V3 mitigation:** enforce
explicit per-alg witness-size bounds derived from the FIPS 204 fixed sizes; reject oversized or
undersized witnesses before verification; re-evaluate standardness limits. Any change to these
consensus limits is itself a consensus change and out of scope for this research PR.

### 6.2 Costly-verify CPU DoS

ML-DSA verification is more expensive than ECDSA verify. An attacker can craft many inputs to force
expensive verification. **V3 mitigation:** *open / research* — reject on cheap checks first
(alg-id, size, encoding) before the expensive verify; measure per-alg verify cost on the isolated
testnet (`scripts/pq_bench/`) — **no timings are asserted in this document.** A candidate
per-transaction **verify-work budget** (weighted sum of per-input verify costs, checked before any
verification, weights calibrated from measured timings) is described in
`docs/PQ_PERFORMANCE_MODEL_V3.md §4.4`; it is a consensus-level bound and out of scope for this PR.

### 6.3 Memory-exhaustion DoS

Variable-length parsing plus large objects can be steered toward large allocations. **V3
mitigation:** hard upper bounds and single-pass, bounds-checked parsing (§4.6); never allocate based
on an unvalidated length field.

### 6.4 Unknown-alg DoS / split

See §4.7 — unknown ids must be rejected deterministically so they cannot be used to split the
network or to smuggle unbounded data.

---

## 7. FIPS object sizes (from published FIPS 204 — do not alter)

| Scheme | NIST level | Public key (B) | Signature (B) |
|---|---|---|---|
| ECDSA secp256k1 (today) | — | 33 (compressed) | 64 |
| ML-DSA-44 | L2 | 1312 | 2420 |
| ML-DSA-65 | L3 | 1952 | 3309 |
| ML-DSA-87 | L5 | 2592 | 4627 |
| SLH-DSA (FIPS 205) | varies | parameter-set dependent | parameter-set dependent |

SLH-DSA sizes vary widely by parameter set (e.g. SLH-DSA-SHA2-128s: public key 32 B, signature
7856 B); sizes are stated as **parameter-set dependent** rather than pinned to one number unless the
exact parameter set is named. No performance timings are given anywhere in this document.

---

## 8. Supply-chain, side-channel, and RNG threats

### 8.1 Compromised libraries (supply chain)

A backdoored or buggy ML-DSA / SLH-DSA implementation could accept forgeries or leak keys. Today's
ECDSA path relies on libsecp256k1 (`README.md:196`). **Exposed:** every node and wallet. **V3
mitigation:** *open / process* — pinned, reproducible dependencies; multiple independent
implementations for cross-checking on testnet; external audit before any activation (see activation
plan). No audit has been performed at V3.

### 8.2 Side channels

Timing/cache/power side channels in signing (and, for hot custodians, in verification) can leak key
material. ML-DSA has known implementation pitfalls (e.g. rejection sampling timing). **Exposed:**
signers, especially hardware wallets and custodians. **V3 mitigation:** *open / implementation* —
require constant-time vetted implementations; part of the pre-activation audit scope.

### 8.3 Entropy / RNG failure

ECDSA is catastrophically broken by nonce reuse/bias; ML-DSA-44 in its standard "hedged" mode still
depends on quality randomness for key generation and hedging. **Exposed:** any keygen or signing with
weak entropy. **V3 mitigation:** deterministic/hedged signing where the standard supports it; keygen
entropy requirements documented; part of audit scope. *Open.*

---

## 9. Governance / network-split threats

### 9.1 Node-upgrade splits

If some nodes accept a new PQ witness and others reject it, the network partitions into incompatible
chains. **Exposed:** the whole network. **V3 mitigation:** activation is a coordinated consensus
change gated by minimum node versions, version signalling, and a height activation set only by a
*future separate proposal* — kept inert today by the sentinel `PQ_ACTIVATION_HEIGHT = INT64_MAX`
(the same "never active" pattern as `POPC_V15_ACTIVATION_HEIGHT` and `atomic_swap_htlc_active_at`).
See `docs/PQ_ACTIVATION_PLAN_V3.md`. **No real height is set in this PR.**

### 9.2 Legacy inert placeholder

`include/sost/proposals.h:44` holds an INERT placeholder proposal (id 8 `post_quantum`, status
DEFINED, heights `-1`) whose label still reads "SPHINCS+/Dilithium" — historical/legacy naming,
**not consensus-active.** V3 notes this should eventually be reworded to ML-DSA / SLH-DSA
terminology, but that reword changes no behaviour and is not part of any activation.

---

## 10. Threat summary table

| # | Threat | Who / what is exposed | V3 mitigation / status |
|---|---|---|---|
| T1 | Shor recovers privkey from pubkey | All ECDSA keys once a CRQC exists | PQ/hybrid spend types (prototype) |
| T2 | Funds at REVEALED pubkeys | Spent-from / reused addresses | Migrate to PQ/hybrid; avoid reuse (guidance) |
| T3 | Funds at UNREVEALED pubkeys | Hash-locked never-spent outputs | Smaller window; hash resistance holds (see §2.3) |
| T4 | Address reuse | Reusing users/services | Wallet guidance; migrate value (guidance) |
| T5 | Mempool / front-run at spend reveal | Anyone spending post-CRQC | PQ/hybrid; commit-reveal — *open research* |
| T6 | Dormant / lost coins | Network (supply integrity) | *Open / governance* — no forced migration |
| T7 | Non-migrating exchanges/custodians | Custodial balances; downgrade vector | *Open / adoption metrics* |
| T8 | Hardware wallets (firmware, big sigs) | HW-wallet users | *Open / vendor* — sizes documented |
| T9 | Downgrade attack | PQ/hybrid outputs forced to ECDSA | Spend type bound to output; `0x00` can't override |
| T10 | Algorithm-confusion | Verifier / any input | Authenticated `alg_id` drives deterministic selection |
| T11 | Signature-substitution | Any input; hybrid | HYBRID requires BOTH to verify (AND) |
| T12 | Malleability | Txid stability | Canonical LOW-S (ECDSA) + canonical PQ witness encoding |
| T13 | Replay | Cross-input/tx/network | Message binds full context + network domain separation |
| T14 | Ambiguous parsing | Consensus split | Strict length-prefixed, bounds-checked, single-pass parse |
| T15 | Unknown / reserved alg-ids | Consensus split | Deterministic REJECT, never ignore |
| T16 | Giant-signature bloat DoS | Blocks / mempool | Per-alg size bounds; reject before verify |
| T17 | Costly-verify CPU DoS | Nodes | Cheap checks first; testnet measurement — *open* |
| T18 | Memory-exhaustion DoS | Nodes | Hard bounds; never allocate on unvalidated length |
| T19 | Compromised crypto library | Every node/wallet | Pinned deps; cross-impl; audit — *open, no audit yet* |
| T20 | Side channels | Signers / custodians | Constant-time vetted impls — *open, audit scope* |
| T21 | Entropy / RNG failure | Any keygen/signer | Hedged signing; entropy reqs — *open, audit scope* |
| T22 | Node-upgrade split | Whole network | Version signalling + sentinel-gated height (INT64_MAX) |

---

## 11. Status

Post-quantum transaction validation is **not active on mainnet**: no activation height, no date, not
merged. ML-DSA (FIPS 204), the crypto-agility registry, and the hybrid AND scheme exist only as a
research prototype. The prototype uses `PQ_ACTIVATION_HEIGHT = INT64_MAX` ("never active"). No
audit has been performed. This document changes no consensus rule and activates nothing.

## 12. Secondary track: transport-channel (KEM) adversary — out of signature scope

Everything above concerns **signatures** (spend authorisation), where the threat is
"collect public keys now, forge later" and the answer is a PQ / hybrid *signature*.
A separate adversary — carried over from the V2 analysis (PR #37, §5/§6) and kept
here so the information is not lost — targets the **encrypted P2P transport
channel**, which is a *different* problem with a *different* primitive family.

### 12.1 Adversary A1 — harvest-now, decrypt-later (transport only)

| Property | Value |
|---|---|
| Target | The node-to-node encrypted channel, today X25519 + ChaCha20-Poly1305 (`src/sost-node.cpp`) |
| Capability | Records ciphertext **now**, decrypts **later** once a CRQC can break X25519 |
| Primitive at risk | The **key-establishment** (Diffie-Hellman / KEM) step, **not** any signature |
| What is exposed | P2P metadata and deal-channel relay content; SOST P2P otherwise carries public blocks/txs, so the marginal value is limited |

This is the classic "harvest-now, decrypt-later" model — which is **why** §2.2
stresses that the *signature* threat is emphatically **not** this model. The two
must not be conflated.

### 12.2 Direction (research, isolated-testnet only — activates nothing)

A hybrid key-establishment step: keep X25519 and add **ML-KEM-768** (FIPS 203 —
a key-encapsulation mechanism, **not** a signature scheme, never used for spends),
concatenating the two shared secrets and running them through the existing KDF into
the ChaCha20-Poly1305 key. Both halves must succeed, so the channel is at least as
strong as X25519 today. Capability-negotiation bits are bound into the transcript
hash that derives the AEAD key, so a downgrade attempt (stripping ML-KEM) changes
the derived key and breaks authentication — transport-level downgrade protection.
The symmetric layer (ChaCha20-Poly1305, 256-bit) is already Grover-adequate.

### 12.3 Scope boundary

- This track is **secondary** to the signature migration and **out of scope for
  any activation in this PR**.
- It sets no height, adds no build dependency, and changes no consensus rule; a
  transport KEM is not a consensus object.
- It would be exercised, if at all, only on the isolated experimental testnet
  (`docs/PQ_TESTNET_PLAN_V3.md`), behind the same default-OFF posture as the rest
  of the prototype.

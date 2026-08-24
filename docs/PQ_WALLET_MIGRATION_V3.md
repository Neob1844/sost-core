# PQ Wallet & Fund Migration Strategy — V3 (RESEARCH / DOCS ONLY)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> **Scope.** This document describes a *proposed* wallet and fund-migration strategy for a
> future post-quantum (PQ) capability. It contains **no dates and no block heights**. Nothing
> here is active on mainnet. It supersedes the wallet-migration discussion in the prior
> iteration (`docs/PQ_MIGRATION_V2.md`, PR #37) without deleting or contradicting it — where V3
> differs from V2 it is noted explicitly.

---

## 1. Where we are today (verified on-chain facts)

- Spends are authorised by **ECDSA over secp256k1**, compact 64-byte `r||s` big-endian, with
  canonical **LOW-S** enforced (`README.md:196`; `src/tx_signer.cpp:8,19`; `IsLowS`
  `src/tx_signer.cpp:210`; `EnforceLowS` `:223`; `secp256k1_ecdsa_verify` `:374`;
  `VerifyTransactionInput` `:551`).
- Each `TxInput` carries a **fixed** `signature = std::array<Byte,64>` and
  `pubkey = std::array<Byte,33>` (compressed 02/03) — `include/sost/transaction.h:72-73` —
  serialized as a **fixed 64 + 33 with no length prefix**
  (`src/transaction.cpp:210-217` / `:220-225`). This fixed layout is precisely why PQ requires
  a **new, versioned, variable-length witness** rather than an in-place field swap.
- Transaction `version` is `uint32_t version{1}` (`include/sost/transaction.h:109`). V3 proposes
  **tx version 2** as the envelope for the PQ witness (**PROVISIONAL**, not active).
- BIP-340 Schnorr is used **only** for SbPoW miner block-identity binding, never for spending
  (`src/sbpow.cpp:37-80`, sign `:249-270`, verify `:304-318`). Wallet migration does not touch it.

### 1.1 The signature threat we are migrating against
The signature risk is **not** "harvest now, decrypt later" (that is the KEM/encryption problem).
For signatures the correct framing is: an adversary can **collect public keys now** from any
**revealed** on-chain pubkey and, once a cryptographically-relevant quantum computer exists,
**forge signatures later** (Shor's algorithm recovers the private key from the public key).

- Funds at **revealed** pubkeys (already-spent-from addresses, **reused** addresses) are the
  exposed set.
- Funds at **unrevealed** pubkeys (hash-locked, never spent) expose only the hash until spend
  time — a smaller window, but the spend transaction reveals the pubkey and creates a
  **mempool front-running window** before confirmation.

Migration priority therefore follows exposure: reused/revealed addresses first, then dormant
never-spent addresses ahead of their first (and only safe) spend.

---

## 2. Address model: legacy, PQ, and hybrid

Three coexisting address classes are proposed, each bound to a crypto-agility `alg_id` (see the
V3 registry in `docs/PQ_DECISION_LOG_V3.md` and the shared spec):

| Class  | alg_id | Meaning                                        | Status                          |
|--------|--------|------------------------------------------------|---------------------------------|
| LEGACY | 0x00   | ECDSA secp256k1, today's 64/33 fixed layout    | mainnet behaviour               |
| PQ     | 0x01   | ML-DSA-44 (FIPS 204, NIST L2)                   | prototype / testnet only        |
| HYBRID | 0x02   | ECDSA **AND** ML-DSA-44 (both must verify)      | prototype / testnet only        |

### 2.1 Address prefix (reserved, provisional — do NOT treat as final)
A **new address prefix** is *reserved* for PQ / hybrid outputs so that a PQ address is visually
and programmatically distinguishable from a legacy `sost1…` address, and so that wallets can
refuse to route funds to a class the recipient's software cannot spend.

- The public website refers to a `sost2…` prefix **aspirationally**. This document treats
  `sost2` as a **provisional placeholder only**. **Do not claim `sost2` is the final prefix.**
  The final prefix (and whether PQ and hybrid share one prefix or take distinct ones) is an
  open item — see *DECISIONS PENDING* in `docs/PQ_DECISION_LOG_V3.md`.
- Whatever prefix is chosen must encode enough to let a wallet reject a spend to an address
  whose `alg_id` the sender cannot produce or the network cannot yet validate.

---

## 3. Key material, seeds, and derivation (honest limitations)

**An ECDSA seed does not directly yield an ML-DSA key.** ML-DSA is a lattice scheme with its own
key structure; a secp256k1 private scalar is not an ML-DSA private key and cannot be reinterpreted
as one. A PQ-capable wallet must therefore **derive PQ keys through their own derivation path**,
separate from the existing secp256k1 BIP-32-style tree.

This document deliberately **does not over-specify** that derivation. The honest, minimal position:

- PQ keys need a dedicated derivation branch (their own path / index space), seeded from the
  wallet's master entropy but through a PQ-appropriate expansion — **the exact KDF/derivation
  scheme is an open design item and is intentionally left unspecified here.**
- A single wallet backup (seed) can, in principle, regenerate **both** the legacy secp256k1 tree
  and the PQ branch, provided the derivation scheme is fixed and documented before any user
  relies on it. Until that scheme is finalised, **treat PQ keys as independently-backed material**.
- Backups, seed export, and recovery flows must make clear **which classes a given backup covers**.
  A pre-PQ backup does not contain PQ keys.

### 3.1 Descriptors and export
- Output descriptors / watch-only export must carry the `alg_id` so that a descriptor unambiguously
  states whether it describes a LEGACY, PQ, or HYBRID output. A descriptor without an explicit
  class must default to **LEGACY** and must never be silently upgraded.
- Private-key export (WIF-style or descriptor-with-keys) must label the class and must never
  export an ECDSA key as if it authorised a PQ output, or vice-versa.

---

## 4. Custody surfaces

### 4.1 Hardware wallets
- ML-DSA-44 keys and signatures are large (public key 1312 B, signature 2420 B — FIPS 204).
  Constrained secure elements may lack the flash/RAM/throughput for on-device ML-DSA. Migration
  must not assume every existing hardware wallet can hold or sign PQ material.
- Hybrid signing needs **both** an ECDSA and an ML-DSA signature from the device (AND semantics),
  doubling the signing work and the data transferred.

### 4.2 Exchanges and custodians
- Deposit-address issuance must let a venue choose LEGACY, PQ, or HYBRID per the classes its
  hot/cold stack can validate and spend. A venue must not hand out PQ deposit addresses it cannot
  later spend from.
- Sweep/cold-storage tooling must understand the new prefix and refuse to co-mingle classes in a
  way that would strand funds.

### 4.3 Multisig
- Multisig policy must state the `alg_id` per key **and** per the aggregate script. Mixed-class
  multisig (e.g. some ECDSA, some ML-DSA cosigners) is an explicit design question and must be
  either fully specified or refused — never implicitly allowed.
- A quorum of legacy keys does not confer PQ resistance; a multisig is only as PQ-resistant as
  the weakest **required** signer.

### 4.4 Coinbase outputs
- Coinbase outputs paying to legacy addresses inherit legacy exposure. Miner payout tooling should
  be able to target PQ/HYBRID outputs once the class is validated, so that freshly-minted, long-held
  coins are not created directly into the exposed set.

---

## 5. High-exposure fund categories

- **Reused addresses** — pubkey already revealed; highest priority. Recommend consolidating to a
  fresh PQ/HYBRID output.
- **Dormant / never-spent coins** — only the hash is exposed; safer today, but the owner must be
  reachable and able to run PQ-capable software before their *single* safe spend. Unreachable
  dormant owners are the hardest problem and cannot be solved by protocol alone.
- **Coinbase / long-term holdings** — should be steered toward PQ/HYBRID outputs at creation time
  where possible.

---

## 6. Auto-migration vs opt-in

**Recommendation: opt-in, with clear warnings. Do NOT auto-migrate.**

Rationale:
- Any migration spend **reveals** the source pubkey and creates a mempool front-running window;
  forcing it on a schedule could push many users through that window at once.
- Auto-moving user funds is a custody and consent hazard and risks stranding coins whose owners
  have not upgraded.
- Opt-in lets each holder choose their moment and confirm they hold a valid PQ backup first.

Opt-in flow must surface, at minimum:
- what class the funds are moving **from** and **to**;
- that the spend **reveals the old pubkey permanently**;
- that PQ keys are **separately derived and separately backed up** (§3);
- that sending to a PQ/HYBRID address requires the recipient to run PQ-capable software.

---

## 7. Coexistence and interoperability

Legacy, PQ, and hybrid outputs **coexist indefinitely**. The network must validate all classes it
recognises and deterministically **reject** any `alg_id` it does not (never "ignore an unknown
witness"). Key interop rules:

- A wallet must **refuse to send to an address whose class the network cannot yet validate**
  (protection against building an unspendable output).
- A wallet must **refuse to send to a PQ/HYBRID address if the recipient/old client cannot spend
  it** — protection against sending to incompatible or not-yet-upgraded clients.
- Change outputs should match the wallet's chosen class, and the wallet must warn if it would
  create change of a class it cannot itself spend.

### 7.1 RPC / explorer labelling
- Every input's spend type must be surfaced by its `alg_id` label (LEGACY / PQ ML-DSA-44 /
  HYBRID …) in RPC output and in the explorer, so operators, exchanges, and users can see exactly
  which scheme authorised a spend.
- Unknown/reserved `alg_id` values must be shown as **INVALID/unrecognised**, never rendered as a
  known-good class.

---

## 8. Conceptual migration phases A–J (labels, not dates)

No phase has a date or a block height. Each phase has explicit **entry** and **exit** conditions.
Advancement is gated on conditions, not a calendar.

- **A — Prototype.** *Entry:* V3 architecture docs merged; abstract crypto interface drafted.
  *Exit:* ML-DSA-44 sign/verify wired behind the interface in a prototype build (off by default);
  versioned witness parse/serialize round-trips in unit tests.
- **B — Testnet.** *Entry:* Phase A exit met. *Exit:* PQ + HYBRID spends validate on an isolated
  testnet with the new prefix; explorer/RPC labelling shows `alg_id`; no consensus code path
  reachable on mainnet.
- **C — Independent audit.** *Entry:* Phase B stable. *Exit:* external cryptographic + code audit
  completed against `docs/PQ_AUDIT_CHECKLIST_V3.md` with findings resolved. **No audit has been
  performed yet.**
- **D — Performance & limits review.** *Entry:* audit clean. *Exit:* size/weight/limit review
  completed and benchmarks published (`docs/PQ_BENCHMARK_RESULTS_V3.md`,
  `docs/PQ_PERFORMANCE_MODEL_V3.md`) from a valid compute environment — **no unjustified weight
  discount for PQ**.
- **E — Wallet tooling.** *Entry:* limits settled. *Exit:* PQ key derivation scheme finalised and
  documented; backup/restore/descriptor/export flows cover all classes; hardware/custodian
  guidance published.
- **F — Governance gating.** *Entry:* E complete. *Exit:* an activation mechanism defined behind
  the `INT64_MAX` "never" sentinel; still **not** scheduled.
- **G — Opt-in mainnet availability.** *Entry:* governance approval + all prior exits.
  *Exit:* PQ/HYBRID outputs are spendable on mainnet **opt-in only**, legacy fully supported,
  loud user warnings in place.
- **H — Migration campaign.** *Entry:* opt-in live. *Exit:* high-exposure (reused/revealed) funds
  substantially migrated; tooling and exchange/custodian support broadly available.
- **I — Default-PQ for new funds.** *Entry:* broad support. *Exit:* new wallets default to
  PQ/HYBRID for fresh receive addresses; legacy still spendable.
- **J — Legacy deprecation (eventual).** *Entry:* overwhelming ecosystem migration + governance.
  *Exit:* legacy-spend acceptance narrowed/retired per a governance-approved, separately-documented
  process. **This is a distant, conditional endpoint, not a plan of record.**

---

## 9. User-facing warnings (must appear in tooling before any PQ action)

- "PQ is experimental / not active on mainnet" until Phase G.
- "This spend reveals your public key permanently."
- "PQ keys are backed up separately from your legacy seed" until the unified derivation scheme is
  finalised (§3).
- "The recipient must run PQ-capable software to spend this output."
- "SOST is not 'quantum-safe' today; this is a migration path, not a completed one."

---

*Author: NeoB. Research/architecture only — activates nothing.*

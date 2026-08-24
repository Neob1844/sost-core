# SOST Post-Quantum Testnet Plan (V3) — ISOLATED TESTNET ONLY

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> V3 supersedes `docs/PQ_MIGRATION_V2.md` (PR #37). This plan describes how PQ would be exercised on
> an **isolated testnet only, never on mainnet.** No timings, no dates, no heights, no audit results
> are asserted. SOST is not claimed to be quantum-safe or post-quantum secure.

---

## 1. Isolation principle

Post-quantum spend validation is exercised **exclusively on an isolated experimental testnet** that
cannot interact with mainnet:

- **Separate genesis:** a distinct testnet genesis block, so the chain shares no history with
  mainnet.
- **Separate network magic:** distinct network-magic / protocol bytes so PQ-testnet nodes and
  mainnet nodes never peer, never relay to each other, and never confuse messages (this also
  provides network-level domain separation for anti-replay — see threat model §4.5 and assumptions
  A6/A9).
- **No shared value:** testnet coins have no relationship to mainnet SOST.

Supporting locations for the prototype and its artifacts: `docs/PQ_TESTNET` (testnet
documentation), `prototype/pq/` (prototype code), and `scripts/pq_bench/` (benchmark/measurement
harness). Benchmarks produce measurements on the isolated testnet only; **no timing figures are
asserted in this document.**

---

## 2. The `SOST_EXPERIMENTAL_PQ_TESTNET_ONLY` build flag

All PQ validation code is compiled behind the build flag **`SOST_EXPERIMENTAL_PQ_TESTNET_ONLY`**:

- **Default OFF.** A standard build produces a node with no PQ validation path.
- **Must NOT compile into a mainnet node.** Mainnet release builds must leave this flag OFF; the PQ
  validation code must be absent from the mainnet binary, not merely disabled at runtime.
- **Visible warnings.** When the flag is ON, the build and the running node emit prominent warnings
  that this is an experimental, testnet-only, non-consensus build.
- **Insufficient alone to change consensus.** Even with the flag ON, consensus is *not* changed:
  activation still requires a real height, which remains the `INT64_MAX` sentinel
  (`PQ_ACTIVATION_HEIGHT = INT64_MAX`, the same "never active" pattern as `POPC_V15_ACTIVATION_HEIGHT`
  and `atomic_swap_htlc_active_at`). The flag enables *exercising* PQ on an isolated network; it does
  not arm any activation. See `docs/PQ_ACTIVATION_PLAN_V3.md`.

The flag and the `INT64_MAX` sentinel are two independent locks: the flag controls *what compiles*,
the sentinel controls *whether any activation predicate can ever fire*. Neither alone, and not both
together, changes mainnet consensus in this research PR.

---

## 3. What to test on the isolated testnet

### 3.1 Primitive correctness
- **Keygen / sign / verify** for ML-DSA-44 (`0x01`), against FIPS 204 fixed sizes (public key 1312,
  signature 2420). ML-DSA-65/87 reserved (`0x03`/`0x04`); SLH-DSA reserved (`0x10`).

### 3.2 Witness parsing and rejection
- **Parse acceptance** of well-formed versioned witnesses (tx version 2 envelope — PROVISIONAL).
- **Deterministic rejection** of: unknown alg-ids, `0xFF INVALID`, `RESERVED` ids, truncated
  witnesses, over-long/trailing bytes, inconsistent length prefixes, and ambiguous encodings (threat
  model §4.6/§4.7). Rejection must be deterministic across nodes — never "ignore."
- **Canonical-encoding enforcement:** non-canonical encodings rejected (malleability, assumptions
  A7).

### 3.3 Hybrid AND semantics
- **HYBRID (`0x02`)** accepts a spend only when **both** ECDSA **and** ML-DSA-44 verify over the same
  canonical message; rejects when either is missing, wrong, or substituted (threat model §4.3/§5,
  assumptions A10). Confirm OR-behaviour is impossible.

### 3.4 Size and DoS limits
- **Per-alg witness-size bounds** enforced before verification; oversized/undersized witnesses
  rejected. Confirm PQ/hybrid transactions respect consensus limits (`MAX_TX_BYTES_CONSENSUS =
  100000` `include/sost/consensus_constants.h:15`; `MAX_BLOCK_BYTES_CONSENSUS = 1000000` `:16`;
  `MAX_BLOCK_TXS_CONSENSUS = 65536` `include/sost/block_validation.h:37`; `MAX_BLOCK_TX_COUNT = 4096`
  `include/sost/mempool.h:22`; `MAX_TX_BYTES_STANDARD = 16000` `include/sost/tx_validation.h:26`).
  Per-input size grows well beyond today's 133 bytes (`src/tx_validation.cpp:77`).
- **DoS behaviour:** giant-signature bloat, costly-verify, and memory-exhaustion vectors are
  exercised (threat model §6); cheap checks (alg-id, size, encoding) must precede expensive verify.

### 3.5 Node-split behaviour
- **Mixed-version networks:** confirm that a node without the flag / below minimum version rejects
  unknown witnesses deterministically, and characterise partition behaviour so activation-time
  version signalling (see activation plan Phases D/E) is understood (threat model §9.1).

### 3.6 Wallet round-trips
- **End-to-end wallet round-trips:** create → sign → serialize → relay → validate → confirm for
  LEGACY, PQ, and HYBRID spend types on the isolated testnet, including hardware-wallet-shaped
  constraints (large keys/signatures).

---

## 4. Success / exit criteria

A testnet campaign is considered successful only when **all** of the following hold (criteria are
conditions, not dates):

1. All valid PQ/hybrid spends validate; all malformed/unknown/reserved-id witnesses are
   deterministically rejected.
2. Hybrid AND semantics proven (both-required; neither-alone).
3. Canonical-encoding and anti-malleability checks pass; no ambiguous parse found.
4. Size/DoS bounds enforced; no memory-exhaustion or unbounded-allocation path.
5. Mixed-version node-split behaviour characterised and consistent with reject-by-default.
6. Wallet round-trips succeed for all three spend types.
7. Benchmarks recorded in `scripts/pq_bench/` (measurements only — not asserted here).

Exit for the campaign feeds Phases B/C of the activation plan (public review, external audit). **No
audit has been performed at V3.**

---

## 5. Testnet results never auto-promote to mainnet

Successful testnet results **do not** activate anything on mainnet and **must not** be treated as
approval to do so:

- Testnet success is **input** to public review (Phase B) and external audit (Phase C) — not a
  substitute for them.
- Mainnet activation still requires a real height set by a **future, separate, audited consensus
  proposal** (activation plan Phase F). Until then, `PQ_ACTIVATION_HEIGHT = INT64_MAX`.
- Passing tests on the isolated testnet changes no mainnet consensus rule.

---

## 6. Status

PQ is exercised on an **isolated testnet only, never mainnet**, behind
`SOST_EXPERIMENTAL_PQ_TESTNET_ONLY` (default OFF, absent from mainnet builds). The sentinel
`PQ_ACTIVATION_HEIGHT = INT64_MAX` keeps activation inert regardless. **No audit has been
performed.** Testnet results never auto-promote to mainnet. This document changes no consensus rule
and activates nothing.

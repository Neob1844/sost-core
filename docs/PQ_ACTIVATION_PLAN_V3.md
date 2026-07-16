# SOST Post-Quantum Activation Plan (V3) — DOCS ONLY

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> **Any activation of post-quantum transaction validation is a consensus change and must NOT be
> merged as part of this research PR.**
>
> V3 supersedes `docs/PQ_MIGRATION_V2.md` (PR #37). This document is **DOCS ONLY**: it contains **no
> calendar dates and no block heights.** Phases are labelled A, B, C… and gated by *conditions*, not
> dates. SOST is not claimed to be quantum-safe or post-quantum secure.

---

## 1. Guiding rule and inert-by-construction mechanism

The activation of PQ transaction validation is a **hard consensus change**. Nothing in this research
PR — and nothing in this document — sets a real activation height or date. The prototype is kept
**inert by construction** using the same sentinel pattern already established in this codebase:

- An activation height of `INT64_MAX` means **"never active."** This is the pattern used by
  `POPC_V15_ACTIVATION_HEIGHT` and `atomic_swap_htlc_active_at`. The PQ prototype reuses it:
  `PQ_ACTIVATION_HEIGHT = INT64_MAX`.
- Because the height is `INT64_MAX`, no block ever satisfies the activation predicate, so the PQ
  validation path is unreachable on mainnet regardless of what the prototype code contains.
- The legacy inert placeholder proposal (id 8 `post_quantum`, status DEFINED, heights `-1`,
  `include/sost/proposals.h:44`) likewise activates nothing; its old "SPHINCS+/Dilithium" label is
  historical and should eventually be reworded to ML-DSA / SLH-DSA, but that reword changes no
  behaviour.

> **It is explicitly forbidden to set any real activation height in this PR.** The only permitted
> value for `PQ_ACTIVATION_HEIGHT` here is the `INT64_MAX` sentinel. A concrete height may be set
> **only** by a future, separate, audited consensus proposal — never here.

---

## 2. Conceptual activation pipeline (conditions, not dates)

The following is a conceptual ordering. Each phase is entered **only** when the prior phase's exit
conditions are met. No phase implies a date or a height.

### Phase A — Proposal
- Publish the V3 architecture: threat model, security assumptions, witness format, crypto-agility
  registry, hybrid AND semantics, testnet plan.
- Deliverable: a written, reviewable specification. Activates nothing.

### Phase B — Public review
- Open community and expert review of the specification and prototype.
- Exit condition: material design objections addressed or documented; consensus on approach.

### Phase C — External audit
- Independent external cryptographic and implementation audit (ML-DSA integration, SLH-DSA backup,
  witness parser, hybrid verifier, side channels, DoS bounds, encoding canonicality).
- **No audit has been performed at V3.** Exit condition: audit complete, findings resolved.

### Phase D — Minimum node versions defined
- Define the minimum node/wallet versions that understand the PQ witness and enforce reject-by-
  default for unknown alg-ids.
- Exit condition: released, adopted client versions available.

### Phase E — Version signalling
- Nodes/miners signal readiness (version signalling) so adoption can be measured before any
  activation predicate is armed.
- Exit condition: signalling threshold sustained (threshold set by the future separate proposal).

### Phase F — Height activation (height TBD by a future separate proposal)
- A concrete activation height is chosen **only** in a future, separate, audited proposal — **not
  here.** Until then `PQ_ACTIVATION_HEIGHT = INT64_MAX`.
- Exit condition: the separate proposal is merged with a real height; not in scope for this PR.

### Phase G — Grace period
- After the (future) activation height, a grace window during which both legacy and PQ/hybrid spends
  remain valid, to let wallets, exchanges, and hardware vendors migrate.
- Exit condition: adoption metrics (§5) reach the agreed level.

### Phase H — Rollback plan
- A predefined rollback: if a critical flaw is found post-activation, revert to legacy-only
  validation via a coordinated, versioned client release; see §4 (suspend-on-vulnerability).

---

## 3. Old-client incompatibility handling

- **Unknown alg-ids** must be deterministically REJECTED by every conforming node (never ignored),
  so that a pre-PQ client and a PQ client never diverge on whether an unknown witness is valid — the
  divergence is instead handled by minimum-version gating.
- Nodes below the minimum version (Phase D) cannot validate PQ witnesses and must not be on the
  activated network past the grace period; this is a node-upgrade-split risk (see threat model §9.1)
  and is managed by version signalling (Phase E) plus clear operator communication.
- The fixed 64+33 legacy layout (`include/sost/transaction.h:72-73`; `src/transaction.cpp:210-225`)
  remains valid for LEGACY (`0x00`) spends throughout, for compatibility only.

---

## 4. Rule surfaces touched at (future) activation

At a future activation these rule surfaces would change (each is a consensus/policy change requiring
its own review — **none change in this PR**):

- **Mempool rules:** accept/relay PQ and hybrid witnesses; enforce per-alg size bounds and cheap
  pre-verify checks; standardness limits (today `MAX_TX_BYTES_STANDARD = 16000`,
  `include/sost/tx_validation.h:26`) re-evaluated for larger witnesses.
- **Block rules:** enforce PQ/hybrid validation within consensus limits (`MAX_TX_BYTES_CONSENSUS =
  100000`, `include/sost/consensus_constants.h:15`; `MAX_BLOCK_BYTES_CONSENSUS = 1000000`, `:16`;
  `MAX_BLOCK_TXS_CONSENSUS = 65536`, `include/sost/block_validation.h:37`; `MAX_BLOCK_TX_COUNT =
  4096`, `include/sost/mempool.h:22`). Per-input size grows well beyond today's 133 bytes
  (`src/tx_validation.cpp:77`).
- **Wallet rules:** produce PQ/hybrid witnesses (tx version 2 envelope — PROVISIONAL, not active;
  today `version{1}`, `include/sost/transaction.h:109`); guidance to avoid address reuse.
- **Exchange rules:** custodial signing and withdrawal in PQ/hybrid formats; adoption tracked via
  metrics (§5).

**Suspend-on-vulnerability:** if a vulnerability in ML-DSA, SLH-DSA, an implementation, or the
witness handling is discovered at any point, activation is suspended (pre-activation) or the rollback
plan (Phase H) is executed (post-activation) via a coordinated versioned client release. A
vulnerability discovery is an automatic stop condition.

---

## 5. Adoption metrics and failure response

- **Adoption metrics:** share of nodes/miners signalling readiness; share of new outputs using
  PQ/hybrid spend types; exchange/custodian and hardware-wallet support status.
- **Failure response:** if signalling stalls, if audit findings are unresolved, or if a
  vulnerability is found, the pipeline halts at its current phase. Activation never auto-arms; it
  requires the affirmative future separate proposal in Phase F.

---

## 6. Testnet relationship

All exercising of PQ happens on an **isolated testnet only**, never mainnet, gated by the
`SOST_EXPERIMENTAL_PQ_TESTNET_ONLY` build flag (default OFF). Testnet success **never
auto-promotes** to mainnet activation. See `docs/PQ_TESTNET_PLAN_V3.md`.

---

## 7. Status

Post-quantum transaction validation is **not active on mainnet**: no activation height, no date, not
merged. The prototype is inert by construction (`PQ_ACTIVATION_HEIGHT = INT64_MAX`). **No audit has
been performed.** **Any activation of post-quantum transaction validation is a consensus change and
must NOT be merged as part of this research PR.** No real activation height may be set in this PR.
This document changes no consensus rule and activates nothing.

# V15 PoPC Model A/B — deterministic on-chain rails (DESIGN, P0)

> Status date: 2026-06-08 · **P0 = inventory + design only. No consensus code yet.**
> PoPC automation belongs to **V15 (block 20,000)**, not V14 (block 15,000). Mainnet
> stays no-op until a final, soaked, coordinated gate flip. This document is the impact
> map and phase plan we agree on BEFORE touching consensus.

PoPC = **Proof-of-Personal-Custody**: a holder commits that they hold gold-backed tokens
(XAUT / PAXG) in their own wallet (Model A) or under a supervised escrow/contract
(Model B), posts a SOST bond, and in return earns rewards + DTD-lottery eligibility.

---

## 1. Current state (audited)

**Data model** (`include/sost/popc.h`)
- `PoPCCommitment`: `id`, owner `pkh`, `eth_wallet`, `gold_token` (XAUT/PAXG), `gold_amount_mg`,
  `bond_sost_stocks`, `start_height`, `end_height`, `status`, price snapshots (`sost/gold_usd_micro`),
  audit fields (`audit_height`, `balance_observed_mg`, `response_height`).
- `PoPCStatus`: ACTIVE / COMPLETED / SLASHED / EXPIRED.
- Reward math: `POPC_DURATIONS {1,3,6,9,12}`, `POPC_REWARD_RATES {100,400,900,1400,2000}` bps,
  fee 3% (A) / 8% (B), floors 10/5 SOST, max 1,000 SOST, whale tiers, reputation→max-gold tiers,
  PUR (pool-utilization-ratio) dynamic rate via `compute_pur_bps`.

**Registry / state** (`include/sost/popc.h`, `src/popc.cpp`)
- `PoPCRegistry` is an **in-memory object persisted to `popc_registry.json`** (`save`/`load`).
- `src/sost-node.cpp`: global `g_popc_registry` at path `"popc_registry.json"`; RPC handlers
  register / complete / slash / list / status; PUR computed from `committed_rewards()` vs pool.

**On-chain pieces today** (`src/popc_tx_builder.cpp`)
- `build_bond_release_tx`, `build_reward_tx`, `build_slash_marker`. So bond movement and a slash
  marker can be expressed on-chain, but the **authoritative lifecycle/active-set lives in the JSON**.

**Model B** (`include/sost/popc_model_b.h`) — escrow-based, `EscrowStatus`, `ESCROW_REWARD_RATES
{40,150,350,550,800}`, uses `ESCROW_LOCK (0x11)` (active since block 10,000). Today "supervised":
an operator manually verifies declared Ethereum contracts. Header says "application layer only".

**DTD / lottery coupling** (`src/lottery.cpp`)
- V14 eligibility was wired to also require `has_active_canonical_popc(pkh, height)` BUT it is gated
  by `DTD_POPC_GATE_CONSENSUS_ACTIVE = false` (params.h) → the helper **short-circuits to `true`**
  (no-op). The stub explicitly says the real impl "must inspect chain-derived PoPC state and never
  touch `popc_registry.json` from this path." `DTD_POPC_ELIGIBILITY_HEIGHT = V14_HEIGHT`.

---

## 2. The core problem

`popc_registry.json` is **per-node, RPC/manual-populated, non-deterministic**. If consensus
(e.g. DTD eligibility, or auto-slash/settle) read it, two honest nodes could compute different
active sets → **chain split**. That is exactly why `DTD_POPC_GATE_CONSENSUS_ACTIVE` ships `false`.

To automate PoPC verifiably we must move the **active set + lifecycle** into **deterministic
on-chain state** that every node recomputes identically from the chain — and confront the one
genuinely hard fact: **the custody truth (a gold balance in an external ETH wallet/contract) is
off-chain and cannot be made consensus-deterministic without an oracle.**

---

## 3. Proposed design — deterministic rails + attested facts

**Principle:** consensus owns everything that is *deterministic from chain state* (registration,
bond lock, timeouts, slash/settle scheduling, eligibility recomputation, signature checks). The
*off-chain custody fact* is supplied as a **signed attestation / challenge-response**; consensus
verifies the signature and the timing deterministically, and never re-derives the external balance
itself. This keeps the chain deterministic while automating the lifecycle.

### 3.1 On-chain commitment (replaces the JSON as source of truth)
- A **PoPC register** transaction (new tx-type or typed output, gated): carries the canonical
  commitment fields, **locks the SOST bond on-chain** (a bond UTXO type, like BOND_LOCK), and
  fixes `start_height` / `end_height` / `audit` schedule from the block height (deterministic).
- `commitment_id = sha256(canonical terms)` — already the model; make it the on-chain key.

### 3.2 Lifecycle as on-chain events (deterministic state machine)
ACTIVE → {COMPLETED | SLASHED | EXPIRED}, driven only by on-chain events + height:
- **Challenge** posted deterministically at `audit_height` (schedule derived from start/end).
- **Response** = a signed attestation tx from the holder (Model A) or supervisor (Model B) within
  `POPC_AUDIT_GRACE_BLOCKS (288)`. Consensus verifies the signature + that it lands in the window.
- **No valid response in grace → auto-SLASH** (deterministic; bond forfeited per rules).
- **At `end_height` with good standing → auto-SETTLE**: bond release + reward tx, amounts fixed by
  the committed terms (no node discretion).
- **EXPIRED** for unredeemed/edge states.

### 3.3 `chain_active_popc_set(height)` — the pure recompute
A pure function that rebuilds the active set from chain state (registrations minus
completed/slashed/expired up to `height`), replacing both `popc_registry.json` and the
`has_active_canonical_popc` stub. DTD eligibility then reads THIS, never the JSON. Must be
reorg-safe (recomputed from the active chain, no caching) — same discipline as Gold Vault G4/G5.

### 3.4 The off-chain custody fact (the hard part)
- **Model A (personal custody):** consensus cannot read an ETH balance. The holder periodically
  posts a **signed self-attestation** (optionally a verifiable proof) of holding `gold_amount_mg`
  of `gold_token` in `eth_wallet`. Consensus checks signature + timeliness; the economic deterrent
  is the **bond** (false attestation → reputational/again-slashable, and the bond is at risk).
  This is honest about limits: PoPC proves *commitment + a signed claim under bond*, not an
  oracle-verified balance. Optional later: an attester/oracle set (beacon-style N-of-M) raises
  assurance without breaking determinism.
- **Model B (supervised):** a designated supervisor/attester key (e.g. Beacon II-A, like G5)
  signs the verification of the declared external contract; consensus verifies that signature.
  This is the natural automation of today's manual "operator verifies" step.

### 3.5 No bridges
PAXG/XAUT live on Ethereum; we do NOT bridge them. The user keeps their own ETH account; PoPC only
records the SOST-side commitment + bond + attestations. (OTC/P2P atomic swap is a separate V15 item.)

---

## 4. Consensus vs policy/UI boundary
- **Consensus:** on-chain commitment + bond lock; deterministic audit/slash/settle schedule;
  attestation signature verification; `chain_active_popc_set(height)`; DTD eligibility reading it;
  reward/bond amounts fixed by committed terms; all gated.
- **Policy / UI / off-chain:** quoting rewards, reputation display, the tooling that actually checks
  an ETH balance and helps the user produce an attestation, mempool relay policy. `popc_registry.json`
  is demoted to a **node-local cache/index**, never consensus input.

---

## 5. Gating & safety
- New `POPC_*_ACTIVATION_HEIGHT` ships **DEFERRED (INT64_MAX)** on mainnet → `→ V15_HEIGHT` only in
  the final commit; testnet (`-DSOST_TESTNET_FORKS`) activates at `V15_HEIGHT` for dry-run.
- `DTD_POPC_GATE_CONSENSUS_ACTIVE` stays `false` until `chain_active_popc_set` exists, is tested,
  soaked and replay-byte-identical. Pre-activation behaviour byte-identical (same discipline as
  W1–W4). Auto-slash/settle wired into `process_block` only behind the gate.

---

## 6. Risks
- **Off-chain truth gap** (biggest): a signed self-attestation is not an oracle-verified balance.
  Mitigation: bond at risk, slashing, optional attester set later; market PoPC honestly as
  "custody commitment under bond + signed claim," never "proven reserves."
- **Determinism of the schedule** under reorg — must recompute from chain like G4/G5.
- **Coinbase/tx-shape surface** — register/attest/slash carriers add consensus surface; gate + test
  exactly like the Gold Vault markers (W2/W4b).
- **Scope creep** — keep Model B supervised-attestation minimal in V15; full event-listener
  automation can follow.

---

## 7. Implementation phases (after this design is accepted)
- **P1** ✅ DONE — pure modules `include/sost/popc_v15.h` + `src/popc_v15.cpp` (+ `test-popc-v15`):
  gated activation (`POPC_V15_ACTIVATION_HEIGHT` INT64_MAX mainnet / V15_HEIGHT testnet), the
  canonical `PopcV15Commitment` + deterministic `popc_v15_commitment_id`, `PopcV15Status`
  (Pending/Active/Expired/Slashed/Settled), pure lifecycle helpers (min-bond, term, expiry,
  audit schedule/`next_audit`/`audit_due`, `slash_eligible` with the 288-block grace, `settle_eligible`),
  the attestation digest, and ECDSA `verify_attestation` + `pubkey_pkh`/`pubkey_is_owner` (Model A
  self-attestation binding vs Model B supervisor key). `chain_active_popc_set` declared as the
  future interface only. **No node wiring, no DTD-gate change, mainnet no-op.** Tests: mainnet
  29/29 + testnet 29/29 (commitment id, bond/term, lifecycle, slash grace, attestation sign→verify
  + all rejections, Model A vs B, gating). full ctest 69/69; in the CI hard-gate. This is the PURE
  BASE — not enforcement.
- **P2** — `chain_active_popc_set(height)` pure recompute + tests (reorg-safe), replacing the
  `has_active_canonical_popc` stub behind the gate.
- **P3** — on-chain carriers (register/attest/slash/settle) with gated tx/coinbase-shape rules,
  byte-identical pre-activation (mirror W2/W4b).
- **P4** — wire auto-audit/slash/settle into `process_block` (gated); DTD eligibility reads the
  chain set. Cross-validator + determinism tests (mirror B3).
- **P5** — testnet soak across V15_HEIGHT + replay; then the coordinated flip.

## 8. Tests needed
- Reward/schedule math (pure), attestation sign→verify + all rejections, `chain_active_popc_set`
  determinism + reorg recompute, gated carrier acceptance (pre/post activation), end-to-end
  lifecycle (register→audit→response/slash→settle) with zero RPC, mainnet replay byte-identical,
  cross-validator agreement.

> **Decision needed from operator before P1:** confirm the Model A custody model — *signed
> self-attestation under bond* (deterministic, honest) vs waiting for an attester/oracle set. The
> design above assumes self-attestation-under-bond now, oracle optional later.

# Gold Vault Governance Hardening — Implementation Plan (DESIGN / NOT ACTIVE)

**Status: DESIGN / NOT ACTIVE.** This document is a build plan. It activates nothing,
moves no funds, adds no consensus rule and deploys nothing. It describes how to turn the
Gold Vault from *"narrative lock"* into a **real, consensus-enforced, community-governed
reserve**.

---

## 0. The decision this implements (founder, 2026-07)

The Vault stops being *"immutable · cannot be spent"* and becomes **GOVERNED**:

```
Gold Accumulation compartment  (≥ 50%)  → reserved for tokenized gold, LOCKED long-term
                                          (no rush — years is fine).
Growth / Listing compartment   (≤ 50%)  → spendable ONLY via weighted holder vote
                                          + guardian veto + caps + timelock + registry.
```

**The mother rule (target):**
```
Nothing leaves the Vault on a single key. Not the founder, not a key leak, not a whale,
not a simple majority alone. It leaves ONLY with:
   weighted holder approval + allowlisted destination + weekly cap
   + timelock + public registry + no guardian veto.
```

---

## 1. Honest starting point (what is TRUE today)

- The Vault holds ~22,510 SOST (25% of every block) at `sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d`.
- The consensus spend-governance (G1–G5) is **DEFERRED** (`GV_SLICE1_ACTIVATION_HEIGHT = INT64_MAX`).
  While deferred, `gv_slice1_check_block_spend` is a **no-op** (`src/block_validation.cpp:365`),
  so a normal spend of a Vault UTXO signed with the `gold_vault.json` key **would be accepted**.
- **→ Today the "🔒 CONSTITUTIONAL LOCK · cannot be spent" shown in the explorer is NARRATIVE,
  not consensus-enforced.** This plan's #1 job is to make the lock **REAL (fail-closed)** and
  then add the governed spend path on top.

---

## 2. Components — what exists vs what to build

| Component | Today | To do |
|---|---|---|
| **G1/G2 destination allowlist** (`gold_vault_slice1.h`) | scaffolded, deferred | populate destinations + wire fail-closed |
| **G3a per-spend cap** | wired, deferred | set value |
| **G3b cumulative cap + rate-limit** | **WIRED** (PR #29, derived from chain, reorg-safe) | set values |
| **G5 transitional guardian veto** (`gv_g5.h`) | wired, deferred | set the guardian set (2-of-3 / 3-of-5) |
| **Fail-closed Vault lock** | ❌ NOT built | NEW — reject ANY Vault spend not satisfying the governed path |
| **Compartment accounting (50 gold / 50 growth)** | ❌ NOT built | NEW — track cumulative gold-vs-growth outflow, enforce ≤50% growth |
| **Snapshot balance** (`getbalanceatheight`) | ❌ NOT built | NEW indexer/RPC — **the blocker** for weighted voting |
| **Vote collection + tally** | partial — `GVOTE` wallet signature exists (non-binding) | build tally + publish, verifiable |
| **Execution bridge (vote → authorized spend)** | ❌ NOT built | NEW |
| **Public Protocol Registry** | prepared (empty) | wire every operation |

The G-gates are the *enforcement* layer (already largely scaffolded); the holder vote is the
*decision* layer (mostly to build). The old G4 "miner-signaling" is **superseded** by
holder-weighted voting — **no miner-block voting**.

---

## 3. Architecture decision — off-chain votes + consensus-enforced rails

Two ways to bind a vote to a spend:

- **(A) Off-chain votes + consensus-enforced rails (RECOMMENDED for now).** Votes are
  collected off-chain (wallet `GVOTE` signatures), the tally is computed against the snapshot
  and **published** so anyone can recompute and verify it. Consensus makes the Vault
  **fail-closed**: a spend is rejected unless it goes to an allowlisted destination, within
  caps, after the timelock, carrying a valid **guardian authorization** and not vetoed. The
  vote *authorizes* the executor; the executor **cannot** misdirect (allowlist), drain (caps),
  rush (timelock) or act while vetoed (guardian). Pragmatic, strong, shippable.
- **(B) Fully on-chain votes + consensus tally (later, ideal).** Votes posted on-chain,
  consensus computes the weighted tally against snapshot state and only then permits the spend.
  Trustless end-to-end but much heavier (snapshot balances become consensus state). Deferred.

**Trust boundary of (A):** the guardian(s) honour the *published* vote. That trust is bounded
by allowlist + caps + timelock + public registry + the fact the whole tally is publicly
recomputable. A dishonest executor still cannot send funds anywhere bad or drain the reserve.

---

## 4. Build phases (each height-gated / inert until the coordinated activation)

```
Phase 0 — Foundations
  • getbalanceatheight(address, height) indexer/RPC   [THE blocker]
  • votable-supply denominator (exclude Vault, PoPC pool, burn/genesis)

Phase 1 — Voting (off-chain, verifiable)
  • extend GVOTE: collect signed YES/NO, verify signature + snapshot weight
  • tally + publish; proposal lifecycle Draft→Open→Passed/Failed→Timelock→Executed
  • activate the explorer "Strategic Reserve Governance Vote" module for REAL (was preview)

Phase 2 — Fail-closed Vault lock  [the blindaje]
  • wire G1/G2 allowlist + G3a/G3b caps + G5 guardian as FAIL-CLOSED:
    a Vault-input tx is REJECTED unless it satisfies ALL of them
  • populate the operator values (see §5)

Phase 3 — Compartment accounting
  • track cumulative outflow tagged gold vs growth; enforce growth ≤ 50%, gold ≥ 50%
  • per-compartment weekly cap (≤ 1%)

Phase 4 — Execution bridge + registry
  • passed+published vote + guardian co-sign → authorizes the spend tx
  • mandatory Public Protocol Registry entry per operation

Phase 5 — Ship
  • testnet soak (non-zero sentinels, exercise every reject e2e)
  • coordinated activation fork: flip GV_SLICE1_ACTIVATION_HEIGHT INT64_MAX → future height
    (same playbook as V14.5); byte-identical below the height
```

---

## 5. Open operator decisions (MUST be filled before activation)

- **Allowlist destinations** — the Ethereum Safe address(es) + verified listing/provider
  addresses. (G1/G2 fail-closed against these.)
- **Guardian set** — who holds the veto (recommend 2-of-3 / 3-of-5; founder is one, not the only).
- **Thresholds** — quorum 15% of votable SOST · approval 51% YES weighted · weekly cap ≤1%
  per compartment · timelock 72h. (Emergency track: ≥90% / ≥25% quorum / verified emergency Safe.)
- **Snapshot definition** — `snapshot_height = voting_start − 1`; votable-supply exclusions.
- **Votes on-chain vs off-chain** — start (A); revisit (B) later.
- **Narrative update** — when the lock becomes real, change the explorer wording
  *"immutable · cannot be spent"* → *"governed · spendable only via weighted vote + guardian
  + timelock"*. **Do NOT change the wording until the fail-closed rule is live.**

---

## 6. Sequencing vs liquidity (important — read this)

**This is weeks of engineering. Liquidity does NOT wait for it.** Immediate funding comes from
selling the founder's *own* SOST via the (already-working, open-to-all) atomic swap in a private
OTC round — that path never touches the Vault. This plan runs **in parallel** and delivers the
long-term *"sound / secure"* structure: a Vault that literally cannot be spent except by a
transparent, capped, time-locked, community-approved, guardian-checked process.

```
Now (days):     atomic-swap test + founder gold seed + OTC round   → liquidity, no Vault touch
In parallel:    this plan (Phases 0→5)                              → blindaje real del Vault
Then:           narrative "immutable" → "governed", once the rule is live and tested
```

## 7. What this plan does NOT do

Adds no active consensus rule; moves no funds; changes no wording yet; deploys nothing. Every
gate stays at `INT64_MAX` until a separate, tested, coordinated activation commit. Related:
[`GOLD_METALS_RESERVE_POLICY.md`](GOLD_METALS_RESERVE_POLICY.md),
[`GOLD_VAULT_SIGNAL_DESIGN.md`](GOLD_VAULT_SIGNAL_DESIGN.md),
[`GOLD_VAULT_GOVERNANCE_AUTOMATION.md`](GOLD_VAULT_GOVERNANCE_AUTOMATION.md),
[`FOUNDER_SEED_RESERVE_AND_FORGE_PAYMENT.md`](FOUNDER_SEED_RESERVE_AND_FORGE_PAYMENT.md).

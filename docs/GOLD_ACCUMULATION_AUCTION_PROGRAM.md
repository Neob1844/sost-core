# Gold Reserve Forge — Design (NOT ACTIVE)

> **File note:** the public product name is **Gold Reserve Forge**. This file keeps
> its original path (`GOLD_ACCUMULATION_AUCTION_PROGRAM.md`) so already-published
> links do not break; it may be renamed later with clean redirects. "Auction /
> window / RFQ / sealed-bid" appear below only as *implementation mechanics*, never
> as the product's public branding.

**Status: PLANNED / NOT ACTIVE.** This is a design/policy document only. It activates
nothing, moves no funds, runs no window, mints no token, and deploys no smart
contract.

> The Gold Vault accumulates SOST today. No Forge exists, no SOST is being sold, and
> no tokenized-gold reserve has been created.

Related: [`GOLD_METALS_RESERVE_POLICY.md`](GOLD_METALS_RESERVE_POLICY.md),
[`TOKENIZED_GOLD_RESERVE_SAFE_DESIGN.md`](TOKENIZED_GOLD_RESERVE_SAFE_DESIGN.md),
[`V13_GOLD_VAULT_GOVERNANCE_GATES.md`](V13_GOLD_VAULT_GOVERNANCE_GATES.md).

---

## 1. What the Gold Reserve Forge is (and is not)

**The Gold Reserve Forge converts a limited amount of the SOST Gold Vault balance
into tokenized gold reserve assets (PAXG / XAUT), progressively and verifiably.** It
is a *reserve-conversion framework*, **not a token sale**.

- **It does not mint new SOST.** Only existing Gold-Vault SOST is converted.
- **It does not create a claim on gold.** The reserve belongs to the protocol.
- **It is not a peg.** The reserve ratio is an observable metric, not a redemption right.
- **It is not a dividend, yield, or investment return.**
- **It is planned / not active.**

**Narrative frame:** *We are not selling SOST. We are forging a verifiable
tokenized-gold reserve* — converting reserve SOST into gold, one publicly-proven
operation at a time.

---

## 2. Core rules

1. The Forge is **NOT ACTIVE**.
2. It converts a **limited, capped** amount of Gold-Vault SOST into tokenized gold.
3. **Settlement is atomic.** Each conversion executes as a **SOST↔PAXG/XAUT atomic
   swap (HTLC)** — the SOST↔EVM atomic-swap infrastructure already live from V14.
   Both legs settle together or neither does; there is no "pay and trust". The gold
   leg is delivered **directly into the Tokenized Gold Reserve Safe**.
4. **No intermediate USDT/USDC staging.** Settlement is PAXG/XAUT → Safe, full stop.
5. Every operation is published as a **Forge Proof** in the Protocol Registry.
6. **No AMM. No CEX dependency.**
7. **One-way / accumulation-only:** the protocol acquires gold; it does not run a
   two-way market or buy SOST back.
8. First phase is **founder-only**; wider participation is **whitelisted**; any fully
   public phase happens **only after** legal/compliance review.

---

## 3. Pricing — discovered, not discounted

SOST has no market price yet, so the Forge **discovers** a price rather than offering
a "discount" (a discount against a non-existent reference would be meaningless and
regulatorily dangerous):

- **Mechanic:** sealed-bid / RFQ. Approved participants submit a private offer
  (SOST wanted, PAXG/XAUT offered). At window close the best valid bid is selected and
  settled atomically.
- **Floor:** a **reserve price derived from the reserve ratio** (tokenized gold in the
  Safe ÷ SOST supply), not an arbitrary number. A bid below the floor does not execute.
- **Honesty:** early windows are **plumbing + signal**, not a market price. Real price
  discovery only begins in the whitelist phase, at small size. **We never present the
  Forge as a discount or a bargain.**

---

## 4. Policy parameters (proposed, not enforced)

| Parameter | Value |
|---|---|
| Max **weekly** conversion | `min(500 SOST, 0.5% of Gold Vault SOST balance)` |
| Max **monthly** conversion | `2% of Gold Vault SOST balance` |
| Accepted settlement assets | **PAXG (primary), XAUT (secondary)** |
| Settlement | **Atomic swap (HTLC)**, gold leg → **Ethereum Safe multisig only** |
| Reserve price (floor) | Derived from the **reserve ratio**; below floor ⇒ no execution |
| Release condition | Atomic — SOST releases **iff** the PAXG/XAUT leg settles into the Safe |
| Emergency stop | Guardian / governance can **pause** the Forge |

**Hard preconditions — no conversion may occur while any is false:**
- The tokenized-gold Safe multisig is **not created** ⇒ no conversion.
- **G3b** (accumulated cap / rate-limit) is **not complete/wired** ⇒ no conversion.
- Legal/compliance review is **missing** ⇒ no conversion.

---

## 5. Flow

```
SOST Gold Vault
   ↓  Forge Window (capped, framework-approved — not a per-op vote)
Atomic swap (HTLC): SOST  ⇄  PAXG/XAUT
   ↓  (both legs settle together, or neither)
Tokenized Gold Reserve Safe   ← gold leg lands here
   ↓
Forge Proof published in the Protocol Registry
```

---

## 6. Staged activation plan (by block height)

Conservative rollout: a founder-only test before anything limited, a public phase only
much later. **Being breakthrough is not running faster than the brakes.**

> *A founder-only reserve-conversion test is targeted **no earlier than block 20,000**,
> subject to Safe setup, legal review and internal approval. A limited Gold Reserve Forge
> **may be considered no earlier than block 25,000, only if** the founder test, legal review
> and registry process are successful. Public participation remains a future step, dependent
> on legal/compliance review. None of these are commitments or guaranteed activation dates.*

### Phase 1 — no earlier than block 20,000: FOUNDER TEST (subject to review)

```
Gold Reserve Forge:        FOUNDER TEST
Public participation:      NOT ACTIVE
Gold Vault normal spending: NOT ACTIVE
```

- **1 symbolic operation**, founder only, **50–100 SOST**.
- Settlement **only in PAXG**, atomic swap, gold leg into the future Safe.
- **Mandatory** Forge Proof in the Protocol Registry.
- Not allowed: no public participation, no AMM, no CEX, no automatic window, no
  anonymous participants, no investment marketing, no profit promise, no claim on gold.

Purpose — prove the full circuit end-to-end (atomic swap → gold in Safe → Forge Proof).

### Phase 2 — block 20,000–25,000: OBSERVATION

Public status stays: **"Founder-only reserve-conversion test. Public Forge not active."**
Review: does the Safe work? is the Forge Proof clear/auditable? any flow errors? any
legal/commercial confusion? does the community understand it?

### Phase 3 — no earlier than block 25,000: LIMITED (may be considered, only if the test passes)

```
Gold Reserve Forge:        LIMITED
```

- Weekly cap `min(500 SOST, 0.5%)`, monthly cap `2%`.
- PAXG primary, XAUT secondary.
- Atomic-swap settlement, gold → Safe only.
- Emergency stop active.
- **Whitelist / sealed-bid first — not a public AMM.**

### Later — public participation

Only with legal/compliance and a larger community. Same caps, same atomic settlement,
same Forge Proofs. Not scheduled.

---

## 7. Forge Proofs (the public artifact)

Every completed conversion publishes a **Forge Proof** — an on-chain-verifiable record,
the centrepiece of the Forge (the proof is the protagonist, **not** a countdown):

- SOST txid
- Ethereum txid
- PAXG/XAUT amount
- Safe address
- timestamp
- reserve price used
- status

A **Reserve Growth Timeline** aggregates the proofs; a **Proof-of-Reserve Meter** shows
only factual metrics (Gold-Vault SOST balance, PAXG/XAUT Safe balance, number of Forge
Proofs). None of this implies a peg, backing guarantee, redemption right, or value.

---

## 8. Preconditions before Phase 1 can even be scheduled

```
Status: NOT ACTIVE
Requires:
- G3b complete (accumulated cap / rate-limit wired + cross-validated)
- Gold Vault Governance closed (G1–G5)
- Safe multisig created (PAXG/XAUT custody, timelock, allowlist)
- legal / compliance review
- first symbolic test
- Protocol Registry live for reserve operations
- public notice period
```

---

## 9. Optional non-financial participation (carefully bounded)

Participation may carry **reputational / transparency** recognition only — never a
financial promise:

- Public **"Reserve Supporter"** acknowledgement in the Protocol Registry (optional).
- Priority access in future OTC/Forge windows.
- Early access to reserve reports.
- Reputational badge / transparent participation record.

**Prohibited framing (must never appear):** "buy now and you will gain", "guaranteed
price", "yield/return", "rights over the gold", "share in the vault", "gold-backed
SOST", dividend, or equity.

> ⚠️ **The Gold Reserve Forge must not be marketed as an investment return, a claim on
> gold, equity, a dividend, a yield, or a guaranteed profit.**

---

## 10. What the Forge deliberately does NOT do

- No public SOST/PAXG or SOST/XAUT AMM.
- No CEX dependency.
- No automatic conversion without governance.
- No non-atomic "pay and trust" settlement.
- No USDT/USDC staging with a "we'll buy gold later" promise.
- No new SOST minted; no claim on gold created.

---

## 11. Regulatory note

Even under the "Forge" framing, a public conversion window can resemble a primary
token offering or a crypto-asset service — regulators look at substance, not name. In
the EU, MiCA (Regulation (EU) 2023/1114) regulates crypto-asset offers and services in
phases from 2024/2025. Nothing here activates without prior legal/compliance review.
This document is not legal advice.

---

**Bottom line:** it is not a sale and not an auction as a product — it is a **Gold
Reserve Forge**: a sober, atomic, capped, publicly-proven conversion of reserve SOST
into verifiable tokenized gold. Off until every precondition in §8 is satisfied.

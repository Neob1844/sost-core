# Gold Accumulation Auction Program — Design (NOT ACTIVE)

**Also referred to as:** *SOST Reserve Gold Accumulation Program*.

**Status: NOT ACTIVE.** This is a design/policy document only. It activates nothing,
moves no funds, runs no auction, and deploys no smart contract. It defines *how* a
future, tightly-constrained mechanism would convert a limited amount of the SOST
Gold Vault balance into tokenized gold — **if and only if** the preconditions in §6
are all met.

> The Gold Vault accumulates SOST today. No auction exists, no SOST is being sold,
> and no tokenized-gold reserve has been created.

Related: [`GOLD_METALS_RESERVE_POLICY.md`](GOLD_METALS_RESERVE_POLICY.md),
[`V13_GOLD_VAULT_GOVERNANCE_GATES.md`](V13_GOLD_VAULT_GOVERNANCE_GATES.md).

---

## 1. What this is (and is not)

**It is:** a *framework policy*, approved once, that would permit small, capped,
rule-bound auctions of SOST from the Gold Vault, settled **only** in tokenized gold
delivered into a public Safe multisig, with every operation published.

**It is not:**
- Not "sell whenever someone votes each time." The community/miners do **not** vote
  on each individual sale — they approve the framework; individual auctions run
  inside its strict caps.
- Not a public AMM (no SOST/PAXG or SOST/XAUT pool at launch).
- Not a CEX-dependent sale.
- Not automatic selling without governance.
- Not a promise to hold gold. It is a mechanism to convert reserve value **into**
  verifiable tokenized gold **progressively**.

**Narrative frame:** *SOST does not promise to have gold. SOST accumulates value and
converts it progressively into verifiable tokenized reserve.*

---

## 2. Core rules

1. The program is **NOT ACTIVE**.
2. It is a future controlled mechanism to convert a **limited** amount of the SOST
   Gold Vault balance into tokenized gold.
3. Each auction sells a **small, capped** amount of SOST.
4. **Settlement must be in PAXG/XAUT delivered directly to the Tokenized Gold
   Reserve Safe** (Ethereum multisig). No intermediate USDT/USDC "we'll buy gold
   later" staging.
5. **SOST is released only after the PAXG/XAUT transfer into the Safe is verified.**
   Delivery-versus-payment: no gold in the Safe ⇒ no SOST released.
6. Every operation is registered in the **Protocol Registry** (public).
7. **No AMM at launch.**
8. **No CEX dependency at launch.**
9. First phase is **founder-controlled / whitelisted / OTC-style** (known buyers,
   small amounts, fully recorded).
10. A **public** auction happens **only after** legal/compliance review.

---

## 3. Policy parameters (proposed, not enforced)

| Parameter | Value |
|---|---|
| Max **weekly** sale | `min(500 SOST, 0.5% of Gold Vault SOST balance)` |
| Max **monthly** sale | `2% of Gold Vault SOST balance` |
| Accepted settlement assets | **PAXG (primary), XAUT (secondary)** |
| Settlement destination | **Ethereum Safe multisig only** |
| Minimum price | Auction executes **only if a floor/reserve price is met** |
| Emergency stop | Guardian / governance can **pause** the program |
| Timelock | Delay before any operation executes |
| Release condition | SOST released **only after** verified PAXG/XAUT receipt in the Safe |

**Hard preconditions — no sale may occur while any is false:**
- The tokenized-gold Safe multisig is **not created** ⇒ no sale.
- **G3b** (accumulated cap / rate-limit) is **not complete/wired** ⇒ no sale.
- Legal/compliance review is **missing** ⇒ no sale.

---

## 4. Flow

```
SOST Gold Vault
   ↓ weekly capped auction (framework-approved, not per-sale vote)
Buyer pays PAXG / XAUT
   ↓
Ethereum Safe multisig  (receipt verified)
   ↓
SOST released to the buyer   (only after receipt verified)
   ↓
Protocol Registry publishes everything
```

---

## 5. Staged activation plan (by block height)

The program is introduced conservatively, with a founder-only test before anything
limited, and a public auction only much later. **Being breakthrough is not running
faster than the brakes.** In one line:

> *V15 introduces a founder-only reserve conversion test. If successful, a limited
> Gold Accumulation Program may begin around block 25,000. A public auction remains
> a future step, dependent on legal/compliance review.*

### Phase 1 — V15 / block 20,000: FOUNDER TESTING

```
Gold Accumulation Program: FOUNDER TESTING
Public auction:            NOT ACTIVE
Gold Vault normal spending: NOT ACTIVE
```

Allowed:
- **1 symbolic operation**, administrator/founder only.
- Very small amount: **50–100 SOST**.
- Settlement **only in PAXG** (XAUT possibly later), delivered to the future
  Ethereum Safe multisig.
- **Mandatory** record in the Protocol Registry.

Not allowed: no public auction, no AMM, no CEX, no automatic weekly sale, no
anonymous buyers, no investment marketing, no profit promise, no claim on the gold.

Purpose — prove the full circuit end-to-end:
```
Gold Vault SOST → founder-only operation → founder delivers PAXG
→ PAXG enters Safe multisig → SOST released → everything publicly recorded
```

### Phase 2 — between block 20,000 and 25,000: OBSERVATION

Public status must read: **"Founder-only reserve conversion test. Public program not
active."** Review before going further:
- Does the Safe work? Is the public record clear and auditable?
- Any flow errors? Any legal/commercial confusion? Does the community understand it?

### Phase 3 — block 25,000: LIMITED ACTIVE (only if the test passes)

```
Gold Accumulation Program: LIMITED ACTIVE
```

- Weekly cap: `min(500 SOST, 0.5% of Gold Vault balance)`.
- Monthly cap: `2% of Gold Vault balance`.
- PAXG primary, XAUT secondary.
- Safe multisig destination only.
- Emergency stop active.
- **Whitelist / OTC first — not a public AMM.**

### Later — public / open auction

Only when legal/compliance and a larger community are in place. Same caps, same
delivery-versus-payment, same public registry. Not scheduled.

---

## 6. Preconditions before Phase 1 can even be scheduled

```
Status: NOT ACTIVE
Requires:
- G3b complete (accumulated cap / rate-limit wired + cross-validated)
- Gold Vault Governance closed (G1–G5)
- Safe multisig created (PAXG/XAUT custody, timelock, whitelist)
- legal / compliance review
- first symbolic test
- Protocol Registry live for reserve operations
- public notice period
```

---

## 7. Optional non-financial participation (carefully bounded)

Participation may carry **reputational / transparency** recognition only — never a
financial promise:

- Public "Reserve Supporter" acknowledgement in the Protocol Registry.
- Priority access in future OTC windows.
- A small rule-bound discount **only** if strict conditions are met.
- Reputational badge / transparent participation record.
- Option to buy SOST and voluntarily lock it in PoPC once Bond v2 is ready.

**Prohibited framing (must never appear):** "buy now and you will gain", "guaranteed
price", "yield/return", "rights over the gold", "share in the vault", dividend, or
equity.

> ⚠️ **This program must not be marketed as an investment return, claim on gold,
> equity, dividend, or guaranteed profit.**

---

## 8. What we will NOT do

- No public SOST/PAXG AMM.
- No public SOST/XAUT AMM.
- No automatic sale without governance.
- No direct sale from the vault to anyone.
- No USDT/USDC staging with a "we'll buy gold later" promise.

Settlement must be **PAXG or XAUT → Safe multisig** directly, so the destination is
never in doubt.

---

## 9. Regulatory note

A public token auction can resemble a primary token sale or a crypto-asset service.
In the EU, MiCA (Regulation (EU) 2023/1114) regulates crypto-asset offers and
services in phases from 2024/2025. Nothing in this program is activated without
prior legal/compliance review. This document is not legal advice.

---

**Bottom line:** the correct name is not "automatic sale" — it is a **controlled
gold-accumulation program**. Serious, gradual, transparent, and off until every
precondition in §6 is satisfied.

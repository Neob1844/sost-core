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

## 5. Two-phase rollout

**Phase 1 — Founder-controlled / whitelist / OTC auction.** Known counterparties,
small amounts, floor price, settlement to the Safe, every op in the Registry. No
aggressive marketing.

*Example first operation (illustrative only, not scheduled):* a symbolic auction of
**100–250 SOST**, settled in **PAXG**, fully recorded, no marketing.

**Phase 2 — Public / more open auction.** Only after legal/compliance clears it.
Same caps, same delivery-versus-payment, same public registry.

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

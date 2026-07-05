# Founder Seed Reserve + Forge Payment Policy — Design (PLANNED / NOT ACTIVE)

**Status: PLANNED / NOT ACTIVE.** Design/policy document only. It activates nothing,
moves no funds, sells nothing, deploys no contract and changes no consensus rule. It
describes how the protocol *could* start a tokenized-gold reserve **without creating an
official SOST price**.

**The one hard rule of this document:**

```
Publish how much GOLD is in the Safe.
NEVER publish a $/SOST figure (not even as a "reference").
```

Why: any per-SOST number — even labelled "reference, not price" — will be read by the
market as a price or a floor, and it drags the token toward a *backed / redeemable*
interpretation. SOST has no market yet, so such a number would set an anchor that later
constrains the project. See canonical policy:
[`GOLD_METALS_RESERVE_POLICY.md`](GOLD_METALS_RESERVE_POLICY.md).

---

## 1. Founder Seed Reserve

The founder **may** contribute PAXG/XAUT to the protocol Safe to bootstrap the reserve.

- It creates the **first protocol-held tokenized gold**.
- It does **NOT** create an official SOST price.
- It does **NOT** create a peg.
- It does **NOT** create a redemption right.
- It does **NOT** make SOST gold-backed.

**Canonical framing (use verbatim):**

> *This creates the first protocol-held tokenized gold reserve. It does not make SOST
> gold-backed, pegged, or redeemable.*

The Founder Seed is a **treasury fact** (gold the protocol holds), not a claim attached
to the token.

---

## 2. What IS published (per seed / operation)

Each Founder Seed or reserve operation is recorded in the Public Protocol Registry with:

- **Safe address** (Ethereum) — `0x…`
- **Asset** — PAXG / XAUT (only)
- **Amount** — token quantity
- **Estimated grams** and **USD value** (of the gold held)
- **Proof tx** — the EVM txid funding the Safe
- **Date**
- **Registry entry** — an ID (e.g. `Founder Seed Reserve #001`)

Example registry entry:

```
Founder Seed Reserve #001
Safe:          0x…              (Ethereum, multisig)
Asset:         PAXG / XAUT
Amount:        <token qty>
Est. grams:    <X g>
Est. USD:      <$ value of gold>
Proof tx:      0x…
Date:          YYYY-MM-DD
Purpose:       initial protocol-held gold reserve
Rights:        none — no peg, no redemption, no gold-backed SOST
```

The dashboard shows: **Protocol-held tokenized gold: <$ / grams>** — the amount of gold,
full stop.

---

## 3. What is NOT published (hard prohibitions)

Never publish, in any surface (site, dashboard, docs, announcements):

- **No `$/SOST`** figure of any kind.
- **No "floor price".**
- **No "backing per SOST".**
- **No "1 SOST = X gold".**
- **No redemption ratio.**

If a number would let someone compute "gold per SOST" by dividing reserve gold by a SOST
count, it does not get published. Publish gold held; do not divide it by SOST.

---

## 4. Gold Reserve Forge (future phase)

The Forge is the future mechanism to **grow** the gold reserve — it converts a **limited**
amount of Gold-Accumulation SOST into protocol-held tokenized gold.

- **Future phase**, not active.
- The **buyer pays PAXG/XAUT**; the protocol releases **limited** SOST from the **Gold
  Accumulation Reserve** compartment; the received PAXG/XAUT enters the Safe.
- **Ideally executed via Atomic Swap** (trustless: either both legs settle or both
  refund) — but **only once the atomic swap is proven** (see the founder test runbook
  [`V15_OTC_FOUNDER_TEST_RUNBOOK.md`](V15_OTC_FOUNDER_TEST_RUNBOOK.md)) **and the EVM
  contract is deployed**.
- **Until the atomic swap is proven**, any Forge operation would be **manual / OTC,
  founder-controlled and registered — not automatic.**

Forge framing (use verbatim):

> *The Forge converts limited reserve SOST into protocol-held tokenized gold. It is not a
> redemption mechanism, not a peg, and not a gold-backed claim.*

---

## 5. Gold in the Safe — enters easy, exits very hard

The tokenized gold in the Safe is **not** normal working capital.

**It may exit ONLY for:**

1. **Security migration** — move PAXG/XAUT to another **verified** Safe.
2. **Issuer risk** — if PAXG/XAUT has a serious issuer/legal problem, move or convert to
   another permitted asset.
3. **Extraordinary decision** — very high weighted approval + guardian veto window +
   timelock + public registry.

**It NEVER exits to:**

- A personal wallet.
- Any CEX.
- The founder.
- Normal expenses.

Governance for any exit follows the veto-not-spending-power model in
[`GOLD_METALS_RESERVE_POLICY.md`](GOLD_METALS_RESERVE_POLICY.md) (weighted holder vote +
time-boxed guardian veto + caps + timelock + registry).

---

## 6. Growth / Listing / Compliance — a separate compartment

Listings, legal, MiCA/compliance, audits, infrastructure and liquidity are **not** paid
from the Safe gold. They are paid from the **Growth / Listing / Compliance Reserve**
compartment (max 50%).

- Paid from **Growth**, never from the **Gold Accumulation** Safe.
- Requires its **own governance** (weighted holder vote + caps + timelock + registry).
- **More legally delicate** — sequenced after legal/compliance readiness; the Gold
  compartment (PAXG/XAUT only) comes first.

---

## Sequence (design)

```
1. (optional) Founder Seed: PAXG/XAUT -> Safe multisig 3/5. Register. Publish gold-in-Safe
   ($/grams) ONLY — never $/SOST.
2. Dashboard shows real gold in the Safe (verifiable fact), no per-SOST ratio.
3. Atomic Swap proven (founder Stages 1-3) + EVM contract deployed.
4. Then: Gold Reserve Forge via atomic swap (Gold Accumulation compartment).
5. Growth/Listing: separate compartment, own governance, when legal/compliance is ready.
```

**Nothing here is active.** No contract is deployed, no Safe is created, no funds move,
no consensus/node/wallet is touched. This document only fixes the policy and the hard
"no $/SOST" line before any of it is built.

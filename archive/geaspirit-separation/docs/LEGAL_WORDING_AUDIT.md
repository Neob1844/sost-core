# SOST public-wording legal/regulatory audit

Goal: keep all public SOST wording legally cautious — describe what SOST **is**
(a native Layer-1 PoW blockchain with fixed supply, open-source infrastructure,
on-chain verification tools, PoPC, ConvergenceX mining, and an *observable* Gold
Vault funding mechanism) and avoid wording that frames it as money, currency,
legal tender, a payment instrument, an e-money token, a stablecoin, a redeemable
gold-backed token, a guaranteed store of value, or a product promising returns.

This is an internal risk review, **not legal advice**. A qualified lawyer should
sign off before launch/marketing.

---

## A. Videos — FIXED ✅
- **SOST × GeaSpirit cut:** removed both "sovereign money" uses → "verifiable on-chain
  trust". Kept "a sovereign Layer-1 blockchain" (describes the chain architecture, not money).
- **sost_video_v01 (SOST intro):** clean — uses "Sovereign Stock Token", "Native Layer-1
  Proof-of-Work", technical framing. No "money" wording. No change needed.

## B. Website — FIXED ✅ (meaning-preserving safer synonyms)
| Was | Now | Files |
|---|---|---|
| "gold-backed position(s)" | "gold-referenced position(s)" | dex, gold-dex, otc-alpha, position-desk, position-market, community-rules, whitepaper-reader, btctalk-ann (incl. meta/OG descriptions) |
| "Gold-backed Proof-of-Work protocol" | "Gold-reserve Proof-of-Work protocol" | btctalk-ann |
| PoPC "future yield" / "sustainable yield from the PoPC Pool" | "future reward" / "sustainable rewards from the PoPC Pool" | gold-dex |
| "into gold-backed reserves" | "into a gold-funded reserve" | whitepaper |

## C. Already SAFE — keep as-is ✅ (good negated/disclaimer framing)
- **FAQ:** "Is SOST pegged to gold? **No.** … observable metric, not a redemption right …
  holders have no claim on the gold reserve." · "Can I redeem SOST for gold? **No.** …
  no redemption rights … not a financial product." → model disclaimers, keep.
- **Gold Vault / Metals Reserve** pages already use: "observable", "not a peg", "no
  redemption promise", "no price floor", "no claim on the reserve". Keep.
- "guaranteed / risk-free profit / guaranteed buyer" → almost all are **anti-scam
  warnings** (community-rules, FAQ, DEX) telling users these phrases signal scams. Keep.
- "currency" → the **price-display currency switcher** (USD/EUR/…) and CSS classes. Not a claim. Keep.
- "redeem / redeemable" → **HTLC atomic-swap** technical terms ("redeem script",
  "redeemable by Bob"). Not gold redemption. Keep.
- "stablecoin / stable value" → **comparisons / simulated price pairs / settlement rails**
  (USDT/USDC ~$1), not a self-claim. Keep.
- "gold-backed tokens (XAUT, PAXG)" / "gold-backed ERC-20" → **describing competitors**
  in a contrast that argues SOST is *different*. Defensible; left as-is.

## D. Core-narrative terms — REFINED, not gutted ✅ (do not overcorrect)
Precision, not ambiguity. SOST keeps its full identity (fixed-supply PoW L1, Gold Vault,
PoPC, store-of-value architecture, Bitcoin-inspired scarcity). We only remove wording that
implies a *promise* (peg / redemption / price floor / return / legal tender / e-money /
stablecoin / claim over the reserve). Applied:

1. **"Store of Value" → "Store-of-Value Architecture"** (index.html + whitepaper, both pillar
   tags, the compact pillar row and the "(Scarcity, …)" line). The thesis is preserved and
   explicitly framed as a **protocol design objective**, not a guarantee.
2. **Disclaimer line added** to the Pillar-4 body on both pages:
   *"No peg. No redemption right. No price floor. No investment return. No legal claim over the reserve."*
3. **"gold-backed value/channels/floor"** (self-claims) → "gold-funded reserve value" /
   "gold-reserve channels" / "observable gold-reserve reference value (not a price floor or
   guarantee)". The contrastive "gold-backed ERC-20 / tokens (XAUT, PAXG)" in btctalk-ann stay
   — they describe competitors, not SOST.
4. **"sound money" → "sound-money-inspired design"** (whitepaper). The btctalk-ann "sound money"
   uses are contrastive (they argue custodial gold tokens *fail* at it) and stay.

Approved standing framing (strong + cautious): *"SOST is designed with Bitcoin-inspired scarcity,
fixed supply and an observable Gold Vault mechanism. This does not create a peg, redemption right,
price floor, investment return or legal claim over the reserve."*

## E. GeaSpirit wording — verified ✅
GeaSpirit pages already state: "does not detect minerals underground", "never a guarantee
of discovery", "open-data triage — not legal, technical or investment due diligence",
"not a drilling substitute". The new worked-examples + engine-pass section say "surface
indicators, never confirmed ore" and "no deposit is claimed". Safe.

## Standing rule
**Allowed (the protocol identity — keep it strong):** native Layer-1 Proof-of-Work, fixed /
hard-capped supply, ConvergenceX mining, PoPC, Gold Vault / observable reserve mechanism,
**Store-of-Value Architecture** / reserve-value architecture (as a *design objective*),
Bitcoin-inspired scarcity, **sound-money-inspired design**, inflation-resistant fixed supply.

**Never imply (promise wording):** "money / currency / legal tender / payment instrument /
e-money", "stablecoin / peg / stable value", "redeemable / backed by gold / gold-backed value",
"guaranteed store of value / price floor / investment return / yield / profit", "claim over the
gold reserve". Use these **only** when explicitly negated.

When the gold / store-of-value thesis is stated, attach the disclaimer:
*"No peg. No redemption right. No price floor. No investment return. No legal claim over the reserve."*

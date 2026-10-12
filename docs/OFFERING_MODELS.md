# SOST — Offering models (Tokenize / Auction / Draw / Project Funding)

One Asset Passport (or, before the asset exists, a **Project Passport**) can be offered four ways. Only
Tokenize is a current product; Auction/Draw/Project Funding are full engines with live demos, **real-funds
execution DISABLED** until a legal framework + settlement rail exist. No consensus/node/STRATO/DTD change.

| Model | Purpose | Right / what the taker gets | Money flow | Settlement | Legal readiness | Status |
|---|---|---|---|---|---|---|
| **Tokenize** | Divide a right into units | Typed RIGHT (certificate…equity) | none in-app | future | depends on the right | **CURRENT / LIVE WEB** |
| **Auction** | Sell to the best bid | The asset to the highest valid bid | refundable bid escrow (ref → SOST quote) | SOST / external-documented / future | asset-sale + contract + AML/tax | **FUTURE / LIVE DEMO / LAB VERIFIED** |
| **Draw** | Adjudicate by verifiable draw | The asset to one ticket | ticket escrow (ref → SOST quote), refundable | future | Spanish *rifa* (DGOJ / Ley 13/2011) | **FUTURE · REGULATED / LIVE DEMO / LAB VERIFIED** |
| **Project Funding** | Finance something not built yet | Pre-purchase / debt / revenue / equity right | all-or-nothing, milestone-gated releases | future | ECSPR crowdfunding / MiFID II / CNMV PSFP (≤ €5M) | **FUTURE · REGULATORY-READY / LIVE DEMO / LAB VERIFIED** |

## Lifecycle & cross-mode
A **Project Passport** follows IDEA → FUNDING → CONSTRUCTION → OPERATION → **ASSET Passport** (history
preserved, never overwritten). The same Asset Passport can then be offered via Tokenize, Auction or Draw.

## Engines & tests (application layer)
- `website/js/asset-auction.js` — signed bids (domain `SOST_ASSET_AUCTION_V1`), refundable escrow, reserve,
  anti-sniping, state machine, highest-wins/earliest-tie, settlement separate from result. `tests/auction.test.js` 29/29.
- `website/js/asset-draw.js` — commit→freeze(campaignHash)→future-block entropy→deterministic, third-party-
  verifiable winner; refund if unsold. (DTD *philosophy*, not DTD/consensus.) `tests/offering_models.test.js`.
- `website/js/project-funding.js` — models + all-or-nothing + milestone-gated ordered releases + honest
  funded/released/escrowed accounting. `tests/offering_models.test.js`.
- Draw+Funding suite 25/25; Auction 29/29; cross-mode test proves one passport feeds Tokenize+Draw+Auction
  and a Project Passport becomes an Asset Passport.

## Reference value vs SOST
Escrow/ticket amounts are a **reference value** (e.g. 20 / 100 USDC) converted to an equivalent **SOST quote**
at entry (oracle: price, timestamp, source recorded). No fiat/USDC is custodied. Who bears the SOST price
variation between entry and close is an explicit design point to fix before any real launch.

## Legal readiness
Shown as an **AUTOMATED READINESS CHECK — NOT A LEGAL DETERMINATION**; SOST never determines legal/regulatory
classification. Real funds stay disabled for the three FUTURE models.

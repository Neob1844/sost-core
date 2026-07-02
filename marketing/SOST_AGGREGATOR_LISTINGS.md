# SOST — Aggregator listing submission pack (CoinMooner · CoinCarp · CoinCodex)

Purpose: get SOST a public, verifiable listing on the free aggregators **now**, for Google
visibility, ticker recognition, and links to explorer/code/whitepaper. These are **not**
exchanges and do **not** create liquidity or a price. Submit honestly — a native Layer-1
pre-market coin. **Never invent market cap, circulating supply, or a price.**

All figures below are verified against the repo (README.md, include/sost/params.h,
genesis_block.json). Do not alter them.

## Shared fact sheet (use for all three)

| Field | Value |
|---|---|
| Project name | SOST Protocol |
| Ticker / symbol | SOST |
| Type | **Native Layer-1 Proof-of-Work coin** (NOT an ERC-20/BEP-20/token; no contract address) |
| Chain | Own mainnet (SOST) |
| Consensus | ConvergenceX (CPU-friendly, memory-hard PoW; Transcript V2) |
| Block time | ~600 s (10 min) target |
| Genesis | 2026-03-15 18:00 UTC (`GENESIS_TIME = 1773597600`) |
| Max supply | 4,669,201 SOST |
| Circulating supply | **Do not declare a tradeable circulating supply** (no public market). If a field is required: "N/A — pre-market, no exchange market yet" |
| Emission split | 50% miner / 25% Metals Reserve / 25% PoPC Pool (constitutional at genesis) |
| Smallest unit | 1 SOST = 100,000,000 stocks |
| Address format | `sost1` + 40 hex chars (20-byte pubkey hash) |
| Signature scheme | ECDSA over secp256k1, canonical LOW-S (post-quantum migration = research, not active) |
| SLIP-0044 | Registered (own coin_type) |
| Website | https://sostcore.com |
| Explorer | https://sostcore.com/sost-explorer.html |
| Source code | https://github.com/Neob1844/sost-core |
| Whitepaper | https://sostcore.com (whitepaper reader) |
| Logo | http://sostcore.com/sost-logo.png |
| Contact | sost@sostcore.com · Telegram https://t.me/SOSTProtocolOfficial |
| Initial / current price | **N/A — pre-market native Layer 1** (leave blank or "N/A" wherever allowed) |

**One-line description (EN):**
> SOST is a native Layer-1 Proof-of-Work blockchain powered by the CPU-friendly, memory-hard
> ConvergenceX consensus engine. It is not an ERC-20, BEP-20 or token deployed on another
> chain — it has its own mainnet, explorer, wallet and miner. Addresses begin with `sost1`.

**Honest guardrails (do NOT cross):**
- No claimed price, market cap, or tradeable circulating supply until a real public market exists.
- Do not claim exchange listings, audits, or partnerships that don't exist.
- Do not claim "post-quantum secure" (it is ECDSA today; PQ is roadmap/research).

---

## 1) CoinMooner — submit now (simplest)
Submit at coinmooner.com ("Add coin"). It's a promo/voting board, not a certification.
- Name: SOST Protocol · Symbol: SOST · Chain/Platform: **Own blockchain / Native coin** (NOT BitcoinClone/BEP-20)
- Launch date: 2026-03-15
- Website / Explorer / Whitepaper / GitHub / Telegram: as above
- Audit: "Not provided" · KYC: "Not provided" (be honest)
- Description: the one-liner + "mainnet live; explorer, web wallet and CPU miner available; no exchange market yet."
- Do NOT enable "Add to MetaMask" (SOST is not EVM).

## 2) CoinCarp — submit now (form: name, ticker, logo, issue date, supply, web, source, explorer, whitepaper, description)
Fill exactly from the fact sheet. Notes:
- Coin type: Native Layer-1 coin.
- Total/Max supply: 4,669,201. Circulating: leave blank / "N/A — pre-market".
- Initial Price: `N/A — pre-market native Layer 1` (do not invent).
- CoinCarp may accept/reject without explanation — that's normal; resubmit later if needed.

## 3) CoinCodex — submit now via their "request a coin" form
- They can list a project without a market, hold it pending, or create it without price.
- Circulating supply: not declared (no market).
- When a real independent public market exists (a CEX/DEX pair + API), send an **update** with
  the pair + API so CoinCodex can read the price (this is exactly how Animica got a price from
  its NonKYC ANM/USDT market — the aggregator reads reported markets, it doesn't invent them).

---

## Why we're behind Animica (context, not a model to copy)
Animica isn't listed because it's technically better — it opened an `ANM/USDT` market on NonKYC,
packaged web/explorer/wallet/whitepaper, and **submitted to the aggregators immediately**.
Aggregators do not discover chains on their own; you must submit the form. SOST already has all
the technical pieces — we just need to submit. Do it honestly (pre-market), and add the market
feed later when one exists. We do **not** need to pay a $30k exchange listing to start existing
on aggregators.

---

*Prepared from verified repo facts. Submitting the forms is a manual, operator-only step
(each site's web form). This pack is the copy/data to paste. Keep it honest — no invented price,
cap, or circulating supply.*

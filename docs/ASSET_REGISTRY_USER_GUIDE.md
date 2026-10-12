# SOST Asset Registry — User Guide

A plain guide to registering and (optionally) tokenizing an asset. No knowledge of claims,
JSON, provenance or hashing is required — the Registry records all of that for you underneath.
For the technical contract (schema, canonicalization, vectors) see `ASSET_REGISTRY_V2.md`.

## What it does
SOST turns a real or digital asset into a **verifiable digital record** (an *Asset Passport*).
It captures what the asset is, the evidence behind it, **who declares each fact and whether it was
independently verified**, the right a token represents, and seals it into a fingerprint that anyone
can re-check and that can be anchored on the SOST chain. SOST proves integrity and existence-in-time —
**never** that a claim is legally true, and it never decides the legal classification of the asset or token.

## Register an asset in four steps (sostcore.com/sost-universal-assets.html#create)
1. **Asset** — pick a type (real estate, mining, company, commodity, equipment, IP, collectible, other),
   name it, give the jurisdiction, an estimated value and the declared owner, and (optionally) attach
   **evidence** sources (technical report, public registry, dataset, URL…). You choose the *source*;
   SOST records it as *declared* until independently checked.
2. **Rights** — say what each token represents: Certificate · Usage right · Revenue share · Sale-proceeds ·
   Ownership/equity-like · Custom. For an economic right, add the %, obligor, agreement (reference/hash),
   distribution mechanism/frequency, exit mechanism and transferability.
3. **Token** — choose the supply and decimals (1 token = 1 unit of value / round / custom). The
   **reference value per token** is only valuation ÷ supply — **not** a market price and **not** liquidity.
   Optionally add a SOST deterministic estimate (a ±15% reference band, recorded as a separate SOST-calculation
   claim, not an appraisal).
4. **Compliance & settlement** — jurisdiction, transferability and settlement method (SOST on-chain, or
   *external — documented*; SOST does not custody funds). Regulated investor controls (KYC/AML, eligibility,
   holding limits, freeze/recovery) are a **future** module — prepared, not active.
5. **Review & generate** — see the Asset → Right → Token summary, then **Generate Asset Passport**.

## Your Passport
You get a dashboard: passport integrity, a lifecycle line (REGISTERED → DOCUMENTED → CLAIMED → VERIFIED →
ANCHORED, each stage lit only when it is really true), claim counts (declared vs independently verified),
evidence sources, economic-rights facts, valuation, liquidity (**NOT VERIFIED** until a real book exists),
**legal classification: NOT DETERMINED BY SOST**, and an anchor-ready payload. **View technical details**
reveals the manifestHash, every claim with its source and verification, and the SOST price scenarios.

## Who verifies what
The owner supplies the raw material; SOST records **who declared each fact**; independent sources — a public
registry, an appraiser, a lawyer, or GeaSpirit analysis — can later upgrade a claim from *declared* to
*independently verified*. Passports created earlier in the v1 format keep their original hash and still verify.

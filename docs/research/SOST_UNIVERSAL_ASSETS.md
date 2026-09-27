# SOST Universal Assets — technical + legal research (investigation kickoff)

**Status: RESEARCH ONLY.** No production, consensus, V16-height, SOST-supply or atomic-swap code is
touched by this document. GeaSpirit is explicitly OUT of scope (a future external user, nothing
more). This is the specification/feasibility investigation ordered before any prototype decision.
Facts verified in the repo are marked **[VERIFIED]**; everything else is **[HYPOTHESIS]** or
**[LEGAL — needs specialist counsel]**.

## 0. One-line thesis
SOST becomes an **open, optional registry + issuance layer** for arbitrary assets/rights. SOST the
coin keeps its supply and only pays fees. Each tokenized asset is an independent unit with its own
issuer, policy, passport and history. **SOST proves who issued a token, under what rules, how many
units exist, who controls them and their history — it does NOT decide the legal meaning, guarantee
value, custody the asset, or enforce off-chain promises.** Not an ERC-20 clone, not an EVM.

## 1. Repo audit — what SOST can do TODAY vs what needs a future fork
- **[VERIFIED] Capsules are live on mainnet since block 7350** (`CAPSULE_ACTIVATION_HEIGHT_MAINNET
  = 7350`, tx_validation.h). Modes include `doc_ref` (a 32-byte document hash + an off-chain
  locator, `CAPSULE_DOC_REF_MAX_LOCATOR`), `open_note`, `sealed_note` (ECIES), `template`
  (structured fields) and a certificate mode (`CAPSULE_CERT_MAX_NOTE`). Body ≤ **243 bytes**
  (`CAPSULE_MAX_BODY`), so documents stay OFF-chain and only their hashes/locators are anchored.
- **[VERIFIED] UTXO output types** in use: TRANSFER 0x00, coinbases 0x01–0x04, BOND_LOCK 0x10,
  ESCROW_LOCK 0x11, HTLC_LOCK 0x12, HTLC_CLAIM_WITNESS 0x13, BURN 0x20, NODE_PROTOCOL 0x30. The
  0x40+ range is FREE — natural home for `OUT_ASSET_ISSUE/TRANSFER/BURN/FREEZE` in a future module.
- **[VERIFIED] No native-asset / colored-coin / token-issuance concept exists yet** — this is
  greenfield.
- **Consequence (two honest phases):**
  - **Phase 1 — Asset Passport (documentary): buildable now, NO consensus change.** Anchor a
    passport's hash via a `doc_ref`/`cert` capsule; keep the passport + evidence off-chain
    (IPFS/HTTPS). Gives verifiable "this issuer registered these documents at this height", plus
    third-party attestations. It does NOT make the token a natively-validated asset.
  - **Phase 2 — native UTXO assets: needs a new consensus module** (issuance/transfer/burn/freeze
    validation over the 0x40+ outputs), adversarial tests, devnet-first, external audit, and a
    coordinated network upgrade — never folded into V16 while its security/sync work runs.

## 2. Model comparison (what to borrow, what to avoid)
| Model | Borrow | Avoid / cost |
|---|---|---|
| **Cardano Native Assets** | assets native to the ledger, no per-token contract; base coin pays fees (the SOST model) | requires ledger/consensus support (our Phase 2) |
| **Liquid Issued Assets** | native UTXO issuance + unique asset-id + controlled reissuance — closest to SOST's UTXO model | federation/functionary assumptions we don't want |
| **Bitcoin RGB** | client-side validation, data off-chain, only commitments on-chain (privacy + scale) | heavy client-side infra; indexer/proof-courier dependence |
| **Taproot Assets** | Merkle-committed asset trees anchored in outputs; UTXO-native | Taproot-specific; SOST has no Taproot |
| **ERC-3643 (T-REX)** | on-chain identity + restricted transfers + compliance hooks for REGULATED assets | EVM/contract model; we take the *policy* ideas, not the VM |
| **ERC-1155** | one schema for fungible + non-fungible + semi-fungible | EVM; we reuse the *multi-class* idea in Asset Policy |
| **W3C Verifiable Credentials 2.0** | signed, verifiable attestations off-chain with suspension/revocation, only hashes on-chain | not a token system by itself — pair it with the passport |

**Direction [HYPOTHESIS]:** a Liquid/Cardano-style *native UTXO asset* for Phase 2, with RGB-style
*off-chain data + on-chain commitment* for the passport, and W3C-VC *attestations* for third-party
certification. No EVM, no wrapped-SOST, no federation.

## 3. Architecture (universal, sector-agnostic)
Four separated concerns:
1. **SOST** — the coin; unchanged supply; pays all fees.
2. **Asset ID** — a unique, collision-resistant issuance identifier (issuer key + nonce + genesis
   commitment), so units of different assets never conflate.
3. **Asset Policy** — declared AT ISSUANCE and immutable thereafter: fungible vs unique(NFT) vs
   semi-fungible; fixed vs reissuable supply; free vs restricted transfer (allow-list / KYC);
   burnable; freezable; forced-transfer-by-court-order flag; expiry. An issuer must NOT be able to
   add powers over holders' units later that weren't in the original policy.
3. **Asset Passport** — off-chain document set (identity, evidence, rights, jurisdiction, custodian,
   valuations, audits) with a common core + per-sector modules (serial+report for machinery, land
   registry for real estate, sanitary traceability for food, etc.), anchored on-chain by hash;
   third-party certifications as W3C VCs (with suspension/revocation), clearly separated from the
   owner's own declarations, with certificate-expiry surfaced.
Operations (future module): ISSUE, TRANSFER, BURN, FREEZE/UNFREEZE, POLICY-bound UPDATE, PROOF
(attach report hashes), all fee-paid in SOST. Wallet/explorer show SOST balance and asset units
separately.

## 4. Legal landscape (EU / Spain) — **needs specialist counsel before any real issuance**
- **[LEGAL] Three product tiers, three regimes:** (a) *documentary passport* (identity/provenance,
  no property transfer) — lightest; still data-protection + "don't misrepresent third-party certs".
  (b) *tokenized contractual right* (right to receive a machine, withdraw goods, use equipment) —
  needs an enforceable contract and coordination with any official registry/custodian/procedure.
  (c) *financial instrument* (equity/debt/investment participations) — full financial regulation.
- **[LEGAL] ESMA:** tokenizing a financial instrument does NOT change its legal nature; financial
  instruments are excluded from MiCA and remain under MiFID II etc.
- **[LEGAL] Spain Ley 6/2023 (Mercado de Valores)** contemplates negotiable securities represented
  via DLT and requires an issuance document + an entity responsible for its registration/
  administration (generally an *authorized* entity — you can't freely designate any company); the
  system must also be able to record seizures/liens/court actions.
- **[LEGAL] MiCA** has specific rules for certain crypto-assets (incl. value-referenced ones) — a
  "gold token", "warehouse token" or "real-estate participation" must NOT be auto-classified
  without analysing its rights. **Do not use SOST's informational gold reference (1.14 mg) as a
  peg/backing here** (see docs/dex/GOLD_REFERENCE_RECONCILIATION.md).
- **[LEGAL] DLT Pilot Regime, MiFID II, AML/KYC, GDPR** all potentially engage depending on tier.
- **Takeaway:** the *technology* can be universal; the *legal authorization* per operation is not.
  Phase 1 (passport) is the low-risk starting point; regulated issuance needs authorized partners.

## 5. Risk matrix (asset-specific, beyond generic infosec)
| Risk | Mitigation |
|---|---|
| Double-representation of one physical asset (same good tokenized twice, even cross-platform) | unique Asset ID + custodian/registry attestation; the chain alone CANNOT prevent physical duplication — needs contractual + custodian responsibility |
| False title / issuer sells rights they don't hold | third-party (VC) certification separated from issuer self-declaration; surface "declared vs certified vs expired" |
| Fraudulent / expired certificates | VC revocation + expiry shown in the passport; never render "authentic/insured/custodied" just because the issuer says so |
| Key loss / issuer key compromise | policy-declared recovery only; no retroactive issuer powers; rotation procedures |
| Unit duplication / reissuance abuse | Phase-2 consensus rules enforce supply against Asset Policy; Phase-1 relies on indexer + issuer honesty (documented limitation) |
| Indexer divergence / reorg (Phase 1 is off-consensus) | deterministic indexer spec + reorg handling; Phase 2 moves validation into consensus |
| Custodian default (goods/metals) | custody attestations, audits, insurance references — all off-chain facts the chain only *anchors*, never *guarantees* |
| Forced transfer / seizure legitimacy | court-order flag in policy; only exercisable per declared, lawful conditions |

## 6. Asset Finance (the "valuation + lending pool" idea) — feasibility [HYPOTHESIS + LEGAL]
Answer to "can a pool/miners lend SOST at interest against a tokenized asset?": **technically yes,
legally the hard part.**
- **Tokenizing an asset does NOT create the money to finance it.** Financing must come from parties
  who *voluntarily* commit their own SOST. Miners are NOT obligatory lenders and consensus must not
  mint credit — SOST supply is untouched.
- **`SOST Asset Intelligence` (valuation engine) [HYPOTHESIS]:** NOT one AI guessing any value.
  A *modular* engine: a per-category methodology (real estate: comparables/income; metals: assayed
  weight × spot; machinery: depreciated replacement; debt: discounted cash-flow) that outputs a
  value + confidence, and a common layer translating it into a *financing proposal* (max loan-to-
  value, haircut, interest band) — always as an estimate with explicit risk, never a promised
  return. Every input (assay, appraisal, audit) is a dated, signed attestation, not a bare number.
- **`SOST Asset Finance` module [HYPOTHESIS]:** an independent, opt-in matching layer where lenders
  post SOST offers (signed, with reserved inventory — reuse the DEX RFQ engine's fail-closed,
  confirmed/committed/available model), borrowers pledge asset units into a policy-bound lock, and
  repayment/liquidation follow the declared terms. No AMM promising instant loans without real
  reserves; no auto-conversion of the asset into SOST.
- **[LEGAL]** A common lending pool, interest-bearing offers, and asset-backed credit are very
  likely **regulated financial activity** (lending, collective investment, possibly MiCA/MiFID II).
  This tier needs authorized partners and specialist counsel BEFORE any real-money pilot. Build and
  test only in the lab; do not activate market-making or public lending pre-review.

## 7. Phased plan (independent of V16; nothing merged/activated without authorization)
1. **Research + spec** (this document; extend with primary sources + a formal protocol spec).
2. **Asset Passport + Asset Studio (documentary), on existing capsules** — issuer studio, verifier,
   asset explorer; no consensus change; devnet/experimental branch.
3. **Native UTXO asset prototype (devnet)** — OUT_ASSET_* types + issuance/transfer/burn/freeze +
   policy enforcement; measure storage/sync/verify cost; adversarial suite.
4. **Audit + real pilots** — one real holder + one concrete asset, verified rights/docs; regulated
   tiers only with authorized entities.

## 8. Open questions for you (decisions, not code)
- Phase-1-only first (passport/traceability), or research Phase-2 native assets in parallel on devnet?
- Which first pilot category (collectible / machinery / warehouse goods / real estate)?
- Asset Finance: research now as a lab-only module, or defer until Universal Assets Phase 1–2 land?

## 6b. Asset Finance — owner's completed proposal (folded in; still RESEARCH/lab-only)
Three SEPARATE services so registering ≠ valuing ≠ financing (tokenize a machine without ever
taking a loan; miners never obliged to lend):
- **Valuation distinguishes three amounts that must not be conflated:** *estimated asset value*
  (data/evidence-based) → *net recoverable value* (what a forced sale nets after costs/time/risk) →
  *admissible financing* (capped by recoverable value AND by the SOST lenders actually willing to
  commit). Output is an interval with uncertainty, never an official appraisal or a promised
  recovery. Missing key documents ⇒ engine reports "insufficiently evidenced valuation", never a
  fabricated figure; complex/large loans require an independent appraisal.
- **Where the SOST comes from:** only from parties who VOLUNTARILY lend their own SOST. Two
  structures to study: *bilateral loan* (one borrower, one lender, negotiated terms — simplest,
  cleanly separates tech registry from financial activity) vs *funding pool* (many contributors,
  needs liquidity mgmt, loss rules, investor disclosure, withdrawal mechanics, and an appropriate
  legal structure). Miners may lend their OWN earned coins in either; the protocol NEVER auto-lends
  mining rewards, consensus reserves, or the Gold Vault, and NEVER mints new SOST to pay interest —
  interest comes solely from the borrower.
- **Excavator example (SIMULATION, no real funds):** market value ~€100k, net recoverable ~€60k,
  loan €20k (20% LTV), 12m, 8% illustrative. At a hypothetical SOST=€0.10 with enough liquidity:
  borrow 200,000 SOST, repay 216,000 SOST. **Volatility risk is explicit:** if SOST doubles, the
  borrower needs ~€43.2k worth to repay a loan that gave them €20k; if SOST falls, lenders recover
  fewer euros. Hence a second modality to study: **debt denominated in EUR, paid in SOST at a
  verifiable rate each due date** (cuts denomination risk; liquidity/slippage risk remains).
- **Physical-collateral enforcement is the hardest problem:** software can't repossess an
  excavator. Requires a validly constituted, enforceable guarantee, borrower's capacity to grant
  it, and a legal execution procedure (registries/notaries/custodians/courts per asset+jurisdiction).
  Must prevent the same excavator backing three loans by hiding prior liens ⇒ the passport must
  surface guarantee existence, priority, validity and available verifications. The digital passport
  does NOT replace the legal guarantee.
- **[LEGAL] Spain/EU specifics to analyse with counsel:** taking repayable funds from the public is
  RESERVED to authorized entities (Banco de España) — so NO "SOST savings account" guaranteeing
  repayment without a studied legal structure. Crowdfunding/PFP regimes (CNMV + EU ECSPR) cover
  credit-risk assessment, conflicts of interest, loan-portfolio mgmt — applicability to
  SOST-denominated loans needs specialist review. An ESMA/EBA joint report notes crypto-asset
  lending is NOT expressly among MiCA-defined services — which does NOT exempt it from other
  financial/AML/consumer rules. Likely path: partner with an AUTHORIZED platform/entity for the
  regulated parts while SOST provides only the technology.
- **Phasing:** (1) Universal Assets passports — no finance; (2) Asset Intelligence valuation engine
  (intervals, evidence, scenarios); (3) Asset Finance simulator + bilateral prototype on an
  isolated net, no deposits/real funds; (4) real financing only if viable, with appraisers/counsel/
  authorized entities; a common pool is investigated separately.
- **Essential distinction:** a tokenized asset's price and SOST's price are INDEPENDENT. The engine
  can estimate a machine's value and admissible financing; it CANNOT guarantee enough SOST demand
  to turn that financing into euros without material loss. Therefore start with the universal
  passport + assisted valuation; keep financing an optional later function — a utility for any
  sector, without turning SOST into a financial entity or touching its monetary rules.

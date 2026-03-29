# GeaSpirit & Materials Engine — Full Status Report (v2)

**Date:** 2026-03-29
**Author:** NeoB (CTO)
**Classification:** Internal decision document
**Supersedes:** v1 (same date — corrected for Phase 35-39 findings and operational accuracy)

---

## 1. Executive Summary

GeaSpirit is a multi-source mineral prospectivity intelligence platform that combines satellite imagery, geophysics, geology, hydrology, and machine learning to predict where mineral deposits are likely to exist. It scores 22.8/40 on its canonical objective ("There is [MINERAL] at [DEPTH] at [COORDINATES] with [X%] certainty"). The gap to a higher score is primarily a DATA ACCESS problem — all deposit-scale geophysics sources (gravity, AEM, Earth MRI) are blocked by government portal access — not an architecture or ML problem.

GeaSpirit has 3 core production zones (Kalgoorlie 0.879, Chuquicamata 0.882, Zambia 0.760), plus a newly validated transfer zone (Tennant Creek 0.763 combined terrain+magnetics). Magnetics has been upgraded to CONSOLIDATED_VALIDATED_SELECTIVE after Phase 39 confirmed a +0.069 delta over independent terrain baseline at a second zone with a different deposit type (IOCG vs orogenic Au).

The Materials Engine is a separate platform with 76,193 materials, graph neural network predictions, and a FastAPI server — fully functional but not yet public.

---

## 2. What GeaSpirit Is

GeaSpirit is a **surface-proxy and near-surface context system for mineral exploration intelligence**. It answers one question:

> "Where should you look for minerals?"

It works by:
1. **Ingesting** free satellite data (Sentinel-2, Landsat, SAR, SRTM terrain) + geophysics (magnetics) + geology (Macrostrat API) + hydrology
2. **Building** multi-source feature stacks optimized per zone, deposit type, and climate regime
3. **Training** Random Forest classifiers with spatial cross-validation against known deposit locations
4. **Producing** probability maps showing where undiscovered deposits are most likely
5. **Calibrating** results with isotonic calibration for honest uncertainty estimates

**It is NOT:**
- A geological survey replacement
- A direct subsurface imaging platform — it uses surface proxies and near-surface geophysical context, not direct depth penetration
- A drill target generator — it finds prospective areas, not ore bodies at specific depths
- A commercial product yet — it is a research platform in active development

---

## 3. What GeaSpirit Produces

### Core Outputs per Zone

| Output | Format | Resolution | Description |
|--------|--------|-----------|-------------|
| **Probability map** | GeoTIFF raster | 30m pixel | 0.0-1.0 probability of mineral presence per pixel |
| **Top-50 targets** | CSV + GeoJSON | Point coordinates | Highest-probability areas with GPS coordinates |
| **Calibrated confidence** | Brier score + reliability curve | Per-zone | How well the probabilities match reality |
| **Feature importance** | Table | Per-family | Which data sources matter most at this zone |
| **AUC score** | Number | Per-zone | How well the model discriminates deposits from background |
| **QA report** | Markdown | Per-zone | Label validation, alignment check, coverage assessment |

### Operational Outputs (Post-Phase 33)

| Output | Description |
|--------|-------------|
| **Selective family status report** | Which families work at this zone, which don't, and why |
| **Source status registry** | Which data sources are active, blocked, or manual-required |
| **Fail-fast validation log** | Automated checks for corrupted files, HTML stubs, wrong formats |
| **QGIS QA package** | Layer stack + alignment checks + anomaly detection workflows |
| **Batch export pipeline** | Reproducible GEE feature extraction (resolves memory limits) |

---

## 4. Canonical Score

**"There is [MINERAL] at [DEPTH] at [COORDINATES] with [X%] certainty"**

| Dimension | Score | Max | What It Measures | Current State |
|-----------|-------|-----|-----------------|---------------|
| **MINERAL** | 4.0 | 10 | Can we identify the mineral/deposit type? | Deposit-type classification (Au, Cu, IOCG). Not mineral species. |
| **DEPTH** | 4.1 | 10 | Can we estimate subsurface location? | Surface proxies only. ALL deposit-scale geophysics BLOCKED. |
| **COORDINATES** | 7.0 | 10 | Can we locate it precisely? | 30m pixel, QGIS QA validated, spatial alignment confirmed. |
| **CERTAINTY** | 7.7 | 10 | How confident are we? | Isotonic calibration, best Brier 0.096. Bootstrap CIs on all results. |
| **TOTAL** | **22.8** | **40** | **57%** | **Bottleneck = DEPTH (data access, not architecture)** |

**Methodology:** Frozen at v4 (Phase 13). Changes require CTO approval.

**What would move the score:**
- DEPTH +3-5: If gravity + AEM data enters (all currently BLOCKED_BY_PORTAL)
- MINERAL +1-2: If S2 spectral comparison at Tennant Creek confirms magnetics over spectral baseline
- CERTAINTY +0.5-1: With more validated zones (currently 4 core + 1 transfer test)
- Realistic ceiling with all available data: ~30/40 (75%)

**Honest disclaimer:** The score reflects what is measured and validated. It does NOT reflect architectural potential. The system is capable of more — it lacks the DATA to prove it.

---

## 5. Validated Zones

### Zone Classification (Post-Phase 39)

| Category | Zones | Meaning |
|----------|-------|---------|
| **Core Production** | Kalgoorlie, Chuquicamata, Zambia | Multi-source fusion validated, stable AUC, calibrated |
| **Transfer Validated** | Tennant Creek | First generalization test with measured delta |
| **Weak Baseline** | Peru | Baseline too low for fusion (0.698, below 0.73 threshold) |
| **Insufficient** | Arizona | Only 5 labels — not enough for any statistical claim |
| **Failed** | Pilbara | Iron formation signature too uniform to discriminate |

### Detailed Zone Table

| Zone | Country | Deposit Type | Labels | Best AUC | Best Stack | Delta | Status |
|------|---------|-------------|--------|----------|-----------|-------|--------|
| **Chuquicamata** | Chile | Porphyry Cu | 38 | **0.882** | S2+thermal+EMIT+geology+NB+hydro | +0.093 | Core Production |
| **Kalgoorlie** | Australia | Orogenic Au | 205 | **0.879** | S2+thermal+PCA+magnetics+NB+hydro | +0.013 | Core Production |
| **Tennant Creek** | Australia | IOCG + Au | 33 | **0.763** | Terrain+magnetics | +0.069 over terrain | Transfer Validated |
| **Zambia** | Zambia | Sediment Cu | 28 | **0.760** | S2+NB+hydrology | +0.024 | Core Production |
| **Peru** | Peru | Porphyry Cu | 71 | 0.698 | S2+thermal | -0.063 (fusion NEGATIVE) | Weak Baseline |
| **Arizona** | USA | Porphyry Cu | 5 | — | — | — | Insufficient |
| **Pilbara** | Australia | Iron Fe | 8 | — | — | — | Failed |

### Key Findings from Zone Validation

1. **Fusion is conditional:** Helps when baseline >= 0.73. Below that, fusion can be NEGATIVE (Peru -0.063).
2. **Magnetics generalizes across deposit types:** Kalgoorlie (orogenic Au) + Tennant Creek (IOCG) = multi-type evidence.
3. **Best single delta:** Chuquicamata +0.093 (EMIT hyperspectral for porphyry Cu).
4. **Strongest single feature:** tpi_heterogeneity d=+0.878 (topographic structural complexity).

---

## 6. Magnetics Generalization — Phase 35-39 Arc

This is the most significant recent development:

| Phase | What Happened | Result |
|-------|--------------|--------|
| 35 | Tennant Creek activated as AOI (91 labels, IOCG) | Planning complete |
| 36 | GA TMI magnetics downloaded for Tennant Creek (5.2MB, validated) | Data acquired |
| 37 | First ML measurement: magnetics-only AUC 0.668 CV / 0.762 bootstrap | Above random but unstable |
| 38 | GEE S2 comparison attempted — blocked by interactive memory limit | S2 baseline NOT measured |
| **39** | **SRTM terrain as independent baseline — delta +0.069 CV measured** | **CONSOLIDATED** |

**Final verdict (Phase 39): CONSOLIDATED_VALIDATED_SELECTIVE**

Evidence:
- Two independent zones: Kalgoorlie (+0.008 over S2 fusion) and Tennant Creek (+0.069 over terrain)
- Two deposit types: orogenic Au and IOCG
- Independent baseline comparison (terrain ≠ magnetics-derived)
- Physical coherence: IOCG = magnetite-rich, gradient/analytic signal features dominant
- Combined terrain+magnetics AUC 0.763 = best Tennant Creek result

**Remaining caveat:** S2 spectral baseline at Tennant Creek not yet measured (GEE auth expired). Terrain is a valid independent baseline, but S2 comparison is needed for definitive spectral-vs-magnetics assessment.

---

## 7. Current Operational Reality

### Active Sources (Autonomous Lane)

| Source | Resolution | Access | Status |
|--------|-----------|--------|--------|
| Sentinel-2 | 10-20m | GEE | OPERATIONAL |
| Landsat 8/9 thermal | 30-100m | GEE | OPERATIONAL |
| Sentinel-1 SAR | 10m | GEE | OPERATIONAL |
| SRTM DEM | 30m | GEE + AWS | OPERATIONAL |
| CSP/ERGo Landforms | 30m | GEE | OPERATIONAL |
| JRC Surface Water | 30m | GEE | OPERATIONAL |
| Macrostrat API | Variable | REST API | VALIDATED_SELECTIVE |
| GA TMI Magnetics | ~80m | NCI THREDDS | CONSOLIDATED_VALIDATED_SELECTIVE |
| USGS MRDS | Points | REST API | OPERATIONAL (labels) |
| OZMIN (GA) | Points | Download | OPERATIONAL (labels) |

### Blocked Sources (Operator Handoff Required)

| Source | What It Would Add | Why Blocked | Canonical Impact |
|--------|-----------------|-------------|-----------------|
| GA Gravity Grid | Subsurface density → DEPTH | GADDS portal returns HTML | +2-3 DEPTH points |
| GSWA AEM | Conductivity profiles → DEPTH | DMIRS portal 403 Forbidden | +1-2 DEPTH points |
| USGS Earth MRI | US regional geophysics → DEPTH | ScienceBase auth required | Arizona unlock |
| Peru EMIT L2A | Hyperspectral → MINERAL | Download truncated (54%, 41%) | Peru improvement |
| MINDAT | 500K+ mineral localities → better labels | API key not registered | Better label quality |

### Consolidated Validated Selective Families

| Family | Zones | Best Delta | Physical Basis |
|--------|-------|-----------|---------------|
| Magnetics (GA TMI) | Kalgoorlie, Tennant Creek | +0.069 | Magnetite alteration halos (IOCG), structural control (Au) |
| Geology (Macrostrat) | Zambia, Peru, Kalgoorlie | +0.054 to +0.104 | Lithology classification aids discrimination |
| EMIT alteration | Chuquicamata | +0.052 | Hydroxyl/iron oxide for porphyry Cu |
| PCA embeddings | Kalgoorlie | +0.026 | Greenstone belt spectral signatures |

### Frontier Testable Branch (Private Repo Only)

| Branch | Items | Status |
|--------|-------|--------|
| PHYSICALLY_PLAUSIBLE | 8 hypotheses | Documented, not tested |
| SPECULATIVE_BUT_TESTABLE | 6 hypotheses | Documented, not tested |
| NON_TESTABLE_AT_THIS_MOMENT | 5 ideas | Documented, explicitly excluded from production |
| Untested frontier families | 8+ | Temporal DNA, Prithvi-EO, ECOSTRESS diurnal, etc. |

### Rejected/Neutral Families

| Family | Result | Status |
|--------|--------|--------|
| Spatial gradients | -0.006 AUC | REJECTED |
| ML residuals | Overfitting artifact | REJECTED |
| Terrain + S2 combined | Neutral at 4 zones | DEPRIORITIZED (redundant with spectral) |
| Cross-zone transfer | LOZO AUC 0.51 | REJECTED |

---

## 8. Operational Infrastructure (Post-Phase 33)

### Fail-Fast Access Guard
10 mandatory checks for ALL new data sources:
1. HTTP status (403, 404, 5xx → BLOCKED)
2. DNS resolution
3. Content-Type (HTML → INVALID_FILE_HTML)
4. File size (<1KB → INVALID_FILE_STUB)
5. Magic bytes verification
6. Rasterio open test
7. Band count validation
8. Value range check (all zeros/NaN → corrupted)
9. CRS present
10. Coverage overlap with AOI

### Operator Handoff Mode
- Dropzone directories: `~/SOST/geaspirit/data/manual_drop/{gravity,aem,arizona_earthmri,peru_emit}/`
- Gating rule R9: auto-detects new files in dropzones
- Source status registry tracks every source with explicit status codes

### GEE Memory-Block Pattern (Phase 38-39)
- **Problem:** GEE `sampleRegions().getInfo()` exceeds memory on >100 points × >500 images
- **Solution Track A:** `Export.table.toDrive()` — async batch, no memory limit (infrastructure BUILT, awaiting GEE re-auth)
- **Solution Track B:** Batched `sampleRegions` in groups of 50
- **Solution Track C:** Download raw rasters locally (SRTM via AWS, TMI via NCI) and sample with rasterio
- **This is now a documented reusable pattern** for all future AOIs

### Adaptive Family Gating Engine (v13 — 28 rules)
Auto-selects the right feature combination per zone based on:
- Climate regime (hyperarid, arid, semi-arid, tropical)
- Deposit type (porphyry, orogenic Au, IOCG, sediment Cu)
- Baseline strength (< 0.73 → defer fusion)
- Data availability (magnetics → Australia only via GA TMI)
- Sample size (< 50 labels → PROVISIONAL flag, require bootstrap CIs)
- Pool utilization (PUR-based dynamic rewards for PoPC)

### Public/Private Separation (Enforced Post-Phase 35)
- **Public repo (sost-core):** Sober summaries, phase notes, roadmap, framing. No technology details, no hypotheses, no frontier research.
- **Private repo (geaspirit-research):** Full technical documentation, measured results, frontier hypotheses, NON_TESTABLE layer, free data access map, geological search playbook, all CTO reports.
- **Rule:** 11 frontier files moved from public to private in Phase 35. Verified clean in every subsequent phase.

---

## 9. Materials Engine

| Item | Value |
|------|-------|
| **Purpose** | Predict material properties from crystal structure |
| **Corpus** | 76,193 materials from 4+ sources (MP, AFLOW, COD, JARVIS) |
| **Models** | CGCNN (formation energy, MAE 0.15 eV/atom), ALIGNN-Lite (band gap, MAE 0.34 eV) |
| **API** | FastAPI on port 8000, 70+ endpoints |
| **Features** | Search, predict, mix materials, autonomous discovery, multilingual (9 languages) |
| **Cost** | $0/month (CPU-only) |
| **Status** | v3.2.0, Phase XIII, functional but not public |
| **Unique** | Material Mixer (generate theoretical candidates from parent pairs) |
| **DB** | SQLite 173MB |

**Use case:** A researcher wants to find materials with band gap 1.5-2.0 eV and formation energy < -1.0 eV/atom → Materials Engine returns candidates ranked by confidence with crystal structure data.

---

## 10. Commercial Value Estimate

### Market Context

| Service | Typical Cost | What You Get |
|---------|-------------|-------------|
| Traditional geological survey | $50K-$500K | Field team, samples, lab analysis, report |
| Airborne geophysics survey | $100K-$1M | Gravity/magnetics/EM data over AOI |
| Satellite image analysis (manual) | $10K-$50K | Expert interpretation of imagery |
| AI exploration platform (competitors) | $5K-$50K/month | Prospectivity maps, target ranking |

### What GeaSpirit Could Offer

| Tier | Product | Value | Price Estimate |
|------|---------|-------|---------------|
| **Screening** | Probability map for any 100×100 km AOI | First-pass filter before expensive fieldwork | $500-$2,000 |
| **Full Analysis** | Multi-source stack + calibrated targets + QA report | Replaces preliminary desktop geological study | $5,000-$15,000 |
| **Subscription** | Monthly updates for monitored AOIs | Continuous prospectivity intelligence | $2,000-$10,000/month |
| **Enterprise** | Custom models per deposit type + private data integration | Competitive intelligence for mining companies | $50,000-$200,000/year |

### Competitive Advantages

1. **Zero GPU cost** — runs on CPU, no cloud compute bills
2. **Multi-source selective fusion** — not just satellite; magnetics + geology + hydrology + terrain
3. **Regime-aware auto-selection** — 28 gating rules choose the right stack per zone automatically
4. **Calibrated uncertainty** — Brier score 0.096, not just "hot/cold" maps
5. **Fail-fast data quality** — 10-check guard prevents corrupted inputs
6. **Documented frontier discipline** — clear separation between validated production and speculative research

### Current Limitations for Commercialization

1. No public API yet (internal research tool)
2. No web interface for clients
3. 4 core zones + 1 transfer test — need 15-20+ for global credibility
4. Depth dimension weak (4.1/10) — mining companies care most about depth
5. S2 spectral comparison at Tennant Creek still pending (GEE auth expired)
6. No SLA, no support, no guaranteed uptime

---

## 11. Roadmap

### Immediate (Phase 40-42)
- Re-authenticate GEE (`earthengine authenticate`)
- S2 spectral comparison at Tennant Creek (Track A batch export)
- If positive: officially upgrade MINERAL score
- Mt Isa as third Australian magnetics zone (Ernest Henry IOCG)
- Apply batch export pattern to all expansion AOIs

### Short Term (Q2-Q3 2026)
- Expand to 8-10 validated zones globally
- First PoPC participant (after block 5000 activation, ~April 18)
- Materials Engine public read-only API

### Medium Term (Q4 2026 - Q1 2027)
- Operator unlocks blocked geophysics data (gravity, AEM)
- DEPTH score improvement (target 6.0/10 with real geophysics)
- Web interface prototype for GeaSpirit clients
- First paid GeaSpirit analysis (invitation-only beta)

### Long Term (2027+)
- 20+ zones for global credibility
- Native metal tokens on SOST chain
- Fully native PoPC (no Ethereum dependency)
- GeaSpirit as a service (SaaS)
- Canonical score target: 30/40 (75%) with full data access

---

## 12. Recommendations for Access Model

### GeaSpirit Access
- **Phase 1 (now):** Free for internal use, research validation
- **Phase 2 (Q3 2026):** Invitation-only beta for 3-5 mining companies
- **Phase 3 (Q1 2027):** Public API with tiered pricing
- **Phase 4 (2027+):** PoPC-linked access — gold custody participants get priority access

### Materials Engine Access
- **Phase 1 (now):** Internal use only
- **Phase 2 (Q2 2026):** Public read-only API (search, query)
- **Phase 3 (Q3 2026):** Prediction API (submit structure, get properties)
- **Phase 4 (2027):** Premium features (Material Mixer, autonomous discovery)

---

**This report reflects the state as of 2026-03-29 (post-Phase 39). No code was modified.**

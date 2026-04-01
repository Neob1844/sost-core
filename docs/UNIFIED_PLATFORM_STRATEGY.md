# SOST GeaSpirit: Unified Materials Discovery + Remote Sensing Platform

## Strategic Plan for Platform Integration

**Date:** 2026-03-20
**Version:** 1.0
**Status:** Strategic Planning Document

---

## Executive Summary

**Platform Name:** GeaSpirit

**One-liner:** Computationally predict new materials, then search for them in satellite imagery — and register discoveries on a blockchain.

**What nobody else offers:** GeaSpirit is the first system that closes the loop between computational materials science (graph neural networks predicting material properties from crystal structure) and orbital remote sensing (detecting mineral spectral signatures from space). Every other player in mineral exploration does one or the other. Nobody combines GNN-predicted spectral signatures with automated satellite search, and nobody anchors discoveries to an immutable blockchain ledger.

**Why the combination is more powerful than either alone:**

The Materials Discovery Engine (76,193 materials, CGCNN/ALIGNN-Lite GNN models, novelty scoring, candidate generation, frontier ranking, validation pipeline, 635 tests) can predict what materials *should* exist and what properties they would have. The Remote Sensing capability (Sentinel-2, EMIT hyperspectral, Sentinel-1 radar — all free) can detect what minerals are *actually present* on Earth's surface. Separately, one is a library without a search party, and the other is a search party without a target list. Together, they form a directed discovery system: predict what is interesting, then go find it.

The SOST blockchain provides the third ingredient neither component delivers alone: timestamped, immutable Proof of Discovery that creates intellectual property and economic value from the discovery cycle.

---

## 1. Unified Vision

### Platform Name and Branding

**GeaSpirit** — "Geo" for geoscience and remote sensing, "Forge" for computational materials creation. The name signals the fusion of two domains.

Tagline: *Predict. Detect. Discover.*

### The Key Innovation

The core technical insight is that crystal structure determines electronic structure, which determines optical properties, including spectral reflectance in the VNIR/SWIR bands that satellites measure. A GNN trained on crystal structures can, in principle, predict the spectral signature of a material — and that predicted signature can be used as a search template against real satellite imagery.

This creates a closed discovery cycle:

```
PREDICT ──> SEARCH ──> FIND ──> REGISTER ──> MONETIZE
   |                                              |
   └──── feedback loop (found/not found) ─────────┘
```

1. **Predict**: Researcher specifies desired material properties (e.g., high hardness + specific band gap). Materials Engine generates computational candidates using element substitution, stoichiometry perturbation, and prototype remixing. GNN models score candidates for stability, band gap, and novelty.

2. **Search**: For candidates that match known mineral classes or have predictable spectral signatures, the Remote Sensing module queries Sentinel-2/EMIT imagery for spectral matches in geologically plausible regions.

3. **Find**: System reports probability maps: "Material signature consistent with predicted CuFeS2 variant detected at these coordinates in the Atacama, Chile — 73% spectral match confidence."

4. **Register**: Discovery is hashed and recorded as a Proof of Discovery transaction on the SOST blockchain, with timestamp, coordinates, spectral evidence hash, and discoverer identity.

5. **Monetize**: Discovery data is sold as geological intelligence to mining companies. Payment in SOST creates token demand.

### Why No Competitor Has This

- **KoBold Metals** ($3B valuation): Uses AI + geophysics for battery metals. No computational materials science. No blockchain. No spectral prediction from crystal structure.
- **Earth AI**: Drilling target prediction from geophysical data. No GNN materials models. No novel material prediction.
- **Goldspot Discoveries**: ML on geological maps + geochemistry. No crystal-structure-level prediction. No remote sensing automation.
- **Academic groups**: Plenty of GNN materials work (CGCNN, ALIGNN, MEGNet, M3GNet). Plenty of remote sensing mineral mapping. Nobody connects the two.

The gap exists because computational materials science and remote sensing geoscience are entirely separate academic disciplines with different conferences, journals, and toolchains. GeaSpirit bridges them.

---

## 2. Zero-Cost Phased Roadmap

### Timeline Overview

```
2026         Q2        Q3        Q4       2027 Q1      Q2        Q3       Q4       2028
 |--PHASE 0--|--PHASE 1--|----PHASE 2----|----PHASE 3----|------PHASE 4------|
 $0           $0          $0-2,600        Revenue-funded  Revenue-funded
 Sentinel-2   +EMIT       +CNN fusion     Hyperspectral   Full subsurface
 Basic maps   +Sentinel-1 +MatEngine      precision       inference
 MVP product  ML models   integration     Data marketplace Ultimate goal
```

---

### PHASE 0: Foundation (Now, $0, 0-3 months)

**Goal:** Produce the first sellable mineral alteration maps using only free tools and data.

**What to build:**

| Component | Tool/Data | Cost |
|---|---|---|
| Spectral processing | Python + rasterio + spectral library | $0 |
| Satellite imagery | Sentinel-2 L2A via Copernicus Open Access Hub | $0 |
| Band ratio computation | NDVI, clay ratio (B11/B12), iron oxide (B04/B02), ferrous (B11/B08) | $0 |
| Reference spectra | USGS Spectral Library v7 (1,371 spectra, 481 minerals) | $0 |
| Cloud compute | Google Earth Engine (free for research) | $0 |
| Target regions | Atacama (Chile), Pilbara (Australia), Nevada (USA) — arid, exposed | $0 |
| Basic Materials Engine link | Query engine for known mineral compositions matching detected spectra | $0 |

**Connection to Materials Engine:**

When the remote sensing module detects a spectral anomaly (e.g., strong Al-OH absorption at 2200 nm), query the Materials Engine's 76,193-material database for minerals containing those elements with matching crystal systems. Report: "Spectral signature consistent with kaolinite-group minerals. Materials Engine identifies 47 matching phases in corpus, including 3 novel candidates with predicted formation energy < -2.0 eV/atom."

**Deliverable:** Sentinel-2 mineral alteration probability maps for 3-5 arid regions. Color-coded maps showing iron oxide, clay, carbonate, and silica alteration zones at 10-20m resolution.

**Sellable product:** "Mineral Screening Report" for a 50x50 km zone. Junior mining companies currently pay geological consultants $5,000-$25,000 for similar work that takes weeks. We produce it in hours for $0 marginal cost.

**Realistic client count year 1:** 3-8 junior mining companies. The junior mining sector (TSX-V, ASX) has ~2,000 listed companies, many actively exploring in arid regions. Conservative 0.2-0.4% conversion.

---

### PHASE 1: Multi-Sensor Integration ($0, 3-6 months)

**What changes:**

| Addition | Data Source | What It Adds |
|---|---|---|
| EMIT hyperspectral | NASA LP DAAC (free) | 285 bands, 7.5 nm resolution — can distinguish minerals Sentinel-2 cannot (e.g., different clay minerals, carbonates, sulfates) |
| Sentinel-1 SAR | Copernicus (free) | Surface roughness, moisture, structural lineaments (faults, fractures that control mineralization) |
| ASTER archive | NASA Earthdata (free) | 14 bands including TIR, good for silicate discrimination. 20+ years of archive. |
| Known deposit training | USGS MRDS + provincial databases (free) | Training labels: known deposits for supervised ML |

**First ML models:**

Train Random Forest / XGBoost classifiers on spectral + radar features over known mining districts. Labels from USGS Mineral Resources Data System (50,000+ records, free). Target: predict "prospective" vs "non-prospective" terrain at 60m resolution.

Training data pipeline: Extract Sentinel-2 band ratios + EMIT mineral abundances + Sentinel-1 backscatter over known deposit locations (positive class) and barren terrain (negative class). Standard 70/15/15 train/val/test split. Expect AUC 0.70-0.80 for major commodity types (copper porphyry, iron oxide, gold-bearing alteration) based on published literature benchmarks.

**New clients:** Environmental consulting firms (acid mine drainage mapping), government geological surveys (regional mineral assessment).

---

### PHASE 2: Deep Integration ($0-2,600, 6-12 months)

**The $2,600 is optional:** For a single EMIT commercial processing tier or a modest GPU cloud allocation. Everything can still run on CPU/GEE for $0, just slower.

**CNN models:**

Replace band-ratio heuristics with convolutional neural networks operating on raw spectral datacubes. Architecture: 1D-CNN on per-pixel spectra (like DeepSpectra) or 3D-CNN on spatial-spectral patches. Training on USGS-labeled regions.

**Multi-sensor fusion:**

Concatenate Sentinel-2 (13 bands) + EMIT (285 bands) + Sentinel-1 (2 polarizations) + DEM (elevation, slope, aspect) into a unified feature stack. Late fusion (separate encoders per sensor, combined classifier) is more robust than early fusion for sensors with different resolutions.

**Real Materials Engine integration — the first bridge:**

This is where the platforms truly merge. The integration works on two levels:

**Level 1 — Compositional matching (achievable now):**
- Remote sensing detects mineral assemblage (e.g., jarosite + goethite + alunite)
- Materials Engine searches for all phases containing Fe, S, K, Al, O with matching crystal systems
- Engine reports known materials, novel candidates, and exotic compositions in that chemical space
- Product: "This alteration zone chemistry is consistent with 142 known materials and 23 novel candidates predicted stable by CGCNN"

**Level 2 — Spectral prediction (research frontier, see Section 3):**
- Materials Engine generates a novel candidate (e.g., a new Cu-Fe-S phase)
- Spectral prediction module estimates its VNIR/SWIR reflectance signature
- Remote sensing module searches global imagery for that signature
- Product: "We searched for the predicted spectral signature of candidate CuFe3S5 across 12 million km2 of Sentinel-2 imagery. Three regions show >60% spectral match."

**Revenue start:** Phase 2 is when the integration produces unique value no competitor offers. Target: $50K-$150K ARR from 10-15 clients (junior miners + geological consultants).

---

### PHASE 3: Precision + Marketplace (Revenue-Funded, 12-24 months)

**Hyperspectral precision:**

With revenue from Phase 2, invest in:
- EnMAP data processing (free data, 242 bands, 30m resolution, German Space Agency)
- PRISMA data (free for research, ASI, 240 bands, 30m)
- EMIT L2B mineral products (already identified minerals, not just spectra)

**Subsurface inference models:**

The key insight from economic geology: surface alteration halos extend laterally far beyond the buried ore body. A porphyry copper deposit creates concentric alteration zones (propylitic → phyllic → argillic → potassic) that can extend 2-5 km from center. Mapping the alteration pattern from orbit reveals the probable location and depth of the ore body, even when it is completely buried.

Train models on:
- Known deposits with published alteration maps + known depth/grade
- Surface alteration patterns (spectral) → depth/grade (regression target)
- Start with porphyry copper (best-studied alteration model) and VMS deposits

**Geological Data Marketplace on SOST blockchain:**

- Probability maps minted as data-tokens (Capsule Protocol v1, activates at height 5000)
- Proof of Discovery transactions: hash of discovery data + coordinates + timestamp
- Data consumers pay in SOST to access probability maps
- Discoverers receive SOST royalties when their data is accessed

---

### PHASE 4: The Complete System (24-48 months)

**Ultimate goal:** Fuse ALL available data layers — spectral, radar, gravity, magnetic, topographic, geochemical, drilling, seismic — with GNN material models into a unified probabilistic model that estimates subsurface mineral composition with quantified uncertainty.

**Technology advances needed:**
- Spectral prediction from crystal structure (Section 3) must be validated
- Foundation models for geoscience (similar to how LLMs work for text, but for multi-modal geospatial data) are emerging in research
- NASA SBG (Surface Biology and Geology) mission (~2028-2030): 10nm spectral resolution, global coverage, will be a step change for mineral mapping

**When subsurface detection becomes viable at high confidence:**
With current technology: surface minerals only (top ~1mm of exposed rock/soil). With alteration halo modeling: indirect inference to ~500m depth for large deposits (moderate confidence, ~60-70% for copper porphyry type systems). With future multi-physics integration (gravity + magnetics + spectral + drilling): potentially 1-2 km depth at useful confidence (~75-85%) for specific deposit types. True "X-ray vision" for arbitrary subsurface composition remains beyond current physics constraints.

---

## 3. The Key Connection: Predicted Spectra to Detected Spectra

This section addresses the core scientific question: can a GNN predict the spectral reflectance of a material from its crystal structure alone?

### A) Can a GNN Predict Spectral Reflectance from Crystal Structure?

**The physics chain:**

```
Crystal Structure
    → Electronic Band Structure (DFT or GNN approximation)
        → Dielectric Function ε(ω)
            → Complex Refractive Index n(ω) + k(ω)
                → Reflectance R(λ) at each wavelength
```

Each step is well-defined physics. The question is whether a GNN can learn the composite mapping end-to-end, or whether intermediate steps are needed.

**Theoretical basis — YES, it is possible in principle:**

Crystal structure completely determines electronic structure (this is the foundational theorem of DFT — Hohenberg-Kohn). Electronic structure determines the dielectric function, which determines all optical properties including spectral reflectance. Therefore, crystal structure *does* uniquely determine spectral reflectance. The question is whether ML models can learn this mapping efficiently.

**Existing research:**

- Xie & Grossman (PRL 2018) showed CGCNN can predict band gap, formation energy, and other electronic properties from crystal structure. Band gap is already a coarse optical property (it determines absorption onset).
- Chen & Ong (Nature Computational Science 2022) demonstrated that GNNs (M3GNet) can predict a wide range of material properties including dielectric constants from structure.
- Zhuo et al. (J. Phys. Chem. Lett. 2018) predicted refractive indices of crystals from composition using ML.
- Choudhary et al. (npj Computational Materials 2021) used ALIGNN to predict optical absorption spectra (imaginary part of dielectric function) from crystal structure, achieving useful accuracy for screening.
- Spectral reflectance specifically (the VNIR/SWIR signature measured by satellites) has not been directly predicted by GNN from crystal structure. This is the gap GeaSpirit would fill.

**Training data assessment:**

| Data Source | What It Provides | Size | Overlap |
|---|---|---|---|
| USGS Spectral Library v7 | Measured reflectance spectra (350-2500 nm) | 481 minerals, 1,371 spectra | Need to match these to crystal structures |
| RRUFF Database | Raman + reflectance for minerals with known structures | ~4,000 minerals | Many have both structure and some optical data |
| Materials Project | Crystal structures + computed band structure | ~150,000 materials | Computed optical properties for ~10,000 |
| JARVIS-DFT | Crystal structures + optical properties (dielectric function) | ~55,000 materials | ~20,000 have optical absorption spectra (computed) |
| Our Materials Engine | Crystal structures + properties | 76,193 materials | Need to add spectral data via cross-referencing |

**The training data bottleneck:**

The critical challenge is finding materials that have BOTH (a) known crystal structure in a database our GNN can ingest and (b) measured VNIR/SWIR reflectance spectra. The USGS Spectral Library has ~481 minerals with spectra, and most of these are well-characterized minerals with known crystal structures in the Inorganic Crystal Structure Database (ICSD) or the Crystallography Open Database (COD, already ingested in our Materials Engine).

Estimated overlap: ~300-400 minerals with both crystal structure data and measured reflectance spectra. This is small for training a deep GNN, but viable for a transfer learning approach:

1. Pre-train on JARVIS computed optical absorption (20,000 materials, no measured spectra needed)
2. Fine-tune on the ~300-400 minerals with measured VNIR/SWIR reflectance
3. The pre-trained model learns "crystal structure → optical response" from DFT data; fine-tuning adapts this to real measured spectra

**Two viable approaches:**

**Approach 1 — Physics-Informed Pipeline (more rigorous):**
```
Crystal Structure → GNN → Band Gap + Dielectric Constants → Lorentz Model → Reflectance(λ)
```
Use our existing CGCNN/ALIGNN-Lite models to predict band gap and dielectric constants (they already predict band gap). Add a dielectric constant prediction head. From band gap + dielectric constants, use the Lorentz oscillator model (analytical physics) to generate an approximate reflectance spectrum. This approach requires fewer training samples because the physics is explicitly encoded.

**Approach 2 — End-to-End Prediction (more ambitious):**
```
Crystal Structure → GNN → Reflectance(λ) as 200-dimensional vector
```
Train the GNN to directly output reflectance at 200 wavelengths spanning 350-2500 nm. This requires more training data but could capture effects the physics-informed approach misses (surface roughness effects, grain size, mixtures).

**Recommendation:** Start with Approach 1 (physics-informed, achievable with existing models + ~6 months work). Pursue Approach 2 as a research objective when more training data is available.

### B) The Complete Flow (When Spectral Prediction Works)

**Step-by-step operational scenario:**

1. **Researcher input:** "I need a thermoelectric material with band gap 0.5-1.0 eV, containing abundant elements, formation energy < -1.0 eV/atom."

2. **Materials Engine generates candidates:** The GenerationEngine runs mixed strategy (element substitution + stoichiometry perturbation + prototype remix) with constraints. Produces 50-200 novel candidates. FrontierEngine ranks them by stability, band gap fit, novelty, and exotic score.

3. **GNN predicts spectral signature:** For the top 20 candidates, the spectral prediction module (CGCNN-Spectra or ALIGNN-Spectra model) outputs predicted reflectance R(lambda) from 350-2500 nm. Each candidate gets a diagnostic spectral fingerprint: absorption features at specific wavelengths that distinguish it from known minerals.

4. **Remote sensing searches:** The predicted spectral fingerprint is converted to a Sentinel-2 band-ratio template (which combination of Sentinel-2's 13 bands would show the predicted absorption features). For EMIT coverage areas, the full 285-band spectrum is used for matching. The search runs on Google Earth Engine across geologically plausible regions (exposed terrain, known mineralizing geology).

5. **Results:** "Candidate MgFe2Si3O10 (predicted band gap 0.72 eV, formation energy -1.3 eV/atom) — spectral signature with diagnostic Fe2+ absorption at 1050 nm and Mg-OH at 2320 nm. Sentinel-2 search found 17 regions with >60% spectral match. Top hit: 73% match at -24.15, -69.42 (Atacama, Chile). EMIT data available for 3 of 17 regions, confirming Fe/Mg absorption features."

6. **Blockchain registration:** Proof of Discovery transaction recorded on SOST blockchain:
   - Discovery hash: SHA-256(candidate_id + coordinates + spectral_evidence + timestamp)
   - Embedded in Capsule Protocol v1 metadata (12-byte header + evidence payload)
   - Immutable timestamp proves priority of discovery
   - Discoverer's SOST address is the registered owner

7. **Field verification:** Researcher or partnered mining company visits the top-ranked coordinates. Collects rock samples. Laboratory XRD confirms or refutes the predicted phase. Results fed back into the system (Section 3C feedback loop).

### C) Realism Assessment

| Capability | Status | Timeline | Confidence |
|---|---|---|---|
| Sentinel-2 mineral alteration maps (iron oxide, clay, carbonate) | **Achievable today** | Phase 0 (now) | High (90%) — published methods, proven at 10-20m |
| EMIT mineral identification for ~15 common mineral groups | **Achievable today** | Phase 1 (3-6 months) | High (85%) — NASA provides L2B mineral products |
| GNN prediction of band gap from crystal structure | **Already working** | Operational | High (90%) — CGCNN/ALIGNN-Lite in Materials Engine |
| GNN prediction of dielectric constants from structure | **Research stage, feasible** | 6-12 months | Medium (65%) — published results from M3GNet, needs adaptation |
| Approximate reflectance from predicted dielectric constants | **Physics-based, feasible** | 12 months | Medium (60%) — Lorentz model is standard, but grain size/surface effects add noise |
| End-to-end GNN crystal structure to reflectance spectrum | **Research frontier** | 18-24 months | Low-Medium (40%) — insufficient training data today, needs ~1000+ matched samples |
| Automated satellite search for GNN-predicted spectral signatures | **Engineering challenge, feasible** | 12-18 months | Medium (55%) — individual steps work, integration is novel |
| High-confidence subsurface mineral detection from orbit | **Long-term aspiration** | 3-5+ years | Low (25%) — physics limits penetration to surface; indirect inference is possible |

**Honest bottom line:** Phase 0-1 deliverables (mineral alteration maps from Sentinel-2/EMIT) are well-established and achievable today at zero cost. The compositional bridge to the Materials Engine (Level 1) is straightforward engineering. The spectral prediction bridge (Level 2) is a genuine research challenge with approximately 50-60% chance of producing useful results within 18 months. The full closed-loop system (predict material, find it from orbit) is a 24-36 month R&D objective.

---

## 4. Zero-Cost Business Model

### A) Mineral Screening Service

**Product:** Probability map of mineral alteration for a client-specified zone (up to 100x100 km).

**Pricing:**
| Tier | Coverage | Deliverable | Price |
|---|---|---|---|
| Scout | 25x25 km | Sentinel-2 alteration map, 4 mineral groups | $1,000 |
| Standard | 50x50 km | Sentinel-2 + ASTER, 8 mineral groups, structural lineaments | $3,000 |
| Advanced | 100x100 km | Multi-sensor (S2+EMIT+S1), ML-ranked targets, Materials Engine cross-reference | $8,000 |
| Premium | Custom | All sensors + GNN spectral search + on-chain registration | $15,000+ |

**Our cost:** $0 for Scout/Standard (free data, free GEE compute). $0-50 for Advanced (potential cloud compute for ML inference). Premium is where revenue funds Phase 3.

**Gross margin:** 95-100% for Scout/Standard tiers.

**Realistic year 1 clients:** 5-10 clients generating $30K-$80K revenue. The junior mining market is accessible through mining conferences (PDAC, Prospectors & Developers Association of Canada — 25,000 attendees), online mining forums, and direct outreach to exploration-stage companies.

### B) Materials Prediction API

**Freemium model:**

| Tier | Access | Price |
|---|---|---|
| Free | Search 76,193 known materials by composition, property, structure. 100 queries/day. | $0 |
| Pro | Generative candidate pipeline + novelty scoring + frontier ranking. 1,000 queries/day. | $50/month or 5 SOST/month |
| Enterprise | Full GNN inference + spectral prediction + remote sensing search. Unlimited. | $500/month or 50 SOST/month |

**SOST payment integration:** Offering a discount (20%) for payment in SOST creates organic token demand from a professional user base, not speculation.

### C) Geological Data on Blockchain

**Data-tokens:** Each mineral probability map is hashed and registered as a Capsule Protocol v1 payload in a SOST transaction. The on-chain record contains:
- Hash of the probability map data file
- Bounding box coordinates
- Sensor sources used
- Model version
- Creator address

**Proof of Discovery:** When the remote sensing module identifies a significant anomaly, the discovery is timestamped on-chain. This has real commercial value: mining claims and exploration rights are sensitive to timing. An immutable, decentralized timestamp is more credible than a company's internal database.

**Marketplace:** Data consumers browse available probability maps by region/commodity. Payment in SOST unlocks the full-resolution data. Creators receive 80% of revenue; 20% goes to the SOST ecosystem (Gold Vault + PoPC Pool via standard block allocation).

### D) Compute Marketplace

**Concept:** SOST miners (running ConvergenceX PoW, which requires ~8GB RAM and significant CPU) have idle capacity between successful block finds. Satellite data processing (band ratios, spectral unmixing, ML inference) is CPU-friendly work.

**Implementation:** A sidecar process on mining nodes accepts satellite processing jobs. Miners are paid in SOST for completed processing. This creates a decentralized compute network for geospatial processing — essentially a specialized version of what Golem or Render Network do, but focused on geological data.

**Timeline:** Phase 3-4. This requires the mining network to reach sufficient scale (100+ active miners).

---

## 5. Competitive Analysis

| Company | Valuation | What They Do | What They Lack |
|---|---|---|---|
| **KoBold Metals** | ~$3B (2024) | AI + geophysics for battery metals. Backed by Gates, Bezos. Large geophysical datasets. | No computational materials science. No GNN models. No blockchain. No spectral prediction. Black-box proprietary. |
| **Earth AI** | ~$30M | Drilling target prediction from geophysical data. Operating in Australia. | No novel material prediction. No spectral search. No blockchain. Drilling-focused, not remote sensing. |
| **Minerva Intelligence** | ~$15M (TSX-V) | Expert system for geological targeting. Knowledge graphs. | Rule-based, not ML. No GNN. No remote sensing automation. No blockchain. |
| **Goldspot Discoveries** | ~$20M (TSX-V) | ML on geological maps + geochemistry + drilling data. | No crystal-structure-level analysis. No novel material prediction. No spectral prediction. No blockchain. |
| **Descartes Labs** | ~$50M | Satellite imagery platform + ML. General purpose. | No materials science. No mineral-specific models. No blockchain. Generic imagery analysis. |
| **GeaSpirit (SOST)** | Pre-revenue | GNN materials discovery + remote sensing + blockchain. | No geophysical datasets (yet). Small team. Unproven market traction. |

**Our unique position:**

Nobody — not a single company or academic group — currently combines:
1. Graph neural networks predicting material properties from crystal structure (76,193 materials)
2. Automated remote sensing mineral detection from satellite imagery
3. Blockchain-anchored Proof of Discovery

The closest would be if KoBold Metals built a materials science division and added a blockchain layer, which would require them to move far outside their core competency and business model. The integration of these three domains is genuinely novel.

**Vulnerability:** KoBold has $3B and could theoretically build everything we build. Our defense is speed-to-market on the integration, the open-source nature of the SOST blockchain creating network effects, and the fact that the materials science + remote sensing bridge is a research problem that money alone does not solve quickly.

---

## 6. Detailed Technical Roadmap

### Phase 0: Sentinel-2 Mineral Mapping (Months 1-3)

| Item | Detail |
|---|---|
| **Software** | Python 3.10+, rasterio, numpy, scikit-learn, matplotlib, Google Earth Engine Python API |
| **Data** | Sentinel-2 L2A (Copernicus), USGS Spectral Library v7, SRTM DEM |
| **Models** | Band ratio indices (published formulas), PCA on spectral bands, spectral angle mapper (SAM) |
| **Output** | GeoTIFF probability maps, PDF report per zone |
| **Dev time** | 6-8 weeks for one developer |
| **Dependencies** | GEE account (free), Copernicus Data Space account (free) |
| **KPIs** | 3 demo maps for known mining districts; validation against published geological maps (>70% spatial agreement for major alteration zones); 1 paying client |

### Phase 1: Multi-Sensor + First ML (Months 4-6)

| Item | Detail |
|---|---|
| **Software** | + xarray, earthaccess (NASA), sentinelsat, pytorch (CPU) |
| **Data** | + EMIT L2A/L2B (NASA Earthdata), Sentinel-1 GRD (Copernicus), ASTER L1T (NASA), USGS MRDS deposit database |
| **Models** | Random Forest / XGBoost on multi-sensor features. Training: known deposits vs. barren terrain. |
| **Output** | Multi-sensor fusion maps, ML prospectivity maps with uncertainty |
| **Dev time** | 8-10 weeks |
| **Dependencies** | NASA Earthdata login, sufficient GEE quota |
| **KPIs** | AUC >0.72 for copper porphyry detection on holdout test set; 5 client conversations; 2 signed contracts |

### Phase 2: CNN + Materials Engine Bridge (Months 7-12)

| Item | Detail |
|---|---|
| **Software** | + PyTorch (GPU optional), custom CNN architecture, Materials Engine API integration |
| **Data** | + RRUFF mineral spectra, cross-referenced crystal structures from COD/Materials Engine |
| **Models** | 1D-CNN on spectral datacubes; compositional matching module linking detected minerals to Materials Engine database |
| **Output** | Integrated reports: spectral detection + materials science context + novel candidate identification |
| **Dev time** | 16-20 weeks (2 developers) |
| **Dependencies** | Materials Engine API (already built), spectral-structure cross-reference database (must build) |
| **KPIs** | 10 paying clients; $50K+ ARR; Materials Engine cross-reference working for >200 minerals; spectral prediction prototype for 5 test minerals |

### Phase 3: Hyperspectral + Marketplace (Months 13-24)

| Item | Detail |
|---|---|
| **Software** | + EnMAP/PRISMA processing pipelines, SOST Capsule Protocol integration, marketplace web app |
| **Data** | + EnMAP L2A (DLR), PRISMA L2D (ASI), NISAR (NASA/ISRO, launch 2025, free SAR) |
| **Models** | Spectral prediction model v1 (physics-informed GNN → dielectric → reflectance), alteration halo depth regression |
| **Output** | On-chain data marketplace, spectral prediction for top 50 novel candidates, automated search pipeline |
| **Dev time** | 30-40 weeks (2-3 developers) |
| **Dependencies** | Revenue from Phase 2, SOST blockchain at sufficient block height for Capsule Protocol |
| **KPIs** | $200K+ ARR; 25 clients; spectral prediction validated for >50 minerals (MAE < 0.15 reflectance); 10 Proof of Discovery transactions on-chain |

### Phase 4: Full Integration (Months 25-48)

| Item | Detail |
|---|---|
| **Software** | + Geophysical inversion libraries, passive seismic processing, subsurface modeling |
| **Data** | + NASA SBG (if launched), public gravity/magnetic surveys, drilling databases |
| **Models** | Multi-physics fusion model, subsurface composition estimation, spectral prediction v2 (end-to-end GNN) |
| **Output** | Subsurface probability volumes, complete predict-search-find-register pipeline |
| **Dev time** | 50+ weeks (3-5 developers) |
| **Dependencies** | Revenue stream, research breakthroughs in spectral prediction, SBG mission data |
| **KPIs** | $500K+ ARR; validated subsurface predictions at 3+ sites; spectral prediction MAE < 0.10 for >200 minerals; marketplace with >100 data-tokens traded |

---

## 7. Risks and Mitigation

### Risk 1: Sentinel-2 Insufficient for Useful Mineral Detection

**Probability:** Low (20%). Sentinel-2 mineral mapping is published extensively in peer-reviewed literature.

**Impact:** Phase 0 deliverables are weaker than expected.

**Mitigation:** Sentinel-2 has only 13 bands, so it cannot distinguish fine mineral differences. But it reliably maps broad alteration classes (iron oxide, clay, carbonate) in arid terrain. For finer discrimination, EMIT provides 285 bands at zero cost. Plan B: Skip straight to EMIT-based products in humid regions where Sentinel-2 is insufficient.

### Risk 2: GNN Spectral Prediction Does Not Work

**Probability:** Medium-High (40-50%). This is a research problem, not an engineering problem.

**Impact:** The core innovation (predicted spectrum search) is delayed or impossible.

**Mitigation:** The business does not depend on spectral prediction working. Phases 0-2 produce sellable products using only established remote sensing techniques plus compositional matching to the Materials Engine (Level 1 integration). Spectral prediction (Level 2) is the moonshot that would make GeaSpirit truly unique, but the business survives without it. Plan B: Focus on compositional inference instead of spectral matching — "this alteration assemblage is consistent with these Materials Engine candidates" is still valuable even without predicting the exact spectrum.

### Risk 3: No Customers

**Probability:** Low-Medium (25%). Junior mining companies are notoriously cost-conscious and skeptical of new technology.

**Impact:** No revenue, cannot fund Phase 3+.

**Mitigation:** Start with free pilot projects for 2-3 companies to build case studies. Target companies already using remote sensing consultants (they understand the value proposition, we just need to be cheaper and faster). Attend PDAC 2027 (Toronto, March) with demo results. Also target non-mining clients: environmental monitoring (acid mine drainage), government geological surveys, agriculture (soil mineral mapping).

### Risk 4: Large Competitor Copies the Approach

**Probability:** Medium (30%). KoBold Metals or a well-funded startup could build something similar.

**Impact:** Loss of competitive advantage, price compression.

**Mitigation:** Our moat is the integration itself — the Materials Engine with 76,193 materials, the blockchain layer, and the spectral prediction research are all hard to replicate quickly. Open-source the non-competitive components to build community and network effects. Patent the spectral prediction methodology if it works. Move fast.

### Risk 5: SOST Blockchain Does Not Reach Sufficient Adoption

**Probability:** Medium (35%). Blockchain adoption is uncertain.

**Impact:** Proof of Discovery and marketplace features have no users.

**Mitigation:** The geological intelligence business works without blockchain. The blockchain layer is a value-add, not a requirement. If SOST adoption is slow, the marketplace can operate on a traditional database with blockchain registration as an optional premium feature. The token demand created by the geological business itself helps bootstrap adoption.

---

## 8. Path to the "Holy Grail"

The ultimate goal: **look at terrain from orbit and know with high probability what minerals and metals lie beneath the surface.**

### A) Scientific Advances Needed

1. **Spectral prediction from crystal structure** — bridging computational materials science and spectroscopy (Section 3). This is the closest to being solved: the physics is well-understood, the ML tools exist, the training data is the bottleneck.

2. **Alteration halo quantitative modeling** — converting surface mineral assemblage maps into subsurface ore body probability distributions. Currently done qualitatively by expert geologists. Needs to be formalized into ML models trained on deposits with known subsurface data.

3. **Multi-physics inversion** — combining spectral, gravity, magnetic, and potentially seismic data into a single 3D model of subsurface composition. Each data type constrains different physical properties. Joint inversion is an active research area in geophysics but is not yet routine for mineral exploration.

4. **Uncertainty quantification** — for any subsurface prediction to be actionable, it needs calibrated uncertainty estimates. A "60% probability of Cu-Au porphyry at 200-400m depth" is useful; an uncalibrated prediction is not.

### B) New Data Available in 2-5 Years

| Mission/Dataset | Expected | What It Adds |
|---|---|---|
| **NISAR** (NASA/ISRO) | 2025 (launched) | L-band SAR, global coverage, soil moisture/structure at depth |
| **NASA SBG** | ~2028-2030 | VSWIR imaging spectrometer (10nm resolution) + TIR. Global coverage. Free. This is the game-changer for mineral mapping. |
| **Sentinel-2 Next Gen** | ~2028+ | More spectral bands, higher resolution |
| **SWOT** | Operating | Surface water mapping, indirect geological inference |
| **Commercial hyperspectral** | Now (Planet, Pixxel) | 150-400 bands, 5-30m resolution, but costly |
| **Drilling databases** | Ongoing | Provinces releasing historical drilling data; ML on drill logs for subsurface labels |

### C) How Each Phase Contributes

- **Phase 0:** Establishes surface mineral mapping capability (the foundation)
- **Phase 1:** Adds radar/structural data (surface + shallow subsurface indicators)
- **Phase 2:** Connects surface observations to crystal-structure-level understanding via Materials Engine
- **Phase 3:** Adds depth-proxy inference through alteration halo modeling and hyperspectral precision (indirect, not direct measurement)
- **Phase 4:** Integrates all data layers for subsurface probability estimation (statistical, not imaging)

Each phase adds a "data dimension" to the model. Surface spectral is 2D. Add radar for surface roughness/moisture. Add alteration modeling for shallow 3D. Add geophysics for deep 3D.

### D) Is It a Data Problem, Model Problem, Physics Problem, or All Three?

**All three, but in different proportions:**

- **Data problem (50%):** The biggest bottleneck is labeled subsurface data. We know what is on the surface (from satellites). We know what is underground at drill sites. The gap is that drilled sites are a tiny fraction of Earth's surface, and most drilling data is proprietary. As more historical drilling data becomes public, and as new missions (SBG) provide better surface data, the data problem shrinks.

- **Model problem (30%):** Current ML models for geoscience are mostly 2D (surface classification). Extending to 3D subsurface estimation with calibrated uncertainty is a model architecture challenge. Geoscience foundation models (similar to weather prediction models like GraphCast) would help.

- **Physics problem (20%):** Spectral remote sensing physically cannot penetrate rock. Electromagnetic radiation in VNIR/SWIR interacts with the top ~50 micrometers of material. All subsurface inference is *indirect* — based on surface expressions of subsurface processes (alteration halos, structural geology, geochemical dispersion, vegetation anomalies). This is a fundamental limitation that no amount of data or better models can overcome. The physics ceiling for purely spectral subsurface detection is approximately 0m (direct) to ~500m (indirect, for large systems with strong surface expression).

### E) Creative Approaches Nobody Is Trying

**1. Soil microbiology as mineral proxy:**
Microbial communities in soil are influenced by substrate geochemistry. Acidophilic bacteria (Acidithiobacillus) concentrate over sulfide ore bodies. Metagenomic surveys of soil could, in principle, reveal subsurface mineralogy. Not yet practical from orbit, but soil sampling + metagenomics + ML could be a Phase 4 data source.

**2. Vegetation as geochemical indicator (biogeochemistry):**
Plants absorb metals from soil, and metal stress causes detectable spectral changes in vegetation (blue shift in red edge, reduced chlorophyll absorption). "Geobotanical remote sensing" is a real field with published results for Cu, Zn, Au anomalies. Sentinel-2's red-edge bands (B05, B06, B07) are well-suited for this. This is achievable in Phase 2 and could work in vegetated terrain where mineral mapping fails.

**3. Gravimetry + magnetometry combined with spectral:**
Public gravity and magnetic surveys exist for many countries (USGS, Geoscience Australia, GSC). Dense metallic ore bodies create gravity highs and magnetic anomalies. Combining gravity/magnetic anomaly maps with spectral alteration maps constrains subsurface models significantly. Free data, just needs integration.

**4. Passive seismic (ambient noise):**
Ambient seismic noise from ocean waves and human activity can be processed to reveal shallow crustal structure (top 1-5 km). Dense seismometer networks (USArray) have mapped velocity structure across the USA. Anomalous velocities correlate with mineral deposits. This is a long-term (Phase 4+) data source requiring seismometer deployments, not orbital.

**5. ML on historical drilling data for subsurface inference training:**
The single most impactful creative approach. Millions of drill holes exist worldwide with logged lithology, assay results, and depth. Most are locked in PDF reports or proprietary databases. A concerted effort to digitize and standardize historical drilling data would provide the training labels needed for subsurface ML models. Several jurisdictions (Ontario, Quebec, Western Australia) are digitizing their historical drilling records. This is where the biggest data opportunity lies.

**6. Temporal change detection:**
Monitoring the same area over months/years reveals processes: seasonal moisture patterns expose different minerals, vegetation stress changes with seasons, and active geological processes (hot springs, fumaroles, seepage) vary temporally. Multi-temporal stacks of Sentinel-2 data (free, revisit every 5 days) contain temporal signatures that single-date analysis misses.

---

## 9. Immediate Next Step

### This Week: Build the Sentinel-2 Mineral Alteration Pipeline ($0)

**Day 1-2:** Set up Google Earth Engine Python environment. Write scripts to:
- Pull Sentinel-2 L2A imagery for a 50x50 km test area in the Atacama Desert, Chile (cloud-free, highly mineralized, well-studied reference area)
- Compute 6 standard band ratio indices: iron oxide (B04/B02), ferric iron (B04/B03), clay/hydroxyl (B11/B12), carbonate (B11/B13 where available, or B11/B12 variant), ferrous iron (B11/B08A), vegetation mask (NDVI B08/B04)
- Generate false-color composites optimized for geology (B12-B11-B04, B11-B08-B02)

**Day 3-4:** Spectral angle mapper implementation:
- Load USGS Spectral Library v7 reference spectra for key minerals (kaolinite, montmorillonite, illite, goethite, hematite, jarosite, calcite, dolomite, chlorite, epidote)
- Resample reference spectra to Sentinel-2 band centers
- Run SAM classification on test imagery
- Validate against published geological maps of the Atacama

**Day 5-6:** Materials Engine cross-reference:
- For each detected mineral class, query the Materials Engine database
- List all materials in the engine matching the detected composition + crystal system
- Identify any novel candidates in the same chemical space
- Generate first integrated report: "Sentinel-2 detected [mineral class] → Materials Engine has [N] matching phases, [M] novel candidates"

**Day 7:** Package as a reproducible pipeline (CLI script) and generate the first demo PDF report.

**Deliverable by end of week:** A working Python pipeline that takes geographic coordinates and outputs a mineral alteration map with Materials Engine cross-references. Zero cost. Ready to show to first potential clients.

---

## Appendix: Key Data Sources Reference

| Source | URL | Cost | Key Content |
|---|---|---|---|
| Sentinel-2 L2A | dataspace.copernicus.eu | Free | 13 bands, 10-60m, 5-day revisit |
| EMIT | search.earthdata.nasa.gov | Free | 285 bands, 60m, ISS orbit |
| Sentinel-1 | dataspace.copernicus.eu | Free | C-band SAR, 10m, 6-day revisit |
| ASTER | search.earthdata.nasa.gov | Free | 14 bands (VNIR+SWIR+TIR), 15-90m |
| USGS Spectral Library v7 | speclab.cr.usgs.gov | Free | 1,371 spectra, 481 minerals |
| USGS MRDS | mrdata.usgs.gov | Free | 50,000+ mineral deposit records |
| Google Earth Engine | earthengine.google.com | Free (research) | Petabyte-scale processing |
| RRUFF | rruff.info | Free | 4,000+ mineral structures + spectra |
| Materials Project | materialsproject.org | Free (API) | 150,000+ computed structures |
| JARVIS-DFT | jarvis.nist.gov | Free | 55,000+ structures + properties |
| SOST Materials Engine | local | Operational | 76,193 materials, GNN models, generation pipeline |

---

*Document prepared for SOST GeaSpirit strategic planning. All cost estimates, timelines, and probability assessments reflect honest evaluation as of 2026-03-20. This is a living document — update after each phase milestone.*

---

## Confirmed Architecture (Phase 5G, March 2026)

- **Zone-specific models** as production architecture (AUC 0.72-0.86)
- **AOI heuristic scanner** as global product (works anywhere, no training needed)
- **Transfer learning abandoned** for satellite features (confirmed across 5 zones)
- **Labels are #1 bottleneck** in every zone (labels > sensors > model tuning)
- **Custom AOI capability demonstrated** (Spain: Banos de Mula, Barqueros, Salave)
- **10 AOIs in registry**, 162 targets with exact coordinates
- **Direct GNN inference working** (CGCNN forward pass on crystal structures)
- **Blockers**: EMIT (Earthdata auth), GA geophysics (manual download)

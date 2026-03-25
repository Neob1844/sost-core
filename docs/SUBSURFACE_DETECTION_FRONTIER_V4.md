# Subsurface Detection — Frontier Research V4

**Date:** 2026-03-25
**Status:** Research document — new ideas beyond V2 and V3
**Prerequisite reading:** SUBSURFACE_DETECTION_THEORY_V2.md, SUBSURFACE_DETECTION_EXPERIMENTS_V3.md

---

## Executive Summary

GeaSpirit has confirmed that long-term thermal proxies provide a moderate but real signal for mineral prospectivity (Thermal V2: d=-0.627, +0.013 AUC, replicated across 2 zones). EMIT hyperspectral shows strong alteration signal (hydroxyl d=+0.645 at Chuquicamata). ML residual decomposition was negative (discarded).

This document explores the **next frontier**: physically grounded ideas that have NOT been tested in V2 or V3, ordered by viability. The ultimate goal — probabilistic subsurface mineral inference at depth — requires stacking multiple independent weak signals, not finding a single magic sensor.

**Framing:** Everything here is **proxy-based inference**, not direct subsurface imaging. No satellite can see through rock. Every technique infers subsurface conditions from surface observables. The value comes from combining independent signals that are each individually weak but jointly powerful.

---

## Current State

| Signal | Status | Result |
|--------|--------|--------|
| 20-year thermal amplitude | **CONFIRMED** | d=-0.627, +0.013 AUC, 2 zones |
| EMIT alteration minerals | **PROMISING** | hydroxyl d=+0.645, clay d=+0.516 |
| ML residual maps | **NEGATIVE** | Discarded — no independent signal |
| Spatial gradients | **NEGATIVE** | -0.006 AUC at Kalgoorlie — discarded |
| PCA embeddings | **CONFIRMED (zone-specific)** | +0.026 AUC at Kalgoorlie, NEGATIVE at porphyry zones |
| EMIT porphyry replication (Peru) | **PENDING** | 50 granules found via CMR, download pending |
| Aeromagnetics + radiometrics | **TESTED — NEUTRAL** | +0.002 AUC at Kalgoorlie, K/Th ratio relevant |
| Multiscale texture | Proposed (V3) | Not yet tested |
| NDVI↔thermal cross-correlation | Proposed (V3) | Not yet tested |
| InSAR coherence | Proposed (V3) | Not yet tested |
| Night-time thermal | Proposed (V3) | Partially redundant |
| Foundation model embeddings | **TESTED — NEUTRAL** | +0.004 AUC at Kalgoorlie (strict block CV) |
| Post-rainfall SAR drying | Proposed (6E) | HIGH priority, needs pipeline |
| Spectral unmixing endmembers | Proposed (6E) | MEDIUM priority, ready to test |

---

## NEW Ideas — Not in V2 or V3

### Idea 1: Post-Rainfall Differential Drying Rate (SAR)

**Physical basis:** After rainfall, altered rock (clay-rich from hydrothermal alteration) retains moisture longer than unaltered rock. Silicified zones shed water faster. This creates a **time-dependent moisture contrast** that SAR backscatter can detect.

**What's new vs V3 "soil moisture anomaly persistence":** V3 Idea 4 looked at coarse-resolution (10-40km) soil moisture products and was rated INVIABLE due to resolution. THIS idea uses **Sentinel-1 SAR at 10m resolution** with temporal differencing: backscatter_after_rain - backscatter_before_rain = drying rate map. The resolution is 1000x finer than SMAP.

**Data:** Sentinel-1 (free, 12-day repeat), CHIRPS rainfall (free, daily, 5km). Need to identify rain events, then compare SAR backscatter at t+1day, t+6days, t+12days.

**Difficulty:** Medium. Requires aligning SAR acquisitions with rainfall events.

**Risk of false signal:** Medium. Soil depth, vegetation, slope all affect drying rate.

**Published research:** SAR change detection for soil moisture mapping is well-established (Bauer-Marschallinger et al., 2019, "Toward global soil moisture monitoring with Sentinel-1", IEEE TGRS). However, using drying RATE as a lithology/alteration proxy is underexplored. Some work in archaeological remote sensing uses similar approaches (Tapete & Cigna, 2019).

**Viability:** HIGH — all data free, physically sound, testable at Kalgoorlie.

---

### Idea 2: Persistent Nighttime Thermal Offset (Not Seasonal)

**Physical basis:** Sulfide oxidation is exothermic. Pyrite (FeS2) oxidizing to iron sulfate releases heat. Over a large orebody, this could create a **constant** thermal offset of 0.1-0.5°C above ambient, visible at night when solar heating is absent.

**What's new vs V3 "night-time cooling" and thermal V2:** V3 Idea 6 looked at diurnal range (day-night difference) and was rated partially redundant with thermal amplitude. Thermal V2 measured seasonal amplitude. THIS idea looks for an **absolute persistent offset** — a pixel that is consistently 0.1-0.5°C warmer than its neighbors AT NIGHT, EVERY NIGHT, ALL YEAR. Not seasonal variation, but a constant heat source.

**Data:** MODIS LST nighttime (1km, daily, 20+ years). ECOSTRESS (70m, irregular coverage). Landsat thermal (30m day-only — not usable for night).

**Difficulty:** High. The signal (0.1-0.5°C) is near the noise floor of MODIS (1km pixels average out the signal). ECOSTRESS has the resolution but limited coverage.

**Published research:** Sulfide oxidation heat has been measured in tailings ponds (Amos et al., 2015, "Geochemistry and source of oxidative heating"). Surface expression over intact orebodies is theoretically possible but no published satellite detection found.

**Viability:** LOW at MODIS resolution (1km >> orebody size). MODERATE if ECOSTRESS coverage exists over an AOI. Speculative.

---

### Idea 3: Multi-Decadal Vegetation Trend as Geochemical Stress Proxy

**Physical basis:** Soil over mineral deposits has elevated heavy metal concentrations (Cu, Zn, As, Pb) from weathering. These metals cause chronic plant stress. Over decades, this manifests as **slower vegetation recovery**, **reduced maximum greenness**, or **species composition change** detectable in 20+ year NDVI trends.

**What's new vs V3 "NDVI↔thermal cross-correlation":** V3 Idea 1 looked at NDVI-thermal temporal correlation, which is a snapshot relationship. THIS looks at the **long-term slope of NDVI per pixel** over 20 years — is vegetation systematically degrading over mineral deposits? This is a fundamentally different signal: temporal TREND, not correlation.

**Data:** Landsat NDVI (30m, 1984-2024 = 40 years). Google Earth Engine can compute per-pixel linear regression of NDVI vs time.

**Difficulty:** Low-Medium. Standard time series analysis.

**Risk of false signal:** Medium-high. Land use change, urbanization, and climate trends dominate NDVI trends in most areas. Need to control for non-geological factors.

**Published research:** Geobotanical anomalies from metal stress are well-documented at field scale (Brooks, 1983, "Biological methods of prospecting for minerals"). Satellite-scale multi-decadal detection is underexplored. Sabins & Ellis (2020, "Remote Sensing: Principles, Interpretation, and Applications", 4th ed.) discuss geobotanical methods but not multi-decadal satellite trends.

**Viability:** MODERATE — testable with free data, but very noisy. Best in semi-arid zones where vegetation is sparse enough that geological signal isn't drowned by land use change. Kalgoorlie or Pilbara could work.

---

### Idea 4: Downstream Water Color Anomaly as Upstream Mineralization Tracer

**Physical basis:** Weathering and natural acid rock drainage from mineralized zones releases dissolved metals (Fe, Cu, Mn) into surface water. This changes water color — iron precipitates produce orange/red staining, copper produces blue-green. Sentinel-2 can detect these color changes in rivers, lakes, and ephemeral streams.

**The new twist:** Instead of mapping KNOWN mine drainage (published extensively), use the anomaly as an EXPLORATION tool — trace color anomalies UPSTREAM to find UNDISCOVERED mineralization. Combine with DEM flow accumulation to map probable source areas.

**Data:** Sentinel-2 (10m visible bands), DEM (SRTM/Copernicus 30m), flow accumulation from DEM.

**Difficulty:** Medium. Water color analysis is well-established. The novel part is the upstream tracing logic.

**Risk of false signal:** Medium. Agricultural runoff, urban discharge, and natural turbidity create similar color changes.

**Published research:** Acid mine drainage detection is extensively published (Riaza & Muller, 2010; Tripathi et al., 2020, "AMD detection using Sentinel-2", Remote Sensing). Using it as an upstream exploration tracer for undiscovered deposits is rare. One relevant paper: Buzzi et al. (2021, "Monitoring acid mine drainage signatures in river waters", IJAEOG).

**Viability:** MODERATE for arid zones with surface water. Limited in hyperarid zones (no surface water). Best suited to Zambia Copperbelt, Peru, or forested zones with rivers.

---

### Idea 5: Evapotranspiration Anomaly Persistence

**Physical basis:** Altered rock (clays, silicification) changes soil water-holding capacity. Clay-altered zones retain more water → higher ET. Silicified zones shed water → lower ET. Over years, this creates persistent ET anomalies.

**What's new vs V3:** V3 Idea 4 was about soil moisture at coarse resolution. THIS uses ET products that are already available at 30-100m resolution (Landsat SSEBop, MODIS ET at 500m). ET integrates soil, vegetation, and climate — a more complete signal than raw soil moisture.

**Data:** SSEBop (USGS, Landsat-based, 30m). MODIS ET (500m, monthly). Both free.

**Difficulty:** Medium. Need multi-year ET composites and anomaly detection.

**Published research:** ET mapping for water resources is extensively published. ET anomalies for mineral exploration specifically: very limited. Hewson et al. (2019) mention ET as a potential indicator in geological mapping context but no direct mineral prospectivity application found.

**Viability:** MODERATE — data available, physically plausible, no published mineral exploration application.

---

### Idea 6: Foundation Model Embeddings for Geological Feature Extraction

**Physical basis:** Pre-trained geospatial foundation models (Prithvi-2, IBM/NASA; SatMAE; S2-MAE) learn rich representations of Earth surface from billions of satellite images. These embeddings capture spatial patterns, textures, and temporal dynamics that hand-crafted features miss.

**What's new vs V2 Idea 4 (Foundation Models):** V2 proposed fine-tuning a foundation model on mineral labels. THIS takes a different approach: use the foundation model as a **feature extractor** (no fine-tuning), concatenate embeddings with traditional features (thermal, spectral, DEM), and train a simple classifier on top. This avoids overfitting and leverages the model's learned texture/pattern understanding.

**Data:** Sentinel-2 imagery (free), pre-trained model weights (publicly available for Prithvi-2).

**Difficulty:** Medium-High. Requires running inference on Prithvi/SatMAE (GPU helpful but not required for per-patch inference).

**Published research:** Prithvi-2 (Jakubik et al., 2024, "Foundation Models for Generalist Geospatial AI") demonstrates strong transfer across tasks. No published application to mineral exploration specifically. This would be genuinely novel if it works.

**Viability:** MODERATE-HIGH — technically feasible, strong theoretical basis, no published mineral application.

---

### Idea 7: SAR Interferometric Phase Stability (Long-Term Coherence Decay)

**Physical basis:** InSAR coherence measures how stable the radar phase is between two acquisitions. Over years, different surface materials lose coherence at different rates. Altered rock surfaces (clay minerals, oxide crusts) may have different coherence decay profiles than unaltered surfaces.

**What's new vs V3 Idea 3 (InSAR coherence):** V3 proposed multi-temporal coherence as a single-pass measure and rated it SPECULATIVE due to atmospheric noise. THIS looks at the **coherence decay curve** over multiple time baselines (12d, 24d, 36d, 6mo, 1yr) — the SHAPE of the decay function, not a single coherence value. Different surface materials have characteristic decay signatures.

**Data:** Sentinel-1 SLC pairs (free from ASF DAAC). Processing: SNAP or ISCE.

**Difficulty:** HIGH. InSAR processing is complex. Atmospheric correction needed.

**Published research:** Coherence-based land classification exists (Jacob et al., 2020). Application to mineral exploration is rare. Barrett et al. (2021) used coherence for geological mapping in arid environments.

**Viability:** LOW-MODERATE — high processing complexity, uncertain signal strength, but free data.

---

### Idea 8: Muon Tomography for Dense Body Detection

**Physical basis:** Cosmic ray muons pass through rock and are absorbed in proportion to rock density. A muon detector placed underground (in a mine or borehole) can image the density distribution of rock above it — like a medical CT scan of the subsurface.

**This is NOT satellite-based.** It requires physical sensors underground. But it's the closest technology to "seeing through rock" that exists.

**Current state:** Operational for volcano imaging (Tanaka et al., 2007). Applied to mining by companies like Muon Solutions Oy (Finland) and Ideon Technologies (Canada). Resolution: ~10m at 100m depth. Cost: $100K-500K per survey. Requires existing underground access (borehole or tunnel).

**Published research:** Baccani et al. (2019, "Muon radiography of ancient mines"); Ideon Technologies (2023) reports on copper exploration in Arizona using borehole muon detectors.

**Viability for GeaSpirit:** NOT VIABLE as a remote sensing technique. Relevant only if GeaSpirit evolves to include ground-truth campaigns. Mentioned for completeness.

---

### Idea 9: Airborne Electromagnetic Public Data Integration

**Physical basis:** Airborne electromagnetic (AEM) surveys map subsurface conductivity to 300-500m depth. Conductive bodies (sulfides, graphite, saline water) show as strong anomalies. This is the most direct non-invasive subsurface detection method available.

**This is NOT satellite data.** However, Geoscience Australia has released extensive AEM survey data under CC-BY 4.0 covering large parts of Australia. This data has never been integrated into a satellite-based prospectivity model.

**Data available:** AusAEM (national-scale, 15km line spacing, ~300m depth), regional surveys at 250m-2km line spacing. All downloadable from GA portal.

**What's new:** Combining AEM conductivity with satellite features (thermal, spectral, DEM) in a fusion model. The AEM provides the subsurface dimension that satellites cannot — this is the closest to the "tungsten at 100m" dream.

**Difficulty:** Medium. Data download and gridding. Integration with existing stack.

**Published research:** AEM for mineral exploration is extensively published (Ley-Cooper et al., 2020, "AusAEM: Australia's airborne electromagnetic survey"). Fusion with satellite features is underexplored.

**Viability:** HIGH for Australian AOIs (Kalgoorlie, Pilbara). NOT available for non-Australian zones. This should be a top priority.

---

### Idea 10: Gravity Gradient Tensor (FTG) Public Data

**Physical basis:** Full Tensor Gravity Gradiometry measures tiny variations in gravitational acceleration caused by density differences underground. Dense ore bodies (massive sulfides, iron formations, kimberlites) create measurable gravity anomalies.

**Data:** Geoscience Australia provides national gravity data (Bouguer anomaly at ~2-5km spacing). Higher-resolution FTG requires commercial surveys ($$$). Some mining company data enters public domain after license expiry.

**Difficulty:** Low (for publicly available gridded gravity). Medium (for integration).

**Published research:** Extensive. FTG for mineral exploration reviewed by Dransfield (2010). GA gravity data: freely available.

**Viability:** MODERATE — coarse public data available for Australia. Useful as a complementary feature but resolution insufficient for deposit-scale detection.

---

## Commercial/Private Techniques — Not Available as Free Data

| Technique | Depth | Resolution | Cost | Public Data? |
|-----------|-------|-----------|------|-------------|
| **Muon tomography** | 100-500m | ~10m | $100-500K | No |
| **Full Tensor Gravity (FTG)** | 500m+ | 50-200m | $50-200K/survey | Partial (GA) |
| **Airborne EM (SkyTEM/VTEM)** | 300-500m | 50-200m | $30-100K/survey | Yes (GA AusAEM) |
| **ZTEM (Z-axis tipper EM)** | 500m+ | 200m | $50-150K | Rare |
| **Airborne magnetics** | 500m+ | 20-80m | $10-50K | Yes (GA) |
| **Airborne radiometrics** | 0-30cm | 50-100m | $10-30K | Yes (GA) |
| **HyLogger drill core scan** | Core depth | mm-scale | $5-20K | Partial (GSWA) |
| **Ground IP/Resistivity** | 200-500m | 10-50m | $20-80K | No |

**Key insight:** Australia (via Geoscience Australia) has the world's most comprehensive free geophysical data. Kalgoorlie and Pilbara have AEM, magnetics, radiometrics, and gravity ALL publicly available. This is a unique opportunity for GeaSpirit.

---

## Untested Combinations

### Combo A: Post-Rainfall Drying Rate + Thermal Amplitude + Spatial Gradients
Triple surface-process proxy: moisture behavior + thermal inertia + structural contacts. All free data, all at 10-30m resolution. If all three show anomalies at the same location, the probability of subsurface alteration increases multiplicatively.

### Combo B: 20-Year NDVI Trend + 20-Year Thermal Trend + Geomorphometry
Triple long-term proxy: vegetation degradation + thermal behavior change + landscape form. 40 years of Landsat data available. Pure time-series fusion.

### Combo C: Downstream Water Color + Upstream DEM Flow + Geology Map
Trace observable surface contamination back to its source using hydrology. Limited to zones with surface water.

### Combo D: AEM Conductivity + Satellite Spectral + Thermal + DEM (Australia only)
The most powerful combination: actual subsurface conductivity data + surface feature stack. This is the closest to the "100m depth" goal. Australia-only due to data availability.

### Combo E: Foundation Model Embeddings + All Traditional Features
Use Prithvi-2 or SatMAE as feature extractor on Sentinel-2 imagery. Concatenate with thermal, spectral, DEM, geomorphometry. Train ensemble classifier. The embeddings capture patterns that hand-crafted features miss.

---

## Prioritized Experimental Plan

| Priority | Experiment | Data | Viability | P(success) | Impact | Sprint |
|----------|-----------|------|-----------|-----------|--------|--------|
| 1 | **Spatial gradients** (V3) | S2+DEM | High | High | High | Sprint 1 |
| 2 | **AEM integration** (Idea 9) | GA AusAEM | High | High | Very High | Sprint 1 |
| 3 | **Post-rainfall drying rate** (Idea 1) | S1+CHIRPS | High | Medium | High | Sprint 2 |
| 4 | **Foundation model embeddings** (Idea 6) | S2+Prithvi | Medium-High | Medium | Very High | Sprint 2 |
| 5 | **Multi-decadal NDVI trend** (Idea 3) | Landsat | Medium | Medium | Medium | Sprint 2 |
| 6 | **ET anomaly persistence** (Idea 5) | SSEBop | Medium | Low-Med | Medium | Sprint 3 |
| 7 | **Downstream water tracing** (Idea 4) | S2+DEM | Medium | Medium | Medium | Sprint 3 |
| 8 | **Coherence decay curves** (Idea 7) | S1 SLC | Low-Med | Low | Medium | Sprint 3 |
| 9 | **Persistent night thermal** (Idea 2) | MODIS/ECOS | Low | Low | High | Deferred |
| 10 | **Muon tomography** (Idea 8) | Ground only | N/A for sat | N/A | Very High | N/A |

### Sprint 1 (immediate): Spatial Gradients + AEM
- Both use existing or freely downloadable data
- Spatial gradients: Sobel/Laplacian on spectral + DEM → test at Kalgoorlie
- AEM: download AusAEM grid for Kalgoorlie → integrate as feature → measure AUC improvement

### Sprint 2 (next): Drying Rate + Foundation Model + NDVI Trend
- Post-rainfall drying: identify rain events in CHIRPS, compute SAR differencing
- Foundation model: run Prithvi-2 inference on Sentinel-2 patches, extract embeddings
- NDVI trend: 20-year per-pixel linear regression in GEE

### Sprint 3 (later): ET + Water Tracing + Coherence
- Lower priority due to lower expected signal or higher complexity

---

## Updated Mineral-Specific Routes

| Mineral | Confirmed Route | Best Untested Route | New Idea (This Doc) |
|---------|----------------|-------------------|---------------------|
| **Gold (Au)** | Thermal + alteration (AUC 0.81) | Spatial gradients (structural contacts) | AEM conductivity fusion |
| **Copper (Cu)** | EMIT alteration + thermal (0.86) | Foundation model embeddings | Post-rainfall drying rate |
| **Graphite** | Thermal anomaly (conductor) | AEM conductivity (direct) | SAR coherence decay |
| **Platinum** | DEM + magnetics proxy | AEM conductivity | Gravity + magnetics fusion |
| **Silver** | Alteration (epithermal) | NDVI trend (Hg/As stress) | Water color tracing |
| **Lithium** | Spectral (salares) | ET anomaly (brine) | Foundation model on VNIR |
| **Cobalt** | Associated with Cu/Ni | AEM (sedimentary Cu-Co) | Post-rainfall + spectral |
| **REE** | Spectral (carbonatite) | Spatial gradients (circular) | Thorium radiometrics (GA) |
| **Uranium** | Gamma ray (direct) | Radiometrics (GA public) | NDVI trend (radiotoxicity) |
| **Diamonds** | Magnetics (kimberlite) | AEM + gravity fusion | Foundation model (circular structures) |

---

## What I Would Try First, Second, and Third

### FIRST: AEM Integration at Kalgoorlie (Sprint 1)

**Why:** This is the single highest-impact addition possible. AEM directly measures subsurface conductivity to 300m depth. Geoscience Australia provides it free (AusAEM program, East Yilgarn coverage confirmed). No other free data source gives direct subsurface information. If AEM + satellite features improves the model significantly, GeaSpirit gains a unique competitive advantage for Australian AOIs.

**Expected AUC improvement:** +0.03 to +0.10 (speculative but physically well-grounded — AEM literally measures what we're trying to infer).

### SECOND: Spatial Gradient Features at Kalgoorlie (Sprint 1)

**Why:** Zero-cost, zero-download, uses existing data. Deposits cluster near geological contacts. Edge detection on spectral/DEM layers finds contacts. This should be a quick test with clear pass/fail.

**Expected AUC improvement:** +0.005 to +0.02.

### THIRD: Foundation Model Embeddings (Sprint 2)

**Why:** GFM4MPM (Daruna et al., 2024) has already demonstrated foundation models for mineral prospectivity mapping. Prithvi-EO-2.0 is available on HuggingFace. This is no longer purely speculative — there is published precedent. NOTE: must test against GeaSpirit's zone-specific finding (transfer doesn't work for satellite features).

**Expected AUC improvement:** Unknown — could be +0.00 or +0.05.

### BONUS: NVCL Drill Core Data (Sprint 1, minimal effort)

**Why:** The National Virtual Core Library has 690,000+ metres of HyLogger-scanned drill core with Python API (nvcl-kit). This provides ground-truth mineral assemblage data to validate/calibrate satellite-derived alteration maps at Kalgoorlie. Not a feature for the model, but essential calibration data.

### BONUS: Post-Rainfall SAR Drying Rate (Sprint 2, genuinely novel)

**Why:** No one has published drying-rate-vs-alteration for mineral exploration. The physics is sound (argillic alteration retains moisture → delayed SAR recovery). Atacama study showed 5.5 dB SAR changes from 1-3% moisture variation. This could be a genuinely original GeaSpirit contribution.

---

## Honest Assessment: How Close Can We Get to the Dream?

**The dream:** "Tungsten at 100m, coordinates, 83% certainty."

**Reality with current satellite-only approach:**
- We can identify areas with 2-10x higher probability of mineralization
- We cannot specify depth, tonnage, or grade
- We cannot achieve >90% certainty without ground truth
- Probability maps are useful for exploration PRIORITIZATION, not confirmation

**Reality with AEM integration (Australia only):**
- We CAN infer conductivity anomalies to 300m depth
- Combined with surface features, we could identify conductive bodies (sulfides) at depth
- Still cannot determine mineral type, grade, or tonnage
- Could potentially reach 70-85% precision for "conductive anomaly present below 100m"

**Reality with full multi-source fusion (5-10 independent signals):**
- Each signal adds 0.01-0.05 AUC individually
- Combined, they create a probability surface that is substantially better than any single layer
- The correct framing: "multi-proxy probabilistic inference with quantified uncertainty"
- NOT: "subsurface detection" or "mineral imaging"

**The honest answer:** We will never see tungsten from orbit. But we can build probability maps that are good enough to tell a geologist "drill HERE, not there" — and be right 70-85% of the time. That alone has enormous value.

---

## Key Research Findings (Web Search, March 2026)

### Foundation Models — GFM4MPM (Directly Relevant)
Daruna et al. (2024), "GFM4MPM: Towards Geospatial Foundation Models for Mineral Prospectivity Mapping," ACM SIGSPATIAL 2024. First paper explicitly applying foundation models to mineral prospectivity. Self-supervised pretraining on unlabeled geospatial data improved robustness. Tested on MVT and CD Pb-Zn deposits. **This directly validates Idea 6.** Also: Prithvi-EO-2.0 (IBM/NASA, Dec 2024) available on HuggingFace. NOTE: GeaSpirit's finding that "zone-specific architecture confirmed (transfer does NOT work)" may conflict with the foundation model premise — worth testing explicitly.

### Ambient Noise Tomography — Fleet Space (Operational)
Fleet Space Technologies (Australia) has commercialized satellite-connected ANT. Multiple 2023-2024 case studies: IOCG deposits under 750m cover, uranium in Athabasca Basin (confirmed by drilling), porphyry copper to 500m+. Shan et al. (2024), "Real-Time ANT of the Hillside IOCG Deposit," Minerals 14(3), 254. **Not free data (field service), but relevant as validation pathway for GeaSpirit targets.**

### National Virtual Core Library — NVCL (Australia, Free)
AuScope NVCL: 690,000+ metres of HyLogger-scanned drill core from 2,340+ holes. Python API: nvcl-kit (PyPI). CSIRO released MyLogger (2023) for automated interpretation. **Directly usable as ground truth for Kalgoorlie alteration maps.** This is a hidden gem.

### SAR Drying Rate — Novel, Unpublished for Minerals
Bachri et al. (2021), "Lithology Discrimination Using Sentinel-1 Dual-Pol Data," Remote Sensing 13(7). Aznar et al. (2022), Sentinel-1 backscatter in Atacama: 1-3% soil moisture changes produce up to 5.5 dB SAR intensity changes. **No one has published drying-rate-vs-alteration for mineral exploration. This would be genuinely original.**

### AMD Water Tracing — Proven for Monitoring, Novel for Prospecting
Rampheri et al. (2024), "ML for AMD Mapping Using Sentinel-2 and WorldView-3," Remote Sensing 16(24). Strong classification accuracy for iron precipitates. **Reverse inference (trace upstream to undiscovered source) is unpublished as exploration method.**

### NDVI Stress — VIGS Index
Hede et al. (2015), "VIGS: a new vegetation index for detecting vegetation anomalies due to mineral deposits," Remote Sensing of Environment. Outperforms NDVI for metal-induced vegetation stress. **Multi-decadal trend application is underexplored.**

### Self-Potential from Satellite — DEAD END
Biswas et al. (2024), Scientific Reports. SP remains millivolt-scale, requires ground electrodes. **No remote sensing pathway exists. Confirmed INVIABLE.**

### Drone NMR — NOT VIABLE
MDPI Drones (2025) review confirms no prototype exists. Loop area and transmit power requirements are physically incompatible with drone payloads. **Confirmed INVIABLE.**

### Optical Polarimetry — EMERGING
GARAI-A (Satlantis, launched Jan 2025) is the first dedicated optical polarimetric satellite. No published mineral mapping from orbit yet. **Watch for 2026-2027 publications.**

### Sulfide Oxidation Heat — REAL BUT UNDETECTABLE
Knobloch & Lottermoser (2020), "IR Thermography: Visualise Sulphide Oxidation," Minerals 10(11). Temperature rises confirmed at hand-sample scale. Surface flux at satellite resolution is orders of magnitude below noise floor. **Confirmed LOW viability from orbit.**

### AusAEM — Confirmed Free and Production Quality
AusAEM program: national-scale SkyTEM surveys at 20km line spacing. East Yilgarn, Eastern Goldfields coverage. All data freely downloadable from GA. **Top priority for Kalgoorlie integration.** Queensland GSQ also releases AEM data.

### Muon Tomography — NOW OPERATIONAL
Ideon Technologies deployed commercially at Rio Tinto Bingham Canyon (2024), BHP Nickel West. Zhang et al. (2024), "Muography in mineral exploration: Zaozigou gold mine," GJI 237(1). 10m resolution at 600m depth. **Not satellite, but the closest technology to "seeing through rock" that exists.**

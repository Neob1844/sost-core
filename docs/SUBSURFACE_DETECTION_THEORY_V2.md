# Subsurface Mineral Detection — Theoretical Framework V2

**Date:** 2026-03-24
**Status:** Research document — hypotheses and theoretical analysis
**Scope:** Novel approaches to inferring subsurface mineralogy from free remote sensing data

---

## Executive Summary

This document evaluates non-obvious pathways for detecting subsurface minerals using freely available satellite and airborne data. The key insight: **direct detection of most minerals from orbit is physically impossible**, but several indirect pathways remain underexplored:

1. **Solar-Induced Fluorescence (SIF)** as a proxy for geochemical soil stress
2. **20-year thermal time series** for differential thermal inertia mapping
3. **InSAR seasonal deformation** as a lithology discriminator
4. **Foundation models** (self-supervised) trained on global geology
5. **TROPOMI trace gases** over active hydrothermal systems
6. **Biogeochemical indicators** detectable spectrally

The most promising near-term experiments use data we already have access to.

---

## Mineral-by-Mineral Analysis

### A. GRAPHITE (Conductor, metamorphic)

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| EM conductivity | Direct | **INVIABLE from orbit** | Requires ground/airborne EM |
| Swarm magnetic | Indirect | **SPECULATIVE** | Resolution ~300km, far too coarse |
| Metamorphic belt mapping | Proxy | **VIABLE** | Sentinel-2 + DEM + geology maps |
| Self-potential | Direct | **INVIABLE from orbit** | Requires ground electrodes |
| Spectral absorption | Direct | **MARGINAL** | Graphite is spectrally featureless (absorbs all) |
| Airborne EM (public) | Direct | **VIABLE where available** | GA, USGS datasets |
| SIF stress over graphite soils | Indirect | **SPECULATIVE** | No published evidence |
| InSAR deformation | Indirect | **SPECULATIVE** | Graphite schists may deform differently |

**Best route:** Metamorphic belt + structural mapping + airborne EM where available.
**Speculative route:** InSAR seasonal deformation over graphite schist vs non-graphite schist.

### B. GOLD (Dense, inert, invisible)

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| Spectral (gold itself) | Direct | **INVIABLE** | Gold has no spectral signature at ppm levels |
| Alteration halos | Proxy | **VIABLE (proven)** | Sericite, silica, jarosite — GeaSpirit already does this |
| Gossan detection | Proxy | **VIABLE** | Iron oxide caps detectable with Sentinel-2/EMIT |
| Eucalyptus Au accumulation | Bio-proxy | **SPECULATIVE** | CSIRO 2013: Au in eucalyptus leaves. Spectral detection unproven |
| SIF over Au-stressed vegetation | Bio-proxy | **SPECULATIVE** | No published research |
| 20-year thermal amplitude | Temporal | **SPECULATIVE** | Quartz veins have different thermal inertia |
| Placer geomorphology | Proxy | **VIABLE** | DEM + river analysis |
| Mercury vapor | Gas | **INVIABLE from orbit** | Requires ground/drone sensor |

**Best route:** Alteration halo mapping (already AUC 0.81 at Kalgoorlie).
**Speculative route:** 20-year Landsat thermal time series — quartz-rich zones should show lower thermal amplitude than surrounding rock (higher thermal inertia of silicification).

### C. PLATINUM (Ultra-dense, mafic intrusions)

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| Magnetic anomaly (intrusions) | Direct | **VIABLE** | Mafic intrusions are strongly magnetic |
| Serpentinite spectral | Proxy | **VIABLE** | EMIT can detect serpentine minerals |
| Chromite spectral | Proxy | **VIABLE** | Chromite absorption features in VNIR |
| DEM circular features | Morphologic | **VIABLE** | Layered intrusions create concentric ridges |
| Gravimetry (GOCE) | Indirect | **INVIABLE** | Resolution too coarse (~100km) |
| Swarm magnetic | Indirect | **MARGINAL** | Bushveld-scale may be detectable |
| Serpentine barrens vegetation | Bio-proxy | **VIABLE** | Distinctive flora on ultramafic soils |
| Thermal inertia (dense rock) | Indirect | **SPECULATIVE** | Ultramafic rocks have high thermal inertia |

**Best route:** Magnetic + spectral (serpentinite/chromite) + DEM morphology.
**Speculative route:** Sentinel-2 red edge for serpentine barren vegetation mapping → ultramafic indicator.

### D. SILVER (Conductor, epithermal)

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| Argillic alteration | Proxy | **VIABLE** | Alunite, kaolinite, dickita → EMIT |
| Silica caps | Proxy | **VIABLE** | Chalcedony/opal spectral features |
| Thermal anomaly | Proxy | **MARGINAL** | Only for active systems (hot springs) |
| TROPOMI SO2 | Gas | **SPECULATIVE** | Epithermal systems emit SO2 near surface |
| pH-altered vegetation | Bio-proxy | **SPECULATIVE** | Acid soils from alteration → plant stress |

**Best route:** Epithermal alteration mapping (EMIT + Sentinel-2).
**Speculative route:** TROPOMI SO2 anomaly correlation with known epithermal deposits.

### E. COPPER (Porphyry, hydrothermal)

Already AUC 0.86 at Chuquicamata with current approach. Incremental improvements:

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| EMIT mineral zonation | Proxy | **VIABLE** | Map propilytic→argillic→sericitic→potassic zones |
| Red edge Cu stress | Bio-proxy | **SPECULATIVE** | Cu toxicity causes specific chlorophyll changes |
| Seasonal series | Temporal | **SPECULATIVE** | Alteration zones may have different seasonal response |
| SIF fluorescence | Bio-proxy | **SPECULATIVE** | Cu-stressed vegetation photosynthesis changes |

**Best route:** EMIT mineral zonation (already planned).
**Speculative route:** SIF comparison between known Cu-stress zones and background.

### F. LITHIUM (Salares, pegmatites, clays)

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| Salar spectral | Direct | **VIABLE** | Sentinel-2 detects salt flats directly |
| Borate spectral | Proxy | **VIABLE** | EMIT can detect borate minerals in salars |
| Endorheic basin DEM | Morphologic | **VIABLE** | Basins detectable from DEM alone |
| EMIT Li-clay (hectorite) | Direct | **VIABLE** | Hectorite has SWIR absorption at 2.31μm |
| Spodumene spectral | Direct | **MARGINAL** | Weak spectral features |
| Groundwater chemistry proxy | Indirect | **INVIABLE from orbit** | Requires sampling |

**Best route:** Salar mapping + borate spectral + DEM basins. Li-clays via EMIT.
**Speculative route:** EMIT hectorite mapping in sedimentary basins (e.g., Nevada).

### G. COBALT (Cu-Co sedimentary, Ni-laterite)

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| Laterite spectral | Proxy | **VIABLE** | Iron oxides/hydroxides → Sentinel-2 |
| Co mineral color | Direct | **MARGINAL** | Erythrite (Co arsenate) is pink but rare in outcrops |
| Ni/Co hyperaccumulator plants | Bio-proxy | **VIABLE** | Alyssum bertolonii documented |
| Radiometric K/Th/U anomaly | Indirect | **MARGINAL** | Laterites often have distinct radiometric signature |
| Cu-Co association | Proxy | **VIABLE** | Map Cu alteration → Co follows |

**Best route:** Laterite mapping + Cu association mapping.
**Speculative route:** Hyperaccumulator plant spectral signatures via EMIT.

### H. RARE EARTH ELEMENTS (Carbonatites, placers)

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| Th/U radiometric anomaly | Direct | **VIABLE** | Carbonatites have high Th/U |
| Magnetic anomaly | Direct | **VIABLE** | Carbonatites are magnetically distinct |
| EMIT monazite/bastnäsite | Direct | **SPECULATIVE** | These minerals have absorption features at 2.2-2.35μm |
| Alkaline vegetation response | Bio-proxy | **SPECULATIVE** | Alkaline soils from carbonatite weathering |
| Circular DEM features | Morphologic | **VIABLE** | Carbonatite pipes create circular depressions |

**Best route:** Radiometric Th anomaly + magnetic + DEM circular features.
**Speculative route:** EMIT REE-mineral mapping in known carbonatite complexes.

### I. URANIUM (Radioactive — directly detectable)

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| Gamma-ray (airborne) | **DIRECT** | **VIABLE** | The only mineral directly detectable by its radiation |
| U-channel radiometric | Direct | **VIABLE** | Public airborne data (USGS, GA) |
| Inconformity structure | Proxy | **VIABLE** | DEM + SAR for Athabasca-type deposits |
| Vegetation indicator (Astragalus) | Bio-proxy | **VIABLE** | Well-documented Se/U indicator plants |
| Radon gas | Direct | **INVIABLE from orbit** | Requires ground/drone detection |
| InSAR over sandstone | Indirect | **SPECULATIVE** | Sandstone-hosted U may deform differently |

**Best route:** Airborne radiometric U-channel + structural mapping (DEM/SAR).
**Speculative route:** SIF over Astragalus indicator plant communities.

### J. DIAMONDS (Kimberlites)

| Signal | Type | Viability | Notes |
|--------|------|-----------|-------|
| Magnetic anomaly (circular) | Direct | **VIABLE** | Kimberlite pipes are magnetically distinct |
| DEM circular depression | Morphologic | **VIABLE** | Eroded diatremes create circular lakes/depressions |
| SAR texture | Indirect | **SPECULATIVE** | Kimberlite weathering creates different surface texture |
| Indicator minerals in drains | Proxy | **VIABLE but ground-based** | Pyrope, chromite in streams |
| Craton boundary mapping | Regional | **VIABLE** | Diamonds only occur in Archean cratons |
| Vegetation over kimberlite | Bio-proxy | **SPECULATIVE** | Ultramafic soil → distinctive flora |

**Best route:** Aeromagnetic circular anomalies + DEM depressions + craton mapping.
**Speculative route:** SAR backscatter texture analysis for kimberlite-weathered surfaces.

---

## General Unexploited Signals

### 1. Solar-Induced Fluorescence (SIF)

**Physical basis:** Plants under geochemical stress (heavy metals in soil) have altered photosynthesis, producing different SIF signatures. OCO-2/3, TROPOMI, and GOSAT measure SIF globally at no cost.

**Hypothesis:** SIF anomalies correlate with subsurface mineralization via root-zone geochemistry.

**Viability:** SPECULATIVE but testable. No published research specifically linking SIF to mineral deposits as of 2025. Published work exists on SIF and vegetation stress from contaminated soils.

**Key challenge:** SIF resolution (~2-7km) may be too coarse for individual deposits.

### 2. 20-Year Thermal Time Series

**Physical basis:** Different rock types have different thermal inertia. Over 20+ years of Landsat thermal data (free), the seasonal temperature amplitude at each pixel encodes thermal properties of the near-surface geology.

**Hypothesis:** Silicified zones (quartz veins, alteration halos) show lower thermal amplitude than unaltered rock. Massive sulfides show different thermal response than host rock.

**Viability:** VIABLE to test. Landsat thermal archive is freely available back to 2000. No one has specifically used multi-decadal thermal amplitude as a mineral prospectivity layer.

### 3. InSAR Seasonal Deformation

**Physical basis:** Different lithologies respond differently to seasonal moisture/temperature cycles. Clay-rich alteration zones swell more than fresh rock. This differential deformation is measurable by InSAR (Sentinel-1, free).

**Hypothesis:** Systematic InSAR seasonal deformation patterns correlate with subsurface lithology and alteration.

**Viability:** SPECULATIVE but plausible. Published work exists on InSAR lithology discrimination but not specifically for mineral prospectivity.

### 4. Foundation Models for Geospatial Mineral Detection

**Physical basis:** Self-supervised models (IBM/NASA Prithvi, Google S2-MAE) learn spatial representations from millions of satellite images. Fine-tuned with drill-hole labels, these representations may encode subsurface information learned from global geological patterns.

**Hypothesis:** Foundation model embeddings, fine-tuned on MRDS deposit locations, outperform hand-crafted features for mineral prospectivity.

**Viability:** VIABLE to test. Prithvi model is open-source. MRDS has 300K+ deposit records.

### 5. TROPOMI Trace Gas Anomalies

**Physical basis:** Active hydrothermal systems emit SO2, CO2, H2S. Oxidizing sulfide deposits may release trace gases. TROPOMI measures SO2/CO2/CH4 globally at 5km resolution.

**Hypothesis:** TROPOMI gas anomalies correlate with active mineralized systems.

**Viability:** MARGINAL. Resolution likely too coarse for individual deposits. May work for regional volcanic/hydrothermal belt mapping.

---

## Three Concrete Experiments

### Experiment 1: SIF as Mineral Prospectivity Proxy

**Hypothesis:** OCO-2 SIF signal is statistically different over known mineral deposits vs background.

**Data:** OCO-2 L2 SIF (free, NASA), MRDS deposits (free, USGS), Sentinel-2 (free, ESA).

**Zone:** Chuquicamata, Chile (existing GeaSpirit stack, 43 Cu/Au/Ag labels).

**Method:**
1. Download OCO-2 SIF footprints over Chuquicamata AOI
2. Extract mean SIF within 2km of each deposit vs random background locations
3. Statistical test: two-sample t-test for SIF difference
4. If significant: add SIF as feature to existing model

**Success criterion:** p < 0.05 for SIF difference; AUC improvement if added as feature.

**Risk:** OCO-2 sparse footprints may have insufficient coverage over the AOI.

### Experiment 2: 20-Year Thermal Amplitude Mapping

**Hypothesis:** The seasonal thermal amplitude (max_summer - min_winter) over 20 years of Landsat thermal data differs over mineralized vs unmineralized ground.

**Data:** Landsat 7/8/9 thermal (free, USGS), existing Kalgoorlie labels (205 deposits).

**Zone:** Kalgoorlie, Australia (existing stack, good ground truth).

**Method:**
1. Download all Landsat thermal scenes 2004-2024 for Kalgoorlie AOI
2. Compute per-pixel: mean annual amplitude, trend, variance
3. Extract thermal amplitude at deposit locations vs background
4. Train classifier: thermal features alone → AUC

**Success criterion:** AUC > 0.60 with thermal features alone; AUC improvement when added to existing model.

**Risk:** Thermal resolution (100m) may blur deposit-scale signals.

### Experiment 3: Foundation Model Fine-Tuning

**Hypothesis:** A pre-trained geospatial foundation model (Prithvi or equivalent), fine-tuned on MRDS deposit locations, produces better mineral prospectivity maps than hand-crafted spectral features.

**Data:** Prithvi model (free, HuggingFace), Sentinel-2 imagery (free), MRDS (free).

**Zone:** Kalgoorlie, Australia (existing labels and infrastructure).

**Method:**
1. Load Prithvi model
2. Extract embeddings for Kalgoorlie AOI (per-pixel 64-dim vectors)
3. Train classifier on embeddings vs deposits
4. Compare AUC with existing GeaSpirit model (spectral features)

**Success criterion:** Competitive AUC (>0.75) using only learned representations.

**Risk:** Prithvi trained on 6 bands (not 12+), may lose spectral detail.

---

## What Nobody Has Tried (Most Promising Combinations)

### 1. Multi-Decadal Temporal + Spectral + Structural Fusion
**Idea:** Combine 20-year Landsat thermal trends + current Sentinel-2 spectral + DEM geomorphology + InSAR seasonal deformation into a single per-pixel feature vector. Each source captures a different physical dimension of the subsurface.

**Why new:** Published work uses each source separately. The combination is untested for mineral prospectivity.

### 2. SIF + Red Edge + Soil Moisture Triple Bio-Proxy
**Idea:** Fuse OCO-2 SIF (photosynthesis stress) + Sentinel-2 red edge (chlorophyll stress) + SMAP soil moisture (water availability) as a triple proxy for root-zone geochemistry.

**Why new:** Each has been used individually. The fusion exploits three independent measurements of the same biological response.

### 3. Foundation Model Embedding + Traditional Spectral
**Idea:** Use Prithvi embeddings as additional features alongside hand-crafted GeaSpirit features. The model may learn non-obvious spatial patterns that complement explicit spectral ratios.

**Why new:** Foundation models in mineral exploration are barely explored. Using them as feature augmentation (not replacement) is untested.

---

## Summary Table

| Mineral | Best Proven Route | Best Speculative Route | Viability |
|---------|------------------|----------------------|-----------|
| Graphite | Metamorphic mapping + airborne EM | InSAR deformation over schist | Low |
| Gold | Alteration halos (AUC 0.81) | 20yr thermal + SIF | Medium |
| Platinum | Magnetic + serpentinite spectral | Sentinel-2 serpentine barrens | Medium |
| Silver | Epithermal alteration mapping | TROPOMI SO2 correlation | Low |
| Copper | Porphyry alteration (AUC 0.86) | SIF Cu-stress + EMIT zonation | Medium |
| Lithium | Salar spectral + DEM basins | EMIT hectorite mapping | High |
| Cobalt | Laterite + Cu association | Hyperaccumulator spectral | Low |
| REE | Th/U radiometric + magnetic | EMIT REE minerals | Medium |
| Uranium | **Airborne gamma (direct!)** | SIF Astragalus mapping | High |
| Diamonds | Aeromagnetic + DEM circles | SAR texture analysis | Medium |

---

## Recommendation: What to Try First

1. **First (lowest risk, highest reward):** 20-year Landsat thermal amplitude at Kalgoorlie. We have the labels, the infrastructure, and 20 years of free data. If thermal inertia correlates with mineralization, it's a new feature for every zone.

2. **Second (medium risk, high novelty):** Foundation model embeddings (Prithvi) as feature augmentation. The model is free, the labels exist, and it could reveal patterns invisible to hand-crafted features.

3. **Third (highest novelty, most speculative):** SIF anomaly testing at Chuquicamata. If SIF correlates with Cu mineralization, it opens an entirely new remote sensing pathway.

---

## Honest Limitations

- No experiment here guarantees subsurface detection
- Most ideas are SPECULATIVE — they need testing before claiming value
- Resolution mismatches (SIF at ~5km, deposits at ~1km) are real constraints
- Statistical correlation ≠ physical causation
- What works at Chuquicamata may not work at Kalgoorlie
- Foundation models may learn surface patterns, not subsurface ones

---

*This document is a research hypothesis framework. All claims marked SPECULATIVE require experimental validation. References section will be updated when background literature search completes.*

---

## References and Literature Status

### Confirmed Published Research

| Topic | Key Reference | Status |
|-------|-------------|--------|
| Eucalyptus gold accumulation | Lintern et al. (2013), *Nature Communications* — gold nanoparticles in Eucalyptus leaves | **Confirmed** — biogeochemical, NOT spectral remote sensing |
| ML mineral prospectivity | Zuo R. (2020), "Geodata Science-Based Mineral Prospectivity Mapping", *Natural Resources Research* | **Active field**, large literature |
| EMIT mineral mapping | Thompson D.R. et al. (2024), Green R.O. et al. — EMIT mission results | **Very active**, mineral dust focus |
| Ambient noise tomography | Olivier G. et al. — ambient noise for mine/exploration contexts | **Active geophysical method** |
| Thermal inertia lithology | Rajendran S. et al. — ASTER thermal for geological mapping | **Established** for lithology discrimination |
| Biogeochemical prospecting | Multiple authors — vegetation stress from heavy metals | **Well-established** field |
| Foundation models (Prithvi) | IBM/NASA (2023) — HLS geospatial foundation model | **Available** but not tested for mineral prospectivity |
| Lawley et al. (2022) | Prospectivity modelling of Canadian Ni-Cu-PGE deposits | **ML + geological data** |

### No Published Research Found (as of 2025)

| Topic | Status |
|-------|--------|
| SIF specifically for mineral exploration | **No published research** — concept is novel |
| TROPOMI SO2 for deposit discovery | **No published research** — volcanic monitoring only |
| InSAR seasonal deformation for prospecting | **Niche/marginal** — mine monitoring exists, prospecting does not |
| OCO-2 SIF for heavy metal detection | **No published research** — concept is novel |
| Spectral detection of Au in Eucalyptus | **Not demonstrated** — biogeochemistry works, remote sensing doesn't |
| Swarm magnetic for deposit-scale mapping | **Resolution too coarse** (~300km) — regional tectonic studies only |
| GOCE gravity for deposit detection | **Resolution too coarse** (~80-100km) — regional only |

### Implication

The most novel ideas in this document (SIF, thermal amplitude series, InSAR for prospecting) are **genuinely unexplored territory**. This means:
- Higher risk but higher novelty
- No one to copy from — we would be first
- Results could be negative (signal doesn't exist) or groundbreaking (new prospecting layer)

---

*Document generated 2026-03-24. Literature search limited to training data (cutoff May 2025). Recommend manual Google Scholar verification for all cited references.*

# GeaSpirit Frontier Research V5 — Ultra-Deep Investigation

**Date:** 2026-03-25
**Author:** GeaSpirit Research Team
**Canonical objective:** "Determine that there is a deposit of [mineral] at [X meters] depth at [coordinates], with [83%]+ certainty"
**Current reality:** We cannot do this today. Every new tool, signal, or combination that works gets us one step closer.

---

## 1. Executive Summary

GeaSpirit has confirmed that satellite-based mineral prospectivity works (AUC 0.72-0.94 across 5 zones) but hits a ceiling: surface proxies alone cannot resolve depth, composition, or grade. This document investigates **every available tool we're not using**, **tools that should exist but don't**, **novel physical mechanisms**, and **untried combinations** — prioritized by viability, cost, and expected impact.

**Top 3 recommendations (immediate action):**

1. **Temporal DNA Transformer** — treat each pixel as a 20-year multi-band time series, train a transformer. Nobody has done this for mineral exploration. Free data, cheap compute, high novelty. **Viability: 9/10.**

2. **Foundation Model Fine-tuning** — fine-tune Prithvi-EO-2.0 or Clay on our 5 supervised zones. Tests whether pre-trained representations overcome the cross-zone transfer problem. Open source, free. **Viability: 8/10.**

3. **ECOSTRESS Diurnal Thermal Fusion** — add ISS-based multi-time-of-day thermal to our proven 20-year Landsat pipeline. True apparent thermal inertia. Free data. **Viability: 7/10.**

**Biggest untapped data:** Geoscience Australia national geophysical grids (magnetics, gravity, radiometrics) for Kalgoorlie and USGS Earth MRI airborne geophysics for Arizona. These are standard exploration features used by every major mining company — and they're free.

---

## 2. Existing Tools We're Not Using

### 2.1 Satellite Sensors

| Sensor | Resolution | Cost | Coverage | Mineral Exploration Use | Viability |
|--------|-----------|------|----------|------------------------|-----------|
| **NISAR** (NASA/ISRO) | 3-10m L+S SAR | Free | Global, 12-day | Dual-frequency subsurface proxy. Launched 2024. | **8/10** |
| **ECOSTRESS** (ISS) | 70m thermal | Free | 52°N-52°S | Diurnal thermal inertia (day+night passes) | **7/10** |
| **PALSAR-2** (JAXA) | 25m L-band SAR | Free mosaics | Global | Soil penetration (1-2m in arid), structural mapping | **6/10** |
| **EnMAP** (DLR) | 30m, 242 bands | Free | 52°N-52°S | VNIR+SWIR hyperspectral, complements EMIT | **6/10** |
| **GPM** (NASA) | 10km, 30-min | Free | Global | Precipitation timing for SAR conditioning | **4/10** |
| DESIS (ISS) | 30m VNIR only | Mixed | ISS orbit | VNIR-only, EMIT is superior | 4/10 |
| SAOCOM (CONAE) | 10m L-band | Restricted | South America | Access friction kills utility | 3/10 |
| SMAP | 9-36km | Free | Global | Too coarse, Sentinel-1 better proxy | 3/10 |
| ICESat-2 | 0.7m along-track | Free | Global tracks | Track-only, not wall-to-wall | 2/10 |
| VIIRS thermal | 375-750m | Free | Global | Too coarse, ECOSTRESS better | 2/10 |
| GRACE-FO | 200-500km | Free | Global | Orders of magnitude too coarse | 1/10 |

**Priority actions:**
- **NISAR:** Monitor ASF DAAC for data availability at our AOIs. When L+S data arrives, test L-C difference as subsurface proxy.
- **ECOSTRESS:** Download Collection 2 over 5 zones. Build diurnal thermal inertia features. Fuse with existing 20-year Landsat pipeline.
- **PALSAR-2:** Download free 25m mosaics. Test lineament density as structural feature.

### 2.2 Databases

| Database | Coverage | Cost | Content | Viability |
|----------|----------|------|---------|-----------|
| **GA Geophysical Grids** | Australia | Free | Magnetics 80m, gravity 250m, radiometrics 100m, AEM | **9/10** |
| **USGS Earth MRI** | USA | Free | Airborne magnetics/radiometrics 250-400m | **8/10** (Arizona) |
| **MINDAT API** | Global | Free | 400K+ mineral localities with species assemblages | **7/10** |
| **GSWA Drill Holes** | WA Australia | Free | Structured drill data for Kalgoorlie region | **6/10** |
| **SoilGrids 250m** | Global | Free | Sand/silt/clay, pH, CEC as lithology proxies | **6/10** |
| OneGeology (BGS) | Global | Free | Geological map polygons, inconsistent schemas | 5/10 |
| GPlates | Global | Free | Tectonic reconstructions, research-grade | 5/10 |
| CDS ERA5 | Global | Free | Climate context at 9-25km | 4/10 |
| SIGMINE/ProMine | Brazil/EU | Free | Wrong AOIs currently | 2/10 |

**Priority actions:**
- **GA grids:** Already partially integrated (magnetics). Add national gravity, full radiometrics, AEM conductivity.
- **Earth MRI:** Download Arizona airborne geophysics for the Arizona AOI.
- **MINDAT:** Integrate mineral species assemblage data to enrich training labels.

### 2.3 Processing Tools

| Tool | What it adds | Viability |
|------|-------------|-----------|
| **Prithvi-EO-2.0** (NASA/IBM) | Foundation model, temporal embeddings, open source | **8/10** |
| **Clay Foundation Model** | Open-source ViT with MAE, any sensor support | **8/10** |
| **SoilGrids via WCS** | 250m soil properties as lithology proxy features | **6/10** |
| Microsoft Planetary Computer | NAIP 1m for Arizona, STAC-based access | 5/10 |

---

## 3. Tools That Should Exist But Don't

### 3.1 Ideal Mineral Exploration Sensor

The perfect sensor would measure:
- **Spectral:** 380-2500nm at 5nm resolution, 10m spatial (EMIT quality but systematic coverage)
- **Thermal:** Multi-time-of-day (dawn, noon, afternoon, night) at 30m, weekly
- **SAR:** Dual L+S band, polarimetric, 10m, weekly
- **Subsurface proxy:** Some form of natural-source EM sensitivity integrated

**Status:** NISAR (L+S SAR) + EnMAP/EMIT (hyperspectral) + ECOSTRESS (multi-time thermal) collectively approximate this, but no single platform provides it. The gap: no satellite can do subsurface EM.

### 3.2 Multi-Sensor Exploration Drone

A single drone carrying magnetometer + hyperspectral + thermal + gamma + RTK GPS.

**Status:** PARTIALLY EXISTS. The MULSEDRO project (Denmark, 2022) combined magnetic + hyperspectral. Pioneer Exploration offers modular payloads. But no true all-in-one simultaneous system exists as a commercial product. Barrier: weight (gamma spectrometers are 3-10 kg) limits flight time.

**Cost:** $200-500K development, $10-30K/day operations.
**Resolution:** 5-50cm (vs satellite 10-30m). Valuable for calibration sites.

### 3.3 IoT Geophysical Sensor Network

Low-cost sensor nodes (passive seismic, temperature, EM) deployed in a grid.

**Status:** COMMERCIAL AND OPERATIONAL. Fleet Space ExoSphere (satellite-connected ANT, 2.5km depth, 5-7 day surveys). CAUR Technologies (IoT passive seismic with AI). Both actively deployed at mine sites.

**Cost:** $100-300K per survey campaign.
**GeaSpirit integration:** Satellite screening → IoT ground validation → drilling.

### 3.4 "Geological GPT" — Foundation Model Trained on All Exploration Data

A model pre-trained on every available geological dataset (drill holes, geophysics, satellite, geochemistry) that, given a multi-sensor context, predicts mineral probability.

**Status:** EMERGING. VerAI ($24M, 60+ projects) and GeologicAI ($44M) are building proprietary versions. Open-source alternative: fine-tune Prithvi-EO-2.0 on mineral labels. Nobody has published an open "geological GPT" yet. **This is the most impactful tool that should exist.**

---

## 4. Novel Physical Theories

### 4.1 Temporal DNA — Pixel-Level 20-Year Behavioral Fingerprint

**Concept:** Each pixel has a unique temporal behavior signature: how its spectral bands, temperature, and backscatter change across seasons and years. Mineralized zones have different temporal behavior than barren zones because geology controls vegetation phenology, moisture retention, thermal response, and surface weathering.

**Implementation:** For each pixel, extract a feature vector: 52 weekly composites × 10+ bands × 20 years = 10,400+ dimensions. Train a temporal transformer (attention-based architecture) to classify deposit vs background.

**Physical basis:** SOLID. Extends proven thermal long-term proxy concept to all bands.
**Published:** Temporal transformers for satellite time series exist (crop classification, land cover). **Nobody has applied this to mineral prospectivity.** Genuinely novel.
**Data:** Free (Landsat archive 1984-present, Sentinel-2 2017-present).
**Compute:** $5-20K GPU for training.

**This is the single most promising idea in this document.**

### 4.2 Biogeochemical Spectral Signatures via Hyperspectral

**Concept:** Plants absorb metals from subsurface through roots. Cu, Zn, Au, As modify leaf chemistry (chlorophyll degradation, carotenoid ratios, specific absorption features). With EMIT's 285 bands at 5nm resolution, specific metal signatures in leaf spectra might be detectable.

**Physical basis:** SOLID in lab, WEAK from orbit. Published for airborne hyperspectral (Cu, Zn, Fe, Mo detection in canopies at field scale). Satellite-scale metal-specific detection NOT yet demonstrated.
**Papers:** Mapping leaf metal content from airborne hyperspectral (Scientific Reports, 2020). Hyperspectral detection of Fe/Mo in vegetation (Remote Sensing, 2024).
**Viability: 6/10.** Requires vegetated zones (Zambia, not Chuquicamata). Best tested with EnMAP/EMIT over Zambia Copperbelt.

### 4.3 Passive EM — Natural Source Magnetotellurics

**Concept:** Buried conductive ore bodies (sulfides, graphite) respond to natural EM field variations from lightning and magnetosphere. Measurable at surface with sensitive sensors.

**Status:** MATURE AND OPERATIONAL. Expert Geophysics MobileMT is deployed commercially (airborne passive EM to 1-2km depth). Used at Sabre Uranium Project (2025, 1,536 line-km).
**But:** Requires airborne or ground sensors. No satellite proxy exists.
**GeaSpirit role:** Use MobileMT results as high-quality training labels, not as a direct feature.

### 4.4 Muography for Mineral Exploration

**Concept:** Cosmic muons absorbed proportionally to material density. Dense ore bodies (sulfides, iron oxide) attenuate muon flux. Resolution: 1-10m. Depth: up to 1km.

**Status:** ACTIVE RESEARCH. Surface detectors demonstrated at mine sites (Zaozigou gold mine, GJI 2024). Borehole detectors (24cm diameter) developed 2024. Data acquisition: days to weeks per site.
**Papers:** 3+ major papers in 2023-2025.
**Viability: 2/10.** Fascinating physics but impractical: slow, expensive, requires on-site deployment. Could provide density ground truth for calibrating satellite models.

### 4.5 Geochemistry Proxy via Water Color

**Concept:** Streams draining mineralized zones carry dissolved metals that alter water spectral signatures. Acid mine drainage changes water color detectably by Sentinel-2 (pH <4 turns streams orange/red from iron precipitation).

**Physical basis:** SOLID for acid drainage detection. WEAK for undiscovered deposit detection (natural backgrounds may not produce visible drainage).
**Implementation:** Sentinel-2 water-pixel spectral extraction + DEM flow direction + upstream source tracing.
**Viability: 4/10.** Only works where sulfide weathering produces acid drainage. Not universal.

### 4.6 Acoustic Emission — Ambient Noise Tomography

**Concept:** Use natural ground vibrations to image subsurface velocity structure. Does NOT listen for ore body signals but uses ambient noise to resolve velocity contrasts.

**Status:** COMMERCIAL. Fleet Space ExoSphere, CAUR Technologies. Proven at mine sites to 2.5km depth.
**Papers:** SEG Discovery 2025, Minerals 2024.
**GeaSpirit role:** GeaSpirit screens → ANT validates → drill.

### 4.7 Quantum Gravity Gradiometry

**Concept:** Atom interferometry for ultra-precise gravity sensing. Dense ore bodies create measurable gravity anomalies.

**Status:** PROTOTYPE. Birmingham group field demo 2022 (tunnel detection). NASA JPL developing space version (target ~2030). Airborne quantum systems: 5+ years from operational.
**Viability: 2/10.** Too far from field-ready. Classical airborne gravity gradiometry (Lockheed FTG) already operational.

---

## 5. Untried Combinations

### 5.1 Temporal DNA + Foundation Model (TOP PRIORITY)

Pre-train Prithvi-EO-2.0 on 20-year Landsat temporal stacks. Fine-tune on mineral labels. Tests whether temporal representations learned from millions of global samples encode geological patterns useful for mineral discrimination.

### 5.2 L-band minus C-band SAR Difference

When NISAR data arrives: compute (NISAR L-band) minus (Sentinel-1 C-band) backscatter. L-band penetrates deeper into dry soil. The difference isolates subsurface contribution. Best tested at Chuquicamata (hyperarid).

### 5.3 ECOSTRESS Diurnal + Landsat 20-Year Thermal

ECOSTRESS provides multiple daily thermal observations (dawn, noon, evening). Landsat provides 20-year baseline. Fusion creates ultra-precise apparent thermal inertia maps.

### 5.4 Drill Hole Ground Truth Transfer

Train on Kalgoorlie (205 labels + GSWA drill data enrichment). Test on Peru/Arizona (no drill data). Transfer the ground truth relationship (what does the surface look like where drilling found ore?) rather than transferring features.

### 5.5 Massive Multi-Source Ensemble

Stack 50+ features from 10+ sources (satellite + thermal + EMIT + magnetics + radiometrics + soil + embeddings + temporal). Test if a gradient-boosted ensemble with proper regularization extracts signal from the noise, or if the noise destroys it.

---

## 6. Prioritized Experimental Plan

| # | Experiment | Data | Cost | P(success) | Impact | Novelty | Sprint |
|---|-----------|------|------|-----------|--------|---------|--------|
| 1 | **Temporal DNA Transformer** | Landsat 20yr + Sentinel-2 | $0 data, $10K GPU | High | Very High | **Very High** | Week 1-4 |
| 2 | **Prithvi-EO-2.0 Fine-tune** | HLS + OZMIN labels | $0 data, $5K GPU | Medium-High | High | High | Week 1-3 |
| 3 | **ECOSTRESS Thermal Fusion** | ECOSTRESS + Landsat | $0 | Medium | Medium-High | Medium | Week 2-3 |
| 4 | **Earth MRI Geophysics (Arizona)** | USGS ScienceBase | $0 | High | Medium | Low | Week 1 |
| 5 | **MINDAT Label Enrichment** | MINDAT API | $0 | Medium | Medium | Medium | Week 1 |
| 6 | **SoilGrids Lithology Proxy** | SoilGrids WCS | $0 | Low-Medium | Low-Medium | Low | Week 1 |
| 7 | **Biogeochemical via EnMAP** | EnMAP archive | $0 | Low | High if works | High | Week 3-4 |
| 8 | **NISAR L-C SAR Difference** | NISAR + S1 (when available) | $0 | Low-Medium | Medium | High | Week 4+ |
| 9 | **Drill Hole Transfer** | GSWA + satellite | $0 | Medium | High | Medium | Week 3-4 |
| 10 | **PALSAR-2 Structural Features** | ASF DAAC | $0 | Low-Medium | Low | Low | Week 2 |

---

## 7. Three Detailed Experiments

### Experiment A: Temporal DNA Transformer at Kalgoorlie

**Hypothesis:** A temporal transformer trained on 20-year, multi-band Landsat time series per pixel can distinguish deposit locations from background with higher accuracy than static multi-band features alone.

**Falsifiable prediction:** AUC > baseline satellite model (0.806) by >= 0.02.

**Data:**
- Landsat 5/7/8/9 Collection 2 Surface Reflectance, 1999-2025, bands 1-7 + thermal
- Google Earth Engine for extraction (free)
- Labels: 205 Kalgoorlie curated deposits + OZMIN

**Method:**
1. For each labeled pixel: extract 52 weekly composites × 7 bands × 20 years
2. Handle gaps via interpolation
3. Train temporal transformer (3-layer, 128-dim) with spatial block CV
4. Compare: AUC vs static baseline, vs thermal baseline

**Scripts needed:**
- `build_temporal_dna_features.py` — GEE extraction
- `train_temporal_dna_experiment.py` — transformer training + CV

**Zone:** Kalgoorlie (most labels, best baseline to beat)
**Success criteria:** AUC delta >= +0.02 (spatial block CV)
**Timeline:** 3-4 weeks (data extraction 1 week, model development 2-3 weeks)

### Experiment B: Prithvi-EO-2.0 Fine-tuning for Mineral Prospectivity

**Hypothesis:** A foundation model pre-trained on 4.2M global satellite samples encodes geological features that, when fine-tuned on mineral labels, outperform zone-specific models at cross-zone transfer.

**Falsifiable prediction:** Cross-zone AUC > 0.65 (vs current 0.51 with LOZO).

**Data:**
- Prithvi-EO-2.0 weights (open source, HuggingFace)
- Harmonized Landsat-Sentinel-2 (HLS) time series at all 5 supervised zones
- OZMIN + MRDS labels

**Method:**
1. Download Prithvi-EO-2.0 pre-trained weights
2. Extract HLS time series at all labeled locations
3. Fine-tune classification head on 4 zones, test on held-out 5th (LOZO)
4. Compare: AUC vs zone-specific model, vs direct cross-zone transfer

**Scripts needed:**
- `setup_prithvi_eo.py` — model download + env setup
- `train_prithvi_mineral_experiment.py` — fine-tuning + LOZO evaluation

**Zones:** All 5 supervised zones (LOZO protocol)
**Success criteria:** Cross-zone AUC > 0.65
**Timeline:** 2-3 weeks

### Experiment C: ECOSTRESS Diurnal Thermal Inertia

**Hypothesis:** Multiple daily thermal observations from ECOSTRESS enable true apparent thermal inertia (ATI) calculation, which better discriminates mineralized zones than single-overpass Landsat thermal.

**Falsifiable prediction:** ATI feature shows Cohen's d > 0.3 (deposits vs background) AND improves model AUC by >= 0.005.

**Data:**
- ECOSTRESS Collection 2 LST (free, NASA LP DAAC AppEEARS)
- 2018-2025, all available passes over Kalgoorlie and Chuquicamata
- Existing Landsat thermal 20-year features for comparison

**Method:**
1. Download all ECOSTRESS passes over Kalgoorlie (expect 200-500 passes)
2. Group by local time (pre-dawn, morning, afternoon)
3. Compute ATI = (albedo × (T_max - T_min)) for each pixel
4. Statistical comparison: ATI at deposits vs background (Cohen's d, MW-U)
5. Add ATI as feature to baseline model (spatial block CV)

**Scripts needed:**
- `download_ecostress_kalgoorlie.py` — AppEEARS bulk download
- `build_ecostress_ati_features.py` — ATI computation
- `train_ecostress_experiment.py` — ML comparison

**Zones:** Kalgoorlie (primary), Chuquicamata (replication)
**Success criteria:** Cohen's d > 0.3, AUC delta >= +0.005
**Timeline:** 2-3 weeks

---

## 8. Mineral-Specific Routes

| Mineral | Confirmed Route | Best Pending Route | New Idea (this document) | Ideal Missing Tool |
|---------|----------------|-------------------|-------------------------|-------------------|
| **Gold (orogenic)** | Satellite + thermal + PCA embeddings (0.937 AUC) | GA magnetics/gravity + GSWA AEM | Temporal DNA transformer | Airborne passive EM (MobileMT) |
| **Copper (porphyry)** | Satellite + thermal + EMIT (0.862 AUC) | ECOSTRESS ATI + EnMAP biogeochem | Foundation model transfer | High-res systematic hyperspectral |
| **Copper (sediment)** | Satellite baseline (0.763 AUC) | Biogeochemical via EnMAP (vegetated) | NDVI trend + SAR moisture | Airborne EM conductivity survey |
| **Lithium** | No confirmed route | EMIT clay detection + SoilGrids | Temporal anomaly in pegmatite terrain | Regional EM conductivity mapping |
| **Cobalt** | No confirmed route | Co associates with Cu/Ni → use Cu models | Biogeochemical leaf metal detection | Hyperspectral systematic SWIR |
| **REE** | No confirmed route | Radiometrics (Th anomaly) + magnetics | Spectral unmixing for REE-bearing minerals | Airborne gamma spectrometry |
| **Graphite** | No confirmed route | AEM conductivity (graphite = conductor) | Passive EM detection of conductive bodies | Ground-based EM survey network |
| **Platinum (PGE)** | No confirmed route | Mafic/ultramafic lithology mapping | SAR texture + magnetics for layered intrusions | High-res airborne magnetics |
| **Silver** | Associates with Cu/Au → use existing models | EMIT alteration mapping | Part of porphyry Cu pipeline | Same as copper |
| **Diamonds** | No confirmed route | Magnetics (kimberlite pipes are magnetic) | ICESat-2 micro-depressions? (speculative) | Airborne magnetics + gravity gradient |
| **Uranium** | No confirmed route | Radiometrics K/U anomaly at depth | Muography (density contrast) | Passive EM + ANT for Athabasca-type |
| **Iron** | Failed (0.405 AUC at Pilbara) | Magnetics (strong magnetic signal) | Gravity + magnetics combined | Airborne mag+grav simultaneously |

---

## 9. References

### Satellite Sensors
- Pour & Hashim (2021). PALSAR-2 lithological mapping in arid terrain. *Advances in Space Research*.
- Rosen et al. (2024). The NISAR mission. *IEEE TGRS*.
- Hulley et al. (2022). ECOSTRESS science data products. *Remote Sensing of Environment*.

### Biogeochemistry
- Mapping leaf metal content from airborne hyperspectral imaging. *Scientific Reports* (2020). doi:10.1038/s41598-020-79439-z
- Hyperspectral Detection of Fe and Mo in Vegetation. *Remote Sensing* (2024). 16(23):4519.
- Mineral prospecting from biogeochemistry and hyperspectral RS. *J Geochem Exploration* (2022). doi:10.1016/j.gexplo.2021.106899

### Passive EM / Geophysics
- Detecting critical mineral systems using airborne AFMAG. *Geophysics* (2024). doi:10.1190/geo2023-0224.1
- MobileMT 2.5D Inversion for Deep Ore. *Minerals* (2025). 15(8):874

### Ambient Noise Tomography
- ANT: Sensitive, Rapid Passive Seismic for Mineral Exploration. *SEG Discovery* (2025). doi:10.5382/SEGnews.2025-140.fea-01
- Real-Time ANT of Hillside IOCG Deposit. *Minerals* (2024). 14(3):254

### Temporal Transformers
- Deep Learning for Satellite Image Time Series. arXiv:2404.03936 (2024).
- Lithology identification combining reinforcement learning and Transformer. *Frontiers Earth Science* (2025). doi:10.3389/feart.2025.1595574
- Earthformer: space-time transformer. arXiv:2207.05833 (2022).

### Foundation Models
- Prithvi-EO-2.0. arXiv:2412.02732 (2024). NASA/IBM/Jülich.
- Clay Foundation Model. Development Seed (2024). github.com/Clay-foundation/model
- When Geoscience Meets Foundation Models. arXiv:2309.06799 (2023).

### Muography
- Deep investigation of muography at Zaozigou gold mine. *GJI* (2024). 237(1):588.
- Muography in Strategic Deposits. *Minerals* (2025). 15(9):945.
- Transmission-Based Muography for Ore Bodies. *Natural Resources Research* (2023). doi:10.1007/s11053-023-10201-8

### Quantum Gravity
- Quantum gravity gradiometry for mass change science. *EPJ Quantum Technology* (2025). doi:10.1140/epjqt/s40507-025-00338-1
- Quantum sensing for gravity cartography. *Nature* (2022). doi:10.1038/s41586-021-04315-3

### Drones
- MULSEDRO multi-sensor drone project. *GEUS Bulletin* (2022).
- Aerial Drones for Geophysical Prospection in Mining. *Drones* (2025). 9(5):383.

### Mineral Prospectivity ML
- Review of MPM using Deep Learning. *Minerals* (2024). 14(10):1021.
- Transfer learning for gold prospectivity mapping. He et al. (2024).
- Hoggard et al. (2020). Sediment-hosted deposits linked to paleo-rift architecture. *Nature Geoscience*.

### Thermal Inertia
- Thermal inertia mapping for mineral exploration: Mamandur. *GJI* (2013). 195(1):357.
- Sharpening ECOSTRESS with Landsat-Sentinel reflectances. *RSE* (2020). doi:10.1016/j.rse.2020.112027

---

## 10. CTO Recommendation: What I Would Do First

**Week 1 (quick wins):**
1. Download USGS Earth MRI geophysics for Arizona ($0, 2 hours work) → add as ML features
2. Integrate MINDAT API mineral species labels ($0, 1 day) → enrich training data
3. Download SoilGrids 250m for all zones ($0, 2 hours) → lithology proxy features

**Week 1-4 (main experiment):**
4. Build Temporal DNA pipeline: extract 20-year weekly Landsat composites over all 5 zones via GEE
5. Train temporal transformer model at Kalgoorlie first (best labels)
6. If AUC improves by >=0.02 → this becomes the new architecture

**Week 2-3 (parallel):**
7. Download Prithvi-EO-2.0 weights, set up fine-tuning pipeline
8. Test cross-zone transfer with foundation model (LOZO protocol)

**Week 2-3 (parallel):**
9. Download ECOSTRESS Collection 2 over Kalgoorlie and Chuquicamata
10. Build diurnal ATI features
11. Test as ML feature (spatial block CV)

**Week 4+ (conditional):**
12. When NISAR data becomes available at our AOIs → test L-C SAR difference
13. If Temporal DNA works → expand to all zones, integrate with foundation model
14. If Peru EMIT download resolves → complete porphyry replication

**What NOT to pursue (at least not now):**
- Drone-anything (we're satellite-first)
- Muography (too slow, too expensive)
- Quantum gravity (5+ years away)
- Self-potential from drone (physics prevents airborne measurement)
- Standoff Raman (engineering too immature)

**The big picture:** GeaSpirit's next breakthrough is not a new sensor — it's a new way of using the data we already have. The 40-year Landsat archive is an untapped goldmine. Every pixel on Earth has been photographed thousands of times across decades. The question is not "what new data do we need?" but "what have we been leaving on the table?"

The Temporal DNA Transformer is the answer. Build it.

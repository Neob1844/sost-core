# Subsurface Mineral Inference Research
## How to Detect Buried Minerals Using Free Data and AI

**Version:** 1.0 — March 2026
**Author:** SOST Protocol Research / NeoB
**Status:** Strategic research document for Geaspirit platform

---

## Executive Summary

Direct detection of buried minerals from satellites is not possible with current technology. However, **indirect inference** through multiple layers of surface evidence is not only possible but increasingly powerful when combined with modern AI. This document catalogs every known free data source, proxy signal, and ML approach for maximizing the probability of inferring subsurface mineralization — and proposes a novel algorithm that fuses them all.

**Key finding:** No single proxy is sufficient, but the **probabilistic fusion of 8-12 independent evidence layers** can achieve commercially useful confidence levels (estimated 60-80% for alteration-associated deposits in arid terrain, 30-50% in vegetated terrain).

---

## 1. Surface Proxies for Buried Mineralization

### 1.1 Hydrothermal Alteration Mapping

**The science:** Ore deposits form through hydrothermal fluids that alter surrounding rock in concentric zones. These zones extend to the surface even when the ore body is hundreds of meters deep.

**Alteration sequence (outer → inner / surface → depth):**
| Zone | Key Minerals | Spectral Signature | Sentinel-2 | EMIT/EnMAP |
|------|-------------|-------------------|------------|------------|
| Propylitic | Chlorite, epidote, calcite | Fe/Mg-OH absorption 2.2-2.35μm | Partial (B12) | Yes |
| Argillic | Kaolinite, montmorillonite | Al-OH absorption 2.16-2.21μm | Limited | Yes |
| Sericitic | Sericite/muscovite, pyrite | Al-OH 2.20μm sharp | Limited | Yes |
| Potassic | K-feldspar, biotite | Broad SWIR features | Marginal | Partial |

**Detection capability:**
- Sentinel-2: Can detect broad iron oxide and clay anomalies via band ratios (B11/B12 for clay, B4/B2 for iron oxide). Resolution: 20m SWIR. Limited mineral discrimination.
- EMIT (285 bands, 60m): Can distinguish individual alteration minerals. Launched 2022, data free via NASA Earthdata. Coverage: ISS orbit (~52°N-52°S).
- EnMAP (242 bands, 30m): German hyperspectral mission, data available since 2023.

**Correlation with depth:** Published models (Sillitoe, 1973; 2010 updates) suggest propylitic alteration visible at surface can indicate ore at 200-1000m depth in porphyry copper systems. The presence of advanced argillic alteration at surface strongly suggests a mineralized system at shallower depths (50-300m).

**Viability for free platform: HIGH** — Sentinel-2 provides initial screening, EMIT provides detailed mineral mapping.

### 1.2 Gossans and Iron Caps

**The science:** A gossan is the oxidized, weathered surface expression of a sulfide ore body. When sulfides (pyrite, chalcopyrite, galena, sphalerite) weather, they produce distinctive iron oxides (goethite, jarosite, hematite) that form a "cap" over the buried deposit.

**Spectral signatures:**
- Goethite: absorption at 0.48μm and 0.94μm
- Jarosite: absorption at 0.43μm and 2.27μm (key discriminator from laterite)
- Hematite: absorption at 0.53μm and 0.87μm

**Can Sentinel-2 detect gossans?**
Sentinel-2 can map broad iron oxide anomalies but **cannot reliably distinguish gossans from normal laterites** — both appear as iron-rich surfaces. Band ratios B4/B2 (ferric iron) and B11/B8A (ferrous iron) provide initial indicators.

**Can EMIT distinguish gossans?**
Yes. Hyperspectral data with SWIR coverage can identify **jarosite** specifically, which is the key marker distinguishing gossans from laterites. Jarosite has a diagnostic absorption at 2.27μm that requires hyperspectral resolution to detect.

**This is probably the most direct surface proxy for buried sulfide deposits.**

**Viability: HIGH** for EMIT-covered regions, MEDIUM for Sentinel-2 alone.

### 1.3 Geobotanical Anomalies — Vegetation as a Chemical Sensor

**The science:** Plants growing over mineral deposits absorb heavy metals from soil. This causes measurable stress: reduced chlorophyll, altered cell structure, and shifted spectral signatures. The "red edge" (680-740nm) shifts toward shorter wavelengths under metal stress.

**Key findings from literature:**
- A Vegetation Index for Greenness and Shortwave (VIGS) was developed to detect vegetation anomalies over mineral deposits in tropical forests (Filho et al., Remote Sensing of Environment, 2016)
- Heavy metal stress in vegetation causes: red edge blue-shift, increased reflectance at 680nm, decreased NIR reflectance
- Copper, lead, zinc, and cadmium each produce subtly different spectral responses in lab conditions
- Sentinel-2 red-edge bands (B5: 705nm, B6: 740nm, B7: 783nm) can detect vegetation stress

**Differentiation by metal type:**
Lab studies show different metals affect different spectral regions, but in the field, multiple stressors overlap. With hyperspectral data (EMIT/EnMAP), discrimination between Cu-stress and Zn-stress may be possible but is still experimental.

**THIS IS THE KEY FOR VEGETATED TERRAIN** where direct mineral spectroscopy fails.

**Viability: HIGH** with Sentinel-2 multi-temporal analysis. **VERY HIGH** with EMIT in vegetated regions.

### 1.4 Soil Geochemical Anomalies

**The science:** Trace elements migrate upward from buried ore through soil moisture, plant uptake, and gas transport, creating diffuse geochemical halos detectable in surface soil.

**Remote detection:** SWIR spectroscopy can detect elevated iron, clay alteration, and some heavy metal effects in bare soil. Random Forest regression from Sentinel-2 and Landsat-8 data has shown R² ≈ 0.78 for some soil properties. However, direct spectral detection of Cu/Pb/Zn in soil at typical ppm levels is at the edge of remote sensing capability.

**Viability: MEDIUM** — useful as supporting evidence, not primary.

### 1.5 Thermal Anomalies

**The science:** Mineralized bodies have different thermal conductivity than surrounding rock. This creates surface temperature anomalies, especially visible in day-night temperature differences (thermal inertia).

**Free thermal data:**
- Landsat 8/9 TIRS: 100m resolution, 16-day revisit
- ECOSTRESS: 70m resolution, irregular revisit (ISS orbit)
- Sentinel-3 SLSTR: 1km (too coarse for local mapping)

**Thermal inertia = (day temp - night temp):** High thermal inertia indicates dense rock (could be mineralized). Published studies show correlation coefficient ~0.78 between thermal inertia and rock density.

**Viability: MEDIUM** — supportive evidence layer, not primary detection.

### 1.6 SAR/InSAR Signals

**Sentinel-1 SAR:**
- Polarimetric ratios (VV/VH) correlate with surface roughness and soil properties
- InSAR can detect mm-scale ground deformation associated with hydrothermal subsidence/uplift
- Free data, 6-day revisit, all-weather capability

**InSAR for mineral exploration:**
- Hydrothermal systems can cause measurable subsidence (up to 40mm/yr at Dallol volcano)
- Subsidence patterns may indicate active fluid systems associated with mineralization
- SBAS-InSAR achieves millimeter-level accuracy

**Viability: MEDIUM-HIGH** for active hydrothermal systems, LOW for dormant deposits.

### 1.7 Topographic/Geomorphological Signals

**DEM analysis (Copernicus GLO-30, 30m resolution, free):**
- Resistant ore bodies create positive relief
- Weathered deposits create depressions
- Drainage pattern analysis reveals structural controls
- Lineament extraction indicates faults that channel mineralizing fluids

**Viability: MEDIUM** — essential structural context layer.

---

## 2. Non-Conventional Signals — Innovation Frontier

### 2.1 Vegetation as Distributed Biological Sensor (HIGH POTENTIAL)

**Concept:** Instead of treating vegetation as an obstacle to mineral mapping, treat it as a **distributed chemical analysis network** that has been sampling the soil for decades.

**Multi-temporal phenology approach:**
- Sentinel-2 every 5 days → seasonal vegetation behavior
- Plants over mineral deposits may show: earlier senescence, delayed green-up, altered drought response
- A TIME SERIES of years reveals patterns invisible in any single image
- "Not one image, but a multi-year movie revealing subtle patterns"

**This is potentially the highest-impact innovation for vegetated terrain.** No one has systematically applied multi-year Sentinel-2 time series phenology to mineral exploration at scale.

### 2.2 Volatile Gas Emissions

**TROPOMI (Sentinel-5P):**
- Detects SO₂, NO₂, CO, CH₄ with unprecedented resolution (3.5×7km)
- Active hydrothermal/volcanic systems emit SO₂ detectable from space
- AI algorithms can quantify volcanic SO₂ emissions in near real-time
- Potential for detecting subtle degassing over buried geothermal/hydrothermal systems

**Viability: LOW-MEDIUM** — resolution too coarse for local mineral exploration, but useful for regional screening of active systems.

### 2.3 SAR Polarimetry for Lithology

Full-quad polarimetric SAR (not available from Sentinel-1, but from ALOS-2 and future NISAR) can distinguish rock types based on surface scattering properties. NISAR (NASA-ISRO, expected 2025-2026) will provide free L-band polarimetric SAR globally.

**Viability: MEDIUM** — future potential with NISAR.

### 2.4 Gravity and Magnetic Anomalies

- Dense ore bodies create measurable gravity anomalies
- Magnetite-bearing deposits create magnetic anomalies
- Satellite gravity (GRACE) is too coarse (~300km)
- Airborne surveys exist as open data from some geological surveys (USGS, Geoscience Australia)
- These **directly sense subsurface** but at regional resolution

**Free airborne data sources:**
- USGS: airborne magnetic/gravity for parts of US
- Geoscience Australia: extensive airborne coverage
- British Geological Survey: selected areas

**Viability: HIGH where data exists** — the only signals that truly "see" underground.

---

## 3. Machine Learning for Subsurface Inference

### 3.1 Architecture Recommendations

| Architecture | Use Case | Maturity |
|-------------|----------|---------|
| Random Forest / XGBoost | Baseline prospectivity mapping | Production-ready |
| CNN on multi-band images | Spatial pattern recognition | High |
| Vision Transformer (ViT) | Global context in large images | Emerging (2024+) |
| Transformer-GCN fusion | Spatial + geological relationships | Cutting edge (2025) |
| Deep Forest | Interpretable alternative to DNN | New (2024) |
| Bayesian Neural Networks | Uncertainty quantification | Research stage |
| Self-supervised pretraining | No-label satellite feature learning | Active research |

**Recent innovations (2024-2025):**
- Deep Forest provides high performance without black-box problems
- Transformer–GCN fusion captures both local and global geological features
- Conformer combines CNN local extraction with Transformer global dependencies
- Multimodal Transformer frameworks integrate diverse geological data types

### 3.2 Training Data Sources (Free)

| Source | Content | Coverage | URL |
|--------|---------|----------|-----|
| USGS MRDS | 300K+ mineral deposit records worldwide | Global | mrdata.usgs.gov |
| USMIN | Updated US deposit database | USA | usgs.gov/usmin |
| MINDAT.org | Mineral localities with coordinates | Global | mindat.org |
| Geoscience Australia | Deposits + airborne geophysics | Australia | ga.gov.au |
| OneGeology | Geological maps + known deposits | Global | onegeology.org |
| CGS Canada | Geological data + mineral occurrences | Canada | nrcan.gc.ca |

**Training set construction:**
Cross-reference: satellite image at known deposit location + deposit type + estimated depth → training sample. Estimated: **10,000-50,000 labeled examples** constructible from MRDS + Sentinel-2 imagery.

### 3.3 Transfer Learning

Train on well-studied regions (Andes copper belt, Australian gold provinces, African copper belt) → transfer to unexplored regions. Published evidence suggests geological transfer learning works across similar deposit types even on different continents.

---

## 4. Materials Engine + Remote Sensing Integration

### 4.1 Spectral Prediction from Crystal Structure

**Breakthrough paper (Hung et al., Advanced Materials, 2024):** GNNOpt — an equivariant GNN that directly predicts optical spectra from crystal structure. This enables:
1. Materials Engine predicts spectral signature of any mineral from its structure
2. Remote Sensing searches for that signature in satellite data
3. Closed loop: computational prediction → satellite verification

**Training data:** USGS Spectral Library (~2,600 spectra) + Materials Project + JARVIS structures.

### 4.2 Reverse Geological Search

**Workflow:**
1. User: "Search for lithium deposits"
2. Engine knows Li appears in: spodumene (LiAlSi₂O₆), lepidolite, petalita, Li-rich clays
3. Each mineral has a known spectral signature (USGS library)
4. System searches EMIT/Sentinel-2 imagery globally for those signatures
5. Returns: coordinates + probability + supporting evidence

**This is viable today with free data.**

---

## 5. Key References

| Topic | Authors/Title | Year | Finding |
|-------|-------------|------|---------|
| ML + Remote Sensing Review | Shirmard et al., Remote Sensing of Env. | 2022 | Comprehensive review of ML methods for mineral RS |
| Gossans + Hyperspectral | Kumar et al., Geocarto International | 2021 | Hyperspectral mapping of gossans and alteration in Himalayas |
| Vegetation Stress + Metals | Shi et al., Remote Sensing | 2024 | Review of heavy metal detection in soil/vegetation |
| GNN Optical Spectra | Hung et al., Advanced Materials | 2024 | GNNOpt predicts optical spectra from crystal structure |
| Transformer-GCN Fusion | Gao et al., Minerals | 2025 | Transformer+GCN for mineral prospectivity mapping |
| Deep Forest | Dong et al., JGR:ML | 2024 | Interpretable deep learning for mineral prospectivity |
| TROPOMI SO₂ AI | Corradini et al., Remote Sensing of Env. | 2024 | AI quantification of volcanic SO₂ emissions |
| Multi-sensor Alteration | Ghezelbash et al., Scientific Reports | 2023 | Multi-sensor RS + airborne geophysics for alteration |
| Iron Oxide Sentinel-2 | van der Meer et al., Remote Sensing | 2021 | Hyperspectral unmixing for iron mineral detection |
| Thermal Inertia | Multiple authors | 2020+ | R²≈0.78 for rock density from thermal inertia |

---

## 6. Proposed Algorithm: Geaspirit Core

### **Deep Evidence-Enhanced Probabilistic Characterization of Ore REsources**

**Concept:** Bayesian fusion of N independent evidence layers, each with calibrated confidence, to produce a posterior probability map of subsurface mineralization.

### Input Layers (all free)

| Layer | Source | What it detects | Weight |
|-------|--------|----------------|--------|
| 1. Iron oxide anomalies | Sentinel-2 B4/B2 ratio | Gossans, oxidation | 0.15 |
| 2. Clay/alteration anomalies | Sentinel-2 B11/B12 ratio | Hydrothermal alteration | 0.15 |
| 3. Hyperspectral minerals | EMIT 285-band | Specific alteration minerals | 0.20 |
| 4. Vegetation stress | Sentinel-2 red-edge time series | Geobotanical anomaly | 0.15 |
| 5. Thermal anomaly | Landsat 8/9 TIRS day/night | Thermal inertia | 0.05 |
| 6. Structural context | DEM lineaments + drainage | Fault/fracture control | 0.10 |
| 7. SAR backscatter | Sentinel-1 VV/VH ratio | Surface roughness/moisture | 0.05 |
| 8. Geological context | OneGeology maps | Favorable host rock | 0.10 |
| 9. Known deposit proximity | MRDS/MINDAT | Spatial autocorrelation | 0.05 |

### Process

1. **Feature extraction:** For each 30m pixel, extract all 9 evidence layers
2. **Normalization:** Convert each to [0,1] probability using calibrated thresholds
3. **Bayesian fusion:** P(mineral|evidence) = product of layer likelihoods, weighted by confidence
4. **Spatial regularization:** CNN or GNN smooths noise while preserving real anomalies
5. **Calibration:** Compare against known deposit locations (MRDS ground truth)
6. **Output:** Probability map + uncertainty map + ranked hot spots

### Innovation

1. **No one fuses ALL these layers together** — existing systems use 2-4 layers maximum
2. **Vegetation-as-sensor concept** — systematic use of multi-year phenology for mineral inference
3. **Materials Engine integration** — predicted spectral signatures guide the search
4. **Bayesian uncertainty** — every prediction comes with calibrated confidence
5. **Zero cost** — all data sources are free

---

## 7. Implementation Plan — Zero Cost

### Phase 1: Proof of Concept (Weeks 1-4)

**Pilot zones (3 candidates):**

| Zone | Why | Data quality | Known deposits |
|------|-----|-------------|---------------|
| **Atacama, Chile** | Arid, minimal vegetation, world-class porphyry Cu-Au | Excellent S2+EMIT | 100+ known Cu deposits |
| **Pilbara, Western Australia** | Semi-arid, iron ore + gold, open geophysical data | Excellent + airborne mag/grav | 500+ known deposits |
| **Zambian Copperbelt** | Moderate vegetation, sediment-hosted Cu, well-studied | Good S2, limited EMIT | 50+ known Cu deposits |

**Recommended start:** Atacama — best conditions for initial validation.

**Week 1-2:** Download Sentinel-2 + EMIT for Atacama pilot area (100×100km). Download MRDS deposit locations. Build training set: 200 positive (known deposit) + 200 negative (no deposit) 30m patches.

**Week 3:** Train Random Forest baseline on band ratios + DEM derivatives. Evaluate AUC against held-out deposit locations.

**Week 4:** Add EMIT hyperspectral features. Compare RF vs CNN. Produce first probability map.

### Phase 2: Multi-Layer Fusion (Weeks 5-8)

Add thermal, SAR, vegetation time series layers. Train deep fusion model. Validate on second pilot zone (Pilbara).

### Phase 3: Vegetation Sensor (Weeks 9-12)

Build 5-year Sentinel-2 time series for vegetated pilot (Zambia). Extract phenological anomalies. Test if vegetation temporal patterns correlate with known deposits.

### Phase 4: Product (Weeks 13-16)

Web interface: user selects area → system runs Geaspirit Core → returns probability map + ranked targets. First sellable product: "AI-powered mineral exploration screening reports."

---

## Conclusion — Next Immediate Step

**Download Sentinel-2 and EMIT data for a 100×100km area around Chuquicamata, Atacama, Chile.** This is the world's largest open-pit copper mine, surrounded by dozens of known porphyry deposits at various depths. Build the first training set by pairing satellite pixels with MRDS deposit records. Train the first Random Forest model. If AUC > 0.7, the concept is validated and worth scaling.

The competitive advantage is not any single data source — it's the **systematic probabilistic fusion of all available free evidence**, guided by a Materials Engine that knows what to look for, and powered by modern deep learning that can find patterns humans cannot see.

---

## Sources

- [Remote Sensing in Mineral Exploration: 2025 Innovations](https://farmonaut.com/mining/remote-sensing-in-mineral-exploration-2025-innovations)
- [AI Satellite Mineral Exploration: 2025 ML Mapping Breakthroughs](https://farmonaut.com/mining/ai-satellite-mineral-exploration-2025-ml-mapping-breakthroughs)
- [Secondary Iron Mineral Detection via Hyperspectral Unmixing with Sentinel-2](https://www.sciencedirect.com/science/article/pii/S0303243421000507)
- [Towards Better Delineation of Hydrothermal Alterations via Multi-Sensor RS](https://www.nature.com/articles/s41598-023-34531-y)
- [Monitoring Heavy Metals in Soils and Vegetation by Remote Sensing: A Review](https://www.mdpi.com/2072-4292/16/17/3221)
- [Universal Ensemble-Embedding GNN for Optical Spectra Prediction (GNNOpt)](https://advanced.onlinelibrary.wiley.com/doi/10.1002/adma.202409175)
- [Transformer–GCN Fusion Framework for Mineral Prospectivity Mapping](https://www.mdpi.com/2075-163X/15/7/711)
- [Deep Forest for Interpretable Mineral Prospectivity Mapping](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2024JH000311)
- [USGS Mineral Resources Data System (MRDS)](https://mrdata.usgs.gov/mrds/)
- [USMIN Mineral Deposit Database](https://www.usgs.gov/centers/gggsc/science/usmin-mineral-deposit-database)
- [Mineral Exploration Machine Learning Resources (GitHub)](https://github.com/RichardScottOZ/mineral-exploration-machine-learning)
- [TROPOMI Volcanic SO₂ Monitoring with AI](https://www.sciencedirect.com/science/article/pii/S0034425724004899)
- [Mapping Gossans Using Hyperspectral Data in Eastern Kumaon Himalaya](https://www.sciencedirect.com/science/article/pii/S2590197421000021)
- [A Review of ML in Processing RS Data for Mineral Exploration](https://www.sciencedirect.com/science/article/abs/pii/S0034425721004703)
- [RS Insights into Subsurface-Surface Relationships: Copper Deposits](https://link.springer.com/article/10.1007/s12145-024-01423-2)

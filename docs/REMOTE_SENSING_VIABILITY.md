# Remote Material Detection System: Viability Report

## Combining Spectral Sensors, Radar, and AI for Mineral Exploration

**Date:** 2026-03-20
**Prepared for:** SOST Materials Discovery Engine Integration Assessment

---

## Table of Contents

1. [State of the Art](#1-state-of-the-art)
2. [Proposed Architecture](#2-proposed-architecture)
3. [Honest Limitations](#3-honest-limitations)
4. [Costs and Data Access](#4-costs-and-data-access)
5. [Integration with SOST](#5-integration-with-sost)
6. [Competitors and Market](#6-competitors-and-market)
7. [Zero-Cost Route](#7-zero-cost-route)
8. [Conclusions and Recommendation](#8-conclusions-and-recommendation)

---

## 1. STATE OF THE ART

### A) Current Hyperspectral Orbital/Airborne Sensors

#### EMIT (NASA/ISS) -- Earth Surface Mineral Dust Source Investigation

| Parameter | Value |
|---|---|
| **What it measures** | Surface mineral composition, methane/CO2 plumes, dust source mineralogy |
| **Spectral range** | 381--2,493 nm (VNIR + SWIR) |
| **Number of bands** | 285 contiguous bands |
| **Spectral resolution** | ~7.5 nm |
| **Spatial resolution** | 60 m |
| **Swath width** | 75 km |
| **Data access** | **Free and open** via NASA LP DAAC (Earthdata Login required) |
| **Notable results** | First global mineral dust source map; detected >750 methane super-emitters; L2B mineral identification products available; L4 Earth System Model mineral maps |

EMIT was installed on the ISS in July 2022 and entered an extended mission phase in 2024, continuing operations through at least 2026. Its Dyson F/1.8 imaging spectrometer uses a mercury cadmium telluride detector array with spectral uniformity better than 98%. Coverage is limited to the ISS orbital inclination (~52 degrees N/S), so high-latitude regions are excluded.

**Reference:** https://earth.jpl.nasa.gov/emit/instrument/specifications/

#### EnMAP (DLR Germany) -- Environmental Mapping and Analysis Program

| Parameter | Value |
|---|---|
| **What it measures** | Land surface composition, vegetation, water quality, geology, soils |
| **Spectral range** | 420--2,450 nm (VNIR + SWIR) |
| **Number of bands** | 228 total (up to 99 VNIR at 6.5 nm sampling, up to 163 SWIR at 10 nm sampling) |
| **Spatial resolution** | 30 m x 30 m |
| **Swath width** | 30 km |
| **Revisit time** | 4 days (with +/- 30 degree off-nadir pointing) |
| **Orbit** | Sun-synchronous at 653 km altitude |
| **Data access** | **Free and open** to the user community at three processing levels |
| **Notable results** | Operational since April 2022; high-quality spectroscopy data for mineralogical and environmental mapping |

**Reference:** https://www.enmap.org/mission/

#### PRISMA (ASI Italy) -- PRecursore IperSpettrale della Missione Applicativa

| Parameter | Value |
|---|---|
| **What it measures** | Land and coastal surface composition, pollution monitoring, environmental assessment |
| **Spectral range** | 400--2,505 nm (VNIR + SWIR) |
| **Number of bands** | 239 total (66 VIS/NIR channels 400--1010 nm, 173 NIR/SWIR channels 920--2505 nm) |
| **Spectral resolution** | Better than 12 nm |
| **Spatial resolution** | 30 m (hyperspectral), 5 m (panchromatic, co-registered) |
| **Swath width** | 30 km |
| **Data access** | **Free** after registration at prisma.asi.it; archived and new acquisitions available |
| **Notable results** | Launched March 2019; successful mineral mapping validations in arid regions; fusion-ready Pan+Hyp co-registration |

**Reference:** https://www.eoportal.org/satellite-missions/prisma-hyperspectral

#### AVIRIS / AVIRIS-NG (NASA Airborne)

| Parameter | AVIRIS Classic | AVIRIS-NG (Next Generation) |
|---|---|---|
| **What it measures** | Surface mineralogy, vegetation, water quality, atmospheric gases | Same, higher performance |
| **Spectral range** | 400--2,500 nm | 380--2,510 nm |
| **Number of bands** | 224 (each ~10 nm wide) | 425 (each ~5 nm wide) |
| **Spatial resolution** | 4 m (low altitude) to 20 m (high altitude) | 0.3--8 m depending on altitude |
| **Swath width** | 1.9 km (low) to 11 km (high) | ~1.8 km at 4 km altitude |
| **Data access** | Archived data freely available via aviris.jpl.nasa.gov | Campaign data via NASA Earthdata |
| **Notable results** | Gold standard for mineral mapping since 1987; Cuprite (NV) validation site; extensive India campaign with AVIRIS-NG |

AVIRIS is a whiskbroom scanner using four grating spectrometers. It has flown on NASA's ER-2, Twin Otter, Proteus, and WB-57 aircraft.

**Reference:** https://aviris.jpl.nasa.gov/

#### DESIS (DLR on ISS) -- DLR Earth Sensing Imaging Spectrometer

| Parameter | Value |
|---|---|
| **What it measures** | Vegetation, water quality, land cover, limited mineralogy (VNIR only) |
| **Spectral range** | 402--1,000 nm (VNIR only, no SWIR) |
| **Number of bands** | 235 at full resolution (2.55 nm sampling); 118 at 5.1 nm; 60 at 10.2 nm |
| **Spatial resolution** | 30 m |
| **Swath width** | 30 km tile size |
| **Data access** | **Commercial** -- available for purchase via Teledyne TCloud portal |
| **Notable results** | Operational since November 2018; limited for mineral mapping due to lack of SWIR bands |

**Important limitation:** DESIS covers only the VNIR range (to 1000 nm), which means it cannot detect the critical SWIR absorption features (2000--2500 nm) that distinguish most clay minerals, carbonates, and sulfates. It is useful for iron oxide mapping but not comprehensive mineral exploration.

**Reference:** https://www.tbe.com/what-we-do/markets/space/geospatial-solutions/desis/instrument

#### Other Relevant Sensors

- **Landsat 8/9 OLI/TIRS**: 11 bands (30 m VNIR/SWIR, 100 m thermal), free via USGS. Two SWIR bands useful for broad iron oxide and clay discrimination.
- **ASTER (Terra satellite)**: 14 bands -- 3 VNIR (15 m), 6 SWIR (30 m), 5 TIR (90 m). Free data. SWIR sensor failed April 2008, so only pre-2008 SWIR data available. TIR bands remain operational and are valuable for silicate/carbonate mapping.
- **Sentinel-2 (ESA)**: 13 multispectral bands (10--60 m), free. See Section 7 for detailed mineral mapping capabilities.
- **WorldView-3 (Maxar)**: 8 SWIR bands at 3.7 m + 8 VNIR bands at 1.24 m. Commercial ($14--25/km2). Best spatial resolution for mineral mapping from orbit.

### B) Spectral Libraries

#### USGS Spectral Library Version 7

| Parameter | Value |
|---|---|
| **Number of spectra** | ~2,600+ spectra (including 1,000+ new in v7) |
| **Materials covered** | Minerals, rocks, soils, vegetation, man-made materials, volatiles, mixtures |
| **Wavelength range** | 0.2--200 micrometers (UV to far-infrared) |
| **Primary instrument range** | 350--2,500 nm (ASD spectrometers, 2,151 channels at 1 nm intervals) |
| **Format** | SPECPR native format; also available as generic ASCII text files |
| **Access** | **Free download** from USGS ScienceBase (doi:10.5066/F7RR1WDJ) and speclab.cr.usgs.gov |

The USGS Spectral Library is the gold standard reference for mineral identification in remote sensing. It includes lab-measured spectra of pure minerals under controlled conditions.

**Reference:** https://pubs.usgs.gov/publication/ds1035

#### ECOSTRESS / ASTER Spectral Library (JPL)

| Parameter | Value |
|---|---|
| **Number of spectra** | 3,400+ spectra |
| **Materials covered** | Minerals, rocks, lunar/terrestrial soils, man-made materials, meteorites, vegetation, NPV, snow, ice |
| **Wavelength range** | 0.35--15.4 micrometers (extends into thermal infrared) |
| **Format** | ASCII text files with 20-line metadata headers |
| **Access** | **Free** at speclib.jpl.nasa.gov |

The ECOSTRESS library is the successor to the ASTER spectral library and is one of the most comprehensive collections available, with particular strength in the thermal infrared region.

**Reference:** https://speclib.jpl.nasa.gov

#### Other Relevant Spectral Libraries

- **GhoSST (Grenoble)**: Primarily ices and planetary materials, maintained by IPAG. Free access.
- **RELAB (Brown University)**: Reflectance Experiment Laboratory; 30,000+ spectra of minerals and meteorites. Access via relabdocs.brown.edu.
- **Mineral Spectroscopy Server (Caltech)**: Raman, IR, and optical spectra of minerals. Free.

### C) SAR Radar for Geology

#### Penetration Depth by Radar Band

| Band | Frequency | Wavelength | Penetration in Dry Sand | Current Satellites |
|---|---|---|---|---|
| **C-band** | 5.4 GHz | ~5.7 cm | 0.1--0.5 m | Sentinel-1A/B (free), RADARSAT-2 |
| **L-band** | 1.25 GHz | ~24 cm | 1--2 m | ALOS-2 PALSAR-2, NISAR (free) |
| **P-band** | 0.435 GHz | ~68 cm | 3--5+ m | BIOMASS (ESA, launched 2024) |

**Critical conditions for radar penetration:**
- Surface material must be extremely dry (moisture reflects radar signals)
- Material must be fine-grained (grain diameter < 1/5 of radar wavelength)
- Overburden must be no more than a few meters thick
- Best results in hyperarid desert environments (Sahara, Arabian Peninsula, Atacama)

#### NISAR (NASA/ISRO)

NISAR launched July 30, 2025, aboard ISRO's GSLV-F16. Key specifications:
- **Dual-band**: L-band (24 cm) and S-band (10 cm) -- first satellite with two radar frequencies
- **Swath**: 242 km at 7 m along-track resolution
- **Orbit**: Sun-synchronous at 747 km, 12-day repeat cycle
- **Sensitivity**: Detects land deformation as small as 4 mm/year
- **Data policy**: **All data free** within 1--2 days of observation
- **Relevance to geology**: Structural mapping (faults, lineaments), surface deformation monitoring, soil moisture estimation; L-band can penetrate vegetation and thin overburden

**Reference:** https://science.nasa.gov/mission/nisar/

#### ALOS-2 PALSAR-2

- L-band SAR (1.27 GHz, 24 cm wavelength)
- 1--10 m resolution depending on mode
- Effective for lineament mapping, lithological discrimination via backscatter
- **Free data**: L1.1 data free from JAXA G-Portal; ScanSAR L2.2 mosaics free on AWS
- Successfully used for mapping paleochannels in Rajasthan (India) and subsurface geology in the Sahara

**Reference:** https://www.eorc.jaxa.jp/ALOS/en/dataset/alos_open_and_free_e.htm

#### Documented Cases of Subsurface Detection

1. **SIR-A/SIR-C "Radar Rivers" (1981--1994)**: The Shuttle Imaging Radar missions discovered ancient river systems ("radar rivers") beneath 1--2 m of sand in the Eastern Sahara Desert. The SIR-A instrument in 1981 first revealed these features, invisible in optical imagery. SIR-C/X-SAR flights in 1994 on Space Shuttle Endeavour confirmed and extended the findings. This remains the most famous demonstration of radar subsurface imaging.

2. **ALOS/PALSAR Sahara mapping**: L-band PALSAR images revealed previously unknown craters, faults, and paleo-river systems beneath Saharan sand cover, detected at depths of 1--2 m.

3. **PALSAR-2 paleochannel detection in Rajasthan, India**: L-band cross-polarization (HV) data outperformed C-band for detecting buried river channels beneath desert alluvium.

4. **BIOMASS P-band**: ESA's BIOMASS mission (launched 2024) carries a P-band SAR expected to penetrate up to 5 m in dry conditions -- the deepest orbital radar penetration capability to date.

### D) Airborne Gamma-Ray Spectrometry

#### What It Measures

Airborne gamma-ray spectrometry measures naturally occurring gamma radiation emitted by radioactive decay of three elements in rocks and soils:

- **Potassium (K-40)**: 1.46 MeV gamma ray. Abundant in feldspars, micas, clay minerals.
- **Uranium (U-238 series)**: Measured via Bi-214 at 1.76 MeV. Indicator of granites, phosphorites, some hydrothermal alteration.
- **Thorium (Th-232 series)**: Measured via Tl-208 at 2.62 MeV. Indicator of heavy mineral sands, granites, some carbonatites.

These three radioelements serve as proxies for lithology, weathering, and alteration -- not direct ore detection, but powerful geological mapping tools.

#### Penetration Depth

Gamma rays are detected from the **top 30--45 cm** of soil/rock only. This is an inherent physical limitation -- gamma radiation is quickly absorbed by matter. The method therefore maps surface and near-surface geochemistry, not deep subsurface.

#### Detection Equipment

Typical systems use packages of sodium iodide (NaI) scintillation detectors, commonly four 10.2 x 10.2 x 40.6 cm crystals. Larger detector volumes increase sensitivity.

#### Available Data

- **IAEA**: Published guidelines (TECDOC-1363) and maintains reference calibration standards. Does not distribute survey data directly.
- **National geological surveys**: Australia (Geoscience Australia), Canada (NRCan), and the USA (USGS EarthMRI) have extensive airborne gamma-ray survey archives, many now freely available.
- **USGS EarthMRI**: The Earth Mapping Resources Initiative is collecting new airborne geophysical data (including gamma-ray spectrometry) across the US, with data made publicly available.

**Reference:** IAEA-TECDOC-1363, https://www-pub.iaea.org/MTCD/Publications/PDF/te_1363_web.pdf

### E) Real Success Cases

#### KoBold Metals -- The Leading Example

- **Founded**: 2018, Berkeley, California
- **Funding**: $537M Series C (January 2025), total funding exceeding $1 billion, valued at ~$3 billion
- **Investors**: Bill Gates (Breakthrough Energy Ventures), Andreessen Horowitz, T. Rowe Price
- **Technology**: Integrates historical geophysical data, satellite imagery, geochemical surveys, and geological models using proprietary AI/ML
- **Major discovery**: In July 2024, discovered a massive copper deposit at Mingomba, Zambia -- the largest copper find in over a decade. Planning a $2 billion underground mine producing 300,000+ tonnes/year of copper by 2030.
- **Scale**: Invests >$100M annually across 70+ projects on five continents
- **Success rate**: AI-powered exploration has achieved ~75% success in discovering new critical mineral reserves, compared to <1% industry average for traditional methods

**Reference:** https://koboldmetals.com/

#### Other Companies and Projects

- **Earth AI (Australia)**: Proprietary drilling hardware + AI trained on decades of Australian geological data. Targets copper, nickel, gold.
- **GeologicAI (Canada)**: $44M Series B. AI-powered drill core analysis using on-site sensors and machine learning. Provides real-time mineral data from physical cores.
- **Terra AI**: Builds "underground maps" by integrating thousands of geological layers. Aims to halve the 17-year average mine development timeline.
- **VRIFY/DORA**: AI prospectivity mapping software that converts multivariate geoscience datasets into ranked exploration targets.
- **Barrick Gold, Newmont, Tata Steel**: Major miners now embed AI models across exploration-to-extraction workflows. Tata Steel runs 550+ AI models for optimization.

#### Academic Research (2022--2025)

Key findings from recent literature:

1. **CNN + hyperspectral mineral classification**: Hybrid CNN-Vision Transformer models achieve 98% overall accuracy on hyperspectral mineral datasets, outperforming SVM (72%) and standalone CNN (86%).

2. **Random Forest with Sentinel-2**: Iron oxide mapping in Cuprite, Nevada achieved ~70% overall accuracy with Sentinel-2 multispectral data alone. Lithological classification combining remote sensing + geophysics reached 81% overall accuracy.

3. **MTMF with Hyperion**: Mixture-Tuned Matched Filtering on spaceborne hyperspectral data achieved 86% overall accuracy for alteration mineral mapping (kappa = 0.80).

4. **Deep learning for prospectivity**: AI models identifying mineral deposits with up to 92% accuracy using multispectral data, analyzing >10,000 km2/day.

---

## 2. PROPOSED ARCHITECTURE

### System Design: Four-Layer Pipeline

```
+------------------------------------------------------------------+
|                    LAYER 1: DATA ACQUISITION                      |
+------------------------------------------------------------------+
| Hyperspectral  | SAR Radar   | Thermal  | Gamma-Ray | Ancillary  |
| EMIT/EnMAP/    | NISAR L+S   | ASTER    | Airborne  | DEM (SRTM) |
| PRISMA/S-2     | PALSAR-2 L  | Landsat  | surveys   | Geology    |
| (VNIR+SWIR)    | Sentinel-1 C| TIR      | (K,U,Th)  | Geochemistry|
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                    LAYER 2: PROCESSING                            |
+------------------------------------------------------------------+
| 2a. Atmospheric Correction                                        |
|     - FLAASH / 6S / Sen2Cor (for Sentinel-2)                    |
|     - Converts radiance -> surface reflectance                    |
|                                                                   |
| 2b. Spectral Processing                                          |
|     - Continuum removal for absorption feature analysis           |
|     - Spectral Angle Mapper (SAM): angle-based mineral ID         |
|     - Spectral Feature Fitting (SFF): absorption-based matching   |
|     - Mixture-Tuned Matched Filtering (MTMF): sub-pixel targets  |
|     - Linear/nonlinear spectral unmixing                          |
|                                                                   |
| 2c. Material Classification                                      |
|     - Band ratio indices (Clay, Iron Oxide, Ferrous, Carbonate)  |
|     - Principal Component Analysis for anomaly detection          |
|     - Minimum Noise Fraction (MNF) transform                     |
|                                                                   |
| 2d. Multi-Sensor Fusion                                           |
|     - Co-registration and resampling to common grid               |
|     - Feature-level fusion of spectral + radar + thermal          |
|     - SAR-derived structural maps overlaid on mineral maps        |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                    LAYER 3: AI/ML ENGINE                          |
+------------------------------------------------------------------+
| 3a. Classical ML (Baseline)                                       |
|     - Random Forest / XGBoost: fast, interpretable, robust        |
|     - SVM with RBF kernel: proven on hyperspectral data           |
|     - Good for <50 input features (band ratios, indices)          |
|                                                                   |
| 3b. Deep Learning                                                 |
|     - 1D-CNN: spectral classification per pixel                   |
|     - 2D/3D-CNN: spatial-spectral feature extraction              |
|     - Vision Transformers (ViT): long-range spectral dependencies |
|     - Hybrid CNN-ViT: SOTA for hyperspectral (98% OA)            |
|                                                                   |
| 3c. Subsurface Inference (Indirect)                               |
|     - Surface alteration halo detection -> infer buried ore body  |
|     - Structural lineament analysis from SAR/DEM                  |
|     - Geochemical anomaly pattern recognition                     |
|     - Pathfinder mineral association models                       |
|                                                                   |
| 3d. Transfer Learning                                             |
|     - Pre-train on USGS spectral library (lab spectra)            |
|     - Fine-tune on satellite imagery of known deposits            |
|     - Domain adaptation: lab spectra -> field spectra             |
|                                                                   |
| 3e. Training Data Strategy                                        |
|     - USGS MRDS database: known mine/deposit locations            |
|     - USGS/ECOSTRESS spectral libraries: reference spectra        |
|     - Published hyperspectral+mineral label datasets              |
|     - Self-supervised pre-training on unlabeled satellite imagery |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                    LAYER 4: OUTPUT PRODUCTS                       |
+------------------------------------------------------------------+
| 4a. Mineral Probability Maps                                      |
|     - Per-pixel probability for target minerals                   |
|     - Multi-class mineral occurrence maps                         |
|                                                                   |
| 4b. Confidence/Uncertainty Layers                                 |
|     - Model confidence scores per pixel                           |
|     - Data quality flags (cloud, vegetation, moisture)            |
|     - Spectral match quality metrics                              |
|                                                                   |
| 4c. Anomaly Maps                                                  |
|     - Spectral anomalies (unusual compositions)                   |
|     - Structural anomalies (lineament intersections)              |
|     - Multi-parameter coincidence scoring                         |
|                                                                   |
| 4d. Exploration Target Ranking                                    |
|     - Prioritized target list with supporting evidence            |
|     - Ground-truth sampling recommendations                       |
|     - Cost-benefit analysis per target                            |
+------------------------------------------------------------------+
```

### Model Selection Guidance

| Method | Best For | Accuracy (OA) | Compute | Interpretability |
|---|---|---|---|---|
| Random Forest | Baseline, small datasets, few features | 70--85% | Low | High |
| XGBoost | Tabular features, band ratios | 75--88% | Low | Medium |
| SVM (RBF) | Small training sets, hyperspectral | 72--85% | Medium | Low |
| 1D-CNN | Per-pixel spectral classification | 85--95% | Medium | Low |
| 2D/3D-CNN | Spatial-spectral jointly | 88--98% | High | Low |
| Vision Transformer | Long-range spectral dependencies | 90--98% | High | Low |
| CNN-ViT Hybrid | SOTA hyperspectral classification | 95--98% | High | Low |

**Recommendation:** Start with Random Forest/XGBoost on band ratios as a baseline, then progress to 1D-CNN for hyperspectral data, and CNN-ViT hybrid for maximum performance.

---

## 3. HONEST LIMITATIONS

### Maximum Realistic Depth of Detection

| Method | Detection Type | Max Depth | Conditions Required |
|---|---|---|---|
| Hyperspectral (optical) | Direct surface detection | 0 m (surface only) | Exposed rock/soil, no vegetation |
| Thermal IR | Surface emissivity mapping | 0 m (surface only) | Clear atmosphere, no cloud |
| SAR L-band | Subsurface structure | 1--2 m | Hyperarid, fine-grained sand |
| SAR P-band | Subsurface structure | 3--5 m | Hyperarid, fine-grained sand |
| Gamma-ray spectrometry | Radioelement concentration | 30--45 cm | No water cover |
| Indirect inference | Alteration halo/pathfinders | Conceptually unlimited | Exposed alteration minerals at surface |

**The critical distinction:**
- **Detection** = directly sensing a material. Limited to surface or near-surface.
- **Inference** = detecting surface clues (alteration minerals, structural patterns, geochemical anomalies) that statistically correlate with buried ore bodies. This is how all successful remote-sensing-based mineral exploration actually works.

### Terrain and Conditions Where It Fails

| Condition | Impact | Severity |
|---|---|---|
| **Dense vegetation (>30% cover)** | Masks spectral signature of underlying geology | **Critical** -- renders optical methods useless |
| **Wet soil / recent rain** | Alters spectral response, blocks radar penetration | **Severe** -- distorts mineral signatures |
| **Snow / ice cover** | Completely masks surface | **Critical** |
| **Water bodies** | No mineral information retrievable | **Critical** |
| **Thick regolith / transported cover** | Masks bedrock mineralogy | **Severe** -- surface minerals unrelated to subsurface |
| **Cloud cover** | Blocks optical sensors (SAR unaffected) | **Moderate** -- use cloud-free composites |
| **Urban / built areas** | Man-made materials create false spectral matches | **Moderate** |
| **Deep weathering profiles** | Surface geochemistry differs from primary rock | **Significant** |

### Most Common False Positives

1. **Iron oxide confusion**: Lateritic soils can appear similar to hydrothermal iron oxide alteration
2. **Clay mineral ambiguity**: Weathering clays vs. hydrothermal clays have overlapping spectral signatures at multispectral resolution
3. **Vegetation-mineral mixing**: Partial vegetation cover creates mixed spectra that algorithms misclassify
4. **Shadow effects**: Topographic shadows alter apparent reflectance
5. **Atmospheric residuals**: Incomplete atmospheric correction creates artifacts mimicking mineral features, especially near water vapor absorption bands (1.4 and 1.9 micrometers)
6. **Transported materials**: Alluvial deposits may show mineral signatures unrelated to local bedrock

### Material Detectability

**Directly detectable with optical remote sensing (exposed surfaces):**
- Iron oxides: hematite, goethite, jarosite (VNIR absorption ~0.5--0.9 um)
- Clay minerals: kaolinite, montmorillonite, illite (SWIR absorption ~2.2 um)
- Carbonates: calcite, dolomite (SWIR absorption ~2.3 um, TIR ~11 um)
- Sulfates: gypsum, alunite, jarosite (SWIR absorption ~1.75, 2.2 um)
- Silicates: quartz (TIR reststrahlen ~8.5 um), olivine, pyroxene
- Amphiboles/epidote (SWIR absorption features)

**Not directly detectable by spectral methods:**
- Most metallic ores (gold, copper sulfides, zinc, lead) -- they lack diagnostic spectral features in VNIR/SWIR
- Subsurface deposits with no surface expression
- Materials under water, thick vegetation, or transported cover

**Inferred through association:**
- Copper porphyry deposits: detected via associated alteration minerals (phyllic: sericite/pyrite; argillic: kaolinite/montmorillonite; propylitic: chlorite/epidote)
- Gold deposits: detected via associated silicification, iron oxide gossans, arsenic-bearing minerals
- Lithium (in pegmatites): detected via associated muscovite, lepidolite spectral signatures
- REE deposits: sometimes associated with specific carbonate/phosphate signatures

---

## 4. COSTS AND DATA ACCESS

### Free Satellite Data Sources

| Sensor | Data | Resolution | Coverage | Access |
|---|---|---|---|---|
| **EMIT (NASA)** | 285-band hyperspectral | 60 m | ISS orbit (+/- 52 deg) | **Free** via LP DAAC |
| **EnMAP (DLR)** | 228-band hyperspectral | 30 m | Global (request-based) | **Free** (open access) |
| **PRISMA (ASI)** | 239-band hyperspectral | 30 m | Global (request-based) | **Free** (registration required) |
| **Sentinel-2 (ESA)** | 13-band multispectral | 10--60 m | Global, 5-day revisit | **Free** via Copernicus |
| **Sentinel-1 (ESA)** | C-band SAR | 5--20 m | Global, 6-day revisit | **Free** via Copernicus |
| **Landsat 8/9 (USGS)** | 11-band multispectral | 15--100 m | Global, 8-day revisit | **Free** via USGS |
| **ASTER (NASA/METI)** | 14-band multi (TIR active) | 15--90 m | Global archive | **Free** (SWIR failed 2008) |
| **NISAR (NASA/ISRO)** | L+S band SAR | 7 m | Global, 12-day repeat | **Free** (launched July 2025) |
| **ALOS-2 PALSAR-2** | L-band SAR | 1--10 m | Global mosaics | **Free** (mosaics via JAXA) |

### Commercial Data Costs

| Data Type | Typical Cost | Notes |
|---|---|---|
| **Hyperspectral airborne survey (AVIRIS-class)** | $3,000--5,000 per flight hour; min ~$70,000 per mission | Covers ~100--500 km2 per flight day |
| **WorldView-3 SWIR** | $14--25/km2 | Best commercial resolution (3.7 m SWIR) |
| **DESIS hyperspectral** | Commercial pricing via Teledyne | 30 m, VNIR only |
| **Custom drone hyperspectral** | $5,000--20,000 per survey day | Very high resolution (<1 m), small areas |
| **Airborne gamma-ray survey** | $20--50/line-km | Typically flown at 200--400 m line spacing |

### Processing Costs

| Component | Estimate | Notes |
|---|---|---|
| **Cloud GPU (training)** | $1--3/hr (T4/A10G via Colab Pro, RunPod) | A single hyperspectral scene trains in minutes |
| **Cloud storage (1 TB)** | ~$20--50/month | A single EMIT scene is ~2--5 GB |
| **Google Earth Engine** | Free for research | Limited for very large-scale commercial use |
| **Microsoft Planetary Computer** | Free (approved account) | Includes Jupyter + co-located data |

### MVP Cost Estimate

| Phase | Cost | Timeline |
|---|---|---|
| **Phase 1: Free data pipeline** | $0 (researcher time only) | 2--3 months |
| **Phase 2: Sentinel-2 mineral mapping** | $0--100 (Colab Pro) | 1--2 months |
| **Phase 3: Hyperspectral (EMIT/EnMAP) integration** | $0--500 (compute) | 2--3 months |
| **Phase 4: Multi-sensor fusion + AI** | $500--2,000 (compute) | 3--4 months |
| **Phase 5: Validation against known deposits** | $0 (USGS data) | 1--2 months |
| **Total MVP** | **$0--2,600** | **9--14 months** |

Note: This assumes the developer's time is not costed. A single full-time developer/researcher working on this would add $80,000--150,000/year in salary.

---

## 5. INTEGRATION WITH SOST

### Connection to the Materials Discovery Engine

The SOST Materials Discovery Engine (as described in MATERIALS_ENGINE_PLAN.md) focuses on computational materials discovery using graph neural networks and other AI methods. Remote sensing integration creates a powerful feedback loop:

1. **GNN-predicted materials -> Spectral signature prediction**: If a GNN discovers a novel material with a predicted crystal structure, density functional theory (DFT) calculations can estimate its vibrational modes, which in turn predict infrared/Raman spectral signatures. These predicted signatures could be added to a synthetic spectral library for remote detection. This is technically feasible but challenging -- predicted spectra would need validation against lab measurements.

2. **Remote sensing -> Materials Engine validation**: If remote sensing detects an unknown spectral signature in a geological context, the Materials Engine could search its database of predicted materials for matching optical/vibrational properties, potentially identifying novel natural materials before physical sampling.

### Blockchain for Proof of Discovery

SOST's blockchain could provide:

1. **Timestamped Proof of Discovery**: When the remote sensing system identifies a potential mineral deposit, the discovery metadata (location hash, spectral evidence hash, confidence score, timestamp) could be recorded as a transaction on the SOST blockchain using the Capsule Protocol. This creates an immutable, timestamped record of who discovered what, when.

2. **Claim Staking**: A "Proof of Discovery" transaction type could encode discovery claims. The Capsule Protocol v1 (12-byte header + up to 243-byte body, activating at height 5000) is well-suited for embedding discovery metadata.

3. **Verification Trail**: Subsequent ground-truth validation results could be linked to the original discovery transaction, building an auditable chain from remote detection to confirmed deposit.

4. **Economic incentive**: SOST's gold-backing philosophy aligns naturally with mineral exploration. Discovery claims could have economic value within the SOST ecosystem.

### Distributed Computation Marketplace

SOST could host a distributed marketplace for hyperspectral processing:

1. **Problem**: Hyperspectral data processing is compute-intensive but embarrassingly parallel (each pixel can be classified independently).
2. **Mechanism**: Users submit processing jobs (atmospheric correction, spectral unmixing, classification) as transactions. Miners/processors compete to perform the computation. Results are verified by consensus.
3. **Payment**: Processing fees paid in SOST tokens.
4. **Challenge**: Verifying that computation was performed correctly is non-trivial. A commit-reveal scheme or redundant computation with majority voting could work.

This is conceptually feasible but would require significant protocol development beyond the current SOST architecture.

---

## 6. COMPETITORS AND MARKET

### Key Competitors in AI-Powered Mineral Exploration

| Company | Focus | Funding | Technology |
|---|---|---|---|
| **KoBold Metals** | Critical minerals (Cu, Ni, Li, Co) | $1B+ total, $3B valuation | Proprietary AI on multi-source geological data |
| **Earth AI** | Cu, Ni, Au in Australia | Series A | Proprietary drilling + AI analytics |
| **GeologicAI** | Drill core analysis | $44M Series B | On-site AI sensors for real-time mineral ID |
| **Terra AI** | Multi-layer underground mapping | Early stage | Geological layer integration |
| **VRIFY (DORA)** | Prospectivity mapping software | Public (TSXV) | Multi-variate AI target generation |
| **Datarock** | Drill core & chip logging | Early stage | Computer vision for geological logging |
| **Minerva Intelligence** | AI reasoning for exploration | Public (TSXV) | Knowledge graph-based geological AI |

### Market Size

- **Global mineral exploration spending**: Estimated at $10--13 billion annually (2024), growing 5--7% CAGR
- **Copper exploration alone**: Exceeded $3 billion for the first time since 2013
- **Lithium exploration**: Grew 77% to $830 million (2023), now third most explored commodity
- **Remote sensing services for mining**: ~$500M--1B subset of exploration market
- **AI in mining market**: Projected to reach $3--5 billion by 2028

### What Mining Companies Pay for Exploration Data

- **Airborne geophysical surveys**: $50,000--500,000 per project
- **Satellite data packages**: $10,000--100,000 per region
- **AI prospectivity reports**: $50,000--500,000 per study area
- **Full exploration programs (greenfield)**: $1M--10M before any drilling
- **Drilling programs**: $200--500 per meter; a 5,000 m program costs $1--2.5M

### Business Model Viability

**Viable models:**
1. **SaaS prospectivity mapping**: Subscription platform where junior miners upload their data and get AI-generated exploration targets. ~$5,000--50,000/month per client.
2. **Project-based consulting**: Deliver mineral probability maps for specific concessions. $50,000--200,000 per project.
3. **Data marketplace**: Sell processed mineral maps derived from free satellite data. $1,000--10,000 per region.
4. **Equity stakes**: Provide exploration services in exchange for equity/royalties in discoveries (KoBold's model).

**The KoBold model proves the market exists.** Their $3B valuation is built on AI-guided mineral exploration. The key differentiator would be making the technology more accessible and affordable, particularly for junior mining companies who cannot afford KoBold-scale operations.

---

## 7. ZERO-COST ROUTE

This section details how to build a functional mineral detection system using exclusively free and open resources.

### A) Free Satellite Data

#### Sentinel-2 (ESA Copernicus)

**Specifications:** 13 bands, 10/20/60 m resolution, 5-day revisit, global coverage.

**Mineral mapping capability with 13 bands:**

Sentinel-2 has two SWIR bands (B11: 1610 nm, B12: 2190 nm) and three red-edge bands (B5, B6, B7) that provide limited but useful mineralogical discrimination:

| Mineral Group | Detection Index | Sentinel-2 Bands Used | Effectiveness |
|---|---|---|---|
| **Iron oxides** (hematite, goethite) | B4/B2 (ferric iron) | Red / Blue ratio | **Good** -- broad VNIR absorption is captured |
| **Ferrous iron** (Fe2+ in mafics) | B11/B8A + B12/B8A | SWIR/NIR ratios | **Moderate** |
| **Hydroxyl/clay minerals** | B11/B12 | SWIR ratio | **Moderate** -- detects presence but cannot distinguish kaolinite from montmorillonite |
| **Carbonates** | B11/B2, B13/B14 (Landsat equivalents) | SWIR combinations | **Weak** -- single SWIR band near 2.2 um lacks resolution |
| **Sulfates** (gypsum, alunite) | B11/B12 | SWIR ratio | **Weak** -- need narrow bands around 1.75 um |

**Key limitation:** With only 2 SWIR bands, Sentinel-2 can detect the *presence* of clays, carbonates, and sulfates but **cannot distinguish between them**. This requires the narrow bands (5--10 nm) that only hyperspectral sensors provide. For example, kaolinite, montmorillonite, and illite all have absorption features near 2.2 um but at slightly different positions -- Sentinel-2's ~200 nm-wide B12 band cannot resolve these differences.

**What IS useful:** Sentinel-2 excels at mapping iron oxide zones, broad clay alteration halos, and lithological boundaries. For porphyry copper exploration, the combination of iron oxide + clay alteration mapping is a valid first-pass target generation approach.

#### Landsat 8/9 (USGS)

Two SWIR bands (Band 6: 1570--1650 nm, Band 7: 2110--2290 nm) at 30 m. Complementary to Sentinel-2, providing a longer time series (Landsat archive back to 1972). Same mineralogical limitations as Sentinel-2.

#### EMIT (NASA)

- **Free and open**: All data downloadable via NASA Earthdata (LP DAAC)
- **Coverage**: ISS orbit, so limited to latitudes between ~52 deg N and 52 deg S. Not continuous global coverage -- data collected in strips as the ISS passes overhead. Coverage is best over arid dust source regions (the primary mission objective) but includes many other areas.
- **Mineral products**: L2B mineral identification and L4 Earth System Model products are available as pre-processed mineral maps.
- **For zero-cost route**: This is the **best free hyperspectral data source**. 285 bands at 60 m can distinguish individual mineral species. Check coverage at https://search.earthdata.nasa.gov for your area of interest.

#### EnMAP and PRISMA

Both offer free data but require proposals/requests:
- **EnMAP**: Submit a data request via enmap.org. Processing and approval may take weeks. 228 bands, 30 m.
- **PRISMA**: Register at prisma.asi.it. Both archived and new acquisitions available. 239 bands, 30 m.
- These provide excellent hyperspectral data for targeted study areas but are not suitable for systematic global screening (limited coverage, request-based access).

#### Sentinel-1 SAR

- C-band (5.7 cm wavelength), free via Copernicus
- Useful for: structural lineament mapping, surface roughness, soil moisture estimation
- **Not useful for subsurface mineral detection** at C-band -- penetration is only 0.1--0.5 m even in ideal conditions
- Best used as a complementary structural geology layer

#### ASTER

- Free via NASA Earthdata
- **TIR bands still operational**: 5 thermal bands at 90 m are uniquely valuable for mapping quartz, feldspars, carbonates, and silicates
- **SWIR bands failed in April 2008**: Only pre-2008 SWIR data available, but the archive is extensive
- Good for: thermal inertia mapping, silicate composition, and pre-2008 mineral mapping

### B) Free Spectral Libraries

#### USGS Spectral Library v7

- ~2,600+ spectra covering minerals, rocks, soils, vegetation, and man-made materials
- Wavelength range: 0.35--200 um (practical range 0.35--2.5 um for most remote sensing)
- **Download**: https://www.sciencebase.gov/catalog/item/5807a2a2e4b0841e59e3a18d
- **Format**: ASCII text files and SPECPR format

**Resampling to Sentinel-2 bands:** Yes, this is a standard and well-documented procedure. You take the high-resolution (1 nm) USGS spectra and convolve them with Sentinel-2's spectral response functions to produce 13-band "simulated Sentinel-2" spectra for each mineral. This creates training signatures for classifiers. However, the discriminating power is limited because many minerals that are distinct at 1 nm resolution become indistinguishable when reduced to 13 broad bands.

#### ECOSTRESS Spectral Library (JPL)

- 3,400+ spectra with thermal infrared coverage (0.35--15.4 um)
- Particularly useful for ASTER TIR band analysis
- **Download**: https://speclib.jpl.nasa.gov

### C) Free Software

| Tool | Purpose | License |
|---|---|---|
| **QGIS** | GIS visualization, analysis, map production | GPL |
| **Google Earth Engine (GEE)** | Cloud-based satellite data access and processing | Free for research/education |
| **Python + rasterio** | Raster I/O, geotransforms, reprojection | BSD |
| **Spectral Python (SPy)** | Hyperspectral image processing, classification, spectral matching | MIT |
| **scikit-learn** | Random Forest, SVM, XGBoost, clustering | BSD |
| **PyTorch / TensorFlow** | Deep learning (CNN, Transformer) | BSD / Apache 2.0 |
| **hylite** | Open-source spectral geology toolbox | GPL |
| **HypPy** | Hyperspectral processing with spectral math | Open source |
| **GDAL/OGR** | Geospatial data abstraction, format conversion | MIT |
| **Awesome Spectral Indices** | Pre-built spectral index calculations for GEE | MIT |
| **Sen2Cor** | Atmospheric correction for Sentinel-2 (ESA official) | GPL |
| **SNAP (ESA)** | Sentinel Application Platform, full processing toolbox | GPL |

**Specialized mineral mapping in Python:** The `spectral` (SPy) library directly supports reading USGS spectral libraries, performing SAM/SFF classification, and working with ENVI-format hyperspectral data. The `hylite` library adds machine learning-based mineral classification with reference spectra integration.

### D) Free Training Data

#### USGS Mineral Deposit Databases

- **MRDS (Mineral Resources Data System)**: Global database of metallic and nonmetallic mineral deposits with name, location, commodity, geology. Accessible via https://mrdata.usgs.gov/mrds/
- **USMIN**: Detailed database of significant US mineral deposits. Access via https://mrdata.usgs.gov/deposit/
- **EarthMRI data**: New geophysical/geochemical surveys being released publicly
- **Use case**: Mine and deposit locations serve as ground-truth labels. Extract Sentinel-2/EMIT pixels at known deposit locations to build training datasets.

#### OneGeology

- Global geological maps from 120+ national surveys, typically at 1:1M scale
- Accessible via https://portal.onegeology.org
- **Use case**: Cross-reference mineral maps with geological unit boundaries; use lithology as prior information for classifiers

#### Published Labeled Datasets

Several papers have published satellite + mineral label datasets:
- **Cuprite, Nevada**: The de facto validation site for mineral remote sensing. AVIRIS data + detailed mineral maps from USGS are freely available.
- **Indian AVIRIS-NG datasets**: Published mineral maps from the India campaign.
- **Various thesis/paper datasets**: Search for "hyperspectral mineral mapping dataset" on Zenodo, Figshare, or paper supplementary materials.

### E) Free Compute

| Platform | GPU | Storage | Limitations |
|---|---|---|---|
| **Google Colab (free)** | T4 (15 GB VRAM) | 15 GB RAM, temp disk | ~12 hr sessions, limited runtime |
| **Google Colab Pro** | T4/A100 ($10/month) | 25 GB RAM | Longer sessions, priority access |
| **Google Earth Engine** | Google cloud backend | Petabytes of satellite data | Free for research; GEE processes server-side |
| **Microsoft Planetary Computer** | JupyterHub with co-located data | Petabytes (Sentinel, Landsat, etc.) | Free with approved account |
| **Kaggle Notebooks** | T4/P100 (free) | 16 GB RAM | 30 hr/week GPU quota |

### F) Proposed Zero-Cost Pipeline

#### Step 1: Define Study Area and Download Data

```
Target: Known arid mining region (e.g., Atacama, Pilbara, Cuprite NV)
Data: Download Sentinel-2 L2A (atmospherically corrected) via GEE
       -> Select cloud-free composite for dry season
       -> Extract all 13 bands at 20 m resolution (resample 10m bands)
Time: 1 day
```

#### Step 2: Acquire Ground Truth

```
Source: USGS MRDS database + USMIN for known deposit locations
        USGS geologic maps for lithological boundaries
Action: Extract Sentinel-2 pixel values at each known deposit/mine location
        Label: commodity type, deposit type, host rock
        Split: 70% training, 15% validation, 15% test
Time: 2-3 days
```

#### Step 3: Calculate Spectral Indices

```
Iron Oxide Index:        B4/B2  (ferric iron enhancement)
Ferrous Iron Index:      B11/B8A  (ferrous silicate indicator)
Clay/Hydroxyl Index:     B11/B12  (clay mineral indicator)
Carbonate Index:         B11/B2  (carbonate/mafic separator)
Vegetation Index (NDVI): (B8-B4)/(B8+B4)  (to MASK vegetated areas)
False Color Composite:   B12/B11/B4  (mineral alteration visualization)

Implementation: Google Earth Engine or Python (rasterio + numpy)
Time: 1-2 days
```

#### Step 4: Train Baseline ML Models

```
Features: 13 Sentinel-2 bands + 5 spectral indices = 18 features per pixel
Labels: Mineral deposit type from USGS MRDS
Models:
  - Random Forest (500 trees) -> baseline
  - XGBoost -> typically outperforms RF on tabular data
  - SVM (RBF kernel) -> if training set is small
Evaluation: F1-score, confusion matrix, per-class accuracy
Platform: Google Colab (free GPU not needed for RF/XGBoost)
Time: 1-2 weeks
```

#### Step 5: Upgrade to Deep Learning (if warranted)

```
Input: Multi-band Sentinel-2 patches (e.g., 32x32 pixels x 13 bands)
Models:
  - 1D-CNN on spectral vectors (fast, good baseline)
  - 2D-CNN on image patches (captures spatial context)
Augmentation: Random rotation, flipping, spectral noise injection
Platform: Google Colab (free T4 GPU)
Time: 2-4 weeks
```

#### Step 6: Generate Probability Maps

```
Apply trained model to new target regions
Generate per-pixel probability maps for target mineral groups
Apply confidence thresholding and minimum cluster size
Export as GeoTIFF for visualization in QGIS
Time: 1 week per target region
```

#### Step 7: Validate Against Known Geology

```
Compare output maps to:
  - Published geological maps (OneGeology, national surveys)
  - Known but withheld deposit locations (test set)
  - Published mineral maps from hyperspectral studies of same area
Calculate precision/recall for deposit detection
Time: 1-2 weeks
```

### G) Realistic Results with the Free Approach

#### Minerals Detectable with Sentinel-2 (13 bands)

| Mineral/Group | Detection Quality | Evidence |
|---|---|---|
| **Hematite/goethite (iron oxides)** | Good | Strong VNIR absorption captured by B2/B3/B4 ratios. Papers report 70--85% accuracy in arid regions. |
| **Broad clay alteration zones** | Moderate | B11/B12 ratio detects clay presence but cannot distinguish species. ~60--70% accuracy for presence/absence. |
| **Laterite/ferricrete** | Good | Strong iron oxide + clay signature. Well-captured by multispectral data. |
| **Gossans (oxidized sulfide caps)** | Moderate | Iron oxide-rich, detectable as anomalous iron zones. High false positive rate. |
| **Lithological boundaries** | Good | Multispectral + textural features can discriminate major rock types at 70--81% accuracy. |
| **Individual clay species** | Poor | Kaolinite vs. montmorillonite vs. illite: NOT distinguishable with 13 bands. Requires hyperspectral. |
| **Carbonates vs. clays** | Poor | Overlapping signatures at Sentinel-2 resolution. |
| **Sulfates (gypsum, alunite)** | Poor | Requires narrow SWIR bands not available on Sentinel-2. |
| **Silicate variation** | Poor | Requires TIR bands (use ASTER instead). |

#### Reported Accuracy from Literature

- **Iron oxide mapping (Sentinel-2)**: 70--85% overall accuracy, ~0.70 F1-score in arid regions (Cuprite, NV validation).
- **Lithological classification (Sentinel-2 + geophysics)**: 81% overall accuracy, 0.52 F1-score (macro-averaged across many classes).
- **Broad alteration zone detection**: 65--75% overall accuracy as binary classification.
- **Compared to hyperspectral**: Sentinel-2 achieves roughly 60--70% of the discrimination capability of 200+ band hyperspectral for mineral mapping.

#### Conditions for Success vs. Failure

| Condition | Expected Performance |
|---|---|
| **Arid, exposed rock** (Atacama, Sahara, Pilbara) | **Best results**. 70--85% accuracy for iron oxides and broad alteration. |
| **Semi-arid, sparse vegetation** (<30% cover) | **Moderate**. NDVI masking needed, 60--75% accuracy. |
| **Temperate with seasonal exposure** | **Seasonal only**. Use dry-season imagery. 50--65% accuracy. |
| **Tropical / dense vegetation** | **Fails**. Vegetation completely masks geology. Use SAR for structure only. |
| **Glaciated terrain** | **Fails** during snow cover. Limited summer windows. |

#### Is It Enough to Produce Something Useful and Sellable?

**Yes, with caveats.** A Sentinel-2-based mineral alteration map is useful as a **first-pass screening tool** for identifying areas of interest in arid/semi-arid regions. Junior mining companies routinely use multispectral data for early-stage target generation. The output is comparable to what consulting geologists produce manually with Landsat/ASTER band ratios.

**It is NOT a substitute for:**
- Detailed mineral identification (need hyperspectral)
- Subsurface exploration (need geophysics)
- Resource estimation (need drilling)

**Potential market positioning:** Sell Sentinel-2-derived alteration maps at $1,000--5,000 per concession area as a low-cost screening service, positioned below the $50,000+ full hyperspectral surveys.

### H) Comparison Table: Free vs. Commercial

| Capability | Free Approach | Commercial Approach | Gap Assessment |
|---|---|---|---|
| **Spatial resolution** | 10--60 m (Sentinel-2, EMIT) | 1--5 m (WorldView-3, drones) | Significant -- commercial is 10-60x sharper |
| **Spectral bands** | 13 (S-2) or 285 (EMIT, if coverage exists) | 200--400 (AVIRIS-NG, drone) | Critical for S-2; negligible if EMIT available |
| **Mineral discrimination** | 5--8 broad groups | 50+ individual species | Large gap with S-2; small with EMIT |
| **Global coverage** | Excellent (S-2), partial (EMIT) | On-demand anywhere | S-2 advantage for screening |
| **Temporal coverage** | Multi-year archive (S-2 since 2015) | Single acquisition | Free data wins for change detection |
| **Processing tools** | Python, GEE, QGIS | ENVI, Harris, proprietary | Functionally equivalent for research |
| **ML/AI capability** | scikit-learn, PyTorch, Colab | Same tools + larger compute | Negligible gap |
| **Turnaround time** | Days to weeks | Hours to days | Moderate gap |
| **Subsurface inference** | SAR lineaments + alteration halos | Full geophysics suite | Large gap -- geophysics not replaceable |
| **Confidence level** | Screening / indicative | Decision-grade | Significant -- commercial supports drilling decisions |
| **Cost** | $0--2,600 (MVP) | $50,000--500,000 per project | 20--200x cheaper |

---

## 8. CONCLUSIONS AND RECOMMENDATION

### Executive Summary

Remote sensing-based mineral detection is a mature, proven technology for surface and near-surface geological mapping. The combination of freely available satellite data (Sentinel-2, EMIT, NISAR), open spectral libraries (USGS, ECOSTRESS), and modern AI/ML creates a genuinely viable path to building a mineral detection system at near-zero data acquisition cost.

However, the technology has fundamental physical limitations: optical sensors detect only surface-exposed minerals, radar penetrates at most a few meters in ideal conditions, and all remote sensing is a screening tool that must be followed by ground-truth validation and drilling. The most successful commercial approaches (KoBold Metals, $3B valuation) combine remote sensing with comprehensive multi-source geological data integration.

### Viability Rating per Component

| Component | Rating | Justification |
|---|---|---|
| **Surface mineral mapping (arid regions)** | **VIABLE** | Proven technology, free data available, 70--85% accuracy achievable |
| **Surface mineral mapping (vegetated regions)** | **NOT VIABLE** | Vegetation masks spectral signatures; no free workaround |
| **Individual mineral species identification** | **PARTIALLY VIABLE** | Requires hyperspectral (EMIT/EnMAP, free but limited coverage). Not possible with Sentinel-2. |
| **Subsurface deposit inference** | **PARTIALLY VIABLE** | Works via alteration halo detection in known geological contexts. Cannot detect blind/deep deposits. |
| **SAR structural geology** | **VIABLE** | Free NISAR/Sentinel-1 data, proven for lineament/fault mapping |
| **AI/ML mineral classification** | **VIABLE** | Open-source tools mature, published models achieve SOTA results |
| **Zero-cost Sentinel-2 screening** | **VIABLE** | Useful first-pass product for arid regions; marketable to junior miners |
| **Competing with KoBold-class systems** | **NOT VIABLE** | They integrate proprietary geological databases, field teams, and drilling programs. Technology alone is insufficient. |
| **SOST blockchain integration (Proof of Discovery)** | **PARTIALLY VIABLE** | Conceptually sound; Capsule Protocol suitable; market demand uncertain |
| **GNN spectral signature prediction** | **PARTIALLY VIABLE** | Technically possible via DFT intermediate; needs significant R&D |
| **Distributed processing marketplace** | **PARTIALLY VIABLE** | Technically feasible but verification is hard; small market initially |

### MVP Cost and Timeline

| Phase | Timeline | Cost | Deliverable |
|---|---|---|---|
| **Phase 1**: Sentinel-2 pipeline + USGS ground truth | Month 1--3 | $0 | Working iron oxide + clay alteration mapping for arid regions |
| **Phase 2**: ML model training + validation | Month 3--5 | $0--100 | Trained RF/XGBoost + CNN models, accuracy benchmarks |
| **Phase 3**: EMIT hyperspectral integration | Month 5--8 | $0--500 | 285-band mineral identification for EMIT-covered areas |
| **Phase 4**: Multi-sensor fusion (SAR + optical) | Month 8--11 | $500--2,000 | Fused structural + mineral probability maps |
| **Phase 5**: Blockchain integration prototype | Month 11--14 | $0 | Proof of Discovery Capsule transactions on SOST testnet |
| **TOTAL MVP** | **14 months** | **$0--2,600** (excluding labor) | |

### Final Recommendation

**Build it, but in phases with reality checks.**

1. **Start with Sentinel-2 mineral mapping** (Phase 1--2). This is zero-cost, uses proven techniques, and produces immediately useful outputs. Focus on a well-studied arid region (e.g., Cuprite NV, Pilbara AU, or Atacama CL) where you can validate against published results.

2. **Integrate EMIT hyperspectral data** (Phase 3) for the significant step up in mineral discrimination. This is the strongest free-data advantage available -- 285-band hyperspectral data that was previously only available via expensive airborne campaigns.

3. **Defer blockchain integration** until the remote sensing pipeline produces validated, useful outputs. Proof of Discovery is a compelling concept but has no value without a working detection system behind it.

4. **Do not attempt to compete with KoBold Metals directly.** Their advantage is not technology -- it is proprietary geological databases built over decades, field teams, and drilling infrastructure. Instead, position as an **accessible, low-cost screening platform** for junior mining companies and geological surveys who cannot afford KoBold-scale services.

5. **The GNN spectral prediction pipeline** is a novel research direction worth exploring as a long-term differentiator, but it should not be on the critical path for the MVP.

The strongest zero-cost opportunity is building a Sentinel-2 + EMIT + NISAR fusion system that delivers automated mineral/structural mapping products. This would compete at the $1,000--10,000 tier of exploration services rather than the $100,000+ tier, but could reach a much larger customer base of junior miners and government geological surveys.

---

### References

#### Sensors and Missions
- EMIT: https://earth.jpl.nasa.gov/emit/
- EnMAP: https://www.enmap.org/
- PRISMA: https://www.eoportal.org/satellite-missions/prisma-hyperspectral
- AVIRIS: https://aviris.jpl.nasa.gov/
- DESIS: https://www.tbe.com/what-we-do/markets/space/geospatial-solutions/desis/
- NISAR: https://science.nasa.gov/mission/nisar/
- ALOS-2 PALSAR-2: https://www.eorc.jaxa.jp/ALOS/en/dataset/alos_open_and_free_e.htm
- Sentinel-2: https://sentiwiki.copernicus.eu/web/s2-mission

#### Spectral Libraries
- USGS Spectral Library v7: https://pubs.usgs.gov/publication/ds1035
- ECOSTRESS Spectral Library: https://speclib.jpl.nasa.gov

#### Data Access
- NASA Earthdata (EMIT, ASTER): https://search.earthdata.nasa.gov
- Copernicus Open Access Hub (Sentinel): https://scihub.copernicus.eu
- USGS Earth Explorer (Landsat, ASTER): https://earthexplorer.usgs.gov
- USGS MRDS: https://mrdata.usgs.gov/mrds/
- Google Earth Engine: https://earthengine.google.com
- Microsoft Planetary Computer: https://planetarycomputer.microsoft.com

#### Software Tools
- Spectral Python (SPy): https://www.spectralpython.net/
- hylite: https://github.com/hifexplo/hylite
- Awesome Spectral Indices: https://awesome-ee-spectral-indices.readthedocs.io/
- QGIS: https://qgis.org

#### Companies
- KoBold Metals: https://koboldmetals.com/
- GeologicAI: https://geologicai.com/
- VRIFY: https://vrify.com/

#### Key Research
- "Assessment of the Capability of Sentinel-2 Imagery for Iron-Bearing Minerals Mapping" (2020), Remote Sensing 12(18):3028
- "Twenty Years of ASTER Contributions to Lithologic Mapping and Mineral Exploration" (2019), Remote Sensing 11(11):1394
- "A Comprehensive Survey for Hyperspectral Image Classification: From Conventional to Transformers" (2024), arXiv:2404.14955
- "Advanced Mineral Deposit Mapping via Deep Learning and SVM Integration" (2025), Engineering Reports
- IAEA-TECDOC-1363: Guidelines for Radioelement Mapping Using Gamma Ray Spectrometry

---

## Actual Results vs Predictions (March 2026 Update)

| Component | Prediction | Actual Result | Status |
|-----------|-----------|---------------|--------|
| S2 mineral mapping | VIABLE (AUC 0.70-0.85) | AUC 0.73 (S2 only, Chuquicamata) | CONFIRMED |
| Multi-source fusion | VIABLE | AUC 0.86 (24 bands, Chuquicamata) | CONFIRMED |
| Cross-zone transfer | PARTIALLY VIABLE | AUC 0.45-0.54 (cross-type = random) | FAILED cross-type |
| Label enrichment | HIGH impact | +0.15 AUC (Kalgoorlie 16→205 deposits) | CONFIRMED |
| Heuristic scanning | VIABLE | Working (Tintic, Utah — zero training) | CONFIRMED |
| EMIT integration | HIGH potential | 50 L2A scenes/zone, infrastructure ready | PENDING |
| Airborne geophysics | HIGH potential | GA data exists but WCS endpoints changed | PENDING |

**Key unexpected finding**: Transfer learning between commodity-compatible zones
(Chuquicamata Cu vs Zambia Cu) FAILS because deposit TYPES differ (porphyry vs
sediment-hosted). Transfer requires geological similarity, not just commodity match.

**Phase 5A finding**: Type-filtered training IMPROVES over mixed-type training.
Kalgoorlie Au-only (103 labels): AUC 0.8063 vs Kalgoorlie mixed (205 labels): AUC 0.7690.
Fewer labels of the right type beat more labels of mixed types (+0.037 AUC).

| Component | Prediction | Actual | Phase 5A Update |
|-----------|-----------|--------|-----------------|
| Type-aware models | Not predicted | AUC +0.04 | **CONFIRMED: type > mixed** |
| Deposit type taxonomy | Not predicted | 5,467 classified | **4 trainable types** |
| Same-type transfer | Not predicted | FAILED (0.49-0.55) | Even same deposit type fails |
| Domain normalization | Not predicted | +0.12 AUC (2 zones) | Helps partially |
| 3-zone LOZO | VIABLE | FAILED (0.510 avg) | Adding zones makes it worse |
| Vegetation zones | LIMITED | 0 signal (Salave) | Forest kills satellite signal |
| GNN inference | PARTIALLY VIABLE | CGCNN working | Direct forward pass on CIF |
| Heuristic scanning | VIABLE | 50 targets (Tintic) | Works globally without training |

## Phase 5G Conclusion (March 2026)

10 AOIs validated across 5 continents. Zone-specific models are the production
architecture. Transfer learning is definitively not viable for satellite features.
The heuristic scanner IS the global product. 162 targets with exact coordinates exported.

---

## Experiment 1: 20-Year Thermal Long-Term Proxies (V2 — Hardened)

**Date:** March 2026

### Background

Following detection of a moderate thermal signal in the original experiment (+0.013 AUC
at Kalgoorlie), V2 applied rigorous physical hardening:

- Bare-ground NDVI mask (exclude vegetated pixels)
- Topographic normalization (elevation regression for residual std)
- Geology-matched background (terrain + spectral proxy, >5km exclusion)
- Cross-site replication at Chuquicamata, Chile
- All validation via spatial block CV (no random pixel splits)

### Key Results

**Statistical signal survives geology-matched background:**
- `amplitude`: Cohen's d = -0.680, p = 2.2e-15 (VERY STRONG)
- `std_annual`: d = -0.617, p = 1.0e-12 (VERY STRONG)
- `thermal_range_ratio`: d = -0.565, p = 1.3e-07 (VERY STRONG)
- 6 of 14 features survive with p < 0.05 and |d| > 0.3

**Model improvement (spatial block CV at Kalgoorlie):**
- Baseline satellite: AUC 0.797
- + std_annual: AUC 0.825 (+0.013)
- + ratio + std: AUC 0.823 (+0.011)
- thermal_range_ratio enters permutation importance top 5

**Chuquicamata proxy replication:**
- LST bands show significant signal (d = -0.727, p = 0.010) in same direction
- Full 20-year replication pending GEE export

**Assessment score: 10/12 — MULTI_ZONE_READY**

### Correct Framing

This is a **thermal long-term proxy family**, not direct subsurface detection.
Deposits show lower thermal amplitude and range ratio than geologically-similar background,
consistent with different thermal inertia of altered/sulphide-bearing rock.
The signal is moderate but real, physically defensible, and cross-site consistent.
It improves but does not dominate the satellite spectral model.

| Component | Prediction | Actual | Status |
|-----------|-----------|--------|--------|
| Thermal proxy signal | Possible | d = -0.68, p < 1e-15 | **CONFIRMED** |
| Survives geology-matched BG | Unknown | YES (scenario C) | **CONFIRMED** |
| Model AUC improvement | Unknown | +0.013 (std_annual) | **CONFIRMED** |
| Cross-site consistency | Unknown | Same direction at Chuquicamata | **PARTIAL** (proxy only) |
| Physical plausibility | Expected | Lower thermal ratio at deposits | **CONFIRMED** |

### What Thermal Long-Term Proxies CAN Do

- Detect statistically significant differences in 20-year thermal climatology between mineralized and barren ground
- Provide a moderate but real improvement to zone-specific predictive models (+0.01-0.02 AUC)
- Add a physically defensible feature family based on thermal inertia differences
- Work in arid, bare-ground environments where vegetation does not dominate

### What Thermal Long-Term Proxies CANNOT Do

- Detect specific minerals or ore types underground
- Estimate depth, tonnage, or grade of mineralization
- Replace field verification, drilling, or geophysical surveys
- Work reliably in vegetated or heavily urbanized areas
- Dominate satellite spectral indices (thermal is a complement, not a replacement)
- Guarantee the presence of economic mineralization

### Phase 5I: Chuquicamata Full Replication

Full v2 pipeline replicated at Chuquicamata (55 porphyry Cu deposits, Atacama Desert).

**Cross-zone consistency (4 stable features):**
- amplitude: Kal d=-0.680, Chu d=-0.898 (both lower at deposits)
- thermal_range_ratio: Kal d=-0.565, Chu d=-0.785 (both lower)
- mean_annual: Kal d=-0.508, Chu d=-1.121 (both lower)
- summer_winter_diff: Kal d=-0.423, Chu d=-0.898 (both lower)

**Model improvement:** Kalgoorlie +0.013 AUC (moderate baseline 0.80). Chuquicamata
no AUC gain (strong baseline 0.91) but +0.044 PR-AUC. Thermal proxies are most useful
when the satellite baseline is moderate — they add less where spectral/SAR already saturates.

**Multi-zone verdict: PRODUCTION_WORTHY (4/6)**
Cautious backfill to similar arid zones recommended. Third-zone validation needed.

### Experiment 2: EMIT — EXECUTED (Chuquicamata)

EMIT (285 bands, 60m, ISS) — Earthdata Login resolved. 3 granules downloaded,
18.5% coverage at Chuquicamata.

Effect sizes large but marginal p-values (small sample: 8 deposits with valid EMIT data):
- clay_proxy d=+0.901, hydroxyl_proxy d=+0.885, mineral_id_count d=+0.785
- Physically correct: porphyry Cu deposits have clay/hydroxyl alteration detectable by EMIT
- EMIT-only AUC 0.750 (23 samples) vs satellite baseline 0.646 (88 samples)
- Fusion test inconclusive — need more granules for overlapping coverage

EMIT detects surface alteration minerals, NOT subsurface ore directly.

### Subsurface-Proxy V3: ML Residual — NEGATIVE

Predicted thermal_range_ratio from surface covariates (R² = 0.517), computed residual.
Residual does NOT differ between deposits and geology-matched background (p = 0.138, d = -0.250).
Does not improve deposit prediction AUC.

**Interpretation:** The thermal signal detected in Experiment 1 is substantially
explained by surface processes (elevation + NDVI account for 52% of thermal variance).
The "unexplained" component does not concentrate geological signal at Kalgoorlie.

This does NOT invalidate thermal proxies — Experiment 1 signal is real and replicable.
It means the residual decomposition approach does not extract additional independent value.

## Phase 6E: Type-Aware Feature Selection — Viability Assessment (March 2026)

### Universal Candidate Matrix

GeaSpirit now maintains a universal candidate family matrix tracking 17 feature families
across 9 zones (153 cells). Each family is classified as: USEFUL, NEGATIVE, AVAILABLE,
BLOCKED, or UNTESTED.

**Production-validated families:**
- **satellite_baseline** — Universal foundation. Always included. AUC 0.72-0.86 across 5 supervised zones.
- **thermal_20yr** — Universal modest improvement. +0.013 AUC at Kalgoorlie, consistent features across zones. Thermal long-term proxy family, NOT direct subsurface detection.
- **emit_alteration** — Porphyry-specific. hydroxyl d=+0.645 at Chuquicamata, d=-0.273 at Kalgoorlie (orogenic Au). 50 granules found for Peru replication.
- **pca_embeddings** — Kalgoorlie-specific. +0.026 AUC at Kalgoorlie, negative at all porphyry zones. Captures greenstone belt spatial textures.

**Negative results (honest):**
- **spatial_gradients** — Negative everywhere tested (-0.006 AUC at Kalgoorlie). Sobel + Laplacian multi-scale gradients do not help.
- **ml_residual** — Negative. Thermal signal at deposits appears explained by surface covariates.
- **pca_embeddings at porphyry zones** — Negative. Does not transfer from orogenic Au context.

### EMIT Viability — Deposit-Type Dependent

EMIT (285 bands, 60m, ISS orbit) is VIABLE for porphyry Cu but NOT for orogenic Au.

| Zone | Deposit Type | hydroxyl d | clay d | Model Impact | Verdict |
|------|-------------|-----------|--------|-------------|---------|
| Chuquicamata | Porphyry Cu | +0.645 | +0.293 | No AUC gain (saturated) | USEFUL (physical signal) |
| Kalgoorlie | Orogenic Au | -0.273 | -0.213 | -0.135 AUC | NEGATIVE (type mismatch) |
| Peru | Porphyry Cu | pending | pending | pending | 50 GRANULES FOUND |

**Correct framing:** EMIT detects surface alteration minerals (argillic/phyllic). This is relevant for porphyry Cu deposits (clay/hydroxyl alteration) but not for orogenic Au (carbonate/sericite/silica). EMIT does NOT see underground.

### AEM/Geophysics Viability — Partially Blocked

- GA aeromagnetics available for Kalgoorlie, untested as ML feature
- GSWA detailed AEM (200m spacing, deposit-scale) needs manual portal check
- AusAEM national grid too coarse (20km) for deposit targeting
- Operator checklist generated for manual data acquisition

### Frontier Ideas — 10 Registered

3 HIGH priority candidates ready for future testing:
1. Post-rainfall SAR drying rate
2. Nighttime thermal offset (ECOSTRESS)
3. Foundation model embeddings (SatCLIP/Prithvi)

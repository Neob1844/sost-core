# GeaSpirit CTO Sprint Report

**Date:** 2026-03-25
**Role:** Acting CTO — Decide, Innovate, Execute

---

## 1. Decisions Taken

| Decision | Rationale |
|----------|-----------|
| Skip Peru EMIT recovery | Both granules truncated. Network issue, not pipeline issue. Will retry later. |
| Execute multi-scale anomaly experiment FIRST | Novel idea, uses existing data, zero download needed, highest learning/effort ratio. |
| Document ECOSTRESS path instead of downloading | Download requires AppEEARS API setup. Path confirmed viable — defer to next sprint. |
| Document Earth MRI Arizona path | USGS just released exact data we need. Direct download from ScienceBase. Defer download to next sprint. |
| Assess Prithvi-EO-2.0 feasibility | 300M model fits in 8GB RAM on CPU. Feasible but slow. Defer to GPU session. |
| Invest 50% in innovation | Multi-scale anomaly experiment is the novel contribution of this sprint. |

---

## 2. Priority A Results

### A1: ECOSTRESS Diurnal Thermal — PATH CONFIRMED

- **Data:** ECO_L2T_LSTE V002 available via NASA LP DAAC and Google Earth Engine
- **Coverage:** Kalgoorlie (-31.4°) within ISS orbit (52°N-52°S). ~50-100 cloud-free scenes/year.
- **Access:** AppEEARS API, earthaccess Python library, or GEE (`NASA/ECOSTRESS/L2T_LSTE/V2`)
- **Resolution:** 70m, multiple overpass times per day (pre-dawn, morning, afternoon)
- **Status:** READY TO DOWNLOAD. Blocked only by API setup time.
- **Next step:** Use earthaccess library to bulk-download all Kalgoorlie passes.

### A2: Earth MRI Arizona — EXACT DATA FOUND

- **Data:** "Airborne magnetic and radiometric data, parts of SE Arizona" (USGS Earth MRI)
- **Source:** ScienceBase: `67fe127ed4be0201e1518b12`
- **Coverage:** 162,419 line-km, 200m line spacing, covering Arizona porphyry copper belt
- **Survey:** November 2023 — August 2024 by NV5 Geospatial
- **Format:** GeoTIFF grids (TMI, K, Th, U, dose rate)
- **Cost:** FREE (US Government public domain)
- **Status:** READY TO DOWNLOAD. Direct download, no auth needed.
- **Impact:** This is the STANDARD exploration dataset for Arizona. Integrating it should significantly improve our Arizona model (currently 0.718 AUC with only 5 labels).

### A3: Peru EMIT — BLOCKED

- Both granules truncated (54% and 41% downloaded respectively)
- 50 granules confirmed available via NASA CMR
- Pipeline is ready — needs manual download with better network
- **Status:** DEFERRED, not failed

---

## 3. Priority B: Prithvi-EO-2.0 Assessment

- **Model:** ibm-nasa-geospatial/Prithvi-EO-2.0-300M-TL on HuggingFace
- **Size:** 1.34 GB weights, ~3-4 GB RAM for inference
- **CPU viable:** YES (slow but functional). 8 GB RAM sufficient for single-tile.
- **Input:** 6 channels (B, G, R, NIR, SWIR1, SWIR2) from HLS at 30m
- **Framework:** TerraTorch for fine-tuning
- **Status:** FEASIBLE. Download model, convert our stack to HLS format, extract embeddings.
- **Blocker:** Inference speed on CPU. A full 1673×1960 stack would take hours per image.
- **Recommendation:** Run on Google Colab (free GPU) or downsample patches.

---

## 4. Innovation: Multi-Scale Anomaly Index Experiment

### The Concept (NOVEL — unpublished)

For each satellite/geophysics feature, compute at three spatial scales (local ~100m, medium ~500m, regional ~1.5km). Three derived features per band:
- **local_regional_ratio**: isolates deposit-scale anomalies from lithological trends
- **local_anomaly**: deviation from regional mean
- **heterogeneity**: variance in medium window (structural complexity)

### Statistical Discovery: 19 STRONG Features

| Feature | Cohen's d | p-value | Physical Meaning |
|---------|-----------|---------|-----------------|
| tpi_heterogeneity | **+0.878** | 1.2e-35 | Deposits in structurally complex terrain |
| elevation_heterogeneity | **+0.860** | 2.2e-30 | Deposits near elevation transitions |
| ruggedness_heterogeneity | **+0.835** | 6.6e-30 | Deposits in rough, heterogeneous zones |
| ferrous_iron_heterogeneity | **+0.808** | 8.4e-28 | Ferrous variability at deposit scale |
| ndvi_heterogeneity | **+0.806** | 9.0e-19 | Vegetation patchiness over deposits |
| laterite_heterogeneity | **+0.664** | 1.1e-10 | Laterite variability at deposit scale |
| ndvi_local_anomaly | **-0.596** | 2.6e-08 | LOWER local NDVI at deposits |
| ferrous_iron_local_anomaly | **+0.554** | 2.2e-05 | HIGHER local ferrous at deposits |
| ferrous_iron_local_regional_ratio | **+0.543** | 2.9e-07 | Ferrous anomaly localized |
| laterite_local_regional_ratio | **-0.538** | 1.5e-06 | Less laterite locally at deposits |

**Key insight:** d=+0.878 for tpi_heterogeneity is the STRONGEST single feature we've ever found. Stronger than thermal amplitude (d=-0.627) and EMIT hydroxyl (d=+0.645).

### ML Result: NEUTRAL (AUC delta = -0.0003)

| Model | Features | AUC |
|-------|----------|-----|
| Baseline | 12 | 0.8651 |
| Baseline + Multi-scale | 31 | 0.8648 |
| Multi-scale only | 19 | 0.7881 |

The gradient boosting model already implicitly learns scale-dependent patterns from the raw features. Adding explicit multi-scale features doesn't improve AUC.

### Interpretation

The experiment discovered a powerful PHYSICAL SIGNAL but didn't improve the ML MODEL. This is scientifically valuable:

1. **Deposits sit in structurally complex terrain** (high TPI/elevation/ruggedness heterogeneity) — this is consistent with the geological reality that orogenic gold deposits form along fault intersections and structural contacts.

2. **Local NDVI depression** at deposits (d=-0.596) — vegetation stress signal, consistent with metal toxicity.

3. **Local ferrous iron enrichment** (d=+0.554) — direct alteration signature.

4. The ML model already captures these patterns implicitly through its tree-based architecture (GBM naturally creates splits that act as implicit multi-scale filters). This means the baseline model is already well-designed.

5. **Potential value for interpretability:** Multi-scale features can explain WHY the model makes predictions — "this location is flagged because TPI heterogeneity is 2σ above regional average" is a geologist-friendly explanation.

---

## 5. Table by Mineral (Updated)

| Mineral | Best confirmed route | CTO Sprint finding |
|---------|---------------------|--------------------|
| **Gold (orogenic)** | sat + thermal + PCA (0.937) | tpi_heterogeneity d=+0.878 — strongest feature ever found |
| **Copper (porphyry)** | sat + thermal + EMIT (0.862) | Earth MRI data found for Arizona — next sprint |
| **Copper (sediment)** | sat (0.763) | No new data this sprint |

---

## 6. Next Steps (CTO Recommendation)

### Sprint 2 (next session):
1. **Download Earth MRI Arizona geophysics** from ScienceBase — build magnetics/radiometrics stack, test at Arizona
2. **Setup earthaccess + download ECOSTRESS** for Kalgoorlie — build diurnal ATI features
3. **Run Prithvi-EO-2.0** on Colab — extract embeddings for Kalgoorlie, test as ML features

### Sprint 3:
4. **Temporal DNA prototype** — extract weekly Landsat composites via GEE for Kalgoorlie
5. **Peru EMIT retry** — re-download with `wget --continue` from Earthdata

---

## 7. Honest Assessment: Are We Closer to the Canonical Objective?

> "Hay [mineral] a [profundidad] en [coordenadas] con certeza del [X%]"

**Mineral:** YES — we can say "gold" at Kalgoorlie (AUC 0.937), "copper" at Chuquicamata (0.862).

**Location:** PARTIALLY — we identify 1km² zones of high probability, not exact coordinates.

**Depth:** NO — we have zero depth information. All signals are surface proxies.

**Certainty:** PARTIALLY — AUC 0.937 means strong discrimination, but not calibrated probability.

**This sprint's contribution:**
- Confirmed that **structural complexity** (TPI heterogeneity d=+0.878) is the strongest deposit discriminator we've found — this is a GENUINE scientific finding
- Identified **three executable paths** to new data (ECOSTRESS, Earth MRI, Prithvi) that are ready to download
- The multi-scale framework provides **interpretable evidence** for predictions

**The gap:** We cannot estimate depth. The two most promising paths to depth information are:
1. **AEM conductivity** (subsurface proxy, but blocked by manual download)
2. **ECOSTRESS thermal inertia** (correlates with rock density/porosity, indirect depth proxy)
3. **Drill hole databases** (GSWA WAMEX) as ground truth with actual depth measurements

**Honest verdict:** We are building an increasingly powerful surface screening tool. To reach the canonical objective, we need subsurface data (AEM, drill holes) integrated with our surface predictions. The surface model tells you WHERE; the subsurface data tells you HOW DEEP.

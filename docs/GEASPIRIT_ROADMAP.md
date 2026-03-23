# GeaSpirit Platform — Executable Roadmap

**Version:** 1.0 — March 2026
**Philosophy:** Make → Measure → Fix → Repeat. Every sprint produces something demonstrable.
**Cost:** $0. All data and tools are free.
**Team:** 1 person with a laptop and internet.

---

## Executive Summary

The GeaSpirit Platform fuses computational materials science (Materials Engine) with satellite remote sensing to detect mineral deposits using free data and AI. This roadmap defines 7 sprints over 26 weeks, each producing a measurable result. The goal is to go from zero to a sellable mineral exploration report.

---

## Timeline

| Sprint | Weeks | Goal | Key Metric |
|--------|-------|------|-----------|
| 0 | 1 | Setup & data download | Can load Sentinel-2 image? |
| 1 | 2-3 | First mineral index maps | Visual correlation with known deposits? |
| 2 | 4-6 | First ML classifier | AUC > 0.65 |
| 3 | 7-10 | Multi-sensor fusion | AUC > 0.72 |
| 4 | 11-14 | Vegetation as sensor | +2% AUC from vegetation? |
| 5 | 15-18 | Transfer learning | AUC > 0.60 on new zone |
| 6 | 19-22 | Materials Engine integration | 3/5 known deposits found |
| 7 | 23-26 | First sellable report | Geologist feedback positive? |

---

## Sprint 0 — Setup (Week 1)

### Accounts to Create (free)
| Service | URL | Purpose |
|---------|-----|---------|
| Google Earth Engine | earthengine.google.com | Sentinel-2/1 processing |
| Copernicus Data Space | dataspace.copernicus.eu | Direct Sentinel download |
| USGS EarthExplorer | earthexplorer.usgs.gov | Landsat + DEM |
| NASA Earthdata | urs.earthdata.nasa.gov | EMIT hyperspectral |

### Software
```bash
pip install rasterio spectral scikit-learn xgboost earthengine-api geemap geopandas shapely matplotlib seaborn pandas numpy requests tqdm h5py
```

### Data to Download
- USGS Spectral Library v7 (~2,600 mineral spectra)
- MRDS deposit coordinates (300K+ global deposits)
- Copernicus DEM 30m for pilot zones

### Pilot Zones
| Zone | Location | Difficulty | Why |
|------|----------|-----------|-----|
| **Chuquicamata, Chile** | -22.3, -68.9 | Easy | Arid desert, world's largest Cu mine, 100+ known deposits |
| **Pilbara, Australia** | -22.0, 118.0 | Medium | Semi-arid, Fe+Au, open geophysical data from Geoscience Australia |
| **Zambian Copperbelt** | -12.8, 28.2 | Hard | Some vegetation, sediment-hosted Cu, 50+ known deposits |

**Deliverable:** Environment ready, data downloaded, zone selected.
**Metric:** Can load and visualize a Sentinel-2 image of Chuquicamata? Yes/No.

---

## Sprint 1 — First Mineral Index Maps (Weeks 2-3)

### Steps
1. Download Sentinel-2 L2A for Chuquicamata (cloud <10%, recent)
2. Calculate mineral indices:
   - Iron Oxide = B4/B2
   - Clay/Hydroxyl = B11/B12
   - Ferrous Iron = B11/B8A
   - Laterite = B4/B3
   - NDVI = (B8-B4)/(B8+B4) for vegetation mask
3. Visualize as heatmaps
4. Overlay MRDS deposit locations
5. **Measure:** Are indices higher at known deposits?

**Deliverable:** 5+ mineral index GeoTIFF maps + quicklook PNGs.
**Metric:** Visual correlation between high indices and known deposits.
**Risk:** Indices may be noisy in areas with desert varnish. Plan B: try different band ratios.

---

## Sprint 2 — First ML Classifier (Weeks 4-6)

### Steps
1. Create training set:
   - Positives: pixels within 500m of MRDS deposits
   - Negatives: pixels >5km from any deposit
   - Features: all indices + raw bands + DEM + slope
2. Train/test split: 70/30 geographically stratified
3. Train Random Forest baseline
4. Train XGBoost comparison
5. **Measure:** AUC-ROC, precision, recall
6. **Analyze errors:** What are the false positives? What deposits are missed?

**Deliverable:** Trained model + probability map + error analysis.
**Metric:** AUC > 0.65.
**Risk:** AUC < 0.55 → the indices alone aren't enough. Plan B: add more features in Sprint 3.

---

## Sprint 3 — Multi-Sensor Fusion (Weeks 7-10)

### Additional Data Layers
| Source | Features | Expected Impact |
|--------|----------|----------------|
| Sentinel-1 SAR | VV, VH, VV/VH ratio, GLCM texture | Surface roughness |
| DEM derivatives | Slope, aspect, curvature, TWI, lineaments | Structural context |
| Landsat 8/9 TIRS | Surface temperature, thermal inertia proxy | Rock density |
| EMIT (if available) | Mineral classification via spectral matching | Direct minerals |

### Measurement
For each layer added: **does AUC improve?** By how much?

**Deliverable:** Multi-sensor model + layer-by-layer comparison table.
**Metric:** AUC > 0.72.
**Risk:** Some layers may not improve AUC. Drop them — don't add complexity without improvement.

---

## Sprint 4 — Vegetation as Sensor (Weeks 11-14)

### Steps
1. Download 3-5 year Sentinel-2 time series
2. Calculate monthly NDVI per pixel
3. Extract phenology: green-up date, peak, senescence, duration
4. Calculate red-edge stress indices (B5, B6, B7)
5. Find anomalous pixels: vegetation behaves differently from surroundings
6. **Measure:** Do anomalies coincide with known deposits?

**Deliverable:** Geobotanical anomaly map + impact assessment.
**Metric:** Does vegetation add >2% AUC improvement?
**Risk:** In arid zones there may be no vegetation. This sprint is most useful for the Zambia pilot.

---

## Sprint 5 — Transfer Learning (Weeks 15-18)

### Steps
1. Apply Chuquicamata model to Pilbara (no retraining) → AUC?
2. Fine-tune with 50 local positive examples → AUC improvement?
3. Train from scratch on Pilbara → compare
4. Analyze: which features transfer, which don't?

**Deliverable:** Transferability evaluation + adapted model.
**Metric:** AUC > 0.60 without retraining, > 0.68 with fine-tune.
**Risk:** Transfer fails completely → geology too different. Plan B: train per-region models.

---

## Sprint 6 — Materials Engine Integration (Weeks 19-22)

### Steps
1. Get spectral signatures from USGS library for key minerals
2. Resample to Sentinel-2 and EMIT bands
3. Implement reverse geological search:
   - "Search for lithium" → spodumene, lepidolite spectral signatures
   - Match against satellite imagery
4. Prototype blockchain proof-of-discovery (Capsule transaction)

**Deliverable:** Working reverse geological search prototype.
**Metric:** Detects 3/5 known deposits for target minerals.

---

## Sprint 7 — First Sellable Report (Weeks 23-26)

### Steps
1. Choose a real area of mining interest (not training data)
2. Run full pipeline
3. Generate professional PDF report:
   - Probability map with confidence layers
   - Evidence breakdown per zone
   - Ranked target list with recommendations
4. Price: $1,000-5,000 (vs $50K+ traditional exploration)

**Deliverable:** Professional geological screening report.
**Metric:** A geologist considers it useful (seek feedback).

---

## Progress Tracking Table

| Sprint | AUC | Precision | Recall | FP/km² | Layers | Key Lesson |
|--------|-----|-----------|--------|--------|--------|------------|
| 2 | — | — | — | — | S2 indices | — |
| 3 | — | — | — | — | +SAR+DEM+thermal | — |
| 4 | — | — | — | — | +vegetation | — |
| 5 | — | — | — | — | transfer test | — |

---

## Risks Per Sprint

| Sprint | Main Risk | Detection | Plan B |
|--------|----------|-----------|--------|
| 0 | GEE account denied | Can't authenticate | Use Copernicus direct download |
| 1 | Indices too noisy | No visual correlation | Try PCA on all bands |
| 2 | AUC < 0.55 | Test set metric | Add more features (Sprint 3) |
| 3 | Layers don't help | AUC doesn't improve | Drop unhelpful layers |
| 4 | No vegetation in zone | Empty NDVI | Switch to Zambia pilot |
| 5 | Transfer fails | AUC < 0.55 | Per-region models |
| 6 | Spectral matching poor | Low precision | Use compositional matching instead |
| 7 | Report not credible | Geologist feedback | Improve with expert input |

---

## Actual Results (Updated March 2026)

| Sprint | Zone | AUC | Deposits | Bands | Key Lesson |
|--------|------|-----|----------|-------|------------|
| Phase 1 | Chuquicamata | 0.87 (naive) | 152 | 5 | First pilot works |
| Phase 2 | Chuquicamata | 0.99 (naive) | 152 | 19 | Multi-source helps |
| Phase 3 | Chuquicamata | 0.68 (honest) | 152 | 19 | Spatial CV reveals real AUC |
| Phase 3B | Chuquicamata | **0.86** | 43 curated | 24 | Clean labels > more sensors |
| Phase 4B | Kalgoorlie | 0.58 | 16 MRDS | 14 | Label-limited |
| Phase 4C | Kalgoorlie | 0.72 | 205 OZMIN | 12 | OZMIN breakthrough |
| Phase 4D | Kalgoorlie | **0.77** | 205 OZMIN | 12 | Full valid stack |
| Phase 4E | Zambia | 0.61 | 11 MRDS | 16 | Transfer fails cross-type |
| Phase 4F | Zambia | **0.76** | 28 enriched | 16 | Wider AOI + more labels |

### Key Findings
- **Labels dominate**: Kalgoorlie went from 0.58 (16 labels) to 0.77 (205 labels) — same satellite data
- **OZMIN solved Australia**: 16,225 deposits via free WFS API (CC-BY 4.0)
- **Transfer requires deposit type matching**: Porphyry Cu ≠ Sediment-hosted Cu (AUC drops to random)
- **AOI scanner works globally**: Tintic, Utah scanned with zero training data (heuristic mode)

### Phase 5A: Deposit Type Discovery

| Sprint | Zone | Type | AUC | Labels | Key Lesson |
|--------|------|------|-----|--------|------------|
| Phase 5A | Chuquicamata | Porphyry Cu | **0.86** | 43 | Already type-pure |
| Phase 5A | Kalgoorlie | Orogenic Au | **0.80** | 103 Au-only | +0.04 vs mixed (0.77) |
| Phase 5A | Zambia | Sediment-hosted Cu | 0.76 | 28 | Type matters most |

**The Primary Learning Axis**: Deposit type > commodity > geography.
Training on pure types sharpens the model. Mixing types confuses it.
5,467 labels classified globally, 467 with trainable type confidence.

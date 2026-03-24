# Subsurface-Proxy Detection — Experiment Lines V3

**Date:** 2026-03-24
**Status:** Research design — 10 ideas evaluated, 3 experiments designed, 1 executed
**Previous:** SUBSURFACE_DETECTION_THEORY_V2.md (10 minerals × novel pathways)

---

## Context

V2 cataloged physical pathways for 10 mineral types. V3 moves from theory to testable experiments using free data already available in GeaSpirit.

**Framing:** All methods below are **subsurface probability proxies** — statistical inferences from surface observables, not direct subsurface imaging. No method here can confirm what is underground. Each method can only shift the probability that mineralization exists below.

---

## 10 Ideas Evaluated

### Idea 1: Cross-Correlation Temporal (NDVI ↔ Thermal)

**Concept:** The temporal lag or correlation strength between vegetation response (NDVI) and surface temperature may differ over mineralized ground. Altered soil chemistry or different moisture retention could cause vegetation to respond differently to seasonal temperature changes.

**Physical basis:** Moderate. Geobotanical anomalies are documented in literature. However, the effect requires vegetation to exist (fails in pure desert) and the temporal signal requires multi-year time series.

**Datasets:** Sentinel-2 NDVI time series (GEE), Landsat thermal time series (already built for Thermal V2).

**Difficulty:** Medium. Requires aligning two time series at pixel level and computing cross-correlation per pixel.

**Risk of false signal:** Medium. Agricultural patterns, land-use change, and seasonal water table variations can produce similar signatures without any mineralization.

**Status:** **SPECULATIVE** — physically plausible in vegetated zones but very noisy. Not testable at Kalgoorlie (arid, minimal vegetation).

---

### Idea 2: Spatial Gradients / Edge Operators as Geology Proxies

**Concept:** Apply Sobel, Laplacian, or other edge detection operators to multispectral and DEM layers. Geological contacts (lithological boundaries, fault traces) produce spatial discontinuities. Deposits cluster near certain contact types.

**Physical basis:** Strong. Geological mapping fundamentally relies on identifying contacts and structures. Edge detection is a well-established technique in remote sensing geology.

**Datasets:** Satellite stack (spectral indices), DEM, geomorphology layers — all already available.

**Difficulty:** Low. Standard image processing.

**Risk of false signal:** Low-medium. Edges are everywhere; the question is which edges correlate with mineralization. Requires careful feature engineering to avoid noise.

**Status:** **VIABLE** — straightforward to implement and test. Good candidate for Experiment C.

---

### Idea 3: Multi-Temporal InSAR Coherence

**Concept:** InSAR coherence measures how stable the radar backscatter phase is between two passes. Low coherence over time can indicate ground deformation, surface instability, or different surface composition. Mineralized zones may show anomalous coherence patterns due to altered surface properties.

**Physical basis:** Weak-to-moderate. InSAR coherence is dominated by vegetation change, moisture, and atmospheric effects. The geological signal is typically small relative to these noise sources.

**Datasets:** Sentinel-1 SLC pairs via ASF DAAC (free, but processing is complex). Currently only SAR amplitude is in the GeaSpirit stack.

**Difficulty:** High. Requires InSAR processing (coregistration, interferogram formation, coherence estimation). Not a simple feature extraction.

**Risk of false signal:** High. Decorrelation from vegetation and atmospheric noise is much larger than any geological signal.

**Status:** **SPECULATIVE** — interesting research direction but too complex for current pipeline and high noise-to-signal ratio.

---

### Idea 4: Soil Moisture Anomaly Persistence

**Concept:** Altered rock above mineralized zones may have different permeability and water retention. Long-term soil moisture maps (from SMAP, SMOS, or SAR-derived) could reveal persistent anomalies that correlate with altered ground.

**Physical basis:** Moderate. Alteration haloes do change permeability. However, free soil moisture products have 10-40 km resolution — far too coarse for deposit-scale analysis.

**Datasets:** SMAP (36 km), SMOS (40 km), SAR-derived (can be 100m but requires processing). Sentinel-1 backscatter already in stack could serve as crude moisture proxy.

**Difficulty:** Medium (if using SAR backscatter as proxy) to High (if processing raw SMAP/SMOS).

**Risk of false signal:** High at coarse resolution. Low resolution mixes mineralized pixels with everything else.

**Status:** **INVIABLE** at current resolution. Could become viable if SAR-derived soil moisture at 100m becomes a standard product.

---

### Idea 5: Photovoltaic / Self-Potential Speculative Route

**Concept:** Sulphide ore bodies generate natural electrical currents (self-potential) due to electrochemical reactions at the water table. Could this affect surface properties detectable by satellite?

**Physical basis:** Physically real (self-potential is a standard geophysical method), but the effect on surface properties detectable from orbit is essentially zero. Self-potential anomalies are millivolts measured at ground level.

**Datasets:** None available from satellite. This is a ground-based geophysical method.

**Difficulty:** N/A — not remotely sensible from satellite.

**Risk of false signal:** N/A.

**Status:** **INVIABLE** — cannot be detected from satellite. Include only ground-based if airborne/ground data becomes available.

---

### Idea 6: Night-Time Cooling / Diurnal Thermal Difference

**Concept:** The day-night temperature difference (diurnal thermal range) is controlled by thermal inertia, which depends on rock density, porosity, and moisture. Mineralized zones with different rock properties could show anomalous diurnal signatures.

**Physical basis:** Strong. Thermal inertia is well-established in planetary geology. The Thermal V2 experiment already detected thermal range anomalies at deposits.

**Datasets:** Landsat thermal (day only — no night passes). MODIS has day/night but at 1km resolution. ECOSTRESS on ISS has ~70m but limited coverage.

**Difficulty:** Medium. The 20-year thermal amplitude from Thermal V2 is already a proxy for this. A true diurnal measurement would need MODIS (too coarse) or ECOSTRESS (limited coverage).

**Risk of false signal:** Low-medium. The signal is physically real but Thermal V2 already captures most of it.

**Status:** **VIABLE but partially redundant** — Thermal V2 amplitude is already a diurnal proxy. True diurnal from ECOSTRESS could add precision but coverage is limited.

---

### Idea 7: Multiscale Texture over SAR/DEM/S2

**Concept:** Compute texture features (GLCM: contrast, correlation, entropy, homogeneity) at multiple scales on SAR, DEM, and optical data. Different geological units produce different texture signatures. Mineralized zones may show distinct textural anomalies.

**Physical basis:** Strong. Texture analysis is standard in geological remote sensing. Different rock types produce different surface roughness at different scales.

**Datasets:** Sentinel-1 SAR, DEM, Sentinel-2 optical — all available.

**Difficulty:** Medium. GLCM computation is well-understood but computationally intensive at multiple scales.

**Risk of false signal:** Medium. Texture varies for many reasons (vegetation, land use, weathering). Need to control for these.

**Status:** **VIABLE** — good candidate for systematic feature expansion. Could be combined with edge operators (Idea 2).

---

### Idea 8: SAR Polarimetric Decomposition Proxies

**Concept:** Decompose dual-pol SAR (Sentinel-1 VV/VH) into scattering components. Different surface types produce different polarimetric signatures. Could mineralized zones show anomalous scattering?

**Physical basis:** Moderate. Full-pol decompositions (Cloude-Pottier, Freeman-Durden) are powerful but require quad-pol data. Sentinel-1 is dual-pol only (VV/VH), limiting decomposition options.

**Datasets:** Sentinel-1 VV/VH already in stack for some AOIs. Chuquicamata has 5 SAR bands.

**Difficulty:** Low-medium. VV/VH ratio and cross-pol ratio are simple to compute. Full decomposition not possible with dual-pol.

**Risk of false signal:** Medium. The VV/VH ratio is already somewhat captured in the existing stack.

**Status:** **VIABLE but limited** — Sentinel-1 dual-pol constrains what decompositions are possible. Simple ratios may already be in the stack.

---

### Idea 9: Passive Microwave Residual Downscaling

**Concept:** Downscale coarse passive microwave observations (AMSR2, SMAP) using high-resolution covariates (DEM, SAR, optical). The residual between predicted and observed microwave emission could contain geological information.

**Physical basis:** Weak. Passive microwave at 10-40 km resolution is dominated by soil moisture and vegetation water content. Any geological signal is orders of magnitude smaller.

**Datasets:** AMSR2 (25 km), SMAP (36 km) — free but extremely coarse.

**Difficulty:** High. Downscaling from 25km to 30m is a 800× factor. The statistical relationship breaks down at such ratios.

**Risk of false signal:** Very high. Downscaling artifacts would dominate any real signal.

**Status:** **INVIABLE** — resolution mismatch is too extreme for deposit-scale analysis.

---

### Idea 10: ML Residual Maps as Subsurface-Proxy Signal

**Concept:** Train a model to predict one surface observable (e.g., thermal_range_ratio) from other surface covariates (DEM, slope, geomorphology, spectral indices). The residual — what the model cannot explain from surface topography alone — may concentrate geological signal, including subsurface-related effects.

**Physical basis:** Strong. This is a form of geological anomaly detection. Surface variables like thermal behavior are influenced by both surface processes (topography, aspect, vegetation) and geological processes (rock type, alteration, mineralization). By modeling the surface contribution and subtracting it, the residual enriches the geological component.

**Datasets:** All existing layers — no new data needed.

**Difficulty:** Low-medium. Standard regression + residual computation.

**Risk of false signal:** Low-medium. The residual captures ANYTHING not explained by the covariates, not just geology. Need to test whether it correlates with deposits specifically.

**Status:** **VIABLE — highest priority** — operationally simple, uses existing data, physically sound, and directly testable.

---

## Summary Table

| # | Idea | Physical Basis | Difficulty | False Signal Risk | Status |
|---|------|---------------|-----------|-------------------|--------|
| 1 | NDVI ↔ thermal cross-correlation | Moderate | Medium | Medium | SPECULATIVE |
| 2 | Spatial gradients / edge operators | Strong | Low | Low-medium | **VIABLE** |
| 3 | Multi-temporal InSAR coherence | Weak-moderate | High | High | SPECULATIVE |
| 4 | Soil moisture anomaly persistence | Moderate | High | High | INVIABLE (resolution) |
| 5 | Photovoltaic / self-potential | Real but undetectable | N/A | N/A | INVIABLE |
| 6 | Night-time cooling / diurnal thermal | Strong | Medium | Low-medium | VIABLE (partially redundant) |
| 7 | Multiscale texture (SAR/DEM/S2) | Strong | Medium | Medium | **VIABLE** |
| 8 | SAR polarimetric decomposition | Moderate | Low-medium | Medium | VIABLE (limited) |
| 9 | Passive microwave downscaling | Weak | High | Very high | INVIABLE |
| 10 | ML residual maps | Strong | Low-medium | Low-medium | **VIABLE — PRIORITY** |

---

## 3 Experiments Designed

### Experiment A: Cross-Correlation Temporal (NDVI ↔ Thermal)

**Hypothesis (falsifiable):** The Pearson correlation between monthly NDVI and monthly surface temperature time series is significantly different (p < 0.05) at deposit locations compared to geology-matched background.

**AOI:** Zambia Copperbelt (vegetated — required for NDVI signal) or Kalgoorlie if any NDVI variability exists.

**Datasets:** Landsat thermal monthly composites (existing), Sentinel-2 NDVI monthly composites (GEE).

**Scripts required:**
- `build_ndvi_thermal_crosscorrelation.py`
- `analyze_crosscorrelation_experiment.py`

**Criterion of success:** Cohen's d > 0.3, p < 0.05 for cross-correlation metric at deposits vs geology-matched background.

**Criterion of failure:** d < 0.2 or p > 0.10 — no useful cross-temporal signal.

---

### Experiment B: ML Residuals (PRIORITY — EXECUTED)

**Hypothesis (falsifiable):** The residual of a gradient boosting model that predicts thermal_range_ratio from surface topographic covariates (elevation, slope, TPI, ruggedness, curvature, relative_elevation) differs significantly between deposit and background pixels.

**AOI:** Kalgoorlie (best-characterized, most labels, thermal V2 available).

**Datasets:** All existing (satellite stack 12 bands, thermal v2 14 bands, geomorph 6 bands, labels, geology-matched background).

**Scripts required:**
- `run_residual_proxy_experiment.py`

**Criterion of success:**
1. Residual differs at deposits (Cohen's d > 0.3, p < 0.05 vs geology-matched BG)
2. Adding residual to baseline improves AUC by >= +0.005

**Criterion of failure:**
1. d < 0.2 or p > 0.10 — residual does not concentrate geological signal
2. No AUC improvement — residual is noise, not signal

**Why this is the priority:** Uses only existing data, no new downloads needed, directly testable, physically sound, and the result (positive or negative) is immediately informative.

---

### Experiment C: Spatial Gradient Geology Proxies

**Hypothesis (falsifiable):** Edge magnitude (Sobel) and second-derivative (Laplacian) features computed on spectral index and DEM layers show significantly different statistics at deposit locations vs geology-matched background. Deposits cluster near geological contacts detectable as spatial discontinuities.

**AOI:** Kalgoorlie or Chuquicamata.

**Datasets:** Satellite stack (spectral indices + DEM), all existing.

**Scripts required:**
- `build_spatial_gradient_features.py`
- `analyze_gradient_experiment.py`
- `train_gradient_fusion_experiment.py`

**Criterion of success:** At least 2 gradient features with d > 0.3, p < 0.05.

**Criterion of failure:** No gradient feature shows significant difference — geology contacts are not detectable at pixel resolution or do not correlate with deposits.

---

## Experiment B Results (ML Residuals) — EXECUTED

**AOI:** Kalgoorlie (205 deposits, 1630 geology-matched background points)

**Surface model:** GradientBoostingRegressor predicting thermal_range_ratio from 11 surface covariates (elevation, slope, TPI, ruggedness, NDVI, curvature, TRI, multi-scale TPI, relative_elevation).

**Surface model performance:**
- R² = 0.517 — surface covariates explain ~52% of thermal_range_ratio variance
- Top features: elevation (39.6%), NDVI (38.2%), ruggedness (7.9%)
- 48.3% of variance remains unexplained (the "residual signal space")

**Residual statistical test (deposits vs geology-matched background):**
- Mann-Whitney U: p = 0.138 (**not significant** at α=0.05)
- Cohen's d = -0.250 (small negative effect — deposits slightly lower residual)
- Bootstrap 95% CI for median difference: [-0.009, +0.004] — **includes zero**
- KS test: p = 0.011 (suggests some distributional difference, but weak)

**Predictive value:**
| Model | AUC-ROC | Delta |
|-------|---------|-------|
| A: Baseline satellite | 0.740 | — |
| B: Baseline + residual | 0.724 | -0.016 |
| C: Residual only | 0.298 | -0.442 |
| D: Baseline + thermal_range_ratio | 0.714 | -0.026 |
| E: Baseline + thermal + residual | 0.721 | -0.019 |

**Verdict: NEGATIVE**

The residual of a surface-explanatory model does NOT concentrate useful geological signal for deposit prediction at Kalgoorlie. Key findings:

1. The thermal signal at deposits (detected in Thermal V2) appears to be substantially explained by surface covariates (elevation + NDVI explain ~52% of thermal variance).
2. The residual does not differ significantly between deposits and geology-matched background (p = 0.14).
3. Adding the residual to the baseline model does not improve AUC — it actually decreases slightly.
4. The residual alone has near-random AUC (0.30), confirming no independent predictive value.

**Interpretation:** This does NOT invalidate the thermal proxy signal detected in Thermal V2. It means that after controlling for surface topography, the remaining thermal variance does not add further deposit-discriminating power beyond what the baseline already captures. The thermal signal that DOES help (from V2) operates through the same surface features (elevation, NDVI patterns) that the geology-matched background already partially controls for.

**Next steps:**
- Experiment C (spatial gradients) is the next testable idea
- The residual approach may work better at AOIs where surface covariates explain less of the thermal variance
- Consider testing with different target variables (not just thermal_range_ratio)

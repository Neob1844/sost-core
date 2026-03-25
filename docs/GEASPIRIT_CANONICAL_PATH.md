# GeaSpirit — Path to the Canonical Objective

**Canonical objective:** "Hay [MINERAL] a [PROFUNDIDAD] en [COORDENADAS] con certeza del [X%]"

**Current score: 18/40 (45%)**

| Dimension | Score | Gap | What it means |
|-----------|-------|-----|--------------|
| MINERAL | 2/10 | -8 | Cannot distinguish Au from Ni (AUC 0.50 = random) |
| DEPTH | 3/10 | -7 | Magnetic Euler proxy gives median 6m — too shallow, no deposit/background difference |
| COORDINATES | 7/10 | -3 | 30m resolution, ~1km² zone identification |
| CERTAINTY | 6/10 | -4 | AUC 0.869, Brier 0.161, calibration error 0.121 |

---

## The Honest Truth

### What satellites CAN do (and we do well)
- **Detect WHERE deposits are likely** — AUC 0.87-0.94 across 5 zones
- **Identify geological domains** — greenstone belts, porphyry districts, sedimentary basins
- **Measure surface alteration** — iron oxide, clay/hydroxyl, laterite, NDVI stress
- **Characterize terrain structure** — TPI heterogeneity d=+0.878 (strongest feature)
- **Track long-term thermal anomalies** — 20-year thermal proxy, d=-0.627

### What satellites CANNOT do (fundamental limits)
- **Distinguish mineral type within the same geological province** — Au vs Ni both live in Kalgoorlie greenstones. Surface pixels differ by GEOGRAPHY, not MINERALOGY. Spatial block CV correctly penalizes this.
- **Determine depth** — All surface signals attenuate exponentially with depth. A deposit at 50m and one at 500m look identical from orbit.
- **Provide geological certainty >85%** — Surface proxies have irreducible noise from vegetation, soil cover, weathering, and atmospheric effects.

### Why AUC 0.94 doesn't mean 94% certainty
AUC measures DISCRIMINATION (ranking deposits higher than background). It does NOT measure CALIBRATION (predicted probability matching actual probability). Our Brier score of 0.161 and calibration error of 0.121 show significant miscalibration. When the model says "80% probability", the actual fraction of deposits is ~55%.

---

## The Gap Analysis

### MINERAL Identification (needs +8 points)

**Why it fails:** Au and Ni deposits in Kalgoorlie are spatially intermixed in the same greenstone belts. They can be 500m apart. The surface proxy difference between them (NDVI d=-0.978, ferrous_iron d=+0.698) is a GEOGRAPHIC signal, not a MINERALOGICAL signal. Spatial block CV correctly identifies that these don't generalize.

**What would fix it:**
1. **Geological lithology map as feature** — encoding "greenstone" vs "komatiite" vs "granite" directly encodes the geological control. But this requires existing geological mapping, not discovery from data.
2. **EMIT with mineral-specific bands** — Au alteration (sericite, carbonate, silica) has different SWIR signatures than Ni alteration (serpentinite, magnetite). EMIT's 285 bands at 5nm resolution could theoretically distinguish them. But EMIT at Kalgoorlie was NEGATIVE (orogenic Au doesn't have strong clay/hydroxyl signal).
3. **High-resolution radiometrics** — the national 80m K/Th/U grid showed weak Au-Ni differences (K/U d=+0.265). A detailed survey at 200m line spacing might resolve deposit-scale signatures.
4. **Drill hole guided labeling** — GSWA WAMEX has drill hole data that records WHAT was found. Integrating actual mineral occurrence (not just deposit presence) would enable multi-class training.

**Honest assessment:** With current satellite data alone, mineral-type identification within a single geological province is NOT solvable. We need geological context or hyperspectral alteration mapping.

### DEPTH Estimation (needs +7 points)

**Why it fails:** The simplified Euler depth from TMI gives median 6m for everything. The national TMI grid (80m) doesn't resolve individual deposit-scale magnetic anomalies. The depth proxy reflects regional magnetic basement depth, not individual deposits.

**What would fix it:**
1. **Detailed aeromagnetic survey** (P1261, 100m line spacing) — resolves individual anomaly shapes for proper Euler deconvolution. Would give meaningful depth estimates for magnetic deposits (Ni sulfides, magnetite-bearing iron ore).
2. **AEM conductivity depth slices** — directly images subsurface conductivity at 50m, 100m, 200m, 500m. The most direct depth proxy available from free data. AusAEM (national, 20km lines) is too coarse. Need GA targeted surveys or GSWA detailed surveys.
3. **Drill hole depth calibration** — train a regression: surface features → depth to ore. Requires WAMEX drill data with depth/assay results. This is the GOLD STANDARD for depth estimation.
4. **Gravity gradient analysis** — the SPATIAL SHAPE of the Bouguer anomaly encodes depth. Broad anomaly = deep source, narrow anomaly = shallow source. GA national gravity (250m grid) might be sufficient for this.

**Honest assessment:** Without AEM or drill holes, we cannot estimate depth reliably. The magnetic depth proxy is too noisy at the resolution available. Getting to 7+/10 on depth requires integrating subsurface geophysics data.

### CERTAINTY Improvement (needs +4 points)

**What would fix it:**
1. **Isotonic calibration** — post-hoc calibration of probabilities. Simple, requires only existing predictions + labels.
2. **More labeled data** — 205 labels at Kalgoorlie is good but not great. MINDAT API (400K+ mineral localities) could enrich labels.
3. **Multi-model ensemble** — average predictions from GBM, RF, SVM, logistic regression. Ensemble uncertainty provides calibrated confidence intervals.
4. **Bayesian approach** — replace frequentist ML with Bayesian posterior. Provides principled uncertainty quantification.

**Honest assessment:** Getting to 8+/10 on certainty is achievable with better calibration and ensemble methods. This is a pure ML improvement.

---

## Is 10/10 Plausible?

### With satellite data only: MAX ~22/40 (55%)
- MINERAL: 3/10 (geological context features, not true identification)
- DEPTH: 2/10 (thermal inertia correlation at best)
- COORDINATES: 8/10 (peak finding on probability surface)
- CERTAINTY: 9/10 (isotonic calibration + ensemble)

### With satellite + free airborne geophysics: MAX ~30/40 (75%)
- MINERAL: 5/10 (detailed radiometrics K/Th/U + geology maps)
- DEPTH: 6/10 (magnetic Euler + gravity shape + AEM if available)
- COORDINATES: 9/10 (multi-sensor peak convergence)
- CERTAINTY: 10/10 (well-calibrated ensemble with many labels)

### With satellite + geophysics + drill holes: MAX ~36/40 (90%)
- MINERAL: 8/10 (drill-verified mineral + surface features = calibrated type prediction)
- DEPTH: 8/10 (drill-calibrated depth regression from surface+geophysics features)
- COORDINATES: 10/10 (drill-verified locations + surface prediction convergence)
- CERTAINTY: 10/10 (drill-validated, calibrated, ensembled)

### True 10/10 (40/40): Requires
- Drilling campaign ($100K+) at known+predicted locations for calibration
- AEM survey ($100K+) for direct subsurface imaging
- Detailed aeromagnetics ($50K+) for depth estimation
- This is a standard junior mining exploration budget ($250K-500K)

---

## The Strategy

**Phase 8 (immediate, $0):**
1. Download GA national gravity grid for Kalgoorlie → test gravity shape as depth proxy
2. Download GSWA geological map → encode lithology as feature → test mineral identification
3. Implement isotonic calibration + ensemble → improve certainty score
4. Integrate MINDAT API labels → enrich training data

**Phase 9 (next, $0):**
5. Download P1261 detailed aeromagnetics (if freely available via GADDS)
6. Build proper Euler deconvolution depth estimates
7. ECOSTRESS thermal inertia for diurnal thermal → depth proxy
8. Temporal DNA transformer prototype

**Phase 10 (if funded):**
9. AEM survey or access to existing AEM depth slices
10. WAMEX drill hole data integration → depth calibration
11. Multi-class mineral prediction system

---

## Key Insight

The canonical objective is not a software problem — it's a DATA problem.

We have built the best possible surface screening system from free satellite data (AUC 0.94). But the gap to 10/10 cannot be closed from orbit alone. Each additional data layer (geophysics, geology maps, drill holes) adds a dimension of information that satellites cannot provide:

- **Geology maps** add mineral-type context
- **Magnetics/gravity** add structural depth context
- **AEM** adds direct subsurface conductivity
- **Drill holes** add ground truth calibration

The path to 10/10 is not "better ML" — it's "more data sources, properly integrated."

GeaSpirit's role evolves from "satellite-only prospectivity" to "multi-source exploration intelligence platform" — integrating every available free data source into a unified prediction system.

The 40-year Landsat archive remains the foundation. But the building needs more floors.

# Passive Earth Signal Hypotheses — V1

Date: 2026-03-29
Classification: Frontier Research — NOT production

## Purpose

Translate intuitive concepts like "listening to the Earth", "subsurface response", "terrain memory" into physically testable hypotheses or explicitly classify them as NON_TESTABLE_AT_THIS_MOMENT.

---

## A) PHYSICALLY_PLAUSIBLE

### 1. Passive Magnetotelluric Response

- **Physical basis:** Natural EM fields (lightning, solar wind) induce telluric currents. Conductivity contrasts from ore bodies alter response.
- **Dataset candidates:** MT surveys (government), INTERMAGNET stations, proxy via satellite magnetics
- **Access:** BLOCKED_BY_ACCESS (MT data requires field instruments or restricted government surveys)
- **Canonical dimension:** DEPTH (conductivity profiles), MINERAL (sulfide detection)
- **Risk of smoke:** LOW — well-established geophysics
- **Recommended action:** Identify any open MT datasets near validated zones

---

### 2. Ambient Seismic Noise (H/V Spectral Ratio)

- **Physical basis:** Microtremors from ocean waves/wind interact with subsurface structure. H/V ratio reveals impedance contrasts.
- **Dataset candidates:** IRIS seismic network, passive seismic arrays
- **Access:** BLOCKED_BY_ACCESS (requires seismometer deployment or nearby station data)
- **Canonical dimension:** DEPTH (layer boundaries)
- **Risk of smoke:** LOW — standard passive seismic method
- **Recommended action:** Check IRIS station coverage near Kalgoorlie/Chuquicamata

---

### 3. Electrical Conductivity Anomalies (Proxy)

- **Physical basis:** Sulfide mineralization increases bulk conductivity. Alteration zones change resistivity.
- **Dataset candidates:** AEM surveys (government), ZTEM surveys, proxy from soil moisture
- **Access:** BLOCKED_BY_PORTAL (AEM from GA/GSWA requires manual download)
- **Canonical dimension:** MINERAL, DEPTH
- **Risk of smoke:** LOW — direct physical link to mineralization
- **Recommended action:** Monitor GA/GSWA for open AEM releases

---

### 4. Nocturnal Thermal Micro-Variation

- **Physical basis:** Different rock types cool at different rates (thermal inertia). Ore bodies with metallic minerals have higher thermal conductivity, leading to faster heat dissipation.
- **Dataset candidates:** Landsat thermal (Band 10), ECOSTRESS, ASTER TIR
- **Access:** GEE (Landsat), PARTIALLY_ACCESSIBLE (ECOSTRESS)
- **Canonical dimension:** MINERAL (thermal inertia proxy)
- **Risk of smoke:** MEDIUM — signal is subtle, may be dominated by surface cover
- **Recommended action:** Build day-night thermal difference features from Landsat pairs
- **Status:** PARTIALLY_TESTED (Phase 5 thermal 20yr validated as selective)

---

### 5. Post-Rain Hydrological Response (Differential Drying)

- **Physical basis:** Altered/mineralized rock has different porosity and permeability, causing it to dry faster or slower after rain.
- **Dataset candidates:** Sentinel-2 time series (pre/post rain), soil moisture (SMAP), precipitation (GPM)
- **Access:** GEE (S2, SMAP, GPM all available)
- **Canonical dimension:** MINERAL (alteration detection)
- **Risk of smoke:** MEDIUM — requires cloud-free imagery at right times
- **Recommended action:** Build differential reflectance feature (post-rain minus pre-rain) at pilot zone

---

### 6. Gravity Gradient Anomalies

- **Physical basis:** Dense ore bodies produce measurable gravity anomalies. Bouguer anomaly maps reveal subsurface mass distribution.
- **Dataset candidates:** GA gravity grid, WGM2012, GOCE satellite gravity
- **Access:** BLOCKED_BY_PORTAL (GA GADDS), WGM2012 available but coarse (regional-only)
- **Canonical dimension:** DEPTH, MINERAL
- **Risk of smoke:** LOW — standard exploration geophysics
- **Recommended action:** Test WGM2012 as regional proxy (coarse but free)

---

### 7. SAR Coherence / Slow Deformation (InSAR)

- **Physical basis:** Subsidence, uplift, or ground movement from mining/geological processes. Coherence loss may indicate surface instability or altered ground.
- **Dataset candidates:** Sentinel-1 SAR (GEE), ALOS-2 PALSAR
- **Access:** GEE (Sentinel-1 available)
- **Canonical dimension:** COORDINATES (structural mapping)
- **Risk of smoke:** MEDIUM — signal may not relate to mineralization directly
- **Recommended action:** Build SAR coherence features at pilot zone

---

### 8. Natural EM Signals of the Earth (Schumann Resonances)

- **Physical basis:** Earth's EM cavity resonates at ~7.83 Hz and harmonics. Local conductivity variations theoretically modulate these signals.
- **Dataset candidates:** INTERMAGNET magnetometers, specialized receivers
- **Access:** BLOCKED_BY_ACCESS (requires specialized instruments)
- **Canonical dimension:** DEPTH (deep conductivity)
- **Risk of smoke:** HIGH — signal is extremely weak and global, local modulation unproven for exploration
- **Recommended action:** Literature review only. Do not attempt testing.

---

## B) SPECULATIVE_BUT_TESTABLE

### 9. EM-Mineral Target Correlation

- **Inspiration:** Natural EM signals might correlate with mineral targets
- **Physical translation:** Time-varying magnetic field measurements near known deposits show anomalous spectral content vs background
- **Access:** BLOCKED_BY_ACCESS (requires local magnetometer data)
- **Risk of smoke:** HIGH
- **Recommended action:** Literature search for published MT-mineralization correlation studies

---

### 10. Anomalous Thermal Persistence (Cooling Rate)

- **Inspiration:** "Some areas hold heat differently"
- **Physical translation:** Multi-temporal thermal imaging shows locations that cool slower or faster than surroundings after sunset
- **Access:** GEE (Landsat thermal pairs dawn/dusk), ECOSTRESS (PARTIALLY_ACCESSIBLE)
- **Risk of smoke:** MEDIUM
- **Recommended action:** Select one pilot zone, build cooling-rate anomaly from day/night Landsat thermal

---

### 11. Differential Seasonal Forcing Response

- **Inspiration:** "The ground responds differently to seasons"
- **Physical translation:** Amplitude and phase of seasonal vegetation/moisture cycles differ over mineralized ground
- **Access:** GEE (NDVI time series, LST time series)
- **Risk of smoke:** MEDIUM — seasonal signals are strong, mineralization signal may be buried
- **Recommended action:** Build seasonal amplitude/phase features from multi-year NDVI + LST

---

### 12. Under-Explored Multi-Sensor Passive Signatures

- **Inspiration:** Combined passive signals (thermal + SAR + spectral + temporal) might reveal patterns invisible to single sensors
- **Physical translation:** Feature stacking from multiple passive sources with ML classification
- **Access:** GEE (S2 + Landsat + S1 all available)
- **Risk of smoke:** MEDIUM — existing fusion results mixed (Phase 14, 27)
- **Recommended action:** Systematic multi-sensor passive-only fusion experiment at best zone

---

### 13. Differential Terrain Response to Rain/Drought/Heat Episodes

- **Inspiration:** "The land remembers extreme events"
- **Physical translation:** NDVI/moisture recovery rates after drought or extreme heat events differ over mineralized ground
- **Access:** GEE (NDVI, LST, precipitation time series)
- **Risk of smoke:** MEDIUM-HIGH
- **Recommended action:** Identify extreme weather events in historical record, compare recovery at deposit vs background

---

### 14. Local Time-Series Anomaly as "Resonance" Proxy

- **Inspiration:** "Resonance of the terrain"
- **Physical translation:** Spectral analysis of multi-year NDVI/thermal time series reveals anomalous periodicity or amplitude at mineralized sites
- **Access:** GEE (Landsat 30+ year archive)
- **Risk of smoke:** HIGH — many confounders (land use, irrigation, urbanization)
- **Recommended action:** Fourier analysis of NDVI time series at known deposits vs background

---

## C) NON_TESTABLE_AT_THIS_MOMENT

### 15. "Terrain Memory"

- **Inspiration:** The ground "remembers" past geological events
- **Why non-testable:** No physical sensor can measure geological "memory" — what is measurable are current physical properties (conductivity, density, magnetism) that result from past processes
- **What would make it testable:** Define a specific measurable proxy (e.g., "thermal inertia differences indicate lithological memory of intrusive events")
- **Status:** NON_TESTABLE_AT_THIS_MOMENT — but inspires thermal persistence and cooling-rate hypotheses (10, 13)

---

### 16. "Conscious Subsurface Response"

- **Inspiration:** The ground "responds" or "communicates"
- **Why non-testable:** No measurement protocol exists for subsurface "consciousness" or "intent"
- **Physical residue:** The useful part is that subsurface properties DO modulate surface observables — this is standard remote sensing
- **Status:** NON_TESTABLE_AT_THIS_MOMENT

---

### 17. Dowsing / Radiesthesia as Literal Mechanism

- **Inspiration:** Traditional practice of detecting subsurface features with rods/pendulums
- **Why non-testable:** No reproducible controlled experiment has demonstrated above-chance performance
- **Physical residue:** The operator's knowledge of terrain, vegetation patterns, and geological context IS valuable — but that is pattern recognition, not the claimed mechanism
- **Status:** NON_TESTABLE_AT_THIS_MOMENT
- **Note:** The value is in the operator's geological knowledge, not the claimed mechanism

---

### 18. "Earth Frequencies" as Mineral Detector

- **Inspiration:** Specific frequencies of the Earth could indicate minerals
- **Why non-testable:** While Schumann resonances exist, local modulation by mineral deposits has never been demonstrated at exploration scale
- **Status:** NON_TESTABLE_AT_THIS_MOMENT
- **What would change this:** A peer-reviewed study demonstrating local EM spectral anomalies correlated with known deposits

---

## Summary Table

| # | Hypothesis | Category | Testable Now | Data Access | Canonical Dim |
|---|---|---|---|---|---|
| 1 | Passive magnetotelluric | PHYSICALLY_PLAUSIBLE | NO | BLOCKED_BY_ACCESS | DEPTH, MINERAL |
| 2 | Ambient seismic noise | PHYSICALLY_PLAUSIBLE | NO | BLOCKED_BY_ACCESS | DEPTH |
| 3 | Conductivity anomalies | PHYSICALLY_PLAUSIBLE | NO | BLOCKED_BY_PORTAL | MINERAL, DEPTH |
| 4 | Nocturnal thermal micro-var | PHYSICALLY_PLAUSIBLE | YES | GEE | MINERAL |
| 5 | Post-rain differential drying | PHYSICALLY_PLAUSIBLE | YES | GEE | MINERAL |
| 6 | Gravity gradients | PHYSICALLY_PLAUSIBLE | PARTIAL | BLOCKED + WGM2012 | DEPTH, MINERAL |
| 7 | SAR coherence / InSAR | PHYSICALLY_PLAUSIBLE | YES | GEE | COORDINATES |
| 8 | Schumann resonances | PHYSICALLY_PLAUSIBLE | NO | BLOCKED_BY_ACCESS | DEPTH |
| 9 | EM-mineral correlation | SPECULATIVE_BUT_TESTABLE | NO | BLOCKED_BY_ACCESS | MINERAL |
| 10 | Thermal persistence | SPECULATIVE_BUT_TESTABLE | YES | GEE | MINERAL |
| 11 | Seasonal forcing response | SPECULATIVE_BUT_TESTABLE | YES | GEE | MINERAL |
| 12 | Multi-sensor passive fusion | SPECULATIVE_BUT_TESTABLE | YES | GEE | MINERAL |
| 13 | Drought/heat response | SPECULATIVE_BUT_TESTABLE | YES | GEE | MINERAL |
| 14 | Time-series "resonance" | SPECULATIVE_BUT_TESTABLE | YES | GEE | MINERAL |
| 15 | Terrain memory | NON_TESTABLE_AT_THIS_MOMENT | NO | N/A | — |
| 16 | Conscious response | NON_TESTABLE_AT_THIS_MOMENT | NO | N/A | — |
| 17 | Dowsing literal mechanism | NON_TESTABLE_AT_THIS_MOMENT | NO | N/A | — |
| 18 | Earth frequencies | NON_TESTABLE_AT_THIS_MOMENT | NO | N/A | — |

---

**Canonical score: 22.8/40 UNCHANGED. This is frontier research only.**

No hypothesis in this document has been validated in production. No hypothesis claims direct subsurface detection. All GEE-accessible hypotheses are candidates for controlled pilot experiments only — results must clear the +0.005 AUC threshold with LOW leakage before any canonical score change is considered.

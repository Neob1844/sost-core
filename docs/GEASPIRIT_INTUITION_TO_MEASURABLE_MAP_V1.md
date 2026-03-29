# Intuition-to-Measurable Translation Map — V1

Date: 2026-03-29
Classification: Frontier Research — NOT production

## Purpose

This document maps intuitive or phenomenological phrases — the kind an experienced operator might use in the field — to physical measurements that can be operationalised in a remote sensing pipeline.

The translation discipline is strict:
- The intuitive phrase is the SEED.
- The physical measurement is the SCIENCE.
- Only the measurement ever enters production.
- If no credible physical measurement exists, the phrase is classified NON_TESTABLE_AT_THIS_MOMENT.

---

## Translation Table

| Intuitive Phrase | Physical Translation | Measurable Proxy | Sensor / Source | Access | Category |
|---|---|---|---|---|---|
| "The Earth responds" | Surface properties are modulated by subsurface structure | Reflectance anomaly, thermal anomaly, conductivity contrast, magnetic anomaly | Satellite, airborne geophysics, ground surveys | Various (GEE to BLOCKED) | PHYSICALLY_PLAUSIBLE |
| "The subsurface emits a signal" | Natural EM fields, thermal radiation, and gravity field are modulated by subsurface properties | Magnetic field anomaly, thermal IR radiance, Bouguer gravity deviation | Magnetometers, thermal sensors, gravimeters | BLOCKED_BY_ACCESS to GEE | PHYSICALLY_PLAUSIBLE |
| "The terrain returns a resonance" | Impedance contrast modulates propagation of seismic and EM waves | H/V spectral ratio, MT apparent resistivity, spectral anomalies | Seismometers, MT receivers | BLOCKED_BY_ACCESS | PHYSICALLY_PLAUSIBLE |
| "An operator notices something in the area" | Pattern recognition of vegetation anomaly, colour, texture, drainage, or moisture | NDVI anomaly, spectral indices, terrain derivatives, drainage density | Sentinel-2, Landsat | GEE | PHYSICALLY_PLAUSIBLE |
| "The ground remembers" | Current physical properties reflect the geological history of the site | Thermal inertia, magnetic susceptibility, bulk density, porosity | Thermal sensors, magnetometers, gravimeters | GEE (thermal), BLOCKED (others) | SPECULATIVE_BUT_TESTABLE |
| "The land feels different here" | Anomalous surface properties — colour, roughness, moisture content — relative to surroundings | Multispectral anomaly index, SAR texture, DEM roughness derivative | Sentinel-2, Sentinel-1, SRTM | GEE | PHYSICALLY_PLAUSIBLE |
| "There is energy underground" | Geothermal gradient, radioactive decay heat, exothermic chemical reactions in ore bodies | Heat flow measurements, gamma-ray spectrometry, radon gas emanation | Ground heat flux surveys, airborne radiometrics | BLOCKED_BY_ACCESS | SPECULATIVE_BUT_TESTABLE |
| "Water behaves differently here" | Altered rock changes local groundwater flow paths and surface soil moisture distribution | Soil moisture anomaly (SMAP), spring and seep locations, drainage pattern asymmetry | SMAP, hydrological DEM analysis, GPM | GEE | PHYSICALLY_PLAUSIBLE |
| "The colours are wrong" | Alteration minerals (iron oxides, clays, gossans) produce diagnostic spectral signatures | Iron oxide ratio, clay index, hydroxyl index, gossan detection | Sentinel-2, ASTER, EMIT | GEE + EMIT (PARTIALLY_ACCESSIBLE) | PHYSICALLY_PLAUSIBLE |
| "Something is pulling me there" | No credible physical proxy for human proprioceptive or intuitive response per se | Operator's geological knowledge and terrain observation are real — the sensation of being "pulled" is not a measurable physical field | N/A | N/A | NON_TESTABLE_AT_THIS_MOMENT |

---

## Extended Notes

### "The Earth responds"
The most general and accurate framing. Subsurface properties — lithology, mineralisation, structure, fluids — all modulate surface observables. The whole GeaSpirit pipeline is built on this truth. Nothing in this phrase is speculative; the challenge is which observables to prioritise and whether the signal clears the noise floor.

### "The subsurface emits a signal"
Physically correct for passive geophysical fields (gravity, magnetism, natural EM). The phrase becomes misleading when taken to imply the subsurface is intentionally transmitting. The signals are passive physical phenomena, not transmissions.

### "The terrain returns a resonance"
Technically accurate for seismic H/V methods and magnetotellurics. "Resonance" here means impedance mismatch reflection and standing wave phenomena — not a metaphorical concept. The measurability is real; the access is blocked.

### "An operator notices something"
This is the most GEE-testable translation. Skilled operators notice exactly the kinds of features that satellite remote sensing can encode: anomalous vegetation colour, drainage anomalies, surface texture, colour contrast. Pattern recognition by experienced operators IS a valid information source — it just needs to be translated into quantified features.

### "The ground remembers"
This is the edge between physically plausible and speculative. Geology is history made solid — intrusions, metamorphism, alteration all leave measurable traces. The speculation is in whether the relevant signatures survive to the surface and are detectable by current sensors at useful spatial resolution.

### "There is energy underground"
Geothermal gradients are real and measurable with borehole instruments. Airborne radiometric surveys detect radioactive decay in near-surface rocks. The problem is access: no open satellite geothermal gradient data exists at deposit scale. Radon surveys require ground deployment. This remains blocked.

### "Water behaves differently here"
Strong physical basis. Fault zones concentrate groundwater. Alteration halos change permeability. This is well-validated in exploration geology and is partially accessible via SMAP (coarse) and hydrological DEM analysis (free). Tested in Phase 9 hydrology fusion.

### "The colours are wrong"
The most directly validated intuition in this list. Gossans, iron oxide halos, clay alteration zones, and hydrothermal silicification all produce spectral anomalies detectable by Sentinel-2, ASTER, and EMIT. This is the core of GeaSpirit's satellite baseline. Already in production.

### "Something is pulling me there"
The experience is real and should be respected as a product of the operator's unconscious integration of geological cues. The pulling sensation itself is not a physical field that can be measured. The useful residue is to interview the operator and extract what they actually observed — that observation is measurable.

---

## Guardrails

1. No phrase in this table implies direct subsurface detection.
2. No phrase in this table enters the production pipeline without controlled AUC validation.
3. NON_TESTABLE phrases are documented here so they are not pursued wastefully.
4. SPECULATIVE phrases require a falsifiable experimental design before any compute is allocated.

**Canonical score: 22.8/40 UNCHANGED.**

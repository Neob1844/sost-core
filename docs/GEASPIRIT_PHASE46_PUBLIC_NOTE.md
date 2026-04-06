# GeaSpirit Phase 46 — Multi-Commodity Mineral Intelligence

**Date:** 2026-03-30

## Doctrinal Expansion

GeaSpirit formally expands from metal-focused exploration to **multi-commodity mineral intelligence**. The MINERAL dimension of the canonical objective now covers:

- Metals (Cu, Au, Pb-Zn, Fe)
- Non-metallic minerals (lithium, graphite, evaporites)
- Industrial minerals (phosphate, gypsum, potash)
- Strategic elements (REE, uranium, diamond)

GeaSpirit does not detect atoms directly — it identifies **geological systems, alteration patterns, structural context, and spectral/geophysical signatures** compatible with each commodity.

## Validated Commodities (measured AUC)

| Commodity | Best AUC | Zones | Status |
|-----------|---------|-------|--------|
| Porphyry Cu | 0.882 | Chuquicamata | VALIDATED |
| Orogenic Au | 0.879 | Kalgoorlie | VALIDATED |
| IOCG | 0.841 | Tennant Creek | VALIDATED |
| SEDEX Cu-Pb-Zn | 0.781 | Mt Isa | VALIDATED |
| Sediment Cu | 0.760 | Zambia | VALIDATED |
| Lithium (salar) | 0.804 | Atacama + Uyuni | MULTI-ZONE VALIDATED |
| Graphite | 0.730 | Madagascar | POSITIVE (with geology) |

## Key Finding

**Different commodities have different dominant families:**
- Gold → magnetics
- Copper → spectral
- IOCG → magnetics + gravity
- Lithium → terrain (basin geometry, flatness)
- Graphite → spectral + geology

## New Zone: Pebble, Alaska (Porphyry Cu-Au-Mo)

**Date:** 2026-04-06

- **Zone:** Pebble, Bristol Bay, Alaska (59.89N, 155.27W)
- **Deposit type:** porphyry_cu_au_mo
- **Owner:** Northern Dynasty Minerals (TSX: NDM)
- **Resource:** ~57B lbs Cu, ~70M oz Au, ~3.4B lbs Mo, ~345M oz Ag
- **Regulatory status:** Blocked by EPA Section 404(c) (2023)
- **Labels:** 22 mineral occurrences (NDM NI 43-101 + USGS ARDF)
- **Analog zone:** Chuquicamata (best porphyry results: 0.882 AUC)
- **Expected baseline AUC:** ~0.82 (based on analog performance)
- **Pipeline:** Full 11-tool deployment
  - S2 baseline, thermal 20yr, PCA embeddings, spectral unmixing, NDVI trends, geophysics (USGS), heuristic scoring, frontier targets
- **Alaska-specific adaptations:**
  - Enhanced cloud filtering (high cloud cover at ~60N)
  - Summer-window NDVI (short growing season)
  - Thermal seasonality correction (extreme annual range)
- **EMIT limitation:** ISS orbital inclination (51.6 deg) limits coverage at 59.9N — EMIT data may be sparse or unavailable
- **Status:** Analysis pipeline created, queued for execution

## Canonical: 23.9/40 (60%)
Doctrinal expansion does not change the score. Score moves only with measured validation.

# GeaSpirit CTO Sprint 2 Report

**Date:** 2026-03-26
**Focus:** Three genuinely new experiments on real Kalgoorlie data

---

## Decisions

| Decision | Rationale |
|----------|-----------|
| Skip gravity download | THREDDS path not found for Bouguer. TMI worked, gravity catalog structure different. |
| Execute hydrology from existing DEM | Zero download needed. Flow accumulation + TWI + drainage density from elevation band. |
| Execute error consensus | 4 models on same data. Find systematic blind spots. |
| Execute mineral discrimination with new features | Test if hydro/interactions help Au vs Ni. |

---

## Experiment 1: Hydrological Features

**New features computed from DEM (existing data):**

| Feature | Cohen's d | p-value | Signal | Physical meaning |
|---------|-----------|---------|--------|-----------------|
| drainage_density | **+0.576** | 4.0e-14 | **STRONG** | Deposits in areas with MORE drainage channels |
| twi | **-0.490** | 7.5e-12 | **STRONG** | Deposits in DRIER, hilltop positions |
| log_flow_accumulation | +0.283 | 5.2e-05 | MODERATE | Deposits near flow convergence |

**drainage_density (d=+0.576)** is a genuinely new discriminating feature. Physical interpretation: mineral deposits (especially orogenic Au) form along structural contacts and fault intersections, which also control drainage patterns. Higher drainage density = more fracturing = more structural complexity = more likely deposit location.

**ML result:** AUC neutral (+0.0001). The GBM already learns this from TPI and ruggedness. Value is in interpretability and mineral discrimination.

## Experiment 2: Error Consensus Discovery

| Metric | Count | % |
|--------|-------|---|
| ALL 4 models correct | 153 | 93.3% |
| ALL 4 models wrong | 0 | 0.0% |
| Disagreement | 11 | 6.7% |

**Zero consensus errors.** No deposits that ALL models fail on. The feature stack is complete for this test set — there are no systematic blind spots.

**Implication:** Adding new feature families won't fix detection at Kalgoorlie. The detection ceiling (~0.88 AUC) is likely a label/data quality limit, not a feature gap.

## Experiment 3: Mineral Discrimination

| Model | Au vs Ni AUC |
|-------|-------------|
| Baseline satellite only | 0.4754 |
| + Hydrology + Interactions | **0.5609** |
| Delta | **+0.086** |

**Hydrological features improve Au vs Ni discrimination.** Au deposits are in drier, higher drainage density positions (hilltop structural contacts). Ni deposits are in wetter, lower TWI positions (komatiite flow bases). This is geologically correct.

AUC 0.56 is still weak but the DIRECTION is right. From previous sprint: neighborhood context gave 0.627. Combined path: neighborhood + hydrology should push mineral AUC toward 0.65-0.70.

---

## Canonical Score Update

| Dimension | Previous | Now | Change |
|-----------|----------|-----|--------|
| MINERAL | 3.3/10 | 3.3/10 | +0.0 (hydro helps but not in spatial block CV yet) |
| DEPTH | 4.1/10 | 4.1/10 | +0.0 (gravity download failed) |
| COORDINATES | 7.0/10 | 7.0/10 | unchanged |
| CERTAINTY | 9.3/10 | 9.3/10 | unchanged |
| **TOTAL** | **23.7/40** | **23.7/40** | +0.0 |

## Key Learning

**The detection model is near its ceiling at Kalgoorlie.** Zero consensus errors means our feature stack is complete for detection. The remaining gains are in:
1. **Mineral discrimination** (hydrology + neighborhood + geology)
2. **Depth estimation** (gravity download needed, or AEM)
3. **Cross-zone generalization** (currently zone-specific)

## Next CTO Action

1. **Find correct GA gravity THREDDS path** or download from ecat.ga.gov.au directly
2. **Combine neighborhood context + hydrology** for mineral discrimination at all zones
3. **GSWA geological map** as the strongest remaining mineral-ID lever

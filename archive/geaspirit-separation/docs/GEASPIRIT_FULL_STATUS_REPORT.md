# GeaSpirit — Platform Status

**Date:** 2026-03-29

## Overview

GeaSpirit is a multi-source mineral prospectivity intelligence platform. It combines satellite imagery, geophysics, geology, hydrology, and machine learning to produce calibrated probability maps for mineral exploration.

## Canonical Objective

**22.8/40 (57%)** — "There is [MINERAL] at [DEPTH] at [COORDINATES] with [X%] certainty"

| Dimension | Score | Max |
|-----------|-------|-----|
| MINERAL | 4.0 | 10 |
| DEPTH | 4.1 | 10 |
| COORDINATES | 7.0 | 10 |
| CERTAINTY | 7.7 | 10 |

The gap to a higher score is primarily a data access problem, not an architecture problem.

## Validated Zones

| Zone | Deposit Type | Best AUC | Status |
|------|-------------|----------|--------|
| Chuquicamata (Chile) | Porphyry Cu | 0.882 | Core Production |
| Kalgoorlie (Australia) | Orogenic Au | 0.879 | Core Production |
| Tennant Creek (Australia) | IOCG + Au | 0.763 | Transfer Validated |
| Zambia Copperbelt | Sediment Cu | 0.760 | Core Production |

## Key Capabilities

- Multi-source selective fusion (satellite + magnetics + geology + hydrology)
- Regime-aware automatic family selection (28 gating rules)
- Calibrated uncertainty (isotonic calibration, Brier score 0.096)
- Spatial cross-validation with bootstrap confidence intervals
- Fail-fast data quality guard (10 mandatory checks)
- QGIS QA workflows for operational validation

## Current Phase

Phase 39 — Magnetics upgraded to CONSOLIDATED_VALIDATED_SELECTIVE after measuring +0.069 delta over independent terrain baseline at Tennant Creek (second zone, different deposit type from Kalgoorlie).

## Infrastructure

- CPU-only (no GPU required)
- All primary data sources are free and open
- Runs on standard hardware

## Materials Engine

Separate platform: 76,193 materials corpus with graph neural network predictions. Functional, not yet public.

---

Full technical documentation is maintained in the private research repository.

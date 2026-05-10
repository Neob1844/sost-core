# Trinity Useful Compute Plan — AOI `kalgoorlie`

> **DRY-RUN ONLY.** This document is a design artefact describing what Heavy Tasks *would* look like if the operator later activated Useful Compute rewards. No rewards are active. No tasks have been published. The public Useful Compute API is unaffected.

- **Schema**: `trinity-useful-compute-plan/v0`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source dossier**: `/home/sost/SOST/sostcore/sost-core/TRINITY_DEMO_DOSSIER_kalgoorlie.json`
- **Reviews considered**: 1
- **Candidate tasks emitted**: 3
- **Workers simulated**: 8

## Reward-worthiness summary

| Status | Count |
| --- | --- |
| `candidate_reward_worthy` | 3 |
| `deferred` | 0 |
| `not_reward_worthy` | 0 |

## Candidate Heavy Task families

### 1. AOI feature tile scoring

- **Family id**: `aoi_tile_scoring`
- **Project**: `geaspirit`
- **Reward status (v0 classification)**: `candidate_reward_worthy`
- **Derived from review**: `aoi:kalgoorlie` (hypothesis hash `abb3423914c731a4`)
- **Estimated runtime per task**: 300 s (1536 MB)
- **Requires N workers for verification**: 2
- **Declared deterministic**: `True`
- **Declared auditable**: `True`
- **Dependencies**: `numpy`, `rasterio`, `geopandas`

**Description for classifier:**

> Geaspirit-side per-tile feature scoring across an AOI using fixed feature recipes (DEM derivatives, SAR texture, geological-map overlay). Output: per-tile feature vector + zone score. Reproducibility via pinned recipe library. Verification: N>=2 deterministic batch.

**Why this reward status:**

> Classifier accepted on all five axes (useful, deterministic, auditable, heavy-enough, safe-to-verify). Tagged candidate_reward_worthy.

Classifier axes: useful=`True` determ=`True` auditable=`True` heavy=`True` verifiable=`True` overall=`True`

---

### 2. Geology-aware negative resampling for Geaspirit

- **Family id**: `geology_aware_negative_resampling`
- **Project**: `geaspirit`
- **Reward status (v0 classification)**: `candidate_reward_worthy`
- **Derived from review**: `aoi:kalgoorlie` (hypothesis hash `abb3423914c731a4`)
- **Estimated runtime per task**: 150 s (1024 MB)
- **Requires N workers for verification**: 2
- **Declared deterministic**: `True`
- **Declared auditable**: `True`
- **Dependencies**: `numpy`, `geopandas`

**Description for classifier:**

> Build geology-aware negative training samples for the Geaspirit ranking models so positives are not biased by easily-distinguishable controls. Pinned random seed, deterministic batch, auditable. Output: negative sample set + provenance manifest.

**Why this reward status:**

> Classifier accepted on all five axes (useful, deterministic, auditable, heavy-enough, safe-to-verify). Tagged candidate_reward_worthy.

Classifier axes: useful=`True` determ=`True` auditable=`True` heavy=`True` verifiable=`True` overall=`True`

---

### 3. Spectral template scoring

- **Family id**: `spectral_template_scoring`
- **Project**: `geaspirit`
- **Reward status (v0 classification)**: `candidate_reward_worthy`
- **Derived from review**: `aoi:kalgoorlie` (hypothesis hash `abb3423914c731a4`)
- **Estimated runtime per task**: 240 s (1024 MB)
- **Requires N workers for verification**: 2
- **Declared deterministic**: `True`
- **Declared auditable**: `True`
- **Dependencies**: `numpy`, `rasterio`
- **Notes**: Template library is the audit anchor; it must be version-pinned alongside the worker bundle.

**Description for classifier:**

> Geaspirit-side feature scoring of EMIT / Sentinel-2 spectral tiles against a fixed library of mineral templates. Output: per-tile score vector. Verification: two workers re-run the same template library on the same tile and agree to within rounding tolerance. Deterministic batch.

**Why this reward status:**

> Classifier accepted on all five axes (useful, deterministic, auditable, heavy-enough, safe-to-verify). Tagged candidate_reward_worthy.

Classifier axes: useful=`True` determ=`True` auditable=`True` heavy=`True` verifiable=`True` overall=`True`

---

## Simulated worker queue

- **Workers**: 8
- **Tasks**: 3
- **Total serial work**: 690.0 s
- **Estimated wallclock**: 300.0 s (longest-processing-time-first heuristic)
- **Per-worker seconds**:
    - worker 0: 300.0 s
    - worker 1: 240.0 s
    - worker 2: 150.0 s
    - worker 3: 0.0 s
    - worker 4: 0.0 s
    - worker 5: 0.0 s
    - worker 6: 0.0 s
    - worker 7: 0.0 s

## Safety notice

DRY-RUN ONLY. This plan is a design artefact. No Useful Compute rewards have been activated. No tasks have been published to the public Useful Compute API. No tasks have been enqueued. The classifier's `candidate_reward_worthy` tag means a family WOULD be eligible if and only if the operator's separate consensus + activation procedure later opens that door.

## Integrity

- **Canonical JSON SHA-256**: `1e7ab30aa1595c8f19114382710536ed8faf0b6122ae16f441a34b55a2647b49`
- This SHA-256 is computed over the sorted, no-spaces, ASCII JSON serialisation of the plan object.
- The operator can register the SHA-256 on the SOST chain as a `DOC_REF_OPEN` or `OPEN_NOTE_INLINE` capsule, identically to a Trinity dossier hash.

## What this document is NOT

- This is **not** a list of currently rewarded tasks.
- This is **not** an announcement of an open Useful Compute paid queue.
- This is **not** a guarantee that any of the `candidate_reward_worthy` families will ever become active. Activation requires a separate consensus + governance procedure that has not shipped.
- This is **not** input to the existing public Useful Compute worker; the worker is unchanged.

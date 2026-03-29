# Free Data Access Map Beyond Satellite — V1

Date: 2026-03-29

## Purpose
Operational inventory of free tools and datasets that can help GeaSpirit beyond basic satellite imagery.

## A) Processing & Unified Access

| Source | What It Adds | Canonical Dimension | Access Mode | Auth Required | Can Connect Now | Status |
|--------|-------------|-------------------|-------------|---------------|-----------------|--------|
| Google Earth Engine | Unified processing of S2, Landsat, SRTM, S1, climate, terrain | ALL | API (Python ee) | YES (Google account) | YES | OPERATIONALIZED |

## B) Geology & Lithology

| Source | What It Adds | Canonical Dimension | Access Mode | Auth Required | Can Connect Now | Status |
|--------|-------------|-------------------|-------------|---------------|-----------------|--------|
| Macrostrat API | Lithology, formation age, rock type at any coordinate | MINERAL | REST API | NO | YES | VALIDATED_SELECTIVE (3 zones) |
| OneGeology | Global geological maps (WMS/WFS) | MINERAL | WMS/WFS portal | NO | PARTIAL — many layers require national server | PARTIALLY_ACCESSIBLE |
| USGS Geologic Maps | US geological maps | MINERAL | Download portal | NO | YES (manual) | ACCESSIBLE_MANUAL |

## C) Deposits & Occurrences

| Source | What It Adds | Canonical Dimension | Access Mode | Auth Required | Can Connect Now | Status |
|--------|-------------|-------------------|-------------|---------------|-----------------|--------|
| USGS MRDS | Mineral deposit locations globally | MINERAL, COORDINATES | REST API + download | NO | YES | OPERATIONALIZED (used for labels) |
| OZMIN (GA) | Australian mineral occurrences | MINERAL, COORDINATES | Download | NO | YES | OPERATIONALIZED (Kalgoorlie) |
| MINDAT | Mineral species and localities | MINERAL | API | YES (API key) | NO | BLOCKED_BY_AUTH |

## D) Terrain / Topography / Hydrology

| Source | What It Adds | Canonical Dimension | Access Mode | Auth Required | Can Connect Now | Status |
|--------|-------------|-------------------|-------------|---------------|-----------------|--------|
| SRTM 30m (GEE) | Elevation, slope, aspect | COORDINATES | GEE | YES (Google) | YES | OPERATIONALIZED |
| ALOS DEM 30m (GEE) | Elevation (alternative to SRTM) | COORDINATES | GEE | YES (Google) | YES | ACCESSIBLE |
| CSP/ERGo Landform (GEE) | Topographic diversity, landforms | COORDINATES | GEE | YES (Google) | YES | TESTED (Phase 27) |
| HydroSHEDS | Drainage networks, basins, flow accumulation | COORDINATES | Download + GEE | NO | YES | OPERATIONALIZED (hydrology family) |
| SMAP Soil Moisture (GEE) | Surface soil moisture | MINERAL (alteration proxy) | GEE | YES (Google) | YES | ACCESSIBLE |

## E) Thermal / Time Series

| Source | What It Adds | Canonical Dimension | Access Mode | Auth Required | Can Connect Now | Status |
|--------|-------------|-------------------|-------------|---------------|-----------------|--------|
| Landsat thermal (GEE) | Land surface temperature, thermal inertia proxy | MINERAL | GEE | YES (Google) | YES | VALIDATED_SELECTIVE (thermal 20yr) |
| ECOSTRESS (GEE/earthaccess) | High-res thermal (70m), diurnal cycle | MINERAL | earthaccess API | YES (NASA Earthdata) | PARTIAL | PARTIALLY_ACCESSIBLE |
| MODIS LST (GEE) | Coarse thermal time series (1km) | MINERAL | GEE | YES (Google) | YES | ACCESSIBLE (coarse) |

## F) Geophysics (Open)

| Source | What It Adds | Canonical Dimension | Access Mode | Auth Required | Can Connect Now | Status |
|--------|-------------|-------------------|-------------|---------------|-----------------|--------|
| GA TMI Magnetics (NCI THREDDS) | Total magnetic intensity (national grid) | MINERAL, DEPTH | OPeNDAP/THREDDS | NO | YES | VALIDATED_SELECTIVE (Kalgoorlie +0.008) |
| WGM2012 Global Gravity | Bouguer/Free-air gravity (coarse) | DEPTH | Download | NO | YES (but ~10km resolution) | ACCESSIBLE (regional only) |
| EMAG2v3 | Global magnetic anomaly grid (2 arc-min) | MINERAL | Download | NO | YES (but coarse) | ACCESSIBLE (regional only) |
| GA Gravity Grid | National gravity (detailed) | DEPTH, MINERAL | GADDS portal | NO | NO — returns HTML not data | BLOCKED_BY_PORTAL |
| GSWA AEM | Airborne EM surveys (WA) | DEPTH, MINERAL | DMIRS portal | NO | NO — returns 403 | BLOCKED_BY_PORTAL |
| USGS Earth MRI | US regional geophysics | DEPTH, MINERAL | ScienceBase portal | YES (sometimes) | PARTIAL — some datasets accessible | PARTIALLY_ACCESSIBLE |

## G) Precipitation / Climate

| Source | What It Adds | Canonical Dimension | Access Mode | Auth Required | Can Connect Now | Status |
|--------|-------------|-------------------|-------------|---------------|-----------------|--------|
| GPM Precipitation (GEE) | Daily/monthly rainfall for differential drying analysis | MINERAL (response proxy) | GEE | YES (Google) | YES | ACCESSIBLE |
| ERA5 Reanalysis (GEE) | Temperature, wind, radiation, humidity | MINERAL (forcing analysis) | GEE | YES (Google) | YES | ACCESSIBLE |

## H) SAR / Radar

| Source | What It Adds | Canonical Dimension | Access Mode | Auth Required | Can Connect Now | Status |
|--------|-------------|-------------------|-------------|---------------|-----------------|--------|
| Sentinel-1 SAR (GEE) | Radar backscatter, coherence, moisture sensitivity | COORDINATES, MINERAL | GEE | YES (Google) | YES | ACCESSIBLE |

## I) Hyperspectral

| Source | What It Adds | Canonical Dimension | Access Mode | Auth Required | Can Connect Now | Status |
|--------|-------------|-------------------|-------------|---------------|-----------------|--------|
| EMIT (NASA) | Mineralogy from space (380-2500nm) | MINERAL | earthaccess | YES (NASA Earthdata) | PARTIAL (some granules truncated) | VALIDATED_SELECTIVE (porphyry) |
| ASTER L2 (GEE/LP DAAC) | Thermal + SWIR mineralogy | MINERAL | GEE + download | YES (some) | YES | ACCESSIBLE |

## Summary

| Status | Count |
|--------|-------|
| OPERATIONALIZED | 6 |
| VALIDATED_SELECTIVE | 4 |
| ACCESSIBLE | 9 |
| PARTIALLY_ACCESSIBLE | 3 |
| ACCESSIBLE_MANUAL | 1 |
| BLOCKED_BY_PORTAL | 2 |
| BLOCKED_BY_AUTH | 1 |
| **Total sources inventoried** | **26** |

**Key insight:** GEE is the operational backbone. 19 of 26 sources are accessible or operationalized. The gap is DEPTH — the 3 most valuable depth sources (GA gravity detail, GSWA AEM, Earth MRI detail) are all BLOCKED_BY_PORTAL or require manual portal access. Coarse global geophysics (WGM2012, EMAG2v3) are downloadable but provide only regional-scale signal (~10km resolution), insufficient for deposit-scale targeting.

## Access Honesty Notes

- **BLOCKED_BY_PORTAL** means the URL was tried and returned HTML or 403, not machine-readable data. Do not attempt automated download.
- **BLOCKED_BY_AUTH** means the source requires an API key or account that has not been provisioned. Do not invent a workaround.
- **PARTIALLY_ACCESSIBLE** means some datasets or regions within the source are accessible but not all.
- **ACCESSIBLE** means the data can be connected to via GEE or direct download, but has not yet been integrated into the GeaSpirit pipeline.
- **OPERATIONALIZED** means integrated into training and validated at one or more zones.
- **VALIDATED_SELECTIVE** means tested and confirmed to add measurable AUC improvement at specific zone types.

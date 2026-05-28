# `geaspirit.opportunity` — Sprint 1

Isolated subpackage that produces an **OpportunityScorecard** for a
geographic AOI (Area Of Interest). Designed for the "Mine-Waste
Alpha" use case: ranking abandoned / undervalued mineral assets
(tailings, dumps, lapsed concessions, e-waste sites) for desk-research
prioritisation.

**This is NOT a resource estimate. NOT a financial promise. NOT a
substitute for legal title checks or accredited sampling.** The
language guardrail in `contracts.py` raises `ValueError` if any
public-facing string contains phrases like *"confirmed resource"*,
*"guaranteed return"*, *"proven reserves"*, etc.

## Why a separate subpackage

The existing GeaSpirit stack (`dataset.py`, `model.py`, `indices.py`,
`spectral.py`, `ee_download.py`, and the 31+ scripts in
`geaspirit/scripts/`) is focused on **prospectivity modelling** for
operating mineral districts (Kalgoorlie, Chuquicamata, Pilbara,
Zambia Copperbelt). It is not touched by this subpackage.

`opportunity/` plugs onto the side: it consumes **public data only**
(OSM, GRID-Arendal Global Tailings Portal CSV, EEA Natura 2000
GeoJSON, USGS MRDS via existing loader in `dataset.py`), runs a
scoring formula, and emits a canonical-JSON scorecard whose SHA-256
can be anchored on chain via the **SOST Protocol Registry** (same
pattern as Trinity Kalgoorlie Phase 1 — capsule on block #8085).

## Layout

```
opportunity/
├── __init__.py
├── contracts.py         AOI · Evidence · ConnectorResult ·
│                        OpportunityScorecard · language denylist
├── canonical.py         deterministic JSON serialisation + SHA-256
├── cache.py             tiny file cache for connector responses
├── connectors/
│   ├── __init__.py
│   ├── osm_logistics.py   roads / rail / ports via Overpass (no auth)
│   ├── env_constraints.py Natura 2000 / protected area GeoJSON (local file)
│   └── tailings_portal.py GRID-Arendal CSV importer (local file)
├── orchestrator.py      score_opportunity()
└── tests/               unit tests, stdlib unittest, zero network
```

Operator-supplied data dirs:

```
geaspirit/data/opportunity/
├── cache/                file cache for Overpass + future API responses
├── samples/              committed AOI JSON files (Galicia W-Sn demo)
├── tailings_manual/      drop GRID-Arendal Global Tailings Portal CSV here
├── natura2000/           drop EEA protected-areas GeoJSON here
└── results/              CLI output: <slug>__<UTC>.json + .pretty.json
```

## Quick start

```bash
cd ~/SOST/sostcore/sost-core/geaspirit

# Run the demo (Galicia W-Sn)
python3 scripts/opportunity_scan.py \
  --aoi-file data/opportunity/samples/galicia_wsn_aoi.json

# Or pass fields directly
python3 scripts/opportunity_scan.py \
  --name "Faja Pirítica" --lat 37.65 --lon -6.95 \
  --radius-km 40 --country ES --metals Cu,Zn,Pb,Ag,Au

# Run the tests (no network needed)
python3 -m unittest discover -s geaspirit/opportunity/tests -v
```

Sample CLI output:

```
[opportunity_scan] AOI: Galicia W-Sn — Forcarei district (42.6364, -8.3486) r=30 km metals=W,Sn
[opportunity_scan] running connectors ...

  SCORE:        78 / 100   (B+)
  EVIDENCE:     nearby_road_access, nearby_railway, environmental_clear,
                no_known_tailings_in_radius
  THESIS:       Galicia W-Sn — Forcarei district is a B+ candidate for W, Sn.
                Road access is present. Rail infrastructure is reachable. ...
  NEXT STEP:    Run desk validation: cross-check published historical
                occurrence with national mineral catastro / geological survey. ...
  CONNECTORS:
    - osm_logistics            ok
    - env_constraints          skipped   (no Natura 2000 GeoJSON found ...)
    - tailings_portal          ok

  CANONICAL SHA-256:  b8f2...e3c5
  → use this digest in a Protocol Registry capsule to anchor this
    scorecard on chain.

  WROTE canonical:    .../results/galicia-w-sn-forcarei-district__...Z.json
  WROTE pretty:       .../results/galicia-w-sn-forcarei-district__...Z.pretty.json
```

## Scoring formula (Sprint 1)

```
base = 40 (neutral "needs validation")
 + strategic_metal_bonus  (0 .. +15)
 + logistics_bonus        (0 .. +25)   road / rail / port closeness
 + tailings_bonus         (0 .. +25)   count + biggest TSF volume
 - env_risk_penalty       (0 .. -30)   Natura 2000 polygon overlap
 - data_uncertainty       (0 .. -10)   < 3 successful connectors
→ clamp 0-100
```

Grades: **A** ≥80 · **B+** 65-79 · **B** 50-64 · **C** 30-49 · **F** <30.

## Data licences

| Source | Licence | Notes |
|---|---|---|
| OpenStreetMap (via Overpass) | ODbL-1.0 | Attribute "© OpenStreetMap contributors" in any public output. |
| GRID-Arendal Global Tailings Portal | Operator-imported subset | Request the dataset from GRID-Arendal (https://tailing.grida.no/about). Do NOT scrape the web UI. |
| EEA Natura 2000 | EEA standard terms | Free for non-commercial use; commercial use requires attribution per EEA terms. |
| USGS MRDS (loaded via `dataset.py`) | Public domain | Already integrated in the existing GeaSpirit stack. |

## What's NOT in Sprint 1

Roadmap from the planning conversation:

- **Sprint 2**: MITECO Catastro Minero (España), MINDAT API labels,
  metal-price connector improvements, PDF dossier renderer.
- **Sprint 3**: Sentinel-2 visual evidence cards (reuse existing
  `ee_download.py` for the download, add a small image-extraction
  helper here), redacted public teaser, Protocol Registry capsule
  helper (one-liner that takes a scorecard digest and prints the
  `sost-cli --capsule-mode open-note --capsule-text "..."` line),
  private dashboard.

If you want to ship something this sprint:

1. Drop a GRID-Arendal CSV (1 email request) and a EEA Natura 2000
   GeoJSON in the right data dirs.
2. Run the CLI against 2-3 Spanish/Portuguese AOIs (Galicia W-Sn,
   Faja Pirítica, Cartagena-La Unión).
3. Hand the resulting scorecards to a geologist for human
   interpretation. The scorecard is a ranking + evidence trail, not
   the report itself.
4. Anchor the canonical SHA-256 on chain via Protocol Registry so the
   timestamped discovery has a tamper-evident trail before any
   contact with concession holders.

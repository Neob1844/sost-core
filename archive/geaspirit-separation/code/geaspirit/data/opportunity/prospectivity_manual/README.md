# GeaSpirit prospectivity — operator drop-box

The `geaspirit_prospectivity` connector reads every `*.json` and
`*.csv` file in this directory at scan time and merges them into the
**geological** sub-score of the opportunity layer.

It **never** calls the network. The connector itself does not import,
re-run or re-train anything from the classical GeaSpirit satellite/ML
stack. Operators are expected to:

1. Run the classical GeaSpirit pipeline (`analyze_custom_aois.py`,
   `rank_targets.py`, `export_target_coordinates.py`, etc.) on their
   own schedule and infrastructure.
2. Normalise the produced scores into the schema below.
3. Drop the resulting JSON or CSV here.

That contract keeps the opportunity layer fast, offline-runnable and
testable without the full GeaSpirit environment.

## Record schema (JSON or CSV header — case-insensitive)

```
aoi_name      str         free text, e.g. "Galicia W-Sn / Forcarei"
lat, lon      float       decimal degrees, WGS84
radius_km     float       optional; record footprint radius
                          (treated as a point when absent)
score         float       in [0,1] OR in [0,100]; values <= 1.0
                          are auto-multiplied by 100
score_type    str         "heuristic" | "model_auc" |
                          "geaspirit_phase27" | ... (free text)
confidence    float       in [0,1]; defaults to the dataset-level
                          `default_confidence` field, then 0.55
model         str         e.g. "GeaSpirit Phase 27 Subsurface-Aware"
source        str         e.g. "analyze_custom_aois.py"
signals       list[str] / str   recognised families:
                          spectral, geophysics, thermal, terrain
                          (extras are kept on `data` but do not emit
                          signal tags)
notes         str         optional, free text
```

### JSON envelope

Either a top-level list of records, or a dict like:

```json
{
  "version": "geaspirit_prospectivity.v1",
  "default_confidence": 0.6,
  "license_notes": "Internal GeaSpirit output ...",
  "disclaimer": "...",
  "records": [
    { "aoi_name": "...", "lat": 42.6, "lon": -8.3, "score": 0.72, ... }
  ]
}
```

### CSV layout

```csv
aoi_name,lat,lon,radius_km,score,score_type,confidence,model,source,signals,notes
"Galicia W-Sn",42.6,-8.3,30.0,0.72,heuristic,0.7,GeaSpirit Phase 27,analyze_custom_aois.py,spectral|terrain,desk validation candidate
```

`signals` may use `|` or `,` as a separator.

## Filter rule

A record is "near" the AOI if the haversine distance between the
record centroid and the AOI center is at most
`aoi.radius_km + record.radius_km` (the record's own radius is
treated as 0 when absent).

## Emitted Evidence tags

| Tag                                | Trigger                          |
|------------------------------------|----------------------------------|
| `geaspirit_prospectivity_high`     | max(score) >= 70                 |
| `geaspirit_prospectivity_medium`   | 40 <= max(score) < 70            |
| `geaspirit_prospectivity_low`      |  1 <= max(score) < 40            |
| `geaspirit_signal_spectral`        | family appears in any kept record|
| `geaspirit_signal_geophysics`      | "                                |
| `geaspirit_signal_thermal`         | "                                |
| `geaspirit_signal_terrain`         | "                                |

## What the geological sub-score does with them

- Band: `high → +25`, `medium → +15`, `low → +5` (one band only —
  highest priority wins).
- Each recognised signal family: `+3`, capped at `+12`.
- Signal bonus is **not** applied if no band tag is present —
  signals alone are not strong enough to lift a geology score.

## Honesty rule

A drop in this directory is desk-stage evidence. It is not a resource
declaration and not a financial forecast. The language guardrail on
the scorecard contract will refuse to construct a thesis that claims
otherwise.

# Public Demo Surface

## Recommended Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/status` | Engine health and version |
| GET | `/stats` | Corpus statistics |
| GET | `/materials?limit=5` | Browse materials |
| GET | `/materials/{id}` | Material detail |
| GET | `/search?formula=GaAs` | Search by formula |
| POST | `/predict` | Predict properties from CIF |
| GET | `/similar/{id}` | Find similar materials |
| GET | `/novelty/material/{id}` | Novelty assessment |
| GET | `/exotic/ranking/10` | Top exotic materials |
| POST | `/shortlist/build` | Build ranked shortlist |
| GET | `/campaigns/presets` | Campaign presets |
| POST | `/campaigns/run` | Run discovery campaign |
| GET | `/frontier/presets` | Frontier profiles |
| GET | `/intelligence/material/{id}` | Material intelligence report |
| GET | `/release/status` | Release info |
| GET | `/release/manifest` | Full manifest |

## Do NOT Demo
- `/selective-retraining/*`
- `/stratified-retraining/*`
- `/hierarchical-band-gap/*`
- `/hierarchical-band-gap-calibration/*`
- `/hierarchical-band-gap-regressor/*`
- `/hierarchical-band-gap-final/*`
- `/three-tier-band-gap/*`
- `/gate-recall-rescue/*`
- `/retraining-prep/*`

# Golden Workflows

## 1. Search a Known Material
Find GaAs in the corpus and inspect its properties

- `GET /search?formula=GaAs`
- `GET /materials/{id}`

**Value**: Demonstrates corpus quality and search capability

## 2. Predict Band Gap from Structure
Submit a CIF file and get a band_gap prediction

- `POST /predict`

**Value**: Core ML inference — the reason the engine exists

## 3. Discover Exotic Materials
Find the most unusual materials in the corpus

- `GET /exotic/ranking/10`
- `GET /intelligence/material/{id}`

**Value**: Shows the engine's ability to surface undiscovered opportunities

## 4. Run a Discovery Campaign
Launch a stable_semiconductor_hunt campaign

- `GET /campaigns/presets`
- `POST /campaigns/run`

**Value**: End-to-end discovery pipeline in one API call

## 5. Build a Frontier Shortlist
Multi-objective material selection for dual targets

- `GET /frontier/presets`
- `POST /frontier/run`

**Value**: Production-grade material selection for research planning


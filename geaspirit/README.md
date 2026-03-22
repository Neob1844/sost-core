# GeaSpirit Platform — Mineral Detection via Free Satellite AI

Fuses computational materials science with satellite remote sensing to detect mineral deposits using free data and AI.

## Quick Start

### Step 0: Create Free Accounts
| Service | URL | Purpose |
|---------|-----|---------|
| Google Earth Engine | https://earthengine.google.com | Sentinel-2/1 processing |
| Copernicus Data Space | https://dataspace.copernicus.eu | Direct satellite download |
| NASA Earthdata | https://urs.earthdata.nasa.gov | EMIT + Sentinel-1 download |
| USGS EarthExplorer | https://earthexplorer.usgs.gov | Landsat + DEM |

### Step 1: Setup
```bash
cd ~/SOST/sostcore/sost-core
python3 geaspirit/setup_geaspirit.py
```

### Step 2: Authenticate GEE
```bash
earthengine authenticate
```

### Step 3: Download Sentinel-2
```bash
cd ~/SOST/sostcore/sost-core/geaspirit
python3 scripts/download_sentinel2.py --zone chuquicamata
```

### Step 4: Compute Mineral Indices
```bash
python3 scripts/compute_mineral_indices.py \
  --input ~/SOST/geaspirit/data/sentinel2/chuquicamata_s2.tif \
  --output ~/SOST/geaspirit/data/indices/
```

### Step 5: Train Baseline Model
```bash
python3 scripts/train_baseline.py \
  --indices ~/SOST/geaspirit/data/indices/ \
  --mrds ~/SOST/geaspirit/data/mrds/mrds_deposits.csv \
  --zone chuquicamata
```

## Additional Data

### Sentinel-1 SAR
```bash
python3 scripts/download_sentinel1.py --zone chuquicamata
```

### EMIT Hyperspectral
```bash
python3 scripts/download_emit.py --zone chuquicamata
```

## Pilot Zones
| Zone | Location | Difficulty | Target |
|------|----------|-----------|--------|
| Chuquicamata, Chile | -22.3, -68.9 | Easy | Porphyry Cu |
| Pilbara, Australia | -22.0, 118.0 | Medium | Fe + Au |
| Zambian Copperbelt | -12.8, 28.2 | Hard | Sediment Cu |

## Architecture
```
geaspirit/
├── geaspirit/              # Core Python library
│   ├── __init__.py
│   ├── config.py           # Zones, bands, paths
│   ├── indices.py          # Mineral index computation
│   ├── spectral.py         # Spectral library parsing + SAM matching
│   ├── dataset.py          # Training data builder from MRDS + rasters
│   └── model.py            # ML training + evaluation (RF, XGBoost)
├── scripts/                # Executable pipelines
│   ├── download_sentinel2.py   # GEE-based S2 download
│   ├── download_sentinel1.py   # ASF-based SAR download
│   ├── download_emit.py        # NASA Earthdata EMIT guide
│   ├── compute_mineral_indices.py  # S2 → mineral index maps
│   └── train_baseline.py      # End-to-end ML training
├── setup_geaspirit.py      # Automated setup (dirs, deps, MRDS)
└── README.md
```

## Cost: $0
All satellite data, spectral libraries, and ML tools are free.
Runs on CPU — no GPU required.

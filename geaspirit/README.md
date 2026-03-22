# Geaspirit Project — Mineral Detection via Free Satellite AI

Fuses computational materials science with satellite remote sensing to detect mineral deposits using free data and AI.

## Quick Start

### Step 0: Create Free Accounts
| Service | URL | Purpose |
|---------|-----|---------|
| Google Earth Engine | https://earthengine.google.com | Sentinel-2/1 processing |
| Copernicus Data Space | https://dataspace.copernicus.eu | Direct satellite download |
| NASA Earthdata | https://urs.earthdata.nasa.gov | EMIT hyperspectral data |
| USGS EarthExplorer | https://earthexplorer.usgs.gov | Landsat + DEM |

### Step 1: Setup
```bash
python3 geaspirit/setup_geaspirit.py
```
Installs dependencies, downloads MRDS data, creates directory structure.

### Step 2: Authenticate GEE
```bash
earthengine authenticate
```

### Step 3: Download Sentinel-2
```bash
python3 geaspirit/scripts/download_sentinel2.py --zone chuquicamata
```

### Step 4: Compute Mineral Indices
```bash
python3 geaspirit/scripts/compute_mineral_indices.py \
  --input ~/SOST/geaspirit/data/sentinel2/chuquicamata_s2.tif \
  --output ~/SOST/geaspirit/data/indices/
```

### Step 5: Train Baseline Model
```bash
python3 geaspirit/scripts/train_baseline.py \
  --indices ~/SOST/geaspirit/data/indices/ \
  --mrds ~/SOST/geaspirit/data/mrds/mrds_deposits.csv \
  --zone chuquicamata
```

**Result:** Probability map of mineral deposits + AUC metrics.

## Pilot Zones
| Zone | Location | Difficulty | Target |
|------|----------|-----------|--------|
| Chuquicamata, Chile | -22.3, -68.9 | Easy | Porphyry Cu |
| Pilbara, Australia | -22.0, 118.0 | Medium | Fe + Au |
| Zambian Copperbelt | -12.8, 28.2 | Hard | Sediment Cu |

## Architecture
```
geaspirit/
├── geaspirit/          # Core library
│   ├── config.py       # Zones, bands, paths
│   ├── indices.py      # Mineral index computation
│   ├── dataset.py      # Training data builder
│   └── model.py        # ML training + evaluation
├── scripts/            # Executable pipelines
│   ├── download_sentinel2.py
│   ├── compute_mineral_indices.py
│   └── train_baseline.py
├── setup_geaspirit.py  # Automated setup
└── README.md
```

## Cost: $0
All satellite data, spectral libraries, and ML tools are free.
Runs on CPU. No GPU required.

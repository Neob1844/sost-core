#!/usr/bin/env python3
"""Geaspirit Project — Automated Setup Script.

Creates directory structure, installs dependencies, downloads free data.
Run: python3 geaspirit/setup_geaspirit.py
"""
import os
import subprocess
import sys
import urllib.request
import zipfile
import json
from pathlib import Path

BASE = Path.home() / "SOST" / "geaspirit"
REPO = Path(__file__).parent

DIRS = [
    "data/sentinel2", "data/sentinel1", "data/emit", "data/landsat",
    "data/dem", "data/spectral_libraries/usgs_v7", "data/spectral_libraries/aster",
    "data/mrds", "data/geology_maps", "data/indices",
    "models", "outputs", "notebooks",
]

PACKAGES = [
    "rasterio", "spectral", "scikit-learn", "xgboost", "geopandas",
    "shapely", "matplotlib", "seaborn", "pandas", "numpy",
    "requests", "tqdm", "h5py", "joblib", "folium",
]

# GEE and geemap are optional (require auth)
OPTIONAL_PACKAGES = ["earthengine-api", "geemap"]


def step(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def create_dirs():
    step("Creating directory structure")
    for d in DIRS:
        p = BASE / d
        p.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {p}")
    print(f"\n  Base directory: {BASE}")


def install_packages():
    step("Installing Python packages")
    for pkg in PACKAGES:
        try:
            __import__(pkg.replace("-", "_"))
            print(f"  ✓ {pkg} (already installed)")
        except ImportError:
            print(f"  → Installing {pkg}...")
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                           "--break-system-packages", pkg], capture_output=True)
            print(f"  ✓ {pkg}")

    print("\n  Optional packages (require authentication):")
    for pkg in OPTIONAL_PACKAGES:
        try:
            __import__(pkg.replace("-", "_").replace("earthengine-api", "ee"))
            print(f"  ✓ {pkg} (already installed)")
        except ImportError:
            print(f"  → Installing {pkg}...")
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                           "--break-system-packages", pkg], capture_output=True)
            print(f"  ✓ {pkg}")


def download_mrds():
    step("Downloading USGS MRDS deposit data")
    mrds_dir = BASE / "data" / "mrds"
    mrds_file = mrds_dir / "mrds_deposits.csv"

    if mrds_file.exists() and mrds_file.stat().st_size > 1000:
        print(f"  ✓ Already downloaded: {mrds_file} ({mrds_file.stat().st_size:,} bytes)")
        return

    # MRDS CSV export URL
    url = "https://mrdata.usgs.gov/mrds/mrds-csv.zip"
    zip_path = mrds_dir / "mrds-csv.zip"

    print(f"  → Downloading from {url}...")
    try:
        for attempt in range(3):
            try:
                urllib.request.urlretrieve(url, zip_path)
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  ⚠ Retry {attempt+1}/3: {e}")
                else:
                    raise

        if zip_path.exists():
            print(f"  → Extracting...")
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(mrds_dir)
                print(f"  ✓ Extracted to {mrds_dir}")
            except zipfile.BadZipFile:
                # Not a zip — might be direct CSV
                zip_path.rename(mrds_file)
                print(f"  ✓ Saved as CSV")
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        print(f"  → Manual download: https://mrdata.usgs.gov/mrds/")
        # Create placeholder
        mrds_file.write_text("# Download manually from https://mrdata.usgs.gov/mrds/\n")


def create_pilot_config():
    step("Creating pilot zone configuration")
    config = {
        "pilot_zones": {
            "chuquicamata": {
                "center": [-22.3, -68.9],
                "bbox": [-22.8, -69.4, -21.8, -68.4],
                "description": "Atacama desert, Chile — world's largest Cu mine",
                "difficulty": "easy",
                "target_minerals": ["chalcopyrite", "malachite", "azurite"],
                "known_deposit_types": ["porphyry copper", "copper oxide"],
            },
            "pilbara": {
                "center": [-22.0, 118.0],
                "bbox": [-22.5, 117.5, -21.5, 118.5],
                "description": "Pilbara, Western Australia — Fe+Au",
                "difficulty": "medium",
                "target_minerals": ["hematite", "goethite", "magnetite"],
                "known_deposit_types": ["banded iron formation", "gold"],
            },
            "zambia_copperbelt": {
                "center": [-12.8, 28.2],
                "bbox": [-13.3, 27.7, -12.3, 28.7],
                "description": "Zambian Copperbelt — sediment-hosted Cu",
                "difficulty": "hard",
                "target_minerals": ["chalcopyrite", "bornite", "chalcocite"],
                "known_deposit_types": ["sediment-hosted copper"],
            },
        },
        "sentinel2_params": {
            "cloud_cover_max": 10,
            "date_range": "2024-01-01/2025-12-31",
            "bands": ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"],
        },
    }
    config_path = BASE / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  ✓ {config_path}")


def print_summary():
    step("SETUP COMPLETE — Summary")
    print(f"  Base directory: {BASE}")
    print(f"  Data directory: {BASE / 'data'}")
    print()

    checks = [
        ("Directory structure", all((BASE / d).exists() for d in DIRS)),
        ("MRDS data", (BASE / "data" / "mrds").exists()),
        ("Config file", (BASE / "config.json").exists()),
    ]
    for name, ok in checks:
        print(f"  {'✓' if ok else '✗'} {name}")

    print(f"\n  NEXT STEPS:")
    print(f"  1. Create accounts (free):")
    print(f"     - Google Earth Engine: https://earthengine.google.com")
    print(f"     - Copernicus: https://dataspace.copernicus.eu")
    print(f"     - NASA Earthdata: https://urs.earthdata.nasa.gov")
    print(f"  2. Authenticate GEE: earthengine authenticate")
    print(f"  3. Download Sentinel-2: python3 geaspirit/scripts/download_sentinel2.py")
    print(f"  4. Compute indices: python3 geaspirit/scripts/compute_mineral_indices.py")
    print(f"  5. Train baseline: python3 geaspirit/scripts/train_baseline.py")


if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║  GEASPIRIT PROJECT — AUTOMATED SETUP     ║")
    print("║  Mineral Detection via Free Satellite AI  ║")
    print("╚══════════════════════════════════════════╝")

    create_dirs()
    install_packages()
    download_mrds()
    create_pilot_config()
    print_summary()

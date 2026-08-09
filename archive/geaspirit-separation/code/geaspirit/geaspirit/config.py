"""GeaSpirit centralized configuration."""
import os

BASE_DIR = os.path.expanduser("~/SOST/geaspirit")
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "models")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

# Pilot zones: (name, lat, lon, description)
PILOT_ZONES = {
    "chuquicamata": {"lat": -22.3, "lon": -68.9, "desc": "Atacama desert, Chile — world's largest Cu mine", "difficulty": "easy"},
    "pilbara": {"lat": -22.0, "lon": 118.0, "desc": "Pilbara, Western Australia — Fe+Au, exposed geology", "difficulty": "medium"},
    "zambia_copperbelt": {"lat": -12.8, "lon": 28.2, "desc": "Zambian Copperbelt — sediment-hosted Cu", "difficulty": "hard"},
}

# Sentinel-2 band names for mineral indices
S2_BANDS = {
    "B2": "Blue (490nm)", "B3": "Green (560nm)", "B4": "Red (665nm)",
    "B5": "RedEdge1 (705nm)", "B6": "RedEdge2 (740nm)", "B7": "RedEdge3 (783nm)",
    "B8": "NIR (842nm)", "B8A": "NIR narrow (865nm)",
    "B11": "SWIR1 (1610nm)", "B12": "SWIR2 (2190nm)",
}

# Mineral indices formulas (band ratios)
MINERAL_INDICES = {
    "iron_oxide": ("B4", "B2", "Iron Oxide Index = B4/B2"),
    "clay_hydroxyl": ("B11", "B12", "Clay/Hydroxyl Index = B11/B12"),
    "ferrous_iron": ("B11", "B8A", "Ferrous Iron Index = B11/B8A"),
    "laterite": ("B4", "B3", "Laterite Index = B4/B3"),
}

DIRS_TO_CREATE = [
    "data/sentinel2", "data/sentinel1", "data/emit", "data/landsat",
    "data/dem", "data/spectral_libraries/usgs_v7", "data/spectral_libraries/aster",
    "data/mrds", "data/geology_maps", "data/indices",
    "models", "outputs", "notebooks",
]

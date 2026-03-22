"""Shared Earth Engine download utilities for GeaSpirit Platform."""
import os
import sys
import requests
import numpy as np
from pathlib import Path

ZONES = {
    "chuquicamata": {"center": (-22.3, -68.9), "desc": "Atacama Cu"},
    "pilbara":      {"center": (-22.0, 118.0), "desc": "Pilbara Fe+Au"},
    "zambia":        {"center": (-12.8, 28.2),  "desc": "Zambian Cu"},
}
HALF_DEG = 0.25  # ~50km bbox


def init_ee():
    import ee
    try:
        ee.Initialize(project="ee-sost-geaspirit")
    except Exception as e:
        print(f"✗ EE init failed: {e}\n  Run: earthengine authenticate")
        sys.exit(1)
    return ee


def get_bbox(zone_name):
    z = ZONES[zone_name]
    lat, lon = z["center"]
    return [lon - HALF_DEG, lat - HALF_DEG, lon + HALF_DEG, lat + HALF_DEG]


def download_ee_image(image, bbox, output_path, scale, band_names=None):
    """Download EE image with automatic tile splitting if >50MB."""
    import ee
    roi = ee.Geometry.Rectangle(bbox)
    if band_names:
        image = image.select(band_names)
    image = image.clip(roi).toFloat()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Try direct download
    try:
        params = {"region": roi, "scale": scale, "format": "GEO_TIFF", "crs": "EPSG:4326"}
        url = image.getDownloadURL(params)
        _fetch(url, output_path)
        return True
    except Exception as e:
        if "50331648" in str(e) or "request size" in str(e).lower():
            print(f"  → Too large, splitting into 4 tiles...")
            return _download_tiled(image, bbox, output_path, scale, roi)
        raise


def _fetch(url, path):
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    total = 0
    with open(path, "wb") as f:
        for chunk in resp.iter_content(1024*1024):
            f.write(chunk)
            total += len(chunk)
    print(f"  → Downloaded: {total/(1024*1024):.1f} MB")


def _download_tiled(image, bbox, output_path, scale, roi):
    import ee, rasterio
    from rasterio.merge import merge
    w, s, e, n = bbox
    mx, my = (w+e)/2, (s+n)/2
    quads = [("NW",[w,my,mx,n]),("NE",[mx,my,e,n]),("SW",[w,s,mx,my]),("SE",[mx,s,e,my])]
    tiles = []
    parent = Path(output_path).parent
    for name, qb in quads:
        tp = str(parent / f"_tile_{name}.tif")
        try:
            qroi = ee.Geometry.Rectangle(qb)
            url = image.clip(qroi).toFloat().getDownloadURL(
                {"region": qroi, "scale": scale, "format": "GEO_TIFF", "crs": "EPSG:4326"})
            _fetch(url, tp)
            tiles.append(tp)
        except Exception as ex:
            print(f"  ⚠ Tile {name}: {ex}")
    if not tiles:
        return False
    datasets = [rasterio.open(t) for t in tiles]
    merged, transform = merge(datasets)
    profile = datasets[0].profile.copy()
    profile.update(width=merged.shape[2], height=merged.shape[1], transform=transform, count=merged.shape[0])
    for ds in datasets: ds.close()
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(merged)
    for t in tiles:
        try: os.unlink(t)
        except: pass
    return True


def validate_tiff(path):
    import rasterio
    if not os.path.exists(path) or os.path.getsize(path) < 100000:
        return False
    try:
        with rasterio.open(path) as ds:
            if ds.count < 1 or ds.width < 50: return False
            print(f"  ✓ Valid: {ds.width}×{ds.height}, {ds.count} bands, {ds.crs}")
            return True
    except: return False

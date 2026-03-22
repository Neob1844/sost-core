#!/usr/bin/env python3
"""Download Sentinel-2 L2A for GeaSpirit Platform pilot zones via Google Earth Engine.

Prerequisites: pip install earthengine-api && earthengine authenticate
Usage: python3 scripts/download_sentinel2.py --zone chuquicamata
"""
import argparse
import os
import sys
import time
import requests
from pathlib import Path

ZONES = {
    "chuquicamata": {"center": (-22.3, -68.9), "desc": "Atacama Cu"},
    "pilbara":      {"center": (-22.0, 118.0), "desc": "Pilbara Fe+Au"},
    "zambia":        {"center": (-12.8, 28.2),  "desc": "Zambian Cu"},
}

BANDS = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
HALF_SIZE_DEG = 0.25  # ~50km diameter bbox (0.25° ≈ 27km, so ±0.25 ≈ 54km)


def get_bbox(center):
    """Return [west, south, east, north] from center point."""
    lat, lon = center
    return [lon - HALF_SIZE_DEG, lat - HALF_SIZE_DEG,
            lon + HALF_SIZE_DEG, lat + HALF_SIZE_DEG]


def download_tile(image, roi, output_path, scale):
    """Download a single tile using getDownloadURL."""
    import ee
    url = image.getDownloadURL({
        "bands": BANDS,
        "region": roi,
        "scale": scale,
        "format": "GEO_TIFF",
        "crs": "EPSG:4326",
    })
    print(f"  → Downloading from GEE ({scale}m)...")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    total = 0
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            total += len(chunk)
    mb = total / (1024 * 1024)
    print(f"  → Downloaded: {mb:.1f} MB")
    return total


def download_tiled(image, bbox, output_path, scale):
    """Split bbox into 4 quadrants and merge if single tile is too large."""
    import ee
    import rasterio
    from rasterio.merge import merge

    w, s, e, n = bbox
    mid_lon = (w + e) / 2
    mid_lat = (s + n) / 2
    quads = [
        ("NW", [w, mid_lat, mid_lon, n]),
        ("NE", [mid_lon, mid_lat, e, n]),
        ("SW", [w, s, mid_lon, mid_lat]),
        ("SE", [mid_lon, s, e, mid_lat]),
    ]

    tile_paths = []
    parent = Path(output_path).parent
    for name, qbbox in quads:
        tile_path = parent / f"_tile_{name}.tif"
        roi = ee.Geometry.Rectangle(qbbox)
        print(f"  → Tile {name}: {qbbox}")
        try:
            download_tile(image, roi, str(tile_path), scale)
            tile_paths.append(str(tile_path))
        except Exception as ex:
            print(f"  ⚠ Tile {name} failed: {ex}")

    if not tile_paths:
        return False

    # Merge tiles
    print(f"  → Merging {len(tile_paths)} tiles...")
    datasets = [rasterio.open(p) for p in tile_paths]
    merged, transform = merge(datasets)
    profile = datasets[0].profile.copy()
    profile.update(width=merged.shape[2], height=merged.shape[1],
                   transform=transform, count=merged.shape[0])
    for ds in datasets:
        ds.close()

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(merged)

    # Cleanup tiles
    for p in tile_paths:
        try:
            os.unlink(p)
        except OSError:
            pass

    return True


def validate_tiff(path):
    """Validate the downloaded GeoTIFF."""
    import rasterio
    if not os.path.exists(path):
        return False, "File does not exist"
    sz = os.path.getsize(path)
    if sz < 100000:
        return False, f"File too small ({sz} bytes)"
    try:
        with rasterio.open(path) as ds:
            if ds.count < 1:
                return False, "No bands"
            if ds.width < 50 or ds.height < 50:
                return False, f"Too small: {ds.width}x{ds.height}"
            crs = ds.crs
            return True, f"{ds.width}x{ds.height} pixels, {ds.count} bands, CRS={crs}"
    except Exception as e:
        return False, f"rasterio error: {e}"


def main():
    parser = argparse.ArgumentParser(description="Download Sentinel-2 for GeaSpirit Platform pilot zone")
    parser.add_argument("--zone", default="chuquicamata", choices=list(ZONES.keys()))
    parser.add_argument("--output", default=None, help="Output .tif path")
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--max-cloud", type=int, default=10)
    parser.add_argument("--scale", type=int, default=20, help="Resolution in meters")
    args = parser.parse_args()

    if args.output is None:
        args.output = os.path.expanduser(f"~/SOST/geaspirit/data/sentinel2/{args.zone}_s2.tif")

    output_path = str(Path(args.output).expanduser().resolve())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    zone = ZONES[args.zone]
    bbox = get_bbox(zone["center"])

    print(f"{'='*60}")
    print(f"  GeaSpirit Platform — Sentinel-2 Download")
    print(f"  Zone: {args.zone} ({zone['desc']})")
    print(f"  BBox: {bbox}")
    print(f"  Date: {args.start_date} to {args.end_date}")
    print(f"  Max cloud: {args.max_cloud}%")
    print(f"  Scale: {args.scale}m")
    print(f"  Output: {output_path}")
    print(f"{'='*60}")

    # Initialize Earth Engine
    print("→ Initializing Earth Engine...")
    import ee
    try:
        ee.Initialize(project="ee-sost-geaspirit")
    except Exception as e:
        print(f"✗ EE init failed: {e}")
        print("  Run: earthengine authenticate")
        sys.exit(1)
    print("  ✓ Earth Engine ready")

    # Search images
    print(f"→ Searching Sentinel-2 images...")
    roi = ee.Geometry.Rectangle(bbox)
    collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                  .filterBounds(roi)
                  .filterDate(args.start_date, args.end_date)
                  .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", args.max_cloud))
                  .sort("CLOUDY_PIXEL_PERCENTAGE"))

    count = collection.size().getInfo()
    if count == 0:
        print(f"✗ No images found. Try --max-cloud 20 or wider date range.")
        sys.exit(1)

    best_cloud = collection.first().get("CLOUDY_PIXEL_PERCENTAGE").getInfo()
    print(f"  ✓ Found {count} images, best cloud cover: {best_cloud:.1f}%")

    # Select best image
    image = collection.first().select(BANDS).clip(roi)

    # Try direct download first
    print(f"→ Attempting direct download ({len(BANDS)} bands, {args.scale}m)...")
    try:
        download_tile(image, roi, output_path, args.scale)
    except Exception as e:
        err = str(e)
        if "50331648" in err or "50MB" in err.upper() or "request size" in err.lower():
            print(f"  ⚠ Too large for single download. Splitting into 4 tiles...")
            ok = download_tiled(image, bbox, output_path, args.scale)
            if not ok:
                print("✗ Tiled download also failed.")
                sys.exit(1)
        else:
            print(f"✗ Download failed: {e}")
            sys.exit(1)

    # Validate
    print("→ Validating GeoTIFF...")
    valid, msg = validate_tiff(output_path)
    if valid:
        print(f"✓ Valid GeoTIFF: {msg}")
        print(f"✓ Saved: {output_path}")
    else:
        print(f"✗ Invalid: {msg}")
        try:
            os.unlink(output_path)
        except OSError:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()

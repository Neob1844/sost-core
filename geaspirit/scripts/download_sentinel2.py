#!/usr/bin/env python3
"""Download Sentinel-2 L2A for pilot zones via Google Earth Engine.

Prerequisites: pip install earthengine-api geemap && earthengine authenticate
Usage: python3 scripts/download_sentinel2.py --zone chuquicamata
"""
import argparse
import json
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Download Sentinel-2 for pilot zone")
    parser.add_argument("--zone", default="chuquicamata", choices=["chuquicamata", "pilbara", "zambia_copperbelt"])
    parser.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/data/sentinel2"))
    args = parser.parse_args()

    config_path = os.path.expanduser("~/SOST/geaspirit/config.json")
    if not os.path.exists(config_path):
        print("Run setup_geaspirit.py first")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    zone = config["pilot_zones"][args.zone]
    bbox = zone["bbox"]
    s2_params = config["sentinel2_params"]

    try:
        import ee
        ee.Initialize()
    except Exception as e:
        print(f"GEE not authenticated. Run: earthengine authenticate")
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Searching Sentinel-2 for {args.zone}...")
    roi = ee.Geometry.Rectangle([bbox[1], bbox[0], bbox[3], bbox[2]])

    collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                  .filterBounds(roi)
                  .filterDate(*s2_params["date_range"].split("/"))
                  .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", s2_params["cloud_cover_max"]))
                  .sort("CLOUDY_PIXEL_PERCENTAGE")
                  .first())

    if collection is None:
        print("No images found. Try wider date range or higher cloud tolerance.")
        sys.exit(1)

    bands = s2_params["bands"]
    image = collection.select(bands).clip(roi)

    os.makedirs(args.output, exist_ok=True)
    out_path = os.path.join(args.output, f"{args.zone}_s2.tif")

    print(f"Exporting to {out_path}...")
    try:
        import geemap
        geemap.ee_export_image(image, filename=out_path, scale=20, region=roi, file_per_band=False)
        print(f"✓ Saved: {out_path}")
    except Exception as e:
        print(f"Export failed: {e}")
        print("Try using GEE Code Editor for manual export, or use Copernicus Data Space.")

if __name__ == "__main__":
    main()

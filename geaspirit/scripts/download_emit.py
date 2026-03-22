#!/usr/bin/env python3
"""Download EMIT hyperspectral data for GeaSpirit Platform pilot zones.

EMIT data is available from NASA Earthdata (requires free account).
Coverage: ISS orbit (~52°N-52°S), not global.

Usage: python3 scripts/download_emit.py --zone chuquicamata --output data/emit/
"""
import argparse
import json
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Download EMIT hyperspectral data for pilot zone")
    parser.add_argument("--zone", default="chuquicamata",
                        choices=["chuquicamata", "pilbara", "zambia_copperbelt"])
    parser.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/data/emit"))
    args = parser.parse_args()

    config_path = os.path.expanduser("~/SOST/geaspirit/config.json")
    if not os.path.exists(config_path):
        print("Run setup_geaspirit.py first")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)
    zone = config["pilot_zones"][args.zone]
    lat, lon = zone["center"]

    print(f"EMIT Data Access for {args.zone} (center: {lat}, {lon})")
    print(f"{'='*50}")
    print()
    print("EMIT (Earth Surface Mineral Dust Source Investigation)")
    print("- 285 spectral bands, 380-2500nm, ~60m resolution")
    print("- ISS orbit: ~52°N to ~52°S coverage")
    print("- Free via NASA Earthdata")
    print()

    # Check if zone is within EMIT coverage
    if abs(lat) > 52:
        print(f"⚠ Zone {args.zone} at latitude {lat}° is OUTSIDE EMIT coverage (±52°)")
        return

    print(f"✓ Zone {args.zone} at latitude {lat}° is within EMIT coverage")
    print()
    print("To download EMIT data:")
    print("1. Create account at https://urs.earthdata.nasa.gov")
    print("2. Search EMIT data at https://search.earthdata.nasa.gov/")
    print(f"   - Search term: 'EMIT L2A Mineral'")
    print(f"   - Bounding box: {zone['bbox']}")
    print(f"   - Date range: 2023-01-01 to present")
    print("3. Download the L2A mineral identification product")
    print(f"4. Save to: {args.output}")
    print()
    print("Alternative: Use earthaccess Python package:")
    print("  pip install earthaccess")
    print("  import earthaccess")
    print("  earthaccess.login()")
    print(f"  results = earthaccess.search_data(short_name='EMITL2ARFL',")
    print(f"      bounding_box=({zone['bbox'][1]},{zone['bbox'][0]},{zone['bbox'][3]},{zone['bbox'][2]}))")

    os.makedirs(args.output, exist_ok=True)

if __name__ == "__main__":
    main()

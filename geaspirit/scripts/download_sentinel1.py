#!/usr/bin/env python3
"""Download Sentinel-1 SAR data for Geaspirit Platform pilot zones.

Uses ASF (Alaska Satellite Facility) search API — free, no auth for search.
Download requires NASA Earthdata account.

Usage: python3 scripts/download_sentinel1.py --zone chuquicamata --output data/sentinel1/
"""
import argparse
import json
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Download Sentinel-1 SAR for pilot zone")
    parser.add_argument("--zone", default="chuquicamata",
                        choices=["chuquicamata", "pilbara", "zambia_copperbelt"])
    parser.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/data/sentinel1"))
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2025-01-01")
    args = parser.parse_args()

    config_path = os.path.expanduser("~/SOST/geaspirit/config.json")
    if not os.path.exists(config_path):
        print("Run setup_geaspirit.py first")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)
    zone = config["pilot_zones"][args.zone]
    bbox = zone["bbox"]

    # ASF search API (no auth required for search)
    import requests
    url = "https://api.daac.asf.alaska.edu/services/search/param"
    params = {
        "platform": "SENTINEL-1",
        "processingLevel": "GRD_HD",
        "beamMode": "IW",
        "start": args.start_date,
        "end": args.end_date,
        "bbox": f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}",
        "output": "json",
        "maxResults": 5,
    }

    print(f"Searching ASF for Sentinel-1 over {args.zone}...")
    try:
        r = requests.get(url, params=params, timeout=30)
        results = r.json()
        scenes = results if isinstance(results, list) else results.get("results", [])
        print(f"  Found {len(scenes)} scenes")

        os.makedirs(args.output, exist_ok=True)
        # Save search results
        with open(os.path.join(args.output, f"{args.zone}_s1_search.json"), "w") as f:
            json.dump(scenes[:5], f, indent=2)

        if scenes:
            print(f"\n  To download, you need NASA Earthdata credentials.")
            print(f"  Register at: https://urs.earthdata.nasa.gov")
            print(f"  Then download URLs from the search results JSON.")
            for s in scenes[:3]:
                name = s.get("granuleName", s.get("fileName", "unknown"))
                url = s.get("downloadUrl", s.get("url", ""))
                print(f"  - {name}")
                if url:
                    print(f"    {url}")
    except Exception as e:
        print(f"  Search failed: {e}")
        print(f"  Try manual search at: https://search.asf.alaska.edu/")

if __name__ == "__main__":
    main()

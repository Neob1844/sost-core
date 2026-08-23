#!/usr/bin/env python3
"""Define an Area of Interest (AOI) by coordinates.

Creates a JSON definition that the entire GeaSpirit pipeline can use.
Works for any location on Earth — not limited to predefined pilot zones.
"""
import argparse, os, json, math
from datetime import datetime


def main():
    p = argparse.ArgumentParser(description="Define a GeaSpirit AOI")
    p.add_argument("--name", required=True, help="AOI identifier (e.g. kalgoorlie_50km)")
    p.add_argument("--center-lat", type=float, required=True)
    p.add_argument("--center-lon", type=float, required=True)
    p.add_argument("--width-km", type=float, default=50)
    p.add_argument("--height-km", type=float, default=None, help="Defaults to width-km")
    p.add_argument("--crs", default="EPSG:4326")
    p.add_argument("--notes", default="")
    p.add_argument("--output-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    args = p.parse_args()

    if args.height_km is None:
        args.height_km = args.width_km

    # Convert km to degrees (approximate)
    lat_deg_per_km = 1.0 / 111.0
    lon_deg_per_km = 1.0 / (111.0 * math.cos(math.radians(args.center_lat)))

    half_w_deg = (args.width_km / 2.0) * lon_deg_per_km
    half_h_deg = (args.height_km / 2.0) * lat_deg_per_km

    bbox = [
        round(args.center_lon - half_w_deg, 6),
        round(args.center_lat - half_h_deg, 6),
        round(args.center_lon + half_w_deg, 6),
        round(args.center_lat + half_h_deg, 6),
    ]

    area_km2 = round(args.width_km * args.height_km, 1)

    aoi = {
        "name": args.name,
        "center": [args.center_lat, args.center_lon],
        "bbox": bbox,
        "width_km": args.width_km,
        "height_km": args.height_km,
        "area_km2": area_km2,
        "half_deg_lat": round(half_h_deg, 6),
        "half_deg_lon": round(half_w_deg, 6),
        "crs": args.crs,
        "notes": args.notes,
        "created": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, f"{args.name}.json")
    with open(out_path, "w") as f:
        json.dump(aoi, f, indent=2)

    print(f"AOI defined: {args.name}")
    print(f"  Center: ({args.center_lat}, {args.center_lon})")
    print(f"  Size: {args.width_km} x {args.height_km} km ({area_km2} km²)")
    print(f"  BBox: {bbox}")
    print(f"  Saved: {out_path}")


if __name__ == "__main__":
    main()

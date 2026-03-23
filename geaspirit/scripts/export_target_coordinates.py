#!/usr/bin/env python3
"""Export exact target coordinates for all AOIs with scan results."""
import argparse, os, sys, json, csv, glob
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    p = argparse.ArgumentParser(description="Export exact target coordinates")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    p.add_argument("--aoi-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    args = p.parse_args()

    os.makedirs(args.output, exist_ok=True)
    all_targets = []

    # Find all existing target CSVs
    for csv_file in sorted(glob.glob(os.path.join(args.output, "*_proxy_targets.csv")) +
                           glob.glob(os.path.join(args.output, "*_targets.csv"))):
        aoi_name = os.path.basename(csv_file).replace("_proxy_targets.csv", "").replace("_targets.csv", "")
        try:
            with open(csv_file, newline="") as f:
                reader = list(csv.DictReader(f))
            if not reader:
                continue
            for row in reader[:20]:  # top 20 per AOI
                target = {
                    "aoi": aoi_name,
                    "rank": row.get("rank", ""),
                    "centroid_lat": row.get("centroid_lat", ""),
                    "centroid_lon": row.get("centroid_lon", ""),
                    "area_pixels": row.get("area_pixels", ""),
                    "area_km2": row.get("area_km2", ""),
                    "score": row.get("mean_score", row.get("mean_probability", row.get("score", ""))),
                    "score_type": row.get("score_type", "heuristic"),
                }
                all_targets.append(target)
        except Exception:
            continue

    if not all_targets:
        print("No target files found.")
        return

    # Deduplicate and sort
    all_targets.sort(key=lambda t: (-float(t.get("score", 0) or 0)))

    # Export combined CSV
    combined_path = os.path.join(args.output, "all_targets_with_coordinates.csv")
    fieldnames = ["aoi", "rank", "centroid_lat", "centroid_lon", "area_pixels", "area_km2", "score", "score_type"]
    with open(combined_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for t in all_targets:
            w.writerow(t)

    # Export summary markdown
    md = "# All GeaSpirit Targets with Exact Coordinates\n\n"
    md += f"Total targets: {len(all_targets)} across {len(set(t['aoi'] for t in all_targets))} AOIs\n\n"

    # Group by AOI
    aoi_groups = {}
    for t in all_targets:
        aoi_groups.setdefault(t["aoi"], []).append(t)

    for aoi, targets in sorted(aoi_groups.items()):
        md += f"## {aoi} ({len(targets)} targets)\n\n"
        md += "| Rank | Lat | Lon | Area km2 | Score |\n|------|-----|-----|----------|-------|\n"
        for t in targets[:10]:
            md += f"| {t['rank']} | {t['centroid_lat']} | {t['centroid_lon']} | {t.get('area_km2','')} | {t['score']} |\n"
        md += "\n"

    with open(os.path.join(args.output, "all_targets_with_coordinates.md"), "w") as f:
        f.write(md)

    print(f"Exported {len(all_targets)} targets across {len(aoi_groups)} AOIs")
    for aoi, targets in sorted(aoi_groups.items()):
        print(f"  {aoi}: {len(targets)} targets")


if __name__ == "__main__":
    main()

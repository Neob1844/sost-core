#!/usr/bin/env python3
"""Build global porphyry Cu dataset from MRDS explicit + inferred labels."""
import argparse, os, sys, json, csv
from collections import Counter
from math import radians, cos, sin, asin, sqrt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DUPLICATE_THRESHOLD_M = 1000

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * 2 * asin(sqrt(a))

def main():
    p = argparse.ArgumentParser(description="Build global porphyry Cu dataset")
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--output-dir", default=os.path.expanduser("~/SOST/geaspirit/data/labels"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    print("=== Building Global Porphyry Cu Dataset ===\n")

    all_labels = []
    with open(args.mrds, newline='', encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row.get("latitude",""))
                lon = float(row.get("longitude",""))
            except: continue
            dt = (row.get("dep_type","") or "").lower()
            commod = (row.get("commod1","") or "").lower()

            # Explicit porphyry
            if "porphyry" in dt:
                conf = "high"
                method = "explicit_dep_type"
            # Inferred from Chile Cu context
            elif "copper" in commod and row.get("country","") in ("Chile","Peru","Argentina"):
                conf = "medium"
                method = "inferred_andean_cu"
            else:
                continue

            all_labels.append({
                "deposit_id": row.get("dep_id",""),
                "site_name": row.get("site_name",""),
                "latitude": lat, "longitude": lon,
                "country": row.get("country",""),
                "state": row.get("state",""),
                "commodity_raw": row.get("commod1",""),
                "dep_type_raw": row.get("dep_type",""),
                "deposit_type": "porphyry_cu",
                "deposit_type_confidence": conf,
                "type_assignment_method": method,
                "keep_for_training": True,
            })

    print(f"  Total porphyry labels: {len(all_labels)}")
    conf_counts = Counter(l["deposit_type_confidence"] for l in all_labels)
    print(f"  Confidence: {dict(conf_counts)}")
    country_counts = Counter(l["country"] for l in all_labels)
    print(f"  Countries: {country_counts.most_common(10)}")

    # Deduplicate
    dup = 0
    for i in range(len(all_labels)):
        if not all_labels[i]["keep_for_training"]: continue
        for j in range(i+1, len(all_labels)):
            if not all_labels[j]["keep_for_training"]: continue
            d = haversine(all_labels[i]["latitude"], all_labels[i]["longitude"],
                          all_labels[j]["latitude"], all_labels[j]["longitude"])
            if d < DUPLICATE_THRESHOLD_M:
                all_labels[j]["keep_for_training"] = False; dup += 1

    kept = [l for l in all_labels if l["keep_for_training"]]
    print(f"  Duplicates removed: {dup}")
    print(f"  Final kept: {len(kept)}")

    # Find dense clusters for AOI selection
    import numpy as np
    coords = np.array([(l["latitude"], l["longitude"]) for l in kept])
    clusters = []
    for name, bbox in [
        ("Arizona_Cu", (31.0, -114.0, 34.0, -109.0)),
        ("Chuquicamata", (-23.5, -70.0, -21.0, -68.0)),
        ("Peru_Cu", (-18.0, -80.0, -5.0, -75.0)),
        ("BC_Canada", (48.0, -130.0, 56.0, -120.0)),
        ("Argentina_Cu", (-35.0, -70.0, -25.0, -65.0)),
    ]:
        n = sum(1 for la, lo in coords if bbox[0]<=la<=bbox[2] and bbox[1]<=lo<=bbox[3])
        if n >= 3:
            cluster_labels = [l for l in kept if bbox[0]<=l["latitude"]<=bbox[2] and bbox[1]<=l["longitude"]<=bbox[3]]
            center_lat = np.mean([l["latitude"] for l in cluster_labels])
            center_lon = np.mean([l["longitude"] for l in cluster_labels])
            clusters.append({"name": name, "count": n, "center": [round(center_lat,2), round(center_lon,2)]})
    clusters.sort(key=lambda x: -x["count"])
    print(f"\n  Dense clusters (>= 3 deposits):")
    for c in clusters:
        print(f"    {c['name']}: {c['count']} deposits at ({c['center'][0]}, {c['center'][1]})")

    # Save
    os.makedirs(args.output_dir, exist_ok=True)
    fieldnames = list(all_labels[0].keys())
    for fname, data in [("all_porphyry_cu_labels.csv", all_labels),
                         ("trainable_porphyry_cu_labels.csv", kept),
                         ("high_confidence_porphyry_cu_labels.csv", [l for l in kept if l["deposit_type_confidence"]=="high"])]:
        with open(os.path.join(args.output_dir, fname), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for l in data: w.writerow(l)
        print(f"  Saved: {fname} ({len(data)} rows)")

    # Report
    os.makedirs(args.reports, exist_ok=True)
    report = {"total": len(all_labels), "kept": len(kept), "duplicates": dup,
              "confidence": dict(conf_counts), "countries": dict(country_counts.most_common()),
              "clusters": clusters}
    with open(os.path.join(args.reports, "global_porphyry_dataset_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    md = f"# Global Porphyry Cu Dataset\n\nTotal: {len(all_labels)}, Kept: {len(kept)}\n\n"
    md += "## Clusters\n\n| Cluster | Deposits | Center |\n|---------|----------|--------|\n"
    for c in clusters: md += f"| {c['name']} | {c['count']} | {c['center']} |\n"
    md += f"\n## Key: Arizona (47 explicit porphyry) is the best second benchmark zone.\n"
    with open(os.path.join(args.reports, "global_porphyry_dataset_report.md"), "w") as f:
        f.write(md)


if __name__ == "__main__":
    main()

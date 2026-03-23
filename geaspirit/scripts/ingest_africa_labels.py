#!/usr/bin/env python3
"""Ingest African mineral labels — MRDS extraction for Zambia Copperbelt.

MRDS has 177 deposits in wider Zambia, 60 Cu in the Copperbelt region.
The original 50km AOI captured only 14. Expanding to ~100km captures 60.

Future: integrate USGS Africa Mineral Industries GIS (607611a9d34e018b3201cbbf)
for additional 500+ Cu occurrences. Requires 135MB geodatabase download.
"""
import argparse, os, sys, json, csv
from collections import Counter
from math import radians, cos, sin, asin, sqrt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

METAL_KEYWORDS = {
    "copper": "Cu", "gold": "Au", "silver": "Ag", "iron": "Fe",
    "cobalt": "Co", "lead": "Pb", "zinc": "Zn", "nickel": "Ni",
    "manganese": "Mn", "platinum": "Pt",
}
EXCLUDE_KEYWORDS = {"talc", "soapstone", "diatomite", "limestone", "gypsum", "clay", "salt"}

DUPLICATE_THRESHOLD_M = 500

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * 2 * asin(sqrt(a))

def classify(text):
    if not text: return set()
    lower = text.lower()
    for excl in EXCLUDE_KEYWORDS:
        if excl in lower: return set()
    metals = set()
    for kw, code in METAL_KEYWORDS.items():
        if kw in lower: metals.add(code)
    return metals

def classify_deposit_type(dep_type_raw, commod):
    """Classify deposit type from MRDS dep_type field."""
    if not dep_type_raw: return "unknown", "not_available"
    dt = dep_type_raw.lower()
    if "sediment" in dt and "copper" in dt.lower() or "sediment" in dt and "cu" in dt:
        return "sediment_hosted_cu", "source_field"
    if "porphyry" in dt: return "porphyry_cu", "source_field"
    if "massive sulfide" in dt or "vms" in dt: return "vms", "source_field"
    if "orogenic" in dt: return "orogenic_au", "source_field"
    if "stratabound" in dt: return "sediment_hosted_cu", "inferred_from_stratabound"
    # Infer from commodity + region
    if commod and "copper" in commod.lower():
        return "sediment_hosted_cu", "inferred_from_commodity_zambia"
    return "unknown", "not_classifiable"


def main():
    p = argparse.ArgumentParser(description="Ingest African mineral labels for Zambia")
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--bbox", default="27.0,-13.5,29.5,-11.5", help="min_lon,min_lat,max_lon,max_lat")
    p.add_argument("--output-dir", default=os.path.expanduser("~/SOST/geaspirit/data/labels"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    p.add_argument("--aoi-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    args = p.parse_args()

    bbox = [float(x) for x in args.bbox.split(",")]
    min_lon, min_lat, max_lon, max_lat = bbox

    print(f"=== African Label Ingestion — Zambia Copperbelt ===")
    print(f"  BBox: {bbox}")

    # Extract from MRDS
    raw = []
    with open(args.mrds, newline='', encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            try:
                lat, lon = float(row.get("latitude","")), float(row.get("longitude",""))
            except: continue
            if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                raw.append(row)

    print(f"  MRDS deposits in region: {len(raw)}")

    # Curate
    curated = []
    for row in raw:
        lat, lon = float(row["latitude"]), float(row["longitude"])
        metals = classify(row.get("commod1",""))
        if not metals:
            metals = classify(row.get("commod2",""))
        if not metals: continue

        dep_type_raw = row.get("dep_type","").strip()
        dep_type, dt_method = classify_deposit_type(dep_type_raw, row.get("commod1",""))

        quality = 50
        if "." in row.get("latitude","") and len(row["latitude"].split(".")[1]) >= 3: quality += 15
        if row.get("commod1",""): quality += 10
        if dep_type_raw: quality += 10
        if row.get("site_name",""): quality += 5
        quality = min(100, quality)

        curated.append({
            "deposit_id": row.get("dep_id",""),
            "site_name": row.get("site_name",""),
            "latitude": lat, "longitude": lon,
            "commodity_codes": ",".join(sorted(metals)),
            "commodity_raw": row.get("commod1",""),
            "deposit_type": dep_type,
            "deposit_type_confidence": dt_method,
            "deposit_type_raw": dep_type_raw,
            "quality_score": quality,
            "source_dataset": "MRDS",
            "keep_for_training": quality >= 30,
        })

    # Deduplicate
    dup_count = 0
    for i in range(len(curated)):
        if not curated[i]["keep_for_training"]: continue
        for j in range(i+1, len(curated)):
            if not curated[j]["keep_for_training"]: continue
            dist = haversine(curated[i]["latitude"], curated[i]["longitude"],
                             curated[j]["latitude"], curated[j]["longitude"])
            if dist < DUPLICATE_THRESHOLD_M:
                if curated[i]["quality_score"] >= curated[j]["quality_score"]:
                    curated[j]["keep_for_training"] = False
                else:
                    curated[i]["keep_for_training"] = False
                dup_count += 1

    kept = sum(1 for d in curated if d["keep_for_training"])
    print(f"  Metal deposits: {len(curated)}")
    print(f"  Duplicates removed: {dup_count}")
    print(f"  Final kept: {kept}")

    # Per-AOI extraction
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.reports, exist_ok=True)

    csv_path = os.path.join(args.output_dir, "zambia_labels_enriched.csv")
    fieldnames = list(curated[0].keys()) if curated else []
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for d in curated:
            w.writerow(d)

    comm_counts = Counter()
    type_counts = Counter()
    for d in curated:
        if d["keep_for_training"]:
            for c in d["commodity_codes"].split(","):
                if c: comm_counts[c] += 1
            type_counts[d["deposit_type"]] += 1

    print(f"  Commodities: {dict(comm_counts)}")
    print(f"  Deposit types: {dict(type_counts)}")

    report = {
        "source": "USGS MRDS", "region_bbox": bbox,
        "total_raw": len(raw), "metal_curated": len(curated),
        "duplicates_removed": dup_count, "final_kept": kept,
        "commodities": dict(comm_counts), "deposit_types": dict(type_counts),
        "note": "Africa GIS (USGS 607611a9d34e018b3201cbbf) not yet integrated — 135MB geodatabase",
    }
    with open(os.path.join(args.reports, "zambia_label_enrichment_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    md = f"# Zambia Label Enrichment Report\n\n"
    md += f"## Source: MRDS (wider Copperbelt region)\n"
    md += f"- BBox: {bbox}\n- Raw: {len(raw)}\n- Metal: {len(curated)}\n"
    md += f"- Duplicates: {dup_count}\n- **Final kept: {kept}**\n\n"
    md += f"## Commodities\n"
    for c, n in comm_counts.most_common(): md += f"- {c}: {n}\n"
    md += f"\n## Deposit Types\n"
    for t, n in type_counts.most_common(): md += f"- {t}: {n}\n"
    md += f"\n## vs Previous\n- Phase 4E: 11 deposits (50km AOI)\n- Phase 4F: **{kept} deposits** (wider region)\n"
    md += f"\n## Pending: USGS Africa Mineral GIS\n"
    md += f"135MB geodatabase at ScienceBase. Would add hundreds more Cu occurrences.\n"

    with open(os.path.join(args.reports, "zambia_label_enrichment_report.md"), "w") as f:
        f.write(md)
    print(f"  Saved: zambia_labels_enriched.csv + report")


if __name__ == "__main__":
    main()

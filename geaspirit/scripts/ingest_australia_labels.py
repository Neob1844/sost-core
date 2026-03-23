#!/usr/bin/env python3
"""Ingest Australian mineral deposit labels from MRDS + supplementary sources.

MRDS has 1233 Australian deposits. For Kalgoorlie specifically, there are
~40 Au/Cu/Ni deposits within a 50km window — enough for supervised ML.

This script:
1. Extracts all Australian metal deposits from MRDS
2. Curates by commodity, quality, and location
3. Exports per-AOI label files
4. Documents everything with full traceability
"""
import argparse, os, sys, json, csv
from collections import Counter
from math import radians, cos, sin, asin, sqrt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

METAL_KEYWORDS = {
    "copper": "Cu", "gold": "Au", "silver": "Ag", "iron": "Fe",
    "molybdenum": "Mo", "lead": "Pb", "zinc": "Zn", "nickel": "Ni",
    "cobalt": "Co", "manganese": "Mn", "chromium": "Cr", "tungsten": "W",
    "tin": "Sn", "uranium": "U", "lithium": "Li", "platinum": "Pt",
    "palladium": "Pd", "vanadium": "V", "titanium": "Ti", "tantalum": "Ta",
    "niobium": "Nb", "antimony": "Sb", "rare earth": "REE",
}

EXCLUDE_KEYWORDS = {
    "limestone", "dolomite", "silica", "sand", "gravel", "clay",
    "boron", "borate", "gypsum", "anhydrite", "marble", "cement",
    "aggregate", "dimension", "peat", "sodium", "potash", "salt",
    "phosphate", "feldspar", "mica", "talc", "barite",
}

DUPLICATE_THRESHOLD_M = 500


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * 2 * asin(sqrt(a))


def classify_commodity(commod_str):
    if not commod_str:
        return set()
    lower = commod_str.lower()
    for excl in EXCLUDE_KEYWORDS:
        if excl in lower and not any(m in lower for m in ["copper","gold","silver","nickel","iron"]):
            return set()
    metals = set()
    for kw, code in METAL_KEYWORDS.items():
        if kw in lower:
            metals.add(code)
    return metals


def main():
    p = argparse.ArgumentParser(description="Ingest Australian mineral labels from MRDS")
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--output-dir", default=os.path.expanduser("~/SOST/geaspirit/data/labels"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    p.add_argument("--aoi-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.reports, exist_ok=True)

    print("=== Ingesting Australian Mineral Labels ===")

    # Extract all Australian deposits
    aus_raw = []
    with open(args.mrds, newline='', encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            if "Australia" not in row.get("country", ""):
                continue
            try:
                lat = float(row.get("latitude", ""))
                lon = float(row.get("longitude", ""))
            except (ValueError, TypeError):
                continue
            if not (-44 <= lat <= -10 and 112 <= lon <= 154):
                continue
            aus_raw.append(row)

    print(f"  Total Australian deposits in MRDS: {len(aus_raw)}")

    # Classify and curate
    curated = []
    for row in aus_raw:
        lat = float(row["latitude"])
        lon = float(row["longitude"])
        commod1 = row.get("commod1", "").strip()
        commod2 = row.get("commod2", "").strip()
        commod3 = row.get("commod3", "").strip()

        metals = set()
        for c in [commod1, commod2, commod3]:
            metals |= classify_commodity(c)

        if not metals:
            continue

        # Quality score
        quality = 50
        lat_str = row.get("latitude", "")
        if "." in lat_str and len(lat_str.split(".")[1]) >= 3:
            quality += 15
        if commod1:
            quality += 10
        if row.get("dep_type", "").strip():
            quality += 10
        if row.get("dev_stat", "").strip():
            quality += 5
        if row.get("hrock_type", "").strip():
            quality += 5
        quality = min(100, quality)

        curated.append({
            "deposit_id": row.get("dep_id", ""),
            "site_name": row.get("site_name", ""),
            "latitude": lat,
            "longitude": lon,
            "country": "Australia",
            "state": row.get("state", ""),
            "commodity_codes": ",".join(sorted(metals)),
            "commod1_raw": commod1,
            "dep_type": row.get("dep_type", "").strip(),
            "dev_stat": row.get("dev_stat", "").strip(),
            "hrock_type": row.get("hrock_type", "").strip(),
            "quality_score": quality,
            "source": "USGS_MRDS",
            "duplicate_flag": False,
            "keep_for_training": quality >= 30,
        })

    print(f"  Metal deposits retained: {len(curated)}")

    # Deduplicate
    dup_count = 0
    for i in range(len(curated)):
        if not curated[i]["keep_for_training"]:
            continue
        for j in range(i+1, len(curated)):
            if not curated[j]["keep_for_training"]:
                continue
            dist = haversine(curated[i]["latitude"], curated[i]["longitude"],
                             curated[j]["latitude"], curated[j]["longitude"])
            if dist < DUPLICATE_THRESHOLD_M:
                if curated[i]["quality_score"] >= curated[j]["quality_score"]:
                    curated[j]["duplicate_flag"] = True
                    curated[j]["keep_for_training"] = False
                else:
                    curated[i]["duplicate_flag"] = True
                    curated[i]["keep_for_training"] = False
                dup_count += 1

    kept = sum(1 for d in curated if d["keep_for_training"])
    print(f"  Duplicates flagged: {dup_count}")
    print(f"  Final kept: {kept}")

    # Save all Australia labels
    csv_path = os.path.join(args.output_dir, "australia_labels_curated.csv")
    fieldnames = list(curated[0].keys()) if curated else []
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for d in curated:
            w.writerow(d)

    # Per-AOI extraction
    aoi_stats = {}
    import glob
    for aoi_file in glob.glob(os.path.join(args.aoi_dir, "*.json")):
        with open(aoi_file) as f:
            aoi = json.load(f)
        bbox = aoi["bbox"]
        aoi_name = aoi["name"]
        aoi_deps = [d for d in curated if d["keep_for_training"]
                    and bbox[1] <= d["latitude"] <= bbox[3]
                    and bbox[0] <= d["longitude"] <= bbox[2]]
        if aoi_deps:
            aoi_csv = os.path.join(args.output_dir, f"{aoi_name}_labels_curated.csv")
            with open(aoi_csv, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                for d in aoi_deps:
                    w.writerow(d)
            comm_counts = Counter()
            for d in aoi_deps:
                for c in d["commodity_codes"].split(","):
                    if c:
                        comm_counts[c] += 1
            aoi_stats[aoi_name] = {"count": len(aoi_deps), "commodities": dict(comm_counts)}
            print(f"  {aoi_name}: {len(aoi_deps)} deposits — {dict(comm_counts)}")

    # Also count for known zones
    for zone_name, zone_bbox in [("kalgoorlie", [121.2, -31.9, 122.2, -30.9]),
                                  ("pilbara", [118.7, -23.6, 119.7, -22.6])]:
        if zone_name not in aoi_stats:
            zone_deps = [d for d in curated if d["keep_for_training"]
                         and zone_bbox[1] <= d["latitude"] <= zone_bbox[3]
                         and zone_bbox[0] <= d["longitude"] <= zone_bbox[2]]
            comm_counts = Counter()
            for d in zone_deps:
                for c in d["commodity_codes"].split(","):
                    if c:
                        comm_counts[c] += 1
            aoi_stats[zone_name] = {"count": len(zone_deps), "commodities": dict(comm_counts)}
            print(f"  {zone_name} (estimate): {len(zone_deps)} deposits — {dict(comm_counts)}")

    # Report
    report = {
        "source": "USGS MRDS (mrds.csv)",
        "license": "Public domain (US Government)",
        "total_australian_raw": len(aus_raw),
        "total_metal_curated": len(curated),
        "duplicates_removed": dup_count,
        "final_kept": kept,
        "per_aoi": aoi_stats,
        "commodity_global": dict(Counter(
            c for d in curated if d["keep_for_training"]
            for c in d["commodity_codes"].split(",") if c
        ).most_common()),
        "limitations": [
            "MRDS is US-centric — Australian coverage is limited (~1233 records)",
            "No OZMIN/MINEDEX integration yet (requires manual download from GA/DMIRS portals)",
            "Coordinate precision varies — some deposits have coarse locations",
            "Commodity classifications are text-based, not standardized codes",
        ],
    }
    with open(os.path.join(args.reports, "australia_labels_ingestion_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    md = "# Australian Mineral Labels Ingestion Report\n\n"
    md += f"## Source: USGS MRDS\n"
    md += f"- License: Public domain\n"
    md += f"- Total Australian: {len(aus_raw)}\n"
    md += f"- Metal deposits: {len(curated)}\n"
    md += f"- Duplicates removed: {dup_count}\n"
    md += f"- Final kept: {kept}\n\n"
    md += f"## Per-AOI Coverage\n\n"
    md += "| AOI | Deposits | Top Commodities |\n|-----|----------|-----------------|\n"
    for name, stats in aoi_stats.items():
        comms = ", ".join(f"{k}:{v}" for k, v in sorted(stats["commodities"].items(), key=lambda x: -x[1])[:5])
        md += f"| {name} | {stats['count']} | {comms} |\n"
    md += f"\n## Limitations\n\n"
    for lim in report["limitations"]:
        md += f"- {lim}\n"
    md += f"\n## OZMIN/MINEDEX Status\n"
    md += f"OZMIN (Geoscience Australia) and MINEDEX (DMIRS Western Australia) are national/state\n"
    md += f"mineral databases with thousands more deposits. They require manual download from:\n"
    md += f"- https://portal.ga.gov.au (OZMIN)\n"
    md += f"- https://minedex.dmirs.wa.gov.au (MINEDEX/WA)\n"
    md += f"Integration planned for future phase.\n"

    with open(os.path.join(args.reports, "australia_labels_ingestion_report.md"), "w") as f:
        f.write(md)
    print(f"\n  Saved: australia_labels_curated.csv + report")


if __name__ == "__main__":
    main()

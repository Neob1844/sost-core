#!/usr/bin/env python3
"""Priority 1 — Curate MRDS labels with full traceability.

Cleans, deduplicates, and scores the MRDS deposit database for each pilot zone.
Every decision is logged. Nothing is silently modified.
"""
import argparse, os, sys, json, csv
from collections import Counter
from math import radians, cos, sin, asin, sqrt
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, HALF_DEG

# MRDS uses full commodity names — map keywords to groups
COMMODITY_KEYWORDS = {
    "copper":    "Cu",   "gold":      "Au",   "silver":     "Ag",
    "iron":      "Fe",   "molybdenum":"Mo",   "lead":       "Pb",
    "zinc":      "Zn",   "nickel":    "Ni",   "cobalt":     "Co",
    "manganese": "Mn",   "chromium":  "Cr",   "tungsten":   "W",
    "tin":       "Sn",   "uranium":   "U",    "lithium":    "Li",
    "platinum":  "Pt",   "palladium": "Pd",   "vanadium":   "V",
    "titanium":  "Ti",   "rhenium":   "Re",   "antimony":   "Sb",
    "rare earth":"REE",
}

# Commodities relevant per pilot zone
ZONE_COMMODITIES = {
    "chuquicamata": {"Cu", "Au", "Mo", "Ag", "Re", "Sb"},
    "pilbara":      {"Fe", "Au", "Mn", "Cu", "Cr", "Ni"},
    "zambia":       {"Cu", "Co", "Zn", "Pb", "Ag", "U"},
}

# Default: accept all metal commodities
DEFAULT_COMMODITIES = set(COMMODITY_KEYWORDS.values())

DUPLICATE_THRESHOLD_M = 500  # deposits closer than this are potential duplicates


def haversine(lat1, lon1, lat2, lon2):
    """Distance in meters between two points."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * asin(sqrt(a))


def main():
    p = argparse.ArgumentParser(description="Curate MRDS labels with traceability")
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/data/mrds"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    zone = ZONES[args.pilot]
    lat_c, lon_c = zone["center"]
    bbox = [lon_c - HALF_DEG, lat_c - HALF_DEG, lon_c + HALF_DEG, lat_c + HALF_DEG]
    min_lon, min_lat, max_lon, max_lat = bbox
    target_commodities = ZONE_COMMODITIES.get(args.pilot, DEFAULT_COMMODITIES)

    print(f"=== MRDS Label Curation — {args.pilot} ===")
    print(f"  AOI: [{min_lat:.2f}, {min_lon:.2f}] to [{max_lat:.2f}, {max_lon:.2f}]")
    print(f"  Target commodities: {sorted(target_commodities)}")

    # 1. Load all deposits in expanded AOI (1.5x buffer for near-boundary checks)
    buf = HALF_DEG * 0.5
    raw_deposits = []
    with open(args.mrds, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row.get('latitude', ''))
                lon = float(row.get('longitude', ''))
            except (ValueError, TypeError):
                continue
            if (min_lat - buf) <= lat <= (max_lat + buf) and \
               (min_lon - buf) <= lon <= (max_lon + buf):
                raw_deposits.append(row)

    print(f"  Raw deposits in expanded AOI: {len(raw_deposits)}")

    # 2. Process each deposit
    curated = []
    warnings = []
    stats = {
        "total_raw": len(raw_deposits),
        "missing_coords": 0,
        "outside_aoi": 0,
        "irrelevant_commodity": 0,
        "duplicates_flagged": 0,
        "low_quality": 0,
        "kept": 0,
    }

    for row in raw_deposits:
        try:
            lat = float(row.get('latitude', ''))
            lon = float(row.get('longitude', ''))
        except (ValueError, TypeError):
            stats["missing_coords"] += 1
            continue

        dep_id = row.get('dep_id', '')
        site_name = row.get('site_name', '')
        commod1 = row.get('commod1', '').strip()
        commod2 = row.get('commod2', '').strip()
        commod3 = row.get('commod3', '').strip()
        dep_type = row.get('dep_type', '').strip()
        dev_stat = row.get('dev_stat', '').strip()
        country = row.get('country', '').strip()
        hrock_type = row.get('hrock_type', '').strip()
        prod_size = row.get('prod_size', '').strip()

        # Check if within strict AOI
        within_aoi = (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon)
        if not within_aoi:
            stats["outside_aoi"] += 1

        # Commodity relevance — MRDS uses full names like "Copper, Silver"
        all_commods = set()
        for c in [commod1, commod2, commod3]:
            if c:
                c_lower = c.lower()
                for keyword, code in COMMODITY_KEYWORDS.items():
                    if keyword in c_lower:
                        all_commods.add(code)
        commodity_match = bool(all_commods & target_commodities)
        commodity_group = ",".join(sorted(all_commods & target_commodities)) if commodity_match else "other"

        if not commodity_match and within_aoi:
            stats["irrelevant_commodity"] += 1

        # Quality score (0-100)
        quality = 50  # base
        # Has coordinates precision (more than 2 decimal places = higher quality)
        lat_str = row.get('latitude', '')
        if '.' in lat_str and len(lat_str.split('.')[1]) >= 3:
            quality += 15
        elif '.' in lat_str and len(lat_str.split('.')[1]) >= 2:
            quality += 5
        # Has commodity info
        if commod1:
            quality += 10
        # Has deposit type
        if dep_type:
            quality += 10
        # Has development status
        if dev_stat:
            quality += 5
        # Has host rock info
        if hrock_type:
            quality += 5
        # Has production size
        if prod_size:
            quality += 5
        quality = min(100, quality)

        if quality < 30:
            stats["low_quality"] += 1

        # Decide keep_for_training
        keep = within_aoi and commodity_match and quality >= 30

        curated.append({
            "deposit_id_clean": dep_id,
            "site_name": site_name,
            "latitude": lat,
            "longitude": lon,
            "country": country,
            "commod1": commod1,
            "commod2": commod2,
            "commod3": commod3,
            "commodity_group": commodity_group,
            "dep_type": dep_type,
            "dev_stat": dev_stat,
            "hrock_type": hrock_type,
            "prod_size": prod_size,
            "label_quality_score": quality,
            "source_dataset": "USGS_MRDS",
            "within_aoi": within_aoi,
            "duplicate_flag": False,  # updated below
            "keep_for_training": keep,
        })

    # 3. Duplicate detection (within AOI deposits that are kept)
    kept_indices = [i for i, d in enumerate(curated) if d["keep_for_training"]]
    duplicate_pairs = []
    for ii in range(len(kept_indices)):
        for jj in range(ii + 1, len(kept_indices)):
            i, j = kept_indices[ii], kept_indices[jj]
            d1, d2 = curated[i], curated[j]
            dist = haversine(d1["latitude"], d1["longitude"],
                             d2["latitude"], d2["longitude"])
            if dist < DUPLICATE_THRESHOLD_M:
                duplicate_pairs.append((i, j, dist))
                # Keep the one with higher quality; flag the other
                if d1["label_quality_score"] >= d2["label_quality_score"]:
                    curated[j]["duplicate_flag"] = True
                    curated[j]["keep_for_training"] = False
                else:
                    curated[i]["duplicate_flag"] = True
                    curated[i]["keep_for_training"] = False

    stats["duplicates_flagged"] = sum(1 for d in curated if d["duplicate_flag"])
    stats["kept"] = sum(1 for d in curated if d["keep_for_training"])

    # Commodity distribution of kept deposits
    commodity_counts = Counter()
    for d in curated:
        if d["keep_for_training"]:
            commodity_counts[d["commodity_group"]] += 1

    print(f"\n  === CURATION RESULTS ===")
    print(f"  Raw in expanded AOI:   {stats['total_raw']}")
    print(f"  Missing coords:        {stats['missing_coords']}")
    print(f"  Outside strict AOI:    {stats['outside_aoi']}")
    print(f"  Irrelevant commodity:  {stats['irrelevant_commodity']}")
    print(f"  Duplicates flagged:    {stats['duplicates_flagged']}")
    print(f"  Low quality (<30):     {stats['low_quality']}")
    print(f"  KEPT for training:     {stats['kept']}")
    print(f"  Commodities: {dict(commodity_counts)}")

    # 4. Export curated CSV
    os.makedirs(args.output, exist_ok=True)
    csv_path = os.path.join(args.output, "mrds_curated.csv")
    fieldnames = list(curated[0].keys()) if curated else []
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for d in curated:
            w.writerow(d)
    print(f"  Saved: {csv_path} ({len(curated)} rows)")

    # 5. Export reports
    os.makedirs(args.reports, exist_ok=True)

    report = {
        "pilot": args.pilot,
        "aoi_bbox": bbox,
        "target_commodities": sorted(target_commodities),
        "stats": stats,
        "commodity_distribution": dict(commodity_counts),
        "duplicate_pairs_found": len(duplicate_pairs),
        "duplicate_threshold_m": DUPLICATE_THRESHOLD_M,
        "quality_distribution": {
            "high_70plus": sum(1 for d in curated if d["label_quality_score"] >= 70),
            "medium_50_70": sum(1 for d in curated if 50 <= d["label_quality_score"] < 70),
            "low_30_50": sum(1 for d in curated if 30 <= d["label_quality_score"] < 50),
            "rejected_below_30": sum(1 for d in curated if d["label_quality_score"] < 30),
        },
        "warnings": [],
    }

    # Warnings
    if stats["kept"] < 10:
        report["warnings"].append(f"Only {stats['kept']} deposits kept — may be too few for robust training")
    if stats["duplicates_flagged"] > stats["kept"] * 0.2:
        report["warnings"].append(f"High duplicate rate: {stats['duplicates_flagged']} of {stats['kept']+stats['duplicates_flagged']}")
    if not commodity_counts:
        report["warnings"].append("No deposits with target commodities found in AOI")

    with open(os.path.join(args.reports, "mrds_curation_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # Markdown report
    md = f"# MRDS Label Curation Report — {args.pilot}\n\n"
    md += f"## AOI\n"
    md += f"- Center: {zone['center']}\n"
    md += f"- BBox: [{min_lat:.2f}, {min_lon:.2f}] to [{max_lat:.2f}, {max_lon:.2f}]\n"
    md += f"- Target commodities: {sorted(target_commodities)}\n\n"
    md += f"## Statistics\n\n"
    md += f"| Metric | Count |\n|--------|-------|\n"
    for k, v in stats.items():
        md += f"| {k.replace('_', ' ').title()} | {v} |\n"
    md += f"\n## Commodity Distribution (kept deposits)\n\n"
    for comm, cnt in commodity_counts.most_common():
        md += f"- **{comm}**: {cnt}\n"
    md += f"\n## Quality Distribution\n\n"
    for level, cnt in report["quality_distribution"].items():
        md += f"- {level}: {cnt}\n"
    if duplicate_pairs:
        md += f"\n## Duplicate Pairs ({len(duplicate_pairs)})\n\n"
        for i, j, dist in duplicate_pairs[:20]:
            md += f"- {curated[i]['site_name']} ↔ {curated[j]['site_name']}: {dist:.0f}m\n"
        if len(duplicate_pairs) > 20:
            md += f"- ... and {len(duplicate_pairs)-20} more\n"
    if report["warnings"]:
        md += f"\n## Warnings\n\n"
        for w in report["warnings"]:
            md += f"- {w}\n"
    md += f"\n## Traceability\n\n"
    md += f"- Source: USGS MRDS ({args.mrds})\n"
    md += f"- Duplicate threshold: {DUPLICATE_THRESHOLD_M}m\n"
    md += f"- Quality score: 0-100 based on coordinate precision, commodity info, deposit type, host rock, dev status\n"
    md += f"- Output: {csv_path}\n"

    with open(os.path.join(args.reports, "mrds_curation_report.md"), "w") as f:
        f.write(md)

    print(f"  Saved: mrds_curation_report.json + .md")
    return stats["kept"]


if __name__ == "__main__":
    main()

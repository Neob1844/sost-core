#!/usr/bin/env python3
"""Ingest Australian mineral deposit labels from MRDS + OZMIN WFS.

Sources:
- USGS MRDS (local CSV): ~1,233 Australian deposits
- OZMIN WFS (Geoscience Australia): ~16,828 national mineral occurrences
  Endpoint: https://services.ga.gov.au/gis/earthresource/wfs
  Layer: erl:MineralOccurrenceView
  License: CC-BY 4.0, no authentication required

The two sources are merged, deduplicated, and curated per AOI.
"""
import argparse, os, sys, json, csv, time
from collections import Counter
from math import radians, cos, sin, asin, sqrt
import glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OZMIN_WFS_BASE = "https://services.ga.gov.au/gis/earthresource/wfs"
OZMIN_LAYER = "erl:MineralOccurrenceView"

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


def classify_commodity(text):
    if not text:
        return set()
    lower = text.lower()
    for excl in EXCLUDE_KEYWORDS:
        if excl in lower and not any(m in lower for m in ["copper","gold","silver","nickel","iron"]):
            return set()
    metals = set()
    for kw, code in METAL_KEYWORDS.items():
        if kw in lower:
            metals.add(code)
    return metals


def fetch_ozmin_bbox(bbox, max_features=5000):
    """Fetch OZMIN WFS features for a bounding box. Returns list of dicts."""
    import requests
    min_lon, min_lat, max_lon, max_lat = bbox

    results = []
    start_index = 0
    page_size = 1000

    while True:
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAMES": OZMIN_LAYER,
            "BBOX": f"{min_lat},{min_lon},{max_lat},{max_lon}",
            "OUTPUTFORMAT": "application/json",
            "COUNT": str(page_size),
            "STARTINDEX": str(start_index),
        }

        try:
            resp = requests.get(OZMIN_WFS_BASE, params=params, timeout=60)
            if resp.status_code != 200:
                print(f"    WFS error: HTTP {resp.status_code}")
                break

            data = resp.json()
            features = data.get("features", [])
            if not features:
                break

            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [None, None]) if geom else [None, None]

                # OZMIN returns [lon, lat]
                lon, lat = None, None
                if coords and len(coords) >= 2:
                    lon, lat = coords[0], coords[1]

                if lat is None or lon is None:
                    continue

                commodity_text = props.get("commodity", "") or ""
                name = props.get("name", "") or ""
                occ_type = props.get("mineralOccurrenceType", "") or ""
                identifier = props.get("identifier", "") or ""

                results.append({
                    "latitude": lat,
                    "longitude": lon,
                    "site_name": name,
                    "deposit_id": identifier,
                    "commodity_raw": commodity_text,
                    "occurrence_type": occ_type,
                    "source": "OZMIN_WFS",
                })

            start_index += page_size
            if len(features) < page_size or len(results) >= max_features:
                break
            time.sleep(0.3)  # polite rate limiting
        except Exception as e:
            print(f"    WFS fetch error: {e}")
            break

    return results


def fetch_ozmin_australia_wide():
    """Fetch OZMIN data for all of Australia by tiling."""
    # Australia bbox: lon 112-154, lat -44 to -10
    # Tile in 5-degree chunks to avoid WFS limits
    all_results = []
    tiles = []
    for lat_start in range(-44, -10, 5):
        for lon_start in range(112, 154, 5):
            tiles.append([lon_start, lat_start, lon_start+5, lat_start+5])

    print(f"    Fetching OZMIN via {len(tiles)} tiles...")
    for i, tile_bbox in enumerate(tiles):
        results = fetch_ozmin_bbox(tile_bbox, max_features=5000)
        all_results.extend(results)
        if (i + 1) % 10 == 0:
            print(f"    Tile {i+1}/{len(tiles)}: {len(all_results)} total so far")
        time.sleep(0.2)

    # Deduplicate by identifier
    seen = set()
    unique = []
    for r in all_results:
        key = r["deposit_id"] or f"{r['latitude']:.5f}_{r['longitude']:.5f}"
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


def load_mrds_australia(mrds_path):
    """Load Australian deposits from MRDS CSV."""
    deposits = []
    with open(mrds_path, newline='', encoding='utf-8', errors='replace') as f:
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
            deposits.append({
                "latitude": lat,
                "longitude": lon,
                "site_name": row.get("site_name", ""),
                "deposit_id": row.get("dep_id", ""),
                "commodity_raw": row.get("commod1", ""),
                "occurrence_type": row.get("dep_type", ""),
                "source": "MRDS",
            })
    return deposits


def main():
    p = argparse.ArgumentParser(description="Ingest Australian labels from MRDS + OZMIN WFS")
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--source", choices=["all", "mrds", "ozmin"], default="all")
    p.add_argument("--output-dir", default=os.path.expanduser("~/SOST/geaspirit/data/labels"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    p.add_argument("--aoi-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.reports, exist_ok=True)

    print("=== Ingesting Australian Mineral Labels ===")

    all_raw = []
    mrds_count = 0
    ozmin_count = 0

    # MRDS
    if args.source in ("all", "mrds"):
        print("\n  [MRDS] Loading from local CSV...")
        mrds = load_mrds_australia(args.mrds)
        mrds_count = len(mrds)
        all_raw.extend(mrds)
        print(f"    MRDS: {mrds_count} Australian deposits")

    # OZMIN WFS
    if args.source in ("all", "ozmin"):
        print("\n  [OZMIN] Fetching from Geoscience Australia WFS...")
        ozmin = fetch_ozmin_australia_wide()
        ozmin_count = len(ozmin)
        all_raw.extend(ozmin)
        print(f"    OZMIN: {ozmin_count} mineral occurrences")

        # Save raw OZMIN response
        raw_path = os.path.join(args.output_dir, "australia_labels_mrds_ozmin_raw.json")
        with open(raw_path, "w") as f:
            json.dump(ozmin, f, indent=2)

    print(f"\n  Total raw: {len(all_raw)} (MRDS={mrds_count}, OZMIN={ozmin_count})")

    # Classify commodities and curate
    curated = []
    for d in all_raw:
        metals = classify_commodity(d["commodity_raw"])
        if not metals:
            # Try occurrence type
            metals = classify_commodity(d.get("occurrence_type", ""))
        if not metals:
            continue

        # Quality score
        quality = 50
        lat_str = str(d["latitude"])
        if "." in lat_str and len(lat_str.split(".")[1]) >= 4:
            quality += 15
        elif "." in lat_str and len(lat_str.split(".")[1]) >= 2:
            quality += 5
        if d["commodity_raw"]:
            quality += 10
        if d.get("occurrence_type"):
            quality += 10
        if d["site_name"]:
            quality += 5
        quality = min(100, quality)

        curated.append({
            "deposit_id": d["deposit_id"],
            "site_name": d["site_name"],
            "latitude": d["latitude"],
            "longitude": d["longitude"],
            "commodity_codes": ",".join(sorted(metals)),
            "commodity_raw": d["commodity_raw"],
            "occurrence_type": d.get("occurrence_type", ""),
            "quality_score": quality,
            "source_dataset": d["source"],
            "duplicate_flag": False,
            "keep_for_training": quality >= 30,
        })

    print(f"  Metal deposits after classification: {len(curated)}")

    # Cross-source deduplication (MRDS vs OZMIN)
    dup_count = 0
    kept_indices = [i for i, d in enumerate(curated) if d["keep_for_training"]]
    for ii in range(len(kept_indices)):
        i = kept_indices[ii]
        if not curated[i]["keep_for_training"]:
            continue
        for jj in range(ii + 1, min(ii + 200, len(kept_indices))):  # limit comparisons
            j = kept_indices[jj]
            if not curated[j]["keep_for_training"]:
                continue
            dist = haversine(curated[i]["latitude"], curated[i]["longitude"],
                             curated[j]["latitude"], curated[j]["longitude"])
            if dist < DUPLICATE_THRESHOLD_M:
                # Keep the one with higher quality or prefer OZMIN (more data)
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

    # Save all curated labels
    csv_path = os.path.join(args.output_dir, "australia_labels_curated.csv")
    fieldnames = list(curated[0].keys()) if curated else []
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for d in curated:
            w.writerow(d)

    # Per-AOI extraction
    aoi_stats = {}
    for aoi_file in sorted(glob.glob(os.path.join(args.aoi_dir, "*.json"))):
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
            src_counts = Counter()
            for d in aoi_deps:
                for c in d["commodity_codes"].split(","):
                    if c:
                        comm_counts[c] += 1
                src_counts[d["source_dataset"]] += 1
            aoi_stats[aoi_name] = {
                "count": len(aoi_deps),
                "commodities": dict(comm_counts.most_common()),
                "sources": dict(src_counts),
            }
            print(f"  {aoi_name}: {len(aoi_deps)} deposits — {dict(comm_counts.most_common(5))}")
            print(f"    Sources: {dict(src_counts)}")

    # Report
    report = {
        "sources": {
            "MRDS": {"count": mrds_count, "license": "Public domain (US Government)"},
            "OZMIN_WFS": {"count": ozmin_count, "license": "CC-BY 4.0 (Geoscience Australia)",
                          "endpoint": OZMIN_WFS_BASE, "layer": OZMIN_LAYER},
        },
        "total_raw": len(all_raw),
        "total_curated_metal": len(curated),
        "duplicates_removed": dup_count,
        "final_kept": kept,
        "per_aoi": aoi_stats,
        "commodity_global": dict(Counter(
            c for d in curated if d["keep_for_training"]
            for c in d["commodity_codes"].split(",") if c
        ).most_common()),
    }
    with open(os.path.join(args.reports, "ozmin_ingestion_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    md = "# Australian Mineral Labels — MRDS + OZMIN WFS\n\n"
    md += f"## Sources\n"
    md += f"- **MRDS**: {mrds_count} deposits (Public domain)\n"
    md += f"- **OZMIN WFS**: {ozmin_count} occurrences (CC-BY 4.0, Geoscience Australia)\n"
    md += f"- Endpoint: `{OZMIN_WFS_BASE}`\n"
    md += f"- Layer: `{OZMIN_LAYER}`\n\n"
    md += f"## Totals\n"
    md += f"- Raw combined: {len(all_raw)}\n"
    md += f"- Metal deposits: {len(curated)}\n"
    md += f"- Duplicates removed: {dup_count}\n"
    md += f"- **Final kept: {kept}**\n\n"
    md += f"## Per-AOI Coverage\n\n"
    md += "| AOI | Deposits | MRDS | OZMIN | Top Commodities |\n"
    md += "|-----|----------|------|-------|------------------|\n"
    for name, stats in aoi_stats.items():
        comms = ", ".join(f"{k}:{v}" for k, v in list(stats["commodities"].items())[:5])
        mrds_n = stats["sources"].get("MRDS", 0)
        ozmin_n = stats["sources"].get("OZMIN_WFS", 0)
        md += f"| {name} | **{stats['count']}** | {mrds_n} | {ozmin_n} | {comms} |\n"
    md += f"\n## Impact\n"
    for name, stats in aoi_stats.items():
        if "kalgoorlie" in name:
            md += f"- **Kalgoorlie**: {stats['count']} deposits (was 16 with MRDS only)\n"

    with open(os.path.join(args.reports, "ozmin_ingestion_report.md"), "w") as f:
        f.write(md)
    print(f"\n  Saved: australia_labels_curated.csv + ozmin_ingestion_report.md")


if __name__ == "__main__":
    main()

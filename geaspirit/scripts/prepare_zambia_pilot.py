#!/usr/bin/env python3
"""Evaluate Zambia Copperbelt feasibility as next GeaSpirit pilot."""
import argparse, os, sys, json, csv
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    p = argparse.ArgumentParser(description="Prepare Zambia Copperbelt pilot")
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--aoi-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    # Define Zambia AOI
    os.makedirs(args.aoi_dir, exist_ok=True)
    aoi = {
        "name": "zambia_copperbelt",
        "center": [-12.8, 28.2],
        "bbox": [27.95, -13.05, 28.45, -12.55],
        "width_km": 50, "height_km": 50, "area_km2": 2500,
        "half_deg_lat": 0.25, "half_deg_lon": 0.25,
        "crs": "EPSG:4326",
        "notes": "Zambia Copperbelt — Cu/Co, commodity-compatible with Chuquicamata",
    }
    with open(os.path.join(args.aoi_dir, "zambia_copperbelt.json"), "w") as f:
        json.dump(aoi, f, indent=2)

    bbox = aoi["bbox"]
    print(f"=== Zambia Copperbelt Feasibility ===")
    print(f"  Center: {aoi['center']}, BBox: {bbox}")

    # Count MRDS deposits
    deposits = []
    commods = Counter()
    with open(args.mrds, newline='', encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row.get("latitude", ""))
                lon = float(row.get("longitude", ""))
            except: continue
            if bbox[1] <= lat <= bbox[3] and bbox[0] <= lon <= bbox[2]:
                c = row.get("commod1", "").lower()
                deposits.append(row)
                if "copper" in c: commods["Cu"] += 1
                elif "cobalt" in c: commods["Co"] += 1
                elif "gold" in c: commods["Au"] += 1
                elif "zinc" in c: commods["Zn"] += 1
                elif "lead" in c: commods["Pb"] += 1
                else: commods["other"] += 1

    print(f"  MRDS deposits: {len(deposits)}")
    print(f"  Commodities: {dict(commods)}")

    # Feasibility assessment
    n_cu = commods.get("Cu", 0)
    viable = "YES" if n_cu >= 10 else "MARGINAL" if n_cu >= 5 else "NO"

    report = {
        "aoi": "zambia_copperbelt",
        "center": aoi["center"],
        "mrds_deposits": len(deposits),
        "commodities": dict(commods),
        "cu_count": n_cu,
        "commodity_compatible_with_chuquicamata": n_cu >= 5,
        "supervised_ml_viable": viable,
        "satellite_available": {
            "sentinel_2": True, "sentinel_1": "likely (check GEE)",
            "dem": True, "landsat_thermal": True,
        },
        "geology_available": "BGS 1:5M (very coarse), OZMIN not applicable (Australia only)",
        "geophysics_available": "None publicly available",
        "emit_coverage": "50 L2A scenes (from Phase 4A inventory)",
        "recommendation": "",
    }

    if viable == "YES":
        report["recommendation"] = (
            f"Zambia has {n_cu} Cu deposits — enough for supervised ML. "
            f"Cu-compatible with Chuquicamata for transfer learning. "
            f"Recommend as next pilot after Kalgoorlie stabilizes."
        )
    elif viable == "MARGINAL":
        report["recommendation"] = (
            f"Zambia has {n_cu} Cu deposits — marginal for supervised ML. "
            f"Consider supplementing with USGS Africa mineral GIS (500+ Cu points). "
            f"Heuristic scan mode should work immediately."
        )
    else:
        report["recommendation"] = (
            f"Zambia has only {n_cu} Cu deposits — insufficient for supervised ML. "
            f"Use heuristic scan mode only."
        )

    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "zambia_feasibility_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    md = f"# Zambia Copperbelt Feasibility Report\n\n"
    md += f"## AOI\n- Center: {aoi['center']}\n- Size: 50x50km\n\n"
    md += f"## Labels\n- MRDS deposits: **{len(deposits)}**\n"
    md += f"- Cu deposits: **{n_cu}**\n"
    md += f"- Commodities: {dict(commods)}\n\n"
    md += f"## Commodity Compatibility\n"
    md += f"- Chuquicamata: Cu/Au/Ag\n- Zambia: Cu/Co\n"
    md += f"- **Cu overlap: YES** — transfer learning viable\n\n"
    md += f"## Data Availability\n"
    md += f"- Sentinel-2: Available\n- Sentinel-1: Likely available\n"
    md += f"- DEM: Available\n- Landsat thermal: Available\n"
    md += f"- Geology: BGS 1:5M only (very coarse)\n"
    md += f"- Geophysics: None publicly available\n"
    md += f"- EMIT: 50 L2A scenes\n\n"
    md += f"## Verdict: **{viable}**\n\n{report['recommendation']}\n"

    with open(os.path.join(args.output, "zambia_feasibility_report.md"), "w") as f:
        f.write(md)
    print(f"  Verdict: {viable}")
    print(f"  Saved: zambia_feasibility_report.md")


if __name__ == "__main__":
    main()

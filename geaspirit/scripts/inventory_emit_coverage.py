#!/usr/bin/env python3
"""Phase 4A Priority 5A — Inventory EMIT coverage for pilot zones.

Checks NASA's CMR (Common Metadata Repository) API for EMIT L2A/L2B
scene coverage over each GeaSpirit pilot zone.

EMIT: Earth Surface Mineral Dust Source Investigation (ISS instrument)
- L2A: Reflectance (285 bands, 60m resolution)
- L2B: Mineral identification + uncertainty
- Coverage: ±52° latitude, daytime passes only
"""
import argparse, os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, HALF_DEG


def search_cmr_emit(bbox, collection_id, max_results=100):
    """Search NASA CMR for EMIT granules intersecting a bounding box."""
    import requests
    min_lon, min_lat, max_lon, max_lat = bbox

    url = "https://cmr.earthdata.nasa.gov/search/granules.json"
    params = {
        "collection_concept_id": collection_id,
        "bounding_box": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "page_size": max_results,
        "sort_key": "-start_date",
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            entries = data.get("feed", {}).get("entry", [])
            return entries, None
        return [], f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return [], str(e)


# EMIT collection concept IDs in CMR
EMIT_COLLECTIONS = {
    "L2A_RFL": "C2408009906-LPCLOUD",   # L2A Reflectance
    "L2B_MIN": "C2408034764-LPCLOUD",   # L2B Mineral Identification
    "L2B_MINUNC": "C2408034784-LPCLOUD",  # L2B Mineral Uncertainty
}


def main():
    p = argparse.ArgumentParser(description="Inventory EMIT coverage for pilot zones")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("=== EMIT Coverage Inventory ===\n")

    inventory = {}
    for zone_name, zone_info in ZONES.items():
        lat_c, lon_c = zone_info["center"]
        bbox = [lon_c - HALF_DEG, lat_c - HALF_DEG, lon_c + HALF_DEG, lat_c + HALF_DEG]

        print(f"  [{zone_name}] lat={lat_c}, lon={lon_c}")
        zone_result = {
            "zone": zone_name,
            "center": [lat_c, lon_c],
            "bbox": bbox,
            "within_emit_coverage": abs(lat_c) <= 52,
            "collections": {},
        }

        if abs(lat_c) > 52:
            print(f"    Outside EMIT coverage (±52° latitude)")
            zone_result["recommendation"] = "Outside EMIT coverage band"
            inventory[zone_name] = zone_result
            continue

        for coll_name, coll_id in EMIT_COLLECTIONS.items():
            entries, error = search_cmr_emit(bbox, coll_id, max_results=50)

            if error:
                zone_result["collections"][coll_name] = {
                    "status": "ERROR",
                    "error": error,
                    "n_scenes": 0,
                }
                print(f"    {coll_name}: ERROR — {error}")
            else:
                dates = []
                for entry in entries:
                    time_start = entry.get("time_start", "")
                    if time_start:
                        dates.append(time_start[:10])

                zone_result["collections"][coll_name] = {
                    "status": "OK",
                    "n_scenes": len(entries),
                    "dates": sorted(set(dates)),
                    "date_range": [min(dates), max(dates)] if dates else [],
                }
                print(f"    {coll_name}: {len(entries)} scenes"
                      + (f" ({dates[0]}..{dates[-1]})" if dates else ""))

        # Recommendation
        l2a = zone_result["collections"].get("L2A_RFL", {})
        l2b = zone_result["collections"].get("L2B_MIN", {})
        n_l2a = l2a.get("n_scenes", 0)
        n_l2b = l2b.get("n_scenes", 0)

        if n_l2a >= 5 and n_l2b >= 1:
            zone_result["recommendation"] = "GOOD — sufficient L2A+L2B coverage for integration"
            zone_result["integrable"] = True
        elif n_l2a >= 1:
            zone_result["recommendation"] = "PARTIAL — some L2A scenes, limited L2B"
            zone_result["integrable"] = True
        else:
            zone_result["recommendation"] = "POOR — insufficient EMIT coverage"
            zone_result["integrable"] = False

        inventory[zone_name] = zone_result

    # Save JSON
    with open(os.path.join(args.output, "emit_coverage_inventory.json"), "w") as f:
        json.dump(inventory, f, indent=2)

    # Save Markdown
    md = "# EMIT Coverage Inventory\n\n"
    md += "EMIT: Earth Surface Mineral Dust Source Investigation (ISS, 285 bands, 60m)\n\n"
    md += "## Summary\n\n"
    md += "| Zone | In Coverage | L2A Scenes | L2B Scenes | Integrable |\n"
    md += "|------|------------|------------|------------|------------|\n"
    for zn, zi in inventory.items():
        in_cov = "Yes" if zi["within_emit_coverage"] else "No"
        l2a_n = zi["collections"].get("L2A_RFL", {}).get("n_scenes", 0)
        l2b_n = zi["collections"].get("L2B_MIN", {}).get("n_scenes", 0)
        integ = "YES" if zi.get("integrable") else "no"
        md += f"| {zn} | {in_cov} | {l2a_n} | {l2b_n} | **{integ}** |\n"

    for zn, zi in inventory.items():
        md += f"\n## {zn}\n"
        md += f"- **Recommendation**: {zi['recommendation']}\n"
        for coll_name, coll_data in zi.get("collections", {}).items():
            if coll_data.get("n_scenes", 0) > 0:
                md += f"- {coll_name}: {coll_data['n_scenes']} scenes"
                if coll_data.get("date_range"):
                    md += f" ({coll_data['date_range'][0]} to {coll_data['date_range'][1]})"
                md += "\n"

    md += "\n## Integration Notes\n"
    md += "- EMIT L2A provides 285-band reflectance at 60m — mineral-specific detection\n"
    md += "- EMIT L2B provides mineral identification maps + uncertainty\n"
    md += "- Download requires NASA Earthdata authentication\n"
    md += "- Scenes must be mosaicked/composited for full AOI coverage\n"
    md += "- Integration adds ~5-20 features (band depths, mineral IDs)\n"

    with open(os.path.join(args.output, "emit_coverage_inventory.md"), "w") as f:
        f.write(md)

    print(f"\n  Saved: emit_coverage_inventory.json + .md")


if __name__ == "__main__":
    main()

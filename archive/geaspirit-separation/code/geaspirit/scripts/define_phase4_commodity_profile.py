#!/usr/bin/env python3
"""Phase 4A Priority 1 — Define commodity profiles for multi-zone training.

Analyzes MRDS deposits in each AOI and creates a harmonized commodity profile
that excludes noise deposits (limestone, silica, boron, etc.) while retaining
metal deposits relevant to mineral prospectivity.
"""
import argparse, os, sys, json, csv
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, HALF_DEG, get_bbox

# Commodity keywords to EXCLUDE (noise for metal prospectivity)
EXCLUDE_KEYWORDS = {
    "limestone", "dolomite", "silica", "sand", "gravel", "clay",
    "boron", "borate", "gypsum", "anhydrite", "calcite", "marble",
    "cement", "aggregate", "dimension", "slate", "granite dimension",
    "building", "construction", "peat", "soil", "sodium", "potash",
    "salt", "halite", "phosphate", "feldspar", "mica", "talc",
    "vermiculite", "diatomite", "pumice", "perlite", "zeolite",
    "barite", "fluorite", "fluorspar", "gemstone", "gem",
}

# Metal commodity keywords to INCLUDE
METAL_KEYWORDS = {
    "copper": "Cu", "gold": "Au", "silver": "Ag", "iron": "Fe",
    "molybdenum": "Mo", "lead": "Pb", "zinc": "Zn", "nickel": "Ni",
    "cobalt": "Co", "manganese": "Mn", "chromium": "Cr", "tungsten": "W",
    "tin": "Sn", "uranium": "U", "lithium": "Li", "platinum": "Pt",
    "palladium": "Pd", "vanadium": "V", "titanium": "Ti", "rhenium": "Re",
    "antimony": "Sb", "rare earth": "REE", "tantalum": "Ta",
    "niobium": "Nb", "bismuth": "Bi", "mercury": "Hg",
}

# Zone-specific priority commodities
ZONE_PRIORITIES = {
    "chuquicamata": ["Cu", "Au", "Ag", "Mo"],
    "pilbara":      ["Au", "Cu", "Fe", "Ni", "Cr", "Mn"],
    "zambia":       ["Cu", "Co", "Zn", "Pb", "Ag"],
}

# For Pilbara: exclude massive iron ore (BIF) if it dominates too much
PILBARA_FE_NOTE = (
    "Pilbara is dominated by massive iron ore (BIF/hematite). "
    "Including all Fe deposits may bias the model toward iron signatures. "
    "Strategy: include Fe but cap at 50% of total labels. Prioritize Au/Cu."
)


def classify_commodity(commod_str):
    """Extract metal codes from MRDS commodity string."""
    if not commod_str:
        return set(), False
    lower = commod_str.lower()
    # Check exclusions first
    for excl in EXCLUDE_KEYWORDS:
        if excl in lower and not any(m in lower for m in ["copper", "gold", "silver", "iron", "nickel"]):
            return set(), True  # excluded
    metals = set()
    for keyword, code in METAL_KEYWORDS.items():
        if keyword in lower:
            metals.add(code)
    return metals, False


def main():
    p = argparse.ArgumentParser(description="Define Phase 4 commodity profiles")
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/data/mrds"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    profiles = {}

    for zone_name in ["chuquicamata", "pilbara", "zambia"]:
        zone = ZONES[zone_name]
        lat_c, lon_c = zone["center"]
        bbox = get_bbox(zone_name)
        min_lon, min_lat, max_lon, max_lat = bbox
        priority = ZONE_PRIORITIES[zone_name]

        total = 0
        retained = 0
        excluded_noise = 0
        excluded_no_metal = 0
        commodity_counts = Counter()
        all_raw_commods = Counter()

        with open(args.mrds, newline='', encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                try:
                    lat = float(row.get('latitude', ''))
                    lon = float(row.get('longitude', ''))
                except (ValueError, TypeError):
                    continue
                if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                    continue
                total += 1
                commod1 = row.get('commod1', '').strip()
                commod2 = row.get('commod2', '').strip()
                commod3 = row.get('commod3', '').strip()
                all_raw_commods[commod1] += 1

                all_metals = set()
                is_noise = False
                for c in [commod1, commod2, commod3]:
                    metals, noise = classify_commodity(c)
                    all_metals |= metals
                    if noise:
                        is_noise = True

                if is_noise and not all_metals:
                    excluded_noise += 1
                    continue
                if not all_metals:
                    excluded_no_metal += 1
                    continue

                retained += 1
                for m in all_metals:
                    commodity_counts[m] += 1

        # For Pilbara: check Fe dominance
        fe_note = ""
        if zone_name == "pilbara" and commodity_counts.get("Fe", 0) > retained * 0.5:
            fe_note = PILBARA_FE_NOTE

        profiles[zone_name] = {
            "center": list(zone["center"]),
            "bbox": bbox,
            "priority_commodities": priority,
            "total_deposits_in_aoi": total,
            "retained_metal_deposits": retained,
            "excluded_noise": excluded_noise,
            "excluded_no_metal": excluded_no_metal,
            "commodity_distribution": dict(commodity_counts.most_common()),
            "raw_commod1_values": dict(all_raw_commods.most_common(20)),
            "note": fe_note,
        }

        print(f"  {zone_name}: {total} total, {retained} retained, "
              f"{excluded_noise} noise, {excluded_no_metal} no-metal")
        print(f"    Commodities: {dict(commodity_counts.most_common(6))}")

    # Save
    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "commodity_profile_phase4.json"), "w") as f:
        json.dump(profiles, f, indent=2)

    # Pilbara-specific report
    os.makedirs(args.reports, exist_ok=True)
    pil = profiles["pilbara"]
    md = "# Pilbara Commodity Profile — Phase 4A\n\n"
    md += f"## AOI: {pil['center']}\n"
    md += f"- Total deposits: {pil['total_deposits_in_aoi']}\n"
    md += f"- Retained (metal): {pil['retained_metal_deposits']}\n"
    md += f"- Excluded (noise): {pil['excluded_noise']}\n"
    md += f"- Excluded (no metal): {pil['excluded_no_metal']}\n\n"
    md += f"## Priority commodities: {pil['priority_commodities']}\n\n"
    md += "## Commodity Distribution\n\n"
    md += "| Commodity | Count |\n|-----------|-------|\n"
    for comm, cnt in sorted(pil["commodity_distribution"].items(), key=lambda x: -x[1]):
        md += f"| {comm} | {cnt} |\n"
    if pil["note"]:
        md += f"\n## Note\n{pil['note']}\n"
    md += f"\n## Raw commod1 values (top 20)\n\n"
    for raw, cnt in list(pil["raw_commod1_values"].items())[:20]:
        md += f"- `{raw}`: {cnt}\n"
    md += f"\n## Exclusion Rules\n"
    md += f"- Noise keywords: {sorted(list(EXCLUDE_KEYWORDS)[:15])}... ({len(EXCLUDE_KEYWORDS)} total)\n"
    md += f"- Only metal deposits retained for training\n"

    with open(os.path.join(args.reports, "pilbara_commodity_profile.md"), "w") as f:
        f.write(md)

    print(f"\n  Saved: commodity_profile_phase4.json + pilbara_commodity_profile.md")


if __name__ == "__main__":
    main()

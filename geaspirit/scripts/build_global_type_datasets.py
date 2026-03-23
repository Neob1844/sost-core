#!/usr/bin/env python3
"""Build global deposit-type datasets from all curated labels."""
import argparse, os, sys, json, csv, glob, re
from collections import Counter, defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEPOSIT_TYPES = {
    "porphyry_cu": {"keywords": ["porphyry"], "commodities": ["copper","cu"], "regions": ["chile","peru","argentina"]},
    "sediment_hosted_cu": {"keywords": ["sediment","stratabound","kupferschiefer","shale"], "commodities": ["copper","cu","cobalt","co"], "regions": ["zambia","congo","drc"]},
    "orogenic_au": {"keywords": ["orogenic","lode","shear","greenstone"], "commodities": ["gold","au"], "regions": ["australia","canada"]},
    "epithermal_au": {"keywords": ["epithermal","hot spring"], "commodities": ["gold","au","silver","ag"]},
    "iron_formation": {"keywords": ["bif","iron formation","banded iron","hematite","magnetite ore"], "commodities": ["iron","fe"]},
    "komatiite_ni": {"keywords": ["komatiite","ultramafic"], "commodities": ["nickel","ni"]},
    "laterite_ni": {"keywords": ["laterite"], "commodities": ["nickel","ni"]},
    "vms": {"keywords": ["massive sulfide","vms","volcanogenic"], "commodities": ["copper","cu","zinc","zn"]},
    "skarn": {"keywords": ["skarn","contact"], "commodities": ["copper","cu","tungsten","w","zinc","zn"]},
}

# Zone → likely deposit type mapping for inference
ZONE_TYPE_MAP = {
    "chuquicamata": "porphyry_cu",
    "zambia": "sediment_hosted_cu",
    "kalgoorlie": "orogenic_au",
    "pilbara": "iron_formation",
}


def classify_label(row):
    """Classify a label's deposit type. Returns (type, confidence, method)."""
    # Check explicit deposit_type field
    dt = (row.get("deposit_type","") or row.get("deposit_type_raw","") or row.get("dep_type","")).strip().lower()
    if dt:
        for dtype, spec in DEPOSIT_TYPES.items():
            for kw in spec["keywords"]:
                if kw in dt:
                    return dtype, "high", "source_field"

    # Infer from commodity + source file
    commod = (row.get("commodity_raw","") or row.get("commod1","") or row.get("commodity_codes","")).lower()
    source = (row.get("source_file","") or row.get("source_dataset","")).lower()

    # Zone + commodity inference (medium confidence)
    zone = row.get("_zone", "")
    source = source + " " + zone  # include zone in source string
    for zone_key, zone_type in ZONE_TYPE_MAP.items():
        if zone_key in source:
            # For Kalgoorlie, separate Au from Ni
            if zone_key == "kalgoorlie":
                if "au" in commod or "gold" in commod:
                    return "orogenic_au", "medium", "inferred_zone_commodity:kalgoorlie_au"
                if "ni" in commod or "nickel" in commod:
                    return "komatiite_ni", "medium", "inferred_zone_commodity:kalgoorlie_ni"
                if "fe" in commod or "iron" in commod:
                    return "iron_formation", "medium", "inferred_zone_commodity:kalgoorlie_fe"
                return "orogenic_au", "low", "inferred_zone_default:kalgoorlie"
            return zone_type, "medium", f"inferred_zone:{zone_key}"

    # Commodity-based inference (weaker)
    if "copper" in commod or ",cu" in commod or commod.startswith("cu"):
        return "porphyry_cu", "low", "inferred_commodity_default"
    if "gold" in commod or ",au" in commod or commod.startswith("au"):
        return "orogenic_au", "low", "inferred_commodity_default"
    if "iron" in commod or ",fe" in commod:
        return "iron_formation", "low", "inferred_commodity_default"
    if "nickel" in commod or ",ni" in commod:
        return "komatiite_ni", "low", "inferred_commodity_default"

    return "unknown", "none", "not_classifiable"


def main():
    p = argparse.ArgumentParser(description="Build global type datasets")
    p.add_argument("--label-dirs", default=os.path.expanduser("~/SOST/geaspirit/data/labels")
                    + "," + os.path.expanduser("~/SOST/geaspirit/data/mrds"))
    p.add_argument("--output-dir", default=os.path.expanduser("~/SOST/geaspirit/data/labels"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    print("=== Building Global Type Datasets ===\n")

    # Collect all labels
    all_labels = []
    seen_ids = set()
    for label_dir in args.label_dirs.split(","):
        for fp in glob.glob(os.path.join(label_dir.strip(), "*curated*.csv")) + \
                   glob.glob(os.path.join(label_dir.strip(), "*enriched*.csv")):
            with open(fp, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    keep = row.get("keep_for_training", "True").lower()
                    if keep != "true":
                        continue
                    uid = f"{row.get('latitude','')},{row.get('longitude','')}"
                    if uid in seen_ids:
                        continue
                    seen_ids.add(uid)
                    row["source_file"] = os.path.basename(fp)
                    all_labels.append(row)

    print(f"  Total unique labels: {len(all_labels)}")

    # Classify each
    typed = []
    for lab in all_labels:
        zone = _infer_zone(lab)
        lab["_zone"] = zone  # inject zone for classifier
        dtype, conf, method = classify_label(lab)
        typed.append({
            "global_label_id": f"GL{len(typed):06d}",
            "source_dataset": lab.get("source_dataset", lab.get("source_file", "")),
            "latitude": lab.get("latitude", ""),
            "longitude": lab.get("longitude", ""),
            "site_name": lab.get("site_name", ""),
            "zone_name": _infer_zone(lab),
            "country": lab.get("country", ""),
            "commodity_group": lab.get("commodity_codes", lab.get("commodity_group", "")),
            "deposit_type": dtype,
            "deposit_type_confidence": conf,
            "type_assignment_method": method,
            "keep_for_type_training": 1 if conf in ("high", "medium") else 0,
        })

    # Stats
    type_counts = Counter(t["deposit_type"] for t in typed)
    trainable = Counter(t["deposit_type"] for t in typed if t["keep_for_type_training"])
    conf_counts = Counter(t["deposit_type_confidence"] for t in typed)

    print(f"  Type distribution: {dict(type_counts.most_common())}")
    print(f"  Trainable (high/medium conf): {dict(trainable.most_common())}")

    # Save global file
    os.makedirs(args.output_dir, exist_ok=True)
    fieldnames = list(typed[0].keys())
    with open(os.path.join(args.output_dir, "global_type_labels.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for t in typed:
            w.writerow(t)

    # Save per-type files
    for dtype in ["porphyry_cu", "sediment_hosted_cu", "orogenic_au", "bif_fe", "iron_formation"]:
        type_labels = [t for t in typed if t["deposit_type"] == dtype and t["keep_for_type_training"]]
        if not type_labels:
            continue
        fname = f"{dtype}_labels.csv"
        with open(os.path.join(args.output_dir, fname), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for t in type_labels:
                w.writerow(t)
        print(f"  {dtype}: {len(type_labels)} trainable labels -> {fname}")

    # Report
    os.makedirs(args.reports, exist_ok=True)
    report = {
        "total_labels": len(typed),
        "type_distribution": dict(type_counts.most_common()),
        "trainable_by_type": dict(trainable.most_common()),
        "confidence_distribution": dict(conf_counts),
    }
    with open(os.path.join(args.reports, "global_type_dataset_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    md = "# Global Deposit Type Dataset Report\n\n"
    md += f"Total labels: {len(typed)}\n\n"
    md += "| Type | Total | Trainable (high/medium) |\n|------|-------|------------------------|\n"
    for dtype, count in type_counts.most_common():
        tr = trainable.get(dtype, 0)
        md += f"| {dtype} | {count} | **{tr}** |\n"
    with open(os.path.join(args.reports, "global_type_dataset_report.md"), "w") as f:
        f.write(md)

    print(f"\n  Saved: global_type_labels.csv + per-type files + report")


_ZONE_BBOXES = {
    "chuquicamata": [-69.15, -22.55, -68.65, -22.05],
    "kalgoorlie": [121.2, -31.9, 122.2, -30.9],
    "zambia": [27.0, -13.5, 29.5, -11.5],
    "pilbara": [118.0, -24.0, 120.0, -22.0],
}

def _infer_zone(row):
    # Check source file name first
    src = (row.get("source_file","") + row.get("source_dataset","")).lower()
    for zone in ["chuquicamata", "kalgoorlie", "zambia", "pilbara", "tintic"]:
        if zone in src:
            return zone
    # Fall back to geographic position
    try:
        lat = float(row.get("latitude", ""))
        lon = float(row.get("longitude", ""))
        for zone, bb in _ZONE_BBOXES.items():
            if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3]:
                return zone
    except (ValueError, TypeError):
        pass
    return "global"


if __name__ == "__main__":
    main()

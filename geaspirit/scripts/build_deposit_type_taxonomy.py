#!/usr/bin/env python3
"""Build global deposit type taxonomy across all GeaSpirit zones."""
import argparse, os, sys, json, csv, glob
from collections import Counter

DEPOSIT_TYPES = {
    "porphyry_cu": {"keywords": ["porphyry"], "commodities": ["Cu","Mo","Au"]},
    "sediment_hosted_cu": {"keywords": ["sediment","stratabound","kupferschiefer"], "commodities": ["Cu","Co"]},
    "orogenic_au": {"keywords": ["orogenic","lode","shear"], "commodities": ["Au"]},
    "epithermal_au": {"keywords": ["epithermal","hot spring"], "commodities": ["Au","Ag"]},
    "iron_formation": {"keywords": ["bif","iron formation","banded iron","hematite"], "commodities": ["Fe"]},
    "komatiite_ni": {"keywords": ["komatiite","ultramafic"], "commodities": ["Ni","Co"]},
    "laterite_ni": {"keywords": ["laterite","nickel laterite"], "commodities": ["Ni"]},
    "vms": {"keywords": ["massive sulfide","vms","volcanogenic"], "commodities": ["Cu","Zn","Pb"]},
    "iocg": {"keywords": ["iocg","iron oxide copper"], "commodities": ["Cu","Au","Fe"]},
    "skarn": {"keywords": ["skarn","contact metasomatic"], "commodities": ["Cu","Zn","W","Mo"]},
    "mvt": {"keywords": ["mississippi valley","mvt"], "commodities": ["Zn","Pb"]},
    "placer_au": {"keywords": ["placer","alluvial"], "commodities": ["Au","Pt"]},
}


def classify(dep_type_raw, commod, region=""):
    """Classify deposit type. Returns (type, confidence, method)."""
    if dep_type_raw:
        dt = dep_type_raw.lower()
        for dtype, spec in DEPOSIT_TYPES.items():
            for kw in spec["keywords"]:
                if kw in dt:
                    return dtype, "high", "source_field"

    # Infer from commodity + region
    if commod:
        cl = commod.lower()
        if "copper" in cl and "zambia" in region.lower():
            return "sediment_hosted_cu", "medium", "inferred_commodity_region"
        if "copper" in cl and "chile" in region.lower():
            return "porphyry_cu", "medium", "inferred_commodity_region"
        if "gold" in cl and "australia" in region.lower():
            return "orogenic_au", "low", "inferred_commodity_region"
        if "iron" in cl:
            return "iron_formation", "low", "inferred_commodity"
        if "nickel" in cl:
            return "komatiite_ni", "low", "inferred_commodity"
        if "copper" in cl:
            return "porphyry_cu", "low", "inferred_commodity_default"

    return "unknown", "none", "not_classifiable"


def main():
    p = argparse.ArgumentParser(description="Build deposit type taxonomy")
    p.add_argument("--label-dir", default=os.path.expanduser("~/SOST/geaspirit/data/labels"))
    p.add_argument("--mrds-dir", default=os.path.expanduser("~/SOST/geaspirit/data/mrds"))
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    print("=== Building Global Deposit Type Taxonomy ===\n")

    all_labels = []
    # Read all curated label files
    for pattern in [os.path.join(args.label_dir, "*curated*.csv"),
                    os.path.join(args.label_dir, "*enriched*.csv"),
                    os.path.join(args.mrds_dir, "*curated*.csv")]:
        for fp in glob.glob(pattern):
            with open(fp, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    if row.get("keep_for_training","").lower() != "true": continue
                    all_labels.append({
                        "source_file": os.path.basename(fp),
                        "deposit_id": row.get("deposit_id",""),
                        "site_name": row.get("site_name",""),
                        "latitude": row.get("latitude",""),
                        "longitude": row.get("longitude",""),
                        "commodity_codes": row.get("commodity_codes", row.get("commodity_group","")),
                        "commodity_raw": row.get("commodity_raw", row.get("commod1_raw", row.get("commod1",""))),
                        "deposit_type_existing": row.get("deposit_type",""),
                    })

    print(f"  Total labels loaded: {len(all_labels)}")

    # Classify each
    typed = []
    for lab in all_labels:
        existing = lab.get("deposit_type_existing","")
        commod = lab.get("commodity_raw","")
        region = lab.get("source_file","")

        if existing and existing != "unknown":
            dtype, conf, method = existing, "high", "pre_classified"
        else:
            dtype, conf, method = classify(
                lab.get("deposit_type_existing",""), commod, region)

        typed.append({
            **lab,
            "deposit_type": dtype,
            "deposit_type_confidence": conf,
            "deposit_type_method": method,
        })

    # Stats
    type_counts = Counter(t["deposit_type"] for t in typed)
    conf_counts = Counter(t["deposit_type_confidence"] for t in typed)
    method_counts = Counter(t["deposit_type_method"] for t in typed)

    print(f"  Deposit types: {dict(type_counts.most_common())}")
    print(f"  Confidence: {dict(conf_counts)}")
    print(f"  Methods: {dict(method_counts)}")

    # Save
    os.makedirs(args.output, exist_ok=True)
    csv_path = os.path.join(args.label_dir, "global_deposit_type_labels.csv")
    os.makedirs(args.label_dir, exist_ok=True)
    fieldnames = list(typed[0].keys()) if typed else []
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for t in typed: w.writerow(t)

    taxonomy = {
        "types": {k: {"count": v, "keywords": DEPOSIT_TYPES.get(k,{}).get("keywords",[]),
                       "typical_commodities": DEPOSIT_TYPES.get(k,{}).get("commodities",[])}
                  for k, v in type_counts.most_common()},
        "total_classified": len(typed),
        "confidence_distribution": dict(conf_counts),
        "method_distribution": dict(method_counts),
    }
    with open(os.path.join(args.output, "deposit_type_taxonomy.json"), "w") as f:
        json.dump(taxonomy, f, indent=2)

    md = "# Global Deposit Type Taxonomy\n\n"
    md += "| Type | Count | Confidence | Typical Commodities |\n|------|-------|------------|--------------------|\n"
    for dtype, count in type_counts.most_common():
        spec = DEPOSIT_TYPES.get(dtype, {})
        comms = ", ".join(spec.get("commodities", []))
        md += f"| {dtype} | {count} | varies | {comms} |\n"
    md += f"\n## Classification Methods\n"
    for m, c in method_counts.most_common():
        md += f"- {m}: {c}\n"

    with open(os.path.join(args.output, "deposit_type_taxonomy.md"), "w") as f:
        f.write(md)
    print(f"  Saved: global_deposit_type_labels.csv + taxonomy")


if __name__ == "__main__":
    main()

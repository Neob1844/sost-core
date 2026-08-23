#!/usr/bin/env python3
"""Build zone model registry — formalizes the zone-specific production architecture."""
import argparse, os, sys, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ZONES = [
    {"name": "chuquicamata", "deposit_type": "porphyry_cu", "commodity": "Cu/Au/Ag",
     "labels": 43, "bands": 24, "auc": 0.8622, "pr_auc": 0.9532,
     "model_path": "~/SOST/geaspirit/models/geology_aware_model.joblib",
     "validation": "spatial_block_cv_5fold", "status": "strong",
     "use": "local_supervised", "notes": "Best benchmark. Full stack + geology."},
    {"name": "kalgoorlie_au", "deposit_type": "orogenic_au", "commodity": "Au",
     "labels": 103, "bands": 12, "auc": 0.8063, "pr_auc": 0.5471,
     "model_path": "~/SOST/geaspirit/models/kalgoorlie_50km_best_model.joblib",
     "validation": "spatial_block_cv_5fold", "status": "strong",
     "use": "local_supervised", "notes": "Au-only filtering improved +0.04 over mixed."},
    {"name": "zambia_copperbelt", "deposit_type": "sediment_hosted_cu", "commodity": "Cu/Co",
     "labels": 28, "bands": 16, "auc": 0.7626, "pr_auc": 0.5101,
     "model_path": "~/SOST/geaspirit/models/zambia_copperbelt_best_model.joblib",
     "validation": "spatial_block_cv_5fold", "status": "acceptable",
     "use": "local_supervised", "notes": "SAR available. Enriched labels (28 from wider region)."},
    {"name": "peru_porphyry", "deposit_type": "porphyry_cu", "commodity": "Cu",
     "labels": 71, "bands": 16, "auc": 0.7577, "pr_auc": 0.4640,
     "model_path": "~/SOST/geaspirit/models/peru_porphyry_best_model.joblib",
     "validation": "spatial_block_cv_5fold", "status": "acceptable",
     "use": "local_supervised", "notes": "Central Peru Cu belt. High altitude Andes."},
    {"name": "arizona_porphyry", "deposit_type": "porphyry_cu", "commodity": "Cu",
     "labels": 5, "bands": 16, "auc": 0.7178, "pr_auc": 0.4470,
     "model_path": "~/SOST/geaspirit/models/arizona_porphyry_best_model.joblib",
     "validation": "spatial_block_cv_5fold", "status": "marginal",
     "use": "local_supervised", "notes": "Only 5 deposits in stack. Label-limited."},
    {"name": "pilbara", "deposit_type": "iron_formation", "commodity": "Fe",
     "labels": 8, "bands": 19, "auc": 0.4050, "pr_auc": None,
     "model_path": None, "validation": "spatial_block_cv_5fold", "status": "failed",
     "use": "not_recommended", "notes": "MRDS insufficient. Need GA OZMIN enrichment."},
    {"name": "banos_de_mula", "deposit_type": "unknown", "commodity": "unknown",
     "labels": 0, "bands": 16, "auc": None, "pr_auc": None,
     "model_path": None, "validation": "heuristic_only", "status": "heuristic",
     "use": "heuristic_only", "notes": "Top score 0.762. 10 km² HIGH. Hydrothermal alteration."},
    {"name": "volcan_barqueros", "deposit_type": "unknown", "commodity": "unknown",
     "labels": 0, "bands": 16, "auc": None, "pr_auc": None,
     "model_path": None, "validation": "heuristic_only", "status": "heuristic",
     "use": "heuristic_only", "notes": "Top score 0.713. 5.6 km² HIGH. Volcanic/hydrothermal."},
    {"name": "salave_asturias", "deposit_type": "orogenic_au", "commodity": "Au (known)",
     "labels": 0, "bands": 15, "auc": None, "pr_auc": None,
     "model_path": None, "validation": "heuristic_only", "status": "heuristic",
     "use": "heuristic_only", "notes": "Known Au deposit. Vegetation suppresses signals. Needs magnetics."},
]


def main():
    p = argparse.ArgumentParser(description="Build zone model registry")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    p.add_argument("--models", default=os.path.expanduser("~/SOST/geaspirit/models"))
    args = p.parse_args()

    os.makedirs(args.models, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)

    registry = {"architecture": "zone_specific", "version": "5E",
                "description": "Zone-specific production models + global AOI heuristic scanner",
                "zones": ZONES,
                "global_scanner": {
                    "type": "heuristic_proxy",
                    "version": "v8",
                    "works_without_training": True,
                    "calibrated_on": ["chuquicamata", "kalgoorlie", "zambia"],
                }}

    with open(os.path.join(args.models, "zone_model_registry.json"), "w") as f:
        json.dump(registry, f, indent=2)

    md = "# Zone Model Registry\n\n"
    md += "Architecture: **zone-specific** models + global heuristic scanner\n\n"
    md += "| Zone | Type | Labels | AUC | Status | Use |\n"
    md += "|------|------|--------|-----|--------|-----|\n"
    for z in ZONES:
        auc = f"**{z['auc']}**" if z['auc'] else "—"
        md += f"| {z['name']} | {z['deposit_type']} | {z['labels']} | {auc} | {z['status']} | {z['use']} |\n"
    md += f"\n## Transfer Learning: NOT recommended for satellite features\n"
    md += f"Cross-zone transfer (same-type, normalized): avg AUC 0.51 — near random.\n"
    md += f"Zone-specific models are the production architecture.\n"

    with open(os.path.join(args.output, "zone_model_registry.md"), "w") as f:
        f.write(md)
    print(f"Registry: {len(ZONES)} zones saved")


if __name__ == "__main__":
    main()

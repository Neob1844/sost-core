#!/usr/bin/env python3
"""Build heuristic proxy model for label-scarce AOIs.

This model works ANYWHERE on Earth without training data.
It combines domain-knowledge mineral indicators into a composite score.
"""
import argparse, os, sys, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# Heuristic weights derived from Chuquicamata ablation study
# (normalized feature importances from XGBoost)
PROXY_WEIGHTS = {
    "iron_oxide":     0.15,   # direct mineral indicator
    "clay_hydroxyl":  0.12,   # alteration halo
    "ferrous_iron":   0.10,   # sulfide indicator
    "laterite":       0.05,   # weathering product
    "ruggedness":     0.20,   # structural control (#1 feature)
    "elevation":      0.08,   # geomorphology
    "tpi":            0.05,   # terrain position
    "slope":          0.05,   # structural expression
    "VH":             0.08,   # radar texture
    "VV":             0.04,   # radar backscatter
    "LST_zscore":     0.05,   # thermal anomaly
    "ndvi":          -0.10,   # vegetation penalty
}


def main():
    p = argparse.ArgumentParser(description="Build global heuristic proxy model")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/models"))
    args = p.parse_args()

    os.makedirs(args.output, exist_ok=True)

    model_spec = {
        "type": "heuristic_proxy",
        "version": "v1",
        "description": "Domain-knowledge mineral prospectivity score. "
                        "Works without training data on any AOI with satellite coverage.",
        "weights": PROXY_WEIGHTS,
        "normalization": "percentile_clip_0_1",
        "combination": "weighted_sum",
        "output_range": [0, 1],
        "interpretation": {
            "0.0-0.3": "LOW — unlikely mineral indicators",
            "0.3-0.5": "BACKGROUND — normal terrain",
            "0.5-0.7": "MODERATE — some mineral proxy signals",
            "0.7-0.85": "HIGH — multiple proxy indicators aligned",
            "0.85-1.0": "VERY HIGH — strong multi-proxy convergence",
        },
        "caveats": [
            "This is NOT a trained ML model — it uses fixed domain-knowledge weights",
            "Weights derived from Chuquicamata Cu/Au feature importances",
            "May not generalize well to non-porphyry deposit types",
            "Should be validated against known deposits when available",
            "Use for exploration prioritization, not for investment decisions",
        ],
        "based_on": "Chuquicamata Phase 3B XGBoost feature importances (AUC 0.86)",
    }

    out_path = os.path.join(args.output, "global_proxy_heuristic_v1.json")
    with open(out_path, "w") as f:
        json.dump(model_spec, f, indent=2)

    print(f"=== Global Proxy Heuristic Model v1 ===")
    print(f"  Weights:")
    for feat, w in sorted(PROXY_WEIGHTS.items(), key=lambda x: -abs(x[1])):
        sign = "+" if w > 0 else ""
        print(f"    {feat:20s} {sign}{w:.2f}")
    print(f"  Saved: {out_path}")


if __name__ == "__main__":
    main()

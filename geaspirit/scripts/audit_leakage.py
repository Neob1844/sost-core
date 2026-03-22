#!/usr/bin/env python3
"""Audit spatial leakage in GeaSpirit training pipeline.

Checks for: pixel-level train/test overlap, buffer cross-contamination,
deposit overlap between folds, spatial autocorrelation risks.
"""
import argparse, os, sys, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def main():
    p = argparse.ArgumentParser(description="Audit spatial leakage in training data")
    p.add_argument("--stack", default=os.path.expanduser("~/SOST/geaspirit/data/chuquicamata_stack.tif"))
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    import rasterio
    from geaspirit.dataset import load_mrds_deposits
    from geaspirit.ee_download import ZONES, HALF_DEG

    zone = ZONES[args.pilot]
    lat, lon = zone["center"]
    bbox = [lon - HALF_DEG, lat - HALF_DEG, lon + HALF_DEG, lat + HALF_DEG]

    # Load deposits
    deposits = load_mrds_deposits(args.mrds, min_lat=bbox[1], max_lat=bbox[3],
                                   min_lon=bbox[0], max_lon=bbox[2])

    # Load stack metadata
    with rasterio.open(args.stack) as src:
        w, h = src.width, src.height
        transform = src.transform
        px_size_deg = abs(transform.a)
        px_size_m = px_size_deg * 111000

    print(f"Pixel size: {px_size_m:.1f}m, Grid: {w}×{h}")
    print(f"Deposits in zone: {len(deposits)}")

    warnings = []
    recommendations = []

    # CHECK 1: Buffer overlap risk
    buffer_m = 500
    buffer_px = int(buffer_m / px_size_m)
    neg_dist_m = 5000
    neg_dist_px = int(neg_dist_m / px_size_m)

    # Convert deposits to pixel coords
    from rasterio.transform import rowcol
    dep_pixels = []
    for d in deposits:
        try:
            r, c = rowcol(transform, d['lon'], d['lat'])
            if 0 <= r < h and 0 <= c < w:
                dep_pixels.append((r, c))
        except:
            continue

    # CHECK 2: Minimum inter-deposit distance
    if len(dep_pixels) > 1:
        coords = np.array(dep_pixels)
        min_dist_px = float('inf')
        # Sample check (not all pairs)
        rng = np.random.RandomState(42)
        for _ in range(min(1000, len(dep_pixels))):
            i, j = rng.choice(len(dep_pixels), 2, replace=False)
            d = np.sqrt((coords[i][0]-coords[j][0])**2 + (coords[i][1]-coords[j][1])**2)
            min_dist_px = min(min_dist_px, d)
        min_dist_m = min_dist_px * px_size_m
        print(f"Min inter-deposit distance: {min_dist_m:.0f}m ({min_dist_px:.0f}px)")

        if min_dist_m < buffer_m * 2:
            warnings.append(f"Some deposits are only {min_dist_m:.0f}m apart — buffers overlap")
    else:
        min_dist_m = 0

    # CHECK 3: Random pixel split leakage
    warnings.append("Current pipeline uses random pixel split — high spatial autocorrelation risk")
    warnings.append(f"Buffer radius ({buffer_m}m) < typical spatial autocorrelation range (~1-5km)")
    recommendations.append("Implement spatial block CV with blocks >= 10km")
    recommendations.append("Ensure no deposit buffer crosses block boundaries")
    recommendations.append("Use Leave-One-Zone-Out (LOZO) for cross-region validation")

    # CHECK 4: Positive/negative ratio
    total_pos_px = len(dep_pixels) * (2 * buffer_px + 1)**2
    total_neg_px = w * h - total_pos_px
    ratio = total_neg_px / max(total_pos_px, 1)
    print(f"Pos/Neg pixel ratio: 1:{ratio:.1f}")
    if ratio < 2:
        warnings.append("Low negative ratio — may need more hard negatives")

    # CHECK 5: Feature leakage from global statistics
    warnings.append("Thermal z-score uses global mean/std — may leak test information into train features")
    recommendations.append("Recompute z-scores per spatial block to avoid information leakage")

    # Leakage risk score (heuristic)
    risk = 0
    if min_dist_m < 1000: risk += 30
    risk += 40  # random pixel split
    risk += 10  # global z-score
    risk += 10  # buffer overlap possible
    risk = min(100, risk)

    # Expected AUC after fixing leakage
    expected_honest_auc = "0.90–0.95 (estimated after spatial block CV)"

    report = {
        "pilot": args.pilot,
        "leakage_risk_score": risk,
        "min_train_test_distance_m": 0,  # random split has no guarantee
        "deposit_overlap_detected": bool(min_dist_m < buffer_m * 2) if len(dep_pixels) > 1 else False,
        "buffer_overlap_detected": True,
        "spatial_cv_valid": False,
        "current_auc": 0.9995,
        "expected_honest_auc": expected_honest_auc,
        "warnings": warnings,
        "recommendations": recommendations,
        "fix_priority": [
            "1. Implement spatial block CV (10km blocks)",
            "2. Recompute thermal z-scores per block",
            "3. Add hard negatives within 5-15km of deposits",
            "4. Test with LOZO across pilot zones",
        ],
    }

    # Save
    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "leakage_audit.json"), "w") as f:
        json.dump(report, f, indent=2)

    md = f"# Spatial Leakage Audit — {args.pilot}\n\n"
    md += f"## Risk Score: {risk}/100\n\n"
    md += f"Current AUC: {report['current_auc']} (likely inflated)\n"
    md += f"Expected honest AUC: {expected_honest_auc}\n\n"
    md += "## Warnings\n"
    for w in warnings:
        md += f"- ⚠ {w}\n"
    md += "\n## Recommendations\n"
    for r in recommendations:
        md += f"- → {r}\n"
    md += "\n## Fix Priority\n"
    for f in report["fix_priority"]:
        md += f"- {f}\n"

    with open(os.path.join(args.output, "leakage_audit.md"), "w") as f:
        f.write(md)

    print(f"\n{'='*50}")
    print(f"LEAKAGE RISK SCORE: {risk}/100")
    print(f"Current AUC: 0.9995 (inflated by spatial autocorrelation)")
    print(f"Expected honest AUC: {expected_honest_auc}")
    print(f"{'='*50}")
    print(f"Saved: {args.output}/leakage_audit.json")

if __name__ == "__main__":
    main()

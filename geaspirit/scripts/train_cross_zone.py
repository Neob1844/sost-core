#!/usr/bin/env python3
"""Priority 5 — Cross-zone validation (LOZO).

Leave-One-Zone-Out:
1. Train Chuquicamata + Pilbara → Test Zambia
2. Train Chuquicamata + Zambia  → Test Pilbara
3. Train Pilbara + Zambia       → Test Chuquicamata

Uses curated labels, geology-aware negatives, and geology features when available.
Reports per-zone AUC and explains failures.
"""
import argparse, os, sys, json, csv
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, HALF_DEG


def load_zone_data(pilot, data_dir, curated_dir, negatives_dir, geology_dir):
    """Load all data for a single zone. Returns None if stack missing."""
    import rasterio
    from rasterio.transform import rowcol

    stack_path = os.path.join(data_dir, f"{pilot}_stack.tif")
    geo_path = os.path.join(geology_dir, f"{pilot}_geology_stack.tif")
    mrds_path = os.path.join(curated_dir, "mrds_curated.csv")
    neg_path = os.path.join(negatives_dir, f"{pilot}_negatives.csv")

    if not os.path.exists(stack_path):
        return None

    # Load satellite stack
    meta_path = stack_path.replace(".tif", "_meta.json")
    with open(meta_path) as f:
        meta = json.load(f)
    with rasterio.open(stack_path) as src:
        sat_bands = src.read()
        transform = src.transform
        h, w = src.height, src.width

    px_deg = abs(transform.a)
    px_m = px_deg * 111000
    n_sat = sat_bands.shape[0]

    # Load geology if available
    geo_bands = None
    if os.path.exists(geo_path):
        with rasterio.open(geo_path) as gsrc:
            geo_bands = gsrc.read()

    # Load deposits for this zone
    zone = ZONES[pilot]
    lat_c, lon_c = zone["center"]
    bbox = [lon_c - HALF_DEG, lat_c - HALF_DEG, lon_c + HALF_DEG, lat_c + HALF_DEG]

    deposits = []
    if os.path.exists(mrds_path):
        with open(mrds_path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get("keep_for_training", "").lower() != "true":
                    continue
                try:
                    lat = float(row["latitude"])
                    lon = float(row["longitude"])
                    # Check if in this zone's bbox
                    if not (bbox[1] <= lat <= bbox[3] and bbox[0] <= lon <= bbox[2]):
                        continue
                    r, c = rowcol(transform, lon, lat)
                    if 0 <= r < h and 0 <= c < w:
                        deposits.append({"row": r, "col": c})
                except (ValueError, TypeError):
                    continue

    # Build positive mask
    buf_px = max(1, int(500 / px_m))
    pos_mask = np.zeros((h, w), dtype=bool)
    for d in deposits:
        r0, r1 = max(0, d["row"] - buf_px), min(h, d["row"] + buf_px + 1)
        c0, c1 = max(0, d["col"] - buf_px), min(w, d["col"] + buf_px + 1)
        pos_mask[r0:r1, c0:c1] = True

    # Load negatives
    neg_idx = []
    if os.path.exists(neg_path):
        with open(neg_path, newline='') as f:
            for row in csv.DictReader(f):
                r, c = int(row["row"]), int(row["col"])
                if 0 <= r < h and 0 <= c < w:
                    neg_idx.append((r, c))
    else:
        # Fallback: random far negatives
        neg_dist_px = max(1, int(5000 / px_m))
        near = np.zeros((h, w), dtype=bool)
        for d in deposits:
            r0, r1 = max(0, d["row"] - neg_dist_px), min(h, d["row"] + neg_dist_px + 1)
            c0, c1 = max(0, d["col"] - neg_dist_px), min(w, d["col"] + neg_dist_px + 1)
            near[r0:r1, c0:c1] = True
        valid = np.all(np.isfinite(sat_bands), axis=0)
        far = np.argwhere(~near & valid)
        rng = np.random.RandomState(42)
        max_neg = pos_mask.sum() * 3
        if len(far) > max_neg:
            sel = rng.choice(len(far), max_neg, replace=False)
            far = far[sel]
        neg_idx = [(r, c) for r, c in far]

    valid = np.all(np.isfinite(sat_bands), axis=0)
    pos_idx = np.argwhere(pos_mask & valid)

    # Subsample
    rng = np.random.RandomState(42)
    max_pos = min(len(pos_idx), 30000)
    max_neg = min(len(neg_idx), max_pos * 3)
    if len(pos_idx) > max_pos:
        sel = rng.choice(len(pos_idx), max_pos, replace=False)
        pos_idx = pos_idx[sel]
    neg_idx = np.array(neg_idx)
    if len(neg_idx) > max_neg:
        sel = rng.choice(len(neg_idx), max_neg, replace=False)
        neg_idx = neg_idx[sel]

    all_idx = np.vstack([pos_idx, neg_idx]) if len(neg_idx) > 0 else pos_idx
    y = np.array([1]*len(pos_idx) + [0]*len(neg_idx))

    # Build feature matrix
    X_sat = np.array([sat_bands[:, r, c] for r, c in all_idx], dtype=np.float32)
    if geo_bands is not None:
        X_geo = np.array([geo_bands[:, r, c] for r, c in all_idx], dtype=np.float32)
        X = np.hstack([X_sat, X_geo])
    else:
        X = X_sat

    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    return {
        "pilot": pilot,
        "X": X,
        "y": y,
        "n_deposits": len(deposits),
        "n_pos": int((y == 1).sum()),
        "n_neg": int((y == 0).sum()),
        "n_features": X.shape[1],
        "has_geology": geo_bands is not None,
    }


def main():
    p = argparse.ArgumentParser(description="Cross-zone LOZO validation")
    p.add_argument("--data-dir", default=os.path.expanduser("~/SOST/geaspirit/data"))
    p.add_argument("--curated-dir", default=os.path.expanduser("~/SOST/geaspirit/data/mrds"))
    p.add_argument("--negatives-dir", default=os.path.expanduser("~/SOST/geaspirit/data/targets"))
    p.add_argument("--geology-dir", default=os.path.expanduser("~/SOST/geaspirit/data/geology_maps"))
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    from sklearn.metrics import (roc_auc_score, precision_score, recall_score,
                                 f1_score, average_precision_score, brier_score_loss)
    from xgboost import XGBClassifier

    zone_names = ["chuquicamata", "pilbara", "zambia"]
    print("=== Cross-Zone LOZO Validation ===\n")

    # Load all zones
    zone_data = {}
    for zn in zone_names:
        data = load_zone_data(zn, args.data_dir, args.curated_dir,
                              args.negatives_dir, args.geology_dir)
        if data is not None:
            zone_data[zn] = data
            print(f"  {zn}: {data['n_pos']} pos + {data['n_neg']} neg = {len(data['y'])} samples, "
                  f"{data['n_features']} features, geology={'yes' if data['has_geology'] else 'no'}")
        else:
            print(f"  {zn}: NO DATA (satellite stack not found)")

    if len(zone_data) < 2:
        print(f"\n  ! Need at least 2 zones with data for LOZO. Found: {list(zone_data.keys())}")
        print(f"  ! Download satellite data for missing zones first.")

        # Write partial report
        os.makedirs(args.output, exist_ok=True)
        report = {
            "status": "INCOMPLETE",
            "zones_available": list(zone_data.keys()),
            "zones_missing": [z for z in zone_names if z not in zone_data],
            "reason": "Need at least 2 zones with satellite stacks for LOZO",
        }
        with open(os.path.join(args.output, "lozo_geology_aware.json"), "w") as f:
            json.dump(report, f, indent=2)
        with open(os.path.join(args.output, "lozo_geology_aware.md"), "w") as f:
            f.write(f"# LOZO Cross-Zone Validation\n\n**INCOMPLETE**: Only {list(zone_data.keys())} available.\n")
        return

    # Harmonize feature count (use minimum common features = satellite bands only)
    min_features = min(d["n_features"] for d in zone_data.values())
    print(f"\n  Common feature count: {min_features}")
    for zn in zone_data:
        if zone_data[zn]["n_features"] > min_features:
            zone_data[zn]["X"] = zone_data[zn]["X"][:, :min_features]
            zone_data[zn]["n_features"] = min_features

    # LOZO: leave each zone out
    lozo_results = []
    available_zones = list(zone_data.keys())

    for test_zone in available_zones:
        train_zones = [z for z in available_zones if z != test_zone]
        print(f"\n  LOZO: train=[{', '.join(train_zones)}] → test=[{test_zone}]")

        # Combine training data
        X_train = np.vstack([zone_data[z]["X"] for z in train_zones])
        y_train = np.concatenate([zone_data[z]["y"] for z in train_zones])

        X_test = zone_data[test_zone]["X"]
        y_test = zone_data[test_zone]["y"]

        print(f"    Train: {len(y_train)} samples ({(y_train==1).sum()} pos)")
        print(f"    Test:  {len(y_test)} samples ({(y_test==1).sum()} pos)")

        # Train
        model = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                              random_state=42, eval_metric='logloss')
        model.fit(X_train, y_train)

        probs = model.predict_proba(X_test)[:, 1]
        preds = (probs >= 0.5).astype(int)

        if len(np.unique(y_test)) < 2:
            print(f"    ! Only one class in test — cannot compute AUC")
            lozo_results.append({
                "test_zone": test_zone, "train_zones": train_zones,
                "status": "FAILED", "reason": "single class in test",
            })
            continue

        auc = roc_auc_score(y_test, probs)
        pr_auc = average_precision_score(y_test, probs)
        prec = precision_score(y_test, preds, zero_division=0)
        rec = recall_score(y_test, preds, zero_division=0)
        f1 = f1_score(y_test, preds, zero_division=0)
        brier = brier_score_loss(y_test, probs)

        print(f"    AUC={auc:.4f}  PR-AUC={pr_auc:.4f}  P={prec:.4f}  R={rec:.4f}  F1={f1:.4f}")

        result = {
            "test_zone": test_zone,
            "train_zones": train_zones,
            "status": "OK",
            "n_train": int(len(y_train)),
            "n_test": int(len(y_test)),
            "n_pos_test": int((y_test == 1).sum()),
            "auc": round(auc, 4),
            "pr_auc": round(pr_auc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "brier": round(brier, 4),
        }

        # Diagnosis if poor
        if auc < 0.55:
            result["diagnosis"] = "Near-random performance — geology/climate too different between zones"
        elif auc < 0.65:
            result["diagnosis"] = "Weak transfer — some geological signal transfers but significant domain shift"
        elif auc < 0.75:
            result["diagnosis"] = "Moderate transfer — core geological features generalize partially"
        else:
            result["diagnosis"] = "Good transfer — model captures universal geological indicators"

        lozo_results.append(result)

    # Save results
    os.makedirs(args.output, exist_ok=True)
    output = {
        "method": "LOZO (Leave-One-Zone-Out)",
        "zones_available": available_zones,
        "zones_missing": [z for z in zone_names if z not in zone_data],
        "n_features": min_features,
        "results": lozo_results,
    }

    # Average across successful LOZO runs
    ok_results = [r for r in lozo_results if r.get("status") == "OK"]
    if ok_results:
        output["average"] = {
            k: round(np.mean([r[k] for r in ok_results]), 4)
            for k in ["auc", "pr_auc", "precision", "recall", "f1", "brier"]
        }

    with open(os.path.join(args.output, "lozo_geology_aware.json"), "w") as f:
        json.dump(output, f, indent=2)

    # CSV
    csv_path = os.path.join(args.output, "lozo_zone_comparison.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["test_zone", "train_zones", "auc", "pr_auc", "precision",
                         "recall", "f1", "brier", "diagnosis"])
        for r in lozo_results:
            if r.get("status") == "OK":
                writer.writerow([r["test_zone"], "+".join(r["train_zones"]),
                                 r["auc"], r["pr_auc"], r["precision"],
                                 r["recall"], r["f1"], r["brier"],
                                 r.get("diagnosis", "")])

    # Markdown
    md = "# Cross-Zone LOZO Validation\n\n"
    if output.get("zones_missing"):
        md += f"**Warning**: Zones missing data: {output['zones_missing']}\n\n"
    md += "## Results\n\n"
    md += "| Test Zone | Train Zones | AUC | PR-AUC | Precision | Recall | F1 |\n"
    md += "|-----------|-------------|-----|--------|-----------|--------|----|\n"
    for r in lozo_results:
        if r.get("status") == "OK":
            md += f"| {r['test_zone']} | {'+'.join(r['train_zones'])} | "
            md += f"**{r['auc']}** | {r['pr_auc']} | {r['precision']} | {r['recall']} | {r['f1']} |\n"
        else:
            md += f"| {r['test_zone']} | — | FAILED | — | — | — | — |\n"
    if output.get("average"):
        avg = output["average"]
        md += f"\n**Average LOZO AUC: {avg['auc']}**\n"
    md += "\n## Diagnosis\n\n"
    for r in lozo_results:
        if r.get("diagnosis"):
            md += f"- **{r['test_zone']}**: {r['diagnosis']}\n"

    with open(os.path.join(args.output, "lozo_geology_aware.md"), "w") as f:
        f.write(md)

    print(f"\n  Saved: lozo_geology_aware.json, .md, lozo_zone_comparison.csv")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Pooled porphyry Cu training + LOZO + domain normalization comparison."""
import argparse, os, sys, json, csv
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def load_zone(name, stack_path, label_path, max_pos=30000):
    import rasterio
    from rasterio.transform import rowcol
    if not os.path.exists(stack_path) or not os.path.exists(label_path):
        return None
    with rasterio.open(stack_path) as src:
        bands = src.read(); transform = src.transform; h, w = src.height, src.width
    px_m = abs(transform.a) * 111000
    deposits = []
    with open(label_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get("keep_for_training","True").lower() != "true": continue
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
                r, c = rowcol(transform, lon, lat)
                if 0 <= r < h and 0 <= c < w: deposits.append((r, c))
            except: continue
    if len(deposits) < 3: return None
    buf_px = max(1, int(500 / px_m))
    pos_mask = np.zeros((h, w), dtype=bool)
    for r, c in deposits:
        r0, r1 = max(0, r-buf_px), min(h, r+buf_px+1)
        c0, c1 = max(0, c-buf_px), min(w, c+buf_px+1)
        pos_mask[r0:r1, c0:c1] = True
    valid = np.all(np.isfinite(bands), axis=0)
    pos_idx = np.argwhere(pos_mask & valid)
    neg_px = max(1, int(5000 / px_m))
    near = np.zeros((h, w), dtype=bool)
    for r, c in deposits:
        r0, r1 = max(0, r-neg_px), min(h, r+neg_px+1)
        c0, c1 = max(0, c-neg_px), min(w, c+neg_px+1)
        near[r0:r1, c0:c1] = True
    neg_idx = np.argwhere(~near & valid)
    rng = np.random.RandomState(42)
    if len(pos_idx) > max_pos:
        sel = rng.choice(len(pos_idx), max_pos, replace=False); pos_idx = pos_idx[sel]
    max_neg = len(pos_idx) * 3
    if len(neg_idx) > max_neg:
        sel = rng.choice(len(neg_idx), max_neg, replace=False); neg_idx = neg_idx[sel]
    all_idx = np.vstack([pos_idx, neg_idx]) if len(neg_idx) > 0 else pos_idx
    y = np.array([1]*len(pos_idx) + [0]*len(neg_idx))
    X = np.nan_to_num(np.array([bands[:, r, c] for r, c in all_idx], dtype=np.float32))
    return {"name": name, "X": X, "y": y, "n_bands": bands.shape[0],
            "n_deposits": len(deposits), "n_pos": len(pos_idx), "n_neg": len(neg_idx)}


def normalize_features(X):
    """Z-score normalization per feature (domain normalization)."""
    mean = np.nanmean(X, axis=0)
    std = np.nanstd(X, axis=0) + 1e-8
    return (X - mean) / std


def train_eval(X_tr, y_tr, X_te, y_te):
    from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score, average_precision_score
    from xgboost import XGBClassifier
    if len(np.unique(y_te)) < 2: return {"auc": 0.5, "status": "single_class"}
    model = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                          random_state=42, eval_metric='logloss')
    model.fit(X_tr, y_tr)
    probs = model.predict_proba(X_te)[:, 1]
    preds = (probs >= 0.5).astype(int)
    return {
        "auc": round(roc_auc_score(y_te, probs), 4),
        "pr_auc": round(average_precision_score(y_te, probs), 4),
        "precision": round(precision_score(y_te, preds, zero_division=0), 4),
        "recall": round(recall_score(y_te, preds, zero_division=0), 4),
        "f1": round(f1_score(y_te, preds, zero_division=0), 4),
        "status": "OK",
    }


def main():
    p = argparse.ArgumentParser(description="Pooled porphyry + LOZO + normalization")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    data_dir = os.path.expanduser("~/SOST/geaspirit/data")
    zones = {}

    # Load zones
    z = load_zone("chuquicamata",
                   os.path.join(data_dir, "chuquicamata_stack.tif"),
                   os.path.join(data_dir, "mrds/chuquicamata_mrds_curated.csv"))
    if z: zones["chuquicamata"] = z

    z = load_zone("arizona",
                   os.path.join(data_dir, "stack/arizona_porphyry_global_stack.tif"),
                   os.path.join(data_dir, "labels/arizona_porphyry_labels.csv"))
    if z: zones["arizona"] = z

    z = load_zone("peru",
                   os.path.join(data_dir, "stack/peru_porphyry_global_stack.tif"),
                   os.path.join(data_dir, "labels/peru_porphyry_labels_curated.csv"))
    if z: zones["peru"] = z

    print(f"=== Pooled Porphyry Training + LOZO ===\n")
    for name, z in zones.items():
        print(f"  {name}: {z['n_pos']} pos + {z['n_neg']} neg, {z['n_bands']} bands, {z['n_deposits']} deposits")

    if len(zones) < 2:
        print(f"\n  ! Need 2+ zones. Available: {list(zones.keys())}")
        return

    # Harmonize bands (use minimum common)
    min_bands = min(z["n_bands"] for z in zones.values())
    for zn in zones:
        if zones[zn]["X"].shape[1] > min_bands:
            zones[zn]["X"] = zones[zn]["X"][:, :min_bands]
    print(f"  Common bands: {min_bands}")

    zone_names = list(zones.keys())
    results = {"zones": zone_names, "common_bands": min_bands, "experiments": {}}

    # === EXPERIMENT 1: Direct transfer (baseline from Phase 5B) ===
    print(f"\n--- Direct Transfer (raw) ---")
    for train_z in zone_names:
        for test_z in zone_names:
            if train_z == test_z: continue
            r = train_eval(zones[train_z]["X"], zones[train_z]["y"],
                           zones[test_z]["X"], zones[test_z]["y"])
            key = f"direct_{train_z}_to_{test_z}"
            results["experiments"][key] = {**r, "mode": "direct_transfer", "features": "raw"}
            print(f"  {train_z} -> {test_z}: AUC={r['auc']}")

    # === EXPERIMENT 2: Direct transfer (normalized) ===
    print(f"\n--- Direct Transfer (z-score normalized) ---")
    zones_norm = {}
    for zn in zone_names:
        zones_norm[zn] = {"X": normalize_features(zones[zn]["X"]), "y": zones[zn]["y"]}
    for train_z in zone_names:
        for test_z in zone_names:
            if train_z == test_z: continue
            r = train_eval(zones_norm[train_z]["X"], zones_norm[train_z]["y"],
                           zones_norm[test_z]["X"], zones_norm[test_z]["y"])
            key = f"direct_norm_{train_z}_to_{test_z}"
            results["experiments"][key] = {**r, "mode": "direct_transfer_normalized", "features": "z-score"}
            print(f"  {train_z} -> {test_z}: AUC={r['auc']}")

    # === EXPERIMENT 3: Pooled training (raw) ===
    print(f"\n--- Pooled Training (raw) ---")
    X_all = np.vstack([zones[zn]["X"] for zn in zone_names])
    y_all = np.concatenate([zones[zn]["y"] for zn in zone_names])
    # Test on each zone using full pooled model
    from xgboost import XGBClassifier
    from sklearn.metrics import roc_auc_score
    model_pooled = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                                  random_state=42, eval_metric='logloss')
    model_pooled.fit(X_all, y_all)
    for test_z in zone_names:
        probs = model_pooled.predict_proba(zones[test_z]["X"])[:, 1]
        auc = roc_auc_score(zones[test_z]["y"], probs) if len(np.unique(zones[test_z]["y"])) >= 2 else 0.5
        key = f"pooled_raw_test_{test_z}"
        results["experiments"][key] = {"auc": round(auc, 4), "mode": "pooled_raw", "features": "raw"}
        print(f"  Pooled -> {test_z}: AUC={auc:.4f}")

    # === EXPERIMENT 4: Pooled training (normalized) ===
    print(f"\n--- Pooled Training (z-score normalized) ---")
    X_all_norm = np.vstack([zones_norm[zn]["X"] for zn in zone_names])
    model_pooled_norm = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                                       random_state=42, eval_metric='logloss')
    model_pooled_norm.fit(X_all_norm, y_all)
    for test_z in zone_names:
        probs = model_pooled_norm.predict_proba(zones_norm[test_z]["X"])[:, 1]
        auc = roc_auc_score(zones_norm[test_z]["y"], probs) if len(np.unique(zones_norm[test_z]["y"])) >= 2 else 0.5
        key = f"pooled_norm_test_{test_z}"
        results["experiments"][key] = {"auc": round(auc, 4), "mode": "pooled_normalized", "features": "z-score"}
        print(f"  Pooled-norm -> {test_z}: AUC={auc:.4f}")

    # === EXPERIMENT 5: LOZO (Leave-One-Zone-Out) ===
    print(f"\n--- LOZO (raw) ---")
    for held_out in zone_names:
        train_zones = [zn for zn in zone_names if zn != held_out]
        X_tr = np.vstack([zones[zn]["X"] for zn in train_zones])
        y_tr = np.concatenate([zones[zn]["y"] for zn in train_zones])
        r = train_eval(X_tr, y_tr, zones[held_out]["X"], zones[held_out]["y"])
        key = f"lozo_raw_heldout_{held_out}"
        results["experiments"][key] = {**r, "mode": "lozo_raw", "held_out": held_out}
        print(f"  LOZO (hold {held_out}): AUC={r['auc']}")

    # === EXPERIMENT 6: LOZO (normalized) ===
    print(f"\n--- LOZO (z-score normalized) ---")
    for held_out in zone_names:
        train_zones = [zn for zn in zone_names if zn != held_out]
        X_tr = np.vstack([zones_norm[zn]["X"] for zn in train_zones])
        y_tr = np.concatenate([zones_norm[zn]["y"] for zn in train_zones])
        r = train_eval(X_tr, y_tr, zones_norm[held_out]["X"], zones_norm[held_out]["y"])
        key = f"lozo_norm_heldout_{held_out}"
        results["experiments"][key] = {**r, "mode": "lozo_normalized", "held_out": held_out}
        print(f"  LOZO-norm (hold {held_out}): AUC={r['auc']}")

    # Save
    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "pooled_porphyry_lozo.json"), "w") as f:
        json.dump(results, f, indent=2)

    # Summary markdown
    md = "# Pooled Porphyry Cu — Generalization Comparison\n\n"
    md += "| Mode | Train | Test | Features | AUC |\n|------|-------|------|----------|-----|\n"
    for key, exp in sorted(results["experiments"].items()):
        mode = exp.get("mode","")
        auc = exp.get("auc", 0)
        feats = exp.get("features", "raw")
        train = key.split("_to_")[0] if "_to_" in key else "pooled/lozo"
        test = key.split("_to_")[-1] if "_to_" in key else key.split("_")[-1]
        md += f"| {mode} | {train} | {test} | {feats} | **{auc}** |\n"

    # Key comparison
    md += "\n## Key Comparison\n\n"
    direct_aucs = [v["auc"] for k, v in results["experiments"].items() if "direct_" in k and "norm" not in k]
    direct_norm_aucs = [v["auc"] for k, v in results["experiments"].items() if "direct_norm" in k]
    lozo_aucs = [v["auc"] for k, v in results["experiments"].items() if "lozo_raw" in k]
    lozo_norm_aucs = [v["auc"] for k, v in results["experiments"].items() if "lozo_norm" in k]

    md += f"| Approach | Avg AUC |\n|----------|----------|\n"
    if direct_aucs: md += f"| Direct transfer (raw) | {np.mean(direct_aucs):.4f} |\n"
    if direct_norm_aucs: md += f"| Direct transfer (normalized) | {np.mean(direct_norm_aucs):.4f} |\n"
    if lozo_aucs: md += f"| LOZO (raw) | {np.mean(lozo_aucs):.4f} |\n"
    if lozo_norm_aucs: md += f"| LOZO (normalized) | {np.mean(lozo_norm_aucs):.4f} |\n"

    with open(os.path.join(args.output, "pooled_porphyry_lozo.md"), "w") as f:
        f.write(md)
    print(f"\n  Saved: pooled_porphyry_lozo.json + .md")


if __name__ == "__main__":
    main()

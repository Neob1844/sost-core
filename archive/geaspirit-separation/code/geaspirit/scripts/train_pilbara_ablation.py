#!/usr/bin/env python3
"""Phase 4A Priority 7 — Pilbara ablation study.

Compares feature families with honest spatial block CV:
A) S2 only (5 bands)
B) Full satellite (19 bands)
C) Geophysics only (N bands)
D) Satellite + geophysics
E) Satellite + geophysics + geology
F) All + EMIT (only if available)

Reuses the spatial_block_cv engine from train_geology_aware.py.
"""
import argparse, os, sys, json, csv
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, HALF_DEG


def spatial_block_cv(X, y, folds_arr, n_folds=5):
    """Run spatial block CV and return per-fold + average metrics."""
    from sklearn.metrics import (roc_auc_score, precision_score, recall_score,
                                 f1_score, average_precision_score, brier_score_loss)
    from xgboost import XGBClassifier

    fold_metrics = []
    for fold_id in range(n_folds):
        test_mask = folds_arr == fold_id
        train_mask = ~test_mask
        if test_mask.sum() == 0 or train_mask.sum() == 0:
            continue
        X_tr, y_tr = X[train_mask], y[train_mask]
        X_te, y_te = X[test_mask], y[test_mask]

        model = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                              random_state=42, eval_metric='logloss')
        model.fit(X_tr, y_tr)
        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)

        if len(np.unique(y_te)) < 2:
            continue

        fold_metrics.append({
            "fold": fold_id,
            "auc": round(roc_auc_score(y_te, probs), 4),
            "pr_auc": round(average_precision_score(y_te, probs), 4),
            "precision": round(precision_score(y_te, preds, zero_division=0), 4),
            "recall": round(recall_score(y_te, preds, zero_division=0), 4),
            "f1": round(f1_score(y_te, preds, zero_division=0), 4),
            "brier": round(brier_score_loss(y_te, probs), 4),
        })

    if fold_metrics:
        avg = {k: round(np.mean([f[k] for f in fold_metrics]), 4)
               for k in ["auc", "pr_auc", "precision", "recall", "f1", "brier"]}
    else:
        avg = {"auc": 0, "pr_auc": 0, "precision": 0, "recall": 0, "f1": 0, "brier": 1}
    return avg, fold_metrics


def main():
    p = argparse.ArgumentParser(description="Pilbara ablation study")
    p.add_argument("--stack", default=os.path.expanduser("~/SOST/geaspirit/data/pilbara_stack.tif"))
    p.add_argument("--geophysics", default=os.path.expanduser("~/SOST/geaspirit/data/geophysics/pilbara_geophysics_stack.tif"))
    p.add_argument("--geology", default=os.path.expanduser("~/SOST/geaspirit/data/geology_maps/pilbara_geology_stack.tif"))
    p.add_argument("--emit", default=os.path.expanduser("~/SOST/geaspirit/data/emit/pilbara_emit_stack.tif"))
    p.add_argument("--mrds-curated", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/pilbara_mrds_curated.csv"))
    p.add_argument("--negatives", default=os.path.expanduser("~/SOST/geaspirit/data/targets/pilbara_negatives.csv"))
    p.add_argument("--block-km", type=float, default=10.0)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--buffer-m", type=float, default=500)
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    p.add_argument("--models", default=os.path.expanduser("~/SOST/geaspirit/models"))
    args = p.parse_args()

    import rasterio
    from rasterio.transform import rowcol

    if not os.path.exists(args.stack):
        print(f"  ! Satellite stack not found: {args.stack}")
        return

    print(f"=== Pilbara Ablation Study ===")

    # Load satellite stack
    meta_path = args.stack.replace(".tif", "_meta.json")
    with open(meta_path) as f:
        stack_meta = json.load(f)
    with rasterio.open(args.stack) as src:
        sat_bands = src.read()
        transform = src.transform
        h, w = src.height, src.width
    px_m = abs(transform.a) * 111000
    n_sat = sat_bands.shape[0]
    sat_names = stack_meta.get("bands", [f"sat_{i}" for i in range(n_sat)])
    print(f"  Satellite: {n_sat} bands")

    # Load optional stacks
    def load_optional(path, label):
        if os.path.exists(path):
            with rasterio.open(path) as src:
                data = src.read()
            print(f"  {label}: {data.shape[0]} bands")
            return data
        print(f"  {label}: not available")
        return None

    geo_bands = load_optional(args.geophysics, "Geophysics")
    geol_bands = load_optional(args.geology, "Geology")
    emit_bands = load_optional(args.emit, "EMIT")

    # Load curated deposits
    deposits = []
    if os.path.exists(args.mrds_curated):
        with open(args.mrds_curated, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get("keep_for_training", "").lower() != "true":
                    continue
                try:
                    lat, lon = float(row["latitude"]), float(row["longitude"])
                    r, c = rowcol(transform, lon, lat)
                    if 0 <= r < h and 0 <= c < w:
                        deposits.append({"row": r, "col": c})
                except (ValueError, TypeError):
                    continue
    print(f"  Curated deposits: {len(deposits)}")

    if len(deposits) < 5:
        print(f"  ! Too few deposits for training — aborting")
        return

    # Build positive mask
    buf_px = max(1, int(args.buffer_m / px_m))
    pos_mask = np.zeros((h, w), dtype=bool)
    for d in deposits:
        r0, r1 = max(0, d["row"] - buf_px), min(h, d["row"] + buf_px + 1)
        c0, c1 = max(0, d["col"] - buf_px), min(w, d["col"] + buf_px + 1)
        pos_mask[r0:r1, c0:c1] = True

    # Load negatives
    neg_pixels = []
    if os.path.exists(args.negatives):
        with open(args.negatives, newline='') as f:
            for row in csv.DictReader(f):
                r, c = int(row["row"]), int(row["col"])
                if 0 <= r < h and 0 <= c < w:
                    neg_pixels.append((r, c))
        print(f"  Negatives: {len(neg_pixels)}")
    else:
        # Fallback
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
        neg_pixels = [(r, c) for r, c in far]
        print(f"  Negatives (fallback): {len(neg_pixels)}")

    # Build samples
    valid = np.all(np.isfinite(sat_bands), axis=0)
    pos_idx = np.argwhere(pos_mask & valid)
    neg_idx = np.array(neg_pixels) if neg_pixels else np.empty((0, 2), dtype=int)

    rng = np.random.RandomState(42)
    max_pos = min(len(pos_idx), 60000)
    max_neg = min(len(neg_idx), max_pos * 3)
    if len(pos_idx) > max_pos:
        sel = rng.choice(len(pos_idx), max_pos, replace=False)
        pos_idx = pos_idx[sel]
    if len(neg_idx) > max_neg:
        sel = rng.choice(len(neg_idx), max_neg, replace=False)
        neg_idx = neg_idx[sel]

    all_idx = np.vstack([pos_idx, neg_idx]) if len(neg_idx) > 0 else pos_idx
    y = np.array([1]*len(pos_idx) + [0]*len(neg_idx))
    print(f"  Samples: {len(pos_idx)} pos + {len(neg_idx)} neg = {len(y)}")

    # Build fold map
    block_px = max(1, int(args.block_km * 1000 / px_m))
    n_blocks_c = (w + block_px - 1) // block_px
    rng2 = np.random.RandomState(42)
    n_blocks_r = (h + block_px - 1) // block_px
    total_blocks = n_blocks_r * n_blocks_c
    block_ids = np.arange(total_blocks)
    rng2.shuffle(block_ids)
    fold_map = np.full((h, w), -1, dtype=int)
    for br in range(n_blocks_r):
        for bc in range(n_blocks_c):
            bid = br * n_blocks_c + bc
            r0, r1 = br * block_px, min((br + 1) * block_px, h)
            c0, c1 = bc * block_px, min((bc + 1) * block_px, w)
            fold_map[r0:r1, c0:c1] = block_ids[bid] % args.folds
    folds_arr = np.array([fold_map[r, c] for r, c in all_idx])

    # Extract feature matrices
    X_sat = np.nan_to_num(np.array([sat_bands[:, r, c] for r, c in all_idx], dtype=np.float32))

    def extract_opt(bands):
        if bands is None:
            return None
        return np.nan_to_num(np.array([bands[:, r, c] for r, c in all_idx], dtype=np.float32))

    X_geo = extract_opt(geo_bands)
    X_geol = extract_opt(geol_bands)
    X_emit = extract_opt(emit_bands)

    s2_idx = list(range(0, min(5, n_sat)))

    # Define experiments
    experiments = {}
    experiments["A_s2_only"] = {"X": X_sat[:, s2_idx], "desc": f"S2 only ({len(s2_idx)} bands)"}
    experiments["B_full_sat"] = {"X": X_sat, "desc": f"Full satellite ({n_sat} bands)"}

    if X_geo is not None and X_geo.shape[1] > 0:
        # Check if geophysics has real data (not just placeholder zeros)
        if np.any(X_geo != 0):
            experiments["C_geophysics_only"] = {"X": X_geo, "desc": f"Geophysics only ({X_geo.shape[1]} bands)"}
            experiments["D_sat_geophysics"] = {"X": np.hstack([X_sat, X_geo]),
                                                "desc": f"Satellite + geophysics ({X_sat.shape[1]+X_geo.shape[1]} bands)"}
            if X_geol is not None:
                experiments["E_sat_geo_geol"] = {
                    "X": np.hstack([X_sat, X_geo, X_geol]),
                    "desc": f"Satellite + geophysics + geology ({X_sat.shape[1]+X_geo.shape[1]+X_geol.shape[1]} bands)",
                }
        else:
            print("  ! Geophysics stack has no real data — skipping geophysics experiments")

    if X_emit is not None and np.any(X_emit != 0):
        all_non_emit = [X_sat]
        if X_geo is not None and np.any(X_geo != 0):
            all_non_emit.append(X_geo)
        if X_geol is not None:
            all_non_emit.append(X_geol)
        experiments["F_all_plus_emit"] = {
            "X": np.hstack(all_non_emit + [X_emit]),
            "desc": f"All + EMIT ({sum(x.shape[1] for x in all_non_emit) + X_emit.shape[1]} bands)",
        }

    # Run ablation
    results = {}
    best_model_name = None
    best_auc = 0

    print(f"\n  === ABLATION ({len(experiments)} experiments) ===\n")
    for name, exp in experiments.items():
        print(f"  [{name}] {exp['desc']}")
        avg, folds = spatial_block_cv(exp["X"], y, folds_arr, args.folds)
        results[name] = {"description": exp["desc"], "n_features": exp["X"].shape[1],
                         "average": avg, "per_fold": folds}
        print(f"    AUC={avg['auc']:.4f}  PR-AUC={avg['pr_auc']:.4f}  "
              f"P={avg['precision']:.4f}  R={avg['recall']:.4f}  F1={avg['f1']:.4f}")
        if avg["auc"] > best_auc:
            best_auc = avg["auc"]
            best_model_name = name

    # Train best model on all data
    print(f"\n  Best: {best_model_name} (AUC={best_auc:.4f})")
    from xgboost import XGBClassifier
    import joblib
    best_X = experiments[best_model_name]["X"]
    final_model = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                                random_state=42, eval_metric='logloss')
    final_model.fit(best_X, y)

    os.makedirs(args.models, exist_ok=True)
    model_path = os.path.join(args.models, "pilbara_best_model.joblib")
    joblib.dump({"model": final_model, "experiment": best_model_name,
                 "n_features": best_X.shape[1]}, model_path)

    # Chuquicamata comparison
    chuq_baseline = {"auc": 0.8622, "pr_auc": 0.9532, "precision": 0.948,
                     "recall": 0.760, "f1": 0.837}

    # Save
    os.makedirs(args.output, exist_ok=True)
    output = {
        "pilot": "pilbara",
        "experiments": results,
        "best_experiment": best_model_name,
        "best_auc": best_auc,
        "chuquicamata_comparison": chuq_baseline,
        "n_deposits": len(deposits),
        "n_samples": len(y),
        "geophysics_available": bool(X_geo is not None and np.any(X_geo != 0)) if X_geo is not None else False,
        "emit_available": bool(X_emit is not None and np.any(X_emit != 0)) if X_emit is not None else False,
    }
    with open(os.path.join(args.output, "pilbara_ablation.json"), "w") as f:
        json.dump(output, f, indent=2)

    # Markdown
    md = "# Pilbara Ablation Study\n\n"
    md += "## Results (honest spatial block CV)\n\n"
    md += "| Experiment | Features | AUC | PR-AUC | P | R | F1 | Brier |\n"
    md += "|---|---|---|---|---|---|---|---|\n"
    for name, res in results.items():
        avg = res["average"]
        md += f"| {name} | {res['n_features']} | **{avg['auc']}** | {avg['pr_auc']} | "
        md += f"{avg['precision']} | {avg['recall']} | {avg['f1']} | {avg['brier']} |\n"
    md += f"\n## Best: **{best_model_name}** (AUC={best_auc:.4f})\n\n"
    md += f"## vs Chuquicamata (Phase 3B best: AUC={chuq_baseline['auc']})\n\n"
    if best_auc > chuq_baseline["auc"]:
        md += f"Pilbara **exceeds** Chuquicamata by +{best_auc - chuq_baseline['auc']:.4f} AUC\n"
    elif best_auc > chuq_baseline["auc"] - 0.05:
        md += f"Pilbara is **comparable** to Chuquicamata (delta={best_auc - chuq_baseline['auc']:+.4f})\n"
    else:
        md += f"Pilbara **underperforms** Chuquicamata by {chuq_baseline['auc'] - best_auc:.4f} AUC\n"

    # Geophysics contribution
    sat_only = results.get("B_full_sat", {}).get("average", {}).get("auc", 0)
    sat_geo = results.get("D_sat_geophysics", {}).get("average", {}).get("auc", 0)
    if sat_geo > 0:
        delta_geo = sat_geo - sat_only
        md += f"\n## Geophysics Contribution\n"
        md += f"- Satellite only: AUC={sat_only:.4f}\n"
        md += f"- Satellite + geophysics: AUC={sat_geo:.4f}\n"
        md += f"- **Delta: {delta_geo:+.4f}**\n"
        if delta_geo > 0.03:
            md += f"- Open geophysics provides **meaningful improvement**\n"
        elif delta_geo > 0:
            md += f"- Open geophysics provides **marginal improvement**\n"
        else:
            md += f"- Open geophysics **does not help** (may need better alignment or features)\n"

    with open(os.path.join(args.output, "pilbara_ablation.md"), "w") as f:
        f.write(md)
    print(f"\n  Saved: pilbara_ablation.json + .md")


if __name__ == "__main__":
    main()

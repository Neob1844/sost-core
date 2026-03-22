#!/usr/bin/env python3
"""Spatial Block Cross-Validation for GeaSpirit Platform.

Divides the study area into ~10km blocks. All pixels in a block go to
the same fold. This eliminates spatial autocorrelation leakage.
"""
import argparse, os, sys, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def main():
    p = argparse.ArgumentParser(description="Spatial block CV — honest AUC")
    p.add_argument("--stack", default=os.path.expanduser("~/SOST/geaspirit/data/chuquicamata_stack.tif"))
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--block-km", type=float, default=10.0)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--buffer-m", type=float, default=500)
    p.add_argument("--neg-dist-m", type=float, default=5000)
    p.add_argument("--hard-neg-km", type=float, default=12)
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    import rasterio
    from rasterio.transform import rowcol
    from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score, average_precision_score
    from xgboost import XGBClassifier
    from geaspirit.dataset import load_mrds_deposits
    from geaspirit.ee_download import ZONES, HALF_DEG

    zone = ZONES[args.pilot]
    lat, lon = zone["center"]
    bbox = [lon - HALF_DEG, lat - HALF_DEG, lon + HALF_DEG, lat + HALF_DEG]

    # Load stack
    print("→ Loading stack...")
    meta_path = args.stack.replace(".tif", "_meta.json")
    with open(meta_path) as f:
        meta = json.load(f)
    with rasterio.open(args.stack) as src:
        all_bands = src.read()  # (n_bands, h, w)
        transform = src.transform
        h, w = src.height, src.width

    n_bands = all_bands.shape[0]
    px_deg = abs(transform.a)
    px_m = px_deg * 111000
    print(f"  Stack: {w}×{h}, {n_bands} bands, {px_m:.1f}m/px")

    # Load deposits
    deposits = load_mrds_deposits(args.mrds, min_lat=bbox[1], max_lat=bbox[3],
                                   min_lon=bbox[0], max_lon=bbox[2])
    print(f"  Deposits: {len(deposits)}")

    # Convert deposits to pixel coords
    dep_rc = []
    for d in deposits:
        try:
            r, c = rowcol(transform, d['lon'], d['lat'])
            if 0 <= r < h and 0 <= c < w:
                dep_rc.append((r, c))
        except:
            continue

    # Create spatial blocks
    block_px = max(1, int(args.block_km * 1000 / px_m))
    n_blocks_r = (h + block_px - 1) // block_px
    n_blocks_c = (w + block_px - 1) // block_px
    total_blocks = n_blocks_r * n_blocks_c
    print(f"  Blocks: {n_blocks_r}×{n_blocks_c} = {total_blocks} ({args.block_km}km each)")

    # Assign blocks to folds
    rng = np.random.RandomState(42)
    block_ids = np.arange(total_blocks)
    rng.shuffle(block_ids)
    block_fold = np.zeros(total_blocks, dtype=int)
    for i, bid in enumerate(block_ids):
        block_fold[bid] = i % args.folds

    # Build pixel-level fold map
    fold_map = np.full((h, w), -1, dtype=int)
    for br in range(n_blocks_r):
        for bc in range(n_blocks_c):
            bid = br * n_blocks_c + bc
            r0, r1 = br * block_px, min((br + 1) * block_px, h)
            c0, c1 = bc * block_px, min((bc + 1) * block_px, w)
            fold_map[r0:r1, c0:c1] = block_fold[bid]

    # Build positive mask with buffer
    buf_px = max(1, int(args.buffer_m / px_m))
    pos_mask = np.zeros((h, w), dtype=bool)
    for r, c in dep_rc:
        r0, r1 = max(0, r - buf_px), min(h, r + buf_px + 1)
        c0, c1 = max(0, c - buf_px), min(w, c + buf_px + 1)
        pos_mask[r0:r1, c0:c1] = True

    # Build negative mask (far from deposits)
    neg_dist_px = max(1, int(args.neg_dist_m / px_m))
    near_mask = np.zeros((h, w), dtype=bool)
    for r, c in dep_rc:
        r0, r1 = max(0, r - neg_dist_px), min(h, r + neg_dist_px + 1)
        c0, c1 = max(0, c - neg_dist_px), min(w, c + neg_dist_px + 1)
        near_mask[r0:r1, c0:c1] = True
    neg_mask = ~near_mask

    # Hard negatives: within hard_neg_km but outside buffer
    hard_neg_px = max(1, int(args.hard_neg_km * 1000 / px_m))
    hard_zone = np.zeros((h, w), dtype=bool)
    for r, c in dep_rc:
        r0, r1 = max(0, r - hard_neg_px), min(h, r + hard_neg_px + 1)
        c0, c1 = max(0, c - hard_neg_px), min(w, c + hard_neg_px + 1)
        hard_zone[r0:r1, c0:c1] = True
    hard_neg_mask = hard_zone & ~pos_mask & ~neg_mask  # in hard zone, not positive, not far negative

    # NaN mask
    valid = np.all(np.isfinite(all_bands), axis=0)

    # Extract samples
    pos_idx = np.argwhere(pos_mask & valid)
    neg_idx = np.argwhere(neg_mask & valid)
    hard_idx = np.argwhere(hard_neg_mask & valid)

    # Subsample negatives
    max_neg = len(pos_idx) * 2
    if len(neg_idx) > max_neg:
        sel = rng.choice(len(neg_idx), max_neg, replace=False)
        neg_idx = neg_idx[sel]
    max_hard = len(pos_idx)
    if len(hard_idx) > max_hard:
        sel = rng.choice(len(hard_idx), max_hard, replace=False)
        hard_idx = hard_idx[sel]

    all_idx = np.vstack([pos_idx, neg_idx, hard_idx])
    y = np.array([1]*len(pos_idx) + [0]*len(neg_idx) + [0]*len(hard_idx))
    X = np.array([all_bands[:, r, c] for r, c in all_idx], dtype=np.float32)
    folds = np.array([fold_map[r, c] for r, c in all_idx])

    print(f"  Samples: {len(pos_idx)} pos + {len(neg_idx)} neg + {len(hard_idx)} hard neg = {len(y)}")
    print(f"  Hard negatives: {len(hard_idx)} ({args.hard_neg_km}km zone)")

    # Spatial Block CV
    fold_metrics = []
    all_probs = np.full(len(y), np.nan)

    for fold_id in range(args.folds):
        test_mask = folds == fold_id
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
        all_probs[test_mask] = probs

        if len(np.unique(y_te)) < 2:
            print(f"  Fold {fold_id}: only one class in test — skipping")
            continue

        auc = roc_auc_score(y_te, probs)
        pr_auc = average_precision_score(y_te, probs)
        prec = precision_score(y_te, preds, zero_division=0)
        rec = recall_score(y_te, preds, zero_division=0)
        f1 = f1_score(y_te, preds, zero_division=0)

        fold_metrics.append({"fold": fold_id, "n_test": int(test_mask.sum()),
                             "n_pos_test": int(y_te.sum()),
                             "auc": round(auc, 4), "pr_auc": round(pr_auc, 4),
                             "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4)})
        print(f"  Fold {fold_id}: AUC={auc:.4f} PR-AUC={pr_auc:.4f} P={prec:.4f} R={rec:.4f} F1={f1:.4f} (n_test={test_mask.sum()}, pos={y_te.sum()})")

    # Average metrics
    if fold_metrics:
        avg = {k: round(np.mean([f[k] for f in fold_metrics]), 4)
               for k in ["auc", "pr_auc", "precision", "recall", "f1"]}
    else:
        avg = {"auc": 0, "pr_auc": 0, "precision": 0, "recall": 0, "f1": 0}

    results = {
        "pilot": args.pilot,
        "method": "spatial_block_cv",
        "block_km": args.block_km,
        "folds": args.folds,
        "total_samples": len(y),
        "positive_samples": int((y == 1).sum()),
        "negative_samples": int((y == 0).sum()),
        "hard_negatives": len(hard_idx),
        "naive_auc_for_comparison": 0.9995,
        "spatial_cv_average": avg,
        "per_fold": fold_metrics,
    }

    # Save
    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "spatial_cv_metrics.json"), "w") as f:
        json.dump(results, f, indent=2)

    md = f"# Spatial Block CV — {args.pilot}\n\n"
    md += f"Blocks: {n_blocks_r}×{n_blocks_c} ({args.block_km}km), {args.folds} folds\n\n"
    md += f"| Metric | Naive CV | Spatial Block CV | Delta |\n|--------|---------|-----------------|-------|\n"
    md += f"| AUC-ROC | 0.9995 | **{avg['auc']:.4f}** | {avg['auc']-0.9995:+.4f} |\n"
    md += f"| PR-AUC | — | **{avg['pr_auc']:.4f}** | — |\n"
    md += f"| Precision | 0.9916 | **{avg['precision']:.4f}** | {avg['precision']-0.9916:+.4f} |\n"
    md += f"| Recall | 0.9994 | **{avg['recall']:.4f}** | {avg['recall']-0.9994:+.4f} |\n"
    md += f"| F1 | — | **{avg['f1']:.4f}** | — |\n\n"
    md += "This is the **scientifically honest** metric.\n"
    with open(os.path.join(args.output, "spatial_cv_metrics.md"), "w") as f:
        f.write(md)

    print(f"\n{'='*60}")
    print(f"SPATIAL BLOCK CV RESULTS ({args.pilot}):")
    print(f"  Naive AUC:       0.9995 (inflated)")
    print(f"  Spatial CV AUC:  {avg['auc']:.4f} (honest)")
    print(f"  Precision:       {avg['precision']:.4f}")
    print(f"  Recall:          {avg['recall']:.4f}")
    print(f"  F1:              {avg['f1']:.4f}")
    print(f"  PR-AUC:          {avg['pr_auc']:.4f}")
    print(f"{'='*60}")

    # Train final model on all data for prediction
    print("→ Training final model on all data...")
    final_model = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                                random_state=42, eval_metric='logloss')
    final_model.fit(X, y)
    import joblib
    joblib.dump(final_model, os.path.join(args.output, "final_model_spatial_cv.joblib"))
    print(f"  Saved: final_model_spatial_cv.joblib")

    # Save OOF predictions
    np.save(os.path.join(args.output, "oof_probs.npy"), all_probs)
    np.save(os.path.join(args.output, "oof_labels.npy"), y)

if __name__ == "__main__":
    main()

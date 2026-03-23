#!/usr/bin/env python3
"""Kalgoorlie benchmark: honest spatial block CV with Australian labels."""
import argparse, os, sys, json, csv
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def spatial_block_cv(X, y, folds_arr, n_folds=5):
    from sklearn.metrics import (roc_auc_score, precision_score, recall_score,
                                 f1_score, average_precision_score, brier_score_loss)
    from xgboost import XGBClassifier
    fold_metrics = []
    for fold_id in range(n_folds):
        te = folds_arr == fold_id; tr = ~te
        if te.sum() == 0 or tr.sum() == 0: continue
        m = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                          random_state=42, eval_metric='logloss')
        m.fit(X[tr], y[tr])
        probs = m.predict_proba(X[te])[:, 1]
        preds = (probs >= 0.5).astype(int)
        if len(np.unique(y[te])) < 2: continue
        fold_metrics.append({
            "auc": round(roc_auc_score(y[te], probs), 4),
            "pr_auc": round(average_precision_score(y[te], probs), 4),
            "precision": round(precision_score(y[te], preds, zero_division=0), 4),
            "recall": round(recall_score(y[te], preds, zero_division=0), 4),
            "f1": round(f1_score(y[te], preds, zero_division=0), 4),
            "brier": round(brier_score_loss(y[te], probs), 4),
        })
    if fold_metrics:
        avg = {k: round(np.mean([f[k] for f in fold_metrics]), 4)
               for k in ["auc", "pr_auc", "precision", "recall", "f1", "brier"]}
    else:
        avg = {"auc": 0, "pr_auc": 0, "precision": 0, "recall": 0, "f1": 0, "brier": 1}
    return avg, fold_metrics


def main():
    p = argparse.ArgumentParser(description="Kalgoorlie spatial CV benchmark")
    p.add_argument("--aoi", default="kalgoorlie_50km")
    p.add_argument("--stack", default=None)
    p.add_argument("--labels", default=None)
    p.add_argument("--geology", default=None)
    p.add_argument("--block-km", type=float, default=10.0)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--buffer-m", type=float, default=500)
    p.add_argument("--aoi-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    p.add_argument("--stack-dir", default=os.path.expanduser("~/SOST/geaspirit/data/stack"))
    p.add_argument("--label-dir", default=os.path.expanduser("~/SOST/geaspirit/data/labels"))
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    p.add_argument("--models", default=os.path.expanduser("~/SOST/geaspirit/models"))
    args = p.parse_args()

    import rasterio
    from rasterio.transform import rowcol

    # Find files
    if args.stack is None:
        args.stack = os.path.join(args.stack_dir, f"{args.aoi}_global_stack.tif")
    if args.labels is None:
        args.labels = os.path.join(args.label_dir, f"{args.aoi}_labels_curated.csv")
    if args.geology is None:
        geo_path = os.path.expanduser(f"~/SOST/geaspirit/data/geology_maps/{args.aoi}_geology_stack.tif")
        if os.path.exists(geo_path):
            args.geology = geo_path

    if not os.path.exists(args.stack):
        print(f"  ! Stack not found: {args.stack}"); return
    if not os.path.exists(args.labels):
        print(f"  ! Labels not found: {args.labels}"); return

    print(f"=== Kalgoorlie Spatial CV Benchmark: {args.aoi} ===")

    # Load stack
    meta_path = args.stack.replace(".tif", "_metadata.json")
    with open(meta_path) as f:
        meta = json.load(f)
    with rasterio.open(args.stack) as src:
        sat = src.read(); transform = src.transform; h, w = src.height, src.width
    n_sat = sat.shape[0]
    px_m = abs(transform.a) * 111000
    print(f"  Stack: {w}x{h}, {n_sat} bands, {px_m:.1f}m/px")

    # Load optional geology
    geo = None
    if args.geology and os.path.exists(args.geology):
        with rasterio.open(args.geology) as gsrc:
            geo = gsrc.read()
        print(f"  Geology: {geo.shape[0]} bands")

    # Load labels
    deposits = []
    with open(args.labels, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get("keep_for_training", "").lower() != "true": continue
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
                r, c = rowcol(transform, lon, lat)
                if 0 <= r < h and 0 <= c < w:
                    deposits.append({"row": r, "col": c})
            except: continue
    print(f"  Deposits: {len(deposits)}")

    if len(deposits) < 5:
        print(f"  ! Too few deposits ({len(deposits)}) — aborting")
        os.makedirs(args.output, exist_ok=True)
        with open(os.path.join(args.output, f"{args.aoi}_spatial_cv.json"), "w") as f:
            json.dump({"status": "INSUFFICIENT_LABELS", "deposits": len(deposits)}, f, indent=2)
        return

    # Build masks
    buf_px = max(1, int(args.buffer_m / px_m))
    pos_mask = np.zeros((h, w), dtype=bool)
    for d in deposits:
        r0, r1 = max(0, d["row"]-buf_px), min(h, d["row"]+buf_px+1)
        c0, c1 = max(0, d["col"]-buf_px), min(w, d["col"]+buf_px+1)
        pos_mask[r0:r1, c0:c1] = True

    valid = np.all(np.isfinite(sat), axis=0)
    pos_idx = np.argwhere(pos_mask & valid)

    # Negatives: far from deposits
    neg_px = max(1, int(5000 / px_m))
    near = np.zeros((h, w), dtype=bool)
    for d in deposits:
        r0, r1 = max(0, d["row"]-neg_px), min(h, d["row"]+neg_px+1)
        c0, c1 = max(0, d["col"]-neg_px), min(w, d["col"]+neg_px+1)
        near[r0:r1, c0:c1] = True
    neg_idx = np.argwhere(~near & valid)
    rng = np.random.RandomState(42)
    max_pos = min(len(pos_idx), 60000)
    max_neg = min(len(neg_idx), max_pos * 3)
    if len(pos_idx) > max_pos:
        sel = rng.choice(len(pos_idx), max_pos, replace=False); pos_idx = pos_idx[sel]
    if len(neg_idx) > max_neg:
        sel = rng.choice(len(neg_idx), max_neg, replace=False); neg_idx = neg_idx[sel]

    all_idx = np.vstack([pos_idx, neg_idx])
    y = np.array([1]*len(pos_idx) + [0]*len(neg_idx))
    print(f"  Samples: {len(pos_idx)} pos + {len(neg_idx)} neg = {len(y)}")

    # Fold map
    block_px = max(1, int(args.block_km * 1000 / px_m))
    nbr = (h + block_px - 1) // block_px; nbc = (w + block_px - 1) // block_px
    bids = np.arange(nbr * nbc); rng.shuffle(bids)
    fold_map = np.full((h, w), -1, dtype=int)
    for br in range(nbr):
        for bc in range(nbc):
            r0, r1 = br*block_px, min((br+1)*block_px, h)
            c0, c1 = bc*block_px, min((bc+1)*block_px, w)
            fold_map[r0:r1, c0:c1] = bids[br*nbc+bc] % args.folds
    folds_arr = np.array([fold_map[r, c] for r, c in all_idx])

    # Extract features
    X_sat = np.nan_to_num(np.array([sat[:, r, c] for r, c in all_idx], dtype=np.float32))
    X_geo = None
    if geo is not None:
        X_geo = np.nan_to_num(np.array([geo[:, r, c] for r, c in all_idx], dtype=np.float32))

    s2_idx = list(range(0, min(5, n_sat)))

    # Experiments
    experiments = {}
    experiments["A_s2_only"] = {"X": X_sat[:, s2_idx], "desc": f"S2 only ({len(s2_idx)})"}
    experiments["B_full_sat"] = {"X": X_sat, "desc": f"Full satellite ({n_sat})"}
    if X_geo is not None and np.any(X_geo != 0):
        experiments["C_sat_geology"] = {"X": np.hstack([X_sat, X_geo]),
                                         "desc": f"Satellite + geology ({n_sat+X_geo.shape[1]})"}

    results = {}
    best_name, best_auc = None, 0
    print(f"\n  === ABLATION ({len(experiments)} experiments) ===\n")
    for name, exp in experiments.items():
        avg, folds = spatial_block_cv(exp["X"], y, folds_arr, args.folds)
        results[name] = {"description": exp["desc"], "n_features": exp["X"].shape[1],
                         "average": avg, "per_fold": folds}
        print(f"  [{name}] AUC={avg['auc']:.4f} PR-AUC={avg['pr_auc']:.4f} "
              f"P={avg['precision']:.4f} R={avg['recall']:.4f} F1={avg['f1']:.4f}")
        if avg["auc"] > best_auc:
            best_auc = avg["auc"]; best_name = name

    # Train best on all data
    from xgboost import XGBClassifier; import joblib
    best_X = experiments[best_name]["X"]
    final = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                          random_state=42, eval_metric='logloss')
    final.fit(best_X, y)
    os.makedirs(args.models, exist_ok=True)
    joblib.dump({"model": final, "experiment": best_name, "n_features": best_X.shape[1]},
                os.path.join(args.models, f"{args.aoi}_best_model.joblib"))

    chuq = {"auc": 0.8622, "pr_auc": 0.9532, "precision": 0.948, "recall": 0.760, "f1": 0.837}
    os.makedirs(args.output, exist_ok=True)
    output = {"aoi": args.aoi, "experiments": results, "best": best_name, "best_auc": best_auc,
              "chuquicamata_comparison": chuq, "n_deposits": len(deposits), "n_samples": len(y)}
    with open(os.path.join(args.output, f"{args.aoi}_spatial_cv.json"), "w") as f:
        json.dump(output, f, indent=2)

    md = f"# {args.aoi} Spatial CV Benchmark\n\n"
    md += "| Exp | Features | AUC | PR-AUC | P | R | F1 |\n|---|---|---|---|---|---|---|\n"
    for n, r in results.items():
        a = r["average"]
        md += f"| {n} | {r['n_features']} | **{a['auc']}** | {a['pr_auc']} | {a['precision']} | {a['recall']} | {a['f1']} |\n"
    md += f"\n**Best: {best_name} (AUC={best_auc:.4f})**\n"
    md += f"\nvs Chuquicamata Phase 3B: AUC={chuq['auc']}\n"
    delta = best_auc - chuq["auc"]
    if delta > 0: md += f"Kalgoorlie **exceeds** Chuquicamata by +{delta:.4f}\n"
    elif delta > -0.05: md += f"Kalgoorlie is **comparable** ({delta:+.4f})\n"
    else: md += f"Kalgoorlie **underperforms** ({delta:+.4f})\n"
    with open(os.path.join(args.output, f"{args.aoi}_spatial_cv.md"), "w") as f:
        f.write(md)
    print(f"\n  Best: {best_name} AUC={best_auc:.4f} (vs Chuquicamata {chuq['auc']})")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Priority 4 — Geology-aware training with ablation study.

Compares feature families with honest spatial block CV:
A) S2 only (5 bands)
B) S2 + SAR + DEM + thermal (19 bands) — Phase 2 baseline
C) Geology only (5 bands)
D) S2 + geology (10 bands)
E) S2 + SAR + DEM + thermal + geology (24 bands) — full fusion

All experiments use:
- Spatial block CV (10km blocks, 5 folds)
- Curated labels
- Geology-aware negatives (when available)
- Group-by-deposit (no deposit spans train+test)
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
    all_probs = np.full(len(y), np.nan)

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
        all_probs[test_mask] = probs

        if len(np.unique(y_te)) < 2:
            continue

        auc = roc_auc_score(y_te, probs)
        pr_auc = average_precision_score(y_te, probs)
        prec = precision_score(y_te, preds, zero_division=0)
        rec = recall_score(y_te, preds, zero_division=0)
        f1 = f1_score(y_te, preds, zero_division=0)
        brier = brier_score_loss(y_te, probs)

        fold_metrics.append({
            "fold": fold_id, "n_test": int(test_mask.sum()),
            "n_pos_test": int(y_te.sum()),
            "auc": round(auc, 4), "pr_auc": round(pr_auc, 4),
            "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(f1, 4), "brier": round(brier, 4),
        })

    if fold_metrics:
        avg = {k: round(np.mean([f[k] for f in fold_metrics]), 4)
               for k in ["auc", "pr_auc", "precision", "recall", "f1", "brier"]}
    else:
        avg = {"auc": 0, "pr_auc": 0, "precision": 0, "recall": 0, "f1": 0, "brier": 1}

    return avg, fold_metrics, all_probs


def main():
    p = argparse.ArgumentParser(description="Geology-aware training + ablation study")
    p.add_argument("--stack", default=None)
    p.add_argument("--geology-stack", default=None)
    p.add_argument("--mrds-curated", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds_curated.csv"))
    p.add_argument("--negatives", default=None)
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--block-km", type=float, default=10.0)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--buffer-m", type=float, default=500)
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    p.add_argument("--models", default=os.path.expanduser("~/SOST/geaspirit/models"))
    args = p.parse_args()

    if args.stack is None:
        args.stack = os.path.expanduser(f"~/SOST/geaspirit/data/{args.pilot}_stack.tif")
    if args.geology_stack is None:
        args.geology_stack = os.path.expanduser(f"~/SOST/geaspirit/data/geology_maps/{args.pilot}_geology_stack.tif")
    if args.negatives is None:
        args.negatives = os.path.expanduser(f"~/SOST/geaspirit/data/targets/{args.pilot}_negatives.csv")

    import rasterio
    from rasterio.transform import rowcol

    if not os.path.exists(args.stack):
        print(f"  ! Stack not found: {args.stack}")
        return

    print(f"=== Geology-Aware Training + Ablation — {args.pilot} ===")

    # Load satellite stack
    meta_path = args.stack.replace(".tif", "_meta.json")
    with open(meta_path) as f:
        stack_meta = json.load(f)
    with rasterio.open(args.stack) as src:
        sat_bands = src.read()
        transform = src.transform
        h, w = src.height, src.width

    px_deg = abs(transform.a)
    px_m = px_deg * 111000
    n_sat = sat_bands.shape[0]
    band_names_sat = stack_meta.get("bands", [f"band_{i}" for i in range(n_sat)])
    print(f"  Satellite stack: {w}x{h}, {n_sat} bands")

    # Load geology stack if available
    has_geology = os.path.exists(args.geology_stack)
    if has_geology:
        with rasterio.open(args.geology_stack) as gsrc:
            geo_bands = gsrc.read()
        n_geo = geo_bands.shape[0]
        band_names_geo = ["lithology_code", "lithology_group", "geological_age_ma",
                          "distance_to_contact_m", "mapped_geology_available"][:n_geo]
        print(f"  Geology stack: {n_geo} bands")
    else:
        geo_bands = None
        n_geo = 0
        band_names_geo = []
        print(f"  ! No geology stack — experiments C and D will be skipped")

    # Load curated deposits
    deposits = []
    with open(args.mrds_curated, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("keep_for_training", "").lower() != "true":
                continue
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                r, c = rowcol(transform, lon, lat)
                if 0 <= r < h and 0 <= c < w:
                    deposits.append({"row": r, "col": c, "id": row.get("deposit_id_clean", "")})
            except (ValueError, TypeError):
                continue
    print(f"  Curated deposits: {len(deposits)}")

    # Build positive mask
    buf_px = max(1, int(args.buffer_m / px_m))
    pos_mask = np.zeros((h, w), dtype=bool)
    for d in deposits:
        r0, r1 = max(0, d["row"] - buf_px), min(h, d["row"] + buf_px + 1)
        c0, c1 = max(0, d["col"] - buf_px), min(w, d["col"] + buf_px + 1)
        pos_mask[r0:r1, c0:c1] = True

    # Load geology-aware negatives if available
    has_geo_negs = os.path.exists(args.negatives)
    neg_pixels = {"random_far": [], "hard_proximity": [], "matched_similarity": []}
    if has_geo_negs:
        with open(args.negatives, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                r, c = int(row["row"]), int(row["col"])
                if 0 <= r < h and 0 <= c < w:
                    neg_type = row.get("negative_type", "random_far")
                    neg_pixels[neg_type].append((r, c))
        total_negs = sum(len(v) for v in neg_pixels.values())
        print(f"  Geology-aware negatives: {total_negs}")
    else:
        print(f"  ! No geology-aware negatives — using distance-based negatives")
        # Fallback: use far negatives
        neg_dist_px = max(1, int(5000 / px_m))
        near_mask = np.zeros((h, w), dtype=bool)
        for d in deposits:
            r0, r1 = max(0, d["row"] - neg_dist_px), min(h, d["row"] + neg_dist_px + 1)
            c0, c1 = max(0, d["col"] - neg_dist_px), min(w, d["col"] + neg_dist_px + 1)
            near_mask[r0:r1, c0:c1] = True
        valid = np.all(np.isfinite(sat_bands), axis=0)
        far_idx = np.argwhere(~near_mask & valid)
        rng = np.random.RandomState(42)
        max_neg = pos_mask.sum() * 3
        if len(far_idx) > max_neg:
            sel = rng.choice(len(far_idx), max_neg, replace=False)
            far_idx = far_idx[sel]
        neg_pixels["random_far"] = [(r, c) for r, c in far_idx]

    # Build spatial block fold map
    block_px = max(1, int(args.block_km * 1000 / px_m))
    n_blocks_r = (h + block_px - 1) // block_px
    n_blocks_c = (w + block_px - 1) // block_px
    rng = np.random.RandomState(42)
    block_ids = np.arange(n_blocks_r * n_blocks_c)
    rng.shuffle(block_ids)
    fold_map = np.full((h, w), -1, dtype=int)
    for br in range(n_blocks_r):
        for bc in range(n_blocks_c):
            bid = br * n_blocks_c + bc
            r0, r1 = br * block_px, min((br + 1) * block_px, h)
            c0, c1 = bc * block_px, min((bc + 1) * block_px, w)
            fold_map[r0:r1, c0:c1] = block_ids[bid] % args.folds

    # === Build datasets for each experiment ===
    valid = np.all(np.isfinite(sat_bands), axis=0)
    pos_idx = np.argwhere(pos_mask & valid)

    # Collect all negative pixels
    all_neg_idx = []
    for neg_type, pixels in neg_pixels.items():
        for r, c in pixels:
            if valid[r, c]:
                all_neg_idx.append((r, c))
    all_neg_idx = np.array(all_neg_idx) if all_neg_idx else np.empty((0, 2), dtype=int)

    # Subsample to manageable size
    max_pos = min(len(pos_idx), 60000)
    max_neg = min(len(all_neg_idx), max_pos * 3)
    if len(pos_idx) > max_pos:
        sel = rng.choice(len(pos_idx), max_pos, replace=False)
        pos_idx = pos_idx[sel]
    if len(all_neg_idx) > max_neg:
        sel = rng.choice(len(all_neg_idx), max_neg, replace=False)
        all_neg_idx = all_neg_idx[sel]

    all_idx = np.vstack([pos_idx, all_neg_idx])
    y = np.array([1]*len(pos_idx) + [0]*len(all_neg_idx))
    folds_arr = np.array([fold_map[r, c] for r, c in all_idx])

    print(f"  Samples: {len(pos_idx)} pos + {len(all_neg_idx)} neg = {len(y)}")

    # Extract features
    X_sat = np.array([sat_bands[:, r, c] for r, c in all_idx], dtype=np.float32)
    X_geo = None
    if has_geology:
        X_geo = np.array([geo_bands[:, r, c] for r, c in all_idx], dtype=np.float32)

    # Define feature family indices
    # S2 = first 5 bands, SAR = next 5, DEM = next 6, Thermal = next 3
    s2_idx = list(range(0, 5))
    sar_idx = list(range(5, 10)) if n_sat >= 10 else []
    dem_idx = list(range(10, 16)) if n_sat >= 16 else []
    thm_idx = list(range(16, 19)) if n_sat >= 19 else []

    # Define experiments
    experiments = {}
    experiments["A_s2_only"] = {
        "X": X_sat[:, s2_idx],
        "bands": [band_names_sat[i] for i in s2_idx],
        "desc": "S2 spectral indices only (5 bands)",
    }
    experiments["B_full_sat"] = {
        "X": X_sat,
        "bands": band_names_sat,
        "desc": f"S2 + SAR + DEM + thermal ({n_sat} bands) — Phase 2 baseline",
    }
    if has_geology:
        experiments["C_geology_only"] = {
            "X": X_geo,
            "bands": band_names_geo,
            "desc": f"Geology features only ({n_geo} bands)",
        }
        experiments["D_s2_geology"] = {
            "X": np.hstack([X_sat[:, s2_idx], X_geo]),
            "bands": [band_names_sat[i] for i in s2_idx] + band_names_geo,
            "desc": f"S2 + geology ({5 + n_geo} bands)",
        }
        experiments["E_full_fusion"] = {
            "X": np.hstack([X_sat, X_geo]),
            "bands": band_names_sat + band_names_geo,
            "desc": f"Full satellite + geology ({n_sat + n_geo} bands)",
        }

    # Run ablation
    results = {}
    print(f"\n  === ABLATION STUDY ({len(experiments)} experiments) ===\n")
    best_model = None
    best_auc = 0

    for name, exp in experiments.items():
        X_exp = exp["X"]
        # Replace NaN/inf with 0
        X_exp = np.nan_to_num(X_exp, nan=0.0, posinf=0.0, neginf=0.0)

        print(f"  [{name}] {exp['desc']}")
        avg, fold_results, oof_probs = spatial_block_cv(X_exp, y, folds_arr, args.folds)
        results[name] = {
            "description": exp["desc"],
            "n_features": X_exp.shape[1],
            "bands": exp["bands"],
            "average": avg,
            "per_fold": fold_results,
        }
        print(f"    AUC={avg['auc']:.4f}  PR-AUC={avg['pr_auc']:.4f}  "
              f"P={avg['precision']:.4f}  R={avg['recall']:.4f}  "
              f"F1={avg['f1']:.4f}  Brier={avg['brier']:.4f}")

        if avg["auc"] > best_auc:
            best_auc = avg["auc"]
            best_model = name

    # Train final best model on all data
    print(f"\n  Best experiment: {best_model} (AUC={best_auc:.4f})")
    best_exp = experiments[best_model]
    X_best = np.nan_to_num(best_exp["X"], nan=0.0, posinf=0.0, neginf=0.0)

    from xgboost import XGBClassifier
    import joblib
    final_model = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                                random_state=42, eval_metric='logloss')
    final_model.fit(X_best, y)

    os.makedirs(args.models, exist_ok=True)
    model_path = os.path.join(args.models, "geology_aware_model.joblib")
    joblib.dump({"model": final_model, "bands": best_exp["bands"],
                 "experiment": best_model}, model_path)
    print(f"  Saved: {model_path}")

    # Phase 3 baseline for comparison
    phase3_baseline = {"auc": 0.6844, "pr_auc": 0.5007, "precision": 0.6060,
                       "recall": 0.2836, "f1": 0.3454, "brier": 0.1711}

    # Save results
    os.makedirs(args.output, exist_ok=True)
    output = {
        "pilot": args.pilot,
        "phase3_baseline": phase3_baseline,
        "experiments": results,
        "best_experiment": best_model,
        "best_auc": best_auc,
        "improvement_over_baseline": round(best_auc - phase3_baseline["auc"], 4),
        "n_deposits": len(deposits),
        "n_samples": len(y),
        "n_positive": int((y == 1).sum()),
        "n_negative": int((y == 0).sum()),
    }
    with open(os.path.join(args.output, "ablation_spatial_cv.json"), "w") as f:
        json.dump(output, f, indent=2)

    # Feature family comparison CSV
    csv_path = os.path.join(args.output, "feature_family_comparison.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["experiment", "description", "n_features", "auc", "pr_auc",
                         "precision", "recall", "f1", "brier", "delta_auc_vs_baseline"])
        # Phase 3 baseline row
        writer.writerow(["Phase3_baseline", "Phase 3 spatial CV (honest)", 19,
                         phase3_baseline["auc"], phase3_baseline["pr_auc"],
                         phase3_baseline["precision"], phase3_baseline["recall"],
                         phase3_baseline["f1"], phase3_baseline["brier"], 0])
        for name, res in results.items():
            avg = res["average"]
            delta = round(avg["auc"] - phase3_baseline["auc"], 4)
            writer.writerow([name, res["description"], res["n_features"],
                             avg["auc"], avg["pr_auc"], avg["precision"],
                             avg["recall"], avg["f1"], avg["brier"], delta])

    # Markdown report
    md = f"# Ablation Study — {args.pilot}\n\n"
    md += f"## Phase 3 Baseline (honest)\n"
    md += f"- AUC: {phase3_baseline['auc']}\n"
    md += f"- PR-AUC: {phase3_baseline['pr_auc']}\n\n"
    md += f"## Results\n\n"
    md += "| Experiment | Features | AUC | PR-AUC | Precision | Recall | F1 | Delta AUC |\n"
    md += "|------------|----------|-----|--------|-----------|--------|----|-----------|\n"
    md += f"| Phase 3 baseline | 19 | {phase3_baseline['auc']} | {phase3_baseline['pr_auc']} | "
    md += f"{phase3_baseline['precision']} | {phase3_baseline['recall']} | {phase3_baseline['f1']} | — |\n"
    for name, res in results.items():
        avg = res["average"]
        delta = avg["auc"] - phase3_baseline["auc"]
        sign = "+" if delta >= 0 else ""
        md += f"| {name} | {res['n_features']} | **{avg['auc']}** | {avg['pr_auc']} | "
        md += f"{avg['precision']} | {avg['recall']} | {avg['f1']} | {sign}{delta:.4f} |\n"
    md += f"\n## Best: **{best_model}** (AUC={best_auc:.4f}, delta={best_auc-phase3_baseline['auc']:+.4f})\n\n"

    # Analysis
    md += f"## Analysis\n\n"
    if best_auc > phase3_baseline["auc"] + 0.03:
        md += f"Geology features provide a **meaningful improvement** (+{best_auc-phase3_baseline['auc']:.4f} AUC).\n"
    elif best_auc > phase3_baseline["auc"]:
        md += f"Geology features provide a **marginal improvement** (+{best_auc-phase3_baseline['auc']:.4f} AUC).\n"
        md += f"The gain is small — more/better geology data may help.\n"
    else:
        md += f"Geology features **did not improve** the model.\n"
        md += f"Possible reasons:\n"
        md += f"- Macrostrat resolution too coarse for this AOI\n"
        md += f"- Geology already captured implicitly by terrain/spectral features\n"
        md += f"- Need higher-resolution geological maps\n"

    with open(os.path.join(args.output, "ablation_spatial_cv.md"), "w") as f:
        f.write(md)

    print(f"\n  Saved: ablation_spatial_cv.json, .md, feature_family_comparison.csv")
    print(f"  BEST: {best_model} AUC={best_auc:.4f} (delta={best_auc-phase3_baseline['auc']:+.4f})")


if __name__ == "__main__":
    main()

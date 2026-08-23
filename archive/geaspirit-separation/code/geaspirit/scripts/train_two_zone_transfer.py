#!/usr/bin/env python3
"""Phase 4A Priority 8 — Two-zone transfer: Chuquicamata <-> Pilbara.

Tests cross-domain generalization:
1. Train Chuquicamata → Test Pilbara
2. Train Pilbara → Test Chuquicamata

Uses satellite-only features (common to both zones) for fair comparison.
"""
import argparse, os, sys, json, csv
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, HALF_DEG, get_bbox as _get_bbox


def load_zone_samples(pilot, data_dir, curated_csv, negatives_csv, max_pos=30000, max_neg_ratio=3):
    """Load samples for a zone. Returns X (satellite-only), y, or None."""
    import rasterio
    from rasterio.transform import rowcol

    stack_path = os.path.join(data_dir, f"{pilot}_stack.tif")
    if not os.path.exists(stack_path):
        return None

    meta_path = stack_path.replace(".tif", "_meta.json")
    with open(meta_path) as f:
        meta = json.load(f)
    with rasterio.open(stack_path) as src:
        bands = src.read()
        transform = src.transform
        h, w = src.height, src.width

    px_m = abs(transform.a) * 111000
    n_bands = bands.shape[0]
    zone = ZONES[pilot]
    lat_c, lon_c = zone["center"]
    bbox = _get_bbox(pilot)

    # Load deposits
    deposits = []
    if os.path.exists(curated_csv):
        with open(curated_csv, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get("keep_for_training", "").lower() != "true":
                    continue
                try:
                    lat, lon = float(row["latitude"]), float(row["longitude"])
                    if not (bbox[1] <= lat <= bbox[3] and bbox[0] <= lon <= bbox[2]):
                        continue
                    r, c = rowcol(transform, lon, lat)
                    if 0 <= r < h and 0 <= c < w:
                        deposits.append((r, c))
                except (ValueError, TypeError):
                    continue

    if len(deposits) < 3:
        return None

    # Build masks
    buf_px = max(1, int(500 / px_m))
    pos_mask = np.zeros((h, w), dtype=bool)
    for r, c in deposits:
        r0, r1 = max(0, r - buf_px), min(h, r + buf_px + 1)
        c0, c1 = max(0, c - buf_px), min(w, c + buf_px + 1)
        pos_mask[r0:r1, c0:c1] = True

    valid = np.all(np.isfinite(bands), axis=0)
    pos_idx = np.argwhere(pos_mask & valid)

    # Load negatives
    neg_idx = []
    if os.path.exists(negatives_csv):
        with open(negatives_csv, newline='') as f:
            for row in csv.DictReader(f):
                r, c = int(row["row"]), int(row["col"])
                if 0 <= r < h and 0 <= c < w and valid[r, c]:
                    neg_idx.append((r, c))
    neg_idx = np.array(neg_idx) if neg_idx else np.empty((0, 2), dtype=int)

    if len(neg_idx) == 0:
        # Fallback
        neg_dist_px = max(1, int(5000 / px_m))
        near = np.zeros((h, w), dtype=bool)
        for r, c in deposits:
            r0, r1 = max(0, r - neg_dist_px), min(h, r + neg_dist_px + 1)
            c0, c1 = max(0, c - neg_dist_px), min(w, c + neg_dist_px + 1)
            near[r0:r1, c0:c1] = True
        far = np.argwhere(~near & valid)
        rng = np.random.RandomState(42)
        max_n = pos_mask.sum() * max_neg_ratio
        if len(far) > max_n:
            sel = rng.choice(len(far), max_n, replace=False)
            far = far[sel]
        neg_idx = far

    # Subsample
    rng = np.random.RandomState(42)
    if len(pos_idx) > max_pos:
        sel = rng.choice(len(pos_idx), max_pos, replace=False)
        pos_idx = pos_idx[sel]
    max_neg = len(pos_idx) * max_neg_ratio
    if len(neg_idx) > max_neg:
        sel = rng.choice(len(neg_idx), max_neg, replace=False)
        neg_idx = neg_idx[sel]

    all_idx = np.vstack([pos_idx, neg_idx]) if len(neg_idx) > 0 else pos_idx
    y = np.array([1]*len(pos_idx) + [0]*len(neg_idx))
    X = np.nan_to_num(np.array([bands[:, r, c] for r, c in all_idx], dtype=np.float32))

    return {"pilot": pilot, "X": X, "y": y, "n_bands": n_bands,
            "n_deposits": len(deposits), "n_pos": len(pos_idx), "n_neg": len(neg_idx)}


def main():
    p = argparse.ArgumentParser(description="Two-zone transfer: Chuquicamata <-> Pilbara")
    p.add_argument("--data-dir", default=os.path.expanduser("~/SOST/geaspirit/data"))
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    from sklearn.metrics import (roc_auc_score, precision_score, recall_score,
                                 f1_score, average_precision_score, brier_score_loss)
    from xgboost import XGBClassifier

    print("=== Two-Zone Transfer: Chuquicamata <-> Pilbara ===\n")

    # Load both zones
    zones = {}
    for pilot in ["chuquicamata", "pilbara"]:
        curated = os.path.join(args.data_dir, "mrds", f"{pilot}_mrds_curated.csv")
        negs = os.path.join(args.data_dir, "targets", f"{pilot}_negatives.csv")
        data = load_zone_samples(pilot, args.data_dir, curated, negs)
        if data:
            zones[pilot] = data
            print(f"  {pilot}: {data['n_pos']} pos + {data['n_neg']} neg, {data['n_bands']} bands")
        else:
            print(f"  {pilot}: NO DATA")

    if len(zones) < 2:
        print("\n  ! Need both zones for transfer test")
        os.makedirs(args.output, exist_ok=True)
        report = {"status": "INCOMPLETE", "zones_available": list(zones.keys()),
                  "reason": "Need both Chuquicamata and Pilbara data"}
        with open(os.path.join(args.output, "two_zone_transfer.json"), "w") as f:
            json.dump(report, f, indent=2)
        with open(os.path.join(args.output, "two_zone_transfer.md"), "w") as f:
            f.write("# Two-Zone Transfer\n\n**INCOMPLETE**: Need both zones.\n")
        return

    # Harmonize features (use minimum common bands)
    min_bands = min(z["n_bands"] for z in zones.values())
    for zn in zones:
        if zones[zn]["X"].shape[1] > min_bands:
            zones[zn]["X"] = zones[zn]["X"][:, :min_bands]
    print(f"  Common features: {min_bands}")

    # Transfer experiments
    transfer_results = []
    for train_zone, test_zone in [("chuquicamata", "pilbara"), ("pilbara", "chuquicamata")]:
        print(f"\n  Transfer: train={train_zone} -> test={test_zone}")

        X_train, y_train = zones[train_zone]["X"], zones[train_zone]["y"]
        X_test, y_test = zones[test_zone]["X"], zones[test_zone]["y"]

        model = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                              random_state=42, eval_metric='logloss')
        model.fit(X_train, y_train)
        probs = model.predict_proba(X_test)[:, 1]
        preds = (probs >= 0.5).astype(int)

        if len(np.unique(y_test)) < 2:
            print(f"    ! Single class in test")
            transfer_results.append({"train": train_zone, "test": test_zone,
                                     "status": "FAILED", "reason": "single class"})
            continue

        auc = roc_auc_score(y_test, probs)
        pr_auc = average_precision_score(y_test, probs)
        prec = precision_score(y_test, preds, zero_division=0)
        rec = recall_score(y_test, preds, zero_division=0)
        f1 = f1_score(y_test, preds, zero_division=0)
        brier = brier_score_loss(y_test, probs)

        result = {
            "train": train_zone, "test": test_zone, "status": "OK",
            "n_train": len(y_train), "n_test": len(y_test),
            "auc": round(auc, 4), "pr_auc": round(pr_auc, 4),
            "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(f1, 4), "brier": round(brier, 4),
        }

        # Diagnosis
        if auc < 0.55:
            result["diagnosis"] = "Near-random — very different geological domains"
        elif auc < 0.65:
            result["diagnosis"] = "Weak transfer — limited geological commonality"
        elif auc < 0.75:
            result["diagnosis"] = "Moderate transfer — some features generalize"
        else:
            result["diagnosis"] = "Strong transfer — universal geological indicators found"

        transfer_results.append(result)
        print(f"    AUC={auc:.4f}  PR-AUC={pr_auc:.4f}  P={prec:.4f}  R={rec:.4f}  F1={f1:.4f}")
        print(f"    {result['diagnosis']}")

    # Save
    os.makedirs(args.output, exist_ok=True)
    output = {
        "method": "Two-zone transfer (satellite-only features)",
        "common_features": min_bands,
        "results": transfer_results,
    }
    ok = [r for r in transfer_results if r["status"] == "OK"]
    if ok:
        output["average_transfer_auc"] = round(np.mean([r["auc"] for r in ok]), 4)

    with open(os.path.join(args.output, "two_zone_transfer.json"), "w") as f:
        json.dump(output, f, indent=2)

    # CSV
    with open(os.path.join(args.output, "two_zone_transfer_comparison.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["train", "test", "auc", "pr_auc", "precision", "recall", "f1", "diagnosis"])
        for r in transfer_results:
            if r["status"] == "OK":
                w.writerow([r["train"], r["test"], r["auc"], r["pr_auc"],
                            r["precision"], r["recall"], r["f1"], r.get("diagnosis", "")])

    # Markdown
    md = "# Two-Zone Transfer: Chuquicamata <-> Pilbara\n\n"
    md += f"Features: satellite-only ({min_bands} bands, common to both zones)\n\n"
    md += "## Results\n\n"
    md += "| Train | Test | AUC | PR-AUC | P | R | F1 |\n"
    md += "|-------|------|-----|--------|---|---|----|\n"
    for r in transfer_results:
        if r["status"] == "OK":
            md += f"| {r['train']} | {r['test']} | **{r['auc']}** | {r['pr_auc']} | "
            md += f"{r['precision']} | {r['recall']} | {r['f1']} |\n"
    if output.get("average_transfer_auc"):
        md += f"\n**Average transfer AUC: {output['average_transfer_auc']}**\n"
    md += "\n## Diagnosis\n\n"
    for r in transfer_results:
        if r.get("diagnosis"):
            md += f"- {r['train']} -> {r['test']}: **{r['diagnosis']}**\n"
    md += "\n## Implications\n\n"
    avg_auc = output.get("average_transfer_auc", 0)
    if avg_auc >= 0.70:
        md += "Strong cross-domain transfer suggests the model learns **universal geological indicators** "
        md += "that work across different deposit types and terrains. Zambia pilot is warranted.\n"
    elif avg_auc >= 0.60:
        md += "Moderate transfer suggests **some geological features generalize** but there is significant "
        md += "domain shift. Zone-specific fine-tuning recommended. Zambia pilot may benefit from "
        md += "including both Chuquicamata and Pilbara in training.\n"
    else:
        md += "Weak transfer suggests the zones are **geologically too different** for direct transfer. "
        md += "Each zone needs its own model. Zambia should wait for more global training data.\n"

    with open(os.path.join(args.output, "two_zone_transfer.md"), "w") as f:
        f.write(md)
    print(f"\n  Saved: two_zone_transfer.json + .md + comparison.csv")


if __name__ == "__main__":
    main()

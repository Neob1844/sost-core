#!/usr/bin/env python3
"""Cu-compatible transfer: Chuquicamata <-> Zambia."""
import argparse, os, sys, json, csv
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, get_bbox


def load_zone(pilot, data_dir, label_path, max_pos=30000):
    import rasterio
    from rasterio.transform import rowcol

    # Find stack
    for pattern in [f"stack/{pilot}_full_stack.tif", f"stack/{pilot}_global_stack.tif", f"{pilot}_stack.tif"]:
        sp = os.path.join(data_dir, pattern)
        if os.path.exists(sp): break
    else:
        return None

    with rasterio.open(sp) as src:
        bands = src.read(); transform = src.transform; h, w = src.height, src.width
    bbox = get_bbox(pilot) if pilot in ZONES else None

    deposits = []
    if os.path.exists(label_path):
        with open(label_path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get("keep_for_training", "").lower() != "true": continue
                try:
                    lat, lon = float(row["latitude"]), float(row["longitude"])
                    r, c = rowcol(transform, lon, lat)
                    if 0 <= r < h and 0 <= c < w:
                        deposits.append((r, c))
                except: continue

    if len(deposits) < 3: return None
    px_m = abs(transform.a) * 111000
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
    return {"pilot": pilot, "X": X, "y": y, "n_bands": bands.shape[0],
            "n_deposits": len(deposits), "n_pos": len(pos_idx), "n_neg": len(neg_idx)}


def main():
    p = argparse.ArgumentParser(description="Cu-compatible transfer: Chuquicamata <-> Zambia")
    p.add_argument("--data-dir", default=os.path.expanduser("~/SOST/geaspirit/data"))
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    from sklearn.metrics import (roc_auc_score, precision_score, recall_score,
                                 f1_score, average_precision_score)
    from xgboost import XGBClassifier

    print("=== Cu Transfer: Chuquicamata <-> Zambia ===\n")

    chuq_labels = os.path.join(args.data_dir, "mrds", "chuquicamata_mrds_curated.csv")
    zambia_labels = os.path.join(args.data_dir, "labels", "zambia_copperbelt_labels_curated.csv")

    zones = {}
    for pilot, lp in [("chuquicamata", chuq_labels), ("zambia_copperbelt", zambia_labels)]:
        data = load_zone(pilot, args.data_dir, lp)
        if data:
            zones[pilot] = data
            print(f"  {pilot}: {data['n_pos']} pos + {data['n_neg']} neg, {data['n_bands']} bands")
        else:
            print(f"  {pilot}: NO DATA")

    if len(zones) < 2:
        print("\n  ! Need both zones")
        os.makedirs(args.output, exist_ok=True)
        with open(os.path.join(args.output, "cu_transfer_chile_zambia.json"), "w") as f:
            json.dump({"status": "INCOMPLETE", "zones": list(zones.keys())}, f, indent=2)
        return

    min_bands = min(z["n_bands"] for z in zones.values())
    for zn in zones:
        if zones[zn]["X"].shape[1] > min_bands:
            zones[zn]["X"] = zones[zn]["X"][:, :min_bands]
    print(f"  Common features: {min_bands}")

    results = []
    for train_z, test_z in [("chuquicamata", "zambia_copperbelt"), ("zambia_copperbelt", "chuquicamata")]:
        X_tr, y_tr = zones[train_z]["X"], zones[train_z]["y"]
        X_te, y_te = zones[test_z]["X"], zones[test_z]["y"]
        print(f"\n  Train={train_z} -> Test={test_z}")

        model = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                              random_state=42, eval_metric='logloss')
        model.fit(X_tr, y_tr)
        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)

        if len(np.unique(y_te)) < 2:
            results.append({"train": train_z, "test": test_z, "status": "FAILED"})
            continue

        auc = roc_auc_score(y_te, probs)
        pr_auc = average_precision_score(y_te, probs)
        prec = precision_score(y_te, preds, zero_division=0)
        rec = recall_score(y_te, preds, zero_division=0)
        f1 = f1_score(y_te, preds, zero_division=0)

        diag = ("Strong" if auc >= 0.75 else "Moderate" if auc >= 0.65
                else "Weak" if auc >= 0.55 else "Near-random")

        r = {"train": train_z, "test": test_z, "status": "OK",
             "auc": round(auc, 4), "pr_auc": round(pr_auc, 4),
             "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
             "diagnosis": diag + " Cu transfer"}
        results.append(r)
        print(f"    AUC={auc:.4f} PR-AUC={pr_auc:.4f} P={prec:.4f} R={rec:.4f} — {diag}")

    os.makedirs(args.output, exist_ok=True)
    ok = [r for r in results if r.get("status") == "OK"]
    output = {"method": "Cu-compatible transfer (satellite-only)", "common_features": min_bands,
              "results": results, "average_auc": round(np.mean([r["auc"] for r in ok]), 4) if ok else 0}
    with open(os.path.join(args.output, "cu_transfer_chile_zambia.json"), "w") as f:
        json.dump(output, f, indent=2)

    md = "# Cu Transfer: Chuquicamata <-> Zambia\n\n"
    md += "| Train | Test | AUC | PR-AUC | P | R | F1 | Diagnosis |\n|---|---|---|---|---|---|---|---|\n"
    for r in results:
        if r.get("status") == "OK":
            md += f"| {r['train']} | {r['test']} | **{r['auc']}** | {r['pr_auc']} | {r['precision']} | {r['recall']} | {r['f1']} | {r['diagnosis']} |\n"
    if output.get("average_auc"):
        md += f"\n**Average Cu transfer AUC: {output['average_auc']}**\n"
    with open(os.path.join(args.output, "cu_transfer_chile_zambia.md"), "w") as f:
        f.write(md)
    print(f"\n  Saved: cu_transfer_chile_zambia.json + .md")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Same-type porphyry Cu transfer: Chuquicamata <-> Arizona."""
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


def main():
    p = argparse.ArgumentParser(description="Porphyry Cu same-type transfer")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score, average_precision_score
    from xgboost import XGBClassifier

    data_dir = os.path.expanduser("~/SOST/geaspirit/data")
    zones = {}

    # Chuquicamata porphyry
    z = load_zone("chuquicamata",
                   os.path.join(data_dir, "chuquicamata_stack.tif"),
                   os.path.join(data_dir, "mrds/chuquicamata_mrds_curated.csv"))
    if z: zones["chuquicamata"] = z

    # Arizona porphyry
    z = load_zone("arizona",
                   os.path.join(data_dir, "stack/arizona_porphyry_global_stack.tif"),
                   os.path.join(data_dir, "labels/arizona_porphyry_labels.csv"))
    if z: zones["arizona"] = z

    print(f"=== Porphyry Cu Same-Type Transfer ===\n")
    for name, z in zones.items():
        print(f"  {name}: {z['n_pos']} pos + {z['n_neg']} neg, {z['n_bands']} bands")

    if len(zones) < 2:
        print(f"\n  ! Need 2+ zones. Available: {list(zones.keys())}")
        os.makedirs(args.output, exist_ok=True)
        with open(os.path.join(args.output, "porphyry_transfer_matrix.json"), "w") as f:
            json.dump({"status": "INCOMPLETE", "zones": list(zones.keys())}, f, indent=2)
        return

    min_bands = min(z["n_bands"] for z in zones.values())
    for zn in zones:
        if zones[zn]["X"].shape[1] > min_bands:
            zones[zn]["X"] = zones[zn]["X"][:, :min_bands]

    results = []
    zone_names = list(zones.keys())
    for i, train_z in enumerate(zone_names):
        for j, test_z in enumerate(zone_names):
            if i == j: continue
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
            pr = average_precision_score(y_te, probs)
            prec = precision_score(y_te, preds, zero_division=0)
            rec = recall_score(y_te, preds, zero_division=0)
            f1 = f1_score(y_te, preds, zero_division=0)
            diag = "Strong" if auc >= 0.75 else "Moderate" if auc >= 0.65 else "Weak" if auc >= 0.55 else "Near-random"
            r = {"train": train_z, "test": test_z, "status": "OK", "type": "porphyry_cu",
                 "auc": round(auc, 4), "pr_auc": round(pr, 4),
                 "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
                 "diagnosis": f"{diag} same-type porphyry transfer"}
            results.append(r)
            print(f"    AUC={auc:.4f} — {diag}")

    # Compare with cross-type (from Phase 4E)
    cross_type_auc = 0.4543  # Chuquicamata -> Zambia
    ok = [r for r in results if r.get("status") == "OK"]
    avg_same_type = round(np.mean([r["auc"] for r in ok]), 4) if ok else 0

    os.makedirs(args.output, exist_ok=True)
    output = {"method": "Same-type porphyry Cu transfer", "common_bands": min_bands,
              "results": results, "average_same_type_auc": avg_same_type,
              "cross_type_comparison": cross_type_auc,
              "improvement_over_cross_type": round(avg_same_type - cross_type_auc, 4) if avg_same_type else 0}
    with open(os.path.join(args.output, "porphyry_transfer_matrix.json"), "w") as f:
        json.dump(output, f, indent=2)

    md = "# Porphyry Cu Same-Type Transfer\n\n"
    md += "| Train | Test | AUC | Diagnosis |\n|---|---|---|---|\n"
    for r in results:
        if r.get("status") == "OK":
            md += f"| {r['train']} | {r['test']} | **{r['auc']}** | {r['diagnosis']} |\n"
    md += f"\n**Average same-type: {avg_same_type}** vs cross-type: {cross_type_auc}\n"
    md += f"**Improvement: +{output['improvement_over_cross_type']}**\n"
    with open(os.path.join(args.output, "porphyry_transfer_report.md"), "w") as f:
        f.write(md)
    print(f"\n  Saved: porphyry_transfer_matrix.json + report.md")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Rank unexplored targets — the discovery engine for GeaSpirit Platform."""
import argparse, os, sys, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def main():
    p = argparse.ArgumentParser(description="Rank unexplored mineral targets")
    p.add_argument("--stack", default=os.path.expanduser("~/SOST/geaspirit/data/chuquicamata_stack.tif"))
    p.add_argument("--model", default=os.path.expanduser("~/SOST/geaspirit/outputs/final_model_spatial_cv.joblib"))
    p.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds.csv"))
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--exclude-km", type=float, default=5.0)
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--min-pixels", type=int, default=9)
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    import rasterio, joblib
    from rasterio.transform import rowcol, xy
    from scipy.ndimage import label as ndlabel
    from geaspirit.dataset import load_mrds_deposits
    from geaspirit.ee_download import ZONES, HALF_DEG

    zone = ZONES[args.pilot]
    lat, lon = zone["center"]
    bbox = [lon - HALF_DEG, lat - HALF_DEG, lon + HALF_DEG, lat + HALF_DEG]

    # Load
    print("→ Loading model and stack...")
    model = joblib.load(args.model)
    meta_path = args.stack.replace(".tif", "_meta.json")
    with open(meta_path) as f:
        meta = json.load(f)
    with rasterio.open(args.stack) as src:
        all_bands = src.read()
        transform = src.transform
        h, w = src.height, src.width
        crs = src.crs

    px_m = abs(transform.a) * 111000
    band_names = meta["bands"]

    # Load deposits and build exclusion mask
    deposits = load_mrds_deposits(args.mrds, min_lat=bbox[1], max_lat=bbox[3],
                                   min_lon=bbox[0], max_lon=bbox[2])
    exclude_px = max(1, int(args.exclude_km * 1000 / px_m))
    exclude_mask = np.zeros((h, w), dtype=bool)
    dep_coords = []
    for d in deposits:
        try:
            r, c = rowcol(transform, d['lon'], d['lat'])
            if 0 <= r < h and 0 <= c < w:
                r0, r1 = max(0, r - exclude_px), min(h, r + exclude_px + 1)
                c0, c1 = max(0, c - exclude_px), min(w, c + exclude_px + 1)
                exclude_mask[r0:r1, c0:c1] = True
                dep_coords.append((d['lat'], d['lon']))
        except:
            continue

    # Predict on all valid pixels
    print("→ Predicting probabilities...")
    valid = np.all(np.isfinite(all_bands), axis=0)
    prob_map = np.full((h, w), np.nan, dtype=np.float32)
    valid_idx = np.argwhere(valid)

    # Process in chunks
    chunk_size = 50000
    for i in range(0, len(valid_idx), chunk_size):
        chunk = valid_idx[i:i+chunk_size]
        X = np.array([all_bands[:, r, c] for r, c in chunk], dtype=np.float32)
        probs = model.predict_proba(X)[:, 1]
        for j, (r, c) in enumerate(chunk):
            prob_map[r, c] = probs[j]

    # Mask out known deposit buffers
    target_map = prob_map.copy()
    target_map[exclude_mask] = 0
    target_map[~valid] = 0

    # Threshold and cluster
    threshold = 0.6
    binary = target_map >= threshold
    labeled, n_clusters = ndlabel(binary)
    print(f"→ Found {n_clusters} clusters above threshold {threshold}")

    # Rank clusters
    targets = []
    for cid in range(1, n_clusters + 1):
        mask = labeled == cid
        area = mask.sum()
        if area < args.min_pixels:
            continue
        mean_prob = float(np.nanmean(prob_map[mask]))
        rows, cols = np.where(mask)
        cr, cc = rows.mean(), cols.mean()
        clat, clon = xy(transform, int(cr), int(cc))

        # Distance to nearest known deposit
        min_dist = float('inf')
        for dlat, dlon in dep_coords:
            d = np.sqrt((clat - dlat)**2 + (clon - dlon)**2) * 111
            min_dist = min(min_dist, d)

        # Top features
        cluster_feats = np.array([all_bands[:, r, c] for r, c in zip(rows[:100], cols[:100])], dtype=np.float32)
        global_mean = np.nanmean([all_bands[:, r, c] for r, c in valid_idx[:10000]], axis=0)
        feat_diff = np.mean(cluster_feats, axis=0) - global_mean
        top_feat_idx = np.argsort(-np.abs(feat_diff))[:5]
        top_features = [{"feature": band_names[i], "deviation": round(float(feat_diff[i]), 3)} for i in top_feat_idx]

        targets.append({
            "rank": 0,
            "centroid_lat": round(float(clat), 5),
            "centroid_lon": round(float(clon), 5),
            "area_pixels": int(area),
            "mean_probability": round(mean_prob, 4),
            "nearest_known_km": round(min_dist, 2),
            "top_features": top_features,
        })

    # Sort by probability * sqrt(area)
    targets.sort(key=lambda t: -t["mean_probability"] * np.sqrt(t["area_pixels"]))
    for i, t in enumerate(targets[:args.top_k]):
        t["rank"] = i + 1

    targets = targets[:args.top_k]
    print(f"→ Top {len(targets)} targets ranked")

    # Save
    os.makedirs(args.output, exist_ok=True)

    # CSV
    import csv
    csv_path = os.path.join(args.output, f"top{args.top_k}_targets.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["rank","centroid_lat","centroid_lon","area_pixels",
                                                "mean_probability","nearest_known_km"])
        writer.writeheader()
        for t in targets:
            writer.writerow({k: t[k] for k in writer.fieldnames})
    print(f"  ✓ {csv_path}")

    # JSON
    with open(os.path.join(args.output, f"top{args.top_k}_targets.json"), "w") as f:
        json.dump(targets, f, indent=2)

    # Markdown
    md = f"# Top {len(targets)} Unexplored Targets — {args.pilot}\n\n"
    md += f"Exclusion buffer: {args.exclude_km}km from known deposits\n"
    md += f"Threshold: {threshold}\n\n"
    md += "| # | Lat | Lon | Pixels | Probability | Nearest Mine (km) | Top Feature |\n"
    md += "|---|-----|-----|--------|------------|-------------------|-------------|\n"
    for t in targets[:20]:
        feat = t["top_features"][0]["feature"] if t["top_features"] else "—"
        md += f"| {t['rank']} | {t['centroid_lat']:.4f} | {t['centroid_lon']:.4f} | {t['area_pixels']} | {t['mean_probability']:.3f} | {t['nearest_known_km']:.1f} | {feat} |\n"
    with open(os.path.join(args.output, f"top{args.top_k}_targets.md"), "w") as f:
        f.write(md)
    print(f"  ✓ top{args.top_k}_targets.md")

    print(f"\n{'='*60}")
    print(f"TOP 5 UNEXPLORED TARGETS:")
    for t in targets[:5]:
        print(f"  #{t['rank']} ({t['centroid_lat']:.4f}, {t['centroid_lon']:.4f}) prob={t['mean_probability']:.3f} area={t['area_pixels']}px dist={t['nearest_known_km']:.1f}km")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()

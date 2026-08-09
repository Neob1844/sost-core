#!/usr/bin/env python3
"""Scan any AOI for mineral prospectivity signals.

Two modes:
A) TRAINED — if model + labels exist, use supervised prediction
B) LABEL-SCARCE — use heuristic proxy scoring (works anywhere on Earth)
"""
import argparse, os, sys, json, csv
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def heuristic_score(bands, band_names):
    """Compute heuristic mineral prospectivity score from raw features.

    Uses domain knowledge: iron oxide + clay + thermal anomaly + ruggedness
    are positive indicators. High NDVI is negative (vegetation = unlikely mining).
    Returns score 0-1 per pixel.
    """
    h, w = bands.shape[1], bands.shape[2]
    score = np.zeros((h, w), dtype=np.float32)
    weight_sum = 0

    name_idx = {n: i for i, n in enumerate(band_names)}

    # Iron oxide ratio (higher = more iron)
    if "iron_oxide" in name_idx:
        v = bands[name_idx["iron_oxide"]]
        v_norm = np.clip((v - np.nanpercentile(v, 10)) / (np.nanpercentile(v, 90) - np.nanpercentile(v, 10) + 1e-8), 0, 1)
        score += v_norm * 3.0
        weight_sum += 3.0

    # Clay/hydroxyl (higher = more alteration)
    if "clay_hydroxyl" in name_idx:
        v = bands[name_idx["clay_hydroxyl"]]
        v_norm = np.clip((v - np.nanpercentile(v, 10)) / (np.nanpercentile(v, 90) - np.nanpercentile(v, 10) + 1e-8), 0, 1)
        score += v_norm * 2.5
        weight_sum += 2.5

    # Ferrous iron
    if "ferrous_iron" in name_idx:
        v = bands[name_idx["ferrous_iron"]]
        v_norm = np.clip((v - np.nanpercentile(v, 10)) / (np.nanpercentile(v, 90) - np.nanpercentile(v, 10) + 1e-8), 0, 1)
        score += v_norm * 2.0
        weight_sum += 2.0

    # Thermal anomaly (higher z-score = hotter than surroundings)
    for tn in ["LST_zscore", "LST_median"]:
        if tn in name_idx:
            v = bands[name_idx[tn]]
            v_norm = np.clip((v - np.nanpercentile(v, 10)) / (np.nanpercentile(v, 90) - np.nanpercentile(v, 10) + 1e-8), 0, 1)
            score += v_norm * 1.5
            weight_sum += 1.5
            break

    # Ruggedness (moderate ruggedness is positive)
    if "ruggedness" in name_idx:
        v = bands[name_idx["ruggedness"]]
        v_norm = np.clip((v - np.nanpercentile(v, 10)) / (np.nanpercentile(v, 90) - np.nanpercentile(v, 10) + 1e-8), 0, 1)
        score += v_norm * 2.0
        weight_sum += 2.0

    # NDVI penalty (high vegetation = unlikely mineral)
    if "ndvi" in name_idx:
        v = bands[name_idx["ndvi"]]
        ndvi_penalty = np.clip(v, 0, 1)
        score -= ndvi_penalty * 2.0

    if weight_sum > 0:
        score = score / weight_sum
    return np.clip(score, 0, 1)


def novelty_score(bands):
    """Compute novelty: how different each pixel is from the AOI mean."""
    h, w = bands.shape[1], bands.shape[2]
    flat = bands.reshape(bands.shape[0], -1).T  # (pixels, bands)
    valid_mask = np.all(np.isfinite(flat), axis=1)
    if valid_mask.sum() < 100:
        return np.zeros((h, w), dtype=np.float32)
    mean = np.nanmean(flat[valid_mask], axis=0)
    std = np.nanstd(flat[valid_mask], axis=0) + 1e-8
    z = np.abs((flat - mean) / std)
    novelty_flat = np.mean(z, axis=1)
    novelty = novelty_flat.reshape(h, w)
    # Normalize 0-1
    p5, p95 = np.nanpercentile(novelty[valid_mask.reshape(h, w)], [5, 95])
    return np.clip((novelty - p5) / (p95 - p5 + 1e-8), 0, 1).astype(np.float32)


def main():
    p = argparse.ArgumentParser(description="Scan AOI for mineral prospectivity")
    p.add_argument("--aoi", required=True)
    p.add_argument("--stack", default=None)
    p.add_argument("--model", default=None, help="Trained model .joblib (optional)")
    p.add_argument("--aoi-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    p.add_argument("--stack-dir", default=os.path.expanduser("~/SOST/geaspirit/data/stack"))
    p.add_argument("--output-dir", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--threshold", type=float, default=0.6)
    args = p.parse_args()

    import rasterio
    from rasterio.transform import xy
    from scipy.ndimage import label as ndlabel

    # Load AOI
    aoi_path = os.path.join(args.aoi_dir, f"{args.aoi}.json")
    if os.path.exists(aoi_path):
        with open(aoi_path) as f:
            aoi = json.load(f)
    else:
        aoi = {"name": args.aoi}

    # Find stack
    if args.stack is None:
        candidates = [
            os.path.join(args.stack_dir, f"{args.aoi}_global_stack.tif"),
            os.path.expanduser(f"~/SOST/geaspirit/data/{args.aoi}_stack.tif"),
        ]
        for c in candidates:
            if os.path.exists(c):
                args.stack = c
                break
    if not args.stack or not os.path.exists(args.stack):
        print(f"  ! No stack found for {args.aoi}")
        return

    # Load stack
    meta_path = args.stack.replace(".tif", "_metadata.json")
    if not os.path.exists(meta_path):
        meta_path = args.stack.replace(".tif", "_meta.json")
    with open(meta_path) as f:
        meta = json.load(f)
    with rasterio.open(args.stack) as src:
        bands = src.read()
        transform = src.transform
        h, w = src.height, src.width

    band_names = meta.get("bands", [f"band_{i}" for i in range(bands.shape[0])])
    px_m = abs(transform.a) * 111000
    mode = "trained" if args.model and os.path.exists(args.model) else "heuristic"

    print(f"=== AOI Scan: {args.aoi} (mode={mode}) ===")
    print(f"  Stack: {w}x{h}, {bands.shape[0]} bands")

    os.makedirs(args.output_dir, exist_ok=True)

    if mode == "trained":
        import joblib
        model_data = joblib.load(args.model)
        mdl = model_data["model"] if isinstance(model_data, dict) else model_data
        valid = np.all(np.isfinite(bands), axis=0)
        prob_map = np.full((h, w), np.nan, dtype=np.float32)
        valid_idx = np.argwhere(valid)
        for i in range(0, len(valid_idx), 50000):
            chunk = valid_idx[i:i+50000]
            X = np.nan_to_num(np.array([bands[:, r, c] for r, c in chunk], dtype=np.float32))
            if X.shape[1] > mdl.n_features_in_:
                X = X[:, :mdl.n_features_in_]
            probs = mdl.predict_proba(X)[:, 1]
            for j, (r, c) in enumerate(chunk):
                prob_map[r, c] = probs[j]
        score_map = prob_map
        score_label = "model_probability"
    else:
        # Heuristic mode
        h_score = heuristic_score(bands, band_names)
        n_score = novelty_score(bands)
        score_map = np.clip(0.6 * h_score + 0.4 * n_score, 0, 1)
        score_label = "heuristic_score"

    # Save score map
    map_path = os.path.join(args.output_dir, f"{args.aoi}_proxy_map.tif")
    with rasterio.open(args.stack) as src:
        profile = src.profile.copy()
    profile.update(count=1, dtype="float32", compress="lzw")
    with rasterio.open(map_path, "w", **profile) as dst:
        dst.write(score_map[np.newaxis])

    # Cluster and rank targets
    valid = np.isfinite(score_map)
    binary = (score_map >= args.threshold) & valid
    labeled, n_clusters = ndlabel(binary)

    targets = []
    for cid in range(1, n_clusters + 1):
        mask = labeled == cid
        area = mask.sum()
        if area < 4:
            continue
        mean_score = float(np.nanmean(score_map[mask]))
        rows, cols = np.where(mask)
        cr, cc = rows.mean(), cols.mean()
        clat, clon = xy(transform, int(cr), int(cc))
        targets.append({
            "rank": 0,
            "centroid_lat": round(float(clat), 5),
            "centroid_lon": round(float(clon), 5),
            "area_pixels": int(area),
            "area_km2": round(area * (px_m ** 2) / 1e6, 2),
            "mean_score": round(mean_score, 4),
            "score_type": score_label,
        })

    targets.sort(key=lambda t: -t["mean_score"] * np.sqrt(t["area_pixels"]))
    for i, t in enumerate(targets[:args.top_k]):
        t["rank"] = i + 1
    targets = targets[:args.top_k]

    # Save targets CSV
    csv_path = os.path.join(args.output_dir, f"{args.aoi}_proxy_targets.csv")
    if targets:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(targets[0].keys()))
            writer.writeheader()
            for t in targets:
                writer.writerow(t)

    # Summary
    high = (score_map > 0.7).sum() * (px_m ** 2) / 1e6 if valid.any() else 0
    mod = ((score_map >= 0.5) & (score_map <= 0.7)).sum() * (px_m ** 2) / 1e6 if valid.any() else 0
    low = (score_map < 0.5).sum() * (px_m ** 2) / 1e6 if valid.any() else 0

    summary = {
        "aoi": args.aoi,
        "mode": mode,
        "score_type": score_label,
        "n_targets": len(targets),
        "threshold": args.threshold,
        "area_high_km2": round(high, 1),
        "area_moderate_km2": round(mod, 1),
        "area_low_km2": round(low, 1),
    }
    with open(os.path.join(args.output_dir, f"{args.aoi}_proxy_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    md = f"# AOI Scan: {args.aoi}\n\n"
    md += f"**Mode**: {mode} ({score_label})\n\n"
    md += f"## Area Breakdown\n"
    md += f"- HIGH (>0.7): {high:.1f} km²\n"
    md += f"- MODERATE (0.5-0.7): {mod:.1f} km²\n"
    md += f"- LOW (<0.5): {low:.1f} km²\n\n"
    md += f"## Top Targets ({len(targets)} above {args.threshold})\n\n"
    md += "| # | Lat | Lon | Area km² | Score |\n|---|-----|-----|----------|-------|\n"
    for t in targets[:20]:
        md += f"| {t['rank']} | {t['centroid_lat']:.4f} | {t['centroid_lon']:.4f} | {t['area_km2']} | {t['mean_score']:.3f} |\n"
    if mode == "heuristic":
        md += f"\n## Note\nThis scan uses **heuristic proxy scoring** (no trained model).\n"
        md += f"Scores indicate surface mineral indicators, NOT confirmed deposits.\n"
        md += f"Validate with ground truth before any investment decision.\n"

    with open(os.path.join(args.output_dir, f"{args.aoi}_proxy_summary.md"), "w") as f:
        f.write(md)

    print(f"  Targets: {len(targets)} above {args.threshold}")
    print(f"  Area HIGH: {high:.1f} km², MODERATE: {mod:.1f} km², LOW: {low:.1f} km²")
    print(f"  Saved: {args.aoi}_proxy_summary.md + targets.csv + map.tif")
    if targets:
        print(f"  Top 3:")
        for t in targets[:3]:
            print(f"    #{t['rank']} ({t['centroid_lat']:.4f}, {t['centroid_lon']:.4f}) score={t['mean_score']:.3f} area={t['area_km2']}km²")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Priority 3 — Build geology-aware negative samples.

Three tiers of negatives:
A) Random negatives — far from deposits, random locations
B) Hard negatives by proximity — within 5-15km of deposits but not in buffer
C) Matched negatives by geological similarity — similar terrain/spectral/geology
   signatures but no known deposit

The goal: teach the model to distinguish "geologically favorable" from
"geologically similar but barren".
"""
import argparse, os, sys, json, csv
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, HALF_DEG


def cosine_similarity(a, b):
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def main():
    p = argparse.ArgumentParser(description="Build geology-aware negative samples")
    p.add_argument("--stack", default=None)
    p.add_argument("--geology-stack", default=None)
    p.add_argument("--mrds-curated", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds_curated.csv"))
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--buffer-m", type=float, default=500, help="Exclusion buffer around deposits")
    p.add_argument("--hard-min-km", type=float, default=5, help="Hard negative min distance")
    p.add_argument("--hard-max-km", type=float, default=15, help="Hard negative max distance")
    p.add_argument("--matched-top-k", type=int, default=50, help="Top-K most similar pixels per deposit")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/data/targets"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    if args.stack is None:
        args.stack = os.path.expanduser(f"~/SOST/geaspirit/data/{args.pilot}_stack.tif")
    if args.geology_stack is None:
        args.geology_stack = os.path.expanduser(f"~/SOST/geaspirit/data/geology_maps/{args.pilot}_geology_stack.tif")

    import rasterio
    from rasterio.transform import rowcol

    # Check required files
    if not os.path.exists(args.stack):
        print(f"  ! Stack not found: {args.stack}")
        print(f"  ! Run satellite download scripts first for {args.pilot}")
        return

    if not os.path.exists(args.mrds_curated):
        print(f"  ! Curated MRDS not found: {args.mrds_curated}")
        print(f"  ! Run curate_labels.py first")
        return

    print(f"=== Building Geology-Aware Negatives — {args.pilot} ===")

    # Load stack
    with rasterio.open(args.stack) as src:
        all_bands = src.read()  # (n_bands, h, w)
        transform = src.transform
        h, w = src.height, src.width

    px_deg = abs(transform.a)
    px_m = px_deg * 111000
    n_bands = all_bands.shape[0]
    print(f"  Stack: {w}x{h}, {n_bands} bands, {px_m:.1f}m/px")

    # Load geology stack if available
    has_geology = False
    geology_bands = None
    if os.path.exists(args.geology_stack):
        with rasterio.open(args.geology_stack) as gsrc:
            geology_bands = gsrc.read()
            has_geology = True
            print(f"  Geology stack: {geology_bands.shape[0]} bands loaded")
    else:
        print(f"  ! No geology stack — matched negatives will use spectral/terrain only")

    # Load curated deposits
    zone = ZONES[args.pilot]
    lat_c, lon_c = zone["center"]
    bbox = [lon_c - HALF_DEG, lat_c - HALF_DEG, lon_c + HALF_DEG, lat_c + HALF_DEG]

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
                    deposits.append({
                        "id": row.get("deposit_id_clean", ""),
                        "name": row.get("site_name", ""),
                        "lat": lat, "lon": lon,
                        "row": r, "col": c,
                    })
            except (ValueError, TypeError):
                continue
    print(f"  Curated deposits loaded: {len(deposits)}")

    if not deposits:
        print("  ! No deposits found — cannot generate negatives")
        return

    rng = np.random.RandomState(42)
    valid = np.all(np.isfinite(all_bands), axis=0)

    # Compute masks
    buf_px = max(1, int(args.buffer_m / px_m))
    hard_min_px = max(1, int(args.hard_min_km * 1000 / px_m))
    hard_max_px = max(1, int(args.hard_max_km * 1000 / px_m))
    far_px = hard_max_px  # anything beyond hard_max is "far"

    # Exclusion buffer mask (positive zone)
    pos_mask = np.zeros((h, w), dtype=bool)
    for d in deposits:
        r0, r1 = max(0, d["row"] - buf_px), min(h, d["row"] + buf_px + 1)
        c0, c1 = max(0, d["col"] - buf_px), min(w, d["col"] + buf_px + 1)
        pos_mask[r0:r1, c0:c1] = True

    # Hard negative zone: hard_min to hard_max from any deposit
    near_mask = np.zeros((h, w), dtype=bool)  # within hard_min
    hard_zone = np.zeros((h, w), dtype=bool)  # within hard_max
    for d in deposits:
        r, c = d["row"], d["col"]
        # Near mask (within hard_min)
        r0, r1 = max(0, r - hard_min_px), min(h, r + hard_min_px + 1)
        c0, c1 = max(0, c - hard_min_px), min(w, c + hard_min_px + 1)
        near_mask[r0:r1, c0:c1] = True
        # Hard zone (within hard_max)
        r0, r1 = max(0, r - hard_max_px), min(h, r + hard_max_px + 1)
        c0, c1 = max(0, c - hard_max_px), min(w, c + hard_max_px + 1)
        hard_zone[r0:r1, c0:c1] = True

    hard_neg_eligible = hard_zone & ~near_mask & ~pos_mask & valid
    far_neg_eligible = ~hard_zone & valid

    print(f"  Positive pixels: {pos_mask.sum():,}")
    print(f"  Hard neg eligible: {hard_neg_eligible.sum():,}")
    print(f"  Far neg eligible: {far_neg_eligible.sum():,}")

    # === TYPE A: Random far negatives ===
    n_random = min(len(deposits) * 200, int(far_neg_eligible.sum()))
    far_idx = np.argwhere(far_neg_eligible)
    if len(far_idx) > n_random:
        sel = rng.choice(len(far_idx), n_random, replace=False)
        far_idx = far_idx[sel]
    print(f"  Type A (random far): {len(far_idx)}")

    # === TYPE B: Hard negatives by proximity ===
    n_hard = min(len(deposits) * 100, int(hard_neg_eligible.sum()))
    hard_idx = np.argwhere(hard_neg_eligible)
    if len(hard_idx) > n_hard:
        sel = rng.choice(len(hard_idx), n_hard, replace=False)
        hard_idx = hard_idx[sel]
    print(f"  Type B (hard proximity): {len(hard_idx)}")

    # === TYPE C: Matched negatives by geological similarity ===
    # For each deposit, find the most similar pixels outside buffer
    matched_negatives = []
    if len(deposits) > 0:
        # Build deposit feature profiles
        deposit_profiles = []
        for d in deposits:
            r, c = d["row"], d["col"]
            # Extract features in small window around deposit
            win = 3
            r0, r1 = max(0, r - win), min(h, r + win + 1)
            c0, c1 = max(0, c - win), min(w, c + win + 1)
            patch = all_bands[:, r0:r1, c0:c1]
            if has_geology:
                gpatch = geology_bands[:, r0:r1, c0:c1]
                patch = np.concatenate([patch, gpatch], axis=0)
            profile = np.nanmean(patch, axis=(1, 2))
            deposit_profiles.append(profile)
            d["profile"] = profile

        # Sample candidate pixels from hard neg zone
        candidate_mask = hard_neg_eligible
        candidate_idx = np.argwhere(candidate_mask)
        max_candidates = min(50000, len(candidate_idx))
        if len(candidate_idx) > max_candidates:
            sel = rng.choice(len(candidate_idx), max_candidates, replace=False)
            candidate_idx = candidate_idx[sel]

        # Build candidate features
        print(f"  Computing similarity for {len(candidate_idx)} candidates...")
        candidate_features = np.array([all_bands[:, r, c] for r, c in candidate_idx], dtype=np.float32)
        if has_geology:
            candidate_geo = np.array([geology_bands[:, r, c] for r, c in candidate_idx], dtype=np.float32)
            candidate_features = np.concatenate([candidate_features, candidate_geo], axis=1)

        # For each deposit, find top-K most similar candidates
        for di, d in enumerate(deposits):
            profile = d["profile"]
            if np.any(np.isnan(profile)):
                continue
            # Cosine similarity
            valid_mask = np.all(np.isfinite(candidate_features), axis=1)
            valid_candidates = candidate_features[valid_mask]
            valid_idx = candidate_idx[valid_mask]
            if len(valid_candidates) == 0:
                continue

            # Vectorized cosine similarity
            norms = np.linalg.norm(valid_candidates, axis=1)
            prof_norm = np.linalg.norm(profile)
            if prof_norm == 0:
                continue
            sims = valid_candidates @ profile / (norms * prof_norm + 1e-8)

            # Top-K
            top_k = min(args.matched_top_k, len(sims))
            top_indices = np.argsort(sims)[-top_k:]
            for idx in top_indices:
                r, c = valid_idx[idx]
                matched_negatives.append({
                    "row": int(r), "col": int(c),
                    "matched_deposit": d["id"],
                    "similarity": float(sims[idx]),
                })

    # Deduplicate matched negatives by pixel
    seen_pixels = set()
    unique_matched = []
    for m in matched_negatives:
        key = (m["row"], m["col"])
        if key not in seen_pixels:
            seen_pixels.add(key)
            unique_matched.append(m)
    matched_idx = np.array([[m["row"], m["col"]] for m in unique_matched]) if unique_matched else np.empty((0, 2), dtype=int)
    print(f"  Type C (matched similarity): {len(matched_idx)}")

    # === Combine all negatives ===
    all_negatives = []

    for r, c in far_idx:
        lat_px = transform.f + (r + 0.5) * transform.e
        lon_px = transform.c + (c + 0.5) * transform.a
        all_negatives.append({
            "row": int(r), "col": int(c),
            "latitude": round(float(lat_px), 6),
            "longitude": round(float(lon_px), 6),
            "negative_type": "random_far",
            "matched_to_deposit_id": "",
            "geological_similarity_score": 0.0,
            "distance_to_known_deposit_km": 0.0,  # computed below
        })

    for r, c in hard_idx:
        lat_px = transform.f + (r + 0.5) * transform.e
        lon_px = transform.c + (c + 0.5) * transform.a
        all_negatives.append({
            "row": int(r), "col": int(c),
            "latitude": round(float(lat_px), 6),
            "longitude": round(float(lon_px), 6),
            "negative_type": "hard_proximity",
            "matched_to_deposit_id": "",
            "geological_similarity_score": 0.0,
            "distance_to_known_deposit_km": 0.0,
        })

    for m in unique_matched:
        r, c = m["row"], m["col"]
        lat_px = transform.f + (r + 0.5) * transform.e
        lon_px = transform.c + (c + 0.5) * transform.a
        all_negatives.append({
            "row": int(r), "col": int(c),
            "latitude": round(float(lat_px), 6),
            "longitude": round(float(lon_px), 6),
            "negative_type": "matched_similarity",
            "matched_to_deposit_id": m["matched_deposit"],
            "geological_similarity_score": round(m["similarity"], 4),
            "distance_to_known_deposit_km": 0.0,
        })

    # Compute distance to nearest deposit for each negative
    dep_coords = np.array([(d["row"], d["col"]) for d in deposits])
    for neg in all_negatives:
        dists = np.sqrt((dep_coords[:, 0] - neg["row"])**2 + (dep_coords[:, 1] - neg["col"])**2) * px_m / 1000
        neg["distance_to_known_deposit_km"] = round(float(dists.min()), 2)

    # Assign fold candidates (spatial blocks)
    block_px = max(1, int(10000 / px_m))  # 10km blocks
    for neg in all_negatives:
        br = neg["row"] // block_px
        bc = neg["col"] // block_px
        neg["fold_candidate"] = (br * ((w + block_px - 1) // block_px) + bc) % 5

    print(f"\n  === NEGATIVE SUMMARY ===")
    type_counts = {}
    for neg in all_negatives:
        t = neg["negative_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, cnt in sorted(type_counts.items()):
        print(f"    {t}: {cnt}")
    print(f"    TOTAL: {len(all_negatives)}")

    # Save as CSV (GeoPackage requires fiona, CSV is more portable)
    os.makedirs(args.output, exist_ok=True)
    csv_path = os.path.join(args.output, f"{args.pilot}_negatives.csv")
    fieldnames = ["row", "col", "latitude", "longitude", "negative_type",
                  "matched_to_deposit_id", "geological_similarity_score",
                  "distance_to_known_deposit_km", "fold_candidate"]
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for neg in all_negatives:
            writer.writerow({k: neg[k] for k in fieldnames})
    print(f"  Saved: {csv_path}")

    # Summary report
    os.makedirs(args.reports, exist_ok=True)
    summary = {
        "pilot": args.pilot,
        "total_negatives": len(all_negatives),
        "type_counts": type_counts,
        "deposits_used": len(deposits),
        "buffer_m": args.buffer_m,
        "hard_range_km": [args.hard_min_km, args.hard_max_km],
        "matched_top_k": args.matched_top_k,
        "has_geology": has_geology,
        "avg_distance_km": {
            t: round(np.mean([n["distance_to_known_deposit_km"]
                              for n in all_negatives if n["negative_type"] == t]), 2)
            for t in type_counts
        },
        "avg_similarity": {
            "matched_similarity": round(np.mean([
                n["geological_similarity_score"]
                for n in all_negatives if n["negative_type"] == "matched_similarity"
            ]), 4) if type_counts.get("matched_similarity") else 0,
        },
    }
    with open(os.path.join(args.reports, f"{args.pilot}_negatives_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    md = f"# Geology-Aware Negatives — {args.pilot}\n\n"
    md += f"## Configuration\n"
    md += f"- Buffer: {args.buffer_m}m\n"
    md += f"- Hard negative range: {args.hard_min_km}-{args.hard_max_km}km\n"
    md += f"- Matched top-K per deposit: {args.matched_top_k}\n"
    md += f"- Geology features available: {'Yes' if has_geology else 'No'}\n\n"
    md += f"## Results\n\n"
    md += f"| Type | Count | Avg Distance (km) |\n|------|-------|-------------------|\n"
    for t, cnt in sorted(type_counts.items()):
        avg_d = summary["avg_distance_km"][t]
        md += f"| {t} | {cnt:,} | {avg_d:.1f} |\n"
    md += f"| **TOTAL** | **{len(all_negatives):,}** | |\n"
    if unique_matched:
        avg_sim = summary["avg_similarity"]["matched_similarity"]
        md += f"\nAverage geological similarity score (matched): **{avg_sim:.4f}**\n"
    md += f"\n## Purpose\n"
    md += f"These negatives force the model to learn what distinguishes\n"
    md += f"mineralized terrain from geologically *similar* but barren terrain.\n"

    with open(os.path.join(args.reports, f"{args.pilot}_negatives_summary.md"), "w") as f:
        f.write(md)
    print(f"  Report: {args.pilot}_negatives_summary.md")


if __name__ == "__main__":
    main()

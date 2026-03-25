#!/usr/bin/env python3
"""
GeaSpirit Research Loop V2 — Connected to REAL DATA

Critical fixes from V1:
1. Uses actual Kalgoorlie satellite+magnetics data, not synthetic
2. Hypothesis advancement logic fixed
3. Mineral identification uses separate Au-vs-Ni classifier
4. Depth estimation uses real magnetic Euler proxy
5. Each hypothesis adds CUMULATIVE features

This is the real experiment that matters.
"""
import os, sys, json, time, logging
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.isotonic import IsotonicRegression
from scipy.stats import mannwhitneyu
from scipy.ndimage import uniform_filter
import warnings
warnings.filterwarnings('ignore')

BASE = os.path.expanduser("~/SOST/geaspirit")
SAT_STACK = f"{BASE}/data/stack/kalgoorlie_50km_full_stack.tif"
MAG_STACK = f"{BASE}/data/geophysics/kalgoorlie_magnetics_stack_v2.tif"
THERMAL_STACK = f"{BASE}/data/thermal_20yr/kalgoorlie_thermal_20yr_v2.tif"
LABELS_PATH = f"{BASE}/data/labels/kalgoorlie_50km_labels_curated.csv"

RESEARCH_DIR = Path("geaspirit_research_v2")
RESEARCH_DIR.mkdir(exist_ok=True)
LOG_FILE = RESEARCH_DIR / "research_log.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(RESEARCH_DIR / "research.log"),
                              logging.StreamHandler()])
log = logging.getLogger("GeaSpiritV2")

NODATA = -9999
MIN_DIST_KM = 5.0
BG_RATIO = 3
BLOCK_SIZE_DEG = 0.05

SAT_NAMES = ["iron_oxide","clay_hydroxyl","ferrous_iron","laterite","ndvi",
             "elevation","slope","tpi","ruggedness","LST_median","LST_p90","LST_zscore"]
MAG_NAMES = ["tmi_raw","tmi_normalized","tmi_local_anomaly","tmi_gradient","magnetic_depth_proxy_m"]


def haversine_km(lat1, lon1, lat2, lon2):
    dlat, dlon = np.radians(lat2-lat1), np.radians(lon2-lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))


def extract_pixel(raster, transform, lon, lat):
    c, r = ~transform * (lon, lat)
    c, r = int(c), int(r)
    if 0 <= r < raster.shape[1] and 0 <= c < raster.shape[2]:
        v = raster[:, r, c].astype(float)
        v[~np.isfinite(v)] = 0; v[v == NODATA] = 0
        return v
    return None


def extract_neighborhood(raster, transform, lon, lat, radius=5):
    """Extract stats from NxN neighborhood around a point."""
    c, r = ~transform * (lon, lat)
    c, r = int(c), int(r)
    h = radius
    if h <= r < raster.shape[1]-h and h <= c < raster.shape[2]-h:
        patch = raster[:, r-h:r+h+1, c-h:c+h+1].astype(float)
        patch[~np.isfinite(patch)] = 0
        patch[patch == NODATA] = 0
        # Stats per band: mean, std, max-min, center-vs-surround
        feats = []
        for b in range(patch.shape[0]):
            band = patch[b]
            center = float(band[h, h])
            feats += [
                np.mean(band), np.std(band),
                np.max(band) - np.min(band),
                center - np.mean(band),  # local anomaly
            ]
        return np.array(feats)
    return None


def spatial_block_cv(X, y, lats, lons, n_splits=5, return_proba=False):
    blocks = ((lats/BLOCK_SIZE_DEG).astype(int)*10000 + (lons/BLOCK_SIZE_DEG).astype(int))
    unique_blocks = np.unique(blocks)
    rng = np.random.RandomState(42)
    rng.shuffle(unique_blocks)
    fold_size = max(1, len(unique_blocks)//n_splits)

    aucs, probas_all = [], np.zeros(len(y))
    tested = np.zeros(len(y), dtype=bool)

    for fold in range(n_splits):
        test_b = set(unique_blocks[fold*fold_size:(fold+1)*fold_size])
        test_m = np.isin(blocks, list(test_b))
        train_m = ~test_m
        if test_m.sum() < 2 or train_m.sum() < 5: continue
        if len(np.unique(y[test_m])) < 2: continue

        clf = GradientBoostingClassifier(n_estimators=300, max_depth=5, learning_rate=0.05,
                                          subsample=0.8, random_state=42)
        clf.fit(X[train_m], y[train_m])
        proba = clf.predict_proba(X[test_m])[:, 1]
        probas_all[test_m] = proba
        tested[test_m] = True
        try: aucs.append(roc_auc_score(y[test_m], proba))
        except: pass

    auc = np.mean(aucs) if aucs else None
    if return_proba:
        return auc, probas_all, tested
    return auc


# ─────────────────────────────────────────────
# HYPOTHESIS IMPLEMENTATIONS (each adds features)
# ─────────────────────────────────────────────

HYPOTHESES = [
    "H1_baseline_only",
    "H2_add_magnetics",
    "H3_add_neighborhood_context",
    "H4_add_band_ratios",
    "H5_add_isotonic_calibration",
    "H6_mineral_specific_model",
    "H7_depth_from_magnetics",
    "H8_ensemble_all",
]


def build_features(hypothesis_idx, sat_data, sat_tf, mag_data, mag_tf,
                   thermal_data, thermal_tf, labels):
    """Progressively build feature set based on hypothesis index."""

    dep_feats, bg_feats = [], []
    dep_locs, bg_locs = [], []
    minerals = []

    # Extract deposit features
    for _, row in labels.iterrows():
        sv = extract_pixel(sat_data, sat_tf, row.longitude, row.latitude)
        if sv is None: continue

        feat = list(sv)  # H1: baseline satellite

        if hypothesis_idx >= 1 and mag_data is not None:  # H2: magnetics
            mv = extract_pixel(mag_data, mag_tf, row.longitude, row.latitude)
            feat.extend(mv if mv is not None else [0]*mag_data.shape[0])

        if hypothesis_idx >= 2:  # H3: neighborhood context
            nb = extract_neighborhood(sat_data, sat_tf, row.longitude, row.latitude, radius=5)
            if nb is not None:
                feat.extend(nb)
            else:
                feat.extend([0] * sat_data.shape[0] * 4)

        if hypothesis_idx >= 3:  # H4: band ratios
            # ferrous/iron_oxide, clay/laterite, NDVI/LST
            with np.errstate(divide='ignore', invalid='ignore'):
                r1 = sv[2] / max(sv[0], 0.001)  # ferrous/iron_oxide
                r2 = sv[1] / max(sv[3], 0.001)  # clay/laterite
                r3 = sv[4] / max(abs(sv[9]), 0.001)  # ndvi/LST
                r4 = sv[8] / max(sv[6], 0.001)  # ruggedness/slope
            feat.extend([r1, r2, r3, r4])

        if hypothesis_idx >= 4 and thermal_data is not None:  # H5+ uses thermal
            tv = extract_pixel(thermal_data, thermal_tf, row.longitude, row.latitude)
            if tv is not None:
                feat.extend(tv)
            else:
                feat.extend([0]*thermal_data.shape[0])

        dep_feats.append(feat)
        dep_locs.append((row.latitude, row.longitude))
        mineral = 'Au' if 'Au' in str(row.commodity_codes).split(',')[0] else \
                  'Ni' if 'Ni' in str(row.commodity_codes).split(',')[0] else 'other'
        minerals.append(mineral)

    # Sample background
    rng = np.random.RandomState(42)
    ny, nx = sat_data.shape[1], sat_data.shape[2]
    target = len(dep_locs) * BG_RATIO
    attempts = 0
    while len(bg_locs) < target and attempts < target * 100:
        r = rng.randint(0, ny); c = rng.randint(0, nx)
        v = sat_data[:, r, c].astype(float)
        if not np.all(np.isfinite(v)) or np.any(v == NODATA):
            attempts += 1; continue
        lon, lat = sat_tf * (c+0.5, r+0.5)
        if min(haversine_km(lat, lon, dl[0], dl[1]) for dl in dep_locs) >= MIN_DIST_KM:
            feat = list(np.nan_to_num(v, nan=0, posinf=0, neginf=0))

            if hypothesis_idx >= 1 and mag_data is not None:
                mv = extract_pixel(mag_data, mag_tf, lon, lat)
                feat.extend(mv if mv is not None else [0]*mag_data.shape[0])

            if hypothesis_idx >= 2:
                nb = extract_neighborhood(sat_data, sat_tf, lon, lat, radius=5)
                feat.extend(nb if nb is not None else [0]*sat_data.shape[0]*4)

            if hypothesis_idx >= 3:
                with np.errstate(divide='ignore', invalid='ignore'):
                    feat.extend([v[2]/max(v[0],0.001), v[1]/max(v[3],0.001),
                                 v[4]/max(abs(v[9]),0.001), v[8]/max(v[6],0.001)])

            if hypothesis_idx >= 4 and thermal_data is not None:
                tv = extract_pixel(thermal_data, thermal_tf, lon, lat)
                feat.extend(tv if tv is not None else [0]*thermal_data.shape[0])

            bg_feats.append(feat)
            bg_locs.append((lat, lon))
        attempts += 1

    return (np.array(dep_feats), np.array(bg_feats),
            dep_locs, bg_locs, minerals)


def run_hypothesis(idx, hypothesis_name, sat_data, sat_tf, mag_data, mag_tf,
                   thermal_data, thermal_tf, labels):
    """Run a single hypothesis and return results."""
    log.info(f"\n{'='*60}")
    log.info(f"  {hypothesis_name} (progressive features)")
    log.info(f"{'='*60}")

    dep_X, bg_X, dep_locs, bg_locs, minerals = build_features(
        idx, sat_data, sat_tf, mag_data, mag_tf, thermal_data, thermal_tf, labels)

    # Ensure same feature count
    min_feats = min(dep_X.shape[1], bg_X.shape[1])
    dep_X, bg_X = dep_X[:, :min_feats], bg_X[:, :min_feats]

    X = np.vstack([dep_X, bg_X])
    X = np.nan_to_num(X, nan=0, posinf=0, neginf=0)
    y = np.array([1]*len(dep_X) + [0]*len(bg_X))
    lats = np.array([l[0] for l in dep_locs + bg_locs])
    lons = np.array([l[1] for l in dep_locs + bg_locs])

    log.info(f"  Samples: {len(dep_X)} deposits + {len(bg_X)} background = {len(X)}")
    log.info(f"  Features: {X.shape[1]}")

    # ── Detection AUC ──
    auc, probas, tested = spatial_block_cv(X, y, lats, lons, return_proba=True)
    log.info(f"  Detection AUC: {auc:.4f}" if auc else "  AUC: N/A")

    # ── Calibration ──
    brier = None
    cal_error = 0
    if auc and tested.sum() > 20:
        brier = brier_score_loss(y[tested], probas[tested])
        # Isotonic calibration (in-sample estimate)
        iso = IsotonicRegression(out_of_bounds='clip')
        iso.fit(probas[tested], y[tested])
        cal_probas = iso.predict(probas[tested])
        brier_cal = brier_score_loss(y[tested], cal_probas)
        for lo in np.arange(0, 1, 0.1):
            mask = (cal_probas >= lo) & (cal_probas < lo + 0.1)
            if mask.sum() > 5:
                cal_error = max(cal_error, abs(cal_probas[mask].mean() - y[tested][mask].mean()))
        log.info(f"  Brier: {brier:.4f} -> {brier_cal:.4f} (calibrated)")
        log.info(f"  Max calibration error: {cal_error:.3f}")

    # ── Mineral identification (Au vs Ni) ──
    mineral_arr = np.array(minerals)
    au_mask = mineral_arr == 'Au'
    ni_mask = mineral_arr == 'Ni'
    mineral_auc = None

    if au_mask.sum() >= 20 and ni_mask.sum() >= 20:
        au_ni_mask = au_mask | ni_mask
        X_mn = dep_X[au_ni_mask]
        y_mn = au_mask[au_ni_mask].astype(int)
        lats_mn = np.array([dep_locs[i][0] for i in range(len(dep_locs)) if au_ni_mask[i]])
        lons_mn = np.array([dep_locs[i][1] for i in range(len(dep_locs)) if au_ni_mask[i]])
        X_mn = np.nan_to_num(X_mn, nan=0, posinf=0, neginf=0)
        mineral_auc = spatial_block_cv(X_mn, y_mn, lats_mn, lons_mn)
        log.info(f"  Mineral AUC (Au vs Ni): {mineral_auc:.4f}" if mineral_auc else "  Mineral: N/A")

    # ── Depth proxy (from magnetics) ──
    depth_signal = None
    if mag_data is not None:
        # Extract depth proxy for deposits vs background
        dep_depths = [dep_X[i, 12+4] for i in range(len(dep_X))
                      if dep_X.shape[1] > 16 and dep_X[i, 12+4] > 0]
        bg_depths_sample = [bg_X[i, 12+4] for i in range(min(500, len(bg_X)))
                            if bg_X.shape[1] > 16 and bg_X[i, 12+4] > 0]
        if len(dep_depths) > 10 and len(bg_depths_sample) > 10:
            _, p = mannwhitneyu(dep_depths, bg_depths_sample, alternative='two-sided')
            ps = np.sqrt((np.std(dep_depths)**2 + np.std(bg_depths_sample)**2)/2)
            d = (np.mean(dep_depths) - np.mean(bg_depths_sample)) / ps if ps > 0 else 0
            depth_signal = {"d": round(d, 3), "p": round(float(p), 6),
                            "dep_median": round(float(np.median(dep_depths)), 0),
                            "bg_median": round(float(np.median(bg_depths_sample)), 0)}
            log.info(f"  Depth proxy: d={d:+.3f}, p={p:.4f}, "
                     f"deposits={np.median(dep_depths):.0f}m vs bg={np.median(bg_depths_sample):.0f}m")

    # ── Score ──
    scores = {"coordinates": 7.0}

    # Certainty
    if auc and auc > 0.85:
        scores["certainty"] = min(10, round((auc * 0.6 + (1-cal_error) * 0.4) * 10, 1))
    elif auc:
        scores["certainty"] = round(auc * 10 * 0.8, 1)
    else:
        scores["certainty"] = 0

    # Mineral
    if mineral_auc and mineral_auc > 0.7:
        scores["mineral"] = round(2 + (mineral_auc - 0.5) / 0.5 * 8, 1)
    elif mineral_auc and mineral_auc > 0.55:
        scores["mineral"] = round(2 + (mineral_auc - 0.5) * 10, 1)
    else:
        scores["mineral"] = 2.0

    # Depth
    if depth_signal and depth_signal["p"] < 0.05:
        scores["depth"] = min(6, round(3 + abs(depth_signal["d"]) * 5, 1))
    else:
        scores["depth"] = 3.0

    total = sum(scores.values())

    log.info(f"\n  SCORES:")
    log.info(f"    MINERAL:     {scores['mineral']:.1f}/10")
    log.info(f"    DEPTH:       {scores['depth']:.1f}/10")
    log.info(f"    COORDINATES: {scores['coordinates']:.1f}/10")
    log.info(f"    CERTAINTY:   {scores['certainty']:.1f}/10")
    log.info(f"    TOTAL:       {total:.1f}/40 ({total/40*100:.0f}%)")

    return {
        "hypothesis": hypothesis_name,
        "n_features": int(X.shape[1]),
        "detection_auc": round(auc, 4) if auc else None,
        "brier": round(brier, 4) if brier else None,
        "mineral_auc": round(mineral_auc, 4) if mineral_auc else None,
        "depth_signal": depth_signal,
        "scores": scores,
        "total": round(total, 1),
    }


def main():
    t0 = time.time()
    print("GeaSpirit Research Loop V2 — REAL DATA")
    print("Progressive hypothesis testing on Kalgoorlie")
    print()

    import rasterio

    # Load real data
    stacks = {}
    for name, path in [("sat", SAT_STACK), ("mag", MAG_STACK), ("thermal", THERMAL_STACK)]:
        if os.path.exists(path):
            with rasterio.open(path) as src:
                stacks[name] = {"data": src.read(), "transform": src.transform}
                log.info(f"  {name}: {stacks[name]['data'].shape}")

    labels = pd.read_csv(LABELS_PATH)
    log.info(f"  Labels: {len(labels)}")

    sat_data = stacks["sat"]["data"]; sat_tf = stacks["sat"]["transform"]
    mag_data = stacks.get("mag", {}).get("data"); mag_tf = stacks.get("mag", {}).get("transform")
    thermal_data = stacks.get("thermal", {}).get("data"); thermal_tf = stacks.get("thermal", {}).get("transform")

    # Run all hypotheses progressively
    all_results = []
    for idx, hypothesis in enumerate(HYPOTHESES):
        if idx >= 5:  # H6+ are analysis-only, not feature additions
            break
        result = run_hypothesis(idx, hypothesis, sat_data, sat_tf,
                                mag_data, mag_tf, thermal_data, thermal_tf, labels)
        all_results.append(result)

        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(result) + "\n")

    # ── Final summary ──
    print(f"\n{'='*60}")
    print(f"  PROGRESSIVE RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Hypothesis':<35} {'Feats':>5} {'AUC':>7} {'Mineral':>8} {'Total':>7}")
    print(f"  {'-'*70}")
    for r in all_results:
        auc_s = f"{r['detection_auc']:.4f}" if r['detection_auc'] else "N/A"
        min_s = f"{r['mineral_auc']:.4f}" if r['mineral_auc'] else "N/A"
        print(f"  {r['hypothesis']:<35} {r['n_features']:>5} {auc_s:>7} {min_s:>8} {r['total']:>5.1f}/40")

    # Best result
    best = max(all_results, key=lambda x: x["total"])
    print(f"\n  BEST: {best['hypothesis']} → {best['total']}/40")
    print(f"  Detection AUC: {best['detection_auc']}")
    print(f"  Mineral AUC: {best['mineral_auc']}")

    # Save summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "results": all_results,
        "best": best,
        "elapsed_s": round(time.time()-t0, 1),
    }
    (RESEARCH_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\nElapsed: {time.time()-t0:.0f}s")
    print(f"Results in: {RESEARCH_DIR}/")


if __name__ == "__main__":
    main()

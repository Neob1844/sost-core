"""Training dataset builder from MRDS + raster indices."""
import csv
import numpy as np
from pathlib import Path


def load_mrds_deposits(mrds_path, min_lat=-90, max_lat=90, min_lon=-180, max_lon=180):
    """Load MRDS deposit coordinates, filtered by bounding box."""
    deposits = []
    with open(mrds_path, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row.get('latitude', row.get('lat', '')))
                lon = float(row.get('longitude', row.get('lon', '')))
                if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                    deposits.append({
                        'lat': lat, 'lon': lon,
                        'name': row.get('dep_name', row.get('name', '')),
                        'commodity': row.get('commod1', row.get('commodity', '')),
                    })
            except (ValueError, TypeError):
                continue
    return deposits


def create_training_samples(index_arrays, transform, deposits, buffer_m=500, neg_dist_m=5000, seed=42):
    """Create positive/negative training samples from raster indices + deposit locations.

    Args:
        index_arrays: dict of {name: 2D numpy array}
        transform: rasterio affine transform
        deposits: list of {lat, lon, ...}
        buffer_m: radius around deposit for positive samples (meters)
        neg_dist_m: minimum distance from any deposit for negative samples

    Returns:
        X: numpy array (n_samples, n_features)
        y: numpy array (n_samples,) — 1=deposit, 0=no deposit
    """
    rng = np.random.RandomState(seed)
    h, w = list(index_arrays.values())[0].shape
    feature_names = sorted(index_arrays.keys())

    # Convert deposit coords to pixel coords
    from rasterio.transform import rowcol
    dep_pixels = set()
    for d in deposits:
        try:
            row, col = rowcol(transform, d['lon'], d['lat'])
            if 0 <= row < h and 0 <= col < w:
                # Buffer: approximate pixels
                px_sz = abs(transform.a)
                if px_sz < 0.01:  # degrees
                    px_sz *= 111000
                px_buf = max(1, int(buffer_m / px_sz))
                for dr in range(-px_buf, px_buf + 1):
                    for dc in range(-px_buf, px_buf + 1):
                        r, c = row + dr, col + dc
                        if 0 <= r < h and 0 <= c < w:
                            dep_pixels.add((r, c))
        except Exception:
            continue

    # Extract positive samples
    positives = []
    for r, c in dep_pixels:
        feats = [index_arrays[f][r, c] for f in feature_names]
        if not any(np.isnan(feats)):
            positives.append(feats)

    # Negative samples: random pixels far from deposits (fast mask-based)
    # Handle degree-based CRS: 1° ≈ 111,000m at equator
    px_size = max(abs(transform.a), abs(transform.e))
    if px_size < 0.01:  # CRS in degrees
        px_size_m = px_size * 111000
    else:
        px_size_m = px_size
    neg_px_dist = max(1, int(neg_dist_m / px_size_m))
    # Build proximity mask: True where far from deposits
    dep_mask = np.zeros((h, w), dtype=bool)
    for r, c in dep_pixels:
        r0, r1 = max(0, r - neg_px_dist), min(h, r + neg_px_dist + 1)
        c0, c1 = max(0, c - neg_px_dist), min(w, c + neg_px_dist + 1)
        dep_mask[r0:r1, c0:c1] = True
    far_pixels = np.argwhere(~dep_mask)
    if len(far_pixels) > 0:
        target_neg = min(len(positives) * 2, len(far_pixels))
        chosen = rng.choice(len(far_pixels), size=target_neg, replace=False)
        negatives = []
        for idx in chosen:
            r, c = far_pixels[idx]
            feats = [index_arrays[f][r, c] for f in feature_names]
            if not any(np.isnan(feats)):
                negatives.append(feats)
    else:
        negatives = []

    X = np.array(positives + negatives, dtype=np.float32)
    y = np.array([1] * len(positives) + [0] * len(negatives), dtype=np.int32)

    return X, y, feature_names

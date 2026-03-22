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
                # Buffer: approximate pixels (buffer_m / pixel_size)
                px_buf = max(1, int(buffer_m / abs(transform.a)))
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

    # Negative samples: random pixels far from deposits
    neg_px_dist = int(neg_dist_m / abs(transform.a))
    negatives = []
    attempts = 0
    while len(negatives) < len(positives) * 2 and attempts < len(positives) * 20:
        r, c = rng.randint(0, h), rng.randint(0, w)
        if all(abs(r - dr) > neg_px_dist or abs(c - dc) > neg_px_dist for dr, dc in dep_pixels):
            feats = [index_arrays[f][r, c] for f in feature_names]
            if not any(np.isnan(feats)):
                negatives.append(feats)
        attempts += 1

    X = np.array(positives + negatives, dtype=np.float32)
    y = np.array([1] * len(positives) + [0] * len(negatives), dtype=np.int32)

    return X, y, feature_names

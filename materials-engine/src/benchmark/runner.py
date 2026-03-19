"""Benchmark runner — measures prediction accuracy on known corpus materials.

Phase III.H: Reproducible benchmarks by property, element count, value range.
Uses ONLY materials with known values — never invents ground truth.
"""

import json
import logging
import os
import time
import numpy as np
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional, Dict

from ..storage.db import MaterialsDB
from ..novelty.fingerprint import combined_fingerprint

log = logging.getLogger(__name__)

BENCHMARK_DIR = "artifacts/benchmark"

# Bucket definitions
ELEMENT_COUNT_BUCKETS = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 99)]
BG_RANGE_BUCKETS = [(0.0, 0.01), (0.01, 1.0), (1.0, 3.0), (3.0, 6.0), (6.0, 20.0)]
FE_RANGE_BUCKETS = [(-6.0, -3.0), (-3.0, -1.0), (-1.0, 0.0), (0.0, 1.0), (1.0, 5.0)]


def run_benchmark(db: MaterialsDB,
                  target_property: str = "formation_energy",
                  sample_size: int = 500,
                  seed: int = 42,
                  benchmark_name: Optional[str] = None) -> dict:
    """Run a benchmark: predict known materials and measure error.

    Loads materials with known values, predicts using the GNN pipeline,
    and compares predicted vs actual.
    """
    from ..inference.predictor import predict_from_structure
    from ..normalization.structure import load_structure

    if not benchmark_name:
        benchmark_name = f"benchmark_{target_property}"

    t0 = time.time()
    now = datetime.now(timezone.utc).isoformat()
    benchmark_id = f"{benchmark_name}_{seed}"

    # Load materials with known values AND structure
    materials = db.search_training_candidates([target_property], limit=sample_size * 2)

    # Filter to those with structure_data
    with_struct = [m for m in materials if m.structure_data]

    # Sample reproducibly
    rng = np.random.RandomState(seed)
    if len(with_struct) > sample_size:
        indices = rng.choice(len(with_struct), size=sample_size, replace=False)
        sample = [with_struct[i] for i in indices]
    else:
        sample = with_struct

    # Run predictions
    results = []
    errors_by_n_elem = defaultdict(list)
    errors_by_range = defaultdict(list)
    all_errors = []

    for m in sample:
        actual = getattr(m, target_property)
        if actual is None:
            continue

        struct = load_structure(m.structure_data)
        if struct is None:
            continue

        pred_result = predict_from_structure(struct, target_property)
        if "prediction" not in pred_result:
            continue

        predicted = pred_result["prediction"]
        error = abs(predicted - actual)
        all_errors.append(error)

        # Bucket by element count
        n_elem = len(m.elements)
        bucket_n = _bucket_label(n_elem, ELEMENT_COUNT_BUCKETS)
        errors_by_n_elem[bucket_n].append(error)

        # Bucket by value range
        if target_property == "band_gap":
            bucket_v = _bucket_label(actual, BG_RANGE_BUCKETS)
        else:
            bucket_v = _bucket_label(actual, FE_RANGE_BUCKETS)
        errors_by_range[bucket_v].append(error)

        results.append({
            "formula": m.formula,
            "canonical_id": m.canonical_id,
            "actual": round(actual, 4),
            "predicted": round(predicted, 4),
            "error": round(error, 4),
            "n_elements": n_elem,
        })

    elapsed = time.time() - t0

    # Compute statistics
    all_errors_arr = np.array(all_errors) if all_errors else np.array([0.0])

    report = {
        "benchmark_id": benchmark_id,
        "benchmark_name": benchmark_name,
        "target_property": target_property,
        "sample_size": len(results),
        "corpus_with_structure": len(with_struct),
        "seed": seed,
        "elapsed_sec": round(elapsed, 1),
        "created_at": now,
        "overall": {
            "mae": round(float(np.mean(all_errors_arr)), 4),
            "rmse": round(float(np.sqrt(np.mean(all_errors_arr ** 2))), 4),
            "median_error": round(float(np.median(all_errors_arr)), 4),
            "p90_error": round(float(np.percentile(all_errors_arr, 90)), 4),
            "p95_error": round(float(np.percentile(all_errors_arr, 95)), 4),
            "max_error": round(float(np.max(all_errors_arr)), 4),
        },
        "by_element_count": _summarize_buckets(errors_by_n_elem),
        "by_value_range": _summarize_buckets(errors_by_range),
        "sample_results": results[:50],  # first 50 for artifact
    }

    return report


def save_benchmark(report: dict, output_dir: str = BENCHMARK_DIR) -> str:
    os.makedirs(output_dir, exist_ok=True)
    name = report["benchmark_id"]
    path = os.path.join(output_dir, f"{name}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return path


def list_benchmarks(output_dir: str = BENCHMARK_DIR) -> List[dict]:
    if not os.path.exists(output_dir):
        return []
    results = []
    for fname in sorted(os.listdir(output_dir)):
        if fname.startswith("benchmark_") and fname.endswith(".json"):
            try:
                with open(os.path.join(output_dir, fname)) as f:
                    d = json.load(f)
                results.append({
                    "benchmark_id": d.get("benchmark_id"),
                    "target_property": d.get("target_property"),
                    "sample_size": d.get("sample_size"),
                    "mae": d.get("overall", {}).get("mae"),
                    "created_at": d.get("created_at"),
                })
            except Exception:
                continue
    return results


def _bucket_label(value, buckets):
    for low, high in buckets:
        if low <= value < high:
            return f"{low}-{high}"
    return "other"


def _summarize_buckets(bucket_dict):
    summary = {}
    for label, errors in bucket_dict.items():
        arr = np.array(errors)
        summary[label] = {
            "count": len(errors),
            "mae": round(float(np.mean(arr)), 4),
            "median": round(float(np.median(arr)), 4),
            "p90": round(float(np.percentile(arr, 90)), 4),
        }
    return summary

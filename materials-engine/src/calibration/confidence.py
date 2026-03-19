"""Confidence calibration — derive honest confidence from benchmark data.

Phase III.H: Maps prediction contexts (element count, value range) to
empirical error bands derived from actual benchmark results.

NOT statistical probability. Just empirical error-based confidence bands.
"""

import json
import logging
import os
from typing import Optional, Dict, List

log = logging.getLogger(__name__)

CALIBRATION_DIR = "artifacts/calibration"

# Confidence bands
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_UNKNOWN = "unknown"

# Thresholds: MAE below this → high confidence, etc.
DEFAULT_THRESHOLDS = {
    "formation_energy": {"high": 0.3, "medium": 0.6},
    "band_gap": {"high": 0.5, "medium": 1.0},
}


def calibrate_from_benchmark(benchmark_report: dict) -> dict:
    """Derive calibration table from a benchmark report.

    Returns calibration dict with per-bucket confidence bands.
    """
    target = benchmark_report.get("target_property", "")
    thresholds = DEFAULT_THRESHOLDS.get(target, {"high": 0.5, "medium": 1.0})

    overall_mae = benchmark_report.get("overall", {}).get("mae", 999)
    overall_band = _classify_band(overall_mae, thresholds)

    by_elem = {}
    for label, stats in benchmark_report.get("by_element_count", {}).items():
        mae = stats.get("mae", 999)
        by_elem[label] = {
            "mae": mae,
            "count": stats.get("count", 0),
            "confidence_band": _classify_band(mae, thresholds),
            "expected_error": mae,
        }

    by_range = {}
    for label, stats in benchmark_report.get("by_value_range", {}).items():
        mae = stats.get("mae", 999)
        by_range[label] = {
            "mae": mae,
            "count": stats.get("count", 0),
            "confidence_band": _classify_band(mae, thresholds),
            "expected_error": mae,
        }

    calibration = {
        "target_property": target,
        "overall_mae": overall_mae,
        "overall_confidence_band": overall_band,
        "thresholds_used": thresholds,
        "by_element_count": by_elem,
        "by_value_range": by_range,
        "sample_size": benchmark_report.get("sample_size", 0),
        "benchmark_id": benchmark_report.get("benchmark_id"),
        "note": (
            "Confidence bands derived from benchmark MAE on known materials. "
            f"high: MAE < {thresholds['high']}, "
            f"medium: MAE < {thresholds['medium']}, "
            f"low: MAE >= {thresholds['medium']}. "
            "NOT statistical probability — empirical error bands only."
        ),
    }

    return calibration


def get_calibrated_confidence(calibration: dict,
                              n_elements: int = 0,
                              property_value: Optional[float] = None,
                              target_property: str = "") -> dict:
    """Get calibrated confidence for a specific prediction context.

    Returns confidence band, expected error, and rationale.
    """
    if not calibration:
        return {
            "confidence_band": CONFIDENCE_UNKNOWN,
            "expected_error": None,
            "rationale": "No benchmark calibration available.",
        }

    # Find matching bucket
    by_elem = calibration.get("by_element_count", {})
    by_range = calibration.get("by_value_range", {})

    elem_match = None
    for label, stats in by_elem.items():
        parts = label.split("-")
        if len(parts) == 2:
            try:
                low, high = float(parts[0]), float(parts[1])
                if low <= n_elements <= high:
                    elem_match = stats
                    break
            except ValueError:
                continue

    range_match = None
    if property_value is not None:
        for label, stats in by_range.items():
            parts = label.split("-")
            if len(parts) == 2:
                try:
                    low, high = float(parts[0]), float(parts[1])
                    if low <= property_value <= high:
                        range_match = stats
                        break
                except ValueError:
                    continue

    # Combine
    bands = []
    errors = []
    rationale_parts = []

    if elem_match:
        bands.append(elem_match["confidence_band"])
        errors.append(elem_match["expected_error"])
        rationale_parts.append(
            f"Element count bucket: MAE={elem_match['mae']:.3f} "
            f"({elem_match['count']} samples)")

    if range_match:
        bands.append(range_match["confidence_band"])
        errors.append(range_match["expected_error"])
        rationale_parts.append(
            f"Value range bucket: MAE={range_match['mae']:.3f} "
            f"({range_match['count']} samples)")

    if not bands:
        return {
            "confidence_band": calibration.get("overall_confidence_band", CONFIDENCE_UNKNOWN),
            "expected_error": calibration.get("overall_mae"),
            "rationale": "No specific bucket match — using overall calibration.",
        }

    # Use worst (most conservative) band
    band_order = {CONFIDENCE_HIGH: 0, CONFIDENCE_MEDIUM: 1, CONFIDENCE_LOW: 2}
    worst_band = max(bands, key=lambda b: band_order.get(b, 3))
    avg_error = sum(errors) / len(errors)

    return {
        "confidence_band": worst_band,
        "expected_error": round(avg_error, 4),
        "rationale": "; ".join(rationale_parts),
    }


def save_calibration(calibration: dict, output_dir: str = CALIBRATION_DIR) -> str:
    os.makedirs(output_dir, exist_ok=True)
    target = calibration.get("target_property", "unknown")
    path = os.path.join(output_dir, f"calibration_{target}.json")
    with open(path, "w") as f:
        json.dump(calibration, f, indent=2)
    return path


def load_calibration(target_property: str,
                     output_dir: str = CALIBRATION_DIR) -> Optional[dict]:
    path = os.path.join(output_dir, f"calibration_{target_property}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _classify_band(mae: float, thresholds: dict) -> str:
    if mae < thresholds.get("high", 0.3):
        return CONFIDENCE_HIGH
    elif mae < thresholds.get("medium", 0.6):
        return CONFIDENCE_MEDIUM
    else:
        return CONFIDENCE_LOW

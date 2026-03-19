"""Model registry — tracks trained models with metrics and checkpoints.

Simple JSON-based registry for Phase II. Migrate to DB-backed for Phase III.
"""

import json
import os
import logging
from typing import Optional, List

log = logging.getLogger(__name__)

REGISTRY_PATH = "artifacts/training/model_registry.json"


def _load_registry(path: str = REGISTRY_PATH) -> list:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _save_registry(entries: list, path: str = REGISTRY_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(entries, f, indent=2)


def register_model(metrics: dict, path: str = REGISTRY_PATH):
    """Add a trained model to the registry."""
    entries = _load_registry(path)
    entries.append(metrics)
    _save_registry(entries, path)
    log.info("Registered model: %s/%s (MAE=%.4f)",
             metrics.get("model"), metrics.get("target"), metrics.get("test_mae", 0))


def list_models(path: str = REGISTRY_PATH) -> list:
    return _load_registry(path)


def get_best_model(target: str, path: str = REGISTRY_PATH) -> Optional[dict]:
    """Get the model with lowest test_mae for a given target."""
    entries = _load_registry(path)
    candidates = [e for e in entries if e.get("target") == target and "test_mae" in e]
    if not candidates:
        return None
    return min(candidates, key=lambda e: e["test_mae"])

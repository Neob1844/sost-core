"""Training ladder — scaled retraining with reproducible rungs.

Phase IV.A: Systematic evaluation of model quality vs dataset size.
Each rung uses a deterministic sample, fixed seed, and consistent hyperparameters.
"""

import hashlib
import json
import logging
import os
import time
import numpy as np
from datetime import datetime, timezone
from typing import List, Optional, Dict

from ..storage.db import MaterialsDB
from ..normalization.structure import load_structure
from ..features.crystal_graph import structure_to_graph
from .trainer import train_cgcnn, train_alignn, load_dataset

log = logging.getLogger(__name__)

LADDER_DIR = "artifacts/training_ladder"
SEED = 42

RUNGS = [
    {"name": "rung_5k", "size": 5000},
    {"name": "rung_10k", "size": 10000},
    {"name": "rung_20k", "size": 20000},
    {"name": "rung_40k", "size": 40000},
    {"name": "rung_full", "size": 75993},
]


def build_rung_dataset(db: MaterialsDB, target: str, size: int,
                       seed: int = SEED) -> dict:
    """Build a reproducible dataset sample for a training rung.

    Returns dict with train/val/test ids and manifest.
    """
    materials = db.search_training_candidates([target], limit=100000)
    # Filter to those with structure
    valid = [m for m in materials if m.structure_data]

    rng = np.random.RandomState(seed)
    indices = rng.permutation(len(valid))

    actual_size = min(size, len(valid))
    selected = [valid[i] for i in indices[:actual_size]]

    # Deterministic split 80/10/10
    n_train = int(actual_size * 0.8)
    n_val = int(actual_size * 0.1)

    train_ids = [m.canonical_id for m in selected[:n_train]]
    val_ids = [m.canonical_id for m in selected[n_train:n_train + n_val]]
    test_ids = [m.canonical_id for m in selected[n_train + n_val:]]

    # Dataset hash for reproducibility
    id_str = "|".join(sorted(train_ids + val_ids + test_ids))
    dataset_hash = hashlib.sha256(id_str.encode()).hexdigest()[:16]

    manifest = {
        "target": target,
        "requested_size": size,
        "actual_size": actual_size,
        "train_size": len(train_ids),
        "val_size": len(val_ids),
        "test_size": len(test_ids),
        "seed": seed,
        "dataset_hash": dataset_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "manifest": manifest,
        "materials": selected,
        "train": selected[:n_train],
        "val": selected[n_train:n_train + n_val],
        "test": selected[n_train + n_val:],
    }


def run_rung(db: MaterialsDB, target: str, rung_name: str, rung_size: int,
             arch: str = "cgcnn", epochs: int = 30, lr: float = 0.01,
             seed: int = SEED) -> dict:
    """Train a model for one rung and return metrics + manifest."""
    log.info("=== Rung %s: %s %s, %d samples, %d epochs ===",
             rung_name, arch, target, rung_size, epochs)

    rung_dir = os.path.join(LADDER_DIR, rung_name)
    os.makedirs(rung_dir, exist_ok=True)

    # Train using the existing trainer
    if arch == "cgcnn":
        metrics = train_cgcnn(db, target, epochs=epochs, lr=lr, seed=seed,
                              output_dir=rung_dir, limit=rung_size)
    elif arch in ("alignn", "alignn_lite"):
        metrics = train_alignn(db, target, epochs=epochs, lr=lr * 0.5, seed=seed,
                               output_dir=rung_dir, limit=rung_size)
    else:
        return {"error": f"Unknown arch: {arch}"}

    if "error" in metrics:
        return metrics

    # Save manifest
    manifest = {
        "rung_name": rung_name,
        "target": target,
        "architecture": arch,
        "dataset_size": metrics.get("dataset_size", rung_size),
        "train_size": metrics.get("train_size"),
        "val_size": metrics.get("val_size"),
        "test_size": metrics.get("test_size"),
        "epochs": metrics.get("epochs"),
        "best_epoch": metrics.get("best_epoch"),
        "seed": seed,
        "test_mae": metrics.get("test_mae"),
        "test_rmse": metrics.get("test_rmse"),
        "test_r2": metrics.get("test_r2"),
        "training_time_sec": metrics.get("training_time_sec"),
        "checkpoint": metrics.get("checkpoint"),
        "created_at": metrics.get("created_at"),
    }

    manifest_path = os.path.join(rung_dir, f"{arch}_{target}_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    log.info("Rung %s complete: MAE=%.4f RMSE=%.4f R²=%.4f (%.0fs)",
             rung_name, metrics["test_mae"], metrics["test_rmse"],
             metrics["test_r2"], metrics["training_time_sec"])

    return manifest


def run_full_ladder(db: MaterialsDB, target: str = "formation_energy",
                    arch: str = "cgcnn", epochs: int = 30,
                    rungs: Optional[List[dict]] = None) -> dict:
    """Execute the full training ladder."""
    if rungs is None:
        rungs = RUNGS

    results = []
    for rung in rungs:
        manifest = run_rung(db, target, rung["name"], rung["size"],
                            arch=arch, epochs=epochs)
        results.append(manifest)

    # Build comparison table
    comparison = []
    for r in results:
        if "error" not in r:
            comparison.append({
                "rung": r["rung_name"],
                "dataset_size": r["dataset_size"],
                "architecture": r["architecture"],
                "test_mae": r["test_mae"],
                "test_rmse": r["test_rmse"],
                "test_r2": r["test_r2"],
                "time_sec": r["training_time_sec"],
            })

    return {
        "target": target,
        "architecture": arch,
        "rungs": results,
        "comparison": comparison,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def ladder_status() -> dict:
    """List completed training rungs."""
    if not os.path.exists(LADDER_DIR):
        return {"rungs": []}
    rungs = []
    for d in sorted(os.listdir(LADDER_DIR)):
        rung_dir = os.path.join(LADDER_DIR, d)
        if not os.path.isdir(rung_dir):
            continue
        # Find manifests
        for f in os.listdir(rung_dir):
            if f.endswith("_manifest.json"):
                with open(os.path.join(rung_dir, f)) as fh:
                    m = json.load(fh)
                rungs.append({
                    "rung": m.get("rung_name"),
                    "arch": m.get("architecture"),
                    "target": m.get("target"),
                    "dataset_size": m.get("dataset_size"),
                    "mae": m.get("test_mae"),
                    "r2": m.get("test_r2"),
                    "time": m.get("training_time_sec"),
                })
    return {"rungs": rungs}

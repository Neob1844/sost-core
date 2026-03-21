"""Non-metal regressor tuning — train improved regressors for the hierarchical pipeline.

Phase IV.P: The gate is good (90.8%), routing is calibrated. The single
remaining blocker is the non-metal regressor MAE=0.76. This module trains
challengers with more epochs and lower learning rates on the non-metal subset.
"""

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import List, Dict, Tuple

import numpy as np

from ..storage.db import MaterialsDB
from ..training.trainer import train_alignn, train_cgcnn
from .spec import METAL_THRESHOLD

log = logging.getLogger(__name__)

ARTIFACT_DIR = "artifacts/hierarchical_band_gap_regressor"

# Challenger configurations
CHALLENGERS = {
    "nonmetal_longer_train": {
        "arch": "alignn_lite", "epochs": 25, "lr": 0.005,
        "description": "Same arch, 25 epochs (was 15)",
    },
    "nonmetal_lower_lr": {
        "arch": "alignn_lite", "epochs": 20, "lr": 0.002,
        "description": "Same arch, lr=0.002 (was 0.005)",
    },
    "nonmetal_longer_lower_lr": {
        "arch": "alignn_lite", "epochs": 30, "lr": 0.002,
        "description": "30 epochs + lr=0.002 — maximum effort",
    },
}


def _create_nonmetal_db(source_db: MaterialsDB, limit: int = 22000,
                        seed: int = 42) -> str:
    """Create temp DB with only non-metal materials (BG >= threshold)."""
    src_conn = sqlite3.connect(source_db.db_path)
    src_conn.row_factory = sqlite3.Row
    cursor = src_conn.cursor()
    cursor.execute("PRAGMA table_info(materials)")
    columns = [row[1] for row in cursor.fetchall()]
    col_list = ", ".join(columns)

    cursor.execute(f"SELECT {col_list} FROM materials WHERE band_gap >= {METAL_THRESHOLD} "
                   f"ORDER BY canonical_id LIMIT {limit}")
    rows = cursor.fetchall()
    src_conn.close()

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    temp_db = MaterialsDB(tmp.name)
    dst_conn = sqlite3.connect(tmp.name)
    dst_c = dst_conn.cursor()
    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f"INSERT OR REPLACE INTO materials ({col_list}) VALUES ({placeholders})"
    for row in rows:
        dst_c.execute(insert_sql, list(row))
    dst_conn.commit()
    dst_conn.close()

    log.info("Non-metal DB: %d materials (BG >= %.2f)", len(rows), METAL_THRESHOLD)
    return tmp.name


def train_nonmetal_challenger(source_db: MaterialsDB, name: str,
                              seed: int = 42) -> dict:
    """Train a single non-metal regressor challenger."""
    if name not in CHALLENGERS:
        raise ValueError(f"Unknown challenger: {name}")

    cfg = CHALLENGERS[name]
    now = datetime.now(timezone.utc).isoformat()
    cid = hashlib.sha256(f"nmreg|{name}|{now}".encode()).hexdigest()[:12]
    output_dir = os.path.join(ARTIFACT_DIR, f"challenger_{name}")
    os.makedirs(output_dir, exist_ok=True)

    tmp_path = _create_nonmetal_db(source_db, limit=22000, seed=seed)
    try:
        tmp_db = MaterialsDB(tmp_path)
        db_count = tmp_db.count()
        log.info("Training challenger '%s': %d non-metals, %d epochs, lr=%.4f",
                 name, db_count, cfg["epochs"], cfg["lr"])

        if cfg["arch"] == "cgcnn":
            metrics = train_cgcnn(tmp_db, target="band_gap", epochs=cfg["epochs"],
                                  lr=cfg["lr"], seed=seed, output_dir=output_dir,
                                  limit=22000)
        else:
            metrics = train_alignn(tmp_db, target="band_gap", epochs=cfg["epochs"],
                                   lr=cfg["lr"], seed=seed, output_dir=output_dir,
                                   limit=22000)

        if "error" in metrics:
            log.warning("Challenger '%s' failed: %s", name, metrics["error"])
            return {"name": name, "error": metrics["error"]}

        # Compute per-bucket MAE from predictions
        bucket_mae = _compute_bucket_mae(output_dir, cfg["arch"])

        result = {
            "challenger_id": cid,
            "name": name,
            "architecture": cfg["arch"],
            "description": cfg["description"],
            "epochs": cfg["epochs"],
            "lr": cfg["lr"],
            "dataset_size": metrics["dataset_size"],
            "train_size": metrics["train_size"],
            "val_size": metrics["val_size"],
            "test_size": metrics["test_size"],
            "best_epoch": metrics["best_epoch"],
            "test_mae": metrics["test_mae"],
            "test_rmse": metrics["test_rmse"],
            "test_r2": metrics["test_r2"],
            "bucket_mae": bucket_mae,
            "training_time_sec": metrics["training_time_sec"],
            "checkpoint": os.path.join(output_dir, metrics["checkpoint"]),
            "created_at": now,
        }

        with open(os.path.join(output_dir, "result.json"), "w") as f:
            json.dump(result, f, indent=2)

        md = f"# Challenger: {name}\n\n"
        md += f"- Arch: {cfg['arch']}, epochs={cfg['epochs']}, lr={cfg['lr']}\n"
        md += f"- Dataset: {metrics['dataset_size']:,} non-metals\n"
        md += f"- MAE: {metrics['test_mae']:.4f} | RMSE: {metrics['test_rmse']:.4f} | R²: {metrics['test_r2']:.4f}\n"
        md += f"- Best epoch: {metrics['best_epoch']} | Time: {metrics['training_time_sec']:.1f}s\n"
        if bucket_mae:
            md += "\n## Bucket MAE\n"
            for k, v in sorted(bucket_mae.items()):
                md += f"- {k}: {v:.4f}\n"
        with open(os.path.join(output_dir, "result.md"), "w") as f:
            f.write(md)

        log.info("  → MAE=%.4f RMSE=%.4f R²=%.4f (%.1fs)",
                 metrics["test_mae"], metrics["test_rmse"],
                 metrics["test_r2"], metrics["training_time_sec"])
        return result
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _compute_bucket_mae(output_dir: str, arch: str) -> dict:
    """Extract per-bucket MAE from predictions file."""
    prefix = "cgcnn" if arch == "cgcnn" else "alignn"
    pred_path = os.path.join(output_dir, f"{prefix}_band_gap_predictions.json")
    if not os.path.exists(pred_path):
        return {}
    with open(pred_path) as f:
        preds = json.load(f)
    buckets = {"0.05-1.0": [], "1.0-3.0": [], "3.0-6.0": [], "6.0+": []}
    for p in preds:
        actual = p["target"]
        error = abs(p["predicted"] - actual)
        if actual < 1.0:
            buckets["0.05-1.0"].append(error)
        elif actual < 3.0:
            buckets["1.0-3.0"].append(error)
        elif actual < 6.0:
            buckets["3.0-6.0"].append(error)
        else:
            buckets["6.0+"].append(error)
    result = {}
    for k, errs in buckets.items():
        if errs:
            result[k] = round(float(np.mean(errs)), 4)
    return result


def train_all_challengers(source_db: MaterialsDB,
                          seed: int = 42) -> List[dict]:
    """Train all non-metal regressor challengers."""
    results = []
    for name in CHALLENGERS:
        log.info("=== Non-metal challenger: %s ===", name)
        r = train_nonmetal_challenger(source_db, name, seed=seed)
        results.append(r)
    return results

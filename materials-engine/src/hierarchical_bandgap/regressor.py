"""Non-metal band_gap regressor — trains only on materials with BG >= threshold.

Phase IV.N: By excluding metals, the regressor focuses on the harder
prediction problem (semiconductors + insulators) without noise from BG≈0.
"""

import json
import logging
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone

import numpy as np
import torch
import torch.nn as nn

from ..storage.db import MaterialsDB
from ..training.trainer import train_alignn
from .spec import NonMetalRegressorResult, METAL_THRESHOLD

log = logging.getLogger(__name__)


def train_nonmetal_regressor(db: MaterialsDB, epochs: int = 15, lr: float = 0.005,
                             seed: int = 42, limit: int = 20000,
                             output_dir: str = "artifacts/hierarchical_band_gap") -> NonMetalRegressorResult:
    """Train ALIGNN-Lite regressor on non-metal materials only."""
    os.makedirs(output_dir, exist_ok=True)

    # Create temp DB with only non-metal materials
    src_conn = sqlite3.connect(db.db_path)
    src_conn.row_factory = sqlite3.Row
    cursor = src_conn.cursor()
    cursor.execute("PRAGMA table_info(materials)")
    columns = [row[1] for row in cursor.fetchall()]
    col_list = ", ".join(columns)

    cursor.execute(f"SELECT {col_list} FROM materials WHERE band_gap >= {METAL_THRESHOLD} ORDER BY canonical_id LIMIT {limit}")
    rows = cursor.fetchall()
    src_conn.close()

    if len(rows) < 10:
        return NonMetalRegressorResult(architecture="alignn_lite_nonmetal")

    # Write to temp DB
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

    log.info("Non-metal regressor: %d materials (BG >= %.2f eV)", len(rows), METAL_THRESHOLD)

    try:
        metrics = train_alignn(
            temp_db, target="band_gap", epochs=epochs,
            lr=lr, seed=seed, output_dir=output_dir,
            limit=limit)

        if "error" in metrics:
            return NonMetalRegressorResult(architecture="alignn_lite_nonmetal")

        # Compute per-bucket MAE from predictions file
        bucket_mae = {}
        pred_path = os.path.join(output_dir, "alignn_band_gap_predictions.json")
        if os.path.exists(pred_path):
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
            for k, errs in buckets.items():
                if errs:
                    bucket_mae[k] = round(float(np.mean(errs)), 4)

        result = NonMetalRegressorResult(
            architecture="alignn_lite_nonmetal",
            dataset_size=metrics["dataset_size"],
            train_size=metrics["train_size"],
            test_size=metrics["test_size"],
            test_mae=metrics["test_mae"],
            test_rmse=metrics["test_rmse"],
            test_r2=metrics["test_r2"],
            bucket_mae=bucket_mae,
            training_time_sec=metrics["training_time_sec"],
            checkpoint=os.path.join(output_dir, metrics["checkpoint"]),
            created_at=datetime.now(timezone.utc).isoformat())

        with open(os.path.join(output_dir, "nonmetal_regressor.json"), "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        log.info("Non-metal regressor: MAE=%.4f RMSE=%.4f R²=%.4f",
                 result.test_mae, result.test_rmse, result.test_r2)
        return result
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

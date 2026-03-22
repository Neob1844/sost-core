"""Narrow-gap specialist — dedicated regressor for 0.05-1.0 eV band gap.

Phase IV.R: The 2-tier pipeline's single blocker is narrow-gap regression.
This module trains a specialist ALIGNN-Lite only on the 7,632 narrow-gap
materials to give them dedicated attention.
"""

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import numpy as np

from ..storage.db import MaterialsDB
from ..training.trainer import train_alignn
from .spec import METAL_THRESHOLD

log = logging.getLogger(__name__)

NARROW_LOW = 0.05   # eV
NARROW_HIGH = 1.0   # eV
ARTIFACT_DIR = "artifacts/three_tier_band_gap"


def _create_narrow_gap_db(source_db: MaterialsDB, limit: int = 8000, seed: int = 42) -> str:
    """Create temp DB with only narrow-gap materials (0.05 <= BG < 1.0)."""
    src_conn = sqlite3.connect(source_db.db_path)
    src_conn.row_factory = sqlite3.Row
    cursor = src_conn.cursor()
    cursor.execute("PRAGMA table_info(materials)")
    columns = [row[1] for row in cursor.fetchall()]
    col_list = ", ".join(columns)
    cursor.execute(f"SELECT {col_list} FROM materials WHERE band_gap >= {NARROW_LOW} AND band_gap < {NARROW_HIGH} ORDER BY canonical_id LIMIT {limit}")
    rows = cursor.fetchall()
    src_conn.close()

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    MaterialsDB(tmp.name)  # ensure schema
    dst_conn = sqlite3.connect(tmp.name)
    dst_c = dst_conn.cursor()
    placeholders = ", ".join(["?"] * len(columns))
    for row in rows:
        dst_c.execute(f"INSERT OR REPLACE INTO materials ({col_list}) VALUES ({placeholders})", list(row))
    dst_conn.commit()
    dst_conn.close()
    log.info("Narrow-gap DB: %d materials (%.2f-%.2f eV)", len(rows), NARROW_LOW, NARROW_HIGH)
    return tmp.name


def train_narrow_gap_specialist(source_db: MaterialsDB, epochs: int = 20,
                                 lr: float = 0.002, seed: int = 42) -> dict:
    """Train ALIGNN-Lite specialist on narrow-gap materials only."""
    now = datetime.now(timezone.utc).isoformat()
    cid = hashlib.sha256(f"narrow|{now}".encode()).hexdigest()[:12]
    output_dir = os.path.join(ARTIFACT_DIR, "narrow_gap_specialist")
    os.makedirs(output_dir, exist_ok=True)

    tmp_path = _create_narrow_gap_db(source_db, limit=8000, seed=seed)
    try:
        tmp_db = MaterialsDB(tmp_path)
        db_count = tmp_db.count()
        log.info("Training narrow-gap specialist: %d materials, %d epochs, lr=%.4f",
                 db_count, epochs, lr)

        metrics = train_alignn(tmp_db, target="band_gap", epochs=epochs,
                               lr=lr, seed=seed, output_dir=output_dir, limit=8000)

        if "error" in metrics:
            return {"name": "narrow_gap_specialist", "error": metrics["error"]}

        # Per-sub-bucket MAE
        bucket_mae = {}
        pred_path = os.path.join(output_dir, "alignn_band_gap_predictions.json")
        if os.path.exists(pred_path):
            with open(pred_path) as f:
                preds = json.load(f)
            sub_buckets = {"0.05-0.3": [], "0.3-0.6": [], "0.6-1.0": []}
            for p in preds:
                actual = p["target"]
                error = abs(p["predicted"] - actual)
                if actual < 0.3:
                    sub_buckets["0.05-0.3"].append(error)
                elif actual < 0.6:
                    sub_buckets["0.3-0.6"].append(error)
                else:
                    sub_buckets["0.6-1.0"].append(error)
            for k, errs in sub_buckets.items():
                if errs:
                    bucket_mae[k] = round(float(np.mean(errs)), 4)

        result = {
            "challenger_id": cid, "name": "narrow_gap_specialist",
            "architecture": "alignn_lite", "range": f"{NARROW_LOW}-{NARROW_HIGH} eV",
            "dataset_size": metrics["dataset_size"],
            "train_size": metrics["train_size"], "test_size": metrics["test_size"],
            "best_epoch": metrics["best_epoch"], "epochs": epochs, "lr": lr,
            "test_mae": metrics["test_mae"], "test_rmse": metrics["test_rmse"],
            "test_r2": metrics["test_r2"], "sub_bucket_mae": bucket_mae,
            "training_time_sec": metrics["training_time_sec"],
            "checkpoint": os.path.join(output_dir, metrics["checkpoint"]),
            "created_at": now,
        }

        with open(os.path.join(ARTIFACT_DIR, "narrow_gap_specialist.json"), "w") as f:
            json.dump(result, f, indent=2)
        md = f"# Narrow-Gap Specialist\n\n- Range: {NARROW_LOW}-{NARROW_HIGH} eV\n"
        md += f"- Dataset: {metrics['dataset_size']:,} materials\n"
        md += f"- MAE: {metrics['test_mae']:.4f} | RMSE: {metrics['test_rmse']:.4f} | R²: {metrics['test_r2']:.4f}\n"
        md += f"- Epochs: {epochs}, LR: {lr}, Best epoch: {metrics['best_epoch']}\n"
        if bucket_mae:
            md += "\n## Sub-Bucket MAE\n"
            for k, v in sorted(bucket_mae.items()):
                md += f"- {k}: {v:.4f}\n"
        with open(os.path.join(ARTIFACT_DIR, "narrow_gap_specialist.md"), "w") as f:
            f.write(md)

        log.info("Narrow-gap specialist: MAE=%.4f RMSE=%.4f R²=%.4f",
                 metrics["test_mae"], metrics["test_rmse"], metrics["test_r2"])
        return result
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

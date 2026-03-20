"""Selective retraining — train challengers on filtered datasets.

Phase IV.L: Creates temporary DBs with filtered material subsets,
trains ALIGNN-Lite challengers, returns comparable metrics.
"""

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import List, Dict, Optional

from ..storage.db import MaterialsDB
from ..training.trainer import train_alignn
from .spec import ChallengerResult

log = logging.getLogger(__name__)

ARTIFACT_DIR = "artifacts/selective_retraining_band_gap"

# Challenger dataset definitions: name → SQL WHERE condition
CHALLENGER_DATASETS = {
    "bg_hotspots_10k": {
        "sql": "band_gap IS NOT NULL AND band_gap >= 1.0 AND band_gap < 6.0",
        "description": "Materials in hard calibration buckets (1-6 eV BG)",
        "limit": 10000,
    },
    "bg_sparse_exotic_10k": {
        "sql": "band_gap IS NOT NULL AND n_elements >= 4",
        "description": "Complex materials (4+ elements) with band_gap",
        "limit": 10000,
    },
    "bg_balanced_hardmix_20k": {
        "sql": """band_gap IS NOT NULL AND (
            (band_gap >= 1.0 AND band_gap < 6.0)
            OR n_elements >= 4
            OR spacegroup IN (SELECT spacegroup FROM materials GROUP BY spacegroup HAVING COUNT(*) < 50)
        )""",
        "description": "Union of hard BG ranges + complex compositions + rare SGs",
        "limit": 20000,
    },
}


def _create_filtered_db(source_db: MaterialsDB, sql_where: str,
                        limit: int, seed: int = 42) -> str:
    """Create a temporary DB with materials matching the SQL filter.

    Returns path to temp DB file.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    # Copy matching materials from source to temp
    src_conn = sqlite3.connect(source_db.db_path)
    src_conn.row_factory = sqlite3.Row
    cursor = src_conn.cursor()

    # Get column names from source
    cursor.execute("PRAGMA table_info(materials)")
    columns = [row[1] for row in cursor.fetchall()]
    col_list = ", ".join(columns)

    # Fetch matching materials
    query = f"SELECT {col_list} FROM materials WHERE {sql_where} ORDER BY canonical_id LIMIT {limit}"
    cursor.execute(query)
    rows = cursor.fetchall()
    src_conn.close()

    if not rows:
        os.unlink(tmp.name)
        return None

    # Create temp DB with same schema
    temp_db = MaterialsDB(tmp.name)
    dst_conn = sqlite3.connect(tmp.name)
    dst_cursor = dst_conn.cursor()

    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f"INSERT OR REPLACE INTO materials ({col_list}) VALUES ({placeholders})"

    for row in rows:
        dst_cursor.execute(insert_sql, list(row))
    dst_conn.commit()
    dst_conn.close()

    log.info("Created filtered DB: %d materials matching '%s'", len(rows), sql_where[:80])
    return tmp.name


def train_challenger(source_db: MaterialsDB, dataset_name: str,
                     epochs: int = 15, seed: int = 42) -> ChallengerResult:
    """Train a single challenger on a filtered dataset.

    Creates temp DB → trains ALIGNN-Lite → returns ChallengerResult.
    """
    if dataset_name not in CHALLENGER_DATASETS:
        raise ValueError(f"Unknown dataset: {dataset_name}")

    ds = CHALLENGER_DATASETS[dataset_name]
    now = datetime.now(timezone.utc).isoformat()
    challenger_id = hashlib.sha256(f"challenger|{dataset_name}|{now}".encode()).hexdigest()[:12]

    output_dir = os.path.join(ARTIFACT_DIR, f"challenger_{dataset_name}")
    os.makedirs(output_dir, exist_ok=True)

    # Create filtered temp DB
    tmp_path = _create_filtered_db(source_db, ds["sql"], ds["limit"], seed)
    if tmp_path is None:
        return ChallengerResult(
            challenger_id=challenger_id, name=dataset_name,
            target="band_gap", dataset_name=dataset_name,
            dataset_sql=ds["sql"], created_at=now)

    try:
        tmp_db = MaterialsDB(tmp_path)
        db_count = tmp_db.count()
        log.info("Training challenger '%s': %d materials, %d epochs",
                 dataset_name, db_count, epochs)

        # Train ALIGNN-Lite on filtered dataset
        metrics = train_alignn(
            tmp_db, target="band_gap", epochs=epochs,
            lr=0.005, seed=seed, output_dir=output_dir,
            limit=ds["limit"])

        if "error" in metrics:
            log.warning("Challenger '%s' training failed: %s", dataset_name, metrics["error"])
            return ChallengerResult(
                challenger_id=challenger_id, name=dataset_name,
                target="band_gap", dataset_name=dataset_name,
                dataset_sql=ds["sql"], created_at=now)

        result = ChallengerResult(
            challenger_id=challenger_id,
            name=dataset_name,
            target="band_gap",
            architecture="alignn_lite",
            dataset_name=dataset_name,
            dataset_sql=ds["sql"],
            dataset_size=metrics["dataset_size"],
            train_size=metrics["train_size"],
            val_size=metrics["val_size"],
            test_size=metrics["test_size"],
            epochs=metrics["epochs"],
            best_epoch=metrics["best_epoch"],
            seed=seed,
            test_mae=metrics["test_mae"],
            test_rmse=metrics["test_rmse"],
            test_r2=metrics["test_r2"],
            training_time_sec=metrics["training_time_sec"],
            checkpoint=os.path.join(output_dir, metrics["checkpoint"]),
            created_at=now,
        )

        # Save challenger result
        with open(os.path.join(output_dir, "challenger_result.json"), "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        return result
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def train_all_challengers(source_db: MaterialsDB, epochs: int = 15,
                          seed: int = 42) -> List[ChallengerResult]:
    """Train all defined challengers. Returns list of ChallengerResult."""
    results = []
    for name in CHALLENGER_DATASETS:
        log.info("=== Training challenger: %s ===", name)
        result = train_challenger(source_db, name, epochs=epochs, seed=seed)
        results.append(result)
        log.info("  → MAE=%.4f RMSE=%.4f R²=%.4f (%.1fs)",
                 result.test_mae, result.test_rmse, result.test_r2,
                 result.training_time_sec)
    return results

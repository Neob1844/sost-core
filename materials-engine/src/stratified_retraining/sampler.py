"""Stratified and curriculum dataset builders.

Phase IV.M: Builds mixed datasets that preserve global distribution
while overweighting hard cases. Fixes the pure-subset failure from IV.L.
"""

import json
import logging
import sqlite3
import tempfile
import os
from typing import Dict, List, Tuple

import numpy as np

from ..storage.db import MaterialsDB
from .spec import StratifiedSample

log = logging.getLogger(__name__)

# --- Stratum definitions ---
STRATA_SQL = {
    "random_representative": "band_gap IS NOT NULL",
    "hard_wide_gap": "band_gap IS NOT NULL AND band_gap >= 1.0 AND band_gap < 6.0",
    "sparse_exotic": "band_gap IS NOT NULL AND n_elements >= 4",
    "rare_sg": "band_gap IS NOT NULL AND spacegroup IN (SELECT spacegroup FROM materials GROUP BY spacegroup HAVING COUNT(*) < 50)",
    "metals": "band_gap IS NOT NULL AND band_gap < 0.01",
    "narrow_gap": "band_gap IS NOT NULL AND band_gap >= 0.01 AND band_gap < 1.0",
}

# --- Dataset recipes ---
RECIPES = {
    "bg_stratified_20k": {
        "total": 20000,
        "strata": {
            "random_representative": 10000,  # 50%
            "hard_wide_gap": 6000,            # 30%
            "sparse_exotic": 4000,            # 20%
        },
    },
    "bg_curriculum_20k": {
        "total": 20000,
        "strata": {
            "random_representative": 20000,   # full random for phase 1
        },
        "curriculum_finetune": {
            "hard_wide_gap": 5000,
            "sparse_exotic": 2000,
        },
    },
    "bg_stratified_balanced_30k": {
        "total": 30000,
        "strata": {
            "random_representative": 12000,  # 40%
            "hard_wide_gap": 7000,           # 23%
            "sparse_exotic": 5000,           # 17%
            "rare_sg": 3000,                 # 10%
            "metals": 2000,                  # 7%
            "narrow_gap": 1000,              # 3%
        },
    },
}


def _fetch_stratum(db_path: str, sql_where: str, limit: int,
                   seed: int = 42) -> List[dict]:
    """Fetch materials for one stratum."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("PRAGMA table_info(materials)")
    columns = [row[1] for row in c.fetchall()]
    col_list = ", ".join(columns)

    query = f"SELECT {col_list} FROM materials WHERE {sql_where} ORDER BY canonical_id"
    c.execute(query)
    rows = c.fetchall()
    conn.close()

    if not rows:
        return []

    rng = np.random.RandomState(seed)
    if len(rows) > limit:
        indices = rng.choice(len(rows), size=limit, replace=False)
        indices.sort()
        rows = [rows[i] for i in indices]

    return [dict(r) for r in rows]


def build_stratified_db(source_db: MaterialsDB, recipe_name: str,
                        seed: int = 42) -> Tuple[str, StratifiedSample]:
    """Build a temp DB with stratified sampling.

    Returns (temp_db_path, StratifiedSample).
    Deduplicates across strata by canonical_id.
    """
    if recipe_name not in RECIPES:
        raise ValueError(f"Unknown recipe: {recipe_name}")

    recipe = RECIPES[recipe_name]
    strata_def = recipe["strata"]

    # Fetch each stratum
    all_rows = {}  # canonical_id → row dict (dedup)
    actual_counts = {}

    for stratum_name, target_count in strata_def.items():
        sql = STRATA_SQL.get(stratum_name, "band_gap IS NOT NULL")
        rows = _fetch_stratum(source_db.db_path, sql, target_count * 2, seed)

        # Deterministic shuffle then take up to target_count, skipping dupes
        rng = np.random.RandomState(seed + hash(stratum_name) % 10000)
        rng.shuffle(rows)

        added = 0
        for r in rows:
            cid = r.get("canonical_id", "")
            if cid not in all_rows and added < target_count:
                all_rows[cid] = r
                added += 1
        actual_counts[stratum_name] = added
        log.info("Stratum '%s': requested %d, got %d",
                 stratum_name, target_count, added)

    # Cap to recipe total
    total_target = recipe["total"]
    if len(all_rows) > total_target:
        rng = np.random.RandomState(seed)
        keys = list(all_rows.keys())
        rng.shuffle(keys)
        all_rows = {k: all_rows[k] for k in keys[:total_target]}

    # Write to temp DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    temp_db = MaterialsDB(tmp.name)

    dst_conn = sqlite3.connect(tmp.name)
    dst_c = dst_conn.cursor()

    if all_rows:
        sample_row = next(iter(all_rows.values()))
        columns = list(sample_row.keys())
        col_list = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f"INSERT OR REPLACE INTO materials ({col_list}) VALUES ({placeholders})"

        for row in all_rows.values():
            dst_c.execute(insert_sql, [row.get(c) for c in columns])
        dst_conn.commit()
    dst_conn.close()

    sample = StratifiedSample(
        name=recipe_name,
        total_size=len(all_rows),
        strata={k: v for k, v in strata_def.items()},
        strata_sql={k: STRATA_SQL.get(k, "") for k in strata_def},
        actual_counts=actual_counts,
    )

    log.info("Built stratified DB '%s': %d total materials", recipe_name, len(all_rows))
    return tmp.name, sample


def build_curriculum_db(source_db: MaterialsDB, recipe_name: str = "bg_curriculum_20k",
                        seed: int = 42) -> Tuple[str, str, StratifiedSample]:
    """Build two temp DBs for curriculum learning: phase1 (representative) + phase2 (hard finetune).

    Returns (phase1_db_path, phase2_db_path, StratifiedSample).
    """
    recipe = RECIPES[recipe_name]
    finetune = recipe.get("curriculum_finetune", {})

    # Phase 1: representative
    p1_path, sample = build_stratified_db(source_db, recipe_name, seed)

    # Phase 2: hard/exotic subset for fine-tuning
    all_rows = {}
    ft_counts = {}
    for stratum_name, target_count in finetune.items():
        sql = STRATA_SQL.get(stratum_name, "band_gap IS NOT NULL")
        rows = _fetch_stratum(source_db.db_path, sql, target_count * 2, seed + 1)
        rng = np.random.RandomState(seed + 1 + hash(stratum_name) % 10000)
        rng.shuffle(rows)
        added = 0
        for r in rows:
            cid = r.get("canonical_id", "")
            if cid not in all_rows and added < target_count:
                all_rows[cid] = r
                added += 1
        ft_counts[stratum_name] = added

    # Write phase 2 DB
    tmp2 = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp2.close()
    temp_db2 = MaterialsDB(tmp2.name)

    if all_rows:
        dst_conn = sqlite3.connect(tmp2.name)
        dst_c = dst_conn.cursor()
        sample_row = next(iter(all_rows.values()))
        columns = list(sample_row.keys())
        col_list = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f"INSERT OR REPLACE INTO materials ({col_list}) VALUES ({placeholders})"
        for row in all_rows.values():
            dst_c.execute(insert_sql, [row.get(c) for c in columns])
        dst_conn.commit()
        dst_conn.close()

    sample.strata_sql.update({f"finetune_{k}": STRATA_SQL.get(k, "") for k in finetune})
    sample.actual_counts.update({f"finetune_{k}": v for k, v in ft_counts.items()})

    log.info("Built curriculum DBs: phase1=%d, phase2=%d",
             sample.total_size, len(all_rows))
    return p1_path, tmp2.name, sample

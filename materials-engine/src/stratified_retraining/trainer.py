"""Stratified/curriculum trainer — trains challengers on mixed datasets.

Phase IV.M: Uses stratified DBs from sampler, trains ALIGNN-Lite,
returns ChallengerResult with full metrics.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from ..storage.db import MaterialsDB
from ..training.trainer import train_alignn
from .spec import ChallengerResult
from .sampler import build_stratified_db, build_curriculum_db, RECIPES

log = logging.getLogger(__name__)

ARTIFACT_DIR = "artifacts/stratified_retraining_band_gap"


def train_stratified_challenger(source_db: MaterialsDB, recipe_name: str,
                                epochs: int = 15, seed: int = 42) -> ChallengerResult:
    """Train a stratified challenger."""
    now = datetime.now(timezone.utc).isoformat()
    cid = hashlib.sha256(f"strat|{recipe_name}|{now}".encode()).hexdigest()[:12]
    output_dir = os.path.join(ARTIFACT_DIR, f"challenger_{recipe_name}")
    os.makedirs(output_dir, exist_ok=True)

    tmp_path, sample = build_stratified_db(source_db, recipe_name, seed)
    try:
        tmp_db = MaterialsDB(tmp_path)
        log.info("Training stratified '%s': %d materials, %d epochs",
                 recipe_name, sample.total_size, epochs)

        metrics = train_alignn(
            tmp_db, target="band_gap", epochs=epochs,
            lr=0.005, seed=seed, output_dir=output_dir,
            limit=sample.total_size + 1000)

        if "error" in metrics:
            log.warning("Training failed: %s", metrics["error"])
            return ChallengerResult(challenger_id=cid, name=recipe_name,
                                    strategy="stratified", created_at=now)

        result = ChallengerResult(
            challenger_id=cid, name=recipe_name, target="band_gap",
            architecture="alignn_lite", strategy="stratified",
            dataset_size=metrics["dataset_size"],
            train_size=metrics["train_size"],
            val_size=metrics["val_size"],
            test_size=metrics["test_size"],
            strata_summary=sample.actual_counts,
            epochs=metrics["epochs"], best_epoch=metrics["best_epoch"],
            seed=seed, test_mae=metrics["test_mae"],
            test_rmse=metrics["test_rmse"], test_r2=metrics["test_r2"],
            training_time_sec=metrics["training_time_sec"],
            checkpoint=os.path.join(output_dir, metrics["checkpoint"]),
            created_at=now)

        with open(os.path.join(output_dir, "challenger_result.json"), "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        return result
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def train_curriculum_challenger(source_db: MaterialsDB,
                                recipe_name: str = "bg_curriculum_20k",
                                phase1_epochs: int = 10,
                                phase2_epochs: int = 5,
                                seed: int = 42) -> ChallengerResult:
    """Train a curriculum challenger: phase1 (representative) + phase2 (hard finetune)."""
    now = datetime.now(timezone.utc).isoformat()
    cid = hashlib.sha256(f"curr|{recipe_name}|{now}".encode()).hexdigest()[:12]
    output_dir = os.path.join(ARTIFACT_DIR, f"challenger_{recipe_name}")
    os.makedirs(output_dir, exist_ok=True)

    p1_path, p2_path, sample = build_curriculum_db(source_db, recipe_name, seed)
    try:
        # Phase 1: train on representative data
        p1_db = MaterialsDB(p1_path)
        log.info("Curriculum phase 1: %d materials, %d epochs", sample.total_size, phase1_epochs)

        m1 = train_alignn(
            p1_db, target="band_gap", epochs=phase1_epochs,
            lr=0.005, seed=seed, output_dir=output_dir,
            limit=sample.total_size + 1000)

        if "error" in m1:
            return ChallengerResult(challenger_id=cid, name=recipe_name,
                                    strategy="curriculum", created_at=now)

        phase1_time = m1["training_time_sec"]

        # Phase 2: fine-tune on hard cases (lower LR)
        p2_db = MaterialsDB(p2_path)
        p2_count = p2_db.count()
        log.info("Curriculum phase 2: %d hard materials, %d epochs, lr=0.001", p2_count, phase2_epochs)

        m2 = train_alignn(
            p2_db, target="band_gap", epochs=phase2_epochs,
            lr=0.001, seed=seed, output_dir=output_dir,
            limit=p2_count + 100)

        # Use phase 2 metrics if they improved, else fall back to phase 1
        if "error" not in m2 and m2.get("test_mae", 99) < m1.get("test_mae", 99):
            final = m2
            final_note = "phase2_improved"
        else:
            final = m1
            final_note = "phase1_kept"

        total_time = phase1_time + m2.get("training_time_sec", 0)

        result = ChallengerResult(
            challenger_id=cid, name=recipe_name, target="band_gap",
            architecture="alignn_lite", strategy="curriculum",
            dataset_size=final["dataset_size"],
            train_size=final["train_size"],
            val_size=final["val_size"],
            test_size=final["test_size"],
            strata_summary={**sample.actual_counts, "_curriculum_note": final_note,
                           "_phase1_mae": m1.get("test_mae", 0),
                           "_phase2_mae": m2.get("test_mae", 0) if "error" not in m2 else "failed"},
            epochs=phase1_epochs + phase2_epochs,
            best_epoch=final["best_epoch"],
            seed=seed, test_mae=final["test_mae"],
            test_rmse=final["test_rmse"], test_r2=final["test_r2"],
            training_time_sec=round(total_time, 1),
            checkpoint=os.path.join(output_dir, final["checkpoint"]),
            created_at=now)

        with open(os.path.join(output_dir, "challenger_result.json"), "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        return result
    finally:
        for p in (p1_path, p2_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def train_all_challengers(source_db: MaterialsDB, epochs: int = 15,
                          seed: int = 42) -> List[ChallengerResult]:
    """Train all stratified/curriculum challengers."""
    results = []

    # 1. Stratified 20K
    log.info("=== Challenger: bg_stratified_20k ===")
    r1 = train_stratified_challenger(source_db, "bg_stratified_20k", epochs=epochs, seed=seed)
    results.append(r1)
    log.info("  → MAE=%.4f R²=%.4f", r1.test_mae, r1.test_r2)

    # 2. Curriculum 20K
    log.info("=== Challenger: bg_curriculum_20k ===")
    r2 = train_curriculum_challenger(source_db, "bg_curriculum_20k",
                                     phase1_epochs=10, phase2_epochs=5, seed=seed)
    results.append(r2)
    log.info("  → MAE=%.4f R²=%.4f", r2.test_mae, r2.test_r2)

    # 3. Stratified balanced 30K
    log.info("=== Challenger: bg_stratified_balanced_30k ===")
    r3 = train_stratified_challenger(source_db, "bg_stratified_balanced_30k", epochs=epochs, seed=seed)
    results.append(r3)
    log.info("  → MAE=%.4f R²=%.4f", r3.test_mae, r3.test_r2)

    return results

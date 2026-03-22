"""Gate recall rescue — retrain gate with oversampled narrow-gap to fix FN.

Phase IV.S: The 3-tier pipeline MAE=0.2596 missed promotion by +0.005 on
narrow-gap tolerance. Root cause: gate sends 66% of narrow-gap to BG=0.
Fix: oversample narrow-gap in gate training so the classifier sees more
borderline semiconductors.
"""

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from typing import List, Dict, Tuple

import numpy as np
import torch
import torch.nn as nn

from ..storage.db import MaterialsDB
from ..normalization.structure import load_structure
from ..features.crystal_graph import structure_to_graph
from ..models.cgcnn import CGCNN
from .spec import METAL_THRESHOLD
from .narrow_gap import NARROW_LOW, NARROW_HIGH

log = logging.getLogger(__name__)

ARTIFACT_DIR = "artifacts/gate_recall_rescue"


def _build_oversampled_gate_db(source_db: MaterialsDB, metal_count: int = 8000,
                                narrow_count: int = 6000, wide_count: int = 6000,
                                seed: int = 42) -> str:
    """Build gate training DB with oversampled narrow-gap materials.

    Default gate (IV.N): ~14K metals, ~6K non-metals (70/30 split)
    Oversampled: 8K metals + 6K narrow-gap + 6K wide non-metals (40/30/30 split)
    This gives the gate 3x more narrow-gap exposure.
    """
    src_conn = sqlite3.connect(source_db.db_path)
    src_conn.row_factory = sqlite3.Row
    cursor = src_conn.cursor()
    cursor.execute("PRAGMA table_info(materials)")
    columns = [row[1] for row in cursor.fetchall()]
    col_list = ", ".join(columns)
    rng = np.random.RandomState(seed)

    all_rows = []

    # Metals (BG < 0.05)
    cursor.execute(f"SELECT {col_list} FROM materials WHERE band_gap < {METAL_THRESHOLD} ORDER BY canonical_id")
    metals = cursor.fetchall()
    if len(metals) > metal_count:
        idx = rng.choice(len(metals), metal_count, replace=False)
        metals = [metals[i] for i in sorted(idx)]
    all_rows.extend(metals)

    # Narrow-gap non-metals (0.05 - 1.0) — OVERSAMPLED
    cursor.execute(f"SELECT {col_list} FROM materials WHERE band_gap >= {NARROW_LOW} AND band_gap < {NARROW_HIGH} ORDER BY canonical_id")
    narrow = cursor.fetchall()
    if len(narrow) > narrow_count:
        idx = rng.choice(len(narrow), narrow_count, replace=False)
        narrow = [narrow[i] for i in sorted(idx)]
    all_rows.extend(narrow)

    # Wide non-metals (>= 1.0)
    cursor.execute(f"SELECT {col_list} FROM materials WHERE band_gap >= {NARROW_HIGH} ORDER BY canonical_id")
    wide = cursor.fetchall()
    if len(wide) > wide_count:
        idx = rng.choice(len(wide), wide_count, replace=False)
        wide = [wide[i] for i in sorted(idx)]
    all_rows.extend(wide)
    src_conn.close()

    # Write to temp DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    MaterialsDB(tmp.name)
    dst_conn = sqlite3.connect(tmp.name)
    dst_c = dst_conn.cursor()
    placeholders = ", ".join(["?"] * len(columns))
    for row in all_rows:
        dst_c.execute(f"INSERT OR REPLACE INTO materials ({col_list}) VALUES ({placeholders})", list(row))
    dst_conn.commit()
    dst_conn.close()

    log.info("Oversampled gate DB: %d metals + %d narrow + %d wide = %d total",
             len(metals), len(narrow), len(wide), len(all_rows))
    return tmp.name


def train_gate_challenger(source_db: MaterialsDB, name: str,
                          oversample: bool = False, epochs: int = 15,
                          lr: float = 0.005, seed: int = 42) -> dict:
    """Train a gate challenger, optionally with oversampled narrow-gap."""
    now = datetime.now(timezone.utc).isoformat()
    cid = hashlib.sha256(f"gaterescue|{name}|{now}".encode()).hexdigest()[:12]
    output_dir = os.path.join(ARTIFACT_DIR, f"gate_{name}")
    os.makedirs(output_dir, exist_ok=True)

    if oversample:
        tmp_path = _build_oversampled_gate_db(source_db, seed=seed)
    else:
        # Standard balanced: use default 20K limit
        tmp_path = _build_oversampled_gate_db(source_db, metal_count=14000,
                                               narrow_count=2000, wide_count=4000, seed=seed)

    try:
        tmp_db = MaterialsDB(tmp_path)
        # Load dataset for gate training
        materials = tmp_db.search_training_candidates(["band_gap"], limit=25000)
        samples = []
        for m in materials:
            if not m.structure_data or not m.has_valid_structure or m.band_gap is None:
                continue
            struct = load_structure(m.structure_data)
            if struct is None:
                continue
            graph = structure_to_graph(struct)
            if graph is None:
                continue
            label = 0.0 if m.band_gap < METAL_THRESHOLD else 1.0
            samples.append({"graph": graph, "target": label, "band_gap": float(m.band_gap)})

        rng = np.random.RandomState(seed)
        rng.shuffle(samples)
        n = len(samples)
        n_train = int(n * 0.8)
        n_val = int(n * 0.1)
        train_set = samples[:n_train]
        val_set = samples[n_train:n_train+n_val]
        test_set = samples[n_train+n_val:]

        metals_in_test = sum(1 for s in test_set if s["target"] == 0.0)
        narrow_in_test = sum(1 for s in test_set if s["band_gap"] >= NARROW_LOW and s["band_gap"] < NARROW_HIGH)
        log.info("Gate '%s': %d train, %d val, %d test (metals=%d, narrow=%d), %d epochs",
                 name, len(train_set), len(val_set), len(test_set), metals_in_test, narrow_in_test, epochs)

        # Train CGCNN gate
        torch.manual_seed(seed)
        np.random.seed(seed)
        model = CGCNN()
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        criterion = nn.BCEWithLogitsLoss()
        best_val = float("inf")
        best_epoch = 0
        ckpt = os.path.join(output_dir, "gate_best.pt")
        t0 = time.time()

        for epoch in range(epochs):
            model.train()
            for s in train_set:
                g = s["graph"]
                pred = model(torch.tensor(g["atom_features"]), torch.tensor(g["bond_distances"]),
                             torch.tensor(g["neighbor_indices"]))
                loss = criterion(pred, torch.tensor(s["target"], dtype=torch.float32))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            model.eval()
            vl = 0.0
            with torch.no_grad():
                for s in val_set:
                    g = s["graph"]
                    p = model(torch.tensor(g["atom_features"]), torch.tensor(g["bond_distances"]),
                              torch.tensor(g["neighbor_indices"]))
                    vl += criterion(p, torch.tensor(s["target"], dtype=torch.float32)).item()
            avg_vl = vl / max(len(val_set), 1)
            if avg_vl < best_val:
                best_val = avg_vl
                best_epoch = epoch
                torch.save(model.state_dict(), ckpt)
            if (epoch + 1) % 5 == 0:
                log.info("  Gate '%s' epoch %d/%d: val_loss=%.4f", name, epoch+1, epochs, avg_vl)

        elapsed = time.time() - t0

        # Evaluate at multiple thresholds
        model.load_state_dict(torch.load(ckpt, weights_only=True))
        model.eval()
        test_sigmoids = []
        with torch.no_grad():
            for s in test_set:
                g = s["graph"]
                logit = model(torch.tensor(g["atom_features"]), torch.tensor(g["bond_distances"]),
                              torch.tensor(g["neighbor_indices"]))
                test_sigmoids.append((torch.sigmoid(logit).item(), s["target"], s["band_gap"]))

        thresholds_results = {}
        for thresh in [0.30, 0.35, 0.40, 0.45, 0.50]:
            tp = tn = fp = fn = fn_narrow = 0
            for sig, actual, bg in test_sigmoids:
                pred_nm = sig >= thresh
                actual_nm = actual == 1.0
                if actual_nm and pred_nm: tp += 1
                elif not actual_nm and not pred_nm: tn += 1
                elif not actual_nm and pred_nm: fp += 1
                else:
                    fn += 1
                    if NARROW_LOW <= bg < NARROW_HIGH:
                        fn_narrow += 1
            total = tp + tn + fp + fn
            acc = (tp + tn) / max(total, 1)
            rec_nm = tp / max(tp + fn, 1)
            rec_m = tn / max(tn + fp, 1)
            thresholds_results[str(thresh)] = {
                "accuracy": round(acc, 4), "recall_nonmetal": round(rec_nm, 4),
                "recall_metal": round(rec_m, 4),
                "fn": fn, "fn_narrow": fn_narrow, "fp": fp,
                "tp": tp, "tn": tn,
            }

        result = {
            "challenger_id": cid, "name": name,
            "oversample": oversample,
            "dataset_size": n, "train_size": len(train_set),
            "test_size": len(test_set),
            "best_epoch": best_epoch, "epochs": epochs,
            "training_time_sec": round(elapsed, 1),
            "checkpoint": ckpt,
            "thresholds": thresholds_results,
            "created_at": now,
        }

        with open(os.path.join(output_dir, "result.json"), "w") as f:
            json.dump(result, f, indent=2)
        return result
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_rescue_benchmark(db: MaterialsDB, gate_path: str, gate_threshold: float,
                         sample_size: int = 2000, seed: int = 42) -> dict:
    """Run 3-tier benchmark with the rescued gate."""
    from .three_tier import _compute_entry, BUCKET_RANGES
    from ..models.alignn_lite import ALIGNNLite

    materials = db.search_training_candidates(["band_gap"], limit=sample_size * 3)
    rng = np.random.RandomState(seed)
    samples = []
    for m in materials:
        if not m.structure_data or not m.has_valid_structure or m.band_gap is None:
            continue
        struct = load_structure(m.structure_data)
        if struct is None:
            continue
        graph = structure_to_graph(struct)
        if graph is None:
            continue
        samples.append({"formula": m.formula, "band_gap": float(m.band_gap), "graph": graph})
    rng.shuffle(samples)
    samples = samples[:sample_size]
    actuals = np.array([s["band_gap"] for s in samples])

    # Load models
    gate = CGCNN()
    gate.load_state_dict(torch.load(gate_path, weights_only=True))
    gate.eval()

    narrow_path = "artifacts/three_tier_band_gap/narrow_gap_specialist/alignn_band_gap_best.pt"
    general_path = "artifacts/hierarchical_band_gap_regressor/challenger_nonmetal_lower_lr/alignn_band_gap_best.pt"
    prod_path = "artifacts/training_ladder_band_gap/rung_20k/alignn_band_gap_best.pt"
    if not os.path.exists(prod_path):
        prod_path = "artifacts/training/alignn_band_gap_best.pt"

    narrow_model = ALIGNNLite()
    narrow_model.load_state_dict(torch.load(narrow_path, weights_only=True))
    narrow_model.eval()
    general_model = ALIGNNLite()
    general_model.load_state_dict(torch.load(general_path, weights_only=True))
    general_model.eval()
    prod_model = ALIGNNLite()
    prod_model.load_state_dict(torch.load(prod_path, weights_only=True))
    prod_model.eval()

    results = {}

    # Production
    prod_preds = []
    with torch.no_grad():
        for s in samples:
            g = s["graph"]
            prod_preds.append(prod_model(torch.tensor(g["atom_features"]),
                                         torch.tensor(g["bond_distances"]),
                                         torch.tensor(g["neighbor_indices"])).item())
    results["production"] = _compute_entry("production", actuals, np.array(prod_preds), 0)

    # 3-tier with rescued gate
    three_preds = []
    gate_metals = gate_narrow = gate_general = 0
    with torch.no_grad():
        for s in samples:
            g = s["graph"]
            af = torch.tensor(g["atom_features"])
            bd = torch.tensor(g["bond_distances"])
            ni = torch.tensor(g["neighbor_indices"])
            sig = torch.sigmoid(gate(af, bd, ni)).item()

            if sig < gate_threshold:
                three_preds.append(0.0)
                gate_metals += 1
            else:
                gen_pred = max(0.0, general_model(af, bd, ni).item())
                if gen_pred < NARROW_HIGH:
                    three_preds.append(max(0.0, narrow_model(af, bd, ni).item()))
                    gate_narrow += 1
                else:
                    three_preds.append(gen_pred)
                    gate_general += 1

    entry = _compute_entry("three_tier_rescued", actuals, np.array(three_preds), 0)
    entry["gate_metals"] = gate_metals
    entry["gate_narrow"] = gate_narrow
    entry["gate_general"] = gate_general
    entry["gate_threshold"] = gate_threshold
    results["three_tier_rescued"] = entry

    narrow_mask = (actuals >= NARROW_LOW) & (actuals < NARROW_HIGH)
    narrow_reaching = sum(1 for i, s in enumerate(samples) if narrow_mask[i] and three_preds[i] > 0)
    entry["narrow_reaching_specialist"] = narrow_reaching
    entry["narrow_total"] = int(narrow_mask.sum())

    return {"entries": results, "sample_size": len(samples), "seed": seed,
            "gate_path": gate_path, "gate_threshold": gate_threshold,
            "created_at": datetime.now(timezone.utc).isoformat()}

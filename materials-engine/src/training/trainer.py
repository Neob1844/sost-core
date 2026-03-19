"""Training pipeline for GNN models.

Phase II baseline: trains CGCNN on small datasets with full reproducibility.
"""

import json
import hashlib
import logging
import os
import time
import math
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np
import torch
import torch.nn as nn

from ..storage.db import MaterialsDB
from ..normalization.structure import load_structure
from ..features.crystal_graph import structure_to_graph
from ..models.cgcnn import CGCNN

log = logging.getLogger(__name__)


def _set_seed(seed: int):
    torch.manual_seed(seed)
    np.random.seed(seed)


def load_dataset(db: MaterialsDB, target: str, limit: int = 10000, seed: int = 42):
    """Load materials with valid structure + target property into graph format."""
    materials = db.search_training_candidates([target], limit=limit)
    samples = []
    skipped = 0
    for m in materials:
        if not m.structure_data or not m.has_valid_structure:
            skipped += 1
            continue
        struct = load_structure(m.structure_data)
        if struct is None:
            skipped += 1
            continue
        graph = structure_to_graph(struct)
        if graph is None:
            skipped += 1
            continue
        val = getattr(m, target, None)
        if val is None:
            skipped += 1
            continue
        samples.append({"graph": graph, "target": float(val),
                        "formula": m.formula, "canonical_id": m.canonical_id})

    log.info("Dataset '%s': %d usable / %d total (%d skipped)",
             target, len(samples), len(materials), skipped)

    # Reproducible shuffle + split
    rng = np.random.RandomState(seed)
    rng.shuffle(samples)
    n = len(samples)
    n_train = int(n * 0.8)
    n_val = int(n * 0.1)
    return {
        "train": samples[:n_train],
        "val": samples[n_train:n_train + n_val],
        "test": samples[n_train + n_val:],
        "total": n,
    }


def train_cgcnn(db: MaterialsDB, target: str, epochs: int = 50, lr: float = 0.01,
                seed: int = 42, output_dir: str = "artifacts/training") -> dict:
    """Train CGCNN baseline on target property. Returns metrics dict."""
    _set_seed(seed)
    os.makedirs(output_dir, exist_ok=True)

    dataset = load_dataset(db, target, seed=seed)
    if dataset["total"] < 10:
        return {"error": f"Too few samples ({dataset['total']}) for training"}

    model = CGCNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    train_losses, val_losses = [], []
    best_val_loss = float("inf")
    best_epoch = 0

    log.info("Training CGCNN for '%s': %d train, %d val, %d test, %d epochs",
             target, len(dataset["train"]), len(dataset["val"]),
             len(dataset["test"]), epochs)
    t0 = time.time()

    for epoch in range(epochs):
        # Train
        model.train()
        epoch_loss = 0.0
        for s in dataset["train"]:
            g = s["graph"]
            atom_f = torch.tensor(g["atom_features"])
            bond_d = torch.tensor(g["bond_distances"])
            nbr_i = torch.tensor(g["neighbor_indices"])
            tgt = torch.tensor(s["target"], dtype=torch.float32)

            pred = model(atom_f, bond_d, nbr_i)
            loss = criterion(pred, tgt)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        avg_train = epoch_loss / max(len(dataset["train"]), 1)
        train_losses.append(avg_train)

        # Validate
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for s in dataset["val"]:
                g = s["graph"]
                pred = model(torch.tensor(g["atom_features"]),
                             torch.tensor(g["bond_distances"]),
                             torch.tensor(g["neighbor_indices"]))
                val_loss += criterion(pred, torch.tensor(s["target"], dtype=torch.float32)).item()
        avg_val = val_loss / max(len(dataset["val"]), 1)
        val_losses.append(avg_val)

        if avg_val < best_val_loss:
            best_val_loss = avg_val
            best_epoch = epoch
            torch.save(model.state_dict(), os.path.join(output_dir, f"cgcnn_{target}_best.pt"))

        if (epoch + 1) % 10 == 0:
            log.info("  Epoch %d/%d: train_loss=%.4f val_loss=%.4f", epoch + 1, epochs, avg_train, avg_val)

    elapsed = time.time() - t0

    # Test evaluation
    model.load_state_dict(torch.load(os.path.join(output_dir, f"cgcnn_{target}_best.pt"),
                                      weights_only=True))
    model.eval()
    preds, targets = [], []
    with torch.no_grad():
        for s in dataset["test"]:
            g = s["graph"]
            pred = model(torch.tensor(g["atom_features"]),
                         torch.tensor(g["bond_distances"]),
                         torch.tensor(g["neighbor_indices"]))
            preds.append(pred.item())
            targets.append(s["target"])

    preds, targets = np.array(preds), np.array(targets)
    mae = np.mean(np.abs(preds - targets))
    rmse = np.sqrt(np.mean((preds - targets) ** 2))
    ss_res = np.sum((targets - preds) ** 2)
    ss_tot = np.sum((targets - targets.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    metrics = {
        "model": "cgcnn",
        "target": target,
        "dataset_size": dataset["total"],
        "train_size": len(dataset["train"]),
        "val_size": len(dataset["val"]),
        "test_size": len(dataset["test"]),
        "epochs": epochs,
        "best_epoch": best_epoch,
        "seed": seed,
        "test_mae": round(mae, 4),
        "test_rmse": round(rmse, 4),
        "test_r2": round(r2, 4),
        "training_time_sec": round(elapsed, 1),
        "checkpoint": f"cgcnn_{target}_best.pt",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Save metrics
    with open(os.path.join(output_dir, f"cgcnn_{target}_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    # Save predictions
    test_preds = [{"formula": s["formula"], "target": s["target"],
                   "predicted": round(preds[i], 4)}
                  for i, s in enumerate(dataset["test"])]
    with open(os.path.join(output_dir, f"cgcnn_{target}_predictions.json"), "w") as f:
        json.dump(test_preds, f, indent=2)

    log.info("CGCNN '%s': MAE=%.4f RMSE=%.4f R²=%.4f (%.1fs, %d samples)",
             target, mae, rmse, r2, elapsed, dataset["total"])
    return metrics


def train_alignn(db: MaterialsDB, target: str, epochs: int = 50, lr: float = 0.005,
                 seed: int = 42, output_dir: str = "artifacts/training") -> dict:
    """Train ALIGNN-Lite on target property. Returns metrics dict."""
    from ..models.alignn_lite import ALIGNNLite
    _set_seed(seed)
    os.makedirs(output_dir, exist_ok=True)

    dataset = load_dataset(db, target, seed=seed)
    if dataset["total"] < 10:
        return {"error": f"Too few samples ({dataset['total']})"}

    model = ALIGNNLite()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_epoch = 0
    prefix = f"alignn_{target}"

    log.info("Training ALIGNN-Lite '%s': %d train, %d val, %d test, %d epochs",
             target, len(dataset["train"]), len(dataset["val"]), len(dataset["test"]), epochs)
    t0 = time.time()

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        for s in dataset["train"]:
            g = s["graph"]
            pred = model(torch.tensor(g["atom_features"]),
                         torch.tensor(g["bond_distances"]),
                         torch.tensor(g["neighbor_indices"]))
            loss = criterion(pred, torch.tensor(s["target"], dtype=torch.float32))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for s in dataset["val"]:
                g = s["graph"]
                pred = model(torch.tensor(g["atom_features"]),
                             torch.tensor(g["bond_distances"]),
                             torch.tensor(g["neighbor_indices"]))
                val_loss += criterion(pred, torch.tensor(s["target"], dtype=torch.float32)).item()
        avg_val = val_loss / max(len(dataset["val"]), 1)
        if avg_val < best_val_loss:
            best_val_loss = avg_val
            best_epoch = epoch
            torch.save(model.state_dict(), os.path.join(output_dir, f"{prefix}_best.pt"))
        if (epoch + 1) % 10 == 0:
            log.info("  Epoch %d/%d: val_loss=%.4f", epoch + 1, epochs, avg_val)

    elapsed = time.time() - t0

    # Test
    model.load_state_dict(torch.load(os.path.join(output_dir, f"{prefix}_best.pt"), weights_only=True))
    model.eval()
    preds, tgts = [], []
    with torch.no_grad():
        for s in dataset["test"]:
            g = s["graph"]
            p = model(torch.tensor(g["atom_features"]),
                      torch.tensor(g["bond_distances"]),
                      torch.tensor(g["neighbor_indices"]))
            preds.append(p.item())
            tgts.append(s["target"])

    preds, tgts = np.array(preds), np.array(tgts)
    mae = np.mean(np.abs(preds - tgts))
    rmse = np.sqrt(np.mean((preds - tgts) ** 2))
    ss_res = np.sum((tgts - preds) ** 2)
    ss_tot = np.sum((tgts - tgts.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    metrics = {
        "model": "alignn_lite", "target": target,
        "dataset_size": dataset["total"],
        "train_size": len(dataset["train"]), "val_size": len(dataset["val"]),
        "test_size": len(dataset["test"]), "epochs": epochs,
        "best_epoch": best_epoch, "seed": seed,
        "test_mae": round(mae, 4), "test_rmse": round(rmse, 4), "test_r2": round(r2, 4),
        "training_time_sec": round(elapsed, 1),
        "checkpoint": f"{prefix}_best.pt",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(os.path.join(output_dir, f"{prefix}_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    log.info("ALIGNN-Lite '%s': MAE=%.4f RMSE=%.4f R²=%.4f (%.1fs, %d samples)",
             target, mae, rmse, r2, elapsed, dataset["total"])
    return metrics


def train_model(db: MaterialsDB, arch: str, target: str, **kwargs) -> dict:
    """Unified training entry point."""
    if arch == "cgcnn":
        return train_cgcnn(db, target, **kwargs)
    elif arch in ("alignn", "alignn_lite"):
        return train_alignn(db, target, **kwargs)
    else:
        return {"error": f"Unknown architecture: {arch}"}

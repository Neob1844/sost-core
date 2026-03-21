"""Metal gate — binary classifier: metal vs non-metal.

Phase IV.N: Uses the same GNN architecture but with sigmoid output
for binary classification. Metal = band_gap < 0.05 eV.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import numpy as np
import torch
import torch.nn as nn

from ..storage.db import MaterialsDB
from ..normalization.structure import load_structure
from ..features.crystal_graph import structure_to_graph
from ..models.cgcnn import CGCNN
from .spec import MetalGateResult, METAL_THRESHOLD

log = logging.getLogger(__name__)


def _load_gate_dataset(db: MaterialsDB, limit: int = 20000, seed: int = 42):
    """Load dataset for metal/non-metal classification."""
    materials = db.search_training_candidates(["band_gap"], limit=limit)
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
        if m.band_gap is None:
            skipped += 1
            continue
        label = 0.0 if m.band_gap < METAL_THRESHOLD else 1.0  # 0=metal, 1=nonmetal
        samples.append({"graph": graph, "target": label,
                        "band_gap": float(m.band_gap),
                        "formula": m.formula, "canonical_id": m.canonical_id})

    rng = np.random.RandomState(seed)
    rng.shuffle(samples)
    n = len(samples)
    n_train = int(n * 0.8)
    n_val = int(n * 0.1)
    metals = sum(1 for s in samples if s["target"] == 0.0)
    log.info("Gate dataset: %d total (%d metals, %d nonmetals), %d skipped",
             n, metals, n - metals, skipped)
    return {
        "train": samples[:n_train],
        "val": samples[n_train:n_train + n_val],
        "test": samples[n_train + n_val:],
        "total": n,
    }


def train_metal_gate(db: MaterialsDB, epochs: int = 15, lr: float = 0.005,
                     seed: int = 42, limit: int = 20000,
                     output_dir: str = "artifacts/hierarchical_band_gap") -> MetalGateResult:
    """Train binary metal gate classifier using CGCNN + sigmoid."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    os.makedirs(output_dir, exist_ok=True)

    dataset = _load_gate_dataset(db, limit=limit, seed=seed)
    if dataset["total"] < 10:
        return MetalGateResult(architecture="cgcnn_gate")

    model = CGCNN()  # outputs scalar — we apply sigmoid for classification
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.BCEWithLogitsLoss()

    best_val_loss = float("inf")
    best_epoch = 0
    ckpt_path = os.path.join(output_dir, "metal_gate_best.pt")

    log.info("Training metal gate: %d train, %d val, %d test, %d epochs",
             len(dataset["train"]), len(dataset["val"]), len(dataset["test"]), epochs)
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
            torch.save(model.state_dict(), ckpt_path)
        if (epoch + 1) % 5 == 0:
            log.info("  Gate epoch %d/%d: val_loss=%.4f", epoch + 1, epochs, avg_val)

    elapsed = time.time() - t0

    # Test evaluation
    model.load_state_dict(torch.load(ckpt_path, weights_only=True))
    model.eval()
    tp = tn = fp = fn = 0
    with torch.no_grad():
        for s in dataset["test"]:
            g = s["graph"]
            logit = model(torch.tensor(g["atom_features"]),
                          torch.tensor(g["bond_distances"]),
                          torch.tensor(g["neighbor_indices"]))
            pred_class = 1.0 if torch.sigmoid(logit).item() >= 0.5 else 0.0
            actual = s["target"]
            if actual == 0.0 and pred_class == 0.0:
                tn += 1
            elif actual == 0.0 and pred_class == 1.0:
                fp += 1
            elif actual == 1.0 and pred_class == 0.0:
                fn += 1
            else:
                tp += 1

    total_test = tp + tn + fp + fn
    accuracy = (tp + tn) / max(total_test, 1)
    prec_m = tn / max(tn + fn, 1)
    rec_m = tn / max(tn + fp, 1)
    f1_m = 2 * prec_m * rec_m / max(prec_m + rec_m, 1e-9)
    prec_nm = tp / max(tp + fp, 1)
    rec_nm = tp / max(tp + fn, 1)
    f1_nm = 2 * prec_nm * rec_nm / max(prec_nm + rec_nm, 1e-9)

    result = MetalGateResult(
        architecture="cgcnn_gate",
        threshold=METAL_THRESHOLD,
        dataset_size=dataset["total"],
        train_size=len(dataset["train"]),
        test_size=total_test,
        accuracy=round(accuracy, 4),
        precision_metal=round(prec_m, 4),
        recall_metal=round(rec_m, 4),
        f1_metal=round(f1_m, 4),
        precision_nonmetal=round(prec_nm, 4),
        recall_nonmetal=round(rec_nm, 4),
        f1_nonmetal=round(f1_nm, 4),
        confusion_matrix={"TP": tp, "TN": tn, "FP": fp, "FN": fn},
        training_time_sec=round(elapsed, 1),
        checkpoint=ckpt_path,
        created_at=datetime.now(timezone.utc).isoformat())

    with open(os.path.join(output_dir, "gate_metrics.json"), "w") as f:
        json.dump(result.to_dict(), f, indent=2)

    log.info("Metal gate: acc=%.4f, F1_metal=%.4f, F1_nonmetal=%.4f (%.1fs)",
             accuracy, f1_m, f1_nm, elapsed)
    return result

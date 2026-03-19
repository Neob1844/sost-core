"""Inference engine — loads trained models and predicts properties.

Phase II: single-sample and batch prediction from CIF or pymatgen Structure.
"""

import logging
import os
import torch
import numpy as np
from typing import Optional

from ..models.cgcnn import CGCNN
from ..models.registry import get_best_model
from ..normalization.structure import load_structure, validate_structure
from ..features.crystal_graph import structure_to_graph, composition_fingerprint

log = logging.getLogger(__name__)

_loaded_models = {}  # cache: (model_name, target) → (model, metrics)


def _load_model(target: str, model_dir: str = "artifacts/training") -> Optional[tuple]:
    """Load best model for target. Returns (model, metrics) or None."""
    best = get_best_model(target)
    if not best:
        log.warning("No trained model found for target '%s'", target)
        return None

    cache_key = (best["model"], target)
    if cache_key in _loaded_models:
        return _loaded_models[cache_key]

    ckpt_path = os.path.join(model_dir, best["checkpoint"])
    if not os.path.exists(ckpt_path):
        log.error("Checkpoint not found: %s", ckpt_path)
        return None

    # Select model class based on architecture name
    arch = best.get("model", "cgcnn")
    if arch == "alignn_lite":
        from ..models.alignn_lite import ALIGNNLite
        model = ALIGNNLite()
    else:
        model = CGCNN()

    model.load_state_dict(torch.load(ckpt_path, weights_only=True))
    model.eval()
    _loaded_models[cache_key] = (model, best)
    log.info("Loaded %s for '%s' (MAE=%.4f)", arch, target, best["test_mae"])
    return model, best


def predict_from_cif(cif_text: str, target: str) -> dict:
    """Predict property from CIF text.

    Returns dict with prediction, model info, validation status.
    """
    # Validate structure
    valid, err = validate_structure(cif_text)
    if not valid:
        return {"error": f"Invalid structure: {err}", "valid_structure": False}

    struct = load_structure(cif_text)
    if struct is None:
        return {"error": "Failed to load structure", "valid_structure": False}

    return predict_from_structure(struct, target)


def predict_from_structure(structure, target: str) -> dict:
    """Predict property from pymatgen Structure."""
    result = _load_model(target)
    if result is None:
        return {"error": f"No trained model for target '{target}'"}

    model, metrics = result
    graph = structure_to_graph(structure)
    if graph is None:
        return {"error": "Failed to convert structure to graph", "valid_structure": True}

    with torch.no_grad():
        pred = model(
            torch.tensor(graph["atom_features"]),
            torch.tensor(graph["bond_distances"]),
            torch.tensor(graph["neighbor_indices"])
        ).item()

    return {
        "prediction": round(pred, 4),
        "target": target,
        "model": metrics["model"],
        "checkpoint": metrics["checkpoint"],
        "model_mae": metrics["test_mae"],
        "valid_structure": True,
        "n_atoms": graph["n_atoms"],
        "note": f"Baseline model trained on {metrics['dataset_size']} samples. "
                f"Test MAE={metrics['test_mae']}. Small dataset — use with caution.",
    }


def _structural_fingerprint(m) -> Optional[np.ndarray]:
    """Compute structure-aware fingerprint: composition + lattice + spacegroup."""
    comp_fp = composition_fingerprint(m.elements)
    # Add structural features (normalized)
    struct_feats = np.zeros(10, dtype=np.float32)
    if m.spacegroup:
        struct_feats[0] = m.spacegroup / 230.0  # normalized to [0,1]
    if m.lattice_params:
        lp = m.lattice_params
        for i, k in enumerate(["a", "b", "c"]):
            v = lp.get(k)
            if v: struct_feats[1 + i] = min(v / 20.0, 1.0)  # normalize ~0-20Å
        for i, k in enumerate(["alpha", "beta", "gamma"]):
            v = lp.get(k)
            if v: struct_feats[4 + i] = v / 180.0  # normalize to [0,1]
    if m.nsites:
        struct_feats[7] = min(m.nsites / 50.0, 1.0)
    if m.band_gap is not None:
        struct_feats[8] = min(m.band_gap / 10.0, 1.0)
    if m.formation_energy is not None:
        struct_feats[9] = (m.formation_energy + 5.0) / 10.0  # shift to ~[0,1]
    return np.concatenate([comp_fp, struct_feats])


def find_similar(canonical_id: str, db, top_k: int = 5) -> list:
    """Find similar materials using composition + structure fingerprints.

    Phase II.5: combines element frequency (94-dim) with structural features
    (spacegroup, lattice params, nsites, properties) = 104-dim vector.
    Method: cosine similarity on concatenated fingerprint.
    """
    target_mat = db.get_material(canonical_id)
    if not target_mat:
        return []

    target_fp = _structural_fingerprint(target_mat)
    if target_fp is None or target_fp.sum() == 0:
        return []

    all_mats = db.list_materials(limit=5000)
    scored = []
    for m in all_mats:
        if m.canonical_id == canonical_id:
            continue
        fp = _structural_fingerprint(m)
        if fp is None or fp.sum() == 0:
            continue
        dot = np.dot(target_fp, fp)
        na = np.linalg.norm(target_fp)
        nb = np.linalg.norm(fp)
        sim = dot / (na * nb) if na > 0 and nb > 0 else 0.0
        scored.append({"canonical_id": m.canonical_id, "formula": m.formula,
                       "source": m.source, "similarity": round(float(sim), 4),
                       "band_gap": m.band_gap, "spacegroup": m.spacegroup})

    scored.sort(key=lambda x: -x["similarity"])
    return scored[:top_k]

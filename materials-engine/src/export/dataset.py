"""Export reproducible ML-ready datasets with manifests.

Phase I: exports CSV + JSON manifest with hash, seed, split info.
No actual ML training — just dataset preparation.
"""

import csv
import hashlib
import json
import os
import logging
import random
from datetime import datetime, timezone
from typing import List, Optional
from ..schema import Material
from ..storage.db import MaterialsDB

log = logging.getLogger(__name__)


def export_dataset(db: MaterialsDB, name: str, required_props: List[str],
                   output_dir: str = "artifacts", seed: int = 42,
                   train_ratio: float = 0.8, val_ratio: float = 0.1,
                   limit: int = 100000, source_filter: Optional[str] = None) -> dict:
    """Export a reproducible dataset with train/val/test split.

    Returns manifest dict and writes files to output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Fetch candidates
    materials = db.search_training_candidates(required_props, limit=limit)
    if source_filter:
        materials = [m for m in materials if m.source == source_filter]

    if not materials:
        log.warning("No materials found for dataset '%s'", name)
        return {"name": name, "total": 0, "error": "no matching materials"}

    # Reproducible shuffle + split
    rng = random.Random(seed)
    rng.shuffle(materials)
    n = len(materials)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    splits = {
        "train": materials[:n_train],
        "val": materials[n_train:n_train + n_val],
        "test": materials[n_train + n_val:],
    }

    # Write CSV files
    fields = ["canonical_id", "formula", "source", "source_id"] + required_props
    hash_input = ""
    for split_name, split_data in splits.items():
        path = os.path.join(output_dir, f"{name}_{split_name}.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for m in split_data:
                row = {k: getattr(m, k, None) for k in fields}
                w.writerow(row)
                hash_input += json.dumps(row, sort_keys=True)
        log.info("Wrote %s: %d rows", path, len(split_data))

    dataset_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    manifest = {
        "name": name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "dataset_hash": dataset_hash,
        "total": n,
        "train": n_train,
        "val": n_val,
        "test": n - n_train - n_val,
        "required_properties": required_props,
        "source_filter": source_filter,
        "fields": fields,
        "train_ratio": train_ratio,
        "val_ratio": val_ratio,
        "files": {
            "train": f"{name}_train.csv",
            "val": f"{name}_val.csv",
            "test": f"{name}_test.csv",
        }
    }

    manifest_path = os.path.join(output_dir, f"{name}_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    log.info("Manifest: %s (hash=%s, total=%d)", manifest_path, dataset_hash, n)
    return manifest


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else "materials.db"
    db = MaterialsDB(db_path)

    print("Exporting band_gap dataset...")
    m1 = export_dataset(db, "band_gap", ["band_gap"])
    print(json.dumps(m1, indent=2))

    print("\nExporting formation_energy dataset...")
    m2 = export_dataset(db, "formation_energy", ["formation_energy"])
    print(json.dumps(m2, indent=2))

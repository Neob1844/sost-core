"""Persistent fingerprint store — precomputed vectors for fast retrieval.

Phase III.C: Stores 104-dim fingerprints (94 compositional + 10 structural)
in a numpy file alongside a JSON manifest for versioning.

Fingerprints are versioned. If the schema changes, the version bumps
and fingerprints are regenerated.
"""

import json
import logging
import os
import time
import numpy as np
from typing import Optional, List, Tuple

from ..storage.db import MaterialsDB
from ..novelty.fingerprint import material_fingerprint, COMBINED_DIM

log = logging.getLogger(__name__)

FINGERPRINT_VERSION = "1.0"
FINGERPRINT_TYPE = "combined_104"
VECTOR_DIM = COMBINED_DIM  # 104


class FingerprintStore:
    """Persistent fingerprint storage backed by numpy + JSON manifest."""

    def __init__(self, store_dir: str = "artifacts/fingerprints"):
        self.store_dir = store_dir
        self._vectors: Optional[np.ndarray] = None
        self._ids: List[str] = []
        self._formulas: List[str] = []
        self._manifest: dict = {}

    @property
    def vectors_path(self) -> str:
        return os.path.join(self.store_dir, "fingerprints.npy")

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.store_dir, "manifest.json")

    @property
    def ids_path(self) -> str:
        return os.path.join(self.store_dir, "ids.json")

    @property
    def size(self) -> int:
        return len(self._ids)

    @property
    def is_loaded(self) -> bool:
        return self._vectors is not None and len(self._ids) > 0

    def build(self, db: MaterialsDB, limit: int = 100000) -> dict:
        """Build fingerprints for all materials in DB.

        Returns manifest dict with stats.
        """
        os.makedirs(self.store_dir, exist_ok=True)
        t0 = time.time()

        materials = db.list_materials(limit=limit)
        vectors = []
        ids = []
        formulas = []
        skipped = 0

        for m in materials:
            fp = material_fingerprint(m)
            if fp.sum() == 0:
                skipped += 1
                continue
            vectors.append(fp)
            ids.append(m.canonical_id)
            formulas.append(m.formula)

        if vectors:
            arr = np.vstack(vectors).astype(np.float32)
        else:
            arr = np.empty((0, VECTOR_DIM), dtype=np.float32)

        np.save(self.vectors_path, arr)
        with open(self.ids_path, "w") as f:
            json.dump({"ids": ids, "formulas": formulas}, f)

        elapsed = time.time() - t0
        self._manifest = {
            "fingerprint_type": FINGERPRINT_TYPE,
            "fingerprint_version": FINGERPRINT_VERSION,
            "vector_dim": VECTOR_DIM,
            "total_materials": len(materials),
            "indexed": len(ids),
            "skipped": skipped,
            "build_time_sec": round(elapsed, 1),
        }
        with open(self.manifest_path, "w") as f:
            json.dump(self._manifest, f, indent=2)

        self._vectors = arr
        self._ids = ids
        self._formulas = formulas

        log.info("FingerprintStore built: %d vectors in %.1fs", len(ids), elapsed)
        return self._manifest

    def load(self) -> bool:
        """Load pre-built fingerprints from disk."""
        if not os.path.exists(self.vectors_path):
            return False
        try:
            self._vectors = np.load(self.vectors_path)
            with open(self.ids_path) as f:
                d = json.load(f)
            self._ids = d["ids"]
            self._formulas = d["formulas"]
            if os.path.exists(self.manifest_path):
                with open(self.manifest_path) as f:
                    self._manifest = json.load(f)
            log.info("FingerprintStore loaded: %d vectors", len(self._ids))
            return True
        except Exception as e:
            log.error("Failed to load fingerprint store: %s", e)
            return False

    def ensure_loaded(self, db: Optional[MaterialsDB] = None) -> bool:
        """Load from disk, or build if not found and db provided."""
        if self.is_loaded:
            return True
        if self.load():
            return True
        if db is not None:
            self.build(db)
            return True
        return False

    def get_vectors(self) -> np.ndarray:
        return self._vectors if self._vectors is not None else np.empty((0, VECTOR_DIM))

    def get_ids(self) -> List[str]:
        return self._ids

    def get_formulas(self) -> List[str]:
        return self._formulas

    def get_manifest(self) -> dict:
        return self._manifest

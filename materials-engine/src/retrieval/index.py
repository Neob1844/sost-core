"""Fast retrieval index — nearest-neighbor search over fingerprints.

Phase III.C: Uses precomputed L2-normalized vectors for fast cosine similarity.
Backend: numpy vectorized operations. Sufficient for <100K materials on CPU.
For >100K, can add sklearn BallTree or faiss-cpu without API changes.
"""

import logging
import time
import numpy as np
from typing import List, Optional, Tuple

from ..features.fingerprint_store import FingerprintStore, VECTOR_DIM

log = logging.getLogger(__name__)


class RetrievalIndex:
    """Fast nearest-neighbor search over persistent fingerprints.

    Uses L2-normalized vectors for cosine similarity via dot product.
    """

    def __init__(self, store: FingerprintStore):
        self.store = store
        self._normed: Optional[np.ndarray] = None
        self._built = False

    def build(self) -> dict:
        """Normalize vectors for fast dot-product similarity."""
        if not self.store.is_loaded:
            return {"error": "FingerprintStore not loaded"}

        t0 = time.time()
        vecs = self.store.get_vectors()
        if len(vecs) == 0:
            self._normed = np.empty((0, VECTOR_DIM))
            self._built = True
            return {"indexed": 0, "build_time_sec": 0}

        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        self._normed = vecs / norms
        self._built = True

        elapsed = time.time() - t0
        log.info("RetrievalIndex built: %d vectors normalized in %.2fs",
                 len(self._normed), elapsed)
        return {"indexed": len(self._normed), "build_time_sec": round(elapsed, 3)}

    @property
    def is_ready(self) -> bool:
        return self._built and self._normed is not None

    @property
    def size(self) -> int:
        return len(self._normed) if self._normed is not None else 0

    def search(self, query: np.ndarray, top_k: int = 10,
               exclude_id: Optional[str] = None) -> List[Tuple[str, str, float]]:
        """Find top_k nearest neighbors by cosine similarity.

        Args:
            query: 104-dim fingerprint vector
            top_k: number of results
            exclude_id: canonical_id to skip

        Returns:
            list of (canonical_id, formula, similarity)
        """
        if not self.is_ready or len(self._normed) == 0:
            return []

        q_norm = np.linalg.norm(query)
        if q_norm == 0:
            return []
        q = query / q_norm

        # Vectorized dot product = cosine similarity (both L2-normalized)
        sims = self._normed @ q

        # Get top indices
        k = min(top_k + (1 if exclude_id else 0), len(sims))
        if k >= len(sims):
            top_idx = np.argsort(-sims)
        else:
            top_idx = np.argpartition(-sims, k)[:k]
        top_idx = top_idx[np.argsort(-sims[top_idx])]

        ids = self.store.get_ids()
        formulas = self.store.get_formulas()
        results = []
        for idx in top_idx:
            cid = ids[idx]
            if exclude_id and cid == exclude_id:
                continue
            results.append((cid, formulas[idx], float(sims[idx])))
            if len(results) >= top_k:
                break
        return results

    def batch_search(self, queries: np.ndarray, top_k: int = 5) -> List[List[Tuple]]:
        """Search multiple queries efficiently."""
        return [self.search(q, top_k=top_k) for q in queries]

    def status(self) -> dict:
        return {
            "ready": self.is_ready,
            "indexed": self.size,
            "method": "cosine_dot_product",
            "backend": "numpy_vectorized",
            "vector_dim": VECTOR_DIM,
            "manifest": self.store.get_manifest(),
        }

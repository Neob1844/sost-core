"""Novelty filter — high-level API for novelty and exotic assessment.

Phase III.A: All assessments are relative to the current ingested corpus.
NOT relative to all scientific literature.

Usage:
    from src.novelty.filter import NoveltyFilter
    nf = NoveltyFilter(db)
    result = nf.check_material(material)
    exotic = nf.rank_exotic(top_k=20)
"""

import logging
import numpy as np
from typing import List, Optional, Tuple
from collections import Counter

from ..schema import Material
from ..storage.db import MaterialsDB
from .fingerprint import (
    material_fingerprint, combined_fingerprint, compositional_fingerprint,
    cosine_similarity, element_rarity_score, spacegroup_rarity_score,
    COMBINED_DIM,
)
from .scoring import (
    NoveltyResult, ExoticResult,
    compute_novelty, compute_exotic,
    NEAR_KNOWN_THRESHOLD,
)

log = logging.getLogger(__name__)


class NoveltyFilter:
    """Novelty and exotic assessment engine.

    Loads corpus fingerprints on init, then scores new or existing materials
    against the corpus. CPU-friendly brute-force scan — sufficient for <50K materials.
    """

    def __init__(self, db: MaterialsDB, corpus_limit: int = 50000):
        self.db = db
        self._corpus: List[Material] = []
        self._fingerprints: np.ndarray = np.empty(0)
        self._ids: List[str] = []
        self._formulas: List[str] = []
        self._element_counts: dict = {}
        self._sg_counts: dict = {}
        self._loaded = False
        self._corpus_limit = corpus_limit

    def _ensure_loaded(self):
        """Load corpus fingerprints lazily."""
        if self._loaded:
            return
        self._load_corpus()

    def _load_corpus(self):
        """Load all materials and compute fingerprints."""
        materials = self.db.list_materials(limit=self._corpus_limit)
        if not materials:
            self._loaded = True
            return

        fps = []
        ids = []
        formulas = []
        elem_counter = Counter()
        sg_counter = Counter()

        for m in materials:
            fp = material_fingerprint(m)
            if fp.sum() == 0:
                continue
            fps.append(fp)
            ids.append(m.canonical_id)
            formulas.append(m.formula)
            for el in m.elements:
                elem_counter[el] += 1
            if m.spacegroup:
                sg_counter[m.spacegroup] += 1

        self._corpus = materials
        if fps:
            self._fingerprints = np.vstack(fps)
        else:
            self._fingerprints = np.empty((0, COMBINED_DIM))
        self._ids = ids
        self._formulas = formulas
        self._element_counts = dict(elem_counter)
        self._sg_counts = dict(sg_counter)
        self._loaded = True
        log.info("NoveltyFilter loaded %d corpus fingerprints", len(ids))

    @property
    def corpus_size(self) -> int:
        self._ensure_loaded()
        return len(self._ids)

    def _find_neighbors(self, fp: np.ndarray, exclude_id: Optional[str] = None,
                        top_k: int = 5) -> List[Tuple[str, str, float]]:
        """Find top-k nearest neighbors by cosine similarity.

        Returns list of (canonical_id, formula, similarity).
        """
        self._ensure_loaded()
        if len(self._fingerprints) == 0:
            return []

        # Vectorized cosine similarity
        norms = np.linalg.norm(self._fingerprints, axis=1)
        fp_norm = np.linalg.norm(fp)
        if fp_norm == 0:
            return []

        sims = self._fingerprints @ fp / (norms * fp_norm + 1e-10)

        # Sort descending
        order = np.argsort(-sims)
        results = []
        for idx in order:
            cid = self._ids[idx]
            if exclude_id and cid == exclude_id:
                continue
            results.append((cid, self._formulas[idx], float(sims[idx])))
            if len(results) >= top_k:
                break
        return results

    def check_novelty(self, material: Material) -> NoveltyResult:
        """Assess novelty of a material against the corpus.

        Args:
            material: Material object (may or may not be in corpus).

        Returns:
            NoveltyResult with score, band, nearest neighbor, and reason codes.
        """
        self._ensure_loaded()
        fp = material_fingerprint(material)

        if fp.sum() == 0:
            return NoveltyResult(
                novelty_score=0.5,
                novelty_band="near_known",
                reason_codes=["insufficient_data_for_fingerprint"],
            )

        # Check exact formula+spacegroup match in corpus
        exact_match = False
        for m in self._corpus:
            if m.formula == material.formula and m.spacegroup == material.spacegroup:
                exact_match = True
                break

        neighbors = self._find_neighbors(fp, exclude_id=material.canonical_id, top_k=1)
        max_sim = neighbors[0][2] if neighbors else 0.0
        nearest_id = neighbors[0][0] if neighbors else None
        nearest_formula = neighbors[0][1] if neighbors else None

        return compute_novelty(
            max_similarity=max_sim,
            exact_formula_match=exact_match,
            nearest_id=nearest_id,
            nearest_formula=nearest_formula,
        )

    def check_novelty_from_params(self, formula: str, elements: List[str],
                                  spacegroup: Optional[int] = None,
                                  lattice_params: Optional[dict] = None,
                                  nsites: Optional[int] = None,
                                  band_gap: Optional[float] = None,
                                  formation_energy: Optional[float] = None
                                  ) -> NoveltyResult:
        """Assess novelty from raw parameters (no Material object needed)."""
        m = Material(
            formula=formula, elements=elements, n_elements=len(elements),
            spacegroup=spacegroup, lattice_params=lattice_params,
            nsites=nsites, band_gap=band_gap, formation_energy=formation_energy,
            source="query", source_id="ephemeral",
        )
        m.compute_canonical_id()
        return self.check_novelty(m)

    def check_exotic(self, material: Material) -> Tuple[NoveltyResult, ExoticResult]:
        """Full novelty + exotic assessment."""
        self._ensure_loaded()
        novelty = self.check_novelty(material)

        fp = material_fingerprint(material)
        neighbors = self._find_neighbors(fp, exclude_id=material.canonical_id, top_k=5)

        # Element rarity
        elem_rarity = element_rarity_score(
            material.elements, self._element_counts, self.corpus_size)

        # Structure rarity
        struct_rarity = spacegroup_rarity_score(
            material.spacegroup, self._sg_counts, self.corpus_size)

        # Neighbor sparsity: 1 - mean_similarity_to_top_5
        if neighbors:
            mean_sim = np.mean([s for _, _, s in neighbors])
            neighbor_sparsity = max(0.0, min(1.0, 1.0 - mean_sim))
        else:
            neighbor_sparsity = 1.0  # no neighbors = maximally sparse

        exotic = compute_exotic(
            novelty_score=novelty.novelty_score,
            element_rarity=elem_rarity,
            structure_rarity=struct_rarity,
            neighbor_sparsity=neighbor_sparsity,
        )

        return novelty, exotic

    def rank_exotic(self, top_k: int = 20) -> List[dict]:
        """Rank all corpus materials by exotic score. Returns top_k."""
        self._ensure_loaded()
        results = []

        for m in self._corpus:
            try:
                novelty, exotic = self.check_exotic(m)
                results.append({
                    "canonical_id": m.canonical_id,
                    "formula": m.formula,
                    "source": m.source,
                    "spacegroup": m.spacegroup,
                    "band_gap": m.band_gap,
                    "formation_energy": m.formation_energy,
                    "novelty": novelty.to_dict(),
                    "exotic": exotic.to_dict(),
                })
            except Exception as e:
                log.debug("Skipping %s: %s", m.canonical_id, e)
                continue

        results.sort(key=lambda x: -x["exotic"]["exotic_score"])
        return results[:top_k]

    def corpus_summary(self) -> dict:
        """Summary statistics for the corpus novelty distribution."""
        self._ensure_loaded()
        bands = {"known": 0, "near_known": 0, "novel_candidate": 0}
        scores = []

        for m in self._corpus:
            try:
                novelty = self.check_novelty(m)
                bands[novelty.novelty_band] += 1
                scores.append(novelty.novelty_score)
            except Exception:
                continue

        return {
            "corpus_size": self.corpus_size,
            "novelty_bands": bands,
            "mean_novelty_score": round(float(np.mean(scores)), 4) if scores else 0.0,
            "median_novelty_score": round(float(np.median(scores)), 4) if scores else 0.0,
            "disclaimer": "Novelty is relative to the current ingested corpus only, "
                          "not to all scientific literature.",
        }

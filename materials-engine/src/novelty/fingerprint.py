"""Fingerprint computation for novelty detection.

Phase III.A: Reproducible, CPU-friendly fingerprints for composition and structure.

Fingerprint dimensions:
  - Compositional: 94-dim (element frequency, normalized to sum=1)
  - Structural:    10-dim (spacegroup/230, a/20, b/20, c/20, α/180, β/180, γ/180,
                           nsites/50, band_gap/10, formation_energy shifted+scaled)
  - Combined:     104-dim (concatenation)

Distance metric: cosine similarity (dot product of L2-normalized vectors).
"""

import logging
import numpy as np
from typing import Optional, List

from ..features.crystal_graph import composition_fingerprint as _comp_fp, N_ELEM, ELEM_TO_IDX

log = logging.getLogger(__name__)

COMP_DIM = N_ELEM       # 94
STRUCT_DIM = 10
COMBINED_DIM = COMP_DIM + STRUCT_DIM  # 104


def compositional_fingerprint(elements: List[str]) -> np.ndarray:
    """94-dim normalized element frequency vector.

    Identical to features.crystal_graph.composition_fingerprint.
    Reused here for explicit novelty contract.
    """
    return _comp_fp(elements, n_dim=COMP_DIM)


def structural_fingerprint(spacegroup: Optional[int] = None,
                           lattice_params: Optional[dict] = None,
                           nsites: Optional[int] = None,
                           band_gap: Optional[float] = None,
                           formation_energy: Optional[float] = None) -> np.ndarray:
    """10-dim structural feature vector, normalized to [0,1].

    Components:
      [0] spacegroup / 230
      [1] a / 20 Å
      [2] b / 20 Å
      [3] c / 20 Å
      [4] alpha / 180°
      [5] beta / 180°
      [6] gamma / 180°
      [7] nsites / 50
      [8] band_gap / 10 eV
      [9] (formation_energy + 5) / 10
    """
    fp = np.zeros(STRUCT_DIM, dtype=np.float32)
    if spacegroup:
        fp[0] = spacegroup / 230.0
    if lattice_params:
        for i, k in enumerate(["a", "b", "c"]):
            v = lattice_params.get(k)
            if v:
                fp[1 + i] = min(v / 20.0, 1.0)
        for i, k in enumerate(["alpha", "beta", "gamma"]):
            v = lattice_params.get(k)
            if v:
                fp[4 + i] = v / 180.0
    if nsites:
        fp[7] = min(nsites / 50.0, 1.0)
    if band_gap is not None:
        fp[8] = min(band_gap / 10.0, 1.0)
    if formation_energy is not None:
        fp[9] = (formation_energy + 5.0) / 10.0
    return fp


def combined_fingerprint(elements: List[str],
                         spacegroup: Optional[int] = None,
                         lattice_params: Optional[dict] = None,
                         nsites: Optional[int] = None,
                         band_gap: Optional[float] = None,
                         formation_energy: Optional[float] = None) -> np.ndarray:
    """104-dim combined fingerprint: 94 compositional + 10 structural."""
    comp = compositional_fingerprint(elements)
    struct = structural_fingerprint(spacegroup, lattice_params, nsites,
                                    band_gap, formation_energy)
    return np.concatenate([comp, struct])


def material_fingerprint(material) -> np.ndarray:
    """Extract 104-dim fingerprint from a Material object."""
    return combined_fingerprint(
        elements=material.elements,
        spacegroup=material.spacegroup,
        lattice_params=material.lattice_params,
        nsites=material.nsites,
        band_gap=material.band_gap,
        formation_energy=material.formation_energy,
    )


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Returns 0.0 if either is zero."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def element_rarity_score(elements: List[str], corpus_element_counts: dict,
                         corpus_size: int) -> float:
    """How rare are the elements in this material relative to the corpus?

    Returns 0.0 (all elements very common) to 1.0 (all elements very rare).
    Uses inverse document frequency (IDF) normalized to [0,1].
    """
    if not elements or corpus_size == 0:
        return 0.0
    rarities = []
    for el in elements:
        count = corpus_element_counts.get(el, 0)
        # IDF: log(N / (1 + count)) / log(N), normalized to [0,1]
        idf = np.log(corpus_size / (1 + count)) / np.log(max(corpus_size, 2))
        rarities.append(float(np.clip(idf, 0.0, 1.0)))
    return float(np.mean(rarities))


def spacegroup_rarity_score(spacegroup: Optional[int],
                            corpus_sg_counts: dict,
                            corpus_size: int) -> float:
    """How rare is this spacegroup in the corpus?

    Returns 0.0 (very common) to 1.0 (never seen).
    """
    if spacegroup is None or corpus_size == 0:
        return 0.5  # unknown → moderate rarity
    count = corpus_sg_counts.get(spacegroup, 0)
    if count == 0:
        return 1.0
    idf = np.log(corpus_size / count) / np.log(max(corpus_size, 2))
    return float(np.clip(idf, 0.0, 1.0))

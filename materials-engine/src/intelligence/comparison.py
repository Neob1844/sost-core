"""Comparison table generation — multi-parameter material comparison.

Builds comparison tables between a query material and its nearest neighbors
or exact matches from the corpus.
"""

import logging
from typing import List, Optional

from ..schema import Material
from ..storage.db import MaterialsDB
from ..features.fingerprint_store import FingerprintStore
from ..retrieval.index import RetrievalIndex
from ..novelty.fingerprint import material_fingerprint, combined_fingerprint
from .applications import classify_applications
from .evidence import KNOWN, PREDICTED, PROXY, UNAVAILABLE, property_entry

log = logging.getLogger(__name__)


def build_comparison_table(query_material: Optional[Material],
                           query_formula: str,
                           query_elements: List[str],
                           query_spacegroup: Optional[int],
                           db: MaterialsDB,
                           store: Optional[FingerprintStore] = None,
                           top_k: int = 5) -> List[dict]:
    """Build a comparison table between query and corpus neighbors.

    Returns list of row dicts, one per compared material.
    """
    # Find neighbors
    neighbors = _find_neighbors(query_formula, query_elements,
                                query_spacegroup, query_material,
                                db, store, top_k)

    rows = []
    for cid, formula, similarity in neighbors:
        m = db.get_material(cid)
        if m is None:
            continue

        apps = classify_applications(
            band_gap=m.band_gap, band_gap_evidence=KNOWN if m.band_gap is not None else UNAVAILABLE,
            formation_energy=m.formation_energy,
            fe_evidence=KNOWN if m.formation_energy is not None else UNAVAILABLE,
            bulk_modulus=m.bulk_modulus, shear_modulus=m.shear_modulus,
            total_magnetization=m.total_magnetization,
            elements=m.elements)
        top_app = apps[0]["label"] if apps else "unknown"

        rows.append({
            "canonical_id": m.canonical_id,
            "formula": m.formula,
            "spacegroup": m.spacegroup,
            "similarity": round(similarity, 4),
            "band_gap": property_entry(m.band_gap, KNOWN if m.band_gap is not None else UNAVAILABLE),
            "formation_energy": property_entry(m.formation_energy, KNOWN if m.formation_energy is not None else UNAVAILABLE),
            "bulk_modulus": property_entry(m.bulk_modulus, KNOWN if m.bulk_modulus is not None else UNAVAILABLE),
            "shear_modulus": property_entry(m.shear_modulus, KNOWN if m.shear_modulus is not None else UNAVAILABLE),
            "total_magnetization": property_entry(m.total_magnetization, KNOWN if m.total_magnetization is not None else UNAVAILABLE),
            "structure_available": m.has_valid_structure or False,
            "likely_application": top_app,
            "evidence_level": KNOWN,
        })

    return rows


def _find_neighbors(formula, elements, spacegroup, material,
                    db, store, top_k):
    """Find nearest neighbors via retrieval index or brute-force."""
    fp = combined_fingerprint(elements, spacegroup=spacegroup)

    exclude_id = material.canonical_id if material else None

    # Try fast retrieval index
    if store is not None and store.is_loaded:
        idx = RetrievalIndex(store)
        idx.build()
        return idx.search(fp, top_k=top_k, exclude_id=exclude_id)

    # Fallback: brute-force from DB
    import numpy as np
    from ..novelty.fingerprint import material_fingerprint as mat_fp, cosine_similarity
    materials = db.list_materials(limit=5000)
    scored = []
    for m in materials:
        if exclude_id and m.canonical_id == exclude_id:
            continue
        m_fp = mat_fp(m)
        if m_fp.sum() == 0:
            continue
        sim = cosine_similarity(fp, m_fp)
        scored.append((m.canonical_id, m.formula, sim))
    scored.sort(key=lambda x: -x[2])
    return scored[:top_k]

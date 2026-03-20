"""Chemical space coverage analysis.

Phase IV.G: Analyzes what the corpus covers well vs poorly.
"""

import logging
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from ..storage.db import MaterialsDB
from .spec import CoverageSummary

log = logging.getLogger(__name__)

# Elements considered rare/exotic in typical DFT databases
RARE_ELEMENTS = {
    "Tc", "Pm", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Pa", "Np", "Pu",
    "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr",
}

# Common structural elements (usually over-represented)
COMMON_ELEMENTS = {"O", "H", "C", "N", "Fe", "Si", "Al", "Ca", "Na", "K", "Ti", "Mg"}


def analyze_coverage(db: MaterialsDB, limit: int = 100000) -> CoverageSummary:
    """Analyze chemical space coverage of the corpus."""
    materials = db.list_materials(limit=limit)

    elem_counter = Counter()
    sg_counter = Counter()
    n_elem_counter = Counter()
    elem_combos = Counter()

    for m in materials:
        for el in m.elements:
            elem_counter[el] += 1
        if m.spacegroup:
            sg_counter[m.spacegroup] += 1
        n_elem_counter[len(m.elements)] += 1
        if len(m.elements) <= 4:
            combo = tuple(sorted(m.elements))
            elem_combos[combo] += 1

    # Find rare elements present
    rare_present = sorted([el for el in elem_counter if el in RARE_ELEMENTS])

    # Find sparse regions (elements with < 50 occurrences)
    sparse = sorted([el for el, c in elem_counter.items() if c < 50], key=lambda e: elem_counter[e])

    # Find dense regions (elements with > 5000 occurrences)
    dense = sorted([el for el, c in elem_counter.items() if c > 5000], key=lambda e: -elem_counter[e])

    return CoverageSummary(
        total_materials=len(materials),
        total_elements_seen=len(elem_counter),
        total_spacegroups_seen=len(sg_counter),
        element_counts=dict(elem_counter.most_common(50)),
        spacegroup_counts=dict(sg_counter.most_common(30)),
        n_element_distribution=dict(sorted(n_elem_counter.items())),
        rare_elements=rare_present,
        dense_regions=dense[:15],
        sparse_regions=sparse[:20],
    )


def identify_exotic_niches(coverage: CoverageSummary) -> List[dict]:
    """Identify chemical niches where the corpus is weak but exotic materials may exist."""
    niches = []

    # Under-represented element families
    rare_earth = {"La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"}
    actinide = {"Th", "U", "Np", "Pu"}
    heavy_pnictide = {"Sb", "Bi"}
    heavy_chalcogen = {"Te", "Se"}

    for family_name, family_set in [("rare_earth", rare_earth), ("actinide", actinide),
                                      ("heavy_pnictide", heavy_pnictide), ("heavy_chalcogen", heavy_chalcogen)]:
        total = sum(coverage.element_counts.get(el, 0) for el in family_set)
        avg = total / max(1, len(family_set))
        if avg < 200:
            niches.append({
                "niche": family_name,
                "avg_count": round(avg),
                "coverage": "sparse",
                "exotic_potential": "high",
                "recommendation": f"Expand {family_name} materials — underrepresented, high exotic potential",
            })
        else:
            niches.append({
                "niche": family_name,
                "avg_count": round(avg),
                "coverage": "moderate" if avg < 1000 else "dense",
                "exotic_potential": "medium",
                "recommendation": f"Good coverage of {family_name} — focus on novel combinations",
            })

    # High n-element materials (4+ elements)
    high_n = sum(v for k, v in coverage.n_element_distribution.items() if k >= 4)
    total = coverage.total_materials
    if high_n / max(1, total) < 0.3:
        niches.append({
            "niche": "quaternary_plus",
            "count": high_n,
            "coverage": "sparse",
            "exotic_potential": "high",
            "recommendation": "Materials with 4+ elements are under-represented — high combinatorial novelty space",
        })

    return niches

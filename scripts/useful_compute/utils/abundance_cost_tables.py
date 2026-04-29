"""
Abundance / cost / toxicity / PGM tables.

Copied verbatim from internal source (abundance_scoring)
(constants only — no behavior change). Numbers MUST stay in sync with
the engine; if the engine table changes the worker pool sha256 must
change too. That's enforced by `formula_pool_v1.sha256`, the determinism
proof, and the matching test in tests/test_phase4b_heavy_handlers.py.

Stdlib only.
"""

import math
from typing import Dict


# Crustal abundance (ppm by mass) — USGS estimates
ABUNDANCE_PPM: Dict[str, float] = {
    "O": 461000, "Si": 282000, "Al": 82300, "Fe": 56300, "Ca": 41500,
    "Na": 23600, "Mg": 23300, "K": 20900, "Ti": 5650, "H": 1400,
    "P": 1050, "Mn": 950, "F": 585, "Ba": 425, "C": 200, "Sr": 370,
    "S": 350, "Zr": 165, "V": 120, "Cl": 145, "Cr": 102, "Ni": 84,
    "Zn": 70, "Cu": 60, "Co": 25, "Li": 20, "N": 19, "Nb": 20,
    "Ga": 19, "Pb": 14, "B": 10, "Th": 9.6, "Mo": 1.2, "W": 1.3,
    "Sn": 2.3, "As": 1.8, "U": 2.7, "Ge": 1.5, "Sb": 0.2, "Cd": 0.15,
    "In": 0.25, "Ag": 0.075, "Se": 0.05, "Hg": 0.085, "Bi": 0.0085,
    "Te": 0.001, "Au": 0.004, "Pt": 0.005, "Pd": 0.015, "Rh": 0.001,
    "Ir": 0.001, "Ru": 0.001, "Os": 0.0015, "Re": 0.0007,
    "La": 39, "Ce": 66.5, "Y": 33, "Nd": 41.5, "Sc": 22,
}

# Approximate cost $/kg — order of magnitude
COST_USD_KG: Dict[str, float] = {
    "O": 0.2, "Si": 2, "Al": 2.5, "Fe": 0.5, "Ca": 3, "Na": 0.3,
    "Mg": 3, "K": 1, "Ti": 10, "H": 3, "P": 2, "Mn": 2, "C": 0.5,
    "S": 0.1, "Cr": 10, "Ni": 18, "Zn": 3, "Cu": 8, "Co": 50,
    "Li": 70, "N": 0.5, "Mo": 40, "W": 35, "Sn": 25, "V": 30,
    "Nb": 75, "B": 5, "Pb": 2, "Ga": 300, "Ge": 1000, "In": 400,
    "Ag": 800, "Au": 60000, "Pt": 30000, "Pd": 40000, "Rh": 150000,
    "Ir": 50000, "Ru": 15000, "Se": 50, "Te": 100, "Bi": 15,
    "La": 5, "Ce": 5, "Y": 30, "Nd": 60, "Sc": 3500,
    "Zr": 30, "Ba": 0.3, "Sr": 5, "F": 2,
}

TOXIC_ELEMENTS = {"Pb", "Cd", "Hg", "As", "Tl", "Be", "Cr6+", "Se", "Sb"}

PGM_ELEMENTS = {"Pt", "Pd", "Rh", "Ir", "Ru", "Os"}

ABUNDANT_REPLACEMENTS = {
    "Fe", "Ni", "Mn", "Co", "Cu", "Ti", "Mo", "W",
    "Al", "C", "N", "S", "Si", "Mg", "Ca", "Zn", "V",
}


def abundance_score_from_counts(counts: Dict[str, int]) -> float:
    """Score 0-1 based on elemental abundance. 1 = all abundant, 0 = all rare.

    Logic mirrors abundance_scoring.abundance_score, but takes the
    pre-parsed counts dict (avoids re-parsing in tight loops).
    """
    if not counts:
        return 0.5
    scores = []
    for el, count in counts.items():
        ppm = ABUNDANCE_PPM.get(el, 0.01)
        s = min(1.0, max(0.0, math.log10(max(ppm, 0.001)) / 5.0))
        scores.extend([s] * count)
    return sum(scores) / len(scores) if scores else 0.5


def cost_score_from_counts(counts: Dict[str, int]) -> float:
    """Score 0-1 based on elemental cost. 1 = cheap, 0 = expensive."""
    if not counts:
        return 0.5
    scores = []
    for el, count in counts.items():
        usd = COST_USD_KG.get(el, 100)
        s = max(0.0, min(1.0, 1.0 - (math.log10(max(usd, 0.01)) + 1) / 6.0))
        scores.extend([s] * count)
    return sum(scores) / len(scores) if scores else 0.5


def toxicity_penalty_from_counts(counts: Dict[str, int]) -> float:
    """Penalty 0-1 for toxic elements."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    toxic_count = sum(c for el, c in counts.items() if el in TOXIC_ELEMENTS)
    return min(1.0, toxic_count / total)


def pgm_content_from_counts(counts: Dict[str, int]) -> float:
    """Fraction of atoms that are PGM (0-1)."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    pgm_count = sum(c for el, c in counts.items() if el in PGM_ELEMENTS)
    return pgm_count / total


def abundant_replacement_ratio_from_counts(counts: Dict[str, int]) -> float:
    """Fraction of atoms from abundant replacement elements."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    abundant = sum(c for el, c in counts.items() if el in ABUNDANT_REPLACEMENTS)
    return abundant / total

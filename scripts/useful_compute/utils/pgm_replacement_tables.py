"""
PGM replacement tables + family detection helper.

Mirror of internal source (pgm_replacement_engine) with
behavior preserved. Stdlib only.

The Heavy worker computes pgm_replacement_score over millions of
formulas; tight loops need stdlib-friendly data structures. The output
of `pgm_replacement_score_for` MUST be byte-identical to the engine's
when serialised through canonical_hash.
"""

from typing import Dict, List

from .abundance_cost_tables import (
    ABUNDANCE_PPM, COST_USD_KG, TOXIC_ELEMENTS, PGM_ELEMENTS,
    ABUNDANT_REPLACEMENTS,
    abundance_score_from_counts, cost_score_from_counts,
    pgm_content_from_counts,
)


# Catalytic transition metals (cheap alternatives to PGM)
CATALYTIC_TM = {"Fe", "Ni", "Mn", "Co", "Cu", "Ti", "Mo", "W", "V", "Cr", "Ce", "Zr"}

# Family detection — keyed lambdas (closures) on a frozen element set.
# Order matters for tie-breaking; we keep the engine's insertion order.
_FAMILY_TESTS = (
    ("perovskite", lambda els: len(els) >= 3 and "O" in els
        and any(e in els for e in {"La", "Sr", "Ba", "Ca", "Y", "Ce", "Nd"})),
    ("spinel", lambda els: len(els) >= 3 and "O" in els
        and sum(1 for e in els if e in CATALYTIC_TM) >= 2),
    ("fe_n_c", lambda els: "Fe" in els and "N" in els
        and ("C" in els or len(els) <= 3)),
    ("sulfide", lambda els: "S" in els and any(e in els for e in CATALYTIC_TM)),
    ("nitride", lambda els: "N" in els and any(e in els for e in CATALYTIC_TM)
        and "O" not in els),
    ("carbide", lambda els: "C" in els and any(e in els for e in CATALYTIC_TM)
        and "O" not in els and "N" not in els),
    ("phosphide", lambda els: "P" in els and any(e in els for e in CATALYTIC_TM)),
    ("oxide_catalyst", lambda els: "O" in els and any(e in els for e in CATALYTIC_TM)),
)


def detect_family_from_elem_set(elem_set: frozenset) -> List[str]:
    """Return list of family names matching the element set.

    Mirrors pgm_replacement_engine.detect_family. If none match, returns
    `["unknown"]` (sorted-by-detection-order, deterministic).
    """
    families = [name for name, test in _FAMILY_TESTS if test(elem_set)]
    return families if families else ["unknown"]


def pgm_replacement_score_from_counts(formula: str,
                                      counts: Dict[str, int]) -> Dict:
    """Score a material as a PGM replacement candidate (mirror of
    pgm_replacement_engine.pgm_replacement_score).

    Takes pre-parsed counts to avoid re-parsing in the heavy loop.
    """
    elem_set = frozenset(counts.keys())
    total_atoms = sum(counts.values())

    if total_atoms == 0:
        return {
            "formula": formula,
            "pgm_free": False,
            "replacement_score": 0.0,
        }

    pgm_frac = pgm_content_from_counts(counts)
    is_pgm_free = pgm_frac == 0.0

    cat_count = sum(c for el, c in counts.items() if el in CATALYTIC_TM)
    catalytic_ratio = cat_count / total_atoms

    abund = abundance_score_from_counts(counts)
    cost = cost_score_from_counts(counts)

    families = detect_family_from_elem_set(elem_set)
    if any(f in families for f in ("perovskite", "spinel", "fe_n_c")):
        family_bonus = 0.15
    elif any(f in families for f in ("sulfide", "nitride", "phosphide")):
        family_bonus = 0.10
    elif "oxide_catalyst" in families:
        family_bonus = 0.05
    else:
        family_bonus = 0.0

    toxic_count = sum(c for el, c in counts.items() if el in TOXIC_ELEMENTS)
    toxic_frac = toxic_count / total_atoms

    if not is_pgm_free:
        replacement_score = 0.0
    else:
        replacement_score = (
            catalytic_ratio * 0.25
            + abund * 0.20
            + cost * 0.20
            + family_bonus
            + (1.0 - toxic_frac) * 0.10
            + min(0.10, len(elem_set) * 0.02)
        )
        replacement_score = round(min(1.0, replacement_score), 4)

    return {
        "formula": formula,
        "pgm_free": is_pgm_free,
        "pgm_content": round(pgm_frac, 4),
        "catalytic_tm_ratio": round(catalytic_ratio, 4),
        "abundance": round(abund, 4),
        "cost": round(cost, 4),
        "families": families,
        "family_bonus": round(family_bonus, 4),
        "toxic_fraction": round(toxic_frac, 4),
        "replacement_score": replacement_score,
    }

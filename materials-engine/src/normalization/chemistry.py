"""Robust chemical formula parsing.

Uses pymatgen.core.Composition as primary parser with regex fallback.
Tracks which method succeeded for provenance.
"""

import re
import logging
from typing import List, Tuple

log = logging.getLogger(__name__)

try:
    from pymatgen.core import Composition
    HAS_PYMATGEN = True
except ImportError:
    HAS_PYMATGEN = False
    log.warning("pymatgen not installed — using regex fallback for formula parsing")


def parse_formula(formula: str) -> Tuple[List[str], str]:
    """Parse a chemical formula into sorted element list.

    Returns (elements, method) where method is 'pymatgen' or 'regex_fallback'.
    On total failure returns ([], 'failed').
    """
    if not formula or not formula.strip():
        return [], "empty"

    formula = formula.strip()

    # Try pymatgen first
    if HAS_PYMATGEN:
        try:
            comp = Composition(formula)
            elements = sorted(str(e) for e in comp.elements)
            if elements:
                return elements, "pymatgen"
        except Exception:
            log.debug("pymatgen failed to parse '%s', trying regex", formula)

    # Regex fallback
    elements = sorted(set(re.findall(r'[A-Z][a-z]?', formula)))
    if elements:
        return elements, "regex_fallback"

    log.warning("Failed to parse formula '%s' with any method", formula)
    return [], "failed"

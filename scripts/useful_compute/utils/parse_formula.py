"""
Formula parser — copied verbatim (logic-equivalent) from
internal source (abundance_scoring):parse_formula.

The Heavy worker is a public, sandboxed mirror of the materials-engine
scoring layer. It MUST stay in sync with the engine's parse_formula
behavior, because hashes are pinned across both sides for cross-worker
verification.

Stdlib only. No regex tricks beyond what the engine already uses.
"""

import re
from typing import Dict

_FORMULA_PATTERN = re.compile(r'([A-Z][a-z]?)(\d*)')


def parse_formula(formula: str) -> Dict[str, int]:
    """Parse chemical formula to element counts.

    Mirror of `abundance_scoring.parse_formula`. Returns insertion-ordered
    dict of element -> integer count. Empty string in / parse failure
    yields {}.
    """
    elements: Dict[str, int] = {}
    if not formula:
        return elements
    for match in _FORMULA_PATTERN.finditer(formula):
        el = match.group(1)
        if not el:
            continue
        count = int(match.group(2)) if match.group(2) else 1
        elements[el] = elements.get(el, 0) + count
    return elements

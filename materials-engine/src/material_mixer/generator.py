"""Candidate generator — produces theoretical materials from two parents."""
import re
from collections import OrderedDict
from .rules import get_substitutes, valence_compatible, is_valid_candidate


def parse_formula(formula):
    """Parse chemical formula into {element: count} dict."""
    pattern = r'([A-Z][a-z]?)(\d*)'
    elements = OrderedDict()
    for match in re.finditer(pattern, formula):
        elem, count = match.group(1), match.group(2)
        if elem:
            elements[elem] = elements.get(elem, 0) + (int(count) if count else 1)
    return elements


def formula_from_dict(comp):
    """Convert {element: count} dict to formula string."""
    parts = []
    for elem, count in sorted(comp.items()):
        parts.append(elem + (str(count) if count > 1 else ""))
    return "".join(parts)


def generate_candidates(parent_a_formula, parent_b_formula, max_candidates=20):
    """Generate theoretical candidates from two parent materials.

    Strategies:
    1. Element substitution (from parent A, using substitution families)
    2. Composition interpolation (average of A and B)
    3. Single-site doping (insert element from B into A)
    4. Mixed-parent generation (combine elements from both)

    Returns list of candidate dicts.
    """
    comp_a = parse_formula(parent_a_formula)
    comp_b = parse_formula(parent_b_formula)

    if not comp_a or not comp_b:
        return []

    candidates = []
    seen_formulas = {parent_a_formula, parent_b_formula}

    # Strategy 1: Element substitution
    for elem_a in list(comp_a.keys()):
        subs = get_substitutes(elem_a, max_subs=3)
        for sub in subs:
            if sub in comp_a:
                continue
            new_comp = dict(comp_a)
            new_comp[sub] = new_comp.pop(elem_a)
            formula = formula_from_dict(new_comp)
            if formula not in seen_formulas and is_valid_candidate(list(new_comp.keys()), list(new_comp.values())):
                seen_formulas.add(formula)
                candidates.append({
                    "formula": formula,
                    "elements": list(new_comp.keys()),
                    "method": "element_substitution",
                    "description": f"Replaced {elem_a} with {sub} in {parent_a_formula}",
                    "parent_a": parent_a_formula,
                    "parent_b": parent_b_formula,
                })

    # Strategy 2: Single-site doping (add element from B into A)
    for elem_b in comp_b:
        if elem_b not in comp_a:
            new_comp = dict(comp_a)
            new_comp[elem_b] = 1  # single-site doping
            formula = formula_from_dict(new_comp)
            if formula not in seen_formulas and is_valid_candidate(list(new_comp.keys()), list(new_comp.values())):
                seen_formulas.add(formula)
                candidates.append({
                    "formula": formula,
                    "elements": list(new_comp.keys()),
                    "method": "single_site_doping",
                    "description": f"Doped {parent_a_formula} with {elem_b} from {parent_b_formula}",
                    "parent_a": parent_a_formula,
                    "parent_b": parent_b_formula,
                })

    # Strategy 3: Mixed-parent generation (combine unique elements)
    all_elems = set(comp_a.keys()) | set(comp_b.keys())
    if 2 <= len(all_elems) <= 5:
        mixed = {}
        for elem in all_elems:
            ca = comp_a.get(elem, 0)
            cb = comp_b.get(elem, 0)
            mixed[elem] = max(1, (ca + cb + 1) // 2)
        formula = formula_from_dict(mixed)
        if formula not in seen_formulas:
            seen_formulas.add(formula)
            candidates.append({
                "formula": formula,
                "elements": list(mixed.keys()),
                "method": "mixed_parent",
                "description": f"Combined elements from {parent_a_formula} and {parent_b_formula}",
                "parent_a": parent_a_formula,
                "parent_b": parent_b_formula,
            })

    # Strategy 4: Cross-substitution (replace element in A with element from B)
    for elem_a in comp_a:
        for elem_b in comp_b:
            if elem_a != elem_b and elem_b not in comp_a:
                if valence_compatible(elem_a, elem_b):
                    new_comp = dict(comp_a)
                    new_comp[elem_b] = new_comp.pop(elem_a)
                    formula = formula_from_dict(new_comp)
                    if formula not in seen_formulas and is_valid_candidate(list(new_comp.keys()), list(new_comp.values())):
                        seen_formulas.add(formula)
                        candidates.append({
                            "formula": formula,
                            "elements": list(new_comp.keys()),
                            "method": "cross_substitution",
                            "description": f"Replaced {elem_a} in {parent_a_formula} with {elem_b} from {parent_b_formula}",
                            "parent_a": parent_a_formula,
                            "parent_b": parent_b_formula,
                        })

    return candidates[:max_candidates]

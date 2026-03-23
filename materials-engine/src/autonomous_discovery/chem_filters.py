"""Chemical plausibility filters for candidate materials."""
import re

MAX_ELEMENTS = 6
MAX_ATOMS_PER_FORMULA = 24
VALID_ELEMENTS = {
    "H","He","Li","Be","B","C","N","O","F","Ne","Na","Mg","Al","Si","P","S","Cl","Ar",
    "K","Ca","Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn","Ga","Ge","As","Se","Br",
    "Kr","Rb","Sr","Y","Zr","Nb","Mo","Ru","Rh","Pd","Ag","Cd","In","Sn","Sb","Te","I",
    "Xe","Cs","Ba","La","Ce","Pr","Nd","Sm","Eu","Gd","Tb","Dy","Ho","Er","Tm","Yb","Lu",
    "Hf","Ta","W","Re","Os","Ir","Pt","Au","Hg","Tl","Pb","Bi",
}
# Elements that are radioactive/transuranic or impractical
FORBIDDEN_ELEMENTS = {"Tc","Pm","Po","At","Rn","Fr","Ra","Ac","Th","Pa","U","Np","Pu"}

# Noble gases don't form compounds (mostly)
NOBLE_GASES = {"He","Ne","Ar","Kr","Xe"}


def parse_formula(formula):
    """Parse formula -> {element: count}."""
    comp = {}
    for match in re.finditer(r'([A-Z][a-z]?)(\d*)', formula):
        elem, count = match.group(1), match.group(2)
        if elem:
            comp[elem] = comp.get(elem, 0) + (int(count) if count else 1)
    return comp


def filter_candidate(formula, parent_a=None, parent_b=None):
    """Apply chemical plausibility filters. Returns (pass, reason) tuple."""
    if not formula or len(formula) < 1:
        return False, "empty_formula"

    comp = parse_formula(formula)
    if not comp:
        return False, "unparseable_formula"

    elements = set(comp.keys())
    total_atoms = sum(comp.values())

    # Element validity
    invalid = elements - VALID_ELEMENTS
    if invalid:
        return False, f"invalid_elements:{','.join(invalid)}"

    # Forbidden/radioactive elements
    forbidden = elements & FORBIDDEN_ELEMENTS
    if forbidden:
        return False, f"forbidden_elements:{','.join(sorted(forbidden))}"

    # Noble gas check (noble gases don't form stable compounds)
    nobles = elements & NOBLE_GASES
    if nobles and len(elements) > 1:
        return False, f"noble_gas_compound:{','.join(nobles)}"

    # Complexity limits
    if len(elements) > MAX_ELEMENTS:
        return False, f"too_many_elements:{len(elements)}"
    if total_atoms > MAX_ATOMS_PER_FORMULA:
        return False, f"too_many_atoms:{total_atoms}"

    # Single-element pure metals are boring unless specific
    if len(elements) == 1 and total_atoms == 1:
        return False, "trivial_single_element"

    # Identical to parent
    if parent_a and formula == parent_a:
        return False, "identical_to_parent_a"
    if parent_b and formula == parent_b:
        return False, "identical_to_parent_b"

    # Degenerate (all same element)
    if len(elements) == 1 and total_atoms > 8:
        return False, "degenerate_homoatomic"

    # Unreasonable stoichiometry (any element > 12)
    if any(c > 12 for c in comp.values()):
        return False, "extreme_stoichiometry"

    return True, "passed"

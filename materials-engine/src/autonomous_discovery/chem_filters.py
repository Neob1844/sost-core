"""Chemical plausibility filters for candidate materials — Phase II hardened."""
import re
from collections import OrderedDict

MAX_ELEMENTS = 5
MAX_ATOMS_PER_FORMULA = 16
VALID_ELEMENTS = {
    "H","Li","Be","B","C","N","O","F","Na","Mg","Al","Si","P","S","Cl",
    "K","Ca","Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn","Ga","Ge","As","Se","Br",
    "Rb","Sr","Y","Zr","Nb","Mo","Ru","Rh","Pd","Ag","Cd","In","Sn","Sb","Te","I",
    "Cs","Ba","La","Ce","Pr","Nd","Sm","Eu","Gd","Tb","Dy","Ho","Er","Yb","Lu",
    "Hf","Ta","W","Re","Os","Ir","Pt","Au","Tl","Pb","Bi",
}
NOBLE_GASES = {"He","Ne","Ar","Kr","Xe","Rn"}

# Common oxidation states for charge-balance heuristic
COMMON_OX = {
    "Li":1,"Na":1,"K":1,"Rb":1,"Cs":1,"Ag":1,"Cu":1,
    "Be":2,"Mg":2,"Ca":2,"Sr":2,"Ba":2,"Zn":2,"Cd":2,"Fe":2,"Co":2,"Ni":2,"Cu":2,"Mn":2,"Pb":2,"Sn":2,
    "Al":3,"Ga":3,"In":3,"Fe":3,"Cr":3,"Co":3,"La":3,"Ce":3,"Y":3,"Sc":3,"Bi":3,"Sb":3,
    "Si":4,"Ge":4,"Ti":4,"Zr":4,"Hf":4,"Sn":4,"Mn":4,"V":4,"Mo":4,"W":4,"Ce":4,
    "V":5,"Nb":5,"Ta":5,"P":5,"As":5,"Sb":5,
    "Cr":6,"Mo":6,"W":6,"S":6,"Se":6,"Te":6,
    "O":-2,"S":-2,"Se":-2,"Te":-2,"N":-3,"F":-1,"Cl":-1,"Br":-1,"I":-1,
    "C":4,"B":3,"H":1,
}

# Anions that typically appear in compounds
ANIONS = {"O","S","Se","Te","N","F","Cl","Br","I"}
# Cations
CATIONS = VALID_ELEMENTS - ANIONS - NOBLE_GASES


def parse_formula(formula):
    """Parse formula -> OrderedDict {element: count}."""
    comp = OrderedDict()
    for match in re.finditer(r'([A-Z][a-z]?)(\d*)', formula):
        elem, count = match.group(1), match.group(2)
        if elem:
            comp[elem] = comp.get(elem, 0) + (int(count) if count else 1)
    return comp


_ANION_SET = {"O", "S", "Se", "Te", "N", "F", "Cl", "Br", "I", "P", "As", "Sb"}

def normalize_formula(formula):
    """Canonical formula: cations first (alphabetical), then anions (alphabetical).

    Produces standard chemical notation: LiCoO2, InAs, SiN, Zn2O, TiZnO2.
    """
    comp = parse_formula(formula)
    if not comp:
        return formula
    cations = sorted(e for e in comp if e not in _ANION_SET)
    anions = sorted(e for e in comp if e in _ANION_SET)
    parts = []
    for elem in cations + anions:
        parts.append(elem + (str(comp[elem]) if comp[elem] > 1 else ""))
    return "".join(parts)


def formulas_equivalent(f1, f2):
    """Check if two formulas represent the same composition."""
    return normalize_formula(f1) == normalize_formula(f2)


def check_charge_balance(comp):
    """Heuristic charge balance check. Returns (plausible, reason)."""
    cations = {e: c for e, c in comp.items() if e in CATIONS}
    anions = {e: c for e, c in comp.items() if e in ANIONS}

    if not anions:
        # All-metal compound — plausible (alloys, intermetallics)
        return True, "all_metal"
    if not cations:
        return False, "no_cations"

    # Estimate total positive and negative charge
    pos_charge = 0
    for elem, count in cations.items():
        ox = COMMON_OX.get(elem, 3)  # default +3
        pos_charge += abs(ox) * count

    neg_charge = 0
    for elem, count in anions.items():
        ox = COMMON_OX.get(elem, -2)
        neg_charge += abs(ox) * count

    if neg_charge == 0:
        return True, "no_anion_charge"

    ratio = pos_charge / neg_charge
    if 0.5 <= ratio <= 2.0:
        return True, "balanced"
    elif 0.3 <= ratio <= 3.0:
        return True, "marginal_balance"
    else:
        return False, f"charge_imbalance_ratio_{ratio:.1f}"


def filter_candidate(formula, parent_a=None, parent_b=None):
    """Apply hardened chemical plausibility filters. Returns (pass, reason)."""
    if not formula or len(formula) < 1:
        return False, "empty_formula"

    comp = parse_formula(formula)
    if not comp:
        return False, "unparseable"

    elements = set(comp.keys())
    total_atoms = sum(comp.values())
    norm = normalize_formula(formula)

    # Element validity
    invalid = elements - VALID_ELEMENTS - NOBLE_GASES
    if invalid:
        return False, f"invalid_elements:{','.join(sorted(invalid))}"

    # Noble gas compounds
    if elements & NOBLE_GASES:
        return False, "noble_gas_compound"

    # Complexity
    if len(elements) > MAX_ELEMENTS:
        return False, f"too_many_elements:{len(elements)}"
    if total_atoms > MAX_ATOMS_PER_FORMULA:
        return False, f"too_many_atoms:{total_atoms}"

    # Trivial single element
    if len(elements) == 1:
        return False, "trivial_single_element"

    # Parent identity (normalized)
    if parent_a and formulas_equivalent(formula, parent_a):
        return False, "identical_to_parent_a"
    if parent_b and formulas_equivalent(formula, parent_b):
        return False, "identical_to_parent_b"

    # Degenerate homoatomic
    if len(elements) == 1 and total_atoms > 4:
        return False, "degenerate_homoatomic"

    # Extreme stoichiometry
    if any(c > 8 for c in comp.values()):
        return False, "extreme_stoichiometry"

    # Anion-only compounds (no cations)
    if elements and all(e in ANIONS for e in elements):
        return False, "anion_only_compound"

    # Charge balance heuristic
    balanced, reason = check_charge_balance(comp)
    if not balanced:
        return False, f"charge_imbalance:{reason}"

    # Ratio sanity: if binary, check ratio isn't > 1:6
    if len(elements) == 2:
        counts = list(comp.values())
        ratio = max(counts) / min(counts)
        if ratio > 6:
            return False, f"extreme_binary_ratio:{ratio:.1f}"

    return True, "passed"

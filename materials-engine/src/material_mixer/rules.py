"""Chemical rules and substitution families for candidate generation."""

# Elements that can substitute for each other in crystal structures
SUBSTITUTION_FAMILIES = {
    "alkali": ["Li", "Na", "K", "Rb", "Cs"],
    "alkaline_earth": ["Be", "Mg", "Ca", "Sr", "Ba"],
    "3d_transition": ["Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn"],
    "4d_transition": ["Zr", "Nb", "Mo", "Ru", "Rh", "Pd", "Ag", "Cd"],
    "5d_transition": ["Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au"],
    "group_13": ["B", "Al", "Ga", "In", "Tl"],
    "group_14": ["C", "Si", "Ge", "Sn", "Pb"],
    "group_15": ["N", "P", "As", "Sb", "Bi"],
    "group_16": ["O", "S", "Se", "Te"],
    "lanthanide": ["La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy"],
    "rare_earth": ["Y", "Sc", "La", "Ce", "Nd"],
}

# Common oxidation states (for valence checking)
COMMON_VALENCES = {
    "Li": [1], "Na": [1], "K": [1], "Mg": [2], "Ca": [2], "Ba": [2],
    "Al": [3], "Ga": [3], "In": [3], "Si": [4], "Ge": [4], "Sn": [2, 4],
    "Ti": [3, 4], "V": [2, 3, 4, 5], "Cr": [2, 3, 6], "Mn": [2, 3, 4, 7],
    "Fe": [2, 3], "Co": [2, 3], "Ni": [2, 3], "Cu": [1, 2], "Zn": [2],
    "Zr": [4], "Nb": [3, 5], "Mo": [4, 6], "W": [4, 6],
    "O": [-2], "S": [-2], "Se": [-2], "N": [-3], "P": [-3, 3, 5],
    "F": [-1], "Cl": [-1], "Br": [-1],
}

# Maximum elements in a valid candidate
MAX_ELEMENTS = 6


def get_substitutes(element, max_subs=3):
    """Find chemically reasonable substitutes for an element."""
    subs = []
    for family, members in SUBSTITUTION_FAMILIES.items():
        if element in members:
            for m in members:
                if m != element and len(subs) < max_subs:
                    subs.append(m)
    return subs


def valence_compatible(elem_a, elem_b):
    """Check if two elements share at least one common oxidation state."""
    va = set(COMMON_VALENCES.get(elem_a, []))
    vb = set(COMMON_VALENCES.get(elem_b, []))
    if not va or not vb:
        return True  # unknown = allow
    return bool(va & vb)


def is_valid_candidate(elements, counts):
    """Basic validity check for a candidate composition."""
    if not elements or not counts:
        return False
    if len(elements) > MAX_ELEMENTS:
        return False
    if len(elements) != len(counts):
        return False
    if any(c <= 0 for c in counts):
        return False
    if len(set(elements)) != len(elements):
        return False  # no duplicate elements
    return True

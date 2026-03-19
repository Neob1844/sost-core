"""Physical descriptor computation from structure and composition.

Phase III.I: Computes REAL descriptors from crystal structure via pymatgen.
Every descriptor is tagged with evidence level and method.

Evidence levels:
  computed_from_structure — derived from real crystal structure geometry
  computed_from_composition — derived from formula/element properties
  proxy — heuristic estimate, not from direct calculation
  unavailable — cannot compute
"""

import logging
import numpy as np
from typing import Optional, List, Dict

log = logging.getLogger(__name__)

COMPUTED_STRUCTURE = "computed_from_structure"
COMPUTED_COMPOSITION = "computed_from_composition"
PROXY = "proxy"
UNAVAILABLE = "unavailable"

# Element classification
METALS = {
    "Li", "Be", "Na", "Mg", "Al", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn",
    "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Rb", "Sr", "Y", "Zr", "Nb", "Mo",
    "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Cs", "Ba", "La", "Ce", "Pr",
    "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf",
    "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Th",
    "U", "Np", "Pu",
}
METALLOIDS = {"B", "Si", "Ge", "As", "Sb", "Te", "Po"}
NONMETALS = {"H", "He", "C", "N", "O", "F", "Ne", "P", "S", "Cl", "Ar",
             "Se", "Br", "Kr", "I", "Xe", "Rn", "At"}
RARE_EARTHS = {"La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy",
               "Ho", "Er", "Tm", "Yb", "Lu"}
TRANSITION_METALS = {
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd",
    "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
}


def _prop(value, evidence: str, unit: str = "", method: str = "",
          note: str = "") -> dict:
    """Standard descriptor entry."""
    return {"value": value, "evidence": evidence, "unit": unit,
            "method": method, "note": note}


def compute_descriptors(structure=None, formula: str = "",
                        elements: Optional[List[str]] = None) -> dict:
    """Compute all available physical descriptors.

    Args:
        structure: pymatgen Structure object (may be None)
        formula: chemical formula string
        elements: list of element symbols

    Returns dict with categorized descriptors.
    """
    desc = {}
    elements = elements or []

    # --- Composition descriptors (always available) ---
    desc.update(_composition_descriptors(formula, elements))

    # --- Structure descriptors (only if structure available) ---
    if structure is not None:
        desc.update(_structure_descriptors(structure))
        desc.update(_bond_descriptors(structure))
        desc.update(_symmetry_descriptors(structure))
    else:
        desc["density_g_cm3"] = _prop(None, UNAVAILABLE,
                                       note="No structure available for density calculation")
        desc["volume_A3"] = _prop(None, UNAVAILABLE)
        desc["volume_per_atom_A3"] = _prop(None, UNAVAILABLE)

    return desc


def _composition_descriptors(formula: str, elements: List[str]) -> dict:
    """Descriptors from composition only — no structure needed."""
    desc = {}
    n = len(elements) if elements else 0

    desc["nelements"] = _prop(n, COMPUTED_COMPOSITION, method="len(elements)")

    # Formula weight
    try:
        from pymatgen.core import Composition
        comp = Composition(formula)
        desc["formula_weight"] = _prop(
            round(comp.weight, 2), COMPUTED_COMPOSITION,
            unit="g/mol", method="pymatgen.Composition.weight")
    except Exception:
        desc["formula_weight"] = _prop(None, UNAVAILABLE)

    # Element property statistics
    try:
        from pymatgen.core import Element as PmgElement
        atomic_nums = []
        masses = []
        electronegativities = []
        covalent_radii = []
        for el_str in elements:
            try:
                el = PmgElement(el_str)
                atomic_nums.append(el.Z)
                masses.append(el.atomic_mass)
                if el.X and el.X == el.X:  # check not NaN
                    electronegativities.append(el.X)
                if el.atomic_radius:
                    covalent_radii.append(float(el.atomic_radius))
            except Exception:
                continue

        if atomic_nums:
            desc["atomic_number_mean"] = _prop(
                round(float(np.mean(atomic_nums)), 2), COMPUTED_COMPOSITION,
                method="mean(Z)")
            desc["atomic_mass_mean"] = _prop(
                round(float(np.mean(masses)), 2), COMPUTED_COMPOSITION,
                unit="amu", method="mean(atomic_mass)")
        if electronegativities:
            desc["electronegativity_mean"] = _prop(
                round(float(np.mean(electronegativities)), 3), COMPUTED_COMPOSITION,
                method="mean(Pauling X)")
            desc["electronegativity_spread"] = _prop(
                round(float(np.ptp(electronegativities)), 3), COMPUTED_COMPOSITION,
                method="range(Pauling X)")
        if covalent_radii:
            desc["covalent_radius_mean"] = _prop(
                round(float(np.mean(covalent_radii)), 3), COMPUTED_COMPOSITION,
                unit="Å", method="mean(covalent_radius)")
    except Exception:
        pass

    # Element class fractions
    if n > 0:
        desc["fraction_metal"] = _prop(
            round(len(set(elements) & METALS) / n, 3), COMPUTED_COMPOSITION)
        desc["fraction_metalloid"] = _prop(
            round(len(set(elements) & METALLOIDS) / n, 3), COMPUTED_COMPOSITION)
        desc["fraction_nonmetal"] = _prop(
            round(len(set(elements) & NONMETALS) / n, 3), COMPUTED_COMPOSITION)
        desc["fraction_rare_earth"] = _prop(
            round(len(set(elements) & RARE_EARTHS) / n, 3), COMPUTED_COMPOSITION)
        desc["fraction_transition_metal"] = _prop(
            round(len(set(elements) & TRANSITION_METALS) / n, 3), COMPUTED_COMPOSITION)

    return desc


def _structure_descriptors(structure) -> dict:
    """Descriptors from crystal structure geometry."""
    desc = {}
    try:
        n_sites = len(structure)
        vol = structure.volume
        desc["nsites"] = _prop(n_sites, COMPUTED_STRUCTURE, method="len(structure)")
        desc["volume_A3"] = _prop(
            round(vol, 2), COMPUTED_STRUCTURE, unit="ų", method="structure.volume")
        desc["volume_per_atom_A3"] = _prop(
            round(vol / n_sites, 2) if n_sites > 0 else None,
            COMPUTED_STRUCTURE, unit="ų/atom")
        desc["density_g_cm3"] = _prop(
            round(structure.density, 4), COMPUTED_STRUCTURE,
            unit="g/cm³", method="structure.density")

        # Lattice parameters
        latt = structure.lattice
        desc["lattice_a"] = _prop(round(latt.a, 4), COMPUTED_STRUCTURE, unit="Å")
        desc["lattice_b"] = _prop(round(latt.b, 4), COMPUTED_STRUCTURE, unit="Å")
        desc["lattice_c"] = _prop(round(latt.c, 4), COMPUTED_STRUCTURE, unit="Å")
        desc["lattice_alpha"] = _prop(round(latt.alpha, 2), COMPUTED_STRUCTURE, unit="°")
        desc["lattice_beta"] = _prop(round(latt.beta, 2), COMPUTED_STRUCTURE, unit="°")
        desc["lattice_gamma"] = _prop(round(latt.gamma, 2), COMPUTED_STRUCTURE, unit="°")

    except Exception as e:
        log.debug("Structure descriptor error: %s", e)
    return desc


def _bond_descriptors(structure, radius: float = 4.0) -> dict:
    """Bond/neighbor distance summary."""
    desc = {}
    try:
        all_dists = []
        neighbors_list = structure.get_all_neighbors(radius, include_index=True)
        for site_neighbors in neighbors_list:
            for nbr in site_neighbors:
                all_dists.append(nbr[1])  # distance

        if all_dists:
            arr = np.array(all_dists)
            desc["min_neighbor_distance"] = _prop(
                round(float(np.min(arr)), 4), COMPUTED_STRUCTURE,
                unit="Å", method=f"get_all_neighbors(r={radius})")
            desc["mean_neighbor_distance"] = _prop(
                round(float(np.mean(arr)), 4), COMPUTED_STRUCTURE,
                unit="Å", method=f"get_all_neighbors(r={radius})")
            desc["max_neighbor_distance"] = _prop(
                round(float(np.max(arr)), 4), COMPUTED_STRUCTURE,
                unit="Å", method=f"get_all_neighbors(r={radius})")
    except Exception as e:
        log.debug("Bond descriptor error: %s", e)
    return desc


def _symmetry_descriptors(structure) -> dict:
    """Symmetry analysis from structure."""
    desc = {}
    try:
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
        sga = SpacegroupAnalyzer(structure, symprec=0.1)
        desc["spacegroup_number"] = _prop(
            sga.get_space_group_number(), COMPUTED_STRUCTURE,
            method="SpacegroupAnalyzer")
        desc["spacegroup_symbol"] = _prop(
            sga.get_space_group_symbol(), COMPUTED_STRUCTURE,
            method="SpacegroupAnalyzer")
        desc["crystal_system"] = _prop(
            sga.get_crystal_system(), COMPUTED_STRUCTURE,
            method="SpacegroupAnalyzer")
        desc["is_centrosymmetric"] = _prop(
            not sga.get_space_group_operations().are_symmetrically_related(
                [0, 0, 0], [0, 0, 0]),  # dummy — use point group instead
            COMPUTED_STRUCTURE, method="SpacegroupAnalyzer",
            note="Derived from space group point group symmetry")
        # Better centrosymmetric check via point group
        pg = sga.get_point_group_symbol()
        has_inversion = "-" in pg or pg in ("1", "m-3m", "m-3", "mmm",
                                             "4/mmm", "4/m", "6/mmm", "6/m",
                                             "-3m", "-3", "2/m")
        desc["is_centrosymmetric"] = _prop(
            has_inversion, COMPUTED_STRUCTURE,
            method=f"point_group={pg}", note="Inversion center from point group")
    except Exception as e:
        log.debug("Symmetry descriptor error: %s", e)
    return desc

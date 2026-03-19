"""Structure lift — build approximate structures for generated candidates.

Phase III.E: Takes a parent structure and applies the generation strategy
(element substitution, stoichiometry perturbation, prototype remix) to produce
a candidate pymatgen Structure.

The lifted structure is an approximation:
  - Lattice is inherited from parent (NOT relaxed)
  - Atomic positions are inherited (NOT optimized)
  - Species are replaced according to the generation strategy

This is NOT ab-initio validation. It is a prototype lift that enables
real property prediction through the existing GNN pipeline.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timezone

log = logging.getLogger(__name__)

try:
    from pymatgen.core import Structure, Lattice, Element
    HAS_PYMATGEN = True
except ImportError:
    HAS_PYMATGEN = False

from ..normalization.structure import (
    load_structure, validate_structure_obj, structure_to_cif, structure_sha256,
    jarvis_atoms_to_pymatgen,
)

# Lift status constants
LIFT_OK = "lifted_ok"
LIFT_NOT_LIFTABLE = "not_liftable"
LIFT_UNSUPPORTED = "unsupported_strategy"
LIFT_INVALID = "invalid_structure"
LIFT_MISSING_PARENT = "missing_parent_structure"


@dataclass
class LiftResult:
    """Result of attempting to lift a candidate structure."""
    status: str = LIFT_NOT_LIFTABLE
    confidence: float = 0.0
    structure: object = None          # pymatgen Structure (not serialized)
    cif_text: Optional[str] = None
    structure_sha256: Optional[str] = None
    n_atoms: int = 0
    spacegroup_lifted: Optional[int] = None
    reason: str = ""

    def to_dict(self) -> dict:
        d = {
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "n_atoms": self.n_atoms,
            "reason": self.reason,
        }
        if self.structure_sha256:
            d["structure_sha256"] = self.structure_sha256
        if self.spacegroup_lifted:
            d["spacegroup_lifted"] = self.spacegroup_lifted
        return d


def lift_candidate_structure(parent_structure_data: Optional[str],
                             parent_formula: str,
                             candidate_formula: str,
                             candidate_elements: List[str],
                             generation_strategy: str,
                             parent_atoms_dict: Optional[dict] = None,
                             ) -> LiftResult:
    """Attempt to build a candidate structure from parent.

    Args:
        parent_structure_data: CIF text of parent (may be None)
        parent_formula: parent's formula
        candidate_formula: generated candidate formula
        candidate_elements: elements in the candidate
        generation_strategy: how the candidate was generated
        parent_atoms_dict: JARVIS atoms dict (alternative to CIF)

    Returns:
        LiftResult with status, structure, confidence, metadata.
    """
    if not HAS_PYMATGEN:
        return LiftResult(status=LIFT_NOT_LIFTABLE,
                          reason="pymatgen not available")

    # Load parent structure
    parent_struct = None
    if parent_structure_data:
        parent_struct = load_structure(parent_structure_data)
    if parent_struct is None and parent_atoms_dict:
        parent_struct = jarvis_atoms_to_pymatgen(parent_atoms_dict)
    if parent_struct is None:
        return LiftResult(status=LIFT_MISSING_PARENT,
                          reason="No parent structure available")

    # Dispatch by strategy
    if generation_strategy == "element_substitution":
        return _lift_substitution(parent_struct, parent_formula,
                                  candidate_formula, candidate_elements)
    elif generation_strategy == "stoichiometry_perturbation":
        return _lift_stoichiometry(parent_struct, parent_formula,
                                   candidate_formula, candidate_elements)
    elif generation_strategy == "prototype_remix":
        return _lift_prototype(parent_struct, candidate_elements)
    else:
        return LiftResult(status=LIFT_UNSUPPORTED,
                          reason=f"Strategy '{generation_strategy}' not supported for lift")


def _lift_substitution(parent: "Structure", parent_formula: str,
                       candidate_formula: str,
                       candidate_elements: List[str]) -> LiftResult:
    """Substitute elements in parent structure.

    Finds the element mapping (old→new) and replaces species.
    """
    try:
        parent_elems = sorted(set(str(s.specie) for s in parent))
        cand_elems = sorted(candidate_elements)

        # Build substitution map: find which element changed
        sub_map = {}
        unchanged = set(parent_elems) & set(cand_elems)
        old_only = set(parent_elems) - set(cand_elems)
        new_only = set(cand_elems) - set(parent_elems)

        if len(old_only) != len(new_only):
            # Multi-element swap — try sequential matching
            if len(old_only) == 0 and len(new_only) == 0:
                # Same elements, formula count difference only
                return _lift_same_elements(parent, candidate_elements)
            return LiftResult(status=LIFT_NOT_LIFTABLE,
                              reason=f"Cannot map {old_only} → {new_only} (count mismatch)")

        # Pair old→new by sorted order (simple but deterministic)
        for old_e, new_e in zip(sorted(old_only), sorted(new_only)):
            sub_map[old_e] = new_e

        # Apply substitution
        new_struct = parent.copy()
        for old_e, new_e in sub_map.items():
            new_struct.replace_species({old_e: new_e})

        return _validate_and_wrap(new_struct, confidence=0.7,
                                  reason=f"Element substitution: {sub_map}")

    except Exception as e:
        return LiftResult(status=LIFT_INVALID,
                          reason=f"Substitution failed: {str(e)[:100]}")


def _lift_stoichiometry(parent: "Structure", parent_formula: str,
                        candidate_formula: str,
                        candidate_elements: List[str]) -> LiftResult:
    """Stoichiometry perturbation — harder to lift.

    Only supported if elements are the same (just count changed).
    Uses parent structure as-is with a confidence penalty.
    """
    parent_elems = sorted(set(str(s.specie) for s in parent))
    cand_elems = sorted(candidate_elements)

    if set(parent_elems) == set(cand_elems):
        # Same elements, different stoichiometry — use parent as proxy
        return _validate_and_wrap(parent.copy(), confidence=0.4,
                                  reason="Stoichiometry perturbation: same elements, "
                                         "parent structure used as proxy (NOT rebalanced)")
    else:
        return LiftResult(status=LIFT_NOT_LIFTABLE,
                          reason="Stoichiometry change with element change — "
                                 "structure cannot be approximated from parent")


def _lift_prototype(parent: "Structure",
                    candidate_elements: List[str]) -> LiftResult:
    """Prototype remix — substitute all species from parent with candidate set.

    Only works if candidate has same or fewer unique elements than parent sites.
    """
    try:
        parent_species = sorted(set(str(s.specie) for s in parent))
        cand_elems = sorted(candidate_elements)

        if len(cand_elems) != len(parent_species):
            return LiftResult(status=LIFT_NOT_LIFTABLE,
                              reason=f"Element count mismatch: parent has "
                                     f"{len(parent_species)}, candidate has {len(cand_elems)}")

        sub_map = dict(zip(parent_species, cand_elems))
        new_struct = parent.copy()
        for old_e, new_e in sub_map.items():
            new_struct.replace_species({old_e: new_e})

        return _validate_and_wrap(new_struct, confidence=0.5,
                                  reason=f"Prototype remix: {sub_map}")

    except Exception as e:
        return LiftResult(status=LIFT_INVALID,
                          reason=f"Prototype lift failed: {str(e)[:100]}")


def _lift_same_elements(parent: "Structure",
                        candidate_elements: List[str]) -> LiftResult:
    """When elements are the same — use parent structure directly."""
    return _validate_and_wrap(parent.copy(), confidence=0.5,
                              reason="Same elements — parent structure as proxy")


def _validate_and_wrap(struct: "Structure", confidence: float,
                       reason: str) -> LiftResult:
    """Validate lifted structure and produce LiftResult."""
    valid, err = validate_structure_obj(struct)
    if not valid:
        return LiftResult(status=LIFT_INVALID, reason=f"Validation failed: {err}")

    cif = structure_to_cif(struct)
    sha = structure_sha256(cif) if cif else None

    # Try to get spacegroup
    sg = None
    try:
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
        sga = SpacegroupAnalyzer(struct, symprec=0.1)
        sg = sga.get_space_group_number()
    except Exception:
        pass

    return LiftResult(
        status=LIFT_OK,
        confidence=confidence,
        structure=struct,
        cif_text=cif,
        structure_sha256=sha,
        n_atoms=len(struct),
        spacegroup_lifted=sg,
        reason=reason,
    )

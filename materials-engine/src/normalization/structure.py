"""Crystal structure validation, loading, and adaptation.

Supports:
  - Direct JARVIS atoms dict → pymatgen Structure (no CIF intermediate)
  - CIF text validation via pymatgen
  - Structure hashing for provenance
"""

import hashlib
import json
import logging
from typing import Optional, Tuple

log = logging.getLogger(__name__)

try:
    from pymatgen.core import Structure, Lattice
    HAS_PYMATGEN = True
except ImportError:
    HAS_PYMATGEN = False
    log.warning("pymatgen not installed")


def validate_structure(cif_text: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate a CIF string. Returns (is_valid, error_message)."""
    if not cif_text or not cif_text.strip():
        return False, "no structure data"
    if not HAS_PYMATGEN:
        return False, "pymatgen not available"
    try:
        s = Structure.from_str(cif_text, fmt="cif")
        if len(s) == 0:
            return False, "structure has 0 sites"
        return True, None
    except Exception as e:
        return False, str(e)[:200]


def validate_structure_obj(struct) -> Tuple[bool, Optional[str]]:
    """Validate a pymatgen Structure object directly."""
    if struct is None:
        return False, "no structure object"
    try:
        if len(struct) == 0:
            return False, "0 sites"
        return True, None
    except Exception as e:
        return False, str(e)[:200]


def jarvis_atoms_to_pymatgen(atoms_dict: dict):
    """Convert JARVIS atoms dict directly to pymatgen Structure.

    No CIF intermediate — avoids format compatibility issues.
    JARVIS atoms dict has: lattice_mat, coords, elements, cartesian (bool).
    """
    if not HAS_PYMATGEN or not atoms_dict:
        return None
    try:
        latt = atoms_dict.get("lattice_mat")
        coords = atoms_dict.get("coords")
        elements = atoms_dict.get("elements")
        cartesian = atoms_dict.get("cartesian", False)
        if not latt or not coords or not elements:
            return None
        lattice = Lattice(latt)
        return Structure(lattice, elements, coords, coords_are_cartesian=cartesian)
    except Exception as e:
        log.debug("JARVIS→pymatgen conversion failed: %s", e)
        return None


def structure_to_cif(struct) -> Optional[str]:
    """Serialize a pymatgen Structure to CIF text."""
    if struct is None:
        return None
    try:
        return struct.to(fmt="cif")
    except Exception as e:
        log.debug("Structure→CIF failed: %s", e)
        return None


def load_structure(cif_text: str):
    """Load pymatgen Structure from CIF text."""
    if not HAS_PYMATGEN or not cif_text:
        return None
    try:
        return Structure.from_str(cif_text, fmt="cif")
    except Exception:
        return None


def structure_sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

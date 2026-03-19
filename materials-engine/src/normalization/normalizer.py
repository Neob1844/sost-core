"""Normalizes raw data from any source into the canonical Material schema.

Phase I: robust field mapping with pymatgen chemistry parsing,
structure validation, and full provenance tracking.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from ..schema import Material, NORMALIZER_VERSION
from .chemistry import parse_formula
from .structure import validate_structure, structure_sha256

log = logging.getLogger(__name__)


def _safe_float(v) -> Optional[float]:
    if v is None: return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError): return None


def _safe_int(v) -> Optional[int]:
    if v is None: return None
    try: return int(v)
    except (TypeError, ValueError): return None


def _raw_sha256(raw: dict) -> str:
    return hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finalize(m: Material, raw: dict) -> Material:
    """Post-normalization: compute ID, validate, fix inconsistencies."""
    m.raw_payload_sha256 = _raw_sha256(raw)
    m.normalized_at = _now()
    m.normalizer_version = NORMALIZER_VERSION
    if m.elements and m.n_elements != len(m.elements):
        m.n_elements = len(m.elements)
    m.compute_canonical_id()
    # Validate structure if data present
    if m.structure_data:
        m.structure_sha256 = structure_sha256(m.structure_data)
        valid, err = validate_structure(m.structure_data)
        m.has_valid_structure = valid
        if not valid:
            log.debug("Structure validation failed for %s: %s", m.source_id, err)
    errors = m.validate()
    if errors:
        log.warning("Validation issues %s/%s: %s", m.source, m.source_id, errors)
    return m


def normalize_materials_project(raw: dict) -> Material:
    sym = raw.get("symmetry") or {}
    elements = sorted(raw.get("elements", []))
    formula = raw.get("formula_pretty", "")
    if not elements and formula:
        elements, method = parse_formula(formula)
    else:
        method = "source"
    return _finalize(Material(
        formula=formula, formula_pretty=formula,
        elements=elements, n_elements=len(elements),
        spacegroup=_safe_int(sym.get("number")),
        spacegroup_symbol=sym.get("symbol"),
        crystal_system=sym.get("crystal_system"),
        nsites=_safe_int(raw.get("nsites")),
        band_gap=_safe_float(raw.get("band_gap")),
        band_gap_direct=raw.get("is_gap_direct"),
        formation_energy=_safe_float(raw.get("formation_energy_per_atom")),
        energy_above_hull=_safe_float(raw.get("energy_above_hull")),
        bulk_modulus=_safe_float(raw.get("k_vrh")),
        shear_modulus=_safe_float(raw.get("g_vrh")),
        total_magnetization=_safe_float(raw.get("total_magnetization")),
        source="materials_project",
        source_id=raw.get("material_id", ""),
        source_url=f"https://api.materialsproject.org/materials/summary/{raw.get('material_id','')}",
        ingested_at=_now(), confidence=0.8,
        formula_parse_method=method,
    ), raw)


def normalize_aflow(raw: dict) -> Material:
    formula = raw.get("compound", raw.get("Compound", ""))
    elements, method = parse_formula(formula)
    band_gap = _safe_float(raw.get("Egap"))
    egap_type = raw.get("Egap_type")
    band_gap_direct = None
    if isinstance(egap_type, str):
        band_gap_direct = "direct" in egap_type.lower()
    auid = str(raw.get("auid", raw.get("aurl", "")))
    return _finalize(Material(
        formula=formula, formula_pretty=formula,
        elements=elements, n_elements=len(elements),
        spacegroup=_safe_int(raw.get("sg2", raw.get("spacegroup_relax"))),
        spacegroup_symbol=raw.get("sg"),
        band_gap=band_gap, band_gap_direct=band_gap_direct,
        bulk_modulus=_safe_float(raw.get("Bvoigt", raw.get("ael_bulk_modulus_voigt"))),
        shear_modulus=_safe_float(raw.get("Gvoigt", raw.get("ael_shear_modulus_voigt"))),
        source="aflow", source_id=auid,
        source_url=f"http://aflow.org/material/?id={auid}" if auid else None,
        ingested_at=_now(), confidence=0.8,
        formula_parse_method=method,
    ), raw)


def normalize_cod(raw: dict) -> Material:
    formula = raw.get("formula", "")
    if not formula:
        formula = raw.get("chemname", "")
    elements, method = parse_formula(formula)
    lattice = None
    if any(raw.get(k) for k in ["a", "b", "c"]):
        lattice = {k: _safe_float(raw.get(k))
                   for k in ["a", "b", "c", "alpha", "beta", "gamma"]}
    codid = str(raw.get("file", raw.get("codid", "")))
    return _finalize(Material(
        formula=formula, formula_pretty=formula,
        elements=elements, n_elements=len(elements),
        spacegroup=_safe_int(raw.get("sg", raw.get("sgHall"))),
        spacegroup_symbol=raw.get("sgHM"),
        lattice_params=lattice, nsites=_safe_int(raw.get("nel")),
        structure_ref=f"https://www.crystallography.net/cod/{codid}.cif" if codid else None,
        structure_format="cif",
        source="cod", source_id=codid,
        source_url=f"https://www.crystallography.net/cod/{codid}.html" if codid else None,
        ingested_at=_now(), confidence=1.0,
        formula_parse_method=method,
    ), raw)


def normalize_jarvis(raw: dict) -> Material:
    formula = raw.get("formula", raw.get("search", ""))
    elements, method = parse_formula(formula)
    jid = raw.get("jid", "")
    return _finalize(Material(
        formula=formula, formula_pretty=formula,
        elements=elements, n_elements=len(elements),
        spacegroup=_safe_int(raw.get("spg_number")),
        spacegroup_symbol=raw.get("spg_symbol"),
        band_gap=_safe_float(raw.get("optb88vdw_bandgap", raw.get("mbj_bandgap"))),
        formation_energy=_safe_float(raw.get("formation_energy_peratom")),
        energy_above_hull=_safe_float(raw.get("ehull")),
        bulk_modulus=_safe_float(raw.get("kv")),
        shear_modulus=_safe_float(raw.get("gv")),
        nsites=_safe_int(raw.get("nat")),
        source="jarvis", source_id=jid,
        source_url=f"https://jarvis.nist.gov/jarvisdft/{jid}" if jid else None,
        ingested_at=_now(), confidence=0.8,
        formula_parse_method=method,
    ), raw)


_NORMALIZERS = {
    "materials_project": normalize_materials_project,
    "aflow": normalize_aflow,
    "cod": normalize_cod,
    "jarvis": normalize_jarvis,
}


def normalize(raw: dict, source: str) -> Material:
    fn = _NORMALIZERS.get(source)
    if not fn:
        raise ValueError(f"Unknown source: {source}")
    return fn(raw)

"""Material Intelligence Report — comprehensive, honest, auditable.

Produces a full technical report for a material query combining:
- Existence status (vs integrated corpus only)
- Property evidence classification (known/predicted/proxy/unavailable)
- Comparison table with nearest neighbors
- Application hypotheses
- Confidence notes and method documentation
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List

from ..schema import Material
from ..storage.db import MaterialsDB
from ..features.fingerprint_store import FingerprintStore
from ..novelty.fingerprint import combined_fingerprint
from ..retrieval.index import RetrievalIndex
from ..inference.predictor import predict_from_structure
from ..normalization.structure import load_structure
from .evidence import (
    KNOWN, PREDICTED, PROXY, UNAVAILABLE,
    EXACT_KNOWN_MATCH, NEAR_KNOWN_MATCH, NOT_FOUND_IN_CORPUS,
    INSUFFICIENT_STRUCTURE, EXISTENCE_DISCLAIMER,
    property_entry, evidence_summary,
)
from .applications import classify_applications
from .comparison import build_comparison_table

log = logging.getLogger(__name__)

# Thresholds
EXACT_MATCH_SIM = 0.98
NEAR_MATCH_SIM = 0.85


def generate_report(formula: str,
                    elements: List[str],
                    spacegroup: Optional[int] = None,
                    material_id: Optional[str] = None,
                    db: MaterialsDB = None,
                    store: Optional[FingerprintStore] = None,
                    temperature_K: Optional[float] = None,
                    pressure_GPa: Optional[float] = None,
                    ) -> dict:
    """Generate a Material Intelligence Report.

    Can be called with:
    - material_id (existing corpus material)
    - formula + elements (arbitrary query)
    """
    now = datetime.now(timezone.utc).isoformat()

    # Resolve material from corpus if ID given
    material = None
    if material_id and db:
        material = db.get_material(material_id)
        if material:
            formula = material.formula
            elements = material.elements
            spacegroup = material.spacegroup

    # === 1. Existence status ===
    existence, exact_matches, near_matches = _check_existence(
        formula, elements, spacegroup, material, db, store)

    # If no material object but we found exact match, load it for properties
    if material is None and exact_matches and db:
        material = db.get_material(exact_matches[0]["canonical_id"])

    # === 2. Properties — classify evidence ===
    known_props, predicted_props, proxy_props, unavailable_props = _classify_properties(
        material, elements, spacegroup, db)

    # === 3. Comparison table ===
    comparison = build_comparison_table(
        material, formula, elements, spacegroup, db, store, top_k=5)

    # === 4. Applications ===
    bg_val = _get_prop_value(known_props, predicted_props, "band_gap")
    bg_evidence = _get_prop_evidence(known_props, predicted_props, "band_gap")
    fe_val = _get_prop_value(known_props, predicted_props, "formation_energy")
    fe_evidence = _get_prop_evidence(known_props, predicted_props, "formation_energy")

    applications = classify_applications(
        band_gap=bg_val, band_gap_evidence=bg_evidence,
        formation_energy=fe_val, fe_evidence=fe_evidence,
        bulk_modulus=material.bulk_modulus if material else None,
        shear_modulus=material.shear_modulus if material else None,
        total_magnetization=material.total_magnetization if material else None,
        elements=elements)

    # === 5. Novelty / Exotic ===
    novelty_score, exotic_score = _compute_novelty(
        elements, spacegroup, material, db, store)

    # === 6. T/P context ===
    tp_context = None
    if temperature_K is not None or pressure_GPa is not None:
        tp_context = {
            "temperature_K": temperature_K,
            "pressure_GPa": pressure_GPa,
            "method": "heuristic_proxy",
            "note": "T/P context recorded. Real T/P conditioning not yet implemented. "
                    "Heuristic proxy risk assessment available via /screening/thermo-pressure.",
        }

    # === 7. Evidence summary ===
    ev_summary = evidence_summary(
        known=list(known_props.keys()),
        predicted=list(predicted_props.keys()),
        proxy=list(proxy_props.keys()),
        unavailable=list(unavailable_props.keys()))

    # === 8. Assemble report ===
    has_structure = bool(material and material.structure_data)

    report = {
        "query_formula": formula,
        "query_material_id": material_id or (material.canonical_id if material else None),
        "query_elements": elements,
        "query_spacegroup": spacegroup,
        "query_structure_available": has_structure,
        "existence_status": existence,
        "exact_matches": exact_matches,
        "near_matches": near_matches[:5],
        "known_properties": known_props,
        "predicted_properties": predicted_props,
        "proxy_properties": proxy_props,
        "unavailable_properties": unavailable_props,
        "comparison_table": comparison,
        "likely_applications": applications,
        "novelty_score": round(novelty_score, 4),
        "exotic_score": round(exotic_score, 4),
        "thermo_pressure_context": tp_context,
        "evidence_summary": ev_summary,
        "confidence_note": _confidence_note(existence, has_structure, ev_summary),
        "method_notes": [
            "Existence assessed relative to integrated corpus only.",
            "Properties labeled 'known' come from JARVIS/MP/AFLOW/COD databases.",
            "Properties labeled 'predicted' come from baseline GNN models (MAE ~0.23-0.45).",
            "Properties labeled 'proxy' are heuristic estimates, NOT physics-based.",
            "Application classification is rule-based, NOT experimentally validated.",
            EXISTENCE_DISCLAIMER,
        ],
        "generated_at": now,
    }

    return report


def _check_existence(formula, elements, spacegroup, material, db, store):
    """Determine existence status against corpus."""
    exact_matches = []
    near_matches = []

    if db is None:
        return NOT_FOUND_IN_CORPUS, [], []

    # Check exact formula+spacegroup match
    results = db.search_materials(formula=formula, limit=10)
    for m in results:
        if m.formula == formula:
            if spacegroup and m.spacegroup == spacegroup:
                exact_matches.append({
                    "canonical_id": m.canonical_id,
                    "formula": m.formula,
                    "spacegroup": m.spacegroup,
                    "source": m.source,
                })
            elif not spacegroup:
                exact_matches.append({
                    "canonical_id": m.canonical_id,
                    "formula": m.formula,
                    "spacegroup": m.spacegroup,
                    "source": m.source,
                })

    # Find near matches via fingerprint
    fp = combined_fingerprint(elements, spacegroup=spacegroup)
    exclude_id = material.canonical_id if material else None

    if store and store.is_loaded:
        idx = RetrievalIndex(store)
        idx.build()
        neighbors = idx.search(fp, top_k=10, exclude_id=exclude_id)
    else:
        neighbors = []

    for cid, f, sim in neighbors:
        if sim >= NEAR_MATCH_SIM:
            near_matches.append({
                "canonical_id": cid, "formula": f,
                "similarity": round(sim, 4),
            })

    # Determine status
    if exact_matches:
        return EXACT_KNOWN_MATCH, exact_matches, near_matches
    elif near_matches:
        return NEAR_KNOWN_MATCH, exact_matches, near_matches
    else:
        return NOT_FOUND_IN_CORPUS, exact_matches, near_matches


def _classify_properties(material, elements, spacegroup, db):
    """Classify properties by evidence level."""
    known = {}
    predicted = {}
    proxy = {}
    unavailable = {}

    if material:
        # Known properties from corpus
        if material.band_gap is not None:
            known["band_gap"] = property_entry(material.band_gap, KNOWN, "eV, from corpus")
        if material.formation_energy is not None:
            known["formation_energy"] = property_entry(material.formation_energy, KNOWN, "eV/atom, from corpus")
        if material.bulk_modulus is not None:
            known["bulk_modulus"] = property_entry(material.bulk_modulus, KNOWN, "GPa, from corpus")
        if material.shear_modulus is not None:
            known["shear_modulus"] = property_entry(material.shear_modulus, KNOWN, "GPa, from corpus")
        if material.total_magnetization is not None:
            known["total_magnetization"] = property_entry(material.total_magnetization, KNOWN, "μB, from corpus")
        if material.energy_above_hull is not None:
            known["energy_above_hull"] = property_entry(material.energy_above_hull, KNOWN, "eV/atom, from corpus")

        # Try ML prediction if structure available
        if material.structure_data:
            struct = load_structure(material.structure_data)
            if struct:
                for target in ["band_gap", "formation_energy"]:
                    if target not in known:
                        pred = predict_from_structure(struct, target)
                        if "prediction" in pred:
                            predicted[target] = property_entry(
                                round(pred["prediction"], 4), PREDICTED,
                                f"GNN model ({pred.get('model', '?')}), "
                                f"MAE={pred.get('model_mae', '?')}")

    # Proxy properties — always available as heuristics
    n_elem = len(elements) if elements else 0
    if n_elem > 0:
        proxy["element_diversity"] = property_entry(
            n_elem, PROXY, "Number of unique elements")

    # Unavailable properties — honest about what we can't do
    for prop in ["density", "dielectric_constant", "thermal_conductivity",
                 "elastic_tensor", "phonon_stability", "surface_energy"]:
        unavailable[prop] = property_entry(None, UNAVAILABLE,
                                           "Requires DFT/experimental data not yet integrated")

    # Fill in missing main properties as unavailable
    for prop in ["band_gap", "formation_energy", "bulk_modulus",
                 "shear_modulus", "total_magnetization"]:
        if prop not in known and prop not in predicted:
            unavailable[prop] = property_entry(None, UNAVAILABLE, "Not available in corpus or prediction")

    return known, predicted, proxy, unavailable


def _compute_novelty(elements, spacegroup, material, db, store):
    """Compute novelty and exotic scores."""
    if db is None:
        return 0.0, 0.0
    try:
        from ..novelty.filter import NoveltyFilter
        nf = NoveltyFilter(db)
        if material:
            novelty, exotic = nf.check_exotic(material)
            return novelty.novelty_score, exotic.exotic_score
        else:
            m = Material(formula="query", elements=elements or [],
                         n_elements=len(elements or []),
                         spacegroup=spacegroup, source="query", source_id="ephemeral")
            m.compute_canonical_id()
            novelty = nf.check_novelty(m)
            return novelty.novelty_score, 0.0
    except Exception:
        return 0.0, 0.0


def _get_prop_value(known, predicted, prop):
    if prop in known:
        return known[prop]["value"]
    if prop in predicted:
        return predicted[prop]["value"]
    return None


def _get_prop_evidence(known, predicted, prop):
    if prop in known:
        return KNOWN
    if prop in predicted:
        return PREDICTED
    return UNAVAILABLE


def _confidence_note(existence, has_structure, ev_summary):
    """Generate human-readable confidence assessment."""
    parts = []
    if existence == EXACT_KNOWN_MATCH:
        parts.append("Material found as exact match in integrated corpus — high data confidence.")
    elif existence == NEAR_KNOWN_MATCH:
        parts.append("Material not found exactly but has near matches — moderate confidence.")
    else:
        parts.append("Material not found in integrated corpus — limited data confidence.")

    if has_structure:
        parts.append("Crystal structure available — enables structural property prediction.")
    else:
        parts.append("No crystal structure available — structural predictions not possible.")

    k = ev_summary["known_count"]
    p = ev_summary["predicted_count"]
    u = ev_summary["unavailable_count"]
    parts.append(f"Evidence: {k} known, {p} predicted, {u} unavailable properties.")

    return " ".join(parts)


# Import Material for type reference
from ..schema import Material

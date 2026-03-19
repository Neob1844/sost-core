"""Material Validation Dossier — comprehensive, honest, actionable.

Phase III.F: Combines all intelligence layers into a single auditable document
for any material (corpus, generated candidate, or custom formula).

The dossier answers:
1. Does this material exist in the integrated corpus?
2. What similar materials are known?
3. What properties do we have (known/predicted/proxy/unavailable)?
4. What applications are plausible?
5. What validation priority does it deserve?
6. What are the honest limitations?
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict

from ..schema import Material
from ..storage.db import MaterialsDB
from ..features.fingerprint_store import FingerprintStore
from .evidence import (
    KNOWN, PREDICTED, PROXY, UNAVAILABLE,
    EXACT_KNOWN_MATCH, NEAR_KNOWN_MATCH, NOT_FOUND_IN_CORPUS,
    GENERATED_HYPOTHESIS, INSUFFICIENT_STRUCTURE,
    EXISTENCE_DISCLAIMER, property_entry, evidence_summary,
)
from .report import generate_report
from .applications import classify_applications

log = logging.getLogger(__name__)

DOSSIER_DIR = "artifacts/intelligence"

# Validation priority thresholds
PRIORITY_HIGH_THRESHOLD = 0.55
PRIORITY_MEDIUM_THRESHOLD = 0.30

# Priority weights
PRIORITY_WEIGHTS = {
    "novelty": 0.15,
    "exotic": 0.10,
    "evaluation_score": 0.25,
    "stability_signal": 0.20,
    "structure_quality": 0.15,
    "application_score": 0.15,
}


def build_dossier(formula: str,
                  elements: List[str],
                  spacegroup: Optional[int] = None,
                  material_id: Optional[str] = None,
                  candidate_id: Optional[str] = None,
                  query_type: str = "custom_formula",
                  db: MaterialsDB = None,
                  store: Optional[FingerprintStore] = None,
                  evaluation_data: Optional[dict] = None,
                  temperature_K: Optional[float] = None,
                  pressure_GPa: Optional[float] = None,
                  ) -> dict:
    """Build a Material Validation Dossier.

    Args:
        formula: chemical formula
        elements: list of elements
        spacegroup: space group number
        material_id: canonical_id if from corpus
        candidate_id: candidate_id if from generation pipeline
        query_type: corpus_material | generated_candidate | custom_formula
        db: database connection
        store: fingerprint store
        evaluation_data: dict from evaluator if available
        temperature_K, pressure_GPa: optional T/P context
    """
    now = datetime.now(timezone.utc).isoformat()
    dossier_id = hashlib.sha256(
        f"dossier|{formula}|{spacegroup or 0}|{now}".encode()
    ).hexdigest()[:12]

    # Get base intelligence report
    report = generate_report(
        formula=formula, elements=elements, spacegroup=spacegroup,
        material_id=material_id, db=db, store=store,
        temperature_K=temperature_K, pressure_GPa=pressure_GPa)

    # Determine existence status — override for generated candidates
    existence = report["existence_status"]
    if query_type == "generated_candidate":
        if existence == NOT_FOUND_IN_CORPUS:
            existence = GENERATED_HYPOTHESIS

    # Extract evaluation scores if available
    eval_score = 0.0
    lift_confidence = 0.0
    predicted_fe = None
    predicted_bg = None

    if evaluation_data:
        eval_score = evaluation_data.get("scores", {}).get("evaluation", 0.0)
        lift_confidence = evaluation_data.get("lift", {}).get("confidence", 0.0)
        preds = evaluation_data.get("predictions", {})
        predicted_fe = preds.get("formation_energy")
        predicted_bg = preds.get("band_gap")

    # Add predicted properties from evaluation if not already present
    predicted_props = dict(report.get("predicted_properties", {}))
    if predicted_fe is not None and "formation_energy" not in report.get("known_properties", {}):
        predicted_props["formation_energy"] = property_entry(
            predicted_fe, PREDICTED, "GNN prediction on lifted structure")
    if predicted_bg is not None and "band_gap" not in report.get("known_properties", {}):
        predicted_props["band_gap"] = property_entry(
            predicted_bg, PREDICTED, "GNN prediction on lifted structure")

    # Build proxy properties
    proxy_props = dict(report.get("proxy_properties", {}))
    proxy_props.update(_build_proxy_properties(
        elements, spacegroup, temperature_K, pressure_GPa))

    # Rebuild evidence summary with updated props
    known_props = report.get("known_properties", {})
    unavailable_props = report.get("unavailable_properties", {})
    ev = evidence_summary(
        known=list(known_props.keys()),
        predicted=list(predicted_props.keys()),
        proxy=list(proxy_props.keys()),
        unavailable=list(unavailable_props.keys()))

    # Compute validation priority
    has_structure = report.get("query_structure_available", False)
    if evaluation_data:
        has_structure = has_structure or lift_confidence > 0

    apps = report.get("likely_applications", [])
    top_app_score = apps[0]["score"] if apps else 0.0

    priority, rationale = _compute_validation_priority(
        novelty=report.get("novelty_score", 0.0),
        exotic=report.get("exotic_score", 0.0),
        eval_score=eval_score,
        predicted_fe=predicted_fe,
        has_structure=has_structure,
        lift_confidence=lift_confidence,
        top_app_score=top_app_score,
        existence=existence)

    # Build T/P context
    tp_context = report.get("thermo_pressure_context")
    if tp_context is None and (temperature_K or pressure_GPa):
        tp_context = {
            "temperature_K": temperature_K,
            "pressure_GPa": pressure_GPa,
            "note": "T/P context recorded. Heuristic proxy only.",
        }

    # Limitations
    limitations = _build_limitations(existence, has_structure, ev,
                                     query_type, lift_confidence)

    # Calibration integration
    calibration_info = _get_calibration_info(
        elements, predicted_fe, predicted_bg)

    dossier = {
        "dossier_id": dossier_id,
        "query_type": query_type,
        "query_material_id": material_id,
        "query_candidate_id": candidate_id,
        "query_formula": formula,
        "query_elements": elements,
        "query_spacegroup": spacegroup,
        "query_has_structure": has_structure,
        "existence_status": existence,
        "confidence_note": report.get("confidence_note", ""),
        "known_matches": report.get("exact_matches", []),
        "near_matches": report.get("near_matches", []),
        "comparison_table": report.get("comparison_table", []),
        "known_properties": known_props,
        "predicted_properties": predicted_props,
        "proxy_properties": proxy_props,
        "unavailable_properties": unavailable_props,
        "likely_applications": apps,
        "novelty_score": report.get("novelty_score", 0.0),
        "exotic_score": report.get("exotic_score", 0.0),
        "evaluation_score": round(eval_score, 4),
        "validation_priority": priority,
        "validation_rationale": rationale,
        "thermo_pressure_context": tp_context,
        "evidence_summary": ev,
        "calibration": calibration_info,
        "method_notes": report.get("method_notes", []),
        "limitations": limitations,
        "generated_at": now,
    }

    return dossier


def build_dossier_from_evaluation(evaluation_data: dict,
                                  db: MaterialsDB,
                                  store: Optional[FingerprintStore] = None,
                                  ) -> dict:
    """Build a dossier from an evaluated generated candidate."""
    return build_dossier(
        formula=evaluation_data.get("formula", ""),
        elements=evaluation_data.get("elements", []),
        spacegroup=evaluation_data.get("spacegroup"),
        candidate_id=evaluation_data.get("candidate_id"),
        query_type="generated_candidate",
        db=db, store=store,
        evaluation_data=evaluation_data)


def save_dossier(dossier: dict, output_dir: str = DOSSIER_DIR) -> str:
    """Save dossier to disk."""
    os.makedirs(output_dir, exist_ok=True)
    did = dossier["dossier_id"]
    path = os.path.join(output_dir, f"dossier_{did}.json")
    with open(path, "w") as f:
        json.dump(dossier, f, indent=2)
    return path


def load_dossier(dossier_id: str, output_dir: str = DOSSIER_DIR) -> Optional[dict]:
    """Load a saved dossier."""
    path = os.path.join(output_dir, f"dossier_{dossier_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def list_dossiers(output_dir: str = DOSSIER_DIR) -> List[dict]:
    """List saved dossiers."""
    if not os.path.exists(output_dir):
        return []
    results = []
    for fname in sorted(os.listdir(output_dir)):
        if fname.startswith("dossier_") and fname.endswith(".json"):
            try:
                with open(os.path.join(output_dir, fname)) as f:
                    d = json.load(f)
                results.append({
                    "dossier_id": d.get("dossier_id"),
                    "formula": d.get("query_formula"),
                    "query_type": d.get("query_type"),
                    "existence_status": d.get("existence_status"),
                    "validation_priority": d.get("validation_priority"),
                    "generated_at": d.get("generated_at"),
                })
            except Exception:
                continue
    return results


# ================================================================
# Internal helpers
# ================================================================

def _build_proxy_properties(elements, spacegroup, temperature_K, pressure_GPa):
    """Build proxy properties — honest heuristic estimates."""
    proxies = {}

    # Mechanical rigidity proxy
    hard_elems = {"C", "B", "N", "W", "Re", "Os", "Si"}
    soft_elems = {"Na", "K", "Rb", "Cs", "Li"}
    hard_count = len(set(elements or []) & hard_elems)
    soft_count = len(set(elements or []) & soft_elems)
    if hard_count > soft_count:
        proxies["mechanical_rigidity_proxy"] = property_entry(
            "likely_rigid", PROXY,
            f"Contains {hard_count} hard element(s). Heuristic only.")
    elif soft_count > hard_count:
        proxies["mechanical_rigidity_proxy"] = property_entry(
            "likely_soft", PROXY,
            f"Contains {soft_count} soft/alkali element(s). Heuristic only.")

    # Thermal risk proxy
    if temperature_K and temperature_K > 1000:
        proxies["thermal_risk_proxy"] = property_entry(
            "elevated", PROXY,
            f"T={temperature_K}K exceeds 1000K — thermal decomposition risk. "
            "NOT a physics calculation.")
    elif temperature_K and temperature_K > 500:
        proxies["thermal_risk_proxy"] = property_entry(
            "moderate", PROXY, f"T={temperature_K}K — moderate thermal risk.")

    # Pressure sensitivity proxy
    if pressure_GPa and pressure_GPa > 10:
        proxies["pressure_sensitivity_proxy"] = property_entry(
            "high_pressure", PROXY,
            f"P={pressure_GPa}GPa > 10GPa — structural compression likely. Heuristic.")
    elif pressure_GPa and pressure_GPa > 1:
        proxies["pressure_sensitivity_proxy"] = property_entry(
            "moderate_pressure", PROXY, f"P={pressure_GPa}GPa — moderate pressure.")

    # Phase transition risk proxy (very rough)
    if (temperature_K and temperature_K > 1500) or (pressure_GPa and pressure_GPa > 20):
        proxies["phase_transition_risk_proxy"] = property_entry(
            "elevated", PROXY,
            "Extreme T/P conditions. Phase transition risk cannot be assessed "
            "without phonon/EOS calculations.")

    return proxies


def _compute_validation_priority(novelty, exotic, eval_score,
                                 predicted_fe, has_structure,
                                 lift_confidence, top_app_score,
                                 existence):
    """Compute validation priority and rationale."""
    w = PRIORITY_WEIGHTS

    # Stability signal from predicted formation energy
    stab = 0.3  # default neutral
    if predicted_fe is not None:
        stab = max(0.0, min(1.0, (2.0 - predicted_fe) / 5.0))

    # Structure quality
    struct_q = 0.0
    if has_structure:
        struct_q = max(0.3, lift_confidence)

    score = (w["novelty"] * novelty
             + w["exotic"] * exotic
             + w["evaluation_score"] * eval_score
             + w["stability_signal"] * stab
             + w["structure_quality"] * struct_q
             + w["application_score"] * top_app_score)

    # Clamp
    score = max(0.0, min(1.0, score))

    # Determine priority
    reasons = []
    if existence in (EXACT_KNOWN_MATCH, NEAR_KNOWN_MATCH):
        priority = "low"
        reasons.append("already_known_in_corpus")
    elif score >= PRIORITY_HIGH_THRESHOLD:
        priority = "high"
        if eval_score > 0.4:
            reasons.append("strong_evaluation_score")
        if novelty > 0.3:
            reasons.append("high_novelty")
        if stab > 0.6:
            reasons.append("predicted_stable")
        if has_structure:
            reasons.append("structure_available")
    elif score >= PRIORITY_MEDIUM_THRESHOLD:
        priority = "medium"
        if not has_structure:
            reasons.append("needs_structure_confirmation")
        reasons.append("moderate_score")
    else:
        priority = "low"
        reasons.append("insufficient_evidence")

    if not reasons:
        reasons.append("default_assessment")

    rationale = {
        "priority": priority,
        "priority_score": round(score, 4),
        "reason_codes": reasons,
        "weights_used": w,
        "components": {
            "novelty": round(novelty, 4),
            "exotic": round(exotic, 4),
            "evaluation_score": round(eval_score, 4),
            "stability_signal": round(stab, 4),
            "structure_quality": round(struct_q, 4),
            "application_score": round(top_app_score, 4),
        },
    }

    return priority, rationale


def _build_limitations(existence, has_structure, ev, query_type, lift_confidence):
    """Build honest limitations list."""
    limits = [EXISTENCE_DISCLAIMER]

    if not has_structure:
        limits.append(
            "No crystal structure available — structural property predictions "
            "not possible. Density, elastic tensor, phonon stability unavailable.")
    elif lift_confidence > 0 and lift_confidence < 0.6:
        limits.append(
            f"Structure is lifted from parent prototype (confidence: {lift_confidence:.2f}). "
            "NOT relaxed. Lattice parameters and positions are approximate.")

    if query_type == "generated_candidate":
        limits.append(
            "This is a generated hypothesis — the material may not be "
            "experimentally synthesizable. Requires computational or "
            "experimental validation before any claims.")

    if ev["unavailable_count"] > 5:
        limits.append(
            f"{ev['unavailable_count']} properties are unavailable. "
            "Advanced calculations (DFT, phonon, EOS) not yet integrated.")

    if ev["predicted_count"] > 0:
        limits.append(
            "Predicted properties use baseline GNN models (MAE ~0.23-0.45). "
            "Accuracy is limited by training data size and model complexity.")

    return limits


def _get_calibration_info(elements, predicted_fe, predicted_bg):
    """Get calibration info from persisted benchmark calibrations."""
    try:
        from ..calibration.confidence import load_calibration, get_calibrated_confidence
    except Exception:
        return {"confidence_source": "no_calibration_available"}

    n_elem = len(elements) if elements else 0
    result = {"confidence_source": "no_calibration_available"}

    fe_cal = load_calibration("formation_energy")
    bg_cal = load_calibration("band_gap")

    calibrations = {}
    if fe_cal:
        fe_conf = get_calibrated_confidence(
            fe_cal, n_elements=n_elem, property_value=predicted_fe,
            target_property="formation_energy")
        calibrations["formation_energy"] = fe_conf
        result["confidence_source"] = "benchmark_calibrated"

    if bg_cal:
        bg_conf = get_calibrated_confidence(
            bg_cal, n_elements=n_elem, property_value=predicted_bg,
            target_property="band_gap")
        calibrations["band_gap"] = bg_conf
        result["confidence_source"] = "benchmark_calibrated"

    if not calibrations:
        result["confidence_source"] = "heuristic_fallback"
        result["calibration_note"] = "No benchmark calibration available for this context."
    else:
        result["calibrations"] = calibrations
        # Use worst confidence as overall
        bands = [c.get("confidence_band", "unknown") for c in calibrations.values()]
        order = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
        worst = max(bands, key=lambda b: order.get(b, 3))
        result["calibrated_confidence"] = worst
        result["calibration_note"] = (
            "Confidence derived from empirical benchmark on known corpus materials. "
            "NOT statistical probability."
        )

    return result

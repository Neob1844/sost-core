"""Structure lift + GNN inference pipeline for autonomous discovery.

Connects candidate generation → structure lifting → real GNN prediction.
Falls back gracefully when any step fails.
"""
import sys, os, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from .chem_filters import parse_formula, normalize_formula
from .gnn_runtime import predict_from_lifted_cif

DB_PATH = os.path.expanduser("~/SOST/sostcore/sost-core/materials-engine/materials.db")

# Import structure utilities
try:
    from normalization.structure import load_structure, structure_to_cif, validate_structure_obj
    HAS_STRUCTURE = True
except ImportError:
    HAS_STRUCTURE = False

try:
    from pymatgen.core import Structure, Element
    HAS_PYMATGEN = True
except ImportError:
    HAS_PYMATGEN = False


def get_parent_cif(formula, db_path=None):
    """Get CIF structure from corpus for a formula."""
    if db_path is None:
        db_path = DB_PATH
    if not os.path.exists(db_path):
        return None
    try:
        db = sqlite3.connect(db_path)
        cur = db.cursor()
        cur.execute(
            "SELECT structure_data, spacegroup FROM materials "
            "WHERE formula=? AND has_valid_structure=1 AND structure_data IS NOT NULL "
            "ORDER BY ABS(formation_energy) ASC LIMIT 1", (formula,))
        row = cur.fetchone()
        db.close()
        if row and row[0]:
            return {"cif": row[0], "spacegroup": row[1]}
    except Exception:
        pass
    return None


def lift_structure_for_candidate(candidate_formula, candidate_elements,
                                  parent_formula, generation_method):
    """Attempt to lift a structure for a candidate from its parent.

    Returns dict with lift status, CIF if successful, and metadata.
    """
    result = {
        "structure_lift_attempted": True,
        "structure_lift_status": "not_attempted",
        "lifted_from_parent": None,
        "lifted_spacegroup": None,
        "lifted_structure_confidence": "none",
        "lifted_cif": None,
        "structure_validation_notes": "",
    }

    if not HAS_PYMATGEN or not HAS_STRUCTURE:
        result["structure_lift_status"] = "pymatgen_unavailable"
        result["structure_validation_notes"] = "pymatgen or structure utilities not available"
        return result

    # Get parent CIF
    parent_cif = get_parent_cif(parent_formula)
    if not parent_cif:
        # Try finding a corpus neighbor with same elements
        norm = normalize_formula(candidate_formula)
        parent_cif = get_parent_cif(norm)

    if not parent_cif:
        result["structure_lift_status"] = "no_parent_structure"
        result["structure_validation_notes"] = f"No structure found for parent {parent_formula} or formula {candidate_formula}"
        return result

    # Load parent structure
    try:
        parent_struct = load_structure(parent_cif["cif"])
    except Exception as e:
        result["structure_lift_status"] = "parent_load_failed"
        result["structure_validation_notes"] = str(e)
        return result

    if parent_struct is None:
        result["structure_lift_status"] = "parent_invalid"
        return result

    # Attempt element substitution lift
    if generation_method in ("element_substitution", "cross_substitution"):
        try:
            lifted = _lift_by_substitution(parent_struct, parent_formula,
                                            candidate_formula, candidate_elements)
            if lifted:
                cif_text = structure_to_cif(lifted)
                result["structure_lift_status"] = "lifted_ok"
                result["lifted_from_parent"] = parent_formula
                result["lifted_spacegroup"] = parent_cif.get("spacegroup")
                result["lifted_structure_confidence"] = "medium"
                result["lifted_cif"] = cif_text
                result["structure_validation_notes"] = "Element substitution in parent lattice. Positions NOT relaxed."
                return result
        except Exception as e:
            result["structure_lift_status"] = "lift_failed"
            result["structure_validation_notes"] = f"Substitution failed: {e}"
            return result

    # For other methods, try direct copy with element replacement
    if generation_method in ("single_site_doping", "mixed_parent"):
        result["structure_lift_status"] = "method_not_liftable"
        result["structure_validation_notes"] = f"Strategy '{generation_method}' not supported for direct lift"
        return result

    result["structure_lift_status"] = "unsupported_method"
    return result


def _lift_by_substitution(parent_struct, parent_formula, candidate_formula, candidate_elements):
    """Replace elements in parent structure to create candidate structure."""
    parent_comp = parse_formula(parent_formula)
    cand_comp = parse_formula(candidate_formula)

    parent_elems = sorted(parent_comp.keys())
    cand_elems = sorted(cand_comp.keys())

    # Find element mapping
    sub_map = {}
    for pe in parent_elems:
        if pe in cand_elems:
            sub_map[pe] = pe  # same element
        else:
            # Find the replacement
            for ce in cand_elems:
                if ce not in parent_elems and ce not in sub_map.values():
                    sub_map[pe] = ce
                    break

    if len(sub_map) != len(parent_elems):
        return None  # can't map all elements

    # Apply substitution
    new_struct = parent_struct.copy()
    for i, site in enumerate(new_struct):
        old_elem = str(site.specie)
        if old_elem in sub_map:
            new_elem = sub_map[old_elem]
            new_struct[i] = new_elem

    return new_struct


def run_gnn_inference(cif_text, target="formation_energy"):
    """Run real GNN inference on a CIF structure.

    Returns dict with prediction results.
    Uses corpus lookup for known materials, direct GNN for new candidates.
    """
    result = {
        "gnn_inference_status": "unavailable",
        "prediction": None,
        "model_used": None,
        "inference_input_type": "unavailable",
        "gnn_confidence": "none",
        "prediction_origin": "unavailable",
        "direct_fe_inference_attempted": False,
        "direct_fe_inference_success": False,
        "direct_fe_value": None,
        "direct_fe_confidence": "none",
        "direct_fe_error_mode": None,
        "direct_bg_inference_attempted": False,
        "direct_bg_inference_success": False,
        "direct_bg_value": None,
        "direct_bg_confidence": "none",
        "bg_prediction_origin": "unavailable",
    }

    if not cif_text:
        return result

    # Try to load and validate the structure
    try:
        struct = load_structure(cif_text)
        if struct is None:
            result["gnn_inference_status"] = "invalid_structure"
            return result

        # Get the formula from the lifted structure
        formula = struct.composition.reduced_formula

        # Look up if this exact formula has known values in corpus
        parent_data = get_parent_cif(formula)
        if parent_data:
            # We have the exact formula — use corpus values directly
            db = sqlite3.connect(DB_PATH)
            cur = db.cursor()
            cur.execute(
                "SELECT formation_energy, band_gap FROM materials "
                "WHERE formula=? AND has_valid_structure=1 "
                "ORDER BY ABS(formation_energy) ASC LIMIT 1", (formula,))
            row = cur.fetchone()
            db.close()
            if row:
                if target == "formation_energy" and row[0] is not None:
                    result["gnn_inference_status"] = "corpus_exact_match"
                    result["prediction"] = row[0]
                    result["model_used"] = "corpus_lookup"
                    result["inference_input_type"] = "exact_known_structure"
                    result["gnn_confidence"] = "high"
                    result["prediction_origin"] = "known_exact"
                elif target == "band_gap" and row[1] is not None:
                    result["gnn_inference_status"] = "corpus_exact_match"
                    result["prediction"] = row[1]
                    result["model_used"] = "corpus_lookup"
                    result["inference_input_type"] = "exact_known_structure"
                    result["gnn_confidence"] = "high"
                    result["prediction_origin"] = "known_exact"
                    result["bg_prediction_origin"] = "known_exact"
                return result

        # Structure is valid but formula not in corpus — TRUE new candidate
        # Attempt direct GNN inference via gnn_runtime
        if target == "formation_energy":
            result["direct_fe_inference_attempted"] = True
            gnn_out = predict_from_lifted_cif(cif_text, "formation_energy", "cgcnn")
            if gnn_out["status"] == "direct_gnn_success" and gnn_out["prediction"] is not None:
                result["gnn_inference_status"] = "direct_gnn_success"
                result["prediction"] = gnn_out["prediction"]
                result["model_used"] = "cgcnn"
                result["inference_input_type"] = "lifted_structure"
                result["gnn_confidence"] = gnn_out.get("confidence", "medium")
                result["prediction_origin"] = "direct_gnn_lifted"
                result["direct_fe_inference_success"] = True
                result["direct_fe_value"] = gnn_out["prediction"]
                result["direct_fe_confidence"] = gnn_out.get("confidence", "medium")
            else:
                # GNN failed but structure is valid — proxy only
                result["gnn_inference_status"] = "structure_ready_for_gnn"
                result["inference_input_type"] = "lifted_structure"
                result["gnn_confidence"] = "pending"
                result["model_used"] = "none_yet"
                result["prediction_origin"] = "proxy_only"
                result["direct_fe_error_mode"] = gnn_out.get("status", "unknown")

        elif target == "band_gap":
            result["direct_bg_inference_attempted"] = True
            gnn_out = predict_from_lifted_cif(cif_text, "band_gap", "alignn_lite")
            if gnn_out["status"] == "direct_gnn_success" and gnn_out["prediction"] is not None:
                result["gnn_inference_status"] = "direct_gnn_success"
                result["prediction"] = gnn_out["prediction"]
                result["model_used"] = "alignn_lite"
                result["inference_input_type"] = "lifted_structure"
                result["gnn_confidence"] = gnn_out.get("confidence", "medium")
                result["prediction_origin"] = "direct_gnn_lifted"
                result["bg_prediction_origin"] = "direct_gnn_lifted"
                result["direct_bg_inference_success"] = True
                result["direct_bg_value"] = gnn_out["prediction"]
                result["direct_bg_confidence"] = gnn_out.get("confidence", "medium")
            else:
                result["gnn_inference_status"] = "structure_ready_for_gnn"
                result["inference_input_type"] = "lifted_structure"
                result["gnn_confidence"] = "pending"
                result["model_used"] = "none_yet"
                result["prediction_origin"] = "proxy_only"
                result["bg_prediction_origin"] = "proxy_only"

    except Exception as e:
        result["gnn_inference_status"] = f"error:{str(e)[:50]}"

    return result


def run_direct_gnn_inference(cif_text):
    """Run BOTH formation_energy (CGCNN) and band_gap (ALIGNN-Lite) in one call.

    Returns a combined result dict with fe_* and bg_* fields plus overall status.
    Intended to be called from engine.py instead of calling run_gnn_inference twice.
    """
    combined = {
        "direct_fe_inference_attempted": False,
        "direct_fe_inference_success": False,
        "direct_fe_value": None,
        "direct_fe_confidence": "none",
        "direct_fe_error_mode": None,
        "direct_bg_inference_attempted": False,
        "direct_bg_inference_success": False,
        "direct_bg_value": None,
        "direct_bg_confidence": "none",
        "direct_bg_error_mode": None,
        "prediction_origin": "unavailable",
        "bg_prediction_origin": "unavailable",
        "overall_status": "unavailable",
    }

    if not cif_text:
        return combined

    # Check if structure is valid first (avoid loading twice)
    try:
        struct = load_structure(cif_text)
        if struct is None:
            combined["overall_status"] = "invalid_structure"
            return combined
    except Exception as e:
        combined["overall_status"] = f"structure_error:{str(e)[:50]}"
        return combined

    formula = struct.composition.reduced_formula

    # Check corpus first
    parent_data = get_parent_cif(formula)
    if parent_data:
        db = sqlite3.connect(DB_PATH)
        cur = db.cursor()
        cur.execute(
            "SELECT formation_energy, band_gap FROM materials "
            "WHERE formula=? AND has_valid_structure=1 "
            "ORDER BY ABS(formation_energy) ASC LIMIT 1", (formula,))
        row = cur.fetchone()
        db.close()
        if row:
            if row[0] is not None:
                combined["direct_fe_value"] = row[0]
                combined["direct_fe_inference_success"] = True
                combined["direct_fe_confidence"] = "high"
                combined["prediction_origin"] = "known_exact"
            if row[1] is not None:
                combined["direct_bg_value"] = row[1]
                combined["direct_bg_inference_success"] = True
                combined["direct_bg_confidence"] = "high"
                combined["bg_prediction_origin"] = "known_exact"
            combined["overall_status"] = "corpus_exact_match"
            return combined

    # New candidate — run direct GNN for both targets
    # Formation energy via CGCNN
    combined["direct_fe_inference_attempted"] = True
    fe_out = predict_from_lifted_cif(cif_text, "formation_energy", "cgcnn")
    if fe_out["status"] == "direct_gnn_success" and fe_out["prediction"] is not None:
        combined["direct_fe_inference_success"] = True
        combined["direct_fe_value"] = fe_out["prediction"]
        combined["direct_fe_confidence"] = fe_out.get("confidence", "medium")
        combined["prediction_origin"] = "direct_gnn_lifted"
    else:
        combined["direct_fe_error_mode"] = fe_out.get("status", "unknown")
        combined["prediction_origin"] = "proxy_only"

    # Band gap via ALIGNN-Lite
    combined["direct_bg_inference_attempted"] = True
    bg_out = predict_from_lifted_cif(cif_text, "band_gap", "alignn_lite")
    if bg_out["status"] == "direct_gnn_success" and bg_out["prediction"] is not None:
        combined["direct_bg_inference_success"] = True
        combined["direct_bg_value"] = bg_out["prediction"]
        combined["direct_bg_confidence"] = bg_out.get("confidence", "medium")
        combined["bg_prediction_origin"] = "direct_gnn_lifted"
    else:
        combined["direct_bg_error_mode"] = bg_out.get("status", "unknown")
        combined["bg_prediction_origin"] = "proxy_only"

    # Overall status
    if combined["direct_fe_inference_success"] or combined["direct_bg_inference_success"]:
        combined["overall_status"] = "direct_gnn_success"
    else:
        combined["overall_status"] = "gnn_failed_proxy_only"

    return combined

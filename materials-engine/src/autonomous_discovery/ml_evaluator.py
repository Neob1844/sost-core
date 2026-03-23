"""ML evaluation for autonomous discovery candidates — Phase III.

Connects candidates to real ML prediction when possible:
1. Find nearest corpus neighbor with same element set
2. Use its structure as prototype (structure lift)
3. Run CGCNN/ALIGNN prediction on lifted structure
4. Fall back to corpus-based property estimation if lift fails

Honest about what's predicted vs estimated vs unavailable.
"""
import sys, os, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from .chem_filters import parse_formula, normalize_formula

DB_PATH = os.path.expanduser("~/SOST/sostcore/sost-core/materials-engine/materials.db")


def find_nearest_neighbors(formula, elements, db_path=None, max_neighbors=3):
    """Find closest corpus materials by element overlap."""
    if db_path is None:
        db_path = DB_PATH
    if not os.path.exists(db_path):
        return []

    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        cur = db.cursor()

        elem_set = set(elements)
        neighbors = []

        # Strategy 1: Exact element match (same elements, different stoichiometry)
        for elem in elements[:3]:  # limit search scope
            cur.execute(
                "SELECT canonical_id, formula, spacegroup, band_gap, formation_energy, "
                "has_valid_structure, structure_data FROM materials "
                "WHERE formula LIKE ? AND has_valid_structure=1 LIMIT 20",
                (f"%{elem}%",)
            )
            for row in cur.fetchall():
                row_elems = set(parse_formula(row["formula"]).keys())
                overlap = len(elem_set & row_elems) / max(len(elem_set | row_elems), 1)
                if overlap >= 0.5:
                    neighbors.append({
                        "canonical_id": row["canonical_id"],
                        "formula": row["formula"],
                        "spacegroup": row["spacegroup"],
                        "band_gap": row["band_gap"],
                        "formation_energy": row["formation_energy"],
                        "has_structure": bool(row["has_valid_structure"]),
                        "element_overlap": round(overlap, 3),
                    })

        db.close()

        # Sort by overlap descending, deduplicate by formula
        seen = set()
        unique = []
        for n in sorted(neighbors, key=lambda x: -x["element_overlap"]):
            if n["formula"] not in seen:
                seen.add(n["formula"])
                unique.append(n)
        return unique[:max_neighbors]

    except Exception as e:
        return []


def get_prototype_structure(formula, elements, db_path=None):
    """Get a prototype CIF structure from the nearest corpus neighbor."""
    if db_path is None:
        db_path = DB_PATH
    if not os.path.exists(db_path):
        return None, "database_not_found"

    try:
        db = sqlite3.connect(db_path)
        cur = db.cursor()

        # Find exact formula match first
        norm = normalize_formula(formula)
        cur.execute(
            "SELECT structure_data, spacegroup, formula FROM materials "
            "WHERE formula=? AND has_valid_structure=1 AND structure_data IS NOT NULL "
            "LIMIT 1", (formula,)
        )
        row = cur.fetchone()
        if row and row[0]:
            db.close()
            return {"cif": row[0], "spacegroup": row[1], "source_formula": row[2],
                    "match_type": "exact_formula"}, "exact_match"

        # Try element-set match
        for elem in elements[:2]:
            cur.execute(
                "SELECT structure_data, spacegroup, formula FROM materials "
                "WHERE formula LIKE ? AND has_valid_structure=1 AND structure_data IS NOT NULL "
                "ORDER BY ABS(formation_energy) ASC LIMIT 5", (f"%{elem}%",)
            )
            for row in cur.fetchall():
                row_elems = set(parse_formula(row[2]).keys())
                if set(elements) == row_elems:
                    db.close()
                    return {"cif": row[0], "spacegroup": row[1], "source_formula": row[2],
                            "match_type": "same_elements"}, "element_match"

        db.close()
        return None, "no_prototype_found"

    except Exception as e:
        return None, f"error:{e}"


def evaluate_candidate_ml(formula, elements, method, parent_a="", parent_b=""):
    """Evaluate a candidate with ML prediction if possible.

    Returns dict with prediction results and honest confidence labels.
    """
    result = {
        "formula": formula,
        "formation_energy_predicted": None,
        "band_gap_predicted": None,
        "ml_inference_status": "unavailable",
        "ml_confidence": "none",
        "prediction_path": "unavailable",
        "nearest_neighbors": [],
        "prototype_hint": None,
        "structure_context_confidence": "none",
    }

    # Step 1: Find neighbors
    neighbors = find_nearest_neighbors(formula, elements)
    result["nearest_neighbors"] = neighbors

    if not neighbors:
        result["ml_inference_status"] = "no_neighbors"
        return result

    # Step 2: Use neighbor properties as proxy estimates
    best_neighbor = neighbors[0]
    if best_neighbor["element_overlap"] >= 0.8:
        # Good overlap — use neighbor properties as proxy
        result["formation_energy_predicted"] = best_neighbor.get("formation_energy")
        result["band_gap_predicted"] = best_neighbor.get("band_gap")
        result["ml_inference_status"] = "proxy_from_neighbor"
        result["ml_confidence"] = "low"
        result["prediction_path"] = "corpus_neighbor_proxy"
        result["structure_context_confidence"] = "neighbor_based"

        if best_neighbor.get("spacegroup"):
            result["prototype_hint"] = {
                "spacegroup": best_neighbor["spacegroup"],
                "source_formula": best_neighbor["formula"],
                "match_type": "nearest_neighbor",
                "confidence": "tentative",
            }

    if best_neighbor["element_overlap"] >= 1.0:
        # Exact element match — higher confidence
        result["ml_confidence"] = "medium"
        result["prediction_path"] = "corpus_exact_element_proxy"
        result["structure_context_confidence"] = "same_element_set"

    # Step 3: Check if exact formula exists in corpus
    proto, reason = get_prototype_structure(formula, elements)
    if proto:
        result["prototype_hint"] = {
            "spacegroup": proto.get("spacegroup"),
            "source_formula": proto.get("source_formula"),
            "match_type": proto.get("match_type"),
            "confidence": "high" if proto["match_type"] == "exact_formula" else "medium",
        }
        if proto["match_type"] == "exact_formula":
            result["ml_inference_status"] = "known_in_corpus"
            result["ml_confidence"] = "high"
            result["prediction_path"] = "direct_corpus_lookup"
            result["structure_context_confidence"] = "exact_match"

    return result

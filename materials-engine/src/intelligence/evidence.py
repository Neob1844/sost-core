"""Evidence classification for material properties.

Every property in an intelligence report must declare its evidence level:
  known      — value comes directly from an integrated database (JARVIS, MP, etc.)
  predicted  — value computed by a trained ML model on real/lifted structure
  proxy      — heuristic estimate, NOT from physics or ML model
  unavailable — system cannot produce this value with acceptable confidence
"""

# Evidence levels
KNOWN = "known"
COMPUTED_STRUCTURE = "computed_from_structure"
COMPUTED_COMPOSITION = "computed_from_composition"
PREDICTED = "predicted"
PROXY = "proxy"
UNAVAILABLE = "unavailable"

# Existence statuses
EXACT_KNOWN_MATCH = "exact_known_match"
NEAR_KNOWN_MATCH = "near_known_match"
NOT_FOUND_IN_CORPUS = "not_found_in_integrated_corpus"
GENERATED_HYPOTHESIS = "generated_hypothesis"
INSUFFICIENT_STRUCTURE = "insufficient_structure"

EXISTENCE_DISCLAIMER = (
    "Existence is assessed relative to the integrated corpus only, "
    "not all published scientific literature."
)


def property_entry(value, evidence: str, note: str = "") -> dict:
    """Create a standardized property entry with evidence tagging."""
    return {"value": value, "evidence": evidence, "note": note}


def evidence_summary(known: list, predicted: list, proxy: list,
                     unavailable: list) -> dict:
    """Summarize evidence distribution across all properties."""
    return {
        "known_count": len(known),
        "predicted_count": len(predicted),
        "proxy_count": len(proxy),
        "unavailable_count": len(unavailable),
        "known_fields": known,
        "predicted_fields": predicted,
        "proxy_fields": proxy,
        "unavailable_fields": unavailable,
    }

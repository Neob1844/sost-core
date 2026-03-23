"""Dual-output candidate explainer: technical report + plain-language summary.

Every candidate gets TWO layers:
1. technical_report — for scientists, auditors, debugging
2. plain_language — for humans, UI, executives, demos
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from release.common_names import COMMON_NAMES, resolve_query
except ImportError:
    COMMON_NAMES = {}
    def resolve_query(q): return {"resolved": False}

from .chem_filters import normalize_formula, parse_formula, ANIONS

# Known material families for descriptive naming
FAMILY_PATTERNS = {
    frozenset({"Ga","As"}): ("III-V semiconductor", "gallium arsenide family"),
    frozenset({"Al","N"}): ("III-V nitride", "aluminum nitride family"),
    frozenset({"In","P"}): ("III-V phosphide", "indium phosphide family"),
    frozenset({"Si","C"}): ("carbide ceramic", "silicon carbide family"),
    frozenset({"Ti","O"}): ("transition metal oxide", "titanium oxide family"),
    frozenset({"Zn","O"}): ("wide-gap oxide", "zinc oxide family"),
    frozenset({"Fe","O"}): ("iron oxide", "iron oxide family"),
    frozenset({"Fe","S"}): ("iron sulfide", "pyrite family"),
    frozenset({"Cu","O"}): ("copper oxide", "cuprite family"),
    frozenset({"Ba","Ti","O"}): ("perovskite", "barium titanate family"),
    frozenset({"Li","Co","O"}): ("layered cathode", "lithium cobalt oxide family"),
    frozenset({"Li","Fe","P","O"}): ("olivine cathode", "lithium iron phosphate family"),
}

# Element names for descriptive labels
ELEM_NAMES = {
    "Al":"aluminum","As":"arsenic","B":"boron","Ba":"barium","Bi":"bismuth",
    "C":"carbon","Ca":"calcium","Cd":"cadmium","Ce":"cerium","Co":"cobalt",
    "Cr":"chromium","Cu":"copper","Fe":"iron","Ga":"gallium","Ge":"germanium",
    "Hf":"hafnium","In":"indium","K":"potassium","La":"lanthanum","Li":"lithium",
    "Mg":"magnesium","Mn":"manganese","Mo":"molybdenum","N":"nitrogen","Na":"sodium",
    "Nb":"niobium","Ni":"nickel","O":"oxygen","P":"phosphorus","Pb":"lead",
    "Pd":"palladium","Pt":"platinum","Rb":"rubidium","Re":"rhenium","Ru":"ruthenium",
    "S":"sulfur","Sb":"antimony","Sc":"scandium","Se":"selenium","Si":"silicon",
    "Sn":"tin","Sr":"strontium","Ta":"tantalum","Te":"tellurium","Ti":"titanium",
    "V":"vanadium","W":"tungsten","Y":"yttrium","Zn":"zinc","Zr":"zirconium",
}

# Status categories
STATUS_KNOWN = "Known material"
STATUS_FAMILY_VARIANT = "Known family variant"
STATUS_NEAR_KNOWN = "Near-known candidate"
STATUS_THEORETICAL = "Theoretical candidate"
STATUS_WATCHLIST = "Watchlist candidate"
STATUS_LOW_CONF = "Low-confidence exploratory candidate"


def explain_candidate(candidate, corpus_formulas=None):
    """Generate dual technical + plain-language explanation for a candidate.

    Args:
        candidate: dict with formula, method, scores, parent_a, parent_b, etc.
        corpus_formulas: set of known formulas in corpus (for novelty check)

    Returns:
        dict with 'technical_report' and 'plain_language' keys
    """
    formula = candidate.get("formula", "")
    norm = normalize_formula(formula)
    comp = parse_formula(formula)
    elements = sorted(comp.keys()) if comp else []
    scores = candidate.get("scores", {})
    method = candidate.get("method", "unknown")
    parent_a = candidate.get("parent_a", "")
    parent_b = candidate.get("parent_b", "")
    decision = scores.get("decision", candidate.get("decision", "unknown"))

    if corpus_formulas is None:
        corpus_formulas = set()

    # Detect corpus match
    match = _detect_corpus_match(norm, elements, corpus_formulas)

    # Detect name
    name_info = _detect_name(formula, elements)

    # Detect family
    family = _detect_family(elements)

    # Determine status category
    status = _categorize(match, decision, scores)

    # Build technical report
    tech = _build_technical(candidate, norm, match, name_info, family, status, scores)

    # Build plain language
    plain = _build_plain_language(candidate, norm, match, name_info, family, status, scores,
                                  elements, method, parent_a, parent_b)

    return {
        "technical_report": tech,
        "plain_language": plain,
    }


def _detect_corpus_match(norm, elements, corpus_formulas):
    """Check if formula exists in corpus."""
    exact = norm in corpus_formulas
    # Check common variants (different stoichiometry of same elements)
    near = []
    elem_set = frozenset(elements)
    for cf in corpus_formulas:
        cf_elems = frozenset(parse_formula(cf).keys())
        if cf_elems == elem_set and cf != norm:
            near.append(cf)
    return {
        "exact_known_match": exact,
        "near_known_match": len(near) > 0,
        "near_formulas": near[:3],
        "family_known_but_candidate_new": not exact and len(near) > 0,
        "no_direct_match": not exact and len(near) == 0,
    }


def _detect_name(formula, elements):
    """Detect if the material has a known common name."""
    # Try common_names registry — only count as "named" if the source is a common name,
    # not just a formula that was parsed
    resolution = resolve_query(formula)
    if resolution.get("resolved") and resolution.get("source") in ("common_name", "registry_match"):
        return {
            "has_name": True,
            "common_name": resolution.get("original_query", formula),
            "status": "has_well_known_name",
        }

    # Check if formula itself is well-known
    known_names = {
        "Fe2O3": "hematite", "Fe3O4": "magnetite", "SiO2": "quartz/silica",
        "TiO2": "rutile/anatase", "Al2O3": "alumina/corundum", "ZnO": "zinc oxide",
        "GaAs": "gallium arsenide", "SiC": "silicon carbide", "NaCl": "halite/salt",
        "CaCO3": "calcite", "BaTiO3": "barium titanate", "FeS2": "pyrite",
        "Cu2O": "cuprite", "CuO": "tenorite", "MgO": "periclase",
        "ZrO2": "zirconia", "InP": "indium phosphide", "AlN": "aluminum nitride",
        "BN": "boron nitride", "CdTe": "cadmium telluride",
    }
    norm = normalize_formula(formula)
    if norm in known_names or formula in known_names:
        name = known_names.get(norm, known_names.get(formula, ""))
        return {"has_name": True, "common_name": name, "status": "has_well_known_name"}

    return {
        "has_name": False,
        "common_name": None,
        "status": "no_standard_common_name",
        "descriptive_label": _generate_descriptive_name(elements),
    }


def _detect_family(elements):
    """Detect if elements belong to a known material family."""
    elem_set = frozenset(elements)
    for pattern, (family_type, family_name) in FAMILY_PATTERNS.items():
        if pattern.issubset(elem_set):
            return {"known_family": True, "family_type": family_type, "family_name": family_name}

    # Check broad categories
    has_oxygen = "O" in elem_set
    has_chalcogen = bool(elem_set & {"S", "Se", "Te"})
    has_halide = bool(elem_set & {"F", "Cl", "Br", "I"})
    group_3 = bool(elem_set & {"B", "Al", "Ga", "In"})
    group_5 = bool(elem_set & {"N", "P", "As", "Sb"})

    if group_3 and group_5:
        return {"known_family": True, "family_type": "III-V compound", "family_name": "III-V semiconductor family"}
    if has_oxygen:
        return {"known_family": True, "family_type": "oxide", "family_name": "metal oxide family"}
    if has_chalcogen:
        return {"known_family": True, "family_type": "chalcogenide", "family_name": "chalcogenide family"}
    if has_halide:
        return {"known_family": True, "family_type": "halide", "family_name": "halide family"}

    return {"known_family": False, "family_type": "unclassified", "family_name": "no known family detected"}


def _generate_descriptive_name(elements):
    """Generate an honest descriptive label for unnamed candidates."""
    names = [ELEM_NAMES.get(e, e.lower()) for e in elements]
    has_o = "O" in elements
    n = len(elements)

    if has_o and n == 2:
        non_o = [e for e in elements if e != "O"]
        return f"Theoretical {ELEM_NAMES.get(non_o[0], non_o[0])} oxide candidate"
    if has_o and n == 3:
        non_o = [ELEM_NAMES.get(e, e) for e in elements if e != "O"]
        return f"Theoretical {'-'.join(non_o)} mixed oxide candidate"
    if n == 2:
        return f"Theoretical {names[0]}-{names[1]} binary candidate"
    if n == 3:
        return f"Theoretical {names[0]}-{names[1]}-{names[2]} ternary candidate"
    return f"Theoretical {n}-element candidate ({', '.join(names[:3])}...)"


def _categorize(match, decision, scores):
    """Determine the human-readable status category."""
    if match["exact_known_match"]:
        return STATUS_KNOWN
    if match["near_known_match"]:
        return STATUS_FAMILY_VARIANT if scores.get("plausibility", 0) > 0.6 else STATUS_NEAR_KNOWN
    if decision == "accepted":
        return STATUS_THEORETICAL
    if decision == "watchlist":
        return STATUS_WATCHLIST
    return STATUS_LOW_CONF


def _build_technical(candidate, norm, match, name_info, family, status, scores):
    """Build the full technical report."""
    return {
        "candidate_formula": candidate.get("formula", ""),
        "normalized_formula": norm,
        "known_or_candidate_status": status,
        "corpus_match": match,
        "name_info": name_info,
        "family_info": family,
        "parent_a": candidate.get("parent_a", ""),
        "parent_b": candidate.get("parent_b", ""),
        "generation_method": candidate.get("method", ""),
        "iteration": candidate.get("iteration", 0),
        "scores": scores,
        "decision": scores.get("decision", "unknown"),
        "recommended_next_step": _tech_next_step(status, scores),
        "technical_limitations": [
            "No crystal structure assigned — composition only",
            "No DFT validation performed",
            "Scores are heuristic proxies, not measured properties",
            "Novelty is relative to current corpus only",
        ],
    }


def _build_plain_language(candidate, norm, match, name_info, family, status,
                           scores, elements, method, parent_a, parent_b):
    """Build all three plain-language summary formats."""
    formula = candidate.get("formula", norm)

    # Title
    if name_info.get("has_name"):
        title = f"{formula} — {name_info['common_name']}"
    elif name_info.get("descriptive_label"):
        title = f"{formula} — {name_info['descriptive_label']}"
    else:
        title = formula

    # Identity
    if match["exact_known_match"]:
        identity = f"This is a known material ({formula}) already present in the corpus."
    elif match["near_known_match"]:
        near = ", ".join(match["near_formulas"][:2])
        identity = f"This composition is related to known materials ({near}) but is not an exact match in the corpus."
    else:
        identity = f"This is a theoretical candidate composition not found as-is in the current database."

    # Novelty clarity
    if match["exact_known_match"]:
        novelty = "Already known in corpus. Not a new candidate."
    elif match["near_known_match"]:
        novelty = "Close to known materials — may be a variant or polymorph rather than truly new."
    else:
        novelty = "Not found exactly in the current database. New relative to this corpus only — this does not confirm it as a universal novelty."

    # Name status
    if name_info.get("has_name"):
        name_status = f"Has a well-known name: {name_info['common_name']}."
    elif family.get("known_family"):
        name_status = f"No standard common name, but belongs to the {family['family_name']}."
    else:
        name_status = "No standard common name detected. Identified by formula only."

    # Origin
    method_desc = {
        "element_substitution": f"element substitution from {parent_a}",
        "single_site_doping": f"doping {parent_a} with an element from {parent_b}",
        "mixed_parent": f"combining elements from {parent_a} and {parent_b}",
        "cross_substitution": f"replacing an element in {parent_a} with one from {parent_b}",
    }.get(method, f"algorithmic generation from {parent_a} and {parent_b}")
    origin = f"Generated by {method_desc}, then filtered and scored by the autonomous discovery engine."

    # Why it matters
    matters = []
    if scores.get("value", 0) > 0.5:
        matters.append("Contains elements with strategic or industrial relevance.")
    if scores.get("plausibility", 0) > 0.6:
        matters.append("Chemically plausible composition with known family context.")
    if scores.get("novelty", 0) > 0.5:
        matters.append("Compositionally distinct from most known materials in the corpus.")
    if family.get("known_family"):
        matters.append(f"Related to the {family['family_name']}, which includes industrially important materials.")
    if not matters:
        matters.append("Selected by the ranking algorithm as worth further investigation.")

    # Known vs estimated
    known_vs_est = {
        "known": ["Chemical formula", "Elemental composition"],
        "heuristic": ["Plausibility score", "Value score", "Stability proxy", "Family assignment"],
        "not_available": ["Crystal structure", "Exact band gap", "Formation energy", "Experimental validation"],
    }

    # Risk
    risks = [
        "This candidate has not been experimentally validated.",
        "The crystal structure is unknown — only the composition is proposed.",
        "All scores are heuristic estimates, not measured properties.",
    ]
    if scores.get("plausibility", 0) < 0.4:
        risks.append("Plausibility score is low — the composition may not form a stable phase.")

    # Next step
    if status == STATUS_KNOWN:
        next_step = "Already known. Look up detailed properties in the corpus."
    elif status == STATUS_THEORETICAL and scores.get("composite_score", 0) > 0.5:
        next_step = "Run a stronger ML prediction (formation energy + band gap) to assess stability."
    elif status == STATUS_WATCHLIST:
        next_step = "Keep on watchlist. Re-evaluate if more context or data becomes available."
    else:
        next_step = "Low priority. Compare against nearest known compounds before investing more effort."

    # One-paragraph summary
    para = f"{formula}"
    if name_info.get("has_name"):
        para += f" ({name_info['common_name']})"
    para += f" is a {status.lower()} "
    if match["exact_known_match"]:
        para += "already present in the materials corpus. "
    else:
        para += f"generated from {parent_a} and {parent_b} via {method.replace('_',' ')}. "
    if family.get("known_family"):
        para += f"It belongs to the {family['family_name']}. "
    if scores.get("composite_score"):
        para += f"It received a composite score of {scores['composite_score']:.3f} "
        para += f"(plausibility: {scores.get('plausibility','?')}, value: {scores.get('value','?')}). "
    para += "All assessments are heuristic estimates. "
    para += "This result should be treated as a prioritized hypothesis, not a confirmed material."

    # Short / standard / extended
    short = f"{title} | {status} | Score: {scores.get('composite_score','?')} | {novelty.split('.')[0]}."

    standard = f"{identity} {novelty} {origin}"
    if matters:
        standard += " " + matters[0]

    extended = para

    return {
        "title": title,
        "status_category": status,
        "plain_identity": identity,
        "novelty_clarity": novelty,
        "known_name_status": name_status,
        "origin_explanation": origin,
        "why_it_matters": matters,
        "what_is_known_vs_estimated": known_vs_est,
        "risk_and_uncertainty": risks,
        "next_step_plain": next_step,
        "one_paragraph_summary": para,
        "short_summary": short,
        "standard_summary": standard,
        "extended_summary": extended,
    }


def _tech_next_step(status, scores):
    if status == STATUS_KNOWN:
        return "corpus_lookup"
    if scores.get("composite_score", 0) >= 0.5:
        return "ml_prediction_priority"
    if scores.get("composite_score", 0) >= 0.35:
        return "watchlist_reevaluate"
    return "low_priority_archive"

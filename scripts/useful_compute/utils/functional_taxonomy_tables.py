"""
Functional taxonomy classification.

Mirror of internal source (functional_taxonomy) with the
function reduced to take pre-parsed counts (no re-parsing in the hot
loop).

Stdlib only.
"""

from typing import Dict, List


# Functional class definitions based on compositional patterns.
# Mirrors functional_taxonomy.FUNCTIONAL_CLASSES exactly.
FUNCTIONAL_CLASSES = {
    "perovskite": {
        "description": "ABO3-type oxide with tunable electronic/catalytic properties",
        "required": {"O"},
        "preferred_A": {"La", "Sr", "Ba", "Ca", "Y", "Ce", "Nd", "Pr", "Sm",
                         "Na", "K", "Bi"},
        "preferred_B": {"Ti", "Mn", "Fe", "Co", "Ni", "Cr", "V", "Nb",
                         "Mo", "W", "Zr"},
        "min_elements": 3,
        "applications": ["catalysis", "membrane", "photovoltaic",
                          "ion-transport"],
    },
    "spinel": {
        "description": "AB2O4-type with redox-active transition metals",
        "required": {"O"},
        "preferred": {"Fe", "Mn", "Co", "Ni", "Cr", "Cu", "Zn", "Ti",
                       "Al", "Mg"},
        "min_elements": 3,
        "applications": ["catalysis", "battery", "ion-exchange"],
    },
    "layered_oxide": {
        "description": "Layered structure with intercalation capability",
        "required": {"O"},
        "preferred": {"Li", "Na", "K", "Mn", "Co", "Ni", "Ti", "V",
                       "Mo", "W", "Nb"},
        "min_elements": 3,
        "applications": ["battery", "ion-exchange", "lithium-recovery",
                          "membrane"],
    },
    "phosphate_framework": {
        "description": "Phosphate-based framework (NASICON, olivine, etc.)",
        "required": {"P", "O"},
        "preferred": {"Li", "Na", "Fe", "Mn", "Ti", "Zr", "V", "Co"},
        "min_elements": 3,
        "applications": ["battery", "ion-transport", "lithium-recovery"],
    },
    "zeolite_like": {
        "description": "Microporous aluminosilicate or similar framework",
        "required": {"O"},
        "preferred": {"Si", "Al", "Na", "K", "Ca", "Ba"},
        "requires_any": {"Si", "Al"},
        "min_elements": 3,
        "applications": ["membrane", "ion-exchange", "desalination",
                          "catalysis"],
    },
    "titanate": {
        "description": "Titanium oxide-based with ion-exchange/photocatalytic potential",
        "required": {"Ti", "O"},
        "preferred": {"Na", "K", "Li", "Ba", "Sr", "Ca", "La"},
        "min_elements": 2,
        "applications": ["photocatalysis", "ion-exchange",
                          "lithium-recovery", "membrane"],
    },
    "chalcogenide": {
        "description": "Sulfide/selenide with electronic/optical properties",
        "requires_any": {"S", "Se", "Te"},
        "preferred": {"Cu", "Zn", "Sn", "Fe", "Mn", "In", "Ga", "Bi", "Sb"},
        "min_elements": 2,
        "applications": ["photovoltaic", "thermoelectric", "catalysis"],
    },
    "nitride": {
        "description": "Metal nitride with catalytic/electronic properties",
        "required": {"N"},
        "preferred": {"Ti", "Fe", "Mo", "W", "V", "Cr", "Mn", "Al", "Ga", "Si"},
        "exclude": {"O"},
        "min_elements": 2,
        "applications": ["catalysis", "hard-coating", "electronic"],
    },
    "carbide": {
        "description": "Metal carbide with catalytic/structural properties",
        "required": {"C"},
        "preferred": {"Ti", "Mo", "W", "V", "Cr", "Fe", "Nb", "Ta", "Si"},
        "exclude": {"O", "N"},
        "min_elements": 2,
        "applications": ["catalysis", "structural", "electronic"],
    },
    "hydroxide_oxyhydroxide": {
        "description": "Metal hydroxide/oxyhydroxide — water-relevant",
        "required": {"O"},
        "preferred": {"Fe", "Mn", "Ni", "Co", "Al", "Mg", "Ti", "Zn"},
        "min_elements": 2,
        "applications": ["catalysis", "water-treatment", "ion-exchange"],
    },
    "manganese_oxide": {
        "description": "MnOx family — Li-sieve, catalyst, battery",
        "required": {"Mn", "O"},
        "preferred": {"Li", "Na", "K", "Ca", "Fe", "Co", "Ni"},
        "min_elements": 2,
        "applications": ["lithium-recovery", "catalysis", "battery",
                          "ion-exchange"],
    },
}


def classify_material_from_counts(formula: str,
                                   counts: Dict[str, int]) -> Dict:
    """Classify material into functional categories.

    Mirrors functional_taxonomy.classify_material. Returns dict with
    primary_class, all_classes (list of {class, confidence,
    description, applications}), n_classes, applications (sorted list).
    """
    elem_set = set(counts.keys())
    n_elem = len(elem_set)

    matches = []

    for class_name, spec in FUNCTIONAL_CLASSES.items():
        confidence = 0.0

        required = spec.get("required", set())
        if required and not required.issubset(elem_set):
            continue

        requires_any = spec.get("requires_any", set())
        if requires_any and not (requires_any & elem_set):
            continue

        exclude = spec.get("exclude", set())
        if exclude and (exclude & elem_set):
            continue

        if n_elem < spec.get("min_elements", 1):
            continue

        preferred = (spec.get("preferred", set())
                     | spec.get("preferred_A", set())
                     | spec.get("preferred_B", set()))
        if preferred:
            overlap = len(elem_set & preferred)
            confidence = min(1.0, overlap / max(1, min(3, len(preferred))))
        else:
            confidence = 0.3

        if confidence > 0.1:
            matches.append({
                "class": class_name,
                "confidence": round(confidence, 3),
                "description": spec["description"],
                "applications": spec["applications"],
            })

    matches.sort(key=lambda x: x["confidence"], reverse=True)

    primary = matches[0]["class"] if matches else "unclassified"
    applications = set()
    for m in matches:
        applications.update(m["applications"])

    return {
        "formula": formula,
        "primary_class": primary,
        "all_classes": matches,
        "n_classes": len(matches),
        "applications": sorted(applications),
    }

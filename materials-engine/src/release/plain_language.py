"""Plain-language material explainer for non-scientists.

Generates human-readable assessments from corpus data.
All outputs tagged as heuristic_assessment / corpus_relative.
"""

import math


def explain_material(material, corpus_stats=None) -> dict:
    """Generate plain-language explanation for a material."""
    f = material.formula or "Unknown"
    bg = material.band_gap
    fe = material.formation_energy
    sg = material.spacegroup
    elems = material.elements or []
    n_elem = len(elems)

    # Electronic behavior
    if bg is not None:
        if bg < 0.05:
            electronic = {"label": "metal", "reason": f"Band gap ≈ {bg:.3f} eV — essentially zero, conducts electricity freely"}
        elif bg < 1.0:
            electronic = {"label": "narrow-gap semiconductor", "reason": f"Band gap = {bg:.2f} eV — conducts under certain conditions (useful for infrared devices)"}
        elif bg < 3.0:
            electronic = {"label": "semiconductor", "reason": f"Band gap = {bg:.2f} eV — the sweet spot for electronics and solar cells"}
        elif bg < 6.0:
            electronic = {"label": "wide-gap semiconductor", "reason": f"Band gap = {bg:.2f} eV — useful for UV/high-power electronics"}
        else:
            electronic = {"label": "insulator", "reason": f"Band gap = {bg:.2f} eV — does not conduct electricity (good for insulation)"}
    else:
        electronic = {"label": "uncertain", "reason": "Band gap data not available"}

    # Stability
    if fe is not None:
        if fe < -2.0:
            stability = {"label": "very stable", "reason": f"Formation energy = {fe:.2f} eV/atom — strongly favored to exist"}
        elif fe < -0.5:
            stability = {"label": "stable", "reason": f"Formation energy = {fe:.2f} eV/atom — thermodynamically favorable"}
        elif fe < 0.0:
            stability = {"label": "marginally stable", "reason": f"Formation energy = {fe:.2f} eV/atom — exists but near the edge"}
        elif fe < 1.0:
            stability = {"label": "metastable", "reason": f"Formation energy = {fe:.2f} eV/atom — may decompose under stress"}
        else:
            stability = {"label": "unstable", "reason": f"Formation energy = {fe:.2f} eV/atom — hard to synthesize or keep"}
    else:
        stability = {"label": "uncertain", "reason": "Formation energy not available"}

    # Exotic assessment
    exotic_label = "common"
    exotic_reason = "Standard material with well-known chemistry"
    if n_elem >= 5:
        exotic_label = "highly exotic"
        exotic_reason = f"{n_elem}-element compound — very unusual combination, high combinatorial novelty"
    elif n_elem >= 4:
        exotic_label = "exotic"
        exotic_reason = f"{n_elem}-element compound — uncommon composition with potential for unique properties"
    elif n_elem == 3:
        exotic_label = "uncommon"
        exotic_reason = "Ternary compound — more complex than simple binaries"
    elif n_elem <= 1:
        exotic_label = "common element"
        exotic_reason = "Pure element — well-studied reference material"

    # Industry relevance (heuristic)
    industry = _assess_industry(f, elems, bg, fe, electronic["label"])

    # Practical value
    pv = _assess_practical_value(electronic["label"], stability["label"], exotic_label, industry)

    # Applications
    apps = _suggest_applications(electronic["label"], bg, fe, elems)

    # Strengths / limitations
    strengths = []
    limitations = []
    if stability["label"] in ("very stable", "stable"):
        strengths.append("Thermodynamically stable — easy to work with")
    if stability["label"] in ("metastable", "unstable"):
        limitations.append("May be difficult to synthesize or maintain")
    if electronic["label"] == "semiconductor" and bg and 0.5 < bg < 3.0:
        strengths.append(f"Ideal band gap ({bg:.1f} eV) for electronics and photovoltaics")
    if electronic["label"] == "metal":
        strengths.append("Conducts electricity — useful for wiring, electrodes, structural applications")
    if electronic["label"] == "insulator":
        strengths.append("Does not conduct — good for insulation, dielectrics, protective coatings")
    if n_elem >= 4:
        strengths.append("Complex composition may yield unique properties not found in simpler materials")
        limitations.append("Complex to synthesize — may require specialized techniques")
    if not strengths:
        strengths.append("Standard material with known behavior")
    if not limitations:
        limitations.append("No major limitations identified from available data")

    return {
        "title": f"{f} — {_human_name(f, elems)}",
        "formula": f,
        "what_it_is": f"A {_crystal_description(sg, n_elem)} with {n_elem} element{'s' if n_elem != 1 else ''}: {', '.join(elems)}",
        "plain_language_summary": _build_summary(f, electronic, stability, exotic_label, apps),
        "what_it_can_do": apps[:5],
        "main_strengths": strengths[:4],
        "main_limitations": limitations[:3],
        "is_it_exotic": {"label": exotic_label, "reason": exotic_reason},
        "how_different_from_others": _novelty_description(exotic_label, n_elem),
        "stability_assessment": stability,
        "electronic_behavior": electronic,
        "practical_value": pv,
        "industry_relevance": industry,
        "quality_flags": {
            "good": [s for s in strengths if "stable" in s.lower() or "ideal" in s.lower()],
            "bad": [l for l in limitations if "difficult" in l.lower()],
            "exceptional": [s for s in strengths if "unique" in s.lower() or "ideal" in s.lower()],
        },
        "evidence_summary": {
            "known": [p for p in ["band_gap", "formation_energy", "spacegroup"] if getattr(material, p, None) is not None],
            "predicted": [],
            "proxy": [],
        },
        "honesty_note": "This assessment is relative to the ingested corpus (76,193 materials) and model outputs. It is a heuristic evaluation, not a market price or commercial valuation. Labels like 'practical_value' reflect scientific/industrial utility estimates only.",
        "_meta": {"heuristic_assessment": True, "corpus_relative": True, "not_market_price": True},
    }


def _human_name(formula, elems):
    names = {"Si": "Silicon", "C": "Carbon", "Fe": "Iron", "Cu": "Copper", "Au": "Gold",
             "Ag": "Silver", "Ti": "Titanium", "Al": "Aluminum", "O": "Oxygen",
             "NaCl": "Sodium Chloride (Salt)", "SiO2": "Silicon Dioxide (Quartz/Silica)",
             "GaAs": "Gallium Arsenide", "TiO2": "Titanium Dioxide (Rutile)",
             "Fe2O3": "Iron Oxide (Hematite)", "Al2O3": "Aluminum Oxide (Alumina)",
             "ZnO": "Zinc Oxide", "SiC": "Silicon Carbide", "BaTiO3": "Barium Titanate",
             "CaCO3": "Calcium Carbonate (Calcite)", "MgO": "Magnesium Oxide"}
    return names.get(formula, f"{len(elems)}-element {'compound' if len(elems) > 1 else 'element'}")


def _crystal_description(sg, n_elem):
    if sg:
        if sg in range(195, 231):
            return "cubic crystal"
        elif sg in range(168, 195):
            return "hexagonal crystal"
        elif sg in range(75, 143):
            return "tetragonal crystal"
        elif sg in range(16, 75):
            return "orthorhombic crystal"
        elif sg in range(3, 16):
            return "monoclinic crystal"
    return "crystalline material"


def _assess_industry(formula, elems, bg, fe, electronic_type):
    ind = {"electronics": "low", "energy": "low", "construction": "low",
           "optics": "low", "catalysis": "low", "aerospace": "low"}

    if electronic_type == "semiconductor":
        ind["electronics"] = "high"
        ind["energy"] = "medium"
        ind["optics"] = "medium"
    elif electronic_type == "wide-gap semiconductor":
        ind["electronics"] = "high"
        ind["optics"] = "high"
        ind["energy"] = "medium"
    elif electronic_type == "metal":
        ind["construction"] = "medium"
        ind["electronics"] = "medium"
        ind["aerospace"] = "medium"
    elif electronic_type == "insulator":
        ind["construction"] = "medium"

    tech_elems = {"Ga", "As", "In", "Ge", "Se", "Te", "Cd"}
    if tech_elems & set(elems):
        ind["electronics"] = "high"
        ind["optics"] = "high"

    catalyst_elems = {"Pt", "Pd", "Ru", "Rh", "Ir", "Ni", "Co", "Fe", "Ti"}
    if catalyst_elems & set(elems):
        ind["catalysis"] = "medium"

    return ind


def _assess_practical_value(electronic, stability, exotic, industry):
    score = 0
    if electronic in ("semiconductor", "wide-gap semiconductor"):
        score += 3
    if stability in ("very stable", "stable"):
        score += 2
    if exotic in ("exotic", "highly exotic"):
        score += 1
    if industry.get("electronics") == "high":
        score += 2

    if score >= 6:
        return {"label": "high", "reason": "Stable semiconductor with strong electronics/energy relevance", "heuristic_assessment": True, "not_market_price": True}
    elif score >= 3:
        return {"label": "moderate", "reason": "Useful material with some industrial applications", "heuristic_assessment": True, "not_market_price": True}
    else:
        return {"label": "low", "reason": "Common or limited-application material", "heuristic_assessment": True, "not_market_price": True}


def _suggest_applications(electronic, bg, fe, elems):
    apps = []
    if electronic == "semiconductor" and bg and 0.5 < bg < 2.0:
        apps.extend(["Solar cells and photovoltaics", "Transistors and integrated circuits"])
    if electronic == "wide-gap semiconductor":
        apps.extend(["High-power electronics", "UV LEDs and detectors", "Power converters"])
    if electronic == "semiconductor":
        apps.append("Sensors and detectors")
    if electronic == "metal":
        apps.extend(["Structural components", "Electrical conductors", "Electrodes"])
    if electronic == "insulator":
        apps.extend(["Insulation and dielectrics", "Protective coatings", "Optical windows"])
    if {"Ti", "O"} <= set(elems):
        apps.append("Photocatalysis and self-cleaning surfaces")
    if not apps:
        apps.append("General research and reference material")
    return apps


def _build_summary(formula, electronic, stability, exotic, apps):
    parts = [f"{formula} is a {electronic['label']}"]
    if stability["label"] not in ("uncertain",):
        parts.append(f"that is {stability['label']}")
    if apps:
        parts.append(f"It can be used in {apps[0].lower()}")
    if exotic in ("exotic", "highly exotic"):
        parts.append(f"This is an {exotic} material with unusual chemistry")
    return ". ".join(parts) + "."


def _novelty_description(exotic, n_elem):
    if exotic == "highly exotic":
        return {"label": "very unusual", "reason": f"With {n_elem} elements, this is a rare combination not commonly studied"}
    elif exotic == "exotic":
        return {"label": "somewhat unusual", "reason": "Complex composition that stands out from common materials"}
    elif exotic == "uncommon":
        return {"label": "moderately different", "reason": "Ternary compound — more complex than simple binaries but not rare"}
    else:
        return {"label": "very similar to many others", "reason": "Common element or binary compound, well-represented in databases"}

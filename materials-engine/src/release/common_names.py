"""Common name → formula registry with ES/EN support and mixture handling.

Resolves everyday names (water, sal, quartz) to chemical formulas,
and honestly identifies mixtures/non-crystalline materials.
"""

# entity_type: "crystal" | "mixture" | "element" | "gas" | "everyday"
COMMON_NAMES = {
    # --- Water / Ice ---
    "water": {"formula": "H2O", "type": "crystal", "note": "Ice (solid H2O) is in many crystal databases; liquid water is not a single crystal"},
    "agua": {"formula": "H2O", "type": "crystal", "note": "Hielo (H2O sólido) es cristalino; el agua líquida no es un cristal único"},
    "ice": {"formula": "H2O", "type": "crystal"},
    "hielo": {"formula": "H2O", "type": "crystal"},

    # --- Gases ---
    "oxygen": {"formula": "O2", "type": "gas", "note": "Diatomic gas, not typically in crystal databases as a solid"},
    "oxígeno": {"formula": "O2", "type": "gas"},
    "ozone": {"formula": "O3", "type": "gas"},
    "ozono": {"formula": "O3", "type": "gas"},
    "nitrogen": {"formula": "N2", "type": "gas"},
    "nitrógeno": {"formula": "N2", "type": "gas"},
    "carbon dioxide": {"formula": "CO2", "type": "gas", "note": "Solid CO2 (dry ice) has a crystal structure"},
    "dióxido de carbono": {"formula": "CO2", "type": "gas"},

    # --- Salts & Minerals ---
    "salt": {"formula": "NaCl", "type": "crystal"},
    "sal": {"formula": "NaCl", "type": "crystal"},
    "quartz": {"formula": "SiO2", "type": "crystal"},
    "cuarzo": {"formula": "SiO2", "type": "crystal"},
    "silica": {"formula": "SiO2", "type": "crystal"},
    "sílice": {"formula": "SiO2", "type": "crystal"},
    "alumina": {"formula": "Al2O3", "type": "crystal"},
    "alúmina": {"formula": "Al2O3", "type": "crystal"},
    "hematite": {"formula": "Fe2O3", "type": "crystal"},
    "hematita": {"formula": "Fe2O3", "type": "crystal"},
    "magnetite": {"formula": "Fe3O4", "type": "crystal"},
    "magnetita": {"formula": "Fe3O4", "type": "crystal"},
    "calcite": {"formula": "CaCO3", "type": "crystal"},
    "calcita": {"formula": "CaCO3", "type": "crystal"},
    "rutile": {"formula": "TiO2", "type": "crystal"},
    "rutilo": {"formula": "TiO2", "type": "crystal"},
    "titanium dioxide": {"formula": "TiO2", "type": "crystal"},
    "dióxido de titanio": {"formula": "TiO2", "type": "crystal"},

    # --- Elements ---
    "copper": {"formula": "Cu", "type": "element"},
    "cobre": {"formula": "Cu", "type": "element"},
    "iron": {"formula": "Fe", "type": "element"},
    "hierro": {"formula": "Fe", "type": "element"},
    "gold": {"formula": "Au", "type": "element"},
    "oro": {"formula": "Au", "type": "element"},
    "silver": {"formula": "Ag", "type": "element"},
    "plata": {"formula": "Ag", "type": "element"},
    "silicon": {"formula": "Si", "type": "element"},
    "silicio": {"formula": "Si", "type": "element"},
    "graphite": {"formula": "C", "type": "crystal", "note": "Carbon in graphite crystal structure"},
    "grafito": {"formula": "C", "type": "crystal"},
    "diamond": {"formula": "C", "type": "crystal", "note": "Carbon in diamond crystal structure (different spacegroup from graphite)"},
    "diamante": {"formula": "C", "type": "crystal"},

    # --- Tech materials ---
    "gallium arsenide": {"formula": "GaAs", "type": "crystal"},
    "arseniuro de galio": {"formula": "GaAs", "type": "crystal"},
    "silicon carbide": {"formula": "SiC", "type": "crystal"},
    "carburo de silicio": {"formula": "SiC", "type": "crystal"},
    "zinc oxide": {"formula": "ZnO", "type": "crystal"},
    "óxido de zinc": {"formula": "ZnO", "type": "crystal"},
    "barium titanate": {"formula": "BaTiO3", "type": "crystal"},
    "titanato de bario": {"formula": "BaTiO3", "type": "crystal"},

    # --- Everyday mixtures (NOT single crystals) ---
    "air": {"formula": None, "type": "mixture", "composition": "~78% N2 + 21% O2 + 1% Ar + traces",
            "note": "Air is a gas mixture, not a single crystalline material. Try searching for N2 or O2 individually."},
    "aire": {"formula": None, "type": "mixture", "composition": "~78% N2 + 21% O2 + 1% Ar + trazas",
             "note": "El aire es una mezcla gaseosa, no un material cristalino único. Prueba buscar N2 u O2 por separado."},
    "steel": {"formula": None, "type": "everyday", "composition": "Fe + C (0.2-2%) + alloy elements",
              "note": "Steel is an iron alloy, not a single crystal. The engine has pure Fe and Fe-based compounds. Try 'Fe' or 'Fe2O3'."},
    "acero": {"formula": None, "type": "everyday", "composition": "Fe + C (0.2-2%) + elementos de aleación",
              "note": "El acero es una aleación de hierro, no un cristal único. Prueba 'Fe' o 'Fe2O3'."},
    "glass": {"formula": None, "type": "everyday", "composition": "Amorphous SiO2 + additives",
              "note": "Glass is amorphous (non-crystalline). The engine has crystalline SiO2 (quartz). Try 'SiO2'."},
    "vidrio": {"formula": None, "type": "everyday", "composition": "SiO2 amorfo + aditivos",
               "note": "El vidrio es amorfo (no cristalino). Prueba 'SiO2' para cuarzo cristalino."},
    "concrete": {"formula": None, "type": "everyday", "composition": "Cite calcium silicate hydrates + aggregates",
                 "note": "Concrete is a composite, not a single crystal. Try 'CaO' or 'SiO2' for component minerals."},
    "hormigón": {"formula": None, "type": "everyday", "composition": "Silicatos cálcicos hidratados + agregados",
                 "note": "El hormigón es un compuesto, no un cristal. Prueba 'CaO' o 'SiO2'."},
    "cement": {"formula": None, "type": "everyday", "composition": "Ca3SiO5, Ca2SiO4, Ca3Al2O6 + more",
               "note": "Cement is a mixture of calcium silicates. Try 'CaO' or 'Al2O3'."},
    "cemento": {"formula": None, "type": "everyday", "composition": "Ca3SiO5, Ca2SiO4, Ca3Al2O6 + más"},
    "plastic": {"formula": None, "type": "everyday", "note": "Plastics are organic polymers, not in the inorganic crystal corpus."},
    "plástico": {"formula": None, "type": "everyday", "note": "Los plásticos son polímeros orgánicos, no están en el corpus de cristales inorgánicos."},
    "wood": {"formula": None, "type": "everyday", "note": "Wood is an organic composite (cellulose + lignin), not a crystal."},
    "madera": {"formula": None, "type": "everyday", "note": "La madera es un compuesto orgánico, no un cristal."},
}


def resolve_query(q: str) -> dict:
    """Resolve a user query to formula or special response."""
    q_lower = q.strip().lower()

    # Direct common name match
    if q_lower in COMMON_NAMES:
        entry = COMMON_NAMES[q_lower]
        if entry["formula"]:
            return {"resolved": True, "formula": entry["formula"], "source": "common_name",
                    "original_query": q, "entity_type": entry["type"],
                    "note": entry.get("note", "")}
        else:
            return {"resolved": False, "formula": None, "source": "common_name",
                    "original_query": q, "entity_type": entry["type"],
                    "composition": entry.get("composition", ""),
                    "note": entry.get("note", ""),
                    "suggestion": _suggest_related(entry)}

    # Looks like a formula (has uppercase letter)
    if any(c.isupper() for c in q):
        return {"resolved": True, "formula": q.strip(), "source": "formula_direct",
                "original_query": q, "entity_type": "crystal", "note": ""}

    # Fuzzy: try partial match on common names
    for name, entry in COMMON_NAMES.items():
        if q_lower in name or name in q_lower:
            if entry["formula"]:
                return {"resolved": True, "formula": entry["formula"], "source": "fuzzy_name",
                        "original_query": q, "matched_name": name,
                        "entity_type": entry["type"], "note": entry.get("note", "")}

    return {"resolved": False, "formula": None, "source": "not_found",
            "original_query": q, "entity_type": "unknown",
            "note": f"No match for '{q}'. Try a chemical formula (e.g. GaAs) or common name (e.g. quartz, salt)."}


def _suggest_related(entry):
    """Suggest related searchable materials for mixtures."""
    comp = entry.get("composition", "")
    suggestions = []
    for word in comp.replace("+", " ").replace(",", " ").replace("~", "").split():
        w = word.strip().rstrip("%)")
        if any(c.isupper() for c in w) and len(w) <= 10 and not w.replace(".", "").isdigit():
            suggestions.append(w)
    return suggestions[:3] if suggestions else []

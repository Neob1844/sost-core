"""Common name → formula registry with multilingual support and known-entity handling.

Supports ES/EN/FR/DE/IT. Extensible for RU/ZH/JA/AR.
Classifies entities as corpus_material, known_molecule_not_in_corpus,
elemental_gas_or_noble_gas, mixture_or_everyday_material.
"""

import re

# Stop words by language (articles, prepositions, determinants)
STOP_WORDS = {
    "es": {"el","la","los","las","un","una","unas","unos","del","de","al","lo"},
    "en": {"the","a","an","of","some"},
    "fr": {"le","la","les","un","une","de","du","des","l","d"},
    "de": {"der","die","das","ein","eine","den","dem","des","von"},
    "it": {"il","lo","la","i","gli","le","un","una","di","del","della","dei","delle"},
    "ru": {"и","в","на","с","из","по","к","о","у","для"},
    "ar": {"ال","في","من","على","إلى"},
}
ALL_STOPS = set()
for s in STOP_WORDS.values():
    ALL_STOPS |= s


def normalize_query(q: str) -> str:
    """Normalize a user query: lowercase, strip articles, trim, remove accents for matching."""
    q = q.strip().lower()
    # Remove common punctuation
    q = re.sub(r'[¿¡?!.,;:()"\']', '', q)
    # Normalize accented chars for matching
    q_norm = q
    for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ü","u"),("ñ","n"),
                     ("à","a"),("è","e"),("ì","i"),("ò","o"),("ù","u"),("ä","a"),("ö","o"),
                     ("â","a"),("ê","e"),("î","i"),("ô","o"),("û","u"),("ç","c")]:
        q_norm = q_norm.replace(src, dst)
    # Remove stop words
    words = q_norm.split()
    words = [w for w in words if w not in ALL_STOPS]
    return " ".join(words).strip()


# === REGISTRY ===
# type: "crystal" | "gas" | "element" | "mixture" | "everyday" | "noble_gas" | "molecule"

COMMON_NAMES = {}

def _add(names, formula, entity_type, note="", composition="", uses=None, related=None):
    """Register multiple names for the same entity."""
    entry = {"formula": formula, "type": entity_type, "note": note,
             "composition": composition, "uses": uses or [], "related": related or []}
    for n in names:
        COMMON_NAMES[n] = entry

# --- Water / Ice ---
_add(["water","agua","wasser","eau","acqua","ice","hielo","eis","glace","ghiaccio",
      "\u0432\u043e\u0434\u0430","\u043b\u0451\u0434","\u6c34","\u6c37","\u6c34","\u0645\u0627\u0621"],
     "H2O", "crystal", "Ice (solid H2O) is crystalline; liquid water is amorphous")

# --- Common salts & minerals ---
_add(["salt","sal","salz","sel","sale","sodium chloride","cloruro de sodio","natriumchlorid","chlorure de sodium",
      "\u0441\u043e\u043b\u044c","\u76d0","\u5869","\u0645\u0644\u062d"],
     "NaCl", "crystal")
_add(["quartz","cuarzo","quarz","quartzo","\u043a\u0432\u0430\u0440\u0446","\u77f3\u82f1","\u30af\u30a9\u30fc\u30c4","\u0643\u0648\u0627\u0631\u062a\u0632"],
     "SiO2", "crystal")
_add(["silica","silice","sílice","silicium dioxide","dioxido de silicio"],
     "SiO2", "crystal")
_add(["alumina","alumina","alúmina","aluminum oxide","oxido de aluminio","óxido de aluminio","aluminiumoxid","alumine","allumina"],
     "Al2O3", "crystal")
_add(["hematite","hematita","hamatit","hématite","ematite"],
     "Fe2O3", "crystal")
_add(["magnetite","magnetita","magnetit"],
     "Fe3O4", "crystal")
_add(["calcite","calcita","calcit","calcaire"],
     "CaCO3", "crystal")
_add(["rutile","rutilo","rutil"],
     "TiO2", "crystal")
_add(["titanium dioxide","dioxido de titanio","dióxido de titanio","titandioxid","dioxyde de titane","biossido di titanio"],
     "TiO2", "crystal")
_add(["zinc oxide","oxido de zinc","óxido de zinc","zinkoxid","oxyde de zinc","ossido di zinco"],
     "ZnO", "crystal")
_add(["barium titanate","titanato de bario"],
     "BaTiO3", "crystal")

# --- Elements ---
_add(["copper","cobre","kupfer","cuivre","rame","\u043c\u0435\u0434\u044c","\u94dc","\u9285","\u0646\u062d\u0627\u0633"], "Cu", "element")
_add(["iron","hierro","eisen","fer","ferro","\u0436\u0435\u043b\u0435\u0437\u043e","\u94c1","\u9244","\u062d\u062f\u064a\u062f"], "Fe", "element")
_add(["gold","oro","or","ouro","\u0437\u043e\u043b\u043e\u0442\u043e","\u91d1","\u0630\u0647\u0628"], "Au", "element")
_add(["silver","plata","silber","argent","argento","\u0441\u0435\u0440\u0435\u0431\u0440\u043e","\u94f6","\u9280","\u0641\u0636\u0629"], "Ag", "element")
_add(["silicon","silicio","silizium","silicium","\u043a\u0440\u0435\u043c\u043d\u0438\u0439","\u7845","\u0633\u064a\u0644\u064a\u0643\u0648\u0646"], "Si", "element")
_add(["aluminum","aluminio","aluminium","alluminio","\u0430\u043b\u044e\u043c\u0438\u043d\u0438\u0439","\u94dd","\u0623\u0644\u0648\u0645\u0646\u064a\u0648\u0645"], "Al", "element")
_add(["titanium","titanio","titan","titane","\u0442\u0438\u0442\u0430\u043d","\u949b","\u062a\u064a\u062a\u0627\u0646\u064a\u0648\u0645"], "Ti", "element")
_add(["carbon","carbono","kohlenstoff","carbone","carbonio","\u0443\u0433\u043b\u0435\u0440\u043e\u0434","\u78b3","\u0643\u0631\u0628\u0648\u0646"], "C", "element")
_add(["graphite","grafito","graphit","graphite","grafite"],
     "C", "crystal", "Carbon in graphite crystal structure")
_add(["diamond","diamante","diamant","diamante"],
     "C", "crystal", "Carbon in diamond crystal structure (different spacegroup)")

# --- Tech materials ---
_add(["gallium arsenide","arseniuro de galio"], "GaAs", "crystal")
_add(["silicon carbide","carburo de silicio","siliziumkarbid","carbure de silicium","carburo di silicio"],
     "SiC", "crystal")

# --- Known molecules NOT typically in crystal corpus ---
_add(["oxygen","oxigeno","oxígeno","sauerstoff","oxygene","ossigeno",
      "\u043a\u0438\u0441\u043b\u043e\u0440\u043e\u0434","\u6c27","\u9178\u7d20","\u0623\u0643\u0633\u062c\u064a\u0646"],
     "O2", "molecule",
     "Oxygen (O2) is a diatomic gas essential for life. As a molecular gas, it is not typically represented as a bulk crystal in this corpus.",
     uses=["Respiration", "Combustion", "Steel manufacturing", "Medical oxygen", "Water treatment"],
     related=["Fe2O3", "TiO2", "Al2O3", "SiO2"])
_add(["nitrogen","nitrogeno","nitrógeno","stickstoff","azote","azoto",
      "\u0430\u0437\u043e\u0442","\u6c2e","\u7a92\u7d20","\u0646\u064a\u062a\u0631\u0648\u062c\u064a\u0646"],
     "N2", "molecule",
     "Nitrogen (N2) is the most abundant gas in Earth's atmosphere (~78%). It is not a bulk crystalline material in this corpus.",
     uses=["Atmosphere composition", "Fertilizer production (Haber process)", "Cryogenics", "Inert gas shielding", "Food preservation"],
     related=["GaN", "BN", "AlN", "Si3N4"])
_add(["ozone","ozono","ozon","\u043e\u0437\u043e\u043d","\u81ed\u6c27","\u30aa\u30be\u30f3","\u0623\u0648\u0632\u0648\u0646"],
     "O3", "molecule",
     "Ozone (O3) is a reactive gas in Earth's stratosphere. Not a bulk crystal.",
     uses=["UV protection (ozone layer)", "Water purification", "Air treatment"],
     related=["O2"])
_add(["hydrogen","hidrogeno","hidrógeno","wasserstoff","hydrogene","idrogeno"],
     "H2", "molecule",
     "Hydrogen (H2) is the lightest and most abundant element. As a diatomic gas, it's not in the crystal corpus.",
     uses=["Fuel cells", "Rocket propulsion", "Chemical synthesis", "Hydrogenation"],
     related=["H2O", "LiH", "NaH"])
_add(["carbon dioxide","dioxido de carbono","dióxido de carbono","kohlendioxid","dioxyde de carbone","anidride carbonica"],
     "CO2", "molecule",
     "CO2 is a gas (solid form: dry ice). Not typically in bulk crystal databases.",
     uses=["Climate science", "Carbonated beverages", "Fire extinguishers", "Supercritical fluid extraction"],
     related=["CaCO3", "MgCO3"])
_add(["ammonia","amoniaco","amoniak","ammoniac","ammoniaca"],
     "NH3", "molecule",
     "Ammonia (NH3) is an important industrial gas. Not a bulk crystal.",
     uses=["Fertilizer production", "Refrigeration", "Cleaning products", "Chemical synthesis"],
     related=["GaN", "AlN", "BN"])
_add(["methane","metano","methan","méthane"],
     "CH4", "molecule",
     "Methane is the simplest hydrocarbon. Organic/molecular, not in inorganic crystal corpus.",
     uses=["Natural gas fuel", "Chemical feedstock", "Hydrogen production"],
     related=["C", "SiC"])

# --- Noble gases ---
_add(["helium","helio","hélium","elio","\u0433\u0435\u043b\u0438\u0439","\u6c26","\u30d8\u30ea\u30a6\u30e0","\u0647\u064a\u0644\u064a\u0648\u0645"],
     "He", "noble_gas",
     "Helium is a noble gas — it does not form bulk crystals under normal conditions.",
     uses=["Cryogenics (MRI cooling)", "Leak detection", "Controlled atmospheres", "Balloons", "Deep-sea diving gas"],
     related=[])
_add(["neon","neon","neón","néon"],
     "Ne", "noble_gas",
     "Neon is a noble gas used in lighting. Does not form crystals.",
     uses=["Neon signs", "Lasers", "Cryogenics"],
     related=[])
_add(["argon","argon","argón"],
     "Ar", "noble_gas",
     "Argon is the third most abundant gas in Earth's atmosphere. Noble gas, no bulk crystal.",
     uses=["Welding shielding gas", "Incandescent light bulbs", "Cryogenics", "Window insulation"],
     related=[])
_add(["krypton","cripton","kriptón"],
     "Kr", "noble_gas", "Noble gas used in specialty lighting.", uses=["Flash photography", "Lasers"], related=[])
_add(["xenon","xenon","xenón"],
     "Xe", "noble_gas", "Noble gas used in ion propulsion and lighting.", uses=["Ion thrusters", "Anesthesia", "Headlights"], related=[])

# --- Mixtures / everyday materials ---
_add(["air","aire","luft","aria","\u0432\u043e\u0437\u0434\u0443\u0445","\u7a7a\u6c17","\u7a7a\u6c14","\u0647\u0648\u0627\u0621"],
     None, "mixture",
     "Air is a gas mixture (~78% N2 + 21% O2 + 1% Ar + traces), not a single crystal. Try searching for N2 or O2 individually.",
     composition="~78% N2 + 21% O2 + 1% Ar + traces",
     related=["N2", "O2"])
_add(["steel","acero","stahl","acier","acciaio"],
     None, "everyday",
     "Steel is an iron alloy (Fe + 0.2-2% C + alloy elements), not a single crystal. Try 'Fe' or 'Fe2O3'.",
     composition="Fe + C (0.2-2%) + Mn, Cr, Ni, etc.",
     related=["Fe", "Fe2O3", "Cr"])
_add(["glass","vidrio","glas","verre","vetro"],
     None, "everyday",
     "Glass is amorphous (non-crystalline) SiO2 + additives. Try 'SiO2' for crystalline quartz.",
     composition="Amorphous SiO2 + Na2O, CaO, etc.",
     related=["SiO2"])
_add(["concrete","hormigon","hormigón","beton","béton","calcestruzzo"],
     None, "everyday",
     "Concrete is a composite material, not a single crystal. Try 'CaO' or 'SiO2' for components.",
     composition="Calcium silicate hydrates + aggregates",
     related=["CaO", "SiO2", "Al2O3"])
_add(["cement","cemento","zement","ciment"],
     None, "everyday",
     "Cement is a mixture of calcium silicates. Try 'CaO' or 'Al2O3'.",
     composition="Ca3SiO5 + Ca2SiO4 + Ca3Al2O6",
     related=["CaO", "Al2O3"])
_add(["plastic","plastico","plástico","plastik","plastique","plastica"],
     None, "everyday",
     "Plastics are organic polymers, not in the inorganic crystal corpus.")
_add(["wood","madera","holz","bois","legno"],
     None, "everyday",
     "Wood is an organic composite (cellulose + lignin), not a crystal.")
_add(["rubber","goma","caucho","caoutchouc","gomma","gummi"],
     None, "everyday",
     "Rubber is an organic polymer, not in the inorganic crystal corpus.")
_add(["paper","papel","papier","carta"],
     None, "everyday",
     "Paper is made from cellulose fibers, an organic material not in this crystal corpus.")


def resolve_query(q: str) -> dict:
    """Resolve a user query to formula, known entity, or special response."""
    q_clean = normalize_query(q)
    q_orig = q.strip()

    # Direct registry match (normalized)
    if q_clean in COMMON_NAMES:
        return _build_response(q_orig, q_clean, COMMON_NAMES[q_clean])

    # Try original lowercase too
    q_low = q_orig.lower().strip()
    if q_low in COMMON_NAMES:
        return _build_response(q_orig, q_low, COMMON_NAMES[q_low])

    # Looks like a formula (has uppercase letter)?
    if any(c.isupper() for c in q_orig):
        return {"resolved": True, "formula": q_orig.strip(), "source": "formula_direct",
                "original_query": q_orig, "entity_type": "corpus_material", "note": ""}

    # Fuzzy: partial match
    for name, entry in COMMON_NAMES.items():
        if q_clean in name or name in q_clean:
            return _build_response(q_orig, name, entry, source="fuzzy_name")

    return {"resolved": False, "formula": None, "source": "not_found",
            "original_query": q_orig, "entity_type": "unknown",
            "note": f"No match for '{q_orig}'. Try a chemical formula (e.g. GaAs, SiO2) or a common name (e.g. quartz, salt, water)."}


def _build_response(q_orig, matched, entry, source="common_name"):
    """Build structured response from registry entry."""
    etype = entry["type"]
    formula = entry.get("formula")

    # Map internal types to public classification
    if etype in ("crystal", "element"):
        classification = "corpus_material"
    elif etype == "molecule":
        classification = "known_molecule_not_in_corpus"
    elif etype == "noble_gas":
        classification = "elemental_gas_or_noble_gas"
    elif etype in ("mixture", "everyday"):
        classification = "mixture_or_everyday_material"
    else:
        classification = etype

    if formula:
        return {"resolved": True, "formula": formula, "source": source,
                "original_query": q_orig, "matched_name": matched,
                "entity_type": classification,
                "note": entry.get("note", ""),
                "uses": entry.get("uses", []),
                "related": entry.get("related", [])}
    else:
        return {"resolved": False, "formula": None, "source": source,
                "original_query": q_orig, "matched_name": matched,
                "entity_type": classification,
                "composition": entry.get("composition", ""),
                "note": entry.get("note", ""),
                "uses": entry.get("uses", []),
                "related": entry.get("related", []),
                "suggestion": entry.get("related", [])}

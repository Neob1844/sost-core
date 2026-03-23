"""Plain-language material explainer for non-scientists.

Generates human-readable assessments from corpus data.
All outputs tagged as heuristic_assessment / corpus_relative.
"""

import math

# === ELEMENTAL REFERENCE RULES ===
# Pure elements with FE≈0 are reference phases, NOT metastable
ELEMENTAL_OVERRIDES = {
    "Au": {"strategic": "very_high", "specialty": "very_high", "bulk": "low",
           "apps": ["Electrical contacts and connectors", "Corrosion-resistant coatings",
                    "Specialty electronics (bonding wires)", "Jewelry and decorative applications",
                    "Store-of-value / strategic precious metal", "Dental and medical devices"],
           "tags": ["PRECIOUS METAL", "STRATEGIC MATERIAL"],
           "sectors": {"electronics":"high","energy":"low","construction":"low","optics":"medium","catalysis":"medium","aerospace":"medium"}},
    "Ag": {"strategic": "high", "specialty": "high", "bulk": "low",
           "apps": ["Electrical contacts (highest conductivity)", "Antimicrobial coatings",
                    "Photography and mirrors", "Jewelry", "Solar cell contacts", "Brazing alloys"],
           "tags": ["PRECIOUS METAL"],
           "sectors": {"electronics":"high","energy":"medium","construction":"low","optics":"high","catalysis":"medium","aerospace":"low"}},
    "Cu": {"strategic": "high", "specialty": "medium", "bulk": "high",
           "apps": ["Electrical wiring and power transmission", "Heat exchangers", "Plumbing",
                    "Circuit boards (PCB)", "Electric motors", "Roofing and architecture"],
           "tags": ["STRATEGIC MATERIAL"]},
    "Fe": {"strategic": "high", "specialty": "low", "bulk": "very_high",
           "apps": ["Steel production (construction, infrastructure)", "Automotive industry",
                    "Machinery and tools", "Magnetic applications", "Cast iron products"],
           "tags": []},
    "Al": {"strategic": "high", "specialty": "medium", "bulk": "high",
           "apps": ["Aerospace structures", "Automotive lightweight components", "Packaging (foil, cans)",
                    "Construction (window frames)", "Electrical transmission lines"],
           "tags": []},
    "Si": {"strategic": "very_high", "specialty": "very_high", "bulk": "medium",
           "apps": ["Semiconductor chips (the foundation of electronics)", "Solar cells",
                    "MEMS devices", "Optical components", "Silicone production feedstock"],
           "tags": ["STRATEGIC MATERIAL"]},
    "C":  {"strategic": "high", "specialty": "very_high", "bulk": "medium",
           "apps": ["Graphite: lubricants, batteries (anodes), pencils, crucibles",
                    "Diamond: cutting tools, abrasives, jewelry, optics",
                    "Carbon fiber (from precursors)", "Activated carbon (filtration)"],
           "tags": []},
    "Ti": {"strategic": "high", "specialty": "high", "bulk": "medium",
           "apps": ["Aerospace (lightweight, strong)", "Medical implants (biocompatible)",
                    "Chemical processing equipment", "Marine applications", "Sporting goods"],
           "tags": ["STRATEGIC MATERIAL"]},
    "Pt": {"strategic": "very_high", "specialty": "very_high", "bulk": "low",
           "apps": ["Catalytic converters", "Fuel cell electrodes", "Laboratory equipment",
                    "Jewelry", "Chemotherapy drugs", "Hydrogen production catalysis"],
           "tags": ["PRECIOUS METAL", "STRATEGIC MATERIAL"],
           "sectors": {"electronics":"medium","energy":"high","construction":"low","optics":"medium","catalysis":"extra_high","aerospace":"medium"}},
    "Ni": {"strategic": "high", "specialty": "medium", "bulk": "high",
           "apps": ["Stainless steel alloys (8-12% Ni)", "Rechargeable batteries (NiMH, Li-ion cathodes)",
                    "Corrosion-resistant plating", "Superalloys for jet engines", "Coins"],
           "tags": ["STRATEGIC MATERIAL"],
           "sectors": {"electronics":"medium","energy":"high","construction":"medium","optics":"low","catalysis":"high","aerospace":"very_high"}},
    "Zn": {"strategic": "medium", "specialty": "low", "bulk": "high",
           "apps": ["Galvanizing steel (anti-corrosion)", "Zinc-air and zinc-carbon batteries",
                    "Die casting alloys", "Brass production (Cu+Zn)", "Dietary supplement"],
           "tags": [],
           "sectors": {"electronics":"low","energy":"medium","construction":"high","optics":"low","catalysis":"low","aerospace":"low"}},
    "Li": {"strategic": "very_high", "specialty": "very_high", "bulk": "low",
           "apps": ["Lithium-ion batteries (EVs, phones, grid storage)", "Lithium grease lubricants",
                    "Psychiatric medication (lithium carbonate)", "Nuclear fusion fuel (future)", "Glass and ceramics"],
           "tags": ["STRATEGIC MATERIAL"],
           "sectors": {"electronics":"very_high","energy":"extra_high","construction":"low","optics":"low","catalysis":"low","aerospace":"high"}},
    "W":  {"strategic": "very_high", "specialty": "very_high", "bulk": "low",
           "apps": ["Filaments and heating elements", "Cutting tools (tungsten carbide)", "Armor-piercing munitions",
                    "Radiation shielding", "Electrodes for welding"],
           "tags": ["STRATEGIC MATERIAL"],
           "sectors": {"electronics":"medium","energy":"medium","construction":"low","optics":"low","catalysis":"low","aerospace":"high"}},
    "Mo": {"strategic": "high", "specialty": "high", "bulk": "medium",
           "apps": ["Steel alloys (strength at high temperature)", "Catalysts (hydrodesulfurization)",
                    "Electrical contacts", "Missile and aircraft parts", "Lubricant additives (MoS2)"],
           "tags": ["STRATEGIC MATERIAL"],
           "sectors": {"electronics":"medium","energy":"medium","construction":"medium","optics":"low","catalysis":"high","aerospace":"high"}},
    "Co": {"strategic": "very_high", "specialty": "very_high", "bulk": "low",
           "apps": ["Li-ion battery cathodes (NMC, NCA)", "Superalloys for jet engines",
                    "Permanent magnets (SmCo)", "Blue pigments", "Catalysts"],
           "tags": ["STRATEGIC MATERIAL"],
           "sectors": {"electronics":"high","energy":"extra_high","construction":"low","optics":"low","catalysis":"high","aerospace":"very_high"}},
    "Mn": {"strategic": "medium", "specialty": "medium", "bulk": "high",
           "apps": ["Steel production (deoxidizer)", "Batteries (MnO2 in alkaline)", "Aluminum alloys",
                    "Glass decolorizer", "Water treatment"],
           "tags": [],
           "sectors": {"electronics":"low","energy":"medium","construction":"high","optics":"low","catalysis":"low","aerospace":"low"}},
    "Cr": {"strategic": "high", "specialty": "medium", "bulk": "high",
           "apps": ["Stainless steel (10-20% Cr)", "Chrome plating", "Refractory materials",
                    "Pigments", "Leather tanning"],
           "tags": ["STRATEGIC MATERIAL"],
           "sectors": {"electronics":"low","energy":"low","construction":"high","optics":"medium","catalysis":"medium","aerospace":"high"}},
    "V":  {"strategic": "high", "specialty": "high", "bulk": "low",
           "apps": ["Vanadium redox flow batteries", "Steel strengthening (small additions)",
                    "Titanium alloys (aerospace)", "Catalysts", "Superconducting magnets"],
           "tags": ["STRATEGIC MATERIAL"],
           "sectors": {"electronics":"low","energy":"high","construction":"medium","optics":"low","catalysis":"medium","aerospace":"high"}},
    "Mg": {"strategic": "medium", "specialty": "medium", "bulk": "high",
           "apps": ["Lightweight alloys (aerospace, automotive)", "Magnesium die casting",
                    "Flares and pyrotechnics", "Refractory bricks (MgO)", "Dietary supplement"],
           "tags": [],
           "sectors": {"electronics":"low","energy":"low","construction":"medium","optics":"low","catalysis":"low","aerospace":"high"}},
    "Sn": {"strategic": "medium", "specialty": "medium", "bulk": "medium",
           "apps": ["Solder (electronics assembly)", "Tin plating (food cans)", "Bronze alloys",
                    "Float glass process", "Pewter"],
           "tags": [],
           "sectors": {"electronics":"high","energy":"low","construction":"low","optics":"low","catalysis":"low","aerospace":"low"}},
    "Pb": {"strategic": "low", "specialty": "low", "bulk": "medium",
           "apps": ["Lead-acid batteries", "Radiation shielding", "Ammunition", "Cable sheathing",
                    "Historical: pipes, paint (now restricted)"],
           "tags": [],
           "sectors": {"electronics":"low","energy":"medium","construction":"low","optics":"low","catalysis":"low","aerospace":"low"}},
}

# Well-known compounds with curated apps
COMPOUND_OVERRIDES = {
    "NaCl": {"apps": ["Food preservation and seasoning", "De-icing roads", "Chemical feedstock (chlor-alkali)",
                       "Water softening", "Medical saline solutions"],
             "sectors": {"electronics":"low","energy":"low","construction":"low","optics":"low","catalysis":"low","aerospace":"low","chemical":"high"}},
    "SiO2": {"apps": ["Glass production", "Optical fibers", "Electronics (gate oxide in chips)",
                       "Construction (sand, concrete)", "Abrasives", "Chromatography"],
             "sectors": {"electronics":"medium","energy":"low","construction":"high","optics":"high","catalysis":"low","aerospace":"low"}},
    "TiO2": {"apps": ["White pigment (paint, sunscreen)", "Photocatalysis", "Self-cleaning surfaces",
                       "Food additive (E171)", "Optical coatings"],
             "sectors": {"electronics":"low","energy":"medium","construction":"medium","optics":"high","catalysis":"medium","aerospace":"low"}},
    "GaAs": {"apps": ["High-frequency electronics (5G, radar)", "LED and laser diodes",
                       "Solar cells (space-grade)", "Fiber optic communications"],
             "sectors": {"electronics":"extra_high","energy":"high","construction":"extra_low","optics":"very_high","catalysis":"low","aerospace":"high"}},
    "ZnO": {"apps": ["Sunscreen (UV blocker)", "Rubber vulcanization", "Varistors",
                      "Piezoelectric devices", "Cosmetics"],
            "sectors": {"electronics":"medium","energy":"medium","construction":"low","optics":"medium","catalysis":"low","aerospace":"low"}},
    "Al2O3": {"apps": ["Abrasives and grinding", "Ceramic components", "Alumina for aluminum smelting",
                        "Sapphire substrates (LEDs)", "Thermal insulation"],
              "sectors": {"electronics":"medium","energy":"low","construction":"medium","optics":"high","catalysis":"medium","aerospace":"medium"}},
    "Fe2O3": {"apps": ["Iron ore for steel production", "Pigments (red/brown)", "Magnetic storage media",
                        "Water treatment", "Catalyst support"],
              "sectors": {"electronics":"low","energy":"low","construction":"high","optics":"low","catalysis":"medium","aerospace":"low"}},
    "Fe3O4": {"apps": ["Magnetic applications", "Iron ore (magnetite)", "MRI contrast agents",
                        "Water purification", "High-density media"],
              "sectors": {"electronics":"medium","energy":"low","construction":"medium","optics":"low","catalysis":"medium","aerospace":"low"}},
    "CaCO3": {"apps": ["Cement and concrete production", "Paper filler", "Dietary calcium supplement",
                        "Antacid medication", "Agricultural lime"],
              "sectors": {"electronics":"low","energy":"low","construction":"extra_high","optics":"low","catalysis":"low","aerospace":"low"}},
    "SiC":  {"apps": ["Power electronics (EV inverters, fast chargers)", "Abrasives and cutting tools",
                       "High-temperature ceramics", "LED substrates", "Armor plates"],
             "sectors": {"electronics":"very_high","energy":"high","construction":"low","optics":"medium","catalysis":"low","aerospace":"high"}},
    "BaTiO3": {"apps": ["Capacitors (MLCC)", "Piezoelectric sensors and actuators",
                         "Positive temperature coefficient thermistors", "Optical modulators"],
               "sectors": {"electronics":"very_high","energy":"medium","construction":"low","optics":"medium","catalysis":"low","aerospace":"medium"}},
    "MgO":  {"apps": ["Refractory linings (furnaces, kilns)", "Electrical insulation", "Antacid (magnesium oxide)",
                       "Substrate for thin films", "Cement additive"],
             "sectors": {"electronics":"low","energy":"low","construction":"high","optics":"low","catalysis":"low","aerospace":"medium"}},
    "ZrO2": {"apps": ["Thermal barrier coatings (turbine blades)", "Dental crowns and implants",
                       "Oxygen sensors", "Solid oxide fuel cells (electrolyte)", "Jewelry (cubic zirconia)"],
             "sectors": {"electronics":"medium","energy":"high","construction":"low","optics":"medium","catalysis":"medium","aerospace":"very_high"}},
    "WO3":  {"apps": ["Electrochromic glass (smart windows)", "Gas sensors", "Photocatalysis",
                       "Tungsten metal production precursor"],
             "sectors": {"electronics":"medium","energy":"medium","construction":"medium","optics":"high","catalysis":"medium","aerospace":"low"}},
    "InP":  {"apps": ["High-speed fiber optic communications", "Microwave electronics", "Laser diodes (1550nm telecom)",
                       "Photovoltaics"],
             "sectors": {"electronics":"extra_high","energy":"medium","construction":"extra_low","optics":"extra_high","catalysis":"low","aerospace":"medium"}},
    "AlN":  {"apps": ["High-power electronics substrates", "UV LEDs", "Thermal management (high thermal conductivity)",
                       "Surface acoustic wave devices"],
             "sectors": {"electronics":"very_high","energy":"medium","construction":"low","optics":"high","catalysis":"low","aerospace":"high"}},
    "BN":   {"apps": ["Lubricant (hexagonal BN)", "Cutting tools (cubic BN)", "Thermal management",
                       "Cosmetics (smooth texture)", "Neutron absorber"],
             "sectors": {"electronics":"medium","energy":"low","construction":"low","optics":"low","catalysis":"low","aerospace":"high"}},
    "CdTe": {"apps": ["Thin-film solar cells (CdTe photovoltaics)", "Infrared detectors",
                       "Radiation detectors (medical imaging)", "Electro-optic modulators"],
             "sectors": {"electronics":"high","energy":"extra_high","construction":"extra_low","optics":"high","catalysis":"low","aerospace":"medium"}},
    "FeS2": {"apps": ["Iron production (pyrite as ore)", "Sulfuric acid manufacturing",
                       "Lithium-sulfur battery research", "Semiconductor research", "Historical: fire starting"],
             "sectors": {"electronics":"low","energy":"medium","construction":"low","optics":"low","catalysis":"medium","aerospace":"low"}},
    "Cu2O": {"apps": ["Antifouling marine paint", "Solar cell absorber (research)",
                       "Photocatalysis", "Red pigment", "Rectifier diodes (historical)"],
             "sectors": {"electronics":"medium","energy":"medium","construction":"low","optics":"medium","catalysis":"medium","aerospace":"low"}},
    "CuO":  {"apps": ["Catalyst for CO oxidation", "Superconductor precursor",
                       "Gas sensors", "Battery electrode research", "Wood preservative"],
             "sectors": {"electronics":"low","energy":"medium","construction":"low","optics":"low","catalysis":"high","aerospace":"low"}},
}


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

    # Detect elemental reference
    is_elemental = n_elem == 1 and f in ELEMENTAL_OVERRIDES
    is_pure_element = n_elem == 1

    # Stability — with elemental override
    if is_pure_element and fe is not None and abs(fe) < 0.1:
        stability = {"label": "elemental reference", "reason": f"Formation energy ≈ {fe:.2f} eV/atom — this is the reference phase for {f}. Near-zero is expected, not a sign of instability."}
    elif fe is not None:
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

    # Industry relevance — use override sectors if available
    if f in ELEMENTAL_OVERRIDES and "sectors" in ELEMENTAL_OVERRIDES[f]:
        industry = ELEMENTAL_OVERRIDES[f]["sectors"]
    elif f in COMPOUND_OVERRIDES and "sectors" in COMPOUND_OVERRIDES[f]:
        industry = COMPOUND_OVERRIDES[f]["sectors"]
    else:
        industry = _assess_industry(f, elems, bg, fe, electronic["label"])

    # Practical value
    pv = _assess_practical_value(electronic["label"], stability["label"], exotic_label, industry)

    # Confidence
    confidence = "high" if bg is not None and fe is not None and sg else ("medium" if bg is not None or fe is not None else "low")

    # Applications — use overrides for known materials
    if f in ELEMENTAL_OVERRIDES:
        apps = ELEMENTAL_OVERRIDES[f]["apps"]
    elif f in COMPOUND_OVERRIDES:
        apps = COMPOUND_OVERRIDES[f]["apps"]
    else:
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
        limitations.append("Assessment based on limited computed properties — real-world performance may differ")

    # Split value assessment
    if is_elemental and f in ELEMENTAL_OVERRIDES:
        eo = ELEMENTAL_OVERRIDES[f]
        value_split = {
            "scientific_interest": {"label": "low_novelty_high_importance",
                "reason": f"{f} is extremely well-studied — low novelty but foundational reference material"},
            "industrial_relevance": {"label": "high" if eo["bulk"] in ("high","very_high") else "specialty",
                "reason": f"Important in {apps[0].lower() if apps else 'various applications'}"},
            "strategic_significance": {"label": eo["strategic"],
                "reason": "Precious metal" if "PRECIOUS METAL" in eo.get("tags",[]) else "Strategic industrial material" if eo["strategic"]=="very_high" else "Standard industrial material"},
            "bulk_vs_specialty": {"label": "specialty" if eo["bulk"]=="low" else "bulk" if eo["bulk"]=="very_high" else "mixed",
                "reason": f"{'High specialty value, not a mass structural material' if eo['bulk']=='low' else 'Widely used in bulk applications'}"},
        }
        tags = eo.get("tags", [])
        pv = {"label": "strategically important", "reason": f"Low novelty but high real-world importance. {', '.join(tags) if tags else 'Well-known reference material'}.",
              "heuristic_assessment": True, "not_market_price": True}
    elif f in COMPOUND_OVERRIDES:
        value_split = {
            "scientific_interest": {"label": "well_characterized", "reason": "Well-known compound, extensively studied"},
            "industrial_relevance": {"label": "high", "reason": f"Used in {apps[0].lower() if apps else 'various fields'}"},
            "strategic_significance": {"label": "moderate", "reason": "Important industrial compound"},
            "bulk_vs_specialty": {"label": "mixed", "reason": "Both bulk and specialty uses"},
        }
        tags = []
    else:
        value_split = {
            "scientific_interest": {"label": exotic_label, "reason": exotic_reason},
            "industrial_relevance": {"label": pv["label"], "reason": pv["reason"]},
            "strategic_significance": {"label": "standard", "reason": "No special strategic classification"},
            "bulk_vs_specialty": {"label": "unknown", "reason": "Insufficient data for classification"},
        }
        tags = []

    return {
        "title": f"{f} — {_human_name(f, elems)}",
        "formula": f,
        "elemental_reference": is_pure_element,
        "material_tags": tags,
        "what_it_is": f"{'An elemental reference material' if is_pure_element else 'A ' + _crystal_description(sg, n_elem)} ({f}) with {n_elem} element{'s' if n_elem != 1 else ''}: {', '.join(elems)}",
        "plain_language_summary": _build_summary(f, electronic, stability, exotic_label, apps),
        "what_it_can_do": apps[:6],
        "main_strengths": strengths[:4],
        "main_limitations": limitations[:3],
        "is_it_exotic": {"label": exotic_label, "reason": exotic_reason},
        "how_different_from_others": _novelty_description(exotic_label, n_elem),
        "stability_assessment": stability,
        "electronic_behavior": electronic,
        "practical_value": pv,
        "value_breakdown": value_split,
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
        "human_comparisons": _get_comparisons(f),
        "public_importance_summary": _importance_summary(f, exotic_label, pv, is_elemental),
        "rarity": _get_rarity(elems),
        "trust_breakdown": _build_trust(material, is_elemental, f in ELEMENTAL_OVERRIDES, f in COMPOUND_OVERRIDES, confidence),
        "abundance_analysis": _build_abundance_analysis(elems, is_pure_element),
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


def _get_comparisons(formula):
    """Get curated human comparisons."""
    try:
        from .comparisons import get_comparisons
        return get_comparisons(formula)
    except Exception:
        return []


def _importance_summary(formula, exotic_label, pv, is_elemental):
    """Generate public importance summary."""
    if formula in ELEMENTAL_OVERRIDES:
        eo = ELEMENTAL_OVERRIDES[formula]
        if eo["strategic"] == "very_high":
            return {"label": "well-known but strategically important",
                    "reason": "Low scientific novelty, but very high real-world importance in specialized applications."}
        elif eo["bulk"] in ("high", "very_high"):
            return {"label": "common and industrially essential",
                    "reason": "Not exotic, but foundational for modern industry and infrastructure."}
        else:
            return {"label": "industrially useful reference material",
                    "reason": "Well-characterized material with established applications."}
    if formula in COMPOUND_OVERRIDES:
        return {"label": "well-known industrial compound",
                "reason": "Extensively studied compound with clear practical applications."}
    if exotic_label in ("exotic", "highly exotic"):
        return {"label": "scientifically interesting, potentially valuable",
                "reason": "Unusual composition that may have unique properties worth investigating."}
    return {"label": "standard corpus material",
            "reason": "Part of the general materials corpus without special strategic classification."}


def _build_trust(material, is_elemental, has_elem_override, has_compound_override, confidence):
    """Build trust/provenance breakdown."""
    known = []
    heuristic = ["practical_value", "industry_relevance", "rarity_human_label", "exotic_assessment"]
    manual = []
    for p in ["formula", "spacegroup", "formation_energy", "band_gap", "source", "elements"]:
        if getattr(material, p, None) is not None:
            known.append(p)
    if has_elem_override:
        manual.extend(["elemental_reference_label", "application_prioritization"])
    if has_compound_override:
        manual.append("application_override")
    reason = "All core properties from DFT corpus" if len(known) >= 4 else "Some properties missing"
    if manual:
        reason += "; some labels manually curated for well-known materials"
    return {
        "known_corpus_fields": known,
        "predicted_fields": [],
        "heuristic_fields": heuristic,
        "manual_override_fields": manual,
        "confidence_summary": {"overall": confidence, "reason": reason},
    }


def _build_abundance_analysis(elems, is_pure_element):
    """Build honest abundance analysis distinguishing elemental vs compound."""
    try:
        from .rarity import get_rarity, CRUST_ABUNDANCE
    except Exception:
        return None
    rarity_data = get_rarity(elems)
    if not rarity_data or not rarity_data.get("crust_abundance"):
        return None
    ca = rarity_data["crust_abundance"]
    tech = ca.get("technical", {})
    lim_elem = tech.get("limiting_element", elems[0] if elems else "?")
    lim_ppm = tech.get("value", 0)

    if is_pure_element:
        mode = "single_element"
        mode_reason = "Direct elemental crust abundance — high confidence"
        scope_note = "Directly measured Earth crust abundance for this element"
        conf = "high"
    elif len(elems) == 2:
        mode = "rarest_element_proxy"
        mode_reason = f"Approximated from the rarest constituent element ({lim_elem}, ~{lim_ppm} ppm)"
        scope_note = f"This rarity estimate is driven mainly by the scarcity of {lim_elem}, not by a direct abundance measurement of the compound itself."
        conf = "medium"
    else:
        mode = "rarest_element_proxy"
        mode_reason = f"Rough proxy based on {lim_elem} (~{lim_ppm} ppm) — the rarest of {len(elems)} elements"
        scope_note = "For compounds with 3+ elements, Earth crust abundance is usually defined for individual elements, not for the exact compound. This is a proxy estimate, useful for intuition but not a geochemical survey result."
        conf = "low"

    return {
        "elemental_abundance_basis": {"mode": mode, "reason": mode_reason},
        "elemental_reference": {
            "element": lim_elem,
            "technical": f"~{lim_ppm} ppm in Earth crust",
            "human": ca.get("human", {}).get("comparison", ""),
        },
        "compound_rarity": rarity_data["rarity"],
        "scope": scope_note,
        "confidence": conf,
    }


def _get_rarity(elems):
    """Get rarity from rarity module."""
    try:
        from .rarity import get_rarity
        return get_rarity(elems)
    except Exception:
        return None


def _novelty_description(exotic, n_elem):
    if exotic == "highly exotic":
        return {"label": "very unusual", "reason": f"With {n_elem} elements, this is a rare combination not commonly studied"}
    elif exotic == "exotic":
        return {"label": "somewhat unusual", "reason": "Complex composition that stands out from common materials"}
    elif exotic == "uncommon":
        return {"label": "moderately different", "reason": "Ternary compound — more complex than simple binaries but not rare"}
    else:
        return {"label": "very similar to many others", "reason": "Common element or binary compound, well-represented in databases"}


def explain_known_entity(resolution: dict) -> dict:
    """Generate explanation for a known entity NOT in the crystal corpus."""
    formula = resolution.get("formula", "?")
    etype = resolution.get("entity_type", "unknown")
    note = resolution.get("note", "")
    uses = resolution.get("uses", [])
    related = resolution.get("related", [])
    matched = resolution.get("matched_name", resolution.get("original_query", ""))

    type_labels = {
        "known_molecule_not_in_corpus": "Known Molecule (not in crystal corpus)",
        "elemental_gas_or_noble_gas": "Noble / Elemental Gas",
        "mixture_or_everyday_material": "Mixture or Everyday Material",
    }

    return {
        "title": f"{formula or matched} — {type_labels.get(etype, 'Known Substance')}",
        "formula": formula,
        "entity_type": etype,
        "corpus_presence_status": "not_in_corpus",
        "what_it_is": note or f"{formula} is a known chemical entity not represented as a bulk crystal in this engine.",
        "plain_language_summary": f"This substance ({formula or matched}) is real and well-known, but this materials engine focuses on solid-state crystalline materials. {formula or 'It'} does not appear in the corpus as a bulk crystal entry.",
        "why_not_in_corpus": "This engine models solid-state inorganic crystals (76,193 entries from DFT databases). Molecular gases, noble gases, organic compounds, and mixtures are generally outside its scope.",
        "real_world_uses": uses,
        "related_materials_in_corpus": related,
        "scientific_profile": "well-characterized" if formula else "composite/variable",
        "practical_relevance": "high" if uses else "variable",
        "confidence_in_explanation": "high — this is a well-known substance",
        "honesty_note": "This entity is real but not modeled in this corpus. The uses listed are general knowledge, not engine predictions.",
        "_meta": {"heuristic_assessment": True, "corpus_relative": False, "not_market_price": True},
    }

"""Human-readable comparisons between materials for public demo.

Each comparison is a curated, honest, factual statement.
Only materials with reasonable comparisons are included.
"""

COMPARISONS = {
    "Au": [
        "Gold is far rarer in Earth's crust than iron or silicon — about 14,000× scarcer than copper.",
        "Gold's corrosion resistance is exceptional — it does not tarnish or oxidize under normal conditions.",
        "More valuable as a specialty/strategic material than as a bulk engineering material.",
        "Conducts electricity well, but silver and copper conduct better.",
    ],
    "Ag": [
        "Silver has the highest electrical and thermal conductivity of any element.",
        "More conductive than copper and gold, but tarnishes in air (sulfide formation).",
        "Far rarer than copper but more abundant than gold or platinum in the crust.",
        "Used in electronics, mirrors, and antimicrobial applications — not a bulk structural metal.",
    ],
    "Cu": [
        "Copper is the workhorse of electrical wiring — second only to silver in conductivity but far cheaper.",
        "Much more abundant than gold or silver, making it viable for mass infrastructure.",
        "Essential for renewable energy systems (wind turbines, solar, EVs) — demand is rising fast.",
        "Unlike aluminum, copper does not form an insulating oxide layer — better for electrical contacts.",
    ],
    "Fe": [
        "Iron is the most used metal on Earth by mass — the backbone of steel and construction.",
        "Very abundant in Earth's crust (~5.6%), unlike precious metals.",
        "Pure iron is relatively soft — its strength comes from alloying (steel = Fe + C + others).",
        "Magnetically responsive — key for motors, transformers, and magnetic storage.",
    ],
    "Al": [
        "Aluminum is the most abundant metal in Earth's crust, but extracting it requires significant energy.",
        "About one-third the density of steel — essential for aerospace and lightweight engineering.",
        "Forms a protective oxide layer that prevents further corrosion — unlike iron/steel.",
        "Excellent thermal conductor — widely used in heat sinks and heat exchangers.",
    ],
    "Si": [
        "Silicon is geologically very common (~28% of Earth's crust) but technologically strategic.",
        "The foundation of the entire semiconductor industry — chips, solar cells, sensors.",
        "As a semiconductor, silicon sits between metals and insulators — this is what makes electronics possible.",
        "Not exotic at all, but arguably the most important single element for modern technology.",
    ],
    "Pt": [
        "Platinum is one of the rarest elements in Earth's crust — about 100× rarer than gold.",
        "Exceptional catalytic properties — essential for catalytic converters and fuel cells.",
        "More chemically inert than gold in many environments — extremely corrosion resistant.",
        "A precious metal with industrial importance far beyond jewelry.",
    ],
    "Ti": [
        "Titanium combines high strength with low density — stronger than aluminum, lighter than steel.",
        "Exceptional biocompatibility — the material of choice for medical implants.",
        "More abundant than copper in the crust, but much harder and more expensive to refine.",
        "Resists corrosion even in seawater and chlorine environments.",
    ],
    "Ni": [
        "Nickel is essential for stainless steel — most stainless alloys contain 8-12% nickel.",
        "Key component in rechargeable batteries (NiMH, Li-ion cathodes).",
        "More corrosion-resistant than iron, less expensive than chromium for alloying.",
    ],
    "Zn": [
        "Zinc's primary use is galvanizing steel — protecting it from corrosion.",
        "Essential trace element for human biology — not just an industrial metal.",
        "More abundant and cheaper than copper, but with different applications.",
    ],
    "Li": [
        "Lithium is the lightest metal — critical for rechargeable battery technology.",
        "Relatively rare in concentrated form, driving intense global competition for deposits.",
        "Essential for electric vehicles, grid storage, and portable electronics.",
    ],
    "C": [
        "Carbon exists in radically different forms — diamond (hardest natural material) vs graphite (soft lubricant).",
        "Graphite is essential for battery anodes and steel production.",
        "Diamond is used industrially for cutting, drilling, and precision optics — not just jewelry.",
    ],
    "GaAs": [
        "Gallium arsenide is far more specialized than silicon — used where silicon cannot perform.",
        "Superior for high-frequency electronics (5G, radar) and optoelectronics (LEDs, lasers).",
        "Much more expensive than silicon — used only where performance justifies the cost.",
        "Space-grade solar cells use GaAs because of higher efficiency than silicon.",
    ],
    "SiC": [
        "Silicon carbide handles much higher voltages and temperatures than silicon.",
        "Increasingly used in electric vehicle power electronics and fast chargers.",
        "Extremely hard — second only to diamond among common industrial materials.",
    ],
    "TiO2": [
        "Titanium dioxide is the world's most important white pigment — in paint, sunscreen, food.",
        "Photocatalytic properties enable self-cleaning surfaces and water purification.",
        "Very common industrially but has interesting high-tech applications too.",
    ],
    "SiO2": [
        "Silicon dioxide (quartz/silica) is one of the most abundant minerals on Earth.",
        "Essential for glass, optical fibers, and as gate oxide in semiconductor chips.",
        "Crystalline forms (quartz) vs amorphous forms (glass) have very different properties.",
    ],
    "NaCl": [
        "Common table salt — one of the most familiar chemical compounds to humans.",
        "Critical industrial chemical feedstock (chlor-alkali process produces chlorine and NaOH).",
        "Abundant and cheap, but industrially essential — not exotic but foundational.",
    ],
    "ZnO": [
        "Zinc oxide blocks UV radiation — the key ingredient in many sunscreens.",
        "Piezoelectric properties make it useful for sensors and energy harvesting.",
        "Much cheaper than titanium dioxide for some coating applications.",
    ],
    "Al2O3": [
        "Alumina (aluminum oxide) is extremely hard — used as an abrasive and in ceramics.",
        "Sapphire and ruby are gem-quality forms of Al2O3 with trace impurities.",
        "Essential in aluminum smelting — alumina is the intermediate step.",
    ],
    "Fe2O3": [
        "Hematite (iron oxide) is the primary ore of iron — the source of most steel.",
        "Gives Mars its red color and rust its distinctive appearance.",
        "Common, not exotic — but foundational for the entire metals industry.",
    ],
    "CaCO3": [
        "Calcium carbonate (calcite/limestone) is one of the most common minerals on Earth.",
        "Essential for cement production — the foundation of modern construction.",
        "Also used in paper, plastics, and as a dietary calcium supplement.",
    ],
    "H2O": [
        "Water is the most important compound for life — and has an unusually complex phase diagram.",
        "Ice has multiple crystal structures (polymorphs) — at least 19 known phases.",
        "The corpus contains crystalline ice phases, not liquid water.",
    ],
}


def get_comparisons(formula):
    """Return human comparisons for a material. Empty list if none curated."""
    return COMPARISONS.get(formula, [])

"""
Mission profile registry + the per-(formula, mission) consensus scoring
function used by M3 / MCOMB.

Mirror of internal source (mission_profiles) + the
composition-only branches of multiobjective_score.compute_mission_score.

Worker-side context: we never ship formation_energy / band_gap /
spacegroup / crystal_system / relaxation_survived per formula. The
Heavy worker scores composition alone. The mission_fit branch
collapses to "all properties unknown → 0.5 per scored entry weighted
by spec.weight / total_weight". The output is byte-identical to the
engine's output for the same call signature.

Stdlib only.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .abundance_cost_tables import (
    abundance_score_from_counts, cost_score_from_counts,
    toxicity_penalty_from_counts, pgm_content_from_counts,
)
from .functional_taxonomy_tables import classify_material_from_counts
from .pgm_replacement_tables import detect_family_from_elem_set


# Curated seed family — small, hand-picked formulas covering the
# scientific surface area of the seven missions. Used to extend the
# materials.db pool when generating formula_pool_v1.txt so every mission
# has at least a few obvious anchor compounds.
SEED_FAMILIES = [
    # PGM-free / catalysis anchors
    "Fe2O3", "Fe3O4", "FeO", "MnO2", "Mn2O3", "Mn3O4",
    "Co3O4", "NiO", "CuO", "Cu2O", "TiO2", "ZnO",
    "MoO3", "WO3", "V2O5", "Cr2O3", "FeS2", "MoS2", "WS2",
    "Fe3N", "Mo2N", "TiN", "Ni2P", "FeP", "Co2P",
    # Perovskite / spinel anchors
    "BaTiO3", "SrTiO3", "CaTiO3", "LaFeO3", "LaCoO3", "LaNiO3",
    "MgAl2O4", "ZnAl2O4", "FeAl2O4", "MnFe2O4", "CoFe2O4", "NiFe2O4",
    # Photovoltaic anchors
    "Cu2ZnSnS4", "CuInS2", "CuInSe2", "Cu2S", "ZnSnN2",
    # Lithium / membrane anchors
    "LiMn2O4", "LiFePO4", "LiCoO2", "LiNiO2", "Li4Ti5O12",
    "Na2Ti3O7", "K2Ti6O13", "ZrSiO4", "AlPO4",
    # CO2 capture anchors
    "MgO", "CaO", "CaCO3", "MgCO3", "Mg2SiO4",
    # Photonic anchors
    "LiNbO3", "LiTaO3", "BaTiO3", "KNbO3", "Si", "GaN", "AlN",
]

# Mission keys must match internal source (mission_profiles)
# ALL_MISSIONS keys exactly. The Heavy worker iterates these in this
# canonical order for round-robin slicing.
ALL_MISSION_KEYS = [
    "pgm_free_catalyst_v1",
    "water_split_abundant_v1",
    "low_cost_pv_v1",
    "lithium_selective_brine_v1",
    "desalination_membrane_v1",
    "co2_capture_sorbent_v1",
    "photonic_telecom_v0",
]


@dataclass
class MissionProfile:
    name: str
    target_properties: Dict[str, dict]
    forbidden_elements: Set[str] = field(default_factory=set)
    preferred_elements: Set[str] = field(default_factory=set)
    abundance_weight: float = 0.20
    cost_weight: float = 0.20
    stability_weight: float = 0.20
    toxicity_weight: float = 0.10
    pgm_free_bonus: float = 0.15
    mission_fit_weight: float = 0.15


_PGM_FREE_CATALYST = MissionProfile(
    name="pgm_free_catalyst_v1",
    target_properties={
        "formation_energy_per_atom": {"max": 0.0, "weight": 0.3},
        "band_gap": {"min": 0.0, "max": 3.0, "weight": 0.2},
    },
    forbidden_elements={"Pt", "Pd", "Rh", "Ir", "Ru", "Os", "Au"},
    preferred_elements={"Fe", "Ni", "Mn", "Co", "Cu", "Ti", "Mo", "W",
                         "N", "C", "S", "P"},
    abundance_weight=0.20, cost_weight=0.20, stability_weight=0.20,
    toxicity_weight=0.10, pgm_free_bonus=0.20, mission_fit_weight=0.10,
)

_WATER_SPLITTING_CATALYST = MissionProfile(
    name="water_split_abundant_v1",
    target_properties={
        "formation_energy_per_atom": {"max": 0.0, "weight": 0.3},
        "band_gap": {"min": 1.2, "max": 3.5, "weight": 0.3},
    },
    forbidden_elements={"Pt", "Pd", "Rh", "Ir", "Ru", "Os",
                         "Pb", "Cd", "Hg"},
    preferred_elements={"Fe", "Ni", "Mn", "Co", "Ti", "Mo", "W", "Zn", "Cu"},
    abundance_weight=0.20, cost_weight=0.20, stability_weight=0.20,
    toxicity_weight=0.10, pgm_free_bonus=0.15, mission_fit_weight=0.15,
)

_LOW_COST_PV = MissionProfile(
    name="low_cost_pv_v1",
    target_properties={
        "formation_energy_per_atom": {"max": 0.0, "weight": 0.2},
        "band_gap": {"min": 1.0, "max": 2.0, "weight": 0.4},
    },
    forbidden_elements={"Cd", "Pb", "Hg", "As", "Tl", "In", "Ga", "Te"},
    preferred_elements={"Cu", "Zn", "Sn", "Fe", "Ti", "Si", "Ge", "S", "Se", "N"},
    abundance_weight=0.20, cost_weight=0.20, stability_weight=0.15,
    toxicity_weight=0.15, pgm_free_bonus=0.10, mission_fit_weight=0.20,
)

_LITHIUM_SELECTIVE = MissionProfile(
    name="lithium_selective_brine_v1",
    target_properties={
        "formation_energy_per_atom": {"max": 0.0, "weight": 0.3},
        "band_gap": {"min": 0.5, "max": 6.0, "weight": 0.1},
    },
    forbidden_elements={"Pb", "Cd", "Hg", "As", "Tl"},
    preferred_elements={"Mn", "Ti", "Fe", "Al", "Si", "O", "P", "Li"},
    abundance_weight=0.20, cost_weight=0.20, stability_weight=0.25,
    toxicity_weight=0.15, pgm_free_bonus=0.0, mission_fit_weight=0.20,
)

_DESALINATION_MEMBRANE = MissionProfile(
    name="desalination_membrane_v1",
    target_properties={
        "formation_energy_per_atom": {"max": 0.0, "weight": 0.3},
        "band_gap": {"min": 2.0, "max": 8.0, "weight": 0.1},
    },
    forbidden_elements={"Pb", "Cd", "Hg", "As"},
    preferred_elements={"Ti", "Al", "Si", "Zr", "Mg", "Ca", "O", "N", "C", "P"},
    abundance_weight=0.20, cost_weight=0.20, stability_weight=0.25,
    toxicity_weight=0.15, pgm_free_bonus=0.0, mission_fit_weight=0.20,
)

_CO2_CAPTURE = MissionProfile(
    name="co2_capture_sorbent_v1",
    target_properties={
        "formation_energy_per_atom": {"max": 0.0, "weight": 0.3},
    },
    forbidden_elements={"Pt", "Pd", "Au", "Pb", "Cd", "Hg"},
    preferred_elements={"Mg", "Ca", "Al", "Fe", "Mn", "Zn", "C", "N", "O"},
    abundance_weight=0.20, cost_weight=0.20, stability_weight=0.20,
    toxicity_weight=0.10, pgm_free_bonus=0.10, mission_fit_weight=0.20,
)

_PHOTONIC_TELECOM = MissionProfile(
    name="photonic_telecom_v0",
    target_properties={
        "formation_energy_per_atom": {"max": 0.0, "weight": 0.25},
        "band_gap": {"min": 0.6, "max": 4.5, "weight": 0.30},
    },
    forbidden_elements=set(),
    preferred_elements={"Li", "Nb", "Ta", "Ti", "Ba", "Sr", "K", "Zn",
                         "Ga", "In", "Si", "Ge", "N", "O", "S", "Se",
                         "Te", "Al", "Hf", "Zr"},
    abundance_weight=0.15, cost_weight=0.15, stability_weight=0.20,
    toxicity_weight=0.05, pgm_free_bonus=0.05, mission_fit_weight=0.40,
)


ALL_MISSIONS: Dict[str, MissionProfile] = {
    "pgm_free_catalyst_v1":       _PGM_FREE_CATALYST,
    "water_split_abundant_v1":    _WATER_SPLITTING_CATALYST,
    "low_cost_pv_v1":             _LOW_COST_PV,
    "lithium_selective_brine_v1": _LITHIUM_SELECTIVE,
    "desalination_membrane_v1":   _DESALINATION_MEMBRANE,
    "co2_capture_sorbent_v1":     _CO2_CAPTURE,
    "photonic_telecom_v0":        _PHOTONIC_TELECOM,
}


def get_mission(name: str) -> Optional[MissionProfile]:
    return ALL_MISSIONS.get(name)


# ────────────────────────────────────────────────────────────────────────
# Composition-only mission score (M3 logic)
# ────────────────────────────────────────────────────────────────────────


def _compute_mission_fit_composition_only(mission: MissionProfile) -> float:
    """When no per-formula properties are shipped, mission_fit collapses
    to the composition-independent neutral mean: each property scored 0.5
    × spec.weight, normalised by sum of weights. We materialise it once
    per mission for speed.
    """
    if not mission.target_properties:
        return 0.5
    total_weight = sum(spec.get("weight", 1.0)
                       for spec in mission.target_properties.values())
    if total_weight <= 0:
        return 0.5
    score_sum = sum(0.5 * spec.get("weight", 1.0)
                    for spec in mission.target_properties.values())
    return score_sum / total_weight


# Pre-compute the composition-only mission_fit per mission. Saves a sum
# in every formula evaluation in the hot loop.
_MISSION_FIT_CACHE: Dict[str, float] = {
    name: _compute_mission_fit_composition_only(prof)
    for name, prof in ALL_MISSIONS.items()
}


def compute_mission_score_composition_only(formula: str,
                                           counts: Dict[str, int],
                                           mission: MissionProfile) -> Dict:
    """Composition-only port of multiobjective_score.compute_mission_score.

    formation_energy / band_gap / spacegroup / crystal_system /
    relaxation_survived all default to None — i.e. every "neutral
    default" branch in the engine fires here. The output dict structure
    is preserved (so callers serialise to byte-identical JSON), but the
    `formation_energy` / `band_gap` keys remain None.
    """
    elem_set = set(counts.keys())

    forbidden_hit = elem_set & mission.forbidden_elements
    if forbidden_hit:
        return {
            "formula": formula,
            "mission": mission.name,
            "passed_filters": False,
            "rejection_reason":
                f"forbidden elements: {set(sorted(forbidden_hit))}",
            "composite_score": 0.0,
        }

    s_abundance = abundance_score_from_counts(counts)
    s_cost = cost_score_from_counts(counts)
    s_stability = 0.5  # neutral — formation_energy unknown
    s_nontoxic = 1.0 - toxicity_penalty_from_counts(counts)
    s_pgm_free = 1.0 if pgm_content_from_counts(counts) == 0.0 else 0.0
    s_mission_fit = _MISSION_FIT_CACHE.get(mission.name, 0.5)

    preferred_count = sum(c for el, c in counts.items()
                          if el in mission.preferred_elements)
    total = sum(counts.values())
    preferred_ratio = preferred_count / total if total > 0 else 0
    s_preferred = min(1.0, preferred_ratio * 1.5)

    s_relaxation = 0.5  # neutral — relaxation_survived unknown

    composite = (
        s_abundance * mission.abundance_weight
        + s_cost * mission.cost_weight
        + s_stability * mission.stability_weight
        + s_nontoxic * mission.toxicity_weight
        + s_pgm_free * mission.pgm_free_bonus
        + s_mission_fit * mission.mission_fit_weight
    )
    composite += s_preferred * 0.05
    # relaxation gate is None → no multiplicative penalty

    composite = round(min(1.0, max(0.0, composite)), 4)

    families = detect_family_from_elem_set(frozenset(elem_set))
    taxonomy = classify_material_from_counts(formula, counts)

    return {
        "formula": formula,
        "mission": mission.name,
        "passed_filters": True,
        "composite_score": composite,
        "components": {
            "abundance": round(s_abundance, 4),
            "cost": round(s_cost, 4),
            "stability": round(s_stability, 4),
            "non_toxic": round(s_nontoxic, 4),
            "pgm_free": s_pgm_free,
            "mission_fit": round(s_mission_fit, 4),
            "preferred_ratio": round(preferred_ratio, 4),
            "relaxation": s_relaxation,
        },
        "weights": {
            "abundance": mission.abundance_weight,
            "cost": mission.cost_weight,
            "stability": mission.stability_weight,
            "toxicity": mission.toxicity_weight,
            "pgm_free": mission.pgm_free_bonus,
            "mission_fit": mission.mission_fit_weight,
        },
        "families": families,
        "taxonomy": taxonomy["primary_class"],
        "applications": taxonomy["applications"],
        "formation_energy": None,
        "band_gap": None,
    }

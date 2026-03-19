"""Thermo-Pressure proxy screening — honest heuristic-based risk assessment.

Phase III.B: Uses cheap, reproducible proxies to flag T/P risk.
NOT physics simulation. NOT phonon calculation. NOT EOS.

What it does:
  - Estimates risk from extreme conditions via documented heuristics
  - Flags materials with high sensitivity to T/P based on structural class
  - Provides qualitative risk level and method documentation

What it does NOT do:
  - Compute band gap or energy under pressure
  - Confirm or deny phase transitions
  - Predict specific failure temperature

All results tagged with method and reliability.
"""

import logging
from typing import Optional

from ..schema import Material
from .conditions import ThermoPressureConditions, AMBIENT_TEMPERATURE_K

log = logging.getLogger(__name__)

# Crystal system thermal sensitivity heuristics
# Higher = more sensitive to temperature changes
# Based on general materials science knowledge, NOT per-material DFT
CRYSTAL_THERMAL_SENSITIVITY = {
    "cubic": 0.2,
    "hexagonal": 0.3,
    "tetragonal": 0.4,
    "orthorhombic": 0.4,
    "rhombohedral": 0.35,
    "trigonal": 0.35,
    "monoclinic": 0.5,
    "triclinic": 0.6,
}

# Spacegroup ranges known for high-pressure sensitivity
# (very simplified heuristic: lower symmetry → more P-sensitive)
HIGH_SYMMETRY_SG = set(range(195, 231))   # cubic
MODERATE_SYMMETRY_SG = set(range(75, 195))  # tetragonal through hexagonal


def screen_tp_proxy(material: Material,
                    conditions: ThermoPressureConditions) -> dict:
    """Screen a material under T/P using heuristic proxies.

    Returns dict with:
      - method: always "heuristic_proxy"
      - reliability: "baseline_ambient" | "experimental_proxy" | "not_available"
      - risk_level: "low" | "medium" | "high" | "unknown"
      - stability_flag: "assumed_stable" | "caution" | "high_risk" | "unknown"
      - phase_transition_risk: "low" | "medium" | "high" | "unknown"
      - property_drift_risk: "low" | "medium" | "high" | "unknown"
      - operating_window_hint: human-readable note
      - note: method description and honest limitations
    """
    conditions.validate()

    result = {
        "conditions": conditions.to_dict(),
        "method": "heuristic_proxy",
        "reliability": "experimental_proxy",
    }

    # Ambient → trivial case
    if conditions.is_ambient:
        result.update({
            "reliability": "baseline_ambient",
            "risk_level": "low",
            "stability_flag": "assumed_stable",
            "phase_transition_risk": "low",
            "property_drift_risk": "low",
            "operating_window_hint": "Ambient conditions — no T/P risk factors.",
            "note": "Material assessed at ambient conditions (300 K, 1 atm). "
                    "No T/P risk proxy needed.",
        })
        return result

    # --- Temperature risk ---
    t_risk = _temperature_risk(material, conditions.temperature_K)

    # --- Pressure risk ---
    p_risk = _pressure_risk(material, conditions.pressure_GPa)

    # --- Combined risk ---
    risk_map = {"low": 0, "medium": 1, "high": 2, "unknown": 1}
    t_val = risk_map.get(t_risk, 1)
    p_val = risk_map.get(p_risk, 1)
    combined = max(t_val, p_val)

    risk_labels = {0: "low", 1: "medium", 2: "high"}
    risk_level = risk_labels.get(combined, "unknown")

    # Stability flag
    if combined == 0:
        stability_flag = "assumed_stable"
    elif combined == 1:
        stability_flag = "caution"
    else:
        stability_flag = "high_risk"

    # Phase transition risk heuristic
    phase_risk = "unknown"
    if conditions.temperature_K > 1500 or conditions.pressure_GPa > 20:
        phase_risk = "high"
    elif conditions.temperature_K > 800 or conditions.pressure_GPa > 5:
        phase_risk = "medium"
    elif conditions.temperature_K < 600 and conditions.pressure_GPa < 2:
        phase_risk = "low"

    # Property drift risk
    property_drift = t_risk  # temperature is primary driver of property changes

    # Operating window hint
    hints = []
    if conditions.temperature_K > 1000:
        hints.append(f"T={conditions.temperature_K}K is high — thermal decomposition risk")
    if conditions.pressure_GPa > 10:
        hints.append(f"P={conditions.pressure_GPa}GPa is high — structural compression likely")
    if material.crystal_system == "triclinic":
        hints.append("Triclinic structure: higher sensitivity to T/P perturbation")
    if not hints:
        hints.append("Moderate conditions — proxy risk assessment only")

    result.update({
        "risk_level": risk_level,
        "stability_flag": stability_flag,
        "phase_transition_risk": phase_risk,
        "property_drift_risk": property_drift,
        "operating_window_hint": "; ".join(hints),
        "note": (
            f"Heuristic proxy assessment at {conditions.temperature_K} K, "
            f"{conditions.pressure_GPa} GPa. "
            f"Temperature risk: {t_risk}. Pressure risk: {p_risk}. "
            "Method: crystal-system thermal sensitivity + symmetry-based pressure "
            "heuristic. NOT a physics calculation. Phase III+ will add phonon/EOS."
        ),
    })

    return result


def screen_tp_batch(materials: list,
                    conditions: ThermoPressureConditions) -> list:
    """Screen multiple materials under the same T/P conditions."""
    conditions.validate()
    return [screen_tp_proxy(m, conditions) for m in materials]


def _temperature_risk(material: Material, temperature_K: float) -> str:
    """Estimate temperature risk from crystal system and T magnitude."""
    # Base sensitivity from crystal system
    cs = material.crystal_system
    sensitivity = CRYSTAL_THERMAL_SENSITIVITY.get(cs, 0.4) if cs else 0.4

    # Scale by how far from ambient
    t_delta = abs(temperature_K - AMBIENT_TEMPERATURE_K)

    if t_delta < 200:
        return "low"
    elif t_delta < 700:
        return "medium" if sensitivity > 0.35 else "low"
    else:
        return "high" if sensitivity > 0.3 else "medium"


def _pressure_risk(material: Material, pressure_GPa: float) -> str:
    """Estimate pressure risk from spacegroup symmetry and P magnitude."""
    if pressure_GPa < 0.01:
        return "low"  # near-ambient pressure

    sg = material.spacegroup
    if sg and sg in HIGH_SYMMETRY_SG:
        # Cubic: generally more P-resilient
        if pressure_GPa < 20:
            return "low"
        elif pressure_GPa < 100:
            return "medium"
        else:
            return "high"
    elif sg and sg in MODERATE_SYMMETRY_SG:
        if pressure_GPa < 5:
            return "low"
        elif pressure_GPa < 50:
            return "medium"
        else:
            return "high"
    else:
        # Low symmetry or unknown
        if pressure_GPa < 2:
            return "low"
        elif pressure_GPa < 20:
            return "medium"
        else:
            return "high"

"""Application classification — rule-based, honest, no LLM.

Categorizes materials into application areas based on known or predicted
properties. Each classification includes a score, rationale, and evidence level.

NOT absolute — these are hypotheses based on property ranges.
"""

import logging
from typing import List, Optional

log = logging.getLogger(__name__)


def classify_applications(band_gap: Optional[float] = None,
                          band_gap_evidence: str = "unavailable",
                          formation_energy: Optional[float] = None,
                          fe_evidence: str = "unavailable",
                          bulk_modulus: Optional[float] = None,
                          shear_modulus: Optional[float] = None,
                          total_magnetization: Optional[float] = None,
                          elements: Optional[List[str]] = None,
                          ) -> List[dict]:
    """Classify likely applications based on available properties.

    Returns list of {label, score, why, evidence_level}.
    Score 0.0-1.0 is confidence in the classification, not material quality.
    """
    apps = []
    elements = elements or []

    # Semiconductor
    if band_gap is not None and 0.1 < band_gap < 4.0:
        score = 0.7 if band_gap_evidence == "known" else 0.4
        apps.append({
            "label": "semiconductor",
            "score": round(score, 2),
            "why": f"Band gap {band_gap:.2f} eV in semiconductor range (0.1-4.0 eV)",
            "evidence_level": band_gap_evidence,
        })

    # Photovoltaic candidate
    if band_gap is not None and 0.8 < band_gap < 2.0:
        score = 0.6 if band_gap_evidence == "known" else 0.3
        apps.append({
            "label": "photovoltaic_candidate",
            "score": round(score, 2),
            "why": f"Band gap {band_gap:.2f} eV in optimal PV range (0.8-2.0 eV, Shockley-Queisser)",
            "evidence_level": band_gap_evidence,
        })

    # Thermoelectric candidate
    if band_gap is not None and 0.1 < band_gap < 1.5:
        te_elements = {"Bi", "Te", "Sb", "Se", "Pb", "Sn", "Ge"}
        has_te_elem = bool(set(elements) & te_elements)
        score = 0.5 if has_te_elem else 0.25
        if band_gap_evidence != "known":
            score *= 0.6
        apps.append({
            "label": "thermoelectric_candidate",
            "score": round(score, 2),
            "why": f"Band gap {band_gap:.2f} eV suitable for thermoelectrics"
                   + ("; contains known TE elements" if has_te_elem else ""),
            "evidence_level": band_gap_evidence,
        })

    # Catalytic candidate
    catalyst_elements = {"Pt", "Pd", "Ru", "Rh", "Ir", "Ni", "Co", "Fe",
                         "Cu", "Au", "Ag", "Ti", "V", "Mn", "Mo", "W"}
    has_catalyst = bool(set(elements) & catalyst_elements)
    if has_catalyst:
        score = 0.35
        if formation_energy is not None and formation_energy < -0.5:
            score += 0.15
        apps.append({
            "label": "catalytic_candidate",
            "score": round(score, 2),
            "why": f"Contains known catalytic elements: "
                   f"{sorted(set(elements) & catalyst_elements)}",
            "evidence_level": "proxy",
        })

    # Magnetic candidate
    if total_magnetization is not None and abs(total_magnetization) > 0.5:
        apps.append({
            "label": "magnetic_candidate",
            "score": 0.6,
            "why": f"Total magnetization {total_magnetization:.2f} μB indicates magnetic ordering",
            "evidence_level": "known",
        })
    elif any(e in elements for e in ["Fe", "Co", "Ni", "Mn", "Cr", "Gd"]):
        apps.append({
            "label": "magnetic_candidate",
            "score": 0.2,
            "why": "Contains magnetic elements (Fe/Co/Ni/Mn/Cr/Gd)",
            "evidence_level": "proxy",
        })

    # Structural / mechanical candidate
    if bulk_modulus is not None and bulk_modulus > 100:
        apps.append({
            "label": "structural_candidate",
            "score": 0.5,
            "why": f"Bulk modulus {bulk_modulus:.1f} GPa indicates mechanical rigidity",
            "evidence_level": "known",
        })

    # High-pressure candidate
    hp_elements = {"C", "B", "N", "W", "Re", "Os", "Ir", "Ta", "Hf"}
    has_hp = bool(set(elements) & hp_elements)
    if has_hp and bulk_modulus is not None and bulk_modulus > 150:
        apps.append({
            "label": "high_pressure_candidate",
            "score": 0.5,
            "why": f"High bulk modulus ({bulk_modulus:.0f} GPa) + hard elements",
            "evidence_level": "known",
        })
    elif has_hp:
        apps.append({
            "label": "high_pressure_candidate",
            "score": 0.2,
            "why": f"Contains hard/refractory elements: {sorted(set(elements) & hp_elements)}",
            "evidence_level": "proxy",
        })

    # Wide-gap insulator
    if band_gap is not None and band_gap > 4.0:
        score = 0.5 if band_gap_evidence == "known" else 0.25
        apps.append({
            "label": "wide_gap_insulator",
            "score": round(score, 2),
            "why": f"Band gap {band_gap:.2f} eV > 4.0 eV (wide-gap insulator range)",
            "evidence_level": band_gap_evidence,
        })

    if not apps:
        apps.append({
            "label": "unknown_application",
            "score": 0.0,
            "why": "Insufficient property data for application classification",
            "evidence_level": "unavailable",
        })

    apps.sort(key=lambda a: -a["score"])
    return apps

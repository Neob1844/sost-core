"""Thermo-Pressure screening — condition-aware material evaluation.

Phase II.8: Scaffold only. Real thermodynamic screening requires:
- Phonon-based stability (Phase III)
- Equation of state fitting (Phase III)
- Phase diagram lookup / CALPHAD integration (Phase IV)

Current capability: accepts conditions, tags predictions with T/P context,
returns honest status about what is and isn't computed.
"""

import logging
from typing import Optional
from dataclasses import dataclass

from .conditions import ThermoPressureConditions, AMBIENT_TEMPERATURE_K, AMBIENT_PRESSURE_GPA

log = logging.getLogger(__name__)


@dataclass
class ScreeningResult:
    """Result of a thermo-pressure screening evaluation."""
    # Input conditions
    conditions: dict
    # Base prediction (ambient, from existing models)
    base_prediction: Optional[float] = None
    base_target: Optional[str] = None
    base_model: Optional[str] = None
    # Conditioned prediction (when real T/P models exist)
    conditioned_prediction: Optional[float] = None
    conditioned_method: Optional[str] = None
    # Assessment
    stability_flag: Optional[str] = None     # "stable", "unstable", "unknown"
    phase_transition_risk: Optional[str] = None  # "low", "medium", "high", "unknown"
    operating_window: Optional[str] = None   # human-readable note
    reliability: str = "experimental_scaffold"
    note: str = ""

    def to_dict(self) -> dict:
        d = {
            "conditions": self.conditions,
            "base_prediction": self.base_prediction,
            "base_target": self.base_target,
            "base_model": self.base_model,
            "reliability": self.reliability,
            "note": self.note,
        }
        if self.conditioned_prediction is not None:
            d["conditioned_prediction"] = self.conditioned_prediction
            d["conditioned_method"] = self.conditioned_method
        if self.stability_flag is not None:
            d["stability_flag"] = self.stability_flag
        if self.phase_transition_risk is not None:
            d["phase_transition_risk"] = self.phase_transition_risk
        if self.operating_window is not None:
            d["operating_window"] = self.operating_window
        return d


def screen_material(base_prediction: dict,
                    conditions: ThermoPressureConditions) -> ScreeningResult:
    """Evaluate a material prediction under specified T/P conditions.

    Phase II.8: Returns base prediction annotated with conditions.
    Real T/P conditioning is NOT yet implemented — result is tagged
    as 'experimental_scaffold'.

    Args:
        base_prediction: dict from predict_from_cif/predict_from_structure
            Must contain 'prediction', 'target', 'model' keys.
        conditions: ThermoPressureConditions object (validated).

    Returns:
        ScreeningResult with honest status.
    """
    conditions.validate()

    result = ScreeningResult(
        conditions=conditions.to_dict(),
        base_prediction=base_prediction.get("prediction"),
        base_target=base_prediction.get("target"),
        base_model=base_prediction.get("model"),
    )

    if conditions.is_ambient:
        result.stability_flag = "assumed_stable"
        result.reliability = "baseline_model"
        result.note = (
            "Prediction at ambient conditions (300 K, 1 atm). "
            "Result is from baseline GNN model trained on DFT-computed "
            "properties at 0 K. No explicit T/P correction applied."
        )
    else:
        result.stability_flag = "unknown"
        result.phase_transition_risk = "unknown"
        result.reliability = "experimental_scaffold"
        result.note = (
            f"Conditions: {conditions.temperature_K} K, {conditions.pressure_GPa} GPa. "
            "Real T/P-conditioned prediction is not yet implemented. "
            "Base prediction shown is from ambient-trained model. "
            "Phase III will add phonon stability and EOS fitting. "
            "Phase IV will add phase diagram and CALPHAD integration."
        )

    if conditions.has_range:
        result.operating_window = (
            f"Requested range screening — not yet implemented. "
            f"Range: T=[{conditions.temperature_min_K or '?'}, "
            f"{conditions.temperature_max_K or '?'}] K, "
            f"P=[{conditions.pressure_min_GPa or '?'}, "
            f"{conditions.pressure_max_GPa or '?'}] GPa."
        )

    return result


def screen_material_full(cif_text: str, target: str,
                         conditions: ThermoPressureConditions) -> dict:
    """End-to-end: predict + screen under conditions.

    Convenience wrapper that calls predict_from_cif then screen_material.
    """
    from ..inference.predictor import predict_from_cif
    conditions.validate()

    base = predict_from_cif(cif_text, target)
    if "error" in base:
        return {"error": base["error"], "conditions": conditions.to_dict()}

    result = screen_material(base, conditions)
    return result.to_dict()

"""Thermo-Pressure conditions — defines operating conditions for screening.

Phase II.8: Contract and scaffold. No real thermodynamic simulation yet.
Provides validated condition objects for future T/P-aware prediction.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List
import json

# Physical constants / defaults
AMBIENT_TEMPERATURE_K = 300.0
AMBIENT_PRESSURE_GPA = 0.000101325  # 1 atm in GPa

# Validation bounds
MIN_TEMPERATURE_K = 0.0       # absolute zero
MAX_TEMPERATURE_K = 6000.0    # beyond most solid-state relevance
MIN_PRESSURE_GPA = 0.0
MAX_PRESSURE_GPA = 500.0      # upper bound for extreme high-pressure experiments


class ConditionValidationError(ValueError):
    """Raised when thermodynamic conditions are out of valid range."""
    pass


@dataclass
class ThermoPressureConditions:
    """Operating conditions for thermo-pressure screening.

    All temperatures in Kelvin, all pressures in GPa.
    Defaults to ambient conditions (300 K, 1 atm).
    """
    temperature_K: float = AMBIENT_TEMPERATURE_K
    pressure_GPa: float = AMBIENT_PRESSURE_GPA

    # Optional range endpoints for sweep/screening
    temperature_min_K: Optional[float] = None
    temperature_max_K: Optional[float] = None
    pressure_min_GPa: Optional[float] = None
    pressure_max_GPa: Optional[float] = None

    def validate(self) -> None:
        """Validate all conditions are within physical bounds.

        Raises ConditionValidationError if any value is out of range.
        """
        _validate_temperature(self.temperature_K, "temperature_K")
        _validate_pressure(self.pressure_GPa, "pressure_GPa")

        if self.temperature_min_K is not None:
            _validate_temperature(self.temperature_min_K, "temperature_min_K")
        if self.temperature_max_K is not None:
            _validate_temperature(self.temperature_max_K, "temperature_max_K")
        if self.pressure_min_GPa is not None:
            _validate_pressure(self.pressure_min_GPa, "pressure_min_GPa")
        if self.pressure_max_GPa is not None:
            _validate_pressure(self.pressure_max_GPa, "pressure_max_GPa")

        # Range consistency
        if (self.temperature_min_K is not None and self.temperature_max_K is not None
                and self.temperature_min_K > self.temperature_max_K):
            raise ConditionValidationError(
                f"temperature_min_K ({self.temperature_min_K}) > "
                f"temperature_max_K ({self.temperature_max_K})")

        if (self.pressure_min_GPa is not None and self.pressure_max_GPa is not None
                and self.pressure_min_GPa > self.pressure_max_GPa):
            raise ConditionValidationError(
                f"pressure_min_GPa ({self.pressure_min_GPa}) > "
                f"pressure_max_GPa ({self.pressure_max_GPa})")

    @property
    def is_ambient(self) -> bool:
        """True if conditions are at standard ambient (300K, 1atm)."""
        return (abs(self.temperature_K - AMBIENT_TEMPERATURE_K) < 1.0
                and abs(self.pressure_GPa - AMBIENT_PRESSURE_GPA) < 1e-4)

    @property
    def has_range(self) -> bool:
        """True if any range endpoints are specified."""
        return any(v is not None for v in [
            self.temperature_min_K, self.temperature_max_K,
            self.pressure_min_GPa, self.pressure_max_GPa])

    def to_dict(self) -> dict:
        """Serialize to dict, omitting None range fields."""
        d = {"temperature_K": self.temperature_K, "pressure_GPa": self.pressure_GPa}
        for k in ["temperature_min_K", "temperature_max_K",
                   "pressure_min_GPa", "pressure_max_GPa"]:
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "ThermoPressureConditions":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _validate_temperature(value: float, name: str) -> None:
    if not isinstance(value, (int, float)):
        raise ConditionValidationError(f"{name} must be numeric, got {type(value).__name__}")
    if value < MIN_TEMPERATURE_K or value > MAX_TEMPERATURE_K:
        raise ConditionValidationError(
            f"{name}={value} out of range [{MIN_TEMPERATURE_K}, {MAX_TEMPERATURE_K}]")


def _validate_pressure(value: float, name: str) -> None:
    if not isinstance(value, (int, float)):
        raise ConditionValidationError(f"{name} must be numeric, got {type(value).__name__}")
    if value < MIN_PRESSURE_GPA or value > MAX_PRESSURE_GPA:
        raise ConditionValidationError(
            f"{name}={value} out of range [{MIN_PRESSURE_GPA}, {MAX_PRESSURE_GPA}]")


# --- Standard condition presets ---

def ambient() -> ThermoPressureConditions:
    """Standard ambient: 300 K, 1 atm."""
    return ThermoPressureConditions()


def high_temperature(T: float = 1200.0) -> ThermoPressureConditions:
    """High-temperature conditions (default 1200 K, 1 atm)."""
    c = ThermoPressureConditions(temperature_K=T)
    c.validate()
    return c


def high_pressure(P: float = 10.0) -> ThermoPressureConditions:
    """High-pressure conditions (default 10 GPa, 300 K)."""
    c = ThermoPressureConditions(pressure_GPa=P)
    c.validate()
    return c


def extreme(T: float = 2000.0, P: float = 50.0) -> ThermoPressureConditions:
    """Extreme conditions for refractory/superhard screening."""
    c = ThermoPressureConditions(temperature_K=T, pressure_GPa=P)
    c.validate()
    return c


def temperature_sweep(T_min: float = 300.0, T_max: float = 1500.0,
                       P: float = AMBIENT_PRESSURE_GPA) -> ThermoPressureConditions:
    """Temperature sweep at fixed pressure."""
    c = ThermoPressureConditions(
        temperature_K=(T_min + T_max) / 2.0,
        pressure_GPa=P,
        temperature_min_K=T_min,
        temperature_max_K=T_max)
    c.validate()
    return c


def pressure_sweep(P_min: float = 0.0, P_max: float = 50.0,
                    T: float = AMBIENT_TEMPERATURE_K) -> ThermoPressureConditions:
    """Pressure sweep at fixed temperature."""
    c = ThermoPressureConditions(
        temperature_K=T,
        pressure_GPa=(P_min + P_max) / 2.0,
        pressure_min_GPa=P_min,
        pressure_max_GPa=P_max)
    c.validate()
    return c

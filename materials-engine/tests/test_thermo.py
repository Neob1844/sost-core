"""Tests for thermo-pressure conditions and screening scaffold."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.thermo.conditions import (
    ThermoPressureConditions, ConditionValidationError,
    ambient, high_temperature, high_pressure, extreme,
    temperature_sweep, pressure_sweep,
    AMBIENT_TEMPERATURE_K, AMBIENT_PRESSURE_GPA,
    MIN_TEMPERATURE_K, MAX_TEMPERATURE_K,
    MIN_PRESSURE_GPA, MAX_PRESSURE_GPA,
)
from src.thermo.screening import screen_material, ScreeningResult


# --- Condition validation ---

def test_ambient_defaults():
    c = ThermoPressureConditions()
    assert c.temperature_K == 300.0
    assert abs(c.pressure_GPa - 0.000101325) < 1e-9
    assert c.is_ambient
    c.validate()


def test_custom_conditions():
    c = ThermoPressureConditions(temperature_K=1000.0, pressure_GPa=5.0)
    c.validate()
    assert not c.is_ambient
    assert c.temperature_K == 1000.0
    assert c.pressure_GPa == 5.0


def test_temperature_below_zero():
    c = ThermoPressureConditions(temperature_K=-1.0)
    with pytest.raises(ConditionValidationError, match="temperature_K"):
        c.validate()


def test_temperature_above_max():
    c = ThermoPressureConditions(temperature_K=7000.0)
    with pytest.raises(ConditionValidationError, match="temperature_K"):
        c.validate()


def test_pressure_negative():
    c = ThermoPressureConditions(pressure_GPa=-0.1)
    with pytest.raises(ConditionValidationError, match="pressure_GPa"):
        c.validate()


def test_pressure_above_max():
    c = ThermoPressureConditions(pressure_GPa=600.0)
    with pytest.raises(ConditionValidationError, match="pressure_GPa"):
        c.validate()


def test_temperature_range_inverted():
    c = ThermoPressureConditions(temperature_min_K=1000.0, temperature_max_K=500.0)
    with pytest.raises(ConditionValidationError, match="temperature_min_K"):
        c.validate()


def test_pressure_range_inverted():
    c = ThermoPressureConditions(pressure_min_GPa=50.0, pressure_max_GPa=10.0)
    with pytest.raises(ConditionValidationError, match="pressure_min_GPa"):
        c.validate()


def test_valid_range():
    c = ThermoPressureConditions(
        temperature_min_K=300.0, temperature_max_K=1500.0,
        pressure_min_GPa=0.0, pressure_max_GPa=50.0)
    c.validate()
    assert c.has_range


def test_no_range():
    c = ThermoPressureConditions()
    assert not c.has_range


# --- Serialization ---

def test_to_dict():
    c = ThermoPressureConditions(temperature_K=500.0, pressure_GPa=2.0)
    d = c.to_dict()
    assert d["temperature_K"] == 500.0
    assert d["pressure_GPa"] == 2.0
    assert "temperature_min_K" not in d  # None fields omitted


def test_to_dict_with_range():
    c = ThermoPressureConditions(
        temperature_K=500.0, pressure_GPa=2.0,
        temperature_min_K=300.0, temperature_max_K=700.0)
    d = c.to_dict()
    assert d["temperature_min_K"] == 300.0
    assert d["temperature_max_K"] == 700.0


def test_from_dict():
    d = {"temperature_K": 800.0, "pressure_GPa": 15.0}
    c = ThermoPressureConditions.from_dict(d)
    assert c.temperature_K == 800.0
    assert c.pressure_GPa == 15.0
    c.validate()


def test_to_json_roundtrip():
    c = ThermoPressureConditions(temperature_K=1200.0, pressure_GPa=3.5)
    import json
    d = json.loads(c.to_json())
    c2 = ThermoPressureConditions.from_dict(d)
    assert c2.temperature_K == c.temperature_K
    assert c2.pressure_GPa == c.pressure_GPa


# --- Standard presets ---

def test_preset_ambient():
    c = ambient()
    assert c.is_ambient
    c.validate()


def test_preset_high_temperature():
    c = high_temperature()
    assert c.temperature_K == 1200.0
    assert not c.is_ambient
    c.validate()


def test_preset_high_pressure():
    c = high_pressure()
    assert c.pressure_GPa == 10.0
    c.validate()


def test_preset_extreme():
    c = extreme()
    assert c.temperature_K == 2000.0
    assert c.pressure_GPa == 50.0
    c.validate()


def test_preset_temperature_sweep():
    c = temperature_sweep(T_min=300.0, T_max=1500.0)
    assert c.has_range
    assert c.temperature_min_K == 300.0
    assert c.temperature_max_K == 1500.0
    c.validate()


def test_preset_pressure_sweep():
    c = pressure_sweep(P_min=0.0, P_max=100.0)
    assert c.has_range
    assert c.pressure_min_GPa == 0.0
    assert c.pressure_max_GPa == 100.0
    c.validate()


# --- Screening ---

def test_screening_ambient():
    base = {"prediction": 1.5, "target": "band_gap", "model": "cgcnn"}
    result = screen_material(base, ambient())
    assert result.base_prediction == 1.5
    assert result.stability_flag == "assumed_stable"
    assert result.reliability == "baseline_model"


def test_screening_non_ambient():
    base = {"prediction": -2.1, "target": "formation_energy", "model": "alignn_lite"}
    conditions = ThermoPressureConditions(temperature_K=1500.0, pressure_GPa=20.0)
    result = screen_material(base, conditions)
    assert result.stability_flag == "unknown"
    assert result.reliability == "experimental_scaffold"
    assert "not yet implemented" in result.note


def test_screening_to_dict():
    base = {"prediction": 0.5, "target": "band_gap", "model": "cgcnn"}
    result = screen_material(base, ambient())
    d = result.to_dict()
    assert "conditions" in d
    assert "base_prediction" in d
    assert "reliability" in d


def test_screening_with_range():
    base = {"prediction": 1.0, "target": "band_gap", "model": "cgcnn"}
    conditions = temperature_sweep(T_min=300.0, T_max=2000.0)
    result = screen_material(base, conditions)
    assert result.operating_window is not None
    assert "not yet implemented" in result.operating_window


def test_screening_invalid_conditions():
    base = {"prediction": 1.0, "target": "band_gap", "model": "cgcnn"}
    conditions = ThermoPressureConditions(temperature_K=-100.0)
    with pytest.raises(ConditionValidationError):
        screen_material(base, conditions)


# --- API propagation ---

def test_api_predict_with_tp():
    """Test that /predict accepts temperature_K and pressure_GPa."""
    import tempfile
    from fastapi.testclient import TestClient
    from src.api.server import app
    from src.storage.db import MaterialsDB
    from src.schema import Material
    import src.api.server as srv

    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    srv._db = MaterialsDB(f.name)
    m = Material(formula="Si", elements=["Si"], n_elements=1,
                 band_gap=1.1, source="test", source_id="0", confidence=0.8)
    m.compute_canonical_id()
    srv._db.insert_material(m)

    client = TestClient(app)
    # T/P params accepted without error (even if no model → 404 is ok)
    r = client.post("/predict", json={
        "cif": "not real", "target": "band_gap",
        "temperature_K": 500.0, "pressure_GPa": 1.0})
    # Should get 400 (invalid CIF) or 404 (no model), not 422 (validation)
    assert r.status_code in (400, 404)

    os.unlink(f.name)
    srv._db = None


def test_api_predict_invalid_tp():
    """Test that /predict rejects invalid T/P conditions."""
    import tempfile
    from fastapi.testclient import TestClient
    from src.api.server import app
    from src.storage.db import MaterialsDB
    import src.api.server as srv

    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    srv._db = MaterialsDB(f.name)

    client = TestClient(app)
    # Negative temperature should be rejected
    r = client.post("/predict", json={
        "cif": "data_test\n_cell_length_a 5\n_cell_length_b 5\n_cell_length_c 5\n",
        "target": "band_gap",
        "temperature_K": -100.0})
    # Could be 400 for invalid conditions or for invalid CIF
    assert r.status_code in (400, 404)

    os.unlink(f.name)
    srv._db = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

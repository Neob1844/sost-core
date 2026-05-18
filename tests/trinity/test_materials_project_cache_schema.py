"""Schema tests for the Trinity Materials Project Cache v0.1."""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "materials_project_cache.schema.json"
)
CACHE_PATH = (
    REPO_ROOT / "data" / "trinity"
    / "materials_project_cache_v01.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def cache():
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == "trinity-materials-project-cache/v0.1"


def test_schema_const_locks(schema):
    assert schema["properties"]["schema"]["const"] == (
        "trinity-materials-project-cache/v0.1"
    )


def test_record_material_id_pattern(schema):
    item = schema["properties"]["records"]["items"]
    assert item["properties"]["material_id"]["pattern"] == (
        "^trinity-mpc-[a-z0-9-]{2,64}-v[0-9]+$"
    )


def test_record_sha256_patterns(schema):
    item = schema["properties"]["records"]["items"]
    for k in ("property_hash_sha256", "record_sha256"):
        assert item["properties"][k]["pattern"] == "^[0-9a-f]{64}$"


def test_cache_sha256_pattern(schema):
    assert schema["properties"]["cache_sha256"]["pattern"] == (
        "^[0-9a-f]{64}$"
    )


def test_source_enum_locked(schema):
    item = schema["properties"]["records"]["items"]
    assert item["properties"]["source"]["enum"] == [
        "cached_materials_project_style_reference",
    ]


def test_schema_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False
    item = schema["properties"]["records"]["items"]
    assert item["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Cache file validates against schema
# ---------------------------------------------------------------------------


def test_cache_file_validates(schema, cache):
    jsonschema.validate(cache, schema)


def test_cache_carries_ceria_and_prox(cache):
    formulas = {r["formula_pretty"] for r in cache["records"]}
    assert "CeO2" in formulas
    assert "PrOx" in formulas


def test_every_record_has_aliases(cache):
    for r in cache["records"]:
        assert len(r["aliases"]) >= 1


def test_record_count_matches_actual_length(cache):
    assert cache["record_count"] == len(cache["records"])


def test_no_record_carries_a_live_sost_address(cache):
    """Defensive: no real sost1+40hex addresses should appear in
    the cache. Reference data only — not wallet material."""
    raw = json.dumps(cache, sort_keys=True)
    # Reject any sost1 prefix followed by 40 hex chars.
    assert not re.search(r"sost1[0-9a-f]{40}", raw), (
        "cache appears to carry a real SOST address"
    )

"""Trinity / Useful Compute worker address map helper v0.1."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def map_mod():
    return _load(
        "ucwam",
        SCRIPTS_DIR / "useful_compute_worker_address_map.py",
    )


# ---------------------------------------------------------------------------
# create-template
# ---------------------------------------------------------------------------


def test_create_template_writes_placeholder_file(tmp_path, map_mod):
    out = tmp_path / "tmpl.json"
    rc = map_mod.main([
        "create-template", "--out", str(out), "--entries", "5",
    ])
    assert rc == 0
    obj = json.loads(out.read_text(encoding="utf-8"))
    assert obj["schema"] == "trinity-worker-address-map/v0.1"
    assert len(obj["workers"]) == 5
    for w in obj["workers"]:
        assert "worker_id_hash" in w
        assert "payout_address" in w
        # Placeholder uses xxxx chars; not a valid bech32 charset
        assert "xxx" in w["payout_address"]


def test_create_template_rejects_zero_entries(tmp_path, map_mod):
    out = tmp_path / "tmpl.json"
    rc = map_mod.main([
        "create-template", "--out", str(out), "--entries", "0",
    ])
    assert rc == 2


def test_create_template_rejects_too_many_entries(tmp_path, map_mod):
    out = tmp_path / "tmpl.json"
    rc = map_mod.main([
        "create-template", "--out", str(out), "--entries", "9999",
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def _write(tmp_path, obj):
    p = tmp_path / "map.json"
    p.write_text(
        json.dumps(obj, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return p


def test_validate_accepts_well_formed_map(tmp_path, map_mod):
    p = _write(tmp_path, {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [
            {"worker_id_hash": "f" * 16,
             "payout_address":
                 "sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
             "label": "Alice"},
        ],
    })
    rc = map_mod.main(["validate", "--path", str(p)])
    assert rc == 0


def test_validate_rejects_wrong_schema_string(tmp_path, map_mod):
    p = _write(tmp_path, {
        "schema": "wrong/v0",
        "workers": [],
    })
    rc = map_mod.main(["validate", "--path", str(p)])
    assert rc == 2


def test_validate_rejects_invalid_bech32_address(tmp_path, map_mod):
    p = _write(tmp_path, {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [
            {"worker_id_hash": "f" * 16,
             "payout_address": "not-a-sost-address"},
        ],
    })
    rc = map_mod.main(["validate", "--path", str(p)])
    assert rc == 2


def test_validate_rejects_duplicate_worker_id_hash(tmp_path, map_mod):
    p = _write(tmp_path, {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [
            {"worker_id_hash": "a" * 16,
             "payout_address":
                 "sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            {"worker_id_hash": "a" * 16,
             "payout_address":
                 "sost1cccccccccccccccccccccccccccccccccccccccc"},
        ],
    })
    rc = map_mod.main(["validate", "--path", str(p)])
    assert rc == 2


def test_validate_rejects_duplicate_payout_address(tmp_path, map_mod):
    p = _write(tmp_path, {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [
            {"worker_id_hash": "a" * 16,
             "payout_address":
                 "sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            {"worker_id_hash": "c" * 16,
             "payout_address":
                 "sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        ],
    })
    rc = map_mod.main(["validate", "--path", str(p)])
    assert rc == 2


def test_validate_rejects_extra_top_level_field(tmp_path, map_mod):
    p = _write(tmp_path, {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [],
        "secret": "x",
    })
    rc = map_mod.main(["validate", "--path", str(p)])
    assert rc == 2


def test_validate_rejects_extra_worker_field(tmp_path, map_mod):
    p = _write(tmp_path, {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [
            {"worker_id_hash": "f" * 16,
             "payout_address":
                 "sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
             "private_key": "deadbeef"},
        ],
    })
    rc = map_mod.main(["validate", "--path", str(p)])
    assert rc == 2


def test_validate_missing_file_returns_2(tmp_path, map_mod):
    rc = map_mod.main([
        "validate", "--path", str(tmp_path / "missing.json"),
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# helper API
# ---------------------------------------------------------------------------


def test_validate_address_helper_accepts_valid(map_mod):
    assert map_mod.validate_address(
        "sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    ) is None


def test_validate_address_helper_rejects_non_hex_chars(map_mod):
    # Canonical SOST address = "sost1" + 40 lowercase hex chars.
    # Anything outside [0-9a-f] in the body is rejected, as is any
    # length other than 40 body chars.
    assert map_mod.validate_address(
        "sost1aliceXXXXXXXXXXXXXXXXXXXXXXXX",
    ) is not None  # uppercase + non-hex letters
    assert map_mod.validate_address(
        "sost1abi" + "a" * 32,
    ) is not None  # 'i' is not in [0-9a-f]
    assert map_mod.validate_address(
        "sost1o" + "a" * 32,
    ) is not None  # 'o' is not in [0-9a-f]


def test_validate_address_helper_rejects_wrong_prefix(map_mod):
    assert map_mod.validate_address(
        "sost2qaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    ) is not None
    assert map_mod.validate_address("") is not None
    assert map_mod.validate_address(None) is not None

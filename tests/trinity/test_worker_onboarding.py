"""Trinity Friendly Worker Onboarding v0.1 (Sprint 5.35) tests."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "worker_onboarding_bundle.schema.json"
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ob_mod():
    return _load("wob", SCRIPTS_DIR / "worker_onboarding.py")


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# build_bundle determinism + shape
# ---------------------------------------------------------------------------


def test_bundle_id_pattern(ob_mod):
    b = ob_mod.build_bundle(
        worker_id="worker-A",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    assert re.match(r"^twob-[0-9a-f]{16}$", b["bundle_id"])


def test_worker_id_hash_is_sha16(ob_mod):
    import hashlib
    b = ob_mod.build_bundle(
        worker_id="worker-Z",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    expected = hashlib.sha256(b"worker-Z").hexdigest()[:16]
    assert b["worker_id_hash"] == expected


def test_bundle_deterministic_for_same_inputs(ob_mod):
    a = ob_mod.build_bundle(
        worker_id="worker-A",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    b = ob_mod.build_bundle(
        worker_id="worker-A",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    assert a == b


def test_bundle_different_worker_id_different_bundle_id(ob_mod):
    a = ob_mod.build_bundle(
        worker_id="worker-A",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    b = ob_mod.build_bundle(
        worker_id="worker-B",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    assert a["bundle_id"] != b["bundle_id"]


# ---------------------------------------------------------------------------
# Validation against schema
# ---------------------------------------------------------------------------


def test_bundle_validates(ob_mod, schema):
    b = ob_mod.build_bundle(
        worker_id="worker-C",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    jsonschema.validate(b, schema)


@pytest.mark.parametrize("wid", ["worker-A", "wkr.test_01", "x"])
def test_various_valid_worker_ids_pass(ob_mod, schema, wid):
    b = ob_mod.build_bundle(
        worker_id=wid,
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    jsonschema.validate(b, schema)


@pytest.mark.parametrize("bad", [
    "worker A",          # space
    "worker/A",          # slash
    "worker$A",          # special
    "",                  # empty
    "x" * 65,            # too long
])
def test_invalid_worker_id_rejected(ob_mod, bad):
    with pytest.raises(ob_mod.OnboardingError):
        ob_mod.build_bundle(
            worker_id=bad,
            pinned_time="2026-05-18T00:00:00+00:00",
        )


# ---------------------------------------------------------------------------
# Safety: NO secrets in the bundle
# ---------------------------------------------------------------------------


def test_bundle_safety_status_all_const_true(ob_mod):
    b = ob_mod.build_bundle(
        worker_id="worker-A",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    for k, v in b["safety_status"].items():
        assert v is True, k + " is not True"


def test_bundle_address_map_template_uses_placeholder(ob_mod):
    b = ob_mod.build_bundle(
        worker_id="worker-A",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    workers = b["address_map_template"]["workers"]
    assert len(workers) == 1
    addr = workers[0]["payout_address"]
    # The schema enforces ^<PAYOUT_ADDRESS_FOR_[A-Za-z0-9._-]+>$
    assert addr.startswith("<PAYOUT_ADDRESS_FOR_")
    assert addr.endswith(">")
    # Real SOST address pattern must NOT match.
    assert not re.match(r"^sost1[0-9a-f]{40}$", addr)


def test_bundle_does_not_contain_real_sost_address(ob_mod):
    b = ob_mod.build_bundle(
        worker_id="worker-A",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    raw = json.dumps(b)
    assert not re.search(r"sost1[0-9a-f]{40}", raw), (
        "bundle contains a real SOST address — must be a placeholder"
    )


def test_bundle_does_not_contain_private_key_blob(ob_mod):
    """Defensive: the bundle should not contain any 64-hex blob
    that could be confused with a private key. The legitimate
    hashes in the bundle are worker_id_hash (16-hex) and
    bundle_id (16-hex with twob- prefix), neither of which is
    64-hex."""
    b = ob_mod.build_bundle(
        worker_id="worker-A",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    raw = json.dumps(b)
    assert not re.search(r"[0-9a-f]{64}", raw), (
        "bundle contains a 64-hex blob that could look like a key"
    )


def test_required_commands_all_declare_no_wallet(ob_mod):
    b = ob_mod.build_bundle(
        worker_id="worker-A",
        pinned_time="2026-05-18T00:00:00+00:00",
    )
    for c in b["required_commands"]:
        assert c["requires_wallet"] is False
        assert c["requires_private_key"] is False
        assert c["requires_network"] is False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_writes_bundle(tmp_path, ob_mod, schema):
    out = tmp_path / "bundle.json"
    rc = ob_mod.main([
        "--worker-id", "worker-C",
        "--out-json", str(out),
        "--pinned-time", "2026-05-18T00:00:00+00:00",
    ])
    assert rc == 0
    assert out.is_file()
    b = json.loads(out.read_text(encoding="utf-8"))
    jsonschema.validate(b, schema)


def test_cli_rejects_bad_worker_id(tmp_path, ob_mod):
    out = tmp_path / "bundle.json"
    rc = ob_mod.main([
        "--worker-id", "bad space",
        "--out-json", str(out),
        "--pinned-time", "2026-05-18T00:00:00+00:00",
    ])
    assert rc == 2
    assert not out.exists()


def test_cli_repeatable_with_pinned_time(tmp_path, ob_mod):
    """Same args → byte-identical file."""
    out1 = tmp_path / "a.json"
    out2 = tmp_path / "b.json"
    for o in (out1, out2):
        rc = ob_mod.main([
            "--worker-id", "worker-A",
            "--out-json", str(o),
            "--pinned-time", "2026-05-18T00:00:00+00:00",
        ])
        assert rc == 0
    assert out1.read_bytes() == out2.read_bytes()

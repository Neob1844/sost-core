"""Trinity / Useful Compute payment draft schema — strict v0.2."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_payment_draft.schema.json"
)


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def draft_mod():
    return _load(
        "ucpd_schema",
        SCRIPTS_DIR / "useful_compute_payment_draft.py",
    )


UNSIGNED_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST"


def test_schema_id_is_v02(schema):
    assert schema["$id"] == \
        "trinity-useful-compute-payment-draft/v0.2"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "draft_id", "source_proposal_id", "mode",
        "signing_mode",
        "unsigned_only", "dry_signed", "real_signed",
        "total_outputs", "total_payment_stocks",
        "total_fee_stocks_estimated", "change_stocks_estimated",
        "outputs", "capsule_summary", "capsule_attached",
        "warnings", "safety_status",
    }
    assert set(schema["required"]) == expected


def test_capsule_attached_locked_false(schema):
    """v0.1 of --real-sign never attaches the capsule to the
    signed tx; capsule_attached MUST be locked const-false in the
    schema."""
    ca = schema["properties"]["capsule_attached"]
    assert ca["type"] == "boolean"
    assert ca["const"] is False


def test_sost_cli_bin_hash_typed_optional(schema):
    """sost_cli_bin_hash is optional (string-16-hex or null)."""
    sb = schema["properties"]["sost_cli_bin_hash"]
    one_of = sb["oneOf"]
    assert any(
        s.get("type") == "string" and s.get("pattern") == "^[0-9a-f]{16}$"
        for s in one_of
    )
    assert any(s.get("type") == "null" for s in one_of)


def test_signing_mode_enum_locked(schema):
    enum = schema["properties"]["signing_mode"]["enum"]
    assert set(enum) == {
        "unsigned_only", "dry_sign_placeholder", "real_sign_local",
    }


def test_safety_status_const_flags_locked(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    assert ss["properties"]["no_broadcast"]["const"] is True
    assert ss["properties"]["human_review_required"]["const"] is True
    assert ss["properties"]["private_keys_exported"]["const"] is False
    assert ss["properties"]["requires_separate_broadcast"]["const"] is True
    assert ss["properties"]["automatic_payout"]["const"] is False


def test_safety_status_dry_sign_and_wallet_flags_are_typed(schema):
    """dry_sign_only and wallet_access_used vary with mode; they
    must be typed boolean without const."""
    ss = schema["properties"]["safety_status"]
    assert ss["properties"]["dry_sign_only"]["type"] == "boolean"
    assert "const" not in ss["properties"]["dry_sign_only"]
    assert ss["properties"]["wallet_access_used"]["type"] == "boolean"
    assert "const" not in ss["properties"]["wallet_access_used"]


def test_mode_enum_locked(schema):
    assert schema["properties"]["mode"]["enum"] == ["local-dry-run"]


def test_capsule_template_enum_locked(schema):
    enum = schema["properties"]["capsule_summary"]["properties"][
        "template"]["enum"]
    assert enum == ["useful_compute_reward_batch_v1"]


def _validate_against_schema(obj, schema):
    if schema.get("type") == "object":
        if not isinstance(obj, dict):
            raise AssertionError("not an object")
        required = set(schema.get("required", []))
        missing = required - set(obj.keys())
        if missing:
            raise AssertionError(f"missing fields: {sorted(missing)}")
        if schema.get("additionalProperties") is False:
            allowed = set(schema["properties"].keys())
            extra = set(obj.keys()) - allowed
            if extra:
                raise AssertionError(f"extra fields: {sorted(extra)}")
        for k, sub in schema["properties"].items():
            if k in obj:
                _validate_against_schema(obj[k], sub)
    elif schema.get("type") == "array":
        for item in obj:
            _validate_against_schema(item, schema.get("items", {}))
    else:
        if "const" in schema:
            assert obj == schema["const"]
        if "enum" in schema:
            assert obj in schema["enum"]
        if "pattern" in schema:
            assert isinstance(obj, str)
            assert re.match(schema["pattern"], obj)
        if "oneOf" in schema:
            ok = False
            for sub in schema["oneOf"]:
                try:
                    _validate_against_schema(obj, sub)
                    ok = True
                    break
                except AssertionError:
                    continue
            assert ok, f"oneOf failed for {obj!r}"
        if schema.get("type") == "integer":
            assert isinstance(obj, int) and not isinstance(obj, bool)
        if schema.get("type") == "number":
            assert isinstance(obj, (int, float)) and not isinstance(obj, bool)
        if schema.get("type") == "string":
            assert isinstance(obj, str)
        if schema.get("type") == "boolean":
            assert isinstance(obj, bool)


def _proposal_at(tmp_path):
    obj = {
        "schema": "trinity-useful-compute-payment-proposal/v0.1",
        "proposal_id": "prop-" + "a" * 16,
        "mode": "local-dry-run",
        "pinned_time": "2026-05-12T00:00:00+00:00",
        "source_budget_id": "bud-" + "1" * 16,
        "total_payable_stocks": 1000,
        "total_deferred_stocks": 0,
        "total_unresolved_stocks": 0,
        "payable_items": [{
            "request_id": "uc-" + "1" * 16,
            "worker_result_ids": ["c" * 16],
            "payout_address":
                "sost1qaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "allocated_stocks": 1000,
            "allocated_sost": 0.00001,
            "source_budget_id": "bud-" + "1" * 16,
            "source_governance_batch_id": "gov-" + "2" * 16,
            "reason": "test",
        }],
        "unresolved_items": [],
        "deferred_items": [],
        "rejected_items": [],
        "capsule_summary": {
            "template": "useful_compute_reward_batch_v1",
            "text": "Trinity Useful Compute reward proposal "
                    "prop-test; payable=1000 stocks; budget=bud-test",
            "referenced_files": {
                "budget_id": "bud-" + "1" * 16,
                "governance_batch_ids": ["gov-" + "2" * 16],
                "validation_ids": [],
            },
        },
        "safety_status": {
            "no_private_keys": True, "no_wallet_access": True,
            "no_signature": True, "no_broadcast": True,
            "proposal_only": True,
            "requires_manual_signing": True,
            "requires_separate_broadcast": True,
        },
    }
    p = tmp_path / "p.json"
    p.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":")),
                 encoding="utf-8")
    return p


def test_unsigned_draft_validates_against_schema(
    tmp_path, schema, draft_mod,
):
    pp = _proposal_at(tmp_path)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    _validate_against_schema(draft, schema)


def test_draft_rejects_extra_fields(
    tmp_path, schema, draft_mod,
):
    pp = _proposal_at(tmp_path)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    draft["sneaky"] = 1
    with pytest.raises(AssertionError, match="extra fields"):
        _validate_against_schema(draft, schema)


def test_dry_sign_draft_validates_against_schema(
    tmp_path, schema, draft_mod,
):
    DRY_TOKEN = "I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST"
    pp = _proposal_at(tmp_path)
    wallet = tmp_path / "w.json"
    wallet.write_text("{}", encoding="utf-8")
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=False, dry_sign=True,
        wallet_path=wallet, from_label="t",
        require_confirmation_token=DRY_TOKEN,
    )
    _validate_against_schema(draft, schema)

"""Trinity / Useful Compute broadcast receipt schema — strict v0.2."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_broadcast_receipt.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_id_is_v02(schema):
    assert schema["$id"] == \
        "trinity-useful-compute-broadcast-receipt/v0.2"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "receipt_id", "source_draft_id",
        "txid_if_signed", "txid_broadcast",
        "signed_tx_hex_sha256",
        "broadcast_attempted", "broadcast_performed",
        "broadcast_mode", "broadcast_result_status",
        "node_txid_observed",
        "node_stdout_sha256", "node_stderr_sha256",
        "confirmation_token_hash",
        "total_payment_stocks", "max_total_stocks",
        "pinned_time", "sost_cli_bin_hash",
        "safety_status",
    }
    assert set(schema["required"]) == expected


def test_broadcast_mode_enum(schema):
    enum = schema["properties"]["broadcast_mode"]["enum"]
    assert set(enum) == {"local-dry-run", "human-broadcast"}


def test_broadcast_result_status_enum(schema):
    enum = schema["properties"]["broadcast_result_status"]["enum"]
    assert set(enum) == {
        "dry_run", "broadcasted",
        "cli_rejected",
        "node_rejected", "txid_mismatch", "parse_error",
    }


def test_safety_status_const_flags_all_locked(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    for k in (
        "human_broadcast_only",
        "requires_manual_confirmation",
        "no_private_keys", "no_wallet_access", "no_signing",
        "no_automatic_payout", "single_transaction_only",
    ):
        assert ss["properties"][k]["const"] is True


def test_node_observed_fields_are_optional_string_or_null(schema):
    for fname in (
        "node_txid_observed",
        "node_stdout_sha256", "node_stderr_sha256",
    ):
        one_of = schema["properties"][fname]["oneOf"]
        assert any(s.get("type") == "null" for s in one_of)
        assert any(s.get("pattern") for s in one_of)


def test_broadcast_attempted_and_performed_typed(schema):
    assert schema["properties"]["broadcast_attempted"]["type"] == \
        "boolean"
    assert schema["properties"]["broadcast_performed"]["type"] == \
        "boolean"


def test_receipt_id_and_signed_tx_hex_sha256_patterns(schema):
    assert schema["properties"]["receipt_id"]["pattern"] == \
        "^rcpt-[0-9a-f]{16}$"
    assert schema["properties"]["signed_tx_hex_sha256"]["pattern"] \
        == "^[0-9a-f]{64}$"

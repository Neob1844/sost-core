"""Trinity / Useful Compute broadcast receipt schema — strict v0.1."""

from __future__ import annotations

import json
import re
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


def test_schema_id_is_v01(schema):
    assert schema["$id"] == \
        "trinity-useful-compute-broadcast-receipt/v0.1"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "receipt_id", "source_draft_id",
        "txid_if_signed", "txid_broadcast",
        "signed_tx_hex_sha256",
        "broadcast_performed", "broadcast_mode",
        "confirmation_token_hash",
        "total_payment_stocks", "max_total_stocks",
        "pinned_time", "sost_cli_bin_hash",
        "safety_status",
    }
    assert set(schema["required"]) == expected


def test_broadcast_mode_enum(schema):
    enum = schema["properties"]["broadcast_mode"]["enum"]
    assert set(enum) == {"local-dry-run", "human-broadcast"}


def test_safety_status_const_flags_all_locked(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    for k in (
        "human_broadcast_only",
        "requires_manual_confirmation",
        "no_private_keys", "no_wallet_access", "no_signing",
        "no_automatic_payout", "single_transaction_only",
    ):
        assert ss["properties"][k]["const"] is True, (
            f"safety_status.{k} must be const-true"
        )


def test_signed_tx_hex_sha256_pattern(schema):
    p = schema["properties"]["signed_tx_hex_sha256"]
    assert p["type"] == "string"
    assert p["pattern"] == "^[0-9a-f]{64}$"


def test_receipt_id_pattern(schema):
    p = schema["properties"]["receipt_id"]
    assert p["pattern"] == "^rcpt-[0-9a-f]{16}$"


def test_txid_broadcast_oneof_string_or_null(schema):
    one_of = schema["properties"]["txid_broadcast"]["oneOf"]
    assert any(s.get("pattern") == "^[0-9a-f]{64}$" for s in one_of)
    assert any(s.get("type") == "null" for s in one_of)


def test_max_total_stocks_integer_nonneg(schema):
    p = schema["properties"]["max_total_stocks"]
    assert p["type"] == "integer"
    assert p["minimum"] == 0

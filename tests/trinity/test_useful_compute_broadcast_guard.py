"""Trinity / Useful Compute broadcast guard — Sprint 5.18 v0.1.

Functional tests with subprocess fully mocked so no real sost-cli
binary or running node is required.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_broadcast_receipt.schema.json"
)


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def guard_mod():
    return _load(
        "ucbg",
        SCRIPTS_DIR / "useful_compute_broadcast_guard.py",
    )


HUMAN_TOKEN = "I_UNDERSTAND_THIS_WILL_BROADCAST_A_SIGNED_TRANSACTION"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_VALID_TXID = "a" * 64
_VALID_HEX = "deadbeef" * 16


def _good_draft(
    *,
    txid: str = _VALID_TXID,
    signed_hex: str = _VALID_HEX,
    total_payment_stocks: int = 5_000,
) -> Dict[str, Any]:
    """Build a v0.2 real-signed draft that should pass every guard
    check."""
    return {
        "schema": "trinity-useful-compute-payment-draft/v0.2",
        "draft_id": "draft-" + "1" * 16,
        "source_proposal_id": "prop-" + "2" * 16,
        "mode": "local-dry-run",
        "signing_mode": "real_sign_local",
        "signing_scope": "full_proposal",
        "selected_worker_id_hash": None,
        "source_proposal_payable_items_count": 1,
        "unsigned_only": False,
        "dry_signed": False,
        "real_signed": True,
        "wallet_fingerprint_hash": "abcdef0123456789",
        "signer_label_or_address_hash": "fedcba9876543210",
        "sost_cli_bin_hash": "1111222233334444",
        "total_outputs": 1,
        "total_payment_stocks": total_payment_stocks,
        "total_fee_stocks_estimated": 250,
        "change_stocks_estimated": 0,
        "total_input_stocks": 0,
        "total_output_stocks": total_payment_stocks,
        "fee_rate_stocks_per_byte": 1,
        "selected_utxos": [],
        "outputs": [{
            "payout_address":
                "sost1qaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "amount_stocks": total_payment_stocks,
            "amount_sost": total_payment_stocks / 100_000_000,
            "request_id": "uc-" + "3" * 16,
            "worker_result_ids": ["c" * 16],
            "reason": "test",
        }],
        "capsule_summary": {
            "template": "useful_compute_reward_batch_v1",
            "text": "Trinity Useful Compute test capsule",
            "referenced_files": {
                "budget_id": "bud-" + "1" * 16,
                "governance_batch_ids": ["gov-" + "2" * 16],
                "validation_ids": [],
            },
        },
        "capsule_attached": False,
        "unsigned_tx_hex": None,
        "signed_tx_hex": signed_hex,
        "txid_if_signed": txid,
        "warnings": ["SIGNED BUT NOT BROADCAST"],
        "safety_status": {
            "no_broadcast": True,
            "human_review_required": True,
            "dry_sign_only": False,
            "wallet_access_used": True,
            "private_keys_exported": False,
            "requires_separate_broadcast": True,
            "automatic_payout": False,
        },
    }


def _write_draft(tmp_path: Path, draft: Dict[str, Any]) -> Path:
    p = tmp_path / "draft.json"
    p.write_text(
        json.dumps(draft, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return p


@dataclass
class _FakeCompleted:
    returncode: int
    stdout: str
    stderr: str = ""


def _install_fake_subprocess(monkeypatch, guard_mod, responses):
    queue = list(responses)
    captured_argvs: List[List[str]] = []

    def fake_run(argv, **kwargs):
        captured_argvs.append(list(argv))
        if not queue:
            raise RuntimeError(
                "fake subprocess ran out of responses"
            )
        rc, out, err = queue.pop(0)
        return _FakeCompleted(returncode=rc, stdout=out, stderr=err)

    monkeypatch.setattr(guard_mod.subprocess, "run", fake_run)
    return captured_argvs


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


def test_dry_run_emits_receipt_without_subprocess(
    tmp_path, guard_mod, monkeypatch,
):
    draft = _good_draft()
    dp = _write_draft(tmp_path, draft)
    captured = _install_fake_subprocess(
        monkeypatch, guard_mod, [],
    )
    receipt = guard_mod.run_broadcast_guard(
        draft_path=dp,
        out_dir=tmp_path / "out",
        mode="local-dry-run",
        max_total_stocks=1_000_000,
        pinned_time="2026-05-13T00:00:00+00:00",
        sost_cli_bin="sost-cli-fake",
    )
    assert receipt["broadcast_performed"] is False
    assert receipt["broadcast_mode"] == "local-dry-run"
    assert receipt["txid_broadcast"] is None
    assert receipt["confirmation_token_hash"] is None
    assert receipt["source_draft_id"] == draft["draft_id"]
    assert receipt["txid_if_signed"] == draft["txid_if_signed"]
    assert receipt["total_payment_stocks"] == \
        draft["total_payment_stocks"]
    # No subprocess in dry-run, period.
    assert captured == []


# ---------------------------------------------------------------------------
# Token gates
# ---------------------------------------------------------------------------


def test_human_broadcast_without_token_rejected(
    tmp_path, guard_mod, monkeypatch,
):
    draft = _good_draft()
    dp = _write_draft(tmp_path, draft)
    captured = _install_fake_subprocess(monkeypatch, guard_mod, [])
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match="confirmation token",
    ):
        guard_mod.run_broadcast_guard(
            draft_path=dp,
            out_dir=tmp_path / "out",
            mode="human-broadcast",
            max_total_stocks=1_000_000,
            pinned_time="2026-05-13T00:00:00+00:00",
            sost_cli_bin="sost-cli-fake",
        )
    assert captured == []


def test_human_broadcast_with_wrong_token_rejected(
    tmp_path, guard_mod, monkeypatch,
):
    draft = _good_draft()
    dp = _write_draft(tmp_path, draft)
    captured = _install_fake_subprocess(monkeypatch, guard_mod, [])
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match="confirmation token",
    ):
        guard_mod.run_broadcast_guard(
            draft_path=dp,
            out_dir=tmp_path / "out",
            mode="human-broadcast",
            max_total_stocks=1_000_000,
            pinned_time="2026-05-13T00:00:00+00:00",
            require_confirmation_token="wrong",
            sost_cli_bin="sost-cli-fake",
        )
    assert captured == []


# ---------------------------------------------------------------------------
# Draft validation gates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mutator,match", [
    (lambda d: d.update(schema="trinity-wrong/v0"), "schema"),
    (lambda d: d.update(real_signed=False), "real_signed"),
    (lambda d: d.update(signing_mode="unsigned_only"),
     "signing_mode"),
    (lambda d: d.update(signed_tx_hex=""), "signed_tx_hex"),
    (lambda d: d.update(signed_tx_hex="not-hex!"), "signed_tx_hex"),
    (lambda d: d.update(signed_tx_hex="abc"), "signed_tx_hex"),
    (lambda d: d.update(txid_if_signed="short"), "txid_if_signed"),
    (lambda d: d.update(capsule_attached=True), "capsule_attached"),
])
def test_draft_rejected_for(
    tmp_path, guard_mod, monkeypatch, mutator, match,
):
    draft = _good_draft()
    mutator(draft)
    dp = _write_draft(tmp_path, draft)
    captured = _install_fake_subprocess(monkeypatch, guard_mod, [])
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match=match,
    ):
        guard_mod.run_broadcast_guard(
            draft_path=dp,
            out_dir=tmp_path / "out",
            mode="human-broadcast",
            max_total_stocks=1_000_000,
            pinned_time="2026-05-13T00:00:00+00:00",
            require_confirmation_token=HUMAN_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )
    assert captured == []


@pytest.mark.parametrize("safety_key,bad_value,match", [
    ("no_broadcast", False, "no_broadcast"),
    ("automatic_payout", True, "automatic_payout"),
    ("human_review_required", False, "human_review_required"),
    ("private_keys_exported", True, "private_keys_exported"),
    ("requires_separate_broadcast", False,
     "requires_separate_broadcast"),
])
def test_safety_status_flag_rejected(
    tmp_path, guard_mod, monkeypatch,
    safety_key, bad_value, match,
):
    draft = _good_draft()
    draft["safety_status"][safety_key] = bad_value
    dp = _write_draft(tmp_path, draft)
    captured = _install_fake_subprocess(monkeypatch, guard_mod, [])
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match=match,
    ):
        guard_mod.run_broadcast_guard(
            draft_path=dp,
            out_dir=tmp_path / "out",
            mode="human-broadcast",
            max_total_stocks=1_000_000,
            pinned_time="2026-05-13T00:00:00+00:00",
            require_confirmation_token=HUMAN_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )
    assert captured == []


def test_unknown_signing_scope_rejected(
    tmp_path, guard_mod, monkeypatch,
):
    draft = _good_draft()
    draft["signing_scope"] = "future_unknown_scope"
    dp = _write_draft(tmp_path, draft)
    captured = _install_fake_subprocess(monkeypatch, guard_mod, [])
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match="signing_scope",
    ):
        guard_mod.run_broadcast_guard(
            draft_path=dp,
            out_dir=tmp_path / "out",
            mode="human-broadcast",
            max_total_stocks=1_000_000,
            pinned_time="2026-05-13T00:00:00+00:00",
            require_confirmation_token=HUMAN_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )
    assert captured == []


# ---------------------------------------------------------------------------
# Cap
# ---------------------------------------------------------------------------


def test_max_total_cap_blocks_before_subprocess(
    tmp_path, guard_mod, monkeypatch,
):
    draft = _good_draft(total_payment_stocks=10_000)
    dp = _write_draft(tmp_path, draft)
    captured = _install_fake_subprocess(monkeypatch, guard_mod, [])
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match="max-total-stocks",
    ):
        guard_mod.run_broadcast_guard(
            draft_path=dp,
            out_dir=tmp_path / "out",
            mode="human-broadcast",
            max_total_stocks=5_000,
            pinned_time="2026-05-13T00:00:00+00:00",
            require_confirmation_token=HUMAN_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )
    assert captured == []


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def _fake_sendraw_stdout(txid: str) -> str:
    return "Txid: " + txid + "\n"


def test_human_broadcast_happy_path(
    tmp_path, guard_mod, monkeypatch,
):
    draft = _good_draft()
    dp = _write_draft(tmp_path, draft)
    captured = _install_fake_subprocess(
        monkeypatch, guard_mod,
        [(0, _fake_sendraw_stdout(_VALID_TXID), "")],
    )
    receipt = guard_mod.run_broadcast_guard(
        draft_path=dp,
        out_dir=tmp_path / "out",
        mode="human-broadcast",
        max_total_stocks=1_000_000,
        pinned_time="2026-05-13T00:00:00+00:00",
        require_confirmation_token=HUMAN_TOKEN,
        sost_cli_bin="sost-cli-fake",
    )
    assert receipt["broadcast_performed"] is True
    assert receipt["broadcast_mode"] == "human-broadcast"
    assert receipt["txid_broadcast"] == _VALID_TXID
    assert receipt["confirmation_token_hash"] is not None
    assert len(receipt["confirmation_token_hash"]) == 64
    # argv inspection
    assert len(captured) == 1
    argv = captured[0]
    assert argv[0] == "sost-cli-fake"
    assert argv[1] == "sendrawtransaction"
    assert argv[2] == draft["signed_tx_hex"]
    for forbidden in (
        "--auto-pay", "--send", "--payout-now",
        "--export-private-key", "--sign-now",
    ):
        assert forbidden not in argv


def test_human_broadcast_txid_mismatch_rejected(
    tmp_path, guard_mod, monkeypatch,
):
    """If the node returns a different txid than the draft claims,
    something is very wrong and we refuse to write a clean
    receipt."""
    draft = _good_draft()
    dp = _write_draft(tmp_path, draft)
    different_txid = "b" * 64
    captured = _install_fake_subprocess(
        monkeypatch, guard_mod,
        [(0, _fake_sendraw_stdout(different_txid), "")],
    )
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match="txid mismatch",
    ):
        guard_mod.run_broadcast_guard(
            draft_path=dp,
            out_dir=tmp_path / "out",
            mode="human-broadcast",
            max_total_stocks=1_000_000,
            pinned_time="2026-05-13T00:00:00+00:00",
            require_confirmation_token=HUMAN_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )
    assert len(captured) == 1


def test_human_broadcast_nonzero_exit_rejected(
    tmp_path, guard_mod, monkeypatch,
):
    draft = _good_draft()
    dp = _write_draft(tmp_path, draft)
    captured = _install_fake_subprocess(
        monkeypatch, guard_mod,
        [(1, "", "Error: insufficient fee")],
    )
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match="sendrawtransaction exited 1",
    ):
        guard_mod.run_broadcast_guard(
            draft_path=dp,
            out_dir=tmp_path / "out",
            mode="human-broadcast",
            max_total_stocks=1_000_000,
            pinned_time="2026-05-13T00:00:00+00:00",
            require_confirmation_token=HUMAN_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )
    assert len(captured) == 1


# ---------------------------------------------------------------------------
# CLI flag rejection
# ---------------------------------------------------------------------------


def test_cli_rejects_auto_pay(tmp_path, guard_mod):
    rc = guard_mod.main([
        "--mode", "local-dry-run",
        "--draft", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--max-total-stocks", "100",
        "--auto-pay",
    ])
    assert rc == 2


def test_cli_rejects_sign_now(tmp_path, guard_mod):
    rc = guard_mod.main([
        "--mode", "local-dry-run",
        "--draft", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--max-total-stocks", "100",
        "--sign-now",
    ])
    assert rc == 2


def test_cli_rejects_payout_now(tmp_path, guard_mod):
    rc = guard_mod.main([
        "--mode", "local-dry-run",
        "--draft", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--max-total-stocks", "100",
        "--payout-now",
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# Argv safety unit tests
# ---------------------------------------------------------------------------


def test_argv_safety_rejects_send_subcommand(guard_mod):
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match="allowlist",
    ):
        guard_mod._scan_argv_safety(
            ["sost-cli", "send", "sost1...", "1.0"],
        )


def test_argv_safety_rejects_forbidden_token(guard_mod):
    with pytest.raises(
        guard_mod.BroadcastGuardError,
        match="forbidden token",
    ):
        guard_mod._scan_argv_safety(
            ["sost-cli", "sendrawtransaction", "deadbeef",
             "--auto-pay"],
        )


# ---------------------------------------------------------------------------
# Schema validation of the receipt
# ---------------------------------------------------------------------------


def _validate_against_schema(obj, schema):
    if schema.get("type") == "object":
        assert isinstance(obj, dict)
        required = set(schema.get("required", []))
        missing = required - set(obj.keys())
        assert not missing, f"missing fields: {sorted(missing)}"
        if schema.get("additionalProperties") is False:
            allowed = set(schema["properties"].keys())
            extra = set(obj.keys()) - allowed
            assert not extra, f"extra fields: {sorted(extra)}"
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


def test_dry_run_receipt_validates(tmp_path, guard_mod):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    draft = _good_draft()
    dp = _write_draft(tmp_path, draft)
    receipt = guard_mod.run_broadcast_guard(
        draft_path=dp,
        out_dir=tmp_path / "out",
        mode="local-dry-run",
        max_total_stocks=1_000_000,
        pinned_time="2026-05-13T00:00:00+00:00",
        sost_cli_bin="sost-cli-fake",
    )
    _validate_against_schema(receipt, schema)


def test_human_broadcast_receipt_validates(
    tmp_path, guard_mod, monkeypatch,
):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    draft = _good_draft()
    dp = _write_draft(tmp_path, draft)
    _install_fake_subprocess(
        monkeypatch, guard_mod,
        [(0, _fake_sendraw_stdout(_VALID_TXID), "")],
    )
    receipt = guard_mod.run_broadcast_guard(
        draft_path=dp,
        out_dir=tmp_path / "out",
        mode="human-broadcast",
        max_total_stocks=1_000_000,
        pinned_time="2026-05-13T00:00:00+00:00",
        require_confirmation_token=HUMAN_TOKEN,
        sost_cli_bin="sost-cli-fake",
    )
    _validate_against_schema(receipt, schema)


def test_receipt_rejects_extra_fields(tmp_path, guard_mod):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    draft = _good_draft()
    dp = _write_draft(tmp_path, draft)
    receipt = guard_mod.run_broadcast_guard(
        draft_path=dp,
        out_dir=tmp_path / "out",
        mode="local-dry-run",
        max_total_stocks=1_000_000,
        pinned_time="2026-05-13T00:00:00+00:00",
        sost_cli_bin="sost-cli-fake",
    )
    receipt["sneaky"] = 1
    with pytest.raises(AssertionError, match="extra fields"):
        _validate_against_schema(receipt, schema)

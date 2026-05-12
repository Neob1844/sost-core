"""Trinity / Useful Compute payment draft — real-sign mode (v0.2)."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def draft_mod():
    return _load(
        "ucpd_realsign",
        SCRIPTS_DIR / "useful_compute_payment_draft.py",
    )


@pytest.fixture(scope="module")
def signer_mod():
    return _load(
        "ucrs",
        SCRIPTS_DIR / "useful_compute_real_signer.py",
    )


REAL_TOKEN = "I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST"

_ADDR_A = "sost1qaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
# Note: bech32 charset excludes 1/b/i/o; we use 'c' for the second
# address.
_ADDR_B = "sost1qcccccccccccccccccccccccccccccccccccccc"


def _proposal(
    *, proposal_id: str, payable_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total = sum(p["allocated_stocks"] for p in payable_items)
    return {
        "schema": "trinity-useful-compute-payment-proposal/v0.1",
        "proposal_id": proposal_id,
        "mode": "local-dry-run",
        "pinned_time": "2026-05-12T00:00:00+00:00",
        "source_budget_id": "bud-" + "1" * 16,
        "total_payable_stocks": total,
        "total_deferred_stocks": 0,
        "total_unresolved_stocks": 0,
        "payable_items": payable_items,
        "unresolved_items": [],
        "deferred_items": [],
        "rejected_items": [],
        "capsule_summary": {
            "template": "useful_compute_reward_batch_v1",
            "text": "Trinity Useful Compute reward proposal "
                    "prop-test; payable=N stocks; budget=bud-test",
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


def _write_proposal(tmp_path: Path, prop: Dict[str, Any]) -> Path:
    p = tmp_path / "prop.json"
    p.write_text(
        json.dumps(prop, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return p


def _write_wallet(tmp_path: Path) -> Path:
    """Create a non-empty placeholder wallet file so the existence
    check passes. Real-signing tests mock subprocess so no real
    wallet parsing ever happens."""
    w = tmp_path / "wallet.json"
    w.write_text(
        '{"placeholder": "wallet-test-file-not-real"}',
        encoding="utf-8",
    )
    return w


def _payable_item(
    *, request_id: str, payout_address: str, allocated_stocks: int,
    worker_id: str = "c" * 16,
) -> Dict[str, Any]:
    return {
        "request_id": request_id,
        "worker_result_ids": [worker_id],
        "payout_address": payout_address,
        "allocated_stocks": allocated_stocks,
        "allocated_sost": allocated_stocks / 100_000_000,
        "source_budget_id": "bud-" + "1" * 16,
        "source_governance_batch_id": "gov-" + "2" * 16,
        "reason": "test",
    }


# ---------------------------------------------------------------------------
# Fake sost-cli helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeCompleted:
    returncode: int
    stdout: str
    stderr: str = ""


def _fake_createtx_stdout(
    *, raw_hex: str, txid: str, fee_stocks: int = 250,
    size_bytes: int = 250, fee_rate: int = 1,
    inputs: int = 1, outputs: int = 2,
) -> str:
    return "\n".join([
        "Chain height: 8400",
        "Synced 3 UTXOs from node for sost1qx...",
        "Transaction created successfully.",
        f"  Inputs:  {inputs}",
        f"  Outputs: {outputs}",
        f"  Size:    {size_bytes} bytes",
        f"  Fee:     0.00000250 SOST ({fee_stocks} stocks = "
        f"{size_bytes} bytes x {fee_rate} rate)",
        f"  Raw hex: {raw_hex}",
        f"  Txid:    {txid}",
        "",
    ])


def _install_fake_subprocess_run(monkeypatch, signer_mod, responses):
    """Install a monkeypatch on the real_signer module that returns
    canned subprocess responses. `responses` is a list of tuples
    (returncode, stdout, stderr); they are consumed in order."""
    queue = list(responses)
    captured_argvs: List[List[str]] = []

    def fake_run(argv, **kwargs):
        captured_argvs.append(list(argv))
        if not queue:
            raise RuntimeError("fake subprocess ran out of responses")
        rc, out, err = queue.pop(0)
        return _FakeCompleted(returncode=rc, stdout=out, stderr=err)

    monkeypatch.setattr(signer_mod.subprocess, "run", fake_run)
    return captured_argvs


# ---------------------------------------------------------------------------
# --real-sign gate tests
# ---------------------------------------------------------------------------


def test_real_sign_without_token_rejected(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            _payable_item(
                request_id="uc-" + "1" * 16,
                payout_address=_ADDR_A,
                allocated_stocks=1000,
            ),
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = _write_wallet(tmp_path)
    _install_fake_subprocess_run(monkeypatch, signer_mod, [])
    with pytest.raises(ValueError, match="confirmation token"):
        draft_mod.run_real_sign_drafts(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            wallet_path=wallet,
            from_label="test-payer",
            max_total_stocks=1_000_000,
            require_confirmation_token="wrong-token",
            sost_cli_bin="sost-cli-fake",
        )


def test_real_sign_without_wallet_rejected(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            _payable_item(
                request_id="uc-" + "1" * 16,
                payout_address=_ADDR_A,
                allocated_stocks=1000,
            ),
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    _install_fake_subprocess_run(monkeypatch, signer_mod, [])
    with pytest.raises(ValueError, match="--wallet"):
        draft_mod.run_real_sign_drafts(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            wallet_path=None,
            from_label="test-payer",
            max_total_stocks=1_000_000,
            require_confirmation_token=REAL_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )


def test_real_sign_without_from_rejected(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            _payable_item(
                request_id="uc-" + "1" * 16,
                payout_address=_ADDR_A,
                allocated_stocks=1000,
            ),
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = _write_wallet(tmp_path)
    _install_fake_subprocess_run(monkeypatch, signer_mod, [])
    with pytest.raises(ValueError, match="--from-label|--from-address"):
        draft_mod.run_real_sign_drafts(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            wallet_path=wallet,
            from_label=None, from_address=None,
            max_total_stocks=1_000_000,
            require_confirmation_token=REAL_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )


def test_real_sign_without_max_total_rejected(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            _payable_item(
                request_id="uc-" + "1" * 16,
                payout_address=_ADDR_A,
                allocated_stocks=1000,
            ),
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = _write_wallet(tmp_path)
    _install_fake_subprocess_run(monkeypatch, signer_mod, [])
    with pytest.raises(ValueError, match="max-total-stocks"):
        draft_mod.run_real_sign_drafts(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            wallet_path=wallet,
            from_label="test-payer",
            max_total_stocks=None,
            require_confirmation_token=REAL_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )


def test_real_sign_oversize_proposal_refused(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    """If total payment > cap, refuse to invoke the wallet at all."""
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            _payable_item(
                request_id="uc-" + "1" * 16,
                payout_address=_ADDR_A,
                allocated_stocks=2_000_000,
            ),
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = _write_wallet(tmp_path)
    captured = _install_fake_subprocess_run(
        monkeypatch, signer_mod, [],
    )
    with pytest.raises(ValueError, match="max-total-stocks"):
        draft_mod.run_real_sign_drafts(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            wallet_path=wallet,
            from_label="test-payer",
            max_total_stocks=1_000_000,
            require_confirmation_token=REAL_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )
    # No subprocess invocation should have happened.
    assert captured == []


def test_real_sign_empty_proposal_refused(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = _write_wallet(tmp_path)
    captured = _install_fake_subprocess_run(
        monkeypatch, signer_mod, [],
    )
    with pytest.raises(ValueError, match="no eligible outputs"):
        draft_mod.run_real_sign_drafts(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            wallet_path=wallet,
            from_label="test-payer",
            max_total_stocks=1_000_000,
            require_confirmation_token=REAL_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )
    assert captured == []


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_real_sign_single_output_produces_one_draft(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            _payable_item(
                request_id="uc-" + "1" * 16,
                payout_address=_ADDR_A,
                allocated_stocks=10_000,
            ),
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = _write_wallet(tmp_path)
    txid = "a" * 64
    raw_hex = "deadbeef" * 8
    captured = _install_fake_subprocess_run(
        monkeypatch, signer_mod,
        [(0, _fake_createtx_stdout(
            raw_hex=raw_hex, txid=txid,
            fee_stocks=250, size_bytes=250,
            fee_rate=1, inputs=1, outputs=2,
        ), "")],
    )

    drafts = draft_mod.run_real_sign_drafts(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        wallet_path=wallet,
        from_label="test-payer",
        max_total_stocks=1_000_000,
        require_confirmation_token=REAL_TOKEN,
        sost_cli_bin="sost-cli-fake",
    )
    assert len(drafts) == 1
    d = drafts[0]
    assert d["signing_mode"] == "real_sign_local"
    assert d["real_signed"] is True
    assert d["dry_signed"] is False
    assert d["unsigned_only"] is False
    assert d["signed_tx_hex"] == raw_hex
    assert d["signed_tx_hex"] != \
        "DRYSIGN_PLACEHOLDER_NO_REAL_SIGNING_IN_V01"
    assert d["txid_if_signed"] == txid
    assert d["total_payment_stocks"] == 10_000
    assert d["total_fee_stocks_estimated"] == 250
    assert d["fee_rate_stocks_per_byte"] == 1
    assert d["wallet_fingerprint_hash"] is not None
    assert d["signer_label_or_address_hash"] is not None
    assert d["safety_status"]["wallet_access_used"] is True
    assert d["safety_status"]["automatic_payout"] is False
    assert d["safety_status"]["no_broadcast"] is True
    assert any("SIGNED BUT NOT BROADCAST" in w for w in d["warnings"])

    # One subprocess call.
    assert len(captured) == 1
    argv = captured[0]
    assert argv[0] == "sost-cli-fake"
    assert "--wallet" in argv
    assert "createtx" in argv
    for forbidden in (
        "--broadcast", "--send", "--payout-now", "--auto-pay",
        "--sendrawtransaction", "--export-private-key",
    ):
        assert forbidden not in argv


def test_real_sign_multi_output_produces_n_drafts(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            _payable_item(
                request_id="uc-" + "1" * 16,
                payout_address=_ADDR_A,
                allocated_stocks=5_000,
                worker_id="c" * 16,
            ),
            _payable_item(
                request_id="uc-" + "2" * 16,
                payout_address=_ADDR_B,
                allocated_stocks=7_000,
                worker_id="d" * 16,
            ),
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = _write_wallet(tmp_path)
    captured = _install_fake_subprocess_run(
        monkeypatch, signer_mod,
        [
            (0, _fake_createtx_stdout(
                raw_hex="aa" * 32, txid="a" * 64,
            ), ""),
            (0, _fake_createtx_stdout(
                raw_hex="bb" * 32, txid="b" * 64,
            ), ""),
        ],
    )

    drafts = draft_mod.run_real_sign_drafts(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        wallet_path=wallet,
        from_label="test-payer",
        max_total_stocks=1_000_000,
        require_confirmation_token=REAL_TOKEN,
        sost_cli_bin="sost-cli-fake",
    )
    assert len(drafts) == 2
    # Order is sorted by (request_id, payout_address).
    assert drafts[0]["outputs"][0]["request_id"] == "uc-" + "1" * 16
    assert drafts[1]["outputs"][0]["request_id"] == "uc-" + "2" * 16
    assert drafts[0]["signed_tx_hex"] == "aa" * 32
    assert drafts[1]["signed_tx_hex"] == "bb" * 32
    assert drafts[0]["draft_id"] != drafts[1]["draft_id"]
    assert len(captured) == 2


def test_real_sign_subprocess_failure_propagates(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            _payable_item(
                request_id="uc-" + "1" * 16,
                payout_address=_ADDR_A,
                allocated_stocks=10_000,
            ),
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = _write_wallet(tmp_path)
    _install_fake_subprocess_run(
        monkeypatch, signer_mod,
        [(1, "", "Error: insufficient funds")],
    )
    with pytest.raises(ValueError, match="real signing failed"):
        draft_mod.run_real_sign_drafts(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            wallet_path=wallet,
            from_label="test-payer",
            max_total_stocks=1_000_000,
            require_confirmation_token=REAL_TOKEN,
            sost_cli_bin="sost-cli-fake",
        )


# ---------------------------------------------------------------------------
# CLI surface for --real-sign
# ---------------------------------------------------------------------------


def test_cli_real_sign_rejects_broadcast(tmp_path, draft_mod):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--real-sign",
        "--require-confirmation-token", REAL_TOKEN,
        "--broadcast",
    ])
    assert rc == 2


def test_cli_real_sign_rejects_sendrawtransaction(tmp_path, draft_mod):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--real-sign",
        "--require-confirmation-token", REAL_TOKEN,
        "--sendrawtransaction",
    ])
    assert rc == 2


def test_cli_real_sign_mutually_exclusive_with_unsigned_only(
    tmp_path, draft_mod,
):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--real-sign",
        "--unsigned-only",
        "--require-confirmation-token", REAL_TOKEN,
    ])
    assert rc == 2


def test_cli_real_sign_mutually_exclusive_with_dry_sign(
    tmp_path, draft_mod,
):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--real-sign",
        "--dry-sign",
        "--require-confirmation-token", REAL_TOKEN,
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# Real signer module — unit tests
# ---------------------------------------------------------------------------


def test_signer_argv_safety_rejects_send_subcommand(signer_mod):
    with pytest.raises(signer_mod.RealSignerError, match="allowlist"):
        signer_mod._scan_argv_safety(
            ["sost-cli", "--wallet", "/tmp/w.json", "send",
             "sost1...", "1.0"],
        )


def test_signer_argv_safety_rejects_forbidden_token(signer_mod):
    with pytest.raises(signer_mod.RealSignerError, match="forbidden token"):
        signer_mod._scan_argv_safety(
            ["sost-cli", "--wallet", "/tmp/w.json", "createtx",
             "sost1...", "1.0", "--broadcast"],
        )


def test_signer_hash_wallet_file_is_sha16(signer_mod, tmp_path):
    w = tmp_path / "w.json"
    w.write_bytes(b"hello world wallet contents")
    h = signer_mod.hash_wallet_file(w)
    assert isinstance(h, str)
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_signer_hash_signer_identity_label(signer_mod):
    h = signer_mod.hash_signer_identity(label="payer-1", address=None)
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_signer_hash_signer_identity_requires_one(signer_mod):
    with pytest.raises(signer_mod.RealSignerError):
        signer_mod.hash_signer_identity(label=None, address=None)


def test_signer_parses_stdout_correctly(
    signer_mod, monkeypatch, tmp_path,
):
    w = tmp_path / "w.json"
    w.write_text("{}", encoding="utf-8")
    stdout = "\n".join([
        "Chain height: 1000",
        "Synced 2 UTXOs from node for sost1q...",
        "Transaction created successfully.",
        "  Inputs:  2",
        "  Outputs: 2",
        "  Size:    300 bytes",
        "  Fee:     0.00000300 SOST (300 stocks = 300 bytes x 1 rate)",
        "  Raw hex: " + ("ab" * 16),
        "  Txid:    " + ("9" * 64),
        "",
    ])

    def fake_run(argv, **kwargs):
        return _FakeCompleted(
            returncode=0, stdout=stdout, stderr="",
        )

    monkeypatch.setattr(signer_mod.subprocess, "run", fake_run)
    res = signer_mod.call_sost_cli_createtx(
        wallet_path=w,
        to_address="sost1qaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount_sost="0.0001",
        from_label="payer",
        sost_cli_bin="sost-cli-fake",
    )
    assert res.signed_tx_hex == "ab" * 16
    assert res.txid_if_signed == "9" * 64
    assert res.fee_stocks == 300
    assert res.size_bytes == 300
    assert res.fee_rate_stocks_per_byte == 1
    assert res.inputs_count == 2
    assert res.outputs_count == 2


# ---------------------------------------------------------------------------
# Schema validation of v0.2 drafts
# ---------------------------------------------------------------------------


def test_real_signed_draft_validates_against_v02_schema(
    tmp_path, draft_mod, signer_mod, monkeypatch,
):
    """The real-sign output must validate against the v0.2 schema
    (additionalProperties: false, required fields complete)."""
    schema = json.loads(
        (REPO_ROOT / "schemas" / "trinity"
         / "useful_compute_payment_draft.schema.json")
        .read_text(encoding="utf-8")
    )
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            _payable_item(
                request_id="uc-" + "1" * 16,
                payout_address=_ADDR_A,
                allocated_stocks=10_000,
            ),
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = _write_wallet(tmp_path)
    _install_fake_subprocess_run(
        monkeypatch, signer_mod,
        [(0, _fake_createtx_stdout(
            raw_hex="cc" * 32, txid="c" * 64,
        ), "")],
    )
    drafts = draft_mod.run_real_sign_drafts(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        wallet_path=wallet,
        from_label="test-payer",
        max_total_stocks=1_000_000,
        require_confirmation_token=REAL_TOKEN,
        sost_cli_bin="sost-cli-fake",
    )
    d = drafts[0]

    # Strict additionalProperties + required check.
    required = set(schema["required"])
    assert required.issubset(set(d.keys())), (
        f"missing required: {required - set(d.keys())}"
    )
    allowed = set(schema["properties"].keys())
    extra = set(d.keys()) - allowed
    assert not extra, f"extra fields: {extra}"

    # Schema const flags.
    ss = d["safety_status"]
    assert ss["no_broadcast"] is True
    assert ss["human_review_required"] is True
    assert ss["private_keys_exported"] is False
    assert ss["requires_separate_broadcast"] is True
    assert ss["automatic_payout"] is False

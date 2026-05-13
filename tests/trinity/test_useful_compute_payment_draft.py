"""Trinity / Useful Compute payment draft v0.1 — invariants."""

from __future__ import annotations

import copy
import hashlib
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
def draft_mod():
    return _load(
        "ucpd", SCRIPTS_DIR / "useful_compute_payment_draft.py",
    )


UNSIGNED_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST"
DRY_SIGN_TOKEN = "I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST"


_ADDR_A = "sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_ADDR_C = "sost1cccccccccccccccccccccccccccccccccccccccc"
_ADDR_D = "sost1dddddddddddddddddddddddddddddddddddddddd"


def _proposal(*, proposal_id, payable_items, capsule=None):
    """Build a synthetic Sprint 5.15 payment proposal."""
    cap = capsule or {
        "template": "useful_compute_reward_batch_v1",
        "text": "Trinity Useful Compute reward proposal "
                "prop-test; payable=N stocks; budget=bud-test",
        "referenced_files": {
            "budget_id": "bud-" + "1" * 16,
            "governance_batch_ids": ["gov-" + "2" * 16],
            "validation_ids": [],
        },
    }
    total_payable = sum(p["allocated_stocks"] for p in payable_items)
    return {
        "schema": "trinity-useful-compute-payment-proposal/v0.1",
        "proposal_id": proposal_id,
        "mode": "local-dry-run",
        "pinned_time": "2026-05-12T00:00:00+00:00",
        "source_budget_id": "bud-" + "1" * 16,
        "total_payable_stocks": total_payable,
        "total_deferred_stocks": 0,
        "total_unresolved_stocks": 0,
        "payable_items": payable_items,
        "unresolved_items": [],
        "deferred_items": [],
        "rejected_items": [],
        "capsule_summary": cap,
        "safety_status": {
            "no_private_keys": True, "no_wallet_access": True,
            "no_signature": True, "no_broadcast": True,
            "proposal_only": True,
            "requires_manual_signing": True,
            "requires_separate_broadcast": True,
        },
    }


def _write_proposal(tmp_path: Path, proposal: dict) -> Path:
    p = tmp_path / "prop.json"
    p.write_text(
        json.dumps(proposal, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_proposal_to_unsigned_draft(tmp_path, draft_mod):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {
                "request_id": "uc-" + "1" * 16,
                "worker_result_ids": ["c" * 16],
                "payout_address": _ADDR_A,
                "allocated_stocks": 31500,
                "allocated_sost": 0.000315,
                "source_budget_id": "bud-" + "1" * 16,
                "source_governance_batch_id": "gov-" + "2" * 16,
                "reason": "test",
            },
            {
                "request_id": "uc-" + "1" * 16,
                "worker_result_ids": ["d" * 16],
                "payout_address": _ADDR_C,
                "allocated_stocks": 31500,
                "allocated_sost": 0.000315,
                "source_budget_id": "bud-" + "1" * 16,
                "source_governance_batch_id": "gov-" + "2" * 16,
                "reason": "test",
            },
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    assert draft["unsigned_only"] is True
    assert draft["dry_signed"] is False
    assert draft["total_outputs"] == 2
    assert draft["total_payment_stocks"] == 63000
    assert draft["safety_status"]["no_broadcast"] is True
    assert draft["safety_status"]["wallet_access_used"] is False
    assert draft["signed_tx_hex"] is None
    assert draft["unsigned_tx_hex"] is None


def test_total_payment_stocks_matches_payable_items(
    tmp_path, draft_mod,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 12345,
             "allocated_sost": 0.000123,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "x"},
            {"request_id": "uc-" + "2" * 16,
             "worker_result_ids": ["d" * 16],
             "payout_address": _ADDR_C,
             "allocated_stocks": 87655,
             "allocated_sost": 0.000877,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "y"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    assert draft["total_payment_stocks"] == 12345 + 87655 == 100000


def test_outputs_match_payable_items_exactly(tmp_path, draft_mod):
    payable = [
        {"request_id": "uc-" + "1" * 16,
         "worker_result_ids": ["c" * 16],
         "payout_address": _ADDR_A,
         "allocated_stocks": 50000,
         "allocated_sost": 0.0005,
         "source_budget_id": "bud-" + "1" * 16,
         "source_governance_batch_id": "gov-" + "2" * 16,
         "reason": "primary share for c"},
    ]
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=payable,
    )
    pp = _write_proposal(tmp_path, prop)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    assert len(draft["outputs"]) == 1
    o = draft["outputs"][0]
    assert o["payout_address"] == _ADDR_A
    assert o["amount_stocks"] == 50000
    assert abs(o["amount_sost"] - 0.0005) < 1e-9
    assert o["request_id"] == "uc-" + "1" * 16
    assert o["worker_result_ids"] == ["c" * 16]


def test_empty_payable_items_yields_empty_draft_with_warning(
    tmp_path, draft_mod,
):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[],
    )
    pp = _write_proposal(tmp_path, prop)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    assert draft["total_outputs"] == 0
    assert draft["total_payment_stocks"] == 0
    assert any("no eligible outputs" in w
               for w in draft["warnings"])


def test_dust_outputs_skipped_and_warned(tmp_path, draft_mod):
    # 100 stocks is way below the 546 dust threshold.
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 100,
             "allocated_sost": 0.000001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "tiny"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    assert draft["total_outputs"] == 0
    assert any("dust" in w.lower() for w in draft["warnings"])


def test_capsule_summary_copied_from_proposal(tmp_path, draft_mod):
    custom_capsule = {
        "template": "useful_compute_reward_batch_v1",
        "text": "Trinity Useful Compute reward proposal "
                "prop-test; payable=1000 stocks; budget=bud-test",
        "referenced_files": {
            "budget_id": "bud-" + "9" * 16,
            "governance_batch_ids": ["gov-" + "f" * 16],
            "validation_ids": ["val-" + "0" * 16],
        },
    }
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 1000,
             "allocated_sost": 0.00001,
             "source_budget_id": "bud-" + "9" * 16,
             "source_governance_batch_id": "gov-" + "f" * 16,
             "reason": "x"},
        ],
        capsule=custom_capsule,
    )
    pp = _write_proposal(tmp_path, prop)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    assert draft["capsule_summary"] == custom_capsule


# ---------------------------------------------------------------------------
# Max total stocks cap
# ---------------------------------------------------------------------------


def test_max_total_stocks_blocks_oversize_draft(tmp_path, draft_mod):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 100000,
             "allocated_sost": 0.001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "big"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    with pytest.raises(ValueError, match="max_total_stocks|max-total-stocks"):
        draft_mod.run_payment_draft(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            unsigned_only=True,
            require_confirmation_token=UNSIGNED_TOKEN,
            max_total_stocks=50000,
        )


# ---------------------------------------------------------------------------
# Unsigned-only / dry-sign gates
# ---------------------------------------------------------------------------


def test_unsigned_only_does_not_require_wallet(tmp_path, draft_mod):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 1000,
             "allocated_sost": 0.00001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "x"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    assert draft["safety_status"]["wallet_access_used"] is False
    assert draft["safety_status"]["dry_sign_only"] is False


def test_dry_sign_without_token_rejected(tmp_path, draft_mod):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 1000,
             "allocated_sost": 0.00001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "x"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = tmp_path / "w.json"
    wallet.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="confirmation token"):
        draft_mod.run_payment_draft(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            unsigned_only=False, dry_sign=True,
            wallet_path=wallet, from_label="test",
            require_confirmation_token="wrong-token",
        )


def test_dry_sign_without_wallet_rejected(tmp_path, draft_mod):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 1000,
             "allocated_sost": 0.00001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "x"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    with pytest.raises(ValueError, match="--wallet"):
        draft_mod.run_payment_draft(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            unsigned_only=False, dry_sign=True,
            require_confirmation_token=DRY_SIGN_TOKEN,
        )


def test_dry_sign_writes_placeholder_signed_tx_hex(tmp_path, draft_mod):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 1000,
             "allocated_sost": 0.00001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "x"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = tmp_path / "w.json"
    wallet.write_text("{}", encoding="utf-8")
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=False, dry_sign=True,
        wallet_path=wallet, from_label="test-from",
        require_confirmation_token=DRY_SIGN_TOKEN,
    )
    assert draft["dry_signed"] is True
    assert draft["safety_status"]["wallet_access_used"] is True
    assert draft["safety_status"]["private_keys_exported"] is False
    assert draft["signed_tx_hex"] == \
        "DRYSIGN_PLACEHOLDER_NO_REAL_SIGNING_IN_V01"
    assert any("placeholder" in w.lower() for w in draft["warnings"])


def test_unsigned_only_with_wallet_rejected(tmp_path, draft_mod):
    """Unsigned-only mode must not be combined with wallet inputs."""
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 1000,
             "allocated_sost": 0.00001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "x"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    wallet = tmp_path / "w.json"
    wallet.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unsigned-only"):
        draft_mod.run_payment_draft(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            unsigned_only=True, dry_sign=False,
            wallet_path=wallet,
            require_confirmation_token=UNSIGNED_TOKEN,
        )


def test_both_modes_mutually_exclusive(tmp_path, draft_mod):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 1000,
             "allocated_sost": 0.00001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "x"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    with pytest.raises(ValueError, match="mutually exclusive"):
        draft_mod.run_payment_draft(
            proposal_path=pp,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            unsigned_only=True, dry_sign=True,
            require_confirmation_token=UNSIGNED_TOKEN,
        )


# ---------------------------------------------------------------------------
# CLI gates
# ---------------------------------------------------------------------------


def test_cli_rejects_broadcast(tmp_path, draft_mod):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--unsigned-only",
        "--require-confirmation-token", UNSIGNED_TOKEN,
        "--broadcast",
    ])
    assert rc == 2


def test_cli_rejects_send(tmp_path, draft_mod):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--unsigned-only",
        "--require-confirmation-token", UNSIGNED_TOKEN,
        "--send",
    ])
    assert rc == 2


def test_cli_rejects_payout_now(tmp_path, draft_mod):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--unsigned-only",
        "--require-confirmation-token", UNSIGNED_TOKEN,
        "--payout-now",
    ])
    assert rc == 2


def test_cli_rejects_auto_pay(tmp_path, draft_mod):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--unsigned-only",
        "--require-confirmation-token", UNSIGNED_TOKEN,
        "--auto-pay",
    ])
    assert rc == 2


def test_cli_rejects_sendrawtransaction(tmp_path, draft_mod):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--unsigned-only",
        "--require-confirmation-token", UNSIGNED_TOKEN,
        "--sendrawtransaction",
    ])
    assert rc == 2


def test_cli_rejects_export_private_key(tmp_path, draft_mod):
    rc = draft_mod.main([
        "--mode", "local-dry-run",
        "--proposal", str(tmp_path / "p.json"),
        "--out-dir", str(tmp_path),
        "--unsigned-only",
        "--require-confirmation-token", UNSIGNED_TOKEN,
        "--export-private-key",
    ])
    assert rc == 2


def test_cli_rejects_non_local_mode(tmp_path, draft_mod):
    with pytest.raises(SystemExit):
        draft_mod.main([
            "--mode", "live",
            "--proposal", str(tmp_path / "p.json"),
            "--out-dir", str(tmp_path),
            "--require-confirmation-token", UNSIGNED_TOKEN,
        ])


def test_cli_requires_confirmation_token(tmp_path, draft_mod):
    # argparse marks the flag as required.
    with pytest.raises(SystemExit):
        draft_mod.main([
            "--mode", "local-dry-run",
            "--proposal", str(tmp_path / "p.json"),
            "--out-dir", str(tmp_path),
            "--unsigned-only",
        ])


# ---------------------------------------------------------------------------
# Determinism + safety status
# ---------------------------------------------------------------------------


def test_draft_id_deterministic_across_runs(tmp_path, draft_mod):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 1000,
             "allocated_sost": 0.00001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "x"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    a = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out_a",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    b = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out_b",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    assert a["draft_id"] == b["draft_id"]
    assert draft_mod.canonical_dumps(a) == \
        draft_mod.canonical_dumps(b)


def test_safety_status_locks_const_flags(tmp_path, draft_mod):
    prop = _proposal(
        proposal_id="prop-" + "a" * 16,
        payable_items=[
            {"request_id": "uc-" + "1" * 16,
             "worker_result_ids": ["c" * 16],
             "payout_address": _ADDR_A,
             "allocated_stocks": 1000,
             "allocated_sost": 0.00001,
             "source_budget_id": "bud-" + "1" * 16,
             "source_governance_batch_id": "gov-" + "2" * 16,
             "reason": "x"},
        ],
    )
    pp = _write_proposal(tmp_path, prop)
    draft = draft_mod.run_payment_draft(
        proposal_path=pp,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        unsigned_only=True,
        require_confirmation_token=UNSIGNED_TOKEN,
    )
    ss = draft["safety_status"]
    assert ss["no_broadcast"] is True
    assert ss["human_review_required"] is True
    assert ss["private_keys_exported"] is False
    assert ss["requires_separate_broadcast"] is True


def test_wrong_proposal_schema_rejected(tmp_path, draft_mod):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"schema": "not-a-proposal/v0",
                    "proposal_id": "x"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema"):
        draft_mod.run_payment_draft(
            proposal_path=bad,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            unsigned_only=True,
            require_confirmation_token=UNSIGNED_TOKEN,
        )

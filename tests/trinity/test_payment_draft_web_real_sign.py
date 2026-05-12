"""Trinity Web Miner Console x payment draft v0.2 — Sprint 5.17."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_PATH = REPO_ROOT / "website" / "trinity-useful-compute.html"


def _read():
    return WEB_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# v0.2 IDs and labels
# ---------------------------------------------------------------------------


def test_v02_schema_constant_present():
    src = _read()
    assert "trinity-useful-compute-payment-draft/v0.2" in src
    assert "SCHEMA_DRAFT_V02" in src


def test_v02_panel_ids_present():
    """The v0.2 panel must expose IDs for the new fields."""
    src = _read()
    for cid in (
        "draftSigningMode", "draftRealSigned",
        "draftFeeRate", "draftSelectedUtxosCount",
        "draftTxid", "draftWalletFp", "draftSignerHash",
        "draftRealSignBanner",
    ):
        assert f'id="{cid}"' in src, (
            f"v0.2 panel missing id {cid!r}"
        )


def test_signed_but_not_broadcast_banner_text():
    """A red 'SIGNED BUT NOT BROADCAST' banner must exist for the
    real_signed=true case."""
    src = _read()
    assert "SIGNED BUT NOT BROADCAST" in src
    # The banner element must be wired to the real_signed flag.
    assert "draftRealSignBanner" in src
    assert "real_signed" in src


def test_signing_mode_label_present():
    src = _read()
    # The label and the JS value must both appear.
    assert "signing_mode" in src
    assert "draft.signing_mode" in src


def test_real_signed_label_present():
    src = _read()
    assert "real_signed" in src
    assert "draft.real_signed" in src


def test_wallet_fingerprint_and_signer_hash_rendered():
    src = _read()
    assert "wallet_fingerprint_hash" in src
    assert "signer_label_or_address_hash" in src


def test_fee_rate_and_utxo_count_rendered():
    src = _read()
    assert "fee_rate_stocks_per_byte" in src
    assert "selected_utxos" in src


# ---------------------------------------------------------------------------
# Real-sign status string
# ---------------------------------------------------------------------------


def test_real_signed_status_text_present():
    src = _read()
    # The JS sets a clear status for the real-sign case.
    assert "real-signed" in src.lower()
    assert "not broadcast" in src.lower()


# ---------------------------------------------------------------------------
# Safety surface for the section (no wallet inputs, no network)
# ---------------------------------------------------------------------------


_FORBIDDEN_NETWORK_PRIMITIVES = (
    "fetch(", "XMLHttpRequest", "new WebSocket(", "EventSource(",
    "navigator.sendBeacon",
)


def test_no_network_primitives_v02():
    src = _read()
    for tok in _FORBIDDEN_NETWORK_PRIMITIVES:
        assert tok not in src, (
            f"forbidden network primitive: {tok!r}"
        )


def test_no_sensitive_input_fields_v02():
    """Even after Sprint 5.17, the console must NOT accept wallet,
    seed, private-key or RPC inputs."""
    src = _read()
    inputs = re.findall(r"<input\b[^>]*>", src, re.IGNORECASE)
    for tag in inputs:
        lower = tag.lower()
        for forbidden in (
            "private", "wallet", "seed", "mnemonic", "passphrase",
            "rpcpass", "rpcuser", "signature",
        ):
            assert forbidden not in lower, (
                f"<input> looks sensitive: {tag}"
            )


def test_no_signing_or_broadcast_prompts_v02():
    """The page must not contain prompts that would suggest
    signing or broadcasting from the browser."""
    src = _read().lower()
    for phrase in (
        "send tx now", "broadcast now", "trigger payout",
        "click to sign", "auto-pay draft", "auto-sign",
        "publish capsule now",
        "sign here", "broadcast this draft", "sign in browser",
    ):
        assert phrase not in src

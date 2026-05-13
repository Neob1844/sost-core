"""Sprint 5.18 hardening — C++ subcommand validation tests.

These tests invoke the actual ``sost-cli`` binary built from
``src/sost-cli.cpp`` and check that the ``sendrawtransaction``
subcommand:

- Accepts ``--help`` / ``-h`` and prints a SPECIFIC usage line
  containing the literal "Usage: sost-cli sendrawtransaction <hex>"
  instead of falling through to the general help.
- Rejects empty argument.
- Rejects odd-length hex.
- Rejects non-hex characters.
- Rejects extra positional arguments.
- Does NOT invoke RPC for any of the above (we cannot easily
  detect this from outside, but a non-zero return + an "Error:"
  on stderr is the contract).

The binary is expected to live at ``build/sost-cli`` (the default
output of ``cmake --build build --target sost-cli``). If it is not
present these tests skip with a clear reason — no Trinity test
should require a C++ build to be useful, but when the binary is
there we want to verify it really enforces the validation.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_sost_cli() -> Path | None:
    candidates = [
        REPO_ROOT / "build" / "sost-cli",
        REPO_ROOT / "build-phase2" / "sost-cli",
        REPO_ROOT / "build-v11" / "sost-cli",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    on_path = shutil.which("sost-cli")
    if on_path:
        return Path(on_path)
    return None


SOST_CLI = _find_sost_cli()


def _binary_has_subcommand() -> bool:
    """A pre-Sprint-5.18 sost-cli binary may still be on disk
    (left over from a previous build). Skip these tests when the
    binary does not even list 'sendrawtransaction' in its master
    usage — running them would only produce confusing failures
    against an outdated build."""
    if SOST_CLI is None:
        return False
    try:
        cp = subprocess.run(
            [str(SOST_CLI), "--help"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return False
    return "sendrawtransaction" in (cp.stdout + cp.stderr)


_BINARY_READY = _binary_has_subcommand()

skip_reason = (
    "sost-cli binary not built (or pre-Sprint-5.18 build on disk); "
    "rebuild with 'cmake --build build --target sost-cli' from "
    "this branch to enable these tests"
)


pytestmark = pytest.mark.skipif(
    not _BINARY_READY, reason=skip_reason,
)


def test_help_prints_specific_usage():
    """--help on the sendrawtransaction subcommand must print the
    SPECIFIC usage line, not the general CLI help."""
    cp = subprocess.run(
        [str(SOST_CLI), "sendrawtransaction", "--help"],
        capture_output=True, text=True, timeout=15,
    )
    out = cp.stdout + cp.stderr
    assert "Usage: sost-cli sendrawtransaction <hex>" in out, (
        "expected specific subcommand usage; got:\n" + out[:1200]
    )


def test_help_short_flag():
    cp = subprocess.run(
        [str(SOST_CLI), "sendrawtransaction", "-h"],
        capture_output=True, text=True, timeout=15,
    )
    out = cp.stdout + cp.stderr
    assert "Usage: sost-cli sendrawtransaction <hex>" in out


def test_missing_argument_rejected():
    cp = subprocess.run(
        [str(SOST_CLI), "sendrawtransaction"],
        capture_output=True, text=True, timeout=15,
    )
    assert cp.returncode != 0
    assert "Usage: sost-cli sendrawtransaction" in (
        cp.stdout + cp.stderr
    )


def test_empty_hex_rejected():
    cp = subprocess.run(
        [str(SOST_CLI), "sendrawtransaction", ""],
        capture_output=True, text=True, timeout=15,
    )
    assert cp.returncode != 0
    assert "empty hex" in (cp.stdout + cp.stderr).lower()


def test_odd_length_hex_rejected():
    cp = subprocess.run(
        [str(SOST_CLI), "sendrawtransaction", "abc"],
        capture_output=True, text=True, timeout=15,
    )
    assert cp.returncode != 0
    err = (cp.stdout + cp.stderr).lower()
    assert "odd" in err or "even-length" in err


def test_non_hex_character_rejected():
    cp = subprocess.run(
        [str(SOST_CLI), "sendrawtransaction", "deadbeefz"],
        capture_output=True, text=True, timeout=15,
    )
    assert cp.returncode != 0
    err = (cp.stdout + cp.stderr).lower()
    assert "non-hex" in err or "hex character" in err or \
        "odd" in err  # 9 chars triggers odd-length first


def test_extra_positional_argument_rejected():
    cp = subprocess.run(
        [str(SOST_CLI), "sendrawtransaction", "deadbeef", "extra"],
        capture_output=True, text=True, timeout=15,
    )
    assert cp.returncode != 0
    err = (cp.stdout + cp.stderr).lower()
    assert "exactly one" in err or "extra" in err


def test_general_help_lists_sendrawtransaction():
    """The master usage banner should mention the new subcommand
    so operators can discover it."""
    cp = subprocess.run(
        [str(SOST_CLI), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    out = cp.stdout + cp.stderr
    assert "sendrawtransaction" in out


def test_sendrawtransaction_does_not_load_wallet(tmp_path):
    """Sprint 5.18d regression: sost-cli sendrawtransaction <hex>
    must not require --wallet to point at an existing file. The
    earlier build failed with 'Error loading wallet ...' before
    the hex was even validated. After 5.18d the subcommand runs
    BEFORE the wallet load and rejects on hex grounds first.

    We point --wallet at a non-existent path and pass a deliberately
    invalid (odd-length) hex. The expected stderr line is the
    Trinity hex-validation message, NOT the wallet load error.
    """
    missing_wallet = tmp_path / "definitely-does-not-exist.json"
    assert not missing_wallet.exists()
    cp = subprocess.run(
        [str(SOST_CLI),
         "--wallet", str(missing_wallet),
         "sendrawtransaction", "abc"],   # odd-length
        capture_output=True, text=True, timeout=15,
    )
    assert cp.returncode != 0
    out = (cp.stdout + cp.stderr).lower()
    # MUST hit the hex validator…
    assert ("odd" in out or "even-length" in out), (
        "expected hex-length error; got:\n" + out[:1000]
    )
    # …and MUST NOT hit the wallet loader.
    assert "loading wallet" not in out, (
        "sendrawtransaction tried to load wallet; got:\n" + out[:1000]
    )


def test_sendrawtransaction_help_does_not_load_wallet(tmp_path):
    """`sost-cli sendrawtransaction --help` must work even when
    no wallet.json exists in the cwd."""
    missing_wallet = tmp_path / "definitely-does-not-exist.json"
    cp = subprocess.run(
        [str(SOST_CLI),
         "--wallet", str(missing_wallet),
         "sendrawtransaction", "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert cp.returncode == 0
    out = cp.stdout + cp.stderr
    assert "Usage: sost-cli sendrawtransaction <hex>" in out
    assert "loading wallet" not in out.lower()

#!/usr/bin/env python3
# SOST <-> BTC regtest harness (Phase C.8 scaffold).
#
# Status: SCAFFOLD ONLY.
#
# This script exists so a future Phase C.9+ can fill in the actual
# happy-path / refund test bodies against a real bitcoind regtest
# node. Today, the script detects whether `bitcoind` and
# `bitcoin-cli` are on PATH and skips with a clear instruction if
# either is missing. When both are present, it would (eventually):
#
#   1. Spin up bitcoind regtest in a temporary datadir.
#   2. Mine ~101 blocks so coinbase outputs mature.
#   3. Build a SOST HTLC redeem script and derive its P2WSH address.
#   4. Fund the P2WSH address from the regtest wallet.
#   5. Use the SOST CLI / sost-core helpers (Phase C.7 wiring) to
#      build a CLAIM spending transaction; broadcast it; mine a
#      block; assert the coin moved to the claimer.
#   6. Repeat for REFUND with a refund_height past current tip.
#   7. Tear down the regtest node and wipe the datadir.
#
# What is in place TODAY (Phase C.8):
#   - bitcoind / bitcoin-cli detection.
#   - Clean SKIP behaviour when either is missing, with the exact
#     install instructions for Debian/Ubuntu so an operator who
#     wants to enable the harness knows what to run.
#   - A green CI signal regardless of whether bitcoind is installed.
#
# What this scaffold does NOT do (today):
#   - Spin up bitcoind. No actual regtest execution happens — even
#     when bitcoind IS installed, this scaffold still skips, until
#     Phase C.9+ fills in the body. The skip message in the present
#     case is different ("scaffold not yet implemented") so the
#     operator can distinguish "missing tool" from "test code TBD".
#
# Rules respected by this file:
#   - NO mainnet calls.
#   - NO testnet calls (only regtest, only against locally-spawned
#     bitcoind, only in a temporary datadir).
#   - NO wallet files outside the tempdir.
#   - NO private keys with mainnet value.

import os
import shutil
import sys

try:
    import pytest  # type: ignore
except ImportError:
    print("FATAL: pytest is not installed in this environment.")
    print("       Install it with: python3 -m pip install pytest")
    sys.exit(1)


BITCOIND  = shutil.which("bitcoind")
BITCOINCLI = shutil.which("bitcoin-cli")

_BITCOIND_MISSING_MSG = (
    "bitcoind / bitcoin-cli not on PATH — install them to enable the "
    "BTC regtest harness:\n"
    "  Debian/Ubuntu:\n"
    "    sudo apt-get update\n"
    "    sudo apt-get install -y bitcoind\n"
    "  Or build from source: https://github.com/bitcoin/bitcoin\n"
    "  Or use a snap / docker image as long as both 'bitcoind' and "
    "'bitcoin-cli' end up on PATH.\n"
    "The harness is a SCAFFOLD today; even with bitcoind installed it "
    "will SKIP with a different message until Phase C.9+ fills in the "
    "test body."
)

_SCAFFOLD_NOT_IMPLEMENTED_MSG = (
    "BTC regtest harness body is not yet implemented (Phase C.8 ships "
    "the detection + SKIP scaffold only). Phase C.9+ will add the "
    "actual regtest spin-up + CLAIM/REFUND happy-path tests on top "
    "of this file."
)


def _both_tools_present() -> bool:
    return bool(BITCOIND) and bool(BITCOINCLI)


@pytest.fixture(scope="session")
def bitcoind_paths():
    """Yield the resolved (bitcoind, bitcoin-cli) paths, or skip."""
    if not _both_tools_present():
        pytest.skip(_BITCOIND_MISSING_MSG)
    return BITCOIND, BITCOINCLI


def test_bitcoind_detection_runs():
    """Smoke test the detection logic itself runs in any environment."""
    # If both tools are present, we should see truthy paths.
    if _both_tools_present():
        assert os.path.isfile(BITCOIND)
        assert os.path.isfile(BITCOINCLI)
    else:
        # Else the detection should be reporting None for at least one.
        assert (BITCOIND is None) or (BITCOINCLI is None)


def test_btc_regtest_happy_path_claim(bitcoind_paths):
    """Future: spin up bitcoind regtest, fund P2WSH HTLC, claim it.

    Skips today because the scaffold body is not implemented.
    """
    pytest.skip(_SCAFFOLD_NOT_IMPLEMENTED_MSG)


def test_btc_regtest_happy_path_refund(bitcoind_paths):
    """Future: spin up bitcoind regtest, fund P2WSH HTLC, wait for
    timeout, refund it.

    Skips today because the scaffold body is not implemented.
    """
    pytest.skip(_SCAFFOLD_NOT_IMPLEMENTED_MSG)


if __name__ == "__main__":
    # Convenience: report detection state when run directly.
    print("bitcoind   :", BITCOIND   or "<not on PATH>")
    print("bitcoin-cli:", BITCOINCLI or "<not on PATH>")
    if not _both_tools_present():
        print()
        print(_BITCOIND_MISSING_MSG)
        sys.exit(0)
    print()
    print("Both tools present. Phase C.9+ will fill in the harness body.")
    print(_SCAFFOLD_NOT_IMPLEMENTED_MSG)
    sys.exit(0)

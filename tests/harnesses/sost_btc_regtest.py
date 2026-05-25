#!/usr/bin/env python3
# SOST <-> BTC regtest harness (Phase C.10 — executable scaffold).
#
# What this file does:
#
#   * Detects whether `bitcoind` and `bitcoin-cli` are on PATH.
#
#   * When BOTH are present, spins up a fresh bitcoind regtest node in a
#     temporary datadir, runs a small battery of executable connectivity
#     and mining smoke tests, and tears the node down + wipes the
#     datadir on every test exit (including failure paths).
#
#   * When either is missing, every test in this file SKIPs cleanly
#     with a clear install message — so the file is safe to add to
#     any CI matrix that does not have Bitcoin Core installed.
#
# What this file deliberately does NOT do:
#
#   * Touch mainnet or testnet. Only regtest, only against a
#     locally-spawned bitcoind, only in a temporary datadir under
#     /tmp.
#
#   * Persist anything. The temporary datadir is removed at fixture
#     teardown, including on test failure.
#
#   * Exercise the SOST HTLC CLAIM/REFUND flow end-to-end yet —
#     that is Phase C.11 scope. The two tests that would do it are
#     present as SKIPs with a precise TODO list, so when the SOST
#     CLI surface for `htlc-claim` / `htlc-refund` (currently gated
#     at INT64_MAX) is plumbed up for regtest, the harness lights
#     up without restructuring.

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import pytest
except ImportError:
    print("FATAL: pytest is not installed in this environment.")
    print("       Install it with: python3 -m pip install pytest")
    sys.exit(1)


BITCOIND   = shutil.which("bitcoind")
BITCOINCLI = shutil.which("bitcoin-cli")


_BITCOIND_MISSING_MSG = (
    "bitcoind / bitcoin-cli not on PATH — install them to enable the "
    "BTC regtest harness:\n"
    "  Debian/Ubuntu (when the apt repo carries it):\n"
    "    sudo apt-get update\n"
    "    sudo apt-get install -y bitcoind\n"
    "  Or build from source: https://github.com/bitcoin/bitcoin\n"
    "  Or grab a static binary tarball:\n"
    "    https://bitcoincore.org/bin/\n"
    "Make sure both 'bitcoind' AND 'bitcoin-cli' end up on PATH."
)

_HTLC_FLOW_TODO_MSG = (
    "Phase C.10 ships the regtest spin-up + connectivity + mining "
    "smoke tests, NOT the full SOST HTLC CLAIM/REFUND flow. The "
    "missing pieces for Phase C.11+:\n"
    "  - SOST CLI surface for `htlc-claim` / `htlc-refund` that is "
    "addressable from regtest (currently gated at INT64_MAX).\n"
    "  - Or a small `tools/btc_regtest_signer` binary that wraps "
    "SignBtcHtlcClaim / SignBtcHtlcRefund from src/atomic_swap_"
    "btc_signing.cpp and emits raw_tx_hex.\n"
    "  - Fund the P2WSH address derived from "
    "BuildBtcHtlcRedeemScript via `bitcoin-cli sendtoaddress`.\n"
    "  - Broadcast the SOST-signed claim/refund tx via "
    "`bitcoin-cli sendrawtransaction`.\n"
    "  - Mine through the refund_height for the REFUND path."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _both_tools_present() -> bool:
    return bool(BITCOIND) and bool(BITCOINCLI)


def _free_port() -> int:
    """Ask the kernel for a free TCP port; close immediately and return it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _cli(datadir: Path, port: int, *args: str) -> str:
    """Run bitcoin-cli against the spawned regtest node; return stdout."""
    cmd = [
        BITCOINCLI,
        f"-datadir={datadir}",
        f"-rpcport={port}",
        "-regtest",
        *args,
    ]
    res = subprocess.run(
        cmd, capture_output=True, text=True, timeout=15,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"bitcoin-cli failed: {' '.join(cmd)}\n"
            f"stdout: {res.stdout}\nstderr: {res.stderr}"
        )
    return res.stdout.strip()


def _cli_json(datadir: Path, port: int, *args: str):
    out = _cli(datadir, port, *args)
    return json.loads(out) if out else None


# ---------------------------------------------------------------------------
# Fixture: spin up bitcoind regtest in a tempdir; cleanup on teardown.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def regtest_node():
    if not _both_tools_present():
        pytest.skip(_BITCOIND_MISSING_MSG)

    tmpdir = Path(tempfile.mkdtemp(prefix="sost_btc_regtest_"))
    rpc_port = _free_port()
    p2p_port = _free_port()
    rpcuser = "sost_regtest_user"
    rpcpass = "sost_regtest_pass"

    conf = tmpdir / "bitcoin.conf"
    conf.write_text(
        "regtest=1\n"
        f"[regtest]\n"
        f"rpcuser={rpcuser}\n"
        f"rpcpassword={rpcpass}\n"
        f"rpcport={rpc_port}\n"
        f"port={p2p_port}\n"
        f"listen=0\n"
        f"server=1\n"
        f"fallbackfee=0.00001\n"
        f"dnsseed=0\n"
        f"upnp=0\n"
        f"natpmp=0\n"
        f"discover=0\n"
    )

    proc = subprocess.Popen(
        [
            BITCOIND,
            f"-datadir={tmpdir}",
            "-regtest",
            "-daemon=0",
            "-printtoconsole=0",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for bitcoind to accept RPC calls — poll up to ~20 s.
    deadline = time.time() + 20.0
    last_err = None
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            # bitcoind already exited; capture the error and bail.
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
            pytest.skip(
                f"bitcoind regtest exited early "
                f"(rc={proc.returncode}); cannot run harness"
            )
        try:
            _cli(tmpdir, rpc_port, "getblockchaininfo")
            ready = True
            break
        except Exception as e:
            last_err = e
            time.sleep(0.25)

    if not ready:
        # Clean up and skip.
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(tmpdir, ignore_errors=True)
        pytest.skip(
            f"bitcoind regtest did not become RPC-ready within 20s "
            f"(last error: {last_err})"
        )

    try:
        yield {
            "datadir": tmpdir,
            "rpc_port": rpc_port,
            "p2p_port": p2p_port,
            "rpcuser": rpcuser,
            "rpcpass": rpcpass,
            "cli":      lambda *a: _cli(tmpdir, rpc_port, *a),
            "cli_json": lambda *a: _cli_json(tmpdir, rpc_port, *a),
        }
    finally:
        # Always teardown, even on test failure.
        try:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bitcoind_detection_runs():
    """Smoke test the detection logic in any environment."""
    if _both_tools_present():
        assert os.path.isfile(BITCOIND)
        assert os.path.isfile(BITCOINCLI)
    else:
        assert (BITCOIND is None) or (BITCOINCLI is None)


def test_regtest_node_spawns_and_responds(regtest_node):
    """bitcoind regtest comes up + bitcoin-cli can hit it."""
    info = regtest_node["cli_json"]("getblockchaininfo")
    assert info["chain"] == "regtest", (
        f"expected chain=regtest, got chain={info.get('chain')}"
    )
    assert isinstance(info.get("blocks"), int)
    # Fresh regtest starts at height 0 (genesis only).
    assert info["blocks"] == 0


def test_regtest_can_mine_blocks(regtest_node):
    """generatetoaddress mines the requested number of blocks."""
    # Create a fresh wallet (regtest wallet API).
    try:
        regtest_node["cli"]("createwallet", "harness")
    except Exception:
        # Wallet may already exist if a previous test in the module
        # created it; that is fine.
        pass
    addr = regtest_node["cli"]("getnewaddress", "", "bech32")
    assert addr, "getnewaddress returned an empty string"

    # Mine 101 blocks so the first coinbase is spendable.
    regtest_node["cli"]("generatetoaddress", "101", addr)
    info = regtest_node["cli_json"]("getblockchaininfo")
    assert info["blocks"] >= 101, (
        f"expected >=101 blocks after generatetoaddress, "
        f"got {info['blocks']}"
    )


def test_regtest_wallet_has_balance(regtest_node):
    """After mining 101 blocks, the harness wallet has spendable coin."""
    try:
        regtest_node["cli"]("loadwallet", "harness")
    except Exception:
        pass
    bal = float(regtest_node["cli"]("getbalance"))
    assert bal > 0.0, f"expected balance > 0 after mining, got {bal}"


def test_regtest_can_decode_segwit_address(regtest_node):
    """validateaddress recognises a freshly-derived bech32 address."""
    try:
        regtest_node["cli"]("loadwallet", "harness")
    except Exception:
        pass
    addr = regtest_node["cli"]("getnewaddress", "", "bech32")
    v = regtest_node["cli_json"]("validateaddress", addr)
    assert v["isvalid"] is True
    # bcrt is the regtest HRP; SOST EncodeP2WSHAddress(network)
    # for the regtest profile produces addresses with the same
    # prefix.
    assert addr.startswith("bcrt1"), (
        f"expected regtest bcrt1 address, got {addr}"
    )


# ---------------------------------------------------------------------------
# Tests deliberately deferred to Phase C.11+
# ---------------------------------------------------------------------------
#
# These exist as placeholders so the future operator knows the exact
# call shape the harness will take. They SKIP cleanly today.

def test_btc_regtest_htlc_happy_path_claim(regtest_node):
    """End-to-end CLAIM on regtest. Phase C.11 scope."""
    pytest.skip(_HTLC_FLOW_TODO_MSG)


def test_btc_regtest_htlc_happy_path_refund(regtest_node):
    """End-to-end REFUND on regtest (mine past refund_height). Phase C.11 scope."""
    pytest.skip(_HTLC_FLOW_TODO_MSG)


# ---------------------------------------------------------------------------
# Direct invocation: report state + run pytest on this file.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("bitcoind   :", BITCOIND   or "<not on PATH>")
    print("bitcoin-cli:", BITCOINCLI or "<not on PATH>")
    if not _both_tools_present():
        print()
        print(_BITCOIND_MISSING_MSG)
        print()
        print("Running pytest anyway — all bitcoind-dependent tests "
              "will SKIP cleanly.")
    print()
    sys.exit(pytest.main(["-v", __file__]))

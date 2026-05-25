#!/usr/bin/env python3
# SOST <-> BTC regtest harness (Phase C.11 — funding scaffold).
#
# What this file does:
#
#   * Detects whether `bitcoind` and `bitcoin-cli` are on PATH.
#
#   * When BOTH are present, spins up a fresh bitcoind regtest node in
#     a temporary datadir with all the safety flags wired so the node
#     never touches the live network. It then:
#       - creates a temporary wallet
#       - mines through coinbase maturation
#       - builds a SOST-shaped HTLC redeem script in pure Python
#         (mirroring src/atomic_swap_btc.cpp::BuildBtcHtlcRedeemScript)
#       - converts it to a bcrt1q… P2WSH address via
#         `bitcoin-cli decodescript`
#       - funds the address from the temp wallet, locates the funding
#         outpoint, and asserts `testmempoolaccept` on a sanity-check
#         self-spend tx.
#
#   * When either tool is missing, every fixture-bound test SKIPs
#     cleanly with the install runbook pointer. The Python-only unit
#     tests (config safety, redeem-script structure) still run.
#
# What this file deliberately does NOT do:
#
#   * Touch any live network. Only regtest, only against a locally-
#     spawned bitcoind, only in a temporary datadir under /tmp.
#
#   * Persist anything. The temporary datadir is removed at fixture
#     teardown, including on test failure.
#
#   * Sign or broadcast a SOST-produced CLAIM/REFUND tx. That is
#     Phase C.12 scope — it needs either the SOST CLI `htlc-claim`
#     surface (currently gated at INT64_MAX) or a small
#     `tools/btc_regtest_signer` binary that wraps SignBtcHtlcClaim /
#     SignBtcHtlcRefund and emits raw_tx_hex. The two placeholder
#     tests for that flow remain SKIP with a precise TODO list.
#
#   * Move the SOST consensus gate. ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT
#     stays INT64_MAX regardless of what this harness does locally.

import hashlib
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
    "bitcoind / bitcoin-cli not on PATH. See "
    "docs/runbooks/BITCOIN_CORE_REGTEST_SETUP.md for the verified "
    "install procedure (download tarball + verify SHA256SUMS + verify "
    "GPG signatures + put bitcoind/bitcoin-cli on PATH). The harness "
    "deliberately does NOT auto-download Bitcoin Core."
)

_HTLC_SIGN_BROADCAST_TODO_MSG = (
    "Phase C.11 ships regtest lifecycle + wallet + funding + "
    "testmempoolaccept. It does NOT yet broadcast a SOST-signed "
    "claim/refund tx because that requires either:\n"
    "  (a) a tools/btc_regtest_signer C++ helper that links sost-core "
    "and exposes SignBtcHtlcClaim / SignBtcHtlcRefund on the command "
    "line emitting raw_tx_hex, or\n"
    "  (b) wiring the gated CLI surface (htlc-claim / htlc-refund) so "
    "it can produce raw_tx_hex without flipping the activation gate.\n"
    "Either path is Phase C.12 scope. When raw_tx_hex from SOST is "
    "available, the harness should:\n"
    "  - call bitcoin-cli testmempoolaccept '[\"<raw_tx_hex>\"]' to "
    "validate the witness against a real node before broadcast,\n"
    "  - call bitcoin-cli sendrawtransaction <raw_tx_hex>,\n"
    "  - mine a block via generatetoaddress, and\n"
    "  - assert the claim_destination / refund_destination address "
    "received the funds minus fee, with the preimage visible in the "
    "witness on chain for CLAIM."
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


def _cli(datadir: Path, port: int, *args: str, timeout: float = 15.0) -> str:
    """Run bitcoin-cli against the spawned regtest node; return stdout."""
    cmd = [
        BITCOINCLI,
        f"-datadir={datadir}",
        f"-rpcport={port}",
        "-regtest",
        *args,
    ]
    res = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
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
# bitcoind safety-flag template (used by the fixture AND by the
# bitcoind-free unit test below; do NOT inline this in two places).
# ---------------------------------------------------------------------------

def _build_bitcoind_conf(rpcuser: str, rpcpass: str,
                         rpc_port: int, p2p_port: int) -> str:
    return (
        "regtest=1\n"
        f"[regtest]\n"
        f"rpcuser={rpcuser}\n"
        f"rpcpassword={rpcpass}\n"
        f"rpcport={rpc_port}\n"
        f"port={p2p_port}\n"
        # listen=0    -> do NOT accept incoming P2P connections
        # dnsseed=0   -> do NOT contact any DNS seed
        # discover=0  -> do NOT advertise our IP to peers
        # upnp=0      -> do NOT open ports via UPnP
        # natpmp=0    -> do NOT open ports via NAT-PMP
        f"listen=0\n"
        f"server=1\n"
        f"fallbackfee=0.00001\n"
        f"dnsseed=0\n"
        f"upnp=0\n"
        f"natpmp=0\n"
        f"discover=0\n"
    )


# ---------------------------------------------------------------------------
# Pure-Python mirror of src/atomic_swap_btc.cpp::BuildBtcHtlcRedeemScript
# ---------------------------------------------------------------------------
#
# Implemented in Python (no SOST binary required) so the harness can
# construct the same redeem-script bytes that the C++ side produces
# and hand them to `bitcoin-cli decodescript` to get a canonical
# bcrt1q… P2WSH address. The Python implementation MUST stay byte-
# for-byte identical to the C++ side; the structural unit test
# `test_redeem_script_python_mirrors_cpp_layout` guards the invariants.

_OP_IF                = 0x63
_OP_ELSE              = 0x67
_OP_ENDIF             = 0x68
_OP_DROP              = 0x75
_OP_EQUALVERIFY       = 0x88
_OP_SHA256            = 0xa8
_OP_CHECKSIG          = 0xac
_OP_CHECKLOCKTIMEVERIFY = 0xb1
_OP_PUSHDATA1         = 0x4c


def _encode_pushdata(data: bytes) -> bytes:
    """Mirror of EncodePushdata in src/atomic_swap_btc.cpp."""
    n = len(data)
    if n <= 75:
        return bytes([n]) + data
    if n <= 255:
        return bytes([_OP_PUSHDATA1, n]) + data
    if n <= 65535:
        return bytes([0x4d, n & 0xff, (n >> 8) & 0xff]) + data
    # The HTLC builder never pushes more than 33 bytes; this branch
    # exists only for shape-parity with the C++ helper.
    return (bytes([0x4e,
                   n & 0xff, (n >> 8) & 0xff,
                   (n >> 16) & 0xff, (n >> 24) & 0xff])
            + data)


def _encode_script_num_minimal(value: int) -> bytes:
    """Mirror of EncodeScriptNumMinimal in src/atomic_swap_btc.cpp."""
    if value < 0:
        raise ValueError("refund_height must be non-negative")
    if value == 0:
        return b""
    out = bytearray()
    v = value
    while v:
        out.append(v & 0xff)
        v >>= 8
    # Sign-extend if the high bit is set so the value stays positive.
    if out[-1] & 0x80:
        out.append(0x00)
    return bytes(out)


def _build_htlc_redeem_script(hashlock: bytes,
                              refund_height: int,
                              claim_pubkey: bytes,
                              refund_pubkey: bytes) -> bytes:
    """Mirror of BuildBtcHtlcRedeemScript in src/atomic_swap_btc.cpp.

    OP_IF
        OP_SHA256 <hashlock> OP_EQUALVERIFY <claim_pub> OP_CHECKSIG
    OP_ELSE
        <refund_height> OP_CHECKLOCKTIMEVERIFY OP_DROP
        <refund_pub> OP_CHECKSIG
    OP_ENDIF
    """
    if len(hashlock) != 32:
        raise ValueError(f"hashlock must be 32 bytes, got {len(hashlock)}")
    if len(claim_pubkey) != 33:
        raise ValueError(
            f"claim_pubkey must be 33 bytes (compressed), got {len(claim_pubkey)}"
        )
    if len(refund_pubkey) != 33:
        raise ValueError(
            f"refund_pubkey must be 33 bytes (compressed), got {len(refund_pubkey)}"
        )
    s = bytearray()
    s.append(_OP_IF)
    s.append(_OP_SHA256)
    s += _encode_pushdata(hashlock)
    s.append(_OP_EQUALVERIFY)
    s += _encode_pushdata(claim_pubkey)
    s.append(_OP_CHECKSIG)
    s.append(_OP_ELSE)
    s += _encode_pushdata(_encode_script_num_minimal(refund_height))
    s.append(_OP_CHECKLOCKTIMEVERIFY)
    s.append(_OP_DROP)
    s += _encode_pushdata(refund_pubkey)
    s.append(_OP_CHECKSIG)
    s.append(_OP_ENDIF)
    return bytes(s)


def _p2wsh_script_pubkey(redeem_script: bytes) -> bytes:
    """OP_0 <32-byte sha256(redeem_script)> — the segwit-v0 P2WSH SPK."""
    return b"\x00\x20" + hashlib.sha256(redeem_script).digest()


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
    conf.write_text(_build_bitcoind_conf(rpcuser, rpcpass, rpc_port, p2p_port))

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
# Tests that DO NOT need bitcoind — always run.
# ---------------------------------------------------------------------------

def test_bitcoind_detection_runs():
    """Smoke test the detection logic in any environment."""
    if _both_tools_present():
        assert os.path.isfile(BITCOIND)
        assert os.path.isfile(BITCOINCLI)
    else:
        assert (BITCOIND is None) or (BITCOINCLI is None)


def test_conf_template_includes_safety_flags():
    """The bitcoind config NEVER opens a live-network surface."""
    conf = _build_bitcoind_conf("u", "p", 18443, 18444)
    # Must be regtest only.
    assert "regtest=1" in conf
    # Must NOT contain any live-network chain selector.
    for forbidden in ("chain=main", "chain=test", "chain=signet",
                      "testnet=1", "signet=1"):
        assert forbidden not in conf, (
            f"safety regression: '{forbidden}' present in bitcoind conf"
        )
    # Must explicitly disable every outbound-network knob.
    for required in ("listen=0", "dnsseed=0", "upnp=0",
                     "natpmp=0", "discover=0"):
        assert required in conf, (
            f"safety regression: '{required}' missing from bitcoind conf"
        )


def test_redeem_script_python_mirrors_cpp_layout():
    """Structural invariants of the Python redeem script builder.

    The bytes are checked against the layout documented in
    include/sost/atomic_swap_btc_signing.h and produced by
    src/atomic_swap_btc.cpp::BuildBtcHtlcRedeemScript. The C++ side is
    the source of truth; this test verifies the Python mirror stays
    aligned so the harness can hand the bytes to `bitcoin-cli
    decodescript` and get the same P2WSH address the C++ side would
    compute.
    """
    hashlock      = bytes.fromhex("11" * 32)
    claim_pub     = bytes.fromhex("02" + "22" * 32)
    refund_pub    = bytes.fromhex("03" + "33" * 32)
    refund_height = 200

    s = _build_htlc_redeem_script(hashlock, refund_height, claim_pub, refund_pub)

    # Opcode skeleton -- the script must contain exactly these
    # control-flow opcodes in this order, exactly once each.
    assert s[0]  == _OP_IF
    assert s[-1] == _OP_ENDIF
    assert s.count(bytes([_OP_IF]))    == 1
    assert s.count(bytes([_OP_ELSE]))  == 1
    assert s.count(bytes([_OP_ENDIF])) == 1

    # The hashlock must appear with a leading 32-byte pushdata header.
    push_hash = bytes([0x20]) + hashlock
    assert push_hash in s, "hashlock push is missing or malformed"

    # Each pubkey must appear with a leading 33-byte pushdata header.
    push_claim  = bytes([0x21]) + claim_pub
    push_refund = bytes([0x21]) + refund_pub
    assert push_claim  in s, "claim pubkey push missing"
    assert push_refund in s, "refund pubkey push missing"

    # OP_CHECKLOCKTIMEVERIFY and OP_DROP appear once each, in order.
    cltv = s.index(_OP_CHECKLOCKTIMEVERIFY)
    drop = s.index(_OP_DROP, cltv)
    assert drop == cltv + 1, "OP_DROP must immediately follow OP_CHECKLOCKTIMEVERIFY"

    # Two OP_CHECKSIG (one per branch).
    assert s.count(bytes([_OP_CHECKSIG])) == 2


def test_p2wsh_script_pubkey_shape():
    """P2WSH SPK is always 34 bytes: OP_0 + push(32) + program."""
    spk = _p2wsh_script_pubkey(bytes(b"\x01" * 50))
    assert len(spk) == 34
    assert spk[0] == 0x00   # OP_0
    assert spk[1] == 0x20   # push 32 bytes


def test_encode_script_num_minimal_invariants():
    """Smoke-check a few canonical values."""
    assert _encode_script_num_minimal(0)   == b""
    assert _encode_script_num_minimal(1)   == b"\x01"
    assert _encode_script_num_minimal(200) == b"\xc8\x00"   # high-bit -> sign byte
    assert _encode_script_num_minimal(15000) == b"\x98\x3a"


# ---------------------------------------------------------------------------
# Tests that need bitcoind (SKIP when missing).
# ---------------------------------------------------------------------------

def test_regtest_node_spawns_and_responds(regtest_node):
    """bitcoind regtest comes up + bitcoin-cli can hit it."""
    info = regtest_node["cli_json"]("getblockchaininfo")
    assert info["chain"] == "regtest", (
        f"expected chain=regtest, got chain={info.get('chain')}"
    )
    assert isinstance(info.get("blocks"), int)
    assert info["blocks"] == 0


def test_regtest_can_mine_blocks(regtest_node):
    """generatetoaddress mines the requested number of blocks."""
    try:
        regtest_node["cli"]("createwallet", "harness")
    except Exception:
        pass
    addr = regtest_node["cli"]("getnewaddress", "", "bech32")
    assert addr, "getnewaddress returned an empty string"
    regtest_node["cli"]("generatetoaddress", "101", addr)
    info = regtest_node["cli_json"]("getblockchaininfo")
    assert info["blocks"] >= 101, (
        f"expected >=101 blocks after generatetoaddress, "
        f"got {info['blocks']}"
    )


def test_regtest_wallet_has_balance(regtest_node):
    try:
        regtest_node["cli"]("loadwallet", "harness")
    except Exception:
        pass
    bal = float(regtest_node["cli"]("getbalance"))
    assert bal > 0.0, f"expected balance > 0 after mining, got {bal}"


def test_regtest_can_decode_segwit_address(regtest_node):
    try:
        regtest_node["cli"]("loadwallet", "harness")
    except Exception:
        pass
    addr = regtest_node["cli"]("getnewaddress", "", "bech32")
    v = regtest_node["cli_json"]("validateaddress", addr)
    assert v["isvalid"] is True
    assert addr.startswith("bcrt1"), (
        f"expected regtest bcrt1 address, got {addr}"
    )


# ---------------------------------------------------------------------------
# Phase C.11 — HTLC funding flow against a real regtest node.
# ---------------------------------------------------------------------------

def _ensure_funded_wallet(node) -> None:
    """Load (or create) the harness wallet and make sure it has coin."""
    try:
        node["cli"]("createwallet", "harness")
    except Exception:
        try:
            node["cli"]("loadwallet", "harness")
        except Exception:
            pass
    bal_str = node["cli"]("getbalance")
    if float(bal_str) <= 0.0:
        addr = node["cli"]("getnewaddress", "", "bech32")
        node["cli"]("generatetoaddress", "101", addr)


def test_decodescript_returns_bcrt1q_for_sost_htlc(regtest_node):
    """SOST-shaped HTLC redeem script -> canonical bcrt1q… P2WSH addr."""
    _ensure_funded_wallet(regtest_node)
    redeem = _build_htlc_redeem_script(
        hashlock=bytes.fromhex("11" * 32),
        refund_height=200,
        claim_pubkey=bytes.fromhex("02" + "22" * 32),
        refund_pubkey=bytes.fromhex("03" + "33" * 32),
    )
    info = regtest_node["cli_json"]("decodescript", redeem.hex())
    # decodescript reports the bcrt1q segwit-v0 P2WSH variant under
    # `segwit.address` (Bitcoin Core >= 0.21). Older fields are
    # kept as fallbacks.
    p2wsh_addr = None
    seg = info.get("segwit") or {}
    if isinstance(seg.get("address"), str):
        p2wsh_addr = seg["address"]
    elif isinstance(seg.get("p2sh-segwit"), str):
        p2wsh_addr = seg["p2sh-segwit"]
    if p2wsh_addr is None:
        # Direct top-level p2wsh on some Core releases.
        p2wsh_addr = info.get("p2sh") or info.get("address")
    assert isinstance(p2wsh_addr, str) and p2wsh_addr.startswith("bcrt1q"), (
        f"expected bcrt1q… P2WSH address from decodescript, got: {info}"
    )


def test_fund_htlc_and_locate_outpoint(regtest_node):
    """Fund the HTLC P2WSH address and find the funding outpoint."""
    _ensure_funded_wallet(regtest_node)
    redeem = _build_htlc_redeem_script(
        hashlock=bytes.fromhex("aa" * 32),
        refund_height=300,
        claim_pubkey=bytes.fromhex("02" + "bb" * 32),
        refund_pubkey=bytes.fromhex("03" + "cc" * 32),
    )
    info = regtest_node["cli_json"]("decodescript", redeem.hex())
    seg = info.get("segwit") or {}
    p2wsh_addr = seg.get("address") or info.get("address")
    assert isinstance(p2wsh_addr, str) and p2wsh_addr.startswith("bcrt1q"), (
        f"decodescript did not yield a bcrt1q… address: {info}"
    )

    # Send a small amount to the HTLC address, mine one block to
    # confirm, then locate the funding outpoint by scanning the tx
    # outputs for the SPK we expect (no reliance on label/walletnotify).
    txid = regtest_node["cli"]("sendtoaddress", p2wsh_addr, "0.05")
    assert len(txid) == 64, f"unexpected txid format: {txid!r}"
    addr_for_mine = regtest_node["cli"]("getnewaddress", "", "bech32")
    regtest_node["cli"]("generatetoaddress", "1", addr_for_mine)

    raw = regtest_node["cli_json"]("getrawtransaction", txid, "1")
    expected_spk_hex = _p2wsh_script_pubkey(redeem).hex()
    matched_vout = None
    matched_amount = None
    for vout in raw.get("vout", []):
        spk = (vout.get("scriptPubKey") or {}).get("hex")
        if spk == expected_spk_hex:
            matched_vout   = vout.get("n")
            matched_amount = vout.get("value")
            break
    assert matched_vout is not None, (
        f"P2WSH output for SOST HTLC not found in funding tx {txid}; "
        f"expected SPK={expected_spk_hex}, got vouts={raw.get('vout')}"
    )
    assert matched_amount is not None and float(matched_amount) > 0.0


def test_testmempoolaccept_recognises_a_wallet_self_spend(regtest_node):
    """testmempoolaccept smoke test for a wallet-signed self-spend.

    This proves the harness can drive testmempoolaccept end-to-end —
    the same call that will validate a SOST-signed HTLC claim/refund
    tx in Phase C.12 before broadcast.
    """
    _ensure_funded_wallet(regtest_node)
    sink_addr = regtest_node["cli"]("getnewaddress", "", "bech32")
    # createrawtransaction needs at least one funded input — fetch one
    # from listunspent.
    utxos = regtest_node["cli_json"]("listunspent")
    assert isinstance(utxos, list) and len(utxos) > 0
    u = utxos[0]
    inputs  = json.dumps([{"txid": u["txid"], "vout": u["vout"]}])
    outputs = json.dumps([{sink_addr: round(float(u["amount"]) - 0.0001, 8)}])
    raw    = regtest_node["cli"]("createrawtransaction", inputs, outputs)
    signed = regtest_node["cli_json"]("signrawtransactionwithwallet", raw)
    assert signed.get("complete") is True, signed
    pkt = json.dumps([signed["hex"]])
    accept = regtest_node["cli_json"]("testmempoolaccept", pkt)
    assert isinstance(accept, list) and len(accept) == 1
    assert accept[0].get("allowed") is True, (
        f"testmempoolaccept rejected a wallet-signed self-spend: {accept[0]}"
    )


# ---------------------------------------------------------------------------
# Placeholders for Phase C.12 — broadcasting SOST-signed HTLC claim/refund.
# ---------------------------------------------------------------------------
#
# These exist so the future operator knows the exact call shape the
# harness will take. They SKIP cleanly today regardless of whether
# bitcoind is present — the missing piece is on the SOST side.

def test_btc_regtest_htlc_happy_path_claim(regtest_node):
    """End-to-end CLAIM on regtest. Phase C.12 scope."""
    pytest.skip(_HTLC_SIGN_BROADCAST_TODO_MSG)


def test_btc_regtest_htlc_happy_path_refund(regtest_node):
    """End-to-end REFUND on regtest (mine past refund_height). Phase C.12 scope."""
    pytest.skip(_HTLC_SIGN_BROADCAST_TODO_MSG)


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
        print("Running pytest anyway — bitcoind-dependent tests will SKIP, "
              "Python-only unit tests still execute.")
    print()
    sys.exit(pytest.main(["-v", __file__]))

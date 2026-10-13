"""Unit tests for ops/sostbridge/evm_gas.py (no network: mocked JSON-RPC transport)."""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ops"))

from sostbridge import evm_gas  # noqa: E402
from sostbridge.evm_gas import (GasPlanError, MainnetRefused, Rpc, TX_GAS_CAP_EIP7825, check_chain, gas_limit,  # noqa: E402
                                plan, main)

DEPLOYER = "0xB6C433C46B4F7Cd95A524B1a4c8A19fa9b51835D"
# Sepolia node estimates measured 2026-10-13 (docs/bridge/EVM_GAS_ESTIMATION.md)
SEPOLIA_EST = {"WSOST": 15_216_907, "QuarantineVault": 9_839_096, "AtomicSwapHTLCv2": 9_821_151}


class FakeNode:
    """Records every call; refuses anything that would sign or send."""

    def __init__(self, chain_id=11155111, estimates=None, gas_price=1_000_018, glamsterdam=True):
        self.chain_id, self.estimates, self.price, self.glam = chain_id, estimates or {}, gas_price, glamsterdam
        self.calls = []

    def __call__(self, method, params):
        self.calls.append(method)
        if method in ("eth_sendRawTransaction", "eth_sendTransaction", "eth_sign", "eth_signTransaction"):
            raise AssertionError(f"dry-run must never call {method}")
        if method == "eth_chainId":
            return hex(self.chain_id)
        if method == "eth_gasPrice":
            return hex(self.price)
        if method == "eth_getBlockByNumber":
            blk = {"number": "0x1", "gasLimit": hex(200_000_000)}
            if self.glam:
                blk["blockAccessListHash"] = "0x" + "00" * 32
            return blk
        if method == "eth_estimateGas":
            tx = params[0]
            assert tx["from"] == DEPLOYER
            key = tx.get("data", tx.get("to"))
            return hex(self.estimates[key.removeprefix("0x")])
        raise AssertionError(f"unexpected method {method}")


# ---- chain guard -------------------------------------------------------------------------------------------

def test_mainnet_refused_by_default():
    with pytest.raises(MainnetRefused):
        check_chain(1)


def test_mainnet_only_with_explicit_flag():
    assert check_chain(1, allow_mainnet=True) == "Ethereum Mainnet"


def test_expected_chain_mismatch_refused():
    with pytest.raises(GasPlanError):
        check_chain(560048, expected=11155111)
    with pytest.raises(GasPlanError):           # expected wins even with the mainnet flag
        check_chain(1, allow_mainnet=True, expected=11155111)


def test_sepolia_and_devnet_accepted():
    assert check_chain(11155111) == "Sepolia"
    assert check_chain(31337) == "Anvil/devnet"


# ---- gas limit ---------------------------------------------------------------------------------------------

def test_margin_applied_under_cap():
    assert gas_limit(1_000_000, 1.15) == 1_150_000
    assert gas_limit(9_839_096, 1.15) == 11_314_961          # ceil


def test_clamped_to_7825_cap_but_never_below_estimate():
    lim = gas_limit(SEPOLIA_EST["WSOST"], 1.15)
    assert lim == TX_GAS_CAP_EIP7825 >= SEPOLIA_EST["WSOST"]
    assert gas_limit(TX_GAS_CAP_EIP7825, 1.5) == TX_GAS_CAP_EIP7825


def test_above_cap_requires_flag():
    with pytest.raises(GasPlanError, match="EIP-7825"):
        gas_limit(TX_GAS_CAP_EIP7825 + 1)
    assert gas_limit(37_817_024, 1.10, allow_above_cap=True) == 41_598_727


def test_bad_inputs():
    with pytest.raises(GasPlanError):
        gas_limit(0)
    with pytest.raises(GasPlanError):
        gas_limit(100_000, 0.9)
    with pytest.raises(GasPlanError):
        gas_limit(2**32, 1.0, allow_above_cap=True)


# ---- plan / dry run ----------------------------------------------------------------------------------------

def _items():
    return [{"name": k, "data": k} for k in SEPOLIA_EST]


def test_plan_uses_node_estimates_and_totals():
    node = FakeNode(estimates=SEPOLIA_EST)
    p = plan(Rpc(transport=node), DEPLOYER, _items(), gas_price_wei=10**9, expected_chain=11155111)
    assert [r["estimate"] for r in p["txs"]] == list(SEPOLIA_EST.values())
    assert p["totalEstimate"] == sum(SEPOLIA_EST.values())
    assert p["totalCostAtEstimateWei"] == sum(SEPOLIA_EST.values()) * 10**9
    assert p["totalGasLimit"] == sum(r["gasLimit"] for r in p["txs"])
    assert p["txs"][0]["gasLimit"] == TX_GAS_CAP_EIP7825
    assert "EIP-8037" in p["rules"]
    assert node.calls.count("eth_estimateGas") == 3
    assert "eth_gasPrice" not in node.calls          # explicit price given


def test_plan_default_price_from_node():
    node = FakeNode(estimates={"x": 21_000}, gas_price=7)
    p = plan(Rpc(transport=node), DEPLOYER, [{"name": "t", "data": "x"}])
    assert p["gasPriceWei"] == 7 and p["totalCostAtEstimateWei"] == 21_000 * 7


def test_plan_refuses_mainnet_before_any_estimate():
    node = FakeNode(chain_id=1, estimates=SEPOLIA_EST)
    with pytest.raises(MainnetRefused):
        plan(Rpc(transport=node), DEPLOYER, _items(), gas_price_wei=1)
    assert "eth_estimateGas" not in node.calls


def test_plan_above_cap_refused_without_flag():
    node = FakeNode(estimates={"big": 37_817_024})
    with pytest.raises(GasPlanError):
        plan(Rpc(transport=node), DEPLOYER, [{"name": "big", "data": "big"}], gas_price_wei=1)
    p = plan(Rpc(transport=node), DEPLOYER, [{"name": "big", "data": "big"}], gas_price_wei=1, allow_above_cap=True)
    assert p["txs"][0]["aboveEip7825Cap"] is True


def test_pre_glamsterdam_header_reported():
    node = FakeNode(estimates={"x": 1}, glamsterdam=False)
    assert "pre-Glamsterdam" in plan(Rpc(transport=node), DEPLOYER, [{"name": "t", "data": "x"}], gas_price_wei=1)["rules"]


def test_value_transfer_tx_shape():
    seen = {}

    def t(method, params):
        if method == "eth_estimateGas":
            seen.update(params[0])
            return hex(204_600)
        return FakeNode()(method, params)
    p = plan(Rpc(transport=t), DEPLOYER, [{"name": "fund", "to": "0x" + "11" * 20, "value": 5 * 10**14}], gas_price_wei=1)
    assert seen == {"from": DEPLOYER, "to": "0x" + "11" * 20, "value": hex(5 * 10**14)}
    assert p["txs"][0]["estimate"] == 204_600


def test_empty_tx_rejected():
    with pytest.raises(GasPlanError):
        plan(Rpc(transport=FakeNode()), DEPLOYER, [{"name": "nothing"}], gas_price_wei=1)


# ---- CLI ---------------------------------------------------------------------------------------------------

def test_cli_dry_run(tmp_path):
    (tmp_path / "w.hex").write_text("WSOST\n")
    planf = tmp_path / "plan.json"
    planf.write_text(json.dumps([{"name": "WSOST", "data_file": "w.hex"}]))
    node = FakeNode(estimates={"WSOST": SEPOLIA_EST["WSOST"]})
    out = io.StringIO()
    rc = main(["--from", DEPLOYER, "--plan", str(planf), "--gas-price-gwei", "1"], rpc=Rpc(transport=node), stdout=out)
    assert rc == 0
    txt = out.getvalue()
    assert "15,216,907" in txt and "DRY RUN" in txt and "0.015216907 ETH" in txt


def test_cli_mainnet_refused(tmp_path, capsys):
    planf = tmp_path / "plan.json"
    planf.write_text(json.dumps([{"name": "x", "data": "x"}]))
    node = FakeNode(chain_id=1, estimates={"x": 1})
    assert main(["--from", DEPLOYER, "--plan", str(planf)], rpc=Rpc(transport=node)) == 2
    assert "Ethereum Mainnet" in capsys.readouterr().err
    assert "eth_estimateGas" not in node.calls


def test_rpc_error_surfaces():
    class Boom(Rpc):
        def call(self, method, params=None):
            raise GasPlanError("eth_estimateGas: execution reverted")
    with pytest.raises(GasPlanError):
        Boom(transport=lambda m, p: None).estimate_gas({})


def test_module_has_no_send_path():
    src = open(evm_gas.__file__).read()
    for forbidden in ("eth_sendRawTransaction", "eth_sendTransaction", "private_key", "sign_transaction"):
        assert forbidden not in src

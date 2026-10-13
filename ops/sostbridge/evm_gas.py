"""Safe EVM gas planning for deployments and test transactions (no key, no signing, no sending).

Why this exists (docs/bridge/EVM_GAS_ESTIMATION.md): local EVMs (forge script simulation, anvil) price
contract creation with the pre-Glamsterdam schedule. Since Glamsterdam went live on Sepolia
(2026-10-06 13:53:36 UTC), EIP-8037 charges state creation per byte: code deposit 1,530 gas/byte instead
of 200, a new account 183,600, a new storage slot 97,920. WSOST measured 2,239,725 gas in the local
EVM and 15,095,931 on Sepolia. forge's default 130 % margin over the local figure ran out of gas.

Rules applied here:
  * every gas limit comes from the TARGET node's eth_estimateGas, never from a local simulation;
  * a margin is added; the EIP-7825 per-transaction cap (16,777,216) is respected when the estimate
    fits under it; an estimate above the cap is only accepted with an explicit flag (it is valid only
    on chains with the EIP-8037 state-gas reservoir, where unused reservoir gas is returned);
  * chainId 1 (Ethereum Mainnet) is refused unless --i-understand-mainnet is passed;
  * dry-run prints per-transaction estimates and the total cost at a given gas price, and sends nothing.

This module has no third-party dependencies: the JSON-RPC transport is injectable for tests.

CLI (dry run only; this tool never signs or sends):
  python3 ops/sostbridge/evm_gas.py --rpc URL --from 0xDEPLOYER --plan plan.json [--gas-price-gwei 20]
plan.json: [{"name": "WSOST", "data": "0x..." | "data_file": "init_WSOST.hex", "to": null, "value": 0}, ...]
"""
import argparse
import json
import math
import os
import sys
import urllib.request

MAINNET_CHAIN_ID = 1
SEPOLIA_CHAIN_ID = 11155111
TX_GAS_CAP_EIP7825 = 16_777_216          # EIP-7825 per-transaction (execution) gas cap
TX_MAX_TOTAL_GAS_LIMIT = 2**32 - 1       # EIP-8037 total tx.gas bound (state-gas reservoir chains)
DEFAULT_MARGIN = 1.15
KNOWN_CHAINS = {1: "Ethereum Mainnet", 11155111: "Sepolia", 560048: "Hoodi", 17000: "Holesky", 31337: "Anvil/devnet"}


class GasPlanError(Exception):
    pass


class MainnetRefused(GasPlanError):
    pass


class Rpc:
    """Minimal JSON-RPC client. `transport(method, params) -> result` can be injected (tests)."""

    def __init__(self, url=None, transport=None, timeout=60):
        if transport is None and not url:
            raise ValueError("need an RPC url or a transport")
        self.url, self.timeout, self._transport = url, timeout, transport

    def call(self, method, params=None):
        params = params or []
        if self._transport is not None:
            return self._transport(method, params)
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(self.url, body, {"content-type": "application/json", "user-agent": "sost-evm-gas/1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            resp = json.load(r)
        if "error" in resp:
            raise GasPlanError(f"{method}: {resp['error'].get('message', resp['error'])}")
        return resp["result"]

    def chain_id(self):
        return int(self.call("eth_chainId"), 16)

    def estimate_gas(self, tx):
        return int(self.call("eth_estimateGas", [tx]), 16)

    def gas_price(self):
        return int(self.call("eth_gasPrice"), 16)

    def latest_block(self):
        return self.call("eth_getBlockByNumber", ["latest", False])


def check_chain(chain_id, allow_mainnet=False, expected=None):
    """Refuse Ethereum Mainnet unless explicitly allowed; optionally require an exact chain."""
    if expected is not None and chain_id != expected:
        raise GasPlanError(f"REFUSED: chainId {chain_id} is not the expected chain {expected}")
    if chain_id == MAINNET_CHAIN_ID and not allow_mainnet:
        raise MainnetRefused("REFUSED: chainId 1 is Ethereum Mainnet; pass --i-understand-mainnet only after a "
                             "separate, explicit authorisation and a fresh mainnet gas measurement")
    return KNOWN_CHAINS.get(chain_id, f"chain {chain_id}")


def gas_limit(estimate, margin=DEFAULT_MARGIN, allow_above_cap=False):
    """Gas limit for a node estimate.

    estimate <= cap: ceil(estimate * margin), clamped to the EIP-7825 cap (still >= estimate; a limit
    under the cap is valid on every post-Osaka chain).
    estimate > cap: only with allow_above_cap (EIP-8037 state-gas reservoir chains such as current
    Sepolia), bounded by 2**32-1.
    """
    if estimate <= 0:
        raise GasPlanError(f"invalid estimate {estimate}")
    if margin < 1.0:
        raise GasPlanError(f"margin {margin} < 1.0 would set a limit below the node estimate")
    want = math.ceil(estimate * margin)
    if estimate <= TX_GAS_CAP_EIP7825:
        return min(want, TX_GAS_CAP_EIP7825)
    if not allow_above_cap:
        raise GasPlanError(f"node estimate {estimate:,} exceeds the EIP-7825 cap {TX_GAS_CAP_EIP7825:,}; this is valid "
                           "only on a chain with the EIP-8037 state-gas reservoir; re-run with --allow-above-7825-cap "
                           "after checking the target chain's rules")
    if estimate > TX_MAX_TOTAL_GAS_LIMIT:
        raise GasPlanError(f"node estimate {estimate:,} exceeds the absolute tx gas bound")
    return min(want, TX_MAX_TOTAL_GAS_LIMIT)


def detect_rules(rpc):
    """Best-effort description of the gas schedule (informational; the estimate is what counts)."""
    try:
        blk = rpc.latest_block() or {}
    except Exception as e:                       # noqa: BLE001 - informational only
        return f"unknown ({e})"
    if "blockAccessListHash" in blk:
        return ("Glamsterdam-era header (EIP-7928 block access list): expect EIP-8037 state-creation pricing; "
                "local forge/anvil simulations under-price contract creation")
    return "pre-Glamsterdam header: classic state-creation pricing (still use node estimates)"


def _tx_for_estimate(sender, item):
    tx = {"from": sender}
    if item.get("to"):
        tx["to"] = item["to"]
    data = item.get("data")
    if data is None and item.get("data_file"):
        with open(item["data_file"]) as f:
            data = f.read().strip()
    if data:
        tx["data"] = data if data.startswith("0x") else "0x" + data
    if item.get("value"):
        tx["value"] = hex(int(item["value"]))
    if "to" not in tx and "data" not in tx:
        raise GasPlanError(f"{item.get('name', '?')}: neither 'to' nor 'data'")
    return tx


def plan(rpc, sender, items, margin=DEFAULT_MARGIN, gas_price_wei=None, allow_mainnet=False,
         allow_above_cap=False, expected_chain=None):
    """Dry-run plan: node estimate and gas limit per tx, total cost. Never signs or sends."""
    cid = rpc.chain_id()
    chain_name = check_chain(cid, allow_mainnet, expected_chain)
    price = gas_price_wei if gas_price_wei is not None else rpc.gas_price()
    rows, tot_est, tot_lim = [], 0, 0
    for item in items:
        est = rpc.estimate_gas(_tx_for_estimate(sender, item))
        lim = gas_limit(est, margin, allow_above_cap)
        rows.append({"name": item.get("name", "?"), "estimate": est, "gasLimit": lim,
                     "aboveEip7825Cap": est > TX_GAS_CAP_EIP7825,
                     "costAtEstimateWei": est * price, "maxCostAtLimitWei": lim * price})
        tot_est += est
        tot_lim += lim
    return {"chainId": cid, "chain": chain_name, "rules": detect_rules(rpc), "sender": sender, "margin": margin,
            "gasPriceWei": price, "txs": rows, "totalEstimate": tot_est, "totalGasLimit": tot_lim,
            "totalCostAtEstimateWei": tot_est * price, "totalMaxCostAtLimitWei": tot_lim * price}


def format_plan(p):
    eth = lambda w: f"{w / 1e18:.9f} ETH"          # noqa: E731
    out = [f"chain: {p['chain']} (chainId {p['chainId']})", f"rules: {p['rules']}",
           f"sender: {p['sender']}  margin: {p['margin']}  gas price: {p['gasPriceWei'] / 1e9:.9f} gwei", ""]
    out.append(f"{'tx':24} {'node estimate':>14} {'gas limit':>14} {'cost @ estimate':>22}")
    for r in p["txs"]:
        flag = "  (above EIP-7825 cap: reservoir chain only)" if r["aboveEip7825Cap"] else ""
        out.append(f"{r['name'][:24]:24} {r['estimate']:>14,} {r['gasLimit']:>14,} {eth(r['costAtEstimateWei']):>22}{flag}")
    out += ["", f"total node estimate {p['totalEstimate']:,} gas -> {eth(p['totalCostAtEstimateWei'])}",
            f"total gas limit     {p['totalGasLimit']:,} gas -> {eth(p['totalMaxCostAtLimitWei'])} (balance needed, worst case)",
            "DRY RUN: nothing was signed or sent."]
    return "\n".join(out)


def main(argv=None, rpc=None, stdout=sys.stdout):
    ap = argparse.ArgumentParser(description="Dry-run EVM gas plan from node-side eth_estimateGas (never sends).")
    ap.add_argument("--rpc", help="JSON-RPC URL of the TARGET chain")
    ap.add_argument("--from", dest="sender", required=True, help="sender address (no key needed)")
    ap.add_argument("--plan", required=True, help="JSON list of {name, to?, data?|data_file?, value?}")
    ap.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    ap.add_argument("--gas-price-gwei", type=float, help="price for the cost column (default: node eth_gasPrice)")
    ap.add_argument("--expect-chain-id", type=int, help="refuse any other chain")
    ap.add_argument("--allow-above-7825-cap", action="store_true", help="accept estimates above 16,777,216 (EIP-8037 chains)")
    ap.add_argument("--i-understand-mainnet", action="store_true", help="permit chainId 1 (requires separate authorisation)")
    ap.add_argument("--json", action="store_true", help="print the plan as JSON")
    a = ap.parse_args(argv)
    if rpc is None:
        if not a.rpc:
            ap.error("--rpc is required")
        rpc = Rpc(a.rpc)
    with open(a.plan) as f:
        items = json.load(f)
    base = os.path.dirname(os.path.abspath(a.plan))
    for it in items:
        if it.get("data_file") and not os.path.isabs(it["data_file"]):
            it["data_file"] = os.path.join(base, it["data_file"])
    price = None if a.gas_price_gwei is None else int(round(a.gas_price_gwei * 1e9))
    try:
        p = plan(rpc, a.sender, items, a.margin, price, a.i_understand_mainnet, a.allow_above_7825_cap, a.expect_chain_id)
    except GasPlanError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(p, indent=1) if a.json else format_plan(p), file=stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

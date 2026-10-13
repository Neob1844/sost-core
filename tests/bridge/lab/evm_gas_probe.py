#!/usr/bin/env python3
"""Read-only gas probe: exact gasUsed of synthetic and real creation txs via eth_simulateV1.

Reproduces the measurements in docs/bridge/EVM_GAS_ESTIMATION.md. Sends nothing, needs no key:
eth_simulateV1 executes against the latest state with validation off.

  python3 tests/bridge/lab/evm_gas_probe.py --rpc URL [--deployment docs/bridge/sepolia/deployment.json]
  python3 tests/bridge/lab/evm_gas_probe.py --rpc http://127.0.0.1:8545 --classic   # anvil baseline

--classic: run the same set on a local anvil (eth_simulateV1 is also served by anvil) for the
pre-Glamsterdam schedule. Refuses chainId 1.
"""
import argparse
import json
import os
import sys
import urllib.request

FROM = "0xB6C433C46B4F7Cd95A524B1a4c8A19fa9b51835D"     # Stage 2 Sepolia deployer (public address only)
GAS = 16_000_000                                        # below the EIP-7825 cap and the public-RPC gas caps


def rpc(url, method, params):
    req = urllib.request.Request(url, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                 {"content-type": "application/json", "user-agent": "sost-evm-gas-probe/1"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    if "error" in r:
        raise RuntimeError(f"{method}: {r['error']}")
    return r["result"]


def simulate(url, call):
    res = rpc(url, "eth_simulateV1", [{"blockStateCalls": [{"calls": [dict({"from": FROM, "gas": hex(GAS)}, **call)]}],
                                       "validation": False}, "latest"])
    c = res[0]["calls"][0]
    return int(c["gasUsed"], 16) if c["status"] == "0x1" else f"FAILED {c.get('error')}"


def runtime_initcode(n):        # PUSH2 n, PUSH1 0, RETURN -> deploys n zero bytes of runtime code
    return "0x61%04x6000f3" % n


def sstore_initcode(k):         # k x SSTORE(slot i+1, 1), STOP -> empty runtime, k new non-zero slots
    return "0x" + "".join("6001" + "61%04x55" % (i + 1) for i in range(k)) + "00"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--deployment", help="deployment.json whose creation txs are replayed by hash (same chain)")
    ap.add_argument("--initcode-dir", help="directory of init_<Name>.hex files to replay (e.g. for --classic)")
    ap.add_argument("--classic", action="store_true")
    a = ap.parse_args()
    cid = int(rpc(a.rpc, "eth_chainId", []), 16)
    if cid == 1:
        sys.exit("REFUSED: Ethereum Mainnet")
    if a.classic:
        rpc(a.rpc, "anvil_setBalance", [FROM, hex(10**20)])
    out = {"chainId": cid, "block": int(rpc(a.rpc, "eth_blockNumber", []), 16), "cases": {}}
    cases = {"transfer_self_1wei": {"to": FROM, "value": "0x1"},
             "transfer_new_account_1wei": {"to": "0x" + "5e" * 19 + "01", "value": "0x1"},
             "transfer_new_account_0wei": {"to": "0x" + "5e" * 19 + "02", "value": "0x0"}}
    for n in (0, 1, 32, 100, 1000, 2000, 4000, 8000):
        cases[f"create_runtime_{n}_bytes"] = {"data": runtime_initcode(n)}
    for k in (0, 1, 2, 5, 10, 20, 50):
        cases[f"create_{k}_new_slots"] = {"data": sstore_initcode(k)}
    for name, call in cases.items():
        out["cases"][name] = simulate(a.rpc, call)
    if a.deployment:
        dep = json.load(open(a.deployment))
        for name, c in dep["contracts"].items():
            tx = rpc(a.rpc, "eth_getTransactionByHash", [c["tx"]])
            out["cases"]["real_" + name] = {"onChainGasUsed": c["gasUsed"], "simulated": simulate(a.rpc, {"data": tx["input"]}),
                                            "initcodeBytes": (len(tx["input"]) - 2) // 2}
    if a.initcode_dir:
        for f in sorted(os.listdir(a.initcode_dir)):
            if f.startswith("init_") and f.endswith(".hex"):
                data = open(os.path.join(a.initcode_dir, f)).read().strip()
                out["cases"]["real_" + f[5:-4]] = {"simulated": simulate(a.rpc, {"data": data})}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

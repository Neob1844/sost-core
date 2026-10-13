#!/usr/bin/env python3
"""Stage 2 Sepolia deployment with node-side gas estimates.

Same constructors as contracts/wsost/script/DeployStage2.s.sol. forge script estimates gas in its
local EVM, which under-prices contract creation on current Sepolia (WSOST: ~2.9M local vs ~15.2M
reported by the Sepolia node), so its transactions run out of gas. This script asks the node
(eth_estimateGas) for every transaction and adds a margin.

  python3 tests/bridge/sepolia_stage2_deploy.py --rpc URL --key-file FILE --pub test-pub.json \
      --vault-hash 0x.. --out deployment.json

Refuses any chain other than Sepolia (11155111). Never prints key material.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

from eth_account import Account
from web3 import Web3

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SEPOLIA = 11155111
TX_GAS_CAP = 16_777_216          # EIP-7825 per-transaction gas cap
TEST_XAUT = "0x38Ca34c6B7b3772B44212d6c2597Fd91a6f944D0"   # Sepolia "Mock XAUT" — TEST TOKEN, no value
TEST_PAXG = "0x754A7D020D559EDD60848450c563303262cAdec7"   # Sepolia "Mock PAXG" — TEST TOKEN, PAXG path gated


def artifact(rel):
    j = json.load(open(os.path.join(ROOT, "contracts", rel)))
    return j


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--pub", required=True)
    ap.add_argument("--vault-hash", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--margin", type=float, default=1.15)
    a = ap.parse_args()

    w3 = Web3(Web3.HTTPProvider(a.rpc))
    if w3.eth.chain_id != SEPOLIA:
        sys.exit(f"REFUSED: chainId {w3.eth.chain_id} is not Sepolia")
    acct = Account.from_key(open(a.key_file).read().strip())
    me = acct.address
    pub = json.load(open(a.pub))
    obs, g = pub["observers"], pub["guardians"]
    assert len(obs) == 3 and len(g) == 5

    solc = subprocess.run([os.path.expanduser("~/.foundry/bin/forge"), "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    out = {"chainId": SEPOLIA, "deployer": me, "forge": solc, "contracts": {}, "inputs": {
        "observers": obs, "guardians": g, "bridgeVaultHash": a.vault_hash, "testXAUT": TEST_XAUT, "testPAXG": TEST_PAXG}}

    if os.path.exists(a.out):                       # resume: keep contracts already deployed by a previous run
        prev = json.load(open(a.out))
        if prev.get("deployer") == me and prev.get("chainId") == SEPOLIA:
            out["contracts"] = {k: v for k, v in prev["contracts"].items() if v.get("status") == 1}
    nonce = [w3.eth.get_transaction_count(me, "pending")]   # local counter: public RPCs are load-balanced and lag

    def deploy(name, rel, args, label_args):
        if name in out["contracts"]:
            print(f"{name:18} {out['contracts'][name]['address']} (already deployed)", flush=True)
            return out["contracts"][name]["address"]
        j = artifact(rel)
        meta = j.get("metadata") or {}
        compiler = (meta.get("compiler") or {}).get("version") if isinstance(meta, dict) else None
        c = w3.eth.contract(abi=j["abi"], bytecode=j["bytecode"]["object"])
        tx = c.constructor(*args).build_transaction({"from": me, "nonce": nonce[0], "chainId": SEPOLIA, "gas": 1})
        est = w3.eth.estimate_gas({"from": me, "data": tx["data"]})
        tx["gas"] = min(int(est * a.margin), TX_GAS_CAP)
        if tx["gas"] < est:
            sys.exit(f"{name}: node estimate {est} exceeds the per-tx cap")
        h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
        nonce[0] += 1
        r = w3.eth.wait_for_transaction_receipt(h, timeout=900)
        rec = {"address": r.contractAddress, "tx": h.hex() if h.hex().startswith("0x") else "0x" + h.hex(),
               "block": r.blockNumber, "status": r.status, "gasEstimateNode": est, "gasLimit": tx["gas"],
               "gasUsed": r.gasUsed, "effectiveGasPriceWei": r.effectiveGasPrice,
               "costWei": r.gasUsed * r.effectiveGasPrice, "compiler": compiler, "constructorArgs": label_args}
        if r.status != 1:
            out["contracts"][name] = rec
            json.dump(out, open(a.out, "w"), indent=1)
            sys.exit(f"{name}: deployment reverted ({h.hex()})")
        code, t0 = b"", time.time()
        while not code and time.time() - t0 < 120:         # load-balanced RPC: a lagging backend returns empty code
            code = w3.eth.get_code(r.contractAddress) or b""
            time.sleep(0 if code else 2)
        rec["runtimeBytes"] = len(code)
        rec["runtimeKeccak256"] = "0x" + Web3.keccak(code).hex().removeprefix("0x")
        rec["runtimeSha256"] = hashlib.sha256(code).hexdigest()
        rec["runtimeMatchesArtifact"] = code.hex().removeprefix("0x") == j["deployedBytecode"]["object"].removeprefix("0x") \
            if "immutableReferences" not in j["deployedBytecode"] or not j["deployedBytecode"]["immutableReferences"] else "immutables"
        out["contracts"][name] = rec
        json.dump(out, open(a.out, "w"), indent=1)
        print(f"{name:18} {r.contractAddress} block {r.blockNumber} gasUsed {r.gasUsed:,} (node est {est:,})", flush=True)
        return r.contractAddress

    cfg = (me, obs, 2, 30, 100_000 * 10**8, 50_000 * 10**8)
    deploy("WSOST", "wsost/out/WSOST.sol/WSOST.json", [bytes.fromhex(a.vault_hash[2:]), cfg],
           {"bridgeVaultHash": a.vault_hash, "admin": me, "observers": obs, "threshold": 2, "minConfirmations": 30,
            "exposureCap": "100000 wSOST", "dailyMintCap": "50000 wSOST"})
    q = deploy("QuarantineVault", "wsost/out/QuarantineVault.sol/QuarantineVault.json", [g, [TEST_XAUT, TEST_PAXG], 3600],
               {"guardians": g, "registeredTokens": [TEST_XAUT, TEST_PAXG], "minTimelock": 3600})
    deploy("GoldReserveVault", "wsost/out/GoldReserveVault.sol/GoldReserveVault.json", [g, q, TEST_XAUT, TEST_PAXG, 3600, 600],
           {"guardians": g, "quarantine": q, "xaut": TEST_XAUT, "paxg": TEST_PAXG, "minTimelock": 3600, "rescueDelay": 600})
    deploy("AtomicSwapHTLCv2", "wsost/out/AtomicSwapHTLCv2.sol/AtomicSwapHTLCv2.json", [], {})
    print("DEPLOYMENT OK →", a.out)


if __name__ == "__main__":
    main()

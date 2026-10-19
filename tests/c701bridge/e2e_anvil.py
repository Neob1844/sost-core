#!/usr/bin/env python3
"""C701 end-to-end on a LOCAL Anvil chain (chainId 31337). Development only.

Proves that the Python engine's EIP-712 authorizations and price quotes are accepted by the REAL
SOSTBridge bytecode, that one transaction moves the Gold Access Key to Gold Reserve V2 and mints
exactly `amount` wSOST, and that replay / revoke / burn / release / reconciliation behave as specified.
The SOST side is the fixture-backed MockSostChain (same JSON shapes as the node). Keys are Anvil's
public, well-known development accounts — TEST ONLY.

usage:  (cd contracts/bridge && forge build)  &&  python3 tests/c701bridge/e2e_anvil.py
"""
import json
import os
import socket
import subprocess
import sys
import time

from eth_utils import keccak
from web3 import Web3
from web3.logs import DISCARD

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "ops"))
from c701bridge import engine as E  # noqa: E402
from c701bridge.pricing import Observation, PriceSigner, SostValuation, XautEurOracle  # noqa: E402
from c701bridge.sost import MockSostChain  # noqa: E402

OUT = os.path.join(ROOT, "contracts", "bridge", "out")
# Anvil default mnemonic accounts (public test keys, never funded anywhere real)
ANVIL_KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
    "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
    "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
]
PORT = 8557
VAULT = "sost1" + "ab" * 20
USER_SOST = "sost1" + "cd" * 20
XAUT8 = 371_313_000_000
METHOD = keccak(text="TEST-ONLY SOST/EUR methodology - NOT APPROVED")

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


def art(name, file=None):
    with open(os.path.join(OUT, (file or name) + ".sol", name + ".json")) as f:
        j = json.load(f)
    return j["abi"], j["bytecode"]["object"]


def main():
    s = socket.socket()
    if s.connect_ex(("127.0.0.1", PORT)) == 0:
        print("port busy; refusing to reuse an unknown process"); sys.exit(2)
    s.close()
    anvil = subprocess.Popen(["anvil", "--port", str(PORT), "--silent", "--chain-id", "31337"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"anvil pid {anvil.pid}")
    try:
        run()
    finally:
        anvil.terminate()
        anvil.wait(timeout=10)
    ok = sum(1 for _, c in results if c)
    print(f"\nE2E (local Anvil): {ok}/{len(results)} checks passed")
    sys.exit(0 if ok == len(results) else 1)


def run():
    w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{PORT}"))
    for _ in range(50):
        if w3.is_connected():
            break
        time.sleep(0.1)
    assert w3.eth.chain_id == 31337, "refusing: not a local Anvil chain"
    acct = [w3.eth.account.from_key(k) for k in ANVIL_KEYS]
    admin, auth, price, pauser, user = acct[0], acct[1], acct[2], acct[3], acct[4]
    guardians = [a.address for a in acct[5:10]]

    def send(fn, frm, expect_ok=True):
        tx = fn.build_transaction({"from": frm.address, "nonce": w3.eth.get_transaction_count(frm.address), "gas": 12_000_000,
                                   "chainId": 31337})
        h = w3.eth.send_raw_transaction(frm.sign_transaction(tx).raw_transaction)
        r = w3.eth.wait_for_transaction_receipt(h)
        if expect_ok and r.status != 1:
            raise RuntimeError("tx reverted")
        return r

    def deploy(name, args, file=None):
        abi, bc = art(name, file)
        c = w3.eth.contract(abi=abi, bytecode=bc)
        r = send(c.constructor(*args), admin)
        return w3.eth.contract(address=r.contractAddress, abi=abi)

    def reverts(fn, frm):
        try:
            fn.call({"from": frm.address})
            return False
        except Exception:
            return True

    xaut = deploy("MockXAUT", [], "SOSTBridge.t")
    quarantine = deploy("QuarantineVault", [guardians, [xaut.address], 7 * 86400])
    reserve = deploy("GoldReserveV2", [guardians, quarantine.address, xaut.address, "0x" + "00" * 20, 7 * 86400, 6 * 3600])
    params = (30, 1_000_000 * 10**8, 5_000_000 * 10**8, 20_000_000 * 10**8, 900, 3600, 1_000 * 10**8, 10_000 * 10**8,
              100, 100 * 10**8, 500, METHOD, 10**6, 10_000)
    cfg = (admin.address, [auth.address], 1, price.address, [pauser.address], params)
    bridge = deploy("SOSTBridge", [xaut.address, reserve.address, keccak(text=VAULT), cfg])
    token = w3.eth.contract(address=bridge.functions.token().call(), abi=art("WSOST")[0])
    send(xaut.functions.mint(user.address, 10 * 10**6), admin)
    send(xaut.functions.approve(bridge.address, 2**256 - 1), user)
    check("contracts deployed on local Anvil (31337)", w3.eth.get_code(bridge.address) != b"")

    class EthView:
        def deposit_used(self, did): return bridge.functions.depositUsed(did).call()
        def deposit_revoked(self, did): return bridge.functions.depositRevoked(did).call()
        def revoke_final(self, did): return self.deposit_revoked(did) and w3.eth.block_number >= self.revoke_block + 2
        def total_supply(self): return token.functions.totalSupply().call()
        def burned_unreleased(self): return bridge.functions.totalBurned().call() - bridge.functions.releasedTotal().call()
        def release_recorded(self, rid): return bridge.functions.releases(bytes.fromhex(rid[2:])).call()[3]
        def pause_mint(self, why): send(bridge.functions.pauseMint(), pauser)
        revoke_block = 0

    eth = EthView()
    chain = MockSostChain(); chain.mine(5)
    clock = lambda: w3.eth.get_block("latest")["timestamp"]  # noqa: E731
    eng = E.Engine(":memory:", chain, eth, chain_id=31337, bridge=bridge.address, vault_address=VAULT,
                   authorizer_key=auth.key, price_signer=PriceSigner(price.key, 31337, bridge.address),
                   oracle=XautEurOracle(), valuation=SostValuation(METHOD, 100_000_000),
                   observations=lambda: [Observation("srcA", XAUT8, clock() - 30), Observation("srcB", XAUT8, clock() - 20)],
                   now=clock)

    def deposit(req, amount=None, n=[0]):
        n[0] += 1
        txid = keccak(text=f"e2e-tx{n[0]}").hex()
        chain.add_tx(txid, [{"address": VAULT, "stocks": amount or req["amount_stocks"], "payload_hex": req["capsule_hex"]}],
                     vin=[{"prev_txid": "aa" * 32, "index": 0, "address": USER_SOST, "stocks": 5_000 * 10**8}])
        chain.mine(1, include=[txid]); eng.scan_vault(); chain.mine(30)
        return txid

    def call_mint(b, frm):
        a = b["authorization"]; q = b["quote"]
        A = (a["requestId"], a["recipient"], a["amount"], a["depositTxid"], a["depositVout"], a["bridgeVault"],
             a["sostBlockHash"], a["sostBlockHeight"], a["confirmations"], a["feeXaut"], a["priceHash"], a["expiry"], a["nonce"])
        Q = (q["xautEur8"], q["sostEur8"], q["methodology"], q["observedAt"], q["quoteId"])
        return bridge.functions.mint(A, Q, b["authSigs"], b["priceSig"])

    # ---------------- wrap 1,000 SOST
    req = eng.create_request(user.address, 1_000 * 10**8)
    dtx = deposit(req)
    check("deposit verified to DEPOSIT_CONFIRMED (30 conf, capsule, amount, unspent)", eng.verify(req["request_id"]) == E.DEPOSIT_CONFIRMED)
    b = eng.authorize(req["request_id"])
    x0 = xaut.functions.balanceOf(user.address).call()
    r = send(call_mint(b, user), user)
    check("ONE transaction: mint succeeded", r.status == 1)
    check("exactly 1,000 wSOST minted to the recipient", token.functions.balanceOf(user.address).call() == 1_000 * 10**8)
    check("Gold Access Key 0.000270 XAUT moved user -> Gold Reserve V2", xaut.functions.balanceOf(reserve.address).call() == 270
          and x0 - xaut.functions.balanceOf(user.address).call() == 270)
    check("bridge holds no XAUT", xaut.functions.balanceOf(bridge.address).call() == 0)
    logs = bridge.events.BridgeMinted().process_receipt(r, errors=DISCARD)
    check("BridgeMinted event published with deposit id", len(logs) == 1 and logs[0]["args"]["amount"] == 1_000 * 10**8)
    check("engine observes COMPLETED", eng.observe_mint(req["request_id"]) == E.COMPLETED)
    check("replay of the same authorization reverts", reverts(call_mint(b, user), user))
    check("reconciliation BALANCED after wrap", eng.reconcile()["status"] == "BALANCED")

    # ---------------- wrong chain id: an authorization for another chain is useless
    req2 = eng.create_request(user.address, 200 * 10**8)
    deposit(req2); eng.verify(req2["request_id"])
    eng.chain_id = 1                          # forge an authorization for a different chain id
    bad = eng.authorize(req2["request_id"])
    eng.chain_id = 31337
    check("authorization signed for another chainId reverts", reverts(call_mint(bad, user), user))

    # ---------------- refund guard on the real contract
    req3 = eng.create_request(user.address, 300 * 10**8)
    tx3 = deposit(req3, amount=250 * 10**8)
    check("amount mismatch -> PENDING_RECOVERY", eng.verify(req3["request_id"]) == E.PENDING_RECOVERY)
    rr = send(bridge.functions.revokeDeposit(bytes.fromhex(tx3), 0, keccak(text="amount mismatch")), auth)
    eth.revoke_block = rr.blockNumber
    send(xaut.functions.mint(admin.address, 1), admin); send(xaut.functions.mint(admin.address, 1), admin)  # advance 2 blocks
    ref = eng.prepare_refund(req3["request_id"])
    check("refund prepared only after on-chain revoke + finality", ref["ok"] and ref["instruction"]["amount_stocks"] == 250 * 10**8 - 10_000)

    # ---------------- burn -> release (no second XAUT payment)
    xr = xaut.functions.balanceOf(reserve.address).call()
    rb = send(bridge.functions.burnForRelease(400 * 10**8, USER_SOST), user)
    ev = bridge.events.BurnedForRelease().process_receipt(rb, errors=DISCARD)[0]["args"]
    rid = "0x" + ev["releaseId"].hex()
    check("burn emitted BurnedForRelease for 400 wSOST", ev["amount"] == 400 * 10**8 and ev["sostAddress"] == USER_SOST)
    check("no XAUT charged on the return path", xaut.functions.balanceOf(reserve.address).call() == xr)
    eng.ingest_burn(rid, user.address, ev["amount"], ev["sostAddress"], ev["networkFeeStocks"])
    ins = eng.release_instruction(rid)
    chain.spent.add((dtx, 0))
    rel = keccak(text="e2e-release").hex()
    chain.add_tx(rel, [{"address": USER_SOST, "stocks": ins["amount_stocks"], "payload_hex": ins["capsule_hex"]},
                       {"address": VAULT, "stocks": 600 * 10**8}],
                 vin=[{"prev_txid": dtx, "index": 0, "address": VAULT, "stocks": 1_000 * 10**8}])
    chain.mine(31, include=[rel])
    check("release verified on SOST", eng.confirm_release(rid, rel) == "RELEASED")
    send(bridge.functions.recordRelease(bytes.fromhex(rid[2:]), bytes.fromhex(rel)), auth)
    rep = eng.reconcile()
    check("reconciliation BALANCED after unwrap (vault 600 = supply 600, in-flight/unbound accounted)",
          rep["status"] in ("BALANCED", "PENDING") and rep["vault_stocks"] - rep["in_flight_deposits"] - rep["unbound_deposits"] == rep["obligations"] == 600 * 10**8)
    print(json.dumps(rep, indent=1))

    # ---------------- compromise simulation: unbacked mint -> CRITICAL -> on-chain pause
    chain.spent.add((rel, 1))                 # vault loses SOST it still owes (theft/key compromise)
    rep2 = eng.reconcile()
    check("vault < obligations -> CRITICAL", rep2["status"] == "CRITICAL")
    check("engine paused minting ON-CHAIN via the pauser role", bridge.functions.mintPaused().call())
    check("burns still work while mint is paused", send(bridge.functions.burnForRelease(10 * 10**8, USER_SOST), user).status == 1)


if __name__ == "__main__":
    main()

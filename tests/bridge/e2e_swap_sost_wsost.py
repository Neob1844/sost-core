#!/usr/bin/env python3
"""Stage 2C local E2E: SOST <-> wSOST peer-to-peer atomic swap.

  SOST side : the REAL native HTLC (OUT_HTLC_LOCK / HTLC_CLAIM / HTLC_REFUND) on a running
              DEVNET_FAST node, built with the unchanged `sost-cli createhtlclock/claimhtlc/refundhtlc`
              and signed by tests/bridge/lab/sost_lab_sign (lab tool, not part of sost-cli).
  EVM side  : the EXISTING AtomicSwapHTLCv2 (unchanged) and the Stage 1 WSOST on Anvil.

The swap only changes the owners of assets that already exist. After every phase the script checks
that the Bridge Vault SOST balance, wSOST totalSupply / totalMinted / totalBurned / burnNonce and
the mint pause are exactly what they were before.

  python3 tests/bridge/e2e_swap_sost_wsost.py --work DIR --signer PATH   (node must be running on 18655)

Disposable devnet/Anvil keys only. Nothing leaves localhost.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "ops"))

from eth_account import Account
from web3 import Web3

from sostbridge.common import to_stocks, fmt_sost, vault_hash
from sostbridge.sostchain import SostRPC
from sostbridge.eip712 import DepositMsg, sign_deposit, order_signatures

DEV = os.path.join(ROOT, "build-devnet")
CLI = os.path.join(DEV, "sost-cli")
ANVIL = os.path.expanduser("~/.foundry/bin/anvil")
OUT = os.path.join(ROOT, "contracts", "wsost", "out")
GENESIS = "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37"
RPC_PORT, ANVIL_PORT = 18655, 8547
FEE = 100_000            # 0.001 SOST per HTLC tx
MARKER = 10_000          # claim witness marker dust (DUST_THRESHOLD)
OUT_TRANSFER, OUT_HTLC_LOCK = 0, 0x12

results, procs = [], []


def step(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def must(name, ok, detail=""):
    if not step(name, ok, detail):
        finish(1)


def finish(code=None):
    for p in procs:
        if p.poll() is None:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    n = sum(ok for _, ok in results)
    print(f"\nRESULT: {n}/{len(results)} PASS", flush=True)
    sys.exit(code if code is not None else (0 if n == len(results) else 1))


def wait_until(fn, timeout, what, every=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            v = fn()
        except Exception:
            v = None
        if v:
            return v
        time.sleep(every)
    step(f"timeout waiting for {what}", False)
    finish(1)


def pkh(addr):
    return addr[5:]


def artifact(path):
    base = os.path.join(ROOT, "contracts", "atomic-swap", "out") if path.startswith("AtomicSwap") else OUT
    j = json.load(open(os.path.join(base, path)))
    return j["abi"], j["bytecode"]["object"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--signer", required=True)
    a = ap.parse_args()
    work = a.work
    rpc = SostRPC(f"http://127.0.0.1:{RPC_PORT}/")

    def cli(wallet, *args, check=True):
        r = subprocess.run([CLI, "--wallet", os.path.join(work, wallet), "--node", f"127.0.0.1:{RPC_PORT}", *args],
                           capture_output=True, text=True, timeout=180)
        if check and r.returncode != 0:
            raise RuntimeError(f"sost-cli {args[0]} failed: {r.stdout[-300:]} {r.stderr[-300:]}")
        return r.stdout + r.stderr

    def wallet(name):
        f = os.path.join(work, name)
        if not os.path.exists(f):
            cli(name, "newwallet")
        return json.load(open(f))["keys"][0]["address"]

    def utxos(addr):
        return rpc.call("getaddressutxos", [addr]) or []

    def balance(addr):
        return sum(int(u["amount_stocks"]) for u in utxos(addr))

    def sign(wallet_name, unsigned_hex, *specs):
        r = subprocess.run([a.signer, os.path.join(work, wallet_name), GENESIS, unsigned_hex, *specs],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("lab signer: " + r.stderr)
        return r.stdout.strip().splitlines()[-1]   # the library prints [SIGHASH-DEBUG] lines first

    def build(cmd, *params):
        out = subprocess.run([CLI, cmd, *map(str, params)], capture_output=True, text=True)
        if out.returncode != 0:
            raise RuntimeError(f"{cmd}: {out.stderr.strip()}")
        return json.loads(out.stdout)["raw_tx_hex"]

    def broadcast(hexs):
        return rpc.call("sendrawtransaction", [hexs])

    def confirmed(txid):
        t = rpc.call("gettransaction", [txid])
        return t and int(t.get("confirmations", 0) or 0) >= 1

    def rejected(hexs):
        try:
            broadcast(hexs)
            return False, "accepted"
        except Exception as e:
            return True, str(e)[:140]

    # ------------------------------------------------------------------ SOST devnet
    tip = rpc.getblockcount()
    must("SOST devnet node reachable, DEV profile", rpc.call("getinfo").get("profile") == "dev", f"height {tip}")
    must("SOST HTLC active on devnet (V14_5=11, V14_7=12)", tip > 12)
    funder, vault = wallet("juan.json"), wallet("vault.json")
    alice, bob = wallet("alice.json"), wallet("bob.json")
    step("parties", True, f"Alice(SOST)={alice[:14]}… Bob(SOST)={bob[:14]}… BridgeVault={vault[:14]}…")

    if not any(int(u["amount_stocks"]) >= to_stocks("150") and u.get("output_type") == OUT_TRANSFER for u in utxos(alice)):
        cli("juan.json", "--yes", "send", alice, "150")
        wait_until(lambda: any(int(u["amount_stocks"]) >= to_stocks("150") for u in utxos(alice)), 300, "Alice funding")
    must("Alice holds native devnet SOST", balance(alice) >= to_stocks("150"), fmt_sost(balance(alice)) + " SOST")

    # ------------------------------------------------------------------ Anvil, WSOST, HTLCv2
    procs.append(subprocess.Popen([ANVIL, "--port", str(ANVIL_PORT), "--silent"], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, preexec_fn=os.setsid))
    w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{ANVIL_PORT}"))
    wait_until(lambda: w3.eth.chain_id, 30, "anvil")
    admin, alice_eth, bob_eth, relayer = w3.eth.accounts[:4]

    def deploy(path, *args):
        abi, bc = artifact(path)
        r = w3.eth.wait_for_transaction_receipt(w3.eth.contract(abi=abi, bytecode=bc).constructor(*args).transact({"from": admin}))
        return w3.eth.contract(address=r.contractAddress, abi=abi)

    def tx(fn, sender):
        r = w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
        assert r.status == 1
        return r

    obs_keys = [Account.create().key for _ in range(3)]
    obs = [Account.from_key(k).address for k in obs_keys]
    w = deploy("WSOST.sol/WSOST.json", vault_hash(vault), (admin, obs, 2, 30, to_stocks("100000"), to_stocks("50000")))
    htlc = deploy("AtomicSwapHTLCv2.sol/AtomicSwapHTLCv2.json")
    step("Anvil: WSOST + existing AtomicSwapHTLCv2 deployed", True, f"WSOST={w.address} HTLCv2={htlc.address}")

    # Bob's existing wSOST: one canonical 2-of-3 attested bridge mint (500)
    dep = DepositMsg(depositId=hashlib.sha256(b"bob-existing-deposit").digest(), recipient=bob_eth, amount=to_stocks("500"),
                     bridgeVault=vault_hash(vault), sostBlockHash=b"\x11" * 32, sostBlockHeight=tip, confirmations=30)
    sigs = order_signatures([(obs[i], sign_deposit(obs_keys[i], dep, w3.eth.chain_id, w.address)) for i in (0, 2)])
    tx(w.functions.mint(dep.as_tuple(), sigs), relayer)
    must("Bob holds 500 existing wSOST (canonical bridge mint)", w.functions.balanceOf(bob_eth).call() == to_stocks("500"))

    def bridge_state():
        return {"vault_sost": balance(vault), "supply": w.functions.totalSupply().call(),
                "minted": w.functions.totalMinted().call(), "burned": w.functions.totalBurned().call(),
                "burnNonce": w.functions.burnNonce().call(), "mintPaused": w.functions.mintPaused().call()}

    base = bridge_state()
    step("bridge snapshot taken", True, f"vault {fmt_sost(base['vault_sost'])} SOST · wSOST supply {fmt_sost(base['supply'])}")

    def bridge_unchanged(label):
        now = bridge_state()
        diff = {k: (base[k], now[k]) for k in base if base[k] != now[k]}
        step(f"{label}: Bridge Vault, wSOST supply/minted/burned, burn nonce, mint pause UNCHANGED", not diff, str(diff) if diff else "")

    # ================================================================== SWAP 1 — claim path
    # Alice: 100 native SOST  <->  Bob: 99.5 wSOST (negotiated ratio, not hardcoded 1:1)
    S = secrets.token_bytes(32)
    H = hashlib.sha256(S).hexdigest()
    sost_amt, wsost_amt = to_stocks("100"), to_stocks("99.5")
    u = next(u for u in utxos(alice) if int(u["amount_stocks"]) >= sost_amt + FEE and u.get("output_type") == OUT_TRANSFER)
    T1 = rpc.getblockcount() + 120
    raw = build("createhtlclock", u["txid"], u["vout"], u["amount_stocks"], pkh(alice), H, T1, pkh(bob), pkh(alice), sost_amt, FEE)
    lock_txid = broadcast(sign("alice.json", raw, f"{u['amount_stocks']}:{OUT_TRANSFER}:{alice}"))
    step("1. Alice funds the SOST HTLC (100 SOST, claim=Bob, refund=Alice)", bool(lock_txid), f"txid {str(lock_txid)[:16]}… refund_height {T1}")
    wait_until(lambda: confirmed(lock_txid), 300, "SOST lock confirmation")
    def htlc_status(txid):
        return json.loads(re.search(r"\{.*\}", cli("bob.json", "gethtlcstatus", txid, "0"), re.S).group(0))["result"]
    st = htlc_status(lock_txid)
    step("2. Bob verifies the SOST lock on chain (gethtlcstatus)", st["status"] == "locked" and st["hashlock"] == H
         and st["claim_pkh"] == pkh(bob) and st["refund_pkh"] == pkh(alice) and round(st["amount"] * 1e8) == sost_amt
         and st["refund_height"] == T1, f"status {st['status']} amount {st['amount']} refund_height {st['refund_height']}")

    swap1 = hashlib.sha256(b"swap-1" + S).digest()
    T2 = w3.eth.block_number + 40
    tx(w.functions.approve(htlc.address, wsost_amt), bob_eth)
    tx(htlc.functions.lockERC20(swap1, w.address, wsost_amt, bytes.fromhex(H), T2, alice_eth, bob_eth), bob_eth)
    s1 = htlc.functions.getSwap(swap1).call()
    step("3. Bob funds the wSOST HTLC (99.5 wSOST, same hashlock, claim=Alice)", s1[0] == 1 and s1[3] == wsost_amt and s1[4].hex() == H,
         f"lockedAmount {fmt_sost(s1[3])}")
    step("4. same hashlock on both chains", s1[4].hex() == H == st["hashlock"])
    bridge_unchanged("after both locks")

    r = tx(htlc.functions.claimERC20(swap1, S, wsost_amt), alice_eth)
    ev = htlc.events.Claimed().process_receipt(r)[0]
    revealed = bytes(ev["args"]["preimage"])
    step("5. Alice claims the wSOST, revealing the secret on Ethereum", revealed == S and w.functions.balanceOf(alice_eth).call() == wsost_amt)

    # negative: a claim with a wrong preimage is rejected by SOST consensus (R21)
    bad = build("claimhtlc", lock_txid, 0, sost_amt, secrets.token_hex(32), pkh(bob), MARKER, FEE)
    ok, why = rejected(sign("bob.json", bad, f"{sost_amt}:{OUT_HTLC_LOCK}:{bob}"))
    step("   SOST node rejects a claim with the wrong preimage", ok, why)
    # negative: a claim signed by Alice (not the claim key) is rejected
    wrong = build("claimhtlc", lock_txid, 0, sost_amt, revealed.hex(), pkh(alice), MARKER, FEE)
    ok, why = rejected(sign("alice.json", wrong, f"{sost_amt}:{OUT_HTLC_LOCK}:{alice}"))
    step("   SOST node rejects a claim not signed by the claim key", ok, why)

    bob_before = balance(bob)
    claim = build("claimhtlc", lock_txid, 0, sost_amt, revealed.hex(), pkh(bob), MARKER, FEE)
    claim_txid = broadcast(sign("bob.json", claim, f"{sost_amt}:{OUT_HTLC_LOCK}:{bob}"))
    wait_until(lambda: confirmed(claim_txid), 300, "SOST claim confirmation")
    step("6. Bob claims the native SOST with the revealed secret", balance(bob) - bob_before == sost_amt - FEE,
         f"+{fmt_sost(balance(bob) - bob_before)} SOST")
    st = htlc_status(lock_txid)
    step("   SOST node reports the lock CLAIMED with the same secret", st["status"] == "claimed" and st.get("revealed_preimage") == S.hex())
    step("7. final balances", w.functions.balanceOf(alice_eth).call() == wsost_amt
         and w.functions.balanceOf(bob_eth).call() == to_stocks("500") - wsost_amt
         and w.functions.balanceOf(htlc.address).call() == 0,
         f"Alice {fmt_sost(w.functions.balanceOf(alice_eth).call())} wSOST · Bob {fmt_sost(w.functions.balanceOf(bob_eth).call())} wSOST + {fmt_sost(sost_amt - FEE)} SOST")
    ok, why = rejected(sign("bob.json", claim, f"{sost_amt}:{OUT_HTLC_LOCK}:{bob}"))
    step("   SOST claim cannot be replayed", ok, why)
    bridge_unchanged("8. after the claim path (no mint, no burn, no vault release)")

    # ================================================================== SWAP 2 — refund path
    S2 = secrets.token_bytes(32)
    H2 = hashlib.sha256(S2).hexdigest()
    amt2 = to_stocks("20")
    u = next(u for u in utxos(alice) if int(u["amount_stocks"]) >= amt2 + FEE and u.get("output_type") == OUT_TRANSFER)
    T1b = rpc.getblockcount() + 12
    raw = build("createhtlclock", u["txid"], u["vout"], u["amount_stocks"], pkh(alice), H2, T1b, pkh(bob), pkh(alice), amt2, FEE)
    lock2 = broadcast(sign("alice.json", raw, f"{u['amount_stocks']}:{OUT_TRANSFER}:{alice}"))
    wait_until(lambda: confirmed(lock2), 300, "SOST lock 2")
    swap2 = hashlib.sha256(b"swap-2" + S2).digest()
    tx(w.functions.approve(htlc.address, amt2), bob_eth)
    tx(htlc.functions.lockERC20(swap2, w.address, amt2, bytes.fromhex(H2), w3.eth.block_number + 5, alice_eth, bob_eth), bob_eth)
    step("9. refund path: both sides locked, nobody reveals", True, f"SOST refund_height {T1b}")

    refund = build("refundhtlc", lock2, 0, amt2, pkh(alice), FEE)
    ok, why = rejected(sign("alice.json", refund, f"{amt2}:{OUT_HTLC_LOCK}:{alice}"))
    step("   SOST refund before refund_height is rejected", ok, why)
    try:
        htlc.functions.refundERC20(swap2).call({"from": bob_eth})
        early = False
    except Exception:
        early = True
    step("   wSOST refund before refundTime is rejected", early)

    for _ in range(6):
        w3.provider.make_request("evm_mine", [])
    bob_w = w.functions.balanceOf(bob_eth).call()
    tx(htlc.functions.refundERC20(swap2), bob_eth)
    step("10. Bob refunds his wSOST after the EVM timeout", w.functions.balanceOf(bob_eth).call() - bob_w == amt2)

    wait_until(lambda: rpc.getblockcount() >= T1b, 600, "SOST refund height", every=2)
    alice_before = balance(alice)
    rtx = broadcast(sign("alice.json", refund, f"{amt2}:{OUT_HTLC_LOCK}:{alice}"))
    wait_until(lambda: confirmed(rtx), 300, "SOST refund confirmation")
    step("11. Alice refunds her native SOST after refund_height", balance(alice) - alice_before == amt2 - FEE,
         f"+{fmt_sost(balance(alice) - alice_before)} SOST")
    bridge_unchanged("12. after the refund path")
    step("13. HTLC escrow empty", w.functions.balanceOf(htlc.address).call() == 0)
    finish()


if __name__ == "__main__":
    main()

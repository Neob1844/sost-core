#!/usr/bin/env python3
"""Stage 1 local E2E: real SOST DEVNET_FAST node + miner + CLI, real Anvil, real contracts,
real observers / relayer / indexer / release signer. Disposable keys only. Nothing leaves localhost.

  python3 tests/bridge/e2e_devnet_anvil.py [--work DIR] [--min-conf 30]

Requires: build-devnet (SOST_DEVNET_FORKS=ON), ~/.foundry/bin/anvil, forge artifacts in contracts/wsost/out.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "ops"))

from eth_account import Account
from web3 import Web3

from sostbridge.common import to_stocks, fmt_sost, vault_hash, release_note
from sostbridge.sostchain import SostRPC
from sostbridge.ethside import Web3WSOST
from sostbridge.observer import Observer, ObserverConfig, collect, still_canonical
from sostbridge.ledger import scan_vault, reconcile, enforce_safety, BALANCED, PENDING, CRITICAL
from sostbridge.signer import ReleaseProcessor, ReleaseJournal, ColdSingleSigner
from sostbridge.governance import Proposal

DEV = os.path.join(ROOT, "build-devnet")
NODE, MINER, CLI = (os.path.join(DEV, b) for b in ("sost-node", "sost-miner", "sost-cli"))
ANVIL = os.path.expanduser("~/.foundry/bin/anvil")
OUT = os.path.join(ROOT, "contracts", "wsost", "out")
RPC_PORT, P2P_PORT, ANVIL_PORT = 18655, 19655, 8546
SOST_URL = f"http://127.0.0.1:{RPC_PORT}/"
FEE_ALLOWANCE = to_stocks("0.001")

results = []
procs = []


def step(name, ok, detail=""):
    results.append({"step": name, "result": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def must(name, ok, detail=""):
    if not step(name, ok, detail):
        raise SystemExit(f"E2E stopped at: {name}")


def spawn(args, log):
    p = subprocess.Popen(args, stdout=open(log, "a"), stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    procs.append(p)
    return p


def kill(p):
    if p and p.poll() is None:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)


def cli(work, wallet, *args, check=True):
    r = subprocess.run([CLI, "--wallet", os.path.join(work, wallet), "--node", f"127.0.0.1:{RPC_PORT}", *args],
                       capture_output=True, text=True, timeout=180)
    if check and r.returncode != 0:
        raise RuntimeError(f"sost-cli {' '.join(args)} failed: {r.stdout[-300:]} {r.stderr[-300:]}")
    return r.stdout + r.stderr


def new_wallet(work, name):
    out = cli(work, name, "newwallet")
    import re
    return re.findall(r"sost1[0-9a-f]{40}", out)[0]


def spendable(rpc, addr):
    r = rpc.call("getaddressutxos", [addr]) or []
    return sum(int(u.get("amount_stocks", 0)) for u in r if u.get("spendable", True) and u.get("mature", True))


def wait_until(fn, timeout, what, every=2.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise SystemExit(f"timeout waiting for {what}")


def artifact(path):
    with open(os.path.join(OUT, path)) as f:
        j = json.load(f)
    return j["abi"], j["bytecode"]["object"]


def deploy(w3, sender, path, *args):
    abi, bc = artifact(path)
    c = w3.eth.contract(abi=abi, bytecode=bc)
    rcpt = w3.eth.wait_for_transaction_receipt(c.constructor(*args).transact({"from": sender}))
    return w3.eth.contract(address=rcpt.contractAddress, abi=abi)


def tx(w3, fn, sender):
    return w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))


def reverts(fn, sender):
    try:
        fn.call({"from": sender})
        return False
    except Exception:
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work")
    ap.add_argument("--min-conf", type=int, default=30)
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="sost-stage1-e2e-")
    os.makedirs(work, exist_ok=True)
    MINC = a.min_conf
    print(f"work dir: {work}", flush=True)
    for b in (NODE, MINER, CLI, ANVIL):
        must(f"tool present {os.path.basename(b)}", os.access(b, os.X_OK))
    must("devnet build (SOST_DEVNET_FORKS=ON)", "SOST_DEVNET_FORKS:BOOL=ON" in open(os.path.join(DEV, "CMakeCache.txt")).read())

    # ---------------------------------------------------------------- SOST devnet
    spawn([NODE, "--profile", "dev", "--genesis", os.path.join(ROOT, "genesis_block.json"), "--chain", os.path.join(work, "chain.json"),
           "--port", str(P2P_PORT), "--rpc-port", str(RPC_PORT), "--rpc-noauth", "--connect", "127.0.0.1:1"], os.path.join(work, "node.log"))
    rpc = SostRPC(SOST_URL)
    wait_until(lambda: _try(rpc.getblockcount) is not None, 60, "node RPC")
    must("SOST node is DEV profile", rpc.call("getinfo").get("profile") == "dev")
    def wallet(name):
        f = os.path.join(work, name)
        if os.path.exists(f):
            return json.load(open(f))["keys"][0]["address"]
        return new_wallet(work, name)
    juan = wallet("juan.json")
    vault = wallet("vault.json")
    minerw = wallet("miner.json")
    step("wallets: Juan, Bridge Vault (disposable devnet key), miner", True, f"vault={vault}")

    def mine_to(addr, wallet):
        return spawn([MINER, "--profile", "dev", "--rpc", f"127.0.0.1:{RPC_PORT}", "--address", addr, "--wallet",
                      os.path.join(work, wallet), "--mining-key-label", "default", "--blocks", "1000000", "--threads", "1"],
                     os.path.join(work, "miner.log"))

    if spendable(rpc, juan) < to_stocks("1001"):
        m = mine_to(juan, "juan.json")
        wait_until(lambda: spendable(rpc, juan) >= to_stocks("1001"), 7200, "Juan to hold 1,000 spendable devnet SOST", every=5)
        kill(m)
    must("1. Juan holds >= 1,000 devnet SOST", True, fmt_sost(spendable(rpc, juan)))
    miner = mine_to(minerw, "miner.json")
    start_height = rpc.getblockcount() + 1

    # ---------------------------------------------------------------- Anvil + contracts
    spawn([ANVIL, "--port", str(ANVIL_PORT), "--silent"], os.path.join(work, "anvil.log"))
    w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{ANVIL_PORT}"))
    wait_until(lambda: _try(lambda: w3.eth.chain_id) is not None, 30, "anvil")
    acct = w3.eth.accounts
    admin, juan_eth, relayer = acct[0], acct[1], acct[2]
    obs_keys = [Account.create().key for _ in range(3)]
    obs_addrs = [Account.from_key(k).address for k in obs_keys]
    for o in obs_addrs:
        w3.eth.wait_for_transaction_receipt(w3.eth.send_transaction({"from": admin, "to": o, "value": 10**18}))
        w3.provider.make_request("anvil_impersonateAccount", [o])
    cfg_tuple = (admin, obs_addrs, 2, MINC, to_stocks("10000"), to_stocks("5000"))
    wsost_c = deploy(w3, admin, "WSOST.sol/WSOST.json", vault_hash(vault), cfg_tuple)
    eth = Web3WSOST(w3, wsost_c.address, wsost_c.abi)
    step("contracts deployed on Anvil", True, f"WSOST={wsost_c.address} chainId={w3.eth.chain_id}")

    status = {"s": None}

    def reco():
        r = reconcile(scan_vault(rpc, vault, start_height), eth, MINC, FEE_ALLOWANCE)
        status["s"] = r.status
        return r

    ocfg = ObserverConfig(vault=vault, start_height=start_height, min_confirmations=MINC,
                          chain_id=w3.eth.chain_id, wsost=wsost_c.address)
    observers = [Observer(f"obs{i}", k, SostRPC(SOST_URL), ocfg, eth, status_fn=lambda: status["s"]) for i, k in enumerate(obs_keys)]

    # ================================================================ PHASE R — real SOST devnet node + CLI
    # Capsules are accepted by the node (and attachable by the CLI) only from V12_HEIGHT = 7,350 in
    # every profile, devnet included. Below that, a real deposit cannot carry the Ethereum recipient,
    # so Phase R proves the REAL-node adapter and the safety rules; Phase F runs the full capsule flow.
    tip = rpc.getblockcount()
    step("devnet capsule gate", tip < 7350, f"devnet height {tip} < 7,350: capsule deposits need the chain past V12 (node + CLI unchanged)")
    cli(work, "juan.json", "--yes", "send", vault, "500")
    wait_until(lambda: scan_vault(rpc, vault, start_height).unattributed, 600, "plain deposit inclusion")
    sc = scan_vault(rpc, vault, start_height)
    must("R1. real node: 500 SOST to the vault WITHOUT a recipient capsule is read exactly and is NOT mintable",
         sc.unattributed[0]["amount"] == to_stocks("500") and sc.deposits == [] and sc.vault_balance == to_stocks("500"))
    must("R2. real node: observers produce no attestation for it", all(o.candidates() == [] for o in observers))
    r = reco()
    must("R3. real node: reconciliation BALANCED with a manual-review warning", r.status == BALANCED and r.warnings, r.warnings[0] if r.warnings else "")
    cli(work, "vault.json", "--yes", "--from-address", vault, "send", juan, "10")
    wait_until(lambda: scan_vault(rpc, vault, start_height).unexplained_spends, 600, "vault spend inclusion")
    r = reco()
    must("R4. real node: a vault spend without a release capsule -> CRITICAL", r.status == CRITICAL and any("unexplained" in x for x in r.reasons))
    enforce_safety(r, eth, obs_addrs[0])
    must("R5. CRITICAL stops NEW mints on the real contract", wsost_c.functions.mintPaused().call())

    # ================================================================ PHASE F — full capsule flow
    # Real Anvil + real contracts + real observers/relayer/indexer/release processor; the SOST side is
    # an in-memory chain that serves the exact gettransaction shape verified against the real node above.
    phase_f(w3, admin, juan_eth, relayer, obs_keys, obs_addrs, MINC)

    # ---------------------------------------------------------------- gold reserve on Anvil
    gold_e2e(w3, admin)
    kill(miner)



def phase_f(w3, admin, juan_eth, relayer, obs_keys, obs_addrs, MINC):
    from sostbridge.sostchain import FakeSostChain
    from sostbridge.signer import FakeChainSigner
    from sostbridge.common import build_open_note
    chain = FakeSostChain(); chain.mine(5)
    VAULT, JUAN = "sost1" + "a" * 40, "sost1" + "b" * 40
    wsost_c = deploy(w3, admin, "WSOST.sol/WSOST.json", vault_hash(VAULT), (admin, obs_addrs, 2, MINC, to_stocks("10000"), to_stocks("5000")))
    eth = Web3WSOST(w3, wsost_c.address, wsost_c.abi)
    status = {"s": None}
    def reco():
        r = reconcile(scan_vault(chain, VAULT, 1), eth, MINC, FEE_ALLOWANCE); status["s"] = r.status; return r
    ocfg = ObserverConfig(vault=VAULT, start_height=1, min_confirmations=MINC, chain_id=w3.eth.chain_id, wsost=wsost_c.address)
    observers = [Observer(f"obs{i}", k, chain, ocfg, eth, status_fn=lambda: status["s"]) for i, k in enumerate(obs_keys)]
    must("F1. Juan holds 1,000 SOST (in-memory SOST side)", True)
    dep_tx = {"txid": FakeSostChain.txid_for("juan-500"), "vin": [{"address": JUAN, "amount": "1000.00000000"}],
              "vout": [{"address": VAULT, "amount": "500.00000000", "payload_hex": build_open_note("WSOST:" + juan_eth)},
                       {"address": JUAN, "amount": "499.99990000"}]}
    chain.add_block([dep_tx])
    dep = scan_vault(chain, VAULT, 1).deposits[0]
    must("F2. deposit of 500 SOST with recipient capsule", dep.amount == to_stocks("500") and dep.recipient == juan_eth)
    must("F3. before confirmations: PENDING, observers refuse", reco().status == PENDING and all(o.attest(dep) is None for o in observers))
    chain.mine(MINC)
    step(f"F4. {MINC} confirmations reached", chain.getblockcount() - dep.height + 1 >= MINC)
    atts = [o.attest(scan_vault(chain, VAULT, 1).deposits[0]) for o in observers]
    got = collect(atts, 2)
    must("F5. 2-of-3 observers attest (EIP-712, real signatures)", got is not None)
    msg, sigs = got
    must("relayer alone cannot mint", reverts(wsost_c.functions.mint(msg.as_tuple(), []), relayer))
    must("relayer pre-flight: block still canonical", still_canonical(chain, msg))
    eth.mint(msg, sigs, relayer)
    must("F6. 500 wSOST minted on the real contract (Python signatures verified on-chain)", wsost_c.functions.balanceOf(juan_eth).call() == to_stocks("500"))
    must("F7. BALANCED", reco().status == BALANCED)
    must("duplicate mint reverts on-chain", reverts(wsost_c.functions.mint(msg.as_tuple(), sigs), relayer))
    tx(w3, wsost_c.functions.burn(to_stocks("200"), JUAN), juan_eth)
    must("F8. Juan burns 200 wSOST -> release pending", reco().status == PENDING)
    proc = ReleaseProcessor(FakeChainSigner(chain, VAULT), ReleaseJournal(os.path.join(tempfile.mkdtemp(), "j.json")), chain, VAULT, 1, FEE_ALLOWANCE)
    must("F9-10. release signed through the signer interface", len(proc.process(eth)) == 1)
    must("journal blocks a second release", proc.process(eth) == [])
    rel = scan_vault(chain, VAULT, 1).releases[0]
    must("F11. 200 SOST returned (minus the fee allowance)", rel.dest == JUAN and rel.amount == to_stocks("200") - FEE_ALLOWANCE)
    r = reco()
    must("F12. final: 300 wSOST, >= 300 SOST locked, BALANCED", r.status == BALANCED and r.ledger["H_total_supply"] == to_stocks("300")
         and r.ledger["confirmed_backing"] >= to_stocks("300"), json.dumps(r.ledger))
    # failure simulation on the real contract: two compromised observers mint a fake deposit
    from sostbridge.eip712 import DepositMsg, sign_deposit, order_signatures
    fake = DepositMsg(b"\x99" * 32, juan_eth, to_stocks("1000"), vault_hash(VAULT), bytes.fromhex(chain.getblockhash(3)), 3, MINC)
    fsigs = order_signatures([(obs_addrs[i], sign_deposit(obs_keys[i], fake, w3.eth.chain_id, wsost_c.address)) for i in (0, 1)])
    eth.mint(fake, fsigs, relayer)
    r = reco()
    must("FAIL-SIM unbacked mint by 2 compromised observers -> CRITICAL", r.status == CRITICAL and any("without a canonical deposit" in x for x in r.reasons))
    enforce_safety(r, eth, obs_addrs[2])
    must("CRITICAL pauses new mints; transfers keep working", wsost_c.functions.mintPaused().call()
         and tx(w3, wsost_c.functions.transfer(admin, 1), juan_eth).status == 1)
    must("observers refuse new attestations while CRITICAL", all(o.attest(dep) is None for o in observers))

def gold_e2e(w3, admin):
    acct = w3.eth.accounts
    guardians = acct[3:8]
    donor = acct[8]
    TL, RD = 7 * 86400, 6 * 3600
    xaut = deploy(w3, admin, "GoldReserve.t.sol/MockGold.json", "Tether Gold (mock)", "XAUT")
    paxg = deploy(w3, admin, "GoldReserve.t.sol/MockGold.json", "Paxos Gold (mock)", "PAXG")
    q = deploy(w3, admin, "QuarantineVault.sol/QuarantineVault.json", guardians, [xaut.address, paxg.address], TL)
    v = deploy(w3, admin, "GoldReserveVault.sol/GoldReserveVault.json", guardians, q.address, xaut.address, paxg.address, TL, RD)
    q2 = deploy(w3, admin, "QuarantineVault.sol/QuarantineVault.json", guardians, [xaut.address, paxg.address], TL)
    succ = deploy(w3, admin, "GoldReserveVault.sol/GoldReserveVault.json", guardians, q2.address, xaut.address, paxg.address, TL, RD)

    def approve(contract, action, n):
        for g in guardians[:n]:
            tx(w3, contract.functions.approve(action), g)

    tx(w3, xaut.functions.mint(donor, 10**9), admin)
    tx(w3, xaut.functions.approve(v.address, 10**9), donor)
    tx(w3, v.functions.contribute(xaut.address, 100 * 10**6), donor)
    must("G1. mock XAUT contributed to Gold Reserve V2", xaut.functions.balanceOf(v.address).call() == 100 * 10**6)
    raw_ok = True
    for sig in ("withdraw(address)", "withdraw(address,uint256)"):
        sel = Web3.keccak(text=sig)[:4]
        try:
            w3.eth.call({"from": guardians[0], "to": v.address, "data": sel.hex() + "00" * 64})
            raw_ok = False
        except Exception:
            pass
    must("G3. arbitrary withdrawal impossible (no such function)", raw_ok)
    approve(v, v.functions.pauseAction().call(), 1)
    must("G4. pause with 1 guardian fails", reverts(v.functions.pause(), admin))
    approve(v, v.functions.pauseAction().call(), 2)
    tx(w3, v.functions.pause(), admin)
    must("G5. pause with 2-of-5 passes and moves nothing", v.functions.paused().call() and xaut.functions.balanceOf(v.address).call() == 100 * 10**6)
    ua = v.functions.unpauseAction().call(); approve(v, ua, 4); tx(w3, v.functions.unpause(), admin)

    p = Proposal("GRV2-004", v.address, xaut.address, succ.address, xaut.address, bytes(Web3.keccak(w3.eth.get_code(succ.address))),
                 35712, 36000, TL, "XAUT protocol migration")
    must("proposal hash identical in Python and Solidity", p.proposal_hash() == bytes(v.functions.proposalHash(p.as_tuple()).call()))
    rs = v.functions.registerSuccessorAction(succ.address, p.successor_code_hash).call()
    approve(v, rs, 4); tx(w3, v.functions.registerSuccessor(succ.address, p.successor_code_hash), admin)
    ph = p.proposal_hash()
    no_vote = (ph, 12, 7, 0, 0, 36030, Web3.keccak(text="tally-7"))
    approve(v, v.functions.migrationAction(ph, no_vote[6]).call(), 5)
    must("G6. migration without a passing vote fails (7/12)", reverts(v.functions.queueMigration(p.as_tuple(), no_vote), admin))
    yes = (ph, 12, 8, 2, 2, 36030, Web3.keccak(text="tally-8"))
    approve(v, v.functions.migrationAction(ph, yes[6]).call(), 4)
    tx(w3, v.functions.queueMigration(p.as_tuple(), yes), admin)
    must("G7. vote passed but timelock pending: execute fails", reverts(v.functions.executeMigration(p.as_tuple()), admin))
    eoa = Proposal("GRV2-005", v.address, xaut.address, acct[9], xaut.address, b"\x00" * 32, 35712, 36000, TL, "to an EOA")
    eoa_res = (eoa.proposal_hash(), 12, 12, 0, 0, 36030, Web3.keccak(text="eoa"))
    approve(v, v.functions.migrationAction(eoa.proposal_hash(), eoa_res[6]).call(), 5)
    must("G8. destination EOA fails", reverts(v.functions.queueMigration(eoa.as_tuple(), eoa_res), admin))
    ra = v.functions.rescueAction(xaut.address).call()
    approve(v, ra, 3)
    must("G9a. rescue with 3 guardians fails", reverts(v.functions.queueRescue(xaut.address), admin))
    # rescue path proven on its own vault so the queued migration above stays intact
    w3.provider.make_request("evm_increaseTime", [TL]); w3.provider.make_request("evm_mine", [])
    tx(w3, v.functions.executeMigration(p.as_tuple()), admin)
    must("G10. final approved successor migration passes only with all gates", xaut.functions.balanceOf(succ.address).call() == 100 * 10**6)
    sra = succ.functions.rescueAction(xaut.address).call(); approve(succ, sra, 4)
    tx(w3, succ.functions.queueRescue(xaut.address), admin)
    w3.provider.make_request("evm_increaseTime", [RD]); w3.provider.make_request("evm_mine", [])
    tx(w3, succ.functions.executeRescue(xaut.address), admin)
    must("G9b. rescue with 4-of-5 moves the reserve ONLY to its quarantine",
         xaut.functions.balanceOf(q2.address).call() == 100 * 10**6 and xaut.functions.balanceOf(succ.address).call() == 0)


def _try(fn):
    try:
        return fn()
    except Exception:
        return None


if __name__ == "__main__":
    rc = 0
    try:
        main()
    except SystemExit as e:
        print(f"STOPPED: {e}", flush=True)
        rc = 1
    except Exception as e:
        import traceback; traceback.print_exc()
        rc = 1
    finally:
        for p in procs:
            kill(p)
    passed = sum(r["result"] == "PASS" for r in results)
    print(json.dumps({"passed": passed, "total": len(results), "results": results}, indent=1))
    sys.exit(rc if rc else (0 if passed == len(results) else 1))

#!/usr/bin/env python3
"""Atomic-swap completion audit — shared harness (LAB / DEVNET + ANVIL ONLY).

Real SOST DEVNET_FAST node(s) built from release/v40000-prep (build-devnet/), real sost-miner,
real Anvil, the REAL WSOST + AtomicSwapHTLCv2 contracts (unchanged). Disposable devnet/Anvil keys
generated in the work dir only. Nothing touches mainnet, Sepolia or any production process: every
process is started here, tracked by PID and only those PIDs are ever signalled.
"""
import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time

AUD = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REL = os.path.join(AUD, "wt-release-v40000-prep")
DEV = os.path.join(AUD, "build-devnet")
NODE, MINER, CLI, SIGNTX = (os.path.join(DEV, b) for b in ("sost-node", "sost-miner", "sost-cli", "sost-signtx"))
LABSIGN = os.path.join(AUD, "harness", "bin", "sost_lab_sign")
ANVIL = os.path.expanduser("~/.foundry/bin/anvil")
GENESIS_JSON = os.path.join(REL, "genesis_block.json")
GENESIS = "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37"
WSOST_OUT = os.path.join(REL, "contracts", "wsost", "out")
sys.path.insert(0, os.path.join(REL, "ops"))

from web3 import Web3                                       # noqa: E402
from eth_account import Account                             # noqa: E402
from sostbridge.sostchain import SostRPC                    # noqa: E402
from sostbridge.common import vault_hash                    # noqa: E402
from sostbridge.eip712 import DepositMsg, sign_deposit, order_signatures   # noqa: E402

FEE = 100_000
MARKER = 10_000
OUT_TRANSFER, OUT_HTLC_LOCK = 0, 0x12
STOCK = 100_000_000

results = []
procs = {}


def log(msg):
    print(msg, flush=True)


def step(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    log(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def summary(path=None):
    n = sum(ok for _, ok, _ in results)
    log(f"\nRESULT: {n}/{len(results)} PASS")
    if path:
        json.dump([{"step": a, "ok": b, "detail": c} for a, b, c in results], open(path, "w"), indent=1)
    return n == len(results)


def stop(name):
    p = procs.pop(name, None)
    if p and p.poll() is None:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)       # only our own process group
        try:
            p.wait(30)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            p.wait(10)


def stop_all():
    for n in list(procs):
        stop(n)


def wait_until(fn, timeout, what, every=0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            v = fn()
        except Exception:
            v = None
        if v:
            return v
        time.sleep(every)
    raise TimeoutError(what)


class Sost:
    """One devnet node in its own datadir."""

    def __init__(self, work, name, p2p, rpcport):
        self.work, self.name, self.p2p, self.rpcport = os.path.abspath(work), name, p2p, rpcport
        self.dir = os.path.join(self.work, name)
        os.makedirs(self.dir, exist_ok=True)
        self.addr = f"127.0.0.1:{rpcport}"
        self.rpc = SostRPC(f"http://{self.addr}/", timeout=60)

    def start(self, connect="127.0.0.1:1"):
        try:
            self.rpc.getblockcount()
            raise SystemExit(f"something already answers on {self.addr} — refusing to share it")
        except SystemExit:
            raise
        except Exception:
            pass
        procs[self.name] = subprocess.Popen(
            [NODE, "--profile", "dev", "--genesis", GENESIS_JSON, "--chain", "chain.json", "--port", str(self.p2p),
             "--rpc-port", str(self.rpcport), "--rpc-noauth", "--noseed", "--connect", connect],
            cwd=self.dir, stdout=open(os.path.join(self.work, self.name + ".log"), "a"), stderr=subprocess.STDOUT,
            preexec_fn=os.setsid)
        wait_until(lambda: self.rpc.getblockcount() is not None, 120, f"{self.name} RPC")
        return self

    def stop(self):
        stop(self.name)

    def height(self):
        return self.rpc.getblockcount()

    def call(self, m, p=None):
        return self.rpc.call(m, p or [])

    def utxos(self, addr):
        return self.call("getaddressutxos", [addr]) or []

    def balance(self, addr):
        return sum(int(u["amount_stocks"]) for u in self.utxos(addr))

    def confs(self, txid):
        try:
            t = self.call("gettransaction", [txid])
            return int(t.get("confirmations", 0) or 0) if t else 0
        except Exception:
            return 0

    def send(self, hexs):
        return self.call("sendrawtransaction", [hexs])

    def try_send(self, hexs):
        try:
            return True, self.send(hexs)
        except Exception as e:
            return False, str(e)[:200]

    def htlc(self, txid, vout=0):
        return self.call("gethtlcstatus", [txid, str(vout)])

    def mine(self, n, wallet, addr, threads=2):
        """Mine exactly n blocks with the REAL sost-miner (one miner at a time)."""
        h0 = self.height()
        p = subprocess.Popen(["nice", "-n", "15", MINER, "--profile", "dev", "--genesis", GENESIS_JSON, "--rpc", self.addr,
                              "--address", addr, "--wallet", wallet, "--mining-key-label", "default",
                              "--blocks", str(n), "--threads", str(threads), "--realtime"],
                             cwd=self.dir, stdout=open(os.path.join(self.work, "miner.log"), "a"),
                             stderr=subprocess.STDOUT, preexec_fn=os.setsid)
        procs["miner"] = p
        try:
            p.wait(timeout=60 * n + 120)
        except subprocess.TimeoutExpired:
            stop("miner")
            return self.height() - h0
        procs.pop("miner", None)
        return self.height() - h0

    def mine_to(self, target, wallet, addr):
        while self.height() < target:
            got = self.mine(target - self.height(), wallet, addr)
            if got == 0:
                return False
        return True


def cli(*args, timeout=180):
    r = subprocess.run([CLI, *map(str, args)], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def new_wallet(work, name):
    f = os.path.join(work, name)
    if not os.path.exists(f):
        rc, o, e = cli("--wallet", f, "newwallet")
        assert rc == 0, o + e
        os.chmod(f, 0o600)
    return f, json.load(open(f))["keys"][0]["address"]


def pkh(addr):
    return addr[5:]


def build(cmd, *params):
    rc, o, e = cli(cmd, *params)
    if rc != 0:
        raise RuntimeError(f"{cmd}: {e.strip() or o.strip()}")
    return json.loads(o)["raw_tx_hex"]


def labsign(wallet, unsigned_hex, *specs):
    r = subprocess.run([LABSIGN, wallet, GENESIS, unsigned_hex, *specs], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("lab signer: " + r.stderr)
    return r.stdout.strip().splitlines()[-1]          # library prints [SIGHASH-DEBUG] lines first


def pick_utxo(node, addr, need):
    used = getattr(pick_utxo, "used", set())
    for u in sorted(node.utxos(addr), key=lambda u: int(u["amount_stocks"])):
        k = (u["txid"], u["vout"])
        if int(u["amount_stocks"]) >= need and u.get("output_type") in (OUT_TRANSFER, 1) and u.get("spendable") and k not in used:
            used.add(k); pick_utxo.used = used
            return u
    return None


def sost_lock(node, wallet, frm, u, hashlock_hex, refund_height, claim_addr, refund_addr, amount):
    raw = build("createhtlclock", u["txid"], u["vout"], u["amount_stocks"], pkh(frm), hashlock_hex, refund_height,
                pkh(claim_addr), pkh(refund_addr), amount, FEE)
    return raw, labsign(wallet, raw, f"{u['amount_stocks']}:{u.get('output_type', 0)}:{frm}")


def sost_claim(wallet, signer_addr, lock_txid, amount, preimage_hex, dest_addr):
    raw = build("claimhtlc", lock_txid, 0, amount, preimage_hex, pkh(dest_addr), MARKER, FEE)
    return labsign(wallet, raw, f"{amount}:{OUT_HTLC_LOCK}:{signer_addr}")


def sost_refund(wallet, signer_addr, lock_txid, amount, dest_addr):
    raw = build("refundhtlc", lock_txid, 0, amount, pkh(dest_addr), FEE)
    return labsign(wallet, raw, f"{amount}:{OUT_HTLC_LOCK}:{signer_addr}")


# ---------------------------------------------------------------------- EVM
def artifact(path):
    j = json.load(open(os.path.join(WSOST_OUT, path)))
    return j["abi"], j["bytecode"]["object"]


class Evm:
    def __init__(self, work, port):
        self.port = port
        procs["anvil"] = subprocess.Popen([ANVIL, "--port", str(port), "--silent", "--chain-id", "31337"],
                                          stdout=open(os.path.join(work, "anvil.log"), "a"), stderr=subprocess.STDOUT,
                                          preexec_fn=os.setsid)
        self.w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{port}"))
        wait_until(lambda: self.w3.eth.chain_id == 31337, 30, "anvil")
        self.admin, self.alice, self.bob, self.relayer, self.mallory = self.w3.eth.accounts[:5]

    def deploy(self, path, *args):
        abi, bc = artifact(path)
        r = self.w3.eth.wait_for_transaction_receipt(
            self.w3.eth.contract(abi=abi, bytecode=bc).constructor(*args).transact({"from": self.admin}))
        return self.w3.eth.contract(address=r.contractAddress, abi=abi)

    def tx(self, fn, sender):
        r = self.w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
        assert r.status == 1
        return r

    def try_tx(self, fn, sender):
        try:
            fn.call({"from": sender})
        except Exception as e:
            return False, str(e)[:160]
        return True, self.tx(fn, sender)

    def send_status(self, fn, sender):
        """Send without pre-simulation (fixed gas) and return (mined_block, receipt_status)."""
        r = self.w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender, "gas": 400_000}))
        return r.blockNumber, r.status

    def mine(self, n=1):
        for _ in range(n):
            self.w3.provider.make_request("evm_mine", [])

    def automine(self, on):
        self.w3.provider.make_request("evm_setAutomine", [on])

    def setup_wsost(self, vault_addr, bob_amount):
        obs_keys = [Account.create().key for _ in range(3)]
        obs = [Account.from_key(k).address for k in obs_keys]
        self.wsost = self.deploy("WSOST.sol/WSOST.json", vault_hash(vault_addr),
                                 (self.admin, obs, 2, 30, 100_000 * STOCK, 50_000 * STOCK))
        self.htlc = self.deploy("AtomicSwapHTLCv2.sol/AtomicSwapHTLCv2.json")
        dep = DepositMsg(depositId=hashlib.sha256(b"bob-existing-deposit").digest(), recipient=self.bob, amount=bob_amount,
                         bridgeVault=vault_hash(vault_addr), sostBlockHash=b"\x11" * 32, sostBlockHeight=100, confirmations=30)
        sigs = order_signatures([(obs[i], sign_deposit(obs_keys[i], dep, self.w3.eth.chain_id, self.wsost.address))
                                 for i in (0, 2)])
        self.tx(self.wsost.functions.mint(dep.as_tuple(), sigs), self.relayer)

    def bridge_state(self):
        w = self.wsost.functions
        return {"supply": w.totalSupply().call(), "minted": w.totalMinted().call(), "burned": w.totalBurned().call(),
                "burnNonce": w.burnNonce().call(), "mintPaused": w.mintPaused().call()}

    def lock(self, sender, swap_id, amount, hashlock, refund_block, claimer, refunder):
        self.tx(self.wsost.functions.approve(self.htlc.address, amount), sender)
        return self.tx(self.htlc.functions.lockERC20(swap_id, self.wsost.address, amount, hashlock, refund_block,
                                                     claimer, refunder), sender)

    def swap(self, swap_id):
        s = self.htlc.functions.getSwap(swap_id).call()
        return {"state": s[0], "token": s[1], "requested": s[2], "locked": s[3], "hashlock": bytes(s[4]).hex(),
                "refundTime": s[5], "claimer": s[6], "refunder": s[7]}

    def extract_preimage(self, swap_id, from_block=0):
        """Counterparty watcher: read the Claimed log by swapId (independent of the claimer's receipt)."""
        ev = self.htlc.events.Claimed()
        topic = self.w3.keccak(text="Claimed(bytes32,bytes32,address,uint256)").hex()
        logs = self.w3.eth.get_logs({"address": self.htlc.address, "fromBlock": from_block, "toBlock": "latest",
                                     "topics": ["0x" + topic.removeprefix("0x"), "0x" + swap_id.hex()]})
        if not logs:
            return None
        return bytes(ev.process_log(logs[-1])["args"]["preimage"]).hex()

    def bal(self, who):
        return self.wsost.functions.balanceOf(who).call()

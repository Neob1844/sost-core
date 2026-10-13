#!/usr/bin/env python3
"""Stage 2 REAL capsule E2E — no simulated SOST side.

SOST side: a running DEVNET_FAST node with capsules active (>= 7,350, or >= 300 on the capsule-fast
devnet: tests/bridge/run_capsule_fast_devnet.py), real transactions built
with `sost-cli buildtx` (watch-only), signed with `sost-cli signtx` (offline, v1 and encrypted v2) and
broadcast with sendrawtransaction. Observers, ledger and governance read the real node.
EVM side: Anvil by default; any EVM RPC (e.g. Sepolia) with --eth-rpc and a funded --eth-key-file.
With --deployment (JSON from tests/bridge/sepolia_stage2_deploy.py) the run uses that ALREADY-DEPLOYED
WSOST, its test observer keys (--observer-keys) and its Bridge Vault wallet (--vault-wallet), and skips the
unbacked-mint CRITICAL drill (it would leave permanent unbacked supply and a mint pause on a shared
contract; that drill runs on Anvil). --gas-out writes every EVM receipt used by the run.

  python3 tests/bridge/e2e_real_capsule.py --cli <sost-cli with buildtx> --work DIR [--min-conf 30]
  DIR: devnet wallets alice.json (funded), bob.json. A fresh Bridge Vault wallet is created per run.
"""
import argparse
import dataclasses
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "ops"))

from eth_account import Account
from web3 import Web3

from sostbridge.common import (to_stocks, fmt_sost, vault_hash, deposit_id, parse_open_note, parse_wsost_recipient,
                               release_note, parse_release)
from sostbridge.sostchain import SostRPC
from sostbridge.ethside import Web3WSOST
from sostbridge.observer import Observer, ObserverConfig, Attestation, collect, still_canonical
from sostbridge.ledger import scan_vault, reconcile, BALANCED, PENDING, CRITICAL
from sostbridge.signer import ReleaseProcessor, ReleaseJournal, ReleaseSigner, ReleaseRequest
from sostbridge.eip712 import sign_deposit
from sostbridge.governance import Proposal, tally

GENESIS = "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37"
OUT = os.path.join(ROOT, "contracts", "wsost", "out")
FEE_ALLOWANCE = to_stocks("0.001")
results, procs = [], []


def step(name, ok, detail=""):
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def must(name, ok, detail=""):
    if not step(name, ok, detail):
        finish()


def finish():
    for p in procs:
        if p.poll() is None:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    n = sum(results)
    print(f"\nRESULT: {n}/{len(results)} PASS", flush=True)
    sys.exit(0 if n == len(results) else 1)


class OfflinePipelineSigner(ReleaseSigner):
    """Release signer with the key on an OFFLINE machine: buildtx (online, watch-only) ->
    signtx (offline, cold vault wallet) -> sendrawtransaction (online). Here both halves run locally."""

    def __init__(self, cli, cold_wallet, vault, node, network, workdir, passphrase_file=None):
        self.cli, self.cold, self.vault, self.node, self.net, self.dir = cli, cold_wallet, vault, node, network, workdir
        self.pf = passphrase_file

    def execute_release(self, req: ReleaseRequest) -> str:
        tag = req.burn_id.hex()[:12]
        unsigned, signed = os.path.join(self.dir, f"rel-{tag}.json"), os.path.join(self.dir, f"rel-{tag}.hex")
        b = subprocess.run([self.cli, "--node", self.node, "--from-address", self.vault, "--capsule-mode", "open-note",
                            "--capsule-text", release_note(req.burn_id), "buildtx", req.dest, fmt_sost(req.amount),
                            "--network", self.net, "--out", unsigned], capture_output=True, text=True, timeout=180)
        if b.returncode:
            raise RuntimeError("buildtx: " + b.stderr[-300:])
        extra = ["--passphrase-file", self.pf] if self.pf else []
        s = subprocess.run([self.cli, "--wallet", self.cold, "signtx", unsigned, "--network", self.net, "--yes", "--out", signed, *extra],
                           capture_output=True, text=True, timeout=180)
        if s.returncode:
            raise RuntimeError("signtx: " + s.stderr[-300:])
        r = subprocess.run([self.cli, "--node", self.node, "sendrawtransaction", open(signed).read().strip()],
                           capture_output=True, text=True, timeout=60)
        m = re.findall(r"[0-9a-f]{64}", r.stdout)
        if r.returncode or not m:
            raise RuntimeError("broadcast: " + (r.stdout + r.stderr)[-300:])
        return m[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--rpc", default="127.0.0.1:18655")
    ap.add_argument("--min-conf", type=int, default=30)
    ap.add_argument("--eth-rpc")
    ap.add_argument("--eth-key-file")
    ap.add_argument("--deployment")                    # JSON with an already-deployed WSOST (e.g. Sepolia)
    ap.add_argument("--capsule-activation", type=int, default=7350)   # 300 on the capsule-fast devnet build
    ap.add_argument("--observer-keys")                 # with --deployment: JSON {"observers": [hex keys]}
    ap.add_argument("--vault-wallet")                  # with --deployment: Bridge Vault wallet bound in the contract
    ap.add_argument("--gas-out")
    a = ap.parse_args()
    CLI, W, NODE, MINC = os.path.abspath(a.cli), a.work, a.rpc, a.min_conf
    tmp = tempfile.mkdtemp(prefix="sost-realcap-"); os.chmod(tmp, 0o700)
    rpc = SostRPC(f"http://{NODE}/")
    gaslog = []

    def raw_rpc(m, p):
        return rpc.call(m, p)

    def wallet_addr(name):
        f = os.path.join(W, name)
        if not os.path.exists(f):
            subprocess.run([CLI, "--wallet", f, "newwallet"], capture_output=True)
        return json.load(open(f))["keys"][0]["address"]

    def wait(fn, t, what, every=2.0):
        t0 = time.time()
        while time.time() - t0 < t:
            try:
                v = fn()
            except Exception:
                v = None
            if v:
                return v
            time.sleep(every)
        must(f"timeout waiting for {what}", False)

    def confirmed(txid, n=1):
        r = raw_rpc("gettransaction", [txid]) or {}
        return int(r.get("confirmations", 0) or 0) >= n

    def offline_send(src_wallet, src_addr, to, amount, capsule=None, extra_sign=(), tag=None, patch=None):
        """buildtx (watch-only) -> signtx (offline) -> broadcast. Returns (txid|None, error, review_text)."""
        tag = tag or secrets.token_hex(4)
        u, s = os.path.join(tmp, f"{tag}.json"), os.path.join(tmp, f"{tag}.hex")
        cap = ["--capsule-mode", "open-note", "--capsule-text", capsule] if capsule is not None else []
        b = subprocess.run([CLI, "--node", NODE, "--from-address", src_addr, *cap, "buildtx", to, amount, "--network", "dev", "--out", u],
                           capture_output=True, text=True, timeout=180)
        if b.returncode:
            return None, b.stderr.strip(), ""
        if patch:
            j = json.load(open(u)); j["unsigned_hex"] = patch(j["unsigned_hex"]); json.dump(j, open(u, "w"))
        sg = subprocess.run([CLI, "--wallet", os.path.join(W, src_wallet), "signtx", u, "--network", "dev", "--yes", "--out", s, *extra_sign],
                            capture_output=True, text=True, timeout=180)
        if sg.returncode:
            return None, sg.stderr.strip(), sg.stdout
        try:
            return raw_rpc("sendrawtransaction", [open(s).read().strip()]), "", sg.stdout
        except Exception as e:
            return None, str(e), sg.stdout

    tip = rpc.getblockcount()
    must(f"C0. devnet at or above capsule activation ({a.capsule_activation:,})", tip >= a.capsule_activation, f"height {tip}")
    alice, bob = wallet_addr("alice.json"), wallet_addr("bob.json")
    vault_name = f"vault-real-{int(time.time())}.json"
    if a.deployment:
        open(os.path.join(W, vault_name), "w").write(open(a.vault_wallet).read()); os.chmod(os.path.join(W, vault_name), 0o600)
    vault = wallet_addr(vault_name)
    step("parties", True, f"Alice {alice[:14]}… · fresh Bridge Vault {vault[:14]}…")

    # encrypted v2 copy of Alice's wallet for the offline signer (passphrase only in a 0600 file)
    PASS = "real capsule e2e 2026"
    pf = os.path.join(tmp, "alice.pass"); open(pf, "w").write(PASS + "\n"); os.chmod(pf, 0o600)
    alice_v2 = os.path.join(tmp, "alice.v2.json")
    subprocess.run(["bash", "-c", f'exec 3<"{pf}"; "{CLI}" --wallet "{os.path.join(W, "alice.json")}" wallet-export --encrypted --output "{alice_v2}" --passphrase-fd 3'], capture_output=True)
    shutil_copy = lambda s, d: open(d, "w").write(open(s).read())
    shutil_copy(alice_v2, os.path.join(W, "alice.v2.json")); os.chmod(os.path.join(W, "alice.v2.json"), 0o600)

    # ================================================================ A. plain open note (real CLI capsule bytes)
    note = "SOST real capsule test " + secrets.token_hex(3)
    txA, e, review = offline_send("alice.json", alice, bob, "1", capsule=note, tag="A")
    must("A. open-note capsule tx built (buildtx), signed offline (signtx), accepted", bool(txA), e[:120])
    step("   offline review showed the capsule text + hash", note in review and "sha256" in review)
    wait(lambda: confirmed(txA), 300, "A confirmation")
    vA = [o for o in raw_rpc("gettransaction", [txA])["vout"] if o.get("payload_hex")]
    step("H. confirmed; capsule read back from the node and parsed by the bridge parser",
         len(vA) == 1 and parse_open_note(vA[0]["payload_hex"]) == note, f"payload {vA[0]['payload_hex'][:40]}…" if vA else "")

    # ================================================================ EVM side
    if a.eth_rpc:
        w3 = Web3(Web3.HTTPProvider(a.eth_rpc))
        acct = Account.from_key(open(a.eth_key_file).read().strip())
        must("EVM RPC is NOT Ethereum mainnet", w3.eth.chain_id != 1, f"chainId {w3.eth.chain_id}")
        sender = acct.address
        nonce = [w3.eth.get_transaction_count(sender, "pending")]     # public RPCs are load-balanced and lag
        def settle(bn, n=3):
            """Load-balanced RPC: reads after a write may hit a lagging backend. Wait until n consecutive
            requests report the receipt's block, then a short grace period."""
            ok, t0 = 0, time.time()
            while ok < n and time.time() - t0 < 120:
                ok = ok + 1 if w3.eth.block_number >= bn else 0
                time.sleep(1)
            time.sleep(3)
        def send(fn, label=None):
            tx = fn.build_transaction({"from": sender, "nonce": nonce[0], "chainId": w3.eth.chain_id})
            tx["gas"] = int(w3.eth.estimate_gas({k: tx[k] for k in ("from", "to", "data")}) * 1.25)
            h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
            nonce[0] += 1
            r = w3.eth.wait_for_transaction_receipt(h, timeout=600)
            settle(r.blockNumber)
            gaslog.append({"op": label or fn.fn_name, "tx": "0x" + h.hex().removeprefix("0x"), "block": r.blockNumber,
                           "status": r.status, "gasUsed": r.gasUsed, "effectiveGasPriceWei": r.effectiveGasPrice})
            if a.gas_out:
                json.dump(gaslog, open(a.gas_out, "w"), indent=1)
            assert r.status == 1, "tx reverted"; return r
        juan_eth = sender
    else:
        procs.append(subprocess.Popen([os.path.expanduser("~/.foundry/bin/anvil"), "--port", "8550", "--silent"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid))
        w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8550"))
        wait(lambda: w3.eth.chain_id, 30, "anvil")
        sender, juan_eth = w3.eth.accounts[0], w3.eth.accounts[1]
        def send(fn, frm=None, label=None):
            r = w3.eth.wait_for_transaction_receipt(fn.transact({"from": frm or sender})); assert r.status == 1; return r
    j = json.load(open(os.path.join(OUT, "WSOST.sol/WSOST.json")))
    if a.deployment:
        dep = json.load(open(a.deployment))
        must("deployment file is for this chain", dep["chainId"] == w3.eth.chain_id, f"chainId {w3.eth.chain_id}")
        obs_keys = [bytes.fromhex(k.removeprefix("0x")) for k in json.load(open(a.observer_keys))["observers"]]
        obs = [Account.from_key(k).address for k in obs_keys]
        wsost = w3.eth.contract(address=dep["contracts"]["WSOST"]["address"], abi=j["abi"])
        eth = Web3WSOST(w3, wsost.address, j["abi"], from_block=dep["contracts"]["WSOST"]["block"])
        must("deployed WSOST is bound to this Bridge Vault, these observers, 2-of-3, %d confirmations" % MINC,
             bytes(wsost.functions.bridgeVault().call()) == vault_hash(vault) and wsost.functions.threshold().call() == 2
             and wsost.functions.minConfirmations().call() == MINC and all(wsost.functions.isObserver(o).call() for o in obs),
             f"{wsost.address} chainId {w3.eth.chain_id}")
        step("   clean start: supply 0, nothing minted or burned, mint not paused",
             wsost.functions.totalSupply().call() == 0 and wsost.functions.totalMinted().call() == 0
             and wsost.functions.totalBurned().call() == 0 and not wsost.functions.mintPaused().call())
    else:
        obs_keys = [Account.create().key for _ in range(3)]
        obs = [Account.from_key(k).address for k in obs_keys]
        C = w3.eth.contract(abi=j["abi"], bytecode=j["bytecode"]["object"])
        r = send(C.constructor(vault_hash(vault), (sender, obs, 2, MINC, to_stocks("100000"), to_stocks("50000"))))
        wsost = w3.eth.contract(address=r.contractAddress, abi=j["abi"])
        eth = Web3WSOST(w3, wsost.address, j["abi"])
        step("EVM: WSOST deployed for this run", True, f"{wsost.address} chainId {w3.eth.chain_id}")
    start = rpc.getblockcount()
    status = {"s": None}
    def reco():
        rr = reconcile(scan_vault(rpc, vault, start), eth, MINC, FEE_ALLOWANCE); status["s"] = rr.status; return rr
    cfg = ObserverConfig(vault=vault, start_height=start, min_confirmations=MINC, chain_id=w3.eth.chain_id, wsost=wsost.address)
    observers = [Observer(f"obs{i}", k, SostRPC(f"http://{NODE}/"), cfg, eth, status_fn=lambda: status["s"]) for i, k in enumerate(obs_keys)]

    # ================================================================ B. real bridge deposit (encrypted v2 offline signer)
    txB, e, review = offline_send("alice.v2.json", alice, vault, "100", capsule="WSOST:" + juan_eth, tag="B",
                                  extra_sign=("--passphrase-file", pf))
    must("B. bridge deposit 100 SOST + Ethereum-recipient capsule, signed offline with ENCRYPTED v2 wallet", bool(txB), e[:120])
    step("   passphrase never on a command line (file 0600)", oct(os.stat(pf).st_mode)[-3:] == "600")
    wait(lambda: scan_vault(rpc, vault, start).deposits, 300, "deposit inclusion")
    d = scan_vault(rpc, vault, start).deposits[0]
    bh = rpc.getblockhash(d.height)
    step("5. observer reads the REAL deposit: txid, vout, amount, recipient, block hash, height, confirmations",
         d.txid == txB and d.amount == to_stocks("100") and d.recipient == juan_eth and d.block_hash == bh and d.confirmations >= 1,
         f"txid {d.txid[:16]}… vout {d.vout} amount {fmt_sost(d.amount)} → {d.recipient[:10]}… h {d.height} conf {d.confirmations}")
    step("   deposit_id deterministic = keccak(SOST-WSOST-DEPOSIT-V1 || txid || vout)", d.deposit_id == deposit_id(d.txid, d.vout) == deposit_id(txB, d.vout))
    step("   before confirmations: PENDING and observers refuse", reco().status == PENDING and all(o.attest(d) is None for o in observers))
    wait(lambda: rpc.getblockcount() - d.height + 1 >= MINC, 1800, f"{MINC} confirmations", every=5)
    d = scan_vault(rpc, vault, start).deposits[0]
    atts = [o.attest(d) for o in observers]
    got = collect(atts, 2)
    must("   2-of-3 observers attest from the real node", got is not None and sum(x is not None for x in atts) == 3)
    msg, sigs = got
    must("   relayer pre-flight: deposit block still canonical", still_canonical(rpc, msg))
    # wrong recipient: the attested signatures do not cover another recipient
    bad = dataclasses.replace(msg, recipient=Account.create().address)
    try:
        send(wsost.functions.mint(bad.as_tuple(), sigs)); wr = False
    except Exception:
        wr = True
    step("   wrong recipient with valid signatures: mint reverts", wr)
    stale = dataclasses.replace(msg, sostBlockHash=b"\x77" * 32)
    step("   stale / reorged block hash: relayer pre-flight refuses", not still_canonical(rpc, stale))
    send(wsost.functions.mint(msg.as_tuple(), sigs), label="mint (wrap 100)")
    step("9. WRAP: 100 native SOST locked, 100 wSOST minted", wsost.functions.balanceOf(juan_eth).call() == to_stocks("100")
         and scan_vault(rpc, vault, start).vault_balance == to_stocks("100"))
    try:
        send(wsost.functions.mint(msg.as_tuple(), sigs)); dup = False
    except Exception:
        dup = True
    step("   duplicate mint authorization reverts", dup and all(o.attest(d) is None for o in observers))
    rr = reco()
    step("   reconciliation BALANCED", rr.status == BALANCED, json.dumps(rr.ledger)[:160])

    # ================================================================ C. governance vote capsule (real)
    snap = rpc.getblockcount()
    prop = Proposal("GRV2-REALTEST", "0x" + "11" * 20, "0x" + "22" * 20, "0x" + "33" * 20, "0x" + "44" * 20, b"\x55" * 32,
                    snap, snap + 40, 3600, "real capsule test")
    txC, e, _ = offline_send("alice.json", alice, alice, "0.5", capsule=f"SOSTGOV1|GRV2-REALTEST|S{snap}|YES", tag="C")
    step("C. governance vote capsule built + signed offline + accepted", bool(txC), e[:100])
    wait(lambda: confirmed(txC), 300, "vote confirmation")
    t = tally(rpc, prop, [alice, bob], 1)
    step("   governance tally reads the vote from the real chain", t.yes == 1 and t.final_votes.get(alice) == "YES", f"yes {t.yes} census {t.census}")

    # ================================================================ D/E/F. rejections
    def break_magic(h):
        b = bytearray(bytes.fromhex(h)); n = b[5]; o0 = 6 + 133 * n + 1
        b[o0 + 31] = 0x00                                           # first capsule byte: 'S' -> 0x00 (bad magic)
        return bytes(b).hex()
    txD, e, rev = offline_send("alice.json", alice, bob, "1", capsule="WSOST:" + juan_eth, tag="D", patch=break_magic)
    step("D. malformed capsule (bad magic) — offline signer flags it, node rejects", txD is None and bool(e) and "type -1" in rev, e[:100])
    r = subprocess.run([CLI, "--node", NODE, "--from-address", alice, "--capsule-mode", "open-note", "--capsule-text", "x" * 81,
                        "buildtx", bob, "1", "--network", "dev", "--out", os.path.join(tmp, "E.json")], capture_output=True, text=True)
    step("E. oversize capsule (81 > 80) refused before anything is built", r.returncode != 0 and not os.path.exists(os.path.join(tmp, "E.json")))
    u = os.path.join(tmp, "F.json"); s = os.path.join(tmp, "F.hex")
    subprocess.run([CLI, "--node", NODE, "--from-address", alice, "--capsule-mode", "open-note", "--capsule-text", "integrity",
                    "buildtx", bob, "1", "--network", "dev", "--out", u], capture_output=True)
    subprocess.run([CLI, "--wallet", os.path.join(W, "alice.json"), "signtx", u, "--network", "dev", "--yes", "--out", s], capture_output=True)
    sb = bytearray(bytes.fromhex(open(s).read().strip())); n = sb[5]; o0 = 6 + 133 * n + 1
    plen = int.from_bytes(sb[o0 + 29:o0 + 31], "little"); sb[o0 + 31 + plen - 1] ^= 0x20
    try:
        raw_rpc("sendrawtransaction", [bytes(sb).hex()]); rejF = ""
    except Exception as ex:
        rejF = str(ex)
    step("F. capsule mutated after signing: node rejects the signature", "E6" in rejF or "verif" in rejF.lower(), rejF[:90])
    try:
        okF = raw_rpc("sendrawtransaction", [open(s).read().strip()])
    except Exception:
        okF = None
    step("G. same offline-signed capsule tx unmodified: accepted", bool(okF))

    # ================================================================ 10. UNWRAP 40 — release signed offline from the cold vault wallet
    r = send(wsost.functions.burn(to_stocks("40"), alice), juan_eth) if not a.eth_rpc else send(wsost.functions.burn(to_stocks("40"), alice), label="burn (unwrap 40)")
    step("10. burn 40 wSOST on the EVM side", r.status == 1 and wsost.functions.totalSupply().call() == to_stocks("60"),
         f"supply {fmt_sost(wsost.functions.totalSupply().call())}")
    step("   release pending → PENDING", reco().status == PENDING)
    signer = OfflinePipelineSigner(CLI, os.path.join(W, vault_name), vault, NODE, "dev", tmp)
    proc = ReleaseProcessor(signer, ReleaseJournal(os.path.join(tmp, "journal.json")), rpc, vault, start, FEE_ALLOWANCE)
    a0 = sum(u_["amount_stocks"] for u_ in raw_rpc("getaddressutxos", [alice]))
    rel = proc.process(eth)
    step("   release built watch-only, signed OFFLINE by the vault wallet, broadcast", len(rel) == 1)
    step("   journal blocks a second release for the same burn", proc.process(eth) == [])
    wait(lambda: scan_vault(rpc, vault, start).releases and confirmed(rel[0]), 300, "release confirmation")
    rs = scan_vault(rpc, vault, start).releases[0]
    step("   release carries WSOST-RELEASE capsule, 40 SOST − fee allowance to Alice",
         rs.dest == alice and rs.amount == to_stocks("40") - FEE_ALLOWANCE and rs.txid == rel[0])
    rr = reco()
    sc = scan_vault(rpc, vault, start)
    step("11. FINAL: 60 wSOST outstanding, ≥ 60 SOST locked, every id reconciled → BALANCED",
         rr.status == BALANCED and wsost.functions.totalSupply().call() == to_stocks("60") and sc.vault_balance >= to_stocks("60"),
         f"locked {fmt_sost(sc.vault_balance)} SOST · supply {fmt_sost(wsost.functions.totalSupply().call())} · {json.dumps(rr.ledger)[:120]}")

    if a.deployment:
        print(f"FINAL_LOCKED_GROSS: {fmt_sost(sc.vault_balance)} SOST (vault UTXOs)\n"
              f"FINAL_BACKING_OWED: {fmt_sost(rr.ledger['owed'])} SOST (= wSOST supply + awaiting releases + unminted deposits)\n"
              f"FINAL_SURPLUS: {fmt_sost(rr.ledger['surplus'])} SOST (unused part of the release fee allowance)\n"
              f"FINAL_WSOST_SUPPLY: {fmt_sost(wsost.functions.totalSupply().call())} wSOST\n"
              f"LEDGER: {json.dumps(rr.ledger)}\n"
              "CRITICAL drill (unbacked mint → pause) not run on the shared Sepolia contract; covered on Anvil.", flush=True)
        finish()
    # unbacked mint by two compromised observers → CRITICAL (balance alone is not enough)
    from sostbridge.eip712 import DepositMsg, order_signatures
    fake = DepositMsg(b"\x99" * 32, juan_eth, to_stocks("1"), vault_hash(vault), bytes.fromhex(rpc.getblockhash(start)), start, MINC)
    fs = order_signatures([(obs[i], sign_deposit(obs_keys[i], fake, w3.eth.chain_id, wsost.address)) for i in (0, 1)])
    send(wsost.functions.mint(fake.as_tuple(), fs))
    rr = reco()
    step("   unbacked mint (2 compromised observers) while vault still over-collateralised → CRITICAL",
         rr.status == CRITICAL, "; ".join(rr.reasons)[:120])
    from sostbridge.ledger import enforce_safety
    paused = enforce_safety(rr, eth, sender)
    step("   CRITICAL → mint pause issued on the WSOST contract", paused and wsost.functions.mintPaused().call())
    step("   observers refuse every new attestation while CRITICAL", all(o.attest(d) is None and "CRITICAL" in o.log[-1] for o in observers),
         observers[0].log[-1])
    fake2 = DepositMsg(b"\x98" * 32, juan_eth, to_stocks("1"), vault_hash(vault), bytes.fromhex(rpc.getblockhash(start)), start, MINC)
    fs2 = order_signatures([(obs[i], sign_deposit(obs_keys[i], fake2, w3.eth.chain_id, wsost.address)) for i in (0, 1)])
    try:
        send(wsost.functions.mint(fake2.as_tuple(), fs2)); blocked = False
    except Exception:
        blocked = True
    step("   a further mint (even 2-of-3 signed) reverts while paused", blocked)
    sc = scan_vault(rpc, vault, start)
    print(f"FINAL_LOCKED: {fmt_sost(sc.vault_balance)} SOST (60 + release fee allowance; the vault paid the release network fee)\n"
          f"FINAL_WSOST_SUPPLY: {fmt_sost(wsost.functions.totalSupply().call())} wSOST (60 backed + 1 unbacked test mint → CRITICAL)", flush=True)
    finish()


if __name__ == "__main__":
    main()

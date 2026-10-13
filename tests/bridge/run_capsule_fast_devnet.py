#!/usr/bin/env python3
"""REAL DEVNET E2E — accelerated activation height (capsules at #300). Not a mainnet validation.

Drives a FRESH, isolated capsule-fast devnet built with
  -DSOST_DEVNET_FORKS=ON -DSOST_DEVNET_CAPSULE_FAST=ON  (branch devnet/capsule-fast-300)
own datadir, own ports, no peers. Then:
  1. activation boundary with the SAME signed bytes: rejected for block #299, accepted into block #300
  2. the CLI capsule gate and the Python bridge encoder agree byte for byte with the CLI capsule
  3. a REAL reorg (second node, longer competing chain) of a bridge deposit: observers and the
     relayer pre-flight refuse the stale statement
  4. runs tests/bridge/e2e_real_capsule.py (A-H, wrap 100 / unwrap 40, CRITICAL) against it

  python3 tests/bridge/run_capsule_fast_devnet.py --bin <build-cfast> --work <new empty dir>
"""
import argparse
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

from sostbridge.common import build_open_note, to_stocks, deposit_id
from sostbridge.sostchain import SostRPC
from sostbridge.observer import Observer, ObserverConfig, still_canonical
from sostbridge.ledger import scan_vault

ACT = 300
results = []
procs = {}


def step(name, ok, detail=""):
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def stop(name):
    p = procs.pop(name, None)
    if p and p.poll() is None:
        os.kill(p.pid, signal.SIGTERM)               # by PID, never by name
        try:
            p.wait(60)
        except subprocess.TimeoutExpired:
            os.kill(p.pid, signal.SIGKILL); p.wait()


def finish(code=None):
    for n in list(procs):
        stop(n)
    n = sum(results)
    print(f"\nORCHESTRATOR: {n}/{len(results)} PASS", flush=True)
    sys.exit(code if code is not None else (0 if n == len(results) else 1))


def must(name, ok, detail=""):
    if not step(name, ok, detail):
        finish(1)


class NoEth:                                          # observers here only need deposit_used()
    def deposit_used(self, _):
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--genesis", default=os.path.join(ROOT, "genesis_block.json"))
    ap.add_argument("--rpc-port", type=int, default=18755)
    ap.add_argument("--p2p-port", type=int, default=19755)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--min-conf", type=int, default=30)
    ap.add_argument("--skip-e2e", action="store_true")
    # Sepolia: forwarded to e2e_real_capsule.py; --swap-signer also runs e2e_swap_sost_wsost.py on this devnet
    ap.add_argument("--eth-rpc")
    ap.add_argument("--eth-key-file")
    ap.add_argument("--deployment")
    ap.add_argument("--observer-keys")
    ap.add_argument("--vault-wallet")
    ap.add_argument("--test-keys")
    ap.add_argument("--gas-out-dir")
    ap.add_argument("--swap-signer")
    a = ap.parse_args()
    B, W = os.path.abspath(a.bin), os.path.abspath(a.work)
    NODE, MINER, CLI = (os.path.join(B, x) for x in ("sost-node", "sost-miner", "sost-cli"))
    if os.path.exists(W) and os.listdir(W):
        sys.exit(f"{W} is not empty — the capsule-fast devnet always starts from a fresh datadir")
    for d in ("A", "B", "tx"):
        os.makedirs(os.path.join(W, d), exist_ok=True)
    os.chmod(W, 0o700)
    RA, RB = f"127.0.0.1:{a.rpc_port}", f"127.0.0.1:{a.rpc_port + 1}"
    PA, PB = a.p2p_port, a.p2p_port + 1
    rpcA, rpcB = SostRPC(f"http://{RA}/"), SostRPC(f"http://{RB}/")
    try:
        rpcA.getblockcount(); sys.exit(f"something already answers on {RA} — refusing to share it")
    except SystemExit:
        raise
    except Exception:
        pass

    def log(name):
        return open(os.path.join(W, name + ".log"), "a")

    def start_node(name, datadir, p2p, rpcport, connect):
        procs[name] = subprocess.Popen([NODE, "--profile", "dev", "--genesis", a.genesis, "--chain", "chain.json",
                                        "--port", str(p2p), "--rpc-port", str(rpcport), "--rpc-noauth", "--connect", connect],
                                       cwd=os.path.join(W, datadir), stdout=log(name), stderr=subprocess.STDOUT)

    def wait_rpc(r, t=60):
        t0 = time.time()
        while time.time() - t0 < t:
            try:
                return r.getblockcount()
            except Exception:
                time.sleep(0.5)
        must("node RPC up", False)

    def mine(rpc_addr, n, rpc=None):
        """Mine exactly n blocks with the real miner (to Alice), wait for it to exit."""
        r = rpc or rpcA
        h0 = r.getblockcount()
        p = subprocess.Popen(["nice", "-n", "19", MINER, "--profile", "dev", "--genesis", a.genesis, "--rpc", rpc_addr,
                              "--address", alice, "--wallet", os.path.join(W, "alice.json"), "--mining-key-label", "default",
                              "--blocks", str(n), "--threads", str(a.threads), "--realtime"],
                             cwd=W, stdout=log("miner"), stderr=subprocess.STDOUT)
        procs["miner"] = p
        p.wait(); procs.pop("miner", None)
        h = r.getblockcount()
        must(f"   mined {n} block(s) → tip {h}", h == h0 + n, f"from {h0}")
        return h

    def cli(*args, timeout=180):
        return subprocess.run([CLI, *args], capture_output=True, text=True, timeout=timeout)

    def build(to, amount, capsule=None, rpc_addr=RA, tag=None):
        u = os.path.join(W, "tx", (tag or secrets.token_hex(4)) + ".json")
        cap = ["--capsule-mode", "open-note", "--capsule-text", capsule] if capsule is not None else []
        r = cli("--node", rpc_addr, "--from-address", alice, *cap, "buildtx", to, amount, "--network", "dev", "--out", u)
        return (u if r.returncode == 0 else None), (r.stdout + r.stderr)

    def sign(u, wallet="alice.json"):
        s = u[:-5] + ".hex"
        r = cli("--wallet", os.path.join(W, wallet), "signtx", u, "--network", "dev", "--yes", "--out", s)
        return (open(s).read().strip() if r.returncode == 0 else None), r.stdout + r.stderr

    def send(r, hexs):
        try:
            return r.call("sendrawtransaction", [hexs]), ""
        except Exception as e:
            return None, str(e)

    def add_capsule(u, payload_hex, fee_bump):
        """Insert a capsule into output 0 of an UNSIGNED buildtx file (fee raised by fee_bump to pay for the bytes)."""
        j = json.load(open(u)); b = bytes.fromhex(j["unsigned_hex"])
        n_in = b[5]; o0 = 6 + 133 * n_in + 1
        assert b[o0 + 29:o0 + 31] == b"\x00\x00", "output 0 already has a payload"
        amt = int.from_bytes(b[o0:o0 + 8], "little", signed=True) - fee_bump
        p = bytes.fromhex(payload_hex)
        b = b[:o0] + amt.to_bytes(8, "little", signed=True) + b[o0 + 8:o0 + 29] + len(p).to_bytes(2, "little") + p + b[o0 + 31:]
        j["unsigned_hex"] = b.hex(); j["fee"] += fee_bump; j["amount"] -= fee_bump
        j["capsule_mode"] = "open-note"; j["capsule_hex"] = payload_hex
        json.dump(j, open(u, "w"), indent=2)

    def tx_height(r, txid):
        try:
            return int((r.call("gettransaction", [txid]) or {}).get("block_height", -1))
        except Exception:
            return -1

    # ------------------------------------------------------------------ fresh network
    for w in ("alice.json", "bob.json"):
        r = cli("--wallet", os.path.join(W, w), "newwallet")
        must(f"wallet {w}", r.returncode == 0, (r.stdout + r.stderr)[-200:])
    alice = json.load(open(os.path.join(W, "alice.json")))["keys"][0]["address"]
    bob = json.load(open(os.path.join(W, "bob.json")))["keys"][0]["address"]
    start_node("nodeA", "A", PA, a.rpc_port, "127.0.0.1:1")
    h = wait_rpc(rpcA)
    must("capsule-fast devnet A: fresh chain at genesis, isolated (no peers)", h == 0, f"RPC {RA} P2P {PA} datadir {W}/A")
    print(f"--- mining to #{ACT - 2} (Alice is the miner; coinbase maturity 5 on DEVNET_FAST)", flush=True)
    mine(RA, ACT - 2)

    # ------------------------------------------------------------------ 1. activation boundary
    text = "SOST capsule boundary " + secrets.token_hex(3)
    u0, out = build(bob, "1", capsule=text, tag="gate298")
    step(f"CLI gate at tip {ACT - 2}: capsule build refused before activation", u0 is None and f"capsule activation ({ACT})" in out,
         out.strip().splitlines()[-1][:110] if out.strip() else "")
    u, out = build(bob, "1", tag="boundary")
    must("   plain buildtx (watch-only) for the boundary tx", u is not None, out[-120:])
    add_capsule(u, build_open_note(text), to_stocks("0.001"))
    signed, rev = sign(u)
    must("   capsule inserted before signing; signtx (offline, v1) shows it and signs", signed is not None and text in rev, rev[-160:])
    txid, err = send(rpcA, signed)
    step(f"FAST_DEVNET_{ACT - 1}: valid Capsule v1 tx for block #{ACT - 1} → REJECT (R14, not yet active)",
         txid is None and "before capsule activation" in err, err[:120])
    mp = rpcA.call("getmempoolinfo", [])
    step("   not in the mempool", int((mp or {}).get("size", 0)) == 0)
    mine(RA, 1)                                                   # tip 299 → next block is 300
    txid, err = send(rpcA, signed)                                 # the SAME signed bytes
    step(f"   same signed bytes for block #{ACT}: accepted by the mempool", bool(txid), err[:120])
    mine(RA, 1)
    hB = tx_height(rpcA, txid) if txid else -1
    step(f"FAST_DEVNET_{ACT}: the capsule tx is confirmed IN block #{ACT}", hB == ACT, f"txid {str(txid)[:16]}… block {hB}")
    vo = [o for o in rpcA.call("gettransaction", [txid])["vout"] if o.get("payload_hex")] if txid else []
    step("   capsule read back from the node matches the signed bytes", len(vo) == 1 and vo[0]["payload_hex"] == build_open_note(text))

    u2, out = build(bob, "1", capsule=text, tag="cli300")
    cap_cli = json.load(open(u2))["capsule_hex"] if u2 else ""
    step(f"CLI gate at tip {ACT}: capsule build allowed; CLI capsule bytes == bridge encoder bytes", bool(u2) and cap_cli == build_open_note(text),
         cap_cli[:40] + "…")
    s2, _ = sign(u2) if u2 else (None, "")
    t2, err = send(rpcA, s2) if s2 else (None, "no tx")
    mine(RA, 1)
    step(f"   #{ACT + 1}+: normal capsule operation (CLI-built capsule confirmed at #{tx_height(rpcA, t2)})", tx_height(rpcA, t2) == ACT + 1, err[:80])

    # ------------------------------------------------------------------ 3. REAL reorg of a bridge deposit
    print("--- reorg test: node B syncs, goes offline, mines a longer competing chain", flush=True)
    mine(RA, 5)                                                    # mature a few more coinbases
    T = rpcA.getblockcount()
    start_node("nodeB", "B", PB, a.rpc_port + 1, f"127.0.0.1:{PA}")
    wait_rpc(rpcB)
    t0 = time.time()
    while time.time() - t0 < 120 and rpcB.getblockcount() < T:
        time.sleep(1)
    must("   node B synced from A over P2P", rpcB.getblockcount() == T and rpcB.getblockhash(T) == rpcA.getblockhash(T), f"tip {T}")
    stop("nodeB")
    vault2 = None
    cli("--wallet", os.path.join(W, "vault-reorg.json"), "newwallet")
    vault2 = json.load(open(os.path.join(W, "vault-reorg.json")))["keys"][0]["address"]
    rcpt = "0x" + secrets.token_hex(20)
    from web3 import Web3
    rcpt = Web3.to_checksum_address(rcpt)
    ur, out = build(vault2, "5", capsule="WSOST:" + rcpt, tag="reorg-deposit")
    sr, _ = sign(ur) if ur else (None, "")
    txR, err = send(rpcA, sr) if sr else (None, out)
    must("   bridge deposit (5 SOST + WSOST capsule) to a separate reorg-test vault", bool(txR), err[:100])
    mine(RA, 2)
    hR = tx_height(rpcA, txR)
    cfg = ObserverConfig(vault=vault2, start_height=T, min_confirmations=1, chain_id=31337, wsost="0x" + "00" * 20)
    obs = Observer("obsR", "0x" + "11" * 32, rpcA, cfg, NoEth())
    d = scan_vault(rpcA, vault2, T).deposits
    msg = obs.verify(d[0]) if d else None
    must("   observer statement for the deposit on A (block #%d, 2 conf)" % hR, msg is not None and d[0].txid == txR
         and d[0].deposit_id == deposit_id(txR, d[0].vout), obs.log[-1] if obs.log else "")
    hashA = rpcA.getblockhash(hR)
    step("   relayer pre-flight: statement canonical before the reorg", still_canonical(rpcA, msg))
    start_node("nodeB", "B", PB, a.rpc_port + 1, "127.0.0.1:1")      # B alone: never saw the deposit
    wait_rpc(rpcB)
    must("   node B restarted offline at the pre-deposit tip", rpcB.getblockcount() == T)
    mine(RB, 4, rpc=rpcB)                                          # T+4 > T+2
    # Deliver B's heavier branch to A IN ORDER through submitblock (A's real process_block / try_reorganize).
    # Not over P2P: the node's height-based GETB sync cannot fetch a competing branch below its own tip
    # (it asks from tip+1, stores the first block as an orphan, never re-processes it) — see the report.
    sub = []
    for hh in range(T + 1, T + 5):
        raw = rpcB.call("getrawblock", [rpcB.getblockhash(hh)])
        try:
            sub.append(rpcA.call("submitblock", [raw]))
        except Exception as e:
            sub.append(str(e)[:40])
    stop("nodeB")
    reorged = rpcA.getblockhash(hR) != hashA and rpcA.getblockcount() == T + 4
    must("   REAL REORG on node A: deposit block replaced by B's longer chain", reorged,
         f"#{hR} {hashA[:12]}… → {rpcA.getblockhash(hR)[:12]}… tip {rpcA.getblockcount()} · submitblock {sub}")
    h_after = tx_height(rpcA, txR)
    step("REORGANIZED DEPOSIT: relayer pre-flight refuses the stale statement", not still_canonical(rpcA, msg))
    obs.log.clear()
    step("   observer re-verification refuses (block moved / not confirmed / gone)", obs.verify(d[0]) is None,
         (obs.log[-1] if obs.log else "") + f" · deposit now at height {h_after}")

    if a.skip_e2e:
        finish()

    # ------------------------------------------------------------------ 4. full Stage 2 E2E on this devnet
    print("--- continuous mining + tests/bridge/e2e_real_capsule.py", flush=True)
    procs["miner"] = subprocess.Popen(["nice", "-n", "19", MINER, "--profile", "dev", "--genesis", a.genesis, "--rpc", RA,
                                       "--address", alice, "--wallet", os.path.join(W, "alice.json"), "--mining-key-label", "default",
                                       "--blocks", "1000000", "--threads", str(a.threads), "--realtime"],
                                      cwd=W, stdout=log("miner"), stderr=subprocess.STDOUT)
    # The reorg put the deposit back in A's mempool. buildtx now skips mempool-spent inputs
    # (getmempoolspends), but the test still waits for it to be mined again: it checks the re-mined block.
    t0 = time.time()
    while time.time() - t0 < 300 and tx_height(rpcA, txR) < 0:
        time.sleep(2)
    hR2 = tx_height(rpcA, txR)
    d2 = scan_vault(rpcA, vault2, T).deposits
    step("   reorged deposit re-mined on the new chain: new block, old statement still refused, fresh statement differs",
         hR2 > 0 and rpcA.getblockhash(hR2) != hashA and not still_canonical(rpcA, msg) and len(d2) == 1
         and d2[0].block_hash != msg.sostBlockHash.hex() and d2[0].deposit_id == msg.depositId,
         f"#{hR2} {rpcA.getblockhash(hR2)[:12] if hR2 > 0 else ''}… (deposit_id unchanged = txid:vout)")
    sep = []
    if a.deployment:
        sep = ["--eth-rpc", a.eth_rpc, "--eth-key-file", a.eth_key_file, "--deployment", a.deployment,
               "--observer-keys", a.observer_keys, "--vault-wallet", a.vault_wallet]
        if a.gas_out_dir:
            sep += ["--gas-out", os.path.join(a.gas_out_dir, "gas-bridge.json")]
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "bridge", "e2e_real_capsule.py"), "--cli", CLI, "--work", W,
                        "--rpc", RA, "--min-conf", str(a.min_conf), "--capsule-activation", str(ACT), *sep])
    step("tests/bridge/e2e_real_capsule.py on the capsule-fast devnet" + (" + Sepolia" if a.deployment else ""), r.returncode == 0)
    if a.swap_signer and r.returncode == 0:
        print("--- tests/bridge/e2e_swap_sost_wsost.py (SOST devnet HTLC <-> wSOST HTLCv2" + (" on Sepolia)" if a.deployment else ")"), flush=True)
        vault = json.load(open(a.vault_wallet))["keys"][0]["address"] if a.vault_wallet else None
        sw = [sys.executable, os.path.join(ROOT, "tests", "bridge", "e2e_swap_sost_wsost.py"), "--work", os.path.join(W, "swap"),
              "--signer", a.swap_signer, "--rpc-port", str(a.rpc_port), "--cli", CLI, "--funder-wallet", os.path.join(W, "alice.json")]
        if a.deployment:
            sw += ["--eth-rpc", a.eth_rpc, "--eth-key-file", a.eth_key_file, "--alice-eth-key-file", a.test_keys,
                   "--deployment", a.deployment, "--vault", vault]
            if a.gas_out_dir:
                sw += ["--gas-out", os.path.join(a.gas_out_dir, "gas-swap.json")]
        rs = subprocess.run(sw)
        step("tests/bridge/e2e_swap_sost_wsost.py on the same devnet", rs.returncode == 0)
    finish()


if __name__ == "__main__":
    main()

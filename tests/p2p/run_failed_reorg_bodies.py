#!/usr/bin/env python3
"""Failed reorg keeps the fork bodies (DEVNET_FAST V17=60, real sost-node + sost-miner).

Regression for the gate finding F1: when a reorg failed on an invalid block, the valid fork
blocks connected before it lost their stored bodies (process_block replaced their index entry
with a body-less ACTIVE entry and the rollback never put the body back). The next reorg onto
that branch then failed on the first prefix block, re-sent blocks were dropped as already
known, and the node stayed on its minority branch until restarted.

Every case builds, from one shared post-activation base (#60/#61 fund a 2-of-3 and a 3-of-5
multisig vault):

  R  target node on its own branch X;
  F  fork node: valid prefix A,B,C,... (cumulative work <= X, so no reorg on its own), then an
     invalid D on top, chosen so that work(prefix + D) > work(X): D triggers the reorg, the
     reorg connects the whole prefix and fails at D;
  Z  clean node that only ever syncs the winning chain (prefix + valid D').

and checks on R, with no restart: the reorg was attempted and failed at D by the intended rule;
R's tip, height, UTXO-set root (devchainstate), H/J/pending (getjackpotstate), supply, lottery
state and multisig vault UTXOs are unchanged; every prefix block still serves its exact stored
body (getrawblock); re-sending D changes nothing; a valid D' (only D', the prefix is not re-sent)
makes the branch win; R then equals Z and F (tip, UTXO root/count, H/J/pending, supply, lottery,
DEV jackpot accounting, vault UTXOs) and still does after a restart.

Failure causes of D:
  pow_bits     difficulty rule: valid PoW for bits_q + 1.0 (miner --dev-bits-q-delta) -> bits_q mismatch
  pow_target   PoW inequality: commit above the target of the claimed bits_q -> refused BEFORE
               storage, no reorg attempted
  cx           ConvergenceX: same-id copy with a round-witness value flipped -> CX transcript
               verification fails at connect; the bad body is evicted and the genuine block
               (same id) is the valid D'
  coinbase     V17 economics: miner output +1 stock (miner --attack-coinbase miner-plus)
  blocksize    V17 size: 1,000,001 serialized tx bytes (miner --dev-pad-to-bytes 1000001)
  multisig     V17 multisig: corrupted multisig signature in a 3-of-5 spend (miner --inject-tx-at1)

Variants: restart_before (R restarted after the failed reorg, before D'), p2p_reconnect (R is
connected to F with --connect; F goes away and comes back, D' arrives by relay).

Usage:
  python3 tests/p2p/run_failed_reorg_bodies.py --bin <devnet build> --work <new empty dir>
          [--base 34200] [--only pow_bits,cx]
Ports base..base+99. Every process this script starts is stopped by its recorded PID (argv[0]
checked); nothing else is ever signalled.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
V17 = 60
A = None
PROCS = {}
RESULTS = []
T0 = time.time()


def log(m):
    print(f"[{time.time() - T0:7.1f}s] {m}", flush=True)


def check(scn, name, ok, detail=""):
    RESULTS.append((scn, name, bool(ok), detail))
    log(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


# ------------------------------------------------------------------ processes
def spawn(argv, cwd, logf, niceness=15):
    p = subprocess.Popen(argv, cwd=cwd, stdout=open(logf, "a"), stderr=subprocess.STDOUT,
                         preexec_fn=lambda: os.nice(niceness))
    PROCS[p.pid] = (argv[0], p)
    return p


def kill_pid(pid, wait=60):
    ent = PROCS.get(pid)
    if not ent:
        return
    exe, p = ent
    if p.poll() is None:
        try:
            argv0 = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")[0].decode()
        except OSError:
            argv0 = ""
        if argv0 != exe:
            log(f"  !! refusing to signal pid {pid}: argv0={argv0!r}")
            PROCS.pop(pid, None)
            return
        os.kill(pid, signal.SIGTERM)
        try:
            p.wait(wait)
        except subprocess.TimeoutExpired:
            os.kill(pid, signal.SIGKILL)
            p.wait()
    PROCS.pop(pid, None)


def stop_all():
    for pid in list(PROCS):
        kill_pid(pid)


def memwait():
    t = time.time()
    while time.time() - t < 3600:
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemAvailable:"):
                if int(ln.split()[1]) >= 6 * 1024 * 1024:
                    return
        time.sleep(10)
    raise RuntimeError("less than 6 GB available for a devnet miner for 1 h")


# ------------------------------------------------------------------ exact chain work
_LUT = None


def _lut():
    global _LUT
    if _LUT is None:
        txt = open(os.path.join(ROOT, "src", "sostcompact_lut.inc")).read()
        rows = re.findall(r"\{((?:0x[0-9a-f]{2},?\s*){32})\}", txt)
        _LUT = [int("".join(b[2:] for b in re.findall(r"0x[0-9a-f]{2}", r)), 16) for r in rows]
        assert len(_LUT) == 256
    return _LUT


def target_from_bitsq(b):
    """Exact port of sost::target_from_bitsQ (src/sostcompact.cpp)."""
    M = (1 << 256) - 1
    if b <= 65536:
        return M
    if b >= 255 * 65536:
        return 0
    e, f = b >> 16, b & 0xFFFF
    i0 = f >> 8
    i1 = i0 + 1 if i0 < 255 else 255
    w = f & 0xFF
    v0, v1 = _lut()[i0], _lut()[i1]
    if w == 0:
        interp = v0
    else:
        delta = (v0 - v1) & M
        adj = ((delta * w) >> 8) & M          # mul_frac256_be: (v * w) / 256, top byte kept
        interp = (v0 - adj) & M
    return interp >> e if e else interp


def block_work(b):
    """Exact port of compute_block_work: floor(2^256 / (target + 1)), 1 when target is max."""
    t = target_from_bitsq(b)
    return 1 if t == (1 << 256) - 1 else (1 << 256) // (t + 1)


# ------------------------------------------------------------------ nodes
MAGIC_DEV = bytes([0x43, 0x58, 0x50, 0x4f, 0x57, 0x33, 0xf9, 0x50, 0xf9, 0x4b])


def block_id(j):
    u32 = lambda v: struct.pack("<I", int(v) & 0xFFFFFFFF)
    ver = int(j.get("version", 1) or 1)
    hdr = (MAGIC_DEV + b"HDR2" + bytes.fromhex(j["prev_hash"]) + bytes.fromhex(j["merkle_root"]) +
           u32(j["timestamp"]) + u32(j["bits_q"]) + bytes.fromhex(j["checkpoints_root"]) +
           u32(j["nonce"]) + u32(j["extra_nonce"]))
    if ver >= 2:
        hdr += u32(ver) + bytes.fromhex(j["miner_pubkey"]) + bytes.fromhex(j["miner_signature"])
    return hashlib.sha256(hdr + b"ID" + bytes.fromhex(j["commit"])).hexdigest()


class Node:
    def __init__(self, idx, name, root):
        self.idx, self.name = idx, name
        self.ip = f"127.0.0.{31 + idx}"
        self.p2p = A.base + idx
        self.rpcport = A.base + 50 + idx
        self.dir = os.path.join(root, name)
        self.logf = os.path.join(root, name + ".log")
        os.makedirs(self.dir, exist_ok=True)
        self.proc = None
        self.log_mark = 0

    @property
    def addr(self):
        return f"{self.ip}:{self.p2p}"

    @property
    def chain(self):
        return os.path.join(self.dir, "chain.json")

    def start(self, connect=("127.0.0.1:1",), iso=False):
        assert self.proc is None
        try:
            os.remove(os.path.join(self.dir, "peers.txt"))
        except FileNotFoundError:
            pass
        argv = [A.node_bin, "--profile", "dev", "--genesis", A.genesis,
                "--chain", self.chain, "--port", str(self.p2p + 20 if iso else self.p2p), "--rpc-port", str(self.rpcport),
                "--rpc-noauth", "--noseed", "--p2p-bind", self.ip]
        for c in connect:
            argv += ["--connect", c]
        with open(self.logf, "a") as f:
            f.write(f"\n===== start connect={list(connect)} iso={iso} t={time.time():.0f}\n")
        self.log_mark = os.path.getsize(self.logf)
        self.proc = spawn(argv, self.dir, self.logf)
        t0 = time.time()
        while time.time() - t0 < 120:
            try:
                self.height()
                return self
            except Exception:
                time.sleep(0.3)
        raise RuntimeError(f"{self.name}: RPC did not come up")

    def stop(self):
        if self.proc:
            kill_pid(self.proc.pid)
            self.proc = None

    def rpc(self, method, params=None, timeout=120):
        body = json.dumps({"method": method, "params": params or [], "id": 1}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.rpcport}/", data=body,
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        if d.get("error"):
            raise RuntimeError(f"{method}: {d['error']}")
        return d["result"]

    def submit(self, raw):
        try:
            self.rpc("submitblock", [raw])
            return True
        except Exception:
            return False

    def height(self):
        return int(self.rpc("getblockcount"))

    def tip(self):
        return self.rpc("getbestblockhash")

    def hash_at(self, h):
        return self.rpc("getblockhash", [h])

    def raw(self, bh):
        return self.rpc("getrawblock", [bh])

    def bits(self, h):
        return int(self.rpc("getblock", [self.hash_at(h)])["bits_q"])

    def work_above(self, h0):
        return sum(block_work(self.bits(h)) for h in range(h0 + 1, self.height() + 1))

    def logtext(self):
        with open(self.logf, "r", errors="replace") as f:
            f.seek(self.log_mark)
            return f.read()

    def state(self, vaults=()):
        cs = self.rpc("devchainstate")
        st = dict(tip=self.tip(), height=self.height(), utxo_root=cs.get("utxo_root"), utxo_count=cs.get("utxo_count"),
                  jackpot=self.rpc("getjackpotstate"), supply=self.rpc("getsupplyinfo"),
                  lottery=self.rpc("getlotterystate"), devjackpot=self.rpc("devjackpotstate"))
        for v in vaults:
            st["vault:" + v] = sorted((u.get("txid"), u.get("vout"), u.get("amount_stocks"), u.get("output_type"))
                                      for u in self.rpc("getaddressutxos", [v]))
        return st


def state_diff(a, b, ignore=("supply.uptime",)):
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            if isinstance(a.get(k), dict) and isinstance(b.get(k), dict):
                for kk in sorted(set(a[k]) | set(b[k])):
                    if a[k].get(kk) != b[k].get(kk) and f"{k}.{kk}" not in ignore:
                        out.append(f"{k}.{kk}: {a[k].get(kk)!r} != {b[k].get(kk)!r}")
            else:
                out.append(f"{k}: {str(a.get(k))[:80]} != {str(b.get(k))[:80]}")
    return out


def addr_of(wallet):
    return json.load(open(wallet))["keys"][0]["address"]


def mine(node, n, wallet, extra=(), expect_accept=True, tag="miner"):
    memwait()
    h0 = node.height()
    argv = [os.path.join(A.bin, "sost-miner"), "--profile", "dev", "--genesis", A.genesis,
            "--rpc", f"127.0.0.1:{node.rpcport}", "--address", addr_of(wallet), "--wallet", wallet,
            "--mining-key-label", "default", "--blocks", str(n), "--threads", str(A.threads), "--realtime"]
    argv += list(extra)
    p = spawn(argv, os.path.dirname(node.dir), os.path.join(os.path.dirname(node.dir), f"{tag}.log"))
    try:
        rc = p.wait(900)
    except subprocess.TimeoutExpired:
        kill_pid(p.pid)
        raise RuntimeError(f"{node.name}: miner timeout")
    PROCS.pop(p.pid, None)
    if expect_accept and node.height() != h0 + n:
        raise RuntimeError(f"{node.name}: mined {node.height() - h0} != {n}")
    return rc


def cli(*args, check_rc=True):
    r = subprocess.run([os.path.join(A.bin, "sost-cli")] + list(args), capture_output=True, text=True)
    if check_rc and r.returncode:
        raise RuntimeError(f"sost-cli {' '.join(args[:3])}: {r.stdout[-300:]} {r.stderr[-300:]}")
    return r


def copy_snapshot(src, node):
    for f in os.listdir(src):
        if os.path.isfile(os.path.join(src, f)) and f != "peers.txt":
            shutil.copy2(os.path.join(src, f), os.path.join(node.dir, f))


# ------------------------------------------------------------------ base chain
def build_base():
    d = os.path.join(A.work, "_base")
    n = Node(49, "base", d)
    W = A.work
    for w in ("wa", "wb", "s1", "s2", "s3", "s4", "s5", "rcp"):
        cli("--wallet", os.path.join(W, w + ".json"), "newwallet")
    pk = {i: cli("--wallet", os.path.join(W, f"s{i}.json"), "getpubkey").stdout.strip() for i in range(1, 6)}
    cli("createmultisig", "2", pk[1], pk[2], pk[3], "--network", "dev", "--out", os.path.join(W, "pol23.json"))
    cli("createmultisig", "3", pk[1], pk[2], pk[3], pk[4], pk[5], "--network", "dev", "--out", os.path.join(W, "pol35.json"))
    A.v23 = json.load(open(os.path.join(W, "pol23.json")))["address"]
    A.v35 = json.load(open(os.path.join(W, "pol35.json")))["address"]
    n.start()
    mine(n, V17 - 1 - n.height(), A.wa, tag="miner_base")                  # tip 59
    rpc = f"127.0.0.1:{n.rpcport}"
    for pol, amt, tag in ((A.v23, "3", "f23"), (A.v35, "5", "f35")):
        cli("--node", rpc, "--from-address", addr_of(A.wa), "buildtx", pol, amt,
            "--out", os.path.join(W, tag + ".json"), "--network", "dev", "--allow-before-activation")
        cli("--wallet", A.wa, "signtx", os.path.join(W, tag + ".json"), "--out", os.path.join(W, tag + "s.json"),
            "--network", "dev", "--yes")
        hx = json.load(open(os.path.join(W, tag + "s.json")))["final_hex"]
        n.rpc("sendrawtransaction", [hx])
        mine(n, 1, A.wa, tag="miner_base")                                  # 60, 61
    mine(n, 2, A.wa, tag="miner_base")                                      # 62, 63
    v23 = n.rpc("getaddressutxos", [A.v23]); v35 = n.rpc("getaddressutxos", [A.v35])
    if len(v23) != 1 or len(v35) != 1:
        raise RuntimeError(f"vault funding failed: {v23} {v35}")
    log(f"base: tip {n.height()} {n.tip()[:16]}, 2-of-3 {A.v23[:20]}.. and 3-of-5 {A.v35[:20]}.. funded")
    # Pre-built multisig spends: a VALID 2-of-3 spend (goes into the fork prefix) and a 3-of-5
    # spend whose signature is corrupted (the multisig-invalid D carries it).
    def spend(pol, signers, out):
        cli("--node", rpc, "buildtx", "--from-multisig", os.path.join(W, pol), addr_of(os.path.join(W, "rcp.json")), "1",
            "--out", os.path.join(W, out + ".json"), "--network", "dev")
        parts = []
        for s in signers:
            p = os.path.join(W, f"{out}_{s}.json")
            cli("--wallet", os.path.join(W, s + ".json"), "signtx", os.path.join(W, out + ".json"), "--out", p,
                "--network", "dev", "--yes")
            parts.append(p)
        cli("combinetx", *parts, "--out", os.path.join(W, out + "_x.json"))
        return json.load(open(os.path.join(W, out + "_x.json")))
    A.sp23 = spend("pol23.json", ["s1", "s3"], "sp23")
    sp35 = spend("pol35.json", ["s2", "s4", "s5"], "sp35")
    hx = sp35["final_hex"]
    # v2 tx: version(4) type(1) n_in(1) | prev_txid(32) vout(4) auth(1) m(1) n(1) keys(33*5) k(1)
    # | key_index(1) sig(64) ...  -> flip a byte inside the first signature.
    off = 4 + 1 + 1 + 32 + 4 + 1 + 1 + 1 + 33 * 5 + 1 + 1 + 10
    raw = bytearray.fromhex(hx); raw[off] ^= 0x01
    A.bad_ms_hex = raw.hex()
    with open(os.path.join(W, "bad_ms.hex"), "w") as f:
        f.write(A.bad_ms_hex + "\n")
    n.stop()
    snap = os.path.join(d, "snap")
    os.makedirs(snap)
    for f in os.listdir(n.dir):
        if os.path.isfile(os.path.join(n.dir, f)) and f != "peers.txt":
            shutil.copy2(os.path.join(n.dir, f), os.path.join(snap, f))
    return dict(dir=snap, height=63)


# ------------------------------------------------------------------ cases
def mut_witness(j):
    j["round_witnesses"][0]["dv"] = int(j["round_witnesses"][0]["dv"]) ^ 1


CASES = {
    #  name        (D producer, expected reject reason at reorg-connect (regex), storage-reject?)
    "pow_bits":   ("miner", ["--dev-bits-q-delta", "65536"], r"bits_q mismatch", False),
    "pow_target": ("relink_commit", None, r"PoW invalid \(commit above target\)", True),
    "cx":         ("same_id", mut_witness, r"CX Transcript V2 verification failed", False),
    "coinbase":   ("miner", ["--attack-coinbase", "miner-plus"], r"V17 coinbase amounts|CB12: V17 miner amount", False),
    "blocksize":  ("miner", ["--dev-pad-to-bytes", "1000001"], r"BLOCK_TX_BYTES_EXCEEDED", False),
    "multisig":   ("miner", ["--inject-tx-at1", "@bad_ms"], r"S1[0-9]|signature|multisig", False),
}


def produce_d(scn, kind, arg, F, d):
    """Returns (raw_json_of_invalid_D, valid_D_or_None). F's tip is the prefix tip on entry; for
    the honest-mined kinds F's tip is the genuine D on return."""
    dump = os.path.join(d, "D.json")
    if kind == "miner":
        args = [a if a != "@bad_ms" else os.path.join(A.work, "bad_ms.hex") for a in arg]
        h0 = F.height()
        rc = mine(F, 1, A.wb, extra=args + ["--dev-exit-after-submit", "--dump-block", dump],
                  expect_accept=False, tag="miner_D")
        if rc != 3 or F.height() != h0:
            raise RuntimeError(f"{scn}: invalid D was accepted by F (rc={rc})")
        return open(dump).read(), None
    # honest D mined on F (F accepts it); the invalid copy is derived from it
    mine(F, 1, A.wb, extra=["--dump-block", dump], tag="miner_D")
    genuine = F.raw(F.tip())
    j = json.loads(genuine)
    if kind == "same_id":
        arg(j)
    elif kind == "relink_commit":
        # devnet runs at the minimum difficulty, where every commit meets the target; claim
        # twice the difficulty so the all-ones commit is really above the target
        j["bits_q"] = int(j["bits_q"]) + 65536
        j["commit"] = "ff" * 32
        j["block_id"] = block_id(j)
    return json.dumps(j, separators=(",", ":")), genuine


def run_case(scn, base, variant=""):
    kind, arg, reason, storage_reject = CASES[scn.split(":")[0]]
    log(f"\n=== {scn} ===")
    d = os.path.join(A.work, scn.replace(":", "_"))
    os.makedirs(d)
    R, F, Z = Node(0, "R", d), Node(1, "F", d), Node(2, "Z", d)
    for n in (R, F, Z):
        copy_snapshot(base["dir"], n)
    h0 = base["height"]
    vaults = (A.v23, A.v35)
    p2p = (variant == "p2p_reconnect")

    # F: valid prefix (first block carries a valid 2-of-3 multisig spend); F listens on its
    # isolated port, so nothing can dial it until the p2p_reconnect variant brings it back.
    F.start(iso=True)
    F.rpc("sendrawtransaction", [A.sp23["final_hex"]])
    mine(F, 3, A.wb, tag="miner_F")
    wf = F.work_above(h0)
    # R: own branch X with work >= prefix work. In the p2p_reconnect variant R's only peer is F
    # (--connect F.addr), which is offline (F listens on its isolated port) until D' exists.
    R.start(connect=(F.addr,) if p2p else ("127.0.0.1:1",))
    mine(R, 3, A.wa, tag="miner_R")
    while R.work_above(h0) < wf:
        mine(R, 1, A.wa, tag="miner_R")
    # D on top of the prefix, such that prefix + D outweighs X (else grow the prefix and retry)
    for attempt in range(8):
        wr = R.work_above(h0)
        while wr < F.work_above(h0):                         # the prefix alone must not win
            mine(R, 1, A.wa, tag="miner_R"); wr = R.work_above(h0)
        bad, good = produce_d(scn, kind, arg, F, d)
        jb = json.loads(bad)
        prefix_top = F.height() if kind == "miner" else F.height() - 1
        w_prefix = sum(block_work(F.bits(h)) for h in range(h0 + 1, prefix_top + 1))
        w_d = w_prefix + block_work(int(jb["bits_q"]))
        if w_prefix <= wr < w_d:
            break
        log(f"  tuning: prefix work {w_prefix} X work {wr} prefix+D {w_d} -> grow the prefix")
        if kind == "miner":
            mine(F, 1, A.wb, tag="miner_F")                  # (honest kinds: the genuine D joins the prefix)
    else:
        raise RuntimeError("could not tune branch work")
    prefix = [F.raw(F.hash_at(h)) for h in range(h0 + 1, prefix_top + 1)]
    prefix_ids = [json.loads(p)["block_id"] for p in prefix]
    log(f"  fork@{h0}: prefix {h0 + 1}..{prefix_top} ({len(prefix)} blocks) + invalid D at #{jb['height']};"
        f" R branch X to #{R.height()}  (work prefix={w_prefix} X={wr} prefix+D={w_d})")
    if kind == "miner":
        check(scn, "F (the producer's own node) rejected D by the intended rule",
              re.search(r"\[BLOCK\] REJECTED: [^\n]*(" + reason + ")", F.logtext()) is not None,
              (re.findall(r"\[BLOCK\] REJECTED: [^\n]*", F.logtext()) or ["-"])[-1][:120])

    for raw in prefix:
        R.submit(raw)
    time.sleep(1)
    x_tip = R.tip()
    pre = R.state(vaults)
    check(scn, "prefix stored as a fork, R kept branch X (prefix work <= X)",
          R.tip() == x_tip and "[REORG] Disconnecting" not in R.logtext())

    # ---- the invalid D
    R.submit(bad)
    time.sleep(2)
    lt = R.logtext()
    m = re.search(r"\[REORG\] ABORTED: block at height (\d+) failed validation \(([^\n]*)\)", lt)
    # the reorg log carries the recorded reject reason; sites that record none (e.g. per-tx
    # consensus failures) are identified by the node's own REJECTED line just before it
    why = ""
    if m:
        rej = re.findall(r"\[BLOCK\] REJECTED: ([^\n]*)", lt[:m.start()])
        why = m.group(2) + " | " + (rej[-1] if rej else "")
    if storage_reject:
        check(scn, "D refused BEFORE storage by the intended rule, no reorg attempted",
              re.search(r"REJECTED before storage: [^\n]*(" + reason + ")", lt) is not None and
              "[REORG] Disconnecting" not in lt,
              (re.findall(r"REJECTED before storage: [^\n]*", lt) or ["-"])[-1][:120])
    else:
        check(scn, "reorg attempted (prefix + D outweighs X), connected the prefix and failed at D "
                   "by the intended rule",
              m is not None and int(m.group(1)) == int(jb["height"]) and re.search(reason, why) is not None
              and f"Rolling back {len(prefix)} fork blocks" in lt and "Rolled back to original tip" in lt,
              f"h={m.group(1)} {why[:200]}" if m else "no ABORTED line")
    post = R.state(vaults)
    diff = state_diff(pre, post)
    check(scn, "R's active chain and state unchanged (tip, height, UTXO root/count, H/J/pending, supply, "
               "lottery, DEV jackpot, vault UTXOs)", not diff, "; ".join(diff)[:300])
    bodies = [_body(R, i) for i in prefix_ids]
    check(scn, f"all {len(prefix)} valid prefix blocks keep their exact stored body (getrawblock)",
          all(b is not None and json.loads(b) == json.loads(p) for b, p in zip(bodies, prefix)),
          ", ".join("ok" if b is not None else "MISSING" for b in bodies))
    R.submit(bad)                                                # re-sent: changes nothing
    time.sleep(1)
    check(scn, "re-sending D changes nothing (tip/state and prefix bodies intact)",
          not state_diff(pre, R.state(vaults)) and all(_has_body(R, i) for i in prefix_ids))

    # ---- the valid D'
    if good is None:
        mine(F, 1, A.wb, tag="miner_F")
        good = F.raw(F.tip())
    winner = json.loads(good)["block_id"]
    if variant == "restart_before":
        R.stop(); R.start()
        check(scn, "restart after the failed reorg: R reloads branch X", R.tip() == x_tip and
              not state_diff(pre, R.state(vaults)))
        for raw in prefix:
            R.submit(raw)
        R.submit(good)
    elif p2p:
        if F.tip() != winner:
            F.submit(good)
        F.stop()
        F.start()                                                # F back on F.addr: R's --connect redial reaches it
        ok = wait_for(lambda: len(R.rpc("getpeerinfo")) > 0, 150)
        check(scn, "R (peer offline during the failed reorg) reconnects to F through its --connect redial", ok)
        wait_for(lambda: R.tip() == winner, 180)
    else:
        R.submit(good)                                           # ONLY D'
    ok = wait_for(lambda: R.tip() == winner, 120 if p2p else 60)
    check(scn, "no restart needed: the valid D' makes the fork branch win" +
          (" (restart_before variant: after re-delivery)" if variant == "restart_before" else ""),
          ok, f"R tip #{R.height()} {R.tip()[:16]} want {winner[:16]}")
    # clean node Z syncs only the winning chain
    Z.start()
    for raw in prefix + [good]:
        Z.submit(raw)
    check(scn, "clean node Z synced the winning chain on the tip path", Z.tip() == winner)
    sr, sz, sf = R.state(vaults), Z.state(vaults), F.state(vaults)
    dz, dfz = state_diff(sr, sz), state_diff(sf, sz)
    check(scn, "R == clean Z: tip, UTXO root/count, H/J/pending, supply, lottery, DEV jackpot, vault UTXOs",
          not dz, "; ".join(dz)[:300])
    check(scn, "F (miner of the winning chain) == clean Z", not dfz, "; ".join(dfz)[:300])
    check(scn, "winning chain identical block-by-block on R and Z",
          all(R.hash_at(h) == Z.hash_at(h) for h in range(h0, Z.height() + 1)))
    R.stop(); R.start(connect=(F.addr,) if p2p else ("127.0.0.1:1",))
    dr = state_diff(sz, R.state(vaults))
    check(scn, "restart after: R reloads the winning chain with identical state", not dr, "; ".join(dr)[:300])
    for n in (R, F, Z):
        n.stop()


def _body(node, bid):
    try:
        return node.raw(bid)
    except Exception:
        return None


def _has_body(node, bid):
    return _body(node, bid) is not None


def wait_for(pred, timeout, step=0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(step)
    return False


def main():
    global A
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--genesis", default=os.path.join(ROOT, "genesis_block.json"))
    ap.add_argument("--base", type=int, default=34200)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--only", default="")
    ap.add_argument("--node-bin", default="", help="sost-node to test (default <bin>/sost-node); "
                    "e.g. an unfixed devnet node as a negative control")
    A = ap.parse_args()
    A.bin, A.work = os.path.abspath(A.bin), os.path.abspath(A.work)
    A.node_bin = os.path.abspath(A.node_bin) if A.node_bin else os.path.join(A.bin, "sost-node")
    if not open(os.path.join(A.bin, "CMakeCache.txt")).read().count("SOST_DEVNET_FORKS:BOOL=ON"):
        sys.exit("not a DEVNET build")
    if os.path.exists(A.work) and os.listdir(A.work):
        sys.exit(f"{A.work} is not empty")
    os.makedirs(A.work, exist_ok=True)
    A.wa, A.wb = os.path.join(A.work, "wa.json"), os.path.join(A.work, "wb.json")
    plan = ["pow_bits", "pow_target", "cx", "coinbase", "blocksize", "multisig",
            "coinbase:restart_before", "pow_bits:p2p_reconnect"]
    only = set(x for x in A.only.split(",") if x)
    try:
        base = build_base()
        for scn in plan:
            if only and scn not in only and scn.split(":")[0] not in only:
                continue
            try:
                run_case(scn, base, scn.split(":")[1] if ":" in scn else "")
            except Exception as e:
                check(scn, "scenario completed without harness error", False, repr(e)[:300])
                stop_all()
    finally:
        stop_all()
    log("\n================ SUMMARY ================")
    by = {}
    for s, n, ok, _ in RESULTS:
        by.setdefault(s, []).append(ok)
    for s, oks in by.items():
        log(f"{'PASS' if all(oks) else 'FAIL'}  {s}  ({sum(oks)}/{len(oks)})")
    n_ok = sum(1 for r in RESULTS if r[2])
    log(f"checks: {n_ok}/{len(RESULTS)} PASS   scenarios: {sum(all(v) for v in by.values())}/{len(by)} PASS"
        f"   ({time.time() - T0:.0f}s)")
    sys.exit(0 if n_ok == len(RESULTS) and RESULTS else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Deep-fork P2P synchronisation regression harness (DEVNET_FAST, real nodes).

Launches real sost-node processes (Profile DEV, isolated ports and loopback IPs), mines
competing branches with the real sost-miner, connects the nodes over P2P and checks:

  * the honest higher-work branch wins automatically (no manual restart, no submitblock);
  * orphans are placed once their parents arrive (out-of-order delivery);
  * the honest peer is NOT penalised (no misbehaviour / ban for serving its own branch);
  * an invalid competing branch is rejected and cannot poison a later honest branch;
  * a reorg deeper than the reorg-depth cap is refused (legacy rule), and allowed through
    the SACS V2 path once past the devnet SACS V2 height (devnet: cap 8, SACS V2 at 42);
  * the orphan pool stays bounded under a junk-orphan flood and node memory stays flat.

Part of the scenarios use a scripted P2P peer (plain wire protocol, encryption off) to
deliver real blocks in reverse order, tampered blocks, or junk orphans.

Build (devnet profile, separate build dir):
  cmake -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=ON <src>
  make -j3 sost-node sost-miner sost-cli
Run:
  python3 tests/p2p/run_deep_fork_devnet.py --bin <build> --work <new empty dir> [--only s1,s2]

Ports: P2P base..base+19, RPC base+100.., isolated P2P base+200.. (default base 21100;
any base with base..base+300 inside 21000-25999 or 32000-32999 is accepted).
Every process this script starts is stopped by its recorded PID (argv[0] checked).
"""
import argparse
import hashlib
import json
import os
import random
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAGIC = 0x534F5354
REORG_CAP = 8            # MAX_REORG_DEPTH under SOST_DEVNET_FORKS
SACS_V2 = 42             # SACS_V2_ACTIVATION_HEIGHT under SOST_DEVNET_FORKS
ORPHAN_CAP = 200         # MAX_ORPHAN_BLOCKS

A = None                 # parsed args
PROCS = {}               # pid -> (exe, Popen)
RESULTS = []             # (scenario, check, ok, detail)


def log(msg):
    print(msg, flush=True)


def check(scn, name, ok, detail=""):
    RESULTS.append((scn, name, bool(ok), detail))
    log(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


# ----------------------------------------------------------------------------- processes
def spawn(argv, cwd, logf, niceness=0):
    p = subprocess.Popen(argv, cwd=cwd, stdout=open(logf, "a"), stderr=subprocess.STDOUT,
                         preexec_fn=(lambda: os.nice(niceness)) if niceness else None)
    PROCS[p.pid] = (argv[0], p)
    return p


def kill_pid(pid, sig=signal.SIGTERM, wait=30):
    ent = PROCS.get(pid)
    if not ent:
        return
    exe, p = ent
    if p.poll() is None:
        try:
            argv0 = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")[0].decode()
        except OSError:
            argv0 = ""
        if argv0 != exe:                      # never signal a PID we did not start
            log(f"  !! refusing to signal pid {pid}: argv0={argv0!r} != {exe!r}")
            PROCS.pop(pid, None)
            return
        os.kill(pid, sig)
        try:
            p.wait(wait)
        except subprocess.TimeoutExpired:
            os.kill(pid, signal.SIGKILL)
            p.wait()
    PROCS.pop(pid, None)


def stop_all():
    for pid in list(PROCS):
        kill_pid(pid)


class Node:
    def __init__(self, idx, name, root):
        self.idx, self.name = idx, name
        self.ip = f"127.0.0.{11 + idx}"
        self.p2p = A.base + idx
        self.rpcport = A.base + 100 + idx
        self.iso_p2p = A.base + 200 + idx
        self.dir = os.path.join(root, name)
        self.logf = os.path.join(root, name + ".log")
        os.makedirs(self.dir, exist_ok=True)
        self.proc = None

    @property
    def addr(self):
        return f"{self.ip}:{self.p2p}"

    def start(self, connect=(), isolated=False, keep_peers=False, extra=()):
        assert self.proc is None
        if not keep_peers:
            try:
                os.remove(os.path.join(self.dir, "peers.txt"))
            except FileNotFoundError:
                pass
        argv = [os.path.join(A.bin, "sost-node"), "--profile", "dev", "--genesis", A.genesis,
                "--chain", os.path.join(self.dir, "chain.json"),
                "--port", str(self.iso_p2p if isolated else self.p2p),
                "--rpc-port", str(self.rpcport), "--rpc-noauth", "--noseed", "--p2p-bind", self.ip]
        for c in connect:
            argv += ["--connect", c]
        argv += list(extra)
        with open(self.logf, "a") as f:
            f.write(f"\n===== start {'isolated' if isolated else 'network'} connect={list(connect)} t={time.time():.0f}\n")
        self.proc = spawn(argv, self.dir, self.logf)
        self.log_mark = os.path.getsize(self.logf)
        t0 = time.time()
        while time.time() - t0 < 60:
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

    def rpc(self, method, params=None):
        body = json.dumps({"method": method, "params": params or [], "id": 1}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.rpcport}/", data=body,
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        if d.get("error"):
            raise RuntimeError(f"{method}: {d['error']}")
        return d["result"]

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

    def peers(self):
        return self.rpc("getpeerinfo")

    def rss_kb(self):
        for ln in open(f"/proc/{self.proc.pid}/status"):
            if ln.startswith("VmRSS:"):
                return int(ln.split()[1])
        return -1

    def logtext(self, since_start=True):
        with open(self.logf, "r", errors="replace") as f:
            if since_start:
                f.seek(self.log_mark)
            return f.read()


def mine(node, n, wallet):
    h0 = node.height()
    addr = json.load(open(wallet))["keys"][0]["address"]
    p = spawn([os.path.join(A.bin, "sost-miner"), "--profile", "dev", "--genesis", A.genesis,
               "--rpc", f"127.0.0.1:{node.rpcport}", "--address", addr, "--wallet", wallet,
               "--mining-key-label", "default", "--blocks", str(n), "--threads", str(A.threads), "--realtime"],
              os.path.dirname(wallet), os.path.join(os.path.dirname(wallet), "miner.log"), niceness=15)
    p.wait()
    PROCS.pop(p.pid, None)
    h = node.height()
    if h != h0 + n:
        raise RuntimeError(f"{node.name}: mined {h - h0} != {n}")
    return h


def work_of(node, lo, hi):
    """Approximate work of blocks lo..hi on node's active chain: 2^(bits_q/65536)."""
    return sum(2.0 ** (node.bits(h) / 65536.0) for h in range(lo, hi + 1))


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


PENALTY_RE = re.compile(r"\[P2P\] (Misbehavior \+\d+ \(.*?\) from (\S+)|BANNED (\S+): (.*))")


def penalties(node, ip):
    """Misbehaviour / ban lines in node's log (since its last start) about peer `ip`."""
    out = []
    for m in PENALTY_RE.finditer(node.logtext()):
        who = m.group(2) or m.group(3) or ""
        if who.startswith(ip + ":"):
            out.append(m.group(1))
    return out


MAGIC_DEV = bytes([0x43, 0x58, 0x50, 0x4f, 0x57, 0x33, 0xf9, 0x50, 0xf9, 0x4b])


def block_id(j):
    """block_id of a block JSON (header as built by sost-node build_full_header_bytes, DEV magic)."""
    u32 = lambda v: struct.pack("<I", int(v) & 0xFFFFFFFF)
    ver = int(j.get("version", 1) or 1)
    hdr = (MAGIC_DEV + b"HDR2" + bytes.fromhex(j["prev_hash"]) + bytes.fromhex(j["merkle_root"]) +
           u32(j["timestamp"]) + u32(j["bits_q"]) + bytes.fromhex(j["checkpoints_root"]) +
           u32(j["nonce"]) + u32(j["extra_nonce"]))
    if ver >= 2:
        hdr += u32(ver) + bytes.fromhex(j["miner_pubkey"]) + bytes.fromhex(j["miner_signature"])
    return hashlib.sha256(hdr + b"ID" + bytes.fromhex(j["commit"])).hexdigest()


# ----------------------------------------------------------------------------- scripted peer
class FakePeer:
    """Minimal plaintext SOST P2P peer (VERS/VACK/GETB/BLCK/DONE/PING)."""

    def __init__(self, src_ip, target, height, serve=None, reverse=False, mute=False):
        self.serve = serve or {}            # height -> raw block json
        self.mute = mute                    # never answer GETB (a peer that just relays)
        self.reverse = reverse
        self.height = height
        self.getb = []
        self.closed = False
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.bind((src_ip, 0))
        self.s.settimeout(10)
        self.s.connect(target)
        self.lock = threading.Lock()
        self.genesis = None
        self.ready = threading.Event()
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()
        if not self.ready.wait(15):
            raise RuntimeError("fake peer: no VERS from node")

    def send(self, cmd, payload=b""):
        with self.lock:
            self.s.sendall(struct.pack("<I", MAGIC) + cmd.encode() + struct.pack("<I", len(payload)) + payload)

    def _recv_exact(self, n):
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise ConnectionError("closed")
            b += c
        return b

    def _loop(self):
        try:
            self.s.settimeout(None)
            while True:
                hdr = self._recv_exact(12)
                magic, = struct.unpack("<I", hdr[:4])
                cmd = hdr[4:8].decode(errors="replace")
                ln, = struct.unpack("<I", hdr[8:12])
                pl = self._recv_exact(ln) if ln else b""
                if magic != MAGIC:
                    continue
                if cmd == "VERS":
                    self.genesis = pl[8:40]
                    self.send("VERS", struct.pack("<q", self.height) + self.genesis + b"\x00")
                    self.ready.set()
                elif cmd == "PING":
                    self.send("PONG")
                elif cmd == "GETB" and self.mute:
                    pass
                elif cmd == "GETB":
                    frm, = struct.unpack("<q", pl[:8])
                    self.getb.append(frm)
                    hs = [h for h in range(frm, frm + 100) if h in self.serve]
                    if self.reverse:
                        hs = hs[::-1]
                    for h in hs:
                        self.send("BLCK", self.serve[h].encode())
                    self.send("DONE")
        except Exception:
            self.closed = True

    def push(self, blocks, gap=0.0):
        for b in blocks:
            self.send("BLCK", b.encode())
            if gap:
                time.sleep(gap)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


# ----------------------------------------------------------------------------- scenario plumbing
class Ctx:
    pass


def fresh_pair(scn, base_snapshot):
    d = os.path.join(A.work, scn)
    os.makedirs(d)
    a, b = Node(0, "A", d), Node(1, "B", d)
    for n in (a, b):
        for f in os.listdir(base_snapshot):
            shutil.copy2(os.path.join(base_snapshot, f), os.path.join(n.dir, f))
    return d, a, b


def make_fork(scn, base, a_blocks, b_blocks, margin=1.0):
    """A mines a_blocks, B mines b_blocks (both isolated) from the same snapshot; B is topped up
    until its branch work exceeds A's by `margin`. Nodes are left STOPPED."""
    d, a, b = fresh_pair(scn, base["dir"])
    fh = base["height"]
    a.start(isolated=True)
    if a_blocks:
        mine(a, a_blocks, A.wallet_a)
    b.start(isolated=True)
    mine(b, b_blocks, A.wallet_b)
    wa = work_of(a, fh + 1, a.height()) if a_blocks else 0.0
    wb = work_of(b, fh + 1, b.height())
    while wb <= wa * margin:
        mine(b, 1, A.wallet_b)
        wb = work_of(b, fh + 1, b.height())
    info = dict(fork_h=fh, a_tip=a.tip(), a_h=a.height(), b_tip=b.tip(), b_h=b.height(), wa=wa, wb=wb,
                b_blocks={h: b.raw(b.hash_at(h)) for h in range(fh + 1, b.height() + 1)})
    log(f"  fork@{fh}: A h={info['a_h']} (work~{wa:.0f})  B h={info['b_h']} (work~{wb:.0f})")
    a.stop()
    b.stop()
    return d, a, b, info


def converge_checks(scn, a, b, info, timeout, expect=True, label="A converged to B's higher-work branch"):
    ok = wait_for(lambda: a.tip() == info["b_tip"], timeout)
    if expect:
        check(scn, label, ok, f"A tip h={a.height()} {a.tip()[:16]}")
        if ok:
            check(scn, "A's chain matches B block-by-block from the fork point",
                  all(a.hash_at(h) == b.hash_at(h) for h in range(info["fork_h"], info["b_h"] + 1)))
    else:
        check(scn, label, not ok and a.tip() == info["a_tip"], f"A tip h={a.height()} {a.tip()[:16]}")
    time.sleep(2)
    pen = penalties(a, b.ip)
    check(scn, "no misbehaviour/ban recorded against the honest peer", not pen, "; ".join(pen)[:200])
    return ok


# ----------------------------------------------------------------------------- scenarios
def scn_p2p_fork(scn, base, a_n, b_n, expect=True, timeout=90):
    log(f"\n=== {scn}: A +{a_n} vs B +{b_n} over P2P (disconnect depth {a_n}) ===")
    d, a, b, info = make_fork(scn, base, a_n, b_n)
    b.start()
    a.start(connect=[b.addr])
    converge_checks(scn, a, b, info, timeout, expect=expect,
                    label=("A converged to B's higher-work branch" if expect else
                           f"A refused the reorg deeper than the cap ({REORG_CAP}) and kept its own tip"))
    if not expect:
        check(scn, "B (honest, deeper branch) is not banned by A", "BANNED" not in "".join(penalties(a, b.ip)))
    check(scn, "A still answers RPC (alive)", a.height() >= 0)
    a.stop(); b.stop()


def scn_reverse_submit(scn, base):
    log(f"\n=== {scn}: B's branch submitted to A in REVERSE order via submitblock ===")
    d, a, b, info = make_fork(scn, base, 2, 4)
    a.start(isolated=True)
    hs = sorted(info["b_blocks"])[::-1]
    for h in hs:
        try:
            a.rpc("submitblock", [info["b_blocks"][h]])
        except Exception:
            pass                                  # orphans/forks report "rejected" — expected
    ok = wait_for(lambda: a.tip() == info["b_tip"], 20)
    check(scn, "A reorged to B's branch once the lowest missing parent arrived", ok, f"A h={a.height()}")
    orph = re.findall(r"(\d+) orphans total", a.logtext())
    check(scn, "orphans were stored, then re-processed (cascade)", orph and "Re-processing orphan" in a.logtext())
    a.stop()


def scn_reverse_p2p(scn, base):
    log(f"\n=== {scn}: scripted peer serves B's branch in REVERSE order over P2P ===")
    d, a, b, info = make_fork(scn, base, 2, 4)
    a.start(isolated=True)
    fp = FakePeer("127.0.0.31", (a.ip, a.iso_p2p), info["b_h"], serve=info["b_blocks"], reverse=True)
    ok = wait_for(lambda: a.tip() == info["b_tip"], 60)
    check(scn, "A converged to the branch delivered out of order", ok, f"A h={a.height()} GETB from {fp.getb}")
    pen = penalties(a, "127.0.0.31")
    check(scn, "no misbehaviour recorded against the (honest) out-of-order peer", not pen, "; ".join(pen)[:200])
    fp.close()
    a.stop()


def scn_unsolicited_tip(scn, base):
    log(f"\n=== {scn}: only B's TIP is relayed (unsolicited) — A must locate the fork itself ===")
    d, a, b, info = make_fork(scn, base, 3, 5)
    a.start(isolated=True)
    # A scripted peer that announces A's own height (so A does not start a height sync) and
    # relays only the branch tip, then serves GETB like a normal node.
    fp = FakePeer("127.0.0.32", (a.ip, a.iso_p2p), info["a_h"], serve=info["b_blocks"])
    fp.push([info["b_blocks"][info["b_h"]]])
    ok = wait_for(lambda: a.tip() == info["b_tip"], 60)
    check(scn, "A walked back to the fork point and converged", ok, f"A h={a.height()} GETB from {fp.getb}")
    pen = penalties(a, "127.0.0.32")
    check(scn, "no misbehaviour recorded against the relaying peer", not pen, "; ".join(pen)[:200])
    fp.close()
    a.stop()


def tamper(raw):
    j = json.loads(raw)
    j["nonce"] = int(j["nonce"]) ^ 1                # header changes, block_id kept -> id mismatch
    return json.dumps(j, separators=(",", ":"))


def scn_invalid_fork(scn, base):
    log(f"\n=== {scn}: invalid heavier branch (tampered block, real ids) then the honest one ===")
    d, a, b, info = make_fork(scn, base, 2, 4)
    bad = dict(info["b_blocks"])
    hbad = info["fork_h"] + 2
    bad[hbad] = tamper(bad[hbad])
    a.start(isolated=True)
    a_tip = a.tip()
    fp = FakePeer("127.0.0.33", (a.ip, a.iso_p2p), info["b_h"], serve=bad)
    time.sleep(12)
    check(scn, "A rejected the invalid branch and kept its own tip", a.tip() == a_tip, f"A h={a.height()}")
    check(scn, "A still answers RPC (alive)", a.height() == info["a_h"])
    pen = penalties(a, "127.0.0.33")
    log(f"  (malicious peer penalties: {pen})")
    fp.close()
    # The honest peer now serves the REAL branch with the same block ids.
    b.start()
    a.stop()
    a.start(connect=[b.addr], keep_peers=True)
    ok = wait_for(lambda: a.tip() == info["b_tip"], 90)
    check(scn, "after a restart, the honest branch (same ids) is still adopted", ok, f"A h={a.height()}")
    a.stop()
    # Without a restart (the INVALID mark is in memory): fresh A, invalid peer first, then honest B.
    shutil.rmtree(a.dir)
    os.makedirs(a.dir)
    for f in os.listdir(base["dir"]):
        shutil.copy2(os.path.join(base["dir"], f), os.path.join(a.dir, f))
    a.start(isolated=True)
    mine(a, 2, A.wallet_a)
    a_tip2 = a.tip()
    fp = FakePeer("127.0.0.34", (a.ip, a.iso_p2p), info["b_h"], serve=bad)
    time.sleep(12)
    check(scn, "invalid branch rejected again (fresh A)", a.tip() == a_tip2)
    fp.close()
    fp2 = FakePeer("127.0.0.35", (a.ip, a.iso_p2p), info["b_h"], serve=info["b_blocks"])
    ok = wait_for(lambda: a.tip() == info["b_tip"], 60)
    check(scn, "same running node: honest branch with the SAME block ids is adopted after the invalid one",
          ok, f"A h={a.height()} tip {a.tip()[:16]} GETB from {fp2.getb}")
    pen = penalties(a, "127.0.0.35")
    check(scn, "no misbehaviour recorded against the honest peer", not pen, "; ".join(pen)[:200])
    fp2.close()
    a.stop(); b.stop()


def scn_reconnect(scn, base):
    log(f"\n=== {scn}: peer down at start, comes back; then a second fork while disconnected ===")
    d, a, b, info = make_fork(scn, base, 2, 3)
    a.start(connect=[b.addr])                    # B is DOWN: A's first dial fails
    time.sleep(3)
    b.start()
    ok = converge_checks(scn, a, b, info, 120, label="A converged after B came back (reconnect loop)")
    # Second fork while disconnected: B goes down, A mines 1, B (isolated) mines 3.
    b.stop()
    mine(a, 1, A.wallet_a)
    a_tip = a.tip()
    b.start(isolated=True)
    mine(b, 3, A.wallet_b)
    info2 = dict(info, fork_h=info["b_h"], b_tip=b.tip(), b_h=b.height(), a_tip=a_tip)
    b.stop()
    b.start()
    converge_checks(scn, a, b, info2, 120, label="second fork: A converged after B reconnected")
    a.stop(); b.stop()


def scn_reconnect_after_orphans(scn, base):
    log(f"\n=== {scn}: connection drops right after relaying the branch tip; the peer reconnects ===")
    d, a, b, info = make_fork(scn, base, 2, 4)
    a.start(isolated=True)
    top = sorted(info["b_blocks"])[-2:]
    fp = FakePeer("127.0.0.37", (a.ip, a.iso_p2p), info["a_h"])
    fp.push([info["b_blocks"][h] for h in top])  # stored as orphans (parents unknown) ...
    time.sleep(0.5)
    fp.close()                                     # ... and the connection is gone
    time.sleep(2)
    check(scn, "relayed tip blocks were kept as orphans", "orphans total" in a.logtext())
    fp2 = FakePeer("127.0.0.38", (a.ip, a.iso_p2p), info["b_h"], serve=info["b_blocks"])
    ok = wait_for(lambda: a.tip() == info["b_tip"], 60)
    check(scn, "A converged when the peer came back and re-served blocks it held as orphans", ok,
          f"A h={a.height()} GETB from {fp2.getb}")
    pen = penalties(a, "127.0.0.38")
    check(scn, "no misbehaviour recorded against the reconnected honest peer", not pen, "; ".join(pen)[:200])
    fp2.close()
    a.stop()


def scn_orphan_flood(scn, base):
    log(f"\n=== {scn}: junk-orphan flood ({ORPHAN_CAP}+), then an honest fork ===")
    d, a, b, info = make_fork(scn, base, 2, 3)
    a.start(isolated=True)
    rss0 = a.rss_kb()
    tmpl = json.loads(info["b_blocks"][info["fork_h"] + 1])
    check(scn, "harness block-id port reproduces real block ids",
          all(block_id(json.loads(r)) == json.loads(r)["block_id"] for r in info["b_blocks"].values()))
    junk = []
    for i in range(320):                          # self-consistent ids: they pass any id check
        j = dict(tmpl)
        j["prev_hash"] = os.urandom(32).hex()
        j["height"] = info["a_h"] + 3 + (i % 50)
        j["block_id"] = block_id(j)
        junk.append(json.dumps(j, separators=(",", ":")))
    sent = 0
    for k in range(8):                            # 8 source IPs x 40 blocks (< 50/min relay limit)
        fp = FakePeer(f"127.0.0.{41 + k}", (a.ip, a.iso_p2p), info["a_h"])
        fp.push(junk[k * 40:(k + 1) * 40])
        sent += 40
        time.sleep(1)
        fp.close()
    time.sleep(3)
    counts = [int(x) for x in re.findall(r"(\d+) orphans total", a.logtext())]
    mx = max(counts) if counts else 0
    rss1 = a.rss_kb()
    check(scn, f"orphan pool bounded (max {mx} <= {ORPHAN_CAP} after {sent} junk orphans)", mx <= ORPHAN_CAP)
    check(scn, "node memory bounded during the flood", rss1 - rss0 < 200 * 1024, f"RSS {rss0}->{rss1} kB")
    check(scn, "A still on its own tip (junk never connects)", a.tip() == info["a_tip"])
    fp2 = FakePeer("127.0.0.36", (a.ip, a.iso_p2p), info["b_h"], serve=info["b_blocks"])
    ok = wait_for(lambda: a.tip() == info["b_tip"], 60)
    check(scn, "honest fork still converges with a full orphan pool", ok, f"A h={a.height()} GETB from {fp2.getb}")
    pen = penalties(a, "127.0.0.36")
    check(scn, "no misbehaviour recorded against the honest peer", not pen, "; ".join(pen)[:200])
    fp2.close()
    a.stop()



# ----------------------------------------------------------------------------- fork PoW validation
FULL = ["--full-verify"]          # verify ConvergenceX on every block (devnet heights sit below
                                  # the assumevalid height, where the default fast sync skips it)


def relink(blocks, h0, mutate):
    """Copy of a branch where block h0 is changed by `mutate(j)` and every block from h0 up gets
    a self-consistent id (descendants re-pointed at the new parent). The ids are honest hashes of
    the new bodies, so only real validation (PoW / CX / SbPoW) can tell these blocks are bad."""
    out, prev_new = dict(blocks), None
    for h in sorted(blocks):
        if h < h0:
            continue
        j = json.loads(blocks[h])
        if h == h0:
            mutate(j)
        else:
            j["prev_hash"] = prev_new
        j["block_id"] = block_id(j)
        prev_new = j["block_id"]
        out[h] = json.dumps(j, separators=(",", ":"))
    return out


def same_id_mutation(raw, mutate):
    """Copy of a block with an uncommitted field changed and the ORIGINAL block_id kept."""
    j = json.loads(raw)
    mutate(j)
    return json.dumps(j, separators=(",", ":"))


def flip_hex(s, i=0):
    return s[:i] + ("0" if s[i] != "0" else "1") + s[i + 1:]


def mut_witness(j):                                # ConvergenceX round witness: dataset value
    j["round_witnesses"][0]["dv"] = int(j["round_witnesses"][0]["dv"]) ^ 1


def reorg_attempted(node):
    return "[REORG] Disconnecting" in node.logtext()


def bad_branch_then_honest(scn, base, mutate_h, mutate, same_id, full, expect_storage_reject,
                           a_n=2, b_n=4):
    """A (own branch) is offered a heavier branch whose block mutate_h is bad, then the honest
    branch (same ids where same_id) on the SAME running node."""
    d, a, b, info = make_fork(scn, base, a_n, b_n)
    h = info["fork_h"] + mutate_h
    if same_id:
        bad = dict(info["b_blocks"]); bad[h] = same_id_mutation(bad[h], mutate)
    else:
        bad = relink(info["b_blocks"], h, mutate)
    a.start(isolated=True, extra=FULL if full else ())
    a_tip = a.tip()
    evil = "127.0.0.61"
    fp = FakePeer(evil, (a.ip, a.iso_p2p), info["b_h"], serve=bad)
    time.sleep(12)
    check(scn, "A did not adopt the invalid heavier branch (kept its own tip)", a.tip() == a_tip,
          f"A h={a.height()} tip {a.tip()[:16]}")
    if expect_storage_reject:
        check(scn, "bad block refused BEFORE storage (no reorg attempted onto it)",
              "REJECTED before storage" in a.logtext() and not reorg_attempted(a),
              "; ".join(sorted(set(re.findall(r"REJECTED before storage: ([^\n]*)", a.logtext()))))[:200])
    else:
        lt = a.logtext()
        check(scn, "bad block caught at connect time by full validation; reorg rolled back",
              reorg_attempted(a) and "Rolled back to original tip" in lt,
              "; ".join(sorted(set(re.findall(r"\[REORG\] (?:Evicted|Marked)[^\n]*", lt))))[:240])
    log(f"  (malicious peer penalties: {penalties(a, evil)})")
    fp.close()
    honest = "127.0.0.62"
    fp2 = FakePeer(honest, (a.ip, a.iso_p2p), info["b_h"], serve=info["b_blocks"])
    ok = wait_for(lambda: a.tip() == info["b_tip"], 90)
    check(scn, "same running node then adopts the honest branch" + (" (same block ids)" if same_id else ""),
          ok, f"A h={a.height()} tip {a.tip()[:16]} GETB from {fp2.getb}")
    pen = penalties(a, honest)
    check(scn, "no misbehaviour recorded against the honest peer", not pen, "; ".join(pen)[:200])
    fp2.close()
    a.stop()


def scn_valid_ooo_fullverify(scn, base):
    log(f"\n=== {scn}: valid fork served in REVERSE order, A verifies ConvergenceX on every block ===")
    d, a, b, info = make_fork(scn, base, 2, 4)
    a.start(isolated=True, extra=FULL)
    fp = FakePeer("127.0.0.63", (a.ip, a.iso_p2p), info["b_h"], serve=info["b_blocks"], reverse=True)
    ok = wait_for(lambda: a.tip() == info["b_tip"], 90)
    check(scn, "A converged to the valid out-of-order branch (orphans + forks pre-checked, CX verified)",
          ok, f"A h={a.height()} GETB from {fp.getb}")
    lt = a.logtext()
    check(scn, "no genuine block refused by the storage pre-check", "REJECTED before storage" not in lt)
    check(scn, "CX transcript verified on connect", "CX Transcript V2 verified" in lt)
    pen = penalties(a, "127.0.0.63")
    check(scn, "no misbehaviour recorded against the honest peer", not pen, "; ".join(pen)[:200])
    fp.close()
    a.stop()


def scn_delayed_parent(scn, base):
    log(f"\n=== {scn}: children first (orphans), parent delivered later; A verifies CX ===")
    d, a, b, info = make_fork(scn, base, 2, 4)
    a.start(isolated=True, extra=FULL)
    a_tip = a.tip()
    fh = info["fork_h"]
    # First peer relays the children only and goes away (it never had the parent).
    fp = FakePeer("127.0.0.64", (a.ip, a.iso_p2p), info["a_h"], mute=True)
    fp.push([info["b_blocks"][h] for h in sorted(info["b_blocks"]) if h > fh + 1], gap=0.3)
    time.sleep(0.5)
    fp.close()
    time.sleep(4)
    check(scn, "children kept as orphans while the parent is missing (no reorg yet)",
          a.tip() == a_tip and "orphans total" in a.logtext() and not reorg_attempted(a))
    # Much later a second peer relays just the missing parent (unsolicited, no GETB served).
    time.sleep(6)
    fp2 = FakePeer("127.0.0.67", (a.ip, a.iso_p2p), info["a_h"], mute=True)
    fp2.push([info["b_blocks"][fh + 1]])
    ok = wait_for(lambda: a.tip() == info["b_tip"], 60)
    check(scn, "reorg completed from the stored orphans once the delayed parent arrived", ok,
          f"A h={a.height()}")
    pen = penalties(a, "127.0.0.64") + penalties(a, "127.0.0.67")
    check(scn, "no misbehaviour recorded against either honest peer", not pen, "; ".join(pen)[:200])
    fp2.close()
    a.stop()


BLOCKID_MUTATIONS = [
    # (field, mutate, committed-by)
    ("nonce (control: header)", lambda j: j.update(nonce=int(j["nonce"]) ^ 1), "header"),
    ("timestamp (control: header)", lambda j: j.update(timestamp=int(j["timestamp"]) + 1), "header"),
    ("commit (control: id preimage)", lambda j: j.update(commit=flip_hex(j["commit"])), "id"),
    ("transactions (drop all)", lambda j: j.pop("transactions"), "merkle"),
    ("height", lambda j: j.update(height=int(j["height"]) + 1), "-"),
    ("subsidy", lambda j: j.update(subsidy=int(j["subsidy"]) + 1), "-"),
    ("miner", lambda j: j.update(miner=int(j["miner"]) + 1), "-"),
    ("gold_vault", lambda j: j.update(gold_vault=int(j["gold_vault"]) + 1), "-"),
    ("popc_pool", lambda j: j.update(popc_pool=int(j["popc_pool"]) + 1), "-"),
    ("profile_index", lambda j: j.update(profile_index=int(j["profile_index"]) - 1), "commit"),
    ("profile_index (removed)", lambda j: j.pop("profile_index"), "commit"),
    ("stability_metric", lambda j: j.update(stability_metric=int(j["stability_metric"]) + 1), "commit"),
    ("x_bytes", lambda j: j.update(x_bytes=flip_hex(j["x_bytes"])), "commit"),
    ("final_state", lambda j: j.update(final_state=flip_hex(j["final_state"])), "commit"),
    ("segments_root", lambda j: j.update(segments_root=flip_hex(j["segments_root"])), "commit"),
    ("checkpoint_leaves[0]", lambda j: j["checkpoint_leaves"].__setitem__(0, flip_hex(j["checkpoint_leaves"][0])), "checkpoints_root"),
    ("segment_proofs[0].ss", lambda j: j["segment_proofs"][0].update(ss=flip_hex(j["segment_proofs"][0]["ss"])), "segments_root"),
    ("round_witnesses[0].dv", mut_witness, "commit+challenges"),
    ("stab_scale", lambda j: j.update(stab_scale=int(j.get("stab_scale", 0)) + 1), "-"),
    ("stab_k/margin/steps/lr_shift", lambda j: j.update(stab_k=int(j.get("stab_k", 0)) + 1, stab_margin=int(j.get("stab_margin", 0)) + 1,
                                                         stab_steps=int(j.get("stab_steps", 0)) + 1, stab_lr_shift=int(j.get("stab_lr_shift", 0)) + 1), "-"),
    ("unknown extra field", lambda j: j.update(zz_extra="x"), "-"),
]


def scn_blockid_mutation(scn, base):
    """TASK B: mutate each block JSON field of a real devnet block while keeping its block_id,
    and record what the node does with it - on the tip-extending path (submitblock) and on the
    fork-storage / relay path - with the default fast sync and with --full-verify."""
    log(f"\n=== {scn}: same-id mutations of every block JSON field ===")
    d, a, b, info = make_fork(scn, base, 2, 4)
    fh = info["fork_h"]
    genuine = info["b_blocks"][fh + 1]
    gj = json.loads(genuine)
    log("  block fields: " + ", ".join(sorted(gj)))
    snap_a = os.path.join(d, "A_snap")                 # A's own branch (2 blocks above the fork)
    shutil.copytree(a.dir, snap_a, ignore=shutil.ignore_patterns("peers.txt"))
    tip_node = Node(2, "T", d)                          # node whose tip IS the fork point
    for f in os.listdir(base["dir"]):
        shutil.copy2(os.path.join(base["dir"], f), os.path.join(tip_node.dir, f))
    snap_t = os.path.join(d, "T_snap")
    shutil.copytree(tip_node.dir, snap_t)

    def reset(node, snap):
        shutil.rmtree(node.dir)
        shutil.copytree(snap, node.dir)

    table = []
    for mode, extra in (("default", ()), ("full-verify", FULL)):
        tip_node.start(isolated=True, extra=extra)
        dirty = False
        for name, fn, _ in BLOCKID_MUTATIONS:
            if dirty:
                tip_node.stop(); reset(tip_node, snap_t); tip_node.start(isolated=True, extra=extra); dirty = False
            raw = same_id_mutation(genuine, fn)
            try:
                tip_node.rpc("submitblock", [raw]); acc = True
            except Exception:
                acc = False
            stored_same = None
            if acc and tip_node.height() == fh + 1:
                stored = json.loads(tip_node.raw(gj["block_id"]))
                stored_same = (stored == gj)
                dirty = True
            elif acc:
                dirty = True
            table.append((mode, "tip", name, "ACCEPTED" + ("" if stored_same is None else
                          (" (stored body == genuine)" if stored_same else " (MUTATED body stored)")) if acc else "rejected"))
        # the genuine block is still accepted after all the rejected copies
        if dirty:
            tip_node.stop(); reset(tip_node, snap_t); tip_node.start(isolated=True, extra=extra)
        try:
            tip_node.rpc("submitblock", [genuine]); g_ok = True
        except Exception:
            g_ok = False
        check(scn, f"[{mode}] genuine block accepted on the tip path after the mutated copies", g_ok)
        tip_node.stop(); reset(tip_node, snap_t)

    # Relay / fork-storage path: the mutated copy (same id) arrives first as a FORK block from a
    # malicious peer; then the honest peer serves the whole genuine heavier branch (same ids).
    poison_fail = []
    for mode, extra in (("default", ()), ("full-verify", FULL)):
        for name, fn, _ in BLOCKID_MUTATIONS[3:]:
            reset(a, snap_a)
            a.start(isolated=True, extra=extra)
            raw = same_id_mutation(genuine, fn)
            fp = FakePeer("127.0.0.65", (a.ip, a.iso_p2p), info["a_h"])
            fp.push([raw])
            time.sleep(1.5)
            lt = a.logtext()
            m = re.search(r"REJECTED before storage: ([^\n]*)", lt)
            fate = ("refused before storage: " + m.group(1)) if m else (
                "stored as fork" if "Fork stored" in lt or "orphans total" in lt else "rejected/ignored")
            fp.close()
            fp2 = FakePeer("127.0.0.66", (a.ip, a.iso_p2p), info["b_h"], serve=info["b_blocks"])
            ok = wait_for(lambda: a.tip() == info["b_tip"], 60)
            pen = penalties(a, "127.0.0.66")
            same = ok and json.loads(a.raw(gj["block_id"])) == gj
            table.append((mode, "relay", name, f"{fate}; honest branch adopted={ok}; "
                          f"canonical body genuine={same}; honest penalties={len(pen)}"))
            if not ok or pen:
                poison_fail.append(f"{mode}/{name}")
            fp2.close()
            a.stop()
    check(scn, "relay path: no same-id mutated copy prevents the genuine branch or gets the honest "
               "peer penalised", not poison_fail, ", ".join(poison_fail)[:300])
    # G1/G2 (docs/p2p/BLOCK_ID_COMMITMENT_AUDIT.md): inside the fast-sync trust (default mode,
    # devnet heights < assumevalid) the tip path must now refuse a block without transactions
    # and any copy whose profile_index / commit data is not bound by its commit.
    tip_default = {name: fate for mode, path, name, fate in table if mode == "default" and path == "tip"}
    must_reject = ["transactions (drop all)", "profile_index", "stability_metric", "x_bytes",
                   "final_state", "segments_root"]
    if int(gj.get("profile_index", 0)) != 0:
        must_reject.append("profile_index (removed)")
    bad = [n for n in must_reject if tip_default.get(n) != "rejected"]
    check(scn, "[default] G1/G2: header-only and unbound-profile copies rejected inside the trust",
          not bad, ", ".join(f"{n}={tip_default.get(n)}" for n in bad)[:300])
    log("\n  ---- block_id mutation table ----")
    for row in table:
        log("  %-12s %-5s %-30s %s" % row)
    with open(os.path.join(A.work, "blockid_mutation_table.json"), "w") as f:
        json.dump(table, f, indent=1)

# ----------------------------------------------------------------------------- main
def build_base(name, height):
    d = os.path.join(A.work, "_" + name)
    n = Node(19, name, d)
    n.start(isolated=True)
    mine(n, height - n.height(), A.wallet_a)
    n.stop()
    snap = os.path.join(d, "snap")
    os.makedirs(snap)
    for f in os.listdir(n.dir):
        if f != "peers.txt" and os.path.isfile(os.path.join(n.dir, f)):
            shutil.copy2(os.path.join(n.dir, f), os.path.join(snap, f))
    return dict(dir=snap, height=height, node_dir=n.dir)


def extend_base(prev, name, height):
    d = os.path.join(A.work, "_" + name)
    n = Node(19, name, d)
    for f in os.listdir(prev["dir"]):
        shutil.copy2(os.path.join(prev["dir"], f), os.path.join(n.dir, f))
    n.start(isolated=True)
    mine(n, height - n.height(), A.wallet_a)
    n.stop()
    snap = os.path.join(d, "snap")
    os.makedirs(snap)
    for f in os.listdir(n.dir):
        if f != "peers.txt" and os.path.isfile(os.path.join(n.dir, f)):
            shutil.copy2(os.path.join(n.dir, f), os.path.join(snap, f))
    return dict(dir=snap, height=height)


def main():
    global A
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--genesis", default=os.path.join(ROOT, "genesis_block.json"))
    ap.add_argument("--base", type=int, default=21100)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--only", default="")
    A = ap.parse_args()
    A.bin, A.work = os.path.abspath(A.bin), os.path.abspath(A.work)
    if not ((21000 <= A.base and A.base + 300 <= 25999) or (32000 <= A.base and A.base + 300 <= 32999)):
        sys.exit("--base must keep every port (base..base+300) inside 21000-25999 or 32000-32999")
    if os.path.exists(A.work) and os.listdir(A.work):
        sys.exit(f"{A.work} is not empty")
    os.makedirs(A.work, exist_ok=True)
    for w in ("wa.json", "wb.json"):
        r = subprocess.run([os.path.join(A.bin, "sost-cli"), "--wallet", os.path.join(A.work, w), "newwallet"],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stdout + r.stderr)
    A.wallet_a, A.wallet_b = os.path.join(A.work, "wa.json"), os.path.join(A.work, "wb.json")
    only = set(x for x in A.only.split(",") if x)

    def want(s):
        return not only or s in only or s.split("_")[0] in only

    t0 = time.time()
    try:
        base = build_base("base", 4)
        plan = [
            ("s1_race_1", lambda s: scn_p2p_fork(s, base, 1, 2)),
            ("s2_reorg_2", lambda s: scn_p2p_fork(s, base, 2, 3)),
            ("s3_reorg_5", lambda s: scn_p2p_fork(s, base, 5, 6)),
            ("s4_deep_at_cap", lambda s: scn_p2p_fork(s, base, REORG_CAP, REORG_CAP + 1)),
            ("s5_deep_over_cap", lambda s: scn_p2p_fork(s, base, REORG_CAP + 1, REORG_CAP + 2, expect=False, timeout=60)),
            ("s7_reverse_submit", lambda s: scn_reverse_submit(s, base)),
            ("s8_reverse_p2p", lambda s: scn_reverse_p2p(s, base)),
            ("s9_unsolicited_tip", lambda s: scn_unsolicited_tip(s, base)),
            ("s10_invalid_fork", lambda s: scn_invalid_fork(s, base)),
            ("s11_reconnect", lambda s: scn_reconnect(s, base)),
            ("s12_orphan_flood", lambda s: scn_orphan_flood(s, base)),
            ("s13_reconnect_after_orphans", lambda s: scn_reconnect_after_orphans(s, base)),
            # fork / orphan PoW validation (fork_block_precheck + full validation at connect)
            ("s14_valid_ooo_fullverify", lambda s: scn_valid_ooo_fullverify(s, base)),
            ("s15_invalid_pow_parent", lambda s: bad_branch_then_honest(
                s, base, 1, lambda j: j.update(commit="ff" * 32), same_id=False, full=False,
                expect_storage_reject=True)),
            ("s16_invalid_pow_child", lambda s: bad_branch_then_honest(
                s, base, 2, lambda j: j.update(commit="ff" * 32), same_id=False, full=False,
                expect_storage_reject=True)),
            ("s17_invalid_cx_witness", lambda s: bad_branch_then_honest(
                s, base, 2, mut_witness, same_id=True, full=False, expect_storage_reject=False)),
            ("s18_invalid_cx_witness_fullverify", lambda s: bad_branch_then_honest(
                s, base, 2, mut_witness, same_id=True, full=True, expect_storage_reject=True)),
            ("s19_invalid_longer_fork", lambda s: bad_branch_then_honest(
                s, base, 1, lambda j: j.update(commit="00" * 32), same_id=False, full=False,
                expect_storage_reject=False)),
            ("s20_invalid_longer_fork_fullverify", lambda s: bad_branch_then_honest(
                s, base, 1, lambda j: j.update(commit="00" * 32), same_id=False, full=True,
                expect_storage_reject=True)),
            ("s21_delayed_parent", lambda s: scn_delayed_parent(s, base)),
            ("s22_blockid_mutation", lambda s: scn_blockid_mutation(s, base)),
        ]
        for name, fn in plan:
            if want(name):
                try:
                    fn(name)
                except Exception as e:
                    check(name, f"scenario completed without harness error", False, repr(e)[:300])
                    stop_all()
        if want("s6_deep_sacsv2"):
            try:
                base2 = extend_base(base, "base42", SACS_V2 + 1)
                scn_p2p_fork("s6_deep_sacsv2", base2, REORG_CAP + 2, REORG_CAP + 3, timeout=120)
            except Exception as e:
                check("s6_deep_sacsv2", "scenario completed without harness error", False, repr(e)[:300])
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
        f"   ({time.time() - t0:.0f}s)")
    sys.exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Five-node P2P autonomy lab (DEVNET, real nodes, no DNS, seeds unreachable).

Run it inside a network namespace that has only loopback, so sostcore.com cannot be resolved
and the default seeds are unreachable (the nodes run their DEFAULT bootstrap, no --noseed):

  unshare -rn sh -c 'ip link set lo up && python3 tests/p2p/run_p2p_lab.py \
      --bin <devnet build> --work <new empty dir> [--old-bin <old devnet build>]'

Build (devnet profile):
  cmake -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=ON <src>
  make -j2 sost-node sost-miner sost-cli

Phases
  L1 line topology A-B-C-D-E: each node only knows its left neighbour (--addnode). Measures, per
     node, t_full_propagation = time until its address book (peers.txt) holds the listen
     address of every other node, and the time to >= 3 outbound peers. Target <= 1800 s.
  L2 block propagation over the grown mesh (block mined on A reaches E).
  L3 restart: every node is stopped and restarted with NO --addnode/--connect; it must reconnect
     from peers.txt alone (>= 1 peer in 60 s, >= 3 outbound in 600 s) and keep syncing.
  L4 clean node F (empty datadir, only --addnode to one node) syncs to the tip and discovers
     the others through gossip; clean node G (empty chain) whose ONLY input is a peers.txt with
     a sostcore.com hostname + one IPv4 entry recovers through the IPv4 entry.
  L5 (with --old-bin) interoperability with the previous binary in both directions: new nodes
     dial an old node and the old node dials a new node; handshake, block relay both ways, no
     misbehaviour penalties; the old node also reads a new-format peers.txt.

Ports: P2P base+1.., RPC base+101.. (base default 32000; all inside 32000-32999).
Every process started here is stopped by its recorded PID (argv[0] checked). One miner at a time.
"""
import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
A = None
PROCS = {}
RESULTS = []
T0 = time.time()


def log(m):
    print(f"[{time.time() - T0:7.1f}s] {m}", flush=True)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    log(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def spawn(argv, cwd, logf, niceness=19):
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


class Node:
    def __init__(self, idx, name, binary):
        self.idx, self.name, self.bin = idx, name, binary
        self.ip = f"127.0.0.{20 + idx}"
        self.p2p = A.base + idx
        self.rpcport = A.base + 100 + idx
        self.dir = os.path.join(A.work, name)
        self.logf = os.path.join(A.work, name + ".log")
        os.makedirs(self.dir, exist_ok=True)
        self.proc = None

    @property
    def addr(self):
        return f"{self.ip}:{self.p2p}"

    def start(self, addnode=(), connect=()):
        argv = [os.path.join(self.bin, "sost-node"), "--profile", "dev", "--genesis", A.genesis,
                "--chain", os.path.join(self.dir, "chain.json"), "--port", str(self.p2p),
                "--rpc-port", str(self.rpcport), "--rpc-noauth", "--p2p-bind", self.ip]
        for a in addnode:
            argv += ["--addnode", a]
        for c in connect:
            argv += ["--connect", c]
        with open(self.logf, "a") as f:
            f.write(f"\n===== start t={time.time():.0f} argv={' '.join(argv[1:])}\n")
        self.mark = os.path.getsize(self.logf)
        self.proc = spawn(argv, self.dir, self.logf)
        t = time.time()
        while time.time() - t < 120:
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

    def book(self):
        out = set()
        try:
            for ln in open(os.path.join(self.dir, "peers.txt")):
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    out.add(ln.split()[0])
        except FileNotFoundError:
            pass
        return out

    def info(self):
        return self.rpc("getaddrbookinfo")

    def outbound(self):
        try:
            if self.bin == A.bin:
                return int(self.info()["outbound"])
            return sum(1 for p in self.rpc("getpeerinfo") if p.get("direction") == "outbound")
        except Exception:
            return -1

    def logtext(self):
        with open(self.logf, errors="replace") as f:
            f.seek(self.mark)
            return f.read()


def wait_for(pred, timeout, step=1.0):
    t = time.time()
    while time.time() - t < timeout:
        try:
            if pred():
                return time.time() - t
        except Exception:
            pass
        time.sleep(step)
    return None


def free_gb():
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemAvailable:"):
            return int(ln.split()[1]) / 1048576
    return 0


def mine(node, n):
    t = time.time()
    while free_gb() < 6:                    # shared machine: wait for room, never overcommit
        if time.time() - t > 3600:
            raise RuntimeError(f"only {free_gb():.1f} GB available for 1 h, need >= 6 GB for a devnet miner")
        time.sleep(15)
    if time.time() - t > 1:
        log(f"  (waited {time.time() - t:.0f}s for >= 6 GB free memory before mining)")
    h0 = node.height()
    addr = json.load(open(A.wallet))["keys"][0]["address"]
    p = spawn([os.path.join(A.bin, "sost-miner"), "--profile", "dev", "--genesis", A.genesis,
               "--rpc", f"127.0.0.1:{node.rpcport}", "--address", addr, "--wallet", A.wallet,
               "--mining-key-label", "default", "--blocks", str(n), "--threads", "2", "--realtime"],
              A.work, os.path.join(A.work, "miner.log"))
    p.wait()
    PROCS.pop(p.pid, None)
    if node.height() != h0 + n:
        raise RuntimeError(f"{node.name}: mined {node.height() - h0} != {n}")


PEN_RE = re.compile(r"\[P2P\] (Misbehavior \+\d+ \(.*?\) from \S+|BANNED \S+: .*)")


def penalties(node):
    return PEN_RE.findall(node.logtext())


def main():
    global A
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--old-bin", default="")
    ap.add_argument("--work", required=True)
    ap.add_argument("--genesis", default=os.path.join(ROOT, "genesis_block.json"))
    ap.add_argument("--base", type=int, default=32000)
    ap.add_argument("--allow-dns", action="store_true", help="do not require an environment without DNS")
    A = ap.parse_args()
    A.bin, A.work = os.path.abspath(A.bin), os.path.abspath(A.work)
    A.old_bin = os.path.abspath(A.old_bin) if A.old_bin else ""
    if not (32000 <= A.base and A.base + 200 <= 32999):
        sys.exit("--base must keep every port (base..base+200) inside 32000-32999")
    if os.path.exists(A.work) and os.listdir(A.work):
        sys.exit(f"{A.work} is not empty")
    os.makedirs(A.work, exist_ok=True)
    dns_ok = True
    try:
        socket.getaddrinfo("seed.sostcore.com", 19333)
    except OSError:
        dns_ok = False
    log(f"environment: seed.sostcore.com resolvable = {dns_ok}")
    if dns_ok and not A.allow_dns:
        sys.exit("DNS works here: run inside `unshare -rn` (loopback only) or pass --allow-dns")
    check("environment: sostcore.com seeds unresolvable (no DNS)", not dns_ok)
    A.wallet = os.path.join(A.work, "w.json")
    r = subprocess.run([os.path.join(A.bin, "sost-cli"), "--wallet", A.wallet, "newwallet"], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stdout + r.stderr)

    nodes = [Node(i + 1, n, A.bin) for i, n in enumerate("ABCDE")]
    others = {n.name: {m.addr for m in nodes if m is not n} for n in nodes}
    summary = {}
    try:
        # ---------------- L1 line topology
        log("L1: line topology A <- B <- C <- D <- E (each --addnode its left neighbour only)")
        t_start = time.time()
        nodes[0].start()
        for i in range(1, 5):
            nodes[i].start(addnode=[nodes[i - 1].addr])
        mine(nodes[0], 3)
        prop, out3 = {}, {}
        deadline = t_start + 1800
        while time.time() < deadline and (len(prop) < 5 or len(out3) < 5):
            for n in nodes:
                if n.name not in prop and others[n.name] <= n.book():
                    prop[n.name] = time.time() - t_start
                    log(f"  {n.name}: address book holds all 4 other nodes after {prop[n.name]:.0f}s")
                if n.name not in out3 and n.outbound() >= 3:
                    out3[n.name] = time.time() - t_start
                    log(f"  {n.name}: >= 3 outbound after {out3[n.name]:.0f}s")
            time.sleep(5)
        summary["t_full_propagation_s"] = {k: round(v) for k, v in sorted(prop.items())}
        summary["t_outbound3_s"] = {k: round(v) for k, v in sorted(out3.items())}
        check("L1 every node learned every other node's address within 1800 s",
              len(prop) == 5 and max(prop.values()) <= 1800, json.dumps(summary["t_full_propagation_s"]))
        check("L1 every node reached >= 3 outbound peers without a seed", len(out3) == 5,
              json.dumps(summary["t_outbound3_s"]))
        for n in nodes:
            ok = all(re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", a) for a in n.book())
            mode = oct(os.stat(os.path.join(n.dir, "peers.txt")).st_mode & 0o777)
            check(f"L1 {n.name}: peers.txt holds only IPv4 literals, mode {mode}", ok and mode == "0o600")
        summary["peerinfo_sources_E"] = sorted({p["source"] for p in nodes[4].rpc("getpeerinfo")})
        check("L1 getpeerinfo exposes source + subnet16", all("source" in p and "subnet16" in p for p in nodes[4].rpc("getpeerinfo")),
              str(summary["peerinfo_sources_E"]))
        dns_fail = sum(n.logtext().count("Cannot resolve seed") for n in nodes)
        check("L1 default seeds were tried and failed (no DNS), nodes still meshed", dns_fail > 0, f"{dns_fail} failed seed lookups")

        # ---------------- L2 block propagation over the mesh
        log("L2: block mined on A reaches every node")
        mine(nodes[0], 1)
        tip = nodes[0].tip()
        t = wait_for(lambda: all(n.tip() == tip for n in nodes), 300)
        summary["L2_block_propagation_s"] = None if t is None else round(t, 1)
        check("L2 block propagated to all 5 nodes", t is not None, f"{t:.1f}s" if t is not None else "timeout")

        # ---------------- L3 restart with no addnode / connect
        log("L3: stop all, restart with NO --addnode/--connect (peers.txt only, seeds unreachable)")
        for n in nodes:
            n.stop()
        for n in nodes:
            n.start()
        t1 = wait_for(lambda: all(n.outbound() >= 1 for n in nodes), 60)
        check("L3 every node has >= 1 peer within 60 s of restart", t1 is not None, f"{t1:.0f}s" if t1 is not None else "")
        t3 = wait_for(lambda: all(n.outbound() >= 3 for n in nodes), 600, 5)
        check("L3 every node back to >= 3 outbound within 600 s", t3 is not None, f"{t3:.0f}s" if t3 is not None else "")
        stored = sum(n.logtext().count("store peer connected") for n in nodes)
        check("L3 reconnection came from the address book", stored >= 5, f"{stored} 'store peer connected' lines")
        mine(nodes[4], 1)
        tip = nodes[4].tip()
        t = wait_for(lambda: all(n.tip() == tip for n in nodes), 300)
        check("L3 block mined on E after restart reaches every node", t is not None, f"{t:.1f}s" if t is not None else "")
        summary["L3"] = {"t_1peer_s": t1, "t_3outbound_s": t3}

        # ---------------- L4 clean nodes
        log("L4: clean node F (empty datadir, only --addnode C)")
        F = Node(6, "F", A.bin)
        F.start(addnode=[nodes[2].addr])
        tip = nodes[0].tip()
        t = wait_for(lambda: F.tip() == tip, 300)
        check("L4 F synced to the tip from an empty datadir", t is not None, f"{t:.0f}s, h={F.height()}" if t is not None else "")
        allfive = {n.addr for n in nodes}
        t = wait_for(lambda: allfive <= F.book() and F.outbound() >= 3, 900, 5)
        check("L4 F discovered all 5 nodes via gossip and holds >= 3 outbound", t is not None,
              f"{t:.0f}s" if t is not None else f"book={sorted(F.book())}")
        log("L4: clean node G (empty chain, peers.txt = legacy hostname + one IPv4 entry, no addnode)")
        G = Node(7, "G", A.bin)
        with open(os.path.join(G.dir, "peers.txt"), "w") as f:
            f.write(f"seed-eu.sostcore.com:19333\n{nodes[3].addr}\n")
        G.start()
        t = wait_for(lambda: G.tip() == tip, 300)
        check("L4 G recovered and synced from the persisted IPv4 entry (hostname unresolvable)", t is not None,
              f"{t:.0f}s" if t is not None else "")
        t = wait_for(lambda: G.outbound() >= 3, 900, 5)
        check("L4 G grew to >= 3 outbound via gossip", t is not None, f"{t:.0f}s" if t is not None else "")
        check("L4 G no longer stores the hostname", "seed-eu.sostcore.com:19333" not in G.book())
        F.stop(); G.stop()

        # ---------------- L5 old <-> new interoperability
        if A.old_bin:
            log("L5: interoperability with the previous binary")
            O = Node(8, "O", A.old_bin)
            O.start(connect=[nodes[0].addr])          # old dials new (old has no --addnode)
            tip = nodes[0].tip()
            t = wait_for(lambda: O.tip() == tip, 300)
            check("L5 old node (dialing a new node) synced the chain", t is not None, f"{t:.0f}s" if t is not None else "")
            H = Node(9, "H", A.bin)
            H.start(addnode=[O.addr])               # new dials old
            t = wait_for(lambda: H.tip() == tip, 300)
            check("L5 new node (dialing ONLY the old node) synced the chain through it", t is not None,
                  f"{t:.0f}s" if t is not None else "")
            mine(O, 1)                              # block found on the old node
            tip = O.tip()
            t = wait_for(lambda: all(n.tip() == tip for n in nodes + [H]), 300)
            check("L5 block mined on the OLD node reached every new node", t is not None, f"{t:.1f}s" if t is not None else "")
            mine(nodes[2], 1)                       # block found on a new node
            tip = nodes[2].tip()
            t = wait_for(lambda: O.tip() == tip, 300)
            check("L5 block mined on a NEW node reached the old node", t is not None, f"{t:.1f}s" if t is not None else "")
            pen = penalties(O) + sum((penalties(n) for n in nodes + [H]), [])
            check("L5 no misbehaviour/ban on either side", not pen, "; ".join(pen)[:300])
            vers_old = [l for l in O.logtext().splitlines() if "version OK" in l]
            check("L5 old node accepted the 51-byte VERS of new nodes", len(vers_old) >= 1, vers_old[0][:120] if vers_old else "")
            O.stop()
            log("L5: old binary reads a NEW-format peers.txt (downgrade)")
            O2 = Node(10, "O2", A.old_bin)
            shutil.copy2(os.path.join(nodes[1].dir, "peers.txt"), os.path.join(O2.dir, "peers.txt"))
            O2.start()
            t = wait_for(lambda: O2.tip() == tip, 300)
            check("L5 old node bootstrapped from a v2 peers.txt and synced", t is not None, f"{t:.0f}s" if t is not None else "")
            O2.stop(); H.stop()
    except Exception as e:
        check("lab completed without harness error", False, repr(e)[:300])
    finally:
        stop_all()
    with open(os.path.join(A.work, "lab_summary.json"), "w") as f:
        json.dump({"summary": summary, "results": RESULTS}, f, indent=1, default=str)
    n_ok = sum(1 for r in RESULTS if r[1])
    log(f"checks: {n_ok}/{len(RESULTS)} PASS")
    log("summary: " + json.dumps(summary, default=str))
    sys.exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()

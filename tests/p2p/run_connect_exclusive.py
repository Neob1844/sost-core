#!/usr/bin/env python3
"""--connect stays exclusive on reconnect and restart; --addnode keeps normal discovery
(DEVNET, real nodes, loopback only).

Regression for the gate finding F3: the "no peers left" reconnect loop dialed the address
book (peers.txt) and gossiped addresses after the --connect list, so a node started with
--connect could end up connected to (and syncing from) a peer it was told not to use.

Run it inside a network namespace that has only loopback (DNS seeds and fallback IPs are then
unreachable, so nothing outside the lab can ever be dialed):

  unshare -rn sh -c 'ip link set lo up && python3 tests/p2p/run_connect_exclusive.py \\
      --bin <devnet build> --work <new empty dir>'

Nodes (each its own datadir and loopback IP): S1, S2 = discoverable peers, C = the --connect
target, X = node under test, Y = --addnode node.

  P1 learn:      X (no --connect, --addnode S1) meets S1; S2 is connected to S1, so X also learns
                 S2 by gossip; X persists both in its peers.txt.
  P2 restart:    X restarted with --noseed --connect C while C is DOWN: across >= 3 reconnect
                 cycles X dials nothing but C (S1/S2 see no connection from X, X has no peer).
  P3 restart:    same without --noseed (seeds/fallback unreachable here anyway).
  P4 reconnect:  C up; X --connect C, C knows S1/S2 and gossips them to X; C goes away; X's
                 reconnect loop must again dial only C; when C returns X reconnects to it.
  P5 addnode:    Y with --addnode S1 only (no --connect): Y connects to S1 AND discovers and dials
                 another peer (store/gossip discovery still works next to --addnode); after S1
                 goes away Y's peer set is refilled from discovery, and S1 is redialed when back.

Ports base..base+30 (P2P base+i, RPC base+10+i). Every process started here is stopped by its
recorded PID (argv[0] checked).
"""
import argparse
import json
import os
import signal
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


class Node:
    def __init__(self, idx, name):
        self.idx, self.name = idx, name
        self.ip = f"127.0.0.{51 + idx}"
        self.p2p = A.base + idx
        self.rpcport = A.base + 10 + idx
        self.dir = os.path.join(A.work, name)
        self.logf = os.path.join(A.work, name + ".log")
        os.makedirs(self.dir, exist_ok=True)
        self.proc = None
        self.mark = 0

    @property
    def addr(self):
        return f"{self.ip}:{self.p2p}"

    def start(self, connect=(), addnode=(), noseed=False):
        argv = [os.path.join(A.bin, "sost-node"), "--profile", "dev", "--genesis", A.genesis,
                "--chain", os.path.join(self.dir, "chain.json"), "--port", str(self.p2p),
                "--rpc-port", str(self.rpcport), "--rpc-noauth", "--p2p-bind", self.ip]
        if noseed:
            argv.append("--noseed")
        for c in connect:
            argv += ["--connect", c]
        for a in addnode:
            argv += ["--addnode", a]
        with open(self.logf, "a") as f:
            f.write(f"\n===== start {' '.join(argv[1:])} t={time.time():.0f}\n")
        self.mark = os.path.getsize(self.logf)
        p = subprocess.Popen(argv, cwd=self.dir, stdout=open(self.logf, "a"), stderr=subprocess.STDOUT,
                             preexec_fn=lambda: os.nice(10))
        PROCS[p.pid] = (argv[0], p)
        self.proc = p
        t = time.time()
        while time.time() - t < 120:
            try:
                self.rpc("getblockcount")
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

    def peers(self):
        return [p for p in self.rpc("getpeerinfo") if not p.get("feeler")]

    def out_ports(self):
        return sorted(int(p["addr"].rsplit(":", 1)[1]) for p in self.peers() if p["direction"] == "outbound")

    def inbound_from(self, other):
        """Inbound peers whose advertised listen port is `other`'s P2P port."""
        return [p for p in self.peers() if p["direction"] == "inbound" and int(p.get("listen_port", 0)) == other.p2p]

    def logtext(self):
        with open(self.logf, "r", errors="replace") as f:
            f.seek(self.mark)
            return f.read()

    def peers_txt(self):
        try:
            return open(os.path.join(self.dir, "peers.txt")).read()
        except FileNotFoundError:
            return ""


def wait_for(pred, timeout, step=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(step)
    return False


def watch_exclusive(x, c_port, others, seconds):
    """For `seconds`, X must never hold a peer other than C and none of `others` may see X."""
    bad = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            for p in x.peers():
                port = int(p["addr"].rsplit(":", 1)[1]) if p["direction"] == "outbound" else -1
                if p["direction"] == "outbound" and port != c_port:
                    bad.append(f"X outbound to :{port} (source={p.get('source')})")
            for o in others:
                if o.proc and o.inbound_from(x):
                    bad.append(f"{o.name} has an inbound connection from X")
        except Exception as e:
            bad.append(f"rpc error {e!r}")
        time.sleep(2)
    return sorted(set(bad))


def main():
    global A
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--genesis", default=os.path.join(ROOT, "genesis_block.json"))
    ap.add_argument("--base", type=int, default=34400)
    ap.add_argument("--watch", type=int, default=100, help="seconds per exclusivity watch (>= 3 cycles of 30 s)")
    A = ap.parse_args()
    A.bin, A.work = os.path.abspath(A.bin), os.path.abspath(A.work)
    if os.path.exists(A.work) and os.listdir(A.work):
        sys.exit(f"{A.work} is not empty")
    os.makedirs(A.work, exist_ok=True)
    S1, S2, C, X, Y = (Node(i, n) for i, n in enumerate(("S1", "S2", "C", "X", "Y")))
    try:
        # ---- P1: X learns S1 (addnode) and S2 (gossip) and persists them
        log("P1: S1, S2 up (S2 --addnode S1); X --addnode S1 learns both")
        # S1/S2 run the default discovery (no --noseed; DNS seeds and fallback IPs are unreachable
        # in the namespace) so S1 verifies S2's listen address with a feeler and gossips it.
        S1.start()
        S2.start(addnode=[S1.addr])
        wait_for(lambda: S1.inbound_from(S2), 60)
        X.start(addnode=[S1.addr])
        ok = wait_for(lambda: S1.addr in X.peers_txt() and S2.addr in X.peers_txt(), 420)
        check("P1 X persisted S1 (addnode) and S2 (learned by gossip) in peers.txt", ok,
              X.peers_txt().replace("\n", " ")[:200])
        X.stop()
        # From here on S1/S2 run with --noseed (no outbound discovery of their own), so any
        # connection between X and them can only have been dialed by X.
        S2.stop(); S1.stop()
        S1.start(noseed=True)
        S2.start(noseed=True, addnode=[S1.addr])

        # ---- P2/P3: restart with --connect C (C down): never dial the address book or seeds
        for label, noseed in (("P2 --noseed --connect", True), ("P3 --connect (seeds on)", False)):
            log(f"{label}: X restarted with --connect C while C is down (peers.txt lists S1, S2)")
            X.start(connect=[C.addr], noseed=noseed)
            bad = watch_exclusive(X, C.p2p, (S1, S2), A.watch)
            lt = X.logtext()
            check(f"{label}: across {A.watch}s of reconnect cycles X dialed nobody but C "
                  "(no peers.txt / gossip / seed connection)", not bad and not X.peers(), "; ".join(bad)[:300])
            check(f"{label}: reconnect loop ran and announced the exclusive mode",
                  "attempting reconnect (connect/addnode only, exclusive)" in lt and
                  "attempting reconnect (connect/addnode/store" not in lt)
            X.stop()

        # ---- P4: C gossips S1/S2 to X; C disappears; X redials only C; C comes back
        log("P4: C up and connected to S1, S2; X --noseed --connect C")
        C.start(addnode=[S1.addr, S2.addr])
        wait_for(lambda: len(C.out_ports()) >= 2, 60)
        X.start(connect=[C.addr], noseed=True)
        ok = wait_for(lambda: X.out_ports() == [C.p2p], 60)
        check("P4 X connected to C only", ok, f"X outbound ports {X.out_ports()}")
        ok = wait_for(lambda: X.rpc("getaddrbookinfo")["entries"] >= 2, 120)
        info = X.rpc("getaddrbookinfo")
        check("P4 X learned addresses from C (address book / gossip candidates non-empty)", ok,
              f"entries={info['entries']} gossip_candidates={info['gossip_candidates']}")
        C.stop()
        ok = wait_for(lambda: not X.peers(), 30)
        bad = watch_exclusive(X, C.p2p, (S1, S2), A.watch)
        lt = X.logtext()
        check(f"P4 after C went away, {A.watch}s of reconnect cycles dialed only C (S1/S2 never)",
              ok and not bad and not X.peers(), "; ".join(bad)[:300])
        check("P4 the reconnect loop really ran (exclusive mode logged)",
              "attempting reconnect (connect/addnode only, exclusive)" in lt)
        C.start(addnode=[S1.addr, S2.addr])
        ok = wait_for(lambda: X.out_ports() == [C.p2p], 120)
        check("P4 when C came back X reconnected to it (and only to it)", ok, f"X outbound ports {X.out_ports()}")
        X.stop()

        # ---- P5: --addnode coexists with normal discovery
        log("P5: Y --addnode S1 only (no --connect, seeds unreachable)")
        Y.start(addnode=[S1.addr])
        ok1 = wait_for(lambda: S1.p2p in Y.out_ports(), 60)
        check("P5 Y connected to its --addnode peer S1", ok1, f"Y outbound {Y.out_ports()}")
        ok2 = wait_for(lambda: any(p != S1.p2p for p in Y.out_ports()), 240)
        check("P5 Y also discovered and dialed another peer (store/gossip discovery still on with --addnode)",
              ok2, f"Y outbound {Y.out_ports()}")
        S1.stop()
        ok3 = wait_for(lambda: S1.p2p not in Y.out_ports() and len(Y.out_ports()) >= 1, 120)
        check("P5 S1 gone: Y keeps/refills peers from discovery", ok3, f"Y outbound {Y.out_ports()}")
        S1.start(noseed=True)
        ok4 = wait_for(lambda: S1.p2p in Y.out_ports(), 150)
        check("P5 S1 back: Y redials its --addnode peer", ok4, f"Y outbound {Y.out_ports()}")
    except Exception as e:
        check("run completed without harness error", False, repr(e)[:300])
    finally:
        for n in (X, Y, C, S2, S1):
            n.stop()
    n_ok = sum(1 for r in RESULTS if r[1])
    log(f"RESULT: {n_ok}/{len(RESULTS)} checks PASS ({time.time() - T0:.0f}s)")
    sys.exit(0 if RESULTS and n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()

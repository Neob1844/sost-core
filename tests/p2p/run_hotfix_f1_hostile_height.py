#!/usr/bin/env python3
"""HOTFIX F-1 — hostile block heights over real P2P and submitblock (mainnet profile, real chain copy).

A mainnet-profile sost-node loads a copy of the real chain (0..100). A scripted plaintext peer
(minimal plaintext FakePeer, same as tests/p2p deep-fork harness) sends REAL mainnet blocks whose JSON "height" is
rewritten (height is not covered by the block id). A background thread polls getblockcount
every 50 ms the whole time and records the worst RPC latency around each probe.

Scenarios: orphan with unknown parent at 1e11 / 1e12 / 3e12 / INT64_MAX / 0 / -5; window edge
(tip+131553 kept, tip+131554 dropped); fork-parent (parent on the active chain) and fork-child
(parent = stored fork block) at sane and hostile heights; known-set poisoning (hostile copy
first, then the same block id at a sane height must still be processed); submitblock with a
hostile height; the honest peer is never penalised and stays connected.

Run inside `unshare -rn` (loopback only), e.g.
  unshare -rn sh -c 'ip link set lo up; python3 tests/p2p/run_hotfix_f1_hostile_height.py <bin dir> <new work dir> \
      genesis_block.json <copy of mainnet chain.json truncated to 0..100> <copy truncated to 0..3700> LABEL'
(the 0..3700 file only supplies real blocks 101..321 to send).
Exit 0 = all checks passed.
"""
import base64, json, os, re, signal, socket, struct, subprocess, sys, threading, time, urllib.request, shutil

MAGIC = 0x534F5354


PENALTY_RE = re.compile(r"\[P2P\] (Misbehavior \+\d+ \(.*?\) from (\S+)|BANNED (\S+): (.*))")


def penalties(node, ip):
    """Misbehaviour / ban lines in node's log (since its last start) about peer `ip`."""
    out = []
    for m in PENALTY_RE.finditer(node.logtext()):
        who = m.group(2) or m.group(3) or ""
        if who.startswith(ip + ":"):
            out.append(m.group(1))
    return out



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


BIN, WORK, GEN, CHAIN, FULL, LABEL = sys.argv[1:7]
GEN = os.path.abspath(GEN)
os.makedirs(WORK)
shutil.copy(CHAIN, os.path.join(WORK, "chain.json"))
pf = os.path.join(WORK, "pass"); open(pf, "w").write("p"); os.chmod(pf, 0o600)
AUTH = "Basic " + base64.b64encode(b"u:p").decode()
P2P, RPCP = 32761, 32862
RES = []
INT64_MAX = 2**63 - 1


def check(name, ok, detail=""):
    RES.append(bool(ok)); print(f"[{LABEL}] {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""), flush=True)


def rpc(method, params=None, timeout=600):
    req = urllib.request.Request(f"http://127.0.0.1:{RPCP}/",
                                 data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode(),
                                 headers={"content-type": "application/json", "Authorization": AUTH})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class Poller(threading.Thread):
    """getblockcount every 50 ms; records (t_start, latency)."""
    def __init__(self):
        super().__init__(daemon=True); self.samples = []; self.stop = False
    def run(self):
        while not self.stop:
            t = time.time()
            try: rpc("getblockcount", timeout=3600)
            except Exception: pass
            self.samples.append((t, time.time() - t)); time.sleep(0.05)
    def worst_since(self, t0):
        xs = [l for (t, l) in self.samples if t + l >= t0]
        return max(xs) if xs else None


node = subprocess.Popen([os.path.join(BIN, "sost-node"), "--profile", "mainnet", "--noseed", "--genesis", GEN,
                         "--chain", os.path.join(WORK, "chain.json"), "--wallet", os.path.join(WORK, "w.json"),
                         "--port", str(P2P), "--rpc-port", str(RPCP), "--rpc-user", "u", "--rpc-pass-file", pf],
                        cwd=WORK, stdout=open(os.path.join(WORK, "node.log"), "w"), stderr=subprocess.STDOUT)
log = lambda: open(os.path.join(WORK, "node.log"), errors="replace").read()
try:
    h0 = None
    for _ in range(300):
        try: h0 = rpc("getblockcount", timeout=5)["result"]; break
        except Exception: time.sleep(0.3)
    print(f"[{LABEL}] node height {h0}", flush=True)
    blocks = json.load(open(FULL))["blocks"]
    poll = Poller(); poll.start()
    peer = FakePeer("127.0.0.9", ("127.0.0.1", P2P), 0, mute=True)

    def probe(name, blk, limit=1.0, settle=0.4):
        t0 = time.time()
        peer.push([json.dumps(blk, separators=(",", ":"))])
        time.sleep(settle)
        r = rpc("getblockcount")["result"]
        w = poll.worst_since(t0) or 0.0
        dt_after = time.time() - t0 - settle
        check(f"{name}: getblockcount responsive (worst {w*1000:.1f} ms during probe)", w < limit and r == h0, f"tip={r}")
        return w

    def real(src, height, **kw):
        b = dict(blocks[src]); b["height"] = height; b.update(kw); return b

    # --- orphans with unknown parent (real blocks 301.., parent 300 unknown at tip 100)
    for i, H in enumerate([10**11, 10**12, 3 * 10**12, INT64_MAX, 0, -5]):
        probe(f"orphan unknown parent h={H}", real(301 + i, H))
    # --- window edge (relative to tip h0)
    probe("orphan at tip+131553 (inside window)", real(310, h0 + 131553))
    probe("orphan at tip+131554 (outside window)", real(311, h0 + 131554))
    lg = log()
    kept = f"[ORPHAN] Block h={h0 + 131553} stored" in lg
    dropped = f"Block h={h0 + 131554} " in lg and f"[ORPHAN] Block h={h0 + 131554} stored" not in lg
    check("window edge: tip+131553 stored as orphan, tip+131554 not stored", kept and dropped)
    hostile_stored = [H for H in (10**11, 10**12, 3 * 10**12, INT64_MAX) if f"[ORPHAN] Block h={H} stored" in lg]
    check("no hostile-height orphan stored", not hostile_stored, f"stored={hostile_stored}")

    # --- fork parent: parent = active block 50, synthetic id (fork blocks are stored before PoW check on this base)
    pid50 = rpc("getblockhash", [50])["result"]
    fA = real(51, 51, block_id="ab" * 32, prev_hash=pid50)
    probe("fork parent (prev=active #50) at sane height 51", fA)
    probe("fork parent (prev=active #50) at hostile height 1e12", real(52, 10**12, block_id="ac" * 32, prev_hash=pid50))
    probe("fork child (prev=stored fork) at INT64_MAX", real(53, INT64_MAX, block_id="ad" * 32, prev_hash="ab" * 32))
    probe("fork child (prev=stored fork) at sane height 52", real(54, 52, block_id="ae" * 32, prev_hash="ab" * 32))
    lg = log()
    check("fork parent at sane height stored as fork candidate", "bid=abababababababab" in lg and "Fork stored" in lg)

    # --- known-set poisoning: hostile copy of block 101 first, then the honest copy must still connect
    probe("block #101 id with hostile height 1e12", real(101, 10**12))
    peer.push([json.dumps(blocks[101], separators=(",", ":"))]); time.sleep(1.5)
    h1 = rpc("getblockcount")["result"]
    check("honest #101 (same id) accepted after the hostile copy", h1 == h0 + 1, f"tip={h1}")
    h0 = h1

    pens_hostile = penalties(type("N", (), {"logtext": staticmethod(log)})(), "127.0.0.9")
    check("no misbehaviour recorded against the peer for any hostile/out-of-window height probe", not pens_hostile,
          f"penalties={pens_hostile}")
    # --- same, with a wrong but in-window height (pre-existing height-not-in-id caching; informational)
    probe("block #102 id with in-window wrong height tip+500", real(102, h0 + 500))
    peer.push([json.dumps(blocks[102], separators=(",", ":"))]); time.sleep(1.5)
    h2 = rpc("getblockcount")["result"]
    print(f"[{LABEL}] INFO  honest #102 after an in-window wrong-height copy: tip={h2} (accepted={h2 == h0 + 1})", flush=True)
    h0 = h2

    # --- submitblock path
    t0 = time.time()
    r = rpc("submitblock", [json.dumps(real(320, INT64_MAX), separators=(",", ":"))])
    dt = time.time() - t0
    check(f"submitblock with height INT64_MAX answered in {dt*1000:.1f} ms", dt < 1.0, str(r)[:160])
    t0 = time.time()
    r = rpc("submitblock", [json.dumps(real(321, 3 * 10**12), separators=(",", ":"))])
    dt = time.time() - t0
    check(f"submitblock with height 3e12 answered in {dt*1000:.1f} ms", dt < 1.0, str(r)[:160])

    # --- peer health
    time.sleep(1)
    pens = penalties(type("N", (), {"logtext": staticmethod(log)})(), "127.0.0.9")
    # the in-window wrong-height #102 copy has a KNOWN parent and a lying height: it is a really
    # invalid block (parent height != h-1) and costs +10 on every build — that one is expected.
    check("only the genuinely invalid in-window lying block was penalised (+10), peer not banned",
          len(pens) <= 1 and all("+10 (invalid block)" in p for p in pens), f"penalties={pens}")
    check("peer still connected", not peer.closed and len(rpc("getpeerinfo")["result"]) >= 1)
    poll.stop = True
    allw = max(l for (_, l) in poll.samples)
    check(f"worst getblockcount latency over the whole run {allw*1000:.1f} ms (< 1 s)", allw < 1.0, f"{len(poll.samples)} samples")
    check("node alive", node.poll() is None)
    peer.close()
finally:
    node.send_signal(signal.SIGTERM)
    try: node.wait(30)
    except Exception: node.kill()
print(f"[{LABEL}] RESULT {sum(RES)}/{len(RES)} checks passed", flush=True)
sys.exit(0 if all(RES) else 1)

#!/usr/bin/env python3
"""HOTFIX F2 — a non-mining follower must keep receiving blocks (real sost-node + sost-miner, DEVNET_FAST).

Topology: S = server (the only miner, real sost-miner via RPC), F1/F2 = non-mining followers that
--connect S. Every node has its own datadir under WORK; isolated ports; meant to run in `unshare -rn`.

Phases
  P1 growing lag while connected : F1 joins S at a low height, S mines > 150 blocks continuously;
                                   F1 must track the tip (never stall at handshake+49/+50).
  P2 initial lag > 50            : F2 starts from genesis while S is > 150 ahead; syncs via GETB,
                                   then keeps following while S mines 60 more.
  P3 multiple peers              : F1 and F2 both connected during P2 / P4 mining.
  P4 follower restart            : F1 stopped, S mines 60, F1 restarted: catches up and keeps following 60 more.
  P5 server restart / reconnect  : S restarted (followers reconnect on their own), S mines 60: both follow.
  Always: every follower converges to S's tip id; no misbehaviour/ban lines about honest peers on any
  node; followers stay connected (getpeerinfo >= 1) at each checkpoint; no flooding (S never relays a
  block to more peers than it has, and never twice to the same peer).
Build: cmake -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DSOST_DEVNET_FORKS=ON <src>; make sost-node sost-miner sost-cli
usage: unshare -rn sh -c 'ip link set lo up; python3 tests/p2p/run_hotfix_f2_follower_liveness.py <build dir> <new work dir> genesis_block.json LABEL [blocks_p1=160]'
Ports 30700..30721 (inside the private network namespace). Kills only processes it started (PID + cmdline).
"""
import json, os, re, shutil, signal, subprocess, sys, time, urllib.request

BUILD, WORK, GEN, LABEL = sys.argv[1:5]
GEN = os.path.abspath(GEN)
NP1 = int(sys.argv[5]) if len(sys.argv) > 5 else 160
# P2P_ENC=on runs every node with --p2p-enc on (as the production node does); default: build default.
ENC = ["--p2p-enc", os.environ["P2P_ENC"]] if os.environ.get("P2P_ENC") else []
NODE, MINER, CLI = f"{BUILD}/sost-node", f"{BUILD}/sost-miner", f"{BUILD}/sost-cli"
os.makedirs(WORK)
PORTS = {"S": (30700, 30701), "F1": (30710, 30711), "F2": (30720, 30721)}
procs, RES = {}, []


def log(*a): print(f"[{LABEL}]", *a, flush=True)
def check(ok, name, detail=""):
    RES.append(bool(ok)); print(f"[{LABEL}] {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""), flush=True); return ok


def rpc(n, m, p=None, timeout=30):
    body = json.dumps({"method": m, "params": p or [], "id": 1}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORTS[n][1]}/", data=body,
                                    headers={"content-type": "application/json"}), timeout=timeout) as r:
            return json.loads(r.read().decode()).get("result")
    except Exception:
        return None


def height(n): return rpc(n, "getblockcount")
def tipid(n): return rpc(n, "getbestblockhash")
def peers(n): return rpc(n, "getpeerinfo") or []
def logtext(n): return open(f"{WORK}/{n}/node.log", errors="replace").read()


def own_kill(p):
    if p is None or p.poll() is not None: return
    try: cmd = open(f"/proc/{p.pid}/cmdline", "rb").read().decode(errors="replace")
    except OSError: return
    if WORK in cmd:
        p.terminate()
        try: p.wait(60)
        except subprocess.TimeoutExpired: p.kill(); p.wait(10)


def start(n, extra):
    d = f"{WORK}/{n}"; os.makedirs(d, exist_ok=True)
    p2p, rp = PORTS[n]
    procs[n] = subprocess.Popen([NODE, "--profile", "dev", "--genesis", GEN, "--chain", f"{d}/chain.json",
                                 "--wallet", f"{d}/w.json", "--port", str(p2p), "--rpc-port", str(rp),
                                 "--rpc-noauth", "--noseed"] + ENC + extra,
                                cwd=d, stdout=open(f"{d}/node.log", "a"), stderr=subprocess.STDOUT)
    for _ in range(600):
        time.sleep(0.5)
        if isinstance(height(n), int): return
    raise SystemExit(f"node {n} did not boot")


def stop(n): own_kill(procs.pop(n, None)); time.sleep(1)


ADDR = None
def miner_start(n):
    p = subprocess.Popen(["nice", "-n", "19", MINER, "--profile", "dev", "--genesis", GEN, "--rpc", f"127.0.0.1:{PORTS['S'][1]}",
                          "--address", ADDR, "--wallet", f"{WORK}/mw.json", "--mining-key-label", "default",
                          "--blocks", str(n), "--threads", "2", "--realtime"],
                         cwd=f"{WORK}/S", stdout=open(f"{WORK}/miner.log", "a"), stderr=subprocess.STDOUT)
    procs["miner"] = p; return p


def mine(n, watch=(), sample=None):
    """S mines n blocks; returns per-second samples of (S, followers) heights."""
    h0 = height("S"); p = miner_start(n); t0 = time.time(); samples = []
    while p.poll() is None:
        if time.time() - t0 > 300 + 30 * n: own_kill(p); raise SystemExit("miner timeout")
        samples.append({k: height(k) for k in ("S",) + tuple(watch)}); time.sleep(1)
    procs.pop("miner", None)
    h1 = height("S")
    if h1 != h0 + n: raise SystemExit(f"mine: {h1} != {h0 + n}")
    return samples


def converge(f, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if height(f) == height("S") and tipid(f) == tipid("S"): return time.time() - t0
        time.sleep(1)
    return None


PEN = re.compile(r"Misbehavior \+\d+ \([^)]*\) from \S+|BANNED \S+")
def penalties(n): return PEN.findall(logtext(n))


def max_lag(samples, f):
    lags = [s["S"] - s[f] for s in samples if isinstance(s.get("S"), int) and isinstance(s.get(f), int)]
    return max(lags) if lags else None


try:
    r = subprocess.run([CLI, "--wallet", f"{WORK}/mw.json", "newwallet"], capture_output=True, text=True, timeout=60)
    ADDR = json.load(open(f"{WORK}/mw.json"))["keys"][0]["address"]
    start("S", ["--connect", "127.0.0.1:1"])
    log("S up, mining 5 blocks; miner address", ADDR)
    mine(5)
    # ---------------------------------------------------------------- P1 growing lag while connected
    start("F1", ["--connect", f"127.0.0.1:{PORTS['S'][0]}"])
    c = converge("F1"); hs = height("F1")
    check(c is not None, f"P1 F1 initial sync to S tip #{hs}")
    log(f"P1: S mines {NP1} blocks with F1 connected (F1 handshake height ~{hs})")
    smp = mine(NP1, watch=("F1",))
    c = converge("F1", 120)
    check(c is not None, f"P1 F1 converged to S tip #{height('S')} after {NP1} blocks (no stall at +49/+50)",
          f"F1={height('F1')} S={height('S')} max lag while mining={max_lag(smp, 'F1')}")
    check(max_lag(smp, "F1") is not None and max_lag(smp, "F1") <= 10, "P1 F1 tracked the tip continuously while S mined", f"max lag {max_lag(smp, 'F1')}")
    check(len(peers("F1")) >= 1 and len(peers("S")) >= 1, "P1 F1<->S still connected", f"F1 peers={len(peers('F1'))}")
    # ---------------------------------------------------------------- P2 initial lag > 50 + P3 multiple peers
    start("F2", ["--connect", f"127.0.0.1:{PORTS['S'][0]}"])
    c = converge("F2", 180)
    check(c is not None, f"P2 F2 from genesis (lag {height('S')}) synced to S tip via GETB", f"in {c and round(c)} s")
    smp = mine(60, watch=("F1", "F2"))
    ok1, ok2 = converge("F1", 120), converge("F2", 120)
    check(ok2 is not None, "P2 F2 keeps following after its initial >50 lag (60 more blocks)",
          f"F2={height('F2')} S={height('S')} max lag={max_lag(smp, 'F2')}")
    check(ok1 is not None and ok2 is not None, "P3 two followers both at S tip", f"max lag F1={max_lag(smp, 'F1')} F2={max_lag(smp, 'F2')}")
    # ---------------------------------------------------------------- P4 follower restart
    stop("F1"); mine(60, watch=("F2",))
    start("F1", ["--connect", f"127.0.0.1:{PORTS['S'][0]}"])
    c = converge("F1", 180)
    check(c is not None, f"P4 restarted F1 (60 behind) caught up to #{height('S')}")
    smp = mine(60, watch=("F1", "F2"))
    check(converge("F1", 120) is not None and converge("F2", 120) is not None,
          "P4 after restart F1 keeps following (60 more blocks)", f"max lag F1={max_lag(smp, 'F1')} F2={max_lag(smp, 'F2')}")
    # ---------------------------------------------------------------- P5 server restart -> followers reconnect
    stop("S"); time.sleep(5); start("S", ["--connect", "127.0.0.1:1"])
    t0 = time.time()
    while time.time() - t0 < 120 and len(peers("S")) < 2: time.sleep(2)
    check(len(peers("S")) >= 2, "P5 both followers reconnected to the restarted S", f"S peers={len(peers('S'))} after {round(time.time() - t0)} s")
    smp = mine(60, watch=("F1", "F2"))
    check(converge("F1", 120) is not None and converge("F2", 120) is not None,
          f"P5 after server restart both followers follow to #{height('S')}", f"max lag F1={max_lag(smp, 'F1')} F2={max_lag(smp, 'F2')}")
    # ---------------------------------------------------------------- global
    for n in ("S", "F1", "F2"):
        pn = penalties(n)
        check(not pn, f"no misbehaviour/ban recorded on {n}", f"{pn[:3]}")
    st = logtext("S")
    bc = [(int(a), int(b)) for a, b in re.findall(r"Broadcasting block #(\d+) to (\d+) peers", st)]
    per_h = {}
    for h, k in bc: per_h[h] = per_h.get(h, 0) + k
    check(bc and max(per_h.values()) <= 2, "no flooding: S relays each block at most once per follower",
          f"{len(bc)} broadcasts, max sends for one height={max(per_h.values()) if per_h else 0}")
    fin = {n: (height(n), tipid(n)) for n in ("S", "F1", "F2")}
    check(len({v for v in fin.values()}) == 1, "final: S, F1, F2 identical tip", str({k: v[0] for k, v in fin.items()}))
    log("S getpeerinfo:", json.dumps(peers("S")))
finally:
    for n in list(procs): own_kill(procs[n])
print(f"[{LABEL}] RESULT {sum(RES)}/{len(RES)} checks passed", flush=True)
sys.exit(0 if all(RES) else 1)

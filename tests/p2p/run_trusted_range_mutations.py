#!/usr/bin/env python3
"""G1/G2 mutation test on REAL mainnet blocks inside the fast-sync trust (height <= 3554).

For each target height h a mainnet-profile sost-node is started on a copy of the real chain
truncated to h-1 (no network: --noseed, --connect to a closed port), and same-id copies of the
real block h with one field changed are submitted on the tip path (submitblock). Expected:

  G1  a block without transactions is rejected (it used to be accepted header-only);
  G2  a block whose declared profile_index is not bound by its commit is rejected (it used to be
      accepted and stored), and on MAINNET the CX commit data must be present;
  the genuine block is still accepted after every rejected copy.

Usage:
  python3 tests/p2p/run_trusted_range_mutations.py --bin <mainnet build> --chain <COPY of chain.json>
          --work <new empty dir> [--base 32600]
Ports base..base+20 must lie inside 21000-25999 or 32000-32999.
Every process this script starts is stopped by its recorded PID (argv[0] checked).
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


def rpc(port, method, params=None):
    body = json.dumps({"method": method, "params": params or [], "id": 1}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/", data=body, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    if d.get("error"):
        raise RuntimeError(f"{method}: {d['error']}")
    return d["result"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--chain", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--genesis", default=os.path.join(ROOT, "genesis_block.json"))
    ap.add_argument("--base", type=int, default=32600)
    ap.add_argument("--heights", default="100,1777,3300,3301,3400,3554")
    ap.add_argument("--only", default="", help="comma list of substrings: run only matching mutations")
    A = ap.parse_args()
    if not ((21000 <= A.base and A.base + 20 <= 25999) or (32000 <= A.base and A.base + 20 <= 32999)):
        sys.exit("--base must keep every port (base..base+20) inside 21000-25999 or 32000-32999")
    os.makedirs(A.work, exist_ok=True)
    if os.listdir(A.work):
        sys.exit(f"{A.work} is not empty")
    node = os.path.join(os.path.abspath(A.bin), "sost-node")
    chain = json.load(open(A.chain))
    blocks = chain["blocks"]
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok)))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)

    for k, h in enumerate(int(x) for x in A.heights.split(",")):
        d = os.path.join(A.work, f"h{h}")
        os.makedirs(d)
        with open(os.path.join(d, "chain.json"), "w") as f:
            f.write('{\n  "chain_height": %d,\n  "tip": "%s",\n  "blocks": [\n' % (h - 1, blocks[h - 1]["block_id"]))
            f.write(",\n".join("    " + json.dumps(b, separators=(",", ":")) for b in blocks[:h]))
            f.write("\n  ]\n}\n")
        rp = A.base + 1 + k
        argv = [node, "--profile", "mainnet", "--genesis", A.genesis, "--chain", os.path.join(d, "chain.json"),
                "--port", str(A.base + 10 + k), "--rpc-port", str(rp), "--rpc-noauth", "--noseed",
                "--connect", "127.0.0.1:1", "--p2p-bind", "127.0.0.1"]
        logf = open(os.path.join(d, "node.log"), "w")
        p = subprocess.Popen(argv, cwd=d, stdout=logf, stderr=subprocess.STDOUT, preexec_fn=lambda: os.nice(19))
        try:
            t0 = time.time()
            while True:
                try:
                    if int(rpc(rp, "getblockcount")) == h - 1:
                        break
                except Exception:
                    pass
                if time.time() - t0 > 300:
                    raise RuntimeError("node did not come up")
                time.sleep(0.5)
            g = dict(blocks[h])
            if "version" not in g:      # relay form states the v1 header version (p2p_send_block)
                g = dict(version=1, **g)
            print(f"\n=== mainnet block {h} (profile_index {'present=' + str(g['profile_index']) if 'profile_index' in g else 'absent'}) ===", flush=True)
            muts = [("transactions removed (G1)", lambda j: j.pop("transactions"), False),
                    ("x_bytes removed", lambda j: j.pop("x_bytes"), False),
                    ("final_state removed", lambda j: j.pop("final_state"), False),
                    ("segments_root removed", lambda j: j.pop("segments_root"), False)]
            if "profile_index" in g:
                pi = int(g["profile_index"])
                muts += [("profile_index -1 (G2)", lambda j: j.update(profile_index=pi - 1), False),
                         ("profile_index +1 (G2)", lambda j: j.update(profile_index=pi + 1), False),
                         ("profile_index removed", lambda j: j.pop("profile_index"), pi == 0),
                         ("stability_metric +1", lambda j: j.update(stability_metric=int(j["stability_metric"]) + 1), False)]
            else:
                muts += [("profile_index added = -1", lambda j: j.update(profile_index=-1), False),
                         ("profile_index added = 5", lambda j: j.update(profile_index=5), False)]
            if A.only:
                muts = [m for m in muts if any(x in m[0] for x in A.only.split(","))]
            for name, fn, expect in muts:
                j = json.loads(json.dumps(g))
                fn(j)
                try:
                    rpc(rp, "submitblock", [json.dumps(j, separators=(",", ":"))]); acc = True
                except Exception:
                    acc = False
                if acc:   # undo is not possible on the tip path; restart from scratch for safety
                    check(f"h={h} {name}: {'accepted' if acc else 'rejected'} (expected {'accept' if expect else 'reject'})", acc == expect)
                    break
                check(f"h={h} {name}: rejected (expected {'accept' if expect else 'reject'})", acc == expect)
            if int(rpc(rp, "getblockcount")) == h - 1:
                try:
                    rpc(rp, "submitblock", [json.dumps(g, separators=(",", ":"))]); ok = True
                except Exception as e:
                    ok = False
                ok = ok and rpc(rp, "getbestblockhash") == g["block_id"]
                check(f"h={h} genuine block accepted after the rejected copies", ok)
        finally:
            if p.poll() is None:
                argv0 = open(f"/proc/{p.pid}/cmdline", "rb").read().split(b"\0")[0].decode()
                if argv0 == node:
                    os.kill(p.pid, signal.SIGTERM)
                    try:
                        p.wait(60)
                    except subprocess.TimeoutExpired:
                        os.kill(p.pid, signal.SIGKILL)
                        p.wait()
    n_ok = sum(1 for _, ok in results if ok)
    print(f"\nchecks: {n_ok}/{len(results)} PASS", flush=True)
    sys.exit(0 if n_ok == len(results) else 1)


if __name__ == "__main__":
    main()

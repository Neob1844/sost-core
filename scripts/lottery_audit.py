#!/usr/bin/env python3
"""
lottery_audit.py — Walks every Phase 2 block and re-derives the lottery winner
via the node's getlotteryaudit RPC, then compares against the current UTXO set.

Usage:
    python3 scripts/lottery_audit.py
    python3 scripts/lottery_audit.py --rpc 127.0.0.1:18232 --user X --pass Y

The defaults match the SOST VPS node config; override only if pointing at a
different node.
"""
import argparse
import base64
import json
import sys
import urllib.request
from collections import Counter, defaultdict


def rpc(url, user, password, method, params=None):
    body = json.dumps({"method": method, "params": params or []}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    token = base64.b64encode((user + ":" + password).encode()).decode()
    req.add_header("Authorization", "Basic " + token)
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read().decode())
    if out.get("error"):
        raise RuntimeError(out["error"])
    return out["result"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", default="127.0.0.1:18232")
    ap.add_argument("--user", default="7568b6a8a62e4c683fe6a8dda0db632156b84a17")
    ap.add_argument("--password", default="4da539e6b1e8fe8e43a247457087c5f42a8cc5bb")
    ap.add_argument("--from-height", type=int, default=7100)
    ap.add_argument("--addr", action="append", default=[
        "sost1ca9097d830b74495b95db9d779ad63c90579bc18",
        "sost1a8eae8f80fedd8d86187db628a0d81e0367f76de",
    ])
    args = ap.parse_args()

    url = "http://" + args.rpc + "/"
    call = lambda m, p=None: rpc(url, args.user, args.password, m, p)

    tip = int(call("getinfo")["blocks"])
    wins = Counter()
    by_addr = defaultdict(list)

    sys.stdout.write(f"scanning #{args.from_height} -> #{tip} ...\n")
    sys.stdout.flush()

    progress_every = 50
    for h in range(args.from_height, tip + 1):
        try:
            a = call("getlotteryaudit", [str(h)])
        except Exception:
            continue
        if not a or not a.get("is_lottery_block"):
            continue
        addr = a.get("winner_address")
        if not addr:
            continue
        wins[addr] += 1
        by_addr[addr].append(h)
        if (h - args.from_height) % progress_every == 0:
            sys.stdout.write(f"  ...#{h}\n")
            sys.stdout.flush()

    print()
    print(f"CHAIN TIP: {tip}   AUDIT RANGE: #{args.from_height} -> #{tip}")
    print()
    print("TOP LOTTERY WINNERS (consensus truth)")
    for addr, n in wins.most_common(25):
        sample = by_addr[addr][:8]
        suffix = "..." if len(by_addr[addr]) > 8 else ""
        print(f"  {n:3d} wins  {addr}  {sample}{suffix}")
    print()
    for addr in args.addr:
        print(addr)
        print(f"  consensus wins: {wins[addr]}")
        print(f"  heights: {by_addr[addr]}")
        try:
            info = call("getaddressinfo", [addr])
        except Exception as e:
            print(f"  getaddressinfo failed: {e}")
            continue
        lott_unspent = [u for u in info.get("utxos", []) if int(u.get("type", -1)) == 4]
        amt = sum(float(u["amount"]) for u in lott_unspent)
        print(f"  current unspent lottery UTXOs: {len(lott_unspent)}  amount={amt:.8f}")
        print(f"  total balance: {info.get('balance')}")
        print()


if __name__ == "__main__":
    main()

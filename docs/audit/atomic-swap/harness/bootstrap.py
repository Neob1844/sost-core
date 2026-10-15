#!/usr/bin/env python3
"""Bootstrap a fresh devnet: node A, wallets, mine to Alice until she has mature coins."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from swaplab import *
work = os.path.abspath(sys.argv[1]); target = int(sys.argv[2]) if len(sys.argv) > 2 else 30
os.makedirs(work, exist_ok=True)
A = Sost(work, "nodeA", 19801, 19811).start()
try:
    wa, alice = new_wallet(work, "alice.json"); wb, bob = new_wallet(work, "bob.json"); wv, vault = new_wallet(work, "vault.json")
    wm, minr = new_wallet(work, "miner.json")
    print("profile", A.call("getinfo").get("profile"), "height", A.height())
    ok = A.mine_to(target, wa, alice)
    print("mined", ok, "height", A.height(), "alice", A.balance(alice))
    u = A.utxos(alice); print(json.dumps(u[:2], indent=1, default=str)); print(len(u), "utxos")
finally:
    stop_all()

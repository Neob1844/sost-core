#!/usr/bin/env python3
"""SOST governance indexer (Stage 1 research model): recount an on-chain vote from the SOST chain.

  governance-indexer.py --sost-rpc http://127.0.0.1:18555/ --proposal proposal.json --census census.json \
      [--finality-depth 30]

proposal.json: the frozen proposal fields; census.json: the list of identities eligible at the snapshot.
Prints the full tally (state, YES/NO/ABSTAIN/NO VOTE, required YES = ceil(2/3 x census), history, ignored).
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sostbridge.sostchain import SostRPC
from sostbridge.governance import Proposal, tally


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sost-rpc", required=True); ap.add_argument("--proposal", required=True)
    ap.add_argument("--census", required=True); ap.add_argument("--finality-depth", type=int, default=30)
    a = ap.parse_args()
    p = json.load(open(a.proposal))
    p["successor_code_hash"] = bytes.fromhex(p["successor_code_hash"].removeprefix("0x"))
    prop = Proposal(**p)
    t = tally(SostRPC(a.sost_rpc), prop, json.load(open(a.census)), a.finality_depth)
    print(t.to_json())


if __name__ == "__main__":
    main()

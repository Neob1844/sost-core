#!/usr/bin/env python3
"""wSOST bridge indexer (Stage 1, devnet only): reconcile the SOST Bridge Vault against WSOST.

  bridge-indexer.py --sost-rpc http://127.0.0.1:18555/ --vault sost1... --start 100 \
      --eth-rpc http://127.0.0.1:8545 --wsost 0x... --abi-dir contracts/wsost/out \
      [--min-conf 30] [--fee-allowance 0.001] [--out bridge_status.json] [--pause-from 0x...]

Exit code 0 BALANCED, 1 PENDING, 2 CRITICAL. With --pause-from (an observer or admin account),
a CRITICAL result stops NEW mints on the contract; transfers and burns keep working.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sostbridge.common import to_stocks
from sostbridge.sostchain import SostRPC
from sostbridge.ethside import Web3WSOST
from sostbridge.ledger import scan_vault, reconcile, enforce_safety, BALANCED, PENDING


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sost-rpc", required=True); ap.add_argument("--vault", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--eth-rpc", required=True); ap.add_argument("--wsost", required=True)
    ap.add_argument("--abi-dir", required=True)
    ap.add_argument("--min-conf", type=int, default=30)
    ap.add_argument("--fee-allowance", default="0.001")
    ap.add_argument("--out"); ap.add_argument("--pause-from")
    a = ap.parse_args()
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(a.eth_rpc))
    eth = Web3WSOST(w3, Web3.to_checksum_address(a.wsost), Web3WSOST.load_abi(a.abi_dir))
    rec = reconcile(scan_vault(SostRPC(a.sost_rpc), a.vault, a.start), eth, a.min_conf, to_stocks(a.fee_allowance))
    if a.pause_from:
        enforce_safety(rec, eth, a.pause_from)
    js = rec.to_json()
    if a.out:
        tmp = a.out + ".tmp"; open(tmp, "w").write(js); os.replace(tmp, a.out)
    print(js)
    sys.exit(0 if rec.status == BALANCED else 1 if rec.status == PENDING else 2)


if __name__ == "__main__":
    main()

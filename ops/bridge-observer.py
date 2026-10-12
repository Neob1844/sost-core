#!/usr/bin/env python3
"""wSOST bridge observer (Stage 1, devnet only). Verifies deposits on its own SOST node and prints
EIP-712 attestations as JSON lines. The key file holds a DISPOSABLE devnet key; never a production key.

  bridge-observer.py --name obs1 --key-file obs1.key --sost-rpc http://127.0.0.1:18555/ --vault sost1... \
      --start 100 --eth-rpc http://127.0.0.1:8545 --wsost 0x... --abi-dir contracts/wsost/out [--min-conf 30]
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sostbridge.sostchain import SostRPC
from sostbridge.ethside import Web3WSOST
from sostbridge.observer import Observer, ObserverConfig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True); ap.add_argument("--key-file", required=True)
    ap.add_argument("--sost-rpc", required=True); ap.add_argument("--vault", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--eth-rpc", required=True); ap.add_argument("--wsost", required=True)
    ap.add_argument("--abi-dir", required=True); ap.add_argument("--min-conf", type=int, default=30)
    a = ap.parse_args()
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(a.eth_rpc))
    eth = Web3WSOST(w3, Web3.to_checksum_address(a.wsost), Web3WSOST.load_abi(a.abi_dir))
    key = bytes.fromhex(open(a.key_file).read().strip().removeprefix("0x"))
    cfg = ObserverConfig(vault=a.vault, start_height=a.start, min_confirmations=a.min_conf,
                         chain_id=w3.eth.chain_id, wsost=Web3.to_checksum_address(a.wsost))
    ob = Observer(a.name, key, SostRPC(a.sost_rpc), cfg, eth)
    for d in ob.candidates():
        at = ob.attest(d)
        if at:
            m = at.msg
            print(json.dumps({"observer": a.name, "signer": at.signer, "signature": "0x" + at.signature.hex(),
                              "deposit": {"depositId": "0x" + m.depositId.hex(), "recipient": m.recipient, "amount": m.amount,
                                          "bridgeVault": "0x" + m.bridgeVault.hex(), "sostBlockHash": "0x" + m.sostBlockHash.hex(),
                                          "sostBlockHeight": m.sostBlockHeight, "confirmations": m.confirmations,
                                          "bridgeVersion": m.bridgeVersion}}))
    for line in ob.log:
        print("# " + line, file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Foreground logic test for dex_lab_relay: proves state is derived from REAL on-chain
verification (a bogus txid must NOT verify), not from files/browser. Point the DEX_LAB_* env at a
live regtest and pass a real funding + claim txid:
    DEX_LAB_BTC_CLI="bitcoin-cli -regtest -datadir=... -rpcuser=rt -rpcpassword=rt -rpcport=18443" \
    python3 relay_verify_test.py <funding_txid> <claim_txid>
"""
import sys, importlib.util, os
spec=importlib.util.spec_from_file_location("relay", os.path.join(os.path.dirname(__file__),"dex_lab_relay.py"))
r=importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
fund, claim = sys.argv[1], sys.argv[2]
P=[0]; F=[0]
def chk(c,m):
    if c: P[0]+=1
    else: F[0]+=1; print("  [FAIL]", m)
chk(r.btc_call(["getblockcount"]) is not None, "btc node reachable")
chk((r.btc_tx(fund) or {}).get("confirmations",0) >= 1, "real funding txid verifies on-chain")
chk((r.btc_tx(claim) or {}).get("confirmations",0) >= 1, "real claim txid verifies on-chain")
chk(r.btc_tx("00"*32) is None, "bogus txid does NOT verify (real on-chain check, not file-trust)")
st=r.derive_state({"pair":"SOST/BTC","txids":{"cp_lock":fund,"cp_claim":claim}})
chk(st["state"]=="PreimageRevealed", "derive_state = PreimageRevealed from verified cp_lock+cp_claim")
chk(st["verified"].get("cp_lock") and st["verified"].get("cp_claim"), "both legs marked verified")
print("RELAY-VERIFY TESTS: PASS=%d FAIL=%d" % (P[0],F[0]))
sys.exit(1 if F[0] else 0)

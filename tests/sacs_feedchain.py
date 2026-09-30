#!/usr/bin/env python3
# Deliver source node's blocks [START..H] to dest node via getblockhash+getrawblock+submitblock,
# parent-first. START defaults to 1. Delivering only a TAIL (START>1) models a real peer that
# announces new blocks without re-sending ancestors the dest once saw (and may have pruned).
# Prints per-height accept/reject and a summary + the first hash that fails to connect.
import sys, json, urllib.request
def rpc(port, method, params):
    req=urllib.request.Request(f"http://127.0.0.1:{port}/",
        data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode(),
        headers={"Content-Type":"application/json","Authorization":"Basic dTpw"})  # u:p
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=15).read().decode())
        return r.get("result"), r.get("error")
    except Exception as e:
        return None, str(e)
def main():
    src, dst, H = sys.argv[1], sys.argv[2], int(sys.argv[3])
    START = int(sys.argv[4]) if len(sys.argv)>4 else 1
    acc=rej=0; first_reject=None
    for hgt in range(START, H+1):
        bh,err = rpc(src,"getblockhash",[hgt])
        if not bh: print(f"  h{hgt}: getblockhash FAIL {err}"); continue
        raw,err = rpc(src,"getrawblock",[bh])
        if not raw: print(f"  h{hgt}: getrawblock FAIL {err}"); continue
        res,err = rpc(dst,"submitblock",[raw])
        ok = (res in (True,"true")) or (res is True)
        if ok: acc+=1
        else:
            rej+=1
            if first_reject is None: first_reject=(hgt,bh)
        if hgt in (START,H) or not ok:
            print(f"  h{hgt} {bh[:16]} -> submitblock: {'ACCEPT' if ok else 'reject/fork-stored/orphan'} {('' if ok else (err or res))}")
    print(f"  fed [{START}..{H}]: {acc} direct-accept, {rej} fork-stored/orphan/other")
    if first_reject: print(f"  FIRST_NONACCEPT h{first_reject[0]} hash={first_reject[1]}")
if __name__=="__main__": main()

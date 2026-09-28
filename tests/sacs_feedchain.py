#!/usr/bin/env python3
# Deliver source node's blocks [1..H] to dest node via getrawblock+submitblock,
# parent-first, so dest can assemble the competing fork and let the REAL reorg
# engine decide by cumulative work. Prints per-height accept/reject.
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
    acc=rej=0
    for h in range(1, H+1):
        bh,err = rpc(src,"getblockhash",[h])
        if not bh: print(f"  h{h}: getblockhash FAIL {err}"); continue
        raw,err = rpc(src,"getrawblock",[bh])
        if not raw: print(f"  h{h}: getrawblock FAIL {err}"); continue
        res,err = rpc(dst,"submitblock",[raw])
        ok = (res in (True,"true")) or (res is True)
        if ok: acc+=1
        else: rej+=1
        # brief per-height line only for first, last, and rejects to keep output tight
        if h in (1,H) or not ok:
            print(f"  h{h} {bh[:16]} -> submitblock: {'ACCEPT' if ok else 'reject/fork-stored'} {('' if ok else (err or res))}")
    print(f"  fed {H} blocks: {acc} direct-accept, {rej} fork-stored/other")
if __name__=="__main__": main()

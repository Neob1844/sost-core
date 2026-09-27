#!/usr/bin/env python3
"""SOST exchange deposit poller — reference implementation.

Demonstrates the crediting rules from docs/exchange/EXCHANGE_INTEGRATION.md:
  - only credit TRANSFER (0x00) outputs (and matured coinbase if you opt in)
  - honor COINBASE_MATURITY = 1000 for coinbase
  - require N confirmations before crediting
  - detect and roll back reorgs by comparing stored block hashes to getblockhash

This is a REFERENCE (single-file, stdlib only). It does not credit real funds; the
`credit`/`rollback` callbacks are where an exchange wires its ledger. Run against a
local/test node. No keys, read-only except the optional sendrawtransaction demo.
"""
import json, urllib.request, base64, argparse, time

COINBASE_MATURITY = 1000
OUT_TRANSFER = 0x00
COINBASE_TYPES = {0x01, 0x02, 0x03, 0x04}


class Rpc:
    def __init__(self, url, user, password):
        self.url = url
        self.auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    def call(self, method, params=None):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
        req = urllib.request.Request(self.url, data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Basic " + self.auth})
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
        if out.get("error"):
            raise RuntimeError(f"{method}: {out['error']}")
        return out.get("result")


class DepositTracker:
    """In-memory ledger of pending/credited deposits keyed by (txid, vout)."""
    def __init__(self, rpc, watch_addresses, min_conf=30, credit=None, rollback=None):
        self.rpc = rpc
        self.watch = set(watch_addresses)
        self.min_conf = min_conf
        self.credit_cb = credit or (lambda d: print("CREDIT", d))
        self.rollback_cb = rollback or (lambda d: print("ROLLBACK", d))
        self.pending = {}   # (txid,vout) -> deposit dict (seen, not yet final)
        self.credited = {}  # (txid,vout) -> deposit dict (final)
        self.block_hash_at = {}  # height -> hash we last saw (reorg detection)

    def _required_conf(self, out_type):
        return COINBASE_MATURITY if out_type in COINBASE_TYPES else self.min_conf

    def _scan_block(self, height, tip):
        h = self.rpc.call("getblockhash", [height])
        prev = self.block_hash_at.get(height)
        if prev is not None and prev != h:
            # reorg: roll back anything that confirmed in the old block at this height
            for key, d in list(self.credited.items()) + list(self.pending.items()):
                if d.get("height") == height and d.get("block") == prev:
                    self.rollback_cb(d)
                    self.credited.pop(key, None); self.pending.pop(key, None)
        self.block_hash_at[height] = h
        block = self.rpc.call("getblock", [h])
        for tx in block.get("tx", []) if isinstance(block.get("tx"), list) else []:
            txid = tx.get("txid") or tx.get("hash")
            for vout, o in enumerate(tx.get("vout", [])):
                addr = o.get("address")
                if addr not in self.watch:
                    continue
                otype = int(o.get("type", OUT_TRANSFER))
                # only ordinary transfers (and optionally matured coinbase) are deposits
                if otype not in (OUT_TRANSFER,) and otype not in COINBASE_TYPES:
                    continue
                key = (txid, vout)
                if key in self.credited:
                    continue
                self.pending[key] = {"txid": txid, "vout": vout, "address": addr,
                                     "amount": o.get("amount"), "type": otype,
                                     "height": height, "block": h}

    def poll_once(self):
        tip = self.rpc.call("getblockcount")
        best = self.rpc.call("getbestblockhash")
        # rescan the unconfirmed-enough window (plus a reorg-depth cushion)
        window = self.min_conf + 6
        start = max(0, tip - window)
        for hgt in range(start, tip + 1):
            self._scan_block(hgt, tip)
        # promote pending -> credited when buried deep enough AND still on main chain
        for key, d in list(self.pending.items()):
            conf = tip - d["height"] + 1
            if conf < self._required_conf(d["type"]):
                continue
            # confirm the block is still canonical (gettxout also proves unspent)
            if self.rpc.call("getblockhash", [d["height"]]) != d["block"]:
                continue
            utxo = self.rpc.call("gettxout", [d["txid"], d["vout"]])
            if utxo is None:  # spent or gone
                self.pending.pop(key, None); continue
            self.credited[key] = d
            self.pending.pop(key, None)
            self.credit_cb(d)
        return {"tip": tip, "best": best, "pending": len(self.pending), "credited": len(self.credited)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:18332/")
    ap.add_argument("--user", default="sostrpc")
    ap.add_argument("--pass-file", required=True)
    ap.add_argument("--address", action="append", required=True, help="deposit address to watch (repeatable)")
    ap.add_argument("--min-conf", type=int, default=30)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    pw = open(a.pass_file).read().strip()
    rpc = Rpc(a.url, a.user, pw)
    tracker = DepositTracker(rpc, a.address, min_conf=a.min_conf)
    while True:
        print(tracker.poll_once())
        if a.once:
            break
        time.sleep(10)


if __name__ == "__main__":
    main()

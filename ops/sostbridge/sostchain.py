"""Read-only view of the SOST chain for the bridge and governance indexers.

`SostRPC` talks to a real sost-node (devnet in Stage 1). `FakeSostChain` reproduces the same
RPC surface in memory, including reorganisations, for deterministic tests. Amount fields are
decoded with Decimal (never float) and converted to integer stocks by the callers.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from decimal import Decimal
from typing import Dict, List, Optional


class RPCError(Exception):
    pass


class SostRPC:
    def __init__(self, url: str, user: Optional[str] = None, password: Optional[str] = None, timeout: float = 20.0):
        self.url, self.timeout = url, timeout
        self._auth = None
        if user is not None:
            import base64
            self._auth = "Basic " + base64.b64encode(f"{user}:{password or ''}".encode()).decode()

    def call(self, method: str, params: Optional[list] = None):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"content-type": "application/json"})
        if self._auth:
            req.add_header("Authorization", self._auth)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            j = json.loads(r.read().decode(), parse_float=Decimal)
        if j.get("error"):
            raise RPCError(str(j["error"]))
        return j.get("result")

    def getblockcount(self) -> int:
        return int(self.call("getblockcount"))

    def getblockhash(self, h: int) -> str:
        return self.call("getblockhash", [h])

    def getblock(self, block_hash: str) -> dict:
        return self.call("getblock", [block_hash])

    def gettransaction(self, txid: str) -> dict:
        return self.call("gettransaction", [txid])


class FakeSostChain:
    """In-memory canonical chain with reorgs. Transactions are dicts shaped like gettransaction:
    {"txid", "vin": [{"address", "amount"}], "vout": [{"address", "amount", "payload_hex"?}]}."""

    def __init__(self):
        self.blocks: List[dict] = []          # canonical: {"hash", "height", "txs": [tx...]}
        self._salt = 0
        self.add_block([])                    # genesis

    def _hash(self, height: int) -> str:
        self._salt += 1
        return hashlib.sha256(f"blk:{height}:{self._salt}".encode()).hexdigest()

    @staticmethod
    def txid_for(tag: str) -> str:
        return hashlib.sha256(("tx:" + tag).encode()).hexdigest()

    def add_block(self, txs: List[dict]) -> str:
        h = len(self.blocks)
        bh = self._hash(h)
        self.blocks.append({"hash": bh, "height": h, "txs": [dict(t) for t in txs]})
        return bh

    def mine(self, n: int):
        for _ in range(n):
            self.add_block([])

    def reorg(self, fork_height: int, new_blocks: List[List[dict]]):
        """Replace every block from `fork_height` with `new_blocks` (lists of txs)."""
        if fork_height < 1 or fork_height > len(self.blocks):
            raise ValueError("bad fork height")
        del self.blocks[fork_height:]
        for txs in new_blocks:
            self.add_block(txs)

    # ---- RPC surface
    def getblockcount(self) -> int:
        return len(self.blocks) - 1

    def getblockhash(self, h: int) -> str:
        if not (0 <= h < len(self.blocks)):
            raise RPCError("height out of range")
        return self.blocks[h]["hash"]

    def getblock(self, block_hash: str) -> dict:
        for b in self.blocks:
            if b["hash"] == block_hash:
                return {"hash": b["hash"], "height": b["height"], "txids": [t["txid"] for t in b["txs"]]}
        raise RPCError("block not found")

    def gettransaction(self, txid: str) -> dict:
        tip = self.getblockcount()
        for b in self.blocks:
            for t in b["txs"]:
                if t["txid"] == txid:
                    r = json.loads(json.dumps(t), parse_float=Decimal)
                    r["block_height"] = b["height"]
                    r["confirmations"] = tip - b["height"] + 1
                    return r
        raise RPCError("transaction not found")


def iter_canonical_txs(rpc, from_height: int, to_height: int):
    """Yield (height, block_hash, tx) for every transaction in canonical blocks [from, to]."""
    for h in range(max(0, from_height), to_height + 1):
        bh = rpc.getblockhash(h)
        blk = rpc.getblock(bh)
        for txid in blk.get("txids", []):
            try:
                tx = rpc.gettransaction(txid)
            except RPCError:
                continue
            yield h, bh, tx

"""SOST side: JSON-RPC client, fixture-backed mock chain with reorgs, capsule binding.

Response shapes follow src/sost-node.cpp exactly:
  gettransaction (confirmed): {"txid","block_height","tx_position","confirmations","in_mempool":false,
                               "vin":[{"prev_txid","index","address","amount"}],
                               "vout":[{"address","amount","type","payload_hex"?}], "fee", ...}
  gettransaction (mempool):   {... "block_height":-1,"confirmations":0,"in_mempool":true ...}
  gettxout:                   {"bestblock","confirmations","value","address","type","coinbase"} | null
  getblockhash h -> "hex";  getblockcount -> int
  getaddressutxos addr -> [{"txid","vout","amount","amount_stocks","height","confirmations","output_type",
                            "coinbase","mature","spendable","payload"?}]   (full UTXO-set scan on the node)
  getaddressbalance addr -> {"address","balance","balance_stocks","utxo_count"}
Amounts are printed by format_sost() as UNQUOTED JSON numbers with 8 decimals (e.g. 1000.00000000):
they MUST be parsed with Decimal (json parse_float=Decimal), never float.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.request
from decimal import Decimal
from typing import Optional

STOCKS_PER_SOST = 10**8
SOST_ADDR_RE = re.compile(r"^sost1[0-9a-f]{40}$")
TXID_RE = re.compile(r"^[0-9a-f]{64}$")


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(f"rpc error {code}: {message}")
        self.code = code


def to_stocks(v) -> int:
    if isinstance(v, (float, bool)):
        raise TypeError("float amount refused")
    d = Decimal(str(v)) * STOCKS_PER_SOST
    if d != d.to_integral_value():
        raise ValueError("more than 8 decimals")
    return int(d)


def is_sost_address(a: str) -> bool:
    return bool(SOST_ADDR_RE.match(a or ""))


def is_txid(t: str) -> bool:
    return bool(TXID_RE.match(t or ""))


# ------------------------------------------------------------------ capsule binding
# SCPv1 OPEN_NOTE_INLINE (type 0x01, active on mainnet since block 7,350), carried on the deposit
# output ITSELF. Text: "C701:0x<64 hex requestId>" (71 bytes <= 80). The depositor's SOST signature
# over the transaction authenticates the commitment to the request (and therefore to the Ethereum
# recipient, chain, contract and amount hashed into the requestId).
CAPSULE_PREFIX = "C701:0x"
RELEASE_PREFIX = "C701R:0x"


def build_open_note(text: str) -> str:
    t = text.encode()
    if len(t) > 80:
        raise ValueError("open note > 80 bytes")
    body = bytes([len(t)]) + t
    hdr = bytes([0x53, 0x43, 0x01, 0x01, 0, 0, 0, 0, 0, len(body), 0, 0])
    return (hdr + body).hex()


def parse_open_note(payload_hex: Optional[str]) -> Optional[str]:
    if not payload_hex:
        return None
    try:
        b = bytes.fromhex(payload_hex)
    except ValueError:
        return None
    if len(b) < 13 or b[0:3] != b"SC\x01" or b[3] != 0x01 or b[4] != 0:
        return None
    body = b[12:]
    if len(body) != b[9] or body[0] + 1 != len(body):
        return None
    try:
        return body[1:].decode("ascii")
    except UnicodeDecodeError:
        return None


def capsule_for_request(request_id: bytes) -> str:
    return build_open_note(CAPSULE_PREFIX + request_id.hex())


def request_id_from_capsule(payload_hex: Optional[str]) -> Optional[bytes]:
    t = parse_open_note(payload_hex)
    if not t or not t.startswith(CAPSULE_PREFIX):
        return None
    h = t[len(CAPSULE_PREFIX):]
    if not re.fullmatch(r"[0-9a-f]{64}", h):
        return None
    return bytes.fromhex(h)


def release_capsule(release_id: bytes) -> str:
    return build_open_note(RELEASE_PREFIX + release_id.hex())


# ------------------------------------------------------------------ RPC client (real node)
class SostRpc:
    """Read-only JSON-RPC client. Credentials are read by the caller from a mode-600 file; never logged."""

    READ_ONLY = {"getblockcount", "getblockhash", "gettransaction", "gettxout", "getaddressutxos", "getaddressbalance"}

    def __init__(self, url: str, user: str = "", password: str = "", timeout: float = 10.0):
        self.url, self.timeout = url, timeout
        self._auth = base64.b64encode(f"{user}:{password}".encode()).decode() if user else None

    def call(self, method: str, *params):
        if method not in self.READ_ONLY:
            raise PermissionError(f"engine RPC is read-only; {method} refused")
        req = urllib.request.Request(self.url, data=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": [str(p) for p in params]}).encode(),
            headers={"Content-Type": "application/json"})
        if self._auth:
            req.add_header("Authorization", "Basic " + self._auth)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            body = json.loads(r.read().decode(), parse_float=Decimal)
        if body.get("error"):
            raise RpcError(body["error"].get("code"), body["error"].get("message"))
        return body.get("result")


# ------------------------------------------------------------------ mock chain (tests)
class MockSostChain:
    """In-memory chain answering the same methods with the same JSON shapes (serialised then
    re-parsed with Decimal, exactly like the wire). Supports reorgs."""

    READ_ONLY = SostRpc.READ_ONLY

    def __init__(self):
        self.blocks = []            # list of block hashes (index = height)
        self.txs = {}               # txid -> {"height": h|None, "vin": [...], "vout": [...]}
        self.spent = set()          # (txid, vout)
        self._salt = 0
        self.mine(1)

    def _hash(self):
        self._salt += 1
        import hashlib
        return hashlib.sha256(f"blk{self._salt}".encode()).hexdigest()

    @property
    def height(self):
        return len(self.blocks) - 1

    def mine(self, n=1, include=()):
        for i in range(n):
            self.blocks.append(self._hash())
            if i == 0:
                for t in include:
                    self.txs[t]["height"] = self.height

    def add_tx(self, txid, vout, vin=None):
        self.txs[txid] = {"height": None, "vin": vin or [], "vout": vout}

    def reorg(self, depth, drop=()):
        """Replace the last `depth` blocks; txs in `drop` fall out of the chain (back to mempool or gone)."""
        cut = self.height - depth + 1
        for t, d in self.txs.items():
            if d["height"] is not None and d["height"] >= cut:
                d["height"] = None
        del self.blocks[cut:]
        for t in drop:
            self.txs.pop(t, None)
        self.mine(depth + 1)

    @staticmethod
    def _fmt(stocks):
        return f"{stocks // STOCKS_PER_SOST}.{stocks % STOCKS_PER_SOST:08d}"

    def call(self, method, *params):
        if method not in self.READ_ONLY:
            raise PermissionError(method)
        if method == "getblockcount":
            return self.height
        if method == "getblockhash":
            h = int(params[0])
            if h < 0 or h > self.height:
                raise RpcError(-8, "Block height out of range")
            return self.blocks[h]
        if method == "gettransaction":
            d = self.txs.get(params[0])
            if d is None:
                raise RpcError(-5, "Transaction not found")
            confirmed = d["height"] is not None
            vout = []
            for o in d["vout"]:
                e = '{"address":"%s","amount":%s,"type":%d' % (o["address"], self._fmt(o["stocks"]), o.get("type", 0))
                if o.get("payload_hex"):
                    e += ',"payload_hex":"%s"' % o["payload_hex"]
                vout.append(e + "}")
            raw = '{"txid":"%s","block_height":%d,%s"confirmations":%d,"in_mempool":%s,"vin":%s,"vout":[%s],"fee":1000}' % (
                params[0], d["height"] if confirmed else -1,
                ('"tx_position":1,' if confirmed else ""),
                (self.height - d["height"] + 1) if confirmed else 0,
                "false" if confirmed else "true",
                "[" + ",".join('{"prev_txid":"%s","index":%d,"address":"%s","amount":%s}' % (
                    i["prev_txid"], i["index"], i["address"], self._fmt(i["stocks"])) for i in d["vin"]) + "]",
                ",".join(vout))
            return json.loads(raw, parse_float=Decimal)
        if method == "gettxout":
            txid, n = params[0], int(params[1])
            d = self.txs.get(txid)
            if d is None or d["height"] is None or (txid, n) in self.spent or n >= len(d["vout"]):
                return None
            o = d["vout"][n]
            raw = '{"bestblock":"%s","confirmations":%d,"value":%s,"address":"%s","type":%d,"coinbase":false}' % (
                self.blocks[-1], self.height - d["height"] + 1, self._fmt(o["stocks"]), o["address"], o.get("type", 0))
            return json.loads(raw, parse_float=Decimal)
        if method in ("getaddressutxos", "getaddressbalance"):
            addr = params[0]
            if not is_sost_address(addr):
                raise RpcError(-8, "invalid address")
            items = []
            total = 0
            for txid, d in self.txs.items():
                if d["height"] is None:
                    continue
                for n, o in enumerate(d["vout"]):
                    if o["address"] != addr or (txid, n) in self.spent:
                        continue
                    total += o["stocks"]
                    e = ('{"txid":"%s","vout":%d,"amount":%s,"amount_stocks":%d,"height":%d,"confirmations":%d,'
                         '"output_type":%d,"coinbase":false,"mature":true,"spendable":true') % (
                        txid, n, self._fmt(o["stocks"]), o["stocks"], d["height"], self.height - d["height"] + 1, o.get("type", 0))
                    if o.get("payload_hex"):
                        e += ',"payload":"%s"' % o["payload_hex"]
                    items.append(e + "}")
            if method == "getaddressutxos":
                return json.loads("[" + ",".join(items) + "]", parse_float=Decimal)
            return json.loads('{"address":"%s","balance":%s,"balance_stocks":%d,"utxo_count":%d}' % (
                addr, self._fmt(total), total, len(items)), parse_float=Decimal)
        raise RpcError(-32601, "method not found")

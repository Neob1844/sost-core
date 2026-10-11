#!/usr/bin/env python3
"""Node participation indexer — NODE_BIND + NODE_HEARTBEAT, from the chain, for the Explorer.

    SOST node <- read-only gateway <- ONE indexer -> /api/node_participation.json -> N browsers

What it reads, ONLY from canonical blocks from the V16 activation (#30,000) on:
  NODE_BIND       tx_type 0x20, one OUT_NODE_PROTOCOL (0x30) output whose payload is
                  mining_pubkey(33) node_pubkey(33) bind_seq(8 LE) mining_sig(64) [node_sig(64), v2]
                  -> the mining address is sost1 + hex(RIPEMD160(SHA256(mining_pubkey)))
  NODE_HEARTBEAT  tx_type 0x21, payload node_pubkey(33) epoch_idx(8 LE) tip_ref_hash(32) node_sig(64)
Everything mined was already validated by consensus (signatures, epoch == epoch of the inclusion
height, tip_ref == canonical hash, one heartbeat per miner and epoch), so the indexer only replays
it in height order: the latest bind (highest seq) of a miner is its active binding, and a heartbeat
counts for the miner whose active binding holds that node key at inclusion.

What it derives per bound identity (never a claim about hardware: a node key is an identity, not a
proof of one physical machine): bind age, heartbeat coverage since the bind, current streak, last
verified epoch, a participation status, and whether the NODE condition of the next Jackpot V2 draw
(heartbeats in the last 3-of-4 completed epochs, ramped) is met. Each cycle the node's own
getjackpotv2audit for the next draw is read back and compared, so a mismatch is visible, not hidden.

Reorg-safe and incremental exactly like address-earnings-indexer.py (one row per block, tip hash
checked every cycle, atomic state/output writes).
"""
import argparse
import hashlib
import json
import os
import tempfile
import time
import urllib.request

READ_ONLY = frozenset({"getblockcount", "getblockhash", "getblock", "getrawtransaction", "getjackpotv2audit"})
A = 30000                 # HIST_JACKPOT_V2_HEIGHT (mainnet, owner-locked)
L = 288                   # NODE_EPOCH_LENGTH
JP_FIRST, JP_STEP = 25290, 288
HB_WINDOW, HB_REQUIRED = 4, 3
TX_BIND, TX_HEARTBEAT, OUT_NODE_PROTOCOL = 0x20, 0x21, 0x30
SCHEMA = 1
REORG_WALK = 2000


# ---- RIPEMD-160 (hashlib's is missing on some OpenSSL builds; pure fallback, test-vectored) ----
def _ripemd160_py(data):
    def rol(x, n):
        return ((x << n) | (x >> (32 - n))) & 0xffffffff
    r1 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
          3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12, 1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2,
          4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13]
    r2 = [5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12, 6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
          15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13, 8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14,
          12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11]
    s1 = [11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8, 7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12,
          11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5, 11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12,
          9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6]
    s2 = [8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6, 9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11,
          9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5, 15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8,
          8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11]
    k1 = [0, 0x5a827999, 0x6ed9eba1, 0x8f1bbcdc, 0xa953fd4e]
    k2 = [0x50a28be6, 0x5c4dd124, 0x6d703ef3, 0x7a6d76e9, 0]

    def f(j, x, y, z):
        if j < 16:
            return x ^ y ^ z
        if j < 32:
            return (x & y) | (~x & z)
        if j < 48:
            return (x | ~y) ^ z
        if j < 64:
            return (x & z) | (y & ~z)
        return x ^ (y | ~z)
    msg = bytearray(data) + b"\x80"
    while len(msg) % 64 != 56:
        msg += b"\x00"
    msg += (8 * len(data)).to_bytes(8, "little")
    h = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0]
    for i in range(0, len(msg), 64):
        x = [int.from_bytes(msg[i + 4 * j:i + 4 * j + 4], "little") for j in range(16)]
        al, bl, cl, dl, el = h
        ar, br, cr, dr, er = h
        for j in range(80):
            t = (rol((al + (f(j, bl, cl, dl) & 0xffffffff) + x[r1[j]] + k1[j // 16]) & 0xffffffff, s1[j]) + el) & 0xffffffff
            al, el, dl, cl, bl = el, dl, rol(cl, 10), bl, t
            t = (rol((ar + (f(79 - j, br, cr, dr) & 0xffffffff) + x[r2[j]] + k2[j // 16]) & 0xffffffff, s2[j]) + er) & 0xffffffff
            ar, er, dr, cr, br = er, dr, rol(cr, 10), br, t
        t = (h[1] + cl + dr) & 0xffffffff
        h[1] = (h[2] + dl + er) & 0xffffffff
        h[2] = (h[3] + el + ar) & 0xffffffff
        h[3] = (h[4] + al + br) & 0xffffffff
        h[4] = (h[0] + bl + cr) & 0xffffffff
        h[0] = t
    return b"".join(v.to_bytes(4, "little") for v in h)


def ripemd160(data):
    try:
        return hashlib.new("ripemd160", data).digest()
    except (ValueError, TypeError):
        return _ripemd160_py(data)


def address_of_pubkey(pub33):
    return "sost1" + ripemd160(hashlib.sha256(pub33).digest()).hex()


# ---- raw tx decoding ----
def _compact(a, o):
    if o >= len(a):
        return None
    b = a[o]
    if b < 0xFD:
        return b, o + 1
    n = {0xFD: 2, 0xFE: 4, 0xFF: 8}[b]
    if o + 1 + n > len(a):
        return None
    return int.from_bytes(a[o + 1:o + 1 + n], "little"), o + 1 + n


def parse_node_tx(hex_str):
    """Raw tx -> ('bind', {...}) | ('hb', {...}) | None. Only 0-input node-protocol txs qualify."""
    try:
        a = bytes.fromhex(hex_str)
    except (ValueError, TypeError):
        return None
    if len(a) < 7:
        return None
    tx_type = a[4]
    if tx_type not in (TX_BIND, TX_HEARTBEAT):
        return None
    r = _compact(a, 5)
    if not r or r[0] != 0:
        return None
    r = _compact(a, r[1])
    if not r or r[0] != 1:
        return None
    o = r[1]
    if o + 31 > len(a) or a[o + 8] != OUT_NODE_PROTOCOL:
        return None
    plen = a[o + 29] | (a[o + 30] << 8)
    p = a[o + 31:o + 31 + plen]
    if len(p) != plen:
        return None
    if tx_type == TX_BIND and plen in (138, 202):
        mp, npk = p[0:33], p[33:66]
        return "bind", {"miner": address_of_pubkey(mp), "node": npk.hex(),
                        "seq": int.from_bytes(p[66:74], "little"), "v": 2 if plen == 202 else 1}
    if tx_type == TX_HEARTBEAT and plen == 137:
        return "hb", {"node": p[0:33].hex(), "epoch": int.from_bytes(p[33:41], "little"), "tip_ref": p[41:73].hex()}
    return None


def epoch_of(h):
    return -1 if h < A else (h - A) // L


def completed_before(h):
    return 0 if h <= A else (h - A) // L


def next_jackpot_after(h):
    if h < JP_FIRST:
        return JP_FIRST
    return JP_FIRST + ((h - JP_FIRST) // JP_STEP + 1) * JP_STEP


def atomic_write(path, text, mode=0o644):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".np-", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


class Indexer:
    def __init__(self, rpc_url, state_path=None):
        self.rpc_url, self.state_path = rpc_url, state_path
        self.rows = []          # one per height from A: [h, hash, [[miner,node,seq,v,txid]...], [[node,epoch,tip_ref,txid]...]]
        self.reorgs = []
        self.audit = None

    def rpc(self, method, params=None):
        if method not in READ_ONLY:
            raise PermissionError(f"{method} is not a read-only method")
        body = json.dumps({"jsonrpc": "1.0", "id": 1, "method": method, "params": params or []}).encode()
        req = urllib.request.Request(self.rpc_url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
        if out.get("error"):
            raise RuntimeError(f"{method}: {out['error']}")
        return out["result"]

    @property
    def tip(self):
        return self.rows[-1][0] if self.rows else A - 1

    def read_block(self, h):
        bh = self.rpc("getblockhash", [h])
        b = self.rpc("getblock", [bh])
        if not b or b.get("hash") != bh or b.get("height") != h:
            raise RuntimeError(f"inconsistent block at {h}")
        binds, hbs = [], []
        for txid in (b.get("txids") or [])[1:]:
            t = self.rpc("getrawtransaction", [txid, True])
            p = parse_node_tx((t.get("hex") if isinstance(t, dict) else t) or "")
            if p and p[0] == "bind":
                binds.append([p[1]["miner"], p[1]["node"], p[1]["seq"], p[1]["v"], txid])
            elif p and p[0] == "hb":
                hbs.append([p[1]["node"], p[1]["epoch"], p[1]["tip_ref"], txid])
        return [h, bh, binds, hbs], b.get("previousblockhash")

    def unwind_to_canonical(self):
        if not self.rows:
            return 0
        node_tip = self.rpc("getblockcount")
        dropped = 0
        while self.rows and self.rows[-1][0] > node_tip:
            self.rows.pop()
            dropped += 1
        walked = 0
        while self.rows and self.rpc("getblockhash", [self.rows[-1][0]]) != self.rows[-1][1]:
            self.rows.pop()
            dropped += 1
            walked += 1
            if walked > REORG_WALK:
                raise RuntimeError("reorg deeper than REORG_WALK: needs a rebuild")
        if dropped:
            self.reorgs = (self.reorgs + [{"t": int(time.time()), "depth": dropped}])[-20:]
        return dropped

    def step(self, max_blocks=None):
        self.unwind_to_canonical()
        node_tip = self.rpc("getblockcount")
        added = 0
        while self.tip < node_tip and (max_blocks is None or added < max_blocks):
            row, prev = self.read_block(self.tip + 1)
            if self.rows and prev != self.rows[-1][1]:
                self.unwind_to_canonical()
                continue
            self.rows.append(row)
            added += 1
        return added

    # ---- derivation ----
    def derive(self):
        bind = {}      # miner -> {"node","seq","h","v","txid","binds"}
        owner = {}     # node key -> miner (active binding)
        hb = {}        # miner -> {epoch: [h, txid]}
        n_binds = n_hbs = 0
        for h, _bh, binds, hbs in self.rows:
            for miner, node, seq, v, txid in binds:
                n_binds += 1
                cur = bind.get(miner)
                if cur is None or seq > cur["seq"]:
                    if cur:
                        owner.pop(cur["node"], None)
                    bind[miner] = {"node": node, "seq": seq, "h": h, "v": v, "txid": txid,
                                   "binds": (cur["binds"] + 1) if cur else 1}
                    owner[node] = miner
            for node, epoch, _tip_ref, txid in hbs:
                n_hbs += 1
                m = owner.get(node)
                if m is not None:
                    hb.setdefault(m, {}).setdefault(epoch, [h, txid])
        return bind, hb, n_binds, n_hbs

    def document(self):
        tip = self.tip
        bind, hb, n_binds, n_hbs = self.derive()
        cur_ep = epoch_of(tip)
        done = (tip + 1 - A) // L if tip >= A else 0          # epochs fully mined at this tip
        J = next_jackpot_after(tip)
        cj = completed_before(J)
        w, req = min(cj, HB_WINDOW), min(cj, HB_REQUIRED)
        win = list(range(cj - w, cj))
        audit = {}
        for c in ((self.audit or {}).get("candidates") or []):
            audit[c.get("address")] = c
        nodes = []
        for miner, b in bind.items():
            eps = hb.get(miner, {})
            b_ep = epoch_of(b["h"])
            expected = max(0, done - b_ep)                    # completed epochs since (and incl.) the bind epoch
            covered = sum(1 for e in eps if b_ep <= e < done)
            streak, e = 0, (cur_ep if cur_ep in eps else done - 1)
            while e >= b_ep and e in eps:
                streak += 1
                e -= 1
            last = max(eps) if eps else None
            in_win = sum(1 for e in win if e in eps)
            if cur_ep in eps or (done - 1) in eps:
                status = "ACTIVE"
            elif b_ep >= done - 1:
                status = "NEW"
            else:
                status = "LAPSED"
            a = audit.get(miner)
            nodes.append({
                "miner": miner, "node_key": b["node"], "bind_height": b["h"], "bind_seq": b["seq"],
                "bind_version": b["v"], "bind_txid": b["txid"], "binds_total": b["binds"],
                "bind_age_blocks": tip - b["h"], "bind_epoch": b_ep,
                "heartbeats": len(eps), "epochs_expected": expected, "epochs_covered": covered,
                "coverage": (covered / expected) if expected else None, "streak": streak,
                "last_epoch": last, "last_heartbeat_height": eps[last][0] if last is not None else None,
                "current_epoch_sent": cur_ep in eps, "status": status,
                "next_jackpot": {"height": J, "window_epochs": win, "required": req, "in_window": in_win,
                                 "node_condition_met": in_win >= req},
                "audit": None if a is None else {"node_bound": a.get("node_bound"), "heartbeats": a.get("heartbeats"),
                                                 "match": bool(a.get("node_bound")) and a.get("heartbeats") == in_win},
                "epochs": sorted(eps),
            })
        nodes.sort(key=lambda n: (n["status"] != "ACTIVE", -n["streak"], n["bind_height"]))
        return {"schema": SCHEMA, "updated_at": int(time.time()), "tip": tip,
                "tip_hash": self.rows[-1][1] if self.rows else None,
                "activation_height": A, "epoch_length": L, "current_epoch": cur_ep, "completed_epochs": done,
                "current_epoch_start": A + cur_ep * L if cur_ep >= 0 else None,
                "totals": {"bound_identities": len(bind), "active": sum(1 for n in nodes if n["status"] == "ACTIVE"),
                           "bind_txs": n_binds, "heartbeat_txs": n_hbs},
                "next_jackpot": {"height": J, "window_epochs": win, "required": req,
                                 "audit_read": self.audit is not None},
                "nodes": nodes, "reorgs_observed": self.reorgs,
                "note": "A bound node is a node key bound on chain to a mining address. A valid heartbeat proves "
                        "control of that key and that it followed the canonical chain at that time; it does not "
                        "prove one unique physical machine.",
                "source": "canonical blocks from #30,000: NODE_BIND (0x20) and NODE_HEARTBEAT (0x21) txs; "
                          "cross-checked against getjackpotv2audit for the next draw"}

    def refresh_audit(self):
        try:
            self.audit = self.rpc("getjackpotv2audit", [next_jackpot_after(self.tip)])
        except Exception:
            self.audit = None

    def save(self):
        if self.state_path:
            atomic_write(self.state_path, json.dumps({"schema": SCHEMA, "rows": self.rows, "reorgs": self.reorgs},
                                                     separators=(",", ":")), 0o600)

    def load(self):
        try:
            with open(self.state_path) as f:
                s = json.load(f)
            rows = s.get("rows")
            if s.get("schema") == SCHEMA and isinstance(rows, list) and all(r[0] == A + i for i, r in enumerate(rows)):
                self.rows, self.reorgs = rows, s.get("reorgs", [])
        except (OSError, ValueError, TypeError, IndexError):
            self.rows = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", default=os.environ.get("NP_RPC", "http://127.0.0.1:18299/"))
    ap.add_argument("--state", default=os.environ.get("NP_STATE", "/var/lib/sost-node-participation/state.json"))
    ap.add_argument("--out", default=os.environ.get("NP_OUT", "/var/www/sost-website/website/api/node_participation.json"))
    ap.add_argument("--interval", type=float, default=20.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    ix = Indexer(a.rpc, a.state)
    ix.load()
    while True:
        try:
            if ix.step():
                ix.save()
            ix.refresh_audit()
            atomic_write(a.out, json.dumps(ix.document(), separators=(",", ":")))
        except Exception as e:
            print(f"node-participation-indexer: {type(e).__name__}: {e}", flush=True)
        if a.once:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()

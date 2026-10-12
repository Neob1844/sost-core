#!/usr/bin/env python3
"""Address earnings indexer — lifetime reward earnings per address, from the chain, for the Explorer.

    SOST node ← read-only gateway ← ONE indexer → /api/address_earnings.json → N browsers

What it counts, per address, ONLY from canonical blocks (nothing inferred from balances, UTXOs,
amount matching or heuristics):

  mining      getblock.miner_reward  credited to getblock.miner_address          (every block)
  dtd normal  getblock.lottery_payout credited to getblock.lottery_winner_address (when > 0)
  dtd jackpot the jackpot transaction actually mined in the block: tx_type 0x02 (TX_TYPE_JACKPOT),
              output[0] type 0x00, decoded from the raw tx — the amount really paid to the address
              that really received it. Eligibility, candidacy and the audit's projected winner are
              NOT earnings; a draw with no winner pays nothing and credits nothing.
              V1 = jackpots below #30,000 (V15 rules), V2 = from #30,000 (Jackpot V2).

How it stays cheap and correct:
  * one full pass the first time (throttled), then incremental: only new blocks are read;
  * every cycle the stored tip hash is compared with the node; on a mismatch it walks back to the
    fork point, DROPS the orphaned blocks' contributions and re-reads the canonical ones —
    no phantom winnings after a reorg;
  * state (one compact row per block) persisted atomically, so a restart resumes where it stopped;
  * the browser downloads one static JSON (ETag/304), never calls RPC for this.

Usage:
  address-earnings-indexer.py --rpc http://127.0.0.1:18299/ --state /var/lib/sost-earnings/state.json \
      --out /var/www/sost-website/website/api/address_earnings.json
"""
import argparse
import json
import os
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

READ_ONLY = frozenset({"getblockcount", "getblockhash", "getblock", "getrawtransaction"})
V2_HEIGHT = 30000
JP_FIRST, JP_STEP = 25290, 288          # jackpot opportunity heights (same cadence V1 and V2)
SCHEMA = 1
REORG_WALK = 2000                       # deepest fork the indexer will unwind on its own
SYNC_RATE = 25.0                        # RPC calls per second during the first full pass
SAVE_EVERY = 500                        # blocks between state saves during the first pass
SYNC_WORKERS = 4                        # parallel block reads during the first pass (still capped by SYNC_RATE)
BATCH = 100                             # heights read per parallel batch


def atomic_write(path, text, mode=0o644):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".ae-", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def is_jackpot_height(h):
    return h >= JP_FIRST and (h - JP_FIRST) % JP_STEP == 0


def _compact(a, o):
    """Bitcoin-style CompactSize at a[o] -> (value, new offset) or None."""
    if o >= len(a):
        return None
    b = a[o]
    if b < 0xFD:
        return b, o + 1
    n = {0xFD: 2, 0xFE: 4, 0xFF: 8}[b]
    if o + 1 + n > len(a):
        return None
    return int.from_bytes(a[o + 1:o + 1 + n], "little"), o + 1 + n


def parse_jackpot_tx(hex_str):
    """Raw tx -> {tx_type, out_type, amount_sat, winner} or None. Same layout the Explorer parses:
    version(4) tx_type(1) nin inputs(133 each) nout output[0]: amount(8 LE) out_type(1) pkh(20)."""
    try:
        a = bytes.fromhex(hex_str)
    except (ValueError, TypeError):
        return None
    if len(a) < 6:
        return None
    o = 4
    tx_type = a[o]
    o += 1
    r = _compact(a, o)
    if not r:
        return None
    nin, o = r
    o += nin * 133
    r = _compact(a, o)
    if not r:
        return None
    nout, o = r
    if nout < 1 or o + 29 > len(a):
        return None
    amount = int.from_bytes(a[o:o + 8], "little", signed=True)
    out_type = a[o + 8]
    pkh = a[o + 9:o + 29].hex()
    return {"tx_type": tx_type, "out_type": out_type, "amount_sat": amount, "winner": "sost1" + pkh}


class Indexer:
    def __init__(self, rpc_url, state_path=None):
        self.rpc_url = rpc_url
        self.state_path = state_path
        self.rows = []          # one per height from 0: [height, hash, miner, mine_sat, dtd_addr, dtd_sat, [[jp_addr, jp_sat, txid], ...]]
        self.calls = 0
        self._last_call = 0.0
        self.throttle = 0.0
        self.reorgs = []        # observed reorgs (newest last): {"t", "from", "depth"}
        self._lock = threading.Lock()
        self.workers = 1

    # ---- node access (read-only) ----
    def rpc(self, method, params=None):
        if method not in READ_ONLY:
            raise PermissionError(f"{method} is not a read-only method")
        if self.throttle:
            with self._lock:                         # one shared pace for all workers
                wait = self.throttle - (time.time() - self._last_call)
                if wait > 0:
                    time.sleep(wait)
                self._last_call = time.time()
        with self._lock:
            self.calls += 1
        body = json.dumps({"jsonrpc": "1.0", "id": 1, "method": method, "params": params or []}).encode()
        req = urllib.request.Request(self.rpc_url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
        if out.get("error"):
            raise RuntimeError(f"{method}: {out['error']}")
        return out["result"]

    # ---- one block ----
    def read_block(self, h):
        bh = self.rpc("getblockhash", [h])
        b = self.rpc("getblock", [bh])
        if not b or b.get("hash") != bh or b.get("height") != h:
            raise RuntimeError(f"inconsistent block at {h}")
        miner = b.get("miner_address") or ""
        mine = int(b.get("miner_reward") or 0)
        dtd_addr = b.get("lottery_winner_address") or ""
        dtd = int(b.get("lottery_payout") or 0)
        if dtd <= 0 or not dtd_addr:
            dtd_addr, dtd = "", 0
        jps = []
        if is_jackpot_height(h):
            for txid in (b.get("txids") or [])[1:]:          # the coinbase is never a jackpot
                t = self.rpc("getrawtransaction", [txid, True])
                hex_str = t.get("hex") if isinstance(t, dict) else t
                p = parse_jackpot_tx(hex_str or "")
                if p and p["tx_type"] == 0x02 and p["out_type"] == 0x00 and p["amount_sat"] > 0:
                    jps.append([p["winner"], p["amount_sat"], txid])
        return [h, bh, miner, mine, dtd_addr, dtd, jps], b.get("previousblockhash")

    @property
    def tip(self):
        return self.rows[-1][0] if self.rows else -1

    # ---- reorg safety ----
    def unwind_to_canonical(self):
        """Drop stored blocks the node no longer has on its best chain. Returns blocks dropped."""
        if not self.rows:
            return 0
        node_tip = self.rpc("getblockcount")
        h = min(self.tip, node_tip)
        dropped = len(self.rows) - (h + 1)
        del self.rows[h + 1:]                       # heights above the node tip are gone
        walked = 0
        while self.rows and self.rpc("getblockhash", [self.rows[-1][0]]) != self.rows[-1][1]:
            self.rows.pop()
            dropped += 1
            walked += 1
            if walked > REORG_WALK:
                raise RuntimeError("reorg deeper than REORG_WALK: refusing to guess, needs a rebuild")
        if dropped:
            self.reorgs.append({"t": int(time.time()), "from": h, "depth": dropped})
            self.reorgs = self.reorgs[-20:]
        return dropped

    def step(self, max_blocks=None):
        """Bring the index to the node tip. Returns number of blocks added."""
        self.unwind_to_canonical()
        node_tip = self.rpc("getblockcount")
        added = 0
        pool = ThreadPoolExecutor(self.workers) if self.workers > 1 else None
        try:
            while self.tip < node_tip and (max_blocks is None or added < max_blocks):
                n = 1 if pool is None else min(BATCH, node_tip - self.tip,
                                               (max_blocks - added) if max_blocks is not None else BATCH)
                hs = list(range(self.tip + 1, self.tip + 1 + n))
                got = list(pool.map(self.read_block, hs)) if pool else [self.read_block(hs[0])]
                for row, prev in got:                # applied strictly in height order
                    if self.rows and row[0] > 0 and prev != self.rows[-1][1]:
                        self.unwind_to_canonical()   # chain moved under us mid-read: unwind, re-read
                        break
                    self.rows.append(row)
                    added += 1
                    if self.state_path and added % SAVE_EVERY == 0:
                        self.save()
        finally:
            if pool:
                pool.shutdown(wait=True)
        return added

    # ---- outputs ----
    def totals(self):
        t = {}

        def acc(addr):
            return t.setdefault(addr, [0, 0, 0, 0, 0, 0, 0, 0])   # mine_sat, blocks, dtd_sat, wins, jp_sat, jp_wins, jp_v1_sat, jp_v1_wins
        jackpots = []
        for h, _bh, miner, mine, dtd_addr, dtd, jps in self.rows:
            if miner and mine > 0:
                a = acc(miner)
                a[0] += mine
                a[1] += 1
            if dtd_addr and dtd > 0:
                a = acc(dtd_addr)
                a[2] += dtd
                a[3] += 1
            for jp_addr, jp_sat, txid in jps:
                a = acc(jp_addr)
                a[4] += jp_sat
                a[5] += 1
                if h < V2_HEIGHT:
                    a[6] += jp_sat
                    a[7] += 1
                jackpots.append({"h": h, "addr": jp_addr, "sat": jp_sat, "txid": txid, "v": 1 if h < V2_HEIGHT else 2})
        return t, jackpots

    def document(self):
        t, jackpots = self.totals()
        return {"schema": SCHEMA, "updated_at": int(time.time()), "tip": self.tip,
                "tip_hash": self.rows[-1][1] if self.rows else None,
                "fields": ["mining_sat", "mining_blocks", "dtd_normal_sat", "dtd_normal_wins",
                           "dtd_jackpot_sat", "dtd_jackpot_wins", "dtd_jackpot_v1_sat", "dtd_jackpot_v1_wins"],
                "addresses": t, "jackpots": jackpots, "reorgs_observed": self.reorgs,
                "source": "canonical blocks: getblock miner_reward / lottery_payout + mined jackpot txs (type 0x02)"}

    def save(self):
        if self.state_path:
            atomic_write(self.state_path, json.dumps({"schema": SCHEMA, "rows": self.rows, "reorgs": self.reorgs},
                                                     separators=(",", ":")), 0o600)

    def load(self):
        try:
            with open(self.state_path) as f:
                s = json.load(f)
            if s.get("schema") == SCHEMA and isinstance(s.get("rows"), list):
                rows = s["rows"]
                if all(r[0] == i for i, r in enumerate(rows)):   # contiguous from genesis, or nothing
                    self.rows = rows
                    self.reorgs = s.get("reorgs", [])
        except (OSError, ValueError, TypeError, IndexError):
            self.rows = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", default=os.environ.get("AE_RPC", "http://127.0.0.1:18299/"))
    ap.add_argument("--state", default=os.environ.get("AE_STATE", "/var/lib/sost-earnings/state.json"))
    ap.add_argument("--out", default=os.environ.get("AE_OUT", "/var/www/sost-website/website/api/address_earnings.json"))
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    ix = Indexer(a.rpc, a.state)
    ix.load()
    while True:
        try:
            first_pass = ix.tip < 0 or ix.rpc("getblockcount") - ix.tip > 50
            ix.throttle = 1.0 / SYNC_RATE if first_pass else 0.0
            ix.workers = SYNC_WORKERS if first_pass else 1
            added = ix.step(max_blocks=SAVE_EVERY if first_pass else None)
            if added or first_pass:
                ix.save()
            atomic_write(a.out, json.dumps(ix.document(), separators=(",", ":")))
            if first_pass and ix.rpc("getblockcount") - ix.tip > 0:
                continue                                  # keep going until caught up
        except Exception as e:                            # keep the last good document; retry next cycle
            print(f"indexer: {type(e).__name__}: {e}", flush=True)
        if a.once:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()

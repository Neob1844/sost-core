#!/usr/bin/env python3
"""Control Room collector — the ONLY process that queries the node for the Control Room.

    SOST node ← read-only gateway ← ONE collector → /api/control_room.json → N public browsers

Node load depends on this collector only, never on the number of visitors. The browser never
sees RPC credentials, never sends RPC methods and never reaches the RPC port: it only downloads
a static JSON file.

Per-group TTLs (seconds). A group is also refreshed immediately when the tip height changes
(marked "+tip").
  tip       getblockcount                                             1
  head      getbestblockhash, getmempoolinfo                          15 +tip
  info      getinfo (bitsQ next, Equalizer floor-now: time dependent)  3
  blocks    getblockhash/getblock for new heights (immutable, cached)  +tip
  dtd       getlotterystate                                           30 +tip
  jackpot   gethistoricaljackpotstatus, getjackpotv2audit(next)       30 +tip
  miners    geteligibleminers                                         60 +tip
  supply    getsupplyinfo                                             60 +tip
  network   getpeerinfo, getnetworksummary                            15
  node      getminerstats                                             30
Steady state ≈ 1.8 RPC/s in total (+~10 calls once per new block), independent of the number of visitors.
A new block is seen within ~1 s and written in the same cycle (the document records when: tip_changed_at). Cold fill of the 300-block window: ≤ 8 RPC per 1-s cycle for ~75 s.

Usage:
  collector.py --rpc http://127.0.0.1:18299/ --out /var/www/sost-website/website/api/control_room.json
  collector.py --from-snapshot fixtures/snapshot_20261010.json --out api/control_room.json   (staging, offline, one shot)
"""
import argparse
import hashlib
import json
import os
import tempfile
import time
import urllib.request

READ_ONLY = frozenset({"getinfo", "getblockcount", "getbestblockhash", "getblockhash", "getblock", "getsupplyinfo",
                       "getlotterystate", "geteligibleminers", "gethistoricaljackpotstatus", "getjackpotv2audit",
                       "getmempoolinfo", "getnetworksummary", "getminerstats", "getpeerinfo"})
TTL = {"tip": 1, "head": 15, "info": 3, "dtd": 30, "jackpot": 30, "miners": 60, "supply": 60, "network": 15, "node": 30}
ON_TIP = {"head", "dtd", "jackpot", "miners", "supply"}
BLOCK_BUDGET = 4    # at most 4 new blocks (8 RPC) per 1-s cycle: cold fill is spread over ~75 s, never a burst
MISSING_RETRY = 600 # a height that did not answer is retried after 10 min, not every cycle
KEEP_BLOCKS = 300   # always serve the last 300 blocks (≥ 289 for avg288, 144 for the mosaic), independent of the static series
SCHEMA = 2
BLOCK_FIELDS = ["height", "time", "bits_q", "miner_address", "casert_mode", "casert_base", "casert_profile_index", "casert_signal"]
HEARTBEAT_S = 15    # rewrite at least every 15 s so clients can tell the collector is alive


def compact_blocks(blocks):
    """Rows instead of objects (≈3× smaller); only the tip keeps its hash."""
    rows = [[b.get(k) for k in BLOCK_FIELDS] for b in blocks]
    return {"fields": BLOCK_FIELDS, "rows": rows, "tip_hash": blocks[-1].get("hash") if blocks else None}


def atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".cr-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


class Collector:
    def __init__(self, rpc_url, series_path=None, series_url=None):
        self.rpc_url = rpc_url
        self.series_path, self.series_url = series_path, series_url
        self.data = {}            # group -> dict of results
        self.fetched = {}         # group -> unix time
        self.blocks = {}          # height -> slim getblock
        self.height = None
        self.missing = {}         # height -> next retry time
        self.calls = 0
        self.observed = []        # facts observed by the collector (restarts, peer drops), newest last
        self._boot = None
        self._peers = None
        self.tip_changed_at = None   # wall time (s, float) when this collector first saw the current tip height

    def rpc(self, method, params=None):
        if method not in READ_ONLY:
            raise PermissionError(f"{method} is not a read-only method")
        self.calls += 1
        body = json.dumps({"jsonrpc": "1.0", "id": 1, "method": method, "params": params or []}).encode()
        req = urllib.request.Request(self.rpc_url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read())
        if out.get("error"):
            raise RuntimeError(f"{method}: {out['error']}")
        return out["result"]

    def series_tip(self):
        try:
            if self.series_path and os.path.exists(self.series_path):
                with open(self.series_path) as f:
                    return json.load(f).get("tip")
            if self.series_url:
                with urllib.request.urlopen(self.series_url, timeout=20) as r:
                    return json.loads(r.read()).get("tip")
        except Exception:
            return None
        return None

    def due(self, g, now, tip_changed):
        return g not in self.fetched or now - self.fetched[g] >= TTL[g] or (tip_changed and g in ON_TIP)

    def step(self, now=None):
        now = now or time.time()
        tip_changed = False
        if self.due("tip", now, False):
            h = self.rpc("getblockcount")
            if not isinstance(h, int) or h <= 0:
                raise RuntimeError(f"invalid getblockcount {h!r}")
            tip_changed = h != self.height
            if tip_changed:
                self.tip_changed_at = time.time()
            self.height = h
            self.fetched["tip"] = now
        if self.due("head", now, tip_changed):
            self.data["tip"] = {"bestblockhash": self.rpc("getbestblockhash"), "mempool": self.rpc("getmempoolinfo")}
            self.fetched["head"] = now
        if tip_changed or len(self.blocks) < min(KEEP_BLOCKS, self.height or 0):
            try:
                self.refresh_blocks(now)       # bounded per cycle; partial progress is kept
            except Exception as e:
                self.data.setdefault("errors", {})["blocks"] = f"{type(e).__name__}: {e}"[:200]
            else:
                self.data.get("errors", {}).pop("blocks", None)
        for g, fn in (("info", self.g_info), ("dtd", self.g_dtd), ("jackpot", self.g_jackpot), ("miners", self.g_miners),
                      ("supply", self.g_supply), ("network", self.g_network), ("node", self.g_node)):
            if self.due(g, now, tip_changed):
                try:
                    fn()
                    self.fetched[g] = now
                except Exception as e:  # keep the last good value, record the failure
                    self.data.setdefault("errors", {})[g] = f"{type(e).__name__}: {e}"[:200]
        return tip_changed

    def refresh_blocks(self, now=None):
        now = now or time.time()
        lo = max(1, self.height - KEEP_BLOCKS + 1)
        budget = BLOCK_BUDGET
        for h in range(self.height, lo - 1, -1):          # newest first: the tip window fills first
            if h in self.blocks or self.missing.get(h, 0) > now:
                continue
            if budget <= 0:
                break
            budget -= 1
            bh = self.rpc("getblockhash", [h])
            b = self.rpc("getblock", [bh]) if bh else None
            if not b:
                self.missing[h] = now + MISSING_RETRY
                continue
            self.missing.pop(h, None)
            self.blocks[h] = {k: b.get(k) for k in ("height", "hash", "time", "bits_q", "miner_address", "casert_mode",
                                                    "casert_base", "casert_profile_index", "casert_signal")}
        # reorg safety: drop cached heights above the tip and re-check the tip hash
        for h in [h for h in self.blocks if h > self.height or h < lo]:
            del self.blocks[h]
        tip = self.blocks.get(self.height)
        if tip and self.data.get("tip") and tip["hash"] != self.data["tip"]["bestblockhash"]:
            self.blocks.clear()          # reorg: drop the cache, refill (bounded) over the next cycles
            self.refresh_blocks(now)

    def g_info(self):
        self.data["info"] = self.rpc("getinfo")

    def g_dtd(self):
        self.data["dtd"] = self.rpc("getlotterystate")

    def g_jackpot(self):
        hj = self.rpc("gethistoricaljackpotstatus")
        nxt = hj.get("next_jackpot_height")
        self.data["jackpot"] = {"hjack": hj, "jv2": self.rpc("getjackpotv2audit", [nxt]) if nxt else None}

    def g_miners(self):
        self.data["miners"] = self.rpc("geteligibleminers")

    def g_supply(self):
        self.data["supply"] = self.rpc("getsupplyinfo")

    def g_network(self):
        peers = self.rpc("getpeerinfo")
        self.data["network"] = {"peers": peers, "netsum": self.rpc("getnetworksummary")}
        addrs = {p.get("addr") for p in peers or []}
        if self._peers is not None:
            for a in sorted(self._peers - addrs):
                self.observe("peer drop", a)
        self._peers = addrs

    def g_node(self):
        ms = self.rpc("getminerstats")
        self.data["node"] = ms
        boot = ms.get("boot_time_unix")
        if self._boot is not None and boot != self._boot:
            self.observe("node restart", "boot time changed")
        self._boot = boot

    def observe(self, kind, detail):
        self.observed.append({"t": int(time.time()), "kind": kind, "detail": detail})
        self.observed = self.observed[-50:]

    def document(self):
        d = self.data
        bundle = {
            "info": d.get("info"), "supply": d.get("supply"), "lottery": d.get("dtd"), "eligible": d.get("miners"),
            "hjack": (d.get("jackpot") or {}).get("hjack"), "jv2": (d.get("jackpot") or {}).get("jv2"),
            "mempool": (d.get("tip") or {}).get("mempool"), "netsum": (d.get("network") or {}).get("netsum"),
            "minerstats": d.get("node"), "peers": (d.get("network") or {}).get("peers"),
            "bestblockhash": (d.get("tip") or {}).get("bestblockhash"),
            "deltaBlocks": compact_blocks([self.blocks[h] for h in sorted(self.blocks)]),
            "session": {"observed": self.observed},
        }
        return {"schema": SCHEMA, "collected_at": int(time.time()), "height": self.height, "ttl": TTL,
                "tip_changed_at": round(self.tip_changed_at, 3) if self.tip_changed_at else None,
                "fetched": {g: int(t) for g, t in self.fetched.items()}, "errors": d.get("errors", {}),
                "collector": {"rpc_calls_total": self.calls, "observer": "collector (server side)"},
                "bundle": bundle}


def from_snapshot(path):
    """Offline staging: build the same document from a recorded snapshot (no network)."""
    snap = json.load(open(path))
    r = lambda m, p=None: snap["rpc"].get(m + "|" + json.dumps(p or [], separators=(",", ":")))
    info = r("getinfo")
    hj = r("gethistoricaljackpotstatus")
    series = snap["static"]["/api/block_series.json"]
    blocks = []
    for h in range(series["tip"] + 1, info["blocks"] + 1):
        hh = r("getblockhash", [h])
        if hh:
            b = r("getblock", [hh])
            blocks.append({k: b.get(k) for k in ("height", "hash", "time", "bits_q", "miner_address", "casert_mode",
                                                 "casert_base", "casert_profile_index", "casert_signal")})
    bundle = {"info": info, "supply": r("getsupplyinfo"), "lottery": r("getlotterystate"), "eligible": r("geteligibleminers"),
              "hjack": hj, "jv2": r("getjackpotv2audit", [hj["next_jackpot_height"]]), "mempool": r("getmempoolinfo"),
              "netsum": r("getnetworksummary"), "minerstats": r("getminerstats"), "peers": r("getpeerinfo"),
              "bestblockhash": r("getbestblockhash"), "deltaBlocks": compact_blocks(blocks), "session": {"observed": []}}
    return {"schema": SCHEMA, "collected_at": snap["recorded_at"], "height": info["blocks"], "ttl": TTL,
            "fetched": {}, "errors": {}, "collector": {"rpc_calls_total": 0, "observer": "snapshot replay"},
            "replay": True, "bundle": bundle}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", default=os.environ.get("CR_RPC", "http://127.0.0.1:18299/"))
    ap.add_argument("--out", default=os.environ.get("CR_OUT", "/var/www/sost-website/website/api/control_room.json"))
    ap.add_argument("--series-path", default=os.environ.get("CR_SERIES", "/var/www/sost-website/website/api/block_series.json"))
    ap.add_argument("--series-url")
    ap.add_argument("--from-snapshot")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    if a.from_snapshot:
        atomic_write(a.out, json.dumps(from_snapshot(a.from_snapshot), separators=(",", ":")))
        print("wrote", a.out)
        return
    c = Collector(a.rpc, a.series_path if os.path.exists(a.series_path) else None, a.series_url)
    last_write, last_digest = 0, None
    while True:
        t0 = time.time()
        try:
            c.step()
            now = time.time()
            doc = c.document()
            digest = hashlib.sha256(json.dumps({k: v for k, v in doc.items() if k not in ("collected_at", "collector", "fetched")},
                                               sort_keys=True).encode()).hexdigest()
            # write only when the content changed (so clients get HTTP 304) or as a heartbeat
            if digest != last_digest or now - last_write >= HEARTBEAT_S:
                atomic_write(a.out, json.dumps(doc, separators=(",", ":")))
                last_write, last_digest = now, digest
        except Exception as e:
            c.data.setdefault("errors", {})["loop"] = f"{type(e).__name__}: {e}"[:200]
        if a.once:
            break
        time.sleep(max(0.05, 1.0 - (time.time() - t0)))   # 1-s cadence including the cycle's own work


if __name__ == "__main__":
    main()

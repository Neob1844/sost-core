#!/usr/bin/env python3
"""DTD history snapshot for the public explorer (READ-ONLY on the node).

Walks the chain through the node's local RPC and maintains the same accumulator the
explorer's "LOAD FULL DTD HISTORY" scan builds in the browser (localStorage key
sost_dtd_acc_v3), then publishes it as a static JSON file. A browser seeds its scan from
this snapshot and only fetches the blocks after `scannedHeight`, instead of walking the
whole chain through the rate-limited public RPC.

The per-block accumulation is a line-by-line port of processBlock() in
website/sost-explorer.html; keep the two in sync.

Incremental: state is kept in STATE; each run processes only new blocks up to
tip - FINALITY. If the stored hash at scannedHeight no longer matches the chain (reorg),
the state is rebuilt from genesis.
"""
import json, os, sys, tempfile, urllib.request, base64

RPC_URL = os.environ.get("SOST_RPC_URL", "http://127.0.0.1:18232/")
RPC_USER = os.environ.get("RPC_USER", "")
RPC_PASS_FILE = os.environ.get("RPC_PASS_FILE", "/etc/sost/rpc.pass")
STATE = os.environ.get("DTD_STATE", "/var/lib/sost-dtd/acc_state.json")
OUT = os.environ.get("DTD_OUT", "/var/www/sost-website/website/api/dtd_history_acc.json")
SERIES_OUT = os.environ.get("SERIES_OUT", "/var/www/sost-website/website/api/block_series.json")
SERIES_N = int(os.environ.get("SERIES_N", "1200"))
FINALITY = int(os.environ.get("DTD_FINALITY", "6"))
PHASE2_START = 7100
RECENT_KEEP = 13000
CONSTITUTIONAL = ["sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d",
                  "sost1059d1ef8639bcf47ec35e9299c17dc0452c3df33",
                  "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"]

_auth = None
def rpc(method, params):
    global _auth
    if _auth is None:
        pw = open(RPC_PASS_FILE).read().strip()
        _auth = base64.b64encode(f"{RPC_USER}:{pw}".encode()).decode()
    req = urllib.request.Request(RPC_URL, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Basic " + _auth})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    if d.get("error"):
        raise RuntimeError(f"{method}: {d['error']}")
    return d["result"]

def stocks(v):
    # JS: Number(v||0); isFinite ? v : 0
    try:
        x = float(v or 0)
    except (TypeError, ValueError):
        return 0
    if x != x or x in (float("inf"), float("-inf")):
        return 0
    return int(x) if x == int(x) else x

def fresh():
    return {"scannedHeight": -1, "scannedHash": "",
            "t": {"s": 0, "m": 0, "g": 0, "p": 0, "l": 0},
            "rows": {a: {"mb": 0, "ms": 0, "dws": 0, "dwc": 0, "lm": 0} for a in CONSTITUTIONAL},
            "ph2": {"blocks": 0, "payoutCount": 0, "normalCount": 0, "emptyCount": 0,
                    "lotteryWins": 0, "winners": {}, "payouts": [], "minerCounts": {},
                    "largestLottery": 0, "subsidyPhase2": 0, "minerSharePhase2": 0,
                    "goldPhase2": 0, "popcPhase2": 0, "lotteryPhase2": 0},
            "recent": []}

def ensure(acc, addr):
    if not addr:
        return None
    rows = acc["rows"]
    if addr not in rows:
        rows[addr] = {"mb": 0, "ms": 0, "dws": 0, "dwc": 0, "lm": 0}
    return rows[addr]

def process_block(acc, b):
    if not b:
        return
    t, ph2 = acc["t"], acc["ph2"]
    subsidy = stocks(b.get("subsidy"))
    miner_reward = stocks(b["miner_reward"]) if "miner_reward" in b else subsidy // 2
    gold_reward = stocks(b["gold_vault_reward"]) if "gold_vault_reward" in b else subsidy // 4
    popc_reward = stocks(b["popc_pool_reward"]) if "popc_pool_reward" in b else subsidy // 4
    lottery = stocks(b.get("lottery_payout") or b.get("lottery_reward") or 0)
    t["s"] += subsidy; t["m"] += miner_reward; t["g"] += gold_reward; t["p"] += popc_reward; t["l"] += lottery
    winner = b.get("lottery_winner_address")
    if lottery > 0 and winner:
        wr = ensure(acc, winner)
        wr["dws"] += lottery; wr["dwc"] += 1
    height = b.get("height") or 0
    miner = b.get("miner_address")
    if miner:
        r = ensure(acc, miner)
        r["mb"] += 1; r["ms"] += miner_reward; r["lm"] = max(r["lm"], height)
        acc["recent"].append({"h": height, "m": miner})
    if height >= PHASE2_START:
        ph2["blocks"] += 1; ph2["subsidyPhase2"] += subsidy; ph2["minerSharePhase2"] += miner_reward
        ph2["goldPhase2"] += gold_reward; ph2["popcPhase2"] += popc_reward; ph2["lotteryPhase2"] += lottery
        if lottery > 0:
            ph2["payoutCount"] += 1; ph2["lotteryWins"] += 1
            if lottery > ph2["largestLottery"]:
                ph2["largestLottery"] = lottery
            if winner:
                ph2["winners"][winner] = ph2["winners"].get(winner, 0) + lottery
                ph2["payouts"].append({"h": b.get("height"), "addr": winner, "amt": lottery})
        elif gold_reward > 0 or popc_reward > 0:
            ph2["normalCount"] += 1
        else:
            ph2["emptyCount"] += 1
        if miner:
            ph2["minerCounts"][miner] = ph2["minerCounts"].get(miner, 0) + 1

def series_row(b):
    # [height, time, bits_q, casert_profile_index, miner_address] - public header fields only.
    p = b.get("casert_profile_index")
    return [b.get("height"), b.get("time"), b.get("bits_q"), (int(p) if p is not None else None), b.get("miner_address") or ""]

def atomic_write(path, text, mode=0o644):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)

def main():
    try:
        acc = json.load(open(STATE))
    except (OSError, ValueError):
        acc = fresh()
    if acc["scannedHeight"] >= 0:
        if rpc("getblockhash", [str(acc["scannedHeight"])]) != acc["scannedHash"]:
            print(f"reorg below #{acc['scannedHeight']} - rebuilding from genesis", file=sys.stderr)
            acc = fresh()
    tip = int(rpc("getblockcount", []))
    target = tip - FINALITY
    series = acc.get("series") or []
    backfilled = False
    if acc["scannedHeight"] >= 0 and (not series or series[-1][0] != acc["scannedHeight"]):
        backfilled = True
        # backfill the recent block series (state created before the series existed)
        series = []
        for hh in range(max(0, acc["scannedHeight"] - SERIES_N + 1), acc["scannedHeight"] + 1):
            series.append(series_row(rpc("getblock", [rpc("getblockhash", [str(hh)])])))
    h = acc["scannedHeight"] + 1
    last_hash = acc["scannedHash"]
    while h <= target:
        hh = rpc("getblockhash", [str(h)])
        b = rpc("getblock", [hh])
        if b is None or b.get("height") != h:
            raise RuntimeError(f"bad block at #{h}")
        process_block(acc, b)
        series.append(series_row(b))
        last_hash = hh
        h += 1
    series = series[-SERIES_N:]
    acc["series"] = series
    if h - 1 == acc["scannedHeight"] and not backfilled and os.path.exists(OUT) and os.path.exists(SERIES_OUT):
        return
    acc["scannedHeight"] = h - 1
    acc["scannedHash"] = last_hash
    acc["recent"] = [x for x in acc["recent"] if x["h"] > acc["scannedHeight"] - RECENT_KEEP]
    atomic_write(STATE, json.dumps(acc, separators=(",", ":")), 0o600)
    pub = {k: acc[k] for k in ("scannedHeight", "scannedHash", "t", "rows", "ph2", "recent")}
    pub["generated_by"] = "dtd-history-snapshot (read-only replay of public chain data)"
    atomic_write(OUT, json.dumps(pub, separators=(",", ":")))
    atomic_write(SERIES_OUT, json.dumps({"tip": acc["scannedHeight"], "fields": ["h", "t", "bits_q", "profile", "miner"],
                                         "rows": series, "genesis_time": 1773597600, "target_spacing": 600},
                                        separators=(",", ":")))
    print(f"snapshot at #{acc['scannedHeight']} ({len(acc['rows'])} addresses)")

if __name__ == "__main__":
    main()

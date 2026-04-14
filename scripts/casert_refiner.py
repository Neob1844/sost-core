#!/usr/bin/env python3
"""
CASERT post-V5 refiner / observer.

Read-only analytical tool. Does NOT touch consensus.
Reads recent chain data via RPC and produces a numerical report
to help decide whether cASERT needs further refinement.
"""
import argparse
import base64
import csv
import json
import statistics
import sys
import time
import urllib.request
from collections import Counter

GENESIS_TIME = 1773597600
TARGET_SPACING = 600


def parse_casert_mode(mode):
    """Convert SOST casert_mode string ('B0', 'H1'..'H12', 'E1'..'E4') to signed int."""
    if not mode or mode == "B0":
        return 0
    try:
        if mode[0] == "H":
            return int(mode[1:])
        if mode[0] == "E":
            return -int(mode[1:])
    except (ValueError, IndexError):
        pass
    return 0


def rpc_call(url, user, password, method, params=None, timeout=10):
    if params is None:
        params = []
    payload = json.dumps({"method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(f"RPC error in {method}: {data['error']}")
    return data["result"]


def expected_height_from_time(ts):
    elapsed = ts - GENESIS_TIME
    return max(0, elapsed // TARGET_SPACING)


def sign_label(x):
    if x > 0:
        return f"{x} ahead"
    if x < 0:
        return f"{-x} behind"
    return "on schedule"


def pct(n, d):
    return 0.0 if d == 0 else (100.0 * n / d)


def fmt_seconds(s):
    s = int(s)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


def summarize(headers):
    if len(headers) < 2:
        return {"error": "not enough blocks"}

    intervals = [headers[i]["time"] - headers[i - 1]["time"] for i in range(1, len(headers))]
    lags = [h["height"] - expected_height_from_time(h["time"]) for h in headers]
    profiles = [h.get("profile_index", 0) for h in headers]
    bitsq = [h.get("powDiffQ", 0) for h in headers]
    miners = [h.get("miner", "unknown") for h in headers]

    overshoots = 0
    h10plus_entries = 0
    long20 = long40 = long60 = 0
    h10_time = h11_time = h12_time = 0

    for i in range(1, len(headers)):
        dt = intervals[i - 1]
        pi = profiles[i]
        prev_pi = profiles[i - 1]

        if dt > 20 * 60:
            long20 += 1
        if dt > 40 * 60:
            long40 += 1
        if dt > 60 * 60:
            long60 += 1

        if pi == 10:
            h10_time += dt
        elif pi == 11:
            h11_time += dt
        elif pi >= 12:
            h12_time += dt

        if prev_pi < 10 and pi >= 10:
            h10plus_entries += 1

        # Overshoot heuristic: rapid B0 -> H6 -> H9 -> H10+ escalation followed by a long block.
        if i >= 3:
            p3 = profiles[i - 3]
            p2 = profiles[i - 2]
            p1 = profiles[i - 1]
            c = profiles[i]
            if p3 <= 0 and p2 >= 6 and p1 >= 9 and c >= 10 and dt > 20 * 60:
                overshoots += 1

    # Crude sawtooth amplitude on bitsQ.
    sawtooth_swings = []
    last_local_min = last_local_max = None
    for i in range(1, len(bitsq) - 1):
        if bitsq[i] <= bitsq[i - 1] and bitsq[i] <= bitsq[i + 1]:
            last_local_min = bitsq[i]
        if bitsq[i] >= bitsq[i - 1] and bitsq[i] >= bitsq[i + 1]:
            last_local_max = bitsq[i]
        if last_local_min is not None and last_local_max is not None and last_local_max > last_local_min:
            sawtooth_swings.append(last_local_max - last_local_min)
            last_local_min = last_local_max = None

    profile_counts = Counter(profiles)
    miner_counts = Counter(miners)
    top_miner_share = pct(max(miner_counts.values()), len(miners)) if miner_counts else 0.0

    p95 = statistics.quantiles(intervals, n=20)[18] if len(intervals) >= 20 else max(intervals)

    return {
        "blocks": len(headers),
        "avg_interval_s": statistics.mean(intervals),
        "median_interval_s": statistics.median(intervals),
        "p95_interval_s": p95,
        "avg_lag": statistics.mean(lags),
        "min_lag": min(lags),
        "max_lag": max(lags),
        "lag_std": statistics.pstdev(lags) if len(lags) > 1 else 0.0,
        "avg_bitsq": statistics.mean(bitsq),
        "avg_sawtooth_bitsq_q16": statistics.mean(sawtooth_swings) if sawtooth_swings else 0.0,
        "overshoots": overshoots,
        "h10plus_entries": h10plus_entries,
        "long20": long20,
        "long40": long40,
        "long60": long60,
        "h10_time_s": h10_time,
        "h11_time_s": h11_time,
        "h12_time_s": h12_time,
        "unique_miners": len(miner_counts),
        "top_miner_share_pct": top_miner_share,
        "profile_counts": dict(sorted(profile_counts.items())),
        "top_miners": miner_counts.most_common(5),
    }


def recommendation(s):
    notes = []
    avg_int = s["avg_interval_s"]
    if avg_int < 480:
        notes.append("Chain is running fast on average; equalizer may still brake late.")
    elif avg_int > 720:
        notes.append("Chain is running slow on average; possible over-braking or insufficient real hashrate.")
    else:
        notes.append("Average interval is close to the 10-minute target.")

    notes.append("Structural overshoots persist — review entry into high profiles." if s["overshoots"] >= 2
                 else "No severe overshoots in this window.")
    notes.append("Still too many blocks >40 min — check if they follow H9/H10/H11." if s["long40"] >= 2
                 else "Very-long blocks are contained.")
    notes.append("Too much time spent in H12 — extreme range still too frequent." if s["h12_time_s"] > 1800
                 else "Time in H12 looks reasonable or low.")
    notes.append("Lag oscillation still high — controller is still sawtoothing more than desirable." if s["lag_std"] > 6
                 else "Lag variability looks contained.")
    notes.append("bitsQ still shows appreciable sawtooth — keep watching, not consensus-actionable alone." if s["avg_sawtooth_bitsq_q16"] > 12
                 else "bitsQ sawtooth looks moderate.")
    notes.append("Strong hashrate concentration — part of the behavior may come from miner dominance." if s["top_miner_share_pct"] > 50
                 else "Miner distribution looks reasonably spread.")
    return notes


def main():
    ap = argparse.ArgumentParser(description="CASERT post-V5 refiner / observer")
    ap.add_argument("--rpc", default="http://127.0.0.1:18232")
    ap.add_argument("--rpc-user", required=True)
    ap.add_argument("--rpc-pass", required=True)
    ap.add_argument("--window", type=int, default=288, help="blocks to analyze")
    ap.add_argument("--csv", default="casert_refiner.csv")
    args = ap.parse_args()

    u, p = args.rpc_user, args.rpc_pass
    tip = rpc_call(args.rpc, u, p, "getblockcount")
    start = max(1, tip - args.window + 1)

    headers = []
    for h in range(start, tip + 1):
        bh = rpc_call(args.rpc, u, p, "getblockhash", [h])
        blk = rpc_call(args.rpc, u, p, "getblock", [bh])
        headers.append({
            "height": blk["height"],
            "time": blk["time"],
            "powDiffQ": blk.get("bits_q", 0),
            "profile_index": parse_casert_mode(blk.get("casert_mode", "B0")),
            "miner": blk.get("miner_address", "unknown"),
            "hash": bh,
        })

    summary = summarize(headers)
    if "error" in summary:
        print(summary["error"])
        sys.exit(1)

    now = int(time.time())
    exp_now = expected_height_from_time(now)
    lag_now = tip - exp_now

    print("\n=== CASERT REFINER REPORT ===")
    print(f"Tip height:           {tip}")
    print(f"Expected now:         {exp_now}")
    print(f"Current lag:          {lag_now} ({sign_label(lag_now)})")
    print(f"Window analyzed:      {summary['blocks']} blocks")
    print(f"Avg interval:         {fmt_seconds(summary['avg_interval_s'])}")
    print(f"Median interval:      {fmt_seconds(summary['median_interval_s'])}")
    print(f"P95 interval:         {fmt_seconds(summary['p95_interval_s'])}")
    print(f"Avg lag:              {summary['avg_lag']:.2f}")
    print(f"Lag range:            {summary['min_lag']} .. {summary['max_lag']}")
    print(f"Lag std dev:          {summary['lag_std']:.2f}")
    print(f"Avg bitsQ:            {summary['avg_bitsq']:.3f}")
    print(f"Avg bitsQ swing:      {summary['avg_sawtooth_bitsq_q16']:.3f} Q16 units")
    print(f"Overshoots:           {summary['overshoots']}")
    print(f"H10+ entries:         {summary['h10plus_entries']}")
    print(f"Blocks >20m:          {summary['long20']}")
    print(f"Blocks >40m:          {summary['long40']}")
    print(f"Blocks >60m:          {summary['long60']}")
    print(f"Time in H10:          {fmt_seconds(summary['h10_time_s'])}")
    print(f"Time in H11:          {fmt_seconds(summary['h11_time_s'])}")
    print(f"Time in H12:          {fmt_seconds(summary['h12_time_s'])}")
    print(f"Unique miners:        {summary['unique_miners']}")
    print(f"Top miner share:      {summary['top_miner_share_pct']:.1f}%")
    print(f"Profile counts:       {summary['profile_counts']}")
    print(f"Top miners:           {summary['top_miners']}")

    print("\n=== INTERPRETATION ===")
    for line in recommendation(summary):
        print(f"- {line}")

    with open(args.csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in summary.items():
            if isinstance(v, (dict, list, tuple)):
                w.writerow([k, json.dumps(v, ensure_ascii=False)])
            else:
                w.writerow([k, v])

    print(f"\nCSV written to: {args.csv}")
    print("Use this report to decide whether any future tuning is needed. Never change consensus based on one window alone.")


if __name__ == "__main__":
    main()

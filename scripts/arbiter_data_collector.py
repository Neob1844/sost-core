#!/usr/bin/env python3
"""
Mode Arbiter Data Collector — Automatic production data gathering.

Runs periodically against the SOST node RPC, collecting the signals
needed to design and validate the Mode Arbiter for block 10,000.

Data collected per block:
  - height, timestamp, interval (dt)
  - bitsQ (numeric difficulty)
  - profile_index, profile_name
  - lag (schedule lag)
  - stability_pct (from node estimate)
  - anti-stall active or not
  - burst detection signals (median3, lag trend)
  - mode classification (what the arbiter WOULD have decided)

Outputs:
  - data/arbiter_telemetry.csv (append-only, one row per block)
  - data/arbiter_summary.json (rolling summary stats)

Usage:
    # Run once (snapshot current state)
    python3 scripts/arbiter_data_collector.py --rpc http://127.0.0.1:18232

    # Run continuously (poll every 10s, append new blocks)
    python3 scripts/arbiter_data_collector.py --rpc http://127.0.0.1:18232 --watch

    # Analyze existing data
    python3 scripts/arbiter_data_collector.py --analyze data/arbiter_telemetry.csv
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

GENESIS_TIME = 1773597600
TARGET_SPACING = 600

def rpc_call(url, method, params=None):
    body = json.dumps({"jsonrpc":"1.0","id":"collector","method":method,"params":params or []})
    req = urllib.request.Request(url, body.encode(), {"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("result")
    except Exception as e:
        return None

def get_block_data(url, height):
    """Fetch block data from RPC."""
    hash_resp = rpc_call(url, "getblockhash", [str(height)])
    if not hash_resp:
        return None
    block = rpc_call(url, "getblock", [hash_resp])
    if not block:
        return None
    return block

def classify_mode(lag, median3_dt, profile_idx, stall_seconds, anti_stall_threshold=3600):
    """
    Classify what mode the arbiter WOULD assign based on current signals.
    This is hypothetical — the arbiter is not implemented yet.
    """
    if stall_seconds >= anti_stall_threshold:
        return "STALL"
    if lag >= 8 and median3_dt < 120:
        return "BURST"
    if lag >= 6 and median3_dt < 60:
        return "BURST"
    if lag <= 4 and median3_dt >= 300:
        return "NORMAL"
    if lag <= 2:
        return "NORMAL"
    # Transition zone
    if profile_idx <= 2 and lag <= 6:
        return "RECOVERY"
    return "NORMAL"

def compute_signals(blocks, current_height):
    """Compute arbiter signals from recent blocks."""
    if len(blocks) < 4:
        return {}

    # Last 3 intervals
    dts = []
    for i in range(-1, -4, -1):
        if abs(i) < len(blocks):
            dt = blocks[i]["time"] - blocks[i-1]["time"]
            dts.append(max(1, dt))
    dts.sort()
    median3 = dts[1] if len(dts) >= 3 else dts[0]

    # Last block
    last = blocks[-1]
    dt_last = last["time"] - blocks[-2]["time"] if len(blocks) >= 2 else TARGET_SPACING

    # Lag
    elapsed = last["time"] - GENESIS_TIME
    expected = elapsed // TARGET_SPACING if elapsed >= 0 else 0
    lag = int(last["height"] - expected)

    # Live lag (wall clock)
    now = int(time.time())
    live_elapsed = now - GENESIS_TIME
    live_expected = live_elapsed // TARGET_SPACING
    live_lag = int(current_height - live_expected)

    # Stall
    stall_seconds = max(0, now - last["time"])

    # Profile
    pi = last.get("profile_index", 0)

    # bitsQ
    bitsq = last.get("bits_q", 0)

    # Anti-stall active
    anti_stall = stall_seconds >= 3600

    # Mode classification
    mode = classify_mode(live_lag, median3, pi, stall_seconds)

    # Burst signals
    is_burst_t1 = live_lag >= 8 and median3 < 120
    is_burst_t2 = live_lag >= 12 and median3 < 60

    # Profile oscillation (last 10 blocks)
    recent_profiles = [b.get("profile_index", 0) for b in blocks[-10:]]
    profile_changes = sum(1 for i in range(1, len(recent_profiles))
                        if recent_profiles[i] != recent_profiles[i-1])
    max_profile_10 = max(recent_profiles) if recent_profiles else 0
    min_profile_10 = min(recent_profiles) if recent_profiles else 0

    # bitsQ trend (last 10 blocks)
    recent_bitsq = [b.get("bits_q", 0) for b in blocks[-10:]]
    bitsq_delta = (recent_bitsq[-1] - recent_bitsq[0]) if len(recent_bitsq) >= 2 else 0

    return {
        "height": current_height,
        "timestamp": now,
        "dt_last": dt_last,
        "median3_dt": median3,
        "lag_chain": lag,
        "lag_live": live_lag,
        "profile_index": pi,
        "profile_name": f"H{pi}" if pi > 0 else ("B0" if pi == 0 else f"E{abs(pi)}"),
        "bitsq": bitsq,
        "bitsq_float": round(bitsq / 65536, 3) if bitsq else 0,
        "stall_seconds": stall_seconds,
        "anti_stall_active": anti_stall,
        "mode_would_be": mode,
        "burst_t1": is_burst_t1,
        "burst_t2": is_burst_t2,
        "profile_changes_10": profile_changes,
        "max_profile_10": max_profile_10,
        "min_profile_10": min_profile_10,
        "bitsq_delta_10": bitsq_delta,
    }

def append_csv(path, row):
    """Append one row to CSV, creating headers if needed."""
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)

def update_summary(path, signals_history):
    """Write rolling summary JSON."""
    if not signals_history:
        return

    recent = signals_history[-288:]  # last 288 entries (~48h if 1 per block)

    modes = [s["mode_would_be"] for s in recent]
    mode_counts = {}
    for m in modes:
        mode_counts[m] = mode_counts.get(m, 0) + 1

    profiles = [s["profile_index"] for s in recent]
    lags = [s["lag_live"] for s in recent]
    dts = [s["dt_last"] for s in recent]
    stalls = [s["stall_seconds"] for s in recent]
    burst_count = sum(1 for s in recent if s["burst_t1"])

    summary = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "entries": len(recent),
        "latest_height": recent[-1]["height"],
        "mode_distribution": mode_counts,
        "mode_pct": {k: round(v/len(recent)*100, 1) for k, v in mode_counts.items()},
        "lag_mean": round(sum(lags)/len(lags), 1),
        "lag_max": max(lags),
        "lag_min": min(lags),
        "profile_mean": round(sum(profiles)/len(profiles), 1),
        "profile_max": max(profiles),
        "dt_mean": round(sum(dts)/len(dts)),
        "dt_median": sorted(dts)[len(dts)//2],
        "stall_max": max(stalls),
        "burst_events": burst_count,
        "blocks_over_20m": sum(1 for d in dts if d >= 1200),
        "blocks_over_40m": sum(1 for d in dts if d >= 2400),
        "blocks_over_60m": sum(1 for d in dts if d >= 3600),
        "profile_oscillations": sum(1 for s in recent if s["profile_changes_10"] >= 5),
    }

    with open(path, "w") as f:
        json.dump(summary, f, indent=2)

def collect_snapshot(url, last_known_height=0):
    """Collect data for all new blocks since last_known_height."""
    info = rpc_call(url, "getinfo")
    if not info:
        return None, last_known_height

    current_height = info.get("blocks", 0)
    if current_height <= last_known_height:
        return None, last_known_height

    # Fetch recent blocks for signal computation (last 20)
    blocks = []
    start_h = max(0, current_height - 20)
    for h in range(start_h, current_height + 1):
        b = get_block_data(url, h)
        if b:
            blocks.append({
                "height": b.get("height", h),
                "time": b.get("time", 0),
                "bits_q": b.get("bits_q", 0),
                "profile_index": b.get("profile_index", 0),
            })

    if not blocks:
        return None, last_known_height

    signals = compute_signals(blocks, current_height)
    return signals, current_height

def analyze_csv(path):
    """Analyze collected telemetry data."""
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append(r)

    if not rows:
        print("No data.")
        return

    print(f"\n{'═'*70}")
    print(f"  MODE ARBITER TELEMETRY ANALYSIS")
    print(f"  {len(rows)} data points")
    print(f"{'═'*70}")

    # Mode distribution
    modes = {}
    for r in rows:
        m = r.get("mode_would_be", "UNKNOWN")
        modes[m] = modes.get(m, 0) + 1

    print(f"\n  Mode distribution (what the arbiter WOULD have decided):")
    for m, count in sorted(modes.items()):
        pct = count / len(rows) * 100
        bar = '█' * int(pct / 2)
        print(f"    {m:>10}: {count:>5} ({pct:5.1f}%)  {bar}")

    # Burst events
    bursts = sum(1 for r in rows if r.get("burst_t1") == "True")
    print(f"\n  Burst events detected: {bursts} ({bursts/len(rows)*100:.1f}%)")

    # Profile distribution
    profiles = {}
    for r in rows:
        p = r.get("profile_name", "?")
        profiles[p] = profiles.get(p, 0) + 1

    print(f"\n  Profile distribution:")
    for p, count in sorted(profiles.items()):
        pct = count / len(rows) * 100
        print(f"    {p:>5}: {count:>5} ({pct:5.1f}%)")

    # Stall stats
    stalls = [int(r.get("stall_seconds", 0)) for r in rows]
    over_20 = sum(1 for s in stalls if s >= 1200)
    over_40 = sum(1 for s in stalls if s >= 2400)
    over_60 = sum(1 for s in stalls if s >= 3600)
    print(f"\n  Stall stats:")
    print(f"    >20min: {over_20}  >40min: {over_40}  >60min: {over_60}")

    # Key question: would the arbiter have prevented stalls?
    stall_in_burst = sum(1 for r in rows
                        if int(r.get("stall_seconds", 0)) >= 1200
                        and r.get("mode_would_be") == "BURST")
    stall_in_normal = sum(1 for r in rows
                         if int(r.get("stall_seconds", 0)) >= 1200
                         and r.get("mode_would_be") == "NORMAL")
    print(f"\n  Stalls by mode:")
    print(f"    During BURST: {stall_in_burst}")
    print(f"    During NORMAL: {stall_in_normal}")

    print(f"\n{'═'*70}")
    print(f"  This data will inform the Mode Arbiter design for block 10,000.")
    print(f"{'═'*70}")


def main():
    ap = argparse.ArgumentParser(description="Mode Arbiter Data Collector")
    ap.add_argument("--rpc", default="http://127.0.0.1:18232",
                    help="Node RPC URL")
    ap.add_argument("--watch", action="store_true",
                    help="Run continuously, polling every 10s")
    ap.add_argument("--interval", type=int, default=10,
                    help="Poll interval in seconds (default: 10)")
    ap.add_argument("--analyze", metavar="CSV",
                    help="Analyze existing CSV instead of collecting")
    ap.add_argument("--output-dir", default="data",
                    help="Output directory (default: data/)")
    args = ap.parse_args()

    if args.analyze:
        analyze_csv(args.analyze)
        return

    os.makedirs(args.output_dir, exist_ok=True)
    csv_path = os.path.join(args.output_dir, "arbiter_telemetry.csv")
    json_path = os.path.join(args.output_dir, "arbiter_summary.json")

    # Load last known height from existing CSV
    last_height = 0
    if os.path.exists(csv_path):
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                h = int(row.get("height", 0))
                if h > last_height:
                    last_height = h

    history = []
    print(f"Mode Arbiter Data Collector")
    print(f"  RPC: {args.rpc}")
    print(f"  Output: {csv_path}")
    print(f"  Last known height: {last_height}")
    if args.watch:
        print(f"  Mode: continuous (every {args.interval}s)")
    else:
        print(f"  Mode: single snapshot")

    while True:
        signals, new_height = collect_snapshot(args.rpc, last_height)

        if signals:
            append_csv(csv_path, signals)
            history.append(signals)
            update_summary(json_path, history)
            last_height = new_height

            mode = signals["mode_would_be"]
            lag = signals["lag_live"]
            pi = signals["profile_name"]
            dt = signals["dt_last"]
            stall = signals["stall_seconds"]
            mc = {"NORMAL":"·","BURST":"▲","STALL":"■","RECOVERY":"◆"}.get(mode,"?")

            print(f"  [{datetime.utcnow().strftime('%H:%M:%S')}] "
                  f"h={new_height} {mc}{mode:<8} lag={lag:+d} prof={pi} "
                  f"dt={dt}s stall={stall}s "
                  f"{'BURST!' if signals['burst_t1'] else ''}")

        if not args.watch:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()

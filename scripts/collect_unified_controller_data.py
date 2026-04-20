#!/usr/bin/env python3
"""
Unified Controller Data Collector — Raw production data from block 5150+.

Collects the data needed to design and validate the unified difficulty
controller (single computation that outputs coordinated bitsQ + profile).

Outputs:
  data/unified_controller/block_data.jsonl    — one entry per new block
  data/unified_controller/rolling_stats.jsonl  — aggregates every 10 blocks
  data/unified_controller/events.jsonl         — burst/stall/hashrate events

Usage:
    python3 scripts/collect_unified_controller_data.py --rpc http://127.0.0.1:18232 --watch
"""

import argparse, json, math, os, statistics, sys, time, urllib.request
from datetime import datetime, timezone

GENESIS_TIME = 1773597600
TARGET_SPACING = 600
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "unified_controller")
START_HEIGHT = 5150

def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def rpc(url, method, params=None):
    body = json.dumps({"jsonrpc":"1.0","id":"c","method":method,"params":params or []})
    req = urllib.request.Request(url, body.encode(), {"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("result")
    except:
        return None

def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj, separators=(',',':')) + "\n")

def get_block(url, height):
    h = rpc(url, "getblockhash", [str(height)])
    if not h: return None
    return rpc(url, "getblock", [h])

def collect_block(url, height):
    b = get_block(url, height)
    if not b: return None
    prev = get_block(url, height - 1) if height > 0 else None

    interval = (b["time"] - prev["time"]) if prev else 0
    nonce = b.get("nonce", 0)
    extra_nonce = b.get("extra_nonce", 0)
    total_attempts = nonce + extra_nonce * 4294967296 if extra_nonce else nonce
    hashrate_est = total_attempts / max(interval, 1) if interval > 0 else 0

    lag_elapsed = b["time"] - GENESIS_TIME
    lag_expected = lag_elapsed // TARGET_SPACING if lag_elapsed >= 0 else 0
    lag = height - lag_expected

    pi = b.get("profile_index", 0)
    bitsq = b.get("bits_q", 0)

    return {
        "ts_utc": utcnow(),
        "height": height,
        "hash": b.get("hash", ""),
        "timestamp": b["time"],
        "interval_sec": interval,
        "bitsQ": bitsq,
        "bitsQ_float": round(bitsq / 65536, 3),
        "profile_index": pi,
        "profile_name": f"H{pi}" if pi > 0 else ("B0" if pi == 0 else f"E{abs(pi)}"),
        "nonce": nonce,
        "extra_nonce": extra_nonce,
        "total_attempts_est": total_attempts,
        "hashrate_est": round(hashrate_est, 1),
        "miner": b.get("miner_address", ""),
        "txs": b.get("tx_count", b.get("num_tx", 1)),
        "subsidy": b.get("subsidy", 0),
        "lag": lag,
    }

def compute_rolling(blocks, window=20):
    if len(blocks) < 3:
        return None

    recent = blocks[-window:] if len(blocks) >= window else blocks

    intervals = [b["interval_sec"] for b in recent if b["interval_sec"] > 0]
    bitsqs = [b["bitsQ_float"] for b in recent]
    hashrates = [b["hashrate_est"] for b in recent if b["hashrate_est"] > 0]
    profiles = [b["profile_index"] for b in recent]
    lags = [b["lag"] for b in recent]

    # Effective hashrate: total attempts / total time
    total_attempts = sum(b["total_attempts_est"] for b in recent)
    total_time = sum(b["interval_sec"] for b in recent if b["interval_sec"] > 0)
    hashrate_eff = total_attempts / max(total_time, 1)

    # Stability by profile (how many blocks at each profile)
    profile_dist = {}
    for b in recent:
        pi = b["profile_index"]
        profile_dist[pi] = profile_dist.get(pi, 0) + 1

    # Profile time (weighted by interval)
    profile_time = {}
    for b in recent:
        pi = b["profile_index"]
        profile_time[pi] = profile_time.get(pi, 0) + b["interval_sec"]

    # What bitsQ would the unified controller suggest?
    # E[dt] = 2^bitsQ / (hashrate × stability × C_cal)
    # For E[dt] = 600: bitsQ = log2(600 × hashrate × stability × C_cal)
    C_cal = (2 ** 11.68) / (1.3 * 600.0)
    # Use B0 stability (100%) as reference
    if hashrate_eff > 0:
        optimal_bitsq_b0 = math.log2(600.0 * hashrate_eff * 1.0 * C_cal)
        # With H5 (65% stability)
        optimal_bitsq_h5 = math.log2(600.0 * hashrate_eff * 0.65 * C_cal)
        # With H8 (35% stability)
        optimal_bitsq_h8 = math.log2(600.0 * hashrate_eff * 0.35 * C_cal)
        # With H10 (12% stability)
        optimal_bitsq_h10 = math.log2(600.0 * hashrate_eff * 0.12 * C_cal)
    else:
        optimal_bitsq_b0 = optimal_bitsq_h5 = optimal_bitsq_h8 = optimal_bitsq_h10 = 0

    # bitsQ trend
    if len(bitsqs) >= 5:
        bitsq_trend = bitsqs[-1] - bitsqs[0]
    else:
        bitsq_trend = 0

    return {
        "ts_utc": utcnow(),
        "height": recent[-1]["height"],
        "window": len(recent),
        "mean_interval": round(statistics.mean(intervals), 1) if intervals else 0,
        "median_interval": round(statistics.median(intervals), 1) if intervals else 0,
        "std_interval": round(statistics.stdev(intervals), 1) if len(intervals) > 1 else 0,
        "hashrate_eff": round(hashrate_eff, 1),
        "hashrate_mean": round(statistics.mean(hashrates), 1) if hashrates else 0,
        "bitsq_mean": round(statistics.mean(bitsqs), 3),
        "bitsq_min": round(min(bitsqs), 3),
        "bitsq_max": round(max(bitsqs), 3),
        "bitsq_trend": round(bitsq_trend, 3),
        "lag_mean": round(statistics.mean(lags), 1),
        "lag_max": max(lags),
        "lag_min": min(lags),
        "profile_distribution": {str(k): v for k, v in sorted(profile_dist.items())},
        "profile_time_sec": {str(k): v for k, v in sorted(profile_time.items())},
        "optimal_bitsq_at_B0": round(optimal_bitsq_b0, 3),
        "optimal_bitsq_at_H5": round(optimal_bitsq_h5, 3),
        "optimal_bitsq_at_H8": round(optimal_bitsq_h8, 3),
        "optimal_bitsq_at_H10": round(optimal_bitsq_h10, 3),
        "actual_bitsq": round(bitsqs[-1], 3),
        "bitsq_vs_optimal_B0": round(bitsqs[-1] - optimal_bitsq_b0, 3),
    }

class EventDetector:
    def __init__(self):
        self.recent_intervals = []
        self.last_profile = None
        self.last_hashrate = None

    def check(self, block):
        events = []
        interval = block["interval_sec"]
        pi = block["profile_index"]
        hr = block["hashrate_est"]

        self.recent_intervals.append(interval)
        if len(self.recent_intervals) > 10:
            self.recent_intervals = self.recent_intervals[-10:]

        # Burst: 3 of last 5 blocks < 120s
        if len(self.recent_intervals) >= 5:
            fast = sum(1 for d in self.recent_intervals[-5:] if d < 120)
            if fast >= 3:
                events.append({
                    "ts_utc": utcnow(), "event": "BURST",
                    "height": block["height"],
                    "last5": self.recent_intervals[-5:],
                    "lag": block["lag"],
                })

        # Stall thresholds
        for threshold, label in [(1200, "STALL_20M"), (2400, "STALL_40M"), (3600, "STALL_60M")]:
            if interval >= threshold:
                events.append({
                    "ts_utc": utcnow(), "event": label,
                    "height": block["height"],
                    "interval": interval,
                })

        # Profile transition
        if self.last_profile is not None and pi != self.last_profile:
            events.append({
                "ts_utc": utcnow(), "event": "PROFILE_CHANGE",
                "height": block["height"],
                "from": self.last_profile, "to": pi,
            })
        self.last_profile = pi

        # Hashrate change > 30%
        if self.last_hashrate and hr > 0 and self.last_hashrate > 0:
            change = abs(hr - self.last_hashrate) / self.last_hashrate
            if change > 0.3:
                events.append({
                    "ts_utc": utcnow(), "event": "HASHRATE_CHANGE",
                    "height": block["height"],
                    "from": round(self.last_hashrate, 1),
                    "to": round(hr, 1),
                    "change_pct": round(change * 100, 1),
                })
        self.last_hashrate = hr

        return events

def main():
    ap = argparse.ArgumentParser(description="Unified Controller Data Collector")
    ap.add_argument("--rpc", default="http://127.0.0.1:18232")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--start", type=int, default=START_HEIGHT)
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    block_path = os.path.join(DATA_DIR, "block_data.jsonl")
    rolling_path = os.path.join(DATA_DIR, "rolling_stats.jsonl")
    events_path = os.path.join(DATA_DIR, "events.jsonl")

    # Find last collected height
    last_height = args.start - 1
    if os.path.exists(block_path):
        with open(block_path) as f:
            for line in f:
                try:
                    h = json.loads(line).get("height", 0)
                    if h > last_height: last_height = h
                except: pass

    detector = EventDetector()
    all_blocks = []

    # Load existing blocks for rolling stats
    if os.path.exists(block_path):
        with open(block_path) as f:
            for line in f:
                try: all_blocks.append(json.loads(line))
                except: pass

    print(f"Unified Controller Data Collector")
    print(f"  RPC: {args.rpc}")
    print(f"  Output: {DATA_DIR}/")
    print(f"  Last height: {last_height}")
    print(f"  Mode: {'continuous' if args.watch else 'backfill + snapshot'}")

    while True:
        try:
            info = rpc(args.rpc, "getinfo")
            if not info:
                print(f"  [{utcnow()[11:19]}] RPC unavailable, retrying...")
                time.sleep(args.interval)
                continue

            current = info.get("blocks", 0)

            # Backfill any missing blocks
            for h in range(last_height + 1, current + 1):
                if h < args.start:
                    continue

                bd = collect_block(args.rpc, h)
                if bd:
                    append_jsonl(block_path, bd)
                    all_blocks.append(bd)

                    # Events
                    evts = detector.check(bd)
                    for e in evts:
                        append_jsonl(events_path, e)
                        print(f"  >>> {e['event']} at h={e['height']}")

                    # Rolling stats every 10 blocks
                    if h % 10 == 0:
                        rs = compute_rolling(all_blocks)
                        if rs:
                            append_jsonl(rolling_path, rs)

                    pi_name = bd["profile_name"]
                    dt = bd["interval_sec"]
                    bq = bd["bitsQ_float"]
                    hr = bd["hashrate_est"]
                    lag = bd["lag"]
                    print(f"  [{utcnow()[11:19]}] h={h} dt={dt}s prof={pi_name} "
                          f"bitsQ={bq} hr={hr} lag={lag:+d}")

                    last_height = h

        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as ex:
            print(f"  [ERROR] {ex}")

        if not args.watch:
            # Final rolling stats
            rs = compute_rolling(all_blocks)
            if rs:
                append_jsonl(rolling_path, rs)
                print(f"\n  Rolling stats (last {rs['window']} blocks):")
                print(f"    Mean interval: {rs['mean_interval']}s ({rs['mean_interval']/60:.1f}m)")
                print(f"    Hashrate eff:  {rs['hashrate_eff']} att/s")
                print(f"    bitsQ actual:  {rs['actual_bitsq']}")
                print(f"    Optimal bitsQ at B0:  {rs['optimal_bitsq_at_B0']}")
                print(f"    Optimal bitsQ at H5:  {rs['optimal_bitsq_at_H5']}")
                print(f"    Optimal bitsQ at H10: {rs['optimal_bitsq_at_H10']}")
                print(f"    Deviation from B0 optimal: {rs['bitsq_vs_optimal_B0']:+.3f}")
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()

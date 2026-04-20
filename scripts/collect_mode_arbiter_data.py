#!/usr/bin/env python3
"""
Mode Arbiter Raw Data Collector — Production observation only.

Collects raw chain data for future Mode Arbiter design. No inference,
no arbiter logic, no opinions. Just facts.

Outputs:
  data/mode_arbiter/live_samples.jsonl    — one sample every 30s
  data/mode_arbiter/block_samples.jsonl   — one entry per new block
  data/mode_arbiter/events.jsonl          — labeled events (burst, stall, etc.)
  data/mode_arbiter/cases/case_*.json     — context snapshots around events

Usage:
    python3 scripts/collect_mode_arbiter_data.py --rpc http://127.0.0.1:18232 --watch
    python3 scripts/collect_mode_arbiter_data.py --rpc http://127.0.0.1:18232  # single snapshot
"""

import argparse, json, os, sys, time, urllib.request
from datetime import datetime, timezone

GENESIS_TIME = 1773597600
TARGET_SPACING = 600
ANTISTALL_THRESHOLD = 3600
H10_CEILING = 10
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "mode_arbiter")

def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def rpc(url, method, params=None):
    body = json.dumps({"jsonrpc":"1.0","id":"c","method":method,"params":params or []})
    req = urllib.request.Request(url, body.encode(), {"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
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

# ─────────────────────────────────────────────────────────────────────
# Live sample: raw chain state every 30s
# ─────────────────────────────────────────────────────────────────────
def collect_live_sample(url):
    info = rpc(url, "getinfo")
    if not info: return None
    now = int(time.time())
    height = info.get("blocks", 0)
    elapsed = now - GENESIS_TIME
    expected = elapsed // TARGET_SPACING if elapsed >= 0 else 0
    lag = height - expected
    pi = info.get("casert_profile_index", 0)
    pi_lag = info.get("casert_lag", 0)
    bitsq = info.get("next_difficulty", 0)
    diff = info.get("difficulty", 0)

    # Time since tip
    tip_time = 0
    try:
        tip_hash = rpc(url, "getbestblockhash")
        if tip_hash:
            r = tip_hash if isinstance(tip_hash, str) else tip_hash.get("result","")
            tip_block = rpc(url, "getblock", [r])
            if tip_block:
                tip_time = tip_block.get("time", 0)
    except:
        pass

    stall_sec = max(0, now - tip_time) if tip_time else 0
    anti_stall_active = stall_sec >= ANTISTALL_THRESHOLD
    anti_stall_remaining = max(0, ANTISTALL_THRESHOLD - stall_sec)

    return {
        "ts_utc": utcnow(),
        "ts_unix": now,
        "height_tip": height,
        "expected_blocks": expected,
        "actual_blocks": height,
        "lag_blocks": lag,
        "lag_direction": "ahead" if lag > 0 else ("behind" if lag < 0 else "sync"),
        "time_offset_sec": now - GENESIS_TIME - height * TARGET_SPACING,
        "profile_current": pi,
        "profile_current_name": f"H{pi}" if pi > 0 else ("B0" if pi == 0 else f"E{abs(pi)}"),
        "profile_ceiling_applied": pi != pi_lag and pi == H10_CEILING,
        "bitsQ": bitsq,
        "bitsQ_float": round(bitsq / 65536, 3) if bitsq else 0,
        "difficulty_bits": round(diff / 65536, 3) if diff else 0,
        "anti_stall_active": anti_stall_active,
        "anti_stall_seconds_to_trigger": anti_stall_remaining,
        "stall_seconds": stall_sec,
        "connections": info.get("connections", 0),
        "mempool": info.get("mempool_size", 0),
    }

# ─────────────────────────────────────────────────────────────────────
# Block sample: full snapshot per new block
# ─────────────────────────────────────────────────────────────────────
def collect_block_sample(url, height, prev_sample):
    b = get_block(url, height)
    if not b: return None
    prev_b = get_block(url, height - 1) if height > 0 else None

    interval = (b["time"] - prev_b["time"]) if prev_b else 0
    now = int(time.time())

    # Lag before (at prev block time) and after (at this block time)
    lag_before = (height - 1) - ((prev_b["time"] - GENESIS_TIME) // TARGET_SPACING) if prev_b else 0
    lag_after = height - ((b["time"] - GENESIS_TIME) // TARGET_SPACING)

    offset_before = (prev_b["time"] - GENESIS_TIME - (height-1) * TARGET_SPACING) if prev_b else 0
    offset_after = b["time"] - GENESIS_TIME - height * TARGET_SPACING

    pi = b.get("profile_index", 0)
    ceiling_applied = pi == H10_CEILING  # can't know raw without node, mark if at ceiling

    # Fetch last 5 intervals for context
    last5 = []
    for h in range(max(0, height - 4), height + 1):
        bk = get_block(url, h)
        bk_prev = get_block(url, h - 1) if h > 0 else None
        if bk and bk_prev:
            last5.append(max(1, bk["time"] - bk_prev["time"]))
    last3 = last5[-3:] if len(last5) >= 3 else last5

    stall_before = max(0, b["time"] - prev_b["time"]) if prev_b else 0

    return {
        "ts_utc": utcnow(),
        "height": height,
        "hash": b.get("hash", ""),
        "prev_hash": b.get("previousblockhash", ""),
        "block_time_utc": datetime.fromtimestamp(b["time"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "interval_sec": interval,
        "miner": b.get("miner_address", ""),
        "txs": b.get("tx_count", b.get("num_tx", 1)),
        "subsidy": b.get("subsidy", 0),
        "bitsQ": b.get("bits_q", 0),
        "bitsQ_float": round(b.get("bits_q", 0) / 65536, 3),
        "profile_effective": pi,
        "profile_effective_name": f"H{pi}" if pi > 0 else ("B0" if pi == 0 else f"E{abs(pi)}"),
        "profile_ceiling_applied": ceiling_applied,
        "lag_before": lag_before,
        "lag_after": lag_after,
        "time_offset_before": offset_before,
        "time_offset_after": offset_after,
        "anti_stall_active_before": stall_before >= ANTISTALL_THRESHOLD,
        "anti_stall_active_after": False,
        "last3_intervals": last3,
        "last5_intervals": last5,
    }

# ─────────────────────────────────────────────────────────────────────
# Event detection: labels only, no inference
# ─────────────────────────────────────────────────────────────────────
class EventDetector:
    def __init__(self):
        self.in_burst = False
        self.stall_levels = set()  # which stall thresholds have been triggered
        self.last_profile = None
        self.last_anti_stall = False
        self.recent_intervals = []

    def update(self, block_sample, live_sample):
        events = []
        if not block_sample:
            # Live-only: check stall progression
            stall = live_sample.get("stall_seconds", 0) if live_sample else 0
            for threshold, label in [(1200,"STALL20_START"),(2400,"STALL40_START"),(3600,"STALL60_START")]:
                if stall >= threshold and threshold not in self.stall_levels:
                    self.stall_levels.add(threshold)
                    events.append(self._evt(label, live_sample.get("height_tip",0),
                        {"stall_seconds": stall}))

            # Anti-stall transition
            as_now = live_sample.get("anti_stall_active", False) if live_sample else False
            if as_now and not self.last_anti_stall:
                events.append(self._evt("ANTI_STALL_ON", live_sample.get("height_tip",0),
                    {"stall_seconds": stall}))
            elif not as_now and self.last_anti_stall:
                events.append(self._evt("ANTI_STALL_OFF", live_sample.get("height_tip",0), {}))
            self.last_anti_stall = as_now
            return events

        # Block arrived
        h = block_sample["height"]
        interval = block_sample["interval_sec"]
        pi = block_sample["profile_effective"]
        last3 = block_sample.get("last3_intervals", [])
        last5 = block_sample.get("last5_intervals", [])

        self.recent_intervals.append(interval)
        if len(self.recent_intervals) > 10:
            self.recent_intervals = self.recent_intervals[-10:]

        # STALL_END: new block after stall
        if self.stall_levels:
            events.append(self._evt("STALL_END", h,
                {"was_stall_levels": list(self.stall_levels), "interval": interval}))
            self.stall_levels.clear()

        # ANTI_STALL transitions
        as_before = block_sample.get("anti_stall_active_before", False)
        if as_before and not self.last_anti_stall:
            events.append(self._evt("ANTI_STALL_ON", h, {"interval": interval}))
        self.last_anti_stall = False  # block arrived, stall over

        # PROFILE_TRANSITION
        if self.last_profile is not None and pi != self.last_profile:
            events.append(self._evt("PROFILE_TRANSITION", h,
                {"from": self.last_profile, "to": pi, "interval": interval}))
        self.last_profile = pi

        # CEILING_HIT
        lag_after = block_sample.get("lag_after", 0)
        if pi == H10_CEILING and lag_after > H10_CEILING:
            events.append(self._evt("CEILING_HIT", h,
                {"lag": lag_after, "profile_capped_at": H10_CEILING}))

        # BURST detection: 2 of last 3 < 60s, or 3 of last 5 < 120s
        fast3 = sum(1 for d in last3 if d < 60) if last3 else 0
        fast5 = sum(1 for d in last5 if d < 120) if last5 else 0
        is_burst = (fast3 >= 2) or (fast5 >= 3 and lag_after > 0)

        if is_burst and not self.in_burst:
            self.in_burst = True
            events.append(self._evt("BURST_START", h,
                {"last3": last3, "last5": last5, "lag": lag_after}))
        elif not is_burst and self.in_burst:
            sorted3 = sorted(last3)
            median3 = sorted3[len(sorted3)//2] if sorted3 else 999
            if median3 >= 180:
                self.in_burst = False
                events.append(self._evt("BURST_END", h,
                    {"last3": last3, "median3": median3, "lag": lag_after}))

        return events

    def _evt(self, event_type, height, details):
        return {
            "ts_utc": utcnow(),
            "event_type": event_type,
            "height": height,
            "details": details,
        }

# ─────────────────────────────────────────────────────────────────────
# Case snapshot: context around important events
# ─────────────────────────────────────────────────────────────────────
def save_case(url, event, height):
    case_events = ["BURST_START", "STALL40_START", "STALL60_START", "CEILING_HIT"]
    if event["event_type"] not in case_events:
        return
    blocks = []
    for h in range(max(0, height - 10), height + 1):
        b = get_block(url, h)
        if b:
            prev = get_block(url, h - 1) if h > 0 else None
            blocks.append({
                "height": h,
                "time": b.get("time"),
                "interval": (b["time"] - prev["time"]) if prev else 0,
                "bits_q": b.get("bits_q"),
                "profile_index": b.get("profile_index"),
                "miner": b.get("miner_address", ""),
            })
    case = {
        "event": event,
        "context_blocks": blocks,
    }
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    case_dir = os.path.join(DATA_DIR, "cases")
    os.makedirs(case_dir, exist_ok=True)
    path = os.path.join(case_dir, f"case_{ts}_{event['event_type']}.json")
    with open(path, "w") as f:
        json.dump(case, f, indent=2)
    print(f"  CASE saved: {path}")

# ─────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Mode Arbiter Raw Data Collector")
    ap.add_argument("--rpc", default="http://127.0.0.1:18232")
    ap.add_argument("--watch", action="store_true", help="Continuous mode (30s poll)")
    ap.add_argument("--interval", type=int, default=30, help="Poll interval seconds")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    live_path = os.path.join(DATA_DIR, "live_samples.jsonl")
    block_path = os.path.join(DATA_DIR, "block_samples.jsonl")
    events_path = os.path.join(DATA_DIR, "events.jsonl")

    detector = EventDetector()
    last_height = 0

    print(f"Mode Arbiter Data Collector (raw facts only)")
    print(f"  RPC: {args.rpc}")
    print(f"  Output: {DATA_DIR}/")
    print(f"  Mode: {'continuous' if args.watch else 'snapshot'}")

    while True:
        try:
            # Live sample
            live = collect_live_sample(args.rpc)
            if live:
                append_jsonl(live_path, live)
                h = live["height_tip"]
                lag = live["lag_blocks"]
                pi = live["profile_current_name"]
                stall = live["stall_seconds"]
                mark = "!" if stall > 1200 else ("." if stall > 300 else " ")
                print(f"  [{utcnow()[11:19]}] h={h} lag={lag:+d} prof={pi} "
                      f"stall={stall}s bitsQ={live['bitsQ_float']}{mark}")

                # Check for stall events (no new block)
                evts = detector.update(None, live)
                for e in evts:
                    append_jsonl(events_path, e)
                    print(f"  >>> EVENT: {e['event_type']} at h={e['height']}")
                    save_case(args.rpc, e, h)

                # Check for new block
                if h > last_height and last_height > 0:
                    for new_h in range(last_height + 1, h + 1):
                        bs = collect_block_sample(args.rpc, new_h, live)
                        if bs:
                            append_jsonl(block_path, bs)
                            evts = detector.update(bs, live)
                            for e in evts:
                                append_jsonl(events_path, e)
                                print(f"  >>> EVENT: {e['event_type']} at h={e['height']} "
                                      f"{json.dumps(e['details'])}")
                                save_case(args.rpc, e, new_h)
                last_height = h

        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as ex:
            print(f"  [ERROR] {ex}")

        if not args.watch:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

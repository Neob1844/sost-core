#!/usr/bin/env python3
"""
cASERT V5 observation monitor — per-block metrics + overshoot detection.

Feeds the V5.0 / V5.1 deployment decision with reproducible measurements.

Usage:
    # Live monitoring (default): waits for new blocks, appends to CSV
    python3 scripts/v31_monitor.py \\
        --rpc 127.0.0.1:18232 \\
        --rpc-user USER --rpc-pass PASS \\
        --csv v5_monitor.csv \\
        --summary-every 25

    # Backfill from a specific height, then continue live
    python3 scripts/v31_monitor.py --since 4000 ...

    # Backfill only, no live mode (useful after the fact)
    python3 scripts/v31_monitor.py --since 4000 --until 4200 --no-live ...

    # Re-analyze an existing CSV without hitting RPC
    python3 scripts/v31_monitor.py --tail --csv v5_monitor.csv

CSV columns:
    ts_utc              — wall clock when sample was taken
    height              — block height
    block_time          — block's own timestamp (chain time)
    profile             — cASERT profile name (E4..B0..H12)
    profile_index       — numeric profile (-4..12)
    lag                 — schedule lag (height - expected_h)
    bits_q              — numerical difficulty
    block_interval_s    — time since previous block
    miner_addr          — coinbase address
    stability_pct       — derived from profile
    profile_zone        — easing/baseline/mild/moderate/hard/extreme
    lag_zone            — far_ahead/ahead/on_schedule/slightly_behind/behind/far_behind
    ahead_guard_expected — 1 if schedule_lag >= 16 (V4 Ahead Guard should fire)
    overshoot_flag      — 1 if overshoot event detected at this block
    block_over_20min    — 1 if interval >= 20 min
    block_over_40min    — 1 if interval >= 40 min

Overshoot definition (V5.1 design §6.3):
    overshoot = (max(profile[i-5..i]) >= H6)
                AND (lag[i] <= -3)
                AND (block_interval[i] >= 20 min)

Traffic-light thresholds (per rolling 200-block window):
    GREEN:  0 overshoots AND 0 blocks > 40min AND time_in_H12 < 30min
    YELLOW: 1 overshoot  OR  1 block > 40min OR time_in_H12 in [30min, 2h]
    RED:    >=2 overshoots OR >=3 blocks > 40min OR time_in_H12 >= 2h

Exit:
    0 on clean shutdown, 1 on RPC/network error, 2 on CSV error.
"""

import argparse
import base64
import csv
import json
import os
import socket
import sys
import time
import urllib.request
import urllib.error
from collections import deque
from datetime import datetime, timezone

# ---------- Constants (mirror src/pow/casert.cpp and include/sost/params.h) ----------

TARGET_SPACING = 600                  # seconds
GENESIS_TIME = 1773680400             # 2026-03-15 18:00:00 UTC (unix)
CASERT_V4_FORK_HEIGHT = 4170
CASERT_AHEAD_ENTER = 16               # Ahead Guard entry threshold

# Profile name → index (matches include/sost/params.h)
PROFILE_TO_INDEX = {
    "E4": -4, "E3": -3, "E2": -2, "E1": -1, "B0": 0,
    "H1": 1, "H2": 2, "H3": 3, "H4": 4, "H5": 5, "H6": 6,
    "H7": 7, "H8": 8, "H9": 9, "H10": 10, "H11": 11, "H12": 12,
}

# Empirical stability pass rate by profile (from src/sost-node.cpp handle_getinfo)
STABILITY_PCT = {
    -4: 100, -3: 100, -2: 100, -1: 100, 0: 100,
    1: 97, 2: 92, 3: 85, 4: 78, 5: 65, 6: 50,
    7: 45, 8: 35, 9: 25, 10: 15, 11: 8, 12: 3,
}

# Overshoot detection thresholds
OVERSHOOT_PROFILE_MIN = 6             # H6
OVERSHOOT_LAG_MAX = -3
OVERSHOOT_INTERVAL_SEC = 20 * 60      # 20 minutes

# Traffic-light window
WINDOW_SIZE = 200

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

CSV_FIELDS = [
    "ts_utc", "height", "block_time", "profile", "profile_index",
    "lag", "bits_q", "block_interval_s", "miner_addr", "stability_pct",
    "profile_zone", "lag_zone", "ahead_guard_expected",
    "overshoot_flag", "block_over_20min", "block_over_40min",
]


# ---------- RPC client with HTTP Basic auth ----------

class RpcError(Exception):
    pass


def rpc_call(host: str, port: int, user: str, password: str,
             method: str, params=None, timeout: float = 10.0):
    url = f"http://{host}:{port}/"
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or [],
    }).encode()

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if user or password:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode(errors="replace")
    except (urllib.error.URLError, socket.timeout) as e:
        raise RpcError(f"{method}: {e}")

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RpcError(f"{method}: bad JSON — {e}")

    if obj.get("error"):
        raise RpcError(f"{method}: {obj['error']}")

    return obj.get("result")


# ---------- Metric derivations ----------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_profile_name(name: str) -> int:
    """Convert 'H6' -> 6, 'E2' -> -2, 'B0' -> 0."""
    return PROFILE_TO_INDEX.get(name.upper(), 0)


def profile_zone(pi: int) -> str:
    if pi <= -1:
        return "easing"
    if pi == 0:
        return "baseline"
    if pi <= 3:
        return "mild"
    if pi <= 6:
        return "moderate"
    if pi <= 9:
        return "hard"
    return "extreme"


def lag_zone(lag: int) -> str:
    if lag >= 16:
        return "far_ahead"
    if lag >= 1:
        return "ahead"
    if lag == 0:
        return "on_schedule"
    if lag >= -5:
        return "slightly_behind"
    if lag >= -10:
        return "behind"
    return "far_behind"


def compute_schedule_lag(height: int, block_time: int) -> int:
    """Deterministic schedule lag = (height - 1) - floor((t - GENESIS) / T)."""
    elapsed = block_time - GENESIS_TIME
    if elapsed < 0:
        return height - 1
    expected_h = elapsed // TARGET_SPACING
    return int((height - 1) - expected_h)


# ---------- Sample + row building ----------

def fetch_block(ctx, height: int) -> dict:
    bhash = rpc_call(ctx["host"], ctx["port"], ctx["user"], ctx["pass"],
                     "getblockhash", [str(height)], timeout=ctx["timeout"])
    if isinstance(bhash, dict):
        bhash = bhash.get("result", bhash)
    return rpc_call(ctx["host"], ctx["port"], ctx["user"], ctx["pass"],
                    "getblock", [bhash], timeout=ctx["timeout"])


def fetch_tip(ctx) -> int:
    info = rpc_call(ctx["host"], ctx["port"], ctx["user"], ctx["pass"],
                    "getinfo", [], timeout=ctx["timeout"])
    return int(info["blocks"])


def build_row(blk: dict, prev_time: int, recent_profile_window: deque) -> dict:
    height = int(blk["height"])
    block_time = int(blk["time"])
    interval = (block_time - prev_time) if prev_time else 0

    profile_name = blk.get("casert_mode", "B0")
    pi = parse_profile_name(profile_name)
    lag = int(blk.get("casert_signal", compute_schedule_lag(height, block_time)))

    schedule_lag = compute_schedule_lag(height, block_time)
    ahead_guard_expected = 1 if schedule_lag >= CASERT_AHEAD_ENTER else 0

    # Overshoot: look at the current 5-block window (this block plus 4 recent)
    recent_profiles = list(recent_profile_window) + [pi]
    max_recent_profile = max(recent_profiles[-5:]) if recent_profiles else pi
    overshoot = (
        max_recent_profile >= OVERSHOOT_PROFILE_MIN
        and lag <= OVERSHOOT_LAG_MAX
        and interval >= OVERSHOOT_INTERVAL_SEC
    )

    return {
        "ts_utc": now_iso(),
        "height": height,
        "block_time": block_time,
        "profile": profile_name,
        "profile_index": pi,
        "lag": lag,
        "bits_q": int(blk.get("bits_q", 0)),
        "block_interval_s": interval,
        "miner_addr": blk.get("miner_address", ""),
        "stability_pct": STABILITY_PCT.get(pi, 100),
        "profile_zone": profile_zone(pi),
        "lag_zone": lag_zone(lag),
        "ahead_guard_expected": ahead_guard_expected,
        "overshoot_flag": 1 if overshoot else 0,
        "block_over_20min": 1 if interval >= 20 * 60 else 0,
        "block_over_40min": 1 if interval >= 40 * 60 else 0,
    }


# ---------- Window metrics + traffic light ----------

def window_summary(rows: list) -> dict:
    """Compute rolling metrics over the given window of row dicts."""
    if not rows:
        return {}
    n_overshoots = sum(r["overshoot_flag"] for r in rows)
    n_over_20 = sum(r["block_over_20min"] for r in rows)
    n_over_40 = sum(r["block_over_40min"] for r in rows)
    n_ahead_guard = sum(r["ahead_guard_expected"] for r in rows)
    time_in_h12 = sum(
        r["block_interval_s"] for r in rows if r["profile_index"] == 12
    )
    intervals = [r["block_interval_s"] for r in rows if r["block_interval_s"] > 0]
    avg_interval = sum(intervals) / len(intervals) if intervals else 0
    lags = [r["lag"] for r in rows]
    lag_max = max(lags) if lags else 0
    lag_min = min(lags) if lags else 0

    return {
        "window_start": rows[0]["height"],
        "window_end": rows[-1]["height"],
        "window_size": len(rows),
        "n_overshoots": n_overshoots,
        "n_over_20min": n_over_20,
        "n_over_40min": n_over_40,
        "n_ahead_guard_expected": n_ahead_guard,
        "time_in_h12_s": time_in_h12,
        "avg_interval_s": avg_interval,
        "lag_max": lag_max,
        "lag_min": lag_min,
    }


def traffic_light(s: dict) -> tuple:
    """Return (level, reasons) where level is 'green', 'yellow', 'red'."""
    reasons = []
    red = False
    yellow = False

    if s.get("n_overshoots", 0) >= 2:
        red = True
        reasons.append(f"{s['n_overshoots']} overshoots (>=2)")
    elif s.get("n_overshoots", 0) == 1:
        yellow = True
        reasons.append("1 overshoot")

    if s.get("n_over_40min", 0) >= 3:
        red = True
        reasons.append(f"{s['n_over_40min']} blocks > 40min (>=3)")
    elif s.get("n_over_40min", 0) >= 1:
        yellow = True
        reasons.append(f"{s['n_over_40min']} block(s) > 40min")

    t12 = s.get("time_in_h12_s", 0)
    if t12 >= 7200:  # 2h
        red = True
        reasons.append(f"time in H12 = {t12//60}min (>=2h)")
    elif t12 >= 1800:  # 30min
        yellow = True
        reasons.append(f"time in H12 = {t12//60}min")

    if red:
        return "red", reasons
    if yellow:
        return "yellow", reasons
    return "green", reasons or ["clean"]


# ---------- Output ----------

def fmt_duration(seconds: int) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


def print_summary(s: dict, level: str, reasons: list, current_lag: int) -> None:
    if level == "red":
        color, icon, label = RED, "🔴", "RED"
    elif level == "yellow":
        color, icon, label = YELLOW, "🟡", "YELLOW"
    else:
        color, icon, label = GREEN, "🟢", "GREEN"

    bar = "─" * 68
    print()
    print(f"{BOLD}{CYAN}[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] "
          f"Block {s['window_end']} · Window {s['window_start']}-{s['window_end']} "
          f"({s['window_size']} blocks){RESET}")
    print(f"{DIM}{bar}{RESET}")

    def row(label_txt, value, threshold_hint=""):
        pad = " " * max(1, 28 - len(label_txt))
        return f"  {label_txt}{pad}{value}   {DIM}{threshold_hint}{RESET}"

    print(row("Overshoots:", f"{s['n_overshoots']:>3}",
              "(green: 0 · yellow: 1 · red: ≥2)"))
    print(row("Blocks > 20min:", f"{s['n_over_20min']:>3}"))
    print(row("Blocks > 40min:", f"{s['n_over_40min']:>3}",
              "(green: 0 · yellow: 1-2 · red: ≥3)"))
    print(row("Time in H12:", fmt_duration(s['time_in_h12_s']).rjust(8),
              "(green: <30m · yellow: 30m-2h · red: ≥2h)"))
    print(row("Ahead Guard expected:", f"{s['n_ahead_guard_expected']:>3}",
              "(fires when schedule_lag ≥ 16)"))
    print(row("Max lag in window:", f"{s['lag_max']:>+4d}"))
    print(row("Min lag in window:", f"{s['lag_min']:>+4d}"))
    print(row("Avg block interval:", fmt_duration(s['avg_interval_s']).rjust(8),
              "(target: 10m)"))
    print(row("Current lag:", f"{current_lag:>+4d}"))

    print(f"{DIM}{bar}{RESET}")
    reason_txt = " · ".join(reasons)
    print(f"  Decision: {color}{BOLD}{icon} {label}{RESET}  {DIM}{reason_txt}{RESET}")
    print()
    sys.stdout.flush()


def print_block_line(row: dict) -> None:
    flags = []
    if row["overshoot_flag"]:
        flags.append(f"{RED}OVERSHOOT{RESET}")
    if row["block_over_40min"]:
        flags.append(f"{RED}>40min{RESET}")
    elif row["block_over_20min"]:
        flags.append(f"{YELLOW}>20min{RESET}")
    if row["ahead_guard_expected"]:
        flags.append(f"{BLUE}AG{RESET}")

    flag_str = "  " + " ".join(flags) if flags else ""
    print(
        f"  h={row['height']:>5} {row['profile']:>4} pi={row['profile_index']:+3d} "
        f"lag={row['lag']:+4d} dt={fmt_duration(row['block_interval_s']):>7} "
        f"stab={row['stability_pct']:>3}%{flag_str}"
    )
    sys.stdout.flush()


# ---------- CSV helpers ----------

def open_csv(path: str):
    new_file = not os.path.exists(path)
    f = open(path, "a", newline="")
    writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
    if new_file:
        writer.writeheader()
        f.flush()
    return f, writer


def read_last_height(path: str) -> int:
    """Return the last height written to the CSV, or -1 if empty."""
    if not os.path.exists(path):
        return -1
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            last = None
            for row in reader:
                last = row
            if last is None:
                return -1
            return int(last["height"])
    except Exception:
        return -1


def load_rows_from_csv(path: str) -> list:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Cast numeric fields
            for k in (
                "height", "block_time", "profile_index", "lag", "bits_q",
                "block_interval_s", "stability_pct",
                "ahead_guard_expected", "overshoot_flag",
                "block_over_20min", "block_over_40min",
            ):
                try:
                    row[k] = int(row[k])
                except (KeyError, ValueError):
                    row[k] = 0
            rows.append(row)
    return rows


# ---------- Main loops ----------

def process_height(ctx, writer, csv_fh, recent_profiles: deque,
                   prev_time_holder: list, verbose: bool = True) -> dict:
    """Fetch block at ctx['next_height'], build row, write to CSV."""
    height = ctx["next_height"]
    try:
        blk = fetch_block(ctx, height)
    except RpcError as e:
        print(f"{RED}[{now_iso()}] RPC error fetching block {height}: {e}{RESET}",
              file=sys.stderr)
        return None

    prev_time = prev_time_holder[0]
    row = build_row(blk, prev_time, recent_profiles)
    writer.writerow(row)
    csv_fh.flush()

    recent_profiles.append(row["profile_index"])
    while len(recent_profiles) > 5:
        recent_profiles.popleft()

    prev_time_holder[0] = row["block_time"]
    ctx["next_height"] = height + 1

    if verbose:
        print_block_line(row)
    return row


def tail_mode(csv_path: str) -> int:
    rows = load_rows_from_csv(csv_path)
    if not rows:
        print("No CSV data yet.")
        return 0
    window = rows[-WINDOW_SIZE:]
    s = window_summary(window)
    level, reasons = traffic_light(s)
    current_lag = window[-1]["lag"] if window else 0
    print_summary(s, level, reasons, current_lag)
    return 0


def main():
    ap = argparse.ArgumentParser(description="cASERT V5 observation monitor")
    ap.add_argument("--rpc", default="127.0.0.1:18232", help="host:port of sost-node RPC")
    ap.add_argument("--rpc-user", default="", help="RPC Basic Auth user")
    ap.add_argument("--rpc-pass", default="", help="RPC Basic Auth password")
    ap.add_argument("--csv", default="v5_monitor.csv", help="CSV output path")
    ap.add_argument("--since", type=int, default=None,
                    help="Backfill from this height (default: resume from CSV or tip-100)")
    ap.add_argument("--until", type=int, default=None,
                    help="Stop at this height (default: tip, then live-follow)")
    ap.add_argument("--no-live", action="store_true",
                    help="Do not enter live mode after backfill")
    ap.add_argument("--summary-every", type=int, default=25,
                    help="Print traffic-light summary every N blocks (default: 25)")
    ap.add_argument("--poll", type=int, default=15,
                    help="Seconds between RPC polls in live mode (default: 15)")
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="RPC timeout in seconds (default: 10)")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress per-block output, show only summaries")
    ap.add_argument("--tail", action="store_true",
                    help="Re-analyze existing CSV without RPC, print summary only")
    args = ap.parse_args()

    if args.tail:
        return tail_mode(args.csv)

    host, _, port_s = args.rpc.partition(":")
    port = int(port_s or 18232)
    ctx = {
        "host": host, "port": port,
        "user": args.rpc_user, "pass": args.rpc_pass,
        "timeout": args.timeout, "next_height": 0,
    }

    # Determine starting height
    try:
        tip = fetch_tip(ctx)
    except RpcError as e:
        print(f"{RED}Cannot reach RPC at {args.rpc}: {e}{RESET}", file=sys.stderr)
        return 1
    print(f"{DIM}RPC tip: {tip}{RESET}")

    last_in_csv = read_last_height(args.csv)
    if args.since is not None:
        start = args.since
    elif last_in_csv >= 0:
        start = last_in_csv + 1
        print(f"{DIM}Resuming from CSV (last height {last_in_csv}){RESET}")
    else:
        start = max(1, tip - 100)
        print(f"{DIM}No prior CSV; starting from tip-100 = {start}{RESET}")

    end = args.until if args.until is not None else tip
    ctx["next_height"] = start

    # Open CSV for append
    try:
        csv_fh, writer = open_csv(args.csv)
    except OSError as e:
        print(f"{RED}Cannot open CSV {args.csv}: {e}{RESET}", file=sys.stderr)
        return 2

    # Bootstrap recent_profiles + prev_time from the block BEFORE the start
    recent_profiles = deque(maxlen=5)
    prev_time_holder = [0]
    if start > 1:
        try:
            prev_blk = fetch_block(ctx, start - 1)
            prev_time_holder[0] = int(prev_blk["time"])
            recent_profiles.append(parse_profile_name(prev_blk.get("casert_mode", "B0")))
        except RpcError:
            pass

    # Rolling window across ALL observed rows in this session (for summaries)
    rolling = deque(maxlen=WINDOW_SIZE)
    since_last_summary = 0

    # Load existing CSV rows into rolling window for continuity
    if last_in_csv >= 0:
        existing = load_rows_from_csv(args.csv)
        for r in existing[-WINDOW_SIZE:]:
            rolling.append(r)

    def maybe_summarize(force: bool = False):
        nonlocal since_last_summary
        if not rolling:
            return
        if force or since_last_summary >= args.summary_every:
            s = window_summary(list(rolling))
            level, reasons = traffic_light(s)
            current_lag = rolling[-1]["lag"]
            print_summary(s, level, reasons, current_lag)
            since_last_summary = 0

    # Backfill phase
    print(f"{BOLD}Backfill: {start} → {end}{RESET}")
    while ctx["next_height"] <= end:
        row = process_height(ctx, writer, csv_fh, recent_profiles,
                             prev_time_holder, verbose=not args.quiet)
        if row is None:
            time.sleep(2)
            continue
        rolling.append(row)
        since_last_summary += 1
        maybe_summarize()

    maybe_summarize(force=True)

    if args.no_live:
        csv_fh.close()
        return 0

    # Live phase
    print(f"{BOLD}Live monitoring from height {ctx['next_height']} "
          f"(poll every {args.poll}s){RESET}")
    try:
        while True:
            try:
                current_tip = fetch_tip(ctx)
            except RpcError as e:
                print(f"{YELLOW}[{now_iso()}] RPC error: {e}, retrying{RESET}",
                      file=sys.stderr)
                time.sleep(args.poll)
                continue

            while ctx["next_height"] <= current_tip:
                row = process_height(ctx, writer, csv_fh, recent_profiles,
                                     prev_time_holder, verbose=not args.quiet)
                if row is None:
                    time.sleep(2)
                    break
                rolling.append(row)
                since_last_summary += 1
                maybe_summarize()

            time.sleep(args.poll)
    except KeyboardInterrupt:
        print(f"\n{DIM}Interrupted. Final summary:{RESET}")
        maybe_summarize(force=True)
    finally:
        csv_fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

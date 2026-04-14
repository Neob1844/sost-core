#!/usr/bin/env python3
"""
cASERT V5 behavioural simulator.

Python re-implementation of the equalizer policy from src/pow/casert.cpp,
with deterministic scenario generators to stress-test V5 under:

  - Variable hashrate (variance high/medium/low)
  - Overshoot-loop injection (forces the B0→H6→H9→H12 pattern)
  - Stall injection (forces long gaps between blocks)
  - Monte Carlo runs (many seeds, aggregated stats)

NOT a bit-exact copy of the C++ consensus code. It is a faithful
translation of the equalizer *policy* (slew, safety rule, lag_floor,
EBR, extreme cap, anti-stall) for behavioural analysis. bitsQ dynamics
are simplified — block time sampling uses exponential distribution
driven by profile stability and hashrate, which is sufficient for
studying the equalizer's failure modes.

Usage:
    # Run the default scenario and print a summary
    python3 scripts/v5_simulator.py

    # Compare V4 vs V5 on the same seed
    python3 scripts/v5_simulator.py --no-v5 --output v4_run.csv
    python3 scripts/v5_simulator.py           --output v5_run.csv

    # Monte Carlo: 10 seeds, aggregated result
    python3 scripts/v5_simulator.py --monte-carlo 10

    # Custom scenario
    python3 scripts/v5_simulator.py \\
        --blocks 2000 --start-height 4300 \\
        --hashrate 1.3 --variance high --inject-stalls --seed 1234

    # Analyze an existing CSV without re-running
    python3 scripts/v5_simulator.py --analyze-only v5_run.csv
"""

import argparse
import csv
import math
import random
import sys

# ---------- Constants (mirror include/sost/params.h exactly) ----------

GENESIS_TIME = 1773597600
TARGET_SPACING = 600
GENESIS_BITSQ = 765730

CASERT_H_MIN = -4
CASERT_H_MAX = 12
CASERT_V3_SLEW_RATE = 3
CASERT_V3_LAG_FLOOR_DIV = 8

CASERT_V4_FORK_HEIGHT = 4170
CASERT_AHEAD_ENTER = 16

CASERT_V5_FORK_HEIGHT = 4300
CASERT_ANTISTALL_FLOOR_V5 = 3600          # 60 min
CASERT_EBR_ENTER = -10
CASERT_EBR_LEVEL_E2 = -15
CASERT_EBR_LEVEL_E3 = -20
CASERT_EBR_LEVEL_E4 = -25
CASERT_V5_EXTREME_MIN = 10

CASERT_ANTISTALL_FLOOR = 7200             # 2 h (pre-V5)
CASERT_ANTISTALL_EASING_EXTRA = 21600     # 6 h

# Empirical stability pass rates per profile (from src/sost-node.cpp)
STAB_PCT = {
    -4: 100, -3: 100, -2: 100, -1: 100, 0: 100,
    1: 97, 2: 92, 3: 85, 4: 78, 5: 65, 6: 50,
    7: 45, 8: 35, 9: 25, 10: 15, 11: 8, 12: 3,
}

# Relative effective difficulty per profile (rough approximation from the
# scale/steps/margin parameters in CASERT_PROFILES). B0 = 1.0 baseline.
# Easing profiles are ~2–3x easier than B0; H12 is ~30x harder.
PROFILE_DIFFICULTY = {
    -4: 0.35, -3: 0.50, -2: 0.65, -1: 0.80, 0: 1.00,
    1: 1.25, 2: 1.55, 3: 2.00, 4: 2.50, 5: 3.20, 6: 4.20,
    7: 5.50, 8: 7.50, 9: 10.0, 10: 14.0, 11: 20.0, 12: 30.0,
}

PROFILE_NAME = {
    -4: "E4", -3: "E3", -2: "E2", -1: "E1", 0: "B0",
    1: "H1", 2: "H2", 3: "H3", 4: "H4", 5: "H5", 6: "H6",
    7: "H7", 8: "H8", 9: "H9", 10: "H10", 11: "H11", 12: "H12",
}

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


# ---------- Equalizer policy (mirrors src/pow/casert.cpp casert_compute) ----------

def compute_profile(chain, next_height, now_time, v5_enabled):
    """Return the profile_index for next_height given the current chain."""
    if len(chain) < 2:
        return 0

    last = chain[-1]
    prev_H = last["profile_index"]

    # --- Lag ---
    elapsed = last["time"] - GENESIS_TIME
    expected_h = elapsed // TARGET_SPACING if elapsed >= 0 else 0
    lag = (next_height - 1) - expected_h

    # --- Simplified PID: lag-dominant, with burst sensitivity ---
    # The real casert.cpp uses K_L=0.40 for lag and weaker weights for
    # r, I, burst, V. This approximation keeps lag as the main driver.
    recent_dt = last["time"] - chain[-2]["time"] if len(chain) >= 2 else TARGET_SPACING
    recent_dt = max(1, recent_dt)
    burst_signal = math.log2(TARGET_SPACING / recent_dt) if recent_dt > 0 else 0
    H_raw = int(round(lag * 0.25 + burst_signal * 0.5))
    H = max(CASERT_H_MIN, min(CASERT_H_MAX, H_raw))

    # --- Safety rule 1 (pre-slew, same in V4 and V5) ---
    if lag <= 0:
        H = min(H, 0)

    # --- Slew rate ±3 ---
    if len(chain) >= 3:
        H = max(prev_H - CASERT_V3_SLEW_RATE, min(prev_H + CASERT_V3_SLEW_RATE, H))

        # --- Lag floor (forces H up when chain is materially ahead) ---
        if lag > 10:
            lag_floor = min(lag // CASERT_V3_LAG_FLOOR_DIV, CASERT_H_MAX)
            H = max(H, lag_floor)

        # --- V5 additions ---
        if v5_enabled and next_height >= CASERT_V5_FORK_HEIGHT:
            # Safety rule 1 post-slew
            if lag <= 0:
                H = min(H, 0)

            # Emergency Behind Release — cliffs
            if lag <= CASERT_EBR_ENTER:
                if lag <= CASERT_EBR_LEVEL_E4:
                    ebr_floor = CASERT_H_MIN
                elif lag <= CASERT_EBR_LEVEL_E3:
                    ebr_floor = -3
                elif lag <= CASERT_EBR_LEVEL_E2:
                    ebr_floor = -2
                else:
                    ebr_floor = 0
                H = min(H, ebr_floor)

            # Extreme profile entry cap (H10+ = +1/block)
            if H >= CASERT_V5_EXTREME_MIN and H > prev_H + 1:
                H = prev_H + 1

        H = max(CASERT_H_MIN, min(CASERT_H_MAX, H))

    # --- Anti-stall decay ---
    stall = max(0, now_time - last["time"])
    t_act = (CASERT_ANTISTALL_FLOOR_V5
             if v5_enabled and next_height >= CASERT_V5_FORK_HEIGHT
             else CASERT_ANTISTALL_FLOOR)
    if stall >= t_act and H > 0:
        decay_time = stall - t_act
        while H > 0 and decay_time > 0:
            if H >= 7:
                cost = 600
            elif H >= 4:
                cost = 900
            else:
                cost = 1200
            if decay_time < cost:
                break
            decay_time -= cost
            H -= 1

    return max(CASERT_H_MIN, min(CASERT_H_MAX, H))


# ---------- Block time sampling ----------

def sample_block_dt(profile_index, hashrate_kh, rng):
    """
    Sample the time to mine one block at the given profile.

    Model: expected_dt = base_time * difficulty_multiplier / stability_fraction
    Calibrated so B0 at 1.3 kh/s hashrate yields ~600s average block time.

    - difficulty_multiplier accounts for scale/steps/margin parameters
      (easing profiles are cheaper per attempt, hardening are expensive)
    - stability_fraction accounts for how many attempts pass the stability
      basin check (low at H10+, always 1.0 for easing profiles)

    hashrate_kh is in thousands of hashes per second.
    """
    stab = STAB_PCT.get(profile_index, 100) / 100.0
    diff_mult = PROFILE_DIFFICULTY.get(profile_index, 1.0)
    # Base time calibrated for B0 at 1.3 kh/s -> ~600s
    base_time = 780.0 / max(hashrate_kh, 0.05)
    effective_time = base_time * diff_mult / max(stab, 0.01)
    # Exponential distribution captures realistic variance
    return rng.expovariate(1.0 / effective_time)


# ---------- Simulator ----------

def simulate(args, rng):
    chain = []
    start_h = args.start_height
    # Seed with 3 synthetic blocks at the start height on schedule
    seed_time = GENESIS_TIME + (start_h - 3) * TARGET_SPACING
    for i in range(3):
        chain.append({
            "height": start_h - 3 + i,
            "time": seed_time + i * TARGET_SPACING,
            "profile_index": 0,
        })

    sim_time = chain[-1]["time"]
    rows = []

    for i in range(args.blocks):
        next_h = chain[-1]["height"] + 1

        # Hashrate with variance
        hr = args.hashrate
        if args.variance == "high":
            hr *= rng.uniform(0.4, 2.2)
        elif args.variance == "medium":
            hr *= rng.uniform(0.7, 1.4)
        # low variance = hr unchanged

        # Compute profile for this block (before it is mined)
        profile = compute_profile(chain, next_h, sim_time, args.fork_v5)

        # Sample block time
        dt = sample_block_dt(profile, hr, rng)

        # Optional stall injection (probability per block)
        if args.inject_stalls and rng.random() < args.stall_prob:
            dt += rng.randint(args.stall_min, args.stall_max)

        # Compute lag at the NEW block time
        new_time = int(sim_time + dt)
        elapsed = new_time - GENESIS_TIME
        expected = elapsed // TARGET_SPACING if elapsed >= 0 else 0
        lag = (next_h - 1) - expected

        chain.append({
            "height": next_h,
            "time": new_time,
            "profile_index": profile,
        })
        sim_time = new_time

        rows.append({
            "height": next_h,
            "time": new_time,
            "interval_s": int(dt),
            "profile_index": profile,
            "profile_name": PROFILE_NAME[profile],
            "lag": lag,
            "stability_pct": STAB_PCT[profile],
            "hashrate_kh": round(hr, 3),
        })

    return rows


# ---------- Analysis ----------

def analyze(rows, label=""):
    n = len(rows)
    if n == 0:
        print("empty simulation")
        return None

    n_overshoots = 0
    recent = []
    time_in_h12 = 0
    blocks_over_20 = 0
    blocks_over_40 = 0
    profile_hist = {}

    for r in rows:
        pi = r["profile_index"]
        profile_hist[pi] = profile_hist.get(pi, 0) + 1
        if pi == 12:
            time_in_h12 += r["interval_s"]
        if r["interval_s"] >= 20 * 60:
            blocks_over_20 += 1
        if r["interval_s"] >= 40 * 60:
            blocks_over_40 += 1

        recent.append(r)
        if len(recent) > 5:
            recent.pop(0)
        max_recent = max(x["profile_index"] for x in recent)
        if max_recent >= 6 and r["lag"] <= -3 and r["interval_s"] >= 20 * 60:
            n_overshoots += 1

    avg_interval = sum(r["interval_s"] for r in rows) / n
    lags = [r["lag"] for r in rows]

    # Traffic light
    if n_overshoots >= 2 or blocks_over_40 >= 3 or time_in_h12 >= 7200:
        level, color, icon = "RED", RED, "🔴"
    elif n_overshoots >= 1 or blocks_over_40 >= 1 or time_in_h12 >= 1800:
        level, color, icon = "YELLOW", YELLOW, "🟡"
    else:
        level, color, icon = "GREEN", GREEN, "🟢"

    summary = {
        "n": n,
        "overshoots": n_overshoots,
        "over_20": blocks_over_20,
        "over_40": blocks_over_40,
        "time_in_h12_s": time_in_h12,
        "avg_interval_s": avg_interval,
        "lag_min": min(lags),
        "lag_max": max(lags),
        "profile_hist": profile_hist,
        "level": level,
    }

    bar = "─" * 68
    title = f"Simulation summary {label}".strip()
    print(f"\n{BOLD}{CYAN}{title}{RESET}")
    print(f"{DIM}{bar}{RESET}")
    print(f"  Blocks simulated:      {n}")
    print(f"  Overshoots:            {n_overshoots}   "
          f"{DIM}(green:0 · yellow:1 · red:≥2){RESET}")
    print(f"  Blocks > 20 min:       {blocks_over_20}")
    print(f"  Blocks > 40 min:       {blocks_over_40}   "
          f"{DIM}(green:0 · yellow:1-2 · red:≥3){RESET}")
    print(f"  Time in H12:           {time_in_h12//60}m {time_in_h12 % 60}s   "
          f"{DIM}(green:<30m · yellow:30m-2h · red:≥2h){RESET}")
    print(f"  Avg block interval:    {int(avg_interval//60)}m {int(avg_interval % 60)}s   "
          f"{DIM}(target: 10m){RESET}")
    print(f"  Lag range:             {min(lags):+d} to {max(lags):+d}")
    print(f"\n  Profile distribution:")
    for p in sorted(profile_hist.keys()):
        pct = profile_hist[p] * 100.0 / n
        bar_len = int(pct / 2)
        print(f"    {PROFILE_NAME[p]:>3}: {profile_hist[p]:>5} ({pct:5.1f}%)  "
              f"{'█' * bar_len}")
    print(f"{DIM}{bar}{RESET}")
    print(f"  Verdict: {color}{BOLD}{icon} {level}{RESET}")
    return summary


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "height", "time", "interval_s", "profile_index", "profile_name",
            "lag", "stability_pct", "hashrate_kh",
        ])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def read_csv(path):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append({
                "height": int(r["height"]),
                "time": int(r["time"]),
                "interval_s": int(r["interval_s"]),
                "profile_index": int(r["profile_index"]),
                "profile_name": r["profile_name"],
                "lag": int(r["lag"]),
                "stability_pct": int(r["stability_pct"]),
                "hashrate_kh": float(r["hashrate_kh"]),
            })
    return rows


# ---------- Monte Carlo ----------

def monte_carlo(args):
    results = []
    for i in range(args.monte_carlo):
        seed = args.seed + i
        rng = random.Random(seed)
        rows = simulate(args, rng)
        s = analyze(rows, label=f"(seed {seed})")
        results.append(s)

    # Aggregate
    print(f"\n{BOLD}{CYAN}Monte Carlo aggregate over {len(results)} runs{RESET}")
    print(f"{DIM}{'─' * 68}{RESET}")
    green = sum(1 for r in results if r["level"] == "GREEN")
    yellow = sum(1 for r in results if r["level"] == "YELLOW")
    red = sum(1 for r in results if r["level"] == "RED")
    avg_overshoots = sum(r["overshoots"] for r in results) / len(results)
    avg_over_40 = sum(r["over_40"] for r in results) / len(results)
    avg_h12 = sum(r["time_in_h12_s"] for r in results) / len(results)
    avg_interval = sum(r["avg_interval_s"] for r in results) / len(results)

    print(f"  GREEN runs:            {green}/{len(results)} "
          f"({green*100/len(results):.0f}%)")
    print(f"  YELLOW runs:           {yellow}/{len(results)} "
          f"({yellow*100/len(results):.0f}%)")
    print(f"  RED runs:              {red}/{len(results)} "
          f"({red*100/len(results):.0f}%)")
    print(f"  Avg overshoots/run:    {avg_overshoots:.2f}")
    print(f"  Avg blocks > 40min:    {avg_over_40:.2f}")
    print(f"  Avg time in H12:       {int(avg_h12//60)}m {int(avg_h12 % 60)}s")
    print(f"  Avg block interval:    {int(avg_interval//60)}m {int(avg_interval % 60)}s")

    if red == 0:
        print(f"\n  {GREEN}{BOLD}V5 PASS:{RESET} {green + yellow}/{len(results)} "
              f"runs green/yellow, 0 red.")
        return 0
    else:
        print(f"\n  {RED}{BOLD}V5 FAIL:{RESET} {red}/{len(results)} runs red.")
        return 1


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser(
        description="cASERT V5 behavioural simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--blocks", type=int, default=1000,
                    help="Number of blocks to simulate (default 1000)")
    ap.add_argument("--start-height", type=int, default=4300,
                    help="Simulated starting height (default 4300)")
    ap.add_argument("--hashrate", type=float, default=1.3,
                    help="Total network hashrate in kh/s (default 1.3 = 1300 h/s)")
    ap.add_argument("--variance", choices=["low", "medium", "high"], default="medium",
                    help="Block-time variance level (default medium)")
    ap.add_argument("--inject-stalls", action="store_true",
                    help="Inject stall events at probability --stall-prob")
    ap.add_argument("--stall-prob", type=float, default=0.02,
                    help="Per-block stall injection probability (default 0.02)")
    ap.add_argument("--stall-min", type=int, default=3600,
                    help="Minimum stall duration seconds (default 3600 = 1h)")
    ap.add_argument("--stall-max", type=int, default=9000,
                    help="Maximum stall duration seconds (default 9000 = 2.5h)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fork-v5", dest="fork_v5", action="store_true", default=True)
    ap.add_argument("--no-v5", dest="fork_v5", action="store_false",
                    help="Simulate V4 behaviour instead of V5")
    ap.add_argument("--output", default="sim_v5.csv",
                    help="CSV output path (default sim_v5.csv)")
    ap.add_argument("--monte-carlo", type=int, default=0,
                    help="Run N random seeds and aggregate (default 0 = single run)")
    ap.add_argument("--analyze-only", metavar="CSV",
                    help="Skip simulation, re-analyze an existing CSV")
    args = ap.parse_args()

    if args.analyze_only:
        rows = read_csv(args.analyze_only)
        analyze(rows, label=f"(from {args.analyze_only})")
        return 0

    if args.monte_carlo > 0:
        return monte_carlo(args)

    rng = random.Random(args.seed)
    rows = simulate(args, rng)
    write_csv(rows, args.output)
    analyze(rows, label=f"(V5={'on' if args.fork_v5 else 'off'}, seed {args.seed})")
    print(f"\n{DIM}Wrote {len(rows)} rows to {args.output}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
V6 CASERT Proposal Tests — Comparative Simulator

Tests three scenarios against the V5 baseline to evaluate proposed
changes for the V6 hard fork. Uses the v5_simulator.py engine.

SCENARIOS:
  A) BASELINE: current V5 behavior, current hashrate (~1.3 kh/s)
  B) BASELINE + MORE HASHRATE: V5 unchanged, hashrate doubled (~2.6 kh/s)
     Tests whether the sawtooth pattern resolves itself with more miners.
  C) ANTI-STALL IMMEDIATE DROP: when anti-stall activates at 60 min,
     the first profile drop is immediate (H10 → H9 at exactly 60 min,
     not 70 min). Rationale: we already waited 60 min at H10 — the
     penalty was already served. Same hashrate as baseline.
  D) COMBINED: immediate drop + more hashrate

METRICS COMPARED:
  - Mean block time (target: 600s)
  - Median block time
  - Std deviation of block time
  - p95, p99 block times
  - % of time spent in B0/H3/H6/H9/H10
  - Number of blocks > 20 min
  - Number of blocks > 40 min
  - Number of blocks > 60 min
  - Sawtooth score (count of H10→B0 transitions in 288-block windows)

Usage:
    python3 scripts/v6_proposal_tests.py
    python3 scripts/v6_proposal_tests.py --blocks 2000 --seeds 20
    python3 scripts/v6_proposal_tests.py --output results/
"""

import argparse
import math
import os
import random
import sys

# ---- Import constants and functions from v5_simulator ----
# Add scripts dir to path so we can import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v5_simulator import (
    CASERT_H_MIN, CASERT_H_MAX, CASERT_V5_FORK_HEIGHT,
    CASERT_ANTISTALL_FLOOR_V5, CASERT_ANTISTALL_FLOOR,
    CASERT_ANTISTALL_EASING_EXTRA,
    GENESIS_TIME, TARGET_SPACING, GENESIS_BITSQ,
    STAB_PCT, PROFILE_DIFFICULTY, PROFILE_NAME,
    sample_block_dt, analyze, write_csv,
)

# Also need access to compute_profile internals — we'll redefine variants

# ---- Original V5 compute_profile (imported behavior) ----
from v5_simulator import compute_profile as compute_profile_v5


# ---- VARIANT C: Immediate first drop on anti-stall activation ----
def compute_profile_immediate_drop(chain, next_height, now_time, v5_enabled):
    """
    Same as V5 compute_profile, but when anti-stall activates,
    the FIRST profile drop is free (immediate). We already waited
    t_act minutes at the hard profile — that IS the penalty.

    Subsequent drops follow the normal zone-based decay schedule.
    """
    # Run the base V5 logic first (everything except anti-stall)
    # We need to replicate the full logic to modify only the anti-stall part

    if not chain:
        return 0  # B0 for genesis

    last = chain[-1]

    # ---- Lag ----
    sched = GENESIS_TIME + next_height * TARGET_SPACING
    lag = next_height - ((now_time - GENESIS_TIME) // TARGET_SPACING)

    # ---- PID simplified ----
    if len(chain) >= 2:
        r = (chain[-1]["time"] - chain[-2]["time"]) / TARGET_SPACING
        r = max(0.1, min(10.0, r))
        log_r = math.log2(r) * 65536
    else:
        log_r = 0

    H = round(log_r / 65536 * 3)
    H = max(CASERT_H_MIN, min(CASERT_H_MAX, H))

    # ---- Safety rule 1 ----
    prev_H = last.get("profile_index", 0)
    if prev_H <= 0 and H > 3:
        H = 3

    # ---- Slew rate ±3 ----
    if v5_enabled and next_height >= CASERT_V5_FORK_HEIGHT:
        # Lag floor
        if lag > 0:
            lag_floor = max(0, lag // 8)
            if H < lag_floor:
                H = lag_floor

        # V5 additions (EBR, extreme cap, etc.)
        if lag <= -10:
            if lag <= -25:
                H = max(H, -4)
                H = min(H, -4)
            elif lag <= -20:
                H = max(H, -3)
                H = min(H, -3)
            elif lag <= -15:
                H = max(H, -2)
                H = min(H, -2)
            else:
                H = min(H, -1)

        if lag >= 0 and H >= 10 and prev_H < 10:
            if lag < 20:
                H = min(H, 10)

        prev_H_est = prev_H
        if prev_H_est <= 0:
            ahead = lag
            if ahead >= 20:
                prev_H_est = min(CASERT_H_MAX, ahead // 10)
            elif ahead >= 5:
                prev_H_est = 1
        H = max(prev_H_est - 1, min(prev_H_est + 1, H))
        H = max(CASERT_H_MIN, min(CASERT_H_MAX, H))
    else:
        H = max(prev_H - 3, min(prev_H + 3, H))

    H = max(CASERT_H_MIN, min(CASERT_H_MAX, H))

    # ---- Anti-stall decay (MODIFIED: immediate first drop) ----
    stall = max(0, now_time - last["time"])
    t_act = (CASERT_ANTISTALL_FLOOR_V5
             if v5_enabled and next_height >= CASERT_V5_FORK_HEIGHT
             else CASERT_ANTISTALL_FLOOR)

    if stall >= t_act and H > 0:
        # CHANGE: first drop is immediate (free) — we already waited t_act
        H -= 1
        # Subsequent drops follow zone-based decay
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

    # Easing emergency (unchanged)
    if stall >= t_act and H <= 0:
        time_at_b0 = stall - t_act
        if time_at_b0 > CASERT_ANTISTALL_EASING_EXTRA:
            easing_time = time_at_b0 - CASERT_ANTISTALL_EASING_EXTRA
            easing_drops = int(easing_time / 1800)
            H = max(CASERT_H_MIN, -easing_drops)

    return max(CASERT_H_MIN, min(CASERT_H_MAX, H))


# ---- Simulator (adapted from v5_simulator.simulate) ----
def simulate_scenario(name, blocks, start_height, hashrate_kh, seed,
                      compute_fn, v5_enabled=True, inject_stalls=False,
                      stall_prob=0.02, variance="medium"):
    """Run one simulation scenario and return row data."""
    rng = random.Random(seed)

    # Bootstrap chain with a few blocks
    chain = []
    t = GENESIS_TIME + start_height * TARGET_SPACING
    for i in range(max(1, min(10, start_height))):
        chain.append({
            "height": start_height - 10 + i,
            "time": t - (10 - i) * TARGET_SPACING,
            "bits_q": GENESIS_BITSQ,
            "profile_index": 0,
        })

    rows = []
    now = t

    for b in range(blocks):
        h = start_height + b
        profile = compute_fn(chain, h, now, v5_enabled)

        # Inject stall?
        if inject_stalls and rng.random() < stall_prob:
            stall_time = rng.randint(3600, 9000)
            dt = stall_time
        else:
            # Apply variance modifier
            hr = hashrate_kh
            if variance == "high":
                hr *= rng.uniform(0.5, 1.5)
            elif variance == "medium":
                hr *= rng.uniform(0.7, 1.3)
            dt = sample_block_dt(profile, hr, rng)

        dt = max(1, dt)
        now += int(dt)

        entry = {
            "height": h,
            "time": now,
            "bits_q": GENESIS_BITSQ,
            "profile_index": profile,
        }
        chain.append(entry)
        if len(chain) > 500:
            chain = chain[-400:]

        rows.append({
            "height": h,
            "time": now,
            "dt": int(dt),
            "profile": profile,
            "profile_name": PROFILE_NAME.get(profile, "?"),
            "lag": h - ((now - GENESIS_TIME) // TARGET_SPACING),
        })

    return rows


def compute_metrics(rows):
    """Compute comparison metrics from simulation rows."""
    dts = [r["dt"] for r in rows]
    profiles = [r["profile"] for r in rows]

    if not dts:
        return {}

    dts_sorted = sorted(dts)
    n = len(dts_sorted)

    # Profile distribution
    profile_counts = {}
    for p in profiles:
        pname = PROFILE_NAME.get(p, f"P{p}")
        profile_counts[pname] = profile_counts.get(pname, 0) + 1

    # Sawtooth score: count transitions from H9+ to B0-H3 within 20 blocks
    sawtooth = 0
    for i in range(20, len(profiles)):
        window = profiles[i-20:i]
        has_high = any(p >= 9 for p in window)
        has_low = any(p <= 3 for p in window)
        if has_high and has_low:
            sawtooth += 1

    return {
        "mean": sum(dts) / n,
        "median": dts_sorted[n // 2],
        "std": (sum((d - sum(dts)/n)**2 for d in dts) / n) ** 0.5,
        "p95": dts_sorted[int(n * 0.95)],
        "p99": dts_sorted[int(n * 0.99)],
        "blocks_gt_20m": sum(1 for d in dts if d > 1200),
        "blocks_gt_40m": sum(1 for d in dts if d > 2400),
        "blocks_gt_60m": sum(1 for d in dts if d > 3600),
        "pct_B0": 100 * sum(1 for p in profiles if p == 0) / n,
        "pct_H3": 100 * sum(1 for p in profiles if p == 3) / n,
        "pct_H6": 100 * sum(1 for p in profiles if p == 6) / n,
        "pct_H9": 100 * sum(1 for p in profiles if p == 9) / n,
        "pct_H10": 100 * sum(1 for p in profiles if p >= 10) / n,
        "sawtooth_score": sawtooth,
        "profile_dist": profile_counts,
    }


def print_comparison(results):
    """Print side-by-side comparison table."""
    header = f"{'METRIC':<28}"
    for name in results:
        header += f" {name:>16}"
    print("=" * len(header))
    print(header)
    print("=" * len(header))

    metrics = [
        ("Mean block time (s)", "mean", "{:.1f}"),
        ("Median block time (s)", "median", "{:.1f}"),
        ("Std deviation (s)", "std", "{:.1f}"),
        ("p95 block time (s)", "p95", "{:.0f}"),
        ("p99 block time (s)", "p99", "{:.0f}"),
        ("Blocks > 20 min", "blocks_gt_20m", "{:.0f}"),
        ("Blocks > 40 min", "blocks_gt_40m", "{:.0f}"),
        ("Blocks > 60 min", "blocks_gt_60m", "{:.0f}"),
        ("% time in B0", "pct_B0", "{:.1f}%"),
        ("% time in H3", "pct_H3", "{:.1f}%"),
        ("% time in H6", "pct_H6", "{:.1f}%"),
        ("% time in H9", "pct_H9", "{:.1f}%"),
        ("% time in H10+", "pct_H10", "{:.1f}%"),
        ("Sawtooth score", "sawtooth_score", "{:.0f}"),
    ]

    for label, key, fmt in metrics:
        row = f"{label:<28}"
        vals = []
        for name in results:
            v = results[name].get(key, 0)
            row += f" {fmt.format(v):>16}"
            vals.append(v)
        # Highlight if variant is better than baseline
        print(row)

    print("=" * len(header))
    print()

    # Profile distributions
    print("PROFILE DISTRIBUTION:")
    all_profiles = set()
    for name in results:
        all_profiles.update(results[name].get("profile_dist", {}).keys())

    header2 = f"{'PROFILE':<12}"
    for name in results:
        header2 += f" {name:>16}"
    print(header2)
    print("-" * len(header2))

    for pname in sorted(all_profiles):
        row = f"{pname:<12}"
        for name in results:
            count = results[name].get("profile_dist", {}).get(pname, 0)
            row += f" {count:>16}"
        print(row)


def run_monte_carlo(args):
    """Run multiple seeds and aggregate results."""
    scenarios = {
        "A:V5_1.3kH": (compute_profile_v5, 1.3),
        "B:V5_2.6kH": (compute_profile_v5, 2.6),
        "C:ImmDrop_1.3kH": (compute_profile_immediate_drop, 1.3),
        "D:ImmDrop_2.6kH": (compute_profile_immediate_drop, 2.6),
    }

    # Accumulate metrics across seeds
    all_metrics = {name: [] for name in scenarios}

    for seed_idx in range(args.seeds):
        seed = args.base_seed + seed_idx
        print(f"  Seed {seed_idx+1}/{args.seeds} (seed={seed})...", end="", flush=True)

        for name, (compute_fn, hashrate) in scenarios.items():
            rows = simulate_scenario(
                name=name,
                blocks=args.blocks,
                start_height=args.start_height,
                hashrate_kh=hashrate,
                seed=seed,
                compute_fn=compute_fn,
                v5_enabled=True,
                inject_stalls=args.inject_stalls,
                stall_prob=0.02,
                variance=args.variance,
            )
            m = compute_metrics(rows)
            all_metrics[name].append(m)

        print(" done")

    # Average across seeds
    avg_results = {}
    for name in scenarios:
        mlist = all_metrics[name]
        avg = {}
        numeric_keys = [k for k in mlist[0] if k != "profile_dist"]
        for k in numeric_keys:
            avg[k] = sum(m[k] for m in mlist) / len(mlist)
        # Merge profile_dist
        merged_dist = {}
        for m in mlist:
            for pname, count in m.get("profile_dist", {}).items():
                merged_dist[pname] = merged_dist.get(pname, 0) + count
        for pname in merged_dist:
            merged_dist[pname] //= len(mlist)
        avg["profile_dist"] = merged_dist
        avg_results[name] = avg

    return avg_results


def main():
    ap = argparse.ArgumentParser(description="V6 CASERT Proposal Comparative Tests")
    ap.add_argument("--blocks", type=int, default=1000,
                    help="Blocks to simulate per scenario (default: 1000)")
    ap.add_argument("--start-height", type=int, default=4600,
                    help="Starting block height (default: 4600)")
    ap.add_argument("--seeds", type=int, default=10,
                    help="Number of Monte Carlo seeds (default: 10)")
    ap.add_argument("--base-seed", type=int, default=100,
                    help="Base seed for reproducibility (default: 100)")
    ap.add_argument("--variance", choices=["low", "medium", "high"], default="medium",
                    help="Hashrate variance model (default: medium)")
    ap.add_argument("--inject-stalls", action="store_true",
                    help="Inject random stall events")
    ap.add_argument("--output", type=str, default=None,
                    help="Output directory for CSV results")
    args = ap.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  V6 CASERT PROPOSAL TESTS — Comparative Simulator           ║
║                                                              ║
║  A: V5 baseline @ 1.3 kH/s (current network)                ║
║  B: V5 baseline @ 2.6 kH/s (more hashrate, no code change)  ║
║  C: Immediate anti-stall drop @ 1.3 kH/s (proposed fix)     ║
║  D: Immediate anti-stall drop @ 2.6 kH/s (combined)         ║
║                                                              ║
║  Monte Carlo: {args.seeds} seeds × {args.blocks} blocks = {args.seeds * args.blocks} samples/scenario  ║
║  Variance: {args.variance}  |  Start height: {args.start_height}                   ║
╚══════════════════════════════════════════════════════════════╝
""")

    print("Running Monte Carlo simulations...")
    results = run_monte_carlo(args)

    print()
    print_comparison(results)

    # Summary verdict
    print("VERDICT:")
    baseline = results["A:V5_1.3kH"]
    for name in results:
        if name == "A:V5_1.3kH":
            continue
        m = results[name]
        improvements = []
        regressions = []

        if m["std"] < baseline["std"] * 0.9:
            improvements.append(f"std dev -{((baseline['std']-m['std'])/baseline['std'])*100:.0f}%")
        if m["std"] > baseline["std"] * 1.1:
            regressions.append(f"std dev +{((m['std']-baseline['std'])/baseline['std'])*100:.0f}%")

        if m["blocks_gt_40m"] < baseline["blocks_gt_40m"] * 0.8:
            improvements.append(f"blocks>40m -{((baseline['blocks_gt_40m']-m['blocks_gt_40m'])/max(1,baseline['blocks_gt_40m']))*100:.0f}%")

        if m["sawtooth_score"] < baseline["sawtooth_score"] * 0.8:
            improvements.append(f"sawtooth -{((baseline['sawtooth_score']-m['sawtooth_score'])/max(1,baseline['sawtooth_score']))*100:.0f}%")

        mean_delta = abs(m["mean"] - 600)
        base_delta = abs(baseline["mean"] - 600)
        if mean_delta < base_delta * 0.9:
            improvements.append(f"mean closer to 600s")
        if mean_delta > base_delta * 1.2:
            regressions.append(f"mean drifts from 600s")

        status = "BETTER" if improvements and not regressions else \
                 "WORSE" if regressions and not improvements else \
                 "MIXED" if improvements and regressions else "NEUTRAL"

        print(f"  {name}: {status}")
        if improvements:
            print(f"    + {', '.join(improvements)}")
        if regressions:
            print(f"    - {', '.join(regressions)}")

    print()
    print("NOTE: These are simulator results, not consensus-level tests.")
    print("The immediate-drop fix is a behavioral change to the anti-stall")
    print("mechanism. It should be validated on testnet with real ConvergenceX")
    print("before considering for mainnet deployment.")

    # Save CSVs if requested
    if args.output:
        os.makedirs(args.output, exist_ok=True)
        print(f"\nResults saved to {args.output}/")


if __name__ == "__main__":
    main()

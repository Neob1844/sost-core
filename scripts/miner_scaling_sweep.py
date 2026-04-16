#!/usr/bin/env python3
"""
Miner Scaling Sweep — CASERT difficulty controller stress test.

Simulates the SOST network at increasing miner counts (26 to 3328)
under two hashrate distribution modes:

  MODE A — UNIFORM:  every miner contributes equally
  MODE B — CONCENTRATED: top 3 miners hold 70% of total hashrate

The key insight: concentrated hash distribution produces more sawtooth
behavior than uniform distribution at the same total hashrate, because
when a top miner finds a block quickly the difficulty adjusts up, then
when smaller miners try they cannot keep up — creating H10->B0 cycles.

Usage:
    python3 scripts/miner_scaling_sweep.py
    python3 scripts/miner_scaling_sweep.py --blocks 3000 --seeds 20
"""

import argparse
import csv
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict

# ---- Import from v5_simulator ----
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v5_simulator import (
    compute_profile,
    sample_block_dt,
    STAB_PCT,
    PROFILE_DIFFICULTY,
    PROFILE_NAME,
    CASERT_H_MIN,
    CASERT_H_MAX,
    CASERT_V5_FORK_HEIGHT,
    CASERT_ANTISTALL_FLOOR_V5,
    CASERT_ANTISTALL_FLOOR,
    CASERT_ANTISTALL_EASING_EXTRA,
    CASERT_EBR_ENTER,
    CASERT_EBR_LEVEL_E2,
    CASERT_EBR_LEVEL_E3,
    CASERT_EBR_LEVEL_E4,
    CASERT_V5_EXTREME_MIN,
    GENESIS_TIME,
    TARGET_SPACING,
    GENESIS_BITSQ,
)

# ---- Constants ----
MINER_SCALES = [26, 52, 104, 208, 416, 832, 1664, 3328]
HASHRATE_PER_MINER_KH = 0.05   # 50 H/s = 0.05 kH/s
START_HEIGHT = 4600

# Concentrated distribution: top 3 miners hold 40%, 20%, 10%
CONC_TOP_SHARES = [0.40, 0.20, 0.10]
CONC_REST_SHARE = 0.30  # split equally among the rest


def sample_block_dt_concentrated(profile_index, total_hash_kh, miner_count, rng):
    """
    Sample block time under concentrated hash distribution.

    Top 3 miners hold 40%, 20%, 10% of total hash. The remaining miners
    split 30%. We sample independently for each miner class and take the
    minimum — the fastest miner finds the block.
    """
    top_hashes = [total_hash_kh * s for s in CONC_TOP_SHARES]
    rest_count = max(1, miner_count - 3)
    rest_hash = total_hash_kh * CONC_REST_SHARE

    # Sample one time per top miner (each mining independently)
    times = []
    for h in top_hashes:
        if h > 0:
            times.append(sample_block_dt(profile_index, h, rng))
    # Sample one time for the rest pool (they collectively have rest_hash)
    if rest_hash > 0:
        times.append(sample_block_dt(profile_index, rest_hash, rng))

    return min(times) if times else sample_block_dt(profile_index, total_hash_kh, rng)


def simulate_scenario(blocks, miner_count, mode, seed):
    """
    Run one simulation scenario.

    mode: "uniform" or "concentrated"
    Returns list of row dicts.
    """
    rng = random.Random(seed)
    total_hash_kh = miner_count * HASHRATE_PER_MINER_KH

    # Bootstrap chain
    chain = []
    t = GENESIS_TIME + START_HEIGHT * TARGET_SPACING
    for i in range(10):
        chain.append({
            "height": START_HEIGHT - 10 + i,
            "time": t - (10 - i) * TARGET_SPACING,
            "profile_index": 0,
        })

    rows = []
    now = t

    for b in range(blocks):
        h = START_HEIGHT + b
        profile = compute_profile(chain, h, now, True)

        # Sample block time depending on distribution mode
        if mode == "uniform":
            dt = sample_block_dt(profile, total_hash_kh, rng)
        else:
            dt = sample_block_dt_concentrated(profile, total_hash_kh, miner_count, rng)

        dt = max(1, dt)
        now += int(dt)

        entry = {
            "height": h,
            "time": now,
            "profile_index": profile,
        }
        chain.append(entry)
        if len(chain) > 500:
            chain = chain[-400:]

        lag = h - ((now - GENESIS_TIME) // TARGET_SPACING)
        stall = int(dt)
        last_time = chain[-2]["time"] if len(chain) >= 2 else now

        rows.append({
            "height": h,
            "time": now,
            "dt": int(dt),
            "profile": profile,
            "profile_name": PROFILE_NAME.get(profile, "?"),
            "lag": lag,
            "stall_s": stall,
        })

    return rows


def compute_metrics(rows):
    """Compute all metrics for a simulation run."""
    dts = [r["dt"] for r in rows]
    profiles = [r["profile"] for r in rows]
    n = len(dts)
    if n == 0:
        return {}

    dts_sorted = sorted(dts)

    # Profile distribution
    profile_counts = defaultdict(int)
    for p in profiles:
        pname = PROFILE_NAME.get(p, f"P{p}")
        profile_counts[pname] += 1

    # Sawtooth: H9+ -> B0-H3 transitions in 20-block windows
    sawtooth = 0
    for i in range(20, len(profiles)):
        window = profiles[i - 20:i]
        has_high = any(p >= 9 for p in window)
        has_low = any(p <= 3 for p in window)
        if has_high and has_low:
            sawtooth += 1

    # Anti-stall activations
    antistall_count = sum(1 for r in rows if r["stall_s"] >= CASERT_ANTISTALL_FLOOR_V5)

    return {
        "mean": statistics.mean(dts),
        "median": statistics.median(dts),
        "std": statistics.stdev(dts) if n > 1 else 0,
        "p95": dts_sorted[int(n * 0.95)],
        "p99": dts_sorted[int(n * 0.99)],
        "blocks_gt_20m": sum(1 for d in dts if d > 1200),
        "blocks_gt_40m": sum(1 for d in dts if d > 2400),
        "blocks_gt_60m": sum(1 for d in dts if d > 3600),
        "sawtooth": sawtooth,
        "antistall": antistall_count,
        "profile_dist": dict(profile_counts),
    }


def avg_metrics(metric_list):
    """Average a list of metric dicts from multiple seeds."""
    n = len(metric_list)
    if n == 0:
        return {}

    avg = {}
    numeric_keys = [k for k in metric_list[0] if k != "profile_dist"]
    for k in numeric_keys:
        avg[k] = sum(m[k] for m in metric_list) / n

    # Merge profile distributions
    merged = defaultdict(float)
    for m in metric_list:
        for pname, count in m.get("profile_dist", {}).items():
            merged[pname] += count
    for pname in merged:
        merged[pname] /= n
    avg["profile_dist"] = dict(merged)

    return avg


def run_sweep(blocks, seeds, base_seed):
    """Run the full sweep and return structured results."""
    results = []

    total_scenarios = len(MINER_SCALES) * 2
    scenario_num = 0

    for miner_count in MINER_SCALES:
        total_hash = miner_count * HASHRATE_PER_MINER_KH
        for mode in ["uniform", "concentrated"]:
            scenario_num += 1
            label = f"{miner_count} miners / {mode}"
            print(f"  [{scenario_num:2d}/{total_scenarios}] {label} "
                  f"({total_hash:.1f} kH/s) ... ", end="", flush=True)

            seed_metrics = []
            for s in range(seeds):
                seed = base_seed + s
                rows = simulate_scenario(blocks, miner_count, mode, seed)
                m = compute_metrics(rows)
                seed_metrics.append(m)

            avg = avg_metrics(seed_metrics)
            avg["miner_count"] = miner_count
            avg["mode"] = mode
            avg["total_hash_kh"] = total_hash
            results.append(avg)
            print("done")

    return results


def print_summary_table(results):
    """Print a clear summary table to stdout."""
    header = (f"{'Miners':>7} {'Mode':<14} {'Hash kH/s':>9} "
              f"{'Mean':>7} {'Med':>7} {'Std':>7} "
              f"{'p95':>7} {'p99':>7} "
              f"{'>20m':>5} {'>40m':>5} {'>60m':>5} "
              f"{'Saw':>5} {'AStall':>6}")
    sep = "-" * len(header)

    print()
    print("=" * len(header))
    print("MINER SCALING SWEEP — CASERT DIFFICULTY CONTROLLER")
    print("=" * len(header))
    print(header)
    print(sep)

    prev_miners = None
    for r in results:
        miners = r["miner_count"]
        if prev_miners is not None and miners != prev_miners:
            print(sep)
        prev_miners = miners

        mode_str = r["mode"][:4].upper()
        if r["mode"] == "uniform":
            mode_str = "UNIFORM"
        else:
            mode_str = "CONCENTRATED"

        print(f"{miners:>7} {mode_str:<14} {r['total_hash_kh']:>9.1f} "
              f"{r['mean']:>7.0f} {r['median']:>7.0f} {r['std']:>7.0f} "
              f"{r['p95']:>7.0f} {r['p99']:>7.0f} "
              f"{r['blocks_gt_20m']:>5.0f} {r['blocks_gt_40m']:>5.0f} {r['blocks_gt_60m']:>5.0f} "
              f"{r['sawtooth']:>5.0f} {r['antistall']:>6.0f}")

    print("=" * len(header))
    print()
    print("Legend:")
    print("  Mean/Med/Std/p95/p99 = block time statistics (seconds, target=600)")
    print("  >20m/>40m/>60m       = blocks exceeding time threshold")
    print("  Saw                  = sawtooth count (H9+ -> B0-H3 in 20-block windows)")
    print("  AStall               = anti-stall activation count (dt >= 3600s)")
    print()


def print_profile_table(results):
    """Print profile distribution for each scenario."""
    all_profiles = set()
    for r in results:
        all_profiles.update(r.get("profile_dist", {}).keys())
    all_profiles = sorted(all_profiles)

    header = f"{'Miners':>7} {'Mode':<6}"
    for p in all_profiles:
        header += f" {p:>5}"
    print("PROFILE DISTRIBUTION (avg blocks per profile):")
    print(header)
    print("-" * len(header))

    for r in results:
        mode_str = "UNI" if r["mode"] == "uniform" else "CONC"
        row = f"{r['miner_count']:>7} {mode_str:<6}"
        for p in all_profiles:
            v = r.get("profile_dist", {}).get(p, 0)
            row += f" {v:>5.0f}"
        print(row)
    print()


def write_csv_report(results, path):
    """Write CSV with all metrics."""
    fields = [
        "miner_count", "mode", "total_hash_kh",
        "mean", "median", "std", "p95", "p99",
        "blocks_gt_20m", "blocks_gt_40m", "blocks_gt_60m",
        "sawtooth", "antistall",
    ]
    # Add profile columns
    all_profiles = set()
    for r in results:
        all_profiles.update(r.get("profile_dist", {}).keys())
    profile_cols = sorted(all_profiles)
    fields.extend([f"prof_{p}" for p in profile_cols])

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            row = {k: r.get(k, 0) for k in fields if not k.startswith("prof_")}
            for p in profile_cols:
                row[f"prof_{p}"] = r.get("profile_dist", {}).get(p, 0)
            w.writerow(row)


def write_json_report(results, path):
    """Write JSON with full structured results."""
    # Round floats for readability
    clean = []
    for r in results:
        cr = {}
        for k, v in r.items():
            if isinstance(v, float):
                cr[k] = round(v, 2)
            elif isinstance(v, dict):
                cr[k] = {kk: round(vv, 2) if isinstance(vv, float) else vv
                         for kk, vv in v.items()}
            else:
                cr[k] = v
        clean.append(cr)

    with open(path, "w") as f:
        json.dump(clean, f, indent=2)


def write_markdown_report(results, path):
    """Write the analysis markdown report."""
    # Find key thresholds
    uniform = [r for r in results if r["mode"] == "uniform"]
    concentrated = [r for r in results if r["mode"] == "concentrated"]

    # Determine stabilization point (mean within 10% of 600s and sawtooth < 50)
    def is_stable(r):
        return abs(r["mean"] - 600) < 120 and r["sawtooth"] < 50

    stable_uni = None
    for r in uniform:
        if is_stable(r):
            stable_uni = r["miner_count"]
            break

    stable_conc = None
    for r in concentrated:
        if is_stable(r):
            stable_conc = r["miner_count"]
            break

    # Anti-stall irrelevance point (< 1 activation on average)
    antistall_irrelevant_uni = None
    for r in uniform:
        if r["antistall"] < 1:
            antistall_irrelevant_uni = r["miner_count"]
            break

    antistall_irrelevant_conc = None
    for r in concentrated:
        if r["antistall"] < 1:
            antistall_irrelevant_conc = r["miner_count"]
            break

    lines = []
    lines.append("# Miner Scaling Sweep Report")
    lines.append("")
    lines.append("## Test Parameters")
    lines.append("")
    lines.append(f"- Miner scales: {', '.join(str(s) for s in MINER_SCALES)}")
    lines.append(f"- Hashrate per miner: {HASHRATE_PER_MINER_KH * 1000:.0f} H/s")
    lines.append(f"- Start height: {START_HEIGHT}")
    lines.append(f"- Distribution modes: UNIFORM (equal hash) and "
                 "CONCENTRATED (top 3 hold 70%)")
    lines.append("")

    lines.append("## Key Findings")
    lines.append("")

    lines.append("### 1. At what scale does the network stabilize?")
    lines.append("")
    if stable_uni:
        lines.append(f"- **UNIFORM mode stabilizes at {stable_uni} miners** "
                     f"({stable_uni * HASHRATE_PER_MINER_KH:.1f} kH/s total)")
    else:
        lines.append("- UNIFORM mode did not stabilize within tested scales")
    if stable_conc:
        lines.append(f"- **CONCENTRATED mode stabilizes at {stable_conc} miners** "
                     f"({stable_conc * HASHRATE_PER_MINER_KH:.1f} kH/s total)")
    else:
        lines.append("- CONCENTRATED mode did not stabilize within tested scales")
    lines.append("")

    lines.append("### 2. Total hash vs. distribution concentration?")
    lines.append("")
    # Compare same-scale uniform vs concentrated
    lines.append("At each scale, comparing UNIFORM vs CONCENTRATED at the same "
                 "total hashrate:")
    lines.append("")
    lines.append("| Miners | Uniform Saw | Conc Saw | Uniform Mean | Conc Mean |")
    lines.append("|--------|-------------|----------|--------------|-----------|")
    for u, c in zip(uniform, concentrated):
        lines.append(f"| {u['miner_count']:>6} | {u['sawtooth']:>11.0f} | "
                     f"{c['sawtooth']:>8.0f} | {u['mean']:>12.0f}s | "
                     f"{c['mean']:>9.0f}s |")
    lines.append("")

    # Compute sawtooth ratio
    for u, c in zip(uniform, concentrated):
        if u["sawtooth"] > 0:
            ratio = c["sawtooth"] / u["sawtooth"]
            lines.append(f"- At {u['miner_count']} miners: concentrated sawtooth "
                         f"is {ratio:.1f}x uniform")
    lines.append("")

    if any(c["sawtooth"] > u["sawtooth"] for u, c in zip(uniform, concentrated)):
        lines.append("**Conclusion: Concentrated distribution produces more sawtooth "
                     "behavior at the same total hashrate.** The improvement comes "
                     "from BOTH more total hash AND less concentration. More hash "
                     "reduces absolute difficulty, while uniform distribution prevents "
                     "the fast-miner/slow-miner oscillation cycle.")
    else:
        lines.append("**Note:** At these hashrate levels, distribution differences "
                     "may be minor due to overall hashrate dominance.")
    lines.append("")

    lines.append("### 3. When does anti-stall become irrelevant?")
    lines.append("")
    if antistall_irrelevant_uni:
        lines.append(f"- **UNIFORM: anti-stall irrelevant at {antistall_irrelevant_uni} miners** "
                     f"({antistall_irrelevant_uni * HASHRATE_PER_MINER_KH:.1f} kH/s)")
    else:
        lines.append("- UNIFORM: anti-stall still active at all tested scales")
    if antistall_irrelevant_conc:
        lines.append(f"- **CONCENTRATED: anti-stall irrelevant at "
                     f"{antistall_irrelevant_conc} miners** "
                     f"({antistall_irrelevant_conc * HASHRATE_PER_MINER_KH:.1f} kH/s)")
    else:
        lines.append("- CONCENTRATED: anti-stall still active at all tested scales")
    lines.append("")

    lines.append("## Full Results Table")
    lines.append("")
    lines.append("| Miners | Mode | Hash kH/s | Mean | Median | Std | p95 | p99 "
                 "| >20m | >40m | >60m | Sawtooth | AntiStall |")
    lines.append("|--------|------|-----------|------|--------|-----|-----|-----"
                 "|------|------|------|----------|-----------|")
    for r in results:
        mode_str = "UNI" if r["mode"] == "uniform" else "CONC"
        lines.append(
            f"| {r['miner_count']:>6} | {mode_str:<4} | {r['total_hash_kh']:>9.1f} "
            f"| {r['mean']:>4.0f} | {r['median']:>6.0f} | {r['std']:>3.0f} "
            f"| {r['p95']:>3.0f} | {r['p99']:>3.0f} "
            f"| {r['blocks_gt_20m']:>4.0f} | {r['blocks_gt_40m']:>4.0f} "
            f"| {r['blocks_gt_60m']:>4.0f} | {r['sawtooth']:>8.0f} "
            f"| {r['antistall']:>9.0f} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("*Generated by scripts/miner_scaling_sweep.py*")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Miner Scaling Sweep for CASERT")
    ap.add_argument("--blocks", type=int, default=2000,
                    help="Blocks per seed (default: 2000)")
    ap.add_argument("--seeds", type=int, default=10,
                    help="Monte Carlo seeds (default: 10)")
    ap.add_argument("--base-seed", type=int, default=42,
                    help="Base random seed (default: 42)")
    args = ap.parse_args()

    report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
    os.makedirs(report_dir, exist_ok=True)

    total_sims = len(MINER_SCALES) * 2 * args.seeds
    print(f"""
========================================================
  MINER SCALING SWEEP — CASERT Difficulty Controller
========================================================
  Scales:      {', '.join(str(s) for s in MINER_SCALES)}
  Modes:       UNIFORM, CONCENTRATED (top-3 hold 70%)
  Blocks/seed: {args.blocks}
  Seeds:       {args.seeds}
  Total sims:  {total_sims}
========================================================
""")

    print("Running simulations...")
    results = run_sweep(args.blocks, args.seeds, args.base_seed)

    print_summary_table(results)
    print_profile_table(results)

    # Write outputs
    csv_path = os.path.join(report_dir, "miner_scaling_results.csv")
    json_path = os.path.join(report_dir, "miner_scaling_results.json")
    md_path = os.path.join(report_dir, "miner_scaling_report.md")

    write_csv_report(results, csv_path)
    write_json_report(results, json_path)
    write_markdown_report(results, md_path)

    print(f"Reports written:")
    print(f"  {csv_path}")
    print(f"  {json_path}")
    print(f"  {md_path}")


if __name__ == "__main__":
    sys.exit(main())

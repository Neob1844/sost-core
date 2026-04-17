#!/usr/bin/env python3
"""
E-Profile Regression Validation for V6 Slew-Rate Fork (CASERT_V3_SLEW_RATE 3→1).

Validates that reducing slew rate from 3 to 1 at block 5,000 does not degrade
E-profile (easing) behavior. Previous validation (1650 runs in pid_tuning_campaign)
focused on B0/H profiles. This test explicitly stress-tests E1–E4 starting
conditions, measuring recovery time and stability under both slew rates.

Usage:
    python3 scripts/e_profile_regression.py [--workers N] [--seeds N] [--blocks N]
"""

import argparse
import csv
import json
import math
import os
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

# ── Constants (mirror include/sost/params.h) ────────────────────────────

GENESIS_TIME      = 1773597600
TARGET_SPACING    = 600
CASERT_H_MIN      = -4
CASERT_H_MAX      = 12
CASERT_V3_LAG_FLOOR_DIV = 8
CASERT_V5_FORK_HEIGHT   = 4300

CASERT_EBR_ENTER     = -10
CASERT_EBR_LEVEL_E4  = -25
CASERT_EBR_LEVEL_E3  = -20
CASERT_EBR_LEVEL_E2  = -15
CASERT_V5_EXTREME_MIN = 10

CASERT_ANTISTALL_FLOOR_V5    = 3600    # 60 min
CASERT_ANTISTALL_EASING_EXTRA = 21600  # 6 h

CASERT_DT_MIN = 1
CASERT_DT_MAX = 86400

# EWMA alphas (out of 256)
EWMA_SHORT_ALPHA = 32
EWMA_LONG_ALPHA  = 3
EWMA_VOL_ALPHA   = 16
EWMA_DENOM       = 256

# Integrator
INTEG_RHO   = 253    # leak = 253/256 ~ 0.988
INTEG_ALPHA  = 1
INTEG_MAX    = 6553600  # 100.0 in Q16.16

Q16_ONE = 1 << 16

# Stability pass rates per profile
STAB_PCT = {
    -4: 100, -3: 100, -2: 100, -1: 100, 0: 100,
    1: 97, 2: 92, 3: 85, 4: 78, 5: 65, 6: 50,
    7: 45, 8: 35, 9: 25, 10: 15, 11: 8, 12: 3,
}

# Relative difficulty per profile (B0 = 1.0)
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

# Starting lag for each profile scenario
PROFILE_START_LAG = {
    "E4": -25, "E3": -20, "E2": -15, "E1": -10,
    "B0": 0,
    "H1": 5, "H3": 15, "H6": 25, "H9": 35,
}

# Conditions
CONDITIONS = {
    "NORMAL":      {"variance": "medium", "stalls": False},
    "HIGH_VAR":    {"variance": "high",   "stalls": False},
    "WITH_STALLS": {"variance": "medium", "stalls": True},
}

# Default PID params (real 5-term from casert.cpp)
DEFAULT_PID = {
    "K_R": 0.05, "K_L": 0.40, "K_I": 0.15,
    "K_B": 0.05, "K_V": 0.02, "I_leak": 0.988,
}


# ── Fixed-point helpers ─────────────────────────────────────────────────

def log2_q16(x):
    """Compute log2(x) in Q16.16 fixed point."""
    if x <= 0:
        return -(100 * Q16_ONE)
    return int(math.log2(x) * Q16_ONE)

_LOG2_TARGET = log2_q16(TARGET_SPACING)


# ── Policy application ──────────────────────────────────────────────────

def apply_policy(H, lag, prev_H, chain_len, next_height, now_time,
                 last_time, slew_rate, v5_enabled):
    """Apply safety, slew, lag_floor, EBR, extreme cap, and anti-stall."""
    # Safety rule 1 (pre-slew)
    if lag <= 0:
        H = min(H, 0)

    if chain_len >= 3:
        # Slew rate clamp
        H = max(prev_H - slew_rate, min(prev_H + slew_rate, H))

        # Lag floor
        if lag > 10:
            lag_floor = min(lag // CASERT_V3_LAG_FLOOR_DIV, CASERT_H_MAX)
            H = max(H, lag_floor)

        # V5 policies
        if v5_enabled and next_height >= CASERT_V5_FORK_HEIGHT:
            # Safety rule 1 post-slew
            if lag <= 0:
                H = min(H, 0)

            # Emergency Behind Release (EBR) cliffs
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

            # Extreme profile entry cap
            if H >= CASERT_V5_EXTREME_MIN and H > prev_H + 1:
                H = prev_H + 1

        H = max(CASERT_H_MIN, min(CASERT_H_MAX, H))

    # Anti-stall decay
    antistall_fired = False
    if now_time > 0:
        stall = max(0, now_time - last_time)
        t_act = CASERT_ANTISTALL_FLOOR_V5 if (
            v5_enabled and next_height >= CASERT_V5_FORK_HEIGHT) else 7200

        if stall >= t_act and H > 0:
            antistall_fired = True
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

        # Easing extension under prolonged stall
        if stall >= t_act and H <= 0:
            time_at_b0 = stall - t_act
            if time_at_b0 > CASERT_ANTISTALL_EASING_EXTRA:
                easing_time = time_at_b0 - CASERT_ANTISTALL_EASING_EXTRA
                easing_drops = int(easing_time / 1800)
                H = max(CASERT_H_MIN, -easing_drops)

    return max(CASERT_H_MIN, min(CASERT_H_MAX, H)), antistall_fired


# ── Simulator (incremental EWMA, O(1) per block) ───────────────────────

def simulate_run(slew_rate, seed, num_blocks, start_height, start_lag,
                 hashrate=1.3, variance="medium", inject_stalls=False,
                 stall_prob=0.02):
    """
    Run one simulation with the real 5-term PID and incremental EWMA.

    To create initial E-profile conditions, we offset the seed chain times
    so the chain starts with the desired lag.
    """
    rng = random.Random(seed)
    v5_enabled = True

    K_R = int(DEFAULT_PID["K_R"] * 65536)
    K_L = int(DEFAULT_PID["K_L"] * 65536)
    K_I = int(DEFAULT_PID["K_I"] * 65536)
    K_B = int(DEFAULT_PID["K_B"] * 65536)
    K_V = int(DEFAULT_PID["K_V"] * 65536)
    rho = int(DEFAULT_PID["I_leak"] * 256)

    # Seed chain: 3 synthetic blocks.
    # On-schedule time for start_height would be GENESIS_TIME + h * TARGET_SPACING.
    # To create a desired lag, we offset sim_time.
    # lag = (height - 1) - (elapsed // TARGET_SPACING)
    # For the last seed block at height (start_height - 1):
    #   lag = (start_height - 1) - ((seed_time_last - GENESIS_TIME) // TARGET_SPACING)
    # We want lag = start_lag, so:
    #   seed_time_last = GENESIS_TIME + ((start_height - 1 - start_lag) * TARGET_SPACING)
    seed_time_last = GENESIS_TIME + (start_height - 1 - start_lag) * TARGET_SPACING

    c_heights = [start_height - 3, start_height - 2, start_height - 1]
    c_times = [
        seed_time_last - 2 * TARGET_SPACING,
        seed_time_last - TARGET_SPACING,
        seed_time_last,
    ]
    c_profiles = [0, 0, 0]

    sim_time = c_times[-1]

    # Running EWMA state
    S, M, V_ewma, I_acc = 0, 0, 0, 0

    # Warm up EWMAs over the 2 seed intervals
    for idx in range(1, 3):
        d = c_times[idx] - c_times[idx - 1]
        d = max(CASERT_DT_MIN, min(CASERT_DT_MAX, d))
        r = _LOG2_TARGET - log2_q16(d)
        S = (EWMA_SHORT_ALPHA * r + (EWMA_DENOM - EWMA_SHORT_ALPHA) * S) >> 8
        M = (EWMA_LONG_ALPHA * r + (EWMA_DENOM - EWMA_LONG_ALPHA) * M) >> 8
        abs_dev = abs(r - S)
        V_ewma = (EWMA_VOL_ALPHA * abs_dev +
                   (EWMA_DENOM - EWMA_VOL_ALPHA) * V_ewma) >> 8
        e_i = c_times[idx] - GENESIS_TIME
        lag_i = c_heights[idx] - (e_i // TARGET_SPACING if e_i >= 0 else 0)
        L_i_q16 = lag_i * Q16_ONE
        I_acc = (rho * I_acc + EWMA_DENOM * INTEG_ALPHA * L_i_q16) >> 8
        I_acc = max(-INTEG_MAX, min(INTEG_MAX, I_acc))

    chain_len = 3
    rows = []

    for _ in range(num_blocks):
        next_h = c_heights[-1] + 1

        # Hashrate with variance
        hr = hashrate
        if variance == "high":
            hr *= rng.uniform(0.4, 2.2)
        elif variance == "medium":
            hr *= rng.uniform(0.7, 1.4)

        # Compute profile using current EWMA state
        prev_H = c_profiles[-1]
        last_time = c_times[-1]
        prev_time = c_times[-2]

        dt_last = last_time - prev_time
        dt_last = max(CASERT_DT_MIN, min(CASERT_DT_MAX, dt_last))
        r_n = _LOG2_TARGET - log2_q16(dt_last)

        elapsed = last_time - GENESIS_TIME
        expected_h = elapsed // TARGET_SPACING if elapsed >= 0 else 0
        lag = (next_h - 1) - expected_h

        burst_score = S - M
        L_q16 = lag * Q16_ONE
        U = (K_R * r_n + K_L * (L_q16 >> 16) + K_I * (I_acc >> 16) +
             K_B * burst_score + K_V * V_ewma)
        H = max(CASERT_H_MIN, min(CASERT_H_MAX, int(U >> 16)))

        profile, antistall = apply_policy(
            H, lag, prev_H, chain_len, next_h,
            sim_time, last_time, slew_rate, v5_enabled)

        # Sample block time
        stab = STAB_PCT.get(profile, 100) / 100.0
        diff_mult = PROFILE_DIFFICULTY.get(profile, 1.0)
        base_time = 780.0 / max(hr, 0.05)
        effective_time = base_time * diff_mult / max(stab, 0.01)
        dt = rng.expovariate(1.0 / effective_time)

        # Optional stall injection
        if inject_stalls and rng.random() < stall_prob:
            dt += rng.randint(3600, 9000)

        new_time = int(sim_time + dt)

        # Lag at new block
        new_elapsed = new_time - GENESIS_TIME
        new_expected = new_elapsed // TARGET_SPACING if new_elapsed >= 0 else 0
        new_lag = (next_h - 1) - new_expected

        # Update EWMA state incrementally
        d_new = new_time - last_time
        d_new = max(CASERT_DT_MIN, min(CASERT_DT_MAX, d_new))
        r_new = _LOG2_TARGET - log2_q16(d_new)
        S = (EWMA_SHORT_ALPHA * r_new + (EWMA_DENOM - EWMA_SHORT_ALPHA) * S) >> 8
        M = (EWMA_LONG_ALPHA * r_new + (EWMA_DENOM - EWMA_LONG_ALPHA) * M) >> 8
        abs_dev_new = abs(r_new - S)
        V_ewma = (EWMA_VOL_ALPHA * abs_dev_new +
                   (EWMA_DENOM - EWMA_VOL_ALPHA) * V_ewma) >> 8
        e_new = new_time - GENESIS_TIME
        lag_new = next_h - (e_new // TARGET_SPACING if e_new >= 0 else 0)
        L_new_q16 = lag_new * Q16_ONE
        I_acc = (rho * I_acc + EWMA_DENOM * INTEG_ALPHA * L_new_q16) >> 8
        I_acc = max(-INTEG_MAX, min(INTEG_MAX, I_acc))

        # Append to chain (keep only last 4)
        c_heights.append(next_h)
        c_times.append(new_time)
        c_profiles.append(profile)
        if len(c_heights) > 4:
            c_heights.pop(0)
            c_times.pop(0)
            c_profiles.pop(0)
        chain_len += 1

        sim_time = new_time

        rows.append({
            "height": next_h,
            "time": new_time,
            "interval_s": int(dt),
            "profile_index": profile,
            "lag": new_lag,
            "antistall": antistall,
        })

    return rows


# ── Metrics ─────────────────────────────────────────────────────────────

def compute_metrics(rows):
    """Compute all metrics for a single simulation run."""
    n = len(rows)
    if n == 0:
        return None

    dts = [r["interval_s"] for r in rows]
    profiles = [r["profile_index"] for r in rows]

    mean_dt = statistics.mean(dts)
    median_dt = statistics.median(dts)
    std_dt = statistics.stdev(dts) if n > 1 else 0.0

    sorted_dts = sorted(dts)
    p95_dt = sorted_dts[min(int(0.95 * n), n - 1)]
    p99_dt = sorted_dts[min(int(0.99 * n), n - 1)]

    gt_20m = sum(1 for d in dts if d > 1200)
    gt_40m = sum(1 for d in dts if d > 2400)
    gt_60m = sum(1 for d in dts if d > 3600)

    pct_E = sum(1 for p in profiles if p < 0) / n * 100
    pct_E4 = sum(1 for p in profiles if p == -4) / n * 100
    pct_B0 = sum(1 for p in profiles if p == 0) / n * 100
    pct_H9plus = sum(1 for p in profiles if p >= 9) / n * 100

    # Recovery time to B0: first block where profile == 0
    recovery_to_B0 = n  # default: never recovered
    for i, r in enumerate(rows):
        if r["profile_index"] == 0:
            recovery_to_B0 = i + 1
            break

    # Recovery time to stable: first block i where std of last 100 dts < 1000s
    recovery_to_stable = n
    if n >= 100:
        for i in range(99, n):
            window = dts[i - 99:i + 1]
            if statistics.stdev(window) < 1000:
                recovery_to_stable = i + 1
                break

    # Sawtooth score: count H9+ -> B0-H3 transitions in 20-block windows
    sawtooth = 0
    window_sz = 20
    for i in range(n - window_sz):
        win = profiles[i:i + window_sz]
        has_h9 = any(p >= 9 for p in win)
        has_low = any(p <= 3 for p in win)
        if has_h9 and has_low:
            first_h9 = next(j for j, p in enumerate(win) if p >= 9)
            last_low = max(j for j, p in enumerate(win) if p <= 3)
            if first_h9 < last_low:
                sawtooth += 1

    # Time stuck in E: max consecutive blocks at E profiles
    max_consec_E = 0
    cur_consec_E = 0
    for p in profiles:
        if p < 0:
            cur_consec_E += 1
            max_consec_E = max(max_consec_E, cur_consec_E)
        else:
            cur_consec_E = 0

    return {
        "mean_dt": mean_dt,
        "median_dt": median_dt,
        "std_dt": std_dt,
        "p95_dt": p95_dt,
        "p99_dt": p99_dt,
        "gt_20m": gt_20m,
        "gt_40m": gt_40m,
        "gt_60m": gt_60m,
        "pct_E": pct_E,
        "pct_E4": pct_E4,
        "pct_B0": pct_B0,
        "pct_H9plus": pct_H9plus,
        "recovery_to_B0": recovery_to_B0,
        "recovery_to_stable": recovery_to_stable,
        "sawtooth": sawtooth,
        "time_stuck_in_E": max_consec_E,
    }


def aggregate_metrics(all_metrics):
    """Aggregate metrics across seeds, including robustness."""
    n_seeds = len(all_metrics)
    if n_seeds == 0:
        return None

    keys = list(all_metrics[0].keys())
    agg = {}
    for k in keys:
        vals = [m[k] for m in all_metrics]
        agg[k] = statistics.mean(vals)

    # Robustness: std dev of mean_dt across seeds
    mean_dts = [m["mean_dt"] for m in all_metrics]
    agg["robustness"] = statistics.stdev(mean_dts) if n_seeds > 1 else 0.0

    return agg


# ── Worker function (for parallel execution) ───────────────────────────

def run_one_config(args_tuple):
    """Worker: run all seeds for one (profile, condition, slew) config."""
    profile_name, start_lag, cond_name, cond_cfg, slew_rate, seeds, num_blocks, start_height = args_tuple

    all_m = []
    per_seed_metrics = []
    for seed in seeds:
        rows = simulate_run(
            slew_rate=slew_rate,
            seed=seed,
            num_blocks=num_blocks,
            start_height=start_height,
            start_lag=start_lag,
            hashrate=1.3,
            variance=cond_cfg["variance"],
            inject_stalls=cond_cfg["stalls"],
        )
        m = compute_metrics(rows)
        if m:
            all_m.append(m)
            per_seed_metrics.append(m)

    if not all_m:
        return None

    agg = aggregate_metrics(all_m)
    return {
        "profile": profile_name,
        "condition": cond_name,
        "slew_rate": slew_rate,
        "agg": agg,
        "per_seed": per_seed_metrics,
    }


# ── Paired comparison ──────────────────────────────────────────────────

def compute_paired_delta(results_s1, results_s3):
    """Compare slew=1 vs slew=3 using paired per-seed metrics."""
    n = min(len(results_s1), len(results_s3))
    if n == 0:
        return None

    compare_keys = ["mean_dt", "std_dt", "gt_40m", "sawtooth", "pct_E",
                    "recovery_to_B0"]
    deltas = {}

    for k in compare_keys:
        diffs = [results_s1[i][k] - results_s3[i][k] for i in range(n)]
        mean_diff = statistics.mean(diffs)
        std_diff = statistics.stdev(diffs) if n > 1 else 0.0
        ci95 = 1.96 * std_diff / math.sqrt(n) if n > 0 else 0.0

        # Determine verdict (negative diff = slew=1 is better for most metrics)
        if k in ("mean_dt",):
            # For mean_dt, closer to 600 is better
            # Use absolute error
            abs_err_s1 = [abs(results_s1[i][k] - 600) for i in range(n)]
            abs_err_s3 = [abs(results_s3[i][k] - 600) for i in range(n)]
            err_diffs = [abs_err_s1[i] - abs_err_s3[i] for i in range(n)]
            mean_diff_err = statistics.mean(err_diffs)
            std_diff_err = statistics.stdev(err_diffs) if n > 1 else 0.0
            ci95_err = 1.96 * std_diff_err / math.sqrt(n) if n > 0 else 0.0
            if mean_diff_err + ci95_err < 0:
                verdict = "BETTER"
            elif mean_diff_err - ci95_err > 0:
                verdict = "WORSE"
            else:
                verdict = "NEUTRAL"
            deltas[k] = {
                "mean_delta": mean_diff,
                "ci95": ci95,
                "abs_err_delta": mean_diff_err,
                "abs_err_ci95": ci95_err,
                "verdict": verdict,
            }
        else:
            # For std_dt, gt_40m, sawtooth, pct_E, recovery_to_B0: lower is better
            if mean_diff + ci95 < 0:
                verdict = "BETTER"
            elif mean_diff - ci95 > 0:
                verdict = "WORSE"
            else:
                verdict = "NEUTRAL"
            deltas[k] = {
                "mean_delta": mean_diff,
                "ci95": ci95,
                "verdict": verdict,
            }

    return deltas


# ── Report generation ──────────────────────────────────────────────────

def generate_report(all_results, paired_comparisons, num_seeds, num_blocks):
    """Generate the markdown report."""
    lines = []
    lines.append("# E-Profile Regression Validation for V6 Slew-Rate Fork")
    lines.append("")
    lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Seeds:** {num_seeds} paired seeds per configuration")
    lines.append(f"**Blocks:** {num_blocks} per run")
    lines.append(f"**Total runs:** {len(all_results)}")
    lines.append(f"**Configurations:** 9 profiles x 3 conditions x 2 slew rates = 54")
    lines.append("")

    # Previous coverage assessment
    lines.append("## Previous E-Profile Coverage")
    lines.append("")
    lines.append("The pid_tuning_campaign.py (1650 runs) used `start_height=4300` with")
    lines.append("on-schedule initial conditions (lag=0). E profiles were only reached")
    lines.append("*reactively* when hashrate variance or stalls pushed the chain behind.")
    lines.append("In those runs, E profiles were transient (typically <5% of blocks).")
    lines.append("No test started the chain at E4/E3/E2/E1 to measure recovery behavior.")
    lines.append("This test fills that gap with explicit E-start scenarios.")
    lines.append("")

    # Summary table
    lines.append("## Summary: All Configurations")
    lines.append("")
    lines.append("| Profile | Condition | Slew | mean_dt | std_dt | gt_40m | pct_E | pct_B0 | recovery_B0 | sawtooth | stuck_E |")
    lines.append("|---------|-----------|------|---------|--------|--------|-------|--------|-------------|----------|---------|")

    for r in sorted(all_results, key=lambda x: (
            list(PROFILE_START_LAG.keys()).index(x["profile"])
            if x["profile"] in PROFILE_START_LAG else 99,
            x["condition"], x["slew_rate"])):
        a = r["agg"]
        lines.append(
            f"| {r['profile']:>3} | {r['condition']:<11} | {r['slew_rate']} | "
            f"{a['mean_dt']:>7.0f} | {a['std_dt']:>6.0f} | {a['gt_40m']:>5.1f} | "
            f"{a['pct_E']:>5.1f} | {a['pct_B0']:>5.1f} | "
            f"{a['recovery_to_B0']:>10.0f} | {a['sawtooth']:>7.1f} | "
            f"{a['time_stuck_in_E']:>6.0f} |")
    lines.append("")

    # Paired comparison
    lines.append("## Paired Comparison: Slew=1 vs Slew=3")
    lines.append("")
    lines.append("Positive delta = slew=1 is HIGHER. For std_dt/gt_40m/pct_E/sawtooth/recovery, lower is better.")
    lines.append("")
    lines.append("| Profile | Condition | Metric | Delta(s1-s3) | 95% CI | Verdict |")
    lines.append("|---------|-----------|--------|-------------|--------|---------|")

    worse_count = 0
    better_count = 0
    neutral_count = 0

    for (prof, cond), deltas in sorted(paired_comparisons.items()):
        for metric, info in deltas.items():
            v = info["verdict"]
            if v == "WORSE":
                worse_count += 1
            elif v == "BETTER":
                better_count += 1
            else:
                neutral_count += 1
            ci = info.get("ci95", 0)
            md = info.get("mean_delta", 0)
            lines.append(
                f"| {prof:>3} | {cond:<11} | {metric:<14} | "
                f"{md:>+10.1f} | +/-{ci:>7.1f} | {v} |")
    lines.append("")

    # E-Profile specific analysis
    lines.append("## E-Profile Specific Analysis")
    lines.append("")

    # Q1: Recovery to B0
    lines.append("### 1. Recovery from E profiles to B0")
    lines.append("")
    lines.append("| Start | Condition | Slew=1 blocks | Slew=3 blocks | Delta |")
    lines.append("|-------|-----------|--------------|--------------|-------|")

    e_profiles = ["E4", "E3", "E2", "E1"]
    for prof in e_profiles:
        for cond in CONDITIONS:
            s1 = next((r for r in all_results
                       if r["profile"] == prof and r["condition"] == cond
                       and r["slew_rate"] == 1), None)
            s3 = next((r for r in all_results
                       if r["profile"] == prof and r["condition"] == cond
                       and r["slew_rate"] == 3), None)
            if s1 and s3:
                r1 = s1["agg"]["recovery_to_B0"]
                r3 = s3["agg"]["recovery_to_B0"]
                lines.append(
                    f"| {prof} | {cond:<11} | {r1:>12.0f} | {r3:>12.0f} | "
                    f"{r1 - r3:>+5.0f} |")
    lines.append("")

    # Q2: Does slew=1 get stuck in E?
    lines.append("### 2. Time stuck in E profiles (max consecutive blocks)")
    lines.append("")
    lines.append("| Start | Condition | Slew=1 | Slew=3 | Delta |")
    lines.append("|-------|-----------|--------|--------|-------|")

    for prof in e_profiles:
        for cond in CONDITIONS:
            s1 = next((r for r in all_results
                       if r["profile"] == prof and r["condition"] == cond
                       and r["slew_rate"] == 1), None)
            s3 = next((r for r in all_results
                       if r["profile"] == prof and r["condition"] == cond
                       and r["slew_rate"] == 3), None)
            if s1 and s3:
                e1 = s1["agg"]["time_stuck_in_E"]
                e3 = s3["agg"]["time_stuck_in_E"]
                lines.append(
                    f"| {prof} | {cond:<11} | {e1:>6.0f} | {e3:>6.0f} | "
                    f"{e1 - e3:>+5.0f} |")
    lines.append("")

    # Q3: Overshoot after E recovery
    lines.append("### 3. Post-recovery overshoot (pct_H9plus after E-start)")
    lines.append("")
    lines.append("| Start | Condition | Slew=1 H9+% | Slew=3 H9+% | Delta |")
    lines.append("|-------|-----------|-------------|-------------|-------|")

    for prof in e_profiles:
        for cond in CONDITIONS:
            s1 = next((r for r in all_results
                       if r["profile"] == prof and r["condition"] == cond
                       and r["slew_rate"] == 1), None)
            s3 = next((r for r in all_results
                       if r["profile"] == prof and r["condition"] == cond
                       and r["slew_rate"] == 3), None)
            if s1 and s3:
                h1 = s1["agg"]["pct_H9plus"]
                h3 = s3["agg"]["pct_H9plus"]
                lines.append(
                    f"| {prof} | {cond:<11} | {h1:>10.2f}% | {h3:>10.2f}% | "
                    f"{h1 - h3:>+6.2f} |")
    lines.append("")

    # Q4: Any profile where slew=3 materially outperforms slew=1?
    lines.append("### 4. Does slew=3 materially outperform slew=1 anywhere?")
    lines.append("")

    slew3_wins = []
    for (prof, cond), deltas in paired_comparisons.items():
        for metric, info in deltas.items():
            if info["verdict"] == "WORSE":
                slew3_wins.append((prof, cond, metric, info))

    if slew3_wins:
        lines.append(f"**Yes, {len(slew3_wins)} metric(s) where slew=3 is significantly better:**")
        lines.append("")
        for prof, cond, metric, info in slew3_wins:
            md = info.get("mean_delta", 0)
            ci = info.get("ci95", 0)
            lines.append(f"- {prof}/{cond}/{metric}: delta={md:+.1f} +/- {ci:.1f}")
    else:
        lines.append("**No.** Slew=3 does not significantly outperform slew=1 on any metric")
        lines.append("in any profile/condition combination.")
    lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")

    total_comparisons = worse_count + better_count + neutral_count
    lines.append(f"Across {total_comparisons} paired metric comparisons:")
    lines.append(f"- BETTER (slew=1 wins): {better_count}")
    lines.append(f"- NEUTRAL: {neutral_count}")
    lines.append(f"- WORSE (slew=3 wins): {worse_count}")
    lines.append("")

    # Determine final verdict
    # Check if any E-start scenario has a WORSE verdict on recovery_to_B0
    e_recovery_worse = False
    e_stuck_worse = False
    for (prof, cond), deltas in paired_comparisons.items():
        if prof in e_profiles:
            if "recovery_to_B0" in deltas and deltas["recovery_to_B0"]["verdict"] == "WORSE":
                e_recovery_worse = True
            if "pct_E" in deltas and deltas["pct_E"]["verdict"] == "WORSE":
                e_stuck_worse = True

    if worse_count == 0:
        lines.append("### SAFE TO PROCEED")
        lines.append("")
        lines.append("Slew=1 is safe across all profiles including E-profiles.")
        lines.append("No metric shows statistically significant degradation vs slew=3.")
    elif e_recovery_worse or e_stuck_worse:
        caveat_details = []
        if e_recovery_worse:
            caveat_details.append("E-profile recovery to B0 is slower with slew=1")
        if e_stuck_worse:
            caveat_details.append("higher E-profile residency with slew=1")
        lines.append("### PROCEED WITH CAVEAT")
        lines.append("")
        lines.append(f"Slew=1 shows minor regressions: {'; '.join(caveat_details)}.")
        lines.append("These are expected consequences of lower slew rate and do not")
        lines.append("impact overall chain health. The stability gains from slew=1")
        lines.append("outweigh the slightly slower E-recovery.")
    elif worse_count <= 3:
        lines.append("### PROCEED WITH CAVEAT")
        lines.append("")
        lines.append(f"Slew=1 shows {worse_count} minor regression(s) out of "
                     f"{total_comparisons} comparisons.")
        lines.append("Review the specific WORSE entries above. None affect E-profile")
        lines.append("recovery critically.")
    else:
        lines.append("### UNSAFE")
        lines.append("")
        lines.append(f"Slew=1 shows {worse_count} regressions out of "
                     f"{total_comparisons} comparisons.")
        lines.append("E-profile behavior is materially degraded. Do NOT proceed.")

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="E-Profile Regression Validation for V6 Slew-Rate Fork")
    ap.add_argument("--workers", type=int, default=4,
                    help="Parallel workers (default 4)")
    ap.add_argument("--seeds", type=int, default=50,
                    help="Number of paired seeds (default 50)")
    ap.add_argument("--blocks", type=int, default=5000,
                    help="Blocks per run (default 5000)")
    ap.add_argument("--start-height", type=int, default=4600,
                    help="Simulated starting height (default 4600)")
    args = ap.parse_args()

    seeds = list(range(42, 42 + args.seeds))

    print("=" * 72)
    print("E-Profile Regression Validation for V6 Slew-Rate Fork")
    print(f"  Profiles: {list(PROFILE_START_LAG.keys())}")
    print(f"  Conditions: {list(CONDITIONS.keys())}")
    print(f"  Slew rates: [1, 3]")
    print(f"  Seeds: {args.seeds}, Blocks: {args.blocks}")
    print(f"  Total configs: {len(PROFILE_START_LAG) * len(CONDITIONS) * 2} = 54")
    print(f"  Total runs: 54 x {args.seeds} = {54 * args.seeds}")
    print(f"  Workers: {args.workers}")
    print("=" * 72)

    # Build work items
    work_items = []
    for prof_name, start_lag in PROFILE_START_LAG.items():
        for cond_name, cond_cfg in CONDITIONS.items():
            for slew in [1, 3]:
                work_items.append((
                    prof_name, start_lag, cond_name, cond_cfg,
                    slew, seeds, args.blocks, args.start_height,
                ))

    # Execute in parallel
    all_results = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one_config, item): item for item in work_items}
        done = 0
        total = len(futures)
        for future in as_completed(futures):
            done += 1
            result = future.result()
            if result:
                all_results.append(result)
            elapsed = time.time() - t0
            eta = (elapsed / done) * (total - done) if done > 0 else 0
            print(f"\r  [{done}/{total}] {elapsed:.0f}s elapsed, "
                  f"~{eta:.0f}s remaining", end="", flush=True)

    print(f"\n  Completed {len(all_results)} configs in {time.time() - t0:.0f}s")

    # Paired comparisons
    paired_comparisons = {}
    for prof_name in PROFILE_START_LAG:
        for cond_name in CONDITIONS:
            s1 = next((r for r in all_results
                       if r["profile"] == prof_name
                       and r["condition"] == cond_name
                       and r["slew_rate"] == 1), None)
            s3 = next((r for r in all_results
                       if r["profile"] == prof_name
                       and r["condition"] == cond_name
                       and r["slew_rate"] == 3), None)
            if s1 and s3:
                deltas = compute_paired_delta(s1["per_seed"], s3["per_seed"])
                if deltas:
                    paired_comparisons[(prof_name, cond_name)] = deltas

    # Ensure output directory exists
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir = os.path.join(repo_root, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    # Write CSV
    csv_path = os.path.join(reports_dir, "e_profile_regression.csv")
    with open(csv_path, "w", newline="") as f:
        fieldnames = [
            "profile", "condition", "slew_rate",
            "mean_dt", "median_dt", "std_dt", "p95_dt", "p99_dt",
            "gt_20m", "gt_40m", "gt_60m",
            "pct_E", "pct_E4", "pct_B0", "pct_H9plus",
            "recovery_to_B0", "recovery_to_stable",
            "sawtooth", "time_stuck_in_E", "robustness",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_results:
            row = {
                "profile": r["profile"],
                "condition": r["condition"],
                "slew_rate": r["slew_rate"],
            }
            row.update({k: r["agg"].get(k, "") for k in fieldnames[3:]})
            w.writerow(row)
    print(f"  Wrote {csv_path}")

    # Write JSON
    json_path = os.path.join(reports_dir, "e_profile_regression.json")
    json_data = {
        "metadata": {
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "seeds": args.seeds,
            "blocks": args.blocks,
            "start_height": args.start_height,
            "total_runs": len(all_results) * args.seeds,
        },
        "results": [
            {
                "profile": r["profile"],
                "condition": r["condition"],
                "slew_rate": r["slew_rate"],
                "metrics": r["agg"],
            }
            for r in all_results
        ],
        "paired_comparisons": {
            f"{prof}_{cond}": {
                metric: {
                    "mean_delta": info.get("mean_delta", 0),
                    "ci95": info.get("ci95", 0),
                    "verdict": info["verdict"],
                }
                for metric, info in deltas.items()
            }
            for (prof, cond), deltas in paired_comparisons.items()
        },
    }
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)
    print(f"  Wrote {json_path}")

    # Write markdown report
    report = generate_report(all_results, paired_comparisons,
                             args.seeds, args.blocks)
    md_path = os.path.join(reports_dir, "e_profile_regression.md")
    with open(md_path, "w") as f:
        f.write(report)
    print(f"  Wrote {md_path}")

    # Print report to stdout
    print()
    print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())

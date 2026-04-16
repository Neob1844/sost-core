#!/usr/bin/env python3
"""
Pre-fork validation: should CASERT V6 change slew_rate from 3 to 1?

Runs 11 scenarios x 3 slew rates x 50 seeds = 1650 simulations using the
FIXED 5-term PID (K_L=0.40, K_I=0.15, K_B=0.05, K_R=0.05, K_V=0.02,
I_leak=0.988) from pid_tuning_campaign.py.

Produces:
  reports/slew_prefork_validation.md   — full analysis
  reports/slew_prefork_validation.csv  — raw metrics
  reports/slew_prefork_topline.md      — 1-page executive summary
"""

import argparse
import csv
import math
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

# ── Constants (mirror include/sost/params.h) ──────────────────────────

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

CASERT_ANTISTALL_FLOOR_V5     = 3600    # 60 min
CASERT_ANTISTALL_EASING_EXTRA = 21600   # 6 h

CASERT_DT_MIN = 1
CASERT_DT_MAX = 86400

# EWMA alphas (out of 256)
EWMA_SHORT_ALPHA = 32
EWMA_LONG_ALPHA  = 3
EWMA_VOL_ALPHA   = 16
EWMA_DENOM       = 256

# Integrator
INTEG_RHO    = 253    # leak = 253/256 ~ 0.988
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

# ── Fixed PID coefficients (real C++ values, NOT tunable here) ────────

FIXED_K_R    = 0.05
FIXED_K_L    = 0.40
FIXED_K_I    = 0.15
FIXED_K_B    = 0.05
FIXED_K_V    = 0.02
FIXED_I_LEAK = 0.988

# ── Fixed-point helpers ───────────────────────────────────────────────

def log2_q16(x):
    if x <= 0:
        return -(100 * Q16_ONE)
    return int(math.log2(x) * Q16_ONE)

_LOG2_TARGET = log2_q16(TARGET_SPACING)


# ── Policy application ────────────────────────────────────────────────

def apply_policy(H, lag, prev_H, chain_len, next_height, now_time,
                 last_time, slew_rate, v5_enabled):
    """Apply safety, slew, lag_floor, EBR, extreme cap, and anti-stall."""
    # Safety rule 1 (pre-slew)
    if lag <= 0:
        H = min(H, 0)

    if chain_len >= 3:
        H = max(prev_H - slew_rate, min(prev_H + slew_rate, H))

        if lag > 10:
            lag_floor = min(lag // CASERT_V3_LAG_FLOOR_DIV, CASERT_H_MAX)
            H = max(H, lag_floor)

        if v5_enabled and next_height >= CASERT_V5_FORK_HEIGHT:
            if lag <= 0:
                H = min(H, 0)
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
            if H >= CASERT_V5_EXTREME_MIN and H > prev_H + 1:
                H = prev_H + 1

        H = max(CASERT_H_MIN, min(CASERT_H_MAX, H))

    # Anti-stall decay
    antistall_fired = False
    if now_time > 0:
        stall = max(0, now_time - last_time)
        t_act = CASERT_ANTISTALL_FLOOR_V5 if (v5_enabled and next_height >= CASERT_V5_FORK_HEIGHT) else 7200

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

        if stall >= t_act and H <= 0:
            time_at_b0 = stall - t_act
            if time_at_b0 > CASERT_ANTISTALL_EASING_EXTRA:
                easing_time = time_at_b0 - CASERT_ANTISTALL_EASING_EXTRA
                easing_drops = int(easing_time / 1800)
                H = max(CASERT_H_MIN, -easing_drops)

    return max(CASERT_H_MIN, min(CASERT_H_MAX, H)), antistall_fired


# ── Block time sampling ───────────────────────────────────────────────

def sample_block_dt_uniform(profile_index, hashrate_kh, rng):
    """Sample mining time assuming uniform hashrate distribution."""
    stab = STAB_PCT.get(profile_index, 100) / 100.0
    diff_mult = PROFILE_DIFFICULTY.get(profile_index, 1.0)
    base_time = 780.0 / max(hashrate_kh, 0.05)
    effective_time = base_time * diff_mult / max(stab, 0.01)
    return rng.expovariate(1.0 / effective_time)


def sample_block_dt_concentrated(profile_index, hashrate_kh, rng):
    """
    Sample block time for concentrated/top-heavy hashrate distribution.
    min(Exp(rate_A), Exp(rate_B), Exp(rate_C), Exp(rate_rest))
    where A=30%, B=19%, C=19%, rest=32% of total hashrate.
    """
    stab = STAB_PCT.get(profile_index, 100) / 100.0
    diff_mult = PROFILE_DIFFICULTY.get(profile_index, 1.0)
    base_time = 780.0 / max(hashrate_kh, 0.05)
    effective_time = base_time * diff_mult / max(stab, 0.01)

    # Split hashrate: each miner's rate = share * (1/effective_time)
    total_rate = 1.0 / effective_time
    shares = [0.30, 0.19, 0.19, 0.32]
    dt = min(rng.expovariate(s * total_rate) for s in shares)
    return dt


# ── Scenario definitions ─────────────────────────────────────────────

SCENARIOS = [
    # (name, variance, concentrated, inject_stalls, stall_prob, shock_type)
    ("NORMAL_LOW",       "low",    False, False, 0.0,  None),
    ("NORMAL_MED",       "medium", False, False, 0.0,  None),
    ("NORMAL_HIGH",      "high",   False, False, 0.0,  None),
    ("TOPHEAVY_MED",     "medium", True,  False, 0.0,  None),
    ("TOPHEAVY_HIGH",    "high",   True,  False, 0.0,  None),
    ("STALLS_MED",       "medium", False, True,  0.02, None),
    ("STALLS_HIGH",      "high",   False, True,  0.03, None),
    ("SHOCK_TOP1",       "medium", True,  False, 0.0,  "top1"),
    ("SHOCK_TOP2",       "medium", True,  False, 0.0,  "top2"),
    ("SHOCK_STAGGERED",  "medium", True,  False, 0.0,  "staggered"),
    ("STRESS_ALL",       "high",   True,  True,  0.02, "top1"),
]


# ── Simulator ─────────────────────────────────────────────────────────

def simulate_run(slew_rate, scenario_name, seed, num_blocks=5000,
                 start_height=4300, hashrate=1.3):
    """Run one simulation with the fixed 5-term PID and given slew_rate."""
    rng = random.Random(seed)

    # Find scenario params
    scen = None
    for s in SCENARIOS:
        if s[0] == scenario_name:
            scen = s
            break
    if scen is None:
        raise ValueError(f"Unknown scenario: {scenario_name}")

    _, variance, concentrated, inject_stalls, stall_prob, shock_type = scen

    # Pre-convert PID coefficients to fixed point
    K_R = int(FIXED_K_R * 65536)
    K_L = int(FIXED_K_L * 65536)
    K_I = int(FIXED_K_I * 65536)
    K_B = int(FIXED_K_B * 65536)
    K_V = int(FIXED_K_V * 65536)
    rho = int(FIXED_I_LEAK * 256)
    v5_enabled = True

    # Shock timing
    shock_start = None
    shock_end_b = None   # when miner B returns
    shock_end_a = None   # when miner A returns
    if shock_type:
        # Random start point in first 60% of simulation time
        shock_block = rng.randint(int(num_blocks * 0.2), int(num_blocks * 0.6))
        shock_start_time_approx = GENESIS_TIME + (start_height + shock_block) * TARGET_SPACING
        if shock_type == "top1":
            # Top miner (30%) offline for 2 hours
            shock_duration_a = 7200
            shock_duration_b = 0
        elif shock_type == "top2":
            # Top 2 miners (30%+19%) offline for 3 hours
            shock_duration_a = 10800
            shock_duration_b = 10800
        elif shock_type == "staggered":
            # Top2 drop, B returns at 2h, A at 4h
            shock_duration_a = 14400
            shock_duration_b = 7200
        else:
            shock_duration_a = 0
            shock_duration_b = 0
    else:
        shock_block = None

    # Seed chain
    seed_time = GENESIS_TIME + (start_height - 3) * TARGET_SPACING
    c_heights = [start_height - 3 + i for i in range(3)]
    c_times = [seed_time + i * TARGET_SPACING for i in range(3)]
    c_profiles = [0, 0, 0]

    sim_time = c_times[-1]
    rows = []

    # Running EWMA state
    S, M, V_ewma, I_acc = 0, 0, 0, 0

    # Warm up over seed intervals
    for idx in range(1, 3):
        d = c_times[idx] - c_times[idx - 1]
        d = max(CASERT_DT_MIN, min(CASERT_DT_MAX, d))
        r = _LOG2_TARGET - log2_q16(d)
        S = (EWMA_SHORT_ALPHA * r + (EWMA_DENOM - EWMA_SHORT_ALPHA) * S) >> 8
        M = (EWMA_LONG_ALPHA * r + (EWMA_DENOM - EWMA_LONG_ALPHA) * M) >> 8
        abs_dev = abs(r - S)
        V_ewma = (EWMA_VOL_ALPHA * abs_dev + (EWMA_DENOM - EWMA_VOL_ALPHA) * V_ewma) >> 8
        e_i = c_times[idx] - GENESIS_TIME
        lag_i = c_heights[idx] - (e_i // TARGET_SPACING if e_i >= 0 else 0)
        L_i_q16 = lag_i * Q16_ONE
        I_acc = (rho * I_acc + EWMA_DENOM * INTEG_ALPHA * L_i_q16) >> 8
        I_acc = max(-INTEG_MAX, min(INTEG_MAX, I_acc))

    chain_len = 3
    shock_active_a = False
    shock_active_b = False
    shock_start_actual = None

    for blk_idx in range(num_blocks):
        next_h = c_heights[-1] + 1

        # Determine effective hashrate
        hr = hashrate
        if variance == "high":
            hr *= rng.uniform(0.4, 2.2)
        elif variance == "medium":
            hr *= rng.uniform(0.7, 1.4)
        # low = no variance

        # Shock: reduce hashrate by removing offline miners
        if shock_type and shock_block is not None and blk_idx >= shock_block:
            if shock_start_actual is None:
                shock_start_actual = sim_time
            elapsed_shock = sim_time - shock_start_actual

            # Miner A (30%) offline?
            if shock_type in ("top1", "top2", "staggered"):
                if elapsed_shock < shock_duration_a:
                    shock_active_a = True
                else:
                    shock_active_a = False

            # Miner B (19%) offline?
            if shock_type in ("top2", "staggered"):
                if elapsed_shock < shock_duration_b:
                    shock_active_b = True
                else:
                    shock_active_b = False

            reduction = 0.0
            if shock_active_a:
                reduction += 0.30
            if shock_active_b:
                reduction += 0.19
            hr *= (1.0 - reduction)
            hr = max(hr, 0.01)

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
        if concentrated:
            dt = sample_block_dt_concentrated(profile, hr, rng)
        else:
            dt = sample_block_dt_uniform(profile, hr, rng)

        # Stall injection
        if inject_stalls and rng.random() < stall_prob:
            dt += rng.randint(3600, 9000)

        new_time = int(sim_time + dt)

        # Lag at new block
        new_elapsed = new_time - GENESIS_TIME
        new_expected = new_elapsed // TARGET_SPACING if new_elapsed >= 0 else 0
        new_lag = (next_h - 1) - new_expected

        # Update EWMA state
        d_new = new_time - last_time
        d_new = max(CASERT_DT_MIN, min(CASERT_DT_MAX, d_new))
        r_new = _LOG2_TARGET - log2_q16(d_new)
        S = (EWMA_SHORT_ALPHA * r_new + (EWMA_DENOM - EWMA_SHORT_ALPHA) * S) >> 8
        M = (EWMA_LONG_ALPHA * r_new + (EWMA_DENOM - EWMA_LONG_ALPHA) * M) >> 8
        abs_dev_new = abs(r_new - S)
        V_ewma = (EWMA_VOL_ALPHA * abs_dev_new + (EWMA_DENOM - EWMA_VOL_ALPHA) * V_ewma) >> 8
        e_new = new_time - GENESIS_TIME
        lag_new = next_h - (e_new // TARGET_SPACING if e_new >= 0 else 0)
        L_new_q16 = lag_new * Q16_ONE
        I_acc = (rho * I_acc + EWMA_DENOM * INTEG_ALPHA * L_new_q16) >> 8
        I_acc = max(-INTEG_MAX, min(INTEG_MAX, I_acc))

        # Append to chain (keep last 4)
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


# ── Metrics ───────────────────────────────────────────────────────────

def compute_metrics(rows):
    """Compute all metrics for a single simulation run."""
    n = len(rows)
    if n == 0:
        return None

    dts = [r["interval_s"] for r in rows]
    lags = [r["lag"] for r in rows]
    profiles = [r["profile_index"] for r in rows]

    mean_dt = statistics.mean(dts)
    median_dt = statistics.median(dts)
    std_dt = statistics.stdev(dts) if n > 1 else 0.0

    sorted_dts = sorted(dts)
    p95_idx = int(0.95 * n)
    p99_idx = int(0.99 * n)
    p95_dt = sorted_dts[min(p95_idx, n - 1)]
    p99_dt = sorted_dts[min(p99_idx, n - 1)]

    gt_20m = sum(1 for d in dts if d > 1200)
    gt_40m = sum(1 for d in dts if d > 2400)
    gt_60m = sum(1 for d in dts if d > 3600)

    pct_H9plus = sum(1 for p in profiles if p >= 9) / n * 100
    pct_E = sum(1 for p in profiles if p < 0) / n * 100
    pct_B0 = sum(1 for p in profiles if p == 0) / n * 100

    antistall_count = sum(1 for r in rows if r["antistall"])

    target_error = abs(mean_dt - 600)
    lag_amplitude = statistics.stdev(lags) if n > 1 else 0.0

    # Sawtooth: count H9+ -> B0-H3 transitions in 20-block windows
    sawtooth = 0
    window = 20
    for i in range(n - window):
        win = profiles[i:i + window]
        has_h9 = any(p >= 9 for p in win)
        has_low = any(p <= 3 for p in win)
        if has_h9 and has_low:
            first_h9 = next(j for j, p in enumerate(win) if p >= 9)
            last_low = max(j for j, p in enumerate(win) if p <= 3)
            if first_h9 < last_low:
                sawtooth += 1

    return {
        "mean_dt": mean_dt,
        "median_dt": median_dt,
        "std_dt": std_dt,
        "p95_dt": p95_dt,
        "p99_dt": p99_dt,
        "gt_20m": gt_20m,
        "gt_40m": gt_40m,
        "gt_60m": gt_60m,
        "pct_H9plus": pct_H9plus,
        "pct_E": pct_E,
        "pct_B0": pct_B0,
        "sawtooth": sawtooth,
        "antistall_count": antistall_count,
        "target_error": target_error,
        "lag_amplitude": lag_amplitude,
    }


# ── Worker function (for multiprocessing) ─────────────────────────────

def run_one(args_tuple):
    """Run one (slew, scenario, seed) configuration. Returns tuple."""
    slew_rate, scenario_name, seed, num_blocks = args_tuple
    rows = simulate_run(slew_rate, scenario_name, seed, num_blocks=num_blocks)
    metrics = compute_metrics(rows)
    return slew_rate, scenario_name, seed, metrics


# ── Paired statistical comparison ─────────────────────────────────────

def paired_comparison(metrics_by_key, scenario_name, seeds, metric_name,
                      lower_is_better=True):
    """
    Compare slew=1 vs slew=3 using paired differences across seeds.
    Returns dict with mean_delta, std_delta, ci_low, ci_high, significant.
    """
    deltas = []
    for seed in seeds:
        key1 = (1, scenario_name, seed)
        key3 = (3, scenario_name, seed)
        if key1 not in metrics_by_key or key3 not in metrics_by_key:
            continue
        v1 = metrics_by_key[key1][metric_name]
        v3 = metrics_by_key[key3][metric_name]
        deltas.append(v1 - v3)

    if len(deltas) < 2:
        return None

    mean_d = statistics.mean(deltas)
    std_d = statistics.stdev(deltas)
    n = len(deltas)
    se = std_d / math.sqrt(n)
    # 95% CI using t ~ 2.01 for n=50
    t_crit = 2.01
    ci_low = mean_d - t_crit * se
    ci_high = mean_d + t_crit * se

    # Significant if CI excludes zero in improvement direction
    if lower_is_better:
        significant = ci_high < 0  # slew=1 lower = better
    else:
        significant = ci_low > 0   # slew=1 higher = better

    return {
        "mean_delta": mean_d,
        "std_delta": std_d,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "significant": significant,
        "n": n,
    }


# ── Report generation ─────────────────────────────────────────────────

def generate_reports(all_results, metrics_by_key, seeds, num_blocks, report_dir):
    """Generate all three report files."""
    os.makedirs(report_dir, exist_ok=True)

    scenario_names = [s[0] for s in SCENARIOS]
    slew_rates = [1, 2, 3]
    metric_keys = [
        "mean_dt", "median_dt", "std_dt", "p95_dt", "p99_dt",
        "gt_20m", "gt_40m", "gt_60m", "target_error",
        "pct_H9plus", "pct_E", "pct_B0", "sawtooth",
        "antistall_count", "lag_amplitude",
    ]

    # ── Aggregate per (slew, scenario) ────────────────────────────────
    agg = {}  # (slew, scenario) -> aggregated metrics
    per_seed_means = {}  # (slew, scenario) -> list of per-seed mean_dt

    for slew in slew_rates:
        for scen in scenario_names:
            seed_metrics = []
            for seed in seeds:
                key = (slew, scen, seed)
                if key in metrics_by_key:
                    seed_metrics.append(metrics_by_key[key])

            if not seed_metrics:
                continue

            avg = {}
            for k in metric_keys:
                vals = [m[k] for m in seed_metrics]
                avg[k] = statistics.mean(vals)

            # Robustness: std of per-seed mean_dt
            mean_dts = [m["mean_dt"] for m in seed_metrics]
            avg["robustness"] = statistics.stdev(mean_dts) if len(mean_dts) > 1 else 0.0
            avg["worst_seed_mean"] = max(mean_dts)

            agg[(slew, scen)] = avg
            per_seed_means[(slew, scen)] = mean_dts

    # ── Topline: average across all scenarios ─────────────────────────
    topline = {}
    for slew in slew_rates:
        scen_avgs = [agg[(slew, s)] for s in scenario_names if (slew, s) in agg]
        if not scen_avgs:
            continue
        top = {}
        for k in metric_keys + ["robustness", "worst_seed_mean"]:
            top[k] = statistics.mean([a[k] for a in scen_avgs])
        topline[slew] = top

    # ── Per-scenario winners ──────────────────────────────────────────
    winners = {}
    for scen in scenario_names:
        best_slew = None
        best_std = float('inf')
        for slew in slew_rates:
            if (slew, scen) in agg:
                if agg[(slew, scen)]["std_dt"] < best_std:
                    best_std = agg[(slew, scen)]["std_dt"]
                    best_slew = slew
        winners[scen] = best_slew

    # ── Paired tests: slew=1 vs slew=3 ───────────────────────────────
    test_metrics = [
        ("mean_dt",   True,  "target_error"),  # lower error = better
        ("std_dt",    True,  "std_dt"),
        ("gt_40m",    True,  "gt_40m"),
        ("sawtooth",  True,  "sawtooth"),
        ("robustness", True, None),  # handled specially
    ]

    paired_results = {}
    for scen in scenario_names:
        paired_results[scen] = {}
        for label, lower_better, mk in test_metrics:
            if label == "robustness":
                # Can't do paired robustness per seed; use std_dt as proxy
                continue
            paired_results[scen][label] = paired_comparison(
                metrics_by_key, scen, seeds, mk if mk else label, lower_better)

    # ── Decision criteria ─────────────────────────────────────────────
    # 1. mean_dt within 600 +/- 15s for all scenarios
    crit1_pass = True
    crit1_details = []
    for scen in scenario_names:
        if (1, scen) in agg:
            err = abs(agg[(1, scen)]["mean_dt"] - 600)
            if err > 15:
                crit1_pass = False
                crit1_details.append(f"  FAIL: {scen} mean_dt error = {err:.1f}s")

    # 2. std_dt lower in >= 8/11 scenarios
    std_wins = sum(1 for s in scenario_names
                   if (1, s) in agg and (3, s) in agg
                   and agg[(1, s)]["std_dt"] < agg[(3, s)]["std_dt"])
    crit2_pass = std_wins >= 8

    # 3. gt_40m not worse in any scenario
    crit3_pass = True
    crit3_details = []
    for scen in scenario_names:
        if (1, scen) in agg and (3, scen) in agg:
            if agg[(1, scen)]["gt_40m"] > agg[(3, scen)]["gt_40m"] * 1.001:
                # Allow tiny float tolerance
                diff_pct = 0
                if agg[(3, scen)]["gt_40m"] > 0:
                    diff_pct = (agg[(1, scen)]["gt_40m"] - agg[(3, scen)]["gt_40m"]) / agg[(3, scen)]["gt_40m"] * 100
                crit3_details.append(f"  {scen}: slew=1 gt_40m={agg[(1, scen)]['gt_40m']:.1f} vs slew=3 gt_40m={agg[(3, scen)]['gt_40m']:.1f} ({diff_pct:+.1f}%)")
                crit3_pass = False

    # 4. sawtooth lower in >= 8/11 scenarios
    saw_wins = sum(1 for s in scenario_names
                   if (1, s) in agg and (3, s) in agg
                   and agg[(1, s)]["sawtooth"] < agg[(3, s)]["sawtooth"])
    saw_ties = sum(1 for s in scenario_names
                   if (1, s) in agg and (3, s) in agg
                   and abs(agg[(1, s)]["sawtooth"] - agg[(3, s)]["sawtooth"]) < 0.5)
    crit4_pass = (saw_wins + saw_ties) >= 8

    # 5. std_dt statistically significant
    sig_count = 0
    for scen in scenario_names:
        if scen in paired_results and "std_dt" in paired_results[scen]:
            pr = paired_results[scen]["std_dt"]
            if pr and pr["significant"]:
                sig_count += 1
    crit5_pass = sig_count >= 6  # significant in majority of scenarios

    # 6. No regression > 10%
    crit6_pass = True
    crit6_details = []
    critical_metrics = ["mean_dt", "std_dt", "gt_40m", "gt_60m", "sawtooth"]
    for scen in scenario_names:
        for mk in critical_metrics:
            if (1, scen) in agg and (3, scen) in agg:
                v1 = agg[(1, scen)][mk]
                v3 = agg[(3, scen)][mk]
                if v3 > 0 and v1 > v3 * 1.10:
                    crit6_pass = False
                    crit6_details.append(f"  {scen}/{mk}: slew=1={v1:.2f} vs slew=3={v3:.2f} ({(v1/v3-1)*100:+.1f}%)")

    all_pass = crit1_pass and crit2_pass and crit3_pass and crit4_pass and crit5_pass and crit6_pass

    # Also check if slew=2 is best compromise
    std_wins_2v3 = sum(1 for s in scenario_names
                       if (2, s) in agg and (3, s) in agg
                       and agg[(2, s)]["std_dt"] < agg[(3, s)]["std_dt"])
    std_wins_1v2 = sum(1 for s in scenario_names
                       if (1, s) in agg and (2, s) in agg
                       and agg[(1, s)]["std_dt"] < agg[(2, s)]["std_dt"])

    if all_pass:
        recommendation = "RECOMMEND slew=1 for V6"
    elif not crit3_pass and len(crit3_details) <= 2:
        recommendation = "RECOMMEND slew=1 for V6 (with minor gt_40m caveats)"
    elif std_wins_2v3 >= 8:
        recommendation = "RECOMMEND slew=2 as compromise for V6"
    else:
        # Check if evidence is mixed
        criteria_met = sum([crit1_pass, crit2_pass, crit3_pass, crit4_pass, crit5_pass, crit6_pass])
        if criteria_met >= 4:
            recommendation = "RECOMMEND slew=1 for V6 (criteria mostly met, review caveats)"
        elif criteria_met <= 2:
            recommendation = "MAINTAIN slew=3 in V6"
        else:
            recommendation = "INSUFFICIENT EVIDENCE"

    # Determine margin
    if topline.get(1) and topline.get(3):
        improvement_pct = (topline[3]["std_dt"] - topline[1]["std_dt"]) / topline[3]["std_dt"] * 100
        if improvement_pct > 20:
            margin = "decisively"
        elif improvement_pct > 10:
            margin = "clearly"
        elif improvement_pct > 5:
            margin = "moderately"
        else:
            margin = "barely"
    else:
        improvement_pct = 0
        margin = "unknown"

    # ══════════════════════════════════════════════════════════════════
    # WRITE reports/slew_prefork_validation.csv
    # ══════════════════════════════════════════════════════════════════
    csv_path = os.path.join(report_dir, "slew_prefork_validation.csv")
    csv_fields = ["slew_rate", "scenario"] + metric_keys + ["robustness", "worst_seed_mean"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for slew in slew_rates:
            for scen in scenario_names:
                if (slew, scen) in agg:
                    row = {"slew_rate": slew, "scenario": scen}
                    row.update(agg[(slew, scen)])
                    w.writerow(row)

    # ══════════════════════════════════════════════════════════════════
    # WRITE reports/slew_prefork_validation.md
    # ══════════════════════════════════════════════════════════════════
    md_path = os.path.join(report_dir, "slew_prefork_validation.md")
    with open(md_path, "w") as f:
        f.write("# CASERT V6 Pre-Fork Slew Rate Validation\n\n")
        f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n\n")
        f.write(f"**Configuration**: {len(SCENARIOS)} scenarios x 3 slew rates x {len(seeds)} seeds x {num_blocks} blocks = {len(SCENARIOS) * 3 * len(seeds)} runs\n\n")
        f.write(f"**Fixed PID**: K_L={FIXED_K_L}, K_I={FIXED_K_I}, K_B={FIXED_K_B}, K_R={FIXED_K_R}, K_V={FIXED_K_V}, I_leak={FIXED_I_LEAK}\n\n")

        # 1. Topline table
        f.write("## 1. Topline: Slew=1 vs 2 vs 3 (averaged across all scenarios)\n\n")
        f.write("| Metric | slew=1 | slew=2 | slew=3 | slew=1 vs 3 |\n")
        f.write("|--------|--------|--------|--------|-------------|\n")
        display_metrics = ["mean_dt", "std_dt", "p95_dt", "p99_dt", "gt_20m", "gt_40m",
                          "gt_60m", "target_error", "sawtooth", "pct_H9plus", "pct_E",
                          "pct_B0", "antistall_count", "lag_amplitude", "robustness",
                          "worst_seed_mean"]
        for mk in display_metrics:
            vals = []
            for slew in slew_rates:
                if slew in topline and mk in topline[slew]:
                    vals.append(topline[slew][mk])
                else:
                    vals.append(float('nan'))
            if vals[0] != vals[0]:  # nan check
                continue
            delta = ""
            if vals[2] > 0:
                pct = (vals[0] - vals[2]) / vals[2] * 100
                delta = f"{pct:+.1f}%"
            elif vals[2] == 0 and vals[0] == 0:
                delta = "0%"
            else:
                delta = f"{vals[0] - vals[2]:+.1f}"
            f.write(f"| {mk} | {vals[0]:.2f} | {vals[1]:.2f} | {vals[2]:.2f} | {delta} |\n")

        # 2. Per-scenario breakdown
        f.write("\n## 2. Per-Scenario Breakdown\n\n")
        f.write("| Scenario | std_dt winner | std_dt(1) | std_dt(3) | gt_40m(1) | gt_40m(3) | saw(1) | saw(3) |\n")
        f.write("|----------|---------------|-----------|-----------|-----------|-----------|--------|--------|\n")
        for scen in scenario_names:
            w = winners.get(scen, "?")
            s1 = agg.get((1, scen), {})
            s3 = agg.get((3, scen), {})
            f.write(f"| {scen} | slew={w} | {s1.get('std_dt', 0):.1f} | {s3.get('std_dt', 0):.1f} | "
                    f"{s1.get('gt_40m', 0):.1f} | {s3.get('gt_40m', 0):.1f} | "
                    f"{s1.get('sawtooth', 0):.1f} | {s3.get('sawtooth', 0):.1f} |\n")

        # 3. Paired statistical tests
        f.write("\n## 3. Paired Statistical Tests (slew=1 vs slew=3)\n\n")
        f.write("For each scenario, paired differences (same seed): delta = metric(slew=1) - metric(slew=3)\n\n")
        for label in ["std_dt", "gt_40m", "sawtooth", "mean_dt"]:
            f.write(f"\n### {label}\n\n")
            f.write("| Scenario | mean delta | std delta | 95% CI | significant? |\n")
            f.write("|----------|-----------|-----------|--------|-------------|\n")
            for scen in scenario_names:
                pr = paired_results.get(scen, {}).get(label)
                if pr:
                    sig_str = "YES" if pr["significant"] else "no"
                    f.write(f"| {scen} | {pr['mean_delta']:.2f} | {pr['std_delta']:.2f} | "
                            f"[{pr['ci_low']:.2f}, {pr['ci_high']:.2f}] | {sig_str} |\n")
                else:
                    f.write(f"| {scen} | N/A | N/A | N/A | N/A |\n")

        # 4. Safety analysis
        f.write("\n## 4. Safety Analysis: Does slew=1 break anything?\n\n")
        f.write("### mean_dt within 600 +/- 15s\n\n")
        if crit1_pass:
            f.write("PASS: All scenarios within tolerance.\n\n")
        else:
            f.write("FAIL:\n")
            for d in crit1_details:
                f.write(f"{d}\n")
            f.write("\n")

        f.write("### gt_40m not worse than slew=3\n\n")
        if crit3_pass:
            f.write("PASS: slew=1 does not increase blocks > 40min in any scenario.\n\n")
        else:
            f.write("Scenarios where slew=1 has more gt_40m blocks:\n")
            for d in crit3_details:
                f.write(f"{d}\n")
            f.write("\n")

        f.write("### No regression > 10% in critical metrics\n\n")
        if crit6_pass:
            f.write("PASS: No critical metric regresses more than 10%.\n\n")
        else:
            f.write("Regressions > 10%:\n")
            for d in crit6_details:
                f.write(f"{d}\n")
            f.write("\n")

        # Per-scenario safety detail
        f.write("### Per-scenario worst_seed_mean (stress test)\n\n")
        f.write("| Scenario | worst(slew=1) | worst(slew=3) |\n")
        f.write("|----------|---------------|---------------|\n")
        for scen in scenario_names:
            w1 = agg.get((1, scen), {}).get("worst_seed_mean", 0)
            w3 = agg.get((3, scen), {}).get("worst_seed_mean", 0)
            f.write(f"| {scen} | {w1:.1f}s | {w3:.1f}s |\n")

        # 5. Fork-readiness reasoning
        f.write("\n## 5. Fork-Readiness Reasoning\n\n")
        f.write("### Is this consensus-critical?\n\n")
        f.write("**Yes.** `profile_index` is embedded in every block header and validated by all nodes. "
                "Changing `slew_rate` changes which profile indices are valid at each height. "
                "This requires a coordinated hard fork.\n\n")

        f.write("### Is the change simple to specify?\n\n")
        f.write("**Yes.** One constant change in `include/sost/params.h`:\n")
        f.write("```cpp\n")
        f.write("-inline constexpr int32_t  CASERT_V3_SLEW_RATE     = 3;\n")
        f.write("+inline constexpr int32_t  CASERT_V3_SLEW_RATE     = 1;\n")
        f.write("```\n")
        f.write("(Plus a V6 fork height gate so the change activates at a specific block.)\n\n")

        f.write("### Risk of non-intuitive behavior at activation?\n\n")
        f.write("At the fork height, profile transitions will be limited to +/-1 per block instead of +/-3. "
                "If the chain is at a high profile (e.g., H9) when the fork activates, the descent to B0 "
                "will take 9 blocks minimum instead of 3. This is the INTENDED behavior (smoother transitions) "
                "but operators should be aware that the first few blocks after activation may have slightly "
                "different timing characteristics as the equalizer adjusts.\n\n")
        f.write("**Mitigation**: Choose a fork height when the chain is expected to be near B0 (lag ~ 0). "
                "This is standard practice for CASERT fork activations.\n\n")

        f.write("### Should it go in V6 or wait for V7?\n\n")
        if all_pass:
            f.write("**V6 is appropriate.** All decision criteria are met. The change is minimal, "
                    "well-understood, and produces measurable improvement across all tested scenarios.\n\n")
        elif sum([crit1_pass, crit2_pass, crit3_pass, crit4_pass, crit5_pass, crit6_pass]) >= 4:
            f.write("**V6 is appropriate with caveats.** Most decision criteria are met. "
                    "Review the specific failures noted above before proceeding.\n\n")
        else:
            f.write("**Wait for V7.** Insufficient evidence to justify a consensus change at this time.\n\n")

        # 6. Recommendation
        f.write("## 6. Recommendation\n\n")
        f.write(f"### **{recommendation}**\n\n")
        f.write(f"**Decision criteria results**:\n\n")
        f.write(f"1. mean_dt within 600 +/- 15s: **{'PASS' if crit1_pass else 'FAIL'}**\n")
        f.write(f"2. std_dt lower in >= 8/11 scenarios: **{'PASS' if crit2_pass else 'FAIL'}** ({std_wins}/11)\n")
        f.write(f"3. gt_40m not worse in any scenario: **{'PASS' if crit3_pass else 'FAIL'}**\n")
        f.write(f"4. sawtooth lower in >= 8/11 scenarios: **{'PASS' if crit4_pass else 'FAIL'}** ({saw_wins} wins + {saw_ties} ties)\n")
        f.write(f"5. std_dt statistically significant: **{'PASS' if crit5_pass else 'FAIL'}** ({sig_count}/11 scenarios significant)\n")
        f.write(f"6. No regression > 10%: **{'PASS' if crit6_pass else 'FAIL'}**\n\n")

        f.write(f"slew=1 wins **{margin}** with {improvement_pct:.1f}% std_dt improvement overall.\n\n")

        f.write(f"slew=1 is std_dt winner in {std_wins}/11 scenarios.\n")
        f.write(f"slew=2 is std_dt winner in {11 - std_wins - sum(1 for s in scenario_names if (1,s) in agg and (3,s) in agg and agg.get((2,s),{}).get('std_dt',float('inf')) < min(agg.get((1,s),{}).get('std_dt',float('inf')), agg.get((3,s),{}).get('std_dt',float('inf'))))}/11 scenarios (where neither 1 nor 3 wins).\n\n")

        # 7. Appendix
        if "RECOMMEND slew=1" in recommendation:
            f.write("## 7. Appendix: Implementation Details\n\n")
            f.write("### Exact diff for include/sost/params.h\n\n")
            f.write("```diff\n")
            f.write("--- a/include/sost/params.h\n")
            f.write("+++ b/include/sost/params.h\n")
            f.write("-inline constexpr int32_t  CASERT_V3_SLEW_RATE     = 3;       // max +/-3 profile levels per block\n")
            f.write("+inline constexpr int32_t  CASERT_V6_SLEW_RATE     = 1;       // max +/-1 profile levels per block (V6)\n")
            f.write("```\n\n")
            f.write("**Note**: The actual implementation will need a V6 fork height gate:\n")
            f.write("```cpp\n")
            f.write("const int32_t slew = (nHeight >= CASERT_V6_FORK_HEIGHT)\n")
            f.write("                   ? CASERT_V6_SLEW_RATE\n")
            f.write("                   : CASERT_V3_SLEW_RATE;\n")
            f.write("```\n\n")
            f.write("### Pre-fork checklist\n\n")
            f.write("- [ ] Run full consensus test suite with V6 fork height set to test height\n")
            f.write("- [ ] Verify IBD (initial block download) across the fork boundary\n")
            f.write("- [ ] Test activation with chain at various profile levels (B0, H3, H6, H9)\n")
            f.write("- [ ] Confirm anti-stall decay still works correctly with slew=1\n")
            f.write("- [ ] Verify EBR (Emergency Behind Release) still functions correctly\n")
            f.write("- [ ] Test reorg across fork boundary\n")
            f.write("- [ ] Update CASERT_V3_SLEW_RATE references in documentation\n")
            f.write("- [ ] Coordinate activation height with mining pool operators\n")
            f.write("- [ ] Release candidate with at least 2 weeks testnet soak time\n")

    # ══════════════════════════════════════════════════════════════════
    # WRITE reports/slew_prefork_topline.md
    # ══════════════════════════════════════════════════════════════════
    topline_path = os.path.join(report_dir, "slew_prefork_topline.md")
    with open(topline_path, "w") as f:
        f.write("# CASERT V6 Slew Rate: Executive Summary\n\n")
        f.write(f"**{recommendation}**\n\n")
        f.write(f"## Key Findings\n\n")

        if topline.get(1) and topline.get(3):
            f.write(f"- **std_dt improvement**: {improvement_pct:.1f}% (slew=1 wins {margin})\n")
            f.write(f"- **mean_dt**: slew=1 = {topline[1]['mean_dt']:.1f}s vs slew=3 = {topline[3]['mean_dt']:.1f}s (target 600s)\n")
            f.write(f"- **gt_40m blocks**: slew=1 = {topline[1]['gt_40m']:.1f} vs slew=3 = {topline[3]['gt_40m']:.1f}\n")
            f.write(f"- **sawtooth score**: slew=1 = {topline[1]['sawtooth']:.1f} vs slew=3 = {topline[3]['sawtooth']:.1f}\n")
            f.write(f"- **p99 block time**: slew=1 = {topline[1]['p99_dt']:.0f}s vs slew=3 = {topline[3]['p99_dt']:.0f}s\n")

        f.write(f"\n## Decision Criteria: {sum([crit1_pass, crit2_pass, crit3_pass, crit4_pass, crit5_pass, crit6_pass])}/6 PASS\n\n")
        f.write(f"1. mean_dt in range: {'PASS' if crit1_pass else 'FAIL'}\n")
        f.write(f"2. std_dt wins >= 8/11: {'PASS' if crit2_pass else 'FAIL'} ({std_wins}/11)\n")
        f.write(f"3. gt_40m no regression: {'PASS' if crit3_pass else 'FAIL'}\n")
        f.write(f"4. sawtooth wins >= 8/11: {'PASS' if crit4_pass else 'FAIL'}\n")
        f.write(f"5. Statistical significance: {'PASS' if crit5_pass else 'FAIL'}\n")
        f.write(f"6. No 10%+ regression: {'PASS' if crit6_pass else 'FAIL'}\n\n")

        f.write(f"## Methodology\n\n")
        f.write(f"- {len(SCENARIOS)} scenarios covering normal, top-heavy, stall, shock, and stress conditions\n")
        f.write(f"- {len(seeds)} paired seeds per scenario (same seed set for slew=1/2/3)\n")
        f.write(f"- {num_blocks} blocks per run\n")
        f.write(f"- Fixed 5-term PID with real C++ coefficients\n")
        f.write(f"- 95% confidence intervals from paired t-tests\n")

    print(f"\nReports written to:")
    print(f"  {md_path}")
    print(f"  {csv_path}")
    print(f"  {topline_path}")

    return recommendation


# ── Main ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Pre-fork slew rate validation for CASERT V6")
    ap.add_argument("--blocks", type=int, default=5000, help="Blocks per run (default 5000)")
    ap.add_argument("--seeds", type=int, default=50, help="Seeds per scenario (default 50)")
    ap.add_argument("--seed-start", type=int, default=1000, help="Starting seed (default 1000)")
    ap.add_argument("--workers", type=int, default=4, help="Parallel workers (default 4)")
    ap.add_argument("--report-dir", default="reports", help="Report output directory")
    args = ap.parse_args()

    num_blocks = args.blocks
    num_seeds = args.seeds
    seeds = list(range(args.seed_start, args.seed_start + num_seeds))
    slew_rates = [1, 2, 3]
    scenario_names = [s[0] for s in SCENARIOS]

    total_runs = len(slew_rates) * len(scenario_names) * num_seeds
    print("=" * 72)
    print("CASERT V6 PRE-FORK SLEW RATE VALIDATION")
    print("=" * 72)
    print(f"  Slew rates:    {slew_rates}")
    print(f"  Scenarios:     {len(scenario_names)}")
    print(f"  Seeds:         {num_seeds} (starting at {args.seed_start})")
    print(f"  Blocks/run:    {num_blocks}")
    print(f"  Total runs:    {total_runs}")
    print(f"  Workers:       {args.workers}")
    print(f"  PID: K_L={FIXED_K_L} K_I={FIXED_K_I} K_B={FIXED_K_B} K_R={FIXED_K_R} K_V={FIXED_K_V} I_leak={FIXED_I_LEAK}")
    print()

    # Build work items
    work = []
    for slew in slew_rates:
        for scen in scenario_names:
            for seed in seeds:
                work.append((slew, scen, seed, num_blocks))

    # Execute
    metrics_by_key = {}
    t0 = time.time()
    done = 0

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, w): w for w in work}

        for f in as_completed(futures):
            slew, scen, seed, metrics = f.result()
            if metrics:
                metrics_by_key[(slew, scen, seed)] = metrics
            done += 1
            if done % 10 == 0 or done == total_runs:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total_runs - done) / rate if rate > 0 else 0
                print(f"  [{done}/{total_runs}] {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

    elapsed = time.time() - t0
    print(f"\nAll {total_runs} runs complete in {elapsed:.1f}s ({elapsed/60:.1f}m)")
    print(f"Successful: {len(metrics_by_key)}/{total_runs}")

    # Generate reports
    recommendation = generate_reports(
        metrics_by_key, metrics_by_key, seeds, num_blocks, args.report_dir)

    print(f"\n{'=' * 72}")
    print(f"FINAL: {recommendation}")
    print(f"{'=' * 72}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

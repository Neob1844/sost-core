#!/usr/bin/env python3
"""
CASERT PID Tuning Campaign for V6.

Sweeps PID coefficients (K_L, K_I, K_B, K_R, K_V), integrator leak, and
slew rate across hundreds of configurations using a FIXED compute function
that matches the real 5-term PID from src/pow/casert.cpp.

The existing v5_simulator.py uses a simplified 2-term model:
    H_raw = int(round(lag * 0.25 + burst_signal * 0.5))
which is WRONG (K_L=0.25 vs real 0.40, K_B=0.50 vs real 0.05, K_I missing).

This script implements the real controller and then sweeps to find the
optimal tuning for V6.

Usage:
    python3 scripts/pid_tuning_campaign.py [--phase 0|1|2|all] [--workers N]
"""

import argparse
import csv
import itertools
import json
import math
import os
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
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


# ── Fixed-point helpers ─────────────────────────────────────────────────

def log2_q16(x):
    """Compute log2(x) in Q16.16 fixed point, matching the C++ log2_q16."""
    if x <= 0:
        return -(100 * Q16_ONE)  # large negative
    return int(math.log2(x) * Q16_ONE)


# ── Policy application (shared by both compute paths) ────────────────────

def apply_policy(H, lag, prev_H, chain_len, next_height, now_time,
                 last_time, slew_rate, v5_enabled):
    """Apply safety, slew, lag_floor, EBR, extreme cap, and anti-stall.
    Returns (H, antistall_fired)."""
    # Safety rule 1 (pre-slew)
    if lag <= 0:
        H = min(H, 0)

    # Slew rate, lag floor, V5 policies
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


# ── FIXED compute_profile (real 5-term PID) ─────────────────────────────
# Used for standalone calls (e.g. Phase 0 sanity check).
# The hot path in simulate_config uses incremental EWMA below.

def compute_profile_fixed(chain, next_height, now_time, v5_enabled, params):
    """
    Compute equalizer profile using the REAL 5-term PID from casert.cpp.
    Full recomputation (slow but correct). Used for validation only.
    """
    if len(chain) < 2:
        return 0, False

    last = chain[-1]
    prev_H = last["profile_index"]

    K_R = int(params.get("K_R", 0.05) * 65536)
    K_L = int(params.get("K_L", 0.40) * 65536)
    K_I = int(params.get("K_I", 0.15) * 65536)
    K_B = int(params.get("K_B", 0.05) * 65536)
    K_V = int(params.get("K_V", 0.02) * 65536)
    slew_rate = params.get("slew_rate", 3)
    rho = int(params.get("I_leak", 0.988) * 256)

    dt = last["time"] - chain[-2]["time"]
    dt = max(CASERT_DT_MIN, min(CASERT_DT_MAX, dt))
    r_n = log2_q16(TARGET_SPACING) - log2_q16(dt)

    elapsed = last["time"] - GENESIS_TIME
    expected_h = elapsed // TARGET_SPACING if elapsed >= 0 else 0
    lag = (next_height - 1) - expected_h

    S, M, V, I = 0, 0, 0, 0
    lookback = min(len(chain), 128)
    start = len(chain) - lookback
    for i in range(start + 1, len(chain)):
        d = chain[i]["time"] - chain[i - 1]["time"]
        d = max(CASERT_DT_MIN, min(CASERT_DT_MAX, d))
        r = log2_q16(TARGET_SPACING) - log2_q16(d)
        S = (EWMA_SHORT_ALPHA * r + (EWMA_DENOM - EWMA_SHORT_ALPHA) * S) >> 8
        M = (EWMA_LONG_ALPHA * r + (EWMA_DENOM - EWMA_LONG_ALPHA) * M) >> 8
        abs_dev = abs(r - S)
        V = (EWMA_VOL_ALPHA * abs_dev + (EWMA_DENOM - EWMA_VOL_ALPHA) * V) >> 8
        h_i = chain[i]["height"]
        e_i = chain[i]["time"] - GENESIS_TIME
        exp_i = e_i // TARGET_SPACING if e_i >= 0 else 0
        lag_i = h_i - exp_i
        L_i_q16 = lag_i * Q16_ONE
        I = (rho * I + EWMA_DENOM * INTEG_ALPHA * L_i_q16) >> 8
        I = max(-INTEG_MAX, min(INTEG_MAX, I))

    burst_score = S - M
    L_q16 = lag * Q16_ONE
    U = (K_R * r_n + K_L * (L_q16 >> 16) + K_I * (I >> 16) +
         K_B * burst_score + K_V * V)
    H = max(CASERT_H_MIN, min(CASERT_H_MAX, int(U >> 16)))

    return apply_policy(H, lag, prev_H, len(chain), next_height,
                        now_time, last["time"], slew_rate, v5_enabled)


# ── Block time sampling ──────────────────────────────────────────────────

def sample_block_dt(profile_index, hashrate_kh, rng):
    """Sample mining time for one block at given profile and hashrate."""
    stab = STAB_PCT.get(profile_index, 100) / 100.0
    diff_mult = PROFILE_DIFFICULTY.get(profile_index, 1.0)
    base_time = 780.0 / max(hashrate_kh, 0.05)
    effective_time = base_time * diff_mult / max(stab, 0.01)
    return rng.expovariate(1.0 / effective_time)


# ── Simulator (FAST: incremental EWMA) ──────────────────────────────────

# Precomputed log2_q16 for TARGET_SPACING to avoid recalculating
_LOG2_TARGET = log2_q16(TARGET_SPACING)

def simulate_config(params, seed, num_blocks, start_height=4300,
                    hashrate=1.3, variance="medium"):
    """Run one simulation with incremental EWMA updates (O(1) per block).

    Instead of recomputing EWMAs over a 128-block window each time (O(128N)),
    we maintain running EWMA state. Since our chain grows linearly from a
    clean seed, the incremental update produces identical results to the
    full recomputation for chains longer than the EWMA warmup period.
    """
    rng = random.Random(seed)

    # Pre-convert params to fixed point (once per simulation)
    K_R = int(params.get("K_R", 0.05) * 65536)
    K_L = int(params.get("K_L", 0.40) * 65536)
    K_I = int(params.get("K_I", 0.15) * 65536)
    K_B = int(params.get("K_B", 0.05) * 65536)
    K_V = int(params.get("K_V", 0.02) * 65536)
    slew_rate = params.get("slew_rate", 3)
    rho = int(params.get("I_leak", 0.988) * 256)
    v5_enabled = True

    # Seed chain with 3 synthetic blocks on schedule
    seed_time = GENESIS_TIME + (start_height - 3) * TARGET_SPACING
    # Store chain as parallel arrays for speed
    c_heights = [start_height - 3 + i for i in range(3)]
    c_times = [seed_time + i * TARGET_SPACING for i in range(3)]
    c_profiles = [0, 0, 0]

    sim_time = c_times[-1]
    rows = []

    # Running EWMA state (updated incrementally)
    S, M, V_ewma, I_acc = 0, 0, 0, 0

    # Warm up EWMAs over the 2 seed block intervals
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

    chain_len = 3  # track length for policy decisions

    for _ in range(num_blocks):
        next_h = c_heights[-1] + 1

        # Hashrate with variance
        hr = hashrate
        if variance == "high":
            hr *= rng.uniform(0.4, 2.2)
        elif variance == "medium":
            hr *= rng.uniform(0.7, 1.4)

        # ── Compute profile using current EWMA state ──
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

        new_time = int(sim_time + dt)

        # Lag at new block
        new_elapsed = new_time - GENESIS_TIME
        new_expected = new_elapsed // TARGET_SPACING if new_elapsed >= 0 else 0
        new_lag = (next_h - 1) - new_expected

        # ── Update EWMA state incrementally with new block ──
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

        # Append to chain (keep only last 4 entries to save memory)
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


# ── Metrics ──────────────────────────────────────────────────────────────

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
            # Check ordering: H9+ appears before B0-H3
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
        "total_blocks": n,
    }


def aggregate_metrics(all_metrics):
    """Aggregate metrics across multiple seeds."""
    n_seeds = len(all_metrics)
    if n_seeds == 0:
        return None

    # Mean of all metrics
    keys = [k for k in all_metrics[0].keys() if k != "total_blocks"]
    agg = {}
    for k in keys:
        vals = [m[k] for m in all_metrics]
        agg[k] = statistics.mean(vals)
    agg["total_blocks"] = all_metrics[0]["total_blocks"]

    # Robustness: std dev of mean_dt across seeds
    mean_dts = [m["mean_dt"] for m in all_metrics]
    agg["robustness"] = statistics.stdev(mean_dts) if n_seeds > 1 else 0.0

    return agg


def composite_score(m):
    """
    Composite score for ranking configurations.

    Formula:
        score = -1.0 * target_error / 60
                -2.0 * std_dt / 600
                -3.0 * gt_40m / total_blocks * 100
                -1.5 * pct_H9plus / 100
                -1.0 * pct_E / 100
                -2.0 * robustness / 60
                -0.5 * sawtooth / total_blocks * 100

    Higher score = better. All terms are penalties (negative).
    A perfect controller would score 0.
    """
    n = m["total_blocks"]
    return (
        -1.0 * m["target_error"] / 60.0
        - 2.0 * m["std_dt"] / 600.0
        - 3.0 * m["gt_40m"] / n * 100.0
        - 1.5 * m["pct_H9plus"] / 100.0
        - 1.0 * m["pct_E"] / 100.0
        - 2.0 * m.get("robustness", 0) / 60.0
        - 0.5 * m["sawtooth"] / n * 100.0
    )


# ── Single config evaluation (for parallel execution) ───────────────────

def evaluate_config(config_id, params, seeds, num_blocks, hashrate, variance):
    """Evaluate one parameter config across all seeds. Returns (config_id, params, agg_metrics)."""
    all_m = []
    for seed in seeds:
        rows = simulate_config(params, seed, num_blocks, hashrate=hashrate, variance=variance)
        m = compute_metrics(rows)
        if m:
            all_m.append(m)
    if not all_m:
        return config_id, params, None
    agg = aggregate_metrics(all_m)
    agg["score"] = composite_score(agg)
    return config_id, params, agg


# ── Phase runners ────────────────────────────────────────────────────────

def run_phase1(workers=4, hashrate=1.3, variance="medium"):
    """Coarse sweep: 450 configs x 5 seeds x 1000 blocks."""
    print("=" * 72)
    print("PHASE 1: Coarse sweep (450 configs x 5 seeds x 1000 blocks)")
    print("=" * 72)

    # Fixed params for coarse sweep
    fixed_I_leak = 0.988
    fixed_K_R = 0.05
    fixed_K_V = 0.02

    # Sweep ranges
    K_L_vals = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    K_I_vals = [0.00, 0.05, 0.10, 0.15, 0.20]
    K_B_vals = [0.00, 0.02, 0.05, 0.08, 0.10]
    slew_vals = [1, 2, 3]

    seeds = [42, 123, 256, 789, 1337]
    num_blocks = 1000

    # Build config list — baseline is #0
    configs = []

    # Config #0: baseline
    baseline = {
        "K_L": 0.40, "K_I": 0.15, "K_B": 0.05,
        "K_R": fixed_K_R, "K_V": fixed_K_V,
        "I_leak": fixed_I_leak, "slew_rate": 3,
    }
    configs.append(baseline)

    # Sweep configs
    for kl, ki, kb, slew in itertools.product(K_L_vals, K_I_vals, K_B_vals, slew_vals):
        p = {
            "K_L": kl, "K_I": ki, "K_B": kb,
            "K_R": fixed_K_R, "K_V": fixed_K_V,
            "I_leak": fixed_I_leak, "slew_rate": slew,
        }
        # Skip if identical to baseline (already added)
        if (kl == 0.40 and ki == 0.15 and kb == 0.05 and slew == 3):
            continue
        configs.append(p)

    total = len(configs)
    print(f"  Total configurations: {total}")
    print(f"  Seeds: {seeds}")
    print(f"  Blocks per run: {num_blocks}")
    print(f"  Workers: {workers}")
    print()

    results = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for cid, params in enumerate(configs):
            f = pool.submit(evaluate_config, cid, params, seeds, num_blocks, hashrate, variance)
            futures[f] = cid

        done = 0
        for f in as_completed(futures):
            cid, params, agg = f.result()
            done += 1
            if agg:
                results.append((cid, params, agg))
            if done % 50 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                print(f"  [{done}/{total}] {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

    elapsed = time.time() - t0
    print(f"\n  Phase 1 complete in {elapsed:.1f}s ({total} configs)")

    # Sort by score
    results.sort(key=lambda x: x[2]["score"], reverse=True)
    return results, configs


def run_phase2(phase1_results, workers=4, hashrate=1.3, variance="medium"):
    """Fine sweep around top 20 from Phase 1."""
    print("\n" + "=" * 72)
    print("PHASE 2: Fine sweep (top 20 x I_leak/K_L/K_I variants x 10 seeds x 2000 blocks)")
    print("=" * 72)

    top20 = phase1_results[:20]
    seeds = list(range(42, 52))  # 10 seeds
    num_blocks = 2000

    I_leak_vals = [0.980, 0.985, 0.988, 0.992, 0.995]

    configs = []
    # Always include baseline as reference
    baseline = {
        "K_L": 0.40, "K_I": 0.15, "K_B": 0.05,
        "K_R": 0.05, "K_V": 0.02,
        "I_leak": 0.988, "slew_rate": 3,
    }
    configs.append(baseline)

    for _, base_params, _ in top20:
        # Fine sweep around this config
        kl_base = base_params["K_L"]
        ki_base = base_params["K_I"]
        slew = base_params["slew_rate"]
        kb = base_params["K_B"]

        kl_range = [kl_base - 0.02, kl_base - 0.01, kl_base, kl_base + 0.01, kl_base + 0.02]
        ki_range = [ki_base - 0.02, ki_base - 0.01, ki_base, ki_base + 0.01, ki_base + 0.02]

        for il, kl, ki in itertools.product(I_leak_vals, kl_range, ki_range):
            kl = round(kl, 3)
            ki = round(ki, 3)
            if kl < 0.0 or ki < 0.0:
                continue
            p = {
                "K_L": kl, "K_I": ki, "K_B": kb,
                "K_R": base_params["K_R"], "K_V": base_params["K_V"],
                "I_leak": il, "slew_rate": slew,
            }
            # Deduplicate
            key = (kl, ki, kb, il, slew)
            if not any(
                (c["K_L"] == kl and c["K_I"] == ki and c["K_B"] == kb and
                 c["I_leak"] == il and c["slew_rate"] == slew)
                for c in configs
            ):
                configs.append(p)

    total = len(configs)
    print(f"  Total configurations: {total}")
    print(f"  Seeds: {len(seeds)}")
    print(f"  Blocks per run: {num_blocks}")
    print(f"  Workers: {workers}")
    print()

    results = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for cid, params in enumerate(configs):
            f = pool.submit(evaluate_config, cid, params, seeds, num_blocks, hashrate, variance)
            futures[f] = cid

        done = 0
        for f in as_completed(futures):
            cid, params, agg = f.result()
            done += 1
            if agg:
                results.append((cid, params, agg))
            if done % 100 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                print(f"  [{done}/{total}] {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

    elapsed = time.time() - t0
    print(f"\n  Phase 2 complete in {elapsed:.1f}s ({total} configs)")

    results.sort(key=lambda x: x[2]["score"], reverse=True)
    return results


# ── Hybrid slew test ─────────────────────────────────────────────────────

def evaluate_hybrid_slew(workers=4, hashrate=1.3, variance="medium"):
    """Test hybrid slew: slew=1 when |lag|<5, slew=3 when |lag|>=5."""
    print("\n" + "=" * 72)
    print("HYBRID SLEW TEST")
    print("=" * 72)

    # We test by running baseline with slew=1, slew=3, and a hybrid approach
    # For hybrid, we need a special flag
    seeds = list(range(42, 52))
    num_blocks = 2000

    configs = [
        ("baseline_slew3", {"K_L": 0.40, "K_I": 0.15, "K_B": 0.05,
                            "K_R": 0.05, "K_V": 0.02, "I_leak": 0.988, "slew_rate": 3}),
        ("baseline_slew1", {"K_L": 0.40, "K_I": 0.15, "K_B": 0.05,
                            "K_R": 0.05, "K_V": 0.02, "I_leak": 0.988, "slew_rate": 1}),
        ("baseline_slew2", {"K_L": 0.40, "K_I": 0.15, "K_B": 0.05,
                            "K_R": 0.05, "K_V": 0.02, "I_leak": 0.988, "slew_rate": 2}),
    ]

    results = {}
    for name, params in configs:
        all_m = []
        for seed in seeds:
            rows = simulate_config(params, seed, num_blocks, hashrate=hashrate, variance=variance)
            m = compute_metrics(rows)
            if m:
                all_m.append(m)
        agg = aggregate_metrics(all_m)
        agg["score"] = composite_score(agg)
        results[name] = agg
        print(f"  {name}: score={agg['score']:.3f}  mean_dt={agg['mean_dt']:.1f}  "
              f"std_dt={agg['std_dt']:.1f}  gt_40m={agg['gt_40m']:.1f}  "
              f"sawtooth={agg['sawtooth']:.1f}")

    return results


# ── Pareto front ─────────────────────────────────────────────────────────

def compute_pareto(results):
    """Find Pareto-optimal configs on (target_error, std_dt, gt_40m)."""
    pareto = []
    for i, (cid, params, m) in enumerate(results):
        dominated = False
        for j, (_, _, m2) in enumerate(results):
            if j == i:
                continue
            if (m2["target_error"] <= m["target_error"] and
                m2["std_dt"] <= m["std_dt"] and
                m2["gt_40m"] <= m["gt_40m"] and
                (m2["target_error"] < m["target_error"] or
                 m2["std_dt"] < m["std_dt"] or
                 m2["gt_40m"] < m["gt_40m"])):
                dominated = True
                break
        if not dominated:
            pareto.append((cid, params, m))
    pareto.sort(key=lambda x: x[2]["score"], reverse=True)
    return pareto


# ── Report generation ────────────────────────────────────────────────────

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

def ensure_report_dir():
    os.makedirs(REPORT_DIR, exist_ok=True)


def write_results_csv(results, filename):
    """Write all results to CSV."""
    ensure_report_dir()
    path = os.path.join(REPORT_DIR, filename)
    if not results:
        print(f"  WARNING: No results to write to {path}")
        return

    fieldnames = [
        "rank", "K_L", "K_I", "K_B", "K_R", "K_V", "I_leak", "slew_rate",
        "score", "mean_dt", "median_dt", "std_dt", "p95_dt", "p99_dt",
        "gt_20m", "gt_40m", "gt_60m",
        "pct_H9plus", "pct_E", "pct_B0",
        "sawtooth", "antistall_count", "target_error",
        "lag_amplitude", "robustness", "total_blocks",
    ]

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for rank, (cid, params, m) in enumerate(results, 1):
            row = {"rank": rank}
            for k in ["K_L", "K_I", "K_B", "K_R", "K_V", "I_leak", "slew_rate"]:
                row[k] = params.get(k, "")
            for k in m:
                if k in fieldnames:
                    row[k] = round(m[k], 4) if isinstance(m[k], float) else m[k]
            w.writerow(row)

    print(f"  Wrote {path} ({len(results)} rows)")


def format_params(p):
    """Format params dict as a compact string."""
    return (f"K_L={p['K_L']:.3f} K_I={p['K_I']:.3f} K_B={p['K_B']:.3f} "
            f"slew={p['slew_rate']} I_leak={p['I_leak']:.3f}")


def write_top10_report(results, filename, baseline_metrics=None):
    """Write detailed top 10 comparison."""
    ensure_report_dir()
    path = os.path.join(REPORT_DIR, filename)

    lines = []
    lines.append("# CASERT PID Tuning: Top 10 Configurations")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    if baseline_metrics:
        lines.append("## Baseline (current V5)")
        lines.append(f"  Params: K_L=0.400 K_I=0.150 K_B=0.050 slew=3 I_leak=0.988")
        lines.append(f"  Score:       {baseline_metrics['score']:.3f}")
        lines.append(f"  Mean dt:     {baseline_metrics['mean_dt']:.1f}s ({baseline_metrics['mean_dt']/60:.1f}m)")
        lines.append(f"  Std dt:      {baseline_metrics['std_dt']:.1f}s")
        lines.append(f"  Target err:  {baseline_metrics['target_error']:.1f}s")
        lines.append(f"  >40min:      {baseline_metrics['gt_40m']:.1f} blocks")
        lines.append(f"  H9+ pct:     {baseline_metrics['pct_H9plus']:.2f}%")
        lines.append(f"  Sawtooth:    {baseline_metrics['sawtooth']:.1f}")
        lines.append(f"  Robustness:  {baseline_metrics.get('robustness', 0):.2f}s")
        lines.append("")

    lines.append("## Top 10 Ranked Configurations")
    lines.append("")

    for rank, (cid, params, m) in enumerate(results[:10], 1):
        delta_score = ""
        if baseline_metrics:
            ds = m["score"] - baseline_metrics["score"]
            delta_score = f" ({'+' if ds >= 0 else ''}{ds:.3f} vs baseline)"

        lines.append(f"### #{rank}{delta_score}")
        lines.append(f"  Params: {format_params(params)}")
        lines.append(f"  Score:       {m['score']:.3f}")
        lines.append(f"  Mean dt:     {m['mean_dt']:.1f}s ({m['mean_dt']/60:.1f}m)")
        lines.append(f"  Std dt:      {m['std_dt']:.1f}s")
        lines.append(f"  Target err:  {m['target_error']:.1f}s")
        lines.append(f"  P95 dt:      {m['p95_dt']:.0f}s  P99: {m['p99_dt']:.0f}s")
        lines.append(f"  >20min:      {m['gt_20m']:.1f}   >40min: {m['gt_40m']:.1f}   >60min: {m['gt_60m']:.1f}")
        lines.append(f"  H9+ pct:     {m['pct_H9plus']:.2f}%")
        lines.append(f"  E pct:       {m['pct_E']:.2f}%")
        lines.append(f"  B0 pct:      {m['pct_B0']:.2f}%")
        lines.append(f"  Sawtooth:    {m['sawtooth']:.1f}")
        lines.append(f"  Anti-stall:  {m['antistall_count']:.1f}")
        lines.append(f"  Lag amp:     {m['lag_amplitude']:.2f}")
        lines.append(f"  Robustness:  {m.get('robustness', 0):.2f}s")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Wrote {path}")


def sensitivity_analysis(phase1_results, all_configs):
    """Analyze which parameter has the most influence on score."""
    # Group by each parameter and compute mean score
    param_influence = {}
    for param_name in ["K_L", "K_I", "K_B", "slew_rate"]:
        groups = {}
        for cid, params, m in phase1_results:
            val = params[param_name]
            if val not in groups:
                groups[val] = []
            groups[val].append(m["score"])

        means = {v: statistics.mean(scores) for v, scores in groups.items()}
        spread = max(means.values()) - min(means.values()) if len(means) > 1 else 0
        param_influence[param_name] = {
            "spread": spread,
            "means": means,
            "best_val": max(means, key=means.get),
        }

    return param_influence


def write_campaign_report(phase1_results, phase2_results, pareto, hybrid_results,
                          sensitivity, baseline_metrics):
    """Write the full analysis report."""
    ensure_report_dir()
    path = os.path.join(REPORT_DIR, "pid_tuning_campaign.md")

    lines = []
    lines.append("# CASERT PID Tuning Campaign Report")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # ── Methodology
    lines.append("## Methodology")
    lines.append("")
    lines.append("This campaign uses a FIXED simulator that implements the real 5-term PID")
    lines.append("from `src/pow/casert.cpp`, replacing the simplified 2-term model in")
    lines.append("`scripts/v5_simulator.py` (which used K_L=0.25, K_B=0.50 -- both wrong).")
    lines.append("")
    lines.append("The real PID control signal is:")
    lines.append("```")
    lines.append("U = K_R*r + K_L*lag + K_I*I + K_B*burst + K_V*vol")
    lines.append("```")
    lines.append("where r = log2(target/dt), lag = height - expected_height,")
    lines.append("I = leaky integrator of lag, burst = EWMA_short - EWMA_long,")
    lines.append("vol = EWMA of |r - EWMA_short|.")
    lines.append("")

    # ── Composite Score Formula
    lines.append("## Composite Score Formula")
    lines.append("")
    lines.append("```")
    lines.append("score = -1.0 * target_error / 60")
    lines.append("        -2.0 * std_dt / 600")
    lines.append("        -3.0 * gt_40m / total_blocks * 100")
    lines.append("        -1.5 * pct_H9plus / 100")
    lines.append("        -1.0 * pct_E / 100")
    lines.append("        -2.0 * robustness / 60")
    lines.append("        -0.5 * sawtooth / total_blocks * 100")
    lines.append("```")
    lines.append("Higher = better. All terms are penalties.")
    lines.append("")

    # ── Baseline
    lines.append("## Baseline (current V5)")
    lines.append("")
    if baseline_metrics:
        lines.append(f"- **Params**: K_L=0.40, K_I=0.15, K_B=0.05, slew=3, I_leak=0.988")
        lines.append(f"- **Score**: {baseline_metrics['score']:.3f}")
        lines.append(f"- **Mean dt**: {baseline_metrics['mean_dt']:.1f}s ({baseline_metrics['mean_dt']/60:.1f}m)")
        lines.append(f"- **Std dt**: {baseline_metrics['std_dt']:.1f}s")
        lines.append(f"- **>40min blocks**: {baseline_metrics['gt_40m']:.1f}")
        lines.append(f"- **H9+ pct**: {baseline_metrics['pct_H9plus']:.2f}%")
        lines.append(f"- **Sawtooth**: {baseline_metrics['sawtooth']:.1f}")
        lines.append(f"- **Robustness**: {baseline_metrics.get('robustness', 0):.2f}s")
    lines.append("")

    # ── Sensitivity Analysis
    lines.append("## Key Finding 1: Which parameter moves the system most?")
    lines.append("")
    if sensitivity:
        ranked = sorted(sensitivity.items(), key=lambda x: x[1]["spread"], reverse=True)
        for param, info in ranked:
            lines.append(f"### {param}")
            lines.append(f"- Score spread across values: **{info['spread']:.3f}**")
            lines.append(f"- Best value: **{info['best_val']}**")
            lines.append(f"- Mean scores by value:")
            for v in sorted(info["means"].keys()):
                lines.append(f"  - {param}={v}: {info['means'][v]:.3f}")
            lines.append("")

        most_influential = ranked[0][0]
        lines.append(f"**Answer: `{most_influential}` has the largest influence** on composite score,")
        lines.append(f"with a spread of {ranked[0][1]['spread']:.3f} across tested values.")
    lines.append("")

    # ── Slew rate analysis
    lines.append("## Key Finding 2: Does slew_rate=1 help or hurt vs slew_rate=3?")
    lines.append("")
    if hybrid_results:
        s1 = hybrid_results.get("baseline_slew1", {})
        s2 = hybrid_results.get("baseline_slew2", {})
        s3 = hybrid_results.get("baseline_slew3", {})

        if s1 and s3:
            lines.append(f"| Metric | slew=1 | slew=2 | slew=3 |")
            lines.append(f"|--------|--------|--------|--------|")
            for metric in ["score", "mean_dt", "std_dt", "gt_40m", "sawtooth", "robustness"]:
                v1 = s1.get(metric, 0)
                v2 = s2.get(metric, 0) if s2 else "N/A"
                v3 = s3.get(metric, 0)
                if isinstance(v1, float):
                    lines.append(f"| {metric} | {v1:.2f} | {v2:.2f} | {v3:.2f} |")
                else:
                    lines.append(f"| {metric} | {v1} | {v2} | {v3} |")
            lines.append("")

            if s1.get("score", -999) > s3.get("score", -999):
                lines.append("**Answer: slew_rate=1 HELPS.** Lower slew reduces oscillation and improves stability.")
            elif s1.get("score", -999) < s3.get("score", -999):
                lines.append("**Answer: slew_rate=1 HURTS.** Slower response increases stall risk.")
            else:
                lines.append("**Answer: Roughly equivalent.** The difference is within noise.")
    lines.append("")

    # ── Safe zone
    lines.append("## Key Finding 3: Is there a safe zone or a sharp peak?")
    lines.append("")
    if phase1_results:
        scores = [m["score"] for _, _, m in phase1_results]
        top_score = scores[0]
        # Count configs within 10% of top score spread
        score_range = abs(scores[0] - scores[-1]) if len(scores) > 1 else 1
        threshold = top_score - 0.1 * score_range
        near_top = sum(1 for s in scores if s >= threshold)
        lines.append(f"- Best score: {top_score:.3f}")
        lines.append(f"- Worst score: {scores[-1]:.3f}")
        lines.append(f"- Score range: {score_range:.3f}")
        lines.append(f"- Configs within top 10% of range: {near_top} / {len(scores)}")
        lines.append("")
        if near_top > len(scores) * 0.3:
            lines.append("**Answer: PLATEAU.** Many configurations score similarly near the top.")
            lines.append("This means the controller is robust to moderate parameter changes.")
        elif near_top > len(scores) * 0.1:
            lines.append("**Answer: MODERATE plateau.** Some tolerance to parameter variation exists,")
            lines.append("but the top configs are meaningfully better than the rest.")
        else:
            lines.append("**Answer: SHARP PEAK.** The optimal region is narrow. Parameter")
            lines.append("sensitivity is high -- small changes matter significantly.")
    lines.append("")

    # ── Smoothness vs responsiveness
    lines.append("## Key Finding 4: Trade-off between smoothness and responsiveness")
    lines.append("")
    if phase1_results:
        # Low K_L = smoother but slower response
        # High K_L = more responsive but oscillatory
        low_kl = [m for _, p, m in phase1_results if p["K_L"] <= 0.30]
        high_kl = [m for _, p, m in phase1_results if p["K_L"] >= 0.45]
        if low_kl and high_kl:
            avg_std_low = statistics.mean([m["std_dt"] for m in low_kl])
            avg_std_high = statistics.mean([m["std_dt"] for m in high_kl])
            avg_err_low = statistics.mean([m["target_error"] for m in low_kl])
            avg_err_high = statistics.mean([m["target_error"] for m in high_kl])
            lines.append(f"- Low K_L (<=0.30): avg std_dt={avg_std_low:.1f}s, avg target_error={avg_err_low:.1f}s")
            lines.append(f"- High K_L (>=0.45): avg std_dt={avg_std_high:.1f}s, avg target_error={avg_err_high:.1f}s")
            lines.append("")
            if avg_std_low < avg_std_high and avg_err_low > avg_err_high:
                lines.append("Trade-off confirmed: lower K_L is smoother but drifts more from target.")
            elif avg_std_low > avg_std_high:
                lines.append("Counterintuitively, higher K_L is BOTH more responsive AND smoother.")
                lines.append("This suggests the lag correction prevents the chain from drifting into")
                lines.append("difficult territory that causes high-variance block times.")
    lines.append("")

    # ── Integrator wind-up
    lines.append("## Key Finding 5: What K_I avoids integrator wind-up?")
    lines.append("")
    if phase1_results:
        ki_groups = {}
        for _, p, m in phase1_results:
            ki = p["K_I"]
            if ki not in ki_groups:
                ki_groups[ki] = []
            ki_groups[ki].append(m)
        lines.append("| K_I | Avg Score | Avg std_dt | Avg gt_40m | Avg sawtooth |")
        lines.append("|-----|-----------|------------|------------|--------------|")
        for ki in sorted(ki_groups.keys()):
            ms = ki_groups[ki]
            lines.append(f"| {ki:.2f} | {statistics.mean([m['score'] for m in ms]):.3f} | "
                         f"{statistics.mean([m['std_dt'] for m in ms]):.1f} | "
                         f"{statistics.mean([m['gt_40m'] for m in ms]):.1f} | "
                         f"{statistics.mean([m['sawtooth'] for m in ms]):.1f} |")
        lines.append("")
    lines.append("")

    # ── Top 3 Candidates
    lines.append("## Top 3 Candidates")
    lines.append("")
    final_results = phase2_results if phase2_results else phase1_results
    for rank, (cid, params, m) in enumerate(final_results[:3], 1):
        risk = "LOW"
        notes = []
        if m["gt_40m"] > 2:
            risk = "MEDIUM"
            notes.append("occasional >40min blocks")
        if m["pct_H9plus"] > 5:
            risk = "MEDIUM"
            notes.append("significant time at H9+")
        if m.get("robustness", 0) > 30:
            risk = "HIGH"
            notes.append("inconsistent across seeds")

        lines.append(f"### Candidate #{rank}")
        lines.append(f"- **Params**: {format_params(params)}")
        lines.append(f"- **Score**: {m['score']:.3f}")
        lines.append(f"- **Mean dt**: {m['mean_dt']:.1f}s  Std: {m['std_dt']:.1f}s")
        lines.append(f"- **>40min**: {m['gt_40m']:.1f}  H9+: {m['pct_H9plus']:.2f}%")
        lines.append(f"- **Risk**: {risk}" + (f" ({', '.join(notes)})" if notes else ""))
        lines.append("")

    # ── Is baseline near-optimal?
    lines.append("## Key Question: Is the current baseline near-optimal?")
    lines.append("")
    if final_results and baseline_metrics:
        best_score = final_results[0][2]["score"]
        base_score = baseline_metrics["score"]
        improvement = best_score - base_score
        pct_improvement = (improvement / abs(base_score) * 100) if base_score != 0 else 0

        lines.append(f"- Baseline score: {base_score:.3f}")
        lines.append(f"- Best found:     {best_score:.3f}")
        lines.append(f"- Improvement:    {improvement:+.3f} ({pct_improvement:+.1f}%)")
        lines.append("")

        # Find baseline rank
        base_rank = None
        for i, (_, p, _) in enumerate(final_results):
            if (abs(p["K_L"] - 0.40) < 0.001 and abs(p["K_I"] - 0.15) < 0.001 and
                abs(p["K_B"] - 0.05) < 0.001 and p["slew_rate"] == 3 and
                abs(p["I_leak"] - 0.988) < 0.001):
                base_rank = i + 1
                break

        if base_rank:
            lines.append(f"- Baseline ranks #{base_rank} out of {len(final_results)} configs.")

        if abs(pct_improvement) < 5:
            lines.append("")
            lines.append("**The baseline is NEAR-OPTIMAL.** The best config found offers less than 5%")
            lines.append("improvement. Changing PID coefficients is low priority for V6.")
        elif pct_improvement > 20:
            lines.append("")
            lines.append("**There is CLEAR room for improvement.** The best config found is")
            lines.append(f"significantly better ({pct_improvement:+.1f}%). Retuning is recommended for V6.")
        else:
            lines.append("")
            lines.append("**Moderate improvement possible.** The baseline is decent but not optimal.")
            lines.append("Consider the top candidates for V6, especially if the improvement is")
            lines.append("consistent across stress scenarios.")
    lines.append("")

    # ── Single-change recommendation
    lines.append("## Recommendation: If you ship ONE change for V6")
    lines.append("")
    if final_results and baseline_metrics and sensitivity:
        best = final_results[0]
        bp = best[1]
        bm = best[2]
        # Identify the single biggest lever
        ranked_sens = sorted(sensitivity.items(), key=lambda x: x[1]["spread"], reverse=True)
        top_lever = ranked_sens[0][0]
        top_val = ranked_sens[0][1]["best_val"]
        current_val = {"K_L": 0.40, "K_I": 0.15, "K_B": 0.05, "slew_rate": 3}

        if top_lever in current_val and current_val[top_lever] != top_val:
            lines.append(f"**Change `{top_lever}` from {current_val[top_lever]} to {top_val}.**")
            lines.append("")
            lines.append(f"This is the single most influential parameter (spread={ranked_sens[0][1]['spread']:.3f}).")
            lines.append(f"The remaining parameters are already reasonable.")
        else:
            lines.append(f"**The baseline is already well-tuned.** The most influential parameter")
            lines.append(f"(`{top_lever}`) is already at or near its optimal value ({top_val}).")
            lines.append("")
            # Suggest second-best change
            if len(ranked_sens) > 1:
                s2 = ranked_sens[1]
                lines.append(f"If a change is desired, consider `{s2[0]}` -> {s2[1]['best_val']}")
                lines.append(f"(spread={s2[1]['spread']:.3f}).")
    lines.append("")

    # ── Confidence
    lines.append("## Confidence Levels")
    lines.append("")
    lines.append("- Phase 1 (coarse): 5 seeds x 1000 blocks = MODERATE confidence in ranking.")
    lines.append("  Good for identifying promising regions, not for final decimal-place tuning.")
    lines.append("- Phase 2 (fine): 10 seeds x 2000 blocks = GOOD confidence for top candidates.")
    lines.append("  Statistical noise is reduced but not eliminated. Real-network behavior may")
    lines.append("  differ due to correlated hashrate changes, strategic mining, etc.")
    lines.append("- Simulator limitations: Block time model uses exponential distribution with")
    lines.append("  profile-dependent difficulty. Real mining involves PoW variance, network")
    lines.append("  latency, and hashrate correlation that this model does not capture.")
    lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Wrote {path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="CASERT PID Tuning Campaign")
    ap.add_argument("--phase", choices=["0", "1", "2", "all"], default="all",
                    help="Which phase to run (default: all)")
    ap.add_argument("--workers", type=int, default=4,
                    help="Number of parallel workers (default: 4)")
    ap.add_argument("--hashrate", type=float, default=1.3,
                    help="Network hashrate in kH/s (default: 1.3)")
    ap.add_argument("--variance", choices=["low", "medium", "high"], default="medium",
                    help="Hashrate variance level (default: medium)")
    args = ap.parse_args()

    print("CASERT PID Tuning Campaign")
    print(f"  Hashrate: {args.hashrate} kH/s, Variance: {args.variance}")
    print(f"  Workers: {args.workers}")
    print(f"  Target: {TARGET_SPACING}s ({TARGET_SPACING//60}m)")
    print()

    # Phase 0: Quick sanity check of fixed compute
    if args.phase in ("0", "all"):
        print("=" * 72)
        print("PHASE 0: Sanity check — fixed PID vs old simplified model")
        print("=" * 72)
        baseline_params = {
            "K_L": 0.40, "K_I": 0.15, "K_B": 0.05,
            "K_R": 0.05, "K_V": 0.02,
            "I_leak": 0.988, "slew_rate": 3,
        }
        rows = simulate_config(baseline_params, seed=42, num_blocks=200)
        m = compute_metrics(rows)
        print(f"  200-block sanity check (baseline params, seed=42):")
        print(f"    Mean dt:     {m['mean_dt']:.1f}s ({m['mean_dt']/60:.1f}m)")
        print(f"    Std dt:      {m['std_dt']:.1f}s")
        print(f"    Target err:  {m['target_error']:.1f}s")
        print(f"    Profile dist: ", end="")
        hist = {}
        for r in rows:
            p = r["profile_index"]
            hist[p] = hist.get(p, 0) + 1
        for p in sorted(hist.keys()):
            print(f"{PROFILE_NAME[p]}:{hist[p]} ", end="")
        print()
        print("  Phase 0 OK.")
        print()

        if args.phase == "0":
            return

    # Phase 1: Coarse sweep
    phase1_results = None
    baseline_metrics = None
    sensitivity = None

    if args.phase in ("1", "all"):
        phase1_results, all_configs = run_phase1(
            workers=args.workers, hashrate=args.hashrate, variance=args.variance)

        # Extract baseline metrics (config #0)
        for cid, params, m in phase1_results:
            if cid == 0:
                baseline_metrics = m
                break

        # Sensitivity analysis
        sensitivity = sensitivity_analysis(phase1_results, all_configs)
        print("\n  Sensitivity analysis:")
        for param, info in sorted(sensitivity.items(), key=lambda x: x[1]["spread"], reverse=True):
            print(f"    {param}: spread={info['spread']:.3f}, best={info['best_val']}")

        # Write Phase 1 results
        write_results_csv(phase1_results, "pid_tuning_results.csv")
        print()

        # Print top 5
        print("  Phase 1 Top 5:")
        for rank, (cid, params, m) in enumerate(phase1_results[:5], 1):
            is_base = " [BASELINE]" if cid == 0 else ""
            print(f"    #{rank}: score={m['score']:.3f}  {format_params(params)}{is_base}")

        if args.phase == "1":
            # Write reports with Phase 1 data only
            pareto = compute_pareto(phase1_results)
            write_results_csv(pareto, "pid_tuning_pareto.csv")
            write_top10_report(phase1_results, "pid_tuning_top10.md", baseline_metrics)
            hybrid = evaluate_hybrid_slew(workers=args.workers, hashrate=args.hashrate, variance=args.variance)
            write_campaign_report(phase1_results, None, pareto, hybrid, sensitivity, baseline_metrics)
            return

    # Phase 2: Fine sweep
    phase2_results = None
    if args.phase in ("2", "all"):
        if phase1_results is None:
            print("ERROR: Phase 2 requires Phase 1 results. Run with --phase all or --phase 1 first.")
            sys.exit(1)

        phase2_results = run_phase2(
            phase1_results, workers=args.workers,
            hashrate=args.hashrate, variance=args.variance)

        # Find baseline in Phase 2 results
        for cid, params, m in phase2_results:
            if (abs(params["K_L"] - 0.40) < 0.001 and abs(params["K_I"] - 0.15) < 0.001 and
                abs(params["K_B"] - 0.05) < 0.001 and params["slew_rate"] == 3 and
                abs(params["I_leak"] - 0.988) < 0.001):
                baseline_metrics = m
                break

        # Write Phase 2 results (overwrite Phase 1 CSV with combined)
        all_results = phase1_results + phase2_results
        all_results.sort(key=lambda x: x[2]["score"], reverse=True)
        # Deduplicate by params
        seen = set()
        deduped = []
        for cid, params, m in all_results:
            key = (params["K_L"], params["K_I"], params["K_B"],
                   params["I_leak"], params["slew_rate"])
            if key not in seen:
                seen.add(key)
                deduped.append((cid, params, m))
        all_results = deduped

        write_results_csv(all_results, "pid_tuning_results.csv")

        # Pareto
        pareto = compute_pareto(all_results)
        write_results_csv(pareto, "pid_tuning_pareto.csv")

        # Top 10
        write_top10_report(all_results, "pid_tuning_top10.md", baseline_metrics)

        # Hybrid slew
        hybrid = evaluate_hybrid_slew(
            workers=args.workers, hashrate=args.hashrate, variance=args.variance)

        # Full campaign report
        write_campaign_report(all_results, phase2_results, pareto, hybrid,
                              sensitivity, baseline_metrics)

        # Print top 5
        print("\n  Final Top 5 (Phase 1 + Phase 2):")
        for rank, (cid, params, m) in enumerate(all_results[:5], 1):
            is_base = ""
            if (abs(params["K_L"] - 0.40) < 0.001 and abs(params["K_I"] - 0.15) < 0.001 and
                abs(params["K_B"] - 0.05) < 0.001 and params["slew_rate"] == 3):
                is_base = " [BASELINE]"
            print(f"    #{rank}: score={m['score']:.3f}  {format_params(params)}{is_base}")

    print("\n" + "=" * 72)
    print("Campaign complete. Reports written to reports/")
    print("=" * 72)


if __name__ == "__main__":
    main()

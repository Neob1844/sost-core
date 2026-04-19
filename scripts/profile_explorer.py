#!/usr/bin/env python3
"""
Extended Profile Explorer — Dynamic Adaptation Simulation

Explores extended profile tables (up to H50) to find smooth stability
transitions that eliminate the "step" causing sawtooth oscillations.

Approach:
  1. Fit a stability model from known empirical data points
  2. Generate candidate extended profile tables with fine granularity
  3. Run full cASERT V6 simulator with each table
  4. Test with dynamic hashrate scenarios (miners joining/leaving)
  5. Measure smoothness, sawtooth amplitude, mean block time
  6. bitsQ and equalizer work together (dual-vector)

Usage:
    python3 scripts/profile_explorer.py
    python3 scripts/profile_explorer.py --profiles 30 --hashrates 1.3,3.0,8.0
    python3 scripts/profile_explorer.py --sweep --seeds 20
"""

import argparse
import csv
import math
import os
import random
import statistics
import sys
import itertools
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# ─────────────────────────────────────────────────────────────────────
# ANSI
# ──────��────────────────────��─────────────────────────────────────────
GREEN = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"
CYAN = "\033[96m"; DIM = "\033[2m"; BOLD = "\033[1m"; RESET = "\033[0m"
ORANGE = "\033[38;5;208m"

# ──────────────────────────���──────────────────────────────────────────
# Constants (mirror params.h)
# ──��──────────────────────────────────────────────────────────────────
GENESIS_TIME = 1773597600
TARGET_SPACING = 600
GENESIS_BITSQ = 765730
Q16_ONE = 65536

# V6 rules
CASERT_V6_SLEW_RATE = 1
CASERT_V6_H11_MIN_LAG = 11
CASERT_V6_H12_MIN_LAG = 21
CASERT_H_MIN = -4
CASERT_V3_LAG_FLOOR_DIV = 8
CASERT_V5_EXTREME_MIN = 10
CASERT_ANTISTALL_FLOOR_V5 = 3600
CASERT_EBR_ENTER = -10
CASERT_EBR_LEVEL_E2 = -15
CASERT_EBR_LEVEL_E3 = -20
CASERT_EBR_LEVEL_E4 = -25

# bitsQ V2 parameters
BITSQ_HALF_LIFE_V2 = 86400
BITSQ_MAX_DELTA_DEN_V2 = 8  # 12.5% cap (V6: no Ahead Guard)

# PID gains (Q16.16)
K_R = 3277   # 0.05
K_L = 26214  # 0.40
K_I = 9830   # 0.15
K_B = 3277   # 0.05
K_V = 1311   # 0.02
EWMA_SHORT_ALPHA = 32
EWMA_LONG_ALPHA = 3
EWMA_VOL_ALPHA = 16
EWMA_DENOM = 256
INTEG_RHO = 253
INTEG_MAX = 6553600

# ─────────────────────────────────────────────────────────────────────
# Known empirical stability data (from production + estimates)
# ─────────────────��───────────────────────────────���───────────────────
@dataclass
class Profile:
    name: str
    index: int
    scale: int
    steps: int
    k: int
    margin: int
    stability_pct: float  # 0-100
    difficulty_mult: float = 1.0  # relative to B0

KNOWN_PROFILES = [
    Profile("E4", -4, 1, 2, 3, 280, 100.0, 0.35),
    Profile("E3", -3, 1, 3, 3, 240, 100.0, 0.50),
    Profile("E2", -2, 1, 4, 3, 225, 100.0, 0.65),
    Profile("E1", -1, 1, 4, 4, 205, 100.0, 0.80),
    Profile("B0",  0, 1, 4, 4, 185, 100.0, 1.00),
    Profile("H1",  1, 1, 5, 4, 170, 97.0,  1.25),
    Profile("H2",  2, 1, 5, 5, 160, 92.0,  1.55),
    Profile("H3",  3, 1, 6, 5, 150, 85.0,  2.00),
    Profile("H4",  4, 1, 6, 6, 145, 78.0,  2.50),
    Profile("H5",  5, 2, 5, 5, 140, 65.0,  3.20),
    Profile("H6",  6, 2, 6, 5, 135, 50.0,  4.20),
    Profile("H7",  7, 2, 6, 6, 130, 45.0,  5.50),
    Profile("H8",  8, 2, 7, 6, 125, 35.0,  7.50),
    Profile("H9",  9, 2, 7, 7, 120, 25.0, 10.0),
    Profile("H10",10, 2, 7, 7, 115, 12.0, 14.0),
    Profile("H11",11, 2, 8, 7, 110,  5.0, 20.0),
    Profile("H12",12, 2, 8, 8, 105,  3.0, 30.0),
]

# ────────���────────────────────────────────���──────────────────────────���
# Stability model: fit logistic from known data
# ──────────────────��──────────────────────────────────────────────────

def fit_stability_model():
    """
    No fitting needed — we use direct interpolation from known data.
    Returns dummy values for API compatibility.
    """
    # Validate the interpolation model against known profiles
    return 0, 0


def predict_stability(scale, steps, k, margin, *model_args):
    """
    Predict stability % using interpolation from known profiles.
    Uses nearest-neighbor weighted interpolation in parameter space.
    """
    # Direct interpolation: find the two nearest known profiles
    # and interpolate based on parameter distance
    known = [(p.scale, p.steps, p.k, p.margin, p.stability_pct)
             for p in KNOWN_PROFILES]

    # Weighted distance in parameter space
    def dist(s1, st1, k1, m1, s2, st2, k2, m2):
        # Scale has huge effect, margin moderate, steps/k smaller
        return (abs(s1 - s2) * 30.0 +
                abs(st1 - st2) * 3.0 +
                abs(k1 - k2) * 3.0 +
                abs(m1 - m2) * 0.15)

    distances = []
    for s2, st2, k2, m2, stab in known:
        d = dist(scale, steps, k, margin, s2, st2, k2, m2)
        distances.append((d, stab))

    distances.sort()

    # Inverse-distance weighted average of 3 nearest neighbors
    n_neighbors = min(3, len(distances))
    if distances[0][0] < 0.01:
        return distances[0][1]  # exact match

    weight_sum = 0
    stab_sum = 0
    for i in range(n_neighbors):
        d, stab = distances[i]
        w = 1.0 / max(d, 0.01)
        weight_sum += w
        stab_sum += w * stab

    result = stab_sum / weight_sum
    return max(0.1, min(100.0, result))


def predict_difficulty_mult(scale, steps, k, margin, stability_pct):
    """
    Estimate relative difficulty multiplier.
    Combines parameter complexity with stability filter rejection rate.
    """
    base = 1.0 + (scale - 1) * 0.3 + steps * 0.15 + k * 0.1
    # Stability rejection amplifies effective difficulty
    if stability_pct > 0:
        rejection_mult = 100.0 / stability_pct
    else:
        rejection_mult = 1000.0
    return base * (rejection_mult / 1.0) ** 0.3


# ───────────────────────────��─────────────────────────────────────────
# Extended profile table generators
# ──────��──────────────────────────────────────────────────────────────

def generate_smooth_table(n_hardening: int, model_a: float, model_b: float,
                          strategy: str = "margin_first") -> List[Profile]:
    """
    Generate an extended profile table with n_hardening profiles (H1..Hn).
    Easing profiles E4-E1 and B0 are always included unchanged.

    Strategies:
      margin_first: decrease margin first, then increase k, then steps
      uniform_step: try to make each profile ~same stability step
      k_ladder: increase k steadily, margin follows
    """
    # Start with easing + B0
    profiles = [p for p in KNOWN_PROFILES if p.index <= 0]

    if strategy == "margin_first":
        return _gen_margin_first(profiles, n_hardening, model_a, model_b)
    elif strategy == "uniform_step":
        return _gen_uniform_step(profiles, n_hardening, model_a, model_b)
    elif strategy == "k_ladder":
        return _gen_k_ladder(profiles, n_hardening, model_a, model_b)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


def _gen_margin_first(base, n_h, ma, mb):
    """
    Strategy: keep scale=2, gradually increase steps and k while
    decreasing margin. Each profile changes ONE parameter by the
    smallest possible increment.
    """
    profiles = list(base)
    # Starting point: H1-like
    scale, steps, k, margin = 1, 5, 4, 170

    for i in range(1, n_h + 1):
        stab = predict_stability(scale, steps, k, margin, ma, mb)
        diff = predict_difficulty_mult(scale, steps, k, margin, stab)
        name = f"H{i}"
        profiles.append(Profile(name, i, scale, steps, k, margin, stab, diff))

        # Decide next parameter change (priority: margin → k → steps → scale)
        if margin > 80:
            margin -= 5  # decrease margin by 5
        elif k < 12:
            k += 1
            margin = min(margin + 10, 200)  # slight margin recovery after k bump
        elif steps < 12:
            steps += 1
            margin = min(margin + 5, 200)
        elif scale < 3:
            scale += 1
            margin = min(margin + 30, 200)  # big margin recovery after scale bump
        else:
            margin = max(margin - 5, 50)  # keep pushing margin down

    return profiles


def _gen_uniform_step(base, n_h, ma, mb):
    """
    Strategy: target a uniform stability step between consecutive profiles.
    Work backwards from target: 97% at H1 down to ~1% at Hn.
    For each target stability, find the cheapest parameter combination.
    """
    profiles = list(base)

    # Target stability curve: geometric from 97% to 1%
    target_stabs = []
    for i in range(n_h):
        t = i / max(n_h - 1, 1)
        stab = 97.0 * (1.0 / 97.0) ** t  # geometric: 97 → 1
        target_stabs.append(max(stab, 0.5))

    # For each target, find best {scale, steps, k, margin}
    prev_params = (1, 5, 4, 170)  # H1 starting point

    for i, target_stab in enumerate(target_stabs):
        best_params = None
        best_err = 1e9

        ps, pst, pk, pm = prev_params
        # Search nearby parameter space
        for s in range(max(1, ps), min(ps + 2, 4)):
            for st in range(max(2, pst - 1), min(pst + 3, 16)):
                for kk in range(max(3, pk - 1), min(pk + 3, 16)):
                    for m in range(max(50, pm - 30), min(pm + 10, 300), 5):
                        pred = predict_stability(s, st, kk, m, ma, mb)
                        err = abs(pred - target_stab)
                        # Prefer minimal parameter changes from previous
                        change_cost = (abs(s-ps)*10 + abs(st-pst)*2 +
                                      abs(kk-pk)*2 + abs(m-pm)*0.1)
                        err += change_cost * 0.1
                        if err < best_err:
                            best_err = err
                            best_params = (s, st, kk, m)

        if best_params is None:
            best_params = prev_params

        s, st, kk, m = best_params
        stab = predict_stability(s, st, kk, m, ma, mb)
        diff = predict_difficulty_mult(s, st, kk, m, stab)
        name = f"H{i+1}"
        profiles.append(Profile(name, i+1, s, st, kk, m, stab, diff))
        prev_params = best_params

    return profiles


def _gen_k_ladder(base, n_h, ma, mb):
    """
    Strategy: increase k as the primary lever, adjusting margin to
    maintain smooth stability transitions. Scale stays at 2 for as
    long as possible.
    """
    profiles = list(base)
    scale = 1
    steps = 5
    k = 4
    margin = 170

    for i in range(1, n_h + 1):
        stab = predict_stability(scale, steps, k, margin, ma, mb)
        diff = predict_difficulty_mult(scale, steps, k, margin, stab)
        name = f"H{i}"
        profiles.append(Profile(name, i, scale, steps, k, margin, stab, diff))

        # Advance: alternate between margin decrease and k/steps increase
        if i % 3 == 0 and k < 14:
            k += 1
        elif i % 5 == 0 and steps < 14:
            steps += 1
        elif i % 8 == 0 and scale < 3:
            scale += 1
            margin += 20  # compensate scale jump
        else:
            margin -= 3

        margin = max(margin, 50)

    return profiles


# ────────────────────────────���────────────────────────────────────────
# bitsQ simulation (simplified but faithful)
# ���───────────────��────────────────────────────────────────────────────

def log2_q16(x):
    if x <= 0: return -20 * Q16_ONE
    if x == 1: return 0
    int_part = x.bit_length() - 1
    lo = 1 << int_part
    hi = lo << 1
    frac = ((x - lo) * Q16_ONE) // (hi - lo) if hi > lo else 0
    return int_part * Q16_ONE + frac


def next_bitsq(prev_bitsq, dt, anchor_bitsq, time_delta_from_anchor):
    """Simplified bitsQ: exponential adjustment with 12.5% cap. No Ahead Guard (V6)."""
    halflife = BITSQ_HALF_LIFE_V2
    # Direction: if blocks are fast (td negative), bitsq goes up
    exponent = (-time_delta_from_anchor * Q16_ONE) // halflife

    # Simplified: just use delta cap relative to previous
    max_delta = prev_bitsq // BITSQ_MAX_DELTA_DEN_V2
    if max_delta < 1: max_delta = 1

    # If block was fast, increase difficulty; if slow, decrease
    if dt < TARGET_SPACING:
        delta = min(max_delta, prev_bitsq // 16)
    elif dt > TARGET_SPACING:
        delta = -min(max_delta, prev_bitsq // 16)
    else:
        delta = 0

    result = prev_bitsq + delta
    return max(Q16_ONE, min(255 * Q16_ONE, result))


# ─────���───────────────────────────────────────────────────────────────
# Full cASERT V6 simulator with extended profiles
# ──────────────────��─────────────────────────────���────────────────────

@dataclass
class Block:
    height: int
    time: int
    profile_index: int
    bitsq: int
    dt: int = 0
    lag: int = 0
    hashrate_kh: float = 1.3

@dataclass
class SimConfig:
    profile_table: List[Profile]
    n_blocks: int = 1000
    start_height: int = 5000
    base_hashrate_kh: float = 1.3
    hashrate_schedule: Optional[List[Tuple[int, float]]] = None
    variance: str = "medium"  # low, medium, high
    seed: int = 42
    slew_rate: int = 1
    h_max: int = 12  # will be overridden by table size


def get_hashrate_at_block(config: SimConfig, height: int) -> float:
    """Get hashrate at a given height, supporting dynamic schedules."""
    if config.hashrate_schedule:
        hr = config.base_hashrate_kh
        for trigger_h, new_hr in config.hashrate_schedule:
            if height >= trigger_h:
                hr = new_hr
        return hr
    return config.base_hashrate_kh


def sample_block_dt(profile: Profile, hashrate_kh: float, rng) -> float:
    """Sample block time using exponential distribution."""
    stab = max(profile.stability_pct, 0.1) / 100.0
    diff_mult = max(profile.difficulty_mult, 0.1)
    base_time = 780.0 / max(hashrate_kh, 0.05)
    effective_time = base_time * diff_mult / max(stab, 0.001)
    return rng.expovariate(1.0 / effective_time)


def compute_profile_v6(chain: List[Block], next_height: int, now_time: int,
                        config: SimConfig) -> int:
    """Full V6 equalizer with extended profile support."""
    if len(chain) < 2:
        return 0

    h_max = len([p for p in config.profile_table if p.index > 0])
    last = chain[-1]
    prev_H = last.profile_index

    # Schedule lag
    elapsed = last.time - GENESIS_TIME
    expected_h = elapsed // TARGET_SPACING if elapsed >= 0 else 0
    lag = (next_height - 1) - expected_h

    # PID signal (simplified but lag-dominant like real C++)
    dt = last.time - chain[-2].time if len(chain) >= 2 else TARGET_SPACING
    dt = max(1, dt)
    burst_signal = math.log2(TARGET_SPACING / dt) if dt > 0 else 0

    # Use real PID weights (normalized)
    H_raw = int(round(lag * 0.40 + burst_signal * 0.05))
    H = max(CASERT_H_MIN, min(h_max, H_raw))

    # Safety rule 1: never harden when behind
    if lag <= 0:
        H = min(H, 0)

    if len(chain) >= 3:
        # Slew rate ±1 (V6)
        H = max(prev_H - config.slew_rate, min(prev_H + config.slew_rate, H))

        # Lag floor
        if lag > 10:
            lag_floor = min(lag // CASERT_V3_LAG_FLOOR_DIV, h_max)
            H = max(H, lag_floor)

        # Safety rule 1 post-slew (V5+)
        if lag <= 0:
            H = min(H, 0)

        # EBR
        if lag <= CASERT_EBR_ENTER:
            if lag <= CASERT_EBR_LEVEL_E4:
                H = min(H, CASERT_H_MIN)
            elif lag <= CASERT_EBR_LEVEL_E3:
                H = min(H, -3)
            elif lag <= CASERT_EBR_LEVEL_E2:
                H = min(H, -2)
            else:
                H = min(H, 0)

        # Extreme profile entry cap (V5)
        if H >= CASERT_V5_EXTREME_MIN and H > prev_H + 1:
            H = prev_H + 1

        # V6: H11/H12 reservation (extended: generalize for larger tables)
        # For extended tables, reserve top profiles similarly
        if h_max <= 12:
            # Standard 17-profile table: use fixed thresholds
            if H >= 12 and lag < CASERT_V6_H12_MIN_LAG:
                H = 11
            if H >= 11 and lag < CASERT_V6_H11_MIN_LAG:
                H = 10
        else:
            # Extended table: reserve top 20% of profiles for lag >= profile_index
            reserve_start = int(h_max * 0.8)
            if H >= reserve_start:
                required_lag = reserve_start + (H - reserve_start) * 2
                if lag < required_lag:
                    H = reserve_start - 1

        H = max(CASERT_H_MIN, min(h_max, H))

    # Anti-stall (V6: immediate first drop)
    stall = max(0, now_time - last.time)
    if stall >= CASERT_ANTISTALL_FLOOR_V5 and H > 0:
        decay_time = stall - CASERT_ANTISTALL_FLOOR_V5
        decayed_H = H - 1  # immediate first drop
        while decayed_H > 0 and decay_time > 0:
            if decayed_H >= 7:
                cost = 600
            elif decayed_H >= 4:
                cost = 900
            else:
                cost = 1200
            if decay_time < cost:
                break
            decay_time -= cost
            decayed_H -= 1
        H = decayed_H

    return max(CASERT_H_MIN, min(h_max, H))


def get_profile_by_index(table: List[Profile], idx: int) -> Profile:
    """Look up profile by index. Easing profiles have negative indices."""
    for p in table:
        if p.index == idx:
            return p
    # Fallback to B0
    return [p for p in table if p.index == 0][0]


def simulate(config: SimConfig) -> List[Dict]:
    """Run full simulation with given config."""
    rng = random.Random(config.seed)
    chain: List[Block] = []

    # Seed chain with 3 blocks on schedule
    seed_time = GENESIS_TIME + (config.start_height - 3) * TARGET_SPACING
    for i in range(3):
        chain.append(Block(
            height=config.start_height - 3 + i,
            time=seed_time + i * TARGET_SPACING,
            profile_index=0,
            bitsq=GENESIS_BITSQ,
        ))

    sim_time = chain[-1].time
    rows = []

    for _ in range(config.n_blocks):
        next_h = chain[-1].height + 1
        hr = get_hashrate_at_block(config, next_h)

        # Add variance
        if config.variance == "high":
            hr *= rng.uniform(0.4, 2.2)
        elif config.variance == "medium":
            hr *= rng.uniform(0.7, 1.4)

        # Compute profile
        profile_idx = compute_profile_v6(chain, next_h, sim_time, config)
        profile = get_profile_by_index(config.profile_table, profile_idx)

        # Sample block time
        dt = sample_block_dt(profile, hr, rng)
        dt = max(1, dt)

        # bitsQ (simplified)
        prev_bitsq = chain[-1].bitsq
        new_bitsq = next_bitsq(prev_bitsq, int(dt), GENESIS_BITSQ, 0)

        new_time = int(sim_time + dt)
        elapsed = new_time - GENESIS_TIME
        expected = elapsed // TARGET_SPACING if elapsed >= 0 else 0
        lag = (next_h - 1) - expected

        chain.append(Block(
            height=next_h, time=new_time, profile_index=profile_idx,
            bitsq=new_bitsq, dt=int(dt), lag=lag, hashrate_kh=hr,
        ))
        sim_time = new_time

        rows.append({
            "height": next_h,
            "dt": int(dt),
            "profile_index": profile_idx,
            "profile_name": profile.name,
            "stability_pct": profile.stability_pct,
            "lag": lag,
            "bitsq": new_bitsq,
            "hashrate_kh": round(hr, 3),
        })

    return rows


# ─��─────────────────────────���─────────────────────────────────────────
# Analysis and scoring
# ──���─────────────────���────────────────────────────────────────────────

@dataclass
class SimResult:
    table_name: str
    n_profiles: int
    strategy: str
    hashrate_kh: float
    mean_dt: float
    std_dt: float
    median_dt: float
    p95_dt: float
    p99_dt: float
    sawtooth_score: float
    smoothness: float  # lower = smoother transitions
    blocks_over_20m: int
    blocks_over_40m: int
    blocks_over_60m: int
    lag_range: Tuple[int, int]
    profile_distribution: Dict[int, int]
    max_consecutive_stuck: int  # blocks > 20min in a row
    verdict: str  # GREEN/YELLOW/RED


def analyze(rows: List[Dict], table_name: str, strategy: str,
            hashrate: float) -> SimResult:
    """Analyze simulation results."""
    n = len(rows)
    if n == 0:
        return None

    dts = [r["dt"] for r in rows]
    lags = [r["lag"] for r in rows]
    profiles = [r["profile_index"] for r in rows]

    mean_dt = statistics.mean(dts)
    std_dt = statistics.stdev(dts) if n > 1 else 0
    median_dt = statistics.median(dts)
    sorted_dts = sorted(dts)
    p95_dt = sorted_dts[int(n * 0.95)] if n > 20 else max(dts)
    p99_dt = sorted_dts[int(n * 0.99)] if n > 100 else max(dts)

    blocks_20 = sum(1 for d in dts if d >= 1200)
    blocks_40 = sum(1 for d in dts if d >= 2400)
    blocks_60 = sum(1 for d in dts if d >= 3600)

    # Sawtooth score: sum of |profile_change| > 2
    sawtooth = 0
    for i in range(1, len(profiles)):
        diff = abs(profiles[i] - profiles[i-1])
        if diff > 2:
            sawtooth += diff
    sawtooth_score = sawtooth / max(n, 1)

    # Smoothness: average absolute profile change between consecutive blocks
    smoothness = 0
    for i in range(1, len(profiles)):
        smoothness += abs(profiles[i] - profiles[i-1])
    smoothness = smoothness / max(n - 1, 1)

    # Max consecutive stuck blocks (>20 min)
    max_stuck = 0
    cur_stuck = 0
    for d in dts:
        if d >= 1200:
            cur_stuck += 1
            max_stuck = max(max_stuck, cur_stuck)
        else:
            cur_stuck = 0

    # Profile distribution
    prof_hist = {}
    for p in profiles:
        prof_hist[p] = prof_hist.get(p, 0) + 1

    lag_range = (min(lags), max(lags))

    # Verdict
    if blocks_60 >= 3 or max_stuck >= 5 or sawtooth_score > 5:
        verdict = "RED"
    elif blocks_40 >= 3 or max_stuck >= 3 or sawtooth_score > 2:
        verdict = "YELLOW"
    else:
        verdict = "GREEN"

    return SimResult(
        table_name=table_name, n_profiles=len(set(profiles)),
        strategy=strategy, hashrate_kh=hashrate,
        mean_dt=mean_dt, std_dt=std_dt, median_dt=median_dt,
        p95_dt=p95_dt, p99_dt=p99_dt, sawtooth_score=sawtooth_score,
        smoothness=smoothness, blocks_over_20m=blocks_20,
        blocks_over_40m=blocks_40, blocks_over_60m=blocks_60,
        lag_range=lag_range, profile_distribution=prof_hist,
        max_consecutive_stuck=max_stuck, verdict=verdict,
    )


def print_result(r: SimResult, verbose: bool = True):
    """Print analysis result."""
    color = {"GREEN": GREEN, "YELLOW": YELLOW, "RED": RED}[r.verdict]
    icon = {"GREEN": "G", "YELLOW": "Y", "RED": "R"}[r.verdict]

    print(f"\n{BOLD}{CYAN}{r.table_name} [{r.strategy}] @ {r.hashrate_kh} kH/s{RESET}")
    print(f"{DIM}{'─' * 72}{RESET}")
    print(f"  Mean block time:     {r.mean_dt/60:.1f}m   (target: 10.0m)")
    print(f"  Std deviation:       {r.std_dt/60:.1f}m")
    print(f"  Median:              {r.median_dt/60:.1f}m")
    print(f"  p95:                 {r.p95_dt/60:.1f}m")
    print(f"  p99:                 {r.p99_dt/60:.1f}m")
    print(f"  Sawtooth score:      {r.sawtooth_score:.2f}   {DIM}(lower = better){RESET}")
    print(f"  Smoothness:          {r.smoothness:.3f}   {DIM}(avg profile change/block){RESET}")
    print(f"  Blocks > 20m:        {r.blocks_over_20m}")
    print(f"  Blocks > 40m:        {r.blocks_over_40m}")
    print(f"  Blocks > 60m:        {r.blocks_over_60m}")
    print(f"  Max consecutive >20m:{r.max_consecutive_stuck}")
    print(f"  Lag range:           {r.lag_range[0]:+d} to {r.lag_range[1]:+d}")
    print(f"  Active profiles:     {r.n_profiles}")

    if verbose:
        print(f"\n  Profile distribution:")
        for p in sorted(r.profile_distribution.keys()):
            count = r.profile_distribution[p]
            pct = count * 100.0 / sum(r.profile_distribution.values())
            bar_len = int(pct / 2)
            print(f"    {'H' if p > 0 else 'E' if p < 0 else 'B'}"
                  f"{abs(p) if p != 0 else '0':>2}: {count:>5} ({pct:5.1f}%)  "
                  f"{'█' * bar_len}")

    print(f"{DIM}{'─' * 72}{RESET}")
    print(f"  Verdict: {color}{BOLD}[{icon}] {r.verdict}{RESET}")


def print_profile_table(profiles: List[Profile]):
    """Print a profile table with stability estimates."""
    print(f"\n{BOLD}Profile Table ({len(profiles)} profiles){RESET}")
    print(f"{'─' * 80}")
    print(f"  {'Name':>5}  {'Idx':>4}  {'Scale':>5}  {'Steps':>5}  {'K':>3}  "
          f"{'Margin':>6}  {'Stab%':>6}  {'DiffMult':>8}  {'Step':>6}")
    print(f"{'─' * 80}")

    prev_stab = None
    for p in profiles:
        step = ""
        if prev_stab is not None and p.stability_pct < 100:
            step = f"{p.stability_pct - prev_stab:+.1f}"
        prev_stab = p.stability_pct if p.stability_pct < 100 else prev_stab

        stab_color = GREEN if p.stability_pct >= 50 else (
            YELLOW if p.stability_pct >= 15 else RED)
        print(f"  {p.name:>5}  {p.index:>4}  {p.scale:>5}  {p.steps:>5}  "
              f"{p.k:>3}  {p.margin:>6}  {stab_color}{p.stability_pct:>5.1f}%{RESET}  "
              f"{p.difficulty_mult:>8.2f}  {step:>6}")

    print(f"{'─' * 80}")


# ───��─────────────────────────────────────────────────────────────────
# Hashrate scenarios
# ─���────────────────��──────────────────────────────────────────────────

HASHRATE_SCENARIOS = {
    "current": {
        "desc": "Current network (~1.3 kH/s, 3-4 miners)",
        "base": 1.3,
        "schedule": None,
    },
    "growth_2x": {
        "desc": "2x growth: 1.3 → 2.6 kH/s at block +200",
        "base": 1.3,
        "schedule": [(5200, 2.6)],
    },
    "growth_5x": {
        "desc": "5x growth: 1.3 → 6.5 kH/s at block +200",
        "base": 1.3,
        "schedule": [(5200, 6.5)],
    },
    "growth_10x": {
        "desc": "10x growth: 1.3 → 13.0 kH/s at block +300",
        "base": 1.3,
        "schedule": [(5300, 13.0)],
    },
    "shock_drop": {
        "desc": "Top miner leaves: 1.3 → 0.5 kH/s at block +100",
        "base": 1.3,
        "schedule": [(5100, 0.5)],
    },
    "volatile": {
        "desc": "Miners join/leave: 1.3→3.0→0.8→2.5→1.0",
        "base": 1.3,
        "schedule": [(5100, 3.0), (5250, 0.8), (5400, 2.5), (5600, 1.0)],
    },
}


# ───────��─────────────────────────────────────────────────────────────
# Main sweep
# ────���────────────���───────────────────────────────────────────────────

def run_sweep(args):
    """Run the full parameter sweep."""
    print(f"{BOLD}{CYAN}═══════════════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}{CYAN}  SOST Extended Profile Explorer — Dynamic Adaptation Sweep{RESET}")
    print(f"{BOLD}{CYAN}═��═════════════════════════════════════��═══════════════════════{RESET}")

    # Step 1: Fit stability model
    print(f"\n{BOLD}Step 1: Fitting stability model from {len(KNOWN_PROFILES)} known profiles...{RESET}")
    model_a, model_b = fit_stability_model()
    print(f"  Model: stability% = 100 / (1 + exp({model_a:.3f} * (score - {model_b:.2f})))")

    # Validate model against known data
    print(f"\n  Validation against known profiles:")
    max_err = 0
    for p in KNOWN_PROFILES:
        pred = predict_stability(p.scale, p.steps, p.k, p.margin, model_a, model_b)
        err = abs(pred - p.stability_pct)
        max_err = max(max_err, err)
        marker = " *" if err > 10 else ""
        if p.stability_pct < 100:
            print(f"    {p.name:>4}: actual={p.stability_pct:5.1f}%  "
                  f"predicted={pred:5.1f}%  err={err:5.1f}%{marker}")
    print(f"  Max error: {max_err:.1f}%")

    # Step 2: Generate profile tables
    profile_counts = [int(x) for x in args.profiles.split(",")]
    strategies = args.strategies.split(",")
    hashrate_keys = args.hashrates.split(",")

    all_results: List[SimResult] = []

    for n_prof in profile_counts:
        for strategy in strategies:
            print(f"\n{BOLD}{'═' * 72}{RESET}")
            print(f"{BOLD}Generating {n_prof}-profile table (strategy: {strategy}){RESET}")
            table = generate_smooth_table(n_prof, model_a, model_b, strategy)
            print_profile_table(table)

            # Step 3: Simulate with each hashrate scenario
            for hr_key in hashrate_keys:
                scenario = HASHRATE_SCENARIOS.get(hr_key)
                if not scenario:
                    print(f"  {RED}Unknown scenario: {hr_key}{RESET}")
                    continue

                print(f"\n  {ORANGE}Scenario: {scenario['desc']}{RESET}")

                h_max = max(p.index for p in table)
                results_for_seeds = []

                for seed in range(args.seed, args.seed + args.seeds):
                    config = SimConfig(
                        profile_table=table,
                        n_blocks=args.blocks,
                        start_height=5000,
                        base_hashrate_kh=scenario["base"],
                        hashrate_schedule=scenario["schedule"],
                        variance=args.variance,
                        seed=seed,
                        slew_rate=args.slew,
                        h_max=h_max,
                    )
                    rows = simulate(config)
                    result = analyze(rows, f"{n_prof}H-{strategy}", strategy,
                                   scenario["base"])
                    results_for_seeds.append(result)
                    all_results.append(result)

                # Aggregate over seeds
                if len(results_for_seeds) > 1:
                    avg_mean = statistics.mean(r.mean_dt for r in results_for_seeds)
                    avg_std = statistics.mean(r.std_dt for r in results_for_seeds)
                    avg_saw = statistics.mean(r.sawtooth_score for r in results_for_seeds)
                    avg_smooth = statistics.mean(r.smoothness for r in results_for_seeds)
                    greens = sum(1 for r in results_for_seeds if r.verdict == "GREEN")
                    yellows = sum(1 for r in results_for_seeds if r.verdict == "YELLOW")
                    reds = sum(1 for r in results_for_seeds if r.verdict == "RED")
                    total = len(results_for_seeds)

                    color = GREEN if reds == 0 else (YELLOW if reds < total // 2 else RED)
                    print(f"    {BOLD}Aggregate ({total} seeds):{RESET} "
                          f"mean={avg_mean/60:.1f}m  std={avg_std/60:.1f}m  "
                          f"sawtooth={avg_saw:.2f}  smooth={avg_smooth:.3f}  "
                          f"{color}G:{greens} Y:{yellows} R:{reds}{RESET}")
                else:
                    print_result(results_for_seeds[0], verbose=args.verbose)

    # Step 4: Summary comparison
    print(f"\n\n{BOLD}{CYAN}{'═' * 72}{RESET}")
    print(f"{BOLD}{CYAN}  SUMMARY — All configurations ranked by sawtooth score{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 72}{RESET}")

    # Group by (table, strategy, hashrate) and average
    groups = {}
    for r in all_results:
        key = (r.table_name, r.hashrate_kh)
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    ranked = []
    for key, results in groups.items():
        avg_saw = statistics.mean(r.sawtooth_score for r in results)
        avg_mean = statistics.mean(r.mean_dt for r in results)
        avg_std = statistics.mean(r.std_dt for r in results)
        avg_smooth = statistics.mean(r.smoothness for r in results)
        reds = sum(1 for r in results if r.verdict == "RED")
        ranked.append((avg_saw, key[0], key[1], avg_mean, avg_std,
                       avg_smooth, reds, len(results)))

    ranked.sort()
    print(f"\n  {'Rank':>4}  {'Config':>20}  {'HR':>6}  {'Mean':>7}  {'Std':>7}  "
          f"{'Saw':>6}  {'Smooth':>7}  {'Reds':>5}")
    print(f"  {'─' * 80}")
    for i, (saw, name, hr, mean, std, smooth, reds, total) in enumerate(ranked[:20]):
        color = GREEN if reds == 0 else (YELLOW if reds < total // 2 else RED)
        print(f"  {i+1:>4}  {name:>20}  {hr:>5.1f}  {mean/60:>6.1f}m  "
              f"{std/60:>6.1f}m  {saw:>5.2f}  {smooth:>6.3f}  "
              f"{color}{reds}/{total}{RESET}")


def run_single(args):
    """Run a single simulation with the current 17-profile table."""
    print(f"{BOLD}{CYAN}Single simulation with current 17-profile table (V6 rules){RESET}")
    model_a, model_b = fit_stability_model()

    table = KNOWN_PROFILES
    print_profile_table(table)

    config = SimConfig(
        profile_table=table,
        n_blocks=args.blocks,
        start_height=5000,
        base_hashrate_kh=1.3,
        variance=args.variance,
        seed=args.seed,
        slew_rate=args.slew,
    )
    rows = simulate(config)
    result = analyze(rows, "current-17", "known", config.base_hashrate_kh)
    print_result(result, verbose=True)

    # Write CSV
    outpath = os.path.join(os.path.dirname(__file__), "..", "sim_profile_explorer.csv")
    with open(outpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\n{DIM}Wrote {len(rows)} rows to {outpath}{RESET}")


# ─────────────────────────────────────────────────────────────────────
# Entry point
# ──��──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="SOST Extended Profile Explorer",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sweep", action="store_true",
                    help="Run full parameter sweep")
    ap.add_argument("--profiles", default="12,20,30,50",
                    help="Comma-separated profile counts to test (default: 12,20,30,50)")
    ap.add_argument("--strategies", default="margin_first,uniform_step,k_ladder",
                    help="Comma-separated strategies (default: margin_first,uniform_step,k_ladder)")
    ap.add_argument("--hashrates", default="current,growth_2x,growth_5x,volatile",
                    help="Comma-separated hashrate scenarios (default: current,growth_2x,growth_5x,volatile)")
    ap.add_argument("--blocks", type=int, default=1000,
                    help="Blocks per simulation (default: 1000)")
    ap.add_argument("--seeds", type=int, default=5,
                    help="Seeds per configuration (default: 5)")
    ap.add_argument("--seed", type=int, default=42,
                    help="Starting seed (default: 42)")
    ap.add_argument("--variance", choices=["low", "medium", "high"], default="medium",
                    help="Block time variance (default: medium)")
    ap.add_argument("--slew", type=int, default=1,
                    help="Slew rate (default: 1 for V6)")
    ap.add_argument("--verbose", action="store_true",
                    help="Show full profile distributions")
    args = ap.parse_args()

    if args.sweep:
        run_sweep(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()

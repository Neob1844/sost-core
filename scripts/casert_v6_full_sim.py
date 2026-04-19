#!/usr/bin/env python3
"""
cASERT V6 Full Simulator — Bit-exact PID + Dynamic Profile Explorer

Faithful Python reimplementation of the ENTIRE casert_compute() function
from src/pow/casert.cpp, including:
  - Full PID: U = K_R·r + K_L·L + K_I·I + K_B·burst + K_V·V
  - EWMA short/long/volatility with exact Q16.16 fixed-point
  - Integrator with leak (rho=253/256)
  - bitsQ exponential with 12.5% cap (V6: no Ahead Guard)
  - V6 slew ±1
  - V6 H11/H12 reservation (lag >= 11 / lag >= 21)
  - V5 safety rule post-slew, EBR, extreme cap
  - Anti-stall with V6 immediate first drop
  - Easing emergency (6h at B0)

Plus extended profile table generation and multi-scenario testing
for calibration optimization before block 10,000.

Usage:
    # Baseline: current 17 profiles, current hashrate
    python3 scripts/casert_v6_full_sim.py

    # Full sweep: test extended tables under growth scenarios
    python3 scripts/casert_v6_full_sim.py --sweep

    # Custom: 30 profiles, 5x hashrate growth, 2000 blocks
    python3 scripts/casert_v6_full_sim.py --n-profiles 30 --scenario growth_5x --blocks 2000

    # Monte Carlo: 50 seeds for statistical significance
    python3 scripts/casert_v6_full_sim.py --monte-carlo 50
"""

import argparse
import csv
import math
import os
import random
import statistics
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS — exact mirror of include/sost/params.h
# ═══════════════════════════════════════════════════════════════════════

GENESIS_TIME    = 1773597600
TARGET_SPACING  = 600
GENESIS_BITSQ   = 765730
Q16_ONE         = 65536
MIN_BITSQ       = Q16_ONE
MAX_BITSQ       = 255 * Q16_ONE

# bitsQ
BITSQ_HALF_LIFE_V2     = 86400
BITSQ_MAX_DELTA_DEN_V2 = 8       # 12.5% cap

# PID gains (Q16.16 fixed-point)
K_R = 3277    # 0.05
K_L = 26214   # 0.40
K_I = 9830    # 0.15
K_B = 3277    # 0.05
K_V = 1311    # 0.02

# EWMA
EWMA_SHORT_ALPHA = 32
EWMA_LONG_ALPHA  = 3
EWMA_VOL_ALPHA   = 16
EWMA_DENOM       = 256

# Integrator
INTEG_RHO   = 253
INTEG_ALPHA = 1
INTEG_MAX   = 6553600  # 100.0 in Q16.16

# Profile bounds
H_MIN = -4
H_MAX = 12

# Timing
DT_MIN = 1
DT_MAX = 86400

# V3+
V3_LAG_FLOOR_DIV = 8

# V5
V5_EXTREME_MIN = 10
EBR_ENTER    = -10
EBR_LEVEL_E2 = -15
EBR_LEVEL_E3 = -20
EBR_LEVEL_E4 = -25
ANTISTALL_FLOOR_V5     = 3600
ANTISTALL_EASING_EXTRA = 21600

# V6
V6_SLEW_RATE    = 1
V6_H11_MIN_LAG  = 11
V6_H12_MIN_LAG  = 21

# V4 Ahead Guard thresholds (disabled in V6)
AHEAD_ENTER     = 16
AHEAD_DELTA_DEN = 64

# ═══════════════════════════════════════════════════════════════════════
# ANSI
# ═══════════════════════════════════════════════════════════════════════
G="\033[92m";Y="\033[93m";R="\033[91m";C="\033[96m";D="\033[2m"
B="\033[1m";X="\033[0m";O="\033[38;5;208m";M="\033[95m"

# ═══════════════════════════════════════════════════════════════════════
# PROFILE TABLE — production values from params.h
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ProfileParams:
    index: int
    name: str
    scale: int
    steps: int
    k: int
    margin: int
    # Empirical stability pass rate (from production observation)
    stability_pct: float
    # Effective difficulty multiplier relative to B0
    eff_diff: float

# Current 17-profile table with empirical pass rates
PROFILES_17 = [
    ProfileParams(-4, "E4", 1, 2, 3, 280, 100.0, 0.35),
    ProfileParams(-3, "E3", 1, 3, 3, 240, 100.0, 0.50),
    ProfileParams(-2, "E2", 1, 4, 3, 225, 100.0, 0.65),
    ProfileParams(-1, "E1", 1, 4, 4, 205, 100.0, 0.80),
    ProfileParams( 0, "B0", 1, 4, 4, 185, 100.0, 1.00),
    ProfileParams( 1, "H1", 1, 5, 4, 170,  97.0, 1.25),
    ProfileParams( 2, "H2", 1, 5, 5, 160,  92.0, 1.55),
    ProfileParams( 3, "H3", 1, 6, 5, 150,  85.0, 2.00),
    ProfileParams( 4, "H4", 1, 6, 6, 145,  78.0, 2.50),
    ProfileParams( 5, "H5", 2, 5, 5, 140,  65.0, 3.20),
    ProfileParams( 6, "H6", 2, 6, 5, 135,  50.0, 4.20),
    ProfileParams( 7, "H7", 2, 6, 6, 130,  45.0, 5.50),
    ProfileParams( 8, "H8", 2, 7, 6, 125,  35.0, 7.50),
    ProfileParams( 9, "H9", 2, 7, 7, 120,  25.0, 10.0),
    ProfileParams(10, "H10",2, 7, 7, 115,  12.0, 14.0),
    ProfileParams(11, "H11",2, 8, 7, 110,   5.0, 20.0),
    ProfileParams(12, "H12",2, 8, 8, 105,   3.0, 30.0),
]

def make_profile_map(profiles):
    return {p.index: p for p in profiles}

# ═══════════════════════════════════════════════════════════════════════
# FIXED-POINT MATH — exact match of C++ casert.cpp
# ═══════════════════════════════════════════════════════════════════════

def log2_q16(x):
    """log2(x) in Q16.16 fixed point. x is a plain integer."""
    if x <= 0: return -(Q16_ONE * 20)
    if x == 1: return 0
    int_part = x.bit_length() - 1
    lo = 1 << int_part
    hi = lo << 1
    frac = ((x - lo) * Q16_ONE) // (hi - lo) if hi > lo else 0
    return int_part * Q16_ONE + frac

def horner_2exp(frac):
    """2^frac via Horner polynomial, frac in [0, Q16_ONE)."""
    x = frac
    t = 3638
    t = 15743 + ((t * x) >> 16)
    t = 45426 + ((t * x) >> 16)
    return Q16_ONE + ((t * x) >> 16)

# ═══════════════════════════════════════════════════════════════════════
# BLOCK CHAIN STATE
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class BlockMeta:
    height: int
    time: int
    powDiffQ: int    # bitsQ
    profile_index: int

# ═══════════════════════════════════════════════════════════════════════
# BITSQ — exact match of casert_next_bitsq()
# ═══════════════════════════════════════════════════════════════════════

def casert_next_bitsq(chain: List[BlockMeta], next_height: int) -> int:
    if not chain or next_height <= 0:
        return GENESIS_BITSQ

    # Anchor
    epoch = next_height // 131553
    anchor_idx = 0
    if epoch > 0:
        ai = epoch * 131553 - 1
        anchor_idx = max(0, min(ai, len(chain) - 1))
    anchor_time = chain[anchor_idx].time
    anchor_bitsq = chain[anchor_idx].powDiffQ if anchor_idx > 0 else GENESIS_BITSQ

    # Time delta
    parent_idx = len(chain) - 1
    expected_pt = anchor_time + (parent_idx - anchor_idx) * TARGET_SPACING
    td = chain[-1].time - expected_pt

    # Exponential
    halflife = BITSQ_HALF_LIFE_V2
    exponent = ((-td) * Q16_ONE) // halflife

    shifts = exponent >> 16
    frac = exponent & 0xFFFF

    factor = horner_2exp(frac)
    raw_result = (anchor_bitsq * factor) >> 16

    if shifts > 0:
        if shifts > 24: raw_result = MAX_BITSQ
        else: raw_result <<= shifts
    elif shifts < 0:
        rshifts = -shifts
        if rshifts > 24: raw_result = 0
        else: raw_result >>= rshifts

    # Delta cap (12.5%, V6: no Ahead Guard)
    prev_bitsq = chain[-1].powDiffQ if chain[-1].powDiffQ else GENESIS_BITSQ
    max_delta = prev_bitsq // BITSQ_MAX_DELTA_DEN_V2
    if max_delta < 1: max_delta = 1

    delta = raw_result - prev_bitsq
    delta = max(-max_delta, min(max_delta, delta))

    # V6: NO Ahead Guard — bitsQ adjusts freely

    result = prev_bitsq + delta
    return max(MIN_BITSQ, min(MAX_BITSQ, result))

# ═══════════════════════════════════════════════════════════════════════
# CASERT EQUALIZER — bit-exact PID from casert_compute()
# ═══════════════════════════════════════════════════════════════════════

def casert_compute(chain: List[BlockMeta], next_height: int,
                   now_time: int, h_max: int = H_MAX) -> Tuple[int, int, int]:
    """
    Returns (bitsq, profile_index, lag).
    Exact reimplementation of src/pow/casert.cpp casert_compute().
    """
    bitsq = casert_next_bitsq(chain, next_height)

    if len(chain) < 2 or next_height <= 1:
        return bitsq, 0, 0

    # ── Compute signals ──

    # Instantaneous log-ratio
    dt = chain[-1].time - chain[-2].time
    dt = max(DT_MIN, min(DT_MAX, dt))
    r_n = log2_q16(TARGET_SPACING) - log2_q16(dt)

    # Schedule lag
    elapsed = chain[-1].time - GENESIS_TIME
    if elapsed >= 0:
        expected_h = elapsed // TARGET_SPACING
    else:
        expected_h = -((-elapsed + TARGET_SPACING - 1) // TARGET_SPACING)
    lag = int((next_height - 1) - expected_h)

    # EWMA computation over last 128 blocks
    S, M, V = 0, 0, 0
    I = 0

    lookback = min(len(chain), 128)
    start = len(chain) - lookback

    for i in range(start + 1, len(chain)):
        d = chain[i].time - chain[i-1].time
        d = max(DT_MIN, min(DT_MAX, d))
        r = log2_q16(TARGET_SPACING) - log2_q16(d)

        # EWMA short
        S = (EWMA_SHORT_ALPHA * r + (EWMA_DENOM - EWMA_SHORT_ALPHA) * S) >> 8
        # EWMA long
        M = (EWMA_LONG_ALPHA * r + (EWMA_DENOM - EWMA_LONG_ALPHA) * M) >> 8
        # Volatility
        abs_dev = abs(r - S)
        V = (EWMA_VOL_ALPHA * abs_dev + (EWMA_DENOM - EWMA_VOL_ALPHA) * V) >> 8

        # Integrator
        h_i = chain[i].height
        e_i = chain[i].time - GENESIS_TIME
        if e_i >= 0:
            exp_i = e_i // TARGET_SPACING
        else:
            exp_i = -((-e_i + TARGET_SPACING - 1) // TARGET_SPACING)
        lag_i = int(h_i - exp_i)
        L_i_q16 = lag_i * Q16_ONE
        I = (INTEG_RHO * I + EWMA_DENOM * INTEG_ALPHA * L_i_q16) >> 8
        I = max(-INTEG_MAX, min(INTEG_MAX, I))

    burst_score = S - M

    # ── Control signal ──
    L_q16 = lag * Q16_ONE
    U = (K_R * r_n +
         K_L * (L_q16 >> 16) +
         K_I * (I >> 16) +
         K_B * burst_score +
         K_V * V)
    H_raw = int(U >> 16)

    H = max(H_MIN, min(h_max, H_raw))

    # Safety rule 1: never harden when behind
    if lag <= 0:
        H = min(H, 0)

    # Safety rule 2: minimum chain depth
    if len(chain) < 10:
        H = min(H, 0)

    # ── Slew rate + V5/V6 rules ──
    if len(chain) >= 3:
        # Use stored profile_index (V4+)
        prev_H = chain[-1].profile_index
        prev_H = max(H_MIN, min(h_max, prev_H))

        # V6 slew rate: ±1
        slew = V6_SLEW_RATE
        H = max(prev_H - slew, min(prev_H + slew, H))

        # Lag floor
        if lag > 10:
            lag_floor = min(lag // V3_LAG_FLOOR_DIV, h_max)
            H = max(H, lag_floor)

        # V5 safety rule 1 post-slew
        if lag <= 0:
            H = min(H, 0)

        # EBR
        if lag <= EBR_ENTER:
            if lag <= EBR_LEVEL_E4:
                H = min(H, H_MIN)
            elif lag <= EBR_LEVEL_E3:
                H = min(H, -3)
            elif lag <= EBR_LEVEL_E2:
                H = min(H, -2)
            else:
                H = min(H, 0)

        # V5 extreme cap
        if H >= V5_EXTREME_MIN and H > prev_H + 1:
            H = prev_H + 1

        # V6: H11/H12 reservation
        if h_max <= 12:
            if H >= 12 and lag < V6_H12_MIN_LAG:
                H = 11
            if H >= 11 and lag < V6_H11_MIN_LAG:
                H = 10
        else:
            # Extended tables: generalized reservation
            reserve_start = max(10, int(h_max * 0.75))
            for lvl in range(h_max, reserve_start - 1, -1):
                required_lag = reserve_start + (lvl - reserve_start) * 2
                if H >= lvl and lag < required_lag:
                    H = lvl - 1

        H = max(H_MIN, min(h_max, H))

    # ── Anti-stall ──
    if now_time > 0 and chain:
        stall = max(0, now_time - chain[-1].time)
        if stall >= ANTISTALL_FLOOR_V5 and H > 0:
            decay_time = stall - ANTISTALL_FLOOR_V5
            decayed_H = H - 1  # V6: immediate first drop
            while decayed_H > 0 and decay_time > 0:
                if decayed_H >= 7: cost = 600
                elif decayed_H >= 4: cost = 900
                else: cost = 1200
                if decay_time < cost: break
                decay_time -= cost
                decayed_H -= 1
            H = decayed_H
        # Easing emergency
        if stall >= ANTISTALL_FLOOR_V5 and H <= 0:
            time_at_b0 = stall - ANTISTALL_FLOOR_V5
            if time_at_b0 > ANTISTALL_EASING_EXTRA:
                easing_time = time_at_b0 - ANTISTALL_EASING_EXTRA
                easing_drops = int(easing_time // 1800)
                H = max(H_MIN, -easing_drops)

    return bitsq, H, lag

# ═══════════════════════════════════════════════════════════════════════
# STABILITY MODEL — calibrated from production data
#
# The stability basin check (verify_stability_basin in convergencex.cpp)
# runs k perturbation trials. Each trial:
#   1. Perturbs solution by ±scale in each of 32 dimensions
#   2. Runs `steps` gradient descent steps
#   3. Checks L1 contraction: d_new <= d_prev + margin_eff
#   4. Checks ratio: d_final * C_DEN <= d_0 * C_NUM + margin_eff
# All k trials must pass.
#
# The pass rate depends on the "basin quality" of the solution,
# which varies per nonce. We model it as:
#   P(pass) = base_rate ^ k_eff
# where base_rate depends on {scale, steps, margin} and the
# landscape properties at the current difficulty.
# ═══════════════════════════════════════════════════════════════════════

def estimate_stability(scale, steps, k, margin):
    """
    Estimate stability pass rate from profile parameters.
    Calibrated against production data from blocks 4976-5005.

    Key observations:
    - scale=1: most nonces pass easily (basin is small perturbation)
    - scale=2: significant filtering, margin and k matter
    - scale=3: almost nothing passes (retired in V6)
    - Higher k: more trials, each must pass → geometric decrease
    - More steps: more gradient recovery → slightly helps
    - Lower margin: tighter acceptance → harder
    """
    if scale == 1:
        # Scale=1: single-element perturbation
        # Base pass rate per trial is high
        base = 0.99 - (steps - 2) * 0.005 - max(0, 200 - margin) * 0.001
        base = max(0.85, min(0.999, base))
        return min(100.0, max(0.1, 100.0 * (base ** k)))

    elif scale == 2:
        # Scale=2: 2-element perturbation, much harder
        # Calibrated to match: H5=65%, H6=50%, H7=45%, H8=35%, H9=25%, H10=12%, H11=5%, H12=3%
        base = 0.92 - (steps - 5) * 0.02 - max(0, 150 - margin) * 0.005
        base = max(0.50, min(0.95, base))
        pct = 100.0 * (base ** k)
        # Margin correction: lower margin = exponentially harder
        margin_factor = max(0.01, (margin - 80) / 60.0)
        pct *= margin_factor
        return max(0.1, min(100.0, pct))

    else:  # scale >= 3
        # Scale=3+: almost impossible (retired)
        base = 0.60 - (scale - 3) * 0.15
        base = max(0.10, base)
        pct = 100.0 * (base ** (k * steps))
        return max(0.1, min(5.0, pct))


def estimate_eff_difficulty(profile: ProfileParams):
    """
    Effective difficulty multiplier relative to B0.
    Combines bitsQ difficulty with stability rejection.
    """
    stab = max(0.1, profile.stability_pct) / 100.0
    # Base difficulty from profile complexity
    base = 1.0 + (profile.scale - 1) * 0.4 + (profile.steps - 4) * 0.12 + (profile.k - 4) * 0.08
    # Stability rejection amplifies effective difficulty
    return base / stab

# ═══════════════════════════════════════════════════════════════════════
# BLOCK TIME SAMPLING
# ═══════════════════════════════════════════════════════════════════════

def sample_block_dt(profile: ProfileParams, bitsq: int, hashrate_kh: float,
                    rng: random.Random) -> float:
    """
    Sample block time using exponential distribution.

    The expected block time is determined by:
    1. bitsQ numeric difficulty: higher bitsQ = harder to find hash < target
    2. Stability filter: only stability_pct% of valid hashes pass
    3. Hashrate: more hashes/s = faster

    Model: E[dt] = (2^bitsQ_float) / (hashrate * stability_fraction * C)
    where C is calibrated so B0 at genesis_bitsq with 1.3 kH/s ≈ 600s.
    """
    bitsq_float = bitsq / Q16_ONE
    stab = max(0.001, profile.stability_pct / 100.0)

    # Calibration: at bitsQ=11.68, 1.3 kH/s, B0 (100% stable) → ~600s
    # 2^11.68 / (1.3 * 1.0 * C) = 600 → C = 2^11.68 / (1.3 * 600) ≈ 4.22
    C_cal = (2 ** 11.68) / (1.3 * 600.0)

    expected_dt = (2 ** bitsq_float) / (max(hashrate_kh, 0.01) * stab * C_cal)
    expected_dt = max(1.0, expected_dt)

    return rng.expovariate(1.0 / expected_dt)

# ═══════════════════════════════════════════════════════════════════════
# HASHRATE SCENARIOS
# ═══════════════════════════════════════════════════════════════════════

SCENARIOS = {
    "current": {
        "desc": "Current network (~1.3 kH/s, 3-4 miners)",
        "base": 1.3,
        "events": [],
    },
    "growth_2x": {
        "desc": "2x growth over 200 blocks",
        "base": 1.3,
        "events": [(200, 2.6)],
    },
    "growth_5x": {
        "desc": "5x growth: new miners join at block +200",
        "base": 1.3,
        "events": [(200, 6.5)],
    },
    "growth_10x": {
        "desc": "10x growth: major adoption at block +300",
        "base": 1.3,
        "events": [(300, 13.0)],
    },
    "growth_50x": {
        "desc": "50x growth: viral adoption at block +200",
        "base": 1.3,
        "events": [(200, 65.0)],
    },
    "shock_drop": {
        "desc": "Top miner leaves: 1.3 → 0.5 kH/s",
        "base": 1.3,
        "events": [(100, 0.5)],
    },
    "volatile": {
        "desc": "Miners join/leave: 1.3→3→0.8→5→1.5→8→2",
        "base": 1.3,
        "events": [(100, 3.0), (200, 0.8), (350, 5.0),
                   (500, 1.5), (700, 8.0), (900, 2.0)],
    },
    "gradual_10x": {
        "desc": "Gradual 10x: +1 kH/s every 100 blocks",
        "base": 1.3,
        "events": [(100, 2.3), (200, 3.3), (300, 4.3), (400, 5.3),
                   (500, 6.3), (600, 7.3), (700, 8.3), (800, 9.3),
                   (900, 10.3), (1000, 11.3), (1100, 12.3), (1200, 13.0)],
    },
    "production_replay": {
        "desc": "Replay of blocks 4990-5006 pattern (fast climb to H10)",
        "base": 1.3,
        "events": [],  # uses variance=low to reproduce the observed fast blocks
    },
}

def get_hashrate(scenario, block_offset):
    hr = scenario["base"]
    for trigger_offset, new_hr in scenario["events"]:
        if block_offset >= trigger_offset:
            hr = new_hr
    return hr

# ═══════════════════════════════════════════════════════════════════════
# EXTENDED PROFILE TABLE GENERATION
# ═══════════════════════════════════════════════════════════════════════

def generate_extended_profiles(n_hardening, strategy="smooth"):
    """
    Generate extended profile tables with n_hardening profiles (H1..Hn).
    Easing + B0 always included unchanged.

    Strategies:
      smooth: target ~3-5% stability drop per profile level
      aggressive: faster difficulty ramp, fewer profiles needed
      conservative: very gradual, maximum granularity
    """
    base = [p for p in PROFILES_17 if p.index <= 0]

    if strategy == "smooth":
        return _gen_smooth(base, n_hardening)
    elif strategy == "aggressive":
        return _gen_aggressive(base, n_hardening)
    elif strategy == "conservative":
        return _gen_conservative(base, n_hardening)
    elif strategy == "current":
        return list(PROFILES_17)
    else:
        return list(PROFILES_17)


def _gen_smooth(base, n_h):
    """
    Smooth strategy: target stability curve from 97% to 1%
    with approximately equal logarithmic steps.
    """
    profiles = list(base)

    # Target stability at each level (geometric decrease)
    targets = []
    for i in range(n_h):
        t = i / max(n_h - 1, 1)
        stab = 97.0 * math.exp(-t * math.log(97.0 / 0.5))
        targets.append(max(0.5, stab))

    # Generate profiles to hit targets
    scale = 1
    steps = 5
    k = 4
    margin = 170

    for i, target_stab in enumerate(targets):
        # Find params that give closest stability to target
        best_params = _find_params_for_stability(target_stab, scale, steps, k, margin)
        scale, steps, k, margin = best_params

        stab = estimate_stability(scale, steps, k, margin)
        name = f"H{i+1}"
        p = ProfileParams(i+1, name, scale, steps, k, margin, stab, 0)
        p.eff_diff = estimate_eff_difficulty(p)
        profiles.append(p)

    return profiles


def _gen_aggressive(base, n_h):
    """Aggressive: faster stability drop, hit 1% by H12."""
    profiles = list(base)
    params_sequence = [
        (1,5,4,170), (1,5,5,155), (1,6,5,145), (1,6,6,135),
        (2,5,5,135), (2,6,5,125), (2,6,6,120), (2,7,6,115),
        (2,7,7,110), (2,7,7,100), (2,8,7,95), (2,8,8,90),
        (2,9,8,85), (2,9,9,80), (2,10,9,75), (2,10,10,70),
        (3,8,8,100), (3,9,8,95), (3,9,9,90), (3,10,9,85),
    ]
    for i in range(min(n_h, len(params_sequence))):
        s, st, kk, m = params_sequence[i]
        stab = estimate_stability(s, st, kk, m)
        name = f"H{i+1}"
        p = ProfileParams(i+1, name, s, st, kk, m, stab, 0)
        p.eff_diff = estimate_eff_difficulty(p)
        profiles.append(p)
    return profiles


def _gen_conservative(base, n_h):
    """Conservative: very gradual, margin decreases by 3 per level."""
    profiles = list(base)
    scale = 1
    steps = 5
    k = 4
    margin = 175

    for i in range(n_h):
        stab = estimate_stability(scale, steps, k, margin)
        name = f"H{i+1}"
        p = ProfileParams(i+1, name, scale, steps, k, margin, stab, 0)
        p.eff_diff = estimate_eff_difficulty(p)
        profiles.append(p)

        # Very gradual parameter changes
        margin -= 3
        if margin < 90 and scale < 2:
            scale = 2
            margin = 145
            steps = 5
            k = 5
        elif margin < 80 and scale == 2 and k < 10:
            k += 1
            margin += 8
        elif margin < 80 and steps < 12:
            steps += 1
            margin += 5

        margin = max(70, margin)

    return profiles


def _find_params_for_stability(target_stab, prev_scale, prev_steps, prev_k, prev_margin):
    """Find parameter combination closest to target stability."""
    best = (prev_scale, prev_steps, prev_k, prev_margin)
    best_err = abs(estimate_stability(*best) - target_stab)

    for s in range(max(1, prev_scale), min(prev_scale + 2, 4)):
        for st in range(max(2, prev_steps - 1), min(prev_steps + 3, 14)):
            for kk in range(max(3, prev_k - 1), min(prev_k + 3, 14)):
                for m in range(max(60, prev_margin - 25), min(prev_margin + 5, 300), 3):
                    stab = estimate_stability(s, st, kk, m)
                    err = abs(stab - target_stab)
                    # Penalty for large parameter jumps
                    jump = (abs(s-prev_scale)*5 + abs(st-prev_steps) +
                            abs(kk-prev_k) + abs(m-prev_margin)*0.05)
                    err += jump * 0.3
                    if err < best_err:
                        best_err = err
                        best = (s, st, kk, m)

    return best

# ═══════════════════════════════════════════════════════════════════════
# SIMULATOR
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SimConfig:
    profiles: List[ProfileParams]
    n_blocks: int = 1000
    start_height: int = 5000
    scenario_name: str = "current"
    variance: str = "medium"
    seed: int = 42

def run_simulation(config: SimConfig) -> List[Dict]:
    rng = random.Random(config.seed)
    scenario = SCENARIOS.get(config.scenario_name, SCENARIOS["current"])
    pmap = make_profile_map(config.profiles)
    h_max_val = max(p.index for p in config.profiles)

    # Seed chain
    chain: List[BlockMeta] = []
    seed_time = GENESIS_TIME + (config.start_height - 5) * TARGET_SPACING
    for i in range(5):
        chain.append(BlockMeta(
            height=config.start_height - 5 + i,
            time=seed_time + i * TARGET_SPACING,
            powDiffQ=GENESIS_BITSQ,
            profile_index=0,
        ))

    sim_time = chain[-1].time
    rows = []

    for blk in range(config.n_blocks):
        next_h = chain[-1].height + 1
        block_offset = next_h - config.start_height

        # Hashrate with variance
        base_hr = get_hashrate(scenario, block_offset)
        if config.variance == "high":
            hr = base_hr * rng.uniform(0.3, 2.5)
        elif config.variance == "medium":
            hr = base_hr * rng.uniform(0.6, 1.5)
        elif config.variance == "low":
            hr = base_hr * rng.uniform(0.85, 1.15)
        else:
            hr = base_hr

        # Compute bitsQ + profile
        bitsq, profile_idx, lag = casert_compute(chain, next_h, sim_time, h_max_val)

        # Get profile params
        profile = pmap.get(profile_idx)
        if profile is None:
            profile = pmap.get(0)  # fallback to B0

        # Sample block time
        dt = sample_block_dt(profile, bitsq, hr, rng)
        dt = max(1.0, dt)

        new_time = int(sim_time + dt)

        chain.append(BlockMeta(
            height=next_h, time=new_time,
            powDiffQ=bitsq, profile_index=profile_idx,
        ))
        sim_time = new_time

        # Recompute lag at new time
        e = new_time - GENESIS_TIME
        exp_h = e // TARGET_SPACING if e >= 0 else 0
        final_lag = int((next_h) - exp_h)

        rows.append({
            "height": next_h,
            "dt": int(dt),
            "profile_index": profile_idx,
            "profile_name": profile.name,
            "stability_pct": profile.stability_pct,
            "lag": lag,
            "final_lag": final_lag,
            "bitsq": bitsq,
            "bitsq_float": round(bitsq / Q16_ONE, 3),
            "hashrate_kh": round(hr, 3),
        })

    return rows

# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Analysis:
    name: str
    scenario: str
    n_blocks: int
    mean_dt: float
    std_dt: float
    median_dt: float
    p95_dt: float
    p99_dt: float
    max_dt: float
    sawtooth: float       # avg |profile_jump| > 2
    smoothness: float     # avg |profile_change| per block
    max_profile_jump: int
    blocks_over_20m: int
    blocks_over_40m: int
    blocks_over_60m: int
    max_consecutive_slow: int
    lag_min: int
    lag_max: int
    lag_std: float
    profile_hist: Dict[str, int]
    n_active_profiles: int
    bitsq_range: Tuple[float, float]
    verdict: str
    score: float  # composite score (lower = better)


def analyze(rows, name="", scenario=""):
    n = len(rows)
    if n == 0: return None

    dts = [r["dt"] for r in rows]
    lags = [r["lag"] for r in rows]
    profiles = [r["profile_index"] for r in rows]
    bitsqs = [r["bitsq_float"] for r in rows]

    mean_dt = statistics.mean(dts)
    std_dt = statistics.stdev(dts) if n > 1 else 0
    median_dt = statistics.median(dts)
    sdts = sorted(dts)
    p95 = sdts[int(n*0.95)] if n > 20 else max(dts)
    p99 = sdts[int(n*0.99)] if n > 100 else max(dts)

    b20 = sum(1 for d in dts if d >= 1200)
    b40 = sum(1 for d in dts if d >= 2400)
    b60 = sum(1 for d in dts if d >= 3600)

    # Sawtooth: large jumps
    sawtooth = sum(abs(profiles[i]-profiles[i-1])
                   for i in range(1, len(profiles))
                   if abs(profiles[i]-profiles[i-1]) > 2) / max(n, 1)

    # Smoothness
    smoothness = sum(abs(profiles[i]-profiles[i-1])
                     for i in range(1, len(profiles))) / max(n-1, 1)

    max_jump = max((abs(profiles[i]-profiles[i-1]) for i in range(1, len(profiles))),
                   default=0)

    # Max consecutive slow blocks
    max_cons = cur = 0
    for d in dts:
        if d >= 1200:
            cur += 1; max_cons = max(max_cons, cur)
        else:
            cur = 0

    prof_hist = {}
    for r in rows:
        pn = r["profile_name"]
        prof_hist[pn] = prof_hist.get(pn, 0) + 1

    lag_std = statistics.stdev(lags) if n > 1 else 0

    # Composite score: weighted badness metric
    # Lower is better. Penalizes: variance, tail blocks, sawtooth, lag spread
    target_dev = abs(mean_dt - 600)
    score = (target_dev / 60 * 10 +      # mean deviation from target
             std_dt / 600 * 20 +           # normalized variance
             b60 * 50 +                     # severe: >60min blocks
             b40 * 10 +                     # bad: >40min blocks
             b20 * 2 +                      # moderate: >20min blocks
             sawtooth * 100 +               # sawtooth penalty
             max_cons * 15 +                # consecutive stuck
             lag_std * 2)                   # lag instability

    # Verdict
    if b60 >= 3 or max_cons >= 5 or sawtooth > 3:
        verdict = "RED"
    elif b40 >= 5 or max_cons >= 3 or sawtooth > 1:
        verdict = "YELLOW"
    else:
        verdict = "GREEN"

    return Analysis(
        name=name, scenario=scenario, n_blocks=n,
        mean_dt=mean_dt, std_dt=std_dt, median_dt=median_dt,
        p95_dt=p95, p99_dt=p99, max_dt=max(dts),
        sawtooth=sawtooth, smoothness=smoothness, max_profile_jump=max_jump,
        blocks_over_20m=b20, blocks_over_40m=b40, blocks_over_60m=b60,
        max_consecutive_slow=max_cons, lag_min=min(lags), lag_max=max(lags),
        lag_std=lag_std, profile_hist=prof_hist,
        n_active_profiles=len(set(profiles)),
        bitsq_range=(min(bitsqs), max(bitsqs)),
        verdict=verdict, score=score,
    )


def print_analysis(a: Analysis, verbose=True):
    vc = {R: R, "GREEN": G, "YELLOW": Y, "RED": R}
    color = vc.get(a.verdict, X)
    icon = {"GREEN": "G", "YELLOW": "Y", "RED": "R"}.get(a.verdict, "?")

    print(f"\n{B}{C}{a.name} [{a.scenario}]{X}")
    print(f"{D}{'─'*72}{X}")
    print(f"  Mean block time:     {a.mean_dt/60:>7.1f}m   (target: 10.0m)")
    print(f"  Std deviation:       {a.std_dt/60:>7.1f}m")
    print(f"  Median:              {a.median_dt/60:>7.1f}m")
    print(f"  p95 / p99 / max:     {a.p95_dt/60:.0f}m / {a.p99_dt/60:.0f}m / {a.max_dt/60:.0f}m")
    print(f"  Blocks > 20m/40m/60m:{a.blocks_over_20m} / {a.blocks_over_40m} / {a.blocks_over_60m}")
    print(f"  Max consec. >20m:    {a.max_consecutive_slow}")
    print(f"  Sawtooth:            {a.sawtooth:.3f}  {D}(0 = perfect){X}")
    print(f"  Smoothness:          {a.smoothness:.3f}  {D}(avg |delta H| per block){X}")
    print(f"  Max profile jump:    {a.max_profile_jump}")
    print(f"  Lag range:           {a.lag_min:+d} to {a.lag_max:+d}  (std={a.lag_std:.1f})")
    print(f"  bitsQ range:         {a.bitsq_range[0]:.3f} to {a.bitsq_range[1]:.3f}")
    print(f"  Active profiles:     {a.n_active_profiles}")
    print(f"  Composite score:     {a.score:.1f}  {D}(lower = better){X}")

    if verbose:
        print(f"\n  Profile distribution:")
        for pn in sorted(a.profile_hist.keys(),
                         key=lambda x: (0 if x[0]=='B' else (-1 if x[0]=='E' else 1),
                                       int(x[1:]) if len(x)>1 else 0)):
            cnt = a.profile_hist[pn]
            pct = cnt * 100.0 / a.n_blocks
            bar = '█' * int(pct / 2)
            print(f"    {pn:>4}: {cnt:>5} ({pct:5.1f}%)  {bar}")

    print(f"{D}{'─'*72}{X}")
    print(f"  Verdict: {color}{B}[{icon}] {a.verdict}{X}  |  Score: {a.score:.1f}")


def print_profile_table(profiles):
    print(f"\n{B}Profile Table ({len(profiles)} profiles){X}")
    print(f"{'─'*85}")
    print(f"  {'Name':>5}  {'Idx':>4}  {'Sc':>3}  {'St':>3}  {'K':>3}  "
          f"{'Mar':>4}  {'Stab%':>7}  {'EffDiff':>8}  {'Step':>7}")
    print(f"{'─'*85}")
    prev_stab = None
    for p in profiles:
        step = ""
        if prev_stab is not None and p.stability_pct < 100:
            step = f"{p.stability_pct - prev_stab:+.1f}%"
        if p.stability_pct < 100:
            prev_stab = p.stability_pct
        sc = G if p.stability_pct >= 50 else (Y if p.stability_pct >= 15 else R)
        print(f"  {p.name:>5}  {p.index:>4}  {p.scale:>3}  {p.steps:>3}  "
              f"{p.k:>3}  {p.margin:>4}  {sc}{p.stability_pct:>6.1f}%{X}  "
              f"{p.eff_diff:>8.2f}  {step:>7}")
    print(f"{'─'*85}")

# ═══════════════════════════════════════════════════════════════════════
# VALIDATION: check model against production blocks 5000-5005
# ═══════════════════════════════════════════════════════════════════════

def validate_model():
    """Compare simulator against observed production data."""
    print(f"\n{B}{M}MODEL VALIDATION — blocks 4997-5006 (production){X}")
    print(f"{D}{'─'*72}{X}")

    # Real data from explorer
    real_blocks = [
        (4997, "B0", 20),
        (4998, "B0", 16),
        (4999, "H3", 24),  # pre-fork, slew ±3
        (5000, "H4", 21),  # V6 ACTIVE: slew ±1
        (5001, "H5", 22),
        (5002, "H6", 19),
        (5003, "H7", 24),
        (5004, "H8", 36),
        (5005, "H9", 23),
    ]

    # Simulate from 4997
    chain = []
    t = GENESIS_TIME + 4992 * TARGET_SPACING
    for i in range(5):
        chain.append(BlockMeta(4992+i, t + i*TARGET_SPACING, GENESIS_BITSQ, 0))

    sim_time = chain[-1].time
    print(f"  {'Block':>7}  {'Real':>6}  {'RealDT':>7}  {'SimProfile':>10}  {'SimLag':>7}  {'Match':>6}")

    for height, real_profile, real_dt in real_blocks:
        h_max = H_MAX
        bitsq, sim_pi, sim_lag = casert_compute(chain, height, sim_time, h_max)

        # Map index to name
        pmap = make_profile_map(PROFILES_17)
        sim_p = pmap.get(sim_pi, pmap[0])
        match = "OK" if sim_p.name == real_profile else "MISS"
        mc = G if match == "OK" else R

        print(f"  {height:>7}  {real_profile:>6}  {real_dt:>6}s  "
              f"{sim_p.name:>10}  {sim_lag:>+7d}  {mc}{match:>6}{X}")

        # Add block to chain (use real dt for accuracy)
        sim_time += real_dt
        chain.append(BlockMeta(height, sim_time, bitsq, sim_pi))

    print(f"{D}{'─'*72}{X}")

# ═══════════════════════════════════════════════════════════════════════
# SWEEP MODE
# ═══════════════════════════════════════════════════════════════════════

def run_sweep(args):
    print(f"{B}{C}{'═'*72}{X}")
    print(f"{B}{C}  cASERT V6 Full Simulator — Calibration Sweep{X}")
    print(f"{B}{C}  Target: optimal profile configuration for block 10,000{X}")
    print(f"{B}{C}{'═'*72}{X}")

    # Step 0: Validate model
    validate_model()

    # Step 1: Profile table calibration check
    print(f"\n{B}{M}STABILITY MODEL CALIBRATION{X}")
    print(f"{D}{'─'*72}{X}")
    for p in PROFILES_17:
        if p.stability_pct >= 100: continue
        predicted = estimate_stability(p.scale, p.steps, p.k, p.margin)
        err = abs(predicted - p.stability_pct)
        mc = G if err < 5 else (Y if err < 15 else R)
        print(f"  {p.name:>4}: actual={p.stability_pct:5.1f}%  "
              f"model={predicted:5.1f}%  {mc}err={err:5.1f}%{X}")

    # Step 2: Generate tables
    table_configs = [
        ("current-17", "current", 12),
        ("smooth-20", "smooth", 20),
        ("smooth-30", "smooth", 30),
        ("smooth-50", "smooth", 50),
        ("aggressive-20", "aggressive", 20),
        ("conservative-30", "conservative", 30),
    ]

    scenarios_to_test = args.scenarios.split(",")

    all_results = []

    for table_name, strategy, n_h in table_configs:
        profiles = generate_extended_profiles(n_h, strategy)
        print(f"\n{B}{'═'*72}{X}")
        print(f"{B}Table: {table_name} ({len(profiles)} profiles, strategy={strategy}){X}")
        print_profile_table(profiles)

        for sc_name in scenarios_to_test:
            if sc_name not in SCENARIOS:
                continue

            seed_results = []
            for seed in range(args.seed, args.seed + args.seeds):
                config = SimConfig(
                    profiles=profiles,
                    n_blocks=args.blocks,
                    start_height=5000,
                    scenario_name=sc_name,
                    variance=args.variance,
                    seed=seed,
                )
                rows = run_simulation(config)
                a = analyze(rows, table_name, sc_name)
                seed_results.append(a)
                all_results.append(a)

            # Aggregate
            ns = len(seed_results)
            avg_mean = statistics.mean(r.mean_dt for r in seed_results)
            avg_std = statistics.mean(r.std_dt for r in seed_results)
            avg_saw = statistics.mean(r.sawtooth for r in seed_results)
            avg_smooth = statistics.mean(r.smoothness for r in seed_results)
            avg_score = statistics.mean(r.score for r in seed_results)
            greens = sum(1 for r in seed_results if r.verdict == "GREEN")
            yellows = sum(1 for r in seed_results if r.verdict == "YELLOW")
            reds = sum(1 for r in seed_results if r.verdict == "RED")

            vc = G if reds == 0 else (Y if reds < ns // 2 else R)
            sc_desc = SCENARIOS[sc_name]["desc"]
            print(f"\n  {O}{sc_desc}{X}")
            print(f"    {B}Aggregate ({ns} seeds):{X} "
                  f"mean={avg_mean/60:.1f}m  std={avg_std/60:.1f}m  "
                  f"saw={avg_saw:.3f}  smooth={avg_smooth:.3f}  "
                  f"score={avg_score:.0f}  "
                  f"{vc}G:{greens} Y:{yellows} R:{reds}{X}")

    # Step 3: Final ranking
    print(f"\n\n{B}{C}{'═'*72}{X}")
    print(f"{B}{C}  FINAL RANKING — All configurations by composite score{X}")
    print(f"{B}{C}{'═'*72}{X}")

    # Group by (table, scenario)
    groups = {}
    for r in all_results:
        key = (r.name, r.scenario)
        if key not in groups: groups[key] = []
        groups[key].append(r)

    ranked = []
    for (tname, scname), results in groups.items():
        avg_score = statistics.mean(r.score for r in results)
        avg_mean = statistics.mean(r.mean_dt for r in results)
        avg_std = statistics.mean(r.std_dt for r in results)
        avg_saw = statistics.mean(r.sawtooth for r in results)
        reds = sum(1 for r in results if r.verdict == "RED")
        total = len(results)
        ranked.append((avg_score, tname, scname, avg_mean, avg_std,
                       avg_saw, reds, total))

    ranked.sort()
    print(f"\n  {'#':>3}  {'Score':>6}  {'Config':>18}  {'Scenario':>14}  "
          f"{'Mean':>6}  {'Std':>6}  {'Saw':>5}  {'Reds':>6}")
    print(f"  {'─'*82}")
    for i, (score, tn, sn, mean, std, saw, reds, total) in enumerate(ranked):
        vc = G if reds == 0 else (Y if reds < total // 2 else R)
        print(f"  {i+1:>3}  {score:>6.0f}  {tn:>18}  {sn:>14}  "
              f"{mean/60:>5.1f}m  {std/60:>5.1f}m  {saw:>5.3f}  "
              f"{vc}{reds}/{total}{X}")

    # Step 4: Recommendation
    if ranked:
        best = ranked[0]
        print(f"\n{B}{G}RECOMMENDATION:{X}")
        print(f"  Best config: {B}{best[1]}{X} under {best[2]}")
        print(f"  Score: {best[0]:.0f}  Mean: {best[3]/60:.1f}m  "
              f"Std: {best[4]/60:.1f}m  Reds: {best[6]}/{best[7]}")

        # Find best per scenario
        print(f"\n  Best per scenario:")
        by_sc = {}
        for r in ranked:
            if r[2] not in by_sc:
                by_sc[r[2]] = r
        for sn, r in sorted(by_sc.items()):
            vc = G if r[6] == 0 else (Y if r[6] < r[7] // 2 else R)
            print(f"    {sn:>14}: {r[1]:>18}  score={r[0]:>5.0f}  "
                  f"{vc}{r[6]}/{r[7]} reds{X}")


def run_single(args):
    """Single simulation with detailed output."""
    print(f"{B}{C}{'═'*72}{X}")
    print(f"{B}{C}  cASERT V6 Full Simulator — Single Run{X}")
    print(f"{B}{C}{'═'*72}{X}")

    validate_model()

    profiles = generate_extended_profiles(args.n_profiles, args.strategy)
    print_profile_table(profiles)

    config = SimConfig(
        profiles=profiles,
        n_blocks=args.blocks,
        start_height=5000,
        scenario_name=args.scenario,
        variance=args.variance,
        seed=args.seed,
    )
    rows = run_simulation(config)

    # Write CSV
    outpath = os.path.join(os.path.dirname(__file__) or ".",
                           f"sim_v6_{args.scenario}_{args.n_profiles}H.csv")
    with open(outpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows: w.writerow(r)

    a = analyze(rows, f"{args.n_profiles}H-{args.strategy}", args.scenario)
    print_analysis(a, verbose=True)

    # Block-by-block for first 30 blocks
    print(f"\n{B}First 30 blocks:{X}")
    print(f"  {'Block':>7}  {'DT':>6}  {'Profile':>8}  {'Stab%':>6}  "
          f"{'Lag':>5}  {'bitsQ':>7}  {'HR':>5}")
    for r in rows[:30]:
        dtm = r['dt'] / 60
        dc = G if dtm < 15 else (Y if dtm < 30 else R)
        print(f"  {r['height']:>7}  {dc}{dtm:>5.1f}m{X}  {r['profile_name']:>8}  "
              f"{r['stability_pct']:>5.1f}%  {r['lag']:>+5d}  "
              f"{r['bitsq_float']:>7.3f}  {r['hashrate_kh']:>5.2f}")

    print(f"\n{D}Wrote {len(rows)} rows to {outpath}{X}")


def run_monte_carlo(args):
    """Monte Carlo with many seeds for statistical confidence."""
    print(f"{B}{C}{'═'*72}{X}")
    print(f"{B}{C}  cASERT V6 Monte Carlo — {args.monte_carlo} seeds{X}")
    print(f"{B}{C}{'═'*72}{X}")

    profiles = generate_extended_profiles(args.n_profiles, args.strategy)
    print_profile_table(profiles)

    results = []
    for seed in range(args.seed, args.seed + args.monte_carlo):
        config = SimConfig(
            profiles=profiles, n_blocks=args.blocks,
            start_height=5000, scenario_name=args.scenario,
            variance=args.variance, seed=seed,
        )
        rows = run_simulation(config)
        a = analyze(rows, f"MC-{args.n_profiles}H", args.scenario)
        results.append(a)
        # Progress
        if (seed - args.seed + 1) % 10 == 0:
            done = seed - args.seed + 1
            print(f"  {D}... {done}/{args.monte_carlo} seeds complete{X}")

    # Aggregate stats
    means = [r.mean_dt for r in results]
    stds = [r.std_dt for r in results]
    saws = [r.sawtooth for r in results]
    scores = [r.score for r in results]
    greens = sum(1 for r in results if r.verdict == "GREEN")
    yellows = sum(1 for r in results if r.verdict == "YELLOW")
    reds = sum(1 for r in results if r.verdict == "RED")

    print(f"\n{B}{C}Monte Carlo Results ({args.monte_carlo} seeds){X}")
    print(f"{D}{'─'*72}{X}")
    print(f"  Mean block time:    {statistics.mean(means)/60:.1f}m "
          f"(std across seeds: {statistics.stdev(means)/60:.2f}m)")
    print(f"  Std deviation:      {statistics.mean(stds)/60:.1f}m "
          f"(std: {statistics.stdev(stds)/60:.2f}m)")
    print(f"  Sawtooth:           {statistics.mean(saws):.4f} "
          f"(max: {max(saws):.4f})")
    print(f"  Composite score:    {statistics.mean(scores):.0f} "
          f"(std: {statistics.stdev(scores):.0f}, "
          f"best: {min(scores):.0f}, worst: {max(scores):.0f})")
    print(f"  Verdicts:           {G}GREEN:{greens}{X}  "
          f"{Y}YELLOW:{yellows}{X}  {R}RED:{reds}{X}")
    print(f"  GREEN rate:         {greens*100/len(results):.0f}%")
    print(f"{D}{'─'*72}{X}")

    # Confidence interval for mean block time
    m = statistics.mean(means)
    se = statistics.stdev(means) / math.sqrt(len(means))
    print(f"  95% CI mean dt:     [{(m-1.96*se)/60:.1f}m, {(m+1.96*se)/60:.1f}m]")

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="cASERT V6 Full Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--sweep", action="store_true",
                    help="Run full calibration sweep")
    ap.add_argument("--monte-carlo", type=int, default=0,
                    help="Monte Carlo mode: N seeds")
    ap.add_argument("--n-profiles", type=int, default=12,
                    help="Number of hardening profiles (default: 12 = current)")
    ap.add_argument("--strategy", default="current",
                    choices=["current", "smooth", "aggressive", "conservative"],
                    help="Profile table strategy")
    ap.add_argument("--scenario", default="current",
                    choices=list(SCENARIOS.keys()),
                    help="Hashrate scenario")
    ap.add_argument("--scenarios", default="current,growth_2x,growth_5x,growth_10x,volatile,gradual_10x",
                    help="Comma-separated scenarios for sweep")
    ap.add_argument("--blocks", type=int, default=1000,
                    help="Blocks to simulate")
    ap.add_argument("--seeds", type=int, default=10,
                    help="Seeds per config in sweep mode")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--variance", default="medium",
                    choices=["none", "low", "medium", "high"])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.sweep:
        run_sweep(args)
    elif args.monte_carlo > 0:
        run_monte_carlo(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()

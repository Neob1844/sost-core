#!/usr/bin/env python3
"""
Anti-Stall Exhaustive Sweep + Conservative-30 Profile Table
═══════════════════════════════════════════════════════════════

72 combinations × 5 seeds = 360 simulations with 3 concurrent miner types.

Variables:
  V1: Anti-stall activation time (30/60/90/120 min)
  V2: Decay interval per level (2.5/5/7.5/10/12.5/15 min)
  V3: Network hashrate (1.3/5/13 kH/s)

Miners:
  Small:  34 att/s  (laptop)
  Medium: 100 att/s (Beelink)
  Large:  370 att/s (vostokzyf)

Usage:
    python3 scripts/antistall_sweep.py
    python3 scripts/antistall_sweep.py --seeds 10 --blocks 2000
"""

import argparse
import csv
import math
import os
import random
import statistics
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS — mirror params.h
# ═══════════════════════════════════════════════════════════════════════
GENESIS_TIME   = 1773597600
TARGET_SPACING = 600
GENESIS_BITSQ  = 765730
Q16_ONE        = 65536
MIN_BITSQ      = Q16_ONE
MAX_BITSQ      = 255 * Q16_ONE

BITSQ_HALF_LIFE_V2     = 86400
BITSQ_MAX_DELTA_DEN_V2 = 8

K_R = 3277; K_L = 26214; K_I = 9830; K_B = 3277; K_V = 1311
EWMA_SHORT_ALPHA = 32; EWMA_LONG_ALPHA = 3; EWMA_VOL_ALPHA = 16; EWMA_DENOM = 256
INTEG_RHO = 253; INTEG_ALPHA = 1; INTEG_MAX = 6553600

H_MIN = -4; H_MAX = 12
DT_MIN = 1; DT_MAX = 86400
V3_LAG_FLOOR_DIV = 8
V5_EXTREME_MIN = 10
EBR_ENTER = -10; EBR_LEVEL_E2 = -15; EBR_LEVEL_E3 = -20; EBR_LEVEL_E4 = -25
ANTISTALL_EASING_EXTRA = 21600
V6_SLEW_RATE = 1; V6_H11_MIN_LAG = 11; V6_H12_MIN_LAG = 21

# ANSI
G="\033[92m";Y="\033[93m";R="\033[91m";C="\033[96m";D="\033[2m"
B="\033[1m";X="\033[0m";O="\033[38;5;208m";M="\033[95m";W="\033[97m"

# ═══════════════════════════════════════════════════════════════════════
# PROFILE TABLE — current 17 + conservative-30 proposal
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Prof:
    index: int
    name: str
    scale: int
    steps: int
    k: int
    margin: int
    stab_pct: float
    eff_diff: float

PROFILES_17 = [
    Prof(-4,"E4",1,2,3,280,100.0,0.35), Prof(-3,"E3",1,3,3,240,100.0,0.50),
    Prof(-2,"E2",1,4,3,225,100.0,0.65), Prof(-1,"E1",1,4,4,205,100.0,0.80),
    Prof(0,"B0",1,4,4,185,100.0,1.00),
    Prof(1,"H1",1,5,4,170,97.0,1.25),   Prof(2,"H2",1,5,5,160,92.0,1.55),
    Prof(3,"H3",1,6,5,150,85.0,2.00),   Prof(4,"H4",1,6,6,145,78.0,2.50),
    Prof(5,"H5",2,5,5,140,65.0,3.20),   Prof(6,"H6",2,6,5,135,50.0,4.20),
    Prof(7,"H7",2,6,6,130,45.0,5.50),   Prof(8,"H8",2,7,6,125,35.0,7.50),
    Prof(9,"H9",2,7,7,120,25.0,10.0),   Prof(10,"H10",2,7,7,115,12.0,14.0),
    Prof(11,"H11",2,8,7,110,5.0,20.0),  Prof(12,"H12",2,8,8,105,3.0,30.0),
]

# ─────────────────────────────────────────────────────────────────────
# Conservative-30 Profile Table (proposed for block 10,000)
#
# Design principles:
#   - Scale=1 for H1-H14 (gentle perturbation range)
#   - Scale=2 for H15-H28 (moderate perturbation range)
#   - Scale=2 with high k for H29-H30 (reserve brake)
#   - Margin decreases by 3-5 per level (smooth gradient)
#   - k increases every ~5 levels, steps every ~8 levels
#   - Each level changes AT MOST one parameter
#   - Target: ~3% stability drop per level in middle range
# ─────────────────────────────────────────────────────────────────────
PROFILES_30 = [
    # Easing + B0 (unchanged)
    Prof(-4,"E4",1,2,3,280,100.0,0.35), Prof(-3,"E3",1,3,3,240,100.0,0.50),
    Prof(-2,"E2",1,4,3,225,100.0,0.65), Prof(-1,"E1",1,4,4,205,100.0,0.80),
    Prof(0,"B0",1,4,4,185,100.0,1.00),
    # Scale=1 range: H1-H14 (gentle)
    Prof(1, "H1", 1,5,4,175, 98.0, 1.15),
    Prof(2, "H2", 1,5,4,170, 97.0, 1.25),
    Prof(3, "H3", 1,5,5,167, 95.0, 1.35),
    Prof(4, "H4", 1,5,5,163, 93.0, 1.45),
    Prof(5, "H5", 1,5,5,159, 91.0, 1.55),
    Prof(6, "H6", 1,6,5,155, 88.0, 1.70),
    Prof(7, "H7", 1,6,5,150, 85.0, 2.00),
    Prof(8, "H8", 1,6,6,147, 82.0, 2.20),
    Prof(9, "H9", 1,6,6,143, 79.0, 2.40),
    Prof(10,"H10",1,6,6,139, 76.0, 2.60),
    Prof(11,"H11",1,7,6,135, 72.0, 2.90),
    Prof(12,"H12",1,7,6,130, 68.0, 3.20),
    Prof(13,"H13",1,7,7,126, 63.0, 3.60),
    Prof(14,"H14",1,7,7,122, 58.0, 4.00),
    # Scale=2 range: H15-H28 (moderate)
    Prof(15,"H15",2,5,5,145, 52.0, 4.50),
    Prof(16,"H16",2,5,5,140, 47.0, 5.00),
    Prof(17,"H17",2,6,5,137, 42.0, 5.60),
    Prof(18,"H18",2,6,6,133, 37.0, 6.30),
    Prof(19,"H19",2,6,6,129, 32.0, 7.20),
    Prof(20,"H20",2,7,6,125, 27.0, 8.20),
    Prof(21,"H21",2,7,7,121, 22.0, 9.50),
    Prof(22,"H22",2,7,7,117, 17.0, 11.0),
    Prof(23,"H23",2,7,7,113, 13.0, 13.0),
    Prof(24,"H24",2,8,7,110, 9.0, 16.0),
    Prof(25,"H25",2,8,7,106, 6.5, 19.0),
    Prof(26,"H26",2,8,8,103, 4.5, 23.0),
    Prof(27,"H27",2,8,8, 99, 3.0, 28.0),
    Prof(28,"H28",2,9,8, 95, 2.0, 35.0),
    # Reserve brake
    Prof(29,"H29",2,9,9, 91, 1.2, 45.0),
    Prof(30,"H30",2,10,9,87, 0.7, 60.0),
]

def pmap(profiles):
    return {p.index: p for p in profiles}

# ═══════════════════════════════════════════════════════════════════════
# MINER TYPES
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MinerType:
    name: str
    att_per_s: float      # attempts per second
    hashrate_kh: float    # kH/s contribution to network
    # Stability advantage: ratio vs average miner at each profile
    # Higher att/s → more nonces tried → more chances of finding a stable one
    # But stability is per-nonce, not cumulative — all miners have same P(stable)
    # The advantage is purely in speed: more attempts per second
    stab_multiplier: float  # 1.0 = same as reference

MINERS = [
    MinerType("small",   34,  0.034, 1.0),
    MinerType("medium", 100,  0.100, 1.0),
    MinerType("large",  370,  0.370, 1.0),
]

# ═══════════════════════════════════════════════════════════════════════
# FIXED-POINT MATH
# ═══════════════════════════════════════════════════════════════════════

def log2_q16(x):
    if x <= 0: return -(Q16_ONE * 20)
    if x == 1: return 0
    int_part = x.bit_length() - 1
    lo = 1 << int_part
    hi = lo << 1
    frac = ((x - lo) * Q16_ONE) // (hi - lo) if hi > lo else 0
    return int_part * Q16_ONE + frac

def horner_2exp(frac):
    x = frac
    t = 3638
    t = 15743 + ((t * x) >> 16)
    t = 45426 + ((t * x) >> 16)
    return Q16_ONE + ((t * x) >> 16)

# ═══════════════════════════════════════════════════════════════════════
# BITSQ
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class BlockMeta:
    height: int
    time: int
    powDiffQ: int
    profile_index: int

def casert_next_bitsq(chain, next_height):
    if not chain or next_height <= 0:
        return GENESIS_BITSQ
    epoch = next_height // 131553
    anchor_idx = 0
    if epoch > 0:
        ai = epoch * 131553 - 1
        anchor_idx = max(0, min(ai, len(chain) - 1))
    anchor_time = chain[anchor_idx].time
    anchor_bitsq = chain[anchor_idx].powDiffQ if anchor_idx > 0 else GENESIS_BITSQ
    parent_idx = len(chain) - 1
    expected_pt = anchor_time + (parent_idx - anchor_idx) * TARGET_SPACING
    td = chain[-1].time - expected_pt
    exponent = ((-td) * Q16_ONE) // BITSQ_HALF_LIFE_V2
    shifts = exponent >> 16
    frac = exponent & 0xFFFF
    factor = horner_2exp(frac)
    raw = (anchor_bitsq * factor) >> 16
    if shifts > 0:
        raw = MAX_BITSQ if shifts > 24 else raw << shifts
    elif shifts < 0:
        rs = -shifts
        raw = 0 if rs > 24 else raw >> rs
    prev_bitsq = chain[-1].powDiffQ or GENESIS_BITSQ
    max_d = max(1, prev_bitsq // BITSQ_MAX_DELTA_DEN_V2)
    delta = max(-max_d, min(max_d, raw - prev_bitsq))
    return max(MIN_BITSQ, min(MAX_BITSQ, prev_bitsq + delta))

# ═══════════════════════════════════════════════════════════════════════
# CASERT PID — bit-exact
# ═══════════════════════════════════════════════════════════════════════

def casert_compute(chain, next_height, now_time, h_max,
                   antistall_floor, decay_interval):
    """
    Full V6 equalizer. antistall_floor and decay_interval are variable.
    decay_interval: seconds per level drop (replaces zone-based costs).
    """
    bitsq = casert_next_bitsq(chain, next_height)
    if len(chain) < 2 or next_height <= 1:
        return bitsq, 0, 0, False

    # Signals
    dt = max(DT_MIN, min(DT_MAX, chain[-1].time - chain[-2].time))
    r_n = log2_q16(TARGET_SPACING) - log2_q16(dt)
    elapsed = chain[-1].time - GENESIS_TIME
    expected_h = elapsed // TARGET_SPACING if elapsed >= 0 else -((-elapsed + TARGET_SPACING - 1) // TARGET_SPACING)
    lag = int((next_height - 1) - expected_h)

    # EWMA
    S = M = V = 0; I = 0
    lb = min(len(chain), 128); st = len(chain) - lb
    for i in range(st + 1, len(chain)):
        d = max(DT_MIN, min(DT_MAX, chain[i].time - chain[i-1].time))
        r = log2_q16(TARGET_SPACING) - log2_q16(d)
        S = (EWMA_SHORT_ALPHA * r + (EWMA_DENOM - EWMA_SHORT_ALPHA) * S) >> 8
        M = (EWMA_LONG_ALPHA * r + (EWMA_DENOM - EWMA_LONG_ALPHA) * M) >> 8
        V = (EWMA_VOL_ALPHA * abs(r - S) + (EWMA_DENOM - EWMA_VOL_ALPHA) * V) >> 8
        h_i = chain[i].height
        e_i = chain[i].time - GENESIS_TIME
        exp_i = e_i // TARGET_SPACING if e_i >= 0 else -((-e_i + TARGET_SPACING - 1) // TARGET_SPACING)
        lag_i = int(h_i - exp_i)
        I = (INTEG_RHO * I + EWMA_DENOM * INTEG_ALPHA * lag_i * Q16_ONE) >> 8
        I = max(-INTEG_MAX, min(INTEG_MAX, I))

    # PID
    U = (K_R * r_n + K_L * ((lag * Q16_ONE) >> 16) + K_I * (I >> 16) +
         K_B * (S - M) + K_V * V)
    H = max(H_MIN, min(h_max, int(U >> 16)))

    if lag <= 0: H = min(H, 0)
    if len(chain) < 10: H = min(H, 0)

    in_antistall = False

    if len(chain) >= 3:
        prev_H = max(H_MIN, min(h_max, chain[-1].profile_index))
        H = max(prev_H - V6_SLEW_RATE, min(prev_H + V6_SLEW_RATE, H))
        if lag > 10:
            H = max(H, min(lag // V3_LAG_FLOOR_DIV, h_max))
        if lag <= 0: H = min(H, 0)
        if lag <= EBR_ENTER:
            if lag <= EBR_LEVEL_E4: H = min(H, H_MIN)
            elif lag <= EBR_LEVEL_E3: H = min(H, -3)
            elif lag <= EBR_LEVEL_E2: H = min(H, -2)
            else: H = min(H, 0)
        if H >= V5_EXTREME_MIN and H > prev_H + 1:
            H = prev_H + 1
        # V6 reservation
        if h_max <= 12:
            if H >= 12 and lag < V6_H12_MIN_LAG: H = 11
            if H >= 11 and lag < V6_H11_MIN_LAG: H = 10
        else:
            reserve_start = max(10, int(h_max * 0.75))
            for lvl in range(h_max, reserve_start - 1, -1):
                if H >= lvl and lag < reserve_start + (lvl - reserve_start) * 2:
                    H = lvl - 1
        H = max(H_MIN, min(h_max, H))

    # Anti-stall with VARIABLE parameters
    if now_time > 0 and chain:
        stall = max(0, now_time - chain[-1].time)
        if stall >= antistall_floor and H > 0:
            in_antistall = True
            decay_time = stall - antistall_floor
            H_decayed = H - 1  # V6: immediate first drop
            while H_decayed > 0 and decay_time > 0:
                if decay_time < decay_interval:
                    break
                decay_time -= decay_interval
                H_decayed -= 1
            H = H_decayed
        if stall >= antistall_floor and H <= 0:
            in_antistall = True
            time_at_b0 = stall - antistall_floor
            if time_at_b0 > ANTISTALL_EASING_EXTRA:
                easing_time = time_at_b0 - ANTISTALL_EASING_EXTRA
                H = max(H_MIN, -int(easing_time // 1800))

    return bitsq, H, lag, in_antistall

# ═══════════════════════════════════════════════════════════════════════
# BLOCK TIME SAMPLING WITH MULTI-MINER COMPETITION
# ═══════════════════════════════════════════════════════════════════════

def sample_block_competitive(profile, bitsq, total_hr_kh, miners, rng):
    """
    Simulate competitive mining: each miner races to find a block.
    Returns (dt, winning_miner_index, in_antistall_at_find).

    Each miner's expected time is proportional to their share of hashrate.
    The block goes to whoever finds it first (minimum of exponentials).
    """
    bitsq_float = bitsq / Q16_ONE
    stab = max(0.001, profile.stab_pct / 100.0)
    C_cal = (2 ** 11.68) / (1.3 * 600.0)

    # Each miner samples independently
    times = []
    for i, m in enumerate(miners):
        miner_hr = m.hashrate_kh
        expected = (2 ** bitsq_float) / (max(miner_hr, 0.001) * stab * C_cal)
        expected = max(1.0, expected)
        t = rng.expovariate(1.0 / expected)
        times.append((t, i))

    # Winner is the fastest
    times.sort()
    return times[0][0], times[0][1]

# ═══════════════════════════════════════════════════════════════════════
# SIMULATION
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SimResult:
    # Config
    antistall_floor: int
    decay_interval: int
    hashrate_kh: float
    seed: int
    n_blocks: int
    # Core metrics
    mean_dt: float
    std_dt: float
    median_dt: float
    p95_dt: float
    p99_dt: float
    max_dt: float
    sawtooth: float
    # Anti-stall metrics
    pct_blocks_antistall: float   # % blocks mined during anti-stall
    pct_time_antistall: float     # % of elapsed time in anti-stall
    antistall_cycles: int         # number of anti-stall activations
    mean_cycle_duration: float    # mean duration of each cycle (seconds)
    # Profile distribution
    profile_hist: Dict[str, int]
    # Per-miner results
    miner_blocks: Dict[str, int]              # total blocks per miner
    miner_blocks_antistall: Dict[str, int]    # blocks during anti-stall
    miner_blocks_normal: Dict[str, int]       # blocks during normal mining
    miner_antistall_advantage: Dict[str, float]  # ratio
    # Verdict
    score: float
    verdict: str


def run_sim(antistall_floor, decay_interval, hashrate_kh,
            profiles, miners, n_blocks, seed):
    rng = random.Random(seed)
    pm = pmap(profiles)
    h_max = max(p.index for p in profiles)

    # Scale miner hashrates proportionally to target network hashrate
    total_base = sum(m.hashrate_kh for m in miners)
    scale_factor = hashrate_kh / total_base
    scaled_miners = []
    for m in miners:
        scaled_miners.append(MinerType(
            m.name, m.att_per_s * scale_factor,
            m.hashrate_kh * scale_factor, m.stab_multiplier))

    # Seed chain
    chain = []
    t0 = GENESIS_TIME + 4995 * TARGET_SPACING
    for i in range(5):
        chain.append(BlockMeta(4995+i, t0 + i*TARGET_SPACING, GENESIS_BITSQ, 0))
    sim_time = chain[-1].time

    # Tracking
    dts = []
    block_profiles = []
    antistall_blocks = 0
    total_antistall_time = 0
    antistall_active = False
    antistall_start = 0
    cycle_durations = []
    miner_wins = {m.name: 0 for m in miners}
    miner_wins_as = {m.name: 0 for m in miners}
    miner_wins_normal = {m.name: 0 for m in miners}
    prof_hist = {}

    for _ in range(n_blocks):
        next_h = chain[-1].height + 1

        # Add hashrate variance (±20%)
        hr_var = hashrate_kh * rng.uniform(0.8, 1.2)
        s_f = hr_var / total_base
        for j, m in enumerate(miners):
            scaled_miners[j] = MinerType(
                m.name, m.att_per_s * s_f,
                m.hashrate_kh * s_f, m.stab_multiplier)

        # Compute profile
        bitsq, pi, lag, in_as = casert_compute(
            chain, next_h, sim_time, h_max, antistall_floor, decay_interval)
        profile = pm.get(pi, pm[0])

        # Sample block time with competitive mining
        dt, winner_idx = sample_block_competitive(
            profile, bitsq, hr_var, scaled_miners, rng)
        dt = max(1.0, dt)

        # Track anti-stall state
        was_in_as = in_as
        # Check if this block was actually mined during anti-stall
        # (the block time might push us past the threshold)
        stall_at_find = max(0, (sim_time + dt) - chain[-1].time)
        block_in_antistall = stall_at_find >= antistall_floor

        if block_in_antistall:
            antistall_blocks += 1
            if not antistall_active:
                antistall_active = True
                antistall_start = sim_time
        else:
            if antistall_active:
                cycle_dur = sim_time + dt - antistall_start
                cycle_durations.append(cycle_dur)
                antistall_active = False

        # Track time in anti-stall
        if block_in_antistall:
            total_antistall_time += int(dt)

        new_time = int(sim_time + dt)
        chain.append(BlockMeta(next_h, new_time, bitsq, pi))
        sim_time = new_time

        dts.append(int(dt))
        block_profiles.append(pi)
        pn = profile.name
        prof_hist[pn] = prof_hist.get(pn, 0) + 1

        winner = scaled_miners[winner_idx]
        miner_wins[winner.name] = miner_wins.get(winner.name, 0) + 1
        if block_in_antistall:
            miner_wins_as[winner.name] = miner_wins_as.get(winner.name, 0) + 1
        else:
            miner_wins_normal[winner.name] = miner_wins_normal.get(winner.name, 0) + 1

    # Close last anti-stall cycle
    if antistall_active and antistall_start > 0:
        cycle_durations.append(sim_time - antistall_start)

    # Compute metrics
    n = len(dts)
    mean_dt = statistics.mean(dts)
    std_dt = statistics.stdev(dts) if n > 1 else 0
    median_dt = statistics.median(dts)
    sdts = sorted(dts)
    p95 = sdts[int(n*0.95)] if n > 20 else max(dts)
    p99 = sdts[int(n*0.99)] if n > 100 else max(dts)

    # Sawtooth
    saw = sum(abs(block_profiles[i]-block_profiles[i-1])
              for i in range(1, len(block_profiles))
              if abs(block_profiles[i]-block_profiles[i-1]) > 2) / max(n, 1)

    total_time = sum(dts)
    pct_blocks_as = antistall_blocks * 100.0 / max(n, 1)
    pct_time_as = total_antistall_time * 100.0 / max(total_time, 1)

    # Cycles per day: total_time is in seconds
    days = total_time / 86400
    cycles_per_day = len(cycle_durations) / max(days, 0.01)
    mean_cycle = statistics.mean(cycle_durations) if cycle_durations else 0

    # Anti-stall advantage per miner
    miner_advantage = {}
    for m in miners:
        normal = miner_wins_normal.get(m.name, 0)
        antis = miner_wins_as.get(m.name, 0)
        # Advantage = (blocks_as / time_as) / (blocks_normal / time_normal)
        # Simplified: ratio of antistall blocks to normal blocks, normalized
        normal_rate = normal / max(total_time - total_antistall_time, 1)
        as_rate = antis / max(total_antistall_time, 1)
        miner_advantage[m.name] = as_rate / max(normal_rate, 0.0001)

    # Score: lower = better
    target_dev = abs(mean_dt - 600) / 60
    score = (target_dev * 15 +
             std_dt / 600 * 20 +
             (p95 - 600) / 600 * 10 +
             pct_time_as * 2 +
             saw * 50 +
             (mean_cycle / 3600 * 5 if mean_cycle > 0 else 0))

    # Penalize if small miners get < 5% of blocks
    small_pct = miner_wins.get("small", 0) * 100 / max(n, 1)
    if small_pct < 3:
        score += 50

    verdict = "GREEN" if score < 80 else ("YELLOW" if score < 150 else "RED")

    return SimResult(
        antistall_floor=antistall_floor, decay_interval=decay_interval,
        hashrate_kh=hashrate_kh, seed=seed, n_blocks=n,
        mean_dt=mean_dt, std_dt=std_dt, median_dt=median_dt,
        p95_dt=p95, p99_dt=p99, max_dt=max(dts), sawtooth=saw,
        pct_blocks_antistall=pct_blocks_as, pct_time_antistall=pct_time_as,
        antistall_cycles=len(cycle_durations), mean_cycle_duration=mean_cycle,
        profile_hist=prof_hist,
        miner_blocks=miner_wins, miner_blocks_antistall=miner_wins_as,
        miner_blocks_normal=miner_wins_normal,
        miner_antistall_advantage=miner_advantage,
        score=score, verdict=verdict,
    )

# ═══════════════════════════════════════════════════════════════════════
# SWEEP ENGINE
# ═══════════════════════════════════════════════════════════════════════

def run_sweep(args):
    # Variables
    activations = [1800, 3600, 5400, 7200]     # 30/60/90/120 min
    intervals =   [150, 300, 450, 600, 750, 900]  # 2.5/5/7.5/10/12.5/15 min
    hashrates =   [1.3, 5.0, 13.0]

    profiles = PROFILES_17  # current table
    n_combos = len(activations) * len(intervals) * len(hashrates)
    total_sims = n_combos * args.seeds

    print(f"{B}{C}{'═'*90}{X}")
    print(f"{B}{C}  ANTI-STALL EXHAUSTIVE SWEEP{X}")
    print(f"{B}{C}  {n_combos} combinations × {args.seeds} seeds = {total_sims} simulations{X}")
    print(f"{B}{C}  {args.blocks} blocks per simulation{X}")
    print(f"{B}{C}{'═'*90}{X}")

    # Print conservative-30 table
    print(f"\n{B}{M}CONSERVATIVE-30 PROFILE TABLE (proposed for block 10,000){X}")
    print(f"{'─'*90}")
    print(f"  {'Name':>5} {'Idx':>4} {'Sc':>3} {'St':>3} {'K':>3} {'Mar':>4} {'Stab%':>7} {'EffDiff':>8} {'Delta':>7}")
    print(f"{'─'*90}")
    prev_s = None
    for p in PROFILES_30:
        delta = ""
        if prev_s is not None and p.stab_pct < 100:
            delta = f"{p.stab_pct - prev_s:+.1f}%"
        if p.stab_pct < 100: prev_s = p.stab_pct
        sc = G if p.stab_pct >= 50 else (Y if p.stab_pct >= 15 else R)
        print(f"  {p.name:>5} {p.index:>4} {p.scale:>3} {p.steps:>3} "
              f"{p.k:>3} {p.margin:>4} {sc}{p.stab_pct:>6.1f}%{X} "
              f"{p.eff_diff:>8.2f} {delta:>7}")
    print(f"{'─'*90}")

    # Run sweep
    all_results = {}  # key = (activation, interval, hashrate) → list of SimResult
    done = 0

    for act in activations:
        for intv in intervals:
            for hr in hashrates:
                key = (act, intv, hr)
                results = []
                for s in range(args.seed, args.seed + args.seeds):
                    r = run_sim(act, intv, hr, profiles, MINERS,
                               args.blocks, s)
                    results.append(r)
                    done += 1
                all_results[key] = results

                if done % 36 == 0 or done == total_sims:
                    pct = done * 100 / total_sims
                    print(f"  {D}... {done}/{total_sims} ({pct:.0f}%){X}", flush=True)

    # ─── Aggregate and rank ───
    print(f"\n{B}{C}{'═'*90}{X}")
    print(f"{B}{C}  RESULTS — ALL 72 COMBINATIONS (averaged over {args.seeds} seeds){X}")
    print(f"{B}{C}{'═'*90}{X}")

    aggregated = []
    for (act, intv, hr), results in all_results.items():
        n = len(results)
        a = {
            "act": act, "intv": intv, "hr": hr,
            "act_m": act // 60, "intv_m": intv / 60,
            "mean_dt": statistics.mean(r.mean_dt for r in results),
            "std_dt": statistics.mean(r.std_dt for r in results),
            "median_dt": statistics.mean(r.median_dt for r in results),
            "p95_dt": statistics.mean(r.p95_dt for r in results),
            "p99_dt": statistics.mean(r.p99_dt for r in results),
            "saw": statistics.mean(r.sawtooth for r in results),
            "pct_blk_as": statistics.mean(r.pct_blocks_antistall for r in results),
            "pct_time_as": statistics.mean(r.pct_time_antistall for r in results),
            "cycles": statistics.mean(r.antistall_cycles for r in results),
            "cycle_dur": statistics.mean(r.mean_cycle_duration for r in results),
            "small_pct": statistics.mean(
                r.miner_blocks.get("small",0)*100/max(r.n_blocks,1) for r in results),
            "medium_pct": statistics.mean(
                r.miner_blocks.get("medium",0)*100/max(r.n_blocks,1) for r in results),
            "large_pct": statistics.mean(
                r.miner_blocks.get("large",0)*100/max(r.n_blocks,1) for r in results),
            "small_as_adv": statistics.mean(
                r.miner_antistall_advantage.get("small",0) for r in results),
            "medium_as_adv": statistics.mean(
                r.miner_antistall_advantage.get("medium",0) for r in results),
            "large_as_adv": statistics.mean(
                r.miner_antistall_advantage.get("large",0) for r in results),
            "score": statistics.mean(r.score for r in results),
            "greens": sum(1 for r in results if r.verdict == "GREEN"),
            "yellows": sum(1 for r in results if r.verdict == "YELLOW"),
            "reds": sum(1 for r in results if r.verdict == "RED"),
        }
        aggregated.append(a)

    aggregated.sort(key=lambda x: x["score"])

    # ─── Print detailed table per hashrate ───
    for hr in hashrates:
        subset = [a for a in aggregated if a["hr"] == hr]
        subset.sort(key=lambda x: x["score"])

        print(f"\n{B}{O}═══ HASHRATE: {hr} kH/s ═══{X}")
        print(f"  {'#':>3} {'Act':>4} {'Decay':>6} {'Mean':>6} {'Std':>6} "
              f"{'P95':>6} {'Saw':>5} {'%BlkAS':>7} {'%TimeAS':>8} "
              f"{'Cyc/d':>6} {'CycDur':>7} "
              f"{'Sm%':>5} {'Md%':>5} {'Lg%':>5} "
              f"{'SmAdv':>6} {'Score':>6} {'V':>3}")
        print(f"  {'─'*115}")

        for i, a in enumerate(subset):
            vc = G if a["greens"] > 0 else (Y if a["yellows"] > 0 else R)
            vl = "G" if a["greens"] > 0 else ("Y" if a["yellows"] > 0 else "R")
            mark = f" {B}<<<{X}" if i < 3 else ""
            cyc_d = a["cycles"] * 86400 / max(a["mean_dt"] * 1000 / a["hr"], 1)  # rough
            print(f"  {i+1:>3} {a['act_m']:>3}m {a['intv_m']:>5.1f}m "
                  f"{a['mean_dt']/60:>5.1f}m {a['std_dt']/60:>5.1f}m "
                  f"{a['p95_dt']/60:>5.0f}m {a['saw']:>5.3f} "
                  f"{a['pct_blk_as']:>6.1f}% {a['pct_time_as']:>7.1f}% "
                  f"{a['cycles']:>6.1f} {a['cycle_dur']/60:>6.1f}m "
                  f"{a['small_pct']:>4.1f}% {a['medium_pct']:>4.1f}% {a['large_pct']:>4.1f}% "
                  f"{a['small_as_adv']:>5.2f}x "
                  f"{vc}{a['score']:>5.0f}{X} {vc}{vl}{X}{mark}")

    # ─── TOP 3 per hashrate with explanation ───
    print(f"\n\n{B}{C}{'═'*90}{X}")
    print(f"{B}{C}  TOP 3 RECOMMENDATIONS PER HASHRATE{X}")
    print(f"{B}{C}{'═'*90}{X}")

    for hr in hashrates:
        subset = [a for a in aggregated if a["hr"] == hr]
        subset.sort(key=lambda x: x["score"])
        top3 = subset[:3]

        print(f"\n{B}{O}─── {hr} kH/s ───{X}")
        for i, a in enumerate(top3):
            print(f"\n  {B}#{i+1}: Activation={a['act_m']}min, Decay={a['intv_m']:.1f}min/level{X}")
            print(f"      Mean: {a['mean_dt']/60:.1f}m | Std: {a['std_dt']/60:.1f}m | "
                  f"P95: {a['p95_dt']/60:.0f}m | Saw: {a['saw']:.3f}")
            print(f"      Anti-stall: {a['pct_blk_as']:.1f}% blocks, "
                  f"{a['pct_time_as']:.1f}% time, "
                  f"{a['cycles']:.1f} cycles, {a['cycle_dur']/60:.1f}m avg duration")
            print(f"      Miners: small={a['small_pct']:.1f}%, "
                  f"medium={a['medium_pct']:.1f}%, large={a['large_pct']:.1f}%")
            print(f"      Small miner AS advantage: {a['small_as_adv']:.2f}x")
            print(f"      Score: {a['score']:.0f}")

    # ─── OVERALL BEST ───
    best = aggregated[0]
    print(f"\n\n{B}{G}{'═'*90}{X}")
    print(f"{B}{G}  OVERALL BEST COMBINATION{X}")
    print(f"{B}{G}{'═'*90}{X}")
    print(f"\n  {B}Activation: {best['act_m']} minutes{X}")
    print(f"  {B}Decay interval: {best['intv_m']:.1f} minutes per level{X}")
    print(f"  {B}(tested at {best['hr']} kH/s){X}")
    print(f"\n  Mean block time: {best['mean_dt']/60:.1f}m (target: 10.0m)")
    print(f"  Std deviation:   {best['std_dt']/60:.1f}m")
    print(f"  P95 block time:  {best['p95_dt']/60:.0f}m")
    print(f"  Sawtooth:        {best['saw']:.3f}")
    print(f"  Anti-stall:      {best['pct_blk_as']:.1f}% blocks, "
          f"{best['pct_time_as']:.1f}% time")
    print(f"  Miner equity:    small={best['small_pct']:.1f}%, "
          f"medium={best['medium_pct']:.1f}%, large={best['large_pct']:.1f}%")
    print(f"  Score:           {best['score']:.0f}")

    # ─── Save CSV ───
    csvpath = os.path.join(os.path.dirname(__file__) or ".",
                           "antistall_sweep_results.csv")
    with open(csvpath, "w", newline="") as f:
        fields = list(aggregated[0].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for a in aggregated:
            w.writerow(a)
    print(f"\n{D}Saved {len(aggregated)} rows to {csvpath}{X}")

    # ─── Save profile table ───
    ptpath = os.path.join(os.path.dirname(__file__) or ".",
                          "conservative_30_profile_table.txt")
    with open(ptpath, "w") as f:
        f.write("Conservative-30 Profile Table — proposed for block 10,000\n")
        f.write("=" * 85 + "\n\n")
        f.write(f"{'Name':>5} {'Idx':>4} {'Scale':>5} {'Steps':>5} {'K':>3} "
                f"{'Margin':>6} {'Stab%':>7} {'EffDiff':>8}\n")
        f.write("-" * 85 + "\n")
        for p in PROFILES_30:
            f.write(f"{p.name:>5} {p.index:>4} {p.scale:>5} {p.steps:>5} "
                    f"{p.k:>3} {p.margin:>6} {p.stab_pct:>6.1f}% "
                    f"{p.eff_diff:>8.2f}\n")
        f.write("\n\n// C++ format for params.h:\n")
        f.write("inline constexpr CasertProfile CASERT_PROFILES_30[] = {\n")
        for p in PROFILES_30:
            f.write(f"    {{{p.scale},{p.steps},{p.k},{p.margin}}},  "
                    f"// {p.name} ({p.stab_pct:.1f}%)\n")
        f.write("};\n")
    print(f"{D}Saved profile table to {ptpath}{X}")


def main():
    ap = argparse.ArgumentParser(description="Anti-Stall Exhaustive Sweep")
    ap.add_argument("--blocks", type=int, default=1000)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    run_sweep(args)


if __name__ == "__main__":
    main()

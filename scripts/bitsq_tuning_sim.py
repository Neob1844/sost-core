#!/usr/bin/env python3
"""
bitsQ Tuning Simulation — Compare current vs proposed parameters.

  A) Current: half-life 24h, cap 12.5%
  B) Proposed: half-life 12h, cap 25%

Replays production-like scenarios with 19 miners, burst patterns,
and the H10 ceiling active.
"""

import sys, os, math, random, statistics
sys.path.insert(0, os.path.dirname(__file__))
from casert_v6_full_sim import (
    GENESIS_TIME, TARGET_SPACING, Q16_ONE, MIN_BITSQ, MAX_BITSQ,
    K_R, K_L, K_I, K_B, K_V,
    EWMA_SHORT_ALPHA, EWMA_LONG_ALPHA, EWMA_VOL_ALPHA, EWMA_DENOM,
    INTEG_RHO, INTEG_ALPHA, INTEG_MAX,
    H_MIN, V3_LAG_FLOOR_DIV, V5_EXTREME_MIN,
    EBR_ENTER, EBR_LEVEL_E2, EBR_LEVEL_E3, EBR_LEVEL_E4,
    ANTISTALL_FLOOR_V5, ANTISTALL_EASING_EXTRA,
    BlockMeta, log2_q16, ProfileParams,
    PROFILES_17, make_profile_map,
)

G="\033[92m";Y="\033[93m";R="\033[91m";C="\033[96m";D="\033[2m"
B="\033[1m";X="\033[0m";O="\033[38;5;208m"

# Extended profiles with H10 ceiling
PROFILES = list(PROFILES_17[:14])  # E4-H9
PROFILES.append(ProfileParams(10,"H10",2,8,7,115,12.0,14.0))
H10_CEILING = 10
H_MAX = 10

def horner_2exp(frac):
    x = frac
    t = 3638
    t = 15743 + ((t * x) >> 16)
    t = 45426 + ((t * x) >> 16)
    return Q16_ONE + ((t * x) >> 16)

def next_bitsq(chain, next_height, half_life, delta_den):
    """bitsQ with configurable half-life and cap."""
    if not chain: return 765730
    epoch = next_height // 131553
    anchor_idx = 0
    if epoch > 0:
        ai = epoch * 131553 - 1
        anchor_idx = max(0, min(ai, len(chain)-1))
    anchor_bitsq = chain[anchor_idx].powDiffQ if anchor_idx > 0 else 765730
    parent_idx = len(chain) - 1
    expected_pt = chain[anchor_idx].time + (parent_idx - anchor_idx) * TARGET_SPACING
    td = chain[-1].time - expected_pt

    exponent = ((-td) * Q16_ONE) // half_life
    shifts = exponent >> 16
    frac = exponent & 0xFFFF
    factor = horner_2exp(frac)
    raw = (anchor_bitsq * factor) >> 16
    if shifts > 0:
        raw = MAX_BITSQ if shifts > 24 else raw << shifts
    elif shifts < 0:
        rs = -shifts
        raw = 0 if rs > 24 else raw >> rs

    prev_bitsq = chain[-1].powDiffQ or 765730
    max_d = max(1, prev_bitsq // delta_den)
    delta = max(-max_d, min(max_d, raw - prev_bitsq))
    return max(MIN_BITSQ, min(MAX_BITSQ, prev_bitsq + delta))

def compute_profile(chain, next_height, now_time, half_life, delta_den):
    """Full PID + live lag + H10 ceiling."""
    bitsq = next_bitsq(chain, next_height, half_life, delta_den)
    if len(chain) < 2: return bitsq, 0, 0

    dt = max(1, min(86400, chain[-1].time - chain[-2].time))
    r_n = log2_q16(TARGET_SPACING) - log2_q16(dt)

    lag_time = now_time if now_time > chain[-1].time else chain[-1].time
    elapsed = lag_time - GENESIS_TIME
    expected_h = elapsed // TARGET_SPACING if elapsed >= 0 else 0
    lag = int((next_height - 1) - expected_h)

    S=M=V=0; I_acc=0
    lb = min(len(chain), 128); st = len(chain) - lb
    for i in range(st+1, len(chain)):
        d = max(1, min(86400, chain[i].time - chain[i-1].time))
        r = log2_q16(TARGET_SPACING) - log2_q16(d)
        S = (EWMA_SHORT_ALPHA*r + (EWMA_DENOM-EWMA_SHORT_ALPHA)*S) >> 8
        M = (EWMA_LONG_ALPHA*r + (EWMA_DENOM-EWMA_LONG_ALPHA)*M) >> 8
        V = (EWMA_VOL_ALPHA*abs(r-S) + (EWMA_DENOM-EWMA_VOL_ALPHA)*V) >> 8
        h_i = chain[i].height
        e_i = chain[i].time - GENESIS_TIME
        exp_i = e_i // TARGET_SPACING if e_i >= 0 else 0
        lag_i = int(h_i - exp_i)
        I_acc = (INTEG_RHO*I_acc + EWMA_DENOM*INTEG_ALPHA*lag_i*Q16_ONE) >> 8
        I_acc = max(-INTEG_MAX, min(INTEG_MAX, I_acc))

    L_q16 = lag * Q16_ONE
    U = K_R*r_n + K_L*(L_q16>>16) + K_I*(I_acc>>16) + K_B*(S-M) + K_V*V
    H = max(H_MIN, min(H_MAX, int(U >> 16)))

    if lag <= 0: H = min(H, 0)
    if len(chain) < 10: H = min(H, 0)

    if len(chain) >= 3:
        prev_H = max(H_MIN, min(H_MAX, chain[-1].profile_index))
        # Slew ±1
        H = max(prev_H - 1, min(prev_H + 1, H))
        # Lag floor
        if lag > 10: H = max(H, min(lag // V3_LAG_FLOOR_DIV, H_MAX))
        # Safety post-slew
        if lag <= 0: H = min(H, 0)
        # EBR
        if lag <= EBR_ENTER:
            if lag <= EBR_LEVEL_E4: H = min(H, H_MIN)
            elif lag <= EBR_LEVEL_E3: H = min(H, -3)
            elif lag <= EBR_LEVEL_E2: H = min(H, -2)
            else: H = min(H, 0)
        # Extreme cap
        if H >= V5_EXTREME_MIN and H > prev_H + 1: H = prev_H + 1
        # Lag cap
        if H > 0 and H > lag: H = max(0, lag)
        # H10 ceiling
        if H > H10_CEILING: H = H10_CEILING
        H = max(H_MIN, min(H_MAX, H))

    # Anti-stall
    if now_time > 0 and chain:
        stall = max(0, now_time - chain[-1].time)
        if stall >= ANTISTALL_FLOOR_V5 and H > 0:
            decayed = H - 1
            decay_t = stall - ANTISTALL_FLOOR_V5
            while decayed > 0 and decay_t > 0:
                cost = 600 if decayed >= 7 else (900 if decayed >= 4 else 1200)
                if decay_t < cost: break
                decay_t -= cost; decayed -= 1
            H = decayed

    return bitsq, H, lag

def sample_dt(profile, bitsq, hr, rng):
    stab = max(0.001, profile.stability_pct / 100.0)
    bq = bitsq / Q16_ONE
    C_cal = (2 ** 11.68) / (1.3 * 600.0)
    expected = (2 ** bq) / (max(hr, 0.01) * stab * C_cal)
    return max(1.0, rng.expovariate(1.0 / max(1.0, expected)))

def run_sim(half_life, delta_den, label, seed, n_blocks=500, base_hr=1.5):
    rng = random.Random(seed)
    pmap = make_profile_map(PROFILES)
    chain = []
    base_h = 5100
    t = GENESIS_TIME + base_h * TARGET_SPACING
    for i in range(10):
        chain.append(BlockMeta(base_h+i, t+i*TARGET_SPACING, 830000, 0))
    sim_time = chain[-1].time

    rows = []
    max_lag = 0
    for blk in range(n_blocks):
        next_h = chain[-1].height + 1
        # Variable hashrate: simulate miners joining/leaving
        if blk < 50: hr = base_hr * rng.uniform(0.8, 1.2)
        elif blk < 100: hr = base_hr * 2.5 * rng.uniform(0.8, 1.2)  # burst: 5x miners join
        elif blk < 150: hr = base_hr * 0.5 * rng.uniform(0.8, 1.2)  # drop: miners leave
        elif blk < 250: hr = base_hr * 3.0 * rng.uniform(0.8, 1.2)  # another burst
        else: hr = base_hr * rng.uniform(0.7, 1.4)

        bitsq, pi, lag = compute_profile(chain, next_h, sim_time, half_life, delta_den)
        if lag > max_lag: max_lag = lag
        profile = pmap.get(pi, pmap[0])
        dt = sample_dt(profile, bitsq, hr, rng)
        new_time = int(sim_time + dt)
        chain.append(BlockMeta(next_h, new_time, bitsq, pi))
        sim_time = new_time

        rows.append({
            "block": blk+1, "height": next_h, "dt": int(dt),
            "profile": pi, "lag": lag, "bitsq": round(bitsq/Q16_ONE, 3),
            "hr": round(hr, 2),
        })

    dts = [r["dt"] for r in rows]
    lags = [r["lag"] for r in rows]
    profiles = [r["profile"] for r in rows]
    bitsqs = [r["bitsq"] for r in rows]

    return {
        "label": label,
        "seed": seed,
        "mean_dt": statistics.mean(dts),
        "std_dt": statistics.stdev(dts) if len(dts)>1 else 0,
        "median_dt": statistics.median(dts),
        "p95_dt": sorted(dts)[int(len(dts)*0.95)],
        "max_dt": max(dts),
        "over_20m": sum(1 for d in dts if d >= 1200),
        "over_40m": sum(1 for d in dts if d >= 2400),
        "over_60m": sum(1 for d in dts if d >= 3600),
        "max_lag": max_lag,
        "lag_std": statistics.stdev(lags),
        "mean_lag": statistics.mean(lags),
        "bitsq_start": bitsqs[0],
        "bitsq_end": bitsqs[-1],
        "bitsq_max": max(bitsqs),
        "bitsq_min": min(bitsqs),
        "bitsq_range": max(bitsqs) - min(bitsqs),
        "time_in_h10": sum(1 for p in profiles if p == 10),
        "time_in_h9": sum(1 for p in profiles if p == 9),
        "time_in_b0": sum(1 for p in profiles if p == 0),
        "rows": rows,
    }

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--blocks", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    configs = [
        ("A) Current: HL=24h, cap=12.5%", 86400, 8),
        ("B) Proposed: HL=12h, cap=25%", 43200, 4),
    ]

    print(f"{B}{C}{'═'*80}{X}")
    print(f"{B}{C}  bitsQ TUNING SIMULATION{X}")
    print(f"{B}{C}  {args.seeds} seeds × 2 configs × {args.blocks} blocks{X}")
    print(f"{B}{C}{'═'*80}{X}")

    all_results = {}
    for label, hl, den in configs:
        results = []
        print(f"\n{O}Running: {label}{X}")
        for s in range(args.seed, args.seed + args.seeds):
            r = run_sim(hl, den, label, s, args.blocks)
            results.append(r)
        all_results[label] = results

    # Comparison
    print(f"\n{B}{C}{'═'*80}{X}")
    print(f"{B}{C}  COMPARISON{X}")
    print(f"{B}{C}{'═'*80}{X}")

    def avg(results, key):
        return statistics.mean(r[key] for r in results)

    metrics = [
        ("Mean block time", "mean_dt", lambda v: f"{v/60:.1f}m"),
        ("Std deviation", "std_dt", lambda v: f"{v/60:.1f}m"),
        ("Median", "median_dt", lambda v: f"{v/60:.1f}m"),
        ("P95", "p95_dt", lambda v: f"{v/60:.0f}m"),
        ("Max block time", "max_dt", lambda v: f"{v/60:.0f}m"),
        ("Blocks > 20m", "over_20m", lambda v: f"{v:.1f}"),
        ("Blocks > 40m", "over_40m", lambda v: f"{v:.1f}"),
        ("Blocks > 60m", "over_60m", lambda v: f"{v:.1f}"),
        ("Max lag", "max_lag", lambda v: f"{v:.0f}"),
        ("Mean lag", "mean_lag", lambda v: f"{v:+.1f}"),
        ("Lag std", "lag_std", lambda v: f"{v:.1f}"),
        ("bitsQ range", "bitsq_range", lambda v: f"{v:.3f}"),
        ("bitsQ min", "bitsq_min", lambda v: f"{v:.3f}"),
        ("bitsQ max", "bitsq_max", lambda v: f"{v:.3f}"),
        ("Blocks in H10", "time_in_h10", lambda v: f"{v:.0f}"),
        ("Blocks in H9", "time_in_h9", lambda v: f"{v:.0f}"),
        ("Blocks in B0", "time_in_b0", lambda v: f"{v:.0f}"),
    ]

    header = f"  {'Metric':<25}"
    for label, _, _ in configs:
        header += f" {label.split(')')[0]+')':<15}"
    print(f"\n{B}{header}{X}")
    print(f"  {'─'*55}")

    for name, key, fmt in metrics:
        line = f"  {name:<25}"
        vals = []
        for label, _, _ in configs:
            v = avg(all_results[label], key)
            vals.append(v)
            line += f" {fmt(v):>15}"
        # Mark better
        print(line)

    # First 30 blocks detail
    print(f"\n{B}{C}FIRST 30 BLOCKS — seed {args.seed} (burst at block 50-100){X}")
    for label, hl, den in configs:
        r = run_sim(hl, den, label, args.seed, args.blocks)
        print(f"\n  {B}{label}{X}")
        print(f"  {'Blk':>4} {'DT':>6} {'Prof':>5} {'Lag':>5} {'bitsQ':>7} {'HR':>5}")
        # Show blocks 45-75 (burst zone)
        for row in r["rows"][45:75]:
            dtm = row["dt"]/60
            dc = G if dtm < 10 else (Y if dtm < 20 else R)
            pn = f"H{row['profile']}" if row['profile']>0 else "B0"
            print(f"  {row['block']:>4} {dc}{dtm:>5.1f}m{X} {pn:>5} {row['lag']:>+5d} "
                  f"{row['bitsq']:>7.3f} {row['hr']:>5.1f}")

    # Verdict
    a_results = all_results[configs[0][0]]
    b_results = all_results[configs[1][0]]

    a_mean = avg(a_results, "mean_dt")
    b_mean = avg(b_results, "mean_dt")
    a_lag = avg(a_results, "max_lag")
    b_lag = avg(b_results, "max_lag")
    a_over40 = avg(a_results, "over_40m")
    b_over40 = avg(b_results, "over_40m")

    print(f"\n{B}{C}{'═'*80}{X}")
    print(f"{B}{C}  VERDICT{X}")
    print(f"{B}{C}{'═'*80}{X}")
    print(f"\n  Mean dt: A={a_mean/60:.1f}m vs B={b_mean/60:.1f}m")
    print(f"  Max lag: A={a_lag:.0f} vs B={b_lag:.0f}")
    print(f"  >40m blocks: A={a_over40:.1f} vs B={b_over40:.1f}")

    if b_lag < a_lag * 0.85 and b_over40 <= a_over40:
        print(f"\n  {G}{B}PROPOSED (12h/25%) reduces lag significantly. Worth implementing.{X}")
    elif b_mean < a_mean * 1.05 and b_lag < a_lag:
        print(f"\n  {Y}{B}PROPOSED shows improvement in lag without degrading block times.{X}")
    else:
        print(f"\n  {Y}{B}Results mixed. Review the detail before deciding.{X}")


if __name__ == "__main__":
    main()

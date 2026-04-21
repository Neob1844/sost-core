#!/usr/bin/env python3
"""
PID Weight Optimization — Find optimal K_L and signal distribution.

Tests multiple PID configurations under burst + recovery scenarios.
Current: K_R=0.05, K_L=0.40, K_I=0.15, K_B=0.05, K_V=0.02 (total=0.67)

Key question: would a higher K_L (or different weight mix) make the
equalizer reach H9/H10 faster during bursts without causing problems?
"""

import math, random, statistics

TARGET = 600
STABILITY = {
    -4: 1.00, -3: 1.00, -2: 1.00, -1: 1.00,
    0: 1.00, 1: 0.97, 2: 0.92, 3: 0.85, 4: 0.78,
    5: 0.65, 6: 0.50, 7: 0.45, 8: 0.35, 9: 0.25, 10: 0.12,
}
H10_CEILING = 10
H_MIN = -4
Q16 = 65536
EWMA_DENOM = 256
GENESIS_TIME = 0

def sim_pid(config, seed, n_blocks=300, burst_blocks=30, burst_hr=5.0, normal_hr=1.5):
    rng = random.Random(seed)
    k_r, k_l, k_i, k_b, k_v = config['weights']
    label = config['label']

    # Chain history
    times = [0, TARGET, TARGET*2, TARGET*3, TARGET*4]  # 5 seed blocks
    profiles = [0, 0, 0, 0, 0]
    sim_time = times[-1]

    # EWMA state
    S, M, V = 0, 0, 0
    I_acc = 0

    results = []
    max_lag = 0
    blocks_to_h9 = None
    blocks_to_h10 = None
    time_in_h10 = 0
    time_in_h8_plus = 0
    stall_blocks = 0
    overshoot_h10 = 0

    for blk in range(n_blocks):
        height = len(times)

        # Hashrate
        if blk < burst_blocks:
            hr = burst_hr * rng.uniform(0.8, 1.2)
        else:
            hr = normal_hr * rng.uniform(0.7, 1.4)

        # ── PID computation (mirrors casert_compute) ──
        dt_last = max(1, times[-1] - times[-2])
        r_n = math.log2(TARGET / dt_last) if dt_last > 0 else 0

        # Live lag
        elapsed = sim_time - GENESIS_TIME
        expected_h = int(elapsed / TARGET)
        lag = (height - 1) - expected_h

        if lag > max_lag:
            max_lag = lag

        # EWMA update
        r_q16 = int(r_n * Q16)
        S = (32 * r_q16 + (EWMA_DENOM - 32) * S) >> 8
        M = (3 * r_q16 + (EWMA_DENOM - 3) * M) >> 8
        abs_dev = abs(r_q16 - S)
        V = (16 * abs_dev + (EWMA_DENOM - 16) * V) >> 8

        # Integrator
        lag_q16 = lag * Q16
        I_acc = (253 * I_acc + EWMA_DENOM * 1 * lag_q16) >> 8
        I_acc = max(-6553600, min(6553600, I_acc))

        burst_score = S - M

        # Control signal
        U = (k_r * r_q16 +
             k_l * (lag_q16 >> 16) +
             k_i * (I_acc >> 16) +
             k_b * burst_score +
             k_v * V)
        H_raw = int(U >> 16)
        H = max(H_MIN, min(H10_CEILING, H_raw))

        # Safety rule
        if lag <= 0:
            H = min(H, 0)

        # Slew ±1
        prev_H = profiles[-1]
        H = max(prev_H - 1, min(prev_H + 1, H))

        # Lag floor
        if lag > 10:
            H = max(H, min(lag // 8, H10_CEILING))

        # Safety post-slew
        if lag <= 0:
            H = min(H, 0)

        # Lag cap
        if H > 0 and H > lag:
            H = max(0, lag)

        # H10 ceiling
        if H > H10_CEILING:
            H = H10_CEILING

        H = max(H_MIN, min(H10_CEILING, H))

        # Track
        if blocks_to_h9 is None and H >= 9:
            blocks_to_h9 = blk + 1
        if blocks_to_h10 is None and H >= 10:
            blocks_to_h10 = blk + 1
        if H >= 10:
            time_in_h10 += 1
        if H >= 8:
            time_in_h8_plus += 1

        # Sample block time
        stab = STABILITY.get(H, 0.5)
        C_cal = (2 ** 11.68) / (1.3 * 600.0)
        bitsq_float = 12.5  # fixed for comparison
        expected_dt = (2 ** bitsq_float) / (max(hr, 0.01) * stab * C_cal)
        dt = max(1.0, rng.expovariate(1.0 / max(1.0, expected_dt)))

        if dt > 1200:
            stall_blocks += 1

        sim_time += dt
        times.append(int(sim_time))
        profiles.append(H)

        results.append({
            'block': blk + 1,
            'dt': int(dt),
            'profile': H,
            'lag': lag,
            'h_raw': H_raw,
        })

    return {
        'label': label,
        'seed': seed,
        'blocks_to_h9': blocks_to_h9,
        'blocks_to_h10': blocks_to_h10,
        'max_lag': max_lag,
        'time_in_h10': time_in_h10,
        'time_in_h8_plus': time_in_h8_plus,
        'stall_blocks': stall_blocks,
        'mean_dt': statistics.mean(r['dt'] for r in results),
        'std_dt': statistics.stdev(r['dt'] for r in results) if len(results) > 1 else 0,
        'rows': results,
    }


def main():
    seeds = 30

    # PID configs to test (K_R, K_L, K_I, K_B, K_V) — all in Q16.16
    configs = [
        {'label': 'A) Current (K_L=0.40)',
         'weights': (3277, 26214, 9830, 3277, 1311)},  # 0.05/0.40/0.15/0.05/0.02

        {'label': 'B) K_L=0.60',
         'weights': (3277, 39321, 9830, 3277, 1311)},  # 0.05/0.60/0.15/0.05/0.02

        {'label': 'C) K_L=0.80',
         'weights': (3277, 52428, 9830, 3277, 1311)},  # 0.05/0.80/0.15/0.05/0.02

        {'label': 'D) K_L=1.00',
         'weights': (3277, 65536, 9830, 3277, 1311)},  # 0.05/1.00/0.15/0.05/0.02

        {'label': 'E) K_L=0.60 K_I=0.30',
         'weights': (3277, 39321, 19660, 3277, 1311)},  # stronger integrator

        {'label': 'F) K_L=0.80 K_B=0.20',
         'weights': (3277, 52428, 9830, 13107, 1311)},  # stronger burst

        {'label': 'G) Direct: K_L=1.00 only',
         'weights': (0, 65536, 0, 0, 0)},  # profile = lag (no other signals)
    ]

    print(f"{'='*90}")
    print(f"  PID WEIGHT OPTIMIZATION — {seeds} seeds × {len(configs)} configs × 300 blocks")
    print(f"  Burst: 30 blocks at 5 kH/s, then 270 blocks at 1.5 kH/s")
    print(f"{'='*90}")

    all_results = {}
    for config in configs:
        runs = []
        for s in range(42, 42 + seeds):
            runs.append(sim_pid(config, s))
        all_results[config['label']] = runs

    def avg(runs, key):
        vals = [r[key] for r in runs if r[key] is not None]
        return statistics.mean(vals) if vals else float('inf')

    # Header
    print(f"\n{'─'*90}")
    header = f"  {'Metric':<25}"
    for c in configs:
        short = c['label'].split(')')[0] + ')'
        header += f" {short:>8}"
    print(header)
    print(f"{'─'*90}")

    metrics = [
        ("Blocks to H9", "blocks_to_h9"),
        ("Blocks to H10", "blocks_to_h10"),
        ("Max lag", "max_lag"),
        ("Blocks in H10", "time_in_h10"),
        ("Blocks in H8+", "time_in_h8_plus"),
        ("Stalls (>20m)", "stall_blocks"),
        ("Mean dt (s)", "mean_dt"),
        ("Std dt (s)", "std_dt"),
    ]

    for name, key in metrics:
        line = f"  {name:<25}"
        vals = []
        for c in configs:
            v = avg(all_results[c['label']], key)
            vals.append(v)
            if v == float('inf'):
                line += f" {'—':>8}"
            elif key in ('mean_dt', 'std_dt'):
                line += f" {v:>7.0f}s"
            else:
                line += f" {v:>8.1f}"
        # Mark best
        print(line)

    # Profile paths for seed 42
    print(f"\n{'─'*90}")
    print(f"  PROFILE PATHS — first 20 blocks (burst phase, seed 42)")
    print(f"{'─'*90}")

    for config in configs:
        r = all_results[config['label']][0]
        path = [r2['profile'] for r2 in r['rows'][:20]]
        names = ['H'+str(p) if p > 0 else ('B0' if p == 0 else 'E'+str(abs(p))) for p in path]
        print(f"\n  {config['label']}:")
        print(f"  {' → '.join(names)}")
        h9 = r['blocks_to_h9']
        print(f"  H9 at block {h9 if h9 else 'never'}, lag at blk 10: {r['rows'][9]['lag']:+d}, H_raw at blk 10: {r['rows'][9]['h_raw']}")

    # Verdict
    print(f"\n{'='*90}")
    print(f"  VERDICT")
    print(f"{'='*90}")

    best_h9 = None
    best_label = None
    for c in configs:
        v = avg(all_results[c['label']], 'blocks_to_h9')
        stalls = avg(all_results[c['label']], 'stall_blocks')
        if v < (best_h9 or float('inf')) and stalls <= avg(all_results[configs[0]['label']], 'stall_blocks') * 1.1:
            best_h9 = v
            best_label = c['label']

    if best_label:
        current_h9 = avg(all_results[configs[0]['label']], 'blocks_to_h9')
        improvement = (current_h9 - best_h9) / current_h9 * 100 if current_h9 < float('inf') else 0
        print(f"\n  Best config: {best_label}")
        print(f"  Reaches H9 in {best_h9:.0f} blocks (current: {current_h9:.0f}, improvement: {improvement:.0f}%)")
    else:
        print(f"\n  No clear winner — all configurations similar")


if __name__ == "__main__":
    main()

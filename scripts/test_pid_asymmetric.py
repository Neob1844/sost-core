#!/usr/bin/env python3
"""
PID Asymmetric Tuning Test — CTO-proposed configurations.

Tests multiple PID configurations including asymmetric (ahead vs behind)
modes, integral freeze, hysteresis, and interaction with avg288 bitsQ.

Current PID: K_R=0.05, K_L=0.40, K_I=0.15, K_B=0.05, K_V=0.02

Configs tested:
  A) Current (baseline)
  B) Higher K_L (0.60) — more responsive to lag
  C) Asymmetric: ahead Kp+30% Ki-40%, behind unchanged
  D) Integral freeze when ahead >= 6
  E) Hysteresis: don't drop profile until ahead <= 5 for 3 blocks
  F) Combined: C + D + E (full CTO proposal)
  G) Direct lag mapping (profile = lag, no PID)

All configs include avg288 bitsQ with dynamic cap (±15s dead band).
"""

import math, random, statistics

TARGET = 600
Q16 = 65536
STABILITY = {
    -4: 1.00, -3: 1.00, -2: 1.00, -1: 1.00,
    0: 1.00, 1: 0.97, 2: 0.92, 3: 0.85, 4: 0.78,
    5: 0.65, 6: 0.50, 7: 0.45, 8: 0.35, 9: 0.25, 10: 0.12,
}
H10_CEILING = 10
H_MIN = -4
EWMA_DENOM = 256


def compute_avg288_bitsq(intervals, prev_bitsq):
    """avg288 + dynamic cap (±15s dead band)."""
    if not intervals:
        return prev_bitsq
    avg = sum(intervals) / len(intervals)
    dev = avg - TARGET
    abs_dev = abs(dev)
    if abs_dev <= 15:
        return prev_bitsq
    if abs_dev <= 60: max_d = prev_bitsq // 200
    elif abs_dev <= 120: max_d = prev_bitsq // 100
    elif abs_dev <= 240: max_d = prev_bitsq // 50
    else: max_d = prev_bitsq // 33
    if max_d < 1: max_d = 1
    excess = abs_dev - 15
    raw_delta = (prev_bitsq * excess) // (TARGET * 4)
    if dev < 0:
        delta = min(raw_delta, max_d)
    else:
        delta = -min(raw_delta, max_d)
    return max(Q16, min(255 * Q16, prev_bitsq + delta))


def sim_config(config, seed, n_blocks=500):
    rng = random.Random(seed)
    name = config['name']
    mode = config.get('mode', 'normal')

    # PID weights
    kr = config.get('kr', 3277)
    kl = config.get('kl', 26214)
    ki = config.get('ki', 9830)
    kb = config.get('kb', 3277)
    kv = config.get('kv', 1311)
    # Asymmetric overrides
    kl_ahead = config.get('kl_ahead', kl)
    ki_ahead = config.get('ki_ahead', ki)
    # Integral freeze
    freeze_lag = config.get('freeze_lag', None)
    # Hysteresis
    hysteresis = config.get('hysteresis', False)
    hyst_exit_lag = config.get('hyst_exit_lag', 5)
    hyst_blocks = config.get('hyst_blocks', 3)

    # Chain state
    times = [0, TARGET, TARGET * 2, TARGET * 3, TARGET * 4]
    profiles = [0, 0, 0, 0, 0]
    bitsq = 800000  # ~12.2 bits (normal starting point)
    all_intervals = [TARGET, TARGET, TARGET, TARGET]
    sim_time = times[-1]

    S, M, V, I_acc = 0, 0, 0, 0
    hyst_counter = 0
    hyst_high_profile = 0

    rows = []
    max_lag = 0
    blocks_to_h9 = None
    time_in_h10 = 0
    time_in_h8_plus = 0
    stall_20 = 0
    stall_40 = 0
    sawtooth = 0
    prev_pi = 0

    for blk in range(n_blocks):
        height = len(times)
        # Hashrate: burst first 40, then variable
        if blk < 40:
            hr = 5.0 * rng.uniform(0.8, 1.2)
        elif blk < 80:
            hr = 1.0 * rng.uniform(0.5, 1.5)  # drop
        elif blk < 150:
            hr = 3.0 * rng.uniform(0.7, 1.3)  # recovery
        else:
            hr = 1.5 * rng.uniform(0.7, 1.4)  # normal

        # Compute PID
        dt_last = max(1, times[-1] - times[-2])
        r_n = int(math.log2(max(1, TARGET / dt_last)) * Q16) if dt_last > 0 else 0

        elapsed = sim_time
        expected_h = int(elapsed / TARGET)
        lag = (height - 1) - expected_h
        if lag > max_lag: max_lag = lag

        # EWMA
        S = (32 * r_n + (EWMA_DENOM - 32) * S) >> 8
        M = (3 * r_n + (EWMA_DENOM - 3) * M) >> 8
        abs_dev = abs(r_n - S)
        V = (16 * abs_dev + (EWMA_DENOM - 16) * V) >> 8

        # Integrator with optional freeze
        lag_q16 = lag * Q16
        if freeze_lag is not None and lag >= freeze_lag:
            pass  # freeze: don't update I_acc
        else:
            I_acc = (253 * I_acc + EWMA_DENOM * 1 * lag_q16) >> 8
            I_acc = max(-6553600, min(6553600, I_acc))

        burst = S - M

        # Select weights based on ahead/behind
        if lag > 0:
            use_kl = kl_ahead
            use_ki = ki_ahead
        else:
            use_kl = kl
            use_ki = ki

        U = (kr * r_n + use_kl * (lag_q16 >> 16) + use_ki * (I_acc >> 16) +
             kb * burst + kv * V)
        H_raw = int(U >> 16)
        H = max(H_MIN, min(H10_CEILING, H_raw))

        if lag <= 0: H = min(H, 0)

        # Slew ±1
        prev_H = profiles[-1]
        H = max(prev_H - 1, min(prev_H + 1, H))

        # Lag floor
        if lag > 10: H = max(H, min(lag // 8, H10_CEILING))
        if lag <= 0: H = min(H, 0)

        # Lag cap
        if H > 0 and H > lag: H = max(0, lag)
        if H > H10_CEILING: H = H10_CEILING

        # Hysteresis: don't drop if recently climbed high and lag still ahead
        if hysteresis and H < prev_H and lag > hyst_exit_lag:
            hyst_counter += 1
            if hyst_counter < hyst_blocks:
                H = prev_H  # hold
            else:
                hyst_counter = 0
        else:
            hyst_counter = 0

        H = max(H_MIN, min(H10_CEILING, H))

        # Direct lag mode
        if mode == 'direct':
            H = max(0, min(H10_CEILING, lag)) if lag > 0 else max(H_MIN, min(0, lag))
            H = max(prev_H - 1, min(prev_H + 1, H))  # still apply slew

        # Track
        if blocks_to_h9 is None and H >= 9: blocks_to_h9 = blk + 1
        if H >= 10: time_in_h10 += 1
        if H >= 8: time_in_h8_plus += 1
        jump = abs(H - prev_pi)
        if jump > 2: sawtooth += jump
        prev_pi = H

        # Sample block time with bitsQ
        stab = STABILITY.get(H, 0.5)
        bitsq_float = bitsq / Q16
        C_cal = (2 ** 11.68) / (1.3 * 600.0)
        expected_dt = (2 ** bitsq_float) / (max(hr, 0.01) * stab * C_cal)
        dt = max(1.0, rng.expovariate(1.0 / max(1.0, expected_dt)))

        if dt > 1200: stall_20 += 1
        if dt > 2400: stall_40 += 1

        sim_time += dt
        times.append(int(sim_time))
        profiles.append(H)
        all_intervals.append(int(dt))

        # Update bitsQ via avg288
        window = all_intervals[-288:] if len(all_intervals) > 288 else all_intervals
        bitsq = compute_avg288_bitsq(window, bitsq)

        rows.append({'block': blk + 1, 'dt': int(dt), 'profile': H,
                     'lag': lag, 'bitsq': round(bitsq / Q16, 3), 'hr': round(hr, 2)})

    dts = [r['dt'] for r in rows]
    lags = [r['lag'] for r in rows]
    return {
        'name': name, 'seed': seed,
        'blocks_to_h9': blocks_to_h9,
        'max_lag': max_lag,
        'time_in_h10': time_in_h10,
        'time_in_h8_plus': time_in_h8_plus,
        'stall_20': stall_20, 'stall_40': stall_40,
        'sawtooth': sawtooth / max(len(rows), 1),
        'mean_dt': statistics.mean(dts),
        'std_dt': statistics.stdev(dts) if len(dts) > 1 else 0,
        'lag_std': statistics.stdev(lags) if len(lags) > 1 else 0,
        'lag_max': max(lags), 'lag_min': min(lags),
        'bitsq_final': rows[-1]['bitsq'],
        'bitsq_max': max(r['bitsq'] for r in rows),
        'rows': rows,
    }


def main():
    seeds = 30

    configs = [
        {'name': 'A) Current',
         'kr': 3277, 'kl': 26214, 'ki': 9830, 'kb': 3277, 'kv': 1311,
         'kl_ahead': 26214, 'ki_ahead': 9830},

        {'name': 'B) K_L=0.60',
         'kr': 3277, 'kl': 39321, 'ki': 9830, 'kb': 3277, 'kv': 1311,
         'kl_ahead': 39321, 'ki_ahead': 9830},

        {'name': 'C) Asymm ahead',
         'kr': 3277, 'kl': 26214, 'ki': 9830, 'kb': 3277, 'kv': 1311,
         'kl_ahead': 34078, 'ki_ahead': 5898},  # Kl+30%, Ki-40% when ahead

        {'name': 'D) I-freeze >=6',
         'kr': 3277, 'kl': 26214, 'ki': 9830, 'kb': 3277, 'kv': 1311,
         'kl_ahead': 26214, 'ki_ahead': 9830, 'freeze_lag': 6},

        {'name': 'E) Hysteresis',
         'kr': 3277, 'kl': 26214, 'ki': 9830, 'kb': 3277, 'kv': 1311,
         'kl_ahead': 26214, 'ki_ahead': 9830,
         'hysteresis': True, 'hyst_exit_lag': 5, 'hyst_blocks': 3},

        {'name': 'F) C+D+E combo',
         'kr': 3277, 'kl': 26214, 'ki': 9830, 'kb': 3277, 'kv': 1311,
         'kl_ahead': 34078, 'ki_ahead': 5898,
         'freeze_lag': 6, 'hysteresis': True, 'hyst_exit_lag': 5, 'hyst_blocks': 3},

        {'name': 'G) Direct lag',
         'kr': 0, 'kl': 65536, 'ki': 0, 'kb': 0, 'kv': 0,
         'kl_ahead': 65536, 'ki_ahead': 0, 'mode': 'direct'},
    ]

    print(f"{'='*95}")
    print(f"  PID ASYMMETRIC TUNING + avg288 bitsQ INTERACTION")
    print(f"  {seeds} seeds × {len(configs)} configs × 500 blocks")
    print(f"  Scenario: burst(40 blk @ 5kH) → drop(40 blk @ 1kH) → recovery(70 blk @ 3kH) → normal(350 blk @ 1.5kH)")
    print(f"{'='*95}")

    all_results = {}
    for c in configs:
        runs = []
        for s in range(42, 42 + seeds):
            runs.append(sim_config(c, s))
        all_results[c['name']] = runs

    def avg(runs, key):
        vals = [r[key] for r in runs if r[key] is not None]
        return statistics.mean(vals) if vals else float('inf')

    # Table
    print(f"\n{'─'*95}")
    header = f"  {'Metric':<22}"
    for c in configs:
        short = c['name'].split(')')[0] + ')'
        header += f" {short:>9}"
    print(header)
    print(f"{'─'*95}")

    metrics = [
        ("Blocks to H9", "blocks_to_h9"),
        ("Max lag", "max_lag"),
        ("Lag std", "lag_std"),
        ("Lag min", "lag_min"),
        ("Blocks in H8+", "time_in_h8_plus"),
        ("Blocks in H10", "time_in_h10"),
        ("Stalls >20m", "stall_20"),
        ("Stalls >40m", "stall_40"),
        ("Sawtooth", "sawtooth"),
        ("Mean dt (s)", "mean_dt"),
        ("Std dt (s)", "std_dt"),
        ("bitsQ final", "bitsq_final"),
        ("bitsQ max", "bitsq_max"),
    ]

    for name, key in metrics:
        line = f"  {name:<22}"
        vals = []
        for c in configs:
            v = avg(all_results[c['name']], key)
            vals.append(v)
            if v == float('inf'):
                line += f" {'—':>9}"
            elif key in ('mean_dt', 'std_dt'):
                line += f" {v:>8.0f}s"
            elif key in ('sawtooth',):
                line += f" {v:>9.3f}"
            elif key in ('bitsq_final', 'bitsq_max'):
                line += f" {v:>9.2f}"
            elif key in ('lag_std',):
                line += f" {v:>9.1f}"
            else:
                line += f" {v:>9.1f}"
        print(line)

    # Profile paths seed 42
    print(f"\n{'─'*95}")
    print(f"  PROFILE PATHS — first 30 blocks (burst, seed 42)")
    print(f"{'─'*95}")

    for c in configs:
        r = all_results[c['name']][0]
        path = [r2['profile'] for r2 in r['rows'][:30]]
        names = ['H'+str(p) if p > 0 else ('B0' if p == 0 else 'E'+str(abs(p))) for p in path]
        short_path = ' '.join(names)
        print(f"\n  {c['name']}:")
        print(f"  {short_path}")

    # bitsQ evolution comparison
    print(f"\n{'─'*95}")
    print(f"  bitsQ EVOLUTION (seed 42)")
    print(f"{'─'*95}")
    print(f"  {'Block':<8}", end="")
    for c in configs:
        short = c['name'].split(')')[0] + ')'
        print(f" {short:>9}", end="")
    print()

    checkpoints = [1, 10, 20, 40, 80, 150, 300, 500]
    for cp in checkpoints:
        if cp > 500: continue
        line = f"  #{cp:<7}"
        for c in configs:
            r = all_results[c['name']][0]
            if cp - 1 < len(r['rows']):
                line += f" {r['rows'][cp-1]['bitsq']:>9.2f}"
            else:
                line += f" {'—':>9}"
        print(line)

    # Verdict
    print(f"\n{'='*95}")
    print(f"  VERDICT")
    print(f"{'='*95}")

    current = all_results[configs[0]['name']]
    current_saw = avg(current, 'sawtooth')
    current_stall = avg(current, 'stall_20')
    current_lag_std = avg(current, 'lag_std')

    best_name = configs[0]['name']
    best_score = float('inf')

    for c in configs:
        runs = all_results[c['name']]
        saw = avg(runs, 'sawtooth')
        stall = avg(runs, 'stall_20')
        lag_s = avg(runs, 'lag_std')
        mean = avg(runs, 'mean_dt')
        # Score: lower = better. Penalize sawtooth, stalls, lag spread, mean deviation
        score = (abs(mean - 600) / 60 * 10 + saw * 50 + stall * 2 + lag_s * 3)
        if score < best_score:
            best_score = score
            best_name = c['name']

    print(f"\n  Best overall: {best_name} (composite score: {best_score:.0f})")
    print(f"\n  Per-metric winners:")
    for name, key in metrics:
        vals = [(avg(all_results[c['name']], key), c['name']) for c in configs]
        if key in ('stall_20', 'stall_40', 'sawtooth', 'std_dt', 'lag_std', 'max_lag', 'bitsq_max'):
            best = min(vals)
        elif key in ('blocks_to_h9', 'time_in_h8_plus', 'time_in_h10'):
            best = min(vals) if key == 'blocks_to_h9' else max(vals)
        else:
            best = min(vals, key=lambda x: abs(x[0] - 600) if key == 'mean_dt' else x[0])
        print(f"    {name:<22}: {best[1]}")


if __name__ == "__main__":
    main()

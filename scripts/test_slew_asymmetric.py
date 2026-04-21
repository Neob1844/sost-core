#!/usr/bin/env python3
"""
Test: Asymmetric slew ±1 vs ±3 upward with lag-adjust + lag cap.

Compares:
  A) Current: slew ±1 up and down
  B) Proposed: slew ±3 up, lag cap down (free descent)

Both have lag-adjust (30s refresh) and lag cap (H ≤ lag).
Simulates burst scenario: 10 fast blocks then recovery.
"""

import math, random, statistics

TARGET = 600
STABILITY = {
    -4: 1.00, -3: 1.00, -2: 1.00, -1: 1.00,
    0: 1.00, 1: 0.97, 2: 0.92, 3: 0.85, 4: 0.78,
    5: 0.65, 6: 0.50, 7: 0.45, 8: 0.35, 9: 0.25, 10: 0.12,
}
H10_CEILING = 10

def sim_burst(up_slew, label, seed, n_blocks=200, burst_hr=5.0, normal_hr=1.5):
    """Simulate burst then recovery."""
    rng = random.Random(seed)

    # Chain state
    prev_profile = 0
    bitsq_float = 12.5  # starting bitsQ
    lag = 0
    sim_time = 0

    rows = []
    max_lag = 0
    blocks_to_h9 = None
    blocks_to_h10 = None
    time_in_h10 = 0
    time_in_h8_plus = 0
    overshoots = 0
    stall_blocks = 0  # blocks > 20min

    for blk in range(n_blocks):
        # Phase: burst for first 30 blocks, then normal
        if blk < 30:
            hr = burst_hr * rng.uniform(0.8, 1.2)
        else:
            hr = normal_hr * rng.uniform(0.7, 1.4)

        # Compute profile from PID (simplified: lag * 0.40)
        h_raw = int(round(lag * 0.40))
        h_raw = max(-4, min(H10_CEILING, h_raw))

        # Safety: lag <= 0 → B0
        if lag <= 0:
            h_raw = min(h_raw, 0)

        # Slew rate (asymmetric for option B)
        if h_raw > prev_profile:
            # Going UP
            profile = min(prev_profile + up_slew, h_raw)
        else:
            # Going DOWN — lag cap handles this (no slew limit)
            profile = h_raw

        # Lag cap
        if profile > 0 and profile > lag:
            profile = max(0, lag)

        # H10 ceiling
        if profile > H10_CEILING:
            profile = H10_CEILING

        profile = max(-4, min(H10_CEILING, profile))

        # Track metrics
        if profile > max_lag:
            max_lag = profile
        if blocks_to_h9 is None and profile >= 9:
            blocks_to_h9 = blk + 1
        if blocks_to_h10 is None and profile >= 10:
            blocks_to_h10 = blk + 1
        if profile >= 10:
            time_in_h10 += 1
        if profile >= 8:
            time_in_h8_plus += 1

        # Sample block time
        stab = STABILITY.get(profile, 0.5)
        C_cal = (2 ** 11.68) / (1.3 * 600.0)
        expected_dt = (2 ** bitsq_float) / (max(hr, 0.01) * stab * C_cal)
        dt = max(1.0, rng.expovariate(1.0 / max(1.0, expected_dt)))

        if dt > 1200:
            stall_blocks += 1

        # Update lag
        sim_time += dt
        expected_blocks = sim_time / TARGET
        lag = int((blk + 1) - expected_blocks)

        # Lag-adjust simulation: every ~30s equivalent, profile adjusts
        # In practice this means the profile tracks lag closely

        rows.append({
            'block': blk + 1,
            'dt': int(dt),
            'profile': profile,
            'lag': lag,
            'bitsq': round(bitsq_float, 2),
            'hr': round(hr, 2),
        })

        prev_profile = profile

    return {
        'label': label,
        'seed': seed,
        'blocks_to_h9': blocks_to_h9,
        'blocks_to_h10': blocks_to_h10,
        'max_lag': max_lag,
        'time_in_h10': time_in_h10,
        'time_in_h8_plus': time_in_h8_plus,
        'stall_blocks': stall_blocks,
        'mean_dt': statistics.mean(r['dt'] for r in rows),
        'std_dt': statistics.stdev(r['dt'] for r in rows),
        'rows': rows,
    }


def main():
    seeds = 30

    print(f"{'='*70}")
    print(f"  ASYMMETRIC SLEW TEST: ±1 vs ±3 upward")
    print(f"  {seeds} seeds × 200 blocks (30 burst + 170 recovery)")
    print(f"  Both have lag cap (free descent) + lag-adjust")
    print(f"{'='*70}")

    results_a = []
    results_b = []

    for s in range(42, 42 + seeds):
        results_a.append(sim_burst(1, "A) slew ±1", s))
        results_b.append(sim_burst(3, "B) slew ±3 up", s))

    def avg(results, key):
        vals = [r[key] for r in results if r[key] is not None]
        return statistics.mean(vals) if vals else float('inf')

    print(f"\n{'─'*70}")
    print(f"  {'Metric':<30} {'A) slew ±1':>15} {'B) slew ±3 up':>15}")
    print(f"{'─'*70}")

    metrics = [
        ("Blocks to reach H9", "blocks_to_h9"),
        ("Blocks to reach H10", "blocks_to_h10"),
        ("Max profile reached", "max_lag"),
        ("Blocks in H10", "time_in_h10"),
        ("Blocks in H8+", "time_in_h8_plus"),
        ("Stall blocks (>20min)", "stall_blocks"),
        ("Mean block time (s)", "mean_dt"),
        ("Std block time (s)", "std_dt"),
    ]

    for name, key in metrics:
        va = avg(results_a, key)
        vb = avg(results_b, key)
        marker = ""
        if key in ("blocks_to_h9", "blocks_to_h10") and vb < va:
            marker = " <<<"
        elif key in ("stall_blocks",) and vb < va:
            marker = " <<<"
        print(f"  {name:<30} {va:>15.1f} {vb:>15.1f}{marker}")

    # Profile path for seed 42 (first 30 blocks — burst phase)
    print(f"\n{'─'*70}")
    print(f"  PROFILE PATH — burst phase (first 30 blocks, seed 42)")
    print(f"{'─'*70}")

    ra = results_a[0]
    rb = results_b[0]

    print(f"\n  A) slew ±1:")
    path_a = ' → '.join([f"H{r['profile']}" if r['profile'] > 0 else ("B0" if r['profile']==0 else f"E{abs(r['profile'])}") for r in ra['rows'][:30]])
    print(f"  {path_a}")
    print(f"  H9 at block {ra['blocks_to_h9']}, H10 at block {ra['blocks_to_h10']}")

    print(f"\n  B) slew ±3 up:")
    path_b = ' → '.join([f"H{r['profile']}" if r['profile'] > 0 else ("B0" if r['profile']==0 else f"E{abs(r['profile'])}") for r in rb['rows'][:30]])
    print(f"  {path_b}")
    print(f"  H9 at block {rb['blocks_to_h9']}, H10 at block {rb['blocks_to_h10']}")

    # Lag comparison during burst
    print(f"\n  Lag at block 10:  A={ra['rows'][9]['lag']:+d}  B={rb['rows'][9]['lag']:+d}")
    print(f"  Lag at block 20:  A={ra['rows'][19]['lag']:+d}  B={rb['rows'][19]['lag']:+d}")
    print(f"  Lag at block 30:  A={ra['rows'][29]['lag']:+d}  B={rb['rows'][29]['lag']:+d}")

    # Verdict
    print(f"\n{'='*70}")
    print(f"  VERDICT")
    print(f"{'='*70}")

    h9_a = avg(results_a, "blocks_to_h9")
    h9_b = avg(results_b, "blocks_to_h9")
    lag_a = avg(results_a, "max_lag")
    lag_b = avg(results_b, "max_lag")
    stall_a = avg(results_a, "stall_blocks")
    stall_b = avg(results_b, "stall_blocks")

    print(f"\n  Blocks to H9:  A={h9_a:.1f}  B={h9_b:.1f}  (improvement: {(h9_a-h9_b)/h9_a*100:.0f}%)")
    print(f"  Stall blocks:  A={stall_a:.1f}  B={stall_b:.1f}")

    if h9_b < h9_a * 0.7 and stall_b <= stall_a:
        print(f"\n  RECOMMENDATION: slew ±3 up reaches braking zone significantly faster")
        print(f"  without increasing stalls. Worth implementing.")
    elif h9_b < h9_a * 0.85:
        print(f"\n  RECOMMENDATION: moderate improvement. Consider implementing.")
    else:
        print(f"\n  RECOMMENDATION: minimal difference. Not worth the consensus change.")


if __name__ == "__main__":
    main()

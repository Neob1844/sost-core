#!/usr/bin/env python3
"""Simulate cASERT difficulty adjustment under various hashrate scenarios."""
import json, os, math
import numpy as np

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs', 'casert_audit')
os.makedirs(OUT_DIR, exist_ok=True)

# cASERT constants (from params.h)
TARGET_SPACING = 600
Q16_ONE = 65536
GENESIS_BITSQ = 765730
MIN_BITSQ = Q16_ONE
MAX_BITSQ = 255 * Q16_ONE
BITSQ_HALF_LIFE = 172800  # 48h
BITSQ_MAX_DELTA_DEN = 16  # 6.25% cap
BLOCKS_PER_EPOCH = 131553
BASELINE_HASHRATE = 5.5  # attempts/sec

# Horner coefficients for 2^frac (Q0.16)
C_LN2 = 45426
C_LN2_SQ_2 = 15743
C_LN2_CU_6 = 3638


def horner_2exp(frac):
    """Cubic approximation of 2^(frac/65536) in Q16.16."""
    t = C_LN2_CU_6
    t = C_LN2_SQ_2 + ((t * frac) >> 16)
    t = C_LN2 + ((t * frac) >> 16)
    return Q16_ONE + ((t * frac) >> 16)


def casert_next_bitsq(chain_times, chain_bitsq, next_height):
    """Pure Python implementation of casert_next_bitsq."""
    if not chain_times or next_height <= 0:
        return GENESIS_BITSQ

    # Anchor block
    epoch = next_height // BLOCKS_PER_EPOCH
    if epoch > 0:
        anchor_idx = min(epoch * BLOCKS_PER_EPOCH - 1, len(chain_times) - 1)
    else:
        anchor_idx = 0

    anchor_time = chain_times[anchor_idx]
    anchor_bitsq = chain_bitsq[anchor_idx] if anchor_idx < len(chain_bitsq) else GENESIS_BITSQ

    parent_idx = len(chain_times) - 1
    expected_parent_time = anchor_time + (parent_idx - anchor_idx) * TARGET_SPACING
    td = chain_times[-1] - expected_parent_time

    # Exponent in Q16.16
    exponent = (-td * Q16_ONE) // BITSQ_HALF_LIFE if BITSQ_HALF_LIFE else 0
    shifts = exponent >> 16
    frac = exponent & 0xFFFF

    factor = horner_2exp(frac)
    raw = (anchor_bitsq * factor) >> 16

    if shifts > 0:
        if shifts > 24:
            raw = MAX_BITSQ
        else:
            raw <<= shifts
    elif shifts < 0:
        rs = -shifts
        if rs > 24:
            raw = 0
        else:
            raw >>= rs

    # Per-block delta cap
    prev_bitsq = chain_bitsq[-1] if chain_bitsq else GENESIS_BITSQ
    max_delta = max(prev_bitsq // BITSQ_MAX_DELTA_DEN, 1)
    delta = raw - prev_bitsq
    delta = max(-max_delta, min(max_delta, delta))
    result = prev_bitsq + delta

    return max(MIN_BITSQ, min(MAX_BITSQ, result))


def expected_block_time(bitsq, hashrate):
    """Expected seconds per block given difficulty and hashrate.

    bitsq represents log2 of the difficulty multiplier.
    Higher bitsq = harder = longer block time.
    At genesis calibration: bitsq=765730 with 5.5 att/s → ~600s.
    """
    # Difficulty ratio relative to genesis
    diff_ratio = bitsq / GENESIS_BITSQ
    # At genesis difficulty with baseline hashrate, mean = TARGET_SPACING
    # Scale by difficulty ratio and inverse hashrate ratio
    return TARGET_SPACING * diff_ratio * (BASELINE_HASHRATE / hashrate)


def simulate_scenario(name, hashrate_fn, n_blocks=500):
    """Run a simulation scenario.

    hashrate_fn(block_index) -> hashrate in att/s at that block
    """
    times = [0]  # genesis at t=0
    bitsq_list = [GENESIS_BITSQ]
    block_times_out = [0]

    for i in range(1, n_blocks):
        next_bitsq = casert_next_bitsq(times, bitsq_list, i)
        hr = hashrate_fn(i)
        mean_bt = expected_block_time(next_bitsq, hr)
        # Sample from exponential distribution (Poisson process)
        bt = max(1, int(np.random.exponential(mean_bt)))
        t = times[-1] + bt

        times.append(t)
        bitsq_list.append(next_bitsq)
        block_times_out.append(bt)

    return {
        'name': name,
        'heights': list(range(n_blocks)),
        'times': times,
        'bitsq': bitsq_list,
        'block_times': block_times_out,
        'n_blocks': n_blocks,
    }


def analyze_scenario(s):
    """Compute statistics for a scenario."""
    bt = np.array(s['block_times'][1:], dtype=float)
    bq = np.array(s['bitsq'], dtype=float)

    # Convergence: last 100 blocks
    last100 = bt[-100:] if len(bt) > 100 else bt
    # Convergence time: first block where 50-block MA is within 20% of target
    window = 50
    if len(bt) > window:
        ma = np.convolve(bt, np.ones(window)/window, mode='valid')
        converged_at = None
        for i in range(len(ma)):
            if abs(ma[i] - TARGET_SPACING) / TARGET_SPACING < 0.2:
                converged_at = i + window
                break
    else:
        ma = bt
        converged_at = None

    return {
        'name': s['name'],
        'mean_bt': round(float(np.mean(bt)), 1),
        'median_bt': round(float(np.median(bt)), 1),
        'stdev_bt': round(float(np.std(bt)), 1),
        'last100_mean': round(float(np.mean(last100)), 1),
        'pct_fast': round(float(np.sum(bt < 120) / len(bt) * 100), 1),
        'pct_slow': round(float(np.sum(bt > 1800) / len(bt) * 100), 1),
        'converged_at_block': converged_at,
        'final_bitsq': s['bitsq'][-1],
        'min_bitsq': int(np.min(bq)),
        'max_bitsq': int(np.max(bq)),
    }


def run_all():
    np.random.seed(42)
    results = {}

    print("="*60)
    print("cASERT SIMULATION — 6 SCENARIOS")
    print("="*60)

    # Scenario 1: Constant hashrate
    print("\n--- Scenario 1: Constant hashrate (5.5 att/s) ---")
    s1 = simulate_scenario("1_constant", lambda i: BASELINE_HASHRATE, 500)
    a1 = analyze_scenario(s1)
    print(f"  Mean BT: {a1['mean_bt']}s, Last100: {a1['last100_mean']}s, Converged: block {a1['converged_at_block']}")
    results['scenario_1'] = a1

    # Scenario 2: Hashrate doubles at block 100
    print("\n--- Scenario 2: Hashrate x2 at block 100 ---")
    s2 = simulate_scenario("2_double", lambda i: BASELINE_HASHRATE if i < 100 else BASELINE_HASHRATE * 2, 500)
    a2 = analyze_scenario(s2)
    # Measure adjustment time after doubling
    bt2 = np.array(s2['block_times'][101:], dtype=float)
    if len(bt2) > 50:
        ma2 = np.convolve(bt2, np.ones(50)/50, mode='valid')
        adj_time = None
        for j in range(len(ma2)):
            if abs(ma2[j] - TARGET_SPACING) / TARGET_SPACING < 0.2:
                adj_time = j + 50
                break
        a2['adjustment_blocks'] = adj_time
    print(f"  Mean BT: {a2['mean_bt']}s, After doubling adj: ~{a2.get('adjustment_blocks','?')} blocks")
    results['scenario_2'] = a2

    # Scenario 3: Hashrate halves at block 100
    print("\n--- Scenario 3: Hashrate /2 at block 100 ---")
    s3 = simulate_scenario("3_halve", lambda i: BASELINE_HASHRATE if i < 100 else BASELINE_HASHRATE / 2, 500)
    a3 = analyze_scenario(s3)
    print(f"  Mean BT: {a3['mean_bt']}s, Last100: {a3['last100_mean']}s")
    print(f"  Slow blocks (>30min): {a3['pct_slow']}%")
    results['scenario_3'] = a3

    # Scenario 4: Oscillating hashrate (on/off every 50 blocks)
    print("\n--- Scenario 4: Oscillating hashrate (x2 every 50 blocks) ---")
    s4 = simulate_scenario("4_oscillate",
        lambda i: BASELINE_HASHRATE * 2 if (i // 50) % 2 == 0 else BASELINE_HASHRATE / 2, 500)
    a4 = analyze_scenario(s4)
    print(f"  Mean BT: {a4['mean_bt']}s, Stdev: {a4['stdev_bt']}s")
    results['scenario_4'] = a4

    # Scenario 5: Flash hashrate (100x for 10 blocks)
    print("\n--- Scenario 5: Flash hashrate (100x for blocks 100-109) ---")
    s5 = simulate_scenario("5_flash",
        lambda i: BASELINE_HASHRATE * 100 if 100 <= i < 110 else BASELINE_HASHRATE, 500)
    a5 = analyze_scenario(s5)
    # Check overshoot after flash
    post_flash_bt = np.array(s5['block_times'][111:160], dtype=float)
    a5['post_flash_mean'] = round(float(np.mean(post_flash_bt)), 1) if len(post_flash_bt) > 0 else 0
    a5['post_flash_max'] = round(float(np.max(post_flash_bt)), 0) if len(post_flash_bt) > 0 else 0
    print(f"  Post-flash mean BT: {a5['post_flash_mean']}s, max: {a5['post_flash_max']}s")
    results['scenario_5'] = a5

    # Scenario 6: Selfish mining (withhold blocks then release burst)
    print("\n--- Scenario 6: Selfish mining pattern (burst every 20 blocks) ---")
    def selfish_hr(i):
        # Every 20 blocks: 5 blocks come very fast (as if miner releases withheld blocks)
        phase = i % 20
        if phase < 5:
            return BASELINE_HASHRATE * 10  # burst
        return BASELINE_HASHRATE * 0.7  # reduced (public miners only)
    s6 = simulate_scenario("6_selfish", selfish_hr, 500)
    a6 = analyze_scenario(s6)
    print(f"  Mean BT: {a6['mean_bt']}s, Stdev: {a6['stdev_bt']}s")
    results['scenario_6'] = a6

    # Generate combined plot
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle('cASERT Simulation — 6 Scenarios', fontsize=14, fontweight='bold')

        scenarios = [s1, s2, s3, s4, s5, s6]
        for idx, (s, ax) in enumerate(zip(scenarios, axes.flat)):
            bt = s['block_times'][1:]
            ax.scatter(range(1, len(bt)+1), bt, s=2, alpha=0.4, c='steelblue')
            ax.axhline(y=600, color='green', linestyle='--', alpha=0.7)
            # Moving average
            if len(bt) > 30:
                ma = np.convolve(bt, np.ones(30)/30, mode='valid')
                ax.plot(range(30, 30+len(ma)), ma, color='red', linewidth=1.5)
            ax.set_title(s['name'], fontsize=10)
            ax.set_xlabel('Block')
            ax.set_ylabel('Block Time (s)')
            ax.set_ylim(0, min(max(bt)*1.1, 10000))

        plt.tight_layout()
        plt.savefig(os.path.join(OUT_DIR, 'casert_simulation.png'), dpi=150)
        plt.close()
        print(f"\nPlot saved: {OUT_DIR}/casert_simulation.png")
    except ImportError:
        print("\n[WARN] matplotlib not available")

    # Save results
    with open(os.path.join(OUT_DIR, 'casert_simulation.json'), 'w') as f:
        json.dump(results, f, indent=2)
    print(f"JSON saved: {OUT_DIR}/casert_simulation.json")

    # Summary table
    print(f"\n{'='*80}")
    print(f"{'Scenario':<40s} {'Mean BT':>8s} {'Last100':>8s} {'%Fast':>6s} {'%Slow':>6s} {'Converge':>9s}")
    print(f"{'-'*80}")
    for k, v in results.items():
        print(f"  {v['name']:<38s} {v['mean_bt']:>7.0f}s {v['last100_mean']:>7.0f}s {v['pct_fast']:>5.1f}% {v['pct_slow']:>5.1f}% {str(v.get('converged_at_block','—')):>8s}")


if __name__ == '__main__':
    run_all()

#!/usr/bin/env python3
"""Analyze cASERT performance from real chain data."""
import json, os, sys, time
import numpy as np

CHAIN_PATH = os.path.join(os.path.dirname(__file__), '..', 'build', 'chain.json')
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs', 'casert_audit')
os.makedirs(OUT_DIR, exist_ok=True)

TARGET_SPACING = 600  # 10 minutes
Q16_ONE = 65536
GENESIS_BITSQ = 765730

# Profile lookup by (scale, k, margin, steps)
PROFILE_MAP = {
    (1,3,280,2): 'E4', (1,3,240,3): 'E3', (1,3,225,4): 'E2', (1,4,205,4): 'E1',
    (1,4,185,4): 'B0', (1,4,170,5): 'H1', (1,5,160,5): 'H2', (1,5,150,6): 'H3',
    (1,6,145,6): 'H4', (2,5,140,5): 'H5', (2,5,135,6): 'H6', (2,6,130,6): 'H7',
    (2,6,125,7): 'H8', (2,7,120,7): 'H9',
}


def load_chain():
    with open(CHAIN_PATH) as f:
        d = json.load(f)
    blocks = d['blocks']
    print(f"Loaded {len(blocks)} blocks (chain height {d['chain_height']})")
    return blocks


def identify_profile(b):
    s = b.get('stab_scale')
    k = b.get('stab_k')
    m = b.get('stab_margin')
    st = b.get('stab_steps')
    if s is None:
        return 'GENESIS'
    return PROFILE_MAP.get((s, k, m, st), f'?({s},{k},{m},{st})')


def analyze(blocks):
    results = {}
    n = len(blocks)

    # Block times
    heights = []
    timestamps = []
    bits_q = []
    block_times = []
    profiles = []

    for i, b in enumerate(blocks):
        h = b['height']
        t = b['timestamp']
        bq = b['bits_q']
        heights.append(h)
        timestamps.append(t)
        bits_q.append(bq)
        profiles.append(identify_profile(b))
        if i > 0:
            dt = t - blocks[i-1]['timestamp']
            block_times.append(dt)
        else:
            block_times.append(0)

    bt = np.array(block_times[1:], dtype=float)  # skip genesis
    bq = np.array(bits_q, dtype=float)

    print(f"\n{'='*60}")
    print(f"CHAIN ANALYSIS — {n} blocks")
    print(f"{'='*60}")

    # Genesis info
    t0 = timestamps[0]
    t_last = timestamps[-1]
    chain_age_h = (t_last - t0) / 3600
    print(f"\nGenesis: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(t0))}")
    print(f"Latest:  {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(t_last))}")
    print(f"Chain age: {chain_age_h:.1f} hours ({chain_age_h/24:.1f} days)")
    print(f"Expected blocks at 600s: {chain_age_h*6:.0f}")
    print(f"Actual blocks: {n}")
    results['chain_age_hours'] = round(chain_age_h, 1)
    results['expected_blocks'] = round(chain_age_h * 6)
    results['actual_blocks'] = n

    # Block time statistics
    print(f"\n--- BLOCK TIME STATISTICS ---")
    print(f"Mean:   {np.mean(bt):.1f}s ({np.mean(bt)/60:.1f} min)")
    print(f"Median: {np.median(bt):.1f}s ({np.median(bt)/60:.1f} min)")
    print(f"Stdev:  {np.std(bt):.1f}s")
    print(f"Min:    {np.min(bt):.0f}s ({np.min(bt)/60:.1f} min) at height {heights[1+np.argmin(bt)]}")
    print(f"Max:    {np.max(bt):.0f}s ({np.max(bt)/60:.1f} min) at height {heights[1+np.argmax(bt)]}")

    # Percentiles
    for p in [5, 10, 25, 50, 75, 90, 95]:
        print(f"  P{p:2d}: {np.percentile(bt, p):.0f}s")

    fast_2min = np.sum(bt < 120) / len(bt) * 100
    slow_30min = np.sum(bt > 1800) / len(bt) * 100
    stall_60min = np.sum(bt > 3600) / len(bt) * 100
    stall_2h = np.sum(bt > 7200) / len(bt) * 100
    print(f"\n  < 2 min:  {fast_2min:.1f}% ({np.sum(bt < 120)} blocks)")
    print(f"  > 30 min: {slow_30min:.1f}% ({np.sum(bt > 1800)} blocks)")
    print(f"  > 60 min: {stall_60min:.1f}% ({np.sum(bt > 3600)} blocks)")
    print(f"  > 2h:     {stall_2h:.1f}% ({np.sum(bt > 7200)} blocks)")

    results['block_time'] = {
        'mean': round(float(np.mean(bt)), 1),
        'median': round(float(np.median(bt)), 1),
        'stdev': round(float(np.std(bt)), 1),
        'min': round(float(np.min(bt)), 0),
        'max': round(float(np.max(bt)), 0),
        'pct_under_2min': round(fast_2min, 1),
        'pct_over_30min': round(slow_30min, 1),
        'pct_over_60min': round(stall_60min, 1),
    }

    # Exponential distribution check
    # For Poisson process with rate λ=1/600, block times should be exponential
    # Mean should equal stdev for exponential
    cv = np.std(bt) / np.mean(bt)
    print(f"\n  Coefficient of variation: {cv:.3f} (1.0 = perfect exponential)")
    results['cv'] = round(float(cv), 3)

    # Difficulty statistics
    print(f"\n--- DIFFICULTY (bitsQ) ---")
    print(f"Genesis: {bits_q[0]} ({bits_q[0]/Q16_ONE:.4f})")
    print(f"Current: {bits_q[-1]} ({bits_q[-1]/Q16_ONE:.4f})")
    print(f"Min:     {int(np.min(bq))} ({np.min(bq)/Q16_ONE:.4f}) at height {heights[np.argmin(bq)]}")
    print(f"Max:     {int(np.max(bq))} ({np.max(bq)/Q16_ONE:.4f}) at height {heights[np.argmax(bq)]}")
    print(f"Mean:    {np.mean(bq):.0f} ({np.mean(bq)/Q16_ONE:.4f})")

    results['difficulty'] = {
        'genesis': bits_q[0],
        'current': bits_q[-1],
        'min': int(np.min(bq)),
        'max': int(np.max(bq)),
        'mean': round(float(np.mean(bq)), 0),
    }

    # Profile analysis
    print(f"\n--- CASERT PROFILES ---")
    profile_counts = {}
    for p in profiles:
        profile_counts[p] = profile_counts.get(p, 0) + 1
    for p in sorted(profile_counts.keys()):
        pct = profile_counts[p] / n * 100
        print(f"  {p:8s}: {profile_counts[p]:5d} blocks ({pct:5.1f}%)")

    # Profile transitions
    transitions = 0
    transition_list = []
    for i in range(1, len(profiles)):
        if profiles[i] != profiles[i-1]:
            transitions += 1
            transition_list.append((heights[i], profiles[i-1], profiles[i]))
    print(f"\nProfile transitions: {transitions}")
    if transition_list:
        print(f"  First 10:")
        for h, fr, to in transition_list[:10]:
            print(f"    Height {h}: {fr} → {to}")
        if len(transition_list) > 20:
            print(f"  Last 5:")
            for h, fr, to in transition_list[-5:]:
                print(f"    Height {h}: {fr} → {to}")

    results['profiles'] = profile_counts
    results['transitions'] = transitions

    # Anti-stall activations (detect blocks > 2h after a normal block)
    antistall_count = 0
    for i in range(1, len(block_times)):
        if block_times[i] > 7200:  # > 2h
            antistall_count += 1
    print(f"\nPotential anti-stall activations (gaps > 2h): {antistall_count}")
    results['antistall_activations'] = antistall_count

    # Moving average convergence
    window = 72  # 72 blocks ≈ 12 hours
    if len(bt) > window:
        ma = np.convolve(bt, np.ones(window)/window, mode='valid')
        print(f"\n--- MOVING AVERAGE ({window}-block window) ---")
        print(f"  First MA:  {ma[0]:.1f}s")
        print(f"  Last MA:   {ma[-1]:.1f}s")
        print(f"  Min MA:    {np.min(ma):.1f}s at block ~{np.argmin(ma)+window}")
        print(f"  Max MA:    {np.max(ma):.1f}s at block ~{np.argmax(ma)+window}")
        print(f"  Stdev of MA: {np.std(ma):.1f}s")

    # Phase analysis: early chain vs mature chain
    if len(bt) > 200:
        early = bt[:100]
        mature = bt[-500:] if len(bt) > 500 else bt[100:]
        print(f"\n--- EARLY vs MATURE ---")
        print(f"  Early (first 100):  mean={np.mean(early):.0f}s, stdev={np.std(early):.0f}s")
        print(f"  Mature (last {len(mature)}):  mean={np.mean(mature):.0f}s, stdev={np.std(mature):.0f}s")

    # Generate plots
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f'cASERT Performance — {n} blocks', fontsize=14, fontweight='bold')

        # 1. Block time vs height
        ax = axes[0, 0]
        ax.scatter(heights[1:], bt, s=2, alpha=0.5, c='steelblue')
        ax.axhline(y=600, color='green', linestyle='--', alpha=0.7, label='Target 600s')
        if len(bt) > window:
            ma_x = heights[window:]
            ax.plot(ma_x, ma, color='red', linewidth=1.5, label=f'{window}-block MA')
        ax.set_xlabel('Block Height')
        ax.set_ylabel('Block Time (s)')
        ax.set_title('Block Time vs Height')
        ax.legend(fontsize=8)
        ax.set_ylim(0, min(np.max(bt) * 1.1, 20000))

        # 2. Difficulty vs height
        ax = axes[0, 1]
        ax.plot(heights, [b/Q16_ONE for b in bits_q], color='orange', linewidth=0.8)
        ax.set_xlabel('Block Height')
        ax.set_ylabel('bitsQ (Q16.16)')
        ax.set_title('Difficulty vs Height')

        # 3. Profile vs height
        ax = axes[0, 2]
        profile_order = ['E4','E3','E2','E1','B0','H1','H2','H3','H4','H5','H6','H7','H8','H9']
        profile_to_num = {p: i for i, p in enumerate(profile_order)}
        profile_nums = [profile_to_num.get(p, -1) for p in profiles]
        ax.scatter(heights, profile_nums, s=3, alpha=0.6, c='lime')
        ax.set_yticks(range(len(profile_order)))
        ax.set_yticklabels(profile_order, fontsize=7)
        ax.set_xlabel('Block Height')
        ax.set_title('cASERT Profile vs Height')

        # 4. Block time histogram
        ax = axes[1, 0]
        bins = np.linspace(0, min(np.max(bt), 5000), 60)
        ax.hist(bt, bins=bins, color='steelblue', alpha=0.7, density=True, label='Actual')
        # Exponential overlay
        lam = 1.0 / np.mean(bt)
        x_exp = np.linspace(0, bins[-1], 200)
        ax.plot(x_exp, lam * np.exp(-lam * x_exp), 'r-', linewidth=2, label=f'Exponential(λ=1/{np.mean(bt):.0f})')
        ax.set_xlabel('Block Time (s)')
        ax.set_ylabel('Density')
        ax.set_title('Block Time Distribution')
        ax.legend(fontsize=8)

        # 5. Moving average
        ax = axes[1, 1]
        if len(bt) > window:
            ax.plot(heights[window:], ma, color='red', linewidth=1)
            ax.axhline(y=600, color='green', linestyle='--', alpha=0.7)
            ax.set_xlabel('Block Height')
            ax.set_ylabel('Block Time (s)')
            ax.set_title(f'{window}-Block Moving Average')
            ax.set_ylim(0, max(np.max(ma)*1.2, 1200))

        # 6. Difficulty delta per block
        ax = axes[1, 2]
        deltas = np.diff(np.array(bits_q, dtype=float))
        pct_deltas = deltas / np.array(bits_q[:-1], dtype=float) * 100
        ax.scatter(heights[1:], pct_deltas, s=2, alpha=0.4, c='purple')
        ax.axhline(y=6.25, color='red', linestyle='--', alpha=0.5, label='±6.25% cap')
        ax.axhline(y=-6.25, color='red', linestyle='--', alpha=0.5)
        ax.set_xlabel('Block Height')
        ax.set_ylabel('Difficulty Change (%)')
        ax.set_title('Per-Block Difficulty Delta')
        ax.legend(fontsize=8)
        ax.set_ylim(-10, 10)

        plt.tight_layout()
        plt.savefig(os.path.join(OUT_DIR, 'casert_performance.png'), dpi=150)
        plt.close()
        print(f"\nPlot saved: {OUT_DIR}/casert_performance.png")

    except ImportError:
        print("\n[WARN] matplotlib not available, skipping plots")

    return results


if __name__ == '__main__':
    blocks = load_chain()
    results = analyze(blocks)

    with open(os.path.join(OUT_DIR, 'casert_analysis.json'), 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nJSON saved: {OUT_DIR}/casert_analysis.json")

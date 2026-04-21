#!/usr/bin/env python3
"""
Test: bitsQ lag-adjust vs no lag-adjust for bitsQ.

Simulates the real scenario from block 5263:
- bitsQ = 18.619 (very high)
- lag = 10, profile starts at H10
- lag-adjust drops profile every ~10 min
- Question: should bitsQ also drop via lag-adjust?

Compares:
  A) Current: lag-adjust changes profile only, bitsQ stays fixed
  B) Proposed: lag-adjust also recalculates bitsQ with avg288 including
     current elapsed time as virtual interval

Uses production-like block history to compute avg288.
"""

import math, random, statistics

TARGET = 600
STABILITY = {
    0: 1.00, 1: 0.97, 2: 0.92, 3: 0.85, 4: 0.78,
    5: 0.65, 6: 0.50, 7: 0.45, 8: 0.35, 9: 0.25, 10: 0.12,
}
Q16 = 65536
DEADBAND = 30

# Real production-like history: mix of fast and slow blocks
# Simulating ~288 blocks with avg around 500-550s (chain ahead)
def make_history(seed=42):
    rng = random.Random(seed)
    intervals = []
    for _ in range(288):
        # Mix: 60% fast (30-120s), 25% normal (300-900s), 15% slow (1200-4000s)
        r = rng.random()
        if r < 0.60:
            intervals.append(rng.randint(30, 120))
        elif r < 0.85:
            intervals.append(rng.randint(300, 900))
        else:
            intervals.append(rng.randint(1200, 4000))
    return intervals

def avg288(intervals):
    return sum(intervals) / len(intervals)

def median288(intervals):
    s = sorted(intervals)
    return s[len(s) // 2]

def compute_bitsq_delta(prev_bitsq, intervals):
    """avg288 + median + dynamic cap — exact mirror of casert.cpp"""
    avg = avg288(intervals)
    med = median288(intervals)
    dev_avg = avg - TARGET
    dev_med = med - TARGET
    abs_avg = abs(dev_avg)
    abs_med = abs(dev_med)
    effective_dev = max(abs_avg, abs_med)

    if effective_dev <= DEADBAND:
        return 0

    # Dynamic cap
    if effective_dev <= 60:
        max_d = prev_bitsq // 200    # 0.5%
    elif effective_dev <= 120:
        max_d = prev_bitsq // 67     # 1.5%
    elif effective_dev <= 240:
        max_d = prev_bitsq // 40     # 2.5%
    else:
        max_d = prev_bitsq // 33     # 3.0%

    # Direction: use median if avg is in deadband
    direction_dev = dev_avg
    direction_abs = abs_avg
    if abs_avg <= DEADBAND and abs_med > DEADBAND:
        direction_dev = dev_med
        direction_abs = abs_med

    excess = direction_abs - DEADBAND
    raw_delta = (prev_bitsq * excess) // (TARGET * 4)

    if direction_dev < 0:
        delta = min(raw_delta, max_d)   # too fast → up
    else:
        delta = -min(raw_delta, max_d)  # too slow → down

    return delta

def sample_time(bitsq_float, stability, hashrate=35):
    """Expected time to find block given bitsQ, stability, hashrate."""
    C_cal = (2 ** 11.68) / (1.3 * 600.0)
    expected = (2 ** bitsq_float) / (hashrate * stability * C_cal)
    return max(1.0, expected)

def run_scenario(label, history, start_bitsq, start_lag, adjust_bitsq=False, seeds=20):
    results = []

    for seed in range(42, 42 + seeds):
        rng = random.Random(seed)
        bitsq = start_bitsq
        lag = start_lag
        elapsed = 0
        found = False
        profile_history = []
        bitsq_history = []

        # Simulate minute by minute until block found or 120 min
        for minute in range(121):
            # Profile from lag cap
            profile = min(10, max(0, lag))
            stab = STABILITY.get(profile, 0.01)

            profile_history.append(profile)
            bitsq_history.append(bitsq / Q16)

            # Try mining for 1 minute (60 attempts at ~1/s effective)
            bitsq_float = bitsq / Q16
            expected_nonces = sample_time(bitsq_float, stab)
            # P(find in 60s at 35 att/s) = 1 - exp(-60*35 / expected_nonces)
            p_find = 1.0 - math.exp(-60.0 * 35.0 * stab / max(expected_nonces, 1))
            if rng.random() < p_find:
                found = True
                elapsed = minute
                break

            # Every 10 minutes: lag drops by 1
            if minute > 0 and minute % 10 == 0:
                lag -= 1
                if lag < 0: lag = 0

                # If bitsQ lag-adjust is enabled: recalculate
                if adjust_bitsq and lag >= 0:
                    # Add current elapsed as virtual interval
                    virtual_history = list(history)
                    virtual_history.append(minute * 60)  # current elapsed in seconds
                    if len(virtual_history) > 288:
                        virtual_history = virtual_history[-288:]
                    delta = compute_bitsq_delta(bitsq, virtual_history)
                    bitsq = max(Q16, bitsq + delta)

            elapsed = minute

        results.append({
            "found": found,
            "elapsed_min": elapsed,
            "final_profile": profile_history[-1],
            "final_bitsq": bitsq_history[-1],
            "bitsq_drop": bitsq_history[0] - bitsq_history[-1],
            "profile_path": profile_history[:13],  # first 120 min sampled at 10min
            "bitsq_path": [round(b, 2) for b in bitsq_history[::10]][:13],
        })

    return results

def main():
    history = make_history()
    avg = avg288(history)
    med = median288(history)
    print(f"{'='*70}")
    print(f"  bitsQ LAG-ADJUST TEST")
    print(f"  History: avg288={avg:.0f}s, median288={med:.0f}s")
    print(f"  Start: bitsQ=18.619 (1,220,204), lag=10, H10")
    print(f"{'='*70}")

    start_bitsq = 1220204  # 18.619 bits

    # Scenario A: current (profile-only lag-adjust)
    results_a = run_scenario("A) Profile-only", history, start_bitsq, 10, adjust_bitsq=False)
    # Scenario B: proposed (profile + bitsQ lag-adjust)
    results_b = run_scenario("B) Profile+bitsQ", history, start_bitsq, 10, adjust_bitsq=True)

    print(f"\n{'─'*70}")
    print(f"  {'Metric':<30} {'A) Profile only':>15} {'B) Profile+bitsQ':>15}")
    print(f"{'─'*70}")

    found_a = sum(1 for r in results_a if r["found"])
    found_b = sum(1 for r in results_b if r["found"])
    times_a = [r["elapsed_min"] for r in results_a if r["found"]]
    times_b = [r["elapsed_min"] for r in results_b if r["found"]]

    print(f"  {'Blocks found (of 20)':<30} {found_a:>15} {found_b:>15}")
    if times_a:
        print(f"  {'Mean time to find (min)':<30} {statistics.mean(times_a):>15.1f} {statistics.mean(times_b):>15.1f}" if times_b else "")
        print(f"  {'Median time to find (min)':<30} {statistics.median(times_a):>15.1f} {statistics.median(times_b):>15.1f}" if times_b else "")
    not_found_a = sum(1 for r in results_a if not r["found"])
    not_found_b = sum(1 for r in results_b if not r["found"])
    print(f"  {'Stuck >120 min':<30} {not_found_a:>15} {not_found_b:>15}")

    bitsq_drop_a = statistics.mean(r["bitsq_drop"] for r in results_a)
    bitsq_drop_b = statistics.mean(r["bitsq_drop"] for r in results_b)
    print(f"  {'bitsQ drop (bits)':<30} {bitsq_drop_a:>15.3f} {bitsq_drop_b:>15.3f}")

    # Show first seed detail
    print(f"\n{'─'*70}")
    print(f"  DETAIL — seed 42")
    print(f"{'─'*70}")

    for label, results in [("A) Profile-only", results_a), ("B) Profile+bitsQ", results_b)]:
        r = results[0]
        print(f"\n  {label}:")
        print(f"  Found: {'YES at ' + str(r['elapsed_min']) + 'min' if r['found'] else 'NO (>120min)'}")
        print(f"  Profile path (every 10min): {r['profile_path']}")
        print(f"  bitsQ path (every 10min):   {r['bitsq_path']}")
        print(f"  bitsQ drop: {r['bitsq_drop']:.3f} bits")

    # Verdict
    print(f"\n{'='*70}")
    print(f"  VERDICT")
    print(f"{'='*70}")
    if found_b > found_a:
        print(f"\n  bitsQ lag-adjust finds MORE blocks: {found_b} vs {found_a}")
        if times_b and times_a:
            improvement = (statistics.mean(times_a) - statistics.mean(times_b)) / statistics.mean(times_a) * 100
            print(f"  Mean time improvement: {improvement:.0f}%")
        print(f"  RECOMMENDATION: worth implementing")
    elif found_b == found_a and times_b and times_a and statistics.mean(times_b) < statistics.mean(times_a):
        improvement = (statistics.mean(times_a) - statistics.mean(times_b)) / statistics.mean(times_a) * 100
        print(f"\n  Same blocks found but {improvement:.0f}% faster with bitsQ lag-adjust")
        print(f"  RECOMMENDATION: marginal improvement, consider for future")
    else:
        print(f"\n  No significant improvement from bitsQ lag-adjust")
        print(f"  RECOMMENDATION: not worth the consensus complexity")


if __name__ == "__main__":
    main()

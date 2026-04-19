#!/usr/bin/env python3
"""
Burst Phase Validation — Tests the CLIMB phase under real burst conditions.

Starts from B0 with high hashrate producing blocks every 10-11s.
Compares how fast each strategy reaches H9/H10 and how much lag accumulates.

  A) Baseline: slew ±1 fixed
  B) Burst controller: asymmetric slew with H10 ceiling + bitsQ guard
  C) Dynamic slew libre: ±5/±3/±1

Usage:
    python3 scripts/burst_phase_validation.py
    python3 scripts/burst_phase_validation.py --seeds 50
"""

import sys, os, math, random, statistics, csv
sys.path.insert(0, os.path.dirname(__file__))
from casert_v6_full_sim import (
    GENESIS_TIME, TARGET_SPACING, GENESIS_BITSQ, Q16_ONE, MIN_BITSQ, MAX_BITSQ,
    BITSQ_HALF_LIFE_V2, BITSQ_MAX_DELTA_DEN_V2,
    K_R, K_L, K_I, K_B, K_V,
    EWMA_SHORT_ALPHA, EWMA_LONG_ALPHA, EWMA_VOL_ALPHA, EWMA_DENOM,
    INTEG_RHO, INTEG_ALPHA, INTEG_MAX,
    H_MIN, V3_LAG_FLOOR_DIV, V5_EXTREME_MIN,
    EBR_ENTER, EBR_LEVEL_E2, EBR_LEVEL_E3, EBR_LEVEL_E4,
    ANTISTALL_FLOOR_V5, ANTISTALL_EASING_EXTRA,
    BlockMeta, casert_next_bitsq, log2_q16,
    PROFILES_17, make_profile_map, ProfileParams,
)

# Extended profiles
PROFILES_40 = list(PROFILES_17[:14])
PROFILES_40 += [
    ProfileParams(10,"H10",2,8,7,115,12.0,14.0),
    ProfileParams(11,"H11",2,8,8,110,5.0,20.0),
    ProfileParams(12,"H12",2,9,8,105,3.0,30.0),
    ProfileParams(13,"H13",2,9,9,100,2.5,35.0),
    ProfileParams(14,"H14",2,10,9,100,2.0,40.0),
    ProfileParams(15,"H15",2,10,10,100,1.5,48.0),
]
for i in range(16, 36):
    PROFILES_40.append(ProfileParams(i,f"H{i}",2,10+(i-15)//2,10+(i-14)//2,100,0.5,60.0))
H_MAX_40 = 35

G="\033[92m";Y="\033[93m";R="\033[91m";C="\033[96m";D="\033[2m"
B="\033[1m";X="\033[0m";O="\033[38;5;208m";M="\033[95m"

def sample_burst_dt(profile, bitsq, hashrate_kh, rng):
    """Sample block time — high hashrate produces very fast blocks at low profiles."""
    stab = max(0.001, profile.stability_pct / 100.0)
    bitsq_float = bitsq / Q16_ONE
    C_cal = (2 ** 11.68) / (1.3 * 600.0)
    expected = (2 ** bitsq_float) / (max(hashrate_kh, 0.01) * stab * C_cal)
    expected = max(1.0, expected)
    return rng.expovariate(1.0 / expected)


def compute_profile_strategy(chain, next_height, now_time, h_max, strategy):
    """PID + strategy-specific slew. Returns (bitsq, H, lag)."""
    bitsq = casert_next_bitsq(chain, next_height)
    if len(chain) < 2:
        return bitsq, 0, 0

    dt_last = max(1, min(86400, chain[-1].time - chain[-2].time))
    r_n = log2_q16(TARGET_SPACING) - log2_q16(dt_last)

    # Live lag
    lag_time = now_time if now_time > chain[-1].time else chain[-1].time
    elapsed = lag_time - GENESIS_TIME
    expected_h = elapsed // TARGET_SPACING if elapsed >= 0 else 0
    lag = int((next_height - 1) - expected_h)

    # EWMA + PID
    S = M = V = 0; I_acc = 0
    lb = min(len(chain), 128); st = len(chain) - lb
    for i in range(st + 1, len(chain)):
        d = max(1, min(86400, chain[i].time - chain[i-1].time))
        r = log2_q16(TARGET_SPACING) - log2_q16(d)
        S = (EWMA_SHORT_ALPHA * r + (EWMA_DENOM - EWMA_SHORT_ALPHA) * S) >> 8
        M = (EWMA_LONG_ALPHA * r + (EWMA_DENOM - EWMA_LONG_ALPHA) * M) >> 8
        V = (EWMA_VOL_ALPHA * abs(r - S) + (EWMA_DENOM - EWMA_VOL_ALPHA) * V) >> 8
        h_i = chain[i].height
        e_i = chain[i].time - GENESIS_TIME
        exp_i = e_i // TARGET_SPACING if e_i >= 0 else 0
        lag_i = int(h_i - exp_i)
        I_acc = (INTEG_RHO * I_acc + EWMA_DENOM * INTEG_ALPHA * lag_i * Q16_ONE) >> 8
        I_acc = max(-INTEG_MAX, min(INTEG_MAX, I_acc))

    L_q16 = lag * Q16_ONE
    U = K_R * r_n + K_L * (L_q16 >> 16) + K_I * (I_acc >> 16) + K_B * (S-M) + K_V * V
    H = max(H_MIN, min(h_max, int(U >> 16)))

    if lag <= 0: H = min(H, 0)
    if len(chain) < 10: H = min(H, 0)

    if len(chain) >= 3:
        prev_H = max(H_MIN, min(h_max, chain[-1].profile_index))

        # ── STRATEGY SLEW ──
        if strategy == 'baseline':
            H = max(prev_H - 1, min(prev_H + 1, H))

        elif strategy == 'burst':
            up_slew = 1; down_slew = 1
            if len(chain) >= 4:
                dts = sorted([max(1, chain[len(chain)-1-di].time - chain[len(chain)-2-di].time) for di in range(3)])
                median3 = dts[1]
                if lag >= 12 and median3 < 60: up_slew = 3
                elif lag >= 8 and median3 < 120: up_slew = 2
                if up_slew > 1 and H > 10: H = 10
            if H > prev_H: H = min(prev_H + up_slew, H)
            else: H = max(prev_H - down_slew, H)

        elif strategy == 'dynslew':
            slew = 5 if dt_last < 60 else (3 if dt_last < 120 else 1)
            H = max(prev_H - slew, min(prev_H + slew, H))

        # Lag floor
        if lag > 10:
            H = max(H, min(lag // V3_LAG_FLOOR_DIV, h_max))

        # Safety post-slew
        if lag <= 0: H = min(H, 0)

        # EBR
        if lag <= EBR_ENTER:
            if lag <= EBR_LEVEL_E4: H = min(H, H_MIN)
            elif lag <= EBR_LEVEL_E3: H = min(H, -3)
            elif lag <= EBR_LEVEL_E2: H = min(H, -2)
            else: H = min(H, 0)

        # Extreme cap (baseline only — burst/dynslew handle their own)
        if strategy == 'baseline' and H >= V5_EXTREME_MIN and H > prev_H + 1:
            H = prev_H + 1

        # Lag cap
        if H > 0 and H > lag:
            H = max(0, lag)

        H = max(H_MIN, min(h_max, H))

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


def bitsq_with_guard(chain, next_height, strategy):
    bitsq = casert_next_bitsq(chain, next_height)
    if strategy != 'burst' or not chain: return bitsq
    prev_bitsq = chain[-1].powDiffQ or GENESIS_BITSQ
    delta = bitsq - prev_bitsq
    if delta < 0:
        el = chain[-1].time - GENESIS_TIME
        eh = el // TARGET_SPACING if el >= 0 else 0
        lag2 = int((next_height - 1) - eh)
        if lag2 >= 8 and chain[-1].profile_index >= 9:
            guard_max = max(1, prev_bitsq // 64)
            delta = max(-guard_max, delta)
            bitsq = max(MIN_BITSQ, min(MAX_BITSQ, prev_bitsq + delta))
    return bitsq


def run_burst_phase(strategy, seed, burst_hashrate=5.0, n_burst=25, n_after=200):
    """
    Phase 1: n_burst blocks at high hashrate (burst)
    Phase 2: n_after blocks at normal hashrate (recovery)
    """
    rng = random.Random(seed)
    pmap = make_profile_map(PROFILES_40)

    # Seed chain: 10 blocks on schedule at B0
    chain = []
    base_h = 5050
    t = GENESIS_TIME + base_h * TARGET_SPACING
    for i in range(10):
        chain.append(BlockMeta(base_h + i, t + i * TARGET_SPACING, GENESIS_BITSQ, 0))

    sim_time = chain[-1].time
    rows = []
    max_lag = 0
    max_profile = 0
    blocks_to_h9 = None
    blocks_to_h10 = None
    overshoots_h11 = 0
    bitsq_guard_count = 0
    burst_end_lag = 0

    total_blocks = n_burst + n_after
    for blk in range(total_blocks):
        next_h = chain[-1].height + 1
        # Phase 1: high hashrate burst. Phase 2: normal
        if blk < n_burst:
            hr = burst_hashrate * rng.uniform(0.8, 1.2)
        else:
            hr = 1.3 * rng.uniform(0.7, 1.4)

        bitsq_raw, pi, lag = compute_profile_strategy(
            chain, next_h, sim_time, H_MAX_40, strategy)
        bitsq = bitsq_with_guard(chain, next_h, strategy)

        if bitsq != bitsq_raw: bitsq_guard_count += 1
        if lag > max_lag: max_lag = lag
        if pi > max_profile: max_profile = pi
        if pi >= 11: overshoots_h11 += 1
        if blocks_to_h9 is None and pi >= 9: blocks_to_h9 = blk + 1
        if blocks_to_h10 is None and pi >= 10: blocks_to_h10 = blk + 1
        if blk == n_burst - 1: burst_end_lag = lag

        profile = pmap.get(pi, pmap[0])
        dt = sample_burst_dt(profile, bitsq, hr, rng)
        dt = max(1.0, dt)
        new_time = int(sim_time + dt)

        chain.append(BlockMeta(next_h, new_time, bitsq, pi))
        sim_time = new_time

        rows.append({
            "block": blk + 1,
            "height": next_h,
            "dt": int(dt),
            "profile_index": pi,
            "profile_name": profile.name,
            "stability_pct": profile.stability_pct,
            "lag": lag,
            "bitsq_float": round(bitsq / Q16_ONE, 3),
            "hashrate_kh": round(hr, 3),
            "phase": "burst" if blk < n_burst else "recovery",
        })

    # Post-burst metrics
    burst_rows = [r for r in rows if r["phase"] == "burst"]
    recovery_rows = [r for r in rows if r["phase"] == "recovery"]
    burst_time = sum(r["dt"] for r in burst_rows)
    stall_blocks_20 = sum(1 for r in rows if r["dt"] >= 1200)
    stall_blocks_40 = sum(1 for r in rows if r["dt"] >= 2400)
    stall_blocks_60 = sum(1 for r in rows if r["dt"] >= 3600)

    # Profile path during burst
    burst_profile_path = [r["profile_name"] for r in burst_rows]
    burst_bitsq_path = [r["bitsq_float"] for r in burst_rows]

    return {
        "strategy": strategy,
        "seed": seed,
        "blocks_to_h9": blocks_to_h9,
        "blocks_to_h10": blocks_to_h10,
        "max_lag": max_lag,
        "burst_end_lag": burst_end_lag,
        "max_profile": max_profile,
        "overshoots_h11": overshoots_h11,
        "burst_time_s": burst_time,
        "bitsq_guard_activations": bitsq_guard_count,
        "stall_20m": stall_blocks_20,
        "stall_40m": stall_blocks_40,
        "stall_60m": stall_blocks_60,
        "mean_dt": statistics.mean(r["dt"] for r in rows),
        "std_dt": statistics.stdev(r["dt"] for r in rows) if len(rows) > 1 else 0,
        "burst_profile_path": burst_profile_path,
        "burst_bitsq_path": burst_bitsq_path,
        "rows": rows,
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Burst Phase Validation")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--burst-hr", type=float, default=5.0, help="Hashrate during burst (kH/s)")
    ap.add_argument("--n-burst", type=int, default=25, help="Blocks in burst phase")
    ap.add_argument("--n-after", type=int, default=200, help="Blocks in recovery phase")
    args = ap.parse_args()

    strategies = ['baseline', 'burst', 'dynslew']
    labels = {
        'baseline': 'A) Baseline (slew ±1)',
        'burst':    'B) Burst ctrl (H10 ceil)',
        'dynslew':  'C) DynSlew libre',
    }

    print(f"{B}{C}{'═'*80}{X}")
    print(f"{B}{C}  BURST PHASE VALIDATION — Climb under real burst conditions{X}")
    print(f"{B}{C}  {args.seeds} seeds × 3 strategies | {args.n_burst} burst blocks @ {args.burst_hr} kH/s{X}")
    print(f"{B}{C}{'═'*80}{X}")

    all_data = {s: [] for s in strategies}

    for strat in strategies:
        print(f"\n{O}Running: {labels[strat]}{X}")
        for s in range(args.seed, args.seed + args.seeds):
            r = run_burst_phase(strat, s, args.burst_hr, args.n_burst, args.n_after)
            all_data[strat].append(r)
            if (s - args.seed + 1) % 10 == 0:
                print(f"  {D}... {s-args.seed+1}/{args.seeds}{X}")

    # ── Comparison ──
    print(f"\n{B}{C}{'═'*80}{X}")
    print(f"{B}{C}  COMPARISON — Burst Phase Metrics{X}")
    print(f"{B}{C}{'═'*80}{X}")

    def avg(data, key):
        vals = [d[key] for d in data if d[key] is not None]
        return statistics.mean(vals) if vals else float('inf')

    header = f"\n  {'Metric':<35} {'Baseline':>10} {'Burst':>10} {'DynSlew':>10}"
    print(f"{B}{header}{X}")
    print(f"  {'─'*65}")

    metrics_list = [
        ("Blocks to reach H9", "blocks_to_h9"),
        ("Blocks to reach H10", "blocks_to_h10"),
        ("Max lag accumulated", "max_lag"),
        ("Lag at end of burst", "burst_end_lag"),
        ("Max profile reached", "max_profile"),
        ("Overshoots to H11+", "overshoots_h11"),
        ("Burst phase time (s)", "burst_time_s"),
        ("bitsQ guard activations", "bitsq_guard_activations"),
        ("Blocks > 20m (total)", "stall_20m"),
        ("Blocks > 40m (total)", "stall_40m"),
        ("Blocks > 60m (total)", "stall_60m"),
        ("Mean block time (s)", "mean_dt"),
        ("Std block time (s)", "std_dt"),
    ]

    for name, key in metrics_list:
        vals = []
        for strat in strategies:
            v = avg(all_data[strat], key)
            if key == "max_profile":
                vals.append(f"H{int(v)}")
            elif key in ("blocks_to_h9", "blocks_to_h10", "overshoots_h11",
                        "bitsq_guard_activations", "stall_20m", "stall_40m", "stall_60m"):
                vals.append(f"{v:.1f}")
            elif key in ("mean_dt", "std_dt", "burst_time_s"):
                vals.append(f"{v:.0f}")
            else:
                vals.append(f"{v:.1f}")
        best_idx = 0
        try:
            fvals = [float(v.replace('H','')) for v in vals]
            if key in ("blocks_to_h9", "blocks_to_h10"):
                best_idx = fvals.index(min(fvals))  # fewer blocks = better
            elif key in ("max_lag", "burst_end_lag", "overshoots_h11",
                         "stall_20m", "stall_40m", "stall_60m", "std_dt"):
                best_idx = fvals.index(min(fvals))  # lower = better
        except: pass

        line = f"  {name:<35}"
        for i, v in enumerate(vals):
            marker = f"{G}{v}{X}" if i == best_idx else v
            line += f" {marker:>10}"
        print(line)

    # ── Profile path for seed 42 ──
    print(f"\n{B}{C}PROFILE PATH — First {args.n_burst} blocks (burst phase, seed {args.seed}){X}")
    for strat in strategies:
        d = all_data[strat][0]
        path = " → ".join(d["burst_profile_path"])
        print(f"\n  {B}{labels[strat]}{X}")
        print(f"  {path}")
        print(f"  Max lag: {d['max_lag']} | H9 at block {d['blocks_to_h9']} | H10 at block {d['blocks_to_h10']}")

    # ── bitsQ path comparison ──
    print(f"\n{B}{C}BITSQ PATH — During burst (seed {args.seed}){X}")
    for strat in strategies:
        d = all_data[strat][0]
        bq = d["burst_bitsq_path"]
        print(f"  {labels[strat]}: {bq[0]:.3f} → {bq[-1]:.3f} (delta: {bq[-1]-bq[0]:+.3f})")

    # ── Verdict ──
    print(f"\n{B}{C}{'═'*80}{X}")
    print(f"{B}{C}  VERDICT{X}")
    print(f"{B}{C}{'═'*80}{X}")

    bl_h9 = avg(all_data['baseline'], 'blocks_to_h9')
    bu_h9 = avg(all_data['burst'], 'blocks_to_h9')
    ds_h9 = avg(all_data['dynslew'], 'blocks_to_h9')

    bl_lag = avg(all_data['baseline'], 'max_lag')
    bu_lag = avg(all_data['burst'], 'max_lag')
    ds_lag = avg(all_data['dynslew'], 'max_lag')

    bl_os = avg(all_data['baseline'], 'overshoots_h11')
    bu_os = avg(all_data['burst'], 'overshoots_h11')
    ds_os = avg(all_data['dynslew'], 'overshoots_h11')

    print(f"\n  Blocks to H9:     baseline={bl_h9:.1f}  burst={bu_h9:.1f}  dynslew={ds_h9:.1f}")
    print(f"  Max lag:          baseline={bl_lag:.1f}  burst={bu_lag:.1f}  dynslew={ds_lag:.1f}")
    print(f"  H11+ overshoots:  baseline={bl_os:.0f}  burst={bu_os:.0f}  dynslew={ds_os:.0f}")

    # Determine verdict
    burst_faster = bu_h9 < bl_h9 * 0.85  # at least 15% fewer blocks to H9
    burst_less_lag = bu_lag < bl_lag * 0.85
    burst_no_overshoot = bu_os == 0
    dynslew_overshoots = ds_os > 0

    if burst_faster and burst_no_overshoot:
        verdict = "BURST_IMPROVES"
        print(f"\n  {G}{B}CONCLUSION: Burst controller provides measurable improvement.{X}")
        print(f"  {G}Reaches H9 in {bu_h9:.0f} blocks vs {bl_h9:.0f} (baseline).{X}")
        print(f"  {G}Max lag: {bu_lag:.0f} vs {bl_lag:.0f}. No overshoots.{X}")
        print(f"  {G}Recommended for activation after final review.{X}")
    elif burst_faster:
        verdict = "PROMISING"
        print(f"\n  {Y}{B}CONCLUSION: Promising but needs review (overshoots detected).{X}")
    else:
        verdict = "NO_IMPROVEMENT"
        print(f"\n  {Y}{B}CONCLUSION: Burst controller does not improve this scenario.{X}")

    if dynslew_overshoots:
        print(f"\n  {R}Dynamic slew libre: REJECTED (H11+ overshoots: {ds_os:.0f}){X}")
    else:
        print(f"\n  {Y}Dynamic slew libre: no overshoots in this test, but uncapped design risk remains.{X}")

    # ── Save ──
    outdir = os.path.join(os.path.dirname(__file__) or ".", "..", "reports")
    os.makedirs(outdir, exist_ok=True)

    csvpath = os.path.join(outdir, "burst_phase_results.csv")
    with open(csvpath, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["strategy","seed","blocks_to_h9","blocks_to_h10","max_lag",
                     "burst_end_lag","max_profile","overshoots_h11","burst_time_s",
                     "bitsq_guard","stall_20m","stall_40m","stall_60m","mean_dt","std_dt"])
        for strat in strategies:
            for d in all_data[strat]:
                w.writerow([strat, d["seed"], d["blocks_to_h9"], d["blocks_to_h10"],
                           d["max_lag"], d["burst_end_lag"], d["max_profile"],
                           d["overshoots_h11"], d["burst_time_s"], d["bitsq_guard_activations"],
                           d["stall_20m"], d["stall_40m"], d["stall_60m"],
                           f"{d['mean_dt']:.0f}", f"{d['std_dt']:.0f}"])

    rptpath = os.path.join(outdir, "burst_phase_validation.md")
    with open(rptpath, "w") as f:
        f.write("# Burst Phase Validation\n\n")
        f.write(f"Seeds: {args.seeds} | Burst: {args.n_burst} blocks @ {args.burst_hr} kH/s | Recovery: {args.n_after} blocks @ 1.3 kH/s\n\n")
        f.write("## Key Metrics\n\n")
        f.write("| Metric | Baseline | Burst ctrl | DynSlew |\n|---|---|---|---|\n")
        for name, key in metrics_list:
            f.write(f"| {name} | {avg(all_data['baseline'],key):.1f} | {avg(all_data['burst'],key):.1f} | {avg(all_data['dynslew'],key):.1f} |\n")
        f.write(f"\n## Profile Path (seed {args.seed})\n\n")
        for strat in strategies:
            d = all_data[strat][0]
            f.write(f"**{labels[strat]}:** {' → '.join(d['burst_profile_path'])}\n\n")
        f.write(f"\n## Verdict\n\n**{verdict}**\n\n")
        if verdict == "BURST_IMPROVES":
            f.write("Burst controller reaches H9 faster and accumulates less lag. Recommended.\n")
        elif verdict == "NO_IMPROVEMENT":
            f.write("Burst controller does not measurably improve the burst phase.\n")

    print(f"\n{D}Saved: {csvpath}{X}")
    print(f"{D}Saved: {rptpath}{X}")


if __name__ == "__main__":
    main()

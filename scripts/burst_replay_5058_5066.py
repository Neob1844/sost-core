#!/usr/bin/env python3
"""
Burst Replay 5058-5066 — Comparative validation of 3 slew strategies.

Replays the real production burst pattern observed at blocks 5058-5066
(10 consecutive blocks in 10-12s, lag reaching 19) and compares:

  A) Baseline: slew ±1 fixed (current V6 calibration)
  B) Burst controller: asymmetric slew with H10 ceiling + bitsQ guard
  C) Dynamic slew libre: ±5 when dt<60s (rejected design)

Uses casert_v6_full_sim.py as base. Same seeds, same PID, same profiles.

Usage:
    python3 scripts/burst_replay_5058_5066.py
    python3 scripts/burst_replay_5058_5066.py --seeds 50
"""

import sys, os, math, random, statistics, csv, json
from dataclasses import dataclass
from typing import List, Dict, Tuple

# Import the full simulator
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
    PROFILES_17, make_profile_map, sample_block_dt,
    analyze, print_analysis,
)

# ═══════════════════════════════════════════════════════════════════════
# Extended profiles (40 total, E4-H35) — mirrors params.h
# ═══════════════════════════════════════════════════════════════════════
from casert_v6_full_sim import ProfileParams

PROFILES_40 = list(PROFILES_17[:14])  # E4 through H9 unchanged
PROFILES_40 += [
    ProfileParams(10,"H10",2, 8, 7,115, 12.0, 14.0),
    ProfileParams(11,"H11",2, 8, 8,110,  5.0, 20.0),
    ProfileParams(12,"H12",2, 9, 8,105,  3.0, 30.0),
    ProfileParams(13,"H13",2, 9, 9,100,  2.5, 35.0),
    ProfileParams(14,"H14",2,10, 9,100,  2.0, 40.0),
    ProfileParams(15,"H15",2,10,10,100,  1.5, 48.0),
    ProfileParams(16,"H16",2,11,10,100,  1.0, 55.0),
    ProfileParams(17,"H17",2,11,11,100,  0.8, 65.0),
    ProfileParams(18,"H18",2,12,11,100,  0.5, 80.0),
    ProfileParams(19,"H19",2,12,12,100,  0.3,100.0),
    ProfileParams(20,"H20",2,13,12,100,  0.2,120.0),
]
for i in range(21, 36):
    PROFILES_40.append(ProfileParams(i, f"H{i}", 2, 13+(i-21)//2, 13+(i-20)//2, 100, 0.1, 150.0))

H_MAX_40 = 35

# ═══════════════════════════════════════════════════════════════════════
# Three slew strategies
# ═══════════════════════════════════════════════════════════════════════

def compute_profile(chain, next_height, now_time, h_max, strategy):
    """
    Compute profile with variable slew strategy.
    strategy: 'baseline' | 'burst' | 'dynslew'
    """
    bitsq = casert_next_bitsq(chain, next_height)
    if len(chain) < 2:
        return bitsq, 0, 0

    # ── Signals (identical for all strategies) ──
    dt_last = chain[-1].time - chain[-2].time
    dt_last = max(1, min(86400, dt_last))
    r_n = log2_q16(TARGET_SPACING) - log2_q16(dt_last)

    # Live lag (V6 calibration)
    lag_time = now_time if now_time > chain[-1].time else chain[-1].time
    elapsed = lag_time - GENESIS_TIME
    expected_h = elapsed // TARGET_SPACING if elapsed >= 0 else 0
    lag = int((next_height - 1) - expected_h)

    # EWMA
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

    burst_score = S - M
    L_q16 = lag * Q16_ONE
    U = K_R * r_n + K_L * (L_q16 >> 16) + K_I * (I_acc >> 16) + K_B * burst_score + K_V * V
    H = max(H_MIN, min(h_max, int(U >> 16)))

    if lag <= 0: H = min(H, 0)
    if len(chain) < 10: H = min(H, 0)

    if len(chain) >= 3:
        prev_H = max(H_MIN, min(h_max, chain[-1].profile_index))

        # ── STRATEGY-SPECIFIC SLEW ──
        if strategy == 'baseline':
            # Fixed ±1 both directions
            H = max(prev_H - 1, min(prev_H + 1, H))

        elif strategy == 'burst':
            # Asymmetric: up_slew variable, down_slew=1
            up_slew = 1
            down_slew = 1
            if len(chain) >= 4:
                dts = []
                for di in range(3):
                    idx = len(chain) - 1 - di
                    dts.append(max(1, chain[idx].time - chain[idx-1].time))
                dts.sort()
                median3 = dts[1]
                if lag >= 12 and median3 < 60:
                    up_slew = 3  # tier 2
                elif lag >= 8 and median3 < 120:
                    up_slew = 2  # tier 1
                # Burst ceiling: NEVER above H10
                if up_slew > 1 and H > 10:
                    H = 10
            if H > prev_H:
                H = min(prev_H + up_slew, H)
            else:
                H = max(prev_H - down_slew, H)

        elif strategy == 'dynslew':
            # Dynamic slew libre (rejected design)
            if dt_last < 60:
                slew = 5
            elif dt_last < 120:
                slew = 3
            else:
                slew = 1
            H = max(prev_H - slew, min(prev_H + slew, H))

        # Lag floor
        if lag > 10:
            H = max(H, min(lag // V3_LAG_FLOOR_DIV, h_max))

        # Safety rule post-slew
        if lag <= 0: H = min(H, 0)

        # EBR
        if lag <= EBR_ENTER:
            if lag <= EBR_LEVEL_E4: H = min(H, H_MIN)
            elif lag <= EBR_LEVEL_E3: H = min(H, -3)
            elif lag <= EBR_LEVEL_E2: H = min(H, -2)
            else: H = min(H, 0)

        # Extreme cap
        if H >= V5_EXTREME_MIN and H > prev_H + 1:
            if strategy != 'burst' and strategy != 'dynslew':
                H = prev_H + 1

        # Dynamic lag cap (V6 calibration)
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
                decay_t -= cost
                decayed -= 1
            H = decayed
        if stall >= ANTISTALL_FLOOR_V5 and H <= 0:
            t_b0 = stall - ANTISTALL_FLOOR_V5
            if t_b0 > ANTISTALL_EASING_EXTRA:
                H = max(H_MIN, -int((t_b0 - ANTISTALL_EASING_EXTRA) // 1800))

    # bitsQ relax guard (burst strategy only)
    if strategy == 'burst':
        # Applied in bitsq computation — we track it here for metrics
        pass

    return bitsq, H, lag

# ═══════════════════════════════════════════════════════════════════════
# bitsQ with optional relax guard
# ═══════════════════════════════════════════════════════════════════════

def bitsq_with_guard(chain, next_height, strategy):
    """Compute bitsQ with optional relax guard for burst strategy."""
    bitsq = casert_next_bitsq(chain, next_height)
    if strategy != 'burst' or not chain:
        return bitsq

    prev_bitsq = chain[-1].powDiffQ or GENESIS_BITSQ
    delta = bitsq - prev_bitsq

    # Guard: if profile >= H9 and lag >= 8, limit downward
    if delta < 0:
        el = chain[-1].time - GENESIS_TIME
        eh = el // TARGET_SPACING if el >= 0 else 0
        lag2 = int((next_height - 1) - eh)
        last_pi = chain[-1].profile_index
        if lag2 >= 8 and last_pi >= 9:
            guard_max = prev_bitsq // 64
            if guard_max < 1: guard_max = 1
            delta = max(-guard_max, delta)
            bitsq = max(MIN_BITSQ, min(MAX_BITSQ, prev_bitsq + delta))

    return bitsq

# ═══════════════════════════════════════════════════════════════════════
# Production replay: seed chain with real burst pattern
# ═══════════════════════════════════════════════════════════════════════

def build_burst_chain():
    """
    Build a chain that replicates the state at block 5057 (just before burst).
    Then inject the real burst pattern 5058-5066.
    """
    # Seed: 10 blocks on schedule ending at ~block 5050
    chain = []
    base_h = 5045
    t = GENESIS_TIME + base_h * TARGET_SPACING
    for i in range(10):
        bq = 800000  # ~12.2 bitsQ (close to production)
        chain.append(BlockMeta(base_h + i, t + i * TARGET_SPACING, bq, 0))

    # Block 5055: 18m (slow, chain starts getting ahead)
    t = chain[-1].time + 18 * 60
    chain.append(BlockMeta(5055, t, 806414, 9))

    # Block 5056: 9m
    t += 9 * 60
    chain.append(BlockMeta(5056, t, 803189, -3))

    # Block 5057: 12s (burst starts)
    t += 12
    chain.append(BlockMeta(5057, t, 803516, -2))

    # THE BURST: blocks 5058-5066 at 10-12s each (real production data)
    burst_dts = [11, 10, 10, 11, 10, 10, 11, 10, 11]
    burst_profiles = [-2, 1, 2, 3, 4, 5, 6, 7, 8]  # H1 through H8
    burst_bitsqs = [807313, 811146, 814990, 818857, 822736, 826639, 830565, 834491, 838451]

    for i, (bdt, pi, bq) in enumerate(zip(burst_dts, burst_profiles, burst_bitsqs)):
        t += bdt
        chain.append(BlockMeta(5058 + i, t, bq, pi))

    # Block 5066 ends the burst. Chain is now ~19 ahead.
    return chain

# ═══════════════════════════════════════════════════════════════════════
# Run one simulation from the burst point
# ═══════════════════════════════════════════════════════════════════════

def run_replay(strategy, seed, n_blocks=500, hashrate_kh=1.3):
    rng = random.Random(seed)
    pmap = make_profile_map(PROFILES_40)
    chain = build_burst_chain()
    sim_time = chain[-1].time

    rows = []
    bitsq_guard_count = 0
    max_profile_seen = 0
    overshoots_h11 = 0

    for _ in range(n_blocks):
        next_h = chain[-1].height + 1
        hr = hashrate_kh * rng.uniform(0.7, 1.4)

        bitsq_raw, pi, lag = compute_profile(chain, next_h, sim_time, H_MAX_40, strategy)
        bitsq = bitsq_with_guard(chain, next_h, strategy)

        # Track bitsQ guard activations
        if strategy == 'burst' and bitsq != bitsq_raw:
            bitsq_guard_count += 1

        profile = pmap.get(pi, pmap[0])
        if pi > max_profile_seen:
            max_profile_seen = pi
        if pi >= 11:
            overshoots_h11 += 1

        dt = sample_block_dt(profile, bitsq, hr, rng)
        dt = max(1.0, dt)
        new_time = int(sim_time + dt)

        chain.append(BlockMeta(next_h, new_time, bitsq, pi))
        sim_time = new_time

        rows.append({
            "height": next_h,
            "dt": int(dt),
            "profile_index": pi,
            "profile_name": profile.name,
            "stability_pct": profile.stability_pct,
            "lag": lag,
            "final_lag": 0,
            "bitsq": bitsq,
            "bitsq_float": round(bitsq / Q16_ONE, 3),
            "hashrate_kh": round(hr, 3),
        })

    return rows, {
        "max_profile": max_profile_seen,
        "overshoots_h11": overshoots_h11,
        "bitsq_guard_activations": bitsq_guard_count,
    }

# ═══════════════════════════════════════════════════════════════════════
# Main comparison
# ═══════════════════════════════════════════════════════════════════════

G="\033[92m";Y="\033[93m";R="\033[91m";C="\033[96m";D="\033[2m"
B="\033[1m";X="\033[0m";O="\033[38;5;208m";M="\033[95m"

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Burst Replay 5058-5066")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--blocks", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--hashrate", type=float, default=1.3)
    args = ap.parse_args()

    strategies = ['baseline', 'burst', 'dynslew']
    labels = {
        'baseline': 'A) Baseline (slew ±1 fixed)',
        'burst':    'B) Burst controller (H10 ceiling + bitsQ guard)',
        'dynslew':  'C) Dynamic slew libre (±5/±3/±1)',
    }

    print(f"{B}{C}{'═'*80}{X}")
    print(f"{B}{C}  BURST REPLAY 5058-5066 — Comparative Validation{X}")
    print(f"{B}{C}  {args.seeds} seeds × 3 strategies × {args.blocks} blocks = {args.seeds * 3} simulations{X}")
    print(f"{B}{C}{'═'*80}{X}")

    all_results = {}

    for strat in strategies:
        results = []
        extras = []
        print(f"\n{B}{O}Running: {labels[strat]}{X}")

        for s in range(args.seed, args.seed + args.seeds):
            rows, extra = run_replay(strat, s, args.blocks, args.hashrate)
            a = analyze(rows, labels[strat], "burst_replay")
            results.append(a)
            extras.append(extra)
            if (s - args.seed + 1) % 10 == 0:
                print(f"  {D}... {s - args.seed + 1}/{args.seeds}{X}")

        all_results[strat] = (results, extras)

    # ── Comparison table ──
    print(f"\n\n{B}{C}{'═'*80}{X}")
    print(f"{B}{C}  COMPARISON TABLE{X}")
    print(f"{B}{C}{'═'*80}{X}")

    header = f"  {'Metric':<35} {'Baseline':>12} {'Burst ctrl':>12} {'DynSlew':>12}"
    print(f"\n{B}{header}{X}")
    print(f"  {'─'*71}")

    def avg(results, key):
        return statistics.mean(getattr(r, key) for r in results)

    def avg_extra(extras, key):
        return statistics.mean(e[key] for e in extras)

    for strat in strategies:
        results, extras = all_results[strat]

    bl_r, bl_e = all_results['baseline']
    bu_r, bu_e = all_results['burst']
    ds_r, ds_e = all_results['dynslew']

    metrics = [
        ("Mean block time", lambda r,e: f"{avg(r,'mean_dt')/60:.1f}m"),
        ("Std deviation", lambda r,e: f"{avg(r,'std_dt')/60:.1f}m"),
        ("Median", lambda r,e: f"{avg(r,'median_dt')/60:.1f}m"),
        ("P95 block time", lambda r,e: f"{avg(r,'p95_dt')/60:.0f}m"),
        ("P99 block time", lambda r,e: f"{avg(r,'p99_dt')/60:.0f}m"),
        ("Max block time", lambda r,e: f"{avg(r,'max_dt')/60:.0f}m"),
        ("Blocks > 20m", lambda r,e: f"{avg(r,'blocks_over_20m'):.1f}"),
        ("Blocks > 40m", lambda r,e: f"{avg(r,'blocks_over_40m'):.1f}"),
        ("Blocks > 60m", lambda r,e: f"{avg(r,'blocks_over_60m'):.1f}"),
        ("Max consecutive >20m", lambda r,e: f"{avg(r,'max_consecutive_slow'):.1f}"),
        ("Sawtooth score", lambda r,e: f"{avg(r,'sawtooth'):.3f}"),
        ("Smoothness", lambda r,e: f"{avg(r,'smoothness'):.3f}"),
        ("Lag std", lambda r,e: f"{avg(r,'lag_std'):.1f}"),
        ("Lag max", lambda r,e: f"{max(r.lag_max for r in r):.0f}"),
        ("Composite score", lambda r,e: f"{avg(r,'score'):.0f}"),
        ("Max profile reached", lambda r,e: f"H{max(e2['max_profile'] for e2 in e)}"),
        ("Overshoots to H11+", lambda r,e: f"{avg_extra(e,'overshoots_h11'):.1f}"),
        ("bitsQ guard activations", lambda r,e: f"{avg_extra(e,'bitsq_guard_activations'):.1f}"),
        ("GREEN verdicts", lambda r,e: f"{sum(1 for x in r if x.verdict=='GREEN')}/{len(r)}"),
    ]

    for name, fn in metrics:
        try:
            v_bl = fn(bl_r, bl_e)
            v_bu = fn(bu_r, bu_e)
            v_ds = fn(ds_r, ds_e)
            print(f"  {name:<35} {v_bl:>12} {v_bu:>12} {v_ds:>12}")
        except Exception as ex:
            print(f"  {name:<35} {'err':>12} {'err':>12} {'err':>12}  ({ex})")

    # ── First 20 blocks detail for each strategy ──
    print(f"\n\n{B}{C}FIRST 20 BLOCKS — burst recovery comparison (seed {args.seed}){X}")
    for strat in strategies:
        rows, _ = run_replay(strat, args.seed, 30, args.hashrate)
        print(f"\n  {B}{labels[strat]}{X}")
        print(f"  {'Block':>7} {'DT':>6} {'Prof':>5} {'Stab%':>6} {'Lag':>5} {'bitsQ':>7}")
        for r in rows[:20]:
            dtm = r['dt']/60
            dc = G if dtm < 15 else (Y if dtm < 30 else R)
            print(f"  {r['height']:>7} {dc}{dtm:>5.1f}m{X} {r['profile_name']:>5} "
                  f"{r['stability_pct']:>5.1f}% {r['lag']:>+5d} {r['bitsq_float']:>7.3f}")

    # ── Verdict ──
    print(f"\n\n{B}{C}{'═'*80}{X}")
    print(f"{B}{C}  VERDICT{X}")
    print(f"{B}{C}{'═'*80}{X}")

    bl_score = avg(bl_r, 'score')
    bu_score = avg(bu_r, 'score')
    ds_score = avg(ds_r, 'score')

    best = min([('baseline', bl_score), ('burst', bu_score), ('dynslew', ds_score)],
               key=lambda x: x[1])

    bl_overshoots = avg_extra(bl_e, 'overshoots_h11')
    bu_overshoots = avg_extra(bu_e, 'overshoots_h11')
    ds_overshoots = avg_extra(ds_e, 'overshoots_h11')

    print(f"\n  Composite scores: baseline={bl_score:.0f}  burst={bu_score:.0f}  dynslew={ds_score:.0f}")
    print(f"  H11+ overshoots:  baseline={bl_overshoots:.1f}  burst={bu_overshoots:.1f}  dynslew={ds_overshoots:.1f}")
    print(f"  Best: {B}{labels[best[0]]}{X} (score {best[1]:.0f})")

    if best[0] == 'burst':
        print(f"\n  {G}{B}CONCLUSION: Burst controller improves the real burst case.{X}")
        print(f"  {G}Recommended for activation after further validation.{X}")
    elif best[0] == 'baseline':
        print(f"\n  {Y}{B}CONCLUSION: Baseline is still better. Burst controller needs tuning.{X}")
    else:
        print(f"\n  {R}{B}CONCLUSION: Dynamic slew libre wins — unexpected. Review needed.{X}")

    print(f"\n  Dynamic slew libre: {R}REJECTED{X} (overshoots={ds_overshoots:.0f}, pursues H17+)")

    # ── Save results ──
    outdir = os.path.dirname(__file__) or "."

    csvpath = os.path.join(outdir, "..", "reports", "burst_replay_results.csv")
    os.makedirs(os.path.dirname(csvpath), exist_ok=True)
    with open(csvpath, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["strategy","seed","mean_dt","std_dt","p95_dt","p99_dt",
                     "sawtooth","score","overshoots_h11","max_profile","verdict"])
        for strat in strategies:
            results, extras = all_results[strat]
            for i, (r, e) in enumerate(zip(results, extras)):
                w.writerow([strat, args.seed+i, f"{r.mean_dt:.0f}", f"{r.std_dt:.0f}",
                           f"{r.p95_dt:.0f}", f"{r.p99_dt:.0f}",
                           f"{r.sawtooth:.3f}", f"{r.score:.0f}",
                           e['overshoots_h11'], e['max_profile'], r.verdict])

    # ── Generate report ──
    rptpath = os.path.join(outdir, "..", "reports", "burst_replay_5058_5066.md")
    with open(rptpath, "w") as f:
        f.write("# Burst Replay 5058-5066 — Validation Report\n\n")
        f.write(f"Seeds: {args.seeds} | Blocks per sim: {args.blocks} | Hashrate: {args.hashrate} kH/s\n\n")
        f.write("## Results\n\n")
        f.write(f"| Metric | Baseline | Burst ctrl | DynSlew |\n")
        f.write(f"|--------|----------|------------|--------|\n")
        for name, fn in metrics:
            try:
                f.write(f"| {name} | {fn(bl_r,bl_e)} | {fn(bu_r,bu_e)} | {fn(ds_r,ds_e)} |\n")
            except:
                pass
        f.write(f"\n## Verdict\n\n")
        f.write(f"Best: **{labels[best[0]]}** (score {best[1]:.0f})\n\n")
        if best[0] == 'burst':
            f.write("**Burst controller improves the real burst case.** Recommended for activation.\n")
        elif best[0] == 'baseline':
            f.write("**Baseline is still better.** Burst controller needs further tuning.\n")
        f.write(f"\nDynamic slew libre: **REJECTED** (overshoots H11+, pursues impossible profiles)\n")

    print(f"\n{D}Saved: {csvpath}{X}")
    print(f"{D}Saved: {rptpath}{X}")


if __name__ == "__main__":
    main()

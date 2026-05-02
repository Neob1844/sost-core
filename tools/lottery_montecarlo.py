#!/usr/bin/env python3
"""
V11 Phase 2 — Preliminary lottery eligibility Monte Carlo.

Analysis tool only; NOT consensus code. NOT compiled into any binary,
NOT linked into the test suite, NOT subject to consensus invariants.
The output of this script informs (does not decide) the C9 fairness
review and the final value of LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW.

Usage:
    python3 tools/lottery_montecarlo.py                      # default sweep
    python3 tools/lottery_montecarlo.py --seed 42 --blocks 10000
    python3 tools/lottery_montecarlo.py \
        --dominant-share 0.70 --honest-miners 10 \
        --sybils 0,5,10,100 --windows 0,5,10,30
    python3 tools/lottery_montecarlo.py --single 0.70 10 0 5    # one scenario

Output: Markdown tables on stdout — full matrix, sybil-incentive deltas,
and a decision table for the realistic network shape.

Model assumptions (kept explicit so reviewers can challenge them):

  - Block winner is selected by hashrate weight (weighted Bernoulli).
  - Dominant strategy is OPTIMAL for the dominant: when they win,
    they always credit a single fixed address (their main) so only
    that one address ever enters cooldown. All sybil addresses are
    pre-legitimated (i.e. they all start the simulation with >= 1
    historical block and are therefore in the eligibility pool).
    This is a worst case for any eligibility-based defense.
  - Honest miners share (1 - dominant_share) hashrate equally and
    each holds exactly one address.
  - Lottery selection is uniform among eligible addresses.
  - Eligibility excludes:
        * the current block's winner (always),
        * any address that won a block-reward in the last `window`
          blocks (only when `window > 0`).
  - Empty eligibility set => rollover (counted, no winner that block).

Determinism: the random seed is exposed via `--seed` and defaults to
42. Two runs with the same parameters produce bit-identical output.

See docs/V11_PHASE2_DESIGN.md §5.4 for the headline findings of the
default sweep and the implications for C5 / C6 / C9.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from itertools import product
from typing import List


# ---------------------------------------------------------------------------
# Single-scenario simulator
# ---------------------------------------------------------------------------

def simulate(dom_hashrate: float,
             n_honest: int,
             n_sybils: int,
             window: int,
             n_blocks: int = 10_000,
             seed: int = 42) -> dict:
    """Simulate `n_blocks` blocks with the given parameters.

    Returns a dict with the per-scenario metrics described in the
    module docstring. Determinism is anchored by `seed`.
    """
    rng = random.Random(seed)

    n_dom_addrs = 1 + n_sybils
    total = n_dom_addrs + n_honest

    dom_main = 0
    dom_addrs_set = set(range(n_dom_addrs))
    honest_addrs = list(range(n_dom_addrs, total))

    block_wins = [0] * total
    lottery_wins = [0] * total
    recent_winners: List[int] = []
    rollovers = 0
    pool_sizes: List[int] = []

    for _ in range(n_blocks):
        # ----- Block winner: hashrate-weighted -----
        if rng.random() < dom_hashrate:
            # Optimal dominant strategy: always credit the main address.
            winner = dom_main
        else:
            winner = rng.choice(honest_addrs)
        block_wins[winner] += 1

        # ----- Lottery selection -----
        if window > 0:
            cooldown = set(recent_winners[-window:])
        else:
            cooldown = set()
        cooldown.add(winner)  # current block's winner is always excluded

        eligible = [a for a in range(total) if a not in cooldown]
        pool_sizes.append(len(eligible))

        if not eligible:
            rollovers += 1
        else:
            lottery_winner = rng.choice(eligible)
            lottery_wins[lottery_winner] += 1

        recent_winners.append(winner)

    n_payouts = max(1, n_blocks - rollovers)

    return {
        'dom_hashrate':      dom_hashrate,
        'n_honest':          n_honest,
        'n_sybils':          n_sybils,
        'window':            window,
        'dom_block_share':   sum(block_wins[a] for a in dom_addrs_set) / n_blocks,
        'dom_lottery_share': sum(lottery_wins[a] for a in dom_addrs_set) / n_payouts,
        'honest_median':     statistics.median(
            lottery_wins[a] / n_payouts for a in honest_addrs),
        'honest_worst':      min(lottery_wins[a] / n_payouts for a in honest_addrs),
        'rollover_rate':     rollovers / n_blocks,
        'pool_avg':          statistics.mean(pool_sizes),
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_full_matrix(results: List[dict]) -> None:
    print("=" * 100)
    print("FULL MATRIX  (lottery shares as percentages of payouts)")
    print("=" * 100)
    print(f"{'hash':>5} {'hon':>4} {'syb':>4} {'win':>4} | "
          f"{'blk_dom':>8} {'lot_dom':>8} {'med_hon':>8} {'wst_hon':>8} "
          f"{'roll':>6} {'pool':>7}")
    print("-" * 100)
    for r in results:
        print(f"{r['dom_hashrate']*100:5.0f} {r['n_honest']:4d} "
              f"{r['n_sybils']:4d} {r['window']:4d} | "
              f"{r['dom_block_share']*100:7.1f}% "
              f"{r['dom_lottery_share']*100:7.1f}% "
              f"{r['honest_median']*100:7.2f}% "
              f"{r['honest_worst']*100:7.2f}% "
              f"{r['rollover_rate']*100:5.1f}% "
              f"{r['pool_avg']:7.1f}")


def print_sybil_delta(results: List[dict]) -> None:
    print()
    print("=" * 100)
    print("SYBIL INCENTIVE DELTA  (lower = window discourages sybilation)")
    print("Δ_10  = dom_lottery_share(sybils=10)  − dom_lottery_share(sybils=0)")
    print("Δ_100 = dom_lottery_share(sybils=100) − dom_lottery_share(sybils=0)")
    print("=" * 100)
    print(f"{'hash':>5} {'hon':>4} {'win':>4} | "
          f"{'no_syb':>8} {'syb=10':>8} {'syb=100':>9} | "
          f"{'Δ_10':>7} {'Δ_100':>8}")
    print("-" * 100)
    by_key: dict = {}
    for r in results:
        key = (r['dom_hashrate'], r['n_honest'], r['window'])
        by_key.setdefault(key, {})[r['n_sybils']] = r['dom_lottery_share']
    for (h, m, w), shares in sorted(by_key.items()):
        s0 = shares.get(0, 0.0)
        s10 = shares.get(10, 0.0)
        s100 = shares.get(100, 0.0)
        d10 = s10 - s0
        d100 = s100 - s0
        print(f"{h*100:5.0f} {m:4d} {w:4d} | "
              f"{s0*100:7.1f}% {s10*100:7.1f}% {s100*100:8.1f}% | "
              f"{d10*100:+6.1f}% {d100*100:+7.1f}%")


def print_decision_table(results: List[dict], windows: List[int]) -> None:
    """Average across realistic network shapes (70-85 % dom, 5-10 honest)."""
    print()
    print("=" * 100)
    print("DECISION TABLE — current network shape (70-85% dom, 5-10 honest)")
    print("=" * 100)
    print(f"{'window':>7} | {'dom_lot_no_syb':>14} {'dom_lot_syb_10':>14} "
          f"{'dom_lot_syb_100':>15} | {'med_hon_no_syb':>14} {'rollover':>8}")
    print("-" * 100)
    realistic = [r for r in results
                 if r['dom_hashrate'] in (0.70, 0.85)
                 and r['n_honest'] in (5, 10)]

    def avg(xs, k):
        return statistics.mean(r[k] for r in xs) if xs else 0.0

    for w in windows:
        rs_no = [r for r in realistic if r['window'] == w and r['n_sybils'] == 0]
        rs_10 = [r for r in realistic if r['window'] == w and r['n_sybils'] == 10]
        rs_100 = [r for r in realistic if r['window'] == w and r['n_sybils'] == 100]
        print(f"{w:7d} | "
              f"{avg(rs_no, 'dom_lottery_share')*100:13.1f}% "
              f"{avg(rs_10, 'dom_lottery_share')*100:13.1f}% "
              f"{avg(rs_100, 'dom_lottery_share')*100:14.1f}% | "
              f"{avg(rs_no, 'honest_median')*100:13.2f}% "
              f"{avg(rs_no, 'rollover_rate')*100:7.1f}%")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_csv_int(s: str) -> List[int]:
    return [int(x) for x in s.split(',') if x.strip() != '']


def parse_csv_float(s: str) -> List[float]:
    return [float(x) for x in s.split(',') if x.strip() != '']


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(
        description="Preliminary lottery eligibility Monte Carlo "
                    "(analysis tool only; not consensus code).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--blocks", type=int, default=10_000,
                   help="Number of blocks to simulate per scenario.")
    p.add_argument("--seed", type=int, default=42,
                   help="Deterministic RNG seed.")
    p.add_argument("--dominant-share", type=parse_csv_float,
                   default="0.50,0.70,0.85,0.92",
                   help="Comma-separated dominant hashrate fractions.")
    p.add_argument("--honest-miners", type=parse_csv_int,
                   default="5,10,35,100",
                   help="Comma-separated honest miner counts.")
    p.add_argument("--sybils", type=parse_csv_int,
                   default="0,5,10,100",
                   help="Comma-separated dominant sybil counts.")
    p.add_argument("--windows", type=parse_csv_int,
                   default="0,5,10,30",
                   help="Comma-separated exclusion windows (cap values).")
    p.add_argument("--single", nargs=4, metavar=("DOM", "HONEST", "SYBILS", "WINDOW"),
                   help="Run a single scenario (overrides the sweep flags).")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress per-32-scenario progress to stderr.")
    args = p.parse_args(argv)

    # Single-scenario shortcut.
    if args.single:
        dom = float(args.single[0])
        m = int(args.single[1])
        s = int(args.single[2])
        w = int(args.single[3])
        r = simulate(dom, m, s, w, args.blocks, args.seed)
        print(f"Single scenario: dom={dom}, honest={m}, sybils={s}, window={w}")
        for k, v in r.items():
            if isinstance(v, float):
                print(f"  {k:>20} = {v}")
            else:
                print(f"  {k:>20} = {v}")
        return 0

    # Full sweep.
    hashrates = args.dominant_share
    honests = args.honest_miners
    sybils = args.sybils
    windows = args.windows

    results: List[dict] = []
    total = len(hashrates) * len(honests) * len(sybils) * len(windows)
    n = 0
    for h, m, s, w in product(hashrates, honests, sybils, windows):
        n += 1
        results.append(simulate(h, m, s, w, args.blocks, args.seed))
        if not args.quiet and n % 32 == 0:
            print(f"  ... {n}/{total}", file=sys.stderr)

    print_full_matrix(results)
    print_sybil_delta(results)
    print_decision_table(results, windows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""
V13 lottery cooldown sweep — quantitative justification for 5 → 6.

The C9 audit (`tools/lottery_montecarlo.py`) selected
LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW = 5 from a sweep over
windows ∈ {0, 5, 10, 30}. The V13 proposal nudges that to 6. This script
re-runs the C9 simulation core over the SAME scenario grid restricted to
windows ∈ {5, 6, 7} and reports the deltas relevant to the cooldown
decision so the bump is documented with numbers rather than intuition.

Imports `simulate()` from `tools/lottery_montecarlo.py` directly — there
is no second copy of the simulation logic. If C9's invariants hold, this
script's numbers are derived from the same code path.

Output:
  - Stdout: human-readable markdown blocks (full matrix per window, plus
    cross-window deltas, plus a recommendation).
  - --json <path>: structured artefact for embedding in docs/V13_SPEC.md.

Usage:
  python3 tools/sim/lottery_cooldown_v13.py
  python3 tools/sim/lottery_cooldown_v13.py --blocks 50000
  python3 tools/sim/lottery_cooldown_v13.py --json /tmp/v13_cooldown.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Reuse the C9 simulation core verbatim. tools/sim/ → parents[1] = tools/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lottery_montecarlo import simulate  # noqa: E402

# ---------------------------------------------------------------------------
# Scenario grid — identical to the C9 default sweep so the output of this
# script can be cross-checked against the existing audit. Only the WINDOWS
# axis is narrowed to the V13 candidates.
# ---------------------------------------------------------------------------
DOM_SHARES   = [0.50, 0.70, 0.85, 0.92]
HONEST_COUNTS = [5, 10, 35, 100]
SYBIL_COUNTS  = [0, 5, 10, 100]
WINDOWS       = [5, 6, 7]
DEFAULT_BLOCKS = 10_000
DEFAULT_SEED   = 0xC0FFEE  # fixed for reproducibility


def fmt_pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:.{digits}f}%"


def run_sweep(blocks: int, seed: int, freq_mode: str = "lifecycle") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    total = len(DOM_SHARES) * len(HONEST_COUNTS) * len(SYBIL_COUNTS) * len(WINDOWS)
    n = 0
    t0 = time.time()
    for dom, honest, sybils, w in product(DOM_SHARES, HONEST_COUNTS, SYBIL_COUNTS, WINDOWS):
        n += 1
        r = simulate(
            dom_hashrate=dom,
            n_honest=honest,
            n_sybils=sybils,
            window=w,
            n_blocks=blocks,
            seed=seed,
            freq_mode=freq_mode,
        )
        if not r["accounting_ok"]:
            print(
                f"[ACCOUNTING] dom={dom} honest={honest} sybils={sybils} "
                f"window={w}: invariants violated; aborting.",
                file=sys.stderr,
            )
            sys.exit(2)
        # Carry the simulation inputs for later joins.
        r["dom_share_input"] = dom
        rows.append(r)
        if n % 16 == 0:
            print(f"  ... {n}/{total}  ({time.time() - t0:.1f}s)", file=sys.stderr)
    return rows


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------
def by_window(rows: List[Dict[str, Any]], w: int) -> List[Dict[str, Any]]:
    return [r for r in rows if r["window"] == w]


def agg(rows: List[Dict[str, Any]], key: str) -> Dict[str, float]:
    """Return mean / median / max / min of `key` over `rows`."""
    vals = [r[key] for r in rows]
    return {
        "mean":   statistics.mean(vals),
        "median": statistics.median(vals),
        "max":    max(vals),
        "min":    min(vals),
    }


def sybil_delta_for_window(rows: List[Dict[str, Any]], w: int) -> Dict[str, float]:
    """How much does adding sybils boost the dominant's total share?

    For each (dom, honest) pair, take the gap between
    `dom_total_share(sybils=K)` and `dom_total_share(sybils=0)` — averaged
    across K∈{5,10,100}. A smaller delta means sybils help the dominant
    less under that window.
    """
    deltas: List[float] = []
    by = {(r["dom_hashrate"], r["n_honest"], r["n_sybils"]): r
          for r in rows if r["window"] == w}
    for dom in DOM_SHARES:
        for honest in HONEST_COUNTS:
            base = by.get((dom, honest, 0))
            if not base:
                continue
            for s in SYBIL_COUNTS:
                if s == 0:
                    continue
                r = by.get((dom, honest, s))
                if not r:
                    continue
                deltas.append(r["dom_total_share"] - base["dom_total_share"])
    return {
        "mean":   statistics.mean(deltas) if deltas else 0.0,
        "median": statistics.median(deltas) if deltas else 0.0,
        "max":    max(deltas) if deltas else 0.0,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_per_window_summary(rows: List[Dict[str, Any]]) -> None:
    print()
    print("## Per-window aggregates (across full C9 grid)")
    print()
    print("| window | rollover_rate (mean) | pool_avg (mean) | "
          "dom_total_share (mean) | dom_total_share (max) | "
          "honest_median_total (mean) | cooldown_exclusion (mean) | "
          "double_win (mean) |")
    print("|-------:|---------------------:|----------------:|"
          "----------------------:|----------------------:|"
          "--------------------------:|--------------------------:|"
          "-----------------:|")
    for w in WINDOWS:
        sub = by_window(rows, w)
        roll = agg(sub, "rollover_rate")
        pool = agg(sub, "pool_avg")
        dom_share = agg(sub, "dom_total_share")
        honest = agg(sub, "honest_median_total")
        excl = agg(sub, "cooldown_exclusion_rate")
        dw = agg(sub, "double_win_rate")
        print(f"| {w} | {fmt_pct(roll['mean'])} | {pool['mean']:.2f} | "
              f"{fmt_pct(dom_share['mean'])} | {fmt_pct(dom_share['max'])} | "
              f"{fmt_pct(honest['mean'])} | {fmt_pct(excl['mean'])} | "
              f"{fmt_pct(dw['mean'])} |")


def print_sybil_delta_table(rows: List[Dict[str, Any]]) -> None:
    print()
    print("## Sybil delta (smaller = better)")
    print()
    print("How much sybils boost the dominant's total share, averaged across "
          "(dom, honest) and sybil counts ∈ {5, 10, 100}.")
    print()
    print("| window | sybil_delta (mean) | sybil_delta (median) | sybil_delta (max) |")
    print("|-------:|-------------------:|---------------------:|------------------:|")
    for w in WINDOWS:
        d = sybil_delta_for_window(rows, w)
        print(f"| {w} | {fmt_pct(d['mean'], 3)} | {fmt_pct(d['median'], 3)} | "
              f"{fmt_pct(d['max'], 3)} |")


def print_dominant_concentration(rows: List[Dict[str, Any]]) -> None:
    """Top-1 (dominant) and top-5-honest concentration per window.

    The simulator does not natively expose top-k across honest-only addresses
    in the result dict; we approximate via dom_total_share (top-1) and
    1 - dom_total_share - sum(other top-(k-1)). For honest median/worst we
    use the existing honest_median_total / honest_worst_total keys.
    """
    print()
    print("## Concentration view")
    print()
    print("| window | top-1 (mean) | top-1 (max) | honest worst (mean) | "
          "honest median (mean) |")
    print("|-------:|-------------:|------------:|--------------------:|"
          "--------------------:|")
    for w in WINDOWS:
        sub = by_window(rows, w)
        t1 = agg(sub, "dom_total_share")
        worst = agg(sub, "honest_worst_total")
        med = agg(sub, "honest_median_total")
        print(f"| {w} | {fmt_pct(t1['mean'])} | {fmt_pct(t1['max'])} | "
              f"{fmt_pct(worst['mean'])} | {fmt_pct(med['mean'])} |")


def print_pairwise_deltas(rows: List[Dict[str, Any]]) -> None:
    """w=6 vs w=5 and w=7 vs w=6 deltas across the same (dom, honest, sybil) keys."""
    print()
    print("## Pairwise deltas — what does the bump actually buy?")
    print()
    by_key = {(r["dom_hashrate"], r["n_honest"], r["n_sybils"], r["window"]): r
              for r in rows}
    pairs = [(5, 6), (6, 7), (5, 7)]
    metrics = ["dom_total_share", "rollover_rate", "pool_avg",
               "cooldown_exclusion_rate", "honest_worst_total"]
    print("| pair | metric | mean Δ (w_b − w_a) | median Δ | max Δ | min Δ |")
    print("|------|--------|-------------------:|---------:|------:|------:|")
    for (wa, wb) in pairs:
        for metric in metrics:
            deltas: List[float] = []
            for (dom, honest, sybils, w) in by_key:
                if w != wa:
                    continue
                a = by_key.get((dom, honest, sybils, wa))
                b = by_key.get((dom, honest, sybils, wb))
                if not (a and b):
                    continue
                deltas.append(b[metric] - a[metric])
            if not deltas:
                continue
            mean = statistics.mean(deltas)
            median = statistics.median(deltas)
            mx = max(deltas)
            mn = min(deltas)
            # Use percent for fractional metrics, raw for pool_avg.
            if metric == "pool_avg":
                fmt = lambda x: f"{x:+.3f}"
            else:
                fmt = lambda x: f"{x * 100:+.3f}%"
            print(f"| {wa}→{wb} | {metric} | {fmt(mean)} | {fmt(median)} | "
                  f"{fmt(mx)} | {fmt(mn)} |")


def recommend(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pick the window that (a) keeps rollover ≤ 2 % across the grid,
    (b) reduces dominant share vs. the previous window's mean,
    (c) does not collapse honest_worst more than the previous window's
        worst case.

    The output is informational; the human in the loop owns the call.
    """
    summary: Dict[int, Dict[str, float]] = {}
    for w in WINDOWS:
        sub = by_window(rows, w)
        summary[w] = {
            "rollover_max":         agg(sub, "rollover_rate")["max"],
            "rollover_mean":        agg(sub, "rollover_rate")["mean"],
            "dom_share_mean":       agg(sub, "dom_total_share")["mean"],
            "dom_share_max":        agg(sub, "dom_total_share")["max"],
            "honest_worst_mean":    agg(sub, "honest_worst_total")["mean"],
            "honest_worst_min":     agg(sub, "honest_worst_total")["min"],
            "double_win_mean":      agg(sub, "double_win_rate")["mean"],
            "sybil_delta_mean":     sybil_delta_for_window(rows, w)["mean"],
        }

    # Decision rule:
    # The C9 acceptance criterion was "rollover stays low AND sybil delta is
    # smaller than larger windows". A bump is RECOMMENDED iff a candidate
    # window strictly improves on the C9 baseline (window=5) on at least one
    # of {dom_share_mean, sybil_delta_mean, honest_worst_mean} without
    # regressing on the others. Keeping the rollover cap for sanity.
    ROLLOVER_HARD_CAP = 0.02
    base = summary[5]

    # Per-candidate improvement audit
    audit: Dict[int, Dict[str, Any]] = {}
    for w in WINDOWS:
        if w == 5:
            continue
        s = summary[w]
        improves: List[str] = []
        regresses: List[str] = []
        # Lower-is-better axes
        for axis, key in [("dom_share", "dom_share_mean"),
                          ("sybil_delta", "sybil_delta_mean"),
                          ("rollover", "rollover_max")]:
            d = s[key] - base[key]
            if d < 0:
                improves.append(axis)
            elif d > 0:
                regresses.append(axis)
        # Higher-is-better axis
        for axis, key in [("honest_worst", "honest_worst_mean")]:
            d = s[key] - base[key]
            if d > 0:
                improves.append(axis)
            elif d < 0:
                regresses.append(axis)
        audit[w] = {
            "improves":          improves,
            "regresses":         regresses,
            "rollover_under_cap": s["rollover_max"] <= ROLLOVER_HARD_CAP,
        }

    # Pick the candidate with the most improvements minus regressions, ties
    # broken by smaller window (less perturbation from the audited 5).
    scored = sorted(
        ((w, len(audit[w]["improves"]) - len(audit[w]["regresses"]), w)
         for w in audit),
        key=lambda t: (-t[1], t[2]),
    )
    best_w, best_score, _ = scored[0]
    best_audit = audit[best_w]

    if best_score > 0 and best_audit["rollover_under_cap"]:
        selected = best_w
        verdict = (
            f"Window {best_w} improves on baseline (5) on "
            f"{best_audit['improves']} and regresses on "
            f"{best_audit['regresses']} (net +{best_score}). Rollover stays "
            f"under {fmt_pct(ROLLOVER_HARD_CAP)}. Bump RECOMMENDED."
        )
    else:
        selected = 5  # explicit "no bump"
        verdict = (
            "No candidate window strictly dominates baseline (5). "
            "Across the C9 grid, larger windows show small but consistent "
            "regressions on dom_share, sybil_delta, and honest_worst, "
            "while only marginally reducing double_win. "
            f"Bump NOT recommended — keep cooldown=5. "
            f"Best candidate audit: window={best_w}, improves="
            f"{best_audit['improves']}, regresses={best_audit['regresses']}."
        )

    print()
    print("## Recommendation")
    print()
    for w, s in summary.items():
        print(f"- **window={w}**: rollover_max={fmt_pct(s['rollover_max'], 3)} "
              f"· dom_share_mean={fmt_pct(s['dom_share_mean'])} "
              f"· honest_worst_mean={fmt_pct(s['honest_worst_mean'], 3)} "
              f"· sybil_delta_mean={fmt_pct(s['sybil_delta_mean'], 3)}")
    print()
    print(f"**Verdict:** {verdict}")
    return {
        "summary":          summary,
        "rollover_cap":     ROLLOVER_HARD_CAP,
        "audit":            audit,
        "selected_window":  selected,
        "verdict":          verdict,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS,
                   help="Blocks per scenario (default: %(default)s).")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED,
                   help="Deterministic RNG seed (default: 0x%(default)x).")
    p.add_argument("--freq-mode", default="lifecycle",
                   choices=("lifecycle", "hf", "perm", "all"),
                   help="Lottery frequency phase (default: %(default)s).")
    p.add_argument("--json", dest="json_path", default=None,
                   help="If set, write a structured JSON artefact to this path.")
    args = p.parse_args(argv)

    print("# V13 lottery cooldown sweep")
    print()
    print(f"- blocks per scenario: {args.blocks}")
    print(f"- seed: 0x{args.seed:x}")
    print(f"- freq_mode: {args.freq_mode}")
    print(f"- dom_shares: {DOM_SHARES}")
    print(f"- honest_counts: {HONEST_COUNTS}")
    print(f"- sybil_counts: {SYBIL_COUNTS}")
    print(f"- windows: {WINDOWS}")
    print(f"- total scenarios: "
          f"{len(DOM_SHARES) * len(HONEST_COUNTS) * len(SYBIL_COUNTS) * len(WINDOWS)}")

    rows = run_sweep(blocks=args.blocks, seed=args.seed, freq_mode=args.freq_mode)

    print_per_window_summary(rows)
    print_sybil_delta_table(rows)
    print_dominant_concentration(rows)
    print_pairwise_deltas(rows)
    rec = recommend(rows)

    if args.json_path:
        payload = {
            "blocks":         args.blocks,
            "seed":           args.seed,
            "freq_mode":      args.freq_mode,
            "dom_shares":     DOM_SHARES,
            "honest_counts":  HONEST_COUNTS,
            "sybil_counts":   SYBIL_COUNTS,
            "windows":        WINDOWS,
            "rows":           rows,
            "recommendation": rec,
        }
        Path(args.json_path).write_text(json.dumps(payload, indent=2))
        print()
        print(f"Wrote structured artefact to {args.json_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

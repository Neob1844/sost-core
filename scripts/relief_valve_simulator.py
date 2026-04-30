#!/usr/bin/env python3
"""relief_valve_simulator.py — Monte Carlo for SOST relief valve designs.

Simulates how block discovery in PoW with cASERT-style profiles behaves
under four candidate relief-valve designs:

  - "current" : single-step relief valve at 605 s. Everyone reacts.
  - "soft"    : gradual cascade H10 → H9 → ... → E7, one step / 60 s.
  - "cap"     : relief announced at T, blocks valid only after T+30 s.
  - "continuous": difficulty is a smooth function of elapsed; no
                   discrete event to react to.

Each miner is described by (hashrate, rpc_latency, lag_check_period).
The simulator advances time in 0.05 s steps; at each step every miner
that has reacted to the current effective difficulty draws against an
exponential block-find distribution. The first miner to find a valid
block wins.

Outputs a JSON report and a simple ASCII table comparing:
  - per-miner win share
  - average block time
  - block time standard deviation
  - "reaction-race indicator" (% of E7-equivalent blocks won by the
    miner with the lowest rpc_latency — closer to its hashrate share
    means the design is fair)

This is *research code*. It is NOT consensus, NOT shipped to mainnet,
and it doesn't claim absolute realism — just a comparable yard-stick
to score the four designs against each other.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------- profiles


# Difficulty in "expected attempts per block" units. With a total
# network hashrate around 350 attempts/sec (the rough order of
# magnitude on the live SOST trial), H10 ≈ 350 * 600 ≈ 210 k means a
# 10-minute target block time, and E7 ≈ 350 * 60 ≈ 21 k means a
# 1-minute relief target. The exact numbers don't matter for fairness
# comparisons — only the *ratio* H10 / E7 ≈ 10 does, which matches
# the actual cASERT scale=2/k=7 vs scale=1/k=1 jump.
H10 = 210_000.0
E7 = 21_000.0
TARGET_BLOCK_S = 600.0


# Profile-index → difficulty mapping. Profile indices follow the
# real cASERT scale: E7 = -7, B0 = 0, H10 = 10, H13 = 13. Inside this
# simulator each integer step is a uniform multiplicative ratio so
# the dynamics of the staged scheme are reproducible.
#
#   profile_diff(-7) = E7 difficulty (21 k)
#   profile_diff(10) = H10 difficulty (210 k)
#   profile_diff( 0) ≈ B0 (intermediate)
#
# That gives a per-step ratio of (E7/H10)^(-1/17) ≈ 1.144 (each level
# is ~14 % easier than the next harder one). Good enough for
# fairness studies; not a substitute for the real cASERT compute
# tables.
_LEVELS = 17  # H10 (10) down to E7 (-7) inclusive of both ends
_RATIO_PER_LEVEL = (H10 / E7) ** (1.0 / _LEVELS)
_PROFILE_FLOOR = -7   # E7
_PROFILE_CEILING = 13  # H13


def profile_to_difficulty(profile_index: int) -> float:
    """Map a cASERT-style profile index to the simulator's difficulty
    units. Clamped to the [E7, H13] band the live chain uses."""
    p = max(_PROFILE_FLOOR, min(_PROFILE_CEILING, int(profile_index)))
    return E7 * (_RATIO_PER_LEVEL ** (p - _PROFILE_FLOOR))


def difficulty_current(elapsed_s: float) -> float:
    """Today's behaviour: one cliff at 605 s."""
    return E7 if elapsed_s >= 605.0 else H10


def difficulty_soft(elapsed_s: float) -> float:
    """A) Soft cascade: H10 until 600 s, then ~1.5x easier every 60 s
    down to E7."""
    if elapsed_s < 600.0:
        return H10
    steps = int((elapsed_s - 600.0) // 60.0)
    diff = H10 / (1.5 ** steps)
    return max(diff, E7)


def difficulty_cap(elapsed_s: float) -> float:
    """B) Hard cap: relief announced at T=570 s. From T onwards
    everyone is mining E7. The validity rule lives outside the
    difficulty function — see ``cap_block_valid_at``."""
    return E7 if elapsed_s >= 570.0 else H10


def cap_block_valid_at(elapsed_s: float) -> bool:
    """For scheme B: only after T+30 s can a block be submitted."""
    return elapsed_s >= 600.0


def difficulty_continuous(elapsed_s: float) -> float:
    """C) Continuous curve: smooth sigmoid drop centred on 600 s.
    No discrete announcement → no reaction race."""
    if elapsed_s <= 540.0:
        return H10
    excess = elapsed_s - 540.0
    # Drops from H10 to E7 over ~120 s, smoothly. Asymptotes at E7.
    t = excess / 60.0  # in 60-second units
    # Logistic: starts near 0 at t=0, reaches ~1 by t≈3.
    s = 1.0 / (1.0 + math.exp(-(t - 1.5) * 2.5))
    return H10 - (H10 - E7) * s


# ---- Staged relief (the candidate proposed for the live chain) ----
#
# Starts at 570 s, drops 3 profile levels every 30 s, floors at E7.
# Operates relative to the *base* profile picked by cASERT, so the
# behaviour scales with whatever H10/H11/H12/H13 the equalizer
# selected for that block.
#
#   if elapsed < 570:    drop = 0
#   else:                drop = 3 * (floor((elapsed - 570) / 30) + 1)
#   effective_H = max(base_H - drop, E7)
#
# No grace/cap (rejected: cap is unenforceable in consensus without a
# commit-reveal seed; without one the dominant simply pre-mines with
# future timestamps). The fairness comes from removing the H10→E7
# cliff, not from forcing a synchronised restart.

STAGED_RELIEF_START = 570.0
STAGED_STEP_SECONDS = 30.0
STAGED_DROP_PER_STEP = 3


def staged_effective_profile(elapsed_s: float, base_profile: int) -> int:
    """Return the effective profile index under the staged scheme."""
    if elapsed_s < STAGED_RELIEF_START:
        return base_profile
    steps = int((elapsed_s - STAGED_RELIEF_START) // STAGED_STEP_SECONDS) + 1
    drop = STAGED_DROP_PER_STEP * steps
    eff = base_profile - drop
    return max(eff, _PROFILE_FLOOR)


def difficulty_staged(elapsed_s: float, base_profile: int = 10) -> float:
    """Staged relief: 3-profile drops every 30 s starting at 570 s,
    relative to ``base_profile`` (default H10)."""
    return profile_to_difficulty(
        staged_effective_profile(elapsed_s, base_profile)
    )


def _staged_for_h10(elapsed_s: float) -> float:
    return difficulty_staged(elapsed_s, base_profile=10)


def _staged_for_h11(elapsed_s: float) -> float:
    return difficulty_staged(elapsed_s, base_profile=11)


# ---- V10: Granular staged relief (block 6700+) -----------------------
#
# Refines V9: drop ONE profile level every 60 s starting at 600 s.
# Floor still at E7. Lag-advance disabled at this height (out of the
# difficulty function's scope; modelled here as "the base profile is
# stable at the chosen `base_profile` and does not move within the
# block").
GRANULAR_RELIEF_START = 600.0
GRANULAR_STEP_SECONDS = 60.0
GRANULAR_DROP_PER_STEP = 1


def granular_effective_profile(elapsed_s: float, base_profile: int) -> int:
    if elapsed_s < GRANULAR_RELIEF_START:
        return base_profile
    steps = int((elapsed_s - GRANULAR_RELIEF_START) // GRANULAR_STEP_SECONDS) + 1
    drop = GRANULAR_DROP_PER_STEP * steps
    eff = base_profile - drop
    return max(eff, _PROFILE_FLOOR)


def difficulty_granular(elapsed_s: float, base_profile: int = 10) -> float:
    return profile_to_difficulty(
        granular_effective_profile(elapsed_s, base_profile)
    )


def _granular_for_h10(elapsed_s: float) -> float:
    return difficulty_granular(elapsed_s, base_profile=10)


def _granular_for_h11(elapsed_s: float) -> float:
    return difficulty_granular(elapsed_s, base_profile=11)


SCHEMES: Dict[str, Tuple[Callable[[float], float], Optional[Callable[[float], bool]]]] = {
    "current": (difficulty_current, None),
    "soft": (difficulty_soft, None),
    "cap": (difficulty_cap, cap_block_valid_at),
    "continuous": (difficulty_continuous, None),
    # Staged relief, default base profile H10 (most common during the
    # live trial). Use staged_h11 for the H11 base case, etc.
    "staged": (_staged_for_h10, None),
    "staged_h11": (_staged_for_h11, None),
    # V10 granular cascade — drop 1 per 60 s from 600 s. The expected
    # post-fork profile distribution for a chain that mostly mines at
    # base H10 with a small overshoot.
    "granular": (_granular_for_h10, None),
    "granular_h11": (_granular_for_h11, None),
}


# ---------------------------------------------------------------- miner

@dataclass
class MinerProfile:
    name: str
    # attempts/sec at base difficulty (1.0). Effective rate at
    # difficulty d is hashrate / d.
    hashrate: float
    # one-way RPC latency (in seconds) to the node
    rpc_latency: float = 0.05
    # how often the miner polls getinfo (seconds)
    lag_check_period: float = 2.0

    def reaction_time(self, change_announced_at: float) -> float:
        """Time until this miner notices a difficulty change at
        ``change_announced_at``. Worst case = lag_check_period plus
        round-trip RPC latency."""
        # Random offset within the polling window — simulates that
        # the miner could be just before or just after a poll boundary.
        poll_offset = random.random() * self.lag_check_period
        return change_announced_at + poll_offset + self.rpc_latency * 2


# ---------------------------------------------------------------- core sim

@dataclass
class BlockResult:
    winner: str
    elapsed: float
    won_at_difficulty: float


def simulate_one_block(
    miners: List[MinerProfile],
    scheme: str,
    *,
    rng: random.Random,
    dt: float = 0.5,
    max_elapsed: float = 1800.0,
) -> BlockResult:
    """Simulate one race for a single block under ``scheme``."""
    diff_fn, valid_fn = SCHEMES[scheme]

    # Pre-compute reaction times for each miner. For schemes with a
    # discrete announcement, reaction = miner's reaction_time at the
    # announcement instant. For "continuous", every miner is always
    # reacting — reaction_time is essentially zero.
    if scheme == "current":
        announce = 605.0
    elif scheme == "soft":
        announce = 600.0  # the first cascade step
    elif scheme == "cap":
        announce = 570.0
    else:
        announce = 0.0  # continuous — no discrete announcement

    reactions = {m.name: m.reaction_time(announce) for m in miners}

    elapsed = 0.0
    while elapsed < max_elapsed:
        d = diff_fn(elapsed)
        # Each miner that has reacted draws a uniform attempt:
        for m in miners:
            # If the announcement hasn't happened yet, miner is
            # already reacting to the *current* (pre-announce)
            # difficulty.
            if scheme != "continuous" and elapsed < announce:
                d_eff = diff_fn(elapsed)  # H10 typically
                effective_hashrate = m.hashrate / d_eff
            else:
                if elapsed < reactions[m.name]:
                    continue
                effective_hashrate = m.hashrate / d

            p_find = 1.0 - math.exp(-effective_hashrate * dt)
            if rng.random() < p_find:
                # Found a candidate. Validity check (only matters
                # for scheme "cap").
                if valid_fn is not None and not valid_fn(elapsed):
                    # Candidate found but block can't be submitted yet.
                    # The miner keeps the candidate; if the time gate
                    # opens, they submit instantly. We model that by
                    # advancing to T+30 and re-rolling the win.
                    elapsed = 600.0
                    continue
                return BlockResult(
                    winner=m.name,
                    elapsed=elapsed,
                    won_at_difficulty=d,
                )
        elapsed += dt
    # No block found within the cap. Treat as orphaned race; pick a
    # synthetic stall winner so callers can still tally.
    return BlockResult(
        winner="(stall)", elapsed=max_elapsed, won_at_difficulty=H10,
    )


# ---------------------------------------------------------------- driver

@dataclass
class SchemeReport:
    scheme: str
    n_blocks: int
    avg_block_time: float
    stdev_block_time: float
    win_share: Dict[str, float] = field(default_factory=dict)
    e7_or_easier_share: Dict[str, float] = field(default_factory=dict)
    n_e7_or_easier: int = 0


def run_scheme(
    scheme: str, miners: List[MinerProfile], *, n_blocks: int, seed: int,
) -> SchemeReport:
    rng = random.Random(seed)
    times: List[float] = []
    wins: Dict[str, int] = {m.name: 0 for m in miners}
    wins["(stall)"] = 0
    e7_wins: Dict[str, int] = {m.name: 0 for m in miners}
    n_e7 = 0

    for _ in range(n_blocks):
        r = simulate_one_block(miners, scheme, rng=rng)
        wins[r.winner] = wins.get(r.winner, 0) + 1
        times.append(r.elapsed)
        # Tally separately the relief-valve / easy blocks ("E7-equivalent"):
        # under "soft" the difficulty might be H7 etc., still much easier
        # than H10. Treat anything ≤ H10 / 1.5 as relief-territory.
        if r.won_at_difficulty <= H10 / 1.5:
            n_e7 += 1
            if r.winner != "(stall)":
                e7_wins[r.winner] = e7_wins.get(r.winner, 0) + 1

    total = sum(wins.values()) or 1
    e7_total = sum(e7_wins.values()) or 1
    return SchemeReport(
        scheme=scheme,
        n_blocks=n_blocks,
        avg_block_time=statistics.fmean(times),
        stdev_block_time=statistics.pstdev(times),
        win_share={k: v / total for k, v in wins.items()},
        e7_or_easier_share={k: v / e7_total for k, v in e7_wins.items()},
        n_e7_or_easier=n_e7,
    )


# ---------------------------------------------------------------- presets

PRESET_MINERS: List[MinerProfile] = [
    MinerProfile(name="dominant_192c",
                 hashrate=195.0,
                 rpc_latency=0.001,        # colocated with node
                 lag_check_period=0.5),    # aggressive polling
    MinerProfile(name="vostokzyf_64c",
                 hashrate=90.0,
                 rpc_latency=0.030,
                 lag_check_period=2.0),
    MinerProfile(name="neob_12c_wsl",
                 hashrate=36.0,
                 rpc_latency=0.180,         # Murcia → Frankfurt over SSH
                 lag_check_period=2.0),
    MinerProfile(name="small_8c_home",
                 hashrate=22.0,
                 rpc_latency=0.090,
                 lag_check_period=2.0),
    MinerProfile(name="small_4c_remote",
                 hashrate=12.0,
                 rpc_latency=0.220,
                 lag_check_period=2.0),
]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="relief_valve_simulator",
        description="Compare SOST relief-valve designs by Monte Carlo.",
    )
    p.add_argument("--n-blocks", type=int, default=2000,
                   help="Blocks to simulate per scheme (default: 2000).")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--schemes", default="current,soft,cap,continuous",
                   help="Comma-separated scheme names.")
    p.add_argument("--json", action="store_true",
                   help="Emit JSON instead of the ASCII table.")
    return p


def _format_table(reports: List[SchemeReport],
                  miners: List[MinerProfile]) -> str:
    lines: List[str] = []
    headers = ["scheme", "avg blk", "stdev", "n_E7"]
    for m in miners:
        headers.append(m.name + " (all)")
    for m in miners:
        headers.append(m.name + " (E7)")
    lines.append("  ".join(f"{h:<18}" for h in headers))
    for r in reports:
        row = [
            r.scheme,
            f"{r.avg_block_time:7.1f}s",
            f"{r.stdev_block_time:6.1f}",
            str(r.n_e7_or_easier),
        ]
        for m in miners:
            v = r.win_share.get(m.name, 0.0)
            row.append(f"{v*100:5.1f}%")
        for m in miners:
            v = r.e7_or_easier_share.get(m.name, 0.0)
            row.append(f"{v*100:5.1f}%")
        lines.append("  ".join(f"{c:<18}" for c in row))
    # Add hashrate share for reference
    total_hr = sum(m.hashrate for m in miners)
    fair = "  ".join(f"{m.hashrate/total_hr*100:5.1f}%" for m in miners)
    lines.append("")
    lines.append(f"hashrate share (the 'fair' baseline):     {fair}")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    schemes = [s.strip() for s in args.schemes.split(",") if s.strip()]
    miners = PRESET_MINERS

    reports: List[SchemeReport] = []
    for sch in schemes:
        if sch not in SCHEMES:
            print(f"unknown scheme: {sch!r}", file=sys.stderr)
            return 2
        reports.append(run_scheme(sch, miners,
                                   n_blocks=args.n_blocks,
                                   seed=args.seed))

    if args.json:
        out = {
            "miners": [
                {"name": m.name, "hashrate": m.hashrate,
                 "rpc_latency": m.rpc_latency,
                 "lag_check_period": m.lag_check_period}
                for m in miners
            ],
            "n_blocks_per_scheme": args.n_blocks,
            "schemes": [
                {"scheme": r.scheme,
                 "avg_block_time": r.avg_block_time,
                 "stdev_block_time": r.stdev_block_time,
                 "n_e7_or_easier": r.n_e7_or_easier,
                 "win_share": r.win_share,
                 "e7_or_easier_share": r.e7_or_easier_share}
                for r in reports
            ],
        }
        print(json.dumps(out, indent=2))
    else:
        print(_format_table(reports, miners))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

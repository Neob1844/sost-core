#!/usr/bin/env python3
"""SOST chain auditor — miner concentration + timestamp abuse + orphan detection.

Pulls the last N blocks from a SOST node via JSON-RPC and reports:

  1. Share per address (raw) and per entity (with --merge groups)
  2. Block-interval distribution (mean, median, min, max)
  3. Cascade-boundary clustering — how many blocks land in
     [600,605], [660,665], [720,725], … (V10 step boundaries).
     The dominant miner with disproportionate clustering would suggest
     deliberate withholding-and-release at cascade transitions.
  4. Future-drift abuse — running cumulative drift between chain time
     and ideal schedule, plus per-block elapsed > 1.5× target rate.
  5. Reorg / orphan detection — getchaintips for non-active branches.

Stdlib only. No third-party deps. Read-only RPC. No consensus changes.
Save the markdown report under docs/audit/<UTC>.md when --save is set.

Usage:

    ./scripts/audit_miner_concentration.py \\
        --rpc-url http://127.0.0.1:18232 \\
        --rpc-user "$RPC_USER" --rpc-pass "$RPC_PASS" \\
        --last 288 \\
        --merge 'sost1e6945a...111d=A,sost1163c2...df59=A' \\
        --save
"""

from __future__ import annotations

import argparse
import base64
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# V10 cascade boundaries (granular relief):
# elapsed = 600 s   → drop 1
# elapsed = 660 s   → drop 2
# elapsed = 720 s   → drop 3, etc.
CASCADE_BOUNDARIES = [600 + 60 * k for k in range(0, 18)]

# Window after each boundary that counts as "clustering" (just-past-boundary).
# 5 s is tight enough to flag deliberate timing without false positives from
# normal stochastic finds.
CLUSTER_WINDOW_SEC = 5

# Heuristic for "near future-drift cap": SOST allows block.time up to now+60.
# If a miner consistently posts block.time within DRIFT_NEAR_CAP of the cap,
# they may be inflating timestamps to manipulate cASERT lag.
DRIFT_NEAR_CAP = 50  # seconds

TARGET_BLOCK_TIME = 600  # SOST design target


# ---------------------------------------------------------------- RPC

class RPC:
    """Minimal JSON-RPC client over urllib (stdlib only)."""

    def __init__(self, url: str, user: str, password: str,
                 timeout: int = 15) -> None:
        self.url = url
        self.timeout = timeout
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.auth = f"Basic {token}"

    def call(self, method: str, *params: Any) -> Any:
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": list(params),
        }).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": self.auth,
            })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"RPC HTTP {e.code} on {method!r}: {e.read()!r}")
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"RPC connection error on {method!r}: {e}")
        if payload.get("error"):
            raise RuntimeError(f"RPC error on {method!r}: {payload['error']}")
        return payload.get("result")


# ---------------------------------------------------------------- helpers

def extract_miner_addr(block: Dict[str, Any]) -> str:
    """Pull the miner address from the coinbase transaction.

    SOST coinbase has 3 outputs (50% miner / 25% gold vault / 25% PoPC pool).
    The miner is the LARGEST output by value.
    """
    txs = block.get("tx") or []
    if not txs:
        return ""
    cb = txs[0]
    # tx may be a string id or a dict — getblock verbosity 2 gives dicts.
    if isinstance(cb, str):
        return ""
    vouts = cb.get("vout") or []
    if not vouts:
        return ""
    largest = max(vouts, key=lambda v: float(v.get("value", 0)))
    spk = largest.get("scriptPubKey") or {}
    # Modern Bitcoin Core: "address". Older: "addresses" array.
    if "address" in spk:
        return spk["address"]
    addrs = spk.get("addresses") or []
    return addrs[0] if addrs else ""


def parse_merge_arg(specs: List[str]) -> Dict[str, str]:
    """Parse --merge addr1=A,addr2=A specs into {addr -> label}."""
    out: Dict[str, str] = {}
    for spec in specs:
        for pair in spec.split(","):
            if "=" not in pair:
                continue
            addr, label = pair.split("=", 1)
            out[addr.strip()] = label.strip()
    return out


def short_addr(a: str) -> str:
    if not a:
        return "(unknown)"
    return f"{a[:9]}…{a[-6:]}" if len(a) > 16 else a


# ---------------------------------------------------------------- metrics

def cluster_counts(intervals_by_miner: Dict[str, List[int]]
                   ) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Count, per miner, how many of their intervals fall just past a
    cascade boundary. Returns (cluster_count, total_count)."""
    clusters: Dict[str, int] = defaultdict(int)
    totals: Dict[str, int] = defaultdict(int)
    for m, ivals in intervals_by_miner.items():
        for el in ivals:
            totals[m] += 1
            for b in CASCADE_BOUNDARIES:
                if b <= el <= b + CLUSTER_WINDOW_SEC:
                    clusters[m] += 1
                    break
    return clusters, totals


def expected_clustering_rate() -> float:
    """Naive expected fraction of blocks that fall in a 5-s window after any
    boundary, under exponential(rate=1/600s) intervals over [600, 1700]."""
    # P(t in [b, b+5]) for each boundary b. With exponential(rate=1/600):
    rate = 1.0 / TARGET_BLOCK_TIME
    p = 0.0
    for b in CASCADE_BOUNDARIES:
        # P(b <= T <= b+5) = exp(-b/600) - exp(-(b+5)/600)
        import math
        p += math.exp(-rate * b) - math.exp(-rate * (b + CLUSTER_WINDOW_SEC))
    return p  # fraction of all blocks expected in a cluster window


# ---------------------------------------------------------------- pull

def pull_blocks(rpc: RPC, lo: int, hi: int) -> List[Dict[str, Any]]:
    print(f"[pull] fetching blocks {lo}..{hi} via RPC", file=sys.stderr)
    blocks: List[Dict[str, Any]] = []
    n = hi - lo + 1
    last_log = time.time()
    for i, h in enumerate(range(lo, hi + 1)):
        bh = rpc.call("getblockhash", h)
        b = rpc.call("getblock", bh, 2)
        miner = extract_miner_addr(b)
        blocks.append({
            "height": h,
            "hash": bh,
            "time": int(b.get("time") or 0),
            "miner": miner,
            "prev_hash": b.get("previousblockhash"),
        })
        if time.time() - last_log >= 5:
            print(f"[pull] {i+1}/{n}", file=sys.stderr)
            last_log = time.time()
    return blocks


def pull_chaintips(rpc: RPC) -> List[Dict[str, Any]]:
    try:
        return rpc.call("getchaintips") or []
    except RuntimeError as e:
        print(f"[pull] getchaintips failed: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------- report

def build_report(blocks: List[Dict[str, Any]],
                 chaintips: List[Dict[str, Any]],
                 merge: Dict[str, str]) -> Dict[str, Any]:
    if not blocks:
        return {"error": "no blocks"}

    # Decorate intervals
    blocks_sorted = sorted(blocks, key=lambda b: b["height"])
    for i, b in enumerate(blocks_sorted):
        b["entity"] = merge.get(b["miner"], b["miner"])
        if i == 0:
            b["interval"] = None
        else:
            b["interval"] = b["time"] - blocks_sorted[i - 1]["time"]

    # 1) Share per address / per entity
    raw_counts = Counter(b["miner"] for b in blocks_sorted)
    entity_counts = Counter(b["entity"] for b in blocks_sorted)
    n = len(blocks_sorted)

    # 2) Interval stats
    ivals = [b["interval"] for b in blocks_sorted if b["interval"] is not None]
    interval_stats = {
        "n": len(ivals),
        "mean": statistics.mean(ivals) if ivals else 0,
        "median": statistics.median(ivals) if ivals else 0,
        "stdev": statistics.pstdev(ivals) if ivals else 0,
        "min": min(ivals) if ivals else 0,
        "max": max(ivals) if ivals else 0,
    }

    # 3) Boundary clustering — per-entity
    by_entity: Dict[str, List[int]] = defaultdict(list)
    for b in blocks_sorted:
        if b["interval"] is not None:
            by_entity[b["entity"]].append(b["interval"])
    clusters, totals = cluster_counts(by_entity)
    expected_rate = expected_clustering_rate()

    # 4) Future-drift / time-warp
    if len(blocks_sorted) >= 2:
        first = blocks_sorted[0]
        last = blocks_sorted[-1]
        elapsed_chain = last["time"] - first["time"]
        elapsed_target = (last["height"] - first["height"]) * TARGET_BLOCK_TIME
        cumulative_drift_sec = elapsed_chain - elapsed_target
    else:
        cumulative_drift_sec = 0

    # Detect blocks where block.time outpaced previous by > 1.5 × target
    long_intervals = [b for b in blocks_sorted
                       if b["interval"] is not None and
                          b["interval"] > 1.5 * TARGET_BLOCK_TIME]
    long_intervals_pct = len(long_intervals) / max(1, len(ivals)) * 100

    # 5) Orphans / reorgs from chaintips
    active = sum(1 for t in chaintips if t.get("status") == "active")
    valid_fork = [t for t in chaintips
                   if t.get("status") in ("valid-fork", "valid-headers")]
    invalid = [t for t in chaintips if t.get("status") == "invalid"]
    forks = [t for t in chaintips if t.get("status") != "active"]

    return {
        "schema": "sost_miner_concentration_audit@v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "range": {
            "lo": blocks_sorted[0]["height"],
            "hi": blocks_sorted[-1]["height"],
            "n": n,
        },
        "raw_share": [
            {"address": a, "blocks": c, "share_pct": c / n * 100}
            for a, c in raw_counts.most_common()
        ],
        "entity_share": [
            {"entity": e, "blocks": c, "share_pct": c / n * 100}
            for e, c in entity_counts.most_common()
        ],
        "interval_stats": interval_stats,
        "boundary_clustering": {
            "window_sec": CLUSTER_WINDOW_SEC,
            "boundaries": CASCADE_BOUNDARIES,
            "expected_rate_pct": expected_rate * 100,
            "per_entity": [
                {
                    "entity": e,
                    "blocks": totals[e],
                    "clustered": clusters[e],
                    "rate_pct": (clusters[e] / totals[e] * 100) if totals[e] else 0.0,
                    "z_vs_expected": _z_score(
                        clusters[e], totals[e], expected_rate),
                }
                for e in sorted(totals.keys(), key=lambda x: -totals[x])
            ],
        },
        "future_drift": {
            "cumulative_drift_sec": cumulative_drift_sec,
            "cumulative_drift_h": cumulative_drift_sec / 3600,
            "interpretation": _interpret_drift(cumulative_drift_sec, n),
            "long_interval_count": len(long_intervals),
            "long_interval_pct": long_intervals_pct,
        },
        "chaintips": {
            "active": active,
            "forks_count": len(forks),
            "valid_fork": [
                {"height": t.get("height"), "branchlen": t.get("branchlen"),
                 "status": t.get("status"), "hash": t.get("hash")}
                for t in valid_fork
            ],
            "invalid_count": len(invalid),
        },
    }


def _z_score(observed: int, total: int, expected_rate: float) -> float:
    """Two-sided z-score for binomial(total, expected_rate) at observed."""
    if total == 0:
        return 0.0
    import math
    mu = total * expected_rate
    sigma = math.sqrt(total * expected_rate * (1 - expected_rate))
    if sigma == 0:
        return 0.0
    return (observed - mu) / sigma


def _interpret_drift(drift: int, n: int) -> str:
    """Human label for cumulative drift over n blocks."""
    avg = drift / max(1, n)
    if abs(avg) < 5:
        return "ok — chain timing within ±5 s/block of target"
    if abs(avg) < 30:
        return "noticeable — chain timing off by 5-30 s/block, normal cASERT response"
    if abs(avg) < 60:
        return "elevated — sustained 30-60 s/block drift; check time-warp"
    return "alarming — sustained >60 s/block drift; investigate time-warp abuse"


# ---------------------------------------------------------------- render

def render_markdown(report: Dict[str, Any]) -> str:
    if "error" in report:
        return f"# Audit error: {report['error']}\n"
    out: List[str] = []
    rng = report["range"]
    out.append(f"# SOST chain audit — blocks {rng['lo']}..{rng['hi']} "
                f"(n={rng['n']})")
    out.append("")
    out.append(f"_Generated: {report['generated_at_utc']}_")
    out.append("")

    # 1) Top entities
    out.append("## 1. Share per entity (with --merge groups)")
    out.append("")
    out.append("| Entity | Blocks | Share |")
    out.append("|---|---:|---:|")
    for row in report["entity_share"][:10]:
        out.append(f"| `{short_addr(row['entity'])}` "
                   f"| {row['blocks']} | {row['share_pct']:.1f}% |")
    out.append("")

    # 1b) Raw addresses (no merge)
    out.append("## 1b. Share per raw address")
    out.append("")
    out.append("| Address | Blocks | Share |")
    out.append("|---|---:|---:|")
    for row in report["raw_share"][:15]:
        out.append(f"| `{short_addr(row['address'])}` "
                   f"| {row['blocks']} | {row['share_pct']:.1f}% |")
    out.append("")

    # 2) Interval stats
    s = report["interval_stats"]
    out.append("## 2. Block-interval statistics (target 600 s)")
    out.append("")
    out.append(f"- n: **{s['n']}**")
    out.append(f"- mean: **{s['mean']:.0f} s** "
                f"(target 600 s, deviation {s['mean']-600:+.0f} s)")
    out.append(f"- median: {s['median']:.0f} s")
    out.append(f"- stdev: {s['stdev']:.0f} s")
    out.append(f"- min: {s['min']} s, max: {s['max']} s")
    out.append("")

    # 3) Clustering
    bc = report["boundary_clustering"]
    out.append("## 3. Cascade-boundary clustering")
    out.append("")
    out.append(f"Window: blocks landing within **{bc['window_sec']} s** "
                f"of any V10 cascade boundary "
                f"({bc['boundaries'][0]}, {bc['boundaries'][1]}, "
                f"{bc['boundaries'][2]}, … s).")
    out.append(f"Expected fraction under stochastic mining: "
                f"**{bc['expected_rate_pct']:.1f}%**.")
    out.append("")
    out.append("| Entity | Blocks | Clustered | Rate | z |")
    out.append("|---|---:|---:|---:|---:|")
    for row in bc["per_entity"][:10]:
        flag = ""
        if row["z_vs_expected"] >= 2.5:
            flag = " ⚠️"
        elif row["z_vs_expected"] >= 4:
            flag = " 🚨"
        out.append(f"| `{short_addr(row['entity'])}` "
                   f"| {row['blocks']} | {row['clustered']} "
                   f"| {row['rate_pct']:.1f}% | {row['z_vs_expected']:+.2f}{flag} |")
    out.append("")
    out.append("_z ≥ 2.5 → suspicious; z ≥ 4 → strong signal of clustering._")
    out.append("")

    # 4) Drift
    fd = report["future_drift"]
    out.append("## 4. Future-drift / time-warp signals")
    out.append("")
    out.append(f"- Cumulative drift across the window: "
                f"**{fd['cumulative_drift_sec']:+d} s** "
                f"({fd['cumulative_drift_h']:+.2f} h)")
    out.append(f"- Interpretation: **{fd['interpretation']}**")
    out.append(f"- Blocks with interval > 1.5× target (>900 s): "
                f"{fd['long_interval_count']} "
                f"({fd['long_interval_pct']:.1f}%)")
    out.append("")

    # 5) Chaintips
    ct = report["chaintips"]
    out.append("## 5. Reorgs / orphan branches (getchaintips)")
    out.append("")
    out.append(f"- Active tips: {ct['active']}")
    out.append(f"- Non-active forks: {ct['forks_count']}")
    out.append(f"- Invalid branches: {ct['invalid_count']}")
    if ct["valid_fork"]:
        out.append("")
        out.append("**Valid-fork branches detected:**")
        out.append("")
        out.append("| Branch height | Branch len | Status | Hash |")
        out.append("|---:|---:|---|---|")
        for t in ct["valid_fork"][:20]:
            out.append(f"| {t['height']} | {t['branchlen']} | {t['status']} | "
                       f"`{t['hash'][:16]}…` |")
    else:
        out.append("- ✅ No valid-fork branches recorded.")
    out.append("")

    # Verdict line
    out.append("## Verdict")
    out.append("")
    suspicious = []
    for row in bc["per_entity"]:
        if row["z_vs_expected"] >= 2.5 and row["blocks"] >= 20:
            suspicious.append(
                f"`{short_addr(row['entity'])}` clusters with z={row['z_vs_expected']:+.2f}")
    if abs(fd["cumulative_drift_sec"]) > 60 * rng["n"] * 0.5:
        suspicious.append(
            f"sustained drift >30 s/block ({fd['cumulative_drift_sec']:+d} s)")
    if ct["forks_count"] > 0:
        suspicious.append(f"{ct['forks_count']} non-active fork(s) detected")
    if suspicious:
        out.append("⚠️  **Signals to investigate:**")
        for s in suspicious:
            out.append(f"- {s}")
    else:
        out.append("✅ No clustering, drift or fork signal in this window. "
                    "Concentration in this window reflects hashrate share, "
                    "not protocol abuse.")
    out.append("")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- save

def save_report_md(text: str, root: Optional[Path] = None) -> Path:
    base = root or Path(__file__).resolve().parents[1] / "docs" / "audit"
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out = base / f"audit_{stamp}.md"
    out.write_text(text, encoding="utf-8")
    return out


# ---------------------------------------------------------------- main

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="audit_miner_concentration",
        description="SOST miner concentration + timestamp / orphan auditor.")
    p.add_argument("--rpc-url", default="http://127.0.0.1:18232")
    p.add_argument("--rpc-user", required=True)
    p.add_argument("--rpc-pass", required=True)
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--last", type=int, default=288,
                     help="audit the last N blocks (default 288)")
    grp.add_argument("--range", help="height range, e.g., 6700-6900")
    p.add_argument("--merge", action="append", default=[],
                   help="merge addresses into entities; "
                        "repeat or comma-separate: addr1=A,addr2=A")
    p.add_argument("--save", action="store_true",
                   help="write the markdown under docs/audit/<UTC>.md")
    p.add_argument("--json", action="store_true",
                   help="emit JSON instead of markdown")
    args = p.parse_args(argv)

    rpc = RPC(args.rpc_url, args.rpc_user, args.rpc_pass)
    tip = rpc.call("getblockcount")

    if args.range:
        try:
            lo, hi = (int(x) for x in args.range.split("-", 1))
        except ValueError:
            print(f"ERROR: invalid --range {args.range!r}", file=sys.stderr)
            return 2
    else:
        hi = int(tip)
        lo = max(0, hi - args.last + 1)

    if lo > hi or hi > tip:
        print(f"ERROR: range {lo}..{hi} invalid (tip={tip})", file=sys.stderr)
        return 2

    blocks = pull_blocks(rpc, lo, hi)
    chaintips = pull_chaintips(rpc)
    merge = parse_merge_arg(args.merge)
    report = build_report(blocks, chaintips, merge)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        md = render_markdown(report)
        print(md)
        if args.save:
            out = save_report_md(md)
            print(f"\nsaved: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

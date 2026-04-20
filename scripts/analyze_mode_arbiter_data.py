#!/usr/bin/env python3
"""
Mode Arbiter Data Analyzer — Reads raw JSONL and produces observation report.

No arbiter logic. Just statistics from the raw data to inform the design.

Usage:
    python3 scripts/analyze_mode_arbiter_data.py
    python3 scripts/analyze_mode_arbiter_data.py --data-dir data/mode_arbiter
"""

import argparse, json, os, statistics
from collections import Counter
from datetime import datetime

def load_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except:
                    pass
    return rows

def main():
    ap = argparse.ArgumentParser(description="Mode Arbiter Data Analyzer")
    ap.add_argument("--data-dir", default="data/mode_arbiter")
    args = ap.parse_args()

    blocks = load_jsonl(os.path.join(args.data_dir, "block_samples.jsonl"))
    events = load_jsonl(os.path.join(args.data_dir, "events.jsonl"))
    live = load_jsonl(os.path.join(args.data_dir, "live_samples.jsonl"))

    print(f"{'═'*70}")
    print(f"  MODE ARBITER OBSERVATION REPORT")
    print(f"{'═'*70}")
    print(f"  Block samples: {len(blocks)}")
    print(f"  Live samples:  {len(live)}")
    print(f"  Events:        {len(events)}")

    if not blocks and not live:
        print("\n  No data yet. Run the collector first.")
        return

    # ── Block statistics ──
    if blocks:
        intervals = [b["interval_sec"] for b in blocks if b.get("interval_sec", 0) > 0]
        profiles = [b["profile_effective"] for b in blocks]
        lags = [b["lag_after"] for b in blocks]
        bitsqs = [b["bitsQ_float"] for b in blocks]
        ceiling_hits = sum(1 for b in blocks if b.get("profile_ceiling_applied"))

        print(f"\n{'─'*70}")
        print(f"  BLOCK STATISTICS ({len(blocks)} blocks)")
        print(f"{'─'*70}")

        if intervals:
            print(f"  Intervals:")
            print(f"    Mean:   {statistics.mean(intervals)/60:.1f}m")
            print(f"    Median: {statistics.median(intervals)/60:.1f}m")
            print(f"    Std:    {statistics.stdev(intervals)/60:.1f}m" if len(intervals)>1 else "")
            sorted_i = sorted(intervals)
            p95 = sorted_i[int(len(sorted_i)*0.95)] if len(sorted_i)>20 else max(sorted_i)
            print(f"    P95:    {p95/60:.0f}m")
            print(f"    Max:    {max(intervals)/60:.0f}m")
            print(f"    >20m:   {sum(1 for i in intervals if i>=1200)}")
            print(f"    >40m:   {sum(1 for i in intervals if i>=2400)}")
            print(f"    >60m:   {sum(1 for i in intervals if i>=3600)}")

        # Profile distribution
        prof_counts = Counter(profiles)
        print(f"\n  Profile distribution:")
        for p in sorted(prof_counts.keys()):
            name = f"H{p}" if p > 0 else ("B0" if p == 0 else f"E{abs(p)}")
            count = prof_counts[p]
            pct = count / len(profiles) * 100
            bar = '█' * int(pct / 2)
            print(f"    {name:>4}: {count:>5} ({pct:5.1f}%)  {bar}")

        # Time in each profile (weighted by interval)
        prof_time = {}
        for b in blocks:
            pi = b["profile_effective"]
            dt = b.get("interval_sec", 0)
            prof_time[pi] = prof_time.get(pi, 0) + dt
        total_time = sum(prof_time.values())
        if total_time > 0:
            print(f"\n  Time in each profile:")
            for p in sorted(prof_time.keys()):
                name = f"H{p}" if p > 0 else ("B0" if p == 0 else f"E{abs(p)}")
                secs = prof_time[p]
                pct = secs / total_time * 100
                print(f"    {name:>4}: {secs/60:.0f}m ({pct:.1f}%)")

        # Lag statistics
        if lags:
            print(f"\n  Lag:")
            print(f"    Mean:   {statistics.mean(lags):+.1f}")
            print(f"    Max:    {max(lags):+d}")
            print(f"    Min:    {min(lags):+d}")

        # Ceiling hits
        print(f"\n  Ceiling hits (H10 cap): {ceiling_hits}")

        # Profile oscillation: H9↔H10 sequences
        transitions = []
        for i in range(1, len(profiles)):
            if profiles[i] != profiles[i-1]:
                transitions.append((profiles[i-1], profiles[i]))
        trans_counts = Counter(transitions)
        if trans_counts:
            print(f"\n  Profile transitions (top 10):")
            for (fr, to), count in trans_counts.most_common(10):
                fn = f"H{fr}" if fr > 0 else ("B0" if fr == 0 else f"E{abs(fr)}")
                tn = f"H{to}" if to > 0 else ("B0" if to == 0 else f"E{abs(to)}")
                print(f"    {fn:>4} → {tn:<4}: {count}")

    # ── Event statistics ──
    if events:
        print(f"\n{'─'*70}")
        print(f"  EVENTS ({len(events)} total)")
        print(f"{'─'*70}")

        evt_counts = Counter(e["event_type"] for e in events)
        for evt, count in evt_counts.most_common():
            print(f"    {evt:<25} {count}")

        # Burst analysis
        burst_starts = [e for e in events if e["event_type"] == "BURST_START"]
        burst_ends = [e for e in events if e["event_type"] == "BURST_END"]
        if burst_starts:
            print(f"\n  Burst events: {len(burst_starts)} starts, {len(burst_ends)} ends")
            for bs in burst_starts[:5]:
                d = bs.get("details", {})
                print(f"    h={bs['height']} lag={d.get('lag','?')} "
                      f"last3={d.get('last3','?')}")

        # Stall analysis
        stalls_40 = [e for e in events if e["event_type"] == "STALL40_START"]
        stalls_60 = [e for e in events if e["event_type"] == "STALL60_START"]
        if stalls_40 or stalls_60:
            print(f"\n  Stalls: {len(stalls_40)} >40m, {len(stalls_60)} >60m")

    # ── Live sample statistics ──
    if live:
        print(f"\n{'─'*70}")
        print(f"  LIVE SAMPLES ({len(live)} snapshots)")
        print(f"{'─'*70}")

        stalls = [s.get("stall_seconds", 0) for s in live]
        as_active = sum(1 for s in live if s.get("anti_stall_active"))
        print(f"  Anti-stall active: {as_active}/{len(live)} samples ({as_active/len(live)*100:.1f}%)")
        print(f"  Max stall observed: {max(stalls)/60:.0f}m")

    # ── Save report ──
    report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(report_dir, exist_ok=True)

    rpt_path = os.path.join(report_dir, "mode_arbiter_observation_report.md")
    with open(rpt_path, "w") as f:
        f.write("# Mode Arbiter Observation Report\n\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()}Z\n\n")
        f.write(f"- Block samples: {len(blocks)}\n")
        f.write(f"- Live samples: {len(live)}\n")
        f.write(f"- Events: {len(events)}\n\n")
        if blocks:
            intervals = [b["interval_sec"] for b in blocks if b.get("interval_sec",0)>0]
            if intervals:
                f.write(f"## Block Intervals\n\n")
                f.write(f"- Mean: {statistics.mean(intervals)/60:.1f}m\n")
                f.write(f"- Median: {statistics.median(intervals)/60:.1f}m\n")
                f.write(f"- >20m: {sum(1 for i in intervals if i>=1200)}\n")
                f.write(f"- >40m: {sum(1 for i in intervals if i>=2400)}\n")
                f.write(f"- >60m: {sum(1 for i in intervals if i>=3600)}\n\n")
        if events:
            evt_counts = Counter(e["event_type"] for e in events)
            f.write(f"## Events\n\n")
            for evt, count in evt_counts.most_common():
                f.write(f"- {evt}: {count}\n")
        f.write(f"\n---\n*Raw data for future Mode Arbiter design. No inference applied.*\n")

    json_path = os.path.join(report_dir, "mode_arbiter_observation_report.json")
    summary = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "block_samples": len(blocks),
        "live_samples": len(live),
        "events": len(events),
        "event_counts": dict(Counter(e["event_type"] for e in events)) if events else {},
    }
    if blocks:
        intervals = [b["interval_sec"] for b in blocks if b.get("interval_sec",0)>0]
        if intervals:
            summary["mean_interval"] = round(statistics.mean(intervals))
            summary["blocks_over_20m"] = sum(1 for i in intervals if i>=1200)
            summary["blocks_over_40m"] = sum(1 for i in intervals if i>=2400)
            summary["blocks_over_60m"] = sum(1 for i in intervals if i>=3600)
            summary["ceiling_hits"] = sum(1 for b in blocks if b.get("profile_ceiling_applied"))
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  Saved: {rpt_path}")
    print(f"  Saved: {json_path}")
    print(f"\n{'═'*70}")


if __name__ == "__main__":
    main()

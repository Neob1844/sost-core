#!/usr/bin/env python3
"""
PoPC Monitor — live dashboard for the PoPC Pool.

Shows pool balance, active contract count, committed rewards, PUR (pool
utilization ratio), current reward tier, and dynamic factor. Alerts when
PUR crosses the 50% warning threshold or when the pool is approaching
the automatic lockdown (PUR >= 80%).

Read-only. Polls the sost-node RPC once per invocation (or on a loop with
--watch). Does not touch consensus, does not write to the chain.

Usage (one-shot):
    python3 scripts/popc_monitor.py \\
        --rpc-user USER --rpc-pass PASS

Usage (continuous, refresh every 30s):
    python3 scripts/popc_monitor.py \\
        --rpc-user USER --rpc-pass PASS --watch 30

Usage (JSON output for downstream tooling):
    python3 scripts/popc_monitor.py \\
        --rpc-user USER --rpc-pass PASS --json
"""
import argparse
import base64
import json
import sys
import time
import urllib.request


# ── Mirror of include/sost/popc.h constants ─────────────────────────
POPC_POOL_ADDRESS = "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"

POPC_DURATIONS = [1, 3, 6, 9, 12]          # months
POPC_REWARD_RATES = [100, 400, 900, 1500, 2200]  # bps of bond — Model A
ESCROW_REWARD_RATES = [40, 150, 350, 550, 800]   # bps of gold value — Model B

POPC_TIER_THRESHOLDS = [25, 50, 100, 200, 500, 1000]
POPC_TIER_MULTIPLIERS = [10000, 7500, 5000, 3000, 1500, 800]  # bps
POPC_TIER_NAMES = [
    "TIER 1 — EARLY ADOPTER",
    "TIER 2 — GROWTH",
    "TIER 3 — MATURE",
    "TIER 4 — ESTABLISHED",
    "TIER 5 — LATE",
    "TIER 6 — MASS",
]

POPC_MAX_ACTIVE_CONTRACTS = 1000
POPC_MAX_REWARD_STOCKS = 100_000_000_000  # 1000 SOST cap per contract
POPC_PROTOCOL_FEE_BPS = 500  # 5% uniform (post whitepaper alignment)

PUR_WARN_BPS = 5000    # our own 50% alert threshold
PUR_FLOOR_BPS = 8000   # node's floor-rate threshold (80%)
PUR_CLOSED_BPS = 10000 # node's hard gate (100%)

STOCKS_PER_SOST = 100_000_000


# ── RPC helpers ─────────────────────────────────────────────────────
def rpc_call(url, user, password, method, params=None, timeout=10):
    if params is None:
        params = []
    payload = json.dumps({"method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(f"RPC error in {method}: {data['error']}")
    return data["result"]


# ── Derived tier / PUR helpers (mirror of C++) ──────────────────────
def compute_tier(active_contracts):
    for i, th in enumerate(POPC_TIER_THRESHOLDS):
        if active_contracts < th:
            return i, POPC_TIER_NAMES[i], POPC_TIER_MULTIPLIERS[i]
    return 6, "TIER 7 — OVERCAP", 500


def compute_dynamic_factor_bps(pur_bps):
    if pur_bps >= PUR_CLOSED_BPS:
        return 0
    if pur_bps <= 0:
        return 10000
    inv = 10000 - pur_bps
    return (inv * inv) // 10000


def reward_rate_for_duration(duration_months):
    try:
        idx = POPC_DURATIONS.index(duration_months)
        return POPC_REWARD_RATES[idx]
    except ValueError:
        return 0


# ── Data collectors ─────────────────────────────────────────────────
def fetch_pool_balance(rpc_url, user, password):
    """
    Sum of unspent outputs on ADDR_POPC_POOL. Returns stocks (integer).
    Tries listunspent with and without address filter because different
    node versions may implement this differently.
    """
    try:
        result = rpc_call(rpc_url, user, password, "listunspent", [POPC_POOL_ADDRESS])
        if isinstance(result, list):
            total = 0
            for u in result:
                amt = u.get("amount", 0)
                # amount may be string SOST or integer stocks depending on node
                if isinstance(amt, str):
                    total += int(float(amt) * STOCKS_PER_SOST)
                elif isinstance(amt, float):
                    total += int(amt * STOCKS_PER_SOST)
                else:
                    total += int(amt)
            return total
    except Exception:
        pass

    # Fallback: scan full UTXO set and filter client-side
    try:
        result = rpc_call(rpc_url, user, password, "listunspent", [])
        if isinstance(result, list):
            total = 0
            for u in result:
                if u.get("address") == POPC_POOL_ADDRESS:
                    amt = u.get("amount", 0)
                    if isinstance(amt, str):
                        total += int(float(amt) * STOCKS_PER_SOST)
                    elif isinstance(amt, float):
                        total += int(amt * STOCKS_PER_SOST)
                    else:
                        total += int(amt)
            return total
    except Exception:
        pass

    return 0


def fetch_active_commitments(rpc_url, user, password):
    """
    Try a few likely RPC method names so the script keeps working as the
    node API evolves. Returns a list of commitment dicts, possibly empty.
    """
    candidates = ["popc_list_active", "popc_status", "popc_active", "list_popc_commitments"]
    for method in candidates:
        try:
            result = rpc_call(rpc_url, user, password, method, [])
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                if "commitments" in result:
                    return result["commitments"]
                if "active" in result:
                    return result["active"]
        except Exception:
            continue
    return []


def estimate_committed_rewards(commitments, active_count):
    """
    Upper-bound estimate of total committed rewards in stocks. For each
    commitment we compute:
        base_reward = bond × reward_rate
        tier_mult = current tier multiplier
        dyn_mult = 10000 (best case at this snapshot)
        reward = base_reward × tier_mult × dyn_mult / (10000 × 10000)
        reward = min(reward, POPC_MAX_REWARD_STOCKS)
        committed += reward × (1 - fee_bps/10000)
    This is a pessimistic view (all commitments paid at current tier rate).
    Reality will be lower because rewards are paid over time and earlier
    commitments were registered at higher tiers.
    """
    _, _, tier_mult = compute_tier(active_count)
    total = 0
    for c in commitments:
        bond_stocks = int(c.get("bond_sost_stocks", 0))
        duration = int(c.get("duration_months", 0))
        reward_bps = reward_rate_for_duration(duration)
        if bond_stocks <= 0 or reward_bps == 0:
            continue
        base_reward = (bond_stocks * reward_bps) // 10000
        scaled = (base_reward * tier_mult) // 10000
        if scaled > POPC_MAX_REWARD_STOCKS:
            scaled = POPC_MAX_REWARD_STOCKS
        net = (scaled * (10000 - POPC_PROTOCOL_FEE_BPS)) // 10000
        total += net
    return total


# ── Rendering ───────────────────────────────────────────────────────
def bar(pct, width=40, filled="█", empty="·"):
    n = int(pct * width / 100)
    n = max(0, min(width, n))
    return filled * n + empty * (width - n)


def color(status):
    # ANSI escapes — safe to strip if stdout is not a TTY
    if not sys.stdout.isatty():
        return "", ""
    codes = {
        "green":  ("\033[32m", "\033[0m"),
        "yellow": ("\033[33m", "\033[0m"),
        "red":    ("\033[31m", "\033[0m"),
        "cyan":   ("\033[36m", "\033[0m"),
        "bold":   ("\033[1m",  "\033[0m"),
    }
    return codes.get(status, ("", ""))


def render_report(data):
    b1, r1 = color("bold")
    g1, gr = color("green")
    y1, yr = color("yellow")
    rd, rr = color("red")
    c1, cr = color("cyan")

    pool_sost = data["pool_balance_stocks"] / STOCKS_PER_SOST
    committed_sost = data["committed_stocks"] / STOCKS_PER_SOST
    available_sost = pool_sost - committed_sost
    pur_pct = data["pur_bps"] / 100.0
    active = data["active_contracts"]
    tier_idx = data["tier_index"]
    tier_name = data["tier_name"]
    tier_mult_pct = data["tier_multiplier_bps"] / 100.0
    dyn_factor_pct = data["dynamic_factor_bps"] / 100.0

    if pur_pct >= 80:
        pur_color, pur_label = (rd, rr), "CRITICAL — registrations locked at 100%"
    elif pur_pct >= 50:
        pur_color, pur_label = (y1, yr), "WARNING — approaching floor rate"
    else:
        pur_color, pur_label = (g1, gr), "HEALTHY"

    cap_pct = (active / POPC_MAX_ACTIVE_CONTRACTS) * 100
    if cap_pct >= 80:
        cap_color = (rd, rr)
    elif cap_pct >= 50:
        cap_color = (y1, yr)
    else:
        cap_color = (g1, gr)

    print()
    print(f"{b1}╔══════════════════════════════════════════════════════════════╗{r1}")
    print(f"{b1}║              PoPC MONITOR — Pool Dashboard                   ║{r1}")
    print(f"{b1}╚══════════════════════════════════════════════════════════════╝{r1}")
    print()
    print(f"  Pool address   : {c1}{POPC_POOL_ADDRESS}{cr}")
    print(f"  Snapshot time  : {data['timestamp']}")
    print()
    print(f"  {b1}POOL BALANCE{r1}")
    print(f"    Total        : {c1}{pool_sost:>14,.4f} SOST{cr}  ({data['pool_balance_stocks']:,} stocks)")
    print(f"    Committed    : {committed_sost:>14,.4f} SOST  (pessimistic estimate)")
    print(f"    Available    : {available_sost:>14,.4f} SOST")
    print()
    print(f"  {b1}POOL UTILIZATION RATIO (PUR){r1}")
    print(f"    {pur_color[0]}{bar(pur_pct):s}{pur_color[1]}  {pur_color[0]}{pur_pct:5.1f}%{pur_color[1]}")
    print(f"    Status       : {pur_color[0]}{pur_label}{pur_color[1]}")
    print(f"    Thresholds   : 50% WARN · 80% FLOOR · 100% CLOSED")
    print()
    print(f"  {b1}ACTIVE CONTRACTS{r1}")
    print(f"    {cap_color[0]}{bar(cap_pct):s}{cap_color[1]}  {cap_color[0]}{active:>4d} / {POPC_MAX_ACTIVE_CONTRACTS}{cap_color[1]}  ({cap_pct:.1f}% of hard cap)")
    print()
    print(f"  {b1}CURRENT REWARD TIER{r1}")
    print(f"    Tier         : {c1}{tier_name}{cr}")
    print(f"    Multiplier   : {c1}{tier_mult_pct:.0f}%{cr}  (base rewards × this)")
    next_tier = POPC_TIER_THRESHOLDS[tier_idx] if tier_idx < len(POPC_TIER_THRESHOLDS) else None
    if next_tier:
        remaining = next_tier - active
        print(f"    Next tier at : {next_tier} active contracts ({remaining} to go)")
    print()
    print(f"  {b1}DYNAMIC REWARD FACTOR{r1}")
    print(f"    Factor (1-PUR)² : {dyn_factor_pct:.1f}%  (smooth taper as pool fills)")
    print()

    # Effective reward examples at the current tier & PUR
    def effective_reward(duration_months, bond_sost):
        rate = reward_rate_for_duration(duration_months)
        base = bond_sost * rate / 10000
        tier_adj = base * (data["tier_multiplier_bps"] / 10000)
        dyn_adj = tier_adj * (data["dynamic_factor_bps"] / 10000)
        fee_adj = dyn_adj * (1 - POPC_PROTOCOL_FEE_BPS / 10000)
        return fee_adj

    print(f"  {b1}EFFECTIVE REWARDS RIGHT NOW (Model A, 100 SOST bond){r1}")
    for d in POPC_DURATIONS:
        r = effective_reward(d, 100)
        pct_of_bond = r / 100 * 100
        print(f"    {d:2d} months → {r:8.4f} SOST net  ({pct_of_bond:5.2f}% of bond)")
    print()

    if pur_pct >= 50:
        print(f"  {rd}⚠  ALERT: PUR is {pur_pct:.1f}% — above the 50% warning line.{rr}")
        if pur_pct >= 80:
            print(f"  {rd}⚠  CRITICAL: floor rate will be applied to new registrations.{rr}")
        if pur_pct >= 100:
            print(f"  {rd}⚠  LOCKED: new registrations are being rejected by the node.{rr}")
        print()


def build_snapshot(rpc_url, user, password):
    pool_balance = fetch_pool_balance(rpc_url, user, password)
    commitments = fetch_active_commitments(rpc_url, user, password)
    active_count = len(commitments)
    committed = estimate_committed_rewards(commitments, active_count)

    if pool_balance > 0:
        pur_bps = min(10000, (committed * 10000) // pool_balance)
    else:
        pur_bps = 10000 if committed > 0 else 0

    tier_idx, tier_name, tier_mult = compute_tier(active_count)
    dyn_factor = compute_dynamic_factor_bps(pur_bps)

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "pool_address": POPC_POOL_ADDRESS,
        "pool_balance_stocks": pool_balance,
        "committed_stocks": committed,
        "available_stocks": max(0, pool_balance - committed),
        "active_contracts": active_count,
        "max_contracts": POPC_MAX_ACTIVE_CONTRACTS,
        "pur_bps": pur_bps,
        "pur_pct": pur_bps / 100.0,
        "tier_index": tier_idx,
        "tier_name": tier_name,
        "tier_multiplier_bps": tier_mult,
        "dynamic_factor_bps": dyn_factor,
        "alert": pur_bps >= PUR_WARN_BPS,
    }


def main():
    ap = argparse.ArgumentParser(
        description="PoPC Monitor — live dashboard for the PoPC Pool")
    ap.add_argument("--rpc", default="http://127.0.0.1:18232")
    ap.add_argument("--rpc-user", required=True)
    ap.add_argument("--rpc-pass", required=True)
    ap.add_argument("--watch", type=int, default=0,
                    help="refresh interval in seconds (0 = one-shot, default)")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of the rendered dashboard")
    args = ap.parse_args()

    def run_once():
        try:
            snap = build_snapshot(args.rpc, args.rpc_user, args.rpc_pass)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return None
        if args.json:
            print(json.dumps(snap, indent=2))
        else:
            render_report(snap)
        return snap

    if args.watch <= 0:
        snap = run_once()
        sys.exit(1 if (snap and snap["alert"]) else 0)

    try:
        while True:
            if not args.json:
                print("\033[2J\033[H", end="")  # clear screen
            run_once()
            time.sleep(args.watch)
    except KeyboardInterrupt:
        print("\nexiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()

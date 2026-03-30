#!/usr/bin/env python3
"""PoPC Model A — Etherscan/Ethereum RPC Custody Verifier

Verifies that PoPC participants still hold their declared XAUT/PAXG
by querying Ethereum balance via public RPC or Etherscan API V2.

Usage:
  python3 popc_etherscan_checker.py --check-all        # verify all registered
  python3 popc_etherscan_checker.py --check 0xADDRESS   # verify one address
  python3 popc_etherscan_checker.py --report             # generate status report
  python3 popc_etherscan_checker.py --daemon             # continuous monitoring
  python3 popc_etherscan_checker.py --calculate 0xADDR   # show reward calculation
"""
import json, os, sys, time, argparse, logging
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── Constants ────────────────────────────────────────────────
XAUT_CONTRACT = "0x68749665FF8D2d112Fa859AA293F07A622782F38"
PAXG_CONTRACT = "0x45804880De22913dAFE09f4980848ECE6EcbAf78"
XAUT_DECIMALS = 6   # XAUT uses 6 decimals
PAXG_DECIMALS = 18  # PAXG uses 18 decimals

# Bond percentage table (ratio = sost_price / gold_oz_price)
BOND_TABLE = [
    (0.0001, 1200),   # 12%
    (0.001,  1500),   # 15%
    (0.01,   2000),   # 20%
    (0.1,    2500),   # 25%
    (0.2,    2600),   # 26%
    (0.3,    2700),   # 27%
    (0.4,    2800),   # 28%
    (0.5,    2900),   # 29%
    (999,    3000),   # 30% max
]

# Reward table (% of bond × 100)
REWARD_TABLE = {1: 100, 3: 400, 6: 900, 9: 1500, 12: 2200}

PROTOCOL_FEE_BPS = 500  # 5%

# Public Ethereum RPC endpoints (no key needed, may be rate-limited)
PUBLIC_RPCS = [
    "https://eth.meowrpc.com",
    "https://1rpc.io/eth",
    "https://ethereum-rpc.publicnode.com",
    "https://rpc.flashbots.net",
]

BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "config" / "popc_checker.json"
REGISTRY_PATH = BASE / "data" / "popc_registry.json"
LOG_PATH = BASE / "logs" / "popc_audit.log"
FAILURES_PATH = BASE / "logs" / "popc_verification_failures.json"

# ── Config ───────────────────────────────────────────────────
def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {
        "etherscan_api_key": "",
        "infura_project_id": "",
        "alchemy_api_key": "",
        "check_interval_minutes": 60,
        "require_2_consecutive_failures": True,
        "slash_cooldown_hours": 48,
        "log_file": str(LOG_PATH),
        "eth_rpc_endpoints": PUBLIC_RPCS,
    }

def load_failures():
    """Load consecutive failure tracker from disk."""
    if FAILURES_PATH.exists():
        with open(FAILURES_PATH) as f:
            return json.load(f)
    return {}

def save_failures(failures):
    """Persist consecutive failure tracker."""
    os.makedirs(FAILURES_PATH.parent, exist_ok=True)
    with open(FAILURES_PATH, "w") as f:
        json.dump(failures, f, indent=2)

def record_failure(address, today_str):
    """Record a custody failure. Returns True if this is the 2nd consecutive failure (slash warranted)."""
    failures = load_failures()
    addr_key = address.lower()
    rec = failures.get(addr_key, {"consecutive": 0, "last_fail_date": "", "first_fail_date": ""})

    if rec["last_fail_date"] == today_str:
        # Already recorded today — no change
        return rec["consecutive"] >= 2

    rec["consecutive"] += 1
    if rec["consecutive"] == 1:
        rec["first_fail_date"] = today_str
    rec["last_fail_date"] = today_str
    failures[addr_key] = rec
    save_failures(failures)
    return rec["consecutive"] >= 2

def clear_failure(address):
    """Clear failure record when address passes verification."""
    failures = load_failures()
    addr_key = address.lower()
    if addr_key in failures:
        del failures[addr_key]
        save_failures(failures)

def load_registry():
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    return []

def save_registry(reg):
    os.makedirs(REGISTRY_PATH.parent, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(reg, f, indent=2)

# ── Ethereum RPC ─────────────────────────────────────────────
def eth_call(rpc_url, contract, address):
    """Call balanceOf(address) on an ERC-20 contract via JSON-RPC."""
    addr_clean = address.lower().replace("0x", "")
    data = "0x70a08231" + "0" * 24 + addr_clean
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": contract, "data": data}, "latest"],
        "id": 1
    }).encode()
    req = Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if "result" in result and result["result"]:
                return int(result["result"], 16)
    except Exception as e:
        pass
    return None

def etherscan_v2_balance(api_key, contract, address):
    """Query balance via Etherscan API V2."""
    if not api_key:
        return None
    url = (f"https://api.etherscan.io/v2/api?chainid=1&module=account"
           f"&action=tokenbalance&contractaddress={contract}"
           f"&address={address}&tag=latest&apikey={api_key}")
    try:
        req = Request(url)
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "1":
                return int(data["result"])
    except Exception:
        pass
    return None

def infura_balance(project_id, contract, address):
    """Query ERC-20 balance via Infura JSON-RPC endpoint."""
    if not project_id:
        return None
    rpc_url = f"https://mainnet.infura.io/v3/{project_id}"
    return eth_call(rpc_url, contract, address)

def alchemy_balance(api_key, contract, address):
    """Query ERC-20 balance via Alchemy JSON-RPC endpoint."""
    if not api_key:
        return None
    rpc_url = f"https://eth-mainnet.g.alchemy.com/v2/{api_key}"
    return eth_call(rpc_url, contract, address)

def get_balance(config, contract, address, decimals):
    """Get token balance with multi-provider fallback.

    Fallback order: Etherscan V2 → Infura → Alchemy → public RPCs.
    Returns (float_balance, source_string) or (None, "all_failed").
    """
    # 1. Try Etherscan V2
    api_key = config.get("etherscan_api_key", "")
    raw = etherscan_v2_balance(api_key, contract, address)
    if raw is not None:
        return raw / (10 ** decimals), "etherscan_v2"

    # 2. Try Infura (named provider, requires free registration)
    project_id = config.get("infura_project_id", "")
    raw = infura_balance(project_id, contract, address)
    if raw is not None:
        return raw / (10 ** decimals), "infura"

    # 3. Try Alchemy (named provider, requires free registration)
    alchemy_key = config.get("alchemy_api_key", "")
    raw = alchemy_balance(alchemy_key, contract, address)
    if raw is not None:
        return raw / (10 ** decimals), "alchemy"

    # 4. Try public RPCs (no key needed, may be rate-limited)
    public_rpcs = config.get("public_rpc_urls",
                              config.get("eth_rpc_endpoints", PUBLIC_RPCS))
    for rpc in public_rpcs:
        raw = eth_call(rpc, contract, address)
        if raw is not None:
            return raw / (10 ** decimals), rpc
        time.sleep(0.3)  # rate limit between public RPCs

    return None, "all_failed"

# ── Bond & Reward Calculation ────────────────────────────────
def bond_pct_from_ratio(ratio):
    for threshold, pct in BOND_TABLE:
        if ratio < threshold:
            return pct
    return 3000

def calculate_rewards(gold_oz, sost_price_usd=1.0, gold_price_usd=3000.0):
    """Calculate bond and rewards for all durations."""
    ratio = sost_price_usd / gold_price_usd
    bond_pct = bond_pct_from_ratio(ratio)
    gold_value_usd = gold_oz * gold_price_usd
    bond_usd = gold_value_usd * bond_pct / 10000
    bond_sost = bond_usd / sost_price_usd

    results = []
    for months in [1, 3, 6, 9, 12]:
        reward_pct = REWARD_TABLE[months]
        base_reward = bond_sost * reward_pct / 10000
        protocol_fee = base_reward * PROTOCOL_FEE_BPS / 10000
        user_reward = base_reward - protocol_fee
        monthly_reward = user_reward / months if months > 0 else 0

        results.append({
            "months": months,
            "bond_sost": round(bond_sost, 4),
            "reward_pct": reward_pct / 100,
            "base_reward_sost": round(base_reward, 4),
            "protocol_fee_sost": round(protocol_fee, 4),
            "user_reward_sost": round(user_reward, 4),
            "monthly_reward_sost": round(monthly_reward, 4),
            "total_returned_sost": round(bond_sost + user_reward, 4),
        })

    return {
        "gold_oz": gold_oz,
        "gold_value_usd": gold_value_usd,
        "sost_price_usd": sost_price_usd,
        "gold_price_usd": gold_price_usd,
        "ratio": round(ratio, 6),
        "bond_pct": bond_pct / 100,
        "bond_usd": round(bond_usd, 2),
        "bond_sost": round(bond_sost, 4),
        "durations": results,
    }

# ── Check Single Address ─────────────────────────────────────
def check_address(config, entry):
    """Verify custody for a single PoPC participant.

    Double-verification rule: if require_2_consecutive_failures is enabled,
    a CUSTODY_VIOLATION is only escalated to slash_queue after 2 consecutive
    failures on different days. A single transient failure is recorded but
    does NOT immediately trigger a slash.
    """
    eth_addr = entry["eth_address"]
    declared_xaut = entry.get("declared_xaut", 0)
    declared_paxg = entry.get("declared_paxg", 0)
    today_str = time.strftime("%Y-%m-%d")
    require_double = config.get("require_2_consecutive_failures", True)

    result = {
        "eth_address": eth_addr,
        "participant": entry.get("participant", "unknown"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Check XAUT
    if declared_xaut > 0:
        bal, src = get_balance(config, XAUT_CONTRACT, eth_addr, XAUT_DECIMALS)
        result["xaut_declared"] = declared_xaut
        result["xaut_actual"] = bal
        result["xaut_source"] = src
        result["xaut_ok"] = bal is not None and bal >= declared_xaut
    else:
        result["xaut_ok"] = True

    # Check PAXG
    if declared_paxg > 0:
        bal, src = get_balance(config, PAXG_CONTRACT, eth_addr, PAXG_DECIMALS)
        result["paxg_declared"] = declared_paxg
        result["paxg_actual"] = bal
        result["paxg_source"] = src
        result["paxg_ok"] = bal is not None and bal >= declared_paxg
    else:
        result["paxg_ok"] = True

    # Overall status
    if result["xaut_ok"] and result["paxg_ok"]:
        if result.get("xaut_actual") is None and result.get("paxg_actual") is None:
            result["status"] = "RPC_UNAVAILABLE"
        else:
            result["status"] = "VERIFIED"
            # Clear any previous failure record on successful verification
            clear_failure(eth_addr)
    else:
        # Custody shortfall detected — apply double-verification rule
        if require_double:
            slash_warranted = record_failure(eth_addr, today_str)
            failures = load_failures()
            rec = failures.get(eth_addr.lower(), {})
            consecutive = rec.get("consecutive", 1)
            if slash_warranted:
                result["status"] = "CUSTODY_VIOLATION"
                result["slash_queue"] = True
                result["consecutive_failures"] = consecutive
            else:
                # First failure — warn but do not slash yet
                result["status"] = "CUSTODY_VIOLATION_PENDING"
                result["slash_queue"] = False
                result["consecutive_failures"] = consecutive
                result["note"] = ("First failure recorded. Slash requires 2 consecutive "
                                  "failures on different days.")
        else:
            # Immediate slash (double-verification disabled)
            result["status"] = "CUSTODY_VIOLATION"
            result["slash_queue"] = True

    return result

# ── Logging ──────────────────────────────────────────────────
def setup_logging(log_file):
    os.makedirs(Path(log_file).parent, exist_ok=True)
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logging.getLogger().addHandler(logging.StreamHandler())

# ── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="PoPC Model A Custody Verifier")
    parser.add_argument("--check-all", action="store_true", help="Check all registered addresses")
    parser.add_argument("--check", type=str, help="Check single Ethereum address")
    parser.add_argument("--report", action="store_true", help="Generate status report")
    parser.add_argument("--daemon", action="store_true", help="Continuous monitoring loop")
    parser.add_argument("--calculate", type=str, help="Show reward calculation for address")
    args = parser.parse_args()

    config = load_config()
    registry = load_registry()
    setup_logging(config.get("log_file", str(LOG_PATH)))

    print("=" * 62)
    print("  PoPC Model A — Custody Verifier")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62)

    if args.check:
        # Find in registry or create ad-hoc entry
        entry = next((e for e in registry if e["eth_address"].lower() == args.check.lower()), None)
        if not entry:
            entry = {"eth_address": args.check, "declared_xaut": 0, "declared_paxg": 0, "participant": "ad-hoc"}
        result = check_address(config, entry)
        print(json.dumps(result, indent=2))
        logging.info(f"CHECK {result['eth_address']}: {result['status']}")

    elif args.check_all:
        print(f"\nChecking {len(registry)} registered addresses...\n")
        for entry in registry:
            result = check_address(config, entry)
            status = result["status"]
            xaut = result.get("xaut_actual", "N/A")
            paxg = result.get("paxg_actual", "N/A")
            print(f"  {entry.get('participant','?')}: {status} (XAUT={xaut}, PAXG={paxg})")
            logging.info(f"CHECK-ALL {result['eth_address']}: {status}")
            time.sleep(0.5)  # rate limit

    elif args.calculate:
        entry = next((e for e in registry if e["eth_address"].lower() == args.calculate.lower()), None)
        if not entry:
            print(f"Address {args.calculate} not in registry")
            return
        gold_oz = entry.get("declared_xaut", 0) + entry.get("declared_paxg", 0)
        if gold_oz <= 0:
            print("No gold declared")
            return

        # Pre-launch: use reference prices
        calc = calculate_rewards(gold_oz, sost_price_usd=1.0, gold_price_usd=3000.0)

        print(f"\n  Participant: {entry.get('participant', '?')}")
        print(f"  Gold: {gold_oz} oz (~${calc['gold_value_usd']:,.0f} USD)")
        print(f"  SOST price: ${calc['sost_price_usd']} (pre-launch reference)")
        print(f"  Ratio: {calc['ratio']} → Bond: {calc['bond_pct']}%")
        print(f"  Bond: {calc['bond_sost']} SOST (${calc['bond_usd']} USD)")
        print()
        print(f"  {'Duration':<10} {'Bond SOST':<12} {'Reward%':<10} {'Reward SOST':<14} {'Monthly':<12} {'Total Return'}")
        print(f"  {'-'*10} {'-'*12} {'-'*10} {'-'*14} {'-'*12} {'-'*14}")
        for d in calc["durations"]:
            print(f"  {d['months']:>2} months  {d['bond_sost']:<12} {d['reward_pct']:<10}% {d['user_reward_sost']:<14} {d['monthly_reward_sost']:<12} {d['total_returned_sost']}")
        print()
        print(f"  PoPC Pool accumulation: ~1.963 SOST/block × ~4,320 blocks/month = ~8,480 SOST/month")
        print(f"  If sole participant: pool can sustain payments indefinitely")

    elif args.report:
        print(f"\n  Registry: {len(registry)} participant(s)\n")
        for entry in registry:
            print(f"  {entry.get('participant','?')}")
            print(f"    ETH: {entry['eth_address']}")
            print(f"    XAUT: {entry.get('declared_xaut', 0)} | PAXG: {entry.get('declared_paxg', 0)}")
            print(f"    Status: {entry.get('status', '?')}")
            print()

    elif args.daemon:
        interval = config.get("check_interval_minutes", 60) * 60
        print(f"\n  Daemon mode: checking every {interval//60} minutes\n")
        while True:
            for entry in registry:
                result = check_address(config, entry)
                logging.info(f"DAEMON {result['eth_address']}: {result['status']}")
                if result["status"] == "CUSTODY_VIOLATION":
                    logging.warning(f"!!! CUSTODY VIOLATION (slash queued): {result['eth_address']}")
                elif result["status"] == "CUSTODY_VIOLATION_PENDING":
                    logging.warning(f"!!! CUSTODY WARNING (1st failure, not yet slashed): "
                                    f"{result['eth_address']} — {result.get('note','')}")
                time.sleep(0.5)
            time.sleep(interval)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()

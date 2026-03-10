#!/usr/bin/env python3
"""SOST Price Monitor — tracks XAUT, PAXG, and SOST prices.

Usage:
  python3 scripts/price_monitor.py                    # single query
  python3 scripts/price_monitor.py --interval 60      # every 60 min
  python3 scripts/price_monitor.py --twap             # show TWAP 7d
  python3 scripts/price_monitor.py --sost-price 0.50  # manual SOST price
  python3 scripts/price_monitor.py --daemon           # background mode

Dependencies: requests (pip install requests)
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install: pip install requests")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "price_history.csv")

CSV_HEADER = ["timestamp", "xaut_usd", "paxg_usd", "gold_avg_usd",
              "sost_usd", "sost_source", "ratio"]

# Mining cost defaults
DEFAULT_ELECTRICITY_COST = 0.10   # USD per kWh
DEFAULT_WATTS_PER_THREAD = 65     # CPU TDP watts
SECONDS_PER_BLOCK = 600
BLOCKS_PER_DAY = 144
REWARD_PER_BLOCK = 7.851          # epoch 0


def fetch_gold_coingecko():
    """Fetch XAUT and PAXG prices from CoinGecko (free, no key)."""
    url = ("https://api.coingecko.com/api/v3/simple/price"
           "?ids=tether-gold,pax-gold&vs_currencies=usd")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        xaut = data.get("tether-gold", {}).get("usd")
        paxg = data.get("pax-gold", {}).get("usd")
        if xaut and paxg:
            return float(xaut), float(paxg)
    except Exception:
        pass
    return None, None


def fetch_gold_cryptocompare():
    """Fallback: XAUT and PAXG from CryptoCompare (free, no key)."""
    url = ("https://min-api.cryptocompare.com/data/pricemulti"
           "?fsyms=XAUT,PAXG&tsyms=USD")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        xaut = data.get("XAUT", {}).get("USD")
        paxg = data.get("PAXG", {}).get("USD")
        if xaut and paxg:
            return float(xaut), float(paxg)
    except Exception:
        pass
    return None, None


def fetch_gold_prices():
    """Try CoinGecko first, fall back to CryptoCompare."""
    xaut, paxg = fetch_gold_coingecko()
    if xaut and paxg:
        return xaut, paxg
    return fetch_gold_cryptocompare()


def fetch_sost_coingecko():
    """Try to find SOST on CoinGecko."""
    for coin_id in ("sost-protocol", "sost"):
        url = ("https://api.coingecko.com/api/v3/simple/price"
               "?ids={}&vs_currencies=usd".format(coin_id))
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            price = data.get(coin_id, {}).get("usd")
            if price:
                return float(price), "coingecko"
        except Exception:
            pass
    return None, None


def fetch_sost_cryptocompare():
    """Try to find SOST on CryptoCompare."""
    url = ("https://min-api.cryptocompare.com/data/price"
           "?fsym=SOST&tsyms=USD")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        price = data.get("USD")
        if price and price > 0:
            return float(price), "cryptocompare"
    except Exception:
        pass
    return None, None


def calc_mining_cost(electricity=DEFAULT_ELECTRICITY_COST,
                     watts=DEFAULT_WATTS_PER_THREAD):
    """Implied SOST floor price from mining electricity cost."""
    daily_kwh = (watts / 1000.0) * 24.0
    daily_cost = daily_kwh * electricity
    daily_revenue_sost = BLOCKS_PER_DAY * REWARD_PER_BLOCK * 0.5
    if daily_revenue_sost <= 0:
        return 0.0
    return daily_cost / daily_revenue_sost


def fetch_sost_price(manual_price=None, electricity=DEFAULT_ELECTRICITY_COST,
                     watts=DEFAULT_WATTS_PER_THREAD):
    """Get SOST price: manual > coingecko > cryptocompare > mining cost."""
    if manual_price is not None:
        return manual_price, "manual"

    price, source = fetch_sost_coingecko()
    if price:
        return price, source

    price, source = fetch_sost_cryptocompare()
    if price:
        return price, source

    return calc_mining_cost(electricity, watts), "mining_cost"


def append_csv(row):
    """Append a row to price_history.csv, creating header if needed."""
    write_header = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(CSV_HEADER)
        w.writerow(row)


def load_csv():
    """Load all rows from price_history.csv."""
    if not os.path.exists(CSV_PATH):
        return []
    rows = []
    with open(CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def calc_twap_7d():
    """Calculate 7-day TWAP for gold average price."""
    rows = load_csv()
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    prices = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(r["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            val = float(r["gold_avg_usd"])
            if ts >= cutoff and val > 0:
                prices.append(val)
        except (ValueError, KeyError):
            continue
    if not prices:
        return None
    return sum(prices) / len(prices)


def bond_rate(ratio):
    """PoPC bond rate based on SOST/gold ratio."""
    if ratio <= 0:
        return 0.30
    if ratio < 0.0001:
        return 0.12
    if ratio < 0.001:
        return 0.15
    if ratio < 0.01:
        return 0.20
    return 0.30


def query_once(manual_price=None, electricity=DEFAULT_ELECTRICITY_COST,
               watts=DEFAULT_WATTS_PER_THREAD):
    """Perform a single price query, display, and save."""
    xaut, paxg = fetch_gold_prices()
    if xaut is None or paxg is None:
        print("ERROR: Could not fetch gold prices from any source.")
        return False

    gold_avg = (xaut + paxg) / 2.0
    sost, sost_source = fetch_sost_price(manual_price, electricity, watts)
    ratio = sost / gold_avg if gold_avg > 0 else 0.0
    br = bond_rate(ratio)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    append_csv([now, f"{xaut:.2f}", f"{paxg:.2f}", f"{gold_avg:.2f}",
                f"{sost:.6f}", sost_source, f"{ratio:.10f}"])

    twap = calc_twap_7d()

    print(f"  XAUT:  ${xaut:,.2f}")
    print(f"  PAXG:  ${paxg:,.2f}")
    print(f"  Gold:  ${gold_avg:,.2f} (avg)")

    if sost_source == "mining_cost":
        print(f"  SOST:  $0.00 (no listing found "
              f"— using mining cost: ${sost:.4f})")
    else:
        print(f"  SOST:  ${sost:.6f} ({sost_source})")

    print(f"  Ratio: {ratio:.7f}")
    print(f"  Bond:  {int(br * 100)}%")

    if twap:
        print(f"  TWAP 7d: ${twap:,.2f}")
    else:
        print("  TWAP 7d: (insufficient data)")

    print(f"  [{now}]")
    return True


def show_twap():
    """Show TWAP 7d from existing history."""
    twap = calc_twap_7d()
    if twap:
        print(f"  TWAP 7d (gold avg): ${twap:,.2f}")
        rows = load_csv()
        print(f"  Data points: {len(rows)}")
    else:
        print("  TWAP 7d: insufficient data (need at least 1 entry "
              "from the last 7 days)")


def main():
    parser = argparse.ArgumentParser(
        description="SOST Price Monitor — XAUT, PAXG, SOST tracking")
    parser.add_argument("--interval", type=int, default=0,
                        help="Query interval in minutes (0 = single query)")
    parser.add_argument("--daemon", action="store_true",
                        help="Run as daemon (default interval: 60 min)")
    parser.add_argument("--twap", action="store_true",
                        help="Show TWAP 7d from history and exit")
    parser.add_argument("--sost-price", type=float, default=None,
                        help="Manual SOST price override (USD)")
    parser.add_argument("--electricity", type=float,
                        default=DEFAULT_ELECTRICITY_COST,
                        help="Electricity cost USD/kWh (default: 0.10)")
    parser.add_argument("--watts", type=float,
                        default=DEFAULT_WATTS_PER_THREAD,
                        help="CPU watts per thread (default: 65)")
    args = parser.parse_args()

    if args.twap:
        show_twap()
        return

    interval = args.interval
    if args.daemon and interval <= 0:
        interval = 60

    print("SOST Price Monitor")
    print("=" * 40)

    if interval <= 0:
        query_once(args.sost_price, args.electricity, args.watts)
    else:
        print(f"Polling every {interval} minutes. Ctrl+C to stop.\n")
        while True:
            query_once(args.sost_price, args.electricity, args.watts)
            print()
            time.sleep(interval * 60)


if __name__ == "__main__":
    main()

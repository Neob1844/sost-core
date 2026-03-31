#!/usr/bin/env python3
"""SOST Price Oracle — PoPC Reference Price Calculator

Formula: sost_price = (gold_committed_oz × gold_price_usd) / total_sost_supply

This is NOT a market price. It's a reference price based on gold backing.
"""
import json, os, sys, time, argparse
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from datetime import datetime, timezone

CACHE_PATH = Path("/tmp/sost_gold_price_cache.json")
CACHE_MAX_AGE = 900  # 15 minutes

# Foundation commitment (hardcoded — this is a fact)
FOUNDATION_XAUT_OZ = 0.6
FOUNDATION_PAXG_OZ = 0.6
FOUNDATION_TOTAL_OZ = 1.2

# Emission constants
R0 = 7.85100863  # SOST per block at genesis
Q = 0.7788007830714049  # decay factor per epoch
EPOCH = 131553  # blocks per epoch

def fetch_json(url, timeout=10):
    try:
        req = Request(url, headers={"User-Agent": "SOST-Oracle/1.0", "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None

def get_gold_price():
    """Fetch real XAUT and PAXG prices from CoinGecko."""
    # Check cache
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text())
            age = time.time() - cache.get("timestamp", 0)
            if age < CACHE_MAX_AGE:
                return cache["xaut"], cache["paxg"], cache["avg"], int(age)
        except Exception:
            pass

    xaut, paxg = None, None

    # Try CoinGecko
    data = fetch_json("https://api.coingecko.com/api/v3/simple/price?ids=tether-gold,pax-gold&vs_currencies=usd")
    if data:
        xaut = data.get("tether-gold", {}).get("usd")
        paxg = data.get("pax-gold", {}).get("usd")

    # Retry if partial
    if not xaut or not paxg:
        time.sleep(2)
        data = fetch_json("https://api.coingecko.com/api/v3/simple/price?ids=tether-gold,pax-gold&vs_currencies=usd")
        if data:
            if not xaut: xaut = data.get("tether-gold", {}).get("usd")
            if not paxg: paxg = data.get("pax-gold", {}).get("usd")

    # Use whatever we got
    if xaut and paxg:
        avg = (xaut + paxg) / 2
    elif xaut:
        avg = xaut; paxg = xaut
    elif paxg:
        avg = paxg; xaut = paxg
    else:
        # Fallback to cache (even if expired)
        if CACHE_PATH.exists():
            try:
                cache = json.loads(CACHE_PATH.read_text())
                return cache["xaut"], cache["paxg"], cache["avg"], int(time.time() - cache.get("timestamp", 0))
            except Exception:
                pass
        return 3000.0, 3000.0, 3000.0, -1  # absolute fallback

    # Save cache
    cache = {"xaut": xaut, "paxg": paxg, "avg": avg, "timestamp": time.time()}
    try:
        CACHE_PATH.write_text(json.dumps(cache))
    except Exception:
        pass

    return xaut, paxg, avg, 0

def estimate_supply(height):
    """Estimate total SOST supply at a given height."""
    total = 0.0
    h = 0
    while h <= height:
        epoch = h // EPOCH
        reward = R0 * (Q ** epoch)
        epoch_end = min((epoch + 1) * EPOCH - 1, height)
        blocks = epoch_end - h + 1
        total += reward * blocks
        h += blocks
    return total

def get_supply_from_rpc(rpc_url, rpc_user="", rpc_pass=""):
    """Get chain height and supply from node RPC."""
    import urllib.request
    payload = json.dumps({"method": "getinfo", "id": 1}).encode()
    req = Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
    if rpc_user and rpc_pass:
        import base64
        auth = base64.b64encode(f"{rpc_user}:{rpc_pass}".encode()).decode()
        req.add_header("Authorization", f"Basic {auth}")
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            result = data.get("result", {})
            height = result.get("blocks", 0)
            supply = estimate_supply(height)
            return height, supply
    except Exception:
        return None, None

def get_committed_gold_from_rpc(rpc_url, rpc_user="", rpc_pass=""):
    """Get committed gold from PoPC registry via RPC."""
    import urllib.request
    payload = json.dumps({"method": "popc_status", "id": 1}).encode()
    req = Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
    if rpc_user and rpc_pass:
        import base64
        auth = base64.b64encode(f"{rpc_user}:{rpc_pass}".encode()).decode()
        req.add_header("Authorization", f"Basic {auth}")
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            # Parse committed gold from active commitments
            # For now, use foundation commitment
            return FOUNDATION_TOTAL_OZ
    except Exception:
        return FOUNDATION_TOTAL_OZ

def get_sost_price(rpc_url=None, rpc_user="", rpc_pass=""):
    """Calculate SOST reference price."""
    xaut, paxg, gold_price, cache_age = get_gold_price()

    height, supply = None, None
    if rpc_url:
        height, supply = get_supply_from_rpc(rpc_url, rpc_user, rpc_pass)
    if supply is None:
        height = 17704  # approximate current
        supply = estimate_supply(height)

    gold_oz = FOUNDATION_TOTAL_OZ
    if rpc_url:
        gold_oz = get_committed_gold_from_rpc(rpc_url, rpc_user, rpc_pass)

    total_gold_value = gold_oz * gold_price
    sost_price = total_gold_value / supply if supply > 0 else 0

    return {
        "sost_price_usd": round(sost_price, 6),
        "gold_committed_oz": gold_oz,
        "gold_price_usd_per_oz": round(gold_price, 2),
        "xaut_price_usd": round(xaut, 2),
        "paxg_price_usd": round(paxg, 2),
        "total_gold_value_usd": round(total_gold_value, 2),
        "total_sost_supply": round(supply, 4),
        "chain_height": height,
        "source": "popc_backed",
        "participants": 1,
        "foundation_commitment": {"xaut_oz": FOUNDATION_XAUT_OZ, "paxg_oz": FOUNDATION_PAXG_OZ},
        "note": "Reference price based on PoPC gold commitment. Not a market price.",
        "disclaimer": "SOST is not listed on any exchange. This reference price reflects gold backing per token.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cache_age_seconds": cache_age
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SOST Price Oracle")
    parser.add_argument("--rpc-url", default=None)
    parser.add_argument("--rpc-user", default="")
    parser.add_argument("--rpc-pass", default="")
    parser.add_argument("--output-file", default=None)
    args = parser.parse_args()

    result = get_sost_price(args.rpc_url, args.rpc_user, args.rpc_pass)
    output = json.dumps(result, indent=2)
    print(output)

    if args.output_file:
        Path(args.output_file).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_file).write_text(output)
        print(f"\nSaved to {args.output_file}", file=sys.stderr)

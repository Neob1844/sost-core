#!/usr/bin/env python3
"""
PoPC Oracle — Read-only Etherscan audit tool for active commitments.

For each active PoPC commitment registered in the local sost-node, queries
the Ethereum mainnet balance of the declared XAUT/PAXG wallet and compares
it to the committed gold amount. Prints a pass/fail report and writes a
CSV snapshot for archival.

NO consensus interaction. NO writes to the chain. NO signing. This is a
manual audit helper until a daemon version is built.

Usage:
    python3 scripts/popc_oracle.py \\
        --rpc-user USER --rpc-pass PASS \\
        --etherscan-key YOUR_ETHERSCAN_API_KEY \\
        --csv /tmp/popc_audit_$(date +%Y%m%d).csv

Or in single-wallet spot-check mode:
    python3 scripts/popc_oracle.py \\
        --etherscan-key KEY \\
        --check-wallet 0xABC... --token XAUT --min-mg 31103

Get a free Etherscan API key at https://etherscan.io/apis
Free tier: 5 req/s, 100k req/day. More than enough for manual audit.
"""
import argparse
import base64
import csv
import json
import sys
import time
import urllib.request
import urllib.parse
from decimal import Decimal


# ── Ethereum mainnet token contracts ────────────────────────────────
TOKEN_INFO = {
    "XAUT": {
        "contract": "0x68749665FF8D2d112Fa859AA293F07A622782F38",
        "decimals": 6,
        "name": "Tether Gold",
    },
    "PAXG": {
        "contract": "0x45804880De22913dAFE09f4980848ECE6EcbAf78",
        "decimals": 18,
        "name": "Pax Gold",
    },
}

# 1 troy ounce = 31.1034768 grams = 31103.4768 mg
TROY_OZ_IN_MG = Decimal("31103.4768")


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


def etherscan_token_balance(api_key, contract, wallet, timeout=15):
    """
    Query ERC-20 token balance via Etherscan. Returns raw integer balance
    (needs decimal conversion). Raises on HTTP error or API error response.
    """
    params = {
        "module": "account",
        "action": "tokenbalance",
        "contractaddress": contract,
        "address": wallet,
        "tag": "latest",
        "apikey": api_key,
    }
    url = "https://api.etherscan.io/api?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "sost-popc-oracle/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    # Etherscan returns status="1" on success, "0" on error
    if data.get("status") != "1":
        raise RuntimeError(f"Etherscan error: {data.get('message', 'unknown')} "
                           f"({data.get('result', '')})")
    return int(data["result"])


def raw_to_tokens(raw_balance, decimals):
    """Convert Etherscan raw integer balance to human token units (Decimal)."""
    return Decimal(raw_balance) / (Decimal(10) ** decimals)


def tokens_to_mg(tokens):
    """Convert token units (troy oz) to milligrams."""
    return tokens * TROY_OZ_IN_MG


def fetch_active_commitments(rpc_url, rpc_user, rpc_pass):
    """
    Pull active PoPC commitments from the local node. Tries a few possible
    RPC names because the node API is evolving; bail with a clear message
    if none work.
    """
    candidates = ["popc_list_active", "popc_status", "popc_active", "list_popc_commitments"]
    for method in candidates:
        try:
            result = rpc_call(rpc_url, rpc_user, rpc_pass, method, [])
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "commitments" in result:
                return result["commitments"]
            if isinstance(result, dict) and "active" in result:
                return result["active"]
        except Exception:
            continue
    raise RuntimeError(
        "Could not fetch active commitments from node. Tried: "
        + ", ".join(candidates)
        + ". Check that your node exposes one of these RPC methods and that"
        + " PoPC is activated (block >= 5000 on mainnet)."
    )


def audit_commitment(c, api_key, rate_delay):
    """
    Audit a single commitment dict. Returns a result row ready for reporting.
    Gracefully handles missing fields and Etherscan errors.
    """
    cid = c.get("commitment_id", "?")[:16] + "..."
    user_pkh = c.get("user_pkh", "?")
    eth_wallet = c.get("eth_wallet", "").strip()
    token = c.get("gold_token", "").upper()
    committed_mg = int(c.get("gold_amount_mg", 0))

    if not eth_wallet or not token:
        return {
            "commitment_id": cid,
            "user": user_pkh,
            "token": token or "?",
            "wallet": eth_wallet or "(empty)",
            "committed_mg": committed_mg,
            "balance_mg": 0,
            "delta_mg": -committed_mg,
            "status": "SKIP",
            "note": "missing eth_wallet or gold_token",
        }

    if token not in TOKEN_INFO:
        return {
            "commitment_id": cid,
            "user": user_pkh,
            "token": token,
            "wallet": eth_wallet,
            "committed_mg": committed_mg,
            "balance_mg": 0,
            "delta_mg": -committed_mg,
            "status": "ERROR",
            "note": f"unknown token {token} (not XAUT/PAXG)",
        }

    info = TOKEN_INFO[token]
    try:
        raw = etherscan_token_balance(api_key, info["contract"], eth_wallet)
        time.sleep(rate_delay)  # respect Etherscan rate limit
    except Exception as e:
        return {
            "commitment_id": cid,
            "user": user_pkh,
            "token": token,
            "wallet": eth_wallet,
            "committed_mg": committed_mg,
            "balance_mg": 0,
            "delta_mg": -committed_mg,
            "status": "ERROR",
            "note": f"etherscan: {e}",
        }

    tokens = raw_to_tokens(raw, info["decimals"])
    balance_mg = int(tokens_to_mg(tokens))
    delta_mg = balance_mg - committed_mg

    if balance_mg >= committed_mg:
        status = "PASS"
        note = f"{tokens:.6f} {token} held (+{delta_mg} mg surplus)"
    else:
        status = "FAIL"
        note = f"{tokens:.6f} {token} held ({delta_mg} mg deficit)"

    return {
        "commitment_id": cid,
        "user": user_pkh,
        "token": token,
        "wallet": eth_wallet,
        "committed_mg": committed_mg,
        "balance_mg": balance_mg,
        "delta_mg": delta_mg,
        "status": status,
        "note": note,
    }


def print_report(rows):
    """Nice terminal report with color hints."""
    if not rows:
        print("No commitments to audit.")
        return
    print("\n" + "=" * 98)
    print(f"{'COMMITMENT':<20} {'TOKEN':<6} {'COMMIT mg':>10} "
          f"{'WALLET mg':>12} {'DELTA':>10} {'STATUS':<6}  NOTE")
    print("-" * 98)
    for r in rows:
        print(f"{r['commitment_id']:<20} {r['token']:<6} "
              f"{r['committed_mg']:>10} {r['balance_mg']:>12} "
              f"{r['delta_mg']:>10} {r['status']:<6}  {r['note']}")
    print("=" * 98)

    passes = sum(1 for r in rows if r["status"] == "PASS")
    fails = sum(1 for r in rows if r["status"] == "FAIL")
    errors = sum(1 for r in rows if r["status"] == "ERROR")
    skips = sum(1 for r in rows if r["status"] == "SKIP")
    total = len(rows)
    print(f"Total: {total}   PASS: {passes}   FAIL: {fails}   "
          f"ERROR: {errors}   SKIP: {skips}")
    print("=" * 98 + "\n")


def write_csv(rows, path):
    if not rows:
        return
    fields = ["commitment_id", "user", "token", "wallet",
              "committed_mg", "balance_mg", "delta_mg", "status", "note"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"CSV written to: {path}")


def main():
    ap = argparse.ArgumentParser(
        description="PoPC Oracle — read-only Etherscan audit of active commitments")
    ap.add_argument("--etherscan-key", required=True,
                    help="Etherscan API key (free tier is fine)")
    ap.add_argument("--rpc", default="http://127.0.0.1:18232",
                    help="SOST node RPC URL (default: http://127.0.0.1:18232)")
    ap.add_argument("--rpc-user", help="SOST node RPC username")
    ap.add_argument("--rpc-pass", help="SOST node RPC password")
    ap.add_argument("--csv", help="Write audit results to this CSV file")
    ap.add_argument("--rate-delay", type=float, default=0.25,
                    help="Seconds to wait between Etherscan calls (default 0.25 = 4 req/s, "
                         "below the 5 req/s free-tier limit)")
    # Spot-check mode: single wallet/token pair, no node RPC needed
    ap.add_argument("--check-wallet",
                    help="Manual spot check: Ethereum wallet to query")
    ap.add_argument("--token", choices=["XAUT", "PAXG"],
                    help="Token to check in spot-check mode")
    ap.add_argument("--min-mg", type=int, default=0,
                    help="Minimum milligrams required in spot-check mode")
    args = ap.parse_args()

    # Spot check mode: bypass node RPC entirely.
    if args.check_wallet:
        if not args.token:
            ap.error("--check-wallet requires --token XAUT or --token PAXG")
        fake = {
            "commitment_id": "spot-check-manual",
            "user_pkh": "(n/a)",
            "eth_wallet": args.check_wallet,
            "gold_token": args.token,
            "gold_amount_mg": args.min_mg,
        }
        row = audit_commitment(fake, args.etherscan_key, args.rate_delay)
        print_report([row])
        if args.csv:
            write_csv([row], args.csv)
        sys.exit(0 if row["status"] == "PASS" else 1)

    # Registry audit mode: need node RPC credentials.
    if not args.rpc_user or not args.rpc_pass:
        ap.error("--rpc-user and --rpc-pass required (or use --check-wallet for spot check)")

    try:
        commitments = fetch_active_commitments(args.rpc, args.rpc_user, args.rpc_pass)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    if not commitments:
        print("No active commitments found. Nothing to audit.")
        sys.exit(0)

    print(f"Auditing {len(commitments)} active commitment(s)...")
    rows = []
    for c in commitments:
        row = audit_commitment(c, args.etherscan_key, args.rate_delay)
        rows.append(row)

    print_report(rows)
    if args.csv:
        write_csv(rows, args.csv)

    # Exit 1 if any commitment failed (useful for scripting / cron alerts)
    any_fail = any(r["status"] == "FAIL" for r in rows)
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
SOST PoPC Daemon — Automated PoPC Lifecycle Manager

Manages the complete PoPC (Proof of Personal Custody) lifecycle:
  - Activating new commitments (fee collection)
  - Checking all active commitments (balance verification via Ethereum RPC)
  - Processing completed/expired commitments (reward payout)
  - Status reporting

Uses popc_contracts.json as the contract registry.
Does NOT execute transactions — generates sost-cli commands for operator review.

Usage:
    # Activate a new commitment (collect fee, set status to ACTIVE)
    python3 popc_daemon.py --action activate --contract-id FOUND-001

    # Check all active commitments (verify Ethereum balances)
    python3 popc_daemon.py --action check-all [--eth-rpc https://eth-mainnet...]

    # Show status of all contracts
    python3 popc_daemon.py --action status

    # Dry run — show what would happen without modifying state
    python3 popc_daemon.py --action check-all --dry-run
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

# =============================================================================
# Constants
# =============================================================================

STOCKS_PER_SOST = 100_000_000
FOUNDATION_FEE_ADDRESS = "sost13a22c277b5d5cbdc17ecc6c7bc33a9755b88d429"
POPC_POOL_ADDRESS = "sost144cc82d3c711b5a9322640c66b94a520497ac40d"

# Default paths
DEFAULT_CONTRACTS = os.path.join(os.path.dirname(__file__), "popc_contracts.json")
DEFAULT_LOG = os.path.join(os.path.dirname(__file__), "..", "popc_payouts.json")

# ERC-20 balanceOf(address) function selector
BALANCE_OF_SELECTOR = "0x70a08231"

# =============================================================================
# Arithmetic helpers (integer only — no floats for monetary values)
# =============================================================================

def sost_to_stocks(sost_str: str) -> int:
    parts = sost_str.split(".")
    integer_part = int(parts[0]) * STOCKS_PER_SOST
    if len(parts) == 2:
        frac = parts[1].ljust(8, "0")[:8]
        integer_part += int(frac)
    return integer_part


def stocks_to_sost(stocks: int) -> str:
    whole = stocks // STOCKS_PER_SOST
    frac = stocks % STOCKS_PER_SOST
    return f"{whole}.{frac:08d}"


# =============================================================================
# Ethereum RPC helper
# =============================================================================

def eth_call_balance(eth_rpc: str, token_contract: str, wallet: str) -> int:
    """Query ERC-20 balanceOf via Ethereum JSON-RPC. Returns raw token units."""
    # Pad address to 32 bytes for ABI encoding
    addr_padded = wallet.lower().replace("0x", "").zfill(64)
    data = BALANCE_OF_SELECTOR + addr_padded

    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": token_contract, "data": data}, "latest"],
        "id": 1
    }).encode()

    req = urllib.request.Request(
        eth_rpc,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"  ERROR: Ethereum RPC call failed: {e}", file=sys.stderr)
        return -1

    if "error" in result:
        print(f"  ERROR: Ethereum RPC error: {result['error']}", file=sys.stderr)
        return -1

    hex_value = result.get("result", "0x0")
    return int(hex_value, 16)


# =============================================================================
# Contract registry management
# =============================================================================

def load_contracts(path: str) -> dict:
    if not os.path.exists(path):
        print(f"ERROR: Contract registry not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r") as f:
        return json.load(f)


def save_contracts(path: str, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_log(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"payouts": []}


def save_log(path: str, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


# =============================================================================
# Actions
# =============================================================================

def action_activate(args, contracts, log):
    """Activate a commitment: collect upfront fee, set status to ACTIVE."""
    cid = args.contract_id
    contract = None
    for c in contracts.get("contracts", []):
        if c["contract_id"] == cid:
            contract = c
            break

    if not contract:
        print(f"ERROR: Contract {cid} not found in registry", file=sys.stderr)
        return False

    if contract["status"] != "PENDING":
        print(f"ERROR: Contract {cid} status is '{contract['status']}', expected PENDING",
              file=sys.stderr)
        return False

    # Calculate fee
    gross_stocks = sost_to_stocks(contract["gross_reward_sost"])
    fee_rate = contract["fee_rate"]
    fee_rate_bps = int(fee_rate * 10000)
    fee_stocks = (gross_stocks * fee_rate_bps) // 10000
    net_stocks = gross_stocks - fee_stocks

    fee_sost = stocks_to_sost(fee_stocks)
    net_sost = stocks_to_sost(net_stocks)

    timestamp = int(time.time())
    timestamp_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))

    cli_base = f"./sost-cli --wallet {args.wallet}"
    if args.rpc_user:
        cli_base += f" --rpc-user={args.rpc_user} --rpc-pass={args.rpc_pass}"

    print("=" * 60)
    print(f"ACTIVATE COMMITMENT — {cid}")
    print("=" * 60)
    print(f"  Contract:    {cid}")
    print(f"  Model:       {contract['model']}")
    print(f"  Asset:       {contract['asset']} ({contract['amount']})")
    print(f"  Participant: {contract['participant_sost']}")
    print(f"  Duration:    {contract['start_date']} → {contract['expiry_date']}")
    print(f"  Gross reward: {contract['gross_reward_sost']} SOST")
    print(f"  Fee rate:    {fee_rate*100:.1f}%")
    print(f"  Fee amount:  {fee_sost} SOST ({fee_stocks} stocks)")
    print(f"  Net reward:  {net_sost} SOST (at completion)")
    print()
    print("COMMAND TO EXECUTE (collect fee upfront):")
    print("-" * 60)
    cmd = f"{cli_base} send {FOUNDATION_FEE_ADDRESS} {fee_sost}"
    print(f"\n# Fee: {fee_sost} SOST → Foundation ({fee_rate*100:.0f}% of {contract['gross_reward_sost']} SOST)")
    print(cmd)
    print()

    if not args.dry_run:
        contract["status"] = "FEE_PENDING"
        contract["fee_sost"] = fee_sost
        contract["fee_stocks"] = fee_stocks
        contract["net_reward_sost"] = net_sost
        contract["net_reward_stocks"] = net_stocks
        contract["activated_at"] = timestamp_iso

        log["payouts"].append({
            "contract_id": cid,
            "action": "activate",
            "participant": contract["participant_sost"],
            "gross_reward_sost": contract["gross_reward_sost"],
            "fee_sost": fee_sost,
            "fee_stocks": fee_stocks,
            "fee_recipient": FOUNDATION_FEE_ADDRESS,
            "source": POPC_POOL_ADDRESS,
            "timestamp": timestamp,
            "timestamp_iso": timestamp_iso,
            "fee_txid": "PENDING — fill after execution",
            "status": "FEE_PENDING",
        })
        print(f"Contract {cid} status → FEE_PENDING")
        print("After TX confirms, update status to ACTIVE in popc_contracts.json")

    return True


def action_check_all(args, contracts, log):
    """Check all active commitments by querying Ethereum balances."""
    eth_rpc = args.eth_rpc
    if not eth_rpc:
        print("WARNING: No --eth-rpc provided. Using status check only (no balance verification).")
        print()

    now = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    active = [c for c in contracts.get("contracts", []) if c["status"] == "ACTIVE"]

    if not active:
        print("No active commitments to check.")
        return True

    print("=" * 60)
    print(f"PoPC COMMITMENT CHECK — {now_iso}")
    print(f"Active commitments: {len(active)}")
    print("=" * 60)

    all_passed = True
    for contract in active:
        cid = contract["contract_id"]
        print(f"\n--- {cid} ({contract['asset']}) ---")

        # Check expiry
        expiry_str = contract.get("expiry_date", "")
        if expiry_str:
            try:
                expiry_ts = time.mktime(time.strptime(expiry_str, "%Y-%m-%d"))
                if now > expiry_ts:
                    print(f"  STATUS: EXPIRED (expiry: {expiry_str})")
                    if not args.dry_run:
                        contract["status"] = "EXPIRED"
                    continue
                days_left = int((expiry_ts - now) / 86400)
                print(f"  Expiry: {expiry_str} ({days_left} days remaining)")
            except ValueError:
                print(f"  WARNING: Cannot parse expiry date: {expiry_str}")

        # Balance check via Ethereum RPC
        if eth_rpc and "token_contract" in contract and "eth_wallet" in contract:
            print(f"  Token:  {contract['token_contract']}")
            print(f"  Wallet: {contract['eth_wallet']}")

            balance = eth_call_balance(eth_rpc, contract["token_contract"],
                                       contract["eth_wallet"])
            if balance < 0:
                print(f"  Balance: ERROR (RPC call failed)")
                all_passed = False
                continue

            # Token amounts are in 18 decimals
            balance_display = balance / 1e18
            committed = float(contract.get("amount_numeric", 0))
            passed = balance_display >= committed

            print(f"  Balance: {balance_display:.6f} (committed: {committed})")
            print(f"  Result:  {'PASS' if passed else 'FAIL'}")

            if not passed:
                all_passed = False
                print(f"  WARNING: Balance below committed amount!")

            if not args.dry_run:
                # Record check result
                check_entry = {
                    "contract_id": cid,
                    "action": "balance_check",
                    "balance_raw": str(balance),
                    "balance_display": f"{balance_display:.6f}",
                    "committed": str(committed),
                    "result": "PASS" if passed else "FAIL",
                    "timestamp": int(now),
                    "timestamp_iso": now_iso,
                }
                log["payouts"].append(check_entry)
        else:
            print(f"  Balance check: SKIPPED (no eth_rpc or missing contract/wallet info)")

    print()
    if all_passed:
        print("All checks PASSED.")
    else:
        print("WARNING: Some checks FAILED. Review above.")

    return all_passed


def action_status(args, contracts, log):
    """Show status of all contracts."""
    all_contracts = contracts.get("contracts", [])
    if not all_contracts:
        print("No contracts in registry.")
        return True

    print("=" * 60)
    print("PoPC CONTRACT STATUS")
    print("=" * 60)

    for c in all_contracts:
        status_color = {
            "PENDING": "...",
            "FEE_PENDING": "FEE",
            "ACTIVE": "OK",
            "EXPIRED": "END",
            "COMPLETED": "DONE",
            "SLASHED": "FAIL",
        }.get(c["status"], "???")

        print(f"\n  [{status_color}] {c['contract_id']}")
        print(f"       Model: {c['model']} | Asset: {c['asset']} {c.get('amount', '')}")
        print(f"       Period: {c.get('start_date', '?')} → {c.get('expiry_date', '?')}")
        print(f"       Status: {c['status']}")
        if "gross_reward_sost" in c:
            print(f"       Reward: {c['gross_reward_sost']} SOST (fee: {c.get('fee_sost', '?')} SOST)")
        if c.get("participant_sost"):
            print(f"       Participant: {c['participant_sost']}")

    # Summary
    statuses = {}
    for c in all_contracts:
        statuses[c["status"]] = statuses.get(c["status"], 0) + 1

    print(f"\n{'=' * 60}")
    print(f"Total: {len(all_contracts)} contracts")
    for s, count in sorted(statuses.items()):
        print(f"  {s}: {count}")

    return True


def action_complete(args, contracts, log):
    """Process a completed commitment — pay net reward to participant."""
    cid = args.contract_id
    contract = None
    for c in contracts.get("contracts", []):
        if c["contract_id"] == cid:
            contract = c
            break

    if not contract:
        print(f"ERROR: Contract {cid} not found", file=sys.stderr)
        return False

    if contract["status"] not in ("ACTIVE", "EXPIRED"):
        print(f"ERROR: Contract {cid} status is '{contract['status']}', expected ACTIVE or EXPIRED",
              file=sys.stderr)
        return False

    net_sost = contract.get("net_reward_sost")
    if not net_sost:
        # Recalculate
        gross_stocks = sost_to_stocks(contract["gross_reward_sost"])
        fee_rate_bps = int(contract["fee_rate"] * 10000)
        fee_stocks = (gross_stocks * fee_rate_bps) // 10000
        net_stocks = gross_stocks - fee_stocks
        net_sost = stocks_to_sost(net_stocks)

    participant = contract["participant_sost"]
    timestamp = int(time.time())
    timestamp_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))

    cli_base = f"./sost-cli --wallet {args.wallet}"
    if args.rpc_user:
        cli_base += f" --rpc-user={args.rpc_user} --rpc-pass={args.rpc_pass}"

    print("=" * 60)
    print(f"COMPLETE COMMITMENT — {cid}")
    print("=" * 60)
    print(f"  Contract:    {cid}")
    print(f"  Participant: {participant}")
    print(f"  Net reward:  {net_sost} SOST")
    print(f"  Source:      {POPC_POOL_ADDRESS} (PoPC Pool)")
    print()
    print("COMMAND TO EXECUTE (pay net reward):")
    print("-" * 60)
    cmd = f"{cli_base} send {participant} {net_sost}"
    print(f"\n# Net reward: {net_sost} SOST → {participant}")
    print(cmd)
    print()

    if not args.dry_run:
        contract["status"] = "PAYOUT_PENDING"
        contract["completed_at"] = timestamp_iso

        log["payouts"].append({
            "contract_id": cid,
            "action": "complete",
            "participant": participant,
            "payout_sost": net_sost,
            "source": POPC_POOL_ADDRESS,
            "timestamp": timestamp,
            "timestamp_iso": timestamp_iso,
            "payout_txid": "PENDING — fill after execution",
            "status": "PAYOUT_PENDING",
        })
        print(f"Contract {cid} status → PAYOUT_PENDING")
        print("After TX confirms, update status to COMPLETED in popc_contracts.json")

    return True


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="SOST PoPC Daemon — Automated PoPC Lifecycle Manager"
    )
    parser.add_argument("--action", required=True,
                        choices=["activate", "check-all", "status", "complete"],
                        help="Action to perform")
    parser.add_argument("--contract-id", help="Contract ID (for activate/complete)")
    parser.add_argument("--contracts", default=DEFAULT_CONTRACTS,
                        help="Contract registry JSON file")
    parser.add_argument("--log", default=DEFAULT_LOG, help="Payout log file")
    parser.add_argument("--wallet", default="wallet.json", help="Wallet file path")
    parser.add_argument("--rpc-user", default="", help="SOST RPC username")
    parser.add_argument("--rpc-pass", default="", help="SOST RPC password")
    parser.add_argument("--eth-rpc", default="", help="Ethereum RPC endpoint URL")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without modifying state")

    args = parser.parse_args()

    # Validate
    if args.action in ("activate", "complete") and not args.contract_id:
        print(f"ERROR: --contract-id required for --action {args.action}", file=sys.stderr)
        sys.exit(1)

    contracts = load_contracts(args.contracts)
    log = load_log(args.log)

    if args.dry_run:
        print("[DRY RUN — no state changes will be made]\n")

    success = False
    if args.action == "activate":
        success = action_activate(args, contracts, log)
    elif args.action == "check-all":
        success = action_check_all(args, contracts, log)
    elif args.action == "status":
        success = action_status(args, contracts, log)
    elif args.action == "complete":
        success = action_complete(args, contracts, log)

    # Save state (unless dry run)
    if not args.dry_run and success:
        save_contracts(args.contracts, contracts)
        save_log(args.log, log)
        print(f"\nState saved to {args.contracts}")
        print(f"Log saved to {args.log}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

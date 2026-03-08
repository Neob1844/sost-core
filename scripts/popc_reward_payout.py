#!/usr/bin/env python3
"""
SOST PoPC Reward Payout Generator — Phase 1 (Manual)

Generates payout commands for completed PoPC commitments.
Does NOT execute transactions — operator reviews and runs manually.

Usage:
    python3 popc_reward_payout.py \
        --contract-id FOUND-001 \
        --participant sost1abc...def \
        --reward 1.50000000 \
        [--fee-rate 0.05] \
        [--wallet wallet.json] \
        [--rpc-user USER --rpc-pass PASS] \
        [--log popc_payouts.json]

Output:
    - Prints the two sost-cli send commands to stdout
    - Appends a JSON entry to the payout log file
    - Operator copies commands, reviews, and executes manually

Fee logic:
    - Default fee rate: 5% of gross reward (Model A)
    - Participant receives: reward * (1 - fee_rate)
    - Foundation receives: reward * fee_rate
    - Both transactions sourced from PoPC Pool balance
    - All participants pay the same fee — no exceptions
"""

import argparse
import json
import os
import sys
import time

# Foundation fee wallet — receives protocol fees
FOUNDATION_FEE_ADDRESS = "sost13a22c277b5d5cbdc17ecc6c7bc33a9755b88d429"

# PoPC Pool address — source of rewards
POPC_POOL_ADDRESS = "sost144cc82d3c711b5a9322640c66b94a520497ac40d"

STOCKS_PER_SOST = 100_000_000  # 1 SOST = 10^8 stocks


def sost_to_stocks(sost: str) -> int:
    """Convert SOST decimal string to integer stocks."""
    parts = sost.split(".")
    integer_part = int(parts[0]) * STOCKS_PER_SOST
    if len(parts) == 2:
        frac = parts[1].ljust(8, "0")[:8]
        integer_part += int(frac)
    return integer_part


def stocks_to_sost(stocks: int) -> str:
    """Convert integer stocks to SOST decimal string (8 decimal places)."""
    whole = stocks // STOCKS_PER_SOST
    frac = stocks % STOCKS_PER_SOST
    return f"{whole}.{frac:08d}"


def main():
    parser = argparse.ArgumentParser(
        description="SOST PoPC Reward Payout Generator (Phase 1 — Manual)"
    )
    parser.add_argument("--contract-id", required=True, help="Commitment ID (e.g., FOUND-001)")
    parser.add_argument("--participant", required=True, help="Participant SOST address")
    parser.add_argument("--reward", required=True, help="Gross reward amount in SOST (e.g., 1.50000000)")
    parser.add_argument("--fee-rate", type=float, default=0.05, help="Fee rate (default: 0.05 = 5%%)")
    parser.add_argument("--wallet", default="wallet.json", help="Wallet file path")
    parser.add_argument("--rpc-user", default="USER", help="RPC username")
    parser.add_argument("--rpc-pass", default="PASS", help="RPC password")
    parser.add_argument("--log", default="popc_payouts.json", help="Payout log file")

    args = parser.parse_args()

    # Validate participant address
    if not args.participant.startswith("sost1") or len(args.participant) != 45:
        print(f"ERROR: Invalid participant address: {args.participant}", file=sys.stderr)
        print("  Expected format: sost1 + 40 hex chars (45 chars total)", file=sys.stderr)
        sys.exit(1)

    # Calculate amounts in stocks (integer arithmetic only)
    gross_stocks = sost_to_stocks(args.reward)
    if gross_stocks <= 0:
        print(f"ERROR: Reward must be positive, got {args.reward}", file=sys.stderr)
        sys.exit(1)

    fee_rate = args.fee_rate
    if fee_rate < 0 or fee_rate > 1:
        print(f"ERROR: Fee rate must be 0-1, got {fee_rate}", file=sys.stderr)
        sys.exit(1)

    # Integer fee calculation: fee = floor(gross * fee_rate_num / fee_rate_den)
    # Use integer math to avoid float consensus issues
    fee_rate_bps = int(fee_rate * 10000)  # basis points
    fee_stocks = (gross_stocks * fee_rate_bps) // 10000
    payout_stocks = gross_stocks - fee_stocks

    gross_sost = stocks_to_sost(gross_stocks)
    fee_sost = stocks_to_sost(fee_stocks)
    payout_sost = stocks_to_sost(payout_stocks)

    timestamp = int(time.time())
    timestamp_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))

    # Print summary
    print("=" * 60)
    print(f"SOST PoPC Reward Payout — {args.contract_id}")
    print("=" * 60)
    print(f"  Contract ID:   {args.contract_id}")
    print(f"  Participant:   {args.participant}")
    print(f"  Gross reward:  {gross_sost} SOST ({gross_stocks} stocks)")
    print(f"  Fee rate:      {fee_rate*100:.1f}%")
    print(f"  Fee amount:    {fee_sost} SOST ({fee_stocks} stocks)")
    print(f"  Net payout:    {payout_sost} SOST ({payout_stocks} stocks)")
    print(f"  Fee recipient: {FOUNDATION_FEE_ADDRESS}")
    print(f"  Source:        {POPC_POOL_ADDRESS} (PoPC Pool)")
    print(f"  Timestamp:     {timestamp_iso}")
    print()

    # Generate commands
    cli_base = f"./sost-cli --wallet {args.wallet} --rpc-user={args.rpc_user} --rpc-pass={args.rpc_pass}"

    print("COMMANDS TO EXECUTE (review before running):")
    print("-" * 60)

    # Command 1: payout to participant
    cmd_payout = f"{cli_base} send {args.participant} {payout_sost}"
    print(f"\n# 1. Payout to participant ({payout_sost} SOST = 95% of reward)")
    print(cmd_payout)

    # Command 2: fee to Foundation
    cmd_fee = f"{cli_base} send {FOUNDATION_FEE_ADDRESS} {fee_sost}"
    print(f"\n# 2. Protocol fee to Foundation ({fee_sost} SOST = {fee_rate*100:.0f}% of reward)")
    print(cmd_fee)

    print("\n" + "-" * 60)
    print("After executing, record the TX hashes below and update the log.")
    print()

    # Build log entry
    entry = {
        "contract_id": args.contract_id,
        "participant": args.participant,
        "gross_reward_sost": gross_sost,
        "gross_reward_stocks": gross_stocks,
        "fee_rate": fee_rate,
        "fee_sost": fee_sost,
        "fee_stocks": fee_stocks,
        "payout_sost": payout_sost,
        "payout_stocks": payout_stocks,
        "fee_recipient": FOUNDATION_FEE_ADDRESS,
        "source": POPC_POOL_ADDRESS,
        "timestamp": timestamp,
        "timestamp_iso": timestamp_iso,
        "payout_txid": "PENDING — fill after execution",
        "fee_txid": "PENDING — fill after execution",
        "status": "GENERATED",
    }

    # Append to log
    log_path = args.log
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            log_data = json.load(f)
    else:
        log_data = {"payouts": []}

    log_data["payouts"].append(entry)

    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)
        f.write("\n")

    print(f"Log entry appended to {log_path}")
    print(f"Status: GENERATED (update to COMPLETED after TX confirmation)")


if __name__ == "__main__":
    main()

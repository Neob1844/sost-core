#!/usr/bin/env python3
"""
SOST PoPC Balance Verifier — Foundation Commitments

Queries Ethereum mainnet for XAUT and PAXG balances at the Foundation wallet.
Outputs a JSON attestation with balances, block number, and pass/fail status.

Usage:
    python3 verify_popc_balance.py [--rpc URL]

Default RPC: https://eth.llamarpc.com (public, no key required)
For production use, set your own RPC via Infura/Alchemy/etc.

Requirements:
    Python 3.8+, no external dependencies (uses urllib only)
"""

import json
import sys
import time
import urllib.request
import urllib.error

# =============================================================================
# Configuration
# =============================================================================

FOUNDATION_WALLET = "0xd38955822b88867CD010946F0Ba25680B9DfC7a6"

COMMITMENTS = [
    {
        "id": "FOUND-001",
        "asset": "XAUT",
        "contract": "0x68749665FF8D2d112Fa859AA293F07A622782F38",
        "required_raw": 400000000000000000,  # 0.4 * 10^18 (18 decimals)
        "decimals": 18,
        "required_human": "0.4",
    },
    {
        "id": "FOUND-002",
        "asset": "PAXG",
        "contract": "0x45804880De22913dAFE09f4980848ECE6EcbAf78",
        "required_raw": 400000000000000000,  # 0.4 * 10^18 (18 decimals)
        "decimals": 18,
        "required_human": "0.4",
    },
]

DEFAULT_RPC = "https://eth.llamarpc.com"

# =============================================================================
# Ethereum RPC helpers
# =============================================================================

def eth_call(rpc_url: str, to: str, data: str, block: str = "latest") -> str:
    """Execute eth_call and return hex result."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": to, "data": data}, block],
        "id": 1,
    }).encode()

    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    if "error" in result:
        raise RuntimeError(f"RPC error: {result['error']}")
    return result.get("result", "0x0")


def get_block_number(rpc_url: str) -> int:
    """Get current Ethereum block number."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_blockNumber",
        "params": [],
        "id": 1,
    }).encode()

    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    return int(result["result"], 16)


def balance_of(rpc_url: str, token_contract: str, wallet: str) -> int:
    """Query ERC-20 balanceOf(wallet) on token_contract."""
    # balanceOf(address) selector = 0x70a08231
    # Pad wallet address to 32 bytes
    wallet_padded = wallet.lower().replace("0x", "").zfill(64)
    data = "0x70a08231" + wallet_padded

    result_hex = eth_call(rpc_url, token_contract, data)
    return int(result_hex, 16)


# =============================================================================
# Main
# =============================================================================

def main():
    rpc_url = DEFAULT_RPC

    # Parse --rpc flag
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--rpc" and i + 1 < len(args):
            rpc_url = args[i + 1]
        elif arg in ("--help", "-h"):
            print(__doc__.strip())
            sys.exit(0)

    print(f"SOST PoPC Balance Verifier")
    print(f"RPC: {rpc_url}")
    print(f"Wallet: {FOUNDATION_WALLET}")
    print()

    try:
        block_num = get_block_number(rpc_url)
    except Exception as e:
        print(f"ERROR: Cannot connect to RPC: {e}", file=sys.stderr)
        sys.exit(1)

    timestamp = int(time.time())
    timestamp_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))

    results = []
    all_pass = True

    for c in COMMITMENTS:
        try:
            raw_balance = balance_of(rpc_url, c["contract"], FOUNDATION_WALLET)
            human_balance = raw_balance / (10 ** c["decimals"])
            passed = raw_balance >= c["required_raw"]
        except Exception as e:
            raw_balance = -1
            human_balance = -1
            passed = False
            print(f"  WARNING: {c['id']} query failed: {e}", file=sys.stderr)

        if not passed:
            all_pass = False

        entry = {
            "commitment_id": c["id"],
            "asset": c["asset"],
            "contract": c["contract"],
            "balance_raw": str(raw_balance),
            "balance_human": f"{human_balance:.6f}",
            "required_human": c["required_human"],
            "pass": passed,
        }
        results.append(entry)

        status = "PASS" if passed else "FAIL"
        print(f"  {c['id']} ({c['asset']}): {human_balance:.6f} oz >= {c['required_human']} oz -> {status}")

    attestation = {
        "verifier": "sost-popc-balance-verifier",
        "version": "1.0",
        "timestamp": timestamp,
        "timestamp_iso": timestamp_iso,
        "ethereum_block": block_num,
        "wallet": FOUNDATION_WALLET,
        "commitments": results,
        "all_pass": all_pass,
    }

    print()
    print(json.dumps(attestation, indent=2))

    # Write to file
    out_path = "popc_verification_latest.json"
    with open(out_path, "w") as f:
        json.dump(attestation, f, indent=2)
        f.write("\n")
    print(f"\nSaved to {out_path}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()

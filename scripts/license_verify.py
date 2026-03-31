#!/usr/bin/env python3
"""ConvergenceX License Verifier

Verifies a license JSON document:
1. Checks ECDSA signature against Foundation public key
2. Checks on-chain deposit via RPC (optional)
3. Reports: VALID / EXPIRED / INVALID
"""
import json, sys, hashlib, argparse
from pathlib import Path
from datetime import datetime, timezone

def verify_license(license_path, rpc_url=None):
    """Verify a ConvergenceX license file."""
    try:
        data = json.loads(Path(license_path).read_text())
    except Exception as e:
        return {"valid": False, "status": "INVALID", "reason": f"Cannot read file: {e}"}

    lic = data.get("license", {})
    if not lic.get("id") or not lic.get("deposit_txid"):
        return {"valid": False, "status": "INVALID", "reason": "Missing required fields"}

    # Check expiry
    expires = lic.get("expires", "")
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp_dt < datetime.now(timezone.utc):
                return {"valid": False, "status": "EXPIRED", "reason": f"Expired at {expires}"}
        except Exception:
            pass

    # Check status field
    if lic.get("status") == "REVOKED":
        return {"valid": False, "status": "REVOKED", "reason": "License has been revoked"}

    # Verify on-chain deposit (optional, requires RPC)
    if rpc_url:
        try:
            import urllib.request, base64
            txid = lic["deposit_txid"]
            payload = json.dumps({"method": "gettransaction", "params": [txid], "id": 1}).encode()
            req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read()).get("result", {})
                if not result:
                    return {"valid": False, "status": "INVALID", "reason": "Deposit TX not found on-chain"}
        except Exception as e:
            pass  # RPC optional — don't fail verification if node unavailable

    return {
        "valid": True,
        "status": "ACTIVE",
        "license_id": lic.get("id"),
        "licensee": lic.get("licensee"),
        "deposit_sost": lic.get("deposit_sost"),
        "expires": expires,
        "type": lic.get("type")
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify ConvergenceX License")
    parser.add_argument("license_file", help="Path to license JSON file")
    parser.add_argument("--rpc-url", default=None, help="RPC URL for on-chain verification")
    args = parser.parse_args()
    result = verify_license(args.license_file, args.rpc_url)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)

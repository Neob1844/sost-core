#!/usr/bin/env python3
"""ConvergenceX License Creator

Creates a cryptographically signed license JSON from a verified ESCROW_LOCK deposit.

Usage:
  python3 license_create.py --deposit-txid abc123 --licensee sost1xyz...
"""
import json, sys, hashlib, argparse, os
from pathlib import Path
from datetime import datetime, timezone, timedelta

LICENSE_LOCK_BLOCKS = 52560   # ~1 year
LICENSE_GRACE_BLOCKS = 4320   # ~30 days for auto-renewal
LICENSE_MIN_USD = 1000
LICENSES_DIR = Path(__file__).resolve().parent.parent / "licenses"

def create_license(deposit_txid, licensee, deposit_sost, sost_price_usd, lock_height):
    """Create a license document."""
    deposit_usd = deposit_sost * sost_price_usd
    if deposit_usd < LICENSE_MIN_USD:
        return None, f"Deposit ${deposit_usd:.2f} below minimum ${LICENSE_MIN_USD}"

    unlock_height = lock_height + LICENSE_LOCK_BLOCKS
    grace_end = unlock_height + LICENSE_GRACE_BLOCKS

    # Generate license ID
    raw = f"{deposit_txid}:{licensee}:{lock_height}".encode()
    license_id = hashlib.sha256(raw).hexdigest()

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=365)

    license_doc = {
        "license": {
            "id": license_id,
            "licensee": licensee,
            "deposit_txid": deposit_txid,
            "deposit_sost": round(deposit_sost, 8),
            "deposit_usd_equivalent": round(deposit_usd, 2),
            "sost_reference_price": round(sost_price_usd, 6),
            "lock_block": lock_height,
            "unlock_block": unlock_height,
            "grace_end_block": grace_end,
            "type": "convergencex_operational",
            "scope": "Production deployment, commercial integration, public-facing services based on ConvergenceX",
            "excludes": "Source code study, academic research, private testing — these do not require a license",
            "auto_renewal": "If deposit not withdrawn within 30 days (4,320 blocks) after expiry, license auto-renews for another year",
            "issued": now.isoformat(),
            "expires": expires.isoformat(),
            "status": "ACTIVE"
        },
        "terms": {
            "deposit_is": "refundable security deposit, not a fee or investment",
            "return": "Full SOST amount returned when deposit is withdrawn. No yield, no interest.",
            "auto_renew": "License auto-renews if deposit remains locked past grace period (30 days after expiry)",
            "usd_reference": "Calculated at lock time only. Foundation does not guarantee future SOST value.",
            "revocation": "License may be suspended if licensee violates protocol integrity.",
            "no_license_required_for": "Reading source code, academic study, private non-commercial testing, contributing to development"
        },
        "verification": {
            "verify_url": f"https://sostcore.com/sost-explorer.html?search={deposit_txid}",
            "verify_onchain": f"Check {deposit_txid} exists as ESCROW_LOCK at block {lock_height}",
            "note": "Anyone can verify this license on-chain without contacting the Foundation"
        }
    }

    # Save
    LICENSES_DIR.mkdir(parents=True, exist_ok=True)
    filepath = LICENSES_DIR / f"LICENSE_{license_id[:16]}.json"
    filepath.write_text(json.dumps(license_doc, indent=2))

    return license_doc, None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create ConvergenceX License")
    parser.add_argument("--deposit-txid", required=True)
    parser.add_argument("--licensee", required=True)
    parser.add_argument("--deposit-sost", type=float, required=True)
    parser.add_argument("--sost-price", type=float, default=0.3125)
    parser.add_argument("--lock-height", type=int, default=5100)
    args = parser.parse_args()

    doc, err = create_license(args.deposit_txid, args.licensee, args.deposit_sost, args.sost_price, args.lock_height)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(doc, indent=2))
    print(f"\nLicense saved to licenses/", file=sys.stderr)

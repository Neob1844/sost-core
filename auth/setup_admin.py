#!/usr/bin/env python3
"""Setup utility — generate admin password hash for auth.env.

Run ONCE to create the password hash, then put it in /etc/sost/auth.env.
This script does NOT store the password — only outputs the hash.

Usage:
  python3 -m auth.setup_admin
  # Enter password when prompted
  # Copy the output hash to auth.env as SOST_ADMIN_PASS_HASH=<hash>
"""
import getpass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.password import generate_admin_hash


def main():
    print("SOST Auth — Admin Password Hash Generator")
    print("=" * 50)
    print()
    print("This will generate a scrypt hash of your admin password.")
    print("The password itself is NEVER stored.")
    print()

    p1 = getpass.getpass("Enter admin password: ")
    p2 = getpass.getpass("Confirm admin password: ")

    if p1 != p2:
        print("ERROR: Passwords do not match.")
        sys.exit(1)

    if len(p1) < 12:
        print("WARNING: Password should be at least 12 characters.")

    h = generate_admin_hash(p1)
    print()
    print("Add this to /etc/sost/auth.env (or ~/.sost/auth.env):")
    print()
    print(f"SOST_ADMIN_PASS_HASH={h}")
    print()
    print("DO NOT commit this hash to the repository.")


if __name__ == "__main__":
    main()

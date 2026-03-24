#!/usr/bin/env python3
"""Setup utility — generate admin password hash + TOTP secret for auth.env.

Usage:
  python3 -m auth.setup_admin

Outputs values to paste into /etc/sost/auth.env (never commit that file).
"""
import getpass
import secrets
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.password import generate_admin_hash
from auth.otp import TOTPManager


def main():
    print("SOST Auth — Admin Setup")
    print("=" * 50)
    print()

    # 1. Username
    user = input("Admin username [admin]: ").strip() or "admin"

    # 2. Password
    p1 = getpass.getpass("Admin password (min 12 chars): ")
    p2 = getpass.getpass("Confirm password: ")
    if p1 != p2:
        print("ERROR: Passwords do not match.")
        sys.exit(1)
    if len(p1) < 12:
        print("WARNING: Password should be at least 12 characters.")

    pass_hash = generate_admin_hash(p1)

    # 3. TOTP secret
    totp_secret = TOTPManager.generate_secret()
    totp = TOTPManager(totp_secret)
    uri = totp.get_provisioning_uri(username=user, issuer="SOST Protocol")

    print()
    print("=" * 50)
    print("TOTP SETUP — Scan with Google Authenticator or Authy")
    print("=" * 50)
    print()

    # Try to show QR in terminal
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.print_ascii(invert=True)
        print()
    except ImportError:
        print("(Install 'qrcode' for terminal QR: pip3 install qrcode)")
        print()

    print(f"Manual entry secret: {totp_secret}")
    print(f"Provisioning URI:    {uri}")
    print()

    # 4. Verify TOTP works
    print("Verify your authenticator app is working:")
    code = input("Enter the 6-digit code shown in your app: ").strip()
    ok, reason = totp.verify(code)
    if not ok:
        print(f"ERROR: Code verification failed ({reason}). Setup aborted.")
        print("Make sure your phone clock is synced and try again.")
        sys.exit(1)
    print("TOTP verified successfully!")

    # 5. Session secret
    session_secret = secrets.token_hex(32)

    # 6. Output
    print()
    print("=" * 50)
    print("Add these to /etc/sost/auth.env:")
    print("=" * 50)
    print()
    print(f"SOST_ADMIN_USER={user}")
    print(f"SOST_ADMIN_PASS_HASH={pass_hash}")
    print(f"SOST_2FA_SECRET={totp_secret}")
    print(f"SOST_2FA_ENABLED=true")
    print(f"SOST_SESSION_SECRET={session_secret}")
    print()
    print("Then: chmod 600 /etc/sost/auth.env")
    print("DO NOT commit auth.env to the repository.")


if __name__ == "__main__":
    main()

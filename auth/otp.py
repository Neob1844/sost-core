"""TOTP 2FA — Time-based One-Time Password for Google Authenticator / Authy.

Uses pyotp for TOTP generation and verification. No SMS needed.
The shared secret is stored in auth.env (never in repo).
"""
import time
import pyotp
from . import auth_config as cfg


class TOTPManager:
    """TOTP-based 2FA manager compatible with Google Authenticator."""

    def __init__(self, secret=None):
        self.secret = secret or cfg.get("SOST_2FA_SECRET")
        self._attempts = {}  # user → {count, last}

    @staticmethod
    def generate_secret():
        """Generate a new TOTP shared secret (base32, 32 chars)."""
        return pyotp.random_base32(length=32)

    def get_provisioning_uri(self, username="admin", issuer="SOST Protocol"):
        """Generate otpauth:// URI for QR code scanning."""
        if not self.secret:
            return None
        totp = pyotp.TOTP(self.secret)
        return totp.provisioning_uri(name=username, issuer_name=issuer)

    def verify(self, code, user="admin"):
        """Verify a TOTP code with ±1 period tolerance (30s window).

        Returns (success, reason).
        """
        if not self.secret:
            return False, "2fa_not_configured"

        # Rate limit: 5 attempts per 5 minutes
        now = time.time()
        att = self._attempts.get(user, {"count": 0, "last": 0})
        if att["count"] >= 5 and now - att["last"] < 300:
            return False, "too_many_attempts"

        att["count"] = att["count"] + 1 if now - att["last"] < 300 else 1
        att["last"] = now
        self._attempts[user] = att

        totp = pyotp.TOTP(self.secret)
        if totp.verify(str(code).zfill(6), valid_window=1):
            att["count"] = 0  # reset on success
            return True, "verified"

        return False, "invalid_code"

    def is_configured(self):
        """Check if TOTP is set up."""
        return bool(self.secret)

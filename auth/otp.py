"""OTP generation and verification for 2FA.

Generates random 6-digit codes, stores hashed, enforces expiry and rate limits.
SMS delivery is abstracted via a provider interface.
"""
import hashlib
import hmac
import secrets
import time
from . import auth_config as cfg


class OTPStore:
    """In-memory OTP store with expiry and rate limiting.

    For production: replace with Redis or database-backed store.
    """

    def __init__(self):
        self._otps = {}       # user → {hash, created, attempts, verified}
        self._sends = {}      # user → [timestamps of sends]
        self._lockouts = {}   # user → lockout_until

    def generate(self, user):
        """Generate a new OTP for a user. Returns the plaintext code (to send via SMS).

        The code is NOT stored — only its hash. After this function returns,
        the plaintext only exists in the SMS delivery pipeline.
        """
        # Rate limit: max 3 sends per 5 minutes
        now = time.time()
        sends = self._sends.get(user, [])
        sends = [t for t in sends if now - t < 300]
        if len(sends) >= 3:
            return None, "rate_limited"
        sends.append(now)
        self._sends[user] = sends

        # Generate code
        code = str(secrets.randbelow(10 ** cfg.OTP_LENGTH)).zfill(cfg.OTP_LENGTH)

        # Store only the hash
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        self._otps[user] = {
            "hash": code_hash,
            "created": now,
            "attempts": 0,
            "verified": False,
        }

        return code, "ok"

    def verify(self, user, code):
        """Verify an OTP. Returns (success, reason)."""
        now = time.time()

        # Lockout check
        if user in self._lockouts and now < self._lockouts[user]:
            return False, "locked_out"

        entry = self._otps.get(user)
        if not entry:
            return False, "no_pending_otp"

        # Expiry
        if now - entry["created"] > cfg.OTP_EXPIRY_SECONDS:
            del self._otps[user]
            return False, "expired"

        # Attempt limit
        entry["attempts"] += 1
        if entry["attempts"] > 5:
            del self._otps[user]
            self._lockouts[user] = now + cfg.LOCKOUT_SECONDS
            return False, "too_many_attempts"

        # Verify (constant-time)
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        if hmac.compare_digest(code_hash, entry["hash"]):
            entry["verified"] = True
            del self._otps[user]  # one-time use
            return True, "verified"

        return False, "invalid_code"


class SMSProvider:
    """Abstract SMS provider interface."""

    def send(self, phone, message):
        """Send an SMS. Override for real provider."""
        raise NotImplementedError("SMS provider not configured")


class MockSMSProvider(SMSProvider):
    """Mock SMS provider for development/testing."""

    def __init__(self):
        self.sent = []

    def send(self, phone, message):
        self.sent.append({"phone": phone, "message": message, "time": time.time()})
        return True


class LogSMSProvider(SMSProvider):
    """SMS provider that logs to file (for staging)."""

    def send(self, phone, message):
        import logging
        logging.getLogger("sost.auth.sms").info(f"OTP to {phone[-4:]}: {message}")
        return True

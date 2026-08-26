"""Auth configuration — loaded from environment variables or private config file.

NEVER stores secrets in this file. All secrets come from:
  1. Environment variables (preferred)
  2. /etc/sost/auth.env (private, not in repo)
  3. ~/.sost/auth.env (fallback for dev)

The .env file must contain:
  SOST_ADMIN_USER=admin
  SOST_ADMIN_PASS_HASH=<scrypt hash>
  SOST_SESSION_SECRET=<random 64 hex chars>
  SOST_2FA_SECRET=<TOTP base32 secret for Google Authenticator>
  SOST_2FA_ENABLED=true
"""
import os

# Paths to search for config (first found wins)
_ENV_PATHS = [
    "/etc/sost/auth.env",
    os.path.expanduser("~/.sost/auth.env"),
]


def _load_env_file():
    """Load key=value pairs from private env file (not in repo)."""
    for path in _ENV_PATHS:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        os.environ.setdefault(key.strip(), val.strip())
            return path
    return None


_loaded_from = _load_env_file()


def get(key, default=None):
    """Get a config value from environment."""
    return os.environ.get(key, default)


# Public constants (not secrets)
SESSION_DURATION_SECONDS = 600  # 10 minutes
OTP_EXPIRY_SECONDS = 300        # 5 minutes
OTP_LENGTH = 6
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 900            # 15 minutes after max attempts
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32

# Roles
ROLES = {
    # GeaSpirit and materials_engine were listed here when the three were planned as one
    # ecosystem. They are unrelated products and neither asks this gateway for anything —
    # GeaSpirit authenticates entirely on its own. The entitlements were dead entries.
    "public":      {"level": 0,  "products": []},
    "user_tier_1": {"level": 1,  "products": []},
    "user_tier_2": {"level": 2,  "products": []},
    "user_tier_3": {"level": 3,  "products": []},
    "operator":    {"level": 8,  "products": []},
    "admin":       {"level": 10, "products": []},
}

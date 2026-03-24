"""Password hashing and verification using scrypt (hashlib).

Uses scrypt with strong parameters. Never stores plaintext.
Compatible with OpenSSL scrypt used in the C++ wallet.
"""
import hashlib
import hmac
import os
import secrets
from . import auth_config as cfg


def hash_password(password):
    """Hash a password with scrypt. Returns salt:hash as hex string."""
    salt = os.urandom(32)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=cfg.SCRYPT_N, r=cfg.SCRYPT_R, p=cfg.SCRYPT_P,
        dklen=cfg.SCRYPT_DKLEN,
    )
    return salt.hex() + ":" + dk.hex()


def verify_password(password, stored_hash):
    """Verify a password against a stored salt:hash string.

    Uses constant-time comparison to prevent timing attacks.
    """
    try:
        salt_hex, dk_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        expected_dk = bytes.fromhex(dk_hex)
    except (ValueError, AttributeError):
        return False

    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=cfg.SCRYPT_N, r=cfg.SCRYPT_R, p=cfg.SCRYPT_P,
        dklen=cfg.SCRYPT_DKLEN,
    )
    return hmac.compare_digest(dk, expected_dk)


def generate_admin_hash(password):
    """Generate a hash suitable for SOST_ADMIN_PASS_HASH env var.

    Run this ONCE offline, then put the result in auth.env.
    Never store the password itself.
    """
    return hash_password(password)

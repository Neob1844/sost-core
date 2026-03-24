"""Server-side session management.

Sessions are stored server-side (in-memory for now, Redis-ready interface).
Client gets only an opaque session token via HttpOnly cookie.
"""
import secrets
import time
from . import auth_config as cfg


class SessionStore:
    """In-memory session store. Replace with Redis for production."""

    def __init__(self):
        self._sessions = {}  # token → session dict

    def create(self, user, role, products=None):
        """Create a new session. Returns session token."""
        token = secrets.token_hex(32)
        self._sessions[token] = {
            "user": user,
            "role": role,
            "products": products or [],
            "created": time.time(),
            "last_active": time.time(),
            "expires": time.time() + cfg.SESSION_DURATION_SECONDS,
        }
        return token

    def validate(self, token):
        """Validate a session token. Returns session dict or None."""
        if not token:
            return None
        session = self._sessions.get(token)
        if not session:
            return None
        now = time.time()
        if now > session["expires"]:
            del self._sessions[token]
            return None
        # Inactivity timeout (same as expiry for now)
        session["last_active"] = now
        return session

    def refresh(self, token):
        """Extend session expiry."""
        session = self._sessions.get(token)
        if session:
            session["expires"] = time.time() + cfg.SESSION_DURATION_SECONDS
            session["last_active"] = time.time()
            return True
        return False

    def revoke(self, token):
        """Revoke a session."""
        return self._sessions.pop(token, None) is not None

    def revoke_all(self, user):
        """Revoke all sessions for a user."""
        to_remove = [t for t, s in self._sessions.items() if s["user"] == user]
        for t in to_remove:
            del self._sessions[t]
        return len(to_remove)

    def has_access(self, token, product, min_level=1):
        """Check if session has access to a product at minimum role level."""
        session = self.validate(token)
        if not session:
            return False
        role = session.get("role", "public")
        role_info = cfg.ROLES.get(role, cfg.ROLES["public"])
        if role_info["level"] < min_level:
            return False
        if product and product not in role_info["products"]:
            return False
        return True

    def cleanup(self):
        """Remove expired sessions."""
        now = time.time()
        expired = [t for t, s in self._sessions.items() if now > s["expires"]]
        for t in expired:
            del self._sessions[t]
        return len(expired)

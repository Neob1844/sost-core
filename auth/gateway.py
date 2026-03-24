"""Auth gateway — FastAPI endpoints for login, TOTP 2FA, session management.

Mount this as a sub-application on the main server:
  from auth.gateway import create_auth_app
  app.mount("/auth", create_auth_app())
"""
import time
import logging
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

from . import auth_config as cfg
from .password import verify_password
from .otp import TOTPManager
from .sessions import SessionStore

log = logging.getLogger("sost.auth")

_sessions = SessionStore()
_totp = TOTPManager()
_login_attempts = {}
_pending_2fa = {}  # ip → {user, expires}
_audit_log = []


class LoginRequest(BaseModel):
    username: str
    password: str


class OTPRequest(BaseModel):
    otp_code: str


class AccessCheckRequest(BaseModel):
    product: str


def create_auth_app():
    auth = FastAPI(title="SOST Auth Gateway", docs_url=None, redoc_url=None)

    @auth.post("/login")
    async def login(req: LoginRequest, request: Request):
        """Step 1: Verify username + password. If 2FA enabled, require TOTP next."""
        ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Rate limit
        att = _login_attempts.get(ip, {"count": 0, "last": 0})
        if att["count"] >= cfg.MAX_LOGIN_ATTEMPTS and now - att["last"] < cfg.LOCKOUT_SECONDS:
            _audit("login_locked", ip=ip, user=req.username)
            raise HTTPException(429, "Too many attempts. Try again later.")

        stored_user = cfg.get("SOST_ADMIN_USER")
        stored_hash = cfg.get("SOST_ADMIN_PASS_HASH")
        if not stored_user or not stored_hash:
            _audit("login_config_missing", ip=ip)
            raise HTTPException(500, "Auth not configured")

        if req.username != stored_user or not verify_password(req.password, stored_hash):
            att["count"] = att.get("count", 0) + 1
            att["last"] = now
            _login_attempts[ip] = att
            _audit("login_failed", ip=ip, user=req.username)
            raise HTTPException(401, "Invalid credentials")

        _login_attempts.pop(ip, None)

        # Check if TOTP 2FA is enabled
        totp_enabled = cfg.get("SOST_2FA_ENABLED", "true").lower() in ("true", "1", "yes")
        if totp_enabled and _totp.is_configured():
            _pending_2fa[ip] = {"user": req.username, "expires": now + 300}
            _audit("login_password_ok_awaiting_totp", ip=ip, user=req.username)
            return {"status": "otp_required", "requires_otp": True,
                    "message": "Enter 6-digit code from your authenticator app"}

        # No 2FA — issue session directly
        token = _sessions.create(req.username, "admin", ["geaspirit", "materials_engine"])
        _audit("login_success_no_2fa", ip=ip, user=req.username)
        return {"status": "authenticated", "requires_otp": False, "token": token,
                "expires_in": cfg.SESSION_DURATION_SECONDS}

    @auth.post("/verify-otp")
    async def verify_otp(req: OTPRequest, request: Request):
        """Step 2: Verify TOTP code from authenticator app."""
        ip = request.client.host if request.client else "unknown"

        pending = _pending_2fa.get(ip)
        if not pending or time.time() > pending["expires"]:
            _pending_2fa.pop(ip, None)
            _audit("otp_no_pending", ip=ip)
            raise HTTPException(401, "No pending authentication. Login first.")

        user = pending["user"]
        ok, reason = _totp.verify(req.otp_code, user)
        if not ok:
            _audit("otp_failed", ip=ip, user=user, reason=reason)
            if reason == "too_many_attempts":
                _pending_2fa.pop(ip, None)
                raise HTTPException(429, "Too many attempts. Login again.")
            raise HTTPException(401, "Invalid code")

        _pending_2fa.pop(ip, None)
        token = _sessions.create(user, "admin", ["geaspirit", "materials_engine"])
        _audit("login_success", ip=ip, user=user)
        return {"status": "authenticated", "token": token,
                "expires_in": cfg.SESSION_DURATION_SECONDS}

    @auth.post("/check-access")
    async def check_access(req: AccessCheckRequest, request: Request):
        token = _get_token(request)
        session = _sessions.validate(token)
        if not session:
            return {"access": False, "reason": "no_valid_session"}
        role_info = cfg.ROLES.get(session["role"], cfg.ROLES["public"])
        return {"access": req.product in role_info["products"], "role": session["role"],
                "product": req.product,
                "expires_in": max(0, int(session["expires"] - time.time()))}

    @auth.post("/refresh")
    async def refresh(request: Request):
        token = _get_token(request)
        if _sessions.refresh(token):
            return {"status": "refreshed", "expires_in": cfg.SESSION_DURATION_SECONDS}
        raise HTTPException(401, "Invalid session")

    @auth.post("/logout")
    async def logout(request: Request):
        token = _get_token(request)
        _sessions.revoke(token)
        _audit("logout")
        return {"status": "logged_out"}

    @auth.get("/status")
    async def status():
        return {"auth_configured": bool(cfg.get("SOST_ADMIN_USER")),
                "totp_configured": _totp.is_configured(),
                "totp_enabled": cfg.get("SOST_2FA_ENABLED", "true").lower() in ("true", "1"),
                "session_duration": cfg.SESSION_DURATION_SECONDS}

    return auth


def _get_token(request: Request):
    token = request.cookies.get("sost_session")
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _audit(event, **kwargs):
    entry = {"event": event, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ"), **kwargs}
    _audit_log.append(entry)
    if len(_audit_log) > 1000:
        _audit_log.pop(0)
    log.info(f"AUTH: {event} {kwargs}")

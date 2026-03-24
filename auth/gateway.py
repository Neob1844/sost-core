"""Auth gateway — FastAPI endpoints for login, OTP, session management.

Mount this as a sub-application on the main server:
  from auth.gateway import create_auth_app
  app.mount("/auth", create_auth_app())
"""
import time
import logging
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import auth_config as cfg
from .password import verify_password
from .otp import OTPStore, MockSMSProvider, LogSMSProvider
from .sessions import SessionStore

log = logging.getLogger("sost.auth")

# Shared state (in production, these would be backed by Redis/DB)
_sessions = SessionStore()
_otp_store = OTPStore()
_sms_provider = LogSMSProvider()  # Default: log to file. Override for real SMS.
_login_attempts = {}  # ip → {count, last}
_audit_log = []


class LoginRequest(BaseModel):
    username: str
    password: str


class OTPRequest(BaseModel):
    otp_code: str


class AccessCheckRequest(BaseModel):
    product: str  # "geaspirit" or "materials_engine"


def create_auth_app():
    """Create the auth sub-application."""
    auth = FastAPI(title="SOST Auth Gateway", docs_url=None, redoc_url=None)

    @auth.post("/login")
    async def login(req: LoginRequest, request: Request):
        """Step 1: Verify username + password. If valid, send OTP."""
        ip = request.client.host if request.client else "unknown"

        # Rate limit
        now = time.time()
        attempts = _login_attempts.get(ip, {"count": 0, "last": 0})
        if attempts["count"] >= cfg.MAX_LOGIN_ATTEMPTS and now - attempts["last"] < cfg.LOCKOUT_SECONDS:
            _audit("login_locked", ip=ip, user=req.username)
            raise HTTPException(429, "Too many attempts. Try again later.")

        # Verify credentials
        stored_user = cfg.get("SOST_ADMIN_USER")
        stored_hash = cfg.get("SOST_ADMIN_PASS_HASH")

        if not stored_user or not stored_hash:
            _audit("login_config_missing", ip=ip)
            raise HTTPException(500, "Auth not configured")

        if req.username != stored_user or not verify_password(req.password, stored_hash):
            attempts["count"] = attempts.get("count", 0) + 1
            attempts["last"] = now
            _login_attempts[ip] = attempts
            _audit("login_failed", ip=ip, user=req.username)
            raise HTTPException(401, "Invalid credentials")

        # Reset attempts on success
        _login_attempts.pop(ip, None)

        # Generate and send OTP
        phone = cfg.get("SOST_OTP_PHONE")
        if not phone:
            # No 2FA configured — issue session directly (dev mode)
            token = _sessions.create(req.username, "admin", ["geaspirit", "materials_engine"])
            _audit("login_success_no_2fa", ip=ip, user=req.username)
            return {"status": "authenticated", "requires_otp": False, "token": token}

        code, status = _otp_store.generate(req.username)
        if status == "rate_limited":
            raise HTTPException(429, "OTP rate limited. Wait before requesting again.")

        # Send via SMS
        try:
            _sms_provider.send(phone, f"SOST access code: {code}")
        except Exception as e:
            log.error(f"SMS send failed: {e}")
            raise HTTPException(500, "Failed to send verification code")

        _audit("otp_sent", ip=ip, user=req.username)
        return {"status": "otp_sent", "requires_otp": True, "message": "Verification code sent to registered phone"}

    @auth.post("/verify-otp")
    async def verify_otp(req: OTPRequest, request: Request):
        """Step 2: Verify OTP code. If valid, create session."""
        ip = request.client.host if request.client else "unknown"
        user = cfg.get("SOST_ADMIN_USER", "admin")

        ok, reason = _otp_store.verify(user, req.otp_code)
        if not ok:
            _audit("otp_failed", ip=ip, user=user, reason=reason)
            if reason == "locked_out":
                raise HTTPException(429, "Account locked. Try again later.")
            raise HTTPException(401, f"Invalid code: {reason}")

        # Create session
        token = _sessions.create(user, "admin", ["geaspirit", "materials_engine"])
        _audit("login_success", ip=ip, user=user)

        return {"status": "authenticated", "token": token,
                "expires_in": cfg.SESSION_DURATION_SECONDS}

    @auth.post("/check-access")
    async def check_access(req: AccessCheckRequest, request: Request):
        """Check if current session has access to a product."""
        token = _get_token(request)
        session = _sessions.validate(token)
        if not session:
            return {"access": False, "reason": "no_valid_session"}

        role_info = cfg.ROLES.get(session["role"], cfg.ROLES["public"])
        has_access = req.product in role_info["products"]
        return {
            "access": has_access,
            "role": session["role"],
            "product": req.product,
            "expires_in": max(0, int(session["expires"] - time.time())),
        }

    @auth.post("/refresh")
    async def refresh(request: Request):
        """Refresh session timer."""
        token = _get_token(request)
        if _sessions.refresh(token):
            return {"status": "refreshed", "expires_in": cfg.SESSION_DURATION_SECONDS}
        raise HTTPException(401, "Invalid session")

    @auth.post("/logout")
    async def logout(request: Request):
        """Revoke current session."""
        token = _get_token(request)
        _sessions.revoke(token)
        _audit("logout", user="session_holder")
        return {"status": "logged_out"}

    @auth.get("/status")
    async def status(request: Request):
        """Check auth system status (no secrets exposed)."""
        return {
            "auth_configured": bool(cfg.get("SOST_ADMIN_USER")),
            "otp_configured": bool(cfg.get("SOST_OTP_PHONE")),
            "session_duration": cfg.SESSION_DURATION_SECONDS,
        }

    return auth


def _get_token(request: Request):
    """Extract session token from cookie or Authorization header."""
    # Cookie first
    token = request.cookies.get("sost_session")
    if token:
        return token
    # Bearer token fallback
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _audit(event, **kwargs):
    """Log an audit event."""
    entry = {"event": event, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ"), **kwargs}
    _audit_log.append(entry)
    if len(_audit_log) > 1000:
        _audit_log.pop(0)
    log.info(f"AUTH: {event} {kwargs}")

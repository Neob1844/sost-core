#!/usr/bin/env python3
# SOST private-dashboard auth service (localhost-only; nginx fronts it).
# Custom login + signed session cookie, now with TOTP 2FA + one-time backup codes.
#
# Flow:  password (bcrypt)  ->  TOTP (or backup code)  ->  signed session cookie.
#   POST /_dashauth/login      {u,p,dash}
#        - bad password            -> 401
#        - ok + 2FA enabled        -> 200 {"otp_required":true} + short pending cookie (NO session yet)
#        - ok + 2FA NOT enabled    -> 204 + session cookie (rollout/back-compat only)
#   POST /_dashauth/verify-otp  {otp}   (uses the pending cookie)
#        - valid TOTP / backup     -> 204 + session cookie, pending cleared
#        - invalid                 -> 401
#   GET  /_dashauth/verify              -> 204 if session cookie valid, else 401 (nginx auth_request)
#   POST /_dashauth/logout              -> clears both cookies
#
# Secrets: cookie signing key /etc/sost/dash-auth.secret (600); 2FA store
# /etc/sost/dash-2fa.json (600, per-user {secret, enabled, backup_hashes}).
# No secret is ever logged or returned after enrolment. Audit log has NO secrets.
import http.server, socketserver, json, hmac, hashlib, base64, struct, time, os, re, threading, secrets as pysecrets

HTPASSWD   = os.environ.get("DASH_HTPASSWD", "/etc/nginx/auth/sost-admin.htpasswd")
SECRET_PATH= os.environ.get("DASH_SECRET_PATH", "/etc/sost/dash-auth.secret")
TFA_PATH   = os.environ.get("DASH_2FA_PATH", "/etc/sost/dash-2fa.json")
AUDIT_PATH = os.environ.get("DASH_AUDIT_LOG", "/opt/sost/logs/dash-auth-audit.log")
PORT       = int(os.environ.get("DASH_PORT", "18322"))
TTL        = 8*3600            # session lifetime
PENDING_TTL= 300               # 5 min to complete the 2nd factor
COOKIE     = "sost_dash"
PCOOKIE    = "sost_dash_pending"
RL_WINDOW  = 300; RL_MAX = 8   # 8 attempts / 5 min / ip (coarse)

try:
    import bcrypt
except Exception:
    bcrypt = None

SECRET = open(SECRET_PATH, "rb").read().strip()
_rl = {}; _rllock = threading.Lock()
_fail = {}; _faillock = threading.Lock()   # progressive lockout: ip -> {n, until}
_tfa_lock = threading.Lock()

# ---------- helpers ----------
def b64u(b):  return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def b64ud(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
def sign(payload: bytes) -> str: return hmac.new(SECRET, payload, hashlib.sha256).hexdigest()

def make_token(user, dash, ttl, pend=False):
    body = json.dumps({"u": user, "d": dash, "exp": int(time.time()) + ttl,
                       **({"pend": 1} if pend else {})}, separators=(",", ":")).encode()
    p = b64u(body); return p + "." + sign(p.encode())

def check_token(val, pend=False):
    try:
        p, sig = val.split(".", 1)
        if not hmac.compare_digest(sig, sign(p.encode())): return None
        d = json.loads(b64ud(p))
        if int(d.get("exp", 0)) < time.time(): return None
        if bool(d.get("pend")) != bool(pend): return None
        return d
    except Exception:
        return None

def htpasswd_ok(user, pw):
    if not bcrypt or not re.match(r'^[A-Za-z0-9_.@-]{1,64}$', user or ''): return False
    try:
        for ln in open(HTPASSWD):
            ln = ln.strip()
            if not ln or ":" not in ln: continue
            u, h = ln.split(":", 1)
            if u == user and h.startswith(("$2y$", "$2b$", "$2a$")):
                return bcrypt.checkpw(pw.encode(), h.encode())
    except Exception:
        return False
    return False

# ---------- TOTP (RFC 6238, HMAC-SHA1, 30s, 6 digits) — stdlib only ----------
def _totp_at(secret_b32, t, step=30, digits=6):
    key = base64.b32decode(secret_b32.upper() + "=" * ((8 - len(secret_b32) % 8) % 8))
    msg = struct.pack(">Q", int(t // step))
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0f
    code = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % (10 ** digits)
    return str(code).zfill(digits)

def totp_verify(secret_b32, code, window=1, step=30):
    try:
        code = str(code).strip().zfill(6)
        if not re.match(r'^\d{6}$', code): return False
        now = time.time()
        for w in range(-window, window + 1):
            if hmac.compare_digest(_totp_at(secret_b32, now + w * step, step), code):
                return True
    except Exception:
        pass
    return False

# ---------- 2FA store ----------
def load_2fa(user):
    with _tfa_lock:
        try:
            d = json.load(open(TFA_PATH))
            return d.get(user)
        except Exception:
            return None

def _save_2fa_all(d):
    tmp = TFA_PATH + ".tmp"
    with open(tmp, "w") as f: json.dump(d, f, separators=(",", ":"))
    os.chmod(tmp, 0o600); os.replace(tmp, TFA_PATH)

def consume_backup(user, code):
    """One-time backup code: compare sha256, remove on use. Returns True if used."""
    code = re.sub(r'[^A-Za-z0-9]', '', str(code or "")).lower()
    if len(code) < 8: return False
    h = hashlib.sha256(code.encode()).hexdigest()
    with _tfa_lock:
        try:
            d = json.load(open(TFA_PATH))
        except Exception:
            return False
        rec = d.get(user) or {}
        hashes = rec.get("backup_hashes", [])
        for stored in list(hashes):
            if hmac.compare_digest(stored, h):
                hashes.remove(stored); rec["backup_hashes"] = hashes; d[user] = rec
                _save_2fa_all(d); return True
    return False

def tfa_active(user):
    rec = load_2fa(user)
    return bool(rec and rec.get("enabled") and rec.get("secret"))

# ---------- progressive lockout ----------
def locked(ip):
    with _faillock:
        f = _fail.get(ip)
        if f and f.get("until", 0) > time.time():
            return int(f["until"] - time.time())
    return 0

def note_fail(ip):
    # escalating, capped at 900s to avoid permanent DoS
    with _faillock:
        f = _fail.get(ip, {"n": 0, "until": 0}); f["n"] += 1; n = f["n"]
        delay = 0
        if n >= 5:  delay = 60
        if n >= 10: delay = 300
        if n >= 20: delay = 900
        if delay: f["until"] = time.time() + delay
        _fail[ip] = f
        return delay

def note_success(ip):
    with _faillock:
        _fail.pop(ip, None)

def rl_hit(ip):
    now = time.time()
    with _rllock:
        q = [t for t in _rl.get(ip, []) if now - t < RL_WINDOW]; q.append(now); _rl[ip] = q
        return len(q) > RL_MAX

# ---------- audit (append-only, NO secrets) ----------
def audit(event, user="", ip=""):
    try:
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "event": event, "user": user, "ip": ip}, separators=(",", ":"))
        fd = os.open(AUDIT_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.write(fd, (line + "\n").encode()); os.close(fd)
    except Exception:
        pass

def _cookie(name, val, ttl):
    return "%s=%s; Path=/; Max-Age=%d; HttpOnly; Secure; SameSite=Strict" % (name, val, ttl)
def _clear(name):
    return "%s=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict" % name

# ---------- HTTP ----------
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass   # never log request lines (no creds/cookies in logs)
    def _send(self, code, extra=None, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra: self.send_header(k, v)
        self.end_headers()
        if body: self.wfile.write(body)
    def _ip(self):
        return self.headers.get("X-Real-IP") or (self.headers.get("X-Forwarded-For", "").split(",")[0].strip()) or self.client_address[0]
    def _cookieval(self, name):
        ck = self.headers.get("Cookie", "")
        m = re.search(r'(?:^|;\s*)' + re.escape(name) + r'=([^;]+)', ck)
        return m.group(1) if m else None
    def _body(self):
        n = int(self.headers.get("Content-Length", "0")); raw = self.rfile.read(min(n, 4096))
        return json.loads(raw or b"{}")

    def do_GET(self):
        if self.path == "/_dashauth/verify":
            v = self._cookieval(COOKIE)
            if v and check_token(v): return self._send(204)
            return self._send(401)
        return self._send(404)

    def do_POST(self):
        ip = self._ip()
        if self.path == "/_dashauth/logout":
            u = ""
            v = self._cookieval(COOKIE); d = check_token(v) if v else None
            if d: u = d.get("u", "")
            audit("logout", u, ip)
            return self._send(204, [("Set-Cookie", _clear(COOKIE)), ("Set-Cookie", _clear(PCOOKIE))])

        lk = locked(ip)
        if lk or rl_hit(ip):
            audit("lockout", "", ip)
            return self._send(429, [("Retry-After", str(lk or RL_WINDOW))])

        if self.path == "/_dashauth/login":
            try:
                d = self._body(); user = str(d.get("u", "")); pw = str(d.get("p", "")); dash = str(d.get("dash", ""))
            except Exception:
                return self._send(400)
            time.sleep(0.4)  # blunt timing/brute-force
            if not htpasswd_ok(user, pw):
                note_fail(ip); audit("login_fail", user, ip); return self._send(401)
            if tfa_active(user):
                audit("otp_required", user, ip)
                pend = make_token(user, dash, PENDING_TTL, pend=True)
                body = json.dumps({"otp_required": True}).encode()
                return self._send(200, [("Set-Cookie", _cookie(PCOOKIE, pend, PENDING_TTL))], body)
            # 2FA not active -> password-only session (rollout/back-compat)
            note_success(ip); audit("login_success", user, ip)
            return self._send(204, [("Set-Cookie", _cookie(COOKIE, make_token(user, dash, TTL), TTL))])

        if self.path == "/_dashauth/verify-otp":
            pv = self._cookieval(PCOOKIE); pend = check_token(pv, pend=True) if pv else None
            if not pend:
                audit("otp_no_pending", "", ip); return self._send(401)
            user = pend.get("u", ""); dash = pend.get("d", "")
            try:
                otp = str(self._body().get("otp", ""))
            except Exception:
                return self._send(400)
            rec = load_2fa(user) or {}
            time.sleep(0.4)
            if rec.get("secret") and totp_verify(rec["secret"], otp):
                note_success(ip); audit("otp_success", user, ip)
                return self._send(204, [("Set-Cookie", _cookie(COOKIE, make_token(user, dash, TTL), TTL)),
                                        ("Set-Cookie", _clear(PCOOKIE))])
            if consume_backup(user, otp):
                note_success(ip); audit("backup_used", user, ip)
                return self._send(204, [("Set-Cookie", _cookie(COOKIE, make_token(user, dash, TTL), TTL)),
                                        ("Set-Cookie", _clear(PCOOKIE))])
            note_fail(ip); audit("otp_fail", user, ip); return self._send(401)

        return self._send(404)

class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    S(("127.0.0.1", PORT), H).serve_forever()

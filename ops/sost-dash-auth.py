#!/usr/bin/env python3
# SOST private-dashboard auth service (localhost-only; nginx fronts it).
# Replaces the native Basic Auth popup with a custom login + signed session cookie.
# - POST /_dashauth/login  {u,p,dash} -> verifies against the bcrypt htpasswd, sets signed cookie
# - GET  /_dashauth/verify            -> 200 if the session cookie is valid+unexpired, else 401 (nginx auth_request)
# - POST /_dashauth/logout            -> clears the cookie
# Secrets: signing key from /etc/sost/dash-auth.secret (600). No secret is ever logged or returned.
import http.server, socketserver, json, hmac, hashlib, base64, time, os, re, threading
HTPASSWD="/etc/nginx/auth/sost-admin.htpasswd"
SECRET_PATH="/etc/sost/dash-auth.secret"
PORT=18322
TTL=8*3600                      # session lifetime
COOKIE="sost_dash"
RL_WINDOW=300; RL_MAX=8         # 8 attempts / 5 min / ip
try:
    import bcrypt
except Exception:
    bcrypt=None
SECRET=open(SECRET_PATH,"rb").read().strip()
_rl={}; _rllock=threading.Lock()

def b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def b64ud(s): return base64.urlsafe_b64decode(s+"="*(-len(s)%4))

def sign(payload: bytes)->str:
    return hmac.new(SECRET,payload,hashlib.sha256).hexdigest()
def make_cookie(user,dash):
    body=json.dumps({"u":user,"d":dash,"exp":int(time.time())+TTL},separators=(",",":")).encode()
    p=b64u(body); return p+"."+sign(p.encode())
def check_cookie(val):
    try:
        p,sig=val.split(".",1)
        if not hmac.compare_digest(sig, sign(p.encode())): return None
        d=json.loads(b64ud(p)); 
        if int(d.get("exp",0))<time.time(): return None
        return d
    except Exception: return None

def htpasswd_ok(user,pw):
    if not bcrypt or not re.match(r'^[A-Za-z0-9_.@-]{1,64}$', user or ''): return False
    try:
        for ln in open(HTPASSWD):
            ln=ln.strip()
            if not ln or ":" not in ln: continue
            u,h=ln.split(":",1)
            if u==user and h.startswith(("$2y$","$2b$","$2a$")):
                return bcrypt.checkpw(pw.encode(), h.encode())
    except Exception: return False
    return False

def rl_hit(ip):
    now=time.time()
    with _rllock:
        q=[t for t in _rl.get(ip,[]) if now-t<RL_WINDOW]; q.append(now); _rl[ip]=q
        return len(q)>RL_MAX

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass   # never log request lines (no creds/cookies in logs)
    def _send(self,code,extra=None,body=b""):
        self.send_response(code)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        if extra:
            for k,v in extra: self.send_header(k,v)
        self.end_headers()
        if body: self.wfile.write(body)
    def _ip(self):
        return self.headers.get("X-Real-IP") or (self.headers.get("X-Forwarded-For","").split(",")[0].strip()) or self.client_address[0]
    def do_GET(self):
        if self.path=="/_dashauth/verify":
            ck=self.headers.get("Cookie","")
            m=re.search(r'(?:^|;\s*)'+COOKIE+r'=([^;]+)', ck)
            if m and check_cookie(m.group(1)): return self._send(204)
            return self._send(401)
        return self._send(404)
    def do_POST(self):
        if self.path=="/_dashauth/logout":
            return self._send(204,[("Set-Cookie",COOKIE+"=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict")])
        if self.path=="/_dashauth/login":
            ip=self._ip()
            if rl_hit(ip): return self._send(429)
            try:
                n=int(self.headers.get("Content-Length","0")); raw=self.rfile.read(min(n,4096))
                d=json.loads(raw or b"{}"); user=str(d.get("u","")); pw=str(d.get("p","")); dash=str(d.get("dash",""))
            except Exception: return self._send(400)
            time.sleep(0.4)  # blunt timing/brute-force
            if htpasswd_ok(user,pw):
                c="%s=%s; Path=/; Max-Age=%d; HttpOnly; Secure; SameSite=Strict"%(COOKIE,make_cookie(user,dash),TTL)
                return self._send(204,[("Set-Cookie",c)])
            return self._send(401)
        return self._send(404)

class S(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads=True
if __name__=="__main__":
    S(("127.0.0.1",PORT),H).serve_forever()

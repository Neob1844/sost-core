#!/usr/bin/env python3
"""Visit counter for sostcore.com (explorer) + geaspirit.com.

Counts UNIQUE visits (one per IP+UA+day, bot-filtered), seeded with a baseline
because nginx logs do not reach back to launch. Privacy: raw IPs are never
stored — only a daily salted hash for same-day dedup. JSON persistence, atomic.
"""
import json, os, re, hashlib, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DATA_DIR  = "/var/lib/visit-counter"
DATA_FILE = os.path.join(DATA_DIR, "counts.json")
SEED = {"sostcore": 3375, "geaspirit": 675}
SALT = "sost-vc-2026-a7"
BOT_RE = re.compile(
    r"bot|spider|crawl|slurp|curl|wget|python|httpclient|java/|go-http|libwww|"
    r"headless|phantom|puppeteer|playwright|monitor|uptime|pingdom|datadog|"
    r"newrelic|facebookexternal|whatsapp|telegram|preview|scan|semrush|ahrefs|"
    r"mj12|dotbot|bytespider|gptbot|claudebot|ccbot|petalbot|yandex|bingpreview",
    re.I)

_lock = threading.Lock()
_counts = {}
_seen = set()
_seen_day = ""


def _load():
    global _counts
    try:
        with open(DATA_FILE) as f:
            _counts = json.load(f)
    except Exception:
        _counts = {}
    for k, v in SEED.items():
        _counts.setdefault(k, v)


def _save():
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(_counts, f)
    os.replace(tmp, DATA_FILE)


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Cache-Control", "no-store")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        global _seen_day
        u = urlparse(self.path)
        if u.path.rstrip("/") != "/counter":
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        q = parse_qs(u.query)
        site = (q.get("site", [""])[0] or "").strip()
        if site not in SEED:
            self.send_response(400)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"bad site"}')
            return
        do_hit = q.get("hit", ["0"])[0] == "1"
        ua = self.headers.get("User-Agent", "")
        xff = self.headers.get("X-Forwarded-For", "")
        ip = xff.split(",")[0].strip() if xff else self.client_address[0]
        counted = False
        with _lock:
            day = _today()
            if day != _seen_day:
                _seen_day = day
                _seen.clear()
            if do_hit and ua and not BOT_RE.search(ua):
                h = hashlib.sha256(
                    ("|".join([SALT, day, site, ip, ua])).encode()).hexdigest()
                if h not in _seen:
                    _seen.add(h)
                    _counts[site] = _counts.get(site, SEED[site]) + 1
                    _save()
                    counted = True
            n = _counts.get(site, SEED[site])
        body = json.dumps({"site": site, "count": n, "counted": counted}).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    _load()
    _save()
    ThreadingHTTPServer(("127.0.0.1", 8120), H).serve_forever()

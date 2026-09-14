#!/usr/bin/env python3
"""SOST market-history gateway — one upstream fetch shared by every visitor.

Why it exists: the explorer's price charts used to call CoinGecko from the browser,
so every visitor spent their own slice of a per-IP rate limit, and a single page load
asked for the same series several times over. The keyless tier answers a burst with
HTTP 429, and a 429 body carries no `prices`, which is indistinguishable from an empty
range unless you look at the status code. This gateway moves the fetching server-side:

    100 visitors -> this gateway -> (cache hit, or ONE upstream request) -> CoinGecko

What it is NOT: a general HTTP proxy. It accepts no URL, no host and no path from the
caller. The only thing a request can choose is one (asset, vs, range) triple out of a
fixed allowlist, which is then mapped to a URL built here from constants. There is no
input that reaches urllib except integers and strings this file already knows.

Behaviour:
  * shared cache, TTL scaled to the range (a 5Y series does not need re-fetching often);
  * identical in-flight requests are deduplicated — the second caller waits for the first;
  * upstream concurrency capped, with a minimum gap between requests;
  * on 429/5xx/timeout/network error, the last good dataset is served as `stale` while it
    is still inside the stale window, instead of leaving a chart blank;
  * per-IP rate limit, so one client cannot drain the shared budget.

Listens on 127.0.0.1:18310; nginx /api/market-history proxies to it.
No credentials of any kind are used or stored: the upstream endpoint is keyless.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN = ('127.0.0.1', 18310)
UPSTREAM = 'https://api.coingecko.com/api/v3/coins/{asset}/market_chart'
USER_AGENT = 'sost-market-proxy/1.0 (+https://sostcore.com)'

# ---------------------------------------------------------------- allowlist
# Every dimension a caller can influence is enumerated here. Anything else is a 400.
ASSETS = {'tether-gold', 'pax-gold', 'bitcoin'}
VS = {'usd', 'btc'}
# range label -> days asked of the upstream API.
RANGES = {'1H': 1, '4H': 1, '8H': 1, '24H': 1, '3D': 3, '7D': 7,
          '30D': 30, '6M': 180, '1Y': 365, '3Y': 1095, '5Y': 1825}
DAYS = set(RANGES.values())
# Canonical label per days value, for echoing back when the caller sent `days`.
DAYS_LABEL = {1: '24H', 3: '3D', 7: '7D', 30: '30D', 180: '6M',
              365: '1Y', 1095: '3Y', 1825: '5Y'}

# ---------------------------------------------------------------- freshness
# TTL by days. Short ranges move; a 5Y line does not change meaningfully within hours.
# The cache entry is keyed by (asset, vs, days) because that IS the upstream dataset:
# 1H/4H/8H/24H all ask upstream for days=1 and the client slices the window locally, so
# they legitimately share one entry rather than fetching the same series four times.
TTL = {1: 120, 3: 300, 7: 300, 30: 900, 180: 3600, 365: 3600, 1095: 21600, 1825: 21600}
# How long past the TTL a stale copy may still answer when upstream is failing.
STALE_FACTOR = 24
STALE_MAX = 7 * 24 * 3600
# A range the plan will never serve is not worth re-asking hourly.
OUT_OF_RANGE_TTL = 12 * 3600

TIMEOUT = {1: 15, 3: 15, 7: 15, 30: 25, 180: 25, 365: 25, 1095: 35, 1825: 35}

MAX_UPSTREAM_CONCURRENCY = 2
MIN_UPSTREAM_GAP = 0.35          # seconds between upstream requests
# Deliberately small. A caller is blocked on this request, and the client has its own
# backoff ladder, so patience belongs there: if the gateway sat through a long retry
# chain the browser would time out first and the round trip would be wasted. Answer
# fast — from stale if possible, with a 503 otherwise — and let the client come back.
UPSTREAM_ATTEMPTS = 2
UPSTREAM_BACKOFF_CAP = 3.0

RATE_LIMIT_PER_MIN = 120         # per client IP

_cache = {}                      # key -> {'prices', 'fetched_at', 'status'}
_cache_lock = threading.Lock()
_inflight = {}                   # key -> threading.Event
_inflight_lock = threading.Lock()
_upstream_sem = threading.BoundedSemaphore(MAX_UPSTREAM_CONCURRENCY)
_gap_lock = threading.Lock()
_last_upstream = [0.0]
_rate = {}                       # ip -> [timestamps]
_rate_lock = threading.Lock()

STATS = {'client_requests': 0, 'upstream_requests': 0, 'cache_hits': 0,
         'dedup_hits': 0, 'stale_served': 0, 'errors': 0, 'rejected': 0,
         'peak_upstream_concurrency': 0}
_stats_lock = threading.Lock()
_active_upstream = [0]


def _bump(name, n=1):
    with _stats_lock:
        STATS[name] = STATS.get(name, 0) + n


def _rate_ok(ip):
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate.get(ip, []) if now - t < 60]
        if len(hits) >= RATE_LIMIT_PER_MIN:
            _rate[ip] = hits
            return False
        hits.append(now)
        _rate[ip] = hits
        return True


def parse_params(query):
    """Validate the query against the allowlist. Returns (asset, vs, label, days) or raises
    ValueError. Nothing here is interpolated into a URL until it has passed this function."""
    q = urllib.parse.parse_qs(query, keep_blank_values=False)

    def one(name):
        v = q.get(name)
        return v[0].strip() if v else ''

    asset = one('asset')
    if asset not in ASSETS:
        raise ValueError('asset')
    vs = one('vs') or 'usd'
    if vs not in VS:
        raise ValueError('vs')

    label = one('range').upper()
    days_raw = one('days')
    if label:
        if label not in RANGES:
            raise ValueError('range')
        days = RANGES[label]
    elif days_raw:
        if not days_raw.isdigit() or int(days_raw) not in DAYS:
            raise ValueError('days')
        days = int(days_raw)
        label = DAYS_LABEL[days]
    else:
        raise ValueError('range')
    return asset, vs, label, days


def _fetch_upstream(asset, vs, days):
    """One upstream request. Returns (prices, reason). prices is None on failure."""
    url = UPSTREAM.format(asset=asset) + '?' + urllib.parse.urlencode(
        {'vs_currency': vs, 'days': days})
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT,
                                               'Accept': 'application/json'})
    with _upstream_sem:
        with _gap_lock:
            wait = MIN_UPSTREAM_GAP - (time.time() - _last_upstream[0])
            if wait > 0:
                time.sleep(wait)
            _last_upstream[0] = time.time()
        with _stats_lock:
            _active_upstream[0] += 1
            if _active_upstream[0] > STATS['peak_upstream_concurrency']:
                STATS['peak_upstream_concurrency'] = _active_upstream[0]
        _bump('upstream_requests')
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT[days]) as r:
                body = json.loads(r.read().decode('utf-8'))
            prices = body.get('prices') if isinstance(body, dict) else None
            if prices:
                return prices, 'ok'
            if isinstance(body, dict) and isinstance(body.get('status'), dict) \
                    and body['status'].get('error_code') == 429:
                return None, 'rate_limited'
            return [], 'empty'
        except urllib.error.HTTPError as e:
            if e.code == 429:
                return None, 'rate_limited'
            # The keyless tier refuses anything older than 365 days with 401/10012
            # ("Your request exceeds the allowed time range"). That is a permanent
            # property of the plan, not a transient failure: 3Y and 5Y can never be
            # served. Retrying it forever would spend the shared budget on a request
            # that cannot succeed, so it is answered as an empty range and cached.
            if e.code in (401, 403):
                try:
                    detail = json.loads(e.read().decode('utf-8'))
                except Exception:
                    detail = {}
                status = (detail.get('error') or detail).get('status') or {}
                if status.get('error_code') == 10012 or e.code == 401:
                    return [], 'out_of_range'
            return None, 'http_error'
        except Exception:
            return None, 'network'
        finally:
            with _stats_lock:
                _active_upstream[0] -= 1


def _refresh(key, asset, vs, days):
    """Fetch with backoff and store. Caller must hold the in-flight slot for `key`."""
    reason = 'network'
    for attempt in range(UPSTREAM_ATTEMPTS):
        prices, reason = _fetch_upstream(asset, vs, days)
        if prices is not None:
            status = 'ok' if prices else ('out_of_range' if reason == 'out_of_range'
                                          else 'empty')
            with _cache_lock:
                _cache[key] = {'prices': prices, 'fetched_at': time.time(),
                               'status': status}
            return 'fresh' if prices else status
        if attempt + 1 < UPSTREAM_ATTEMPTS:
            time.sleep(min(UPSTREAM_BACKOFF_CAP,
                           (1.5 if reason == 'rate_limited' else 0.7) * (2 ** attempt)))
    _bump('errors')
    return reason


def get_series(asset, vs, days):
    """Cache -> dedup -> upstream. Returns (payload_dict, http_status)."""
    key = '%s|%s|%d' % (asset, vs, days)
    ttl, now = TTL[days], time.time()

    with _cache_lock:
        entry = _cache.get(key)
    if entry and entry.get('status') == 'out_of_range':
        ttl = OUT_OF_RANGE_TTL
    if entry and now - entry['fetched_at'] < ttl:
        _bump('cache_hits')
        return _payload(entry, 'cached', now), 200

    # Deduplicate: whoever creates the event fetches, everyone else waits for it.
    with _inflight_lock:
        ev = _inflight.get(key)
        leader = ev is None
        if leader:
            ev = threading.Event()
            _inflight[key] = ev
    if not leader:
        _bump('dedup_hits')
        ev.wait(timeout=60)
        with _cache_lock:
            entry = _cache.get(key)
        if entry:
            return _payload(entry, 'cached', time.time()), 200
        return {'error': 'upstream_unavailable', 'source_status': 'error'}, 503

    try:
        outcome = _refresh(key, asset, vs, days)
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)
        ev.set()

    with _cache_lock:
        entry = _cache.get(key)
    if outcome in ('fresh', 'empty', 'out_of_range') and entry:
        return _payload(entry, 'fresh', time.time()), 200
    # Upstream failed. Serve the last good copy while it is still inside the stale window.
    if entry:
        age = time.time() - entry['fetched_at']
        if age < min(ttl * STALE_FACTOR, STALE_MAX):
            _bump('stale_served')
            return _payload(entry, 'stale', time.time(), reason=outcome), 200
    return {'error': outcome, 'source_status': 'error'}, 503


def _payload(entry, status, now, reason=None):
    if entry.get('status') == 'out_of_range':
        status = 'out_of_range'
    p = {'prices': entry['prices'],
         'source_status': status,
         'age_s': int(now - entry['fetched_at'])}
    if reason:
        p['upstream_error'] = reason
    return p


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'sost-market-proxy'

    def log_message(self, *a):
        pass

    def _send(self, status, obj, cache_seconds=0):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control',
                         'public, max-age=%d' % cache_seconds if cache_seconds
                         else 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path.rstrip('/')
        if path.endswith('/stats'):
            with _stats_lock:
                self._send(200, dict(STATS, cached_series=len(_cache)))
            return
        if not (path == '' or path.endswith('/market-history')):
            self._send(404, {'error': 'not_found'})
            return

        ip = self.headers.get('X-Real-IP') or self.client_address[0]
        if not _rate_ok(ip):
            _bump('rejected')
            self._send(429, {'error': 'rate_limited_local', 'source_status': 'error'})
            return

        _bump('client_requests')
        try:
            asset, vs, label, days = parse_params(parsed.query)
        except ValueError as e:
            _bump('rejected')
            self._send(400, {'error': 'bad_%s' % e, 'source_status': 'error'})
            return

        payload, status = get_series(asset, vs, days)
        payload.update({'asset': asset, 'vs': vs, 'range': label, 'days': days})
        self._send(status, payload, cache_seconds=TTL[days] // 2 if status == 200 else 0)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Content-Length', '0')
        self.end_headers()


WARM_INTERVAL = 20          # seconds between background refreshes
WARM_LEAD = 0.75            # refresh once an entry is this far through its TTL


def _warm_loop():
    """Keep the working set warm with a trickle, so a visitor never pays for a cold
    entry and never depends on arriving at the right moment.

    It only refreshes series somebody has already asked for — nothing is fetched
    speculatively — one at a time, well spaced, and through the same dedup and
    concurrency limits as a request. A range the plan cannot serve is skipped."""
    while True:
        time.sleep(WARM_INTERVAL)
        try:
            now = time.time()
            due = None
            with _cache_lock:
                for key, entry in _cache.items():
                    if entry.get('status') == 'out_of_range':
                        continue
                    days = int(key.split('|')[2])
                    age = now - entry['fetched_at']
                    if age < TTL[days] * WARM_LEAD:
                        continue
                    if due is None or age / TTL[days] > due[1]:
                        due = (key, age / TTL[days])
            if not due:
                continue
            key = due[0]
            asset, vs, days = key.split('|')
            days = int(days)
            # Refresh directly rather than through get_series: the entry is still inside
            # its TTL — that is the point of warming it early — so get_series would just
            # hand back the cache. Take the in-flight slot so a real request arriving now
            # waits for this fetch instead of starting a second one.
            with _inflight_lock:
                if key in _inflight:
                    continue            # a request is already fetching it
                ev = threading.Event()
                _inflight[key] = ev
            try:
                _refresh(key, asset, vs, days)
            finally:
                with _inflight_lock:
                    _inflight.pop(key, None)
                ev.set()
        except Exception:
            pass                        # a warm pass must never take the service down


def main():
    threading.Thread(target=_warm_loop, daemon=True).start()
    srv = ThreadingHTTPServer(LISTEN, Handler)
    srv.daemon_threads = True
    srv.serve_forever()


if __name__ == '__main__':
    main()

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

OHLC candles (mode=ohlc) are a separate dataset with their own cache keys: see the
"OHLC candles" section. They are real provider candles only, never derived from closes.

Listens on 127.0.0.1:18310; nginx /api/market-history proxies to it.
No credentials of any kind are used or stored: the upstream endpoint is keyless.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN = ('127.0.0.1', 18310)
# The cache lives in memory; this file is its copy on disk, so a restart does not start
# cold and send every visitor's first request upstream at once. Small and self-describing
# on purpose — a JSON file is enough for a few dozen series and needs no database.
STATE_FILE = os.environ.get('SOST_MARKET_CACHE', '/var/lib/sost/market-cache.json')
STATE_SAVE_INTERVAL = 60      # seconds between saves, and saved again on a clean stop
# Optional read-only provider key. Raises the rate limit; it does NOT extend the 365-day
# history cap, so it does not make 3Y or 5Y work. Read from the environment (systemd
# EnvironmentFile) — never from the repository, never sent to a browser, never logged.
API_KEY = os.environ.get('COINGECKO_API_KEY', '').strip()
UPSTREAM = 'https://api.coingecko.com/api/v3/coins/{asset}/market_chart'
# Long-history source (3Y/5Y). CoinGecko's keyless plan hard-caps history at 365 days,
# so multi-year ranges come from Yahoo Finance's public chart API instead: free, no key,
# daily candles going back years for all four assets. Ratios (vs=btc/eth) are derived
# from two USD series aligned by UTC date — never by mixing dates. Short ranges keep
# using CoinGecko (it serves intraday granularity Yahoo's daily candles cannot).
YAHOO_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/{sym}-USD'
YAHOO_SYM = {'tether-gold': 'XAUT', 'pax-gold': 'PAX-gold-placeholder',
             'bitcoin': 'BTC', 'ethereum': 'ETH'}
# pax-gold's Yahoo symbol is PAXG (not pax-gold); set explicitly to avoid the dash clash.
YAHOO_SYM['pax-gold'] = 'PAXG'
LONG_HISTORY_DAYS = 365          # strictly greater than this -> Yahoo
USER_AGENT = 'sost-market-proxy/1.0 (+https://sostcore.com)'

# ---------------------------------------------------------------- allowlist
# Every dimension a caller can influence is enumerated here. Anything else is a 400.
# `ethereum` and `eth` are here for the same reason `bitcoin` and `btc` are: the
# explorer draws the two gold assets priced in a crypto denominator (vs=btc / vs=eth)
# and, alongside them, that denominator's own USD line (asset=bitcoin / asset=ethereum,
# vs=usd). Nothing else about the request shape changes.
ASSETS = {'tether-gold', 'pax-gold', 'bitcoin', 'ethereum'}
VS = {'usd', 'btc', 'eth'}
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

RATE_LIMIT_PER_MIN = 120         # per client IP, requests that would reach an upstream provider
RATE_LIMIT_CACHED_PER_MIN = 600  # per client IP, every request (anti-abuse; a fresh cache hit costs nothing upstream)

_cache = {}                      # key -> {'prices', 'fetched_at', 'status'}
_cache_lock = threading.Lock()
_inflight = {}                   # key -> threading.Event
_inflight_lock = threading.Lock()
_upstream_sem = threading.BoundedSemaphore(MAX_UPSTREAM_CONCURRENCY)
_gap_lock = threading.Lock()
_last_upstream = [0.0]
_rate = {}                       # ip -> [timestamps]   (upstream-touching requests)
_rate_all = {}                   # ip -> [timestamps]   (all requests)
_rate_lock = threading.Lock()

STATS = {'client_requests': 0, 'upstream_requests': 0, 'cache_hits': 0,
         'ohlc_upstream_requests': 0, 'ohlc_cache_hits': 0, 'ohlc_rejected_responses': 0, 'json_cache_hits': 0,
         'dedup_hits': 0, 'stale_served': 0, 'errors': 0, 'rejected': 0,
         'peak_upstream_concurrency': 0}
_stats_lock = threading.Lock()
_active_upstream = [0]
_last_upstream_failure = [0.0]      # when upstream last refused us
_last_upstream_success = [0.0]
_last_upstream_429 = [0.0]


def save_state():
    """Write the cache to disk. Best effort and atomic: a half-written file would be worse
    than no file, so it is written beside the target and renamed."""
    try:
        with _cache_lock:
            snapshot = {k: dict(v) for k, v in _cache.items()}
        d = os.path.dirname(STATE_FILE)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = STATE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'version': 1, 'saved_at': time.time(), 'entries': snapshot}, f)
        os.replace(tmp, STATE_FILE)
        return True
    except Exception:
        return False


def load_state():
    """Restore the cache on boot. Entries keep their ORIGINAL fetched_at, so a restored
    entry is exactly as old as it really is: still fresh inside its TTL, stale-eligible
    past it, and dropped once it is past the stale window. A restart must not make data
    look newer than it is."""
    try:
        with open(STATE_FILE) as f:
            blob = json.load(f)
    except Exception:
        return 0
    if not isinstance(blob, dict) or blob.get('version') != 1:
        return 0
    now, restored = time.time(), 0
    for key, entry in (blob.get('entries') or {}).items():
        try:
            parts = key.split('|')
            if parts[0] == 'json':
                kind = parts[1] if len(parts) > 1 else ''
                ok = (kind == 'spot' and len(parts) == 3 and parts[2] in SPOT_GROUPS) or \
                     (kind == 'fx' and parts[2:] == ['latest']) or \
                     (kind == 'fxh' and len(parts) == 4 and parts[2] in FX_CODES and parts[3] in FXHIST_BACK)
                age = now - float(entry.get('fetched_at', 0))
                if not ok or not _json_ok(kind, entry.get('body')) or age < 0 \
                        or age > min(json_ttl(key) * STALE_FACTOR, STALE_MAX):
                    continue
                with _cache_lock:
                    _cache[key] = {'body': entry['body'], 'fetched_at': float(entry['fetched_at']), 'status': 'ok'}
                restored += 1
                continue
            if len(parts) == 4 and parts[3] == 'ohlc':
                if parts[2] not in OHLC_PLAN or not ((parts[1] == 'usd' and parts[0] in OHLC_ASSETS)
                                                    or MARKETS.get((parts[0], parts[1]))) \
                        or not isinstance(entry.get('candles'), list):
                    continue
                age = now - float(entry.get('fetched_at', 0))
                if age < 0 or age > min(OHLC_TTL[parts[2]] * STALE_FACTOR, STALE_MAX):
                    continue
                with _cache_lock:
                    _cache[key] = {k: entry.get(k) for k in OHLC_FIELDS}
                    _cache[key]['fetched_at'] = float(entry['fetched_at'])
                restored += 1
                continue
            if len(parts) != 3 or parts[0] not in ASSETS or parts[1] not in VS:
                continue
            days = int(parts[2])
            if days not in DAYS or not isinstance(entry.get('prices'), list):
                continue
            age = now - float(entry.get('fetched_at', 0))
            limit = (OUT_OF_RANGE_TTL if entry.get('status') == 'out_of_range'
                     else min(TTL[days] * STALE_FACTOR, STALE_MAX))
            if age < 0 or age > limit:
                continue                      # too old to be worth anything
            with _cache_lock:
                _cache[key] = {'prices': entry['prices'],
                               'fetched_at': float(entry['fetched_at']),
                               'status': entry.get('status', 'ok')}
            restored += 1
        except Exception:
            continue
    return restored


def _save_loop():
    while True:
        time.sleep(STATE_SAVE_INTERVAL)
        save_state()


def _bump(name, n=1):
    with _stats_lock:
        STATS[name] = STATS.get(name, 0) + n


def _rate_ok(ip, table=None, limit=None):
    table = _rate if table is None else table
    limit = RATE_LIMIT_PER_MIN if limit is None else limit
    now = time.time()
    with _rate_lock:
        hits = [t for t in table.get(ip, []) if now - t < 60]
        if len(hits) >= limit:
            table[ip] = hits
            return False
        hits.append(now)
        table[ip] = hits
        return True


def _fresh(key, ttl):
    """True when `key` would be answered from a fresh cache entry (no upstream request)."""
    with _cache_lock:
        e = _cache.get(key)
    if not e:
        return False
    if e.get('status') == 'out_of_range':
        ttl = OUT_OF_RANGE_TTL
    return time.time() - e['fetched_at'] < ttl


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


def parse_ohlc_params(query):
    """mode=ohlc: (asset, vs, range label) from the allowlist. Raises ValueError. A cross
    pair is accepted only where MARKETS lists it (a real market, or explicitly none)."""
    q = urllib.parse.parse_qs(query, keep_blank_values=False)
    one = lambda n: (q.get(n) or [''])[0].strip()
    asset, vs = one('asset'), one('vs') or 'usd'
    if vs == 'usd':
        if asset not in OHLC_ASSETS:
            raise ValueError('asset')
    elif (asset, vs) not in MARKETS:
        raise ValueError('vs')                 # e.g. bitcoin/btc: not a market
    label = one('range').upper()
    if label not in OHLC_PLAN:
        raise ValueError('range')
    return asset, vs, label


def _yahoo_usd_series(sym, days):
    """Daily USD closes for one Yahoo symbol over the trailing `days`. [] on failure."""
    now = int(time.time())
    url = YAHOO_URL.format(sym=sym) + '?' + urllib.parse.urlencode(
        {'period1': now - days * 86400, 'period2': now, 'interval': '1d'})
    req = urllib.request.Request(
        url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT[days]) as r:
        body = json.loads(r.read().decode('utf-8'))
    res = (body.get('chart') or {}).get('result')
    if not res:
        return []
    r0 = res[0]
    ts = r0.get('timestamp') or []
    quote = ((r0.get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
    out = []
    for t, c in zip(ts, quote):
        if c is not None and c > 0:
            out.append([int(t) * 1000, float(c)])
    return out


def _utc_day(ms):
    return time.strftime('%Y-%m-%d', time.gmtime(ms // 1000))


def _fetch_yahoo(asset, vs, days):
    """Long-history fetch (3Y/5Y). Returns (prices, reason) like _fetch_upstream.
    vs=usd -> the asset's own USD close series. vs=btc/eth -> asset_USD / denom_USD,
    aligned by UTC date so prices from different days are never divided together."""
    sym = YAHOO_SYM[asset]
    try:
        base = _yahoo_usd_series(sym, days)
        if not base:
            _last_upstream_failure[0] = time.time()
            return [], 'empty'
        if vs == 'usd':
            _last_upstream_success[0] = time.time()
            return base, 'ok'
        denom_sym = 'BTC' if vs == 'btc' else 'ETH'
        denom = _yahoo_usd_series(denom_sym, days)
        if not denom:
            _last_upstream_failure[0] = time.time()
            return [], 'empty'
        dmap = {}
        for t, c in denom:
            dmap[_utc_day(t)] = c
        out = []
        for t, c in base:
            dc = dmap.get(_utc_day(t))
            if dc and dc > 0:
                out.append([t, c / dc])
        if not out:
            return [], 'empty'
        _last_upstream_success[0] = time.time()
        return out, 'ok'
    except urllib.error.HTTPError as e:
        _last_upstream_failure[0] = time.time()
        return None, ('rate_limited' if e.code == 429 else 'http_error')
    except Exception:
        _last_upstream_failure[0] = time.time()
        return None, 'network'


def _fetch_upstream(asset, vs, days):
    # 3Y/5Y exceed CoinGecko's keyless 365-day cap -> long-history source (Yahoo).
    if days > LONG_HISTORY_DAYS:
        _bump('upstream_requests')
        return _fetch_yahoo(asset, vs, days)
    """One upstream request. Returns (prices, reason). prices is None on failure."""
    url = UPSTREAM.format(asset=asset) + '?' + urllib.parse.urlencode(
        {'vs_currency': vs, 'days': days})
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    if API_KEY:
        headers['x-cg-demo-api-key'] = API_KEY
    req = urllib.request.Request(url, headers=headers)
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
                _last_upstream_success[0] = time.time()
                return prices, 'ok'
            if isinstance(body, dict) and isinstance(body.get('status'), dict) \
                    and body['status'].get('error_code') == 429:
                _last_upstream_failure[0] = _last_upstream_429[0] = time.time()
                return None, 'rate_limited'
            return [], 'empty'
        except urllib.error.HTTPError as e:
            if e.code == 429:
                _last_upstream_failure[0] = _last_upstream_429[0] = time.time()
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
            _last_upstream_failure[0] = time.time()
            return None, 'http_error'
        except Exception:
            _last_upstream_failure[0] = time.time()
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


# ---------------------------------------------------------------- OHLC candles
# A separate dataset from the LINE series above: its own cache keys
# (asset|vs|RANGE|ohlc), its own TTLs, its own upstream slots. Only REAL candles of a
# REAL market are served — every candle is one provider interval of one traded market,
# exactly as the provider returned it. Nothing is derived from the close series, nothing
# is aggregated, resampled or interpolated, a cross rate is NEVER computed by dividing two
# USD candles (the high of a ratio is not the ratio of the highs), and an invalid candle
# is dropped (and counted), never repaired.
#
# Markets (each verified against the live API on 2026-10-11 before it was written):
#   X/USD      Yahoo Finance chart API (BTC-USD, ETH-USD, PAXG-USD, XAUT-USD)
#   XAUT/BTC   Binance spot XAUTBTC   (listed March 2026: long ranges start at the listing)
#   PAXG/BTC   Binance spot PAXGBTC
#   PAXG/ETH   Kraken spot PAXGETH
#   XAUT/ETH   no market on Binance, Kraken, Bitfinex, OKX, KuCoin, Gate or Yahoo ->
#              answered as `no_market`, never synthesized.
#   CODE/USDT  Binance spot, for the assets the Markets page charts (sost-markets.html):
#              XAUT PAXG BTC ETH BNB SOL XRP DOT LINK LTC BCH XLM USDC. Same market the page
#              used to call from every browser; now one shared, cached fetch through here.
# CoinGecko /ohlc was also verified real, but it has no volume, only 30m/4h/4d candles
# and shares the keyless budget the LINE charts depend on, so it is not used.
# Each payload counts `no_trade` candles (high == low: nobody traded in that interval).
# Thin cross markets have many of them at short ranges; the client uses the count to
# say so instead of drawing a row of flat dashes.
OHLC_ASSETS = ASSETS
OHLC_PLAN = {'1H': ('5m', 3600), '4H': ('5m', 4 * 3600), '8H': ('15m', 8 * 3600),
             '24H': ('30m', 86400), '3D': ('1h', 3 * 86400), '7D': ('90m', 7 * 86400),
             '30D': ('1d', 30 * 86400), '6M': ('1d', 182 * 86400), '1Y': ('1wk', 365 * 86400),
             '3Y': ('1wk', 1095 * 86400), '5Y': ('1mo', 1826 * 86400)}
INTERVAL_S = {'1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '90m': 5400, '4h': 14400,
              '1d': 86400, '1wk': 7 * 86400, '1mo': 31 * 86400, '15d': 15 * 86400}
# Exchanges have no 90m candle: 7D uses their real 4h candle; Kraken has no monthly
# candle: 5Y uses its real 15-day candle. Always a native interval of that venue.
VENUE_PLAN = {'7D': ('4h', 7 * 86400)}
KRAKEN_5Y = ('15d', 1826 * 86400)
BINANCE_IV = {'1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m', '1h': '1h', '4h': '4h', '1d': '1d', '1wk': '1w', '1mo': '1M'}
KRAKEN_IV = {'5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440, '1wk': 10080, '15d': 21600}
MARKETS = {('tether-gold', 'btc'): ('binance', 'XAUTBTC', 'XAUT'),
           ('pax-gold', 'btc'): ('binance', 'PAXGBTC', 'PAXG'),
           ('pax-gold', 'eth'): ('kraken', 'PAXGETH', 'PAXG'),
           ('tether-gold', 'eth'): None}       # no real market anywhere
USDT_CODES = ('XAUT', 'PAXG', 'BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'DOT', 'LINK', 'LTC', 'BCH', 'XLM', 'USDC')
MARKETS.update({(c, 'usdt'): ('binance', c + 'USDT', c) for c in USDT_CODES})
# Liquid USDT books trade every minute: 1H uses the real 1m candle (60 of them) there.
USDT_PLAN = {'1H': ('1m', 3600), '7D': ('4h', 7 * 86400)}
BINANCE_URL = 'https://api.binance.com/api/v3/klines'
KRAKEN_URL = 'https://api.kraken.com/0/public/OHLC'
OHLC_TTL = {'1H': 60, '4H': 60, '8H': 120, '24H': 120, '3D': 300, '7D': 300,
            '30D': 900, '6M': 3600, '1Y': 3600, '3Y': 21600, '5Y': 21600}
OHLC_TIMEOUT = 15
# One slot + gap per provider: a slow or limited venue never delays another.
_venue = {v: {'sem': threading.BoundedSemaphore(n), 'lock': threading.Lock(), 'last': [0.0], 'gap': g}
          for v, n, g in (('yahoo', 2, MIN_UPSTREAM_GAP), ('binance', 2, 0.25), ('kraken', 1, 1.6))}


def ohlc_key(asset, vs, label):
    return '%s|%s|%s|ohlc' % (asset, vs, label)


def ohlc_plan(asset, vs, label):
    """(venue, symbol, interval, window_s, volume_unit) or None when no real market exists."""
    if vs == 'usd':
        iv, win = OHLC_PLAN[label]
        return 'yahoo', YAHOO_SYM[asset] + '-USD', iv, win, 'USD'
    m = MARKETS.get((asset, vs))
    if m is None:
        return None
    venue, sym, base = m
    iv, win = (USDT_PLAN if vs == 'usdt' else VENUE_PLAN).get(label, OHLC_PLAN[label])
    if venue == 'kraken' and label == '5Y':
        iv, win = KRAKEN_5Y
    return venue, sym, iv, win, base


def validate_ohlc(ts, quote):
    """Provider arrays -> (candles, dropped_null, dropped_invalid) or raises ValueError.
    Arrays of different lengths mean the response cannot be trusted at all: rejected
    whole. Otherwise a candle with a missing/non-positive value is dropped as null, a
    candle that breaks low <= min(open, close), high >= max(open, close), low <= high
    is dropped as invalid. Kept candles are passed through unchanged."""
    cols = [quote.get(k) for k in ('open', 'high', 'low', 'close')]
    if not isinstance(ts, list) or any(not isinstance(c, list) for c in cols):
        raise ValueError('missing_arrays')
    if any(len(c) != len(ts) for c in cols):
        raise ValueError('length_mismatch')
    vol = quote.get('volume')
    if not isinstance(vol, list) or len(vol) != len(ts):
        vol = None
    out, null, bad = [], 0, 0
    for i, t in enumerate(ts):
        o, h, l, c = (col[i] for col in cols)
        if t is None or any(not isinstance(x, (int, float)) or x <= 0 for x in (o, h, l, c)):
            null += 1
            continue
        if not (l <= min(o, c) and h >= max(o, c) and l <= h):
            bad += 1
            continue
        v = vol[i] if vol and isinstance(vol[i], (int, float)) and vol[i] >= 0 else None
        out.append([int(t) * 1000, float(o), float(h), float(l), float(c), v])
    return out, null, bad


def _rows_to_arrays(rows, ti, oi, hi, li, ci, vi, t_scale):
    """Exchange row lists -> the column arrays validate_ohlc checks (strings -> floats)."""
    def f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    ts = [int(r[ti]) // t_scale if r and r[ti] is not None else None for r in rows]
    return ts, {'open': [f(r[oi]) for r in rows], 'high': [f(r[hi]) for r in rows],
                'low': [f(r[li]) for r in rows], 'close': [f(r[ci]) for r in rows],
                'volume': [f(r[vi]) for r in rows]}


def _venue_get(venue, url):
    v = _venue[venue]
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with v['sem']:
        with v['lock']:
            wait = v['gap'] - (time.time() - v['last'][0])
            if wait > 0:
                time.sleep(wait)
            v['last'][0] = time.time()
        _bump('ohlc_upstream_requests')
        with urllib.request.urlopen(req, timeout=OHLC_TIMEOUT) as r:
            return json.loads(r.read().decode('utf-8'))


def _fetch_ohlc(asset, vs, label):
    """One upstream request. Returns (result_dict, reason); result is None on failure."""
    plan = ohlc_plan(asset, vs, label)
    if plan is None:
        return None, 'no_market'
    venue, sym, interval, window, vol_unit = plan
    now = int(time.time())
    start = now - window - INTERVAL_S[interval]
    try:
        if venue == 'yahoo':
            body = _venue_get('yahoo', YAHOO_URL.format(sym=sym[:-4]) + '?' + urllib.parse.urlencode(
                {'interval': interval, 'period1': start, 'period2': now}))
            res = (body.get('chart') or {}).get('result') if isinstance(body, dict) else None
            if not res:
                return None, 'empty'
            r0 = res[0]
            if (r0.get('meta') or {}).get('dataGranularity') not in (None, interval):
                return None, 'granularity_mismatch'       # never relabel another interval
            ts, quote = r0.get('timestamp') or [], ((r0.get('indicators') or {}).get('quote') or [{}])[0]
            source = 'yahoo-finance'
        elif venue == 'binance':
            body = _venue_get('binance', BINANCE_URL + '?' + urllib.parse.urlencode(
                {'symbol': sym, 'interval': BINANCE_IV[interval], 'startTime': start * 1000, 'limit': 1000}))
            if not isinstance(body, list):
                return None, 'empty'
            ts, quote = _rows_to_arrays(body, 0, 1, 2, 3, 4, 5, 1000)
            source = 'binance ' + sym
        else:
            body = _venue_get('kraken', KRAKEN_URL + '?' + urllib.parse.urlencode(
                {'pair': sym, 'interval': KRAKEN_IV[interval], 'since': start}))
            if not isinstance(body, dict) or body.get('error'):
                return None, ('rate_limited' if 'Too many' in str(body.get('error')) else 'http_error')
            rows = next((v for k, v in (body.get('result') or {}).items() if k != 'last'), [])
            ts, quote = _rows_to_arrays(rows, 0, 1, 2, 3, 4, 6, 1)
            source = 'kraken ' + sym
    except urllib.error.HTTPError as e:
        return None, ('rate_limited' if e.code in (418, 429) else 'http_error')
    except Exception:
        return None, 'network'
    try:
        candles, null, bad = validate_ohlc(ts, quote)
    except ValueError as e:
        _bump('ohlc_rejected_responses')
        return None, 'malformed_' + str(e)
    cut = (now - window) * 1000
    candles = [k for k in candles if k[0] >= cut]
    if not candles:
        return None, 'empty'
    return {'candles': candles, 'interval': interval, 'dropped_null': null, 'dropped_invalid': bad,
            'no_trade': sum(1 for k in candles if k[2] == k[3]), 'source': source,
            'volume_unit': vol_unit}, 'ok'


def get_ohlc(asset, vs, label):
    """Cache -> dedup -> upstream, the same discipline as get_series. (payload, status)."""
    if ohlc_plan(asset, vs, label) is None:
        return {'mode': 'ohlc', 'candles': [], 'source_status': 'no_market',
                'error': 'no_real_market'}, 200
    key = ohlc_key(asset, vs, label)
    ttl, now = OHLC_TTL[label], time.time()
    with _cache_lock:
        entry = _cache.get(key)
    if entry and now - entry['fetched_at'] < ttl:
        _bump('ohlc_cache_hits')
        return _ohlc_payload(entry, 'cached', now), 200
    with _inflight_lock:
        ev = _inflight.get(key)
        leader = ev is None
        if leader:
            ev = threading.Event()
            _inflight[key] = ev
    if not leader:
        _bump('dedup_hits')
        ev.wait(timeout=30)
        with _cache_lock:
            entry = _cache.get(key)
        if entry:
            return _ohlc_payload(entry, 'cached', time.time()), 200
        return {'error': 'upstream_unavailable', 'source_status': 'error'}, 503
    try:
        outcome = _refresh_ohlc(key, asset, vs, label)
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)
        ev.set()
    with _cache_lock:
        entry = _cache.get(key)
    if outcome == 'fresh' and entry:
        return _ohlc_payload(entry, 'fresh', time.time()), 200
    if entry and time.time() - entry['fetched_at'] < min(ttl * STALE_FACTOR, STALE_MAX):
        _bump('stale_served')
        return _ohlc_payload(entry, 'stale', time.time(), reason=outcome), 200
    return {'error': outcome, 'source_status': 'unavailable'}, 503


def _refresh_ohlc(key, asset, vs, label):
    res, reason = _fetch_ohlc(asset, vs, label)
    if res is None:
        _bump('errors')
        return reason
    with _cache_lock:
        _cache[key] = dict(res, fetched_at=time.time(), status='ok')
    return 'fresh'


OHLC_FIELDS = ('candles', 'interval', 'source', 'dropped_null', 'dropped_invalid', 'no_trade', 'volume_unit', 'status')


def _ohlc_payload(entry, status, now, reason=None):
    p = {'mode': 'ohlc', 'candles': entry['candles'], 'interval': entry['interval'],
         'source': entry.get('source', 'yahoo-finance'), 'dropped_null': entry.get('dropped_null', 0),
         'dropped_invalid': entry.get('dropped_invalid', 0),
         'no_trade': entry.get('no_trade', sum(1 for k in entry['candles'] if k[2] == k[3])),
         'volume_unit': entry.get('volume_unit', 'USD'), 'source_status': status,
         'age_s': int(now - entry['fetched_at']),
         'fields': ['t_ms', 'open', 'high', 'low', 'close', 'volume']}
    if reason:
        p['upstream_error'] = reason
    return p


# ---------------------------------------------------------------- JSON snapshots (Markets page)
# Fixed, allowlisted upstream documents the Markets page used to fetch from every browser
# (and partly could not: the site CSP blocks open.er-api.com and frankfurter). The caller
# picks a NAME from these tables, never a URL, a host or a free-form parameter. Bodies are
# passed through in the provider's own shape so the page logic is unchanged; the gateway
# adds shared caching, de-duplication, last-good-on-failure (persisted across restarts)
# and the per-IP upstream budget.
SPOT_FIAT = ('usd', 'cad', 'mxn', 'brl', 'ars', 'clp', 'cop', 'pen', 'eur', 'gbp', 'chf', 'nok', 'sek', 'dkk',
             'pln', 'czk', 'rub', 'try', 'ils', 'jpy', 'cny', 'krw', 'hkd', 'twd', 'sgd', 'thb', 'myr', 'idr',
             'php', 'vnd', 'inr', 'pkr', 'aed', 'sar', 'kwd', 'qar', 'bhd', 'aud', 'nzd', 'zar', 'ngn', 'egp')
SPOT_CRYPTO_IDS = ('bitcoin', 'ethereum', 'binancecoin', 'solana', 'ripple', 'polkadot', 'chainlink',
                   'litecoin', 'bitcoin-cash', 'stellar')
SPOT_CRYPTO_CODES = ('btc', 'eth', 'bnb', 'sol', 'xrp', 'dot', 'link', 'ltc', 'bch', 'xlm')
CG_SIMPLE = 'https://api.coingecko.com/api/v3/simple/price'
# crypto + gold_usd come from Binance spot 24h tickers (USDT books, the market the Markets charts use;
# generous public limits); gold in 60 currencies and the stablecoins have no exchange book in those
# quotes, so they stay on CoinGecko, with long TTLs and background refresh to protect its keyless budget.
BINANCE_TICKER = 'https://api.binance.com/api/v3/ticker/24hr'
BINANCE_SPOT = {'crypto': dict(zip(SPOT_CRYPTO_IDS, ('BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOTUSDT',
                                                      'LINKUSDT', 'LTCUSDT', 'BCHUSDT', 'XLMUSDT'))),
                'gold_usd': {'tether-gold': 'XAUTUSDT', 'pax-gold': 'PAXGUSDT'}}
SPOT_GROUPS = {   # name -> CoinGecko simple/price query (constants only)
    'gold_usd': {'ids': 'tether-gold,pax-gold', 'vs_currencies': 'usd'},
    'gold_all': {'ids': 'tether-gold,pax-gold', 'include_24hr_change': 'true',
                 'vs_currencies': ','.join(SPOT_FIAT + SPOT_CRYPTO_CODES)},
    'stable': {'ids': 'usd-coin,tether', 'vs_currencies': 'usd', 'include_24hr_change': 'true'},
    'crypto': {'ids': ','.join(SPOT_CRYPTO_IDS), 'vs_currencies': 'usd', 'include_24hr_change': 'true'},
}
FX_URL = 'https://open.er-api.com/v6/latest/USD'
FRANKFURTER_URL = 'https://api.frankfurter.dev/v1/'
FX_CODES = ('CAD', 'MXN', 'BRL', 'ARS', 'CLP', 'COP', 'PEN', 'UYU', 'CRC', 'DOP', 'GTQ', 'PYG', 'BOB', 'NIO',
            'HNL', 'HTG', 'EUR', 'GBP', 'CHF', 'NOK', 'SEK', 'DKK', 'ISK', 'PLN', 'CZK', 'RUB', 'TRY', 'ILS',
            'JPY', 'CNY', 'KRW', 'HKD', 'TWD', 'SGD', 'THB', 'MYR', 'IDR', 'PHP', 'VND', 'INR', 'PKR', 'AED',
            'SAR', 'KWD', 'QAR', 'BHD', 'OMR', 'AUD', 'NZD', 'ZAR', 'NGN', 'EGP', 'KES', 'GHS', 'MAD', 'TZS',
            'ETB', 'XOF', 'CDF')
FXHIST_BACK = {'1H': 3, '4H': 3, '8H': 3, '24H': 4, '3D': 6, '7D': 10, '30D': 33, '6M': 183, '1Y': 368,
               '3Y': 1098, '5Y': 1828}   # days of ECB daily history behind each range (as the page used)
JSON_TTL = {'spot': 60, 'fx': 3600, 'fxh': 21600}
GROUP_TTL = {'crypto': 30, 'gold_usd': 30, 'gold_all': 180, 'stable': 600}


def json_ttl(key):
    parts = key.split('|')
    if parts[1] == 'spot':
        return GROUP_TTL.get(parts[2], JSON_TTL['spot'])
    return JSON_TTL[parts[1]]
_venue.update({'erapi': {'sem': threading.BoundedSemaphore(1), 'lock': threading.Lock(), 'last': [0.0], 'gap': 1.0},
               'frankfurter': {'sem': threading.BoundedSemaphore(2), 'lock': threading.Lock(), 'last': [0.0], 'gap': 0.3}})


def json_target(mode, q):
    """(cache key, kind, venue, url-builder) for an allowlisted request, or raises ValueError."""
    one = lambda n: (q.get(n) or [''])[0].strip()
    if mode == 'spot':
        g = one('group')
        if g not in SPOT_GROUPS:
            raise ValueError('group')
        if g in BINANCE_SPOT:
            syms = json.dumps(sorted(BINANCE_SPOT[g].values()), separators=(',', ':'))
            return 'json|spot|' + g, 'spot', 'binance', lambda: BINANCE_TICKER + '?' + urllib.parse.urlencode({'symbols': syms})
        return 'json|spot|' + g, 'spot', 'coingecko', lambda: CG_SIMPLE + '?' + urllib.parse.urlencode(SPOT_GROUPS[g])
    if mode == 'fx':
        return 'json|fx|latest', 'fx', 'erapi', lambda: FX_URL
    if mode == 'fxhist':
        code, label = one('code').upper(), one('range').upper()
        if code not in FX_CODES:
            raise ValueError('code')
        if label not in FXHIST_BACK:
            raise ValueError('range')

        def url():
            end = time.gmtime()
            start = time.gmtime(time.time() - FXHIST_BACK[label] * 86400)
            return FRANKFURTER_URL + time.strftime('%Y-%m-%d', start) + '..' + time.strftime('%Y-%m-%d', end) + \
                '?' + urllib.parse.urlencode({'base': 'USD', 'symbols': code})
        return 'json|fxh|%s|%s' % (code, label), 'fxh', 'frankfurter', url
    raise ValueError('mode')


def _json_ok(kind, body):
    """Only a well-formed answer is cached — an error body must never overwrite a good copy."""
    if not isinstance(body, dict):
        return False
    if kind == 'spot':
        return bool(body) and 'status' not in body and all(
            isinstance(v, dict) and v and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v.values())
            for v in body.values())
    if kind == 'fx':
        return body.get('result') == 'success' and isinstance(body.get('rates'), dict) and body['rates']
    return isinstance(body.get('rates'), dict) and bool(body['rates'])


def _fetch_json(kind, venue, url):
    try:
        if venue == 'coingecko':            # shares the CoinGecko budget and gap with the LINE series
            headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
            if API_KEY:
                headers['x-cg-demo-api-key'] = API_KEY
            with _upstream_sem:
                with _gap_lock:
                    wait = MIN_UPSTREAM_GAP - (time.time() - _last_upstream[0])
                    if wait > 0:
                        time.sleep(wait)
                    _last_upstream[0] = time.time()
                _bump('upstream_requests')
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as r:
                    body = json.loads(r.read().decode('utf-8'))
        else:
            body = _venue_get(venue, url)
            if venue == 'binance':        # 24h tickers -> the simple/price shape the page reads
                body = _binance_to_simple(url, body)
    except urllib.error.HTTPError as e:
        if venue == 'coingecko' and e.code == 429:
            _last_upstream_failure[0] = _last_upstream_429[0] = time.time()
        return None, ('rate_limited' if e.code == 429 else 'http_error')
    except Exception:
        return None, 'network'
    if not _json_ok(kind, body):
        if venue == 'coingecko' and isinstance(body, dict) and (body.get('status') or {}).get('error_code') == 429:
            return None, 'rate_limited'
        return None, 'bad_body'
    return body, 'ok'


def _binance_to_simple(url, rows):
    """[{symbol,lastPrice,priceChangePercent}] -> {id: {'usd': last, 'usd_24h_change': pct}}.
    Real last trade and 24h change of each USDT book; nothing interpolated. A missing symbol is
    simply absent (the page shows its own dash), never filled."""
    if not isinstance(rows, list):
        return None
    group = next(g for g, m in BINANCE_SPOT.items() if all(sym in url for sym in m.values()))
    by_sym = {r.get('symbol'): r for r in rows if isinstance(r, dict)}
    out = {}
    for cid, sym in BINANCE_SPOT[group].items():
        r = by_sym.get(sym)
        try:
            last, pct = float(r['lastPrice']), float(r['priceChangePercent'])
        except (TypeError, KeyError, ValueError):
            continue
        if last > 0:
            out[cid] = {'usd': last, 'usd_24h_change': pct}
    return out


def get_json(key, kind, venue, url_fn):
    """Cache -> dedup -> upstream -> last good copy. Returns (body, http_status, source_status)."""
    ttl, now = json_ttl(key), time.time()
    with _cache_lock:
        entry = _cache.get(key)
    if entry and now - entry['fetched_at'] < ttl:
        _bump('json_cache_hits')
        return entry['body'], 200, 'cached'
    with _inflight_lock:
        ev = _inflight.get(key)
        leader = ev is None
        if leader:
            ev = threading.Event()
            _inflight[key] = ev
    if not leader:
        _bump('dedup_hits')
        ev.wait(timeout=30)
        with _cache_lock:
            entry = _cache.get(key)
        return (entry['body'], 200, 'cached') if entry else ({'error': 'upstream_unavailable'}, 503, 'error')
    try:
        body, reason = _fetch_json(kind, venue, url_fn())
        if body is not None:
            with _cache_lock:
                _cache[key] = {'body': body, 'fetched_at': time.time(), 'status': 'ok'}
        else:
            _bump('errors')
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)
        ev.set()
    if body is not None:
        return body, 200, 'fresh'
    if entry and time.time() - entry['fetched_at'] < min(ttl * STALE_FACTOR, STALE_MAX):
        _bump('stale_served')
        return entry['body'], 200, 'stale'
    return {'error': reason}, 503, 'error'


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

    def _send(self, status, obj, cache_seconds=0, source_status=None):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        if source_status:          # JSON snapshots keep the provider's body shape: status goes in a header
            self.send_header('X-Source-Status', source_status)
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
        if path.endswith('/health'):
            now = time.time()
            with _cache_lock:
                ages = [now - e['fetched_at'] for e in _cache.values()]
            self._send(200, {
                'service': 'ok',
                'cache_entries': len(ages),
                'cache_max_age_s': int(max(ages)) if ages else None,
                'last_upstream_success_s_ago':
                    int(now - _last_upstream_success[0]) if _last_upstream_success[0] else None,
                'last_upstream_429_s_ago':
                    int(now - _last_upstream_429[0]) if _last_upstream_429[0] else None,
                'upstream_backoff_active':
                    now - _last_upstream_failure[0] < WARM_COOLDOWN,
                'provider_key_configured': bool(API_KEY),   # whether, never which
                'state_file_present': os.path.exists(STATE_FILE),
            })
            return
        if path.endswith('/stats'):
            with _stats_lock:
                self._send(200, dict(STATS, cached_series=len(_cache)))
            return
        if not (path == '' or path.endswith('/market-history')):
            self._send(404, {'error': 'not_found'})
            return

        ip = self.headers.get('X-Real-IP') or self.client_address[0]
        if not _rate_ok(ip, _rate_all, RATE_LIMIT_CACHED_PER_MIN):
            _bump('rejected')
            self._send(429, {'error': 'rate_limited_local', 'source_status': 'error'})
            return

        _bump('client_requests')
        q = urllib.parse.parse_qs(parsed.query)
        mode = q.get('mode', [''])[0]
        if mode in ('spot', 'fx', 'fxhist'):
            try:
                key, kind, venue, url_fn = json_target(mode, q)
            except ValueError as e:
                _bump('rejected')
                self._send(400, {'error': 'bad_%s' % e, 'source_status': 'error'})
                return
            if not _fresh(key, json_ttl(key)) and not _rate_ok(ip):
                _bump('rejected')
                self._send(429, {'error': 'rate_limited_local', 'source_status': 'error'})
                return
            body, status, src = get_json(key, kind, venue, url_fn)
            self._send(status, body, cache_seconds=min(json_ttl(key) // 4, 30) if status == 200 else 0, source_status=src)
            return
        if mode == 'ohlc':
            try:
                asset, vs, label = parse_ohlc_params(parsed.query)
            except ValueError as e:
                _bump('rejected')
                self._send(400, {'error': 'bad_%s' % e, 'source_status': 'error'})
                return
            if not _fresh(ohlc_key(asset, vs, label), OHLC_TTL[label]) and ohlc_plan(asset, vs, label) is not None \
                    and not _rate_ok(ip):
                _bump('rejected')
                self._send(429, {'error': 'rate_limited_local', 'source_status': 'error'})
                return
            payload, status = get_ohlc(asset, vs, label)
            payload.update({'asset': asset, 'vs': vs, 'range': label})
            self._send(status, payload, cache_seconds=OHLC_TTL[label] // 2 if status == 200 else 0)
            return
        try:
            asset, vs, label, days = parse_params(parsed.query)
        except ValueError as e:
            _bump('rejected')
            self._send(400, {'error': 'bad_%s' % e, 'source_status': 'error'})
            return

        if not _fresh('%s|%s|%d' % (asset, vs, days), TTL[days]) and not _rate_ok(ip):
            _bump('rejected')
            self._send(429, {'error': 'rate_limited_local', 'source_status': 'error'})
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
WARM_COOLDOWN = 120         # pause warming this long after upstream refuses us


def _refresh_json_key(key):
    """Warm a JSON snapshot by its cache key (the in-flight slot is held by the caller)."""
    parts = key.split('|')
    if parts[1] == 'spot':
        q = {'group': [parts[2]]}
    elif parts[1] == 'fxh':
        q = {'code': [parts[2]], 'range': [parts[3]]}
    else:
        q = {}
    k2, kind, venue, url_fn = json_target({'spot': 'spot', 'fx': 'fx', 'fxh': 'fxhist'}[parts[1]], q)
    body, reason = _fetch_json(kind, venue, url_fn())
    if body is not None:
        with _cache_lock:
            _cache[k2] = {'body': body, 'fetched_at': time.time(), 'status': 'ok'}


def _entry_ttl(key):
    parts = key.split('|')
    return OHLC_TTL[parts[2]] if len(parts) == 4 else TTL[int(parts[2])]


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
            # Warming is optional work. If upstream has just refused a request, the
            # budget belongs to visitors asking for something they are looking at,
            # not to a refresh of something already in the cache.
            if now - _last_upstream_failure[0] < WARM_COOLDOWN:
                continue
            due = None
            with _cache_lock:
                for key, entry in _cache.items():
                    if entry.get('status') == 'out_of_range':
                        continue
                    ttl = json_ttl(key) if key.startswith('json|') else _entry_ttl(key)
                    age = now - entry['fetched_at']
                    if age < ttl * WARM_LEAD:
                        continue
                    if due is None or age / ttl > due[1]:
                        due = (key, age / ttl)
            if not due:
                continue
            key = due[0]
            parts = key.split('|')
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
                if parts[0] == 'json':
                    _refresh_json_key(key)
                elif len(parts) == 4:
                    _refresh_ohlc(key, parts[0], parts[1], parts[2])
                else:
                    _refresh(key, parts[0], parts[1], int(parts[2]))
            finally:
                with _inflight_lock:
                    _inflight.pop(key, None)
                ev.set()
        except Exception:
            pass                        # a warm pass must never take the service down


def main():
    load_state()
    threading.Thread(target=_warm_loop, daemon=True).start()
    threading.Thread(target=_save_loop, daemon=True).start()
    srv = ThreadingHTTPServer(LISTEN, Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    finally:
        save_state()          # a planned restart keeps everything it had


if __name__ == '__main__':
    main()

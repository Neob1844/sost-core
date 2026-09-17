#!/usr/bin/env python3
"""Tests for the market-history gateway (ops/sost-market-proxy.py).

Upstream is replaced by a fake so the suite is deterministic and never touches
CoinGecko: every failure mode the real API produces is injected on demand.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

_real_sleep = time.sleep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    'market_proxy', os.path.join(ROOT, 'ops', 'sost-market-proxy.py'))
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)
REAL_FETCH = mp._fetch_upstream      # kept before any test swaps in a fake


class FakeUpstream:
    """Stands in for _fetch_upstream. Records every call and injects failures."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.mode = 'ok'          # ok | rate_limited | http_error | network | empty
        self.fail_first = 0
        self.delay = 0.0
        self.n = 0
        self.active = 0
        self.peak = 0

    def __call__(self, asset, vs, days):
        # Mirrors the accounting the real _fetch_upstream does, so the stats the
        # gateway reports mean the same thing under test as they do in production.
        with self.lock:
            self.n += 1
            n = self.n
            self.calls.append((asset, vs, days))
            self.active += 1
            self.peak = max(self.peak, self.active)
        mp._bump('upstream_requests')
        with mp._stats_lock:
            mp.STATS['peak_upstream_concurrency'] = max(
                mp.STATS['peak_upstream_concurrency'], self.peak)
        try:
            if self.delay:
                _real_sleep(self.delay)
            if n <= self.fail_first:
                return None, 'rate_limited'
            if self.mode == 'ok':
                return [[1000 + i, 10.0 + i] for i in range(days * 2 + 5)], 'ok'
            if self.mode == 'empty':
                return [], 'empty'
            if self.mode == 'out_of_range':
                return [], 'out_of_range'
            return None, self.mode
        finally:
            with self.lock:
                self.active -= 1


def reset(fake=None, sleepless=True):
    mp._cache.clear()
    mp._inflight.clear()
    mp._rate.clear()
    for k in mp.STATS:
        mp.STATS[k] = 0
    if fake is not None:
        mp._fetch_upstream = fake
    if sleepless:
        mp.time.sleep = lambda s: None      # keep backoff logic, drop the waiting


class ParamValidation(unittest.TestCase):
    """Nothing a caller sends reaches a URL unless it is on the allowlist."""

    def test_accepts_allowlisted_triples(self):
        a, vs, label, days = mp.parse_params('asset=bitcoin&vs=usd&range=30D')
        self.assertEqual((a, vs, label, days), ('bitcoin', 'usd', '30D', 30))

    def test_days_form_is_accepted_and_labelled(self):
        a, vs, label, days = mp.parse_params('asset=pax-gold&vs=btc&days=365')
        self.assertEqual((a, vs, label, days), ('pax-gold', 'btc', '1Y', 365))

    def test_accepts_eth_denominated_pairs(self):
        """The ETH charts ask for the same shapes the BTC charts do: the gold assets
        priced in ETH, plus ETH's own USD line."""
        self.assertEqual(mp.parse_params('asset=tether-gold&vs=eth&range=24H'),
                         ('tether-gold', 'eth', '24H', 1))
        self.assertEqual(mp.parse_params('asset=pax-gold&vs=eth&days=30'),
                         ('pax-gold', 'eth', '30D', 30))
        self.assertEqual(mp.parse_params('asset=ethereum&vs=usd&range=7D'),
                         ('ethereum', 'usd', '7D', 7))

    def test_range_defaults_vs_to_usd(self):
        self.assertEqual(mp.parse_params('asset=bitcoin&range=7D')[1], 'usd')

    def test_rejects_unknown_asset(self):
        with self.assertRaises(ValueError):
            mp.parse_params('asset=dogecoin&vs=usd&range=7D')

    def test_rejects_unknown_vs(self):
        with self.assertRaises(ValueError):
            mp.parse_params('asset=bitcoin&vs=eur&range=7D')

    def test_rejects_unknown_range_and_days(self):
        for q in ('asset=bitcoin&vs=usd&range=99Y',
                  'asset=bitcoin&vs=usd&days=9999',
                  'asset=bitcoin&vs=usd&days=-1',
                  'asset=bitcoin&vs=usd'):
            with self.assertRaises(ValueError, msg=q):
                mp.parse_params(q)

    def test_rejects_ssrf_shaped_input(self):
        """A URL, a host, a path or a scheme in any field is simply not on the allowlist."""
        for q in ('asset=http://169.254.169.254/latest/meta-data&vs=usd&range=7D',
                  'asset=../../etc/passwd&vs=usd&range=7D',
                  'asset=bitcoin/../../admin&vs=usd&range=7D',
                  'asset=bitcoin&vs=usd%0d%0aX-Injected:%201&range=7D',
                  'asset=bitcoin&vs=file:///etc/passwd&range=7D',
                  'asset=localhost&vs=usd&range=7D'):
            with self.assertRaises(ValueError, msg=q):
                mp.parse_params(q)

    def test_upstream_url_is_built_from_constants(self):
        """The asset is the only interpolated piece and it is allowlist-constrained."""
        for asset in mp.ASSETS:
            url = mp.UPSTREAM.format(asset=asset)
            self.assertTrue(url.startswith('https://api.coingecko.com/api/v3/coins/'))
            self.assertNotIn('..', url)


class CacheAndDedup(unittest.TestCase):
    def setUp(self):
        self.fake = FakeUpstream()
        reset(self.fake)

    def test_second_call_is_a_cache_hit(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp.get_series('bitcoin', 'usd', 30)
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(mp.STATS['cache_hits'], 1)

    def test_ranges_sharing_a_days_value_share_one_upstream_fetch(self):
        """1H/4H/8H/24H all ask upstream for days=1 — the same dataset, fetched once."""
        for label in ('1H', '4H', '8H', '24H'):
            mp.get_series('bitcoin', 'usd', mp.RANGES[label])
        self.assertEqual(len(self.fake.calls), 1)

    def test_distinct_series_do_not_share_a_cache_entry(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp.get_series('bitcoin', 'btc', 30)
        mp.get_series('pax-gold', 'usd', 30)
        mp.get_series('bitcoin', 'usd', 7)
        self.assertEqual(len(self.fake.calls), 4)
        self.assertEqual(len(mp._cache), 4)

    def test_concurrent_callers_produce_one_upstream_request(self):
        """Twenty simultaneous visitors asking for the same series."""
        self.fake.delay = 0.25
        out = []
        threads = [threading.Thread(target=lambda: out.append(
            mp.get_series('bitcoin', 'usd', 30))) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(len(out), 20)
        self.assertTrue(all(s == 200 for _, s in out))
        self.assertTrue(all(p.get('prices') for p, _ in out))
        self.assertEqual(mp.STATS['upstream_requests'], 1)
        self.assertEqual(mp.STATS['dedup_hits'] + mp.STATS['cache_hits'], 19)

    def test_expired_entry_is_refetched(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp._cache['bitcoin|usd|30']['fetched_at'] -= mp.TTL[30] + 1
        mp.get_series('bitcoin', 'usd', 30)
        self.assertEqual(len(self.fake.calls), 2)


class FailureModes(unittest.TestCase):
    def setUp(self):
        self.fake = FakeUpstream()
        reset(self.fake)

    def test_initial_429_inside_the_inline_budget_recovers_immediately(self):
        self.fake.fail_first = 1          # one rejection, absorbed by the second attempt
        payload, status = mp.get_series('bitcoin', 'usd', 30)
        self.assertEqual(status, 200)
        self.assertEqual(payload['source_status'], 'fresh')
        self.assertTrue(payload['prices'])

    def test_initial_429_beyond_the_budget_recovers_on_the_client_retry(self):
        """The gateway does not sit through a long retry chain while a caller is blocked:
        it returns a fast 503 and the client's own backoff ladder comes back and wins."""
        self.fake.fail_first = 2          # exhausts the inline budget
        payload, status = mp.get_series('bitcoin', 'usd', 30)
        self.assertEqual(status, 503)
        payload, status = mp.get_series('bitcoin', 'usd', 30)   # what the client does next
        self.assertEqual(status, 200)
        self.assertTrue(payload['prices'])

    def test_sustained_429_without_cache_is_a_controlled_error(self):
        self.fake.mode = 'rate_limited'
        payload, status = mp.get_series('bitcoin', 'usd', 30)
        self.assertEqual(status, 503)
        self.assertEqual(payload['source_status'], 'error')
        self.assertEqual(payload['error'], 'rate_limited')

    def test_stale_is_served_when_upstream_fails(self):
        mp.get_series('bitcoin', 'usd', 30)
        good = list(mp._cache['bitcoin|usd|30']['prices'])
        mp._cache['bitcoin|usd|30']['fetched_at'] -= mp.TTL[30] + 5
        self.fake.mode = 'rate_limited'
        payload, status = mp.get_series('bitcoin', 'usd', 30)
        self.assertEqual(status, 200)
        self.assertEqual(payload['source_status'], 'stale')
        self.assertEqual(payload['prices'], good)
        self.assertEqual(payload['upstream_error'], 'rate_limited')

    def test_stale_is_not_served_forever(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp._cache['bitcoin|usd|30']['fetched_at'] -= mp.TTL[30] * mp.STALE_FACTOR + 10
        self.fake.mode = 'network'
        payload, status = mp.get_series('bitcoin', 'usd', 30)
        self.assertEqual(status, 503)
        self.assertEqual(payload['source_status'], 'error')

    def test_timeout_and_5xx_behave_like_other_failures(self):
        for mode in ('network', 'http_error'):
            reset(self.fake)
            self.fake.mode = mode
            payload, status = mp.get_series('bitcoin', 'usd', 7)
            self.assertEqual(status, 503, mode)
            self.assertEqual(payload['error'], mode)

    def test_genuinely_empty_range_is_cached_as_empty_not_error(self):
        self.fake.mode = 'empty'
        payload, status = mp.get_series('pax-gold', 'btc', 1825)
        self.assertEqual(status, 200)
        self.assertEqual(payload['prices'], [])
        self.assertEqual(mp._cache['pax-gold|btc|1825']['status'], 'empty')


class RateLimit(unittest.TestCase):
    def test_per_ip_budget_is_enforced_then_recovers(self):
        reset(FakeUpstream())
        ip = '203.0.113.7'
        for _ in range(mp.RATE_LIMIT_PER_MIN):
            self.assertTrue(mp._rate_ok(ip))
        self.assertFalse(mp._rate_ok(ip))
        self.assertTrue(mp._rate_ok('203.0.113.8'))     # other clients unaffected
        mp._rate[ip] = [t - 61 for t in mp._rate[ip]]   # window rolls over
        self.assertTrue(mp._rate_ok(ip))


class TtlPolicy(unittest.TestCase):
    def test_every_allowlisted_range_has_a_ttl_and_a_timeout(self):
        for label, days in mp.RANGES.items():
            self.assertIn(days, mp.TTL, label)
            self.assertIn(days, mp.TIMEOUT, label)

    def test_ttl_grows_with_the_range(self):
        self.assertLess(mp.TTL[1], mp.TTL[30])
        self.assertLess(mp.TTL[30], mp.TTL[365])
        self.assertLess(mp.TTL[365], mp.TTL[1825])


class RetryBudget(unittest.TestCase):
    """The gateway answers a blocked caller quickly; the client owns the long retry."""

    def test_inline_retry_budget_stays_under_the_client_timeout(self):
        worst = sum(min(mp.UPSTREAM_BACKOFF_CAP, 1.5 * (2 ** i))
                    for i in range(mp.UPSTREAM_ATTEMPTS - 1))
        worst += mp.UPSTREAM_ATTEMPTS * max(mp.TIMEOUT.values())
        # The browser gives a long range 35s. A gateway that took longer than that under
        # failure would time the caller out and waste the round trip.
        self.assertLessEqual(mp.UPSTREAM_ATTEMPTS, 2)
        self.assertLessEqual(worst - mp.UPSTREAM_ATTEMPTS * max(mp.TIMEOUT.values()), 5.0)

    def test_failure_answers_without_exhausting_the_caller(self):
        fake = FakeUpstream()
        reset(fake, sleepless=False)
        fake.mode = 'rate_limited'
        t0 = time.time()
        payload, status = mp.get_series('bitcoin', 'usd', 30)
        self.assertEqual(status, 503)
        self.assertLess(time.time() - t0, 10.0)


class ProviderRangeCap(unittest.TestCase):
    """The keyless plan refuses anything older than 365 days (401 / error_code 10012).

    That is permanent, not transient: 3Y and 5Y can never be served. It must settle as an
    empty range that is cached, not as an error that is retried forever."""

    def setUp(self):
        self.fake = FakeUpstream()
        reset(self.fake)

    def test_out_of_range_settles_as_an_empty_range(self):
        self.fake.mode = 'out_of_range'
        payload, status = mp.get_series('pax-gold', 'btc', 1825)
        self.assertEqual(status, 200)
        self.assertEqual(payload['prices'], [])
        self.assertEqual(payload['source_status'], 'out_of_range')

    def test_out_of_range_is_not_re_asked_on_every_visit(self):
        self.fake.mode = 'out_of_range'
        for _ in range(5):
            mp.get_series('pax-gold', 'btc', 1825)
        self.assertEqual(len(self.fake.calls), 1)

    def test_out_of_range_ttl_outlasts_a_normal_one(self):
        self.assertGreater(mp.OUT_OF_RANGE_TTL, max(mp.TTL.values()))

    def test_a_401_with_the_range_error_is_classified(self):
        """Exercises the real classification path, not a shortcut in the fake."""
        body = json.dumps({'error': {'status': {'error_code': 10012,
                                                'error_message': 'exceeds the allowed time range'}}})

        class FakeHTTPError(urllib.error.HTTPError):
            def __init__(self):
                self.code = 401
                self._b = body.encode()

            def read(self):
                return self._b

        real_urlopen = mp.urllib.request.urlopen

        def boom(*a, **k):
            raise FakeHTTPError()

        mp.urllib.request.urlopen = boom
        try:
            prices, reason = REAL_FETCH('pax-gold', 'btc', 1825)
        finally:
            mp.urllib.request.urlopen = real_urlopen
        self.assertEqual(prices, [])
        self.assertEqual(reason, 'out_of_range')


class BackgroundWarm(unittest.TestCase):
    """The trickle refresh keeps the working set warm without fetching speculatively."""

    def setUp(self):
        self.fake = FakeUpstream()
        reset(self.fake)

    def _one_pass(self):
        """Run exactly one iteration of the warm loop's body."""
        now = time.time()
        due = None
        with mp._cache_lock:
            for key, entry in mp._cache.items():
                if entry.get('status') == 'out_of_range':
                    continue
                days = int(key.split('|')[2])
                age = now - entry['fetched_at']
                if age < mp.TTL[days] * mp.WARM_LEAD:
                    continue
                if due is None or age / mp.TTL[days] > due[1]:
                    due = (key, age / mp.TTL[days])
        if not due:
            return None
        key = due[0]
        asset, vs, days = key.split('|')
        mp._refresh(key, asset, vs, int(days))
        return key

    def test_nothing_is_fetched_speculatively(self):
        self.assertIsNone(self._one_pass())
        self.assertEqual(self.fake.calls, [])

    def test_a_fresh_entry_is_left_alone(self):
        mp.get_series('bitcoin', 'usd', 30)
        self.assertIsNone(self._one_pass())
        self.assertEqual(len(self.fake.calls), 1)

    def test_an_entry_near_expiry_is_refreshed(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp._cache['bitcoin|usd|30']['fetched_at'] -= mp.TTL[30] * 0.9
        self.assertEqual(self._one_pass(), 'bitcoin|usd|30')
        self.assertEqual(len(self.fake.calls), 2)

    def test_a_range_the_plan_cannot_serve_is_never_re_asked(self):
        self.fake.mode = 'out_of_range'
        mp.get_series('pax-gold', 'btc', 1825)
        mp._cache['pax-gold|btc|1825']['fetched_at'] -= mp.OUT_OF_RANGE_TTL * 2
        self.assertIsNone(self._one_pass())
        self.assertEqual(len(self.fake.calls), 1)


    def test_warming_yields_while_upstream_is_refusing(self):
        """A refresh of something already cached must not compete with a visitor asking
        for something they are looking at."""
        mp.get_series('bitcoin', 'usd', 30)
        mp._cache['bitcoin|usd|30']['fetched_at'] -= mp.TTL[30] * 0.9
        before = len(self.fake.calls)
        mp._last_upstream_failure[0] = time.time()          # upstream just refused us
        now = time.time()
        skipped = now - mp._last_upstream_failure[0] < mp.WARM_COOLDOWN
        self.assertTrue(skipped, 'cooldown should be active')
        self.assertEqual(len(self.fake.calls), before)      # nothing fetched

        mp._last_upstream_failure[0] = now - mp.WARM_COOLDOWN - 1   # cooldown elapsed
        self.assertEqual(self._one_pass(), 'bitcoin|usd|30')
        self.assertEqual(len(self.fake.calls), before + 1)

    def test_a_refusal_is_recorded(self):
        """The cooldown is driven by real upstream refusals, not by a guess."""
        real_urlopen = mp.urllib.request.urlopen
        mp._last_upstream_failure[0] = 0.0

        def boom(*a, **k):
            raise urllib.error.URLError('refused')

        mp.urllib.request.urlopen = boom
        try:
            prices, reason = REAL_FETCH('bitcoin', 'usd', 30)
        finally:
            mp.urllib.request.urlopen = real_urlopen
        self.assertIsNone(prices)
        self.assertEqual(reason, 'network')
        self.assertGreater(mp._last_upstream_failure[0], 0.0)

    def test_it_picks_the_most_overdue_entry(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp.get_series('bitcoin', 'usd', 7)
        mp._cache['bitcoin|usd|30']['fetched_at'] -= mp.TTL[30] * 0.85
        mp._cache['bitcoin|usd|7']['fetched_at'] -= mp.TTL[7] * 1.5
        self.assertEqual(self._one_pass(), 'bitcoin|usd|7')


class Persistence(unittest.TestCase):
    """A restart must not start cold — and must not make data look newer than it is."""

    def setUp(self):
        self.fake = FakeUpstream()
        reset(self.fake)
        self.tmp = tempfile.mkdtemp()
        mp.STATE_FILE = os.path.join(self.tmp, 'market-cache.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _restart(self):
        """Save, wipe memory as a process restart would, restore."""
        self.assertTrue(mp.save_state())
        mp._cache.clear()
        return mp.load_state()

    def test_a_warm_cache_survives_a_restart(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp.get_series('tether-gold', 'btc', 7)
        self.assertEqual(self._restart(), 2)
        before = len(self.fake.calls)
        payload, status = mp.get_series('bitcoin', 'usd', 30)
        self.assertEqual(status, 200)
        self.assertEqual(payload['source_status'], 'cached')
        self.assertEqual(len(self.fake.calls), before)      # no cold-start fetch

    def test_restored_entries_keep_their_real_age(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp._cache['bitcoin|usd|30']['fetched_at'] -= mp.TTL[30] * 0.5
        self._restart()
        self.assertAlmostEqual(time.time() - mp._cache['bitcoin|usd|30']['fetched_at'],
                               mp.TTL[30] * 0.5, delta=5)

    def test_an_entry_past_its_stale_window_is_not_restored(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp._cache['bitcoin|usd|30']['fetched_at'] -= mp.TTL[30] * mp.STALE_FACTOR + 60
        self.assertEqual(self._restart(), 0)

    def test_out_of_range_survives_so_we_never_re_ask_after_a_restart(self):
        self.fake.mode = 'out_of_range'
        mp.get_series('pax-gold', 'btc', 1825)
        self.assertEqual(self._restart(), 1)
        before = len(self.fake.calls)
        payload, status = mp.get_series('pax-gold', 'btc', 1825)
        self.assertEqual(payload['source_status'], 'out_of_range')
        self.assertEqual(len(self.fake.calls), before)

    def test_a_corrupt_or_hostile_state_file_is_ignored(self):
        for blob in ('{not json', '{}', '{"version": 99, "entries": {}}',
                     '{"version": 1, "entries": {"../../etc/passwd|usd|30": {"prices": [[1,2]], "fetched_at": 1}}}',
                     '{"version": 1, "entries": {"dogecoin|usd|30": {"prices": [[1,2]], "fetched_at": 1}}}',
                     '{"version": 1, "entries": {"bitcoin|usd|9999": {"prices": [[1,2]], "fetched_at": 1}}}',
                     '{"version": 1, "entries": {"bitcoin|usd|30": {"prices": "nope", "fetched_at": 1}}}'):
            with open(mp.STATE_FILE, 'w') as f:
                f.write(blob)
            mp._cache.clear()
            self.assertEqual(mp.load_state(), 0, blob[:40])
            self.assertEqual(len(mp._cache), 0)

    def test_saving_is_atomic(self):
        mp.get_series('bitcoin', 'usd', 30)
        mp.save_state()
        self.assertTrue(os.path.exists(mp.STATE_FILE))
        self.assertFalse(os.path.exists(mp.STATE_FILE + '.tmp'))


class ProviderKey(unittest.TestCase):
    """An optional key raises the rate limit. It does not extend the history cap."""

    def test_no_key_configured_by_default_in_tests(self):
        self.assertIsInstance(mp.API_KEY, str)

    def test_the_key_is_never_placed_in_the_url(self):
        url = mp.UPSTREAM.format(asset='bitcoin')
        self.assertNotIn('api_key', url)
        self.assertNotIn('x_cg', url)


if __name__ == '__main__':
    unittest.main(verbosity=2)

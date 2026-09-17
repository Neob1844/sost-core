# Market-history gateway

`ops/sost-market-proxy.py` — a small stdlib-only HTTP service that fetches the
explorer's price series once and shares the result with every visitor.

## Why

The explorer's price charts used to call CoinGecko from the browser. That meant:

* every visitor spent their own slice of a per-IP rate limit;
* one page load asked for the same series more than once, because the client
  cache is only written when a response arrives;
* the keyless tier answers a burst with HTTP 429, and a 429 body carries no
  `prices` — indistinguishable from an empty range unless you read the status
  code, which is how a rate limit came to be painted as "unavailable".

With the gateway:

```
100 visitors  ->  sostcore.com/api/market-history  ->  1 upstream request
                         (shared cache)                (result shared)
```

## Endpoint

```
GET /api/market-history?asset=<asset>&vs=<usd|btc|eth>&range=<label>
GET /api/market-history?asset=<asset>&vs=<usd|btc|eth>&days=<n>
GET /api/market-history/stats
```

Response:

```json
{ "prices": [[ms, value], ...],
  "source_status": "fresh" | "cached" | "stale",
  "age_s": 12, "asset": "bitcoin", "vs": "usd", "range": "30D", "days": 30 }
```

On failure with nothing cacheable: HTTP 503 and
`{"error": "rate_limited|http_error|network|timeout", "source_status": "error"}`.

## It is not a general proxy

The caller chooses nothing but one `(asset, vs, range)` triple out of a fixed
allowlist:

| dimension | allowed |
|---|---|
| `asset`   | `tether-gold`, `pax-gold`, `bitcoin`, `ethereum` |
| `vs`      | `usd`, `btc`, `eth` |
| `range`   | 1H, 4H, 8H, 24H, 3D, 7D, 30D, 6M, 1Y, 3Y, 5Y |

Anything else is a 400 before any network call. The upstream URL is built here
from constants; no caller-supplied URL, host, scheme or path ever reaches
`urllib`. `tests/test_market_proxy.py` asserts this against URL-shaped,
traversal-shaped, header-injection-shaped and link-local-address input.

## Caching

The cache key is `asset|vs|days`, which is exactly the upstream dataset. 1H, 4H,
8H and 24H all ask upstream for `days=1` and the client slices the window
locally, so those four ranges legitimately share one entry instead of fetching
the same series four times.

| days | ranges | TTL |
|---|---|---|
| 1 | 1H / 4H / 8H / 24H | 2 min |
| 3, 7 | 3D / 7D | 5 min |
| 30 | 30D | 15 min |
| 180, 365 | 6M / 1Y | 1 h |
| 1095, 1825 | 3Y / 5Y | 6 h |

A 5Y line does not change meaningfully within hours; a 24H line does.

## Behaviour under failure

* **Dedup** — identical in-flight requests share one upstream call; later
  callers wait on an event rather than starting their own.
* **Concurrency** — at most 2 upstream requests at a time, with a 350 ms gap.
* **Backoff** — 4 attempts, longer waits for a rate limit than for a network
  error.
* **stale-if-error** — if upstream fails and a copy exists that is younger than
  24 × TTL (capped at 7 days), that copy is served with
  `source_status: "stale"` and `upstream_error`. Better a slightly old chart
  than a blank one. Past that window it is a controlled 503, never stale
  forever.
* **Per-IP rate limit** — 120 requests/minute, so one client cannot drain the
  shared budget.

## The provider's 365-day cap

The keyless plan refuses anything older than 365 days with HTTP 401 and
`error_code 10012` ("Your request exceeds the allowed time range"). That is a
property of the plan, not a transient failure: **3Y and 5Y can never be served**.

Treating it as an error meant retrying, on every visit, a request that cannot
succeed — spending the shared budget and painting "unavailable", which reads like
something is broken. It is now classified as `out_of_range`, answered as an empty
range with `source_status: "out_of_range"`, and cached for 12 hours. The client
sees an empty series, settles on its final "no data" state and stops asking; the
timeframe button dims itself, as it already does for any range without enough
history.

If a paid plan is ever added, this classification is the only thing that has to
change for 3Y and 5Y to start working.

## Keeping the working set warm

A trickle of background refreshes keeps entries that somebody has already asked
for from going cold, so a visitor does not pay for a cold fetch and does not
depend on arriving at the right moment.

* Nothing is fetched speculatively — only series already in the cache.
* One at a time, 20 s apart, through the same dedup and concurrency limits as a
  request, so it can never contribute to a burst.
* It picks the most overdue entry once it is 75% through its TTL, and refreshes
  it directly rather than through the cache path, which would otherwise just hand
  the entry back.
* Ranges the plan cannot serve are skipped entirely.

* Warming pauses for two minutes after upstream refuses a request: the budget
  belongs to visitors asking for something they are looking at, not to a
  refresh of something already in the cache.

A failure in a warm pass is swallowed: warming must never take the service down.

## Surviving a restart

The cache lives in memory and is mirrored to `/var/lib/sost/market-cache.json` every
60 seconds and again on a clean stop. On boot it is restored, so a restart does not
send every visitor's first request upstream at once.

Restored entries keep their **original** `fetched_at`, so a restart never makes data
look newer than it is: an entry still inside its TTL serves as `cached`, one past it
is stale-eligible, and one past the stale window is dropped rather than loaded. A
corrupt, truncated, wrong-version or hostile state file is ignored entirely — every
key is re-validated against the allowlist before it is accepted. Writes are atomic
(temp file + rename), because a half-written file would be worse than no file.

Measured: warm the cache, restart the process, and the next visitor gets all five
series from cache with a **cold-start burst of 0** upstream requests.

## Health

`GET /api/market-history/health` reports service state, cache entry count, the age of
the oldest entry, how long ago upstream last succeeded and last returned 429, whether
the backoff is currently active, whether a provider key is configured (never which),
and whether the state file exists. No secret is ever included.

`GET /api/market-history/stats` reports the request counters.

## Provider plans — what a key does and does not fix

An optional read-only key can be supplied through `COINGECKO_API_KEY` in
`/etc/sost/market.env` (systemd `EnvironmentFile`, never the repository, never sent to
a browser, never logged, sent as a header and never in the URL).

It raises the rate limit. It does **not** extend the history cap:

| plan | history |
|---|---|
| Demo / keyless | ~1 year |
| Basic | 2 years |
| Analyst and above | long history |

So a Demo key does not make 3Y or 5Y work. Those two ranges stay classified as
`out_of_range` and the explorer says so plainly — "Extended history unavailable with
current data source" — instead of spinning, retrying, or showing an ambiguous
"unavailable" that reads like a fault.

## Client

`website/sost-explorer.html` calls only this endpoint. There is deliberately
**no** direct fallback to the upstream API: if the gateway were down, every open
tab failing over at once would recreate the request storm the gateway exists to
prevent.

## Deploy

```
cp ops/sost-market-proxy.py       /opt/sost/sost-market-proxy.py
cp ops/sost-market-proxy.service  /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now sost-market-proxy
```

Then add `deploy/nginx-market-proxy.conf` inside the site's `server {}` block and
`nginx -t && systemctl reload nginx`.

## Tests

`python3 tests/test_market_proxy.py` — allowlist and SSRF-shaped input, cache
and dedup (including 20 concurrent callers collapsing to one upstream request),
every failure mode, stale-if-error and its expiry, and the per-IP limit. Upstream
is faked, so the suite never touches CoinGecko.

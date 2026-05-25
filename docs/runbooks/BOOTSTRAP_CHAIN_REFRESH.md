# Bootstrap chain snapshot — refresh runbook

This document describes the **operational** setup on the SOST mainnet
VPS that keeps `https://sostcore.com/bootstrap-chain.json` aligned with
the live chain. None of this lives in the SOST source tree at build
time; it lives on the VPS filesystem. The document is committed to the
repo so the procedure is not "only in the operator's memory" — anyone
re-deploying the VPS or onboarding a second host can reproduce it
byte-for-byte from here.

## Background — what bootstrap-chain.json is

`bootstrap-chain.json` is a snapshot of the live mainnet `chain.json`
from the canonical node, published over HTTPS so a new node operator
can fast-start instead of replaying the entire chain block-by-block
from genesis via peers. Format is identical to what `sost-node` writes
to disk: a JSON object with `chain_height` (int), `tip` (64-hex block
id) and a `blocks` array. A user-visible download is `~120 MB` at
chain heights around 10,200; the file grows by roughly 12-13 MB per
1,000 blocks.

A correctly served `bootstrap-chain.json` lets `sost-node` skip ~9 h
of from-genesis sync down to the seconds it takes to fetch the file
and load it.

## The 2026-05-25 incident

After the nginx-from-worktree isolation refactor (see
`/etc/nginx/sites-enabled/sost` + the `/var/www/sost-website/`
worktree), the static `bootstrap-chain.json` that previously lived
under `/opt/sost/website/` was no longer reachable via the public
URL. The file is too large to track in git (124 MB), so the
`git worktree add ... main` that built the public path did not bring
it along. nginx's catch-all behaviour for unknown paths served the
website homepage (`<!DOCTYPE html>...`, ~110 KB) instead of returning
a 404, so `curl -fO bootstrap-chain.json` succeeded with HTTP 200
and downloaded HTML. New node operators who followed the bootstrap
instructions ended up with a JSON parse error, a chain at height 0,
and orphan blocks from peers piling up into a stuck reorg state.

Reported by `vostokzyf` on BitcoinTalk; root cause fixed the same
day. This document captures the resulting permanent fix.

## Solution — atomic refresh cron

A single shell script + a single cron entry, both as root on the
VPS. No service to restart. No nginx config change.

### Components

| Path | Purpose |
|---|---|
| `/opt/sost/build/chain.json` | the live mainnet `chain.json` written by `sost-node` |
| `/var/www/sost-website/website/bootstrap-chain.json` | the file nginx serves at `https://sostcore.com/bootstrap-chain.json` |
| `/usr/local/bin/sost-bootstrap-refresh.sh` | refresh script (atomic: cp + JSON validate + mv) |
| `/etc/cron.d/sost-bootstrap-refresh` | cron entry, runs the script every hour at minute 17 |
| `/var/log/sost-bootstrap-refresh.log` | append-only refresh log |

### The script

`/usr/local/bin/sost-bootstrap-refresh.sh`:

```bash
#!/bin/bash
# Atomically refresh the public bootstrap-chain.json snapshot from the
# live VPS node chain.json. Validates JSON BEFORE the atomic rename
# so we never publish a broken file. Cron-driven (every hour).
set -euo pipefail
SRC=/opt/sost/build/chain.json
DST=/var/www/sost-website/website/bootstrap-chain.json
TMP="${DST}.tmp.$$"
LOG=/var/log/sost-bootstrap-refresh.log
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
if [ ! -f "$SRC" ]; then
  echo "$(ts)  FATAL: $SRC missing" >> "$LOG"
  exit 2
fi
cp "$SRC" "$TMP"
# Validate JSON parses + has the expected top-level keys
# (chain_height, tip, blocks). If anything fails, drop the tmp and
# leave the live DST untouched.
if ! python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
assert isinstance(d.get('chain_height'), int) and d['chain_height'] > 0
assert isinstance(d.get('tip'), str) and len(d['tip']) == 64
assert isinstance(d.get('blocks'), list) and len(d['blocks']) > 0
print(d['chain_height'])
" "$TMP" > /tmp/.bootstrap_h.$$; then
  echo "$(ts)  FATAL: JSON validation failed on $TMP — leaving DST unchanged" >> "$LOG"
  rm -f "$TMP" /tmp/.bootstrap_h.$$
  exit 3
fi
H=$(cat /tmp/.bootstrap_h.$$); rm -f /tmp/.bootstrap_h.$$
SIZE=$(stat -c%s "$TMP")
mv -f "$TMP" "$DST"  # atomic rename
echo "$(ts)  refreshed: ${SIZE} bytes  chain_height=${H}" >> "$LOG"
```

Key safety property: the `mv -f "$TMP" "$DST"` is a same-filesystem
rename, which the kernel performs atomically. Concurrent downloads
either see the previous snapshot or the new one — they cannot see a
half-written file. If JSON validation fails, the live `$DST` is left
untouched and the failure is logged with the exact path, so the next
hour's cron tries again and the public bootstrap never serves an
invalid snapshot.

### The cron entry

`/etc/cron.d/sost-bootstrap-refresh`:

```
# Refresh the public bootstrap-chain.json snapshot from the live VPS
# node chain.json every hour. JSON-validates BEFORE the atomic rename.
# Log: /var/log/sost-bootstrap-refresh.log
17 * * * * root /usr/local/bin/sost-bootstrap-refresh.sh
```

Minute 17 (rather than 0 or */15) avoids piling on top of any other
top-of-the-hour jobs.

## How to re-install on a fresh VPS

```bash
# 1. Confirm the live chain.json path is correct for this host.
ls -lh /opt/sost/build/chain.json

# 2. Confirm the nginx-served public path exists.
ls -lh /var/www/sost-website/website/

# 3. Install the script (copy/paste the contents above).
sudo tee /usr/local/bin/sost-bootstrap-refresh.sh > /dev/null <<'EOF'
... (full script body) ...
EOF
sudo chmod +x /usr/local/bin/sost-bootstrap-refresh.sh

# 4. Install the cron entry.
sudo tee /etc/cron.d/sost-bootstrap-refresh > /dev/null <<'EOF'
17 * * * * root /usr/local/bin/sost-bootstrap-refresh.sh
EOF

# 5. Manual first run to seed the log and verify the script works.
sudo /usr/local/bin/sost-bootstrap-refresh.sh
tail /var/log/sost-bootstrap-refresh.log

# 6. End-to-end verification (as a user would do it).
curl -sI https://sostcore.com/bootstrap-chain.json | head -5
#   Content-Type: application/json
#   Content-Length: ~130000000  (≈ 124 MB)
curl -sL -o /tmp/b.json https://sostcore.com/bootstrap-chain.json
python3 -m json.tool /tmp/b.json > /dev/null && echo OK_JSON
rm /tmp/b.json
```

If step 6 reports `Content-Type: text/html` or a length around
`110000` bytes, the public path does NOT contain
`bootstrap-chain.json` and nginx is falling back to the homepage.
Re-check step 5 and that `/var/www/sost-website/website/bootstrap-chain.json`
exists with the expected ~124 MB size.

## How to verify health (regular operator check)

```bash
# Last refresh in log + size + parses.
tail -3 /var/log/sost-bootstrap-refresh.log

# Live HTTP check (run from anywhere, not just the VPS).
curl -sI https://sostcore.com/bootstrap-chain.json | grep -iE 'content-type|content-length'

# Compare advertised height vs live chain height.
ADVERTISED=$(curl -s https://sostcore.com/bootstrap-chain.json | head -c 200 | grep -oP '"chain_height":\s*\K[0-9]+')
LIVE=$(curl -s --user $RPC_USER:$RPC_PASS -X POST -H 'Content-Type: application/json' \
       -d '{"method":"getblockcount"}' http://127.0.0.1:18232/ | grep -oP '"result":\K[0-9]+')
echo "served=${ADVERTISED}  live=${LIVE}  drift=$((LIVE - ADVERTISED))"
```

A drift of 0–6 blocks at any point in the hour is normal (between
hourly refreshes); a drift > 60 blocks after the refresh has fired
suggests the cron stopped firing — check `systemctl is-active cron`
and `tail /var/log/syslog | grep cron`.

## How to force an immediate refresh

```bash
sudo /usr/local/bin/sost-bootstrap-refresh.sh
tail -1 /var/log/sost-bootstrap-refresh.log
```

Idempotent; safe to run as often as you like.

## How to roll back (disable the cron)

```bash
sudo rm /etc/cron.d/sost-bootstrap-refresh
# The script and the live file stay in place; only the auto-refresh
# stops. The currently-published bootstrap continues to serve until
# manually overwritten or removed.
```

To also stop serving the bootstrap entirely:

```bash
sudo rm /var/www/sost-website/website/bootstrap-chain.json
```

This will cause public downloads to revert to the same "served HTML
homepage" failure mode this runbook was created to prevent. Only do
it if the bootstrap path is being intentionally retired (announce
the change in the BitcoinTalk thread first).

## What this runbook does NOT cover

- Wallet operations, RPC credentials, P2P connectivity.
- The `chain.json` write semantics inside `sost-node` itself
  (`src/sost-node.cpp` chain-save path).
- Bandwidth limits for the public download.
- A CDN / mirror strategy for the bootstrap (none today; served
  directly by nginx).

If those topics need procedural docs, add them as separate runbooks
under `docs/runbooks/`.

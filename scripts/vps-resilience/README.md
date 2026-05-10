# SOST VPS RPC resilience

One-shot, idempotent fix for the recurring "sost-node alive but unresponsive
after ~24 h of uptime" incident. Root cause observed in production: thousands
of TCP connections in `TIME-WAIT` between nginx and `sost-node` on the
loopback (`127.0.0.1:18232`), exhausting the kernel's ephemeral-port
slots and leaving nginx waiting on upstream forever.

This directory ships everything needed to fix it permanently. Nothing here
touches consensus, the node binary, the miner, the wallet code, the RPC
schema, or transaction format. It is purely operational: kernel tuning,
nginx connection pooling, a systemd-driven RPC health probe with auto-
restart, and an hourly connection-count snapshot.

## Layout

| File                                   | Purpose                                             |
|----------------------------------------|-----------------------------------------------------|
| `apply.sh`                             | one-shot installer (run on the VPS as root)         |
| `sysctl-99-sost.conf`                  | TCP / TIME-WAIT kernel knobs                        |
| `nginx-patch.py`                       | adds `upstream sost_node { keepalive 32; }` and rewrites `proxy_pass` to use it over HTTP/1.1; idempotent |
| `health-check.sh`                      | curls `getinfo`; restarts sost-node on timeout/missing reply |
| `monitor-connections.sh`               | hourly `ss -tan | grep :18232` snapshot to a log    |
| `sost-health.service` + `.timer`       | runs `health-check.sh` every 5 min                  |
| `sost-conn-monitor.service` + `.timer` | runs `monitor-connections.sh` every hour            |

## Deploy

From the laptop:

```bash
ssh root@<vps> 'cd /opt/sost && git pull --ff-only origin main \
    && bash scripts/vps-resilience/apply.sh'
```

Or, if you prefer to run it locally on the VPS:

```bash
ssh root@<vps>
cd /opt/sost && git pull --ff-only origin main
bash scripts/vps-resilience/apply.sh
```

The installer is **idempotent**. Running it twice is safe; the second
run will report "already patched" on the nginx side and overwrite the
sysctl drop-in / scripts / unit files in place.

## Pre-requisite: `/etc/sost/rpc.env`

The health probe reads RPC credentials from `/etc/sost/rpc.env`. Create
it (mode `0600`, root-owned) before the first run:

```bash
install -d -m 0700 /etc/sost
cat > /etc/sost/rpc.env <<'EOF'
RPC_USER=<your-rpc-user>
RPC_PASS=<your-rpc-pass>
EOF
chmod 600 /etc/sost/rpc.env
```

If the file is missing the health probe logs a warning and skips the
restart-on-hang path (better than restarting the node every 5 min when
the probe cannot authenticate).

## What the patch does, layer by layer

### 1. `sysctl-99-sost.conf`

```text
net.ipv4.tcp_tw_reuse        = 1        # reuse TIME-WAIT slots safely
net.ipv4.tcp_fin_timeout     = 15       # drop FIN-WAIT/TIME-WAIT faster
net.core.somaxconn           = 4096     # bigger accept queue
net.ipv4.ip_local_port_range = 10000 65535
net.ipv4.tcp_max_tw_buckets  = 200000   # cap, instead of unlimited growth
```

This alone reduces the saturation half-life from ~24 h to weeks. It
does NOT remove the root cause (the lack of nginx-side pooling), so we
also do step 2.

### 2. nginx connection pool

`nginx-patch.py` looks for a SOST site (`/etc/nginx/sites-enabled/sost`,
`sostcore`, `sostcore.com`, or `conf.d/sost.conf`) and surgically adds:

```nginx
upstream sost_node {
    server 127.0.0.1:18232;
    keepalive 32;
    keepalive_requests 10000;
    keepalive_timeout 60s;
}
```

Then for every `proxy_pass http://127.0.0.1:18232;` in any `location {}`
block it switches to:

```nginx
proxy_pass http://sost_node;
proxy_http_version 1.1;
proxy_set_header  Connection "";
```

Result: nginx reuses 32 long-lived loopback TCP connections to sost-node
forever, instead of opening a fresh one per request. Pool of 2222 vs
pool of 32; the kernel-side `TIME-WAIT` figure stops growing.

`nginx -t` runs after the patch; on failure the original is restored
from the timestamped backup.

### 3. `health-check.sh` + `sost-health.{service,timer}`

`curl -m 10 getinfo` every 5 min:

- response carries `"blocks":N` → log `ok` + connection count
- timeout / non-200 / no `"blocks"` → log `CRITICAL` + `systemctl restart sost-node`

The first run is delayed 60 s after boot so a cold sost-node has time
to load the chain before the probe declares it unhealthy.

### 4. `monitor-connections.sh` + `sost-conn-monitor.{service,timer}`

Once an hour, dump

```text
[2026-05-10T12:00:00+00:00] total=37 6 ESTAB 28 TIME-WAIT 1 LISTEN 2 CLOSE-WAIT
```

to `/var/log/sost-conn-monitor.log`. If `total >= 500`, also touch
`/run/sost-conn-saturation` so an external alerting hook can fire.

### 5. `sost-node.service` drop-in

`/etc/systemd/system/sost-node.service.d/10-restart.conf` — adds:

```ini
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=10
TimeoutStartSec=60
TimeoutStopSec=30
```

If the binary segfaults or systemd's process-alive heartbeat fails,
systemd brings it back inside 10 s. The original unit is untouched
(drop-in is in a `.service.d/` subdirectory); to revert, `rm -rf` the
directory and `daemon-reload`.

## Verification

After `apply.sh` returns:

```bash
systemctl is-active sost-node sost-health.timer sost-conn-monitor.timer
ss -tan | grep ':18232' | awk '{print $1}' | sort | uniq -c
tail -f /var/log/sost-health.log /var/log/sost-conn-monitor.log
```

Expected steady state: `<50` total connections, `0` TIME-WAIT growth
across consecutive hourly snapshots, `health-check` writing `ok` lines.

## Reverting

The installer keeps a snapshot of every config it touched under
`/opt/sost/backups/<YYYYMMDD-HHMMSS>/`. To revert in full:

```bash
TS=<paste-timestamp>
cp -a /opt/sost/backups/$TS/sost                   /etc/nginx/sites-enabled/  # if present
cp -a /opt/sost/backups/$TS/sost-node.service      /etc/systemd/system/        # if present
rm -f /etc/sysctl.d/99-sost.conf
rm -f /etc/systemd/system/sost-health.{service,timer}
rm -f /etc/systemd/system/sost-conn-monitor.{service,timer}
rm -rf /etc/systemd/system/sost-node.service.d
systemctl daemon-reload
nginx -t && systemctl reload nginx
systemctl restart sost-node
```

## What this does NOT change

- consensus, validation rules, fee policy, sighash format
- `sost-node` binary
- `sost-miner` binary
- the RPC schema (no new methods, no removed methods)
- transaction wire format
- `params.h`, `transaction.h`
- the website code (explorer / wallet)

Pure operational hardening. Reversible. Idempotent.

# nginx RPC proxy — required headers + body limits

The repo's reference template lives at `deploy/sost-explorer.nginx`.
This note documents the **why** behind the non-obvious bits and the
exact patch the live VPS may still need.

## Symptom that motivated this note

`deploy/systemd/healthcheck.sh` reported, on 2026-04-30:

```
WARN  unauth getinfo returned 000000 (expected 200)
FAIL  authenticated sendrawtransaction returned empty body
```

- The **WARN** is intermittent connectivity to `/rpc/public` when the
  node is busy serving the local miner. The explorer round-2 fix
  (commit 43c9e96) makes that case degrade gracefully on the client
  side instead of stalling for 45 s.
- The **FAIL** is the actual nginx misconfiguration.

## Root cause of the FAIL

The default `location /rpc { ... }` did not contain:

```nginx
proxy_set_header Authorization $http_authorization;
proxy_pass_request_headers on;
```

Without these, nginx may strip the `Authorization` header on its way
to the upstream `127.0.0.1:18232`. The node then sees an
unauthenticated write (e.g. `sendrawtransaction`), refuses it, and
because the JSON-RPC handler closes the socket without writing a body
the client gets a 200 with an empty payload — exactly what the
healthcheck reported.

## Patch (already applied to the repo template)

`deploy/sost-explorer.nginx` now contains the canonical block:

```nginx
location /rpc {
    proxy_pass http://127.0.0.1:18232;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    # Forward Authorization to the node — fixes the empty-body FAIL.
    proxy_set_header Authorization $http_authorization;
    proxy_pass_request_headers on;

    # Body limits comfortably above any realistic raw TX hex.
    client_max_body_size    64k;
    client_body_buffer_size 64k;

    # Slightly longer than the wallet's 15 s per-call so a busy node
    # returning slowly does not look like a 504 to the client.
    proxy_connect_timeout 5s;
    proxy_send_timeout    20s;
    proxy_read_timeout    20s;

    limit_req zone=rpc burst=10 nodelay;

    # CORS (unchanged) ...
}
```

## Applying the fix on the live VPS

The repo change does not touch the running nginx. To apply on the
production host:

```bash
# 1. backup the live config (one-time before changes)
ssh root@212.132.108.244 \
  "cp /etc/nginx/sites-available/sost-explorer \
       /etc/nginx/sites-available/sost-explorer.bak-$(date +%Y%m%d)"

# 2. edit /etc/nginx/sites-available/sost-explorer to match
#    deploy/sost-explorer.nginx (or rsync the file in if symlinked)

# 3. validate before reload
ssh root@212.132.108.244 "nginx -t"

# 4. reload (no downtime)
ssh root@212.132.108.244 "systemctl reload nginx"

# 5. verify with the healthcheck
ssh root@212.132.108.244 "/opt/sost/deploy/systemd/healthcheck.sh"
```

The healthcheck should now show:

```
PASS  unauth getinfo returned 200
PASS  authenticated sendrawtransaction returned non-empty body
```

If the unauth `getinfo` still warns intermittently, that is the busy
node — not nginx — and the explorer client-side fix
(commit 43c9e96, v41) is the right place for that to be handled.

## Why `/rpc/public` is unaffected

`/rpc/public` is the read-only path; it does not require an
`Authorization` header in the first place, so the bug above did not
apply to it. Read-only methods (getinfo / getblock / getrawmempool)
worked all along; only authenticated writes were broken.

## Hard rules — what this change does NOT do

- It does NOT widen the rate-limit zone.
- It does NOT change CORS.
- It does NOT bypass auth on `/rpc` — auth is still required, the
  header just now actually reaches the node.
- It does NOT touch `/rpc/public`.

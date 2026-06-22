# SOST Public RPC Gateway

How the SOST web wallet (and any user) can broadcast a transaction on `sostcore.com`
without running a node, an SSH tunnel, or holding any RPC credentials — while the node
stays protected.

## Why it exists

The SOST node gates RPC **by method** (`rpc_is_readonly_method()` in `src/sost-node.cpp`):

- **Read** methods (`getblockcount`, `getbalance`, `getinfo`, `getrawtransaction`, …) — no auth.
- **Write** methods, including `sendrawtransaction`, and all admin methods (`stop`, `setban`,
  `generate*`, wallet methods, …) — require the node RPC credentials, else `-401 Authentication required`.

Consequence before this gateway: only someone with the node credentials (`/etc/sost/rpc.env`)
**and** network access to the node (SSH tunnel) could broadcast. A miner running their own node
could broadcast through *their* node; a website-only user could not broadcast at all.

Broadcasting a **signed** transaction is safe to expose publicly — the private keys are generated
and held in the user's browser, never sent anywhere; the node only validates and relays the signed
bytes (this is exactly how Bitcoin's public `sendrawtransaction` works).

## Design

```
browser wallet ──POST /rpc(/public)──> nginx ──> sost-rpc-proxy (127.0.0.1:18299) ──> node (127.0.0.1:18232)
                                       rate-limit          │
                                                           ├─ method == sendrawtransaction → inject node auth, forward
                                                           ├─ any other method             → forward WITHOUT auth
                                                           └─ reserialize a clean single-method body
```

Net effect at the node:

| Request | Auth injected? | Node result |
|---|---|---|
| reads (getblockcount, getbalance, …) | no | 200 (node allows reads) |
| `sendrawtransaction` (signed tx) | **yes** | 200 — broadcast |
| `stop` / `setban` / `generate*` / wallet* / any other write | no | **-401 blocked** |

The only method the gateway will authenticate is `sendrawtransaction`. Everything else relies on
the node's own gate, so the gateway can never *open* a dangerous method.

### Anti-smuggling

The gateway JSON-parses the request and **reserializes a canonical single-method body**
(`{jsonrpc, id, method, params}`), dropping any extra/duplicate fields. So a crafted body like
`{"method":"stop","method":"sendrawtransaction"}` cannot make the gateway authenticate while the
node executes a different method — the node receives exactly the one method the gateway decided on.

## Components

- **`ops/sost-rpc-proxy.py`** — the gateway (Python stdlib only). Deployed to `/opt/sost/sost-rpc-proxy.py`.
- **`ops/sost-rpc-proxy.service`** — systemd unit (`Restart=always`). Reads creds from `/etc/sost/rpc.env` at startup.
- **nginx** (`/etc/nginx/sites-enabled/sost`) — the `location /rpc` blocks `proxy_pass http://127.0.0.1:18299/`
  with `limit_req zone=rpc` (anti-spam). `/rpc/public` matches the same prefix location.
- **wallet** (`website/sost-wallet.html`) — `classifyRpcEndpoint` treats `/rpc` and `/rpc/public` as
  `PUBLIC` (broadcast allowed, no credentials). Default endpoint is `/rpc/public`.
- **tests** — `tests/test_rpc_proxy.py` locks the policy (only sendrawtransaction authenticated;
  single-method reserialization).

## Modifying the policy

To allow another method publicly, add it to `BROADCAST_METHODS` in `ops/sost-rpc-proxy.py`
(only do this for methods that are safe to expose) and update the test. Redeploy: copy the file to
`/opt/sost/sost-rpc-proxy.py` and `systemctl restart sost-rpc-proxy`.

## Operations

- **Status / logs:** `systemctl status sost-rpc-proxy` · `journalctl -u sost-rpc-proxy -f`
  (each request logs `method=… code=… auth_injected=…`; a spike of `code=401` = admin-method probing).
- **Health check:**
  ```
  curl -s -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"getblockcount","params":[]}' https://sostcore.com/rpc/public
  ```
- **Emergency rollback:** `systemctl disable --now sost-rpc-proxy` and restore the nginx backup
  (`/root/sost-nginx.bak-<timestamp>`) → `nginx -t && systemctl reload nginx`.

## Future hardening (optional)

The gateway is the single chokepoint, so these slot in here without touching the node:

- Per-IP broadcast quota (beyond nginx's `limit_req`) — e.g. N `sendrawtransaction`/min per IP.
- Reject obviously-malformed tx hex before forwarding (cheap pre-filter).
- Structured audit log to a file for longer retention.

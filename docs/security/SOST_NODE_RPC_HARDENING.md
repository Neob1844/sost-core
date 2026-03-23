# SOST Node & RPC Hardening Guide

## Default Security Posture

SOST node binds RPC to `127.0.0.1:18232` by default (localhost only).
P2P listens on `0.0.0.0:19333` (all interfaces).

## Recommended Configuration

### sost.conf (create in ~/.sost/ or alongside binary)

```ini
# === RPC Security ===
# NEVER bind RPC to 0.0.0.0 unless behind a firewall
rpc-bind=127.0.0.1
rpc-port=18232
rpc-user=sostoperator
rpc-pass=<strong-random-password-here>

# === P2P ===
p2p-port=19333
# Limit inbound connections if on a resource-constrained machine
# max-inbound=32

# === Logging ===
# Enable detailed logging for security audit
# log-level=debug
```

### Dangerous RPC Methods (Inventory)

| Method | Risk | Recommendation |
|--------|------|----------------|
| `dumpprivkey` | CRITICAL — exposes private key | Disable in production, warn in docs |
| `importprivkey` | HIGH — accepts external key | Verify source, use only for recovery |
| `send` | HIGH — moves funds | Require confirmation flow |
| `getnewaddress` | LOW — generates key | Safe, but keys need backup |
| `getbalance` | LOW — reads balance | Safe |
| `getblockchaininfo` | NONE — read only | Safe |
| `getblock` / `gettx` | NONE — read only | Safe |
| `stop` | MEDIUM — stops node | Restrict to operator |
| `submitblock` | LOW — mining only | Safe for miners |

### Firewall Rules (iptables example)

```bash
# Allow P2P from anywhere
iptables -A INPUT -p tcp --dport 19333 -j ACCEPT

# Allow RPC ONLY from localhost
iptables -A INPUT -p tcp --dport 18232 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 18232 -j DROP

# Rate limit P2P connections
iptables -A INPUT -p tcp --dport 19333 -m connlimit --connlimit-above 8 -j DROP
```

### systemd Service Hardening

```ini
[Service]
# Drop privileges
User=sost
Group=sost
# Restrict filesystem
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/sost/.sost
# No new privileges
NoNewPrivileges=true
# Restrict capabilities
CapabilityBoundingSet=
# Private /tmp
PrivateTmp=true
```

## Monitoring

### Critical Events to Watch
- RPC authentication failures (brute force)
- Peer ban events (network attacks)
- Wallet unlock/lock events
- Large outgoing transactions
- Node process crashes/restarts

### Log Locations
- Node stdout/stderr (capture via systemd journal)
- Wallet operations (currently not logged to file — recommended addition)

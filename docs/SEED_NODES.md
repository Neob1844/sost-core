# SOST seed nodes & community bootnodes

This is a **P2P-only** topic — seeds affect peer discovery and block propagation,
**not consensus**. Adding/removing seeds never forks the chain.

## Why multiple seeds

Until V14.5 the node bootstrapped from a single seed (`seed.sostcore.com`, EU).
A single EU seed bottlenecks far-away miners: an APAC/US miner finds a valid block,
but by the time it crosses to the EU seed a closer miner has already propagated
theirs, so the far block is orphaned (`[FORK] ... LESS cumulative work`). One seed
being down can also isolate a fresh node entirely.

From V14.5 the node tries **several geographically-distributed default seeds** and
connects to up to 3, tolerating any being down. Peer exchange grows the mesh from
there.

## Default seeds (compiled in)

The node, when started **without `--connect`**, tries in order and connects to up to 3:

| Hostname | Region | Notes |
|---|---|---|
| `seed-eu.sostcore.com`   | Europe        | primary (current Germany VPS) |
| `seed-apac.sostcore.com` | Asia-Pacific  | Singapore/Sydney or a community node |
| `seed-us.sostcore.com`   | North America | US VPS |
| `seed.sostcore.com`      | (alias → EU)  | backward-compatible; kept so old configs/docs still work |

Hostnames that don't resolve yet (before their DNS/node exists) **fail closed and
are skipped** — the node degrades gracefully to EU-only until the regional records
are added. No binary change is needed to bring a regional seed online once its DNS
record points at a running node.

## DNS checklist (operator)

Set these A-records (point at the public IPv4 of a running V14.5 node, P2P port 19333 open):

- [ ] `seed-eu.sostcore.com`   → current Germany VPS
- [ ] `seed-apac.sostcore.com` → APAC VPS **or** a vetted community node (e.g. the New Caledonia/APAC miner)
- [ ] `seed-us.sostcore.com`   → US VPS
- [ ] `seed.sostcore.com`      → keep pointing to EU (or DNS round-robin across the three later)

Verify each: `getent hosts seed-apac.sostcore.com` and `nc -vz <host> 19333`.

## Running an OFFICIAL seed (operator-controlled)

Requirements:
- A small always-on VPS in the target region. A seed **does not mine**, so it needs
  far less RAM than a miner (~2–4 GB is fine; chain state is a few hundred MB and grows).
- Public **IPv4**, **P2P port 19333 open** (firewall/security-group inbound TCP 19333).
- The **V14.5 mainnet binary** (it validates + relays blocks, so it must be consensus-correct):
  ```
  git checkout main && git pull origin main
  cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
  cmake --build build --target sost-node sost-cli -j$(nproc)
  ./build/sost-node --genesis genesis_block.json --chain chain.json --profile mainnet
  ```
- Run it under a service manager (systemd) with auto-restart, and keep it updated.
- Point the regional DNS record at its IP.

Cheap regional VPS providers: **Vultr, DigitalOcean, OVH** (all have Singapore / Sydney / US), Linode/Akamai, Hetzner (US/EU), Contabo.

## Running a COMMUNITY bootnode (anyone)

You do **not** need to be in the default list to help the network — any public node
strengthens the mesh. To run a public bootnode:
- Same build as above (V14.5 mainnet binary).
- Open **TCP 19333** inbound; have a **static/public IP** (or a dynamic-DNS hostname).
- Start the node normally; it will accept inbound peers and relay blocks/txs.
- Share your `ip:19333` so others can `--connect` to you. Reliable, long-lived
  community bootnodes may be added to the default seed list after vetting.

## `--connect` examples (operators/miners)

Bootstrap from specific peers instead of (or in addition to) the defaults:
```
# one explicit peer
./build/sost-node ... --connect 203.0.113.10:19333
# a closer regional seed
./build/sost-node ... --connect seed-apac.sostcore.com:19333
# the default behaviour (no --connect): tries seed-eu / seed-apac / seed-us / seed.sostcore.com
./build/sost-node ...
```
A node far from Europe should prefer a closer seed (`seed-apac`/`seed-us`) to cut
propagation latency and reduce orphaned blocks.

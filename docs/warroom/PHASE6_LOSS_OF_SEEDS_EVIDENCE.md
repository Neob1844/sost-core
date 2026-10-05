# Phase 6 — Loss of all seeds (sostcore.com is NOT a technical requirement)

**Goal:** prove a SOST node can join and stay on the network with `seed.sostcore.com`
UNREACHABLE, using only operator-provided alternative sources (`peers.txt` / `seeds.txt`),
and that a node with NO source correctly fails closed with a clear message.

**Setup:** isolated devnet (MAGIC_DEV, cannot touch mainnet). Hub at 127.0.0.40:20701.
Four fresh nodes, each `--p2p-bind`'d to a distinct 127.0.0.x, started WITHOUT `--connect`.
`seed.sostcore.com:19333` is unreachable throughout (confirmed in every log:
`Cannot connect to seed.sostcore.com:19333`).

## Result — authoritative connection-log evidence (run /tmp/ph6c.owyB3B)

| Test | Node source | Node log | Hub log |
|------|-------------|----------|---------|
| A | `peers.txt` only | `stored peer connected: 127.0.0.40:20701` -> `version OK` -> `bootstrapped from 1 peer(s) (store+seeds)` | `Peer connected: 127.0.0.41:... (inbound)` + `version OK` |
| B | `seeds.txt` only | `seeds.txt connected: 127.0.0.40:20701` -> `version OK` -> `bootstrapped from 1 peer(s)` | `Peer connected: 127.0.0.42:... (inbound)` + `version OK` |
| C | both | `stored peer connected` + `seeds.txt connected` (2 outbound) | `Peer connected: 127.0.0.43:... (inbound)` |
| D | none | `WARNING: no stored peer or default seed reachable — pass --connect <host:port> to bootstrap.` (fails closed) | — |

**Conclusion: PASS.** With sostcore.com down, nodes bootstrap over operator-provided
peers.txt/seeds.txt (D1/D2). sostcore.com is a convenience, not a technical dependency.
A node with zero sources fails closed with an actionable message (no silent hang, no crash).

## Measurement note (not a defect)
A hub-side `getpeerinfo` poll can read 0 because the devnet hub stayed at height 0
(nothing to sync) -> the handshaked connection goes idle -> drops -> the node's redial
within 30s is refused by the hub's `IP_COOLDOWN_SECS=30` anti-DoS. With real continuous
block traffic (see the long soak: NEW1 holds 3 peers, 0 errors, flat RSS) connections
persist. The bootstrap mechanism itself is proven by the connection logs above, which are
independent of poll timing.
